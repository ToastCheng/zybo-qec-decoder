# Stim-to-real-UART-RTL simulation bridge

Companion to [`rtl_bridge.py`](rtl_bridge.py).

## Contracts and flow

`run(shots, seed, noise, out=None)` generates Stim repetition windows, packs byte syndromes and writes concatenated A5 requests to `qec/.rtl/requests.mem`. A build-directory symlink makes the committed LUT visible to HDL. Old responses are removed before simulation.

The bridge invokes xvlog, xelab and xsim for the real UART top and `tb_host_bridge`, retaining each tool's combined output. It rejects nonzero returns, Fatal/FATAL diagnostics and a missing `PASS host wire exchange` marker. Each subprocess has a 150-second timeout. Tool discovery prefers VIVADO_BIN as a binary directory, otherwise the xvlog executable's parent, otherwise the versioned home fallback.

HDL response bytes are deliberately fed to the Python Parser in five-byte chunks. Frame count, absence of a trailing partial frame and modulo-256 sequence order must all match. Optional `out` receives `rtl_shots.csv` containing syndrome, sampled truth, prediction and cycles. Returned JSON-ready statistics compare RTL with both the fixed LUT and current-noise PyMatching.

The CLI bounds shots to 1..4096. The shared `qec/.rtl` directory is not safe for concurrent runs. Functional HDL cycles are not routed timing, physical-board evidence or UART roundtrip latency. This module does not open serial or program an FPGA.

## Callable index

- `run` — Run generated UART frames through xsim, validate replies, and return software/RTL comparisons.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/rtl_bridge.py --help
python -m pytest -q qec/tests/test_rtl_bridge.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
