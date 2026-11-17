# Code walkthrough

Read [run.py](../qec/surface/run.py), [circuit.py](../qec/surface/circuit.py),
[decoder.py](../qec/surface/decoder.py), [host.py](../qec/surface/host.py),
[main.c](../fpga/vitis/src/main.c), then
[top_qec_soc.sv](../fpga/rtl/top/top_qec_soc.sv). This follows one experiment
from annotated circuit to observable prediction. For setup, use the
[quick start](quickstart.md).

## Directory map

```text
qec/surface/               Compiler, decoder reference, host, CLI and web interface
  web_assets/              Paper-style circuit/lattice, physical grid and replay UI
  results/                 Historical hardware captures and source snapshots
qec/examples/              Editable annotated Stim circuits
qec/tests/                 Python, native-firmware and browser checks
fpga/rtl/                  Decoder, mailbox bridge, board top and testbenches
fpga/constraints/          Clock and board constraints
fpga/scripts/              Vivado/XSCT Tcl; bd/ creates the PS7/AXI GPIO design
fpga/vitis/                ARM firmware, platform adapter and firmware builder
scripts/                   Simulation runner, timing check and documentation tests
docs/                      Quick start, design, verification and source navigation
build/                     Generated images, logs, tool workspaces and test output
```

## Follow one CLI run

[run.py](../qec/surface/run.py) reads the input text and calls `compile_circuit()`
in [circuit.py](../qec/surface/circuit.py). Compilation bounds input expansion,
requires deterministic noiseless checks and observables, and extracts an ordered
graph. [graph.py](../qec/surface/graph.py) validates its edge representation.
An empty graph needs an explicit compatible noisy reference.

Stim samples detector bits and observable truth. Detector i occupies syndrome
bit i. Without a serial port, [decoder.py](../qec/surface/decoder.py) decodes in
Python. With a port, [host.py](../qec/surface/host.py) reads capacities, uploads
the graph and submits detector vectors. For larger disconnected graphs,
[partition.py](../qec/surface/partition.py) packs whole components into hardware
windows without cutting edges, then XORs their returned masks. Observable truth
stays on the host.
The runner checks logical accuracy against Stim and implementation agreement
against Python separately.

Each run writes compiled input, per-shot results, a summary and a version/hash
manifest to a new output directory. FPGA runs also archive wire traffic. Failed
runs retain partial evidence and an error record; they do not replace failed
FPGA replies with Python results.

## Follow one web run

[web.py](../qec/surface/web.py) is the only HTTP/CLI entry point.
[engine.py](../qec/surface/engine.py) coordinates the preferred editor.
[model.py](../qec/surface/model.py) describes known surface-memory experiments;
[simulation.py](../qec/surface/simulation.py) handles bounded circuit compilation
and generic single-shot simulation. It is not another server.

The browser assets in [web_assets/](../qec/surface/web_assets/) display the circuit
and all used physical qubits. A known memory preset has logical-memory semantics;
general annotated physical input needs an explicit logical description/mapping
before a logical interpretation can be claimed. Supplied logical text is labeled
as supplied, not certified as an encoding. The fixed Bell/echo generator in
[encoded.py](../qec/surface/encoded.py) supplies tested logical/physical pairs;
the UI recognizes those pairs but does not certify arbitrary edited mappings.
See the [example assumptions](../qec/examples/README.md) before changing noise
or gate semantics.

Opening the page and editing settings must not access hardware. Explicit Run
simulates and decodes; Replay, stepping and scrubbing use the completed trace.
A circuit TICK, an extraction round, playback speed and measured FPGA cycles
are different quantities.

## ARM transport and PL decode

[main.c](../fpga/vitis/src/main.c) parses UART frames and dispatches mailbox
commands. [platform.h](../fpga/vitis/src/platform.h) adapts UART, GPIO and deadlines.
The PS ARM is outside PL. AXI GPIO connects it to
[ps_bridge.sv](../fpga/rtl/common/ps_bridge.sv), which stages graph words, submits
syndromes and reads results from [qec_decoder.sv](../fpga/rtl/common/qec_decoder.sv).

The core stores ordered endpoints and observable masks. It initializes cluster
labels/parity, grows half-edges, merges clusters and peels a forest. Registered
read/select/update states process edges serially. Selected masks XOR into the
observable prediction. A cycle counter measures acceptance to first result;
result-hold stalls do not add cycles. Shot abort preserves the graph; full reset
invalidates it. See [decoder design](decoder-design.md) for framing and recovery.

The [core performance study](core-performance.md) records the measured scan
optimization, independent RTL cycle checks and fresh Zybo timing/resource costs.
Its new-core results are simulated/routed, not new board measurements.

## Build and check entry points

The root [Makefile](../Makefile) selects the current design only. `make build`
uses [build.tcl](../fpga/scripts/build.tcl),
[bd/soc.tcl](../fpga/scripts/bd/soc.tcl) and
[top_qec_soc.xdc](../fpga/constraints/top_qec_soc.xdc). `make firmware` uses
[build.py](../fpga/vitis/build.py) against that image's XSA. `make load` calls
[load.tcl](../fpga/scripts/load.tcl); `make status` reads configuration status,
which alone does not establish decoder correctness.

`make test` runs the software regressions and central documentation-link checks.
[scripts/simulate.py](../scripts/simulate.py) runs the core, bridge and counter
benches in isolated build directories. [verify_timing.py](../scripts/verify_timing.py)
checks routed timing; [inspect_timing.tcl](../fpga/scripts/inspect_timing.tcl)
inspects detailed paths. Native parser/PTY tests do not prove physical board
operation, and RTL simulation does not prove routed timing.

Historical captures under `qec/results/` and `qec/surface/results/` keep their
original filenames, source snapshots and manifests. They are evidence, not
alternate maintained entry points. New output belongs under `build/`. See
[verification](verification.md) for the accepted image and the boundary between
archived results and pending refactor checks.
