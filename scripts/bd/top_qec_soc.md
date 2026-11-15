# `top_qec_soc.tcl`

[Source](top_qec_soc.tcl). Block-design fragment sourced by `scripts/build_soc.tcl` after it creates an empty `system` design. It requires Vivado's IP catalog and the Digilent Zybo Z7-10 board preset; it is not a standalone Tcl program.

## Wiring contract

The PS7 preset exports DDR and FIXED_IO, enables PS UART1 and sets FCLK0 to 100 MHz. The UART is on the PS side, so the onboard PROG/UART USB connection reaches ARM firmware rather than the separate PL UART pins.

A dual 32-bit AXI GPIO connects through PS `M_AXI_GP0`. Channel 1 is all outputs (PS command to PL); channel 2 is all inputs (PL status to PS). The assigned base is `0x41200000`; firmware writes command offset 0 and reads status offset 8. The decoder receives explicit external ports for FCLK0 and active-low peripheral reset so GPIO and decoder use the same domain.

The fragment adds `qec/lut.mem` for repetition decoding. The surface design reuses the PS/GPIO wiring but adds its own graph ROM. After sourcing, the caller validates the design and generates the HDL wrapper. Verify the whole flow using the [SoC builder](../build_soc.md); this fragment does not program a board.
