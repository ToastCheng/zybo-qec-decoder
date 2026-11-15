# Runtime physical-circuit compiler tests

`test_runtime_circuit.py` exercises the general frontend with actual Stim 1.16.0
and PyMatching 2.4.0, not fake circuit or graph implementations.

Run from repository root:

```sh
qec/.venv/bin/python -m pytest qec/tests/test_runtime_circuit.py -q
qec/.venv/bin/python -m pytest qec/tests -q
```

The implementation was developed in RED→GREEN slices: missing module, missing
reference requirement/resource capacities, reference fault coverage and hash
fields, independent measurement-record bounds/MPP target counts, then operation
availability metadata were each observed failing before their implementation.
Existing rejection behavior inherited from Stim/checked_graph was tested directly
rather than deliberately broken to manufacture failures.

Coverage includes H/S/CX/inverse compositions; multiobservable masks including
bit 31; strict reference compatibility and required explicit reference for empty
noise graphs; exact nondeterministic detector and observable rejection; ambiguous
endpoint masks; detectorless logical faults; undecomposable three-detector
hyperedges; actual separator-correlated four-detector decomposition; harmless
zero-probability terms; repeat ordering and SHIFT_COORDS; independent long record
lookbacks; feedback/sweep rejection; JSON serialization; layout, TICK and
measurement availability metadata. Resource tests replace Stim's Circuit
constructor with a failure sentinel to prove oversize text, repeat products,
qubit/observable indices, nesting and MPP products are rejected before parsing.

Both checked-in examples are compiled, noiseless-sampled (100 shots each), and
noisy-sampled/decoded (1000 shots each) with real libraries and fixed seed 5.
Phase-Bell predictions exactly equal the two observed parities in this sample;
the repetition experiment only requires output shape and actual sampled noise,
not a false promise of perfect correction at arbitrary fault multiplicity.

These tests establish software compilation and reference-decoder execution.
They do not test runtime RTL, serial transport, board configuration, resource
fit, latency, physical correction or adaptive quantum feedforward.
