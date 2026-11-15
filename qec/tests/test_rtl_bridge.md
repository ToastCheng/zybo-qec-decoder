# Opt-in full Stim-to-UART HDL integration

Companion to [`test_rtl_bridge.py`](test_rtl_bridge.py).

## Test flow and assertions

With QEC_RTL=1, launches 256 real RTL transactions at seed 314159/noise 0.03 and requires received-frame count, exact LUT predictions and two-cycle metadata. Independently resamples the circuit to compare each archived CSV syndrome, observable and prediction. The report must still mark fpga_measured=false.

## Test functions and helpers

- `test_stim_requests_cross_real_uart_rtl`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Skipped by default. Opt in with QEC_RTL=1 and real Vivado xvlog/xelab/xsim available; simulation is not a board measurement.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_rtl_bridge.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.
