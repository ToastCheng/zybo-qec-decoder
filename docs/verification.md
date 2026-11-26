# Verification

This page summarizes what has been verified across software, RTL simulation,
Vivado routing, and physical Zybo Z7-10 hardware runs, along with where the
archived evidence lives.

Scope reminder: the runtime decoder compiles detector-annotated physical
Clifford circuits and uploads their decoding graphs without rebuilding the
FPGA image. It decodes completed simulated shots rather than compiling
arbitrary logical programs or driving live adaptive quantum feedback.

## How to run the current test suites

- `make test` runs the Python test suite, documentation/link checks, and Node
  UI tests.
- `make sim` runs the SystemVerilog core, mailbox bridge, and long-counter
  testbenches in Vivado `xsim`.

See the [quick start](quickstart.md) for building and loading the board, and
the [code walkthrough](code-walkthrough.md) for how each test maps to the
source tree.

## Simulation, firmware, and browser test coverage

- **RTL simulation (`fpga/rtl/tb/`):** Real Vivado `xsim` benches reload
  multiple graph sizes inside one simulation and check every prediction
  against `qec.surface.decoder.decode`. Coverage includes 32-bit observable
  masks (bit 31), rejected/poisoned uploads and recovery, backpressure while
  results are held, shot abort (keeps graph), full reset (clears graph),
  high unused syndrome bits, and independent clock-edge counting.
  - The core corpus runs 12 graphs and 474 shots.
  - A separate compiler-to-core corpus runs 128 Stim shots each on five
    circuits: two-qubit phase-Bell, six-qubit repetition echo, `d3 Z/r3`,
    `d3 X/r5`, and `d5 Z/r3`. All hardware predictions match the Python UF
    reference (the `d3 X/r5` batch had 2 logical failures against Stim truth,
    expected under noise).
  - A long-path diagnostic naturally crosses the 16-bit cycle boundary at
    287,940 clocks to verify both 16-bit cycle metadata words.
- **ARM firmware and host transport (`fpga/vitis/tests/`, `qec/tests/`):**
  Native C tests compile the real firmware parser and GPIO adapter under
  ASan/UBSan. Host tests drive real PTY byte streams, including delayed
  complete replies, malformed frames, CRC errors, and serial-lock conflicts.
  Both firmware and host guard against PL reset aliasing a toggle-0 ACK by
  requiring `DONE = 1`, positive cycles, and an unchanged graph generation;
  after any uncertain serial timeout, the host blocks writes until
  `resynchronize()` drains the pending reply and the graph is reloaded.
- **Web UI and browser checks (`qec/tests/*.cjs`):** Cover the preset
  dropdowns, custom Stim editor, bit-31 masks, 1,024-qubit index grid,
  360 px mobile layout, edit invalidation, zero hardware traffic on page load
  or local replay, and fault injection lists.

## Encoded circuit examples and window partitioning

The default encoded presets use real distance-3 rotated surface-code patches
(9 data qubits + 8 reused extraction ancillas per patch):

- **Encoded Bell:** 34 physical qubits, 144 detectors, 340 edges, 2 logical
  observables (2 hardware windows).
- **Encoded echo:** 102 physical qubits, 720 detectors, 1,716 edges, 6
  logical observables (6 hardware windows).

See [encoded circuit examples](../qec/examples/README.md) for the restricted
storage/readout noise model and nonlocal transversal-CX assumptions used by
these presets.

What was verified:

- **Exact single-fault coverage:** Every distinct raw single-fault signature
  (340 for Bell, 1,716 for echo) matches the compiled graph edge set exactly
  and decodes with zero mismatches under unweighted UF. Unsupported fuller
  circuit-level noise models remain rejected by the compiler.
- **Software runs:** At 128 shots (`seed 42`), Bell had 0 logical failures
  and echo had 1; at `seed 123`, echo had 0 logical failures. All shots had
  zero UF reference mismatches.
- **Physical FPGA CLI runs:** On the loaded Zybo board (no reprogramming),
  both presets ran 8-shot batches (`seed 42`) with zero logical failures and
  zero reference mismatches. Independent frame checks verified framing,
  length, CRC-32, sequence numbers, status, and multi-window mask/cycle
  recombination across all 169 Bell UART transactions (16 core decodes) and
  625 echo transactions (48 core decodes).
- **Physical FPGA web runs:** Both presets completed end-to-end in the web
  UI, showing 34 physical / 2 logical wires for Bell (with a listed Z fault on
  `q0` at tick 8 matching the simulated observable) and 102 physical / 6
  logical wires for echo (`11,551` summed core cycles across 6 windows,
  excluding upload and UART time), with zero POST requests during replay.

![Encoded Bell on the physical FPGA, with injection controls below the layout](images/encoded-bell-fpga.png)

## Reorganized build and unified web interface

After consolidating the repository under `fpga/` and unifying the web UI under
`python -m qec.surface.web`, a fresh Vivado/Vitis build produced matching
`qec_soc.bit`, `qec_soc.xsa`, and `qec_app.elf` artifacts (bitstream inside
the `.xsa` verified byte-for-byte against `qec_soc.bit`; imported firmware
sources matched `fpga/vitis/src/`). Loaded over volatile JTAG without writing
flash, the unified web UI completed physical FPGA runs for the memory preset
(761 core cycles) and a 6-qubit repetition check (21 core cycles), and a
128-shot 6-qubit CLI run passed with zero reference mismatches and zero
logical failures. The [quick start screenshot](images/web-fpga-layout.png)
captures this unified UI after a physical FPGA run.

## Archived initial runtime build and six-graph board acceptance

The historical archives below belong to the initial pre-reorganization runtime
image (`runtime_soc.bit` / `runtime_app.elf`, built with Vivado/Vitis 2025.2
for `xc7z010clg400-1` at 100 MHz, 128 detectors / 512 edges / 32 observables).
Their original filenames are kept untouched as provenance:

- **Routed build archive**
  ([manifest](../qec/surface/results/runtime-build-20261115-v2/manifest.json)):
  The first unpipelined route missed 100 MHz setup by 3.479 ns; splitting
  graph-RAM, label-RAM, union-selection, and parity-write steps into
  registered FSM stages closed timing at the same capacity and clock with
  **+0.095 ns** setup slack, **+0.038 ns** hold slack, 7,822 LUTs, 3,184
  registers, 3 RAMB18 tiles, and zero routed DRC findings (retaining Digilent
  PS DDR skew warnings and four unconstrained LED output notices without
  waivers). Large binary artifacts stay outside Git and are listed as external
  in the manifest.
- **Six-graph physical board archive**
  ([manifest](../qec/surface/results/runtime-board-20261115/manifest.json)):
  Loaded over volatile JTAG (verified `DONE = 1`, `INIT_B = 1`, `CRC_ERROR =
  0`; no flash write). Without reprogramming between circuits, the board
  uploaded and decoded six distinct graphs — phase-Bell, two repetition
  echoes, a three-qubit Clifford circuit exercising observable bit 31,
  `d3 Z/r3`, `d3 X/r5`, and `d5 Z/r3`. Across 768 Stim shots and 251
  diagnostic windows, all **1,019 FPGA predictions matched the Python UF
  reference**, and all **3,096 UART frames** passed independent CRC/sequence
  verification against regenerated Stim truth (0 logical failures in that
  finite sample).

For later benchmarks — including the core-scan optimization (9,048 LUTs,
+0.190 ns setup slack) and the 4-curve on-board UF vs. exact-matching sweep —
see [core performance](core-performance.md),
[accuracy results](benchmark-accuracy.md), and
[decoder performance](benchmark-timing.md).
