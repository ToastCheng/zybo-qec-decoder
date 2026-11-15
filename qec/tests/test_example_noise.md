# Noise changes samples, not fixed FPGA graph

Companion to [`test_example_noise.py`](test_example_noise.py).

## Test flow and assertions

run_example() invokes the real module CLI from repository root with a bounded subprocess. At noise 0, 0.01 and 0.75, circuit dimensions and independently seeded sample/selected-shot truth must match printed JSON and zero detector residual. Zero noise retains a one-bit matching output. Invalid finite/out-of-range/NaN/infinite inputs are rejected both in circuit-only and decode paths. Default circuit text must match committed metadata.

## Test functions and helpers

- `run_example`
- `test_noise_controls_circuit_and_samples`
- `test_invalid_noise_is_a_cli_error`
- `test_default_noise_preserves_committed_circuit`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Stim and subprocess; no --port is supplied and graph artifacts are never regenerated.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_example_noise.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
