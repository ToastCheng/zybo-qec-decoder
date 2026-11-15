# Exhaustive repetition LUT and bit order

Companion to [`test_decoder.py`](test_decoder.py).

## Test flow and assertions

Enumerates all 256 detector rows, checks eight detectors/one observable, table shape and exact weighted-reference predictions, then round-trips packing to addresses 0..255. No statistical agreement threshold replaces this complete truth table.

## Test functions and helpers

- `test_lut_matches_all_pymatching_syndromes`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

numpy and Stim/PyMatching; no serial or vendor tools.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_decoder.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
