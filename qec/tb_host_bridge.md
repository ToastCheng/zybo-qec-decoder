# Host packet files through real UART RTL

Source: [`tb_host_bridge.sv`](tb_host_bridge.sv).

## File and signal interface

`+shots=N` is mandatory and must be 1..4096. `requests.mem` contains four hex bytes
per shot in wire order and is loaded into a 16384-byte array. `responses.mem` is
opened for hex-byte output; open failure is fatal. The bench instantiates
`top_qec_uart` at 32 clocks per bit and uses an 8 ns simulation clock.

## Exchange and validation responsibilities

`send_byte` drives one LSB-first 8N1 frame on falling clock edges. An independent
TX sampler waits for each falling start edge, samples centers, rejects a low stop,
and writes one received byte per line. After sending four request bytes, the
stimulus waits for six more reply bytes plus two idle bit periods before sending
the next request. This respects the single-outstanding DUT contract.

This bench checks transport progress and outgoing stop bits, not the semantic
content of the reply. The Python host test parses `responses.mem`, checking XOR,
sequence and decoder predictions independently. Bad input packets without replies
would wait until the global 300000000 ns watchdog; this file-exchange bench expects
valid requests. Success prints the actual number of replies and closes the file.

## Verification and related files

From root: `QEC_RTL=1 qec/.venv/bin/python -m pytest qec/tests -q` enables the host
RTL integration tests when Vivado is available. Consult `qec/rtl_bridge.py` for the
runner and working-directory setup. See
[`../rtl/top/top_qec_uart.sv`](../rtl/top/top_qec_uart.sv) and
[`../rtl/tb/tb_qec_uart.sv`](../rtl/tb/tb_qec_uart.sv) for malformed/recovery coverage.
This does not open or program a physical board.
