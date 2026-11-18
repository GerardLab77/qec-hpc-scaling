# Persistent-pool experiment

The first campaign completed successfully on Stanage. All 150 sessions and
5,550 batches passed completeness, worker-reuse and paired-output validation.
Raw data are in `results/persistent/20261118T190200Z-ceaad759`; reports and
figures are in `figures/persistent-12198916`. The existing single-batch benchmark
and its raw results are unchanged. For a fresh campaign, run tests and smoke first.

## Measured findings

For one million shots per batch and 16 workers, median paired speedups were:

| Batches per pool | Dispatch only | Setup + dispatches + shutdown | Full workload |
|---:|---:|---:|---:|
| 1 | 15.152x | 0.286x | 0.422x |
| 10 | 15.383x | 2.057x | 1.298x |
| 100 | 15.348x | 9.203x | 1.815x |

These use same-seed one-worker baselines within this campaign, not baselines
from the earlier scaling allocation. Values below 1 mean slower execution.
The full-workload time reduction at 100 batches is approximately
`1 - 1 / 1.815 = 44.9%`. This is a median paired result, not a ratio of median
throughputs. At 100,000 shots and 100 batches, eight workers had a 1.743x
full-workload speedup, compared with 1.432x for 16 workers. The observed median
16-worker crossover is between 1 and 10 batches for the million-shot case,
and between 10 and 100 batches for the smaller case. No exact break-even
point or statistical significance is inferred from that grid.

See `speedup_summary.csv` for quartiles and `paired_speedups.csv` for all
individual paired ratios. No failure counts are pooled across reused datasets.

## Question and controls

How many batches must a pool process before worker startup is amortised, and
does useful overall speedup follow the warmed dispatch speedup?

The full matrix uses distance 5, five rounds, p=0.005, 100,000 and 1,000,000
shots per batch, 1/2/4/8/16 workers and 1/10/100 batches per pool. There are
five repetitions: 150 fresh pool sessions, 5,550 timed batch dispatches and
3,052,500,000 decoded shots across the whole campaign. This is substantially
more work than the first Stanage campaign. The two-hour request is a runtime
ceiling, not a measured requirement; inspect scheduler accounting afterwards.

Each batch gets its own seed, sampler and fresh data. The same repetition,
batch size and batch index produce the same input across worker counts and
batch budgets, verified by analysis. Repetition seeds are separated by the
largest batch budget, preventing accidental overlap between repetitions.
Smaller batch budgets use prefixes of the larger budget's seed sequence.
Those reused datasets are paired controls, not additional independent logical
error observations. Do not pool failure counts across worker counts or budgets.

One pool is created per session, warmed on up to 256 shots per worker from the
first input batch, then reused for all batches. A barrier requires all workers
to participate; worker PID sets are checked on every dispatch. Batch files are
opened in each task and closed before overwriting the single temporary input
file. At most one input batch is retained, not 100 million shots in memory.
These input-map operations are included in dispatch time, unlike the original
benchmark's permanently mapped single input. Compare this experiment against
its own one-worker baseline rather than mixing ratios with old observations.

## Three timing boundaries

| Metric | Boundary |
|---|---|
| Warmed throughput | Total shots / sum of batch dispatch times. Includes input-map open/close, barrier, decode and prediction IPC. |
| Service throughput | Total shots / (pool setup and warmup + dispatch sum + shutdown). An accounted sum that excludes input preparation and parent validation. |
| Full workload throughput | Total shots / measured workload wall time, including model construction, sampling, input hashing/writes, startup, warmup, dispatches, parent validation, batch-log flushes, shutdown and temporary-file cleanup. |

The full workload is a synchronous simulation-and-decoding pipeline. It does
not overlap sampling with decoding and is not a production streaming service.
It excludes runner imports, configuration/metadata creation and the final
session-summary write. Metadata collection and analysis are also outside it.
Full-workload speedup can be limited by serial input generation or logging
even when decoder service scales well. No single-shot latency is measured.

For each timing boundary, speedups are paired against a one-worker session
with identical controls, repetition and seeded batch sequence. Summaries show
median and quartiles across sessions; batches in one session are not treated
as independent startup repetitions. The smallest tested budget with median
speedup above 1 is an observed crossover on this grid, not a precise break-even
point. Inspect quartiles and individual repetitions before drawing conclusions.

## Test and smoke commands

Use the existing virtual environment. These commands are for you to execute.
On Stanage, run tests and analysis in an allocated compute session, not on a
login node. Request two CPUs because correctness tests compare two workers.

```bash
python -m unittest discover -s tests -v
python persistent_pool.py --config configs/persistent-smoke.json --output scratch/persistent-smoke
python analyse_persistent.py scratch/persistent-smoke/PRINTED_RUN_ID --output scratch/persistent-smoke-analysis
```

Smoke should validate four sessions and eight batches. The main campaign
should validate 150 sessions and 5,550 batches. Use the actual printed run
directory, not a parent directory containing multiple runs.

## Main Stanage submission

From the repository root on the login node, after tests and smoke pass:

```bash
bash -n slurm/persistent.sbatch
sbatch --test-only slurm/persistent.sbatch
sbatch slurm/persistent.sbatch
squeue --me
```

The script requests one node, 16 CPUs, 16 GB and up to two hours. It uses the
same Python module already tested on Stanage. It relies on your permitted
default account/partition, as the first successful campaign did. It does not
request exclusive ownership of the node or pin workers individually. Confirm
any account-specific limits before enlarging it. No network access or install
is performed by the batch script.

```bash
sacct -j JOB_ID --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS
tail -n 20 qec-persistent-JOB_ID.out
```

Each run has metadata, `persistent_batches.jsonl` (flushed after each batch),
`persistent_measurements.jsonl` (flushed after each completed pool session)
and a `COMPLETE` marker written only on success. Partial files are retained
for diagnosis, but analysis rejects incomplete campaigns, missing or duplicate
cases, missing batches, changed workers and mismatched parallel outputs.

In an allocated analysis session:

```bash
python analyse_persistent.py results/persistent/PRINTED_RUN_ID --output figures/persistent-JOB_ID
```

Outputs include per-session timings, timing summaries, per-repetition paired
speedups, speedup summaries and PNG figures for all three timing boundaries.
Raw batch rows retain individual dispatch times and worker decode times. Retain
the raw run directory, config, script, scheduler log and analysis together.
The old `analyse_results.py` intentionally ignores these new filenames.
