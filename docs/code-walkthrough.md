# Code walkthrough

If you want to understand how a Stim circuit turns into an FPGA prediction,
read these six files in order:

1. [run.py](../qec/surface/run.py) — CLI entry point that coordinates a batch
   run.
2. [circuit.py](../qec/surface/circuit.py) — validates a Stim circuit and
   compiles its decoding graph.
3. [decoder.py](../qec/surface/decoder.py) — Python reference implementation
   of the union-find decoder.
4. [host.py](../qec/surface/host.py) — UART framing, graph upload, and shot
   decoding on the host.
5. [main.c](../fpga/vitis/src/main.c) — ARM firmware that bridges UART packets
   to the AXI GPIO mailbox.
6. [top_qec_soc.sv](../fpga/rtl/top/top_qec_soc.sv) — FPGA top level wiring
   the Zynq processor to the mailbox bridge and decoder core.

For installation and board commands, see the [quick start](quickstart.md). For
the union-find algorithm and exact bit layouts, see
[decoder design](decoder-design.md).

## Directory map

```text
qec/surface/               Compiler, Python decoder, UART host, CLI, and web server
  web_assets/              Browser UI (lattice view, circuit diagram, detector matrix, replay)
  results/                 Archived hardware captures and build snapshots (historical evidence)
qec/examples/              Annotated Stim circuit presets (Bell and GHZ echo)
qec/tests/                 Python, native-C firmware, and Node/browser test suites
fpga/rtl/                  SystemVerilog decoder core, mailbox bridge, board top, and testbenches
fpga/constraints/          Zybo Z7-10 clock and pin constraints
fpga/scripts/              Vivado/XSCT Tcl scripts (bd/ builds the Zynq PS7 + AXI GPIO design)
fpga/vitis/                ARM firmware source, hardware adapter, and Vitis build script
fpga/experimental/         Separate exact-matching FPGA experiments (frontier and fixed-d3)
scripts/                   RTL simulator wrapper, timing check, benchmarks, and doc-link tests
docs/                      Guides, design spec, verification records, and benchmarks
build/                     Generated bitstreams, logs, caches, and temporary outputs
```

## Follow one CLI run

1. **Compile the circuit.** [run.py](../qec/surface/run.py) loads the `.stim`
   file and passes it to `compile_circuit()` in
   [circuit.py](../qec/surface/circuit.py). The compiler caps input size and
   repeat expansion, verifies that all detectors and observables are
   deterministic when noise is turned off, and extracts an ordered edge list.
   [graph.py](../qec/surface/graph.py) checks that every fault maps cleanly to
   a graph edge (rejecting hyperedges, detectorless logical flips, and
   conflicting observable masks). If the circuit has zero noise, you must pass
   a compatible noisy `--reference` circuit so the compiler has a graph to
   extract.
2. **Sample shots.** Stim generates packed detector bits and true logical
   observable flips for every shot. Detector `i` sits at bit `i` of the
   syndrome integer. True observables stay on the host.
3. **Decode in software or on hardware.**
   - Without `--port`, [decoder.py](../qec/surface/decoder.py) decodes every
     shot in Python.
   - With `--port`, [host.py](../qec/surface/host.py) queries the board's
     capacities, uploads the ordered graph, and sends each shot's detector
     bits over UART.
   - If a circuit has more detectors or edges than one hardware window
     supports (128 detectors / 512 edges by default),
     [partition.py](../qec/surface/partition.py) groups whole disconnected
     detector components into hardware-sized windows without cutting any
     detector-to-detector edge, uploads and decodes each window in turn, and
     XORs their returned observable masks.
4. **Compare and archive.** For every shot, the runner tracks two separate
   counts: logical accuracy against Stim's true observables, and
   implementation agreement against the Python union-find reference. It writes
   the compiled graph, per-shot results, summary JSON, and version/hash
   manifest into a fresh `--out` directory (plus raw UART frames in FPGA
   mode). If an FPGA call fails, partial outputs and the error details are
   saved instead of silently falling back to software.

## Follow one web run

- [web.py](../qec/surface/web.py) is the single HTTP server and CLI entry
  point. It serves the static files in
  [web_assets/](../qec/surface/web_assets/) and routes API requests to
  [engine.py](../qec/surface/engine.py).
- [engine.py](../qec/surface/engine.py) coordinates presets, layout previews,
  and run execution across both software and FPGA backends.
- [model.py](../qec/surface/model.py) handles the rotated surface-code memory
  preset, including computing the host's illustrative physical correction
  overlay.
- [simulation.py](../qec/surface/simulation.py) compiles untrusted custom
  circuits inside a bounded subprocess and steps Stim's `FlipSimulator` tick
  by tick so the browser can animate Pauli errors and active gates.
- [encoded.py](../qec/surface/encoded.py) generates the tested distance-3
  encoded Bell and six-patch GHZ echo presets along with their logical
  diagrams. Custom user-supplied logical text is accepted for display and
  marked as unverified. See [encoded circuit examples](../qec/examples/README.md)
  for the noise assumptions behind those presets.

Loading the page, switching presets, or editing parameters never talks to the
FPGA. Clicking **Simulate and decode** runs one shot and returns the complete
trace; Play, Step, and the timeline scrubber then run purely in the browser.
Keep in mind that Stim `TICK` steps, stabilizer extraction rounds, browser
playback speed, and measured FPGA clock cycles are four distinct quantities.

## ARM transport and programmable-logic decode

On the Zybo Z7-10, the ARM Cortex-A9 processor (PS) sits outside programmable
logic (PL) and connects to it through a 32-bit AXI GPIO channel:

- [main.c](../fpga/vitis/src/main.c) parses framed UART requests (`0xD4`
  header, IEEE CRC-32 trailer), translates each opcode into mailbox commands,
  and sends `0x4D` replies. [platform.h](../fpga/vitis/src/platform.h) wraps
  the Zynq UART, GPIO registers, and millisecond timer.
- [ps_bridge.sv](../fpga/rtl/common/ps_bridge.sv) implements the PL side of
  the toggle mailbox: it stages graph dimensions and edges, writes syndrome
  words, launches decodes, and returns status/metadata words.
- [qec_decoder.sv](../fpga/rtl/common/qec_decoder.sv) stores the uploaded
  edges and runs the serial union-find and forest-peeling FSM. Pipeline
  registers split memory reads, cluster selection, and updates across clock
  cycles so the design meets 100 MHz timing. A dedicated counter measures
  acceptance-to-result cycles (excluding stalls while waiting for the bridge
  to read out the result). A shot abort drops the active shot while keeping
  the loaded graph; a full reset clears both.

See [decoder design](decoder-design.md) for the exact register bitfields,
framing bytes, and recovery rules, and
[core performance](core-performance.md) for the scan-pipeline optimization
study.

## Build and test entry points

The root [Makefile](../Makefile) drives the maintained runtime-UF flow:

- `make build` runs [build.tcl](../fpga/scripts/build.tcl),
  [bd/soc.tcl](../fpga/scripts/bd/soc.tcl), and
  [top_qec_soc.xdc](../fpga/constraints/top_qec_soc.xdc) in Vivado.
- `make firmware` runs [build.py](../fpga/vitis/build.py) in Vitis against the
  exported `.xsa`.
- `make load` runs [load.tcl](../fpga/scripts/load.tcl) in XSCT to load the
  bitstream and ELF over JTAG; `make status` runs
  [status.tcl](../fpga/scripts/status.tcl) to inspect FPGA configuration flags.
- `make test` runs Python unit tests, documentation/link checks, and Node UI
  tests.
- `make sim` calls [scripts/simulate.py](../scripts/simulate.py) to run the
  core, bridge, and long-counter SystemVerilog testbenches in isolated folders
  under `build/sim/`.
- [verify_timing.py](../scripts/verify_timing.py) checks routed setup/hold
  slack, and [inspect_timing.tcl](../fpga/scripts/inspect_timing.tcl) dumps
  detailed critical paths.

Historical capture archives under `qec/results/` and `qec/surface/results/`
keep their original filenames and manifests untouched as evidence. All new
builds, simulations, and run outputs belong under `build/`. See
[verification](verification.md) for a summary of what has been tested in
simulation, routing, and on the physical board.
