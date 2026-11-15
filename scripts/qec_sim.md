# `qec_sim.py`

[Source](qec_sim.py). Runs the repetition decoder and UART regressions using Vivado's `xvlog`, `xelab` and `xsim`, without contacting a board.

## Tool and working-directory selection

The repository root comes from the script path, not the caller's directory. `VIVADO_BIN` overrides executable discovery; otherwise the runner uses the directory containing `xvlog` on PATH, falling back to `~/amd/2025.2/Vivado/bin`. Each run works under `build/qec_sim` or `build/qec_netlist_sim`. A `qec` symlink lets ROM paths resolve there. A real `qec/lut.mem` must exist; no replacement LUT is generated.

## Execution

`run(tool, *args)` captures combined output, prints it and rejects nonzero exit status or HDL fatal markers. Normal mode compiles the RTL and runs receiver framing, decoder and UART testbenches. Every simulation must print `PASS `.

```sh
python scripts/qec_sim.py
```

`--netlist` instead compiles `build/qec_core/post_synth.v` with the exhaustive decoder testbench and Vivado `glbl`/`unisims_ver`. Generate that netlist with the [core report build](qec_build.md) first:

```sh
python scripts/qec_sim.py --netlist
```

The netlist check verifies the synthesized repetition LUT, not a surface-code image. Neither mode programs hardware or measures board latency.
