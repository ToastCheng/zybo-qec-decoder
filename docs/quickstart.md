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

Open **http://127.0.0.1:8765/**. After a completed run, open **Details** to check
that the decoder source is **FPGA**. For software-only use, omit
`--serial-port "$PORT"`; the completed run reports **Software**, and Python runs
the same unweighted graph algorithm. FPGA errors never fall back to software.

The server binds only to loopback. Opening the page does not query, program or
reset the board. No frontend build is needed. Stop it with Ctrl+C before using
the UART with another client.

For a public Cloudflare Tunnel at `https://qec.toastcheng.com`, launch with:

```sh
python -m qec.surface.web --port 8765 --serial-port "$PORT" --public-origin https://qec.toastcheng.com
```

Point the tunnel at `http://localhost:8765` and preserve the incoming Host header.
The option permits only that exact HTTPS origin in addition to localhost; other
hosts and cross-origin requests remain rejected. The server still binds to
loopback. Without this option it accepts only local access. This is not
authentication: public visitors can run simulations and submit experiments to the
connected FPGA. Only one experiment runs at a time.

### 4. Define the circuit, noise and seed

Choose **Surface memory**, **Encoded Bell**, or **Encoded echo** from the circuit
list. Open **Advanced** to edit the annotated Stim circuit. Seed and noise controls
are in **Configure**, collapsed by default. Editing the text changes the selection to Custom and
invalidates the completed result without running anything.

The [Bell example](../qec/examples/phase_bell.stim) uses two distance-3 patches
(34 physical qubits). The [echo example](../qec/examples/two_repetition_echo.stim)
uses six patches (102 physical qubits). Each patch has nine data qubits and eight
measurement ancillas, with three check rounds per protected segment. Their
logical-to-physical descriptions come from the tested generator, not a separate
user-supplied diagram.

**Agent-selected adaptations:** Bell now measures ordinary XX/ZZ correlations,
not the former phase-Bell YX/ZZ correlations; no encoded S gadget is claimed.
The echo omits its canceling S/S_DAG pair and checks all six logical outputs.
Interpatch CX is transversal and assumes nonlocal pairwise couplers, not lattice
surgery. These are fixed encoded experiments, not an arbitrary logical compiler.

The runnable examples use explicitly restricted independent X/Z storage noise
and measurement-result flips. Gates/resets and the last check results before
logical gates are perfect. Full circuit-level gate noise remains unsupported;
its correlations are rejected, not discarded. See the [exact noise model and
validation](../qec/examples/README.md).

Keep **Added gate depolarization** at 0 for the encoded presets: adding gate
faults can produce unsupported correlations. For compatible custom circuits the
accepted rate is 0–0.75. Existing noise in the text is retained. Added noise
follows each one/two-qubit unitary group; other
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

For custom input, **Advanced** contains an optional logical diagram and an
explicit noisy reference. A supplied logical circuit is display metadata unless
both inputs match a tested encoded example.

The physical view includes every used qubit. It uses `QUBIT_COORDS` when complete
2D coordinates are available, or a labeled index grid otherwise.

The injection controls are directly below that layout. Select X/Y/Z and a fault
tick, then click a physical qubit; injected faults appear as individual list
items. Run again to include the edited list. Faults enter before the selected
tick's operations, so a later reset can erase an injection.

Editing settings does not run simulation or contact the board.

### 5. Simulate and decode

Click **Simulate and decode** in the fixed bottom bar. The server compiles the submitted experiment
and samples one seeded Stim shot. In FPGA mode it reads the image's capacities,
uploads the circuit's exact ordered graph and decodes that shot's detector bits.
The FPGA returns an observable-flip mask and measured core cycles. Observable
truth stays on the host and is used to evaluate the returned prediction.

A graph-load or decoding error produces an error, not a software replacement or
an old result. The graph upload happens on Run, not on circuit edits or replay.

### 6. Replay the completed run

Use the bottom bar's play/pause and step buttons, or scrub the circuit tick. Playback
speed affects only visualization. Replay uses the completed response and sends
no simulation, graph-upload or decoder requests. Editing invalidates the result
until the next explicit Run.

Detector events and sampled Pauli frames are derived from the same simulation.
For the default three-round memory, detector columns `r0`, `r1` and `r2` refer
to the three ancilla-check readouts at ticks 7, 14 and 21. `r3` is the final data
readout, also at tick 21: no `TICK` separates it from the last ancilla readout.
The 22 physical tick positions (0–21) describe gate layers, not 22 check rounds.
Replay position 22 is the host correction overlay, not another physical tick.

The final tick shows prediction versus true observable mask; bit i means flip
the interpretation of logical observable i. The animation is not physical quantum
feedback, and the FPGA does not return physical correction gates.

![Web interface after a physical FPGA run](images/web-fpga-layout.png)

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
  "qubits": 102,
  "detectors": 720,
  "observables": 6,
  "edges": 1716,
  "measurements": 774,
  "ticks": 114,
  "logical_failures": 0,
  "reference_mismatches": 0,
  "graph_sha256": "c92e45bee04d38a8561a3aded7f6cb1206aabeec70f3bd00b93ac243aabd49e6"
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

The CLI uploads each hardware-sized graph window and archives actual predictions,
truth, core cycles and serial evidence. This echo uses six windows of disconnected
detector components; they are uploaded and decoded sequentially for each shot,
and their observable masks are XORed. Total cycles sum only the six measured
core decodes, excluding graph uploads and UART. Graph edges are never cut to fit.
`--out` must be new.
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
