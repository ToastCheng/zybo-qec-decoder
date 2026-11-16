# Encoded circuit examples

The editor defaults are protected fixed experiments, not bare circuits and not
an arbitrary logical-to-physical compiler:

| Editor ID / file | Experiment | Physical qubits | Detectors | Exact graph edges | Outputs |
| --- | --- | ---: | ---: | ---: | ---: |
| [phase_bell.stim](phase_bell.stim) | Ordinary encoded Bell | 34 | 144 | 340 | 2 |
| [two_repetition_echo.stim](two_repetition_echo.stim) | Two encoded three-patch GHZ echoes | 102 | 720 | 1716 | 6 |

The `phase_bell` ID is retained for editor compatibility, **not** a claim that
this circuit prepares a phase Bell state. See the semantic adaptations below.

Each logical qubit is a distance-3 rotated surface-code patch: nine data qubits
and eight reusable measurement ancillas. Dense physical indices and full 2D
coordinates are supplied. Every protected segment has **three complete rounds**
of all eight stabilizer checks, using Stim's hook-oriented four-layer extraction
CX schedule. Preparation, extraction, transversal gates and final readout operate
on the same protected patches; no unrelated memory is appended.

## Explicit restricted noise model — runnable default

`examples(noise=0.001, noise_model="phenomenological")` is the default. It is a
**restricted phenomenological CSS model**, not circuit-level depolarization and
not a realistic calibrated hardware model:

- Before **each** extraction round, every data qubit undergoes independent
  `X_ERROR(p)` and `Z_ERROR(p)` channels. A simultaneous X and Z (Y up to phase)
  is a two-fault event of probability p², **not** a correlated single Y fault.
- All reset, extraction H/CX gates and transversal interpatch CX gates are
  perfect. There are no additional idle errors at individual TICKs.
- Stabilizer measurement-result flips occur independently with probability p
  in rounds **1 and 2** of every three-round segment.
- The round **3 measurement results are perfect**. Data storage faults still
  occur immediately before that round and are measured by its full extraction.
- There is **no noisy storage interval between a segment's last extraction and
  a transversal gate**. Storage noise resumes before the next extraction.
- Destructive data measurement results flip independently with probability p.

The exact final-round result boundary is essential, not an optimization hidden
from the user: across a transversal CX, a previous check sign contributes to
multiple subsequent detectors. A faulty final check record can therefore create
a three-detector single-fault signature. Independent X/Z channels, perfect gates,
and exact boundary records avoid those hyperedges without deleting correlations
from the DEM or weakening graph validation. This deliberately limited model
supports noisy storage/readout experiments around real encoded Clifford gates;
it does **not** demonstrate fault tolerance against faulty gates or arbitrary
measurement faults at a gate boundary.

Stabilizer histories are propagated through CX: control X-check signs and target
Z-check signs become products of prior signs on both patches. Initially random
complementary-basis checks are not declared deterministic detectors. A different
basis of detectors alone is not claimed to solve the general noisy-CX problem.

### Exact graph validation

Both defaults compile with `Capacities(max_detectors=1024, max_edges=8192)`.
Tests enumerate **all distinct raw single-fault signatures**, without error
 decomposition: 340 Bell signatures and 1,716 echo signatures. Each has one or
two detector endpoints. The raw `(endpoints, logical_mask)` set equals the
compiled graph edge set exactly, with no lost components and no ambiguous masks.
Unweighted matching reconstructed from that **same compiled graph** returns the
correct full logical mask on every raw single-fault syndrome (zero mismatches).

Tests also verify full extraction geometry, noiseless deterministic detectors
and observables, intermediate encoded Bell/GHZ correlations, unique single-fault
logical labels, and shortest graphlike logical-error length three. These are
single-fault checks, not a promise that every multi-fault shot succeeds or that
unweighted runtime decoding equals optimal weighted decoding. Disconnected graph
components still require the host's component/window handling. No FPGA board
programming or physical hardware-noise validation is claimed here.

## Encoded gates and semantic adaptations

Interpatch logical CX assumes **nonlocal pairwise transversal data-data CX
couplings** between matching patch sites. This is not nearest-neighbor lattice
surgery. The extraction couplers within each patch retain surface geometry.

The Bell experiment prepares the ordinary Bell state with logical **XX/ZZ**
correlations, **not** the original phase Bell's YX/ZZ correlations. No encoded S
gadget is implemented or implied. Its destructive Bell analyzer uses a second
transversal CX, then three extraction rounds and separate encoded X/Z readouts.
These measure the pre-analyzer XX/ZZ correlations. The logical diagram uses MPP
only to name those correlations; the physical circuit contains no MPP.

The echo removes the original S/S_DAG pair. The final ideal action is still the
identity on the specified prepared inputs, but intermediate three-logical-qubit
GHZ states have phase +1, not +i. Encoded |+> preparation/X readout replace the
initial/final H on each root. All six logical outputs are checked, rather than
only the original two bare group outputs. The gates and all three-round protected
segments are retained.

## Optional circuit-level specimens — unsupported by graph decoder

[encoded_bell.stim](encoded_bell.stim) and
[encoded_echo.stim](encoded_echo.stim) retain the more demanding circuit-level
model: reset/result flips, depolarization after extraction H/CX and transversal
CX, and data-idle depolarization after each extraction round.

Generate them with `examples(noise_model="circuit_level")`. Their metadata marks
`decoder_compatible=False`. The graph-only compiler intentionally rejects them:
Stim's decomposition contains detectorless logical components from correlated
faults. Increasing capacities or partitioning components does not resolve that
model mismatch. Do not upload lossy projections or discard these components.
The raw circuit-level single-fault uniqueness tests are retained, but they do
not establish support by the existing graph decoder.

## Generator and verification

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

Each record includes `id`, `label`, `circuit`, `logical_circuit`,
`decoder_compatible`, `decoder_limitation`, `noise_model_id`, `noise_model`,
`semantic_adaptation`, and `coupling_assumption`. A zero-noise request remains
noiseless and has no graph on its own: supply an explicit positive-noise reference
with identical ideal operations when a graph is needed.

```sh
qec/.venv/bin/python -m pytest qec/tests/test_encoded.py -q -o cache_dir=build/cache/pytest
```

The former two-/six-physical-qubit bare examples belong in `qec/tests/fixtures/`
for parser/transport regressions, not in the editor's QEC example list.
