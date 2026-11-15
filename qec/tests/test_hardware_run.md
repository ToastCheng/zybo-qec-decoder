# Separate implementation agreement from logical accuracy

Companion to [`test_hardware_run.py`](test_hardware_run.py).

## Test flow and assertions

Dynamically loads hardware_run without invoking main. Two synthetic row dictionaries deliberately produce zero LUT mismatches but nonzero reference disagreement and logical errors; median host time and fixed cycle extrema are checked independently. Flipping a prediction then proves LUT mismatch counting is live.

## Test functions and helpers

- `test_validate_rows_separates_lut_accuracy_and_observables`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

No port is opened and no build artifacts are copied. This tests evaluate only, not physical capture.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_hardware_run.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
