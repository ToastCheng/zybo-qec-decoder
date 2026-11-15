# Sweep reproducibility and honest software timing

Companion to [`test_experiments.py`](test_experiments.py).

## Test flow and assertions

Runs the real CLI for 2000 shots per noise at seed 12345 into tmp_path. Independently resamples all seven points and verifies every decoder error count and Wilson containment. Checks 21 CSV rows, software-only metadata, all four timing methods, positive durations and nonempty PNGs. Exact timing values are deliberately not asserted.

## Test functions and helpers

- `test_reproducible_sweep_benchmarks_and_charts`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

matplotlib Agg, CSV/JSON readers and subprocess; no board.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_experiments.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
