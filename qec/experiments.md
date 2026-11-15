# Reproducible sweep and software timing artifacts

Companion to [`experiments.py`](experiments.py).

## Contracts and flow

`wilson(errors, shots)` returns a marginal 95% binomial Wilson interval, with exact 0/1 endpoint handling when no/all shots fail. Callers must supply positive shots and valid counts. `write_csv(path, rows)` uses the first dictionary's key order and therefore expects a nonempty sequence.

`run(out, shots, seed)` samples seven NOISE settings using seed+i. Identity, freshly weighted PyMatching and the fixed-default-noise LUT all see the same detector/observable arrays at each point. Rows distinguish logical errors from disagreement with PyMatching. It writes `noise_sweep.csv`, then separately measures warmed-up decoding on another sample seeded seed+100.

Seven repetitions measure whole-batch PyMatching and NumPy LUT indexing. Up to 2000 individual samples measure actual single decode/access calls, without dividing an enclosing loop. Packing and sampling are outside timed operations. `timings.csv` retains raw observations; `metadata.json` records software versions, LUT-file hash, parameters and percentile summaries. Two PNGs visualize accuracy intervals and software costs using the noninteractive Agg backend. The function returns metadata; the CLI prints it and checks positive shots/nonnegative seed.

Output directories may already exist and named outputs are overwritten. Timings depend on host load and are not reproducible latency guarantees. Seed reproduction also depends on Stim version and sample-call shape. Marginal intervals are not a paired significance test. No timing here establishes FPGA speed or adaptive-feedback deadlines.

## Callable index

- `wilson` — Return the marginal 95% Wilson bounds for errors among positive shots.
- `write_csv` — Write nonempty row dictionaries using the first row's key order as the header.
- `run` — Write paired noise-sweep evidence, software timings and charts; return run metadata.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/experiments.py --shots 32 --seed 12345 --out build/readability-sweep
python -m pytest -q qec/tests/test_experiments.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
