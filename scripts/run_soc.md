# `run_soc.tcl`

[Source](run_soc.tcl). XSCT loader for volatile PL configuration and ARM Cortex-A9 core 0 firmware. **Running this script changes the connected board's active state.** It does not write boot flash.

```sh
xsct scripts/run_soc.tcl build/surface_soc.bit build/vitis_ws/surface_app/build/surface_app.elf build/surface_soc.xsa
```

## Inputs and sequence

The bitstream and ELF arguments are required; the XSA is optional if a generated `ps7_init.tcl` is available under `build/vitis_ws/<platform>/export/<platform>/hw/sdt`. The script infers the app/platform names from the ELF path. If that initialization script is missing and an XSA is supplied, it extracts `ps7_init.tcl` into `build/ps7_init`. Missing initialization stops execution.

After connecting to JTAG, it selects the `xc7z010` FPGA, loads the bitstream, selects the APU and runs `ps7_init` plus `ps7_post_config` for DDR, MIO and clocks. It then selects ARM core 0, resets that processor, downloads the ELF and starts execution.

## Acceptance boundary

Use artifacts from the same image build, close competing serial clients first and obtain permission before loading. Target filters assume this board/device family; discover attached targets before use when several boards are connected. A successful loader message means JTAG operations completed, not that the graph identity or decoder replies are correct. Follow with configuration-status readback and real serial transactions. Power loss discards this loaded state.
