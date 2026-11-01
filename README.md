# QEC-HPC-Scaling

**Benchmarking classical quantum error correction decoding at scale.**

This project investigates how offline QEC decoding cost changes with workload
size, surface-code space-time complexity, and independent CPU worker processes.

Stim generates noisy quantum-memory experiments. PyMatching predicts logical
corrections from detector events. The benchmark separates warmed decoding and
dispatch costs from sampling, model construction, and process startup.

## Questions

- How does batch size affect decoder throughput and amortized cost per shot?
- How does increasing surface-code distance and round count change decoding cost?
- When does splitting a fixed batch across CPU workers improve throughput?
- How much overhead sits outside the decoder itself?

## Project status

The local MVP is complete and has been benchmarked. Its source, tests, results,
and documentation are being published in ten logical batches. This is an
incremental release of existing work.

The measured workload uses Stim and PyMatching directly. An adapted SLURM path
reuses Riverlane QStone's generator. No HPC execution has been performed.

## Publication sequence

1. **Project overview and publication plan** — this commit.
2. Repository foundations, dependencies, and tooling audit.
3. Seeded workload and process-based measurement implementation.
4. Configurations and repeated benchmark runner.
5. Decoder correctness and parallel-equivalence tests.
6. Statistical analysis, plots, and analysis safeguards.
7. Raw local measurements and environment metadata.
8. Generated figures and result summaries.
9. QStone-based SLURM pathway and upstream observations.
10. Full findings, methodology, interview notes, and CI configuration.

This repository is not yet the runnable release. Installation and execution
instructions will accompany the relevant source and configuration batches.

## Scope

This is an offline engineering benchmark, not a new decoder or simulator.
Amortized batch cost is not single-shot feedback latency. Worker processes are
not equivalent to exclusive physical cores. Local CPU measurements do not
establish performance on an HPC cluster or Riverlane's real-time hardware.

Independent project; not affiliated with or endorsed by Riverlane.
