# Encoded circuit examples

This folder holds two built-in encoded surface-code experiments (used as
presets in the web interface and CLI), plus two stricter circuit-level
versions that intentionally fail graph-only compilation.

| File / editor ID | Experiment | Physical qubits | Detectors | Graph edges | Logical outputs |
| --- | --- | ---: | ---: | ---: | ---: |
| [phase_bell.stim](phase_bell.stim) | Encoded Bell state | 34 | 144 | 340 | 2 |
| [two_repetition_echo.stim](two_repetition_echo.stim) | Two 3-patch GHZ echoes | 102 | 720 | 1,716 | 6 |

Note: the file ID `phase_bell` is kept for backwards compatibility with older
editor links, even though the encoded circuit prepares a standard Bell state
(see the gate adaptations below).

Each logical qubit is a distance-3 rotated surface-code patch (9 data qubits
and 8 reused measurement ancillas) with full 2D coordinates. Every protected
segment runs three rounds of all eight stabilizer checks using Stim's
hook-safe four-layer CX schedule, with preparation, extraction, transversal
gates, and readout all operating on those same patches.

## Default noise model (runnable with the graph decoder)

`examples(noise=0.001, noise_model="phenomenological")` generates the two
runnable defaults above. It uses a **restricted phenomenological CSS noise
model** rather than full circuit-level depolarization:

- Before each stabilizer round, every data qubit receives independent
  `X_ERROR(p)` and `Z_ERROR(p)` flips (so a combined Y error occurs with
  probability `p²` as two independent faults).
- Reset, extraction H/CX, and interpatch transversal CX gates are noiseless,
  with no extra idle noise on individual `TICK`s.
- Stabilizer measurement outcomes flip with probability `p` in rounds 1 and 2
  of each three-round segment, while **round-3 measurement outcomes are
  noiseless** (data storage errors still happen before round 3 and are caught
  by it).
- There is no extra storage-noise layer between a segment's final round and
  the transversal CX that follows; storage noise resumes before the next
  extraction segment.
- Final destructive data measurements flip with probability `p`.

### Why round-3 measurements are noiseless here

Across a transversal CX, a prior stabilizer outcome feeds into multiple
post-CX detectors (control X checks and target Z checks combine prior signs
from both patches). If that final pre-CX check measurement flips, a single
fault triggers three detectors at once — a hyperedge that a two-endpoint
graph decoder cannot represent. Keeping gates and round-3 check outcomes
noiseless avoids those hyperedges cleanly without dropping correlations from
Stim's detector error model.

### What is verified on these defaults

- Both compile cleanly under `Capacities(max_detectors=1024, max_edges=8192)`.
- Every raw single-fault signature (340 for Bell, 1,716 for echo) has one or
  two detector endpoints, matches the compiled graph edge set exactly, and
  decodes to the exact logical observable mask under unweighted matching with
  zero mismatches.
- Tests also verify patch geometry, deterministic noiseless detectors and
  observables, intermediate Bell/GHZ correlations, and minimum graphlike
  logical-error weight 3.

## Gate and coupling assumptions

- **Transversal CX:** Logical CX between patches applies pairwise physical CX
  gates directly between matching data qubits in the two patches (nonlocal
  coupling rather than nearest-neighbor lattice surgery). Within each patch,
  stabilizer extraction keeps standard 2D surface-code adjacency.
- **Bell circuit:** Prepares the ordinary Bell state with `XX` and `ZZ`
  logical stabilizers (no encoded `S` gate, unlike an earlier bare phase-Bell
  fixture). A second transversal CX followed by three extraction rounds and
  encoded X/Z readout measures those correlations; the accompanying logical
  diagram uses `MPP` purely as shorthand for that correlation check.
- **GHZ echo circuit:** Drops the bare `S`/`S_DAG` pair so the intermediate
  three-qubit GHZ states have phase `+1`, replaces initial/final `H` on root
  qubits with encoded `|+>` preparation and X readout, and checks all six
  logical outputs.

## Circuit-level noise specimens (intentionally rejected)

[encoded_bell.stim](encoded_bell.stim) and
[encoded_echo.stim](encoded_echo.stim) (generated with
`examples(noise_model="circuit_level")`) add full circuit-level noise: reset
and measurement flips, depolarization after extraction H/CX and transversal
CX, and data-idle depolarization after every round.

Their metadata sets `decoder_compatible=False`, and the graph compiler
intentionally rejects them because Stim's decomposition introduces
detectorless logical components from correlated gate faults. They are kept
here as regression specimens so the compiler continues to reject models that
a graph-only decoder cannot represent faithfully.

## Using the generator in Python

```python
from qec.surface.encoded import examples
from qec.surface.circuit import Capacities, compile_circuit

bell, echo = examples()  # p=0.001, restricted phenomenological model
assert bell["decoder_compatible"]
compiled = compile_circuit(
    bell["circuit"],
    capacities=Capacities(max_detectors=1024, max_edges=8192),
)

unsupported = examples(noise_model="circuit_level")
assert not unsupported[0]["decoder_compatible"]
```

Each entry returned by `examples()` includes `id`, `label`, `circuit`,
`logical_circuit`, `decoder_compatible`, `decoder_limitation`,
`noise_model_id`, `noise_model`, `semantic_adaptation`, and
`coupling_assumption`. If you generate a zero-noise circuit (`noise=0`),
pair it with a positive-noise reference circuit when compiling a decoding
graph.

Run the encoded-example test suite with:

```sh
qec/.venv/bin/python -m pytest qec/tests/test_encoded.py -q -o cache_dir=build/cache/pytest
```

The older two- and six-qubit bare circuits used for parser and transport
tests live under `qec/tests/fixtures/`.
