# Batch size, reproducibility and fresh default randomness

Companion to [`test_example_sampling.py`](test_example_sampling.py).

## Test flow and assertions

Parametrizes seed/shot pairs, repeats CLI execution byte-for-byte, independently reproduces the candidate batch and checks first nonzero detector row (or row zero), syndrome/observable and residual. Invalid positive-count/unsigned-seed limits must yield actionable parser errors. CircuitSpy intercepts sampler compilation to prove the default seed stays None rather than silently selecting a fixed seed.

## Test functions and helpers

- `test_seed_and_shots_match_stim_samples`
- `test_invalid_sampling_arguments`
- `test_default_seed_is_unset`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Stim, pytest monkeypatch/capsys and subprocess; no serial hardware or vendor tools.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_example_sampling.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
