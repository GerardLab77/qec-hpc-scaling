# Measurement contract

## Workload

Stim `surface_code:rotated_memory_x`, odd distance d, rounds=d. Only
`after_clifford_depolarization=p` is enabled (p=0.005). This is the same noise
parameter used by QStone's built-in example, **not** a calibrated hardware noise
model or a claim of uniform physical error rate across every operation. Each
shot simulates an entire logical-memory experiment. Detector events and true
logical observables are generated together; MWPM predicts the logical flips.
The detector error model is decomposed into graphlike errors; default
uncorrelated PyMatching decoding is used. No correlations-enabled comparison.

## Timing boundaries

| Field | Includes | Excludes |
|---|---|---|
| model_s | circuit + detector error model construction in parent | worker graph construction |
| sample_s | sampler compilation + all shots | file writing, decoding |
| pool_setup_warmup_s | process spawn, worker imports, decoder construction, mmap, up to 256 warmup shots/worker | main timed batch |
| dispatch_s | submitting W tasks, barrier rendezvous, decode, worker instrumentation, returning predictions through IPC | pool setup, sampling, parent concatenation and validation, shutdown |
| worker_decode_max_s | slowest worker's timed decode call | barrier, IPC, RSS inspection |
| worker_cpu_sum_s | sum of process CPU time within decode calls | parent CPU and IPC CPU |

`shots / dispatch_s` is the primary warmed-pool throughput. `dispatch_s/shots`
is **amortized batch cost**, not individual shot latency. The maximum worker
decode time is a diagnostic, not perfectly aligned global critical-path timing.
RSS is summed worker resident memory immediately after decode, not peak memory;
shared pages may be counted more than once. CPU percent is worker decode CPU
seconds divided by dispatch wall seconds times 100 (100% = one busy CPU); it
is not whole-system utilisation. In the initial Windows run, CPU accounting was
quantised (some short decodes returned zero CPU time); these raw fields are
retained for audit but omitted from the statistical summary and not interpreted.
Reassess CPU timer resolution on Linux before using this diagnostic.
No sampling profiler is used to avoid perturbing
short calls. No performance counters, NUMA placement or isolated cores locally.

Workers load the pre-generated same NPY file read-only using memory mapping.
They warm on their first 256 shots and page in the rest during the timed decode.
Thus input access/cache effects are included. No full input array is sent by IPC;
predictions are returned by IPC. Every timed task waits at a W-party barrier,
ensuring W distinct worker processes participate. The parent checks prediction
shape. Tests compare noiseless, batch/single, and process-split decoding.

## Statistics and reproducibility

Five fresh-data, fresh-pool repetitions per case. Seeds are 20261101 through
20261105. The same seed/configuration/shot count yields identical input and
prediction hashes across worker counts in this pinned environment. All cases
are shuffled within a repetition with a separate seeded Python RNG. Smaller
batches are not assumed to be prefixes of larger batches. Stim seed portability
across different versions, machines and sampling call patterns is not promised.

Median and quartiles describe repeated timing variability; no significance
tests or claims from small differences. Speedups are **paired** on seed and
repetition, verified by input and prediction hashes, before taking medians/IQR.
Every parallel comparison has a one-process pool baseline, never an in-process
baseline with different dispatch costs. Efficiency = speedup / worker count.

Logical error probability is a secondary correctness/sanity metric: failures
divided by independently generated shots in a case, with a 95% Wilson interval.
Do not combine counts across CPU configurations or experiment families because
those reuse the same seeded datasets. No threshold fitting, latency percentiles,
asymptotic scaling exponent or fault-tolerance claim is supported by this MVP.

Analysis splits cohorts by hardware hostname/platform/processor, package versions,
config hash, source hashes and run label; it refuses duplicate case/repetition
rows. This supports aggregation of disjoint worker-filtered jobs on the same
node/software/config, without pooling different machines silently. Runs on
different nodes remain separate cohorts and need their own 1-worker baseline.
For later HPC tests run all worker counts in the same allocation for paired
within-node comparisons. Incomplete or interrupted runs retain their completed
rows; check repetitions against config before interpreting them.

## Limitations

Local runs are on a shared Windows desktop with unrestricted affinity, possible
background tasks, dynamic clock speeds and SMT. Process count is a concurrency
setting, not proof of exclusive physical cores. Full-program execution includes
pool startup, file I/O, validation and shutdown, and is slower than warmed-pool
throughput suggests. There is no live QPU, no streaming decoder, no feedback
deadline, and no FPGA/Deltaflow comparison. These are software offline-decoding
results, not measurements of Riverlane's real-time hardware.
