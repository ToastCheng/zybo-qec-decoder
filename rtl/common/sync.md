# Single-bit input synchronizer

Source: [`sync.sv`](sync.sv).

## Interface and algorithm

At each rising `clk` edge, shift `{shift_reg[STAGES-2:0], din}` into the chain.
`dout` continuously selects the oldest stage. The default two stages reduce the
probability of metastability escaping to downstream logic; they do not eliminate
it mathematically. The input level takes STAGES sampling edges to reach the output.

## Invariants and limits

There is no reset or initialization. Simulation output is unknown until the chain
fills; callers must allow settling before using it as reset or UART input. The
slice requires `STAGES >= 2`. This is for a single asynchronous level, not coherent
multibit buses, pulses shorter than a clock, button debouncing or handshake transport.

## Verification and related files

Run `python scripts/qec_sim.py` from root. UART framing and full UART protocol tests
exercise the receiver synchronizer and button-reset synchronizer in context.
See [`uart_rx.sv`](uart_rx.sv), [`../top/top_qec_uart.sv`](../top/top_qec_uart.sv),
and [`../tb/tb_uart_rx_framing.sv`](../tb/tb_uart_rx_framing.sv).
