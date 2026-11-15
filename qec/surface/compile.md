# Restricted logical-template compiler and loss-checked artifacts

Companion to [`compile.py`](compile.py).

## Contracts and flow

`Program` is a frozen dataclass carrying template, logical-qubit count and source object. `parse_program(text)` uses `_unique_object` to reject duplicate JSON keys and requires exactly qubits/gates and gate/targets fields. Only one-qubit memory, H on 0, or CX from 0 to 1 are accepted; booleans are not integer targets. Arbitrary Clifford sequences, compositions and adaptive control are not supported.

`checked_graph(dem, detectors, observables)` walks flattened error components separated by Stim separators, accumulating detector parity and observable masks. It rejects detectorless logical components, >2 detector components, invalid indices and ambiguous masks for the same endpoints. It compares the sorted PyMatching projection against every retained signature so projection loss is never silently accepted. Decomposed correlations remain in the DEM but matching treats components independently.

`compile_program(program, out, ...)` revalidates source identity and options (x/z, distances 3/5, finite noise 0..0.75, positive integer shots, unsigned 64-bit seed) before loading optional TQEC dependencies. Memory uses Stim; temporal H and surgery CX use vetted TQEC blocks and fixed-bulk convention. Noise zero retains a 0.001-noise reference graph while actual noisy samples remain noiseless.

Ideal samples must have zero detector/observable flips. Noisy samples are decoded by weighted matching and unweighted UF; UF correction endpoints must cancel every nonboundary detector. Artifacts include ideal/noisy circuits, actual/reference DEMs, graph/logical/program JSON, replayable shot masks and a hashed manifest. ROM is emitted only for one observable; multibit CX remains software-only. A temporary sibling directory is renamed only after complete publication; existing outputs are refused. `main(argv)` prints the manifest and rejects --port before reading input or contacting hardware. Source hashes intentionally change after readability edits; this is provenance, not algorithm drift.

## Callable index

- `Program` — Validated template selection, logical qubit count and original strict-JSON source.
- `_unique_object` — Build a JSON object while rejecting duplicate keys at every object nesting level.
- `parse_program` — Reject extra fields, implicit controls, and all unvalidated compositions.
- `checked_graph` — Preserve each graphlike component, or fail before PyMatching can merge it.
- `compile_program` — Publish a fresh self-contained artifact directory; never overwrite a run.
- `main` — Software-only compiler entry point; reject serial before any I/O to a board.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python -m qec.surface.compile --help
python -m pytest -q qec/tests/test_surface_compile.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
