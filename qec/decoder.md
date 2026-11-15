# Repetition-code reference and complete syndrome table

Companion to [`decoder.py`](decoder.py).

## Contracts and flow

`model(p=0.001)` constructs Stim repetition memory with distance 3 and three rounds. The same p drives after-Clifford depolarization, pre-round data depolarization, measurement flips and reset flips. It checks for exactly eight detectors and returns `(circuit, matching)`; matching weights come from the decomposed detector error model.

`pack(detectors)` converts an array of detector rows to uint8 before multiplying by eight powers of two. Detector 0 is the least-significant bit. Rows must have eight columns; this helper does not independently validate binary entries. `make_lut()` enumerates addresses 0 through 255 in that order and returns the first logical-observable prediction as a uint8 vector. It always uses the default model noise, not a caller's sweep noise.

The script entry point overwrites the sibling `lut.mem` with hexadecimal predictions. This is a 256-entry table for one fixed repetition experiment, not the graph-based surface decoder. PyMatching tie choices and versions can affect generated predictions. The model checks detector count, not a general hardware graph identity.

## Callable index

- `model` — Return the d3/r3 Stim circuit and weighted matching model for four-channel noise p.
- `pack` — Pack rows of eight detector bits into little-endian integer LUT addresses.
- `make_lut` — Decode every eight-bit syndrome at the fixed default noise; return 256 uint8 predictions.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/host.py --mode loopback --shots 32 --seed 90210
python -m pytest -q qec/tests/test_decoder.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
