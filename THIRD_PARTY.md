# Third-party material

The original code in this repository is covered by `LICENSE` (MIT).

QStone-generated content under `slurm/generated/`, including the original
suite archive and scheduler template output, derives from Riverlane QStone at
commit `49375fce635259eaea910b1bfede58483bc8e937`, licensed under Apache-2.0.
Its license is retained in `licenses/QStone-Apache-2.0.txt`. The adapted
`qec.sbatch` replaces the generated execution body with this project's offline
runner and adds explicit CPU/task/memory settings; see `docs/HPC.md` and the
original template output for the modifications.

Stim, PyMatching, NumPy and other runtime dependencies are installed separately
and retain their respective licenses. Their implementations are not vendored.
