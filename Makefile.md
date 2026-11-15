# `Makefile`

[Source](Makefile). Root-relative shortcuts for tests, simulation, building and loading the Zybo QEC examples. Run `make help` for the target list. Activate `qec/.venv` and configure AMD executable paths as described in the README first.

## Defaults and overrides

`PYTHON`, `VIVADO`, `VITIS`, `XSCT`, `XVLOG`, `XELAB` and `XSIM` select tools. `SOC_TOP=top_surface_soc` and `APP=surface` select the surface example; repetition uses `SOC_TOP=top_qec_soc APP=qec`. `SOC_NAME` removes `top_` to find matching bitstream/XSA names.

## Targets

- `test` runs Python regressions and the adjacent-documentation check; `example` runs the seeded-shot entry point with its defaults.
- `sim` runs repetition/UART RTL. `sim_surface` runs d3 Z (256 sampled shots), d5 Z and d3 X, writing separate logs.
- `sim_bridge` runs repetition and surface GPIO bridge testbenches, then validates both logs. Run `sim_surface` first: its d3 Z vector file is a bridge-test prerequisite.
- `build_soc` builds bitstream/XSA; `app` builds the selected ARM firmware.
- `run_soc` loads volatile PL/ARM state over JTAG. This changes the connected board and requires authorization. `readback` only reads configuration status.
- `reports MODE=core|uart` creates repetition synthesis/route reports without a bitstream. `netlist` checks the synthesized core and requires a prior `reports MODE=core` run.
- `clean` deletes local build, simulator and tool-log products. It does not remove historical result archives.

Tool exit status alone is not a hardware acceptance result. Inspect timing/DRC, use matching artifacts, then verify actual serial replies separately.
