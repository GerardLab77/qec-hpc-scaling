# QStone findings from actual use

Inspected main commit: `49375fce635259eaea910b1bfede58483bc8e937`.
No upstream issue, PR, fork or message was created.

## Candidate: clarify or repair SLURM CPU allocation

The SLURM template emits `#SBATCH -N {{ nthreads }}`. In SLURM `-N` requests
nodes. A reader setting nthreads=4 to request four CPUs would request four
nodes. The local generator exercise retains nthreads=1 and adds explicit
`--ntasks=1 --cpus-per-task=4`. The saved original output and adapted script
make this visible. This is a source/template observation; no scheduler run
was performed.

A useful small contribution would establish the intended node/task/thread
semantics with maintainers, document those meanings, and add a generation test
for a single-node four-CPU workload. Do not blindly replace -N with -c: existing
MPI users may rely on the current behavior. Inspect current branches/issues
again before proposing a change.

## Built-in PyMatching correctness concerns

`pre()` writes a noiseless Stim circuit. `post()` reads it, builds its detector
error model and samples fallback data. If decoding the supplied syndromes raises
ValueError, the fallback sets `predicted_observables = sampled_syndromes`, rather
than decoding those syndromes. The prediction and observable arrays can have
different meanings/shapes; a success return is not a reliable decoding check.

Before filing, reproduce against the intended connector path with a minimal
failing fixture. A meaningful regression test would require valid observable
predictions or an explicit error, rather than silently substituting detector
events. This project bypasses that path and tests its own serial/batch/process
equivalence; it has **not** demonstrated a live connector failure or fixed the
upstream implementation.

## Known issues deliberately not duplicated

While calling `generate_suite`, the configuration supplies both `app_args={}`
and `app_logging_level=2`. Missing values can truncate generated jobs because
parallel lists are zipped. This is already reported in
[issue 71](https://github.com/riverlane/QStone/issues/71) and
[issue 81](https://github.com/riverlane/QStone/issues/81).
Reproducible generator seeding is already requested in
[issue 83](https://github.com/riverlane/QStone/issues/83).
The fixed single-job generator configuration here avoids relying on its random
selection for scientific case ordering; the local runner owns its seeded matrix.

These are contribution opportunities grounded in source inspection/use, not a
claim that an upstream contribution has been accepted or that a new issue is
needed solely for an application.
