# Integer-divider 8N1 UART receiver

Source: [`uart_rx.sv`](uart_rx.sv).

## Pins and bit timing

`rx` is asynchronous and passes through [`sync.sv`](sync.sv). `data[7:0]` is the
shift register; only the one-clock `valid` pulse marks an accepted byte. Data may
change before valid. There is no reset, ready input, queue or framing-error output.
Timing is integer `CLK_FREQ_HZ / BAUD_RATE` clocks/bit with a half-bit start check;
parameter choices must keep the timer width and sampling interval meaningful.

## State transitions and recovery

`IDLE` notices a low synchronized level (not an explicit edge detector) and enters
`START`. After the half-bit countdown it rejects a high level as a glitch, or starts
`DATA`. Every full-bit countdown samples the next LSB-first bit; after bit 7 the
machine enters `STOP`. At the stop sample, it always returns to IDLE but pulses
valid only if the stop bit is high. Low stop bits are silently discarded; continued
low input can initiate another start attempt. A subsequent valid frame after idle
works without reset. Timers/state rely on FPGA initialization, while the input
synchronizer must first settle.

## Verification and related files

Run `python scripts/qec_sim.py` from root. `rtl/tb/tb_uart_rx_framing.sv` drives a
bad low stop, asserts no valid output, then receives `3C` without resetting.
`rtl/tb/tb_qec_uart.sv` exercises real byte framing through
[`../top/top_qec_uart.sv`](../top/top_qec_uart.sv). Integer division means configured
baud is approximate; these simulations do not characterize analog metastability.
