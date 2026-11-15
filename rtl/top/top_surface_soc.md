# Surface decoder Zynq shell

Source: [`top_surface_soc.sv`](top_surface_soc.sv).

## Ports and wiring

DDR and FIXED_IO ports forward one-for-one into the generated `system_wrapper`. Its 100 MHz FCLK drives the AXI GPIO mailbox and surface decoder in one clock domain. `peripheral_aresetn_0` is inverted for the bridge's active-high synchronous reset. The shell adds no buffering, algorithm or state machine.

The bridge uses its default d3 Z graph dimensions. A hierarchical `defparam bridge.core.GRAPH_FILE = "d3_z_r3.mem"` selects the ROM basename staged into Vivado's project. This top has no graph-identity parameter or runtime graph selection. Changes to graph dimensions or ROM require coordinated source/build/firmware changes; a matching detector count alone does not imply compatibility.

`led = status[31:28]` shows acknowledgement, result-present, error and prediction, in descending bit order. PS firmware owns the host-facing UART protocol; this is not the separate direct PL UART top.

## Verification

Run `make sim_surface` then `make sim_bridge` to check the core/mailbox logic. Full wrapper elaboration requires generated PS IP from `vivado -mode batch -source scripts/build_soc.tcl -tclargs top_surface_soc`. Inspect routed timing before programming; behavioral simulation does not prove routed SoC timing or physical board operation. See [the bridge](../common/surface_ps_bridge.md), [block design](../../scripts/bd/top_surface_soc.md) and [firmware](../../vitis/surface/src/main.md).
