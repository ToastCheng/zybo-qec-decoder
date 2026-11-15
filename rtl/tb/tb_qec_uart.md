# Bit-level UART protocol regression bench

Source: [`tb_qec_uart.sv`](tb_qec_uart.sv).

## Serial model and storage

The DUT uses 3.2 MHz/100 kbaud timing parameters (32 clocks per bit) under an 8 ns
simulation clock. The absolute wall-clock baud is intentionally accelerated; the
clock-to-bit ratio is what matters. `send_byte` drives start, eight LSB-first bits,
and stop at falling clock edges. An independent receiver samples TX bit centers,
requires a high stop bit, and appends to the 4096-byte `replies` array. It does not
reuse the DUT RX implementation. Expected predictions come from the real LUT.

## Scenario sequence

Noise and a deliberately corrupted checksum must yield no reply. Valid requests
use header-like sequence/syndrome values to check byte framing. Reset interrupts
an incomplete packet; another truncated packet is allowed to time out without
reset. The next valid requests must succeed after each recovery. Finally all 256
syndrome values are requested. `check_reply` validates all six bytes including
sequence, prediction, two-byte cycles and XOR. Exactly 1560 received bytes (260
replies) are required. The global watchdog reports the receive count on deadlock.

## Verification and related files

Run `python scripts/qec_sim.py` from root; expect the UART PASS marker mentioning
260 replies. See [`../top/top_qec_uart.sv`](../top/top_qec_uart.sv),
[`tb_uart_rx_framing.sv`](tb_uart_rx_framing.sv) for incoming bad-stop coverage, and
`qec/tb_host_bridge.sv` for externally generated requests. This is digital RTL
verification, not physical baud-tolerance or metastability characterization.
