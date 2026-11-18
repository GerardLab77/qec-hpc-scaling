#!/bin/bash
#SBATCH --job-name=qec-scaling
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --hint=nomultithread
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=qec-%j.out

set -eo pipefail
cd "$SLURM_SUBMIT_DIR"

module load Python/3.10.8-GCCcore-12.2.0
source .venv/bin/activate
set -u

export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export SLURM_EXPORT_ENV=ALL
export QEC_TMPDIR="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}"
test -d "$QEC_TMPDIR" && test -w "$QEC_TMPDIR"

date -u
hostname

srun --export=ALL --ntasks=1 \
  --cpus-per-task="$SLURM_CPUS_PER_TASK" --cpu-bind=cores \
  python -u run_scaling.py \
    --config configs/stanage.json \
    --output results \
    --label stanage-scaling

date -u
