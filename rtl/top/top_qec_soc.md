# Zynq repetition-decoder integration shell

Source: [`top_qec_soc.sv`](top_qec_soc.sv).

## Boundary and wiring

The top forwards all DDR and FIXED_IO ports to generated `system_wrapper`; keeping
these as real top-level pins is required by the PS block design. The wrapper
exports `FCLK_CLK0_0`, active-low `peripheral_aresetn_0`, 32-bit GPIO control and
32-bit GPIO status. [`../common/qec_ps_bridge.sv`](../common/qec_ps_bridge.sv) shares
that clock and receives the inverted reset. There is no extra clock crossing or
state machine in this shell.

## Table and visible status

`defparam bridge.core.LUT_FILE = "lut.mem"` selects the build-local copied table,
not the root-relative simulation default. LEDs are `{status[17:16], status[1:0]}`:
upper two latency bits, prediction and acknowledgement toggle. They are diagnostic
bits, not a UART protocol or a complete latency display. PS firmware handles serial
traffic on its own UART and accesses PL via the generated GPIO.

## Verification and related files

Core/mailbox behavior: `make sim_surface` then `make sim_bridge` from root, with
Vivado tools on PATH. Integration elaboration requires the generated PS wrapper;
`vivado -mode batch -source scripts/build_soc.tcl -tclargs top_qec_soc` builds that
SoC and is distinct from a board-programming command. See
`scripts/bd/top_qec_soc.tcl`, `vitis/qec/src/main.c`, and
[`../common/qec_decoder.sv`](../common/qec_decoder.sv). Standalone core simulations
do not establish DDR pin connectivity, routed timing or physical board operation.
