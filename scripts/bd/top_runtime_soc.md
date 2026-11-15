# Runtime PS block design

`top_runtime_soc.tcl` is sourced by [build_runtime.tcl](../build_runtime.md)
after `create_bd_design system`. It is self-contained and never sources the
fixed-image block-design scripts or adds graph/LUT files.

1. Instantiate PS7 5.5 and apply the Zybo board preset, externalizing DDR/FIXED_IO.
2. Enable PS UART1 and configure FCLK_CLK0 to 100 MHz.
3. Instantiate dual-channel AXI GPIO 2.0: channel 1 is a 32-bit command output;
   channel 2 is a 32-bit status input.
4. Apply AXI automation using PS `M_AXI_GP0` and the automatic clock/reset network.
5. Export GPIO plus FCLK_CLK0 and the generated `rst_ps7_100M` peripheral reset.
6. Assign the GPIO register segment to `0x41200000`. Firmware uses channel data
   offsets `0x00` and `0x08`.

The generated wrapper ports match [top_runtime_soc](../../rtl/top/top_runtime_soc.md).
The reset output is active low. The top converts its polarity, not its clock
domain. The preset supplies PS DDR/MIO routing and UART physical connectivity;
there is no PL UART pin constraint in this image.

The orchestration test executes these Tcl commands under a logging harness and
checks the configured frequency. It cannot validate IP automation or generated
port/reset names. Vivado `validate_bd_design`, synthesis and route remain required
for actual hardware acceptance. No DRC severity is modified here.
