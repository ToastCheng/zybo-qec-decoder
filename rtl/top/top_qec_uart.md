# Single-outstanding repetition UART protocol

Source: [`top_qec_uart.sv`](top_qec_uart.sv).

## Interface and frames

`btn[0]` passes through the reset synchronizer; other buttons and `sw` are unused.
The UART uses integer-divider `CLK_FREQ_HZ`/`BAUD_RATE`, idle high, LSB-first 8N1.
Request bytes are `A5 sequence syndrome xor`; XOR covers the first three bytes.
Response bytes are `5A sequence prediction cycles_lo cycles_hi xor`; prediction is
zero-extended to a byte and XOR covers the preceding five bytes. The sequence is
an opaque byte, not a counter the FPGA validates.

## Parser, decoder and transmit states

`HEADER` ignores noise until A5; `SEQ`, `SYNDROME`, `CHECKSUM` gather a request.
A good checksum enters `ACCEPT`. A bad checksum sets the red status flag and either
returns to HEADER or treats a checksum byte equal to A5 as the next header.
Partial requests time out after the parser gap counter reaches
`20 * (CLK_FREQ_HZ / BAUD_RATE)`, allowing a full byte plus inter-byte idle.
`rx_valid` clears the gap counter; a valid byte wins over timeout on the same edge.

`ACCEPT` holds core valid until ready. `DECODE` accepts the held core result and
builds six response bytes. `SEND` pulses the idle transmitter's start, `WAIT_TX`
waits for busy to rise, and `DRAIN` waits for it to fall before advancing. Only
completion of the final stop bit returns to HEADER and increments `completed`.
RX bytes are ignored while decoding/transmitting: the host must wait for the full
response before sending the next request; there is no request FIFO.

## Reset, LEDs and limits

Reset clears parser/core/response state and counters synchronously. UART primitives
have no reset port, so an active TX frame can finish despite a protocol reset;
allow idle before restarting traffic. `led[3:0]` is low completed-count bits;
`rgb_led` is `{checksum_error, 0, state != HEADER}`. The core's cycle field is a
fixed two-edge schedule, not serial latency. This design uses the PL UART pins,
not the board's PS-connected onboard USB UART route.

## Verification and related files

Run `python scripts/qec_sim.py` from root for exhaustive decoder/UART, checksum,
noise, timeout, reset and incoming bad-stop recovery checks. Run
`QEC_RTL=1 qec/.venv/bin/python -m pytest qec/tests/test_rtl_bridge.py -q` for the
host-generated wire exchange and independent parsing of real RTL responses.
See [`../common/uart_rx.sv`](../common/uart_rx.sv),
[`../common/uart_tx.sv`](../common/uart_tx.sv), and `qec/tb_host_bridge.sv`.
