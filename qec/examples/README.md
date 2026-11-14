# Restricted logical compiler

The separate `python -m qec.surface.compile` CLI compiles a vetted temporal H
or lattice-surgery CX with TQEC, or a Stim rotated-memory template. This is a
software compilation milestone, **not arbitrary Clifford support**. The existing
`qec.surface.example` and its board behavior are unchanged.

## Setup and example

Run from the repository root. Create an isolated Python 3.12 environment:

```sh
uv venv --python 3.12 build/compiler-env
uv pip install --python build/compiler-env/bin/python -r qec/requirements-compiler.txt
source build/compiler-env/bin/activate
```

The requirements pin TQEC to revision
`57b5c1ccfbfc6223f07c6775d432d6a87c08b68f`. Compile [the logical H example](logical_h.json):

```sh
python -m qec.surface.compile qec/examples/logical_h.json --basis z --distance 3 --noise 0.001 --shots 256 --seed 123 --out build/logical-h
```

The command prints the full manifest. Selected fields from this run:

```json
{
  "counts": {"qubits": 25, "detectors": 56, "observables": 1, "edges": 208},
  "shortest_graphlike_error": 3,
  "metrics": {
    "shots": 256,
    "ideal_detector_flips": 0,
    "ideal_observable_flips": 0,
    "uf_syndrome_failures": 0,
    "uf_logical_failures": 3,
    "mwpm_logical_failures": 0
  }
}
```

- `counts` describes the compiled physical Stim circuit and decoding graph.
- `shortest_graphlike_error` is the reference model's minimum graphlike logical
  error weight, not a proof of distance against all correlated faults.
- `metrics` compares software UF and weighted PyMatching with the same sampled
  logical observables. UF corrections also undergo detector-boundary checks.
  Zero observed failures in a finite sample does not imply zero error probability.

## Input contract

Input is strict JSON with exactly `qubits` and `gates`. The only accepted programs
are `{"qubits":1,"gates":[]}` (memory),
`{"qubits":1,"gates":[{"gate":"H","targets":[0]}]}`, and
`{"qubits":2,"gates":[{"gate":"CX","targets":[0,1]}]}`.
[CX](logical_cx.json) and [memory](logical_memory.json) examples are included.
S, T, adaptive controls, extra fields, reversed CX and all gate compositions are
rejected. `--basis x|z` selects input preparation; H swaps the readout basis,
while CX and memory retain it. These are separate commuting correlation
experiments, not simultaneous X/Z readout or an arbitrary unknown-state interface.
Distances 3 and 5 are supported; `--k 1|2` is an alternative with
`distance = 2*k+1`. Memory uses `distance` extraction rounds. Noise is finite in
[0, 0.75]; H/CX use TQEC uniform circuit-level depolarization, and memory uses
Stim's gate/data/reset/measurement noise parameters. `--shots` must be positive
and `--seed` an unsigned 64-bit integer.

## Artifacts and decoding contract

The output directory must not exist. It receives annotated `ideal.stim` and
`noisy.stim`, the sampling circuit's `model.dem`, decoding `reference.dem`,
`graph.json`, logical geometry/correlations in `logical.json`, `program.json`,
per-shot syndrome and prediction evidence in `shots.json`, and a hash/version
`manifest.json`. Reproducibility depends on the recorded software versions as
well as the seed; Stim does not promise identical streams across versions or
sampling batch sizes.

Detector i is integer bit i; edge triples are
`[endpoint_a, endpoint_b, observable_mask]`, with boundary vertex `num_detectors`
and mask bit i representing observable L_i. Logical observable indices follow
the archived correlation-surface order. The exporter rejects non-graphlike
components, detectorless logical components and ambiguous endpoint/mask mappings
rather than dropping them. The archived DEM retains separator correlations; UF
is unweighted and MWPM uses independent weighted graph edges. At zero requested
noise, samples and `model.dem` remain noiseless; the graph and MWPM weights use
an explicitly recorded 0.001 reference model so logical width and topology do
not disappear.

## Hardware boundary

Single-observable templates also emit `graph.mem` in the existing core ROM word
format: `a | (b << vertex_bits) | (mask << (2*vertex_bits))`. CX retains both
observable bits (including masks 2 and 3) in JSON and software decoding, but
deliberately emits no one-bit ROM. The current RTL and serial reply expose one
prediction bit, and the production image embeds the memory graph. A new ROM
file does not update that image: H needs a matching bitstream and firmware; CX
also needs wider RTL/protocol support. This compiler rejects every `--port`
request before opening serial and never substitutes software results for FPGA
replies. It does not program or reset the board.

## Tests

With the optional environment active:

```sh
python -m pytest qec/tests/test_surface_compile.py -q
python -m pytest qec/tests -q
```

Compiler integration tests skip explicitly if TQEC is not installed. Input and
hardware-rejection tests do not require it.
