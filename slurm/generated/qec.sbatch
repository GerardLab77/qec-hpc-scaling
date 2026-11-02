#!/bin/bash
#SBATCH -A CHANGE_ME
#SBATCH -t 00:30:00
#SBATCH -N 1
#SBATCH -J QStone
#SBATCH -o out.%J
#SBATCH -e err.%J
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G

# Offline adapter: QStone stage/QPU execution is intentionally replaced.
set -euo pipefail
: "${QEC_PROJECT_DIR:?Set QEC_PROJECT_DIR to the repository on the cluster}"
: "${QEC_VENV:?Set QEC_VENV to the virtual environment on the cluster}"
module load "${QEC_PYTHON_MODULE:-Python/3.10.8-GCCcore-12.2.0}"
source "$QEC_VENV/bin/activate"
cd "$QEC_PROJECT_DIR"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export QEC_TMPDIR="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}"
export SLURM_EXPORT_ENV=ALL
# One parent task; its spawn workers inherit the allocated CPU affinity.
# All worker counts run within the same node allocation for paired comparisons.
srun --export=ALL --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" --cpu-bind=cores \
  python run_scaling.py --config configs/local.json --output results --label stanage
