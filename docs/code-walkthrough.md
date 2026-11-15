# Code walkthrough

Start with the runtime decoder. It is the path used by the circuit editor in the
[quick start](../README.md). Python compiles and samples the experiment, ARM
firmware transports requests, and the FPGA decodes the detector bits.

For a first pass, read these files in order:

1. [runtime_run.py](../qec/surface/runtime_run.py): the shortest end-to-end Python path.
2. [runtime_circuit.py](../qec/surface/runtime_circuit.py): circuit validation and graph construction.
3. [decoder.py](../qec/surface/decoder.py): the decoding algorithm in Python.
4. [runtime_host.py](../qec/surface/runtime_host.py): graph upload and serial requests.
5. [main.c](../vitis/runtime/src/main.c): ARM request handling and mailbox access.
6. [top_runtime_soc.sv](../rtl/top/top_runtime_soc.sv): the hardware connections, then its bridge and core.

You can leave the fixed-image and logical-template code until you need to
reproduce those experiments. Their entry points are listed under [older paths](#older-paths).

## Directory map

```text
qec/                       Python models, host tools and tests
  surface/                 Union-find decoder and circuit workflows
    runtime_*.py           Current compiler, CLI, web server and serial client
    runtime_web_assets/    Runtime editor and replay UI; no frontend build
    decoder.py             Python decoding reference; also fixed-graph generation
    graphs/                Committed fixed surface-code graphs and ROM files
    web.py, web_assets/    Older fixed-memory web lab
    results/               Archived captures and build evidence
  examples/                Restricted logical JSON inputs
    runtime/               Editable annotated Stim examples
  tests/                   Python, native-firmware and browser regressions
  results/                 Older repetition-code evidence
rtl/                       SystemVerilog hardware
  top/                     Board-level entry modules
  common/                  Decoder cores, mailbox bridges and UART modules
  tb/                      RTL testbenches
  pkg/                     Shared board constants
vitis/                     ARM firmware and Vitis builders
  runtime/                 Runtime graph transport
  surface/, qec/           Older fixed-image transports
scripts/                   Build, simulation, loading and report checks
  bd/                      PS7/AXI GPIO block-design Tcl
constraints/               Clock and board-pin constraints
docs/                      Guides, plans, verification notes and screenshots
build/                     Generated local outputs; ignored by Git
```

The root [Makefile](../Makefile) groups common commands. Its build and firmware
defaults still select the older fixed-surface image. Use the explicit runtime
commands below for the current editor.

## qec/: host code and the software reference

### Follow one CLI run

Read `main()` and then `run_circuit()` in
[runtime_run.py](../qec/surface/runtime_run.py). The CLI reads a Stim file and
passes its text, seed and shot count to `run_circuit()`.

1. `compile_circuit()` validates the circuit and returns an ordered decoding graph.
2. With `--port`, `RuntimeSerialDecoder` reads the device capacities, recompiles
   against them and uploads the graph. Without it, Python decodes in Software mode.
3. Stim samples a batch of detector bits and true observable flips. Each detector
   vector becomes a little-endian syndrome integer: detector i occupies bit i.
4. `decode()` computes the Python reference. The FPGA path sends the syndrome
   and receives its own prediction and measured core-cycle count.
5. The runner compares the prediction with Stim truth for logical accuracy and
   with the Python reference for implementation agreement.

Only detector bits go to the decoder. Observable truth stays on the host. A
prediction bit tells the host whether to flip an observable's interpretation;
the hardware does not return physical correction gates.

Run a small software experiment from the repository root, with the documented
Python environment active:

```sh
python -m qec.surface.runtime_run qec/examples/runtime/two_repetition_echo.stim --shots 128 --seed 123 --out build/walkthrough-run
```

The output directory must be new. It contains `circuit.json` (compiled input),
`shots.jsonl` (per-shot results), `manifest.json` (versions and file hashes) and
`summary.json` (aggregate results). Hardware runs also write `wire.json` with
serial evidence. On failure, the runner retains partial evidence and writes
`error.json`; it does not report a successful summary or substitute software for
a failed FPGA request.

### Circuit compilation and decoding

[runtime_circuit.py](../qec/surface/runtime_circuit.py) is the place to change
accepted circuit operations, resource limits or graph-validation rules.
`compile_circuit()` checks input size and repeat expansion before parsing,
requires noiseless checks and observables to be deterministic, and rejects
unsupported feedback and unrepresentable fault signatures. Empty graphs require
an explicit compatible noisy reference.

Its result includes circuit text, detector metadata, ordered edges, dimensions
and hashes. An edge is `(endpoint_a, endpoint_b, observable_mask)`; the boundary
vertex has index equal to the detector count. Each mask can contain up to 32
observable bits. Runtime compilation imports `checked_graph()` from
[compile.py](../qec/surface/compile.py), but does not use that module's restricted
logical-program parser.

In [decoder.py](../qec/surface/decoder.py), read `decode()` for the shared
software algorithm. It grows half-edges around odd clusters, merges clusters,
then peels a forest to select correction edges and XOR their observable masks.
The algorithm is unweighted. Edge order affects tie handling and must agree
between the Python model and RTL. The same file's `graph()` and `export()`
functions generate fixed memory examples; the runtime path uploads edges
without writing a ROM.

### Web entry point

Start [runtime_web.py](../qec/surface/runtime_web.py) with:

```sh
python -m qec.surface.runtime_web --port 8766
```

Read `main()`, `make_server()` and `RuntimeLab.run()`. The browser posts settings
to `/api/run`. The server compiles in a bounded subprocess, uses one Stim
`FlipSimulator` shot to produce both the trace and final detector/observable
values, then decodes in software or through the serial client. Add
`--serial-port PORT` only for an already loaded runtime image.

The UI lives in [runtime_web_assets/](../qec/surface/runtime_web_assets/):
`index.html` defines the page, `style.css` controls layout, and `app.js` handles
inputs, Run and replay. Edits invalidate the completed result. Replay, stepping
and scrubbing use the returned trace without new simulation or serial requests.
A circuit `TICK` position is independent of measured FPGA cycles.

## rtl/: hardware entry point and state machines

Start at [top_runtime_soc.sv](../rtl/top/top_runtime_soc.sv). Its hierarchy is:

```text
top_runtime_soc
  system_wrapper                  Generated PS7 + AXI GPIO block design
  runtime_surface_ps_bridge       GPIO commands, graph/shot transfer, status
    runtime_surface_decoder       Configurable graph and decode state machine
```

The block design connects ARM to two GPIO channels. The bridge and decoder share
the PS-provided 100 MHz clock. Read
[runtime_surface_ps_bridge.sv](../rtl/common/runtime_surface_ps_bridge.sv) before
following individual core states: it translates mailbox opcodes into graph
configuration, syndrome submission and result reads.

In [runtime_surface_decoder.sv](../rtl/common/runtime_surface_decoder.sv), follow
these groups of states:

- Configuration accepts dimensions, ordered edges and a commit. An invalid load
  stays invalid until a new load begins. The default capacities are 128 detectors,
  512 edges and 32 observable bits.
- Initialization latches the syndrome and clears per-shot cluster, growth and
  forest state.
- Growth scans edges serially and merges clusters after both half-edges saturate.
  Separate registered read, selection and update stages keep indirect memory
  accesses out of one long combinational path.
- Peeling selects forest edges, propagates parity and accumulates observable
  masks. Residual detector parity produces a decode error.
- Result hold keeps the output stable until consumed. The measured cycle counter
  excludes time stalled in this hold state.

A shot abort preserves the loaded graph; a full reset invalidates it. The
[core](../rtl/tb/tb_runtime_core.sv),
[bridge](../rtl/tb/tb_runtime_bridge.sv) and
[counter](../rtl/tb/tb_runtime_counter.sv) benches exercise those boundaries.

## vitis/: ARM firmware between serial and GPIO

The runtime firmware starts at `main()` in
[vitis/runtime/src/main.c](../vitis/runtime/src/main.c). It polls UART bytes,
parses complete frames and dispatches graph or decode operations through GPIO.
[runtime_platform.h](../vitis/runtime/src/runtime_platform.h) contains the
hardware UART, GPIO and deadline adapters. ARM transports data; the PL core
performs the decode.

Read the host [runtime_host.py](../qec/surface/runtime_host.py) alongside the C
parser when changing the protocol. Requests use `D4`, replies use `4D`, and
frames include sequence, payload length and IEEE CRC32. `load_graph()` performs
begin, append, commit and identity readback. `decode()` checks graph metadata
before and after the shot.

The GPIO mailbox allows one outstanding toggle command. Firmware must see both
the matching acknowledgement and decode-complete status, with positive cycles
and unchanged graph generation/dimensions. A matching toggle alone can occur
after reset and is insufficient evidence of completion.

After an uncertain serial timeout, the host blocks further writes until bounded
resynchronization consumes the outstanding reply. A graph reload is then
required. Closing and reopening the port, or issuing abort, does not establish
that the old reply is gone.

## scripts/: build, simulate and load

For the runtime image, start with
[build_runtime.tcl](../scripts/build_runtime.tcl). It reads the runtime RTL and
constraints, creates the block design through
[bd/top_runtime_soc.tcl](../scripts/bd/top_runtime_soc.tcl), runs synthesis and
routing, checks timing, then exports the bitstream and XSA. The XSA describes the
hardware platform used by the firmware builder.

To choose a fresh output directory and explicit capacities:

```sh
vivado -mode batch -source scripts/build_runtime.tcl -tclargs build/walkthrough-image 128 512 32
QEC_RUNTIME_OUTPUT_DIR=build/walkthrough-image vitis -s vitis/runtime/build_app.py
python scripts/verify_runtime_timing.py build/walkthrough-image/runtime_soc_timing_summary.rpt
```

[build_app.py](../vitis/runtime/build_app.py) builds the ARM ELF against that
image's XSA. Both the image directory and Vitis workspace have overwrite guards.
[verify_runtime_timing.py](../scripts/verify_runtime_timing.py) checks the routed
timing report; [inspect_runtime_timing.tcl](../scripts/inspect_runtime_timing.tcl)
is for inspecting detailed paths.

[run_soc.tcl](../scripts/run_soc.tcl) is the XSCT loading entry point. It takes a
matching `.bit`, `.elf` and `.xsa`, programs volatile PL state and starts ARM.
It changes the connected board's running image, so use the loading command in
the [quick start](../README.md#2-load-the-board) when you intend to switch images.
[qec_readback.tcl](../scripts/qec_readback.tcl) reads configuration status;
that check alone does not prove a successful decoder transaction.

[run_runtime_rtl.py](../scripts/run_runtime_rtl.py) invokes Vivado's simulator in
isolated build directories. It generates core vectors from the Python reference:

```sh
python scripts/run_runtime_rtl.py --bench core
python scripts/run_runtime_rtl.py --bench bridge
python scripts/run_runtime_rtl.py --bench counter
```

## constraints/, tests and archived outputs

[constraints/top_runtime_soc.xdc](../constraints/top_runtime_soc.xdc) supplies
runtime timing constraints. The other XDC files belong to fixed-image or
direct-PL UART designs. Change the constraints for the top module you are building.

Run the normal regression entry point with:

```sh
make test
```

Start with the test matching the boundary you are editing:

- `qec/tests/test_runtime_circuit.py`: circuit acceptance, reference compatibility and resource limits.
- `qec/tests/test_runtime_host.py`: framing, PTY traffic, graph readback and timeout recovery.
- `qec/tests/test_runtime_platform.py`: production firmware/platform adapter checks.
- `qec/tests/test_runtime_run.py`: batch results, archives and failure handling.
- `qec/tests/test_runtime_web.py`: shot/trace consistency, HTTP checks and hardware errors.
- `qec/tests/test_runtime_rtl.py`: real core, bridge and cycle-counter simulations when Vivado is installed.
- `scripts/test_source_docs.py`: central-guide coverage and local Markdown links.

Browser checks are separate from `make test`. With a Software-only server on
port 8766, run:

```sh
RUNTIME_WEB_URL=http://127.0.0.1:8766 node --test qec/tests/test_runtime_web_ui.cjs
```

Keep that test pointed at a software server; it drives Run and must not contact
hardware by accident. Native firmware and PTY tests verify software transport
behavior, while RTL simulations verify hardware logic. Neither establishes
physical-board operation.

The `qec/results/` and `qec/surface/results/` directories contain historical
captures, manifests and tested-source snapshots. Leave those snapshots intact.
Use `build/` for new local generated output. Current runtime acceptance evidence
and its limits are recorded in [runtime-verification.md](runtime-verification.md).

## Older paths

Files with similar names belong to different decoder images:

- Fixed surface memory: [web.py](../qec/surface/web.py),
  [example.py](../qec/surface/example.py) and [host.py](../qec/surface/host.py)
  connect to `top_surface_soc` → `surface_ps_bridge` → `surface_decoder`.
  The graph is synthesized into a ROM. Build through
  [build_soc.tcl](../scripts/build_soc.tcl) and
  [vitis/surface/build_app.py](../vitis/surface/build_app.py).
  Follow the [legacy quick start](legacy-memory-quickstart.md).
- Repetition LUT: [qec/decoder.py](../qec/decoder.py) generates the syndrome lookup
  table. `top_qec_soc` → `qec_ps_bridge` → `qec_decoder` uses that fixed table.
  [qec/host.py](../qec/host.py) and [vitis/qec/](../vitis/qec/) provide its host
  and ARM transport. `top_qec_uart` is a separate direct-PL UART top.
- Restricted logical templates: [compile.py](../qec/surface/compile.py) accepts
  vetted memory, H or CX JSON inputs. Start with
  [qec/examples/README.md](../qec/examples/README.md) for that contract. It does
  not compile arbitrary logical programs into fault-tolerant circuits.

The fixed images use different protocols from runtime graph upload. Keep each
host, firmware and bitstream matched when reproducing an older experiment.
