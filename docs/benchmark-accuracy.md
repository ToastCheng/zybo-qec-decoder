# Logical accuracy benchmark

![Zybo Z7-10 FPGA logical failure probability for rotated X and Z memories](images/benchmark-accuracy-fpga.png)

This benchmark measures how often the FPGA decoders mispredict the logical
observable across physical noise rates `p` on rotated surface-code memory.
Every curve in both panels (`Matching d=3`, `Matching d=5`, `UF d=3`, `UF d=5`)
comes from real Zybo Z7-10 programmable-logic execution at 100 MHz:

- **UF** runs on the default runtime union-find image (`fpga/rtl/`).
- **Matching** runs on the experimental programmable parity-frontier exact
  matching image (`fpga/experimental/frontier/`).

Stim generates the noisy shots and true logical observables on the host;
PyMatching is used only offline to extract exact `binary64` edge weights for
the uploaded matching programs.

## On-board 4-curve FPGA results

The hardware sweep tests rotated X and Z memory over three extraction rounds
at six physical noise rates (`p = 0.001, 0.002, 0.004, 0.008, 0.016, 0.032`):

- **Distance 3:** 8,000 shared shots per noise point
- **Distance 5:** 1,500 shared shots per noise point
- **Seeds:** `20261120..20261143` across the 24 `(basis, distance, p)` points

Across all 24 points, there are 114,000 shared simulated shots and 46,750
unique detector syndromes. Both FPGA images decoded every one of the 46,750
unique syndromes over UART (93,500 decode replies and 94,052 total UART
transactions) with zero hardware errors, matching IEEE CRC-32 program readback
on the matching core, and 100% agreement with their independent exact software
references. Because both hardware cores are pure deterministic functions of
the loaded graph/program and input syndrome, mapping each board prediction
back onto all 114,000 truth-labeled shots gives the exact shot-level failure
counts.

Logical failures at `p = 0.004` (out of 8,000 shots for `d=3` and 1,500 shots
for `d=5`):

| Memory | Distance | UF on FPGA | Exact matching on FPGA |
| --- | ---: | ---: | ---: |
| X | 3 | 133 / 8,000 (1.66%) | 119 / 8,000 (1.49%) |
| X | 5 | 23 / 1,500 (1.53%) | 8 / 1,500 (0.53%) |
| Z | 3 | 111 / 8,000 (1.39%) | 84 / 8,000 (1.05%) |
| Z | 5 | 21 / 1,500 (1.40%) | 7 / 1,500 (0.47%) |

Full raw board results, DP schedules, Vivado route reports, and UART wire
archives live in
[fpga-four-curve-benchmark](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/fpga-four-curve-benchmark).

## Earlier 30,000-shot software reference sweep

Before building the programmable matching FPGA core, we ran a larger
software-only sweep (`images/benchmark-accuracy.png`) comparing our ordered
Python UF decoder (`qec.surface.decoder.decode`) against weighted PyMatching.
The details below document that archived reference run.

### Setup and noise model

- **Circuits:** Stim `surface_code:rotated_memory_x` and
  `surface_code:rotated_memory_z` at distances `d=3` and `d=5`, with **three
  extraction rounds** for both distances. Because rounds stay fixed at 3 as
  distance grows, these curves compare finite 3-round memory performance rather
  than asymptotic threshold scaling.
- **Noise parameter `p`:** All four Stim circuit-level noise parameters are
  set equal to `p`: `after_clifford_depolarization`,
  `before_round_data_depolarization`, `after_reset_flip_probability`, and
  `before_measure_flip_probability`.
- **Decoders:** `compile_circuit` extracts the ordered unweighted graph for
  UF; `pymatching.Matching.from_detector_error_model` builds a weighted graph
  from the same circuit's decomposed detector error model at each `p`
  (correlation-aware matching disabled).
- **Sampling and error bars:** 30,000 shared shots per point (in batches of
  1,000) across the same six `p` values. A shot fails if the predicted
  observable disagrees with Stim's true observable flip (or if UF reports an
  error). Error bars show two-sided 95% exact Clopper-Pearson intervals per
  complete shot; a downward triangle marks the 95% upper bound when zero
  failures occurred.

### Software sweep results

Across all 24 points (720,000 shots), UF returned zero decode errors. At
`p = 0.004`, failures out of 30,000 shots were:

| Memory | Distance | UF | Weighted PyMatching |
| --- | ---: | ---: | ---: |
| X | 3 | 477 | 389 |
| X | 5 | 464 | 143 |
| Z | 3 | 409 | 342 |
| Z | 5 | 403 | 141 |

At the lowest noise point (`p = 0.001`, `d=5`), weighted PyMatching had 2
failures in X memory and 0 in Z memory (95% upper bound `0.000123`). Notice
that unweighted, edge-ordered UF does not gain nearly as much from going from
`d=3` to `d=5` as weighted matching does across this noise grid.

### Reproducing the software sweep

From the repository root, create an isolated Python environment and run
`scripts/benchmark_accuracy.py` pointing `--output` at a new directory:

```sh
UV_CACHE_DIR=build/accuracy/uv-cache uv venv --python python3.12 build/accuracy/venv
UV_CACHE_DIR=build/accuracy/uv-cache uv pip install --python build/accuracy/venv/bin/python \
  stim==1.16.0 pymatching==2.4.0 numpy==2.5.5 scipy==1.18.1 matplotlib==3.11.2
PYTHONPYCACHEPREFIX=build/accuracy/cache build/accuracy/venv/bin/python scripts/benchmark_accuracy.py \
  --output /path/to/qc-research/fpga-qec/readme-benchmarks/accuracy/reproduction \
  --png docs/images/benchmark-accuracy.png
```

Defaults reproduce the six-point grid, starting seed `20261119` (incremented
per point in X/Z, distance, ascending-`p` order), and 30,000 shots/point. The
archived raw dataset (`results.csv`, `metadata.json`, `sha256.json`, circuits,
packed shots, and source snapshots) is in
[run-20261119](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/readme-benchmarks/accuracy/run-20261119).
The full software run took about 32 seconds on the host (sampling, decoding,
and plotting combined).
