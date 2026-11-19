# Logical accuracy benchmark

![Logical failure probability for rotated X and Z memories](images/benchmark-accuracy.png)

This is a software experiment using the maintained ordered, unweighted union-find (UF) reference and weighted PyMatching. It does not measure FPGA execution, latency, or adaptive feedback.

## Method

Stim generates `surface_code:rotated_memory_x` and `surface_code:rotated_memory_z` at distances 3 and 5, with **three extraction rounds for both distances**. At each noise point, all four generator parameters equal p: `after_clifford_depolarization`, `before_round_data_depolarization`, `after_reset_flip_probability`, and `before_measure_flip_probability`. These are circuit-level noise settings, not a single effective physical error rate.

The compiler `qec.surface.circuit.compile_circuit` validates each generated circuit and extracts the ordered graph. `qec.surface.decoder.decode` runs actual UF growth and forest peeling on every shot. Weighted `pymatching.Matching.from_detector_error_model` uses the same circuit's decomposed detector error model and regenerates its probability weights at every p. Correlation-aware matching is disabled; both decoders project separator-correlated errors onto graph edges, while Stim samples the original noisy circuit.

Each point uses 30,000 shared detector/observable samples in batches of 1,000. Failure means the predicted logical observable differs from Stim's sampled observable flip. A returned UF error counts as failure regardless of its prediction. Decoder disagreement alone is not the truth criterion. Archived paired failure counts permit paired analysis; marginal intervals alone do not establish a significant difference between decoders.

The fixed logarithmic grid is p = 0.001, 0.002, 0.004, 0.008, 0.016, 0.032. Each point has the same prespecified shot count, without optional stopping. Error bars are two-sided 95% exact Clopper–Pearson binomial intervals. A downward triangle denotes the upper endpoint when zero failures were observed; the estimate itself is zero. Probabilities are **per complete shot, not per round**. With three rounds fixed as distance changes, these curves do not establish a threshold or general asymptotic distance scaling.

## Captured results

The run contains 24 circuit/noise points and 720,000 distinct sampled shots, each evaluated by both decoders. UF returned no errors. Across this mixed grid, UF failed on 75,675 shots and PyMatching on 64,805; the pooled counts are bookkeeping, not an operating-point failure probability.

At p = 0.004, the counts below are failures out of 30,000:

| Memory | Distance | UF | Weighted PyMatching |
| --- | ---: | ---: | ---: |
| X | 3 | 477 | 389 |
| X | 5 | 464 | 143 |
| Z | 3 | 409 | 342 |
| Z | 5 | 403 | 141 |

The lowest-noise d=5 points have sparse matching failures: X has 2 and Z has 0. For Z, zero observed failures gives a 95% interval of [0, 0.0001229551], not evidence of zero logical error probability. The intermediate points provide substantially more failures for comparison. Increasing distance does not consistently improve this ordered UF implementation across the sampled grid.

## Reproduce

From the repository root, create a private environment and run:

```sh
UV_CACHE_DIR=build/accuracy/uv-cache uv venv --python python3.12 build/accuracy/venv
UV_CACHE_DIR=build/accuracy/uv-cache uv pip install --python build/accuracy/venv/bin/python stim==1.16.0 pymatching==2.4.0 numpy==2.5.5 scipy==1.18.1 matplotlib==3.11.2
PYTHONPYCACHEPREFIX=build/accuracy/cache build/accuracy/venv/bin/python scripts/benchmark_accuracy.py \
  --output /home/toastcheng/qc-research/fpga-qec/readme-benchmarks/accuracy/reproduction \
  --png docs/images/benchmark-accuracy.png
```

The output directory must not exist. Defaults reproduce the grid, seed 20261119, and batch sizes above. Seeds increment by point in X/Z, distance, then ascending p order. Stim reproducibility depends on its version, machine/SIMD behavior, batch size, and call sequence, not the seed alone.

Captured evidence is outside this repository at:

```text
/home/toastcheng/qc-research/fpga-qec/readme-benchmarks/accuracy/run-20261119/
```

It contains `results.csv`, `metadata.json`, `sha256.json`, PNG/SVG figures, actual circuit/DEM/graph files, packed detector shots, observable truth, both predictions, and UF error flags. `metadata.json` records exact versions, source revision, worktree status, per-point seeds, dimensions, hashes and elapsed runtime. `source/` preserves the benchmark and the compiler/graph/UF implementation actually used; `source-diff.patch` captures tracked differences. Detector bytes in the NPZ files use little-endian bit order. The measured experiment took about 32 seconds on the recorded host; this includes sampling, software decoding and plotting, and is not a decoder latency benchmark.
