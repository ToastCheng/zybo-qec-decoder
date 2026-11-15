# Serial target required, archive label optional

Companion to [`test_optional_board_id.py`](test_optional_board_id.py).

## Test flow and assertions

Parametrizes both physical capture CLIs with omitted and supplied --board-id. Each gets a nonexistent tmp_path serial device and one shot, so successful parsing must reach a real pyserial open error (exit 1), not argparse rejection (exit 2). Error text must identify the exact missing device.

## Test functions and helpers

- `test_board_label_is_optional`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Creates fresh temporary output directories but cannot contact hardware because the port path is verified absent.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_optional_board_id.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
