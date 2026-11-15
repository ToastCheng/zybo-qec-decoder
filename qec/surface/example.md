# One real sampled surface window with optional serial replay

Companion to [`example.py`](example.py).

## Contracts and flow

`main()` loads the committed d3 Z r3 graph and circuit from the repository-relative graph path. --noise regenerates the sampling circuit when different from the committed noise; it never replaces the fixed decoder edges. Noise is bounded to 0..0.75, shots must be positive and optional seed is an unsigned 64-bit integer. No seed means fresh Stim randomness.

--circuit prints the actual selected Stim circuit and returns before sampling or serial I/O. Otherwise it samples a candidate batch with separate observables and chooses the first nonzero detector row, falling back to row zero if all rows are clear. Detector i becomes syndrome bit i. UF returns graph-edge corrections, whose nonboundary endpoint parity is independently checked for zero residual. Current-noise PyMatching supplies a distinct weighted baseline; ensure_num_fault_ids preserves one output even at zero noise.

Printed JSON identifies selected shot, detector indices, syndrome, true observable, UF/PyMatching predictions, correction edge indices, residual, logical-error flag and exact framed request bytes. With explicit --port, the same window is sent to a previously loaded d3 Z image at 115200 baud. Its reply must parse, agree with UF and report nonzero cycles; board reply fields are added to JSON. No port means no serial access, programming or reset.

The correction is a detector-graph representative, not a physical Pauli command. Zero detector residual can coexist with a logical failure; truth comparison remains essential. Paths require running from repository root. Optional board mode assumes the correct loaded fixed-memory image rather than querying its identity.

## Callable index

- `main` — Inspect a candidate batch, decode its first nonzero syndrome, and optionally validate one board reply.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python -m qec.surface.example --seed 20261107 --shots 256
python -m pytest -q qec/tests/test_surface_example.py qec/tests/test_example_sampling.py qec/tests/test_example_noise.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
