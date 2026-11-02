"""Reuse QStone's generator; adapt its SLURM header for an offline CPU benchmark.

No job is submitted. QStone's original archive is retained for inspection.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
from pathlib import Path

PIN = "49375fce635259eaea910b1bfede58483bc8e937"
TEMPLATE_BLOB = "989244473a19a431327e67c1e0893391a2a6a8e5"


def generate(source, account, config_path, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", account):
        raise ValueError("Account must contain only letters, numbers, _ or -")
    config_path = Path(config_path)
    if config_path.is_absolute() or ".." in config_path.parts:
        raise ValueError("Config must be a repository-relative path")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cpus = max(w for exp in config["experiments"] for w in exp["workers"])
    template = source / "qstone/generators/slurm/schedmd/type_exec_{app}.sbatch.jinja"
    data = template.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob != TEMPLATE_BLOB:
        raise ValueError("QStone template differs from audited version; inspect before adapting")
    sys.path.insert(0, str(source))
    from qstone.generators.generator import generate_suite
    qconfig = {
        "environment": {
            "project_name": account, "job_count": 1, "scheduling_mode": "NONE",
            "qpu": {"mode": "EMULATED"},
            "connectivity": {"mode": "NO_LINK", "qpu": {"ip_address": "127.0.0.1", "port": 0}},
        },
        "jobs": [{"type": "OfflineQEC", "qubits": [1], "num_shots": [1],
                  "nthreads": 1, "walltime": "00:30:00", "app_args": {}, "app_logging_level": 2}],
        "users": [{"user": "qec", "computations": {"OfflineQEC": 1.0}}],
    }
    output.mkdir(parents=True, exist_ok=True)
    qconfig_path = output / "qstone-config.json"
    qconfig_path.write_text(json.dumps(qconfig, indent=2), encoding="utf-8")
    # QStone uses a fixed temporary directory relative to cwd. Isolate it.
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="qstone-generate-") as temporary:
        try:
            os.chdir(temporary)
            archives = generate_suite(str(qconfig_path), 1, str(output), True, "slurm")
        finally:
            # Windows cannot remove a directory while it is the process cwd.
            os.chdir(original_cwd)
    with tarfile.open(archives[0], "r:gz") as archive:
        file = archive.extractfile("qstone_suite/type_exec_OfflineQEC.sbatch")
        if file is None:
            raise RuntimeError("QStone generated no expected SLURM launcher")
        original = file.read().decode("utf-8")
    (output / "qstone-original.sbatch.txt").write_text(original, encoding="utf-8")
    header = "\n".join(line for line in original.splitlines()
                       if line.startswith("#!") or line.startswith("#SBATCH"))
    if "#SBATCH -N 1" not in header:
        raise RuntimeError("Unexpected QStone node allocation")
    body = f'''\n#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem=4G

# Offline adapter: QStone stage/QPU execution is intentionally replaced.
set -euo pipefail
: "${{QEC_PROJECT_DIR:?Set QEC_PROJECT_DIR to the repository on the cluster}}"
: "${{QEC_VENV:?Set QEC_VENV to the virtual environment on the cluster}}"
module load "${{QEC_PYTHON_MODULE:-Python/3.10.8-GCCcore-12.2.0}}"
source "$QEC_VENV/bin/activate"
cd "$QEC_PROJECT_DIR"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export QEC_TMPDIR="${{SLURM_TMPDIR:-${{TMPDIR:-/tmp}}}}"
export SLURM_EXPORT_ENV=ALL
# One parent task; its spawn workers inherit the allocated CPU affinity.
# All worker counts run within the same node allocation for paired comparisons.
srun --export=ALL --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" --cpu-bind=cores \\
  python run_scaling.py --config {config_path.as_posix()} --output results --label stanage
'''
    (output / "qec.sbatch").write_text(header + body, encoding="utf-8", newline="\n")
    (output / "provenance.json").write_text(json.dumps({
        "qstone_commit_inspected": PIN, "verified_template_git_blob": blob,
        "config": str(config_path), "cpus_per_task": cpus,
        "status": "generated locally; not submitted or validated on SLURM",
        "adaptation": "Preserve generated header, nthreads=1 (one node); add task/CPU/memory requests; replace QPU stage commands with offline runner",
    }, indent=2), encoding="utf-8")
    print(output / "qec.sbatch")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qstone-source", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--config", default="configs/local.json")
    parser.add_argument("--output", default="slurm/generated")
    args = parser.parse_args()
    generate(args.qstone_source, args.account, args.config, args.output)
