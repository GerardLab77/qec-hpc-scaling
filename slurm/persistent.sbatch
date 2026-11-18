#!/bin/bash
#SBATCH --job-name=qec-persistent
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --hint=nomultithread
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=qec-persistent-%j.out

set -eo pipefail
cd "$SLURM_SUBMIT_DIR"
module load Python/3.10.8-GCCcore-12.2.0
source .venv/bin/activate
set -u
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export SLURM_EXPORT_ENV=ALL
export QEC_TMPDIR="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}"
if [[ ! -d "$QEC_TMPDIR" || ! -w "$QEC_TMPDIR" ]]; then
  echo "Temporary input directory is missing or not writable: $QEC_TMPDIR" >&2
  exit 1
fi
# Capture scheduler context outside dispatch timers.
date -u
hostname
srun --export=ALL --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" --cpu-bind=cores \
  python -u persistent_pool.py --config configs/persistent-stanage.json \
    --output results/persistent --label stanage-persistent
date -u
