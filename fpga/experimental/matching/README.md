# Experimental full-PL exact matching image

This is a separate, incompatible image for the frozen d3/r3 Z-memory graph in
`graph.json` (SHA256 `612138bcfd40ea7e4aae8e706215afc00944fe6811d1b4d3f951b9f747e22524`).
It is not a general runtime matching graph loader. Every graph upload checks
all 78 ordered endpoint/observable triples; weights are fixed lossless binary64
integers in `ops.svh`. The mailbox advertises experimental protocol 0xd303,
which the normal UF host rejects. Only the dedicated comparison runner may
normalize this version after explicitly checking this image contract.

The maintained PS, GPIO mailbox, top-level and ARM firmware are reused, with
only a separate mailbox version. Per-shot matching is entirely in PL and has no
software fallback. All 32 parity-frontier states advance in parallel through a
five-stage exact update for each of the 102 frozen operations. Nonempty inputs
take 512 cycles; zero syndrome takes one cycle, since every frozen weight is
strictly positive and the empty correction is the unique minimum. Edge order,
integer weights and skip-on-tie behavior are unchanged. The adapter independently
counts acceptance-to-result cycles and raises decode error if the exact core's
counter disagrees. Neither counter includes UART, ARM setup, graph validation or
stalled retirement.

Build from a private build directory with Vivado, selecting a fresh output:
`vivado -mode batch -source <repo>/fpga/experimental/matching/build.tcl -tclargs build/matching-new/image`.
Build the unchanged firmware using `QEC_IMAGE_DIR=build/matching-new/image`
and `vitis -s <repo>/fpga/vitis/build.py`. The default build/loader remains UF.
Never launch the public UF preview against this experimental image.

`capture.py` accepts an explicit `--real-shots` count and verifies truth labels
before serial I/O. Its matching cycle guard defaults to 512 for nonempty input.
Archived serial-core artifacts predate the zero bypass and have a different
schedule; use their original archived capture tool rather than mixing versions.
`verify.py` independently parses frames and compares every result with the
provided RTL edge-counted reference, using each archive's declared population.

Evidence and reproduction: research repository `fpga-qec/matching-optimization/`.
The earlier `fpga-qec/matching-board-comparison/` retains the serial baseline.
