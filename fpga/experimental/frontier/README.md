# Experimental programmable exact matching (d=3 and d=5)

This folder implements an experimental Zybo Z7-10 FPGA decoder that solves
**exact weighted minimum-weight matching** (minimum-weight T-join) in
programmable logic using parity-frontier dynamic programming (DP). Unlike the
fixed `d=3` prototype in `fpga/experimental/matching/`, you can upload new
DP schedules at runtime without rebuilding the bitstream — including both
`d=3` and `d=5` rotated surface-code memory graphs.

## Hardware capacities and design

- **Frontier states:** width up to 12 (up to `2^12 = 4,096` live parity
  states) stored across four parallel BRAM lanes
- **Detectors and program size:** up to 128 detectors and 512 DP operations
  (uploaded as 1,024 indexed 10-byte records)
- **Weights and output:** exact 64-bit unsigned integer costs with explicit
  infinity saturation, and 1 logical observable bit
- **Independent cycle guard:** a second PL cycle counter runs alongside the
  datapath FSM and raises `decode_error` if the two counts ever disagree

## Separate protocol (incompatible with runtime UF)

This image uses its own protocol so ordinary union-find tools cannot
accidentally talk to it:

- Metadata word 0 reports protocol version `0xd505` (instead of UF's `2`), so
  `GraphDecoder` and `qec.surface.web` fail closed.
- Configuration commands upload parity-DP program records (two 10-byte
  records per operation) rather than UF `(endpoint_a, endpoint_b, mask)`
  edges.
- PL computes an IEEE CRC-32 over every accepted 10-byte program record and
  exposes the digest in metadata words 15 and 16. `capture_curves.py` checks
  that hardware digest before and after decoding each noise point.

## Building the image and firmware

Run from a fresh build directory so you do not overwrite the default runtime
UF image:

```sh
vivado -mode batch -source fpga/experimental/frontier/build.tcl \
  -tclargs build/fpga-four-curves/image-v2
QEC_IMAGE_DIR=build/fpga-four-curves/image-v2 \
  vitis -s fpga/experimental/frontier/build_firmware.py
```

The root `Makefile` (`make build`, `make firmware`, `make load`) always
targets the default runtime UF image. Reload the runtime UF image before
launching `qec.surface.web`.

Raw four-curve Zybo board captures, DP schedules, and route reports are
archived in the research repository under
`fpga-qec/fpga-four-curve-benchmark/`.
