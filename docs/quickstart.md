# Quick start

This guide walks through setting up the tools, building the FPGA image for a
**Digilent Zybo Z7-10** (`xc7z010clg400-1`), loading the board, and running
decoding experiments from the web interface or command line.

## Prerequisites

### Python

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then
create the project environment from the repository root:

```sh
uv venv --python 3.12 qec/.venv
uv pip install --python qec/.venv/bin/python -r qec/requirements.txt
source qec/.venv/bin/activate
```

### AMD toolchain and board

You only need Vivado and Vitis if you are building or loading the FPGA image.
Software-only mode works with Python alone.

1. Install Vivado and Vitis with Zynq-7000 support using the
   [AMD installation guide](https://docs.amd.com/r/2025.2-English/ug1742-vitis-release-notes/Installing-the-Vitis-Software-Platform)
   (the examples here were built with version 2025.2). Add both `bin/` folders
   to `PATH`, replacing `/path/to` with your install directory:

   ```sh
   export PATH="/path/to/Vivado/bin:/path/to/Vitis/bin:$PATH"
   ```

2. Install the
   [Digilent board files](https://digilent.com/reference/programmable-logic/guides/install-board-files)
   and AMD cable drivers for the Zybo Z7-10 (`digilentinc.com:zybo-z7-10:part0:1.2`).
   If your `board_files` folder is outside Vivado's default search path, point
   `QEC_BOARD_REPO` to it.
3. Power the Zybo board, connect a USB cable to the **PROG/UART** port, and
   make sure your user account has permission to open the serial device (for
   example, membership in the `dialout` group on Linux).

## Build and run with the web interface

### 1. Build the bitstream and ARM firmware

```sh
make build IMAGE_DIR=build/image
make firmware IMAGE_DIR=build/image
```

`make build` synthesizes and routes the runtime-loadable decoder under `fpga/`
and exports the hardware description (`.xsa`). `make firmware` compiles the
ARM UART-to-mailbox firmware against that `.xsa`. Together they produce:

- `build/image/qec_soc.bit` (FPGA bitstream)
- `build/image/qec_soc.xsa` (Vivado hardware export)
- `build/image/vitis_ws/qec_app/build/qec_app.elf` (ARM firmware)

### 2. Load the board

Close any serial monitor or running web server that might hold the UART port,
find the board's serial device, and load the image over JTAG:

```sh
python -m serial.tools.list_ports -v
PORT=/dev/ttyUSB1          # replace with the UART port from the list above
make load IMAGE_DIR=build/image
```

`make load` writes the bitstream into volatile FPGA memory and starts the ARM
firmware on core 0; it never touches onboard boot flash. The four user LEDs
display low-level mailbox status (`ACK` phase, decode `DONE`, operation
`ERROR`, and `READ_DATA` bit 0) rather than logical pass/fail; see the
[LED map](decoder-design.md#board-leds) for details.

### 3. Start the web interface

```sh
python -m qec.surface.web --port 8765 --serial-port "$PORT"
```

Open **http://127.0.0.1:8765/** in a browser. To run without a board, omit
`--serial-port "$PORT"` and the server will decode on the host with the Python
union-find reference decoder (`qec.surface.decoder`) instead.

The server listens on loopback only, needs no frontend build step, and does
not query or reset the board until you run an experiment. Press `Ctrl+C` to
stop it before using the serial port from another tool.

### 4. Choose a circuit and inject optional faults

Pick **Surface memory**, **Encoded Bell**, or **Encoded echo** from the
circuit dropdown. Open **Configure** to change noise probabilities or the
random seed, or open **Advanced** to edit the Stim circuit directly.

Every physical qubit in the circuit is shown in the lattice/grid view. To
inject a deterministic error, select a Pauli type (`X`, `Y`, or `Z`) and a
tick in the injection controls below the qubits, then click any physical qubit.

### 5. Simulate and decode

Click **Simulate and decode** in the bottom bar. The server compiles the
circuit's decoding graph and samples one shot with Stim. In FPGA mode, it
checks the board's capacities, uploads the ordered decoding graph over UART,
and sends the shot's detector bits. The FPGA returns a predicted observable
flip mask and its core cycle count; the host compares that prediction against
Stim's true observable flips. Open **Details** afterward to confirm the
decoder source shows **FPGA**.

### 6. Replay the shot

Use Play/Pause, Step, or the timeline scrubber in the bottom bar to inspect
gates, Pauli errors, and detector triggers tick by tick. Replay stays local in
the browser without re-running simulation or contacting the board. On the
final step, bit `i` of the prediction mask indicates whether logical
observable `i` is predicted to have flipped.

![Web interface after a physical FPGA run](images/web-fpga-layout.png)

## Alternative: command-line workflow

To run a batch of shots from the terminal in software mode:

```sh
python -m qec.surface.run qec/examples/two_repetition_echo.stim --shots 128 --seed 123 --out build/my-software-run
```

Example summary output:

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

What each field means:

- `source`: which decoder ran (`Software` or `FPGA`).
- `shots`, `seed`: number of Stim shots sampled and the RNG seed.
- `qubits`, `detectors`, `observables`, `edges`: physical qubit index count
  (including any unused index gaps) and compiled decoding-graph dimensions.
- `measurements`, `ticks`: number of Stim measurement operations and `TICK`
  barriers in the circuit.
- `logical_failures`: shots where the decoded observable mask differed from
  Stim's true observable flips.
- `reference_mismatches`: shots where the returned prediction disagreed with
  the Python union-find reference decoder (or the reference hit an error).
- `graph_sha256`: SHA-256 hash of the compiled graph computed on the host for
  tracking artifacts.

To run the same batch on the loaded FPGA, stop the web server and pass
`--port`:

```sh
python -m qec.surface.run qec/examples/two_repetition_echo.stim --shots 128 --seed 123 --port "$PORT" --out build/my-fpga-run
```

Because `two_repetition_echo.stim` has 720 detectors across six disconnected
components, the host packs each component into its own hardware-sized window
without cutting edges, uploads and decodes the six windows in order, and XORs
their returned observable masks. Reported total cycles sum only the six FPGA
core decodes (excluding graph uploads and UART time).

Useful flags and notes:

- `--out` must point to a directory that does not exist yet.
- `--reference FILE` supplies a noisy reference circuit when your main input
  has zero noise and therefore produces an empty decoding graph.
- The CLI batch sampler and the web UI's single-shot `FlipSimulator` call Stim
  differently, so the same seed can produce different shots across the two
  tools.
- See the [CLI walkthrough](code-walkthrough.md#follow-one-cli-run) for the
  files written to `--out`.

## Optional RTL simulation

```sh
make sim
```

If Vivado's `xsim` simulator is on `PATH`, this runs the core, mailbox bridge,
and long-cycle-counter SystemVerilog testbenches to verify predictions, cycle
counts, backpressure, and reset recovery before touching hardware.
