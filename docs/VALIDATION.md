# Validation record

Completed locally on 1 November 2026:

- Four benchmark correctness tests: uneven partition coverage; noiseless
  logical memory; batch vs individual-shot predictions; one vs two processes
  with identical inputs, predictions and failure counts.
- Three analysis tests: median/IQR; reject mismatched input hashes; paired
  speedup and efficiency use the correct serial baseline.
- Smoke matrix: four actual measurements, two seeds, one/two workers.
- Main matrix: 60 actual measurements, 12 cases, five seeds, 3,705,000 shots.
- Analysis validates all seed-paired parallel input/prediction hashes before
  computing speedups. Both generated PNGs were visually inspected.
- QStone `generate_suite` called against the pinned source; original archive
  retained; audited template hash checked; adapted sbatch file inspected.
- Generated sbatch file passed `bash -n` using Git Bash. No SLURM execution.
- Observed Windows CPU accounting quantisation (15.625 ms increments, 11 zero
  short-trial CPU totals): CPU utilisation omitted from summary statistics.

The GitHub Actions workflow is supplied but has not run on GitHub. Linux/HPC
execution, scheduler accounting, NUMA effects and persistent-pool throughput are
future validations, not completed checks.

The main measurement preceded local git initialisation. Its metadata therefore
records null git revision plus the actual measurement-time source hashes.
The benchmark and runner sources are unchanged from that measured version;
analysis, documentation and HPC tooling were completed afterwards.
