# Integer-divider 8N1 UART transmitter

Source: [`uart_tx.sv`](uart_tx.sv).

## Interface and acceptance

A high `start` in `IDLE` captures `data[7:0]` into `data_reg` at the rising edge.
`busy` is combinationally high outside IDLE. Starts while busy are ignored, with no
queue or error indication. A continuously high start causes another frame once
IDLE is reached. No reset port exists; FPGA register initialization establishes
state, timer, bit index and data.

## State and serial waveform

`IDLE` drives tx high; `START` drives low for `CLK_FREQ_HZ / BAUD_RATE` clocks;
`DATA` selects `data_reg[bit_index]` LSB first, incrementing the index after each
bit period; `STOP` drives high for one bit period, then returns to IDLE. Timer and
bit index return to zero through normal progression. Integer division sets the
actual baud and requires a valid nonzero timer width. The captured byte is stable
regardless of input data changes while busy.

## Verification and related files

Run `python scripts/qec_sim.py` from root. The UART integration test samples reply
bits with its own bit-level receiver, validates high stop bits, checks all response
bytes and exhausts all 256 LUT addresses. See
[`../tb/tb_qec_uart.sv`](../tb/tb_qec_uart.sv) and the SEND/WAIT_TX/DRAIN sequence in
[`../top/top_qec_uart.sv`](../top/top_qec_uart.sv). A protocol reset there does not
abort an already-transmitting primitive frame.
