# Runtime SoC top

`top_runtime_soc.sv` is the PS/PL boundary for the runtime-loadable decoder image.
It retains the Zynq DDR and FIXED_IO ports required by the generated
`system_wrapper`, plus four Zybo Z7-10 LEDs. It does not instantiate or configure
a fixed graph decoder.

## Clock, reset and capacity

The wrapper exports `FCLK_CLK0_0` at 100 MHz and `peripheral_aresetn_0`.
The 32-bit GPIO command/status mailbox and `runtime_surface_ps_bridge` use this
same clock. The top inverts the active-low peripheral reset for the bridge's
active-high `rst`; there is no payload clock-domain crossing here.

Top parameters `MAX_DETECTORS=128`, `MAX_EDGES=512` and
`MAX_OBSERVABLES=32` are forwarded unchanged to the bridge. These are synthesized
capacity ceilings, not runtime circuit dimensions. Actual dimensions and edges
arrive through the mailbox after boot. Full reset loses the loaded graph.

LEDs 3, 2, 1 and 0 show `status[31]` acknowledgement toggle,
`status[30]` result-complete, `status[29]` error and `status[0]` read-data LSB.
The last LED is not an independent configuration-valid indicator; its meaning
depends on the selected mailbox read.

## Build and evidence

Use [the standalone build](../../scripts/build_runtime.md), which selects only
the runtime decoder, bridge, this top and the generated PS wrapper. The top has
no ROM filename override. [Constraints](../../constraints/top_runtime_soc.md)
cover only the LEDs; PS-generated constraints own DDR/MIO and clock timing.

`qec/tests/test_runtime_build.py` checks forwarding and wrapper/reset wiring
structurally. This is not HDL elaboration, synthesis, timing or board evidence.
A real build requires the sibling runtime decoder and bridge implementations.
