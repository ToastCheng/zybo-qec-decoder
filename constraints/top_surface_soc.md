# `top_surface_soc.xdc`

[Source](top_surface_soc.xdc). User-LED pin assignments for the Zybo Z7-10 `top_surface_soc` PS/PL top, which runs the surface union-find decoder.

## Pins and clock ownership

The four active-high `led[0:3]` outputs use package pins M14, M15, G14 and D18 respectively, all with LVCMOS33 I/O. The top-level RTL defines their meaning; this constraints file only binds logical ports to board pins. See [the top implementation](../rtl/top/top_surface_soc.md).

The decoder clock comes from PS FCLK_CLK0 at 100 MHz. PS7-generated IP constraints own that clock; this file deliberately does not add the separate PL board's 125 MHz clock. DDR and FIXED_IO assignments also belong to the PS7 board preset rather than these four LED constraints.

## Use and verification

`scripts/build_soc.tcl` selects this XDC when building `top_surface_soc`. Inspect the generated timing and DRC reports for the complete design, not just the presence of pin commands here. Do not substitute `zybo_z7_10.xdc`, whose clock and ports target the external PL-UART design.
