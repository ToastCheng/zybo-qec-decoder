# Incoming stop-bit rejection and reset-free recovery

Source: [`tb_uart_rx_framing.sv`](tb_uart_rx_framing.sv).

## Setup and monitor

The receiver has 32 clocks per UART bit and a 10 ns test clock. Stimulus changes on
falling edges. The monitor samples one time unit after each rising edge, after NBA
updates, and rejects a multi-cycle valid pulse, an unexpected byte or extra bytes.
The only permitted output is one `3C` byte. There is no reset signal in the DUT.

## Scenarios and invariants

`send_frame` drives a low start, eight LSB-first data bits and an explicitly chosen
stop level. The bench first sends A5 with a low stop bit, inserts three idle-high
bit periods, and requires no accepted byte. It then sends 3C with a valid stop and
requires exactly one byte without resetting anything. A 100000 ns watchdog catches
failure to finish. This specifically tests incoming framing errors; inspecting
outgoing TX stop bits would not cover the same behavior.

## Verification and related files

Run `python scripts/qec_sim.py` from root; its first simulation prints
`PASS tb_uart_rx_framing: bad stop rejected, next frame recovered`.
See [`../common/uart_rx.sv`](../common/uart_rx.sv),
[`../common/sync.sv`](../common/sync.sv), and [`tb_qec_uart.sv`](tb_qec_uart.sv).
