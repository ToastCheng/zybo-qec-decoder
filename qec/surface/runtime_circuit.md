# Detector-annotated physical circuit compiler

`runtime_circuit.py` is independent of the restricted logical-template compiler.
`compile_circuit(text, reference_text=None, capacities=None)` accepts Stim physical
Clifford/reset/measurement circuits with `DETECTOR` and `OBSERVABLE_INCLUDE`
annotations. Gate compositions are not selected from memory/H/CX templates.
Stim defines gate semantics, including multi-Pauli measurement. Measurement-record
controlled gates and sweep controls are explicitly unsupported (no adaptive
feedback claim). Invalid gates, stochastic observables/checks and unrepresentable
noise fail with `ValueError`; no output is a hardware acceptance result.

This is **not arbitrary logical-to-fault-tolerant-QEC synthesis**. Callers supply
encoded experiments, checks, readout and noise themselves. A Clifford echo or
stabilizer verification experiment does not establish fault tolerance.

## API and limits

```python
from pathlib import Path
from qec.surface.runtime_circuit import compile_circuit, Capacities

text = Path('qec/examples/runtime/phase_bell.stim').read_text()
bundle = compile_circuit(text, capacities=Capacities())
assert bundle['edges'] == [[0, 1, 3], [0, 2, 1]]
```

The immutable `Capacities` object is trusted application configuration, not a
field accepted from untrusted circuit text. Initial decoder limits are 128
detectors, 512 edges and 32 observable bits. Physical qubit count is independent:
its frontend safety budget defaults to 1024, not 128. Qubit count follows Stim
(highest physical index plus one, including gaps).

Before **any Stim circuit parse or repeat expansion**, lexical preflight checks
UTF-8/source bytes (262144), repeat counts (1024), nesting (16), expanded
instruction upper bound (20000), expanded target/combiner budget (100000),
expanded text estimate (2097152) and qubit-count times instruction-count budget
(20000000). Physical and classical indices are bounded separately; record
lookbacks use the target budget. MPP products count combiners and factors even
without spaces. Observable index is checked before parsing, avoiding giant
observable arrays. Tags/comments do not increase executable work. Invalid brace
structure fails preflight. This intentionally conservative resource grammar is
not a promise to accept every alternative spelling Stim might parse (observable
indices must be unsigned decimal integers). Caller-raised budgets raise resource
exposure; an exposed service should additionally use worker process CPU/memory
limits. These budgets are not an OS sandbox or a wall-clock deadline guarantee.

After bounded parsing, dimensions are checked before expansion and exact Stim
reverse sensitivity analysis of `without_noise()` validates **both** detectors
and observables. This is stronger than finite-shot noiseless sampling. Noise DEM
extraction requests decomposition without ignoring failures, gauge detectors or
approximate disjoint-error conversion.

## Reference and graph contract

A circuit with no nonzero graph edges requires an explicit noisy reference. No
noise is invented. The reference's flattened noiseless operations, TICKs,
measurements and annotations must exactly equal those of the input. Its graph
must cover every actual input fault signature. Different but semantically
equivalent Clifford rewrites are conservatively not considered compatible.

`checked_graph` is reused without changing `compile.py`. It rejects residual
hyperedges, detectorless logical components, distinct observable masks on the
same endpoints, and any PyMatching projection that changes component signatures.
Repeated identical signatures can merge; an ordinary probability-zero fault
must not add an edge. Stim omits zero-probability circuit-generated errors;
reference DEM terms are additionally filtered for probability zero before graph
validation because `checked_graph` itself does not filter them. The complete
actual and reference DEM strings remain archived unchanged.

Edges are deterministic sorted `[a, b, mask]` records, preserving the existing
checked-graph convention rather than promising original DEM term order. Detector
IDs are unchanged Stim declaration order; the boundary is `num_detectors` and
observable bit `i` is `L_i`, including bit 31. Separator-correlated components
remain in the archived DEM, but the runtime graph uses independent edges. It is
an unweighted UF graph, not an assertion of weighted-MWPM equivalence.

## JSON-safe bundle

- `circuit`, `ideal`, `reference_circuit`: canonical Stim texts.
- `dem`, `reference_dem`: actual decomposed noise, not synthesized topology.
- `edges`, `boundary_vertex`, `counts`, `capacities`: exact runtime graph and
  measurement/TICK totals. Ticks count TICK separators, not extraction rounds.
- `layout.qubits`: stringified qubit IDs to final Stim coordinates (may be empty).
- `operations`: flattened declaration order, name, args, Stim target debug
  strings, executable `stim` instruction text, zero-based `tick`, first
  measurement index and result count. SHIFT_COORDS is resolved by Stim flattening.
- `detectors`: unchanged index, coordinates, declaration tick, absolute
  measurement-result indices and `available_after_operation` (zero-based operation
  index). This is structural availability, not a measured hardware latency.
- `stim_version`, `sha256`: hashes of canonical text fields and graph identity.
  Graph hash is SHA-256 of Python `json.dumps(graph, sort_keys=True)` UTF-8, where
  graph has `detectors`, `observables`, `edges`, `boundary_vertex`. Hashes identify
  host artifacts; they are not an FPGA-attested identity.

There is no serial access, filesystem output or board programming in this API.
Serialize the returned bundle with `json.dumps` in the integrating application.

## Verification

From repository root:

```sh
qec/.venv/bin/python -m pytest qec/tests/test_runtime_circuit.py -q
```

See [test walkthrough](../tests/test_runtime_circuit.md) and
[physical examples](../examples/runtime/README.md). Verification covers real Stim
and PyMatching software only; synthesis, routing, transport and board acceptance
remain separate integration boundaries.
