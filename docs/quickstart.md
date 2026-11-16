# Quick start

A standalone QEC decoder project for the **Digilent Zybo Z7-10**
(`xc7z010clg400-1`), with Stim-generated inputs, FPGA decoding, and host-side
verification. This repository uses **`main`**.

## Prerequisites

### Python

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
these commands from the repository root:

```sh
uv venv --python 3.12 qec/.venv
uv pip install --python qec/.venv/bin/python -r qec/requirements.txt
source qec/.venv/bin/activate
mkdir -p build
```

### AMD toolchain and board

For FPGA decoding and optional RTL simulation, install Vivado/Vitis 2025.2 with
Zynq-7000 support using the [AMD installation guide](https://docs.amd.com/r/2025.2-English/ug1742-vitis-release-notes/Installing-the-Vitis-Software-Platform).
Add their bin directories to PATH, adjusting the installation paths below:

```sh
export PATH="$HOME/amd/2025.2/Vivado/bin:$HOME/amd/2025.2/Vitis/bin:$PATH"
```

Install the [Digilent board files](https://digilent.com/reference/programmable-logic/guides/install-board-files)
and AMD cable drivers for the Zybo Z7-10. The build uses board part
`digilentinc.com:zybo-z7-10:part0:1.2`. Set `QEC_BOARD_REPO` to the `board_files`
directory if it is outside Vivado's board search paths.

Connect the powered board through its PROG/UART USB port and grant your account
serial-device access. For software-only use, the Python setup is sufficient.

## Quick start: configure, run and replay in the web interface

The decoder accepts detector-annotated Clifford circuits with different
physical-qubit counts, gates, checks and logical observables. The web editor takes
Stim text; the host compiles its decoding graph and uploads that graph to the
FPGA. Changing a compatible circuit does not require rebuilding the bitstream.

The current Z7-10 image has capacity for **128 detectors, 512 graph edges and
32 observable bits**, at 100 MHz. Physical-qubit count is independent of detector
count; the host parser separately bounds it for resource safety. The decoder is
unweighted union-find/peeling. Non-graphlike fault components, ambiguous observable
labels and detectorless logical faults are rejected rather than silently dropped.

The graph-loadable image has passed RTL regressions, routed timing, an ARM firmware
build and physical FPGA checks across six different circuit graphs without
reprogramming between graphs. See [verification evidence](verification.md).
The verification record separates the archived image from checks of the
reorganized sources and unified interface.

### 1. Build the bitstream and firmware

```sh
make build IMAGE_DIR=build/image
make firmware IMAGE_DIR=build/image
```

The Makefile builds the current graph-loadable design under `fpga/`, then builds
ARM firmware against the exported XSA. With the directory above, outputs are:

- `build/image/qec_soc.bit`
- `build/image/qec_soc.xsa`
- `build/image/vitis_ws/qec_app/build/qec_app.elf`

`IMAGE_DIR` defaults to the repository's `build/image`. Choose a fresh directory
for each build, and pass the same value to build, firmware and load. Tool working
directories stay under `build/tools/`; command logs stay under `build/logs/`.
Review routed timing, utilization and DRC reports
before loading an image. Skip steps 1–2 for software-only use.

### 2. Load the board

Close serial monitors and serial-backed web servers, then find the UART port:

```sh
python -m serial.tools.list_ports -v
PORT=/dev/ttyUSB1          # use the discovered UART port
make load IMAGE_DIR=build/image
```

`make load` loads the matching bitstream, ELF and XSA over JTAG. It programs
volatile PL state and restarts ARM core 0; it does not write boot flash.
Check the load log for successful programming and ARM startup. The four user
LEDs show mailbox ACK, decode-complete, operation error and returned-data bit 0;
none is a logical-success light. See the [LED map](decoder-design.md#board-leds).

### 3. Open the web interface

```sh
python -m qec.surface.web --port 8765 --serial-port "$PORT"
```

Open **http://127.0.0.1:8765/**. The source label is **FPGA**. For software-only
use, omit `--serial-port "$PORT"`; the label is **Software**, and Python runs the
same unweighted graph algorithm. FPGA errors never fall back to software.

The server binds only to loopback. Opening the page does not query, program or
reset the board. No frontend build is needed. Stop it with Ctrl+C before using
the UART with another client.

### 4. Define the circuit, noise and seed

Use the memory preset, or open **Circuit** and edit **Annotated Stim circuit**
for an annotated physical experiment. It accepts supported Clifford compositions, preparation,
measurements, noise instructions, `TICK`, `DETECTOR` and `OBSERVABLE_INCLUDE`.
Qubit indices, gate order, checks and observable definitions come from your text.
The [phase-Bell circuit](../qec/examples/phase_bell.stim) uses two
qubits and two observable bits. The [two-repetition echo](../qec/examples/two_repetition_echo.stim)
uses six qubits and two observable bits; paste it into the same editor to change
the experiment. These are editable examples, not a template whitelist.

Set **Seed** and **Added gate depolarization** (0–0.75). Existing noise in the
editor is retained. Added noise follows each one/two-qubit unitary group; other
unitary Pauli-product operations receive single-qubit depolarization on their
support. It does not add measurement or reset noise; specify those in the circuit.
A rate of 0 disables only the added noise, not noise already present in the text.

For a zero-noise experiment with an empty decoding graph, use **Reference Stim
(optional)** to supply the same annotated experiment with noise.
The compiler checks compatibility and never invents reference noise.

Checks and observables must be deterministic without noise. Bare Clifford gates
do not define a QEC experiment: supply its encoding, checks and readout. This
frontend accepts annotated physical circuits; it does not automatically synthesize
an arbitrary logical program into a fault-tolerant implementation. Measurement
feedback and sweep-controlled operations are currently rejected.

For the memory preset, the logical view shows one encoded memory wire. For a
custom circuit, expand **Circuit editor** and optionally supply **Logical
Clifford circuit**. The right-hand diagram then shows those logical operations;
without it, the diagram shows the submitted physical operations. A supplied
logical circuit is display metadata, not a verified encoding map.

The physical view includes every used qubit. It uses `QUBIT_COORDS` when complete
2D coordinates are available, or a labeled index grid otherwise.

Editing settings does not run simulation or contact the board.

### 5. Simulate and decode

Click **Run**. The server compiles the submitted experiment
and samples one seeded Stim shot. In FPGA mode it reads the image's capacities,
uploads the circuit's exact ordered graph and decodes that shot's detector bits.
The FPGA returns an observable-flip mask and measured core cycles. Observable
truth stays on the host and is used to evaluate the returned prediction.

A graph-load or decoding error produces an error, not a software replacement or
an old result. The graph upload happens on Run, not on circuit edits or replay.

### 6. Replay the completed run

Click **Replay**, **Pause**, or **Step**, or scrub the circuit tick. Playback
speed affects only visualization. Replay uses the completed response and sends
no simulation, graph-upload or decoder requests. Editing invalidates the result
until the next explicit Run.

Detector events and sampled Pauli frames are derived from the same simulation.
The final tick shows prediction versus true observable mask; bit i means flip
the interpretation of logical observable i. The animation is not physical quantum
feedback, and the FPGA does not return physical correction gates.

![Web interface after a physical FPGA run](images/web-fpga-layout.png)

Captured from the unified interface using the FPGA: seed 20261107, prediction 0,
observable 0 and 761 core cycles. The physical layout and logical-memory diagram
are visible together.

## Alternative: command-line workflow

Run an annotated circuit in software:

```sh
python -m qec.surface.run qec/examples/two_repetition_echo.stim --shots 128 --seed 123 --out build/my-software-run
```

```json
{
  "source": "Software",
  "shots": 128,
  "seed": 123,
  "qubits": 6,
  "detectors": 4,
  "observables": 2,
  "edges": 6,
  "measurements": 6,
  "ticks": 2,
  "logical_failures": 0,
  "reference_mismatches": 0,
  "graph_sha256": "26e79c182c4e5ff4999bee26f612919da88ffadd7f06ccd4f5e084529cffbbe6"
}
```

- `source`: actual decoder path, Software or FPGA.
- `shots`, `seed`: sampled batch size and random seed.
- `qubits`, `detectors`, `observables`, `edges`: physical index count and compiled
  decoding dimensions; qubits include gaps up to the highest index.
- `measurements`, `ticks`: measurement results and TICK separators, not measured
  hardware time or extraction rounds.
- `logical_failures`: predictions differing from actual Stim observable truth.
- `reference_mismatches`: returned predictions differing from the Python UF
  reference, or reference decode errors. This is separate from logical accuracy.
- `graph_sha256`: host artifact identity, not FPGA-attested cryptographic identity.

To use the loaded FPGA instead, close the web server and add the UART:

```sh
python -m qec.surface.run qec/examples/two_repetition_echo.stim --shots 128 --seed 123 --port "$PORT" --out build/my-fpga-run
```

The CLI uploads the graph once, decodes the sampled batch and archives actual
predictions, truth, core cycles and serial evidence. `--out` must be new.
`--reference FILE` supplies an explicit compatible noisy reference. See the
[CLI walkthrough](code-walkthrough.md#follow-one-cli-run) for archive fields and failure
behavior. Equal seeds do not imply equal shots across the CLI batch sampler and
the web's single-shot FlipSimulator call sequence.


## Optional RTL check

```sh
make sim
```

With Vivado's simulator available, this checks core predictions, the mailbox
bridge, cycle counts and recovery. It is not required before running a board
example and does not establish physical-board operation.
