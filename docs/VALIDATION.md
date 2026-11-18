# Validation record

## Stanage campaigns, 18 November 2026

The operator ran the tests and experiments; no agent-side SSH or VPN session
was used. All 16 tests passed in the local Windows checkout and on Stanage
before the persistent campaign. The persistent smoke run validated four pool
sessions and eight batches, including matching parallel predictions and stable
worker PID sets. The new tests reject incomplete batches, duplicate sessions,
missing baselines, invalid configs, seed overflow and mismatched predictions.

- Scaling: 65 measurements, 13 cases, five repetitions; 1/2/4/8/16 workers.
  Raw directory: `results/20261118T180740Z-0775c4d9`.
- Persistent pools: 150 sessions, 5,550 batches; five repetitions per case.
  Raw directory: `results/persistent/20261118T190200Z-ceaad759`.
  A `COMPLETE` marker accompanies the raw data. The analyser validated all
  configured cases, batch seeds, worker reuse and paired outputs.
- Operator-supplied scheduler accounting reported `COMPLETED`, exit code
  `0:0`, elapsed 00:03:35 and 01:49:04 respectively. Both used 16 allocated CPUs.
- Configs, scripts, raw data, metadata, CSV summaries, PNGs and stdout logs
  are retained. The measurements were made from a dirty checkout of revision
  `9929de6`; source hashes identify the actual code, including the new files.

Before publication, the imported raw data were re-analysed without rerunning
benchmarks. All four persistent CSV reports matched recomputation exactly;
both original timed modules and the persistent benchmark matched their
measurement-time source hashes. The scaling analyser's plot was updated to
label the actual fixed round count and show one-worker scaling baselines when
no separate batch-size family exists. This changes presentation, not timings.

These are two individual allocations with within-allocation repetitions, not
independent replications across the cluster. No 32-worker, multi-node, NUMA,
individual-worker pinning or real-time latency results are claimed.

## Original desktop validation

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

At the time of this original desktop record, Linux/HPC execution and
persistent-pool throughput were future work. They are now covered by the
Stanage record above. CI status is reported by GitHub Actions separately;
NUMA effects remain unmeasured.

The main measurement preceded local git initialisation. Its metadata therefore
records null git revision plus the actual measurement-time source hashes.
The benchmark and runner sources are unchanged from that measured version;
analysis, documentation and HPC tooling were completed afterwards.
