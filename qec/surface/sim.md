# Generated surface graph through actual decoder RTL

Companion to [`sim.py`](sim.py).

## Contracts and flow

`main()` parses distance, x/z basis and shot count and creates `build/surface_sim_d<distance>_<basis>`. It uses graph/export for the selected distance and basis, retaining graph()'s default three rounds. Thus distance 5 here does not imply five extraction rounds.

The corpus combines zero, all single detectors, every graph edge syndrome, seeded Stim shots (1945) and 64 dense syndromes from Python Random(1946). UF reference results must be error-free before each packed word `(syndrome<<2) | (error<<1) | prediction` is emitted to cases.mem. A generated wrapper selects detector count, edge count, graph and vector paths for surface_core_test.

xvlog compiles the real surface_decoder and shared surface testbench plus wrapper; xelab elaborates and xsim runs it. VIVADO_BIN denotes the tool binary directory here; otherwise PATH and a versioned home fallback locate xvlog. Combined output is retained per tool. Nonzero exit, Fatal/FATAL text or missing final `PASS algorithmic surface` aborts.

Artifacts can be overwritten on rerun and shared output paths prohibit simultaneous runs of the same configuration. These are actual HDL checks if real tools are selected, not physical board measurements. The test suite also uses tiny fake executables solely to verify discovery, explicitly not as RTL evidence. This source never opens serial or programs hardware.

## Callable index

- `main` — Export a graph and deterministic test corpus, then require an actual xsim decoder PASS marker.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/surface/sim.py --help
python -m pytest -q qec/tests/test_standalone.py qec/tests/test_surface.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
