# QEC-HPC-Scaling

**Benchmarking classical quantum error correction decoding at scale.**

This project investigates how offline QEC decoding cost changes with workload
size, surface-code space-time complexity, and independent CPU worker processes.

Stim generates noisy quantum-memory experiments. PyMatching predicts logical
corrections from detector events. The benchmark separates warmed decoding and
dispatch costs from sampling, model construction, and process startup.

## Research questions

- How does batch size affect decoder throughput and amortized cost per shot?
- How does increasing surface-code distance and round count change decoding cost?
- When does splitting a fixed batch across CPU workers improve throughput?
- How much overhead sits outside the decoder itself?

## Approach

The decoding workload uses Stim and PyMatching directly. An adapted SLURM path
reuses Riverlane QStone's generator. Measurements distinguish decoder execution
from process startup, input generation, and dispatch overhead.

Results are based on local CPU execution. No HPC execution has been performed.

## Scope

This is an offline engineering benchmark, not a new decoder or simulator.
Amortized batch cost is not single-shot feedback latency. Worker processes are
not equivalent to exclusive physical cores. Local CPU measurements do not
establish performance on an HPC cluster or Riverlane's real-time hardware.

Independent project; not affiliated with or endorsed by Riverlane.
