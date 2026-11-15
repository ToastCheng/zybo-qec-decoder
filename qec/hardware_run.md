# Physical repetition capture and evidence archive

Companion to [`hardware_run.py`](hardware_run.py).

## Contracts and flow

`evaluate(rows, table)` accepts nonempty transaction dictionaries and returns counts for table disagreement, weighted-reference disagreement and logical-observable errors, plus cycle extrema and host-roundtrip statistics. It does not perform serial I/O.

`main()` requires an explicit `--port` and a fresh `--out` directory. `--board-id` is an optional archive label, not discovery or authentication. It samples noisy repetition windows, opens a 115200-baud endpoint, and uses the nested `transact` helper to write four-byte requests and validate six-byte replies with the repetition Parser. Every accepted transaction is flushed to CSV with raw TX/RX bytes.

The corpus first covers all 256 addresses, then seeded Stim shots. Bad checksums, garbage and a partial request must produce silence, and each is followed by a valid recovery request. The summary separates exhaustive and sampled accuracy. It asserts table agreement and two-cycle replies after creating summary/manifest artifacts.

This physical-only runner copies specifically named bit/XSA/ELF, logs, reports and LUT artifacts; they must already exist. It archives git HEAD and records dirty status, but that archive does not include uncommitted sources. Host nanoseconds include USB/PS/AXI overhead and are not core cycles. Running this command contacts hardware and sends malformed-traffic probes; a help invocation is the safe inspection command below. It never programs the board itself.

## Callable index

- `evaluate` — Summarize nonempty transaction rows without conflating LUT agreement and logical accuracy.
- `main` — Capture exhaustive, sampled and recovery transactions on an explicit physical serial port.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/hardware_run.py --help
python -m pytest -q qec/tests/test_hardware_run.py qec/tests/test_optional_board_id.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
