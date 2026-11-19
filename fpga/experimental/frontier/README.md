# Experimental programmable d3/d5 exact matching frontier image

`fpga/experimental/frontier/` implements a runtime-program-loadable exact
minimum-weight T-join parity-frontier decoder in Zybo Z7-10 PL. It supports
frontier width up to 12 (up to 4,096 live parity states across four parallel
BRAM lanes), up to 128 detectors, up to 512 DP operations (1,024 two-record
mailbox uploads), 64-bit unsigned exact integer costs with explicit infinity
saturation, and one logical observable bit.

This image is intentionally incompatible with the maintained runtime-UF host:

- Metadata word 0 is `0xd505` (not UF's `2`), so `GraphDecoder` and the public
  UF web server fail closed.
- Configuration opcodes load a parity-DP program (two indexed 10-byte records
  per operation), not UF `(endpoint_a, endpoint_b, observable_mask)` edges.
- PL computes an IEEE CRC32 over every accepted 10-byte configuration record
  and exposes it in metadata words 15..16; `capture_curves.py` requires exact
  CRC readback before and after decoding each circuit/noise point.
- A separate PL cycle counter runs independently of the datapath FSM and raises
  `decode_error` on any discrepancy.

## Build and verification

From an isolated build directory:

```sh
vivado -mode batch -source fpga/experimental/frontier/build.tcl \
  -tclargs build/fpga-four-curves/image-v2
QEC_IMAGE_DIR=build/fpga-four-curves/image-v2 \
  vitis -s fpga/experimental/frontier/build_firmware.py
```

Default `make build` / `make firmware` / `make load` remain the maintained
runtime UF image. Restore the maintained UF image before starting
`qec.surface.web`.

Archived four-curve Zybo board evidence lives in the research repository under
`fpga-qec/fpga-four-curve-benchmark/`.
