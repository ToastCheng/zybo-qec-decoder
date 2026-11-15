# Zybo QEC Decoder

A standalone QEC decoder project for the **Digilent Zybo Z7-10**
(`xc7z010clg400-1`), with Stim-generated inputs, FPGA decoding, and host-side
verification. This repository uses **`main`**.

## Source walkthroughs

Every maintained source file has a Markdown walkthrough beside it, using the same
basename: for example, [`qec_decoder.sv`](rtl/common/qec_decoder.sv) and
[`qec_decoder.md`](rtl/common/qec_decoder.md). Each walkthrough explains the
file's interfaces, control flow, invariants and verification commands.

Start with the [surface decoder](rtl/common/surface_decoder.md),
[PS/PL mailbox](rtl/common/surface_ps_bridge.md),
[ARM firmware](vitis/surface/src/main.md), or
[host transport](qec/surface/host.md). Build entry points are covered in the
[Makefile guide](Makefile.md) and [SoC build guide](scripts/build_soc.md).

Source uses four-space indentation (Make recipes retain required tabs), expanded
control flow and comments for protocol, state-machine and timing assumptions.
Keep a source's sibling walkthrough current when changing it. `make test` checks
that every maintained source has one; archived results and fixture snapshots are
excluded.

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

For RTL simulation and the board example, install Vivado/Vitis 2025.2 with
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
serial-device access.

## Quick start: manually decode a complete window

Run all commands from the repository root. The example uses a distance-3
surface code with three rounds of Z memory.

## 1. Workflow

```mermaid
flowchart TD
    C[Host: noisy Stim circuit] --> S[Stim samples one shot]
    S --> D[24 detector bits]
    S --> O[True logical observable: host only]
    D --> P[Pack request bytes]
    P --> U[USB UART]
    U --> A[ARM firmware / PS]
    A --> G[AXI GPIO]
    G --> F[FPGA / PL: union-find and peeling]
    F --> R[Reply: predicted logical flip + cycles]
    R --> B[AXI GPIO → ARM → USB UART → host]
    B --> E[Compare prediction with true observable]
    O --> E
    D --> M[Host: PyMatching baseline]
    M --> E
```

The circuit is simulated on the PC, its detector bits go to the FPGA board.
Stim is used as a circuit simulator, **PyMatching** decodes the same detector
bits separately. The FPGA runs an unweighted union-find/peeling algorithm, so
it can disagree with PyMatching. For implementation correctness we compare the
FPGA with the Python version of its own algorithm.

A detector bit records a measurement-parity change relative to the circuit's
expected behavior. A complete set for one shot is the decoder input.

Stim supplies both the detector input and the true logical flip for evaluation.
**The true flip is not sent to the FPGA.** A prediction of 1 means invert the
logical measurement interpretation. The sample does not connect to a quantum
processor, execute physical corrections, or run continuous feedback. It processes
completed simulated shots.

## 2. Run the software example

The [example](qec/surface/example.py) samples a noisy surface-code shot, decodes its detector bits with Python union-find and PyMatching, and prints both predictions alongside the simulated logical observable.

```sh
python -m qec.surface.example --seed 20261107 --shots 256
```

```json
{
  "shot": 11,
  "detector_indices": [
    11
  ],
  "syndrome": 2048,
  "observable": 0,
  "prediction": 0,
  "pymatching": 0,
  "correction_edges": [
    47
  ],
  "residual": 0,
  "logical_error": false,
  "tx_hex": "c3 00 03 00 08 00 c8"
}
```

- `shot`: zero-based index of the selected shot.
- `detector_indices`: indices of the detectors that fired.
- `syndrome`: detector bits packed into an integer; bit i stores detector i.
- `observable`: simulated logical flip, where 0 means no flip and 1 means a flip.
- `prediction`: logical-flip prediction from the Python union-find decoder.
- `pymatching`: logical-flip prediction from PyMatching.
- `correction_edges`: graph-edge indices selected by the Python decoder.
- `residual`: detector parity remaining after the correction; 0 means all events cancel.
- `logical_error`: whether `prediction` differs from `observable`.
- `tx_hex`: request bytes in hexadecimal.

`--seed` makes sampling reproducible; omit it for fresh randomness. `--shots`
sets the sampled batch size (default: 256); each run decodes one shot from that
batch. `--noise` sets the error probability at each gate, reset and measurement
noise location (default: 0.001, range: 0–0.75); use 0 to disable noise. Add
`--circuit` to print the full Stim circuit and its noise instructions.

## 3. Simulate the FPGA decoder

```sh
python qec/surface/sim.py --distance 3 --basis z --shots 256
```

This optional step compares RTL predictions with the Python reference and checks
cycle counting, backpressure and reset recovery in Vivado Simulator.
Adjust `--distance` (odd values of 3 or greater), `--basis` (`x` or `z`) and
`--shots` to change the code distance, memory basis and number of sampled shots.
The board example below uses distance 3 and Z memory.

## 4. Build the bitstream and firmware

```sh
vivado -mode batch -source scripts/build_soc.tcl -tclargs top_surface_soc > build/surface_build.log 2>&1
vitis -s vitis/surface/build_app.py > build/surface_firmware_build.log 2>&1
```

Vivado builds the PS7/AXI GPIO design and PL decoder. Vitis builds the ARM UART
transport firmware. Check that both commands succeed and produce:

```text
build/surface_soc.bit
build/surface_soc.xsa
build/vitis_ws/surface_app/build/surface_app.elf
```

Review the build logs and `build/top_surface_soc_timing_summary.rpt` before
loading the board.

## 5. Load the board

Close any serial monitor before loading the board.

Find the UART port:

```sh
python -m serial.tools.list_ports -v
PORT=/dev/ttyUSB1          # use the discovered UART port
```

The following command programs the FPGA and restarts ARM core 0. It loads volatile
state over JTAG; power loss requires reloading.

```sh
xsct scripts/run_soc.tcl build/surface_soc.bit build/vitis_ws/surface_app/build/surface_app.elf build/surface_soc.xsa > build/surface_program.log 2>&1
```

Check `build/surface_program.log` for successful FPGA programming and ARM startup.

## 6. Run the board example

```sh
python -m qec.surface.example --seed 20261107 --shots 256 --port "$PORT"
```

```json
{
  "shot": 11,
  "detector_indices": [
    11
  ],
  "syndrome": 2048,
  "observable": 0,
  "prediction": 0,
  "pymatching": 0,
  "correction_edges": [
    47
  ],
  "residual": 0,
  "logical_error": false,
  "tx_hex": "c3 00 03 00 08 00 c8",
  "rx_hex": "3c 00 00 00 a9 03 00 00 96",
  "board_prediction": 0,
  "pl_cycles": 937
}
```

The board run adds:

- `rx_hex`: reply bytes received from the board, in hexadecimal.
- `board_prediction`: logical-flip prediction returned by the FPGA.
- `pl_cycles`: decoder clock cycles measured on the FPGA at 100 MHz.

The example regenerates the shot from section 2 and sends its detector bits to
the loaded surface decoder. It prints the reply, checks the prediction against
the Python reference and checks that the cycle count is positive.

## 7. Visualize the circuit and decoding result

With the d3 Z / 3-round surface decoder still loaded from steps 5–6, start the
local web server using the same UART port:

```sh
python -m qec.surface.web --port 8765 --serial-port "$PORT"
```

Open **http://127.0.0.1:8765/**. Select a fault tick and X, Y, or Z, then click
data qubits, or use the example fault. The Python server simulates the selected
faults with Stim, sends the resulting detector bits to the FPGA and returns a
trace for the browser to replay. It generates a new shot for those faults;
it does not import the output from step 6.

Scrub circuit ticks, step backward or forward, or play at an adjustable speed.
Detector flips appear at their measurement boundaries; the final step shows the
**Host correction** overlay. Open **Details** to inspect the Stim circuits,
FPGA prediction, measured cycles and request/reply bytes.

The FPGA returns a logical-flip prediction and measured cycles. The Python server
computes the graph edges and Pauli overlay and independently simulates a circuit
with that correction for comparison. The animation does not execute physical
corrections or provide live quantum feedback; a cleared syndrome alone does not
establish logical recovery.

For software-only visualization after step 2, omit `--serial-port "$PORT"` and
skip the board build/load/run steps. The server then runs Stim and the Python
union-find decoder, and the page labels the source **Simulated** rather than
**FPGA**. Serial or protocol failures in FPGA mode appear as errors without
software fallback.

The server binds only to loopback and does not program or reset the board. No
frontend build is needed. Stop it with Ctrl+C before using the UART elsewhere.

## Restricted logical compiler

The separate [compiler CLI](qec/surface/compile.py) supports only one-qubit
memory, a single temporal H, or a single lattice-surgery CX, in X/Z basis at
code distance 3 or 5. It explicitly rejects S, T, adaptive controls and all
unvalidated compositions; this is **not arbitrary Clifford compilation**.

Install its pinned optional dependency in a separate Python 3.12 environment:

```sh
uv venv --python 3.12 build/compiler-env
uv pip install --python build/compiler-env/bin/python -r qec/requirements-compiler.txt
source build/compiler-env/bin/activate
python -m qec.surface.compile qec/examples/logical_h.json --basis z --distance 3 --noise 0.001 --shots 256 --seed 123 --out build/logical-h
```

This verified H run produced 56 detectors, 208 edges and one observable;
UF/MWPM logical failures were 3/0 on the same 256 sampled shots, with zero
residual syndromes. The new output directory contains annotated Stim circuits,
DEMs, a loss-checked graph, per-shot evidence, a hash/version manifest and a
single-observable core ROM. CX preserves both observable bits in software/JSON
and emits no one-bit ROM. See the [input and artifact contract](qec/examples/README.md)
for all three example inputs, zero-noise reference handling and reproduction.

The compiler rejects `--port` before opening serial: H requires a matching
bitstream and firmware; CX also needs wider RTL/protocol support. It does not
program or reset the board. The existing `qec.surface.example` remains unchanged.
