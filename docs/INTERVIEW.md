# Explaining the project

**Problem:** classical decoding itself consumes CPU time. More simulated shots,
larger decoding graphs and more worker processes change the cost. The study
asks where useful throughput gains stop justifying the extra resources.

**QEC:** encode logical information across several physical qubits. Repeated
checks reveal patterns of errors without directly measuring the protected
logical information. Differences between expected check outcomes form detector
events. A decoder infers likely errors and predicts a logical correction.

**Decoder:** PyMatching uses minimum-weight perfect matching (MWPM) on the
detector error model produced by Stim. It is established, compiled and locally
available; this project is about measuring its execution, not inventing a new
decoding algorithm.

**Performance:** hardware produces a continuing stream of checks. Sustained
throughput must avoid a backlog, and feedback can have latency deadlines.
Offline batch throughput alone cannot establish either a real-time deadline or
Riverlane hardware performance. My measured per-shot cost is amortized, not a
latency distribution.

**QStone:** Riverlane's benchmark/orchestration tool studies the HPC/quantum
interface. It already packages workloads and generates scheduler scripts. I
inspected its built-in PyMatching workload, found its POST timing unsuitable
for isolating decoder cost, and used explicit timers. The later SLURM scripts
reuse its generator with a documented offline command adaptation.

**Parallelism:** the PyMatching batch API has no thread-count argument. I split
the same fixed batch among independent worker processes. Each builds its own
decoder, maps the same input file, warms up and rendezvous at a barrier. I
compare against a one-process pool baseline and verify identical predictions.

**Strongest methodological choice:** dispatch time and inner decoder time are
separate. Throughput doesn't hide all overhead inside an unexplained timer, and
pool startup is recorded even though it is excluded from warmed-pool throughput.

**HPC changes:** run on allocated compute nodes, constrain CPUs with SLURM,
keep a fixed node type, use local temporary storage, record the allocation and
software environment, and repeat the matrix within each node. No distributed
MPI or multi-node decoder is implemented. Additional nodes provide independent
experiments rather than cooperative decoding.

**Honest boundaries:** a small controlled benchmark, not a new QEC algorithm,
threshold study, production decoder or claim of quantum advantage. The initial
results and their uncertainty are in the README and figures. Two single-node
Stanage campaigns have completed, including persistent-pool execution. Neither
tested multi-node decoding or real-time quantum feedback.

## CV wording grounded in the included results

- Benchmarked offline quantum error-correction decoding on Sheffield's Stanage
  HPC cluster using Slurm, achieving 15.16x median paired speedup and 94.7%
  parallel efficiency with 16 CPU workers on million-shot batches.
- Investigated process-startup amortisation across 150 persistent-pool sessions
  and 5,550 batches; measured 9.20x decoder-service speedup and approximately
  45% lower full-workload time with 16 workers over 100 million-shot batches.
- Added reproducible seeded experiments and 16 automated tests covering decoder
  correctness, process reuse and analysis safeguards; validated matching inputs
  and predictions across worker counts in both completed HPC campaigns.

Use two of these if space is limited. Decoder-service time includes setup,
dispatches and shutdown; full-workload time also includes serial simulation,
input I/O and validation. The 45% figure is not a decoder-only speedup claim.
