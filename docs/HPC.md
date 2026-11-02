# Sheffield / SLURM pathway (prepared, not executed)

The local matrix and analysis are the MVP. No cluster login or job submission
was attempted. This is a **single-node process-parallel workload**, not MPI.
More nodes can run independent campaigns; they do not jointly decode a shot.

## How QStone is reused

`scripts/generate_slurm.py` calls QStone's real `generate_suite(..., atomic=True,
scheduler="slurm")` in a temporary directory. It saves the original archive,
configuration and sbatch output, then adapts that output for this offline job.
The audited template's Git blob hash is verified before adaptation.

The generated `#SBATCH` account, time, node, job-name and log directives are
retained. We set QStone `nthreads=1` because its template emits `-N nthreads`
(**nodes**, not CPU threads). We explicitly add `--ntasks=1`,
`--cpus-per-task=4`, and `--mem=4G`. The CPU count comes from the matrix maximum.
The generated QPU stage body is replaced with the offline benchmark command;
QStone's registry, QPU connectors and tracing do not execute in this path.
This is transparent template reuse, not an unmodified QStone application or a
new scheduler/orchestration framework.

Inspect the generated files in `slurm/generated/`. The placeholder account
`CHANGE_ME` must be replaced by regenerating with your actual allocation.
Nothing in this generator submits jobs.

## Prepare the environment

Use an allocated interactive compute session for installs/tests where required
by Sheffield policy; do not run benchmarks on login nodes. Check the current
[Stanage Python documentation](https://docs.hpc.shef.ac.uk/en/latest/stanage/software/apps/python.html)
for modules available on your selected node type. The example uses the documented
Python 3.10.8 module, matching the local major/minor Python version.

On the cluster, from your project directory:

```bash
module load Python/3.10.8-GCCcore-12.2.0
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_scaling.py --config configs/smoke.json --output scratch/smoke
```

The Linux environment must be built afresh; do not copy the Windows venv or
Windows wheels. Keep the module identical during installation and execution.
If this module is unavailable, select an available Python 3.10–3.12 module and
set `QEC_PYTHON_MODULE` accordingly. Inspect wheel availability and verify tests.

## Generate using audited QStone source

This can be done locally (no SLURM needed) or on the cluster:

```bash
git clone https://github.com/riverlane/QStone.git ../QStone
git -C ../QStone checkout 49375fce635259eaea910b1bfede58483bc8e937
python -m pip install -r requirements-qstone-generator.txt
python scripts/generate_slurm.py --qstone-source ../QStone --account YOUR_ACCOUNT
```

Only the source checkout and generator dependencies are needed to generate.
The full QStone package brings additional QPU backends unrelated to this job.
The generator-only import was exercised locally against the pinned checkout.
An upstream template change requires renewed inspection rather than silently
using stale assumptions.

## Submit only after inspection and local smoke validation

```bash
export QEC_PROJECT_DIR="$PWD"
export QEC_VENV="$PWD/.venv"
export QEC_PYTHON_MODULE=Python/3.10.8-GCCcore-12.2.0
# Inspect account, module, memory, time, CPU count and storage paths first.
sbatch --export=ALL slurm/generated/qec.sbatch
```

Consult [Sheffield job submission guidance](https://docs.hpc.shef.ac.uk/en/latest/hpc/scheduler/index.html)
for account/partition requirements of your allocation. If needed, add a verified
partition/QoS via `sbatch` options; no partition name is guessed here. The initial
request is one node, one parent task, four CPUs, 4 GB RAM, 30 minutes. Verify
actual memory and runtime on the first job before enlarging the matrix.

`srun --cpu-bind=cores` gives the parent an allocated CPU mask that spawn workers
inherit. It does not pin each worker to its own physical core. The runner refuses
worker counts exceeding visible affinity or `SLURM_CPUS_PER_TASK`. BLAS/OpenMP
threads are limited to one to avoid nested oversubscription. Baseline trials use
one active worker within the same four-CPU allocation; efficiency is relative
to active worker count, not whole-allocation utilisation.

## Results, storage and aggregation

Temporary NPY input uses `QEC_TMPDIR`, set to `SLURM_TMPDIR`, `TMPDIR`, or `/tmp`.
Confirm that path exists and has enough space. Result JSONL and metadata are
written beneath the repository's `results/` directory, which must be on durable
storage. Run directories combine UTC timestamp and UUID; metadata contains host,
allocation variables, config/software/source hashes and seeds.

Run all worker counts in one job so the one-worker baseline and comparisons
share a node. Analyse completed results on a permitted analysis machine:

```bash
python analyse_results.py results/NEW_RUN_ID --output figures/stanage-run
```

Multiple disjoint worker-filtered runs can be passed as multiple directories,
but analysis groups by host/software/config/source/label and requires a serial
baseline within each cohort. Separate nodes must each run a serial baseline;
cross-node speedup ratios would mix hardware effects with scaling. Duplicate
case/repetition rows are rejected, so analyse independent full reruns separately.
Retain raw observations; do not average pre-aggregated medians across machines.

After execution inspect `sacct -j JOB_ID` and `seff JOB_ID`, alongside the runner
metadata and repetition counts. Scheduler MaxRSS/CPU accounting supplements the
worker RSS snapshots; it was not available for the local results. Record those
as new HPC evidence only once the jobs have actually completed.
