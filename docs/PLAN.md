# Technical plan (source audit: 1 November 2026)

Question: how do batch size, code distance and independent CPU workers affect
offline classical decoding throughput, and how much does dispatch cost?

## Tooling decision

QStone main was inspected at `49375fce635259eaea910b1bfede58483bc8e937`.
Its generator already renders bare-metal, SLURM and LSF jobs, chooses mixed
workloads, and packages portable suites. Its tracer records PRE/RUN/POST and
connection intervals; its profiler aggregates those intervals. Reuse the SLURM
generator rather than create a scheduler framework.

The built-in PyMatching workload is unsuitable for this controlled study:
`_initialise_circuit` fixes distance=3, rounds=5, p=0.005; `pre` saves a noiseless
circuit; `post` includes graph construction, sampling and NPZ loading. Its
ValueError fallback assigns sampled syndromes to predicted observables rather
than decoding them. Do not report those POST timings as decoder-only timings.
There is no clean distance/rounds/noise/seed experiment matrix in that app.

Deltakit main (`0e8b2700aa2bfa4d607fd88dd392df1a7307cc31`) supports circuit
construction, realistic noise, Stim simulation and a local PyMatching decoder.
It would suit a later noise-model comparison. The MVP needs only the same
established Stim/PyMatching stack, with fewer dependencies and explicit timers.
Neither Deltakit nor Riverlane proprietary decoders is used in measured runs.

PyMatching 2.4.0 `decode_batch` has no worker/thread parameter. Parallelism here
is independent Python **processes**, each with one decoder, splitting a fixed
total shot batch. Setting OMP_NUM_THREADS is not evidence of decoder parallelism.

## Experiments

1. Batch size: 1k, 10k, 100k shots at d=5, rounds=5, p=0.005, one worker.
   Hypothesis: larger batches amortise dispatch overhead.
2. Complexity: d=3,5,7, rounds=d, 100k shots, one worker.
   Hypothesis: larger space-time decoding graphs increase cost per shot.
   This varies distance AND rounds; it is not an isolated spatial-distance effect.
3. Strong scaling: 1,2,4 workers at d=5, rounds=5 for 10k and 100k shots.
   Hypothesis: small jobs suffer from dispatch overhead; larger ones scale better.

Five seeded repetitions, randomised case order within each repetition. Identical
input hashes across worker counts. A small smoke configuration gates the main run.
One fresh process pool per measurement; startup separately timed and excluded
from warm decoding throughput. Warm each worker, then measure a synchronised
batch dispatch, plus each worker's actual decode call. Record failures to detect
incorrect splitting/decoding. No threshold or real-time latency claims.

## Deliverables and gates

1. Source audit and plan (this file).
2. Benchmark and meaningful correctness tests; smoke must pass.
3. Actual local raw JSON rows with input hashes, versions and hardware metadata.
4. Analysis with medians, quartiles, paired speedups and plots; inspect plots.
5. README explaining measured findings and limits; lock measured dependencies.
6. QStone-generated SLURM header plus explicit offline runner adaptation, generated
   and inspected locally; never claim cluster execution. Inspect QStone issues
   before proposing any upstream work. No PR or external messages in this task.

## Sources

- https://github.com/riverlane/QStone/tree/49375fce635259eaea910b1bfede58483bc8e937
- https://github.com/Deltakit/deltakit/tree/0e8b2700aa2bfa4d607fd88dd392df1a7307cc31
- https://github.com/oscarhiggott/PyMatching
- https://github.com/quantumlib/Stim
- https://docs.hpc.shef.ac.uk/en/latest/stanage/software/apps/python.html
- https://docs.hpc.shef.ac.uk/en/latest/hpc/scheduler/index.html
