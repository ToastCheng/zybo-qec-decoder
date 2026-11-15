# `qec_build.tcl`

[Source](qec_build.tcl). Non-project repetition-decoder synthesis/routing flow. It produces reports, checkpoints and functional netlists, **not a bitstream**.

```sh
vivado -mode batch -source scripts/qec_build.tcl -tclargs core
vivado -mode batch -source scripts/qec_build.tcl -tclargs uart
```

## Modes and timing scope

`uart` is the default; any other mode besides `core` is rejected. Both require the real `qec/lut.mem` and target `xc7z010clg400-1`. Missing ROM-initialization diagnostic `Synth 8-2898` is promoted to an error.

- `core`: synthesize `qec_decoder` out of context, constrain its clock to 8 ns, and apply a 0.5 ns virtual synchronous input/output budget. These are evaluation boundaries, not measured board timing.
- `uart`: synthesize `top_qec_uart`, read the board XDC and exclude asynchronous UART/buttons/switches and unsynchronized output pins from external synchronous timing. Internal functional paths remain timed.

## Outputs and acceptance

`build/qec_<mode>/` receives post-synthesis and post-route utilization/timing reports, checkpoints, a post-synthesis Verilog netlist and routed DRC report. The script requires setup and hold paths and nonnegative worst slack, then prints `QEC_IMPLEMENTATION_COMPLETE` with both values.

Use `python scripts/qec_sim.py --netlist` after a core build to exhaustively exercise the actual synthesized LUT. Neither routed timing estimates nor a simulation establishes physical board latency. For a programmable PS/PL image use [build_soc.tcl](build_soc.md).
