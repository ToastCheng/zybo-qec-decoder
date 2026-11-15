# General circuit command-line runner

Companion to [`runtime_run.py`](runtime_run.py). This is the command-line alternative to the runtime web interface, not the fixed-ROM memory example. It never programs or resets an FPGA.

## Run

From the repository root with the Python environment active:

```sh
python -m qec.surface.runtime_run qec/examples/runtime/two_repetition_echo.stim --shots 128 --seed 123 --out build/my-runtime-run
```

Without `--port`, the source is explicitly `Software`; the Python union-find reference performs decoding. To use an already loaded **runtime** image, add `--port /dev/ttyUSB1`, using the actual UART path. An old fixed-ROM image speaks a different protocol and is not compatible. Close other serial clients first. Hardware errors never fall back to software.

`--reference FILE` supplies the explicit compatible noisy reference required for an empty/zero-noise graph. Circuit annotations, graph representability and resource checks follow the [compiler contract](runtime_circuit.md). `--shots` is 1..4096; `--seed` is an unsigned 64-bit integer. Seed portability is limited by the installed Stim version, machine and sampling procedure. Batch CLI sampling need not match the single-shot web FlipSimulator procedure for the same seed.

## Flow and results

`run_circuit` validates scalar inputs and compiles the circuit before opening serial. Hardware mode reads the real advertised capacities, recompiles against them, uploads the exact ordered graph once, and samples a batch of actual Stim detector/observable records. Each FPGA decode uses those detector bits. It independently computes a Python UF reference, retaining disagreements rather than replacing the FPGA answer.

The summary reports source, completed shots, seed, physical qubit index count, detectors, observables, edges, measurement/TICK counts, logical failures against Stim truth, reference mismatches and graph hash. `ticks` counts Stim TICK separators, not extraction rounds. FPGA cycles measure core acceptance to result; graph-upload, PS, serial and host times are excluded. Software rows carry null cycles.

The optional `decoder_factory` function argument is only a test seam; normal CLI execution uses `RuntimeSerialDecoder`. A test-device result is not physical evidence.

## Fresh evidence directory

`--out` must not already exist. The runner creates:

- `circuit.json`: actual compiler bundle, circuit, graph, DEM, counts and host hashes.
- `shots.jsonl`: zero-based shot index, actual syndrome/observable, selected prediction/cycles, host reference and error flags. Rows flush after each completed shot.
- `wire.json`: hardware transactions and exact uploaded graph, produced by the transport; absent in software-only mode.
- `manifest.json`: source, settings, software/machine identity, timing scope, compiler limitations and hashes of raw evidence files.
- `summary.json`: success summary, written only after all shots and archive operations succeed.

On failure, the runner keeps partial rows and any transport archive and writes `error.json` instead of a success summary. It propagates the exception; it does not retry an uncertain completed transaction. Consult [runtime transport](runtime_host.md) for session recovery requirements. Host graph SHA-256 identifies an artifact; it is not an FPGA-attested cryptographic identity.

## Verification

```sh
python -m pytest qec/tests/test_runtime_run.py -q
python -m qec.surface.runtime_run --help
```

The regression independently regenerates seeded Stim records and verifies software evidence, failure archives, fresh-directory protection and rejection before serial access. Board callbacks in that regression are explicitly software test devices, not FPGA execution.
