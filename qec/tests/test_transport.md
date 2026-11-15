# Repetition protocol rejection and recovery boundaries

Companion to [`test_transport.py`](test_transport.py).

## Test flow and assertions

Exercises 2000 held-out loopback windows and CLI JSON against actual observable truth. A real pyserial PTY exchanges 32 framed requests with split replies while requiring fpga_measured=false. LateEndpoint deliberately returns after deadline; Endpoint dribbles one byte at a time to cover partial data, wrong sequence, checksum, nonbinary prediction and timeout. Garbage scanning must retain no unbounded buffer.

## Test functions and helpers

- `test_loopback_heldout_circuits_and_cli`
- `test_pyserial_pty_cli_marks_output_as_unmeasured_hardware`
- `test_expired_response_is_not_accepted`
- `test_partial_response_and_exact_request`
- `test_exchange_validates_sequence_checksum_and_timeout`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Unix PTYs, threads, bounded waits, numpy and pyserial. All endpoints are local software, not FPGA evidence.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_transport.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
