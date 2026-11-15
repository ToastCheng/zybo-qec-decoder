# `top_surface_soc.tcl`

[Source](top_surface_soc.tcl). Surface-code block-design fragment sourced by `scripts/build_soc.tcl` for `top_surface_soc`.

It sources `top_qec_soc.tcl` to share the PS7 board preset, PS UART1, 100 MHz FCLK/reset and dual-channel AXI GPIO mailbox. That shares transport wiring, not the repetition decoding algorithm. The selected RTL top instantiates the surface bridge and decoder.

The fragment adds the committed `qec/surface/graphs/d3_z_r3.mem` to the Vivado file set. Its contents and dimensions must match the RTL and ARM firmware's detector-byte width. It does not infer dimensions from ROM length or configure a different graph image. Equal detector counts alone do not make two graphs interchangeable.

```sh
vivado -mode batch -source scripts/build_soc.tcl -tclargs top_surface_soc
```

The caller validates the complete block design and generates its wrapper. This file is a Vivado fragment, not standalone Tcl, and neither programs the board nor validates an active hardware image. See [the common PS/GPIO fragment](top_qec_soc.md) and [SoC top](../../rtl/top/top_surface_soc.md).
