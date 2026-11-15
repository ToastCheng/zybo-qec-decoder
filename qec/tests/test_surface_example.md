# Single-window output and optional wire replay

Companion to [`test_surface_example.py`](test_surface_example.py).

## Test flow and assertions

Runs the checked-in example with seed 20261107 and checks real noisy detector indices, little-endian syndrome, residual, logical-error flag and request bytes. Circuit-only output is parsed by Stim and must retain the committed noise. The serial test starts the actual CLI against a local PTY, requires the exact request for syndrome 2048 and sends a checksummed reply reporting 937 cycles; printed board fields must preserve those bytes.

## Test functions and helpers

- `test_surface_example_explains_a_real_noisy_shot`
- `test_surface_example_prints_the_actual_circuit`
- `test_surface_example_serial_path`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Unix pty/select and pyserial. The scripted reply is explicitly local transport evidence, not a physical FPGA timing result.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_surface_example.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
