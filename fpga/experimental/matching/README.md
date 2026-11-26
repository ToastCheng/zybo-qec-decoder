# Experimental fixed-d3 parallel exact matching image

This folder implements a specialized Zybo Z7-10 FPGA image that solves exact
weighted minimum-weight matching in programmable logic for **one frozen graph**:
three-round `d=3` rotated Z memory in `graph.json` (SHA-256
`612138bcfd40ea7e4aae8e706215afc00944fe6811d1b4d3f951b9f747e22524`, 24
detectors, 78 edges).

Because its frontier width is only 5 (`2^5 = 32` states), all 32 states live
in flip-flops and update in parallel through a five-stage XOR butterfly for
each of the 102 frozen DP operations:

- **Nonempty syndromes:** always take `512` clocks (`5.12 µs` at 100 MHz).
- **All-zero syndrome:** finishes in `1` clock (`10 ns`), since every frozen
  weight is strictly positive and the empty correction is uniquely optimal.
- **Exact weights and verification:** lossless `binary64`-derived integer
  weights are baked into `ops.svh`. The adapter still validates all 78
  uploaded `(endpoint_a, endpoint_b, mask)` triples against the frozen graph
  and runs a second independent cycle counter that raises `decode_error` if
  the core's counter ever disagrees.

## Protocol isolation

The image reuses the Zynq PS block design, AXI GPIO wiring, and ARM firmware
from `fpga/vitis/`, but advertises protocol version `0xd303` instead of UF's
`2`. That makes normal runtime-UF clients and `qec.surface.web` reject it
immediately. Only `capture.py` accepts `0xd303` after checking the frozen
graph contract.

## Building and verifying

Run from a private build directory with a fresh output path:

```sh
vivado -mode batch -source /path/to/repo/fpga/experimental/matching/build.tcl \
  -tclargs build/matching-new/image
QEC_IMAGE_DIR=build/matching-new/image \
  vitis -s /path/to/repo/fpga/vitis/build.py
```

The root `Makefile` still builds and loads the default runtime UF image. Do
not point `qec.surface.web` at this experimental image.

- `capture.py` replays a vector file over UART against either the UF or
  matching image (`--real-shots` sets the timed shot count, and
  `--matching-nonzero-cycles` defaults to `512`).
- `verify.py` independently parses archived UART frames and checks every
  prediction and cycle count against the RTL edge-counted reference.

Full board comparisons and the earlier serial prototype are archived in the
research repository under `fpga-qec/matching-optimization/` and
`fpga-qec/matching-board-comparison/`.
