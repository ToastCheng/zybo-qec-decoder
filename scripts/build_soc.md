# `build_soc.tcl`

[Source](build_soc.tcl). Full project-mode Vivado build for the Zybo Z7-10 (`xc7z010clg400-1`), including PS7 block design, PL decoder, bitstream and Vitis hardware handoff.

```sh
vivado -mode batch -source scripts/build_soc.tcl -tclargs top_surface_soc
```

## Configuration and flow

The optional top defaults to `top_surface_soc`; `top_qec_soc` selects repetition. Paths resolve from the repository. Board discovery uses `QEC_BOARD_REPO` when supplied, an adjacent AMD board-files directory when available, then Vivado's configured paths.

1. Delete and recreate `build/vivado_<name>`. This is a clean build, not an incremental one.
2. Source `scripts/bd/<top>.tcl`, validate/generate `system.bd`, and add its HDL wrapper.
3. Add shared RTL, the selected top and matching XDC.
4. Run implementation through bitstream generation and require 100% completion.
5. Write utilization and timing reports, copy the bitstream, and export an XSA containing it.

## Outputs and limits

For surface, outputs are `build/surface_soc.bit`, `build/surface_soc.xsa`, `build/top_surface_soc_utilization.rpt` and `build/top_surface_soc_timing_summary.rpt`. This script has no alternate-image directory or graph-generic configuration path. It builds files only, without loading PL or starting ARM software. Inspect tool DRC messages and routed timing before [loading](run_soc.md); completion alone is not timing acceptance. The implementation run may fail with details under the selected project directory.
