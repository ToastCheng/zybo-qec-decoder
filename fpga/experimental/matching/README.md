# Experimental full-PL exact matching image

This is a separate, incompatible image for the frozen d3/r3 Z-memory graph in
`graph.json` (SHA256 `612138bcfd40ea7e4aae8e706215afc00944fe6811d1b4d3f951b9f747e22524`).
It is not a general runtime matching graph loader. Every graph upload checks
all 78 ordered endpoint/observable triples; weights are fixed lossless binary64
integers in `ops.svh`. The mailbox advertises experimental protocol 0xd303,
which the normal UF host rejects. Only the dedicated comparison runner may
normalize this version after explicitly checking this image contract.

The maintained PS, GPIO mailbox, top-level and ARM firmware are reused, with
only a separate mailbox version. Per-shot matching is entirely in PL, has no
software fallback, and executes every operation for every 24-bit syndrome.
The adapter independently counts acceptance-to-result cycles and raises decode
error if the exact core's counter disagrees. Neither counter includes UART,
ARM setup, graph validation or stalled retirement.

Build from a private build directory with Vivado:
`vivado -mode batch -source <repo>/fpga/experimental/matching/build.tcl`.
Build the unchanged firmware using `QEC_IMAGE_DIR=build/matching-board/image`
and `vitis -s <repo>/fpga/vitis/build.py`. The default build/loader remains UF.
Never launch the public UF preview against this experimental image.

Evidence and reproduction: research repository `fpga-qec/matching-board-comparison/`.
