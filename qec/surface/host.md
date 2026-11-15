# Physical d3 Z surface capture and transport boundary

Companion to [`host.py`](host.py).

## Contracts and flow

`request(seq, syndrome, nbytes=3)` emits `C3 seq payload_length payload xor`; syndrome bytes are little-endian and must fit the selected width. None produces a zero-length reset request. `parse(data, seq)` accepts exactly nine bytes with 3C header, matching sequence, zero total XOR and binary prediction. Nonzero status raises IOError; otherwise it returns prediction and a little-endian 32-bit core-cycle count.

`main()` requires an explicit serial port and fresh output directory. It samples a current-noise d3 Z circuit but decodes against committed d3_z_r3 edges matching the existing image, asserting 24 detectors. The nested `transact` validates each real reply against UF, flushes raw CSV evidence, and refuses UF errors, disagreement or zero cycles. Cases cover zero, singleton detectors, edge syndromes, dense seeded patterns and Stim samples.

Malformed checksum, garbage, partial and invalid-length traffic must stay silent; each gets a valid recovery probe. A real firmware command then resets PL state and the following valid decode must recover. The nested `interval(k,total)` computes the summary's 95% Wilson logical-error bounds. Summary separates UF agreement, PyMatching disagreement, logical truth, core cycles and host nanoseconds.

The runner copies expected bit/XSA/ELF/build/simulation artifacts and archives git HEAD plus dirty status and file hashes. Those prerequisites must already exist, and HEAD's source archive omits uncommitted changes. --board-id is metadata only. This runner is physical-only, sends probes and a PL reset, and does not program the board. Use --help to inspect it safely. Its fixed-memory transport is not an identity check for arbitrary compiled H/CX graphs.

## Callable index

- `request` — Encode C3 framing with a little-endian syndrome; None emits the zero-length PL reset command.
- `parse` — Validate a nine-byte 3C reply and return prediction/cycles; raise on transport or PL status.
- `main` — Capture d3 Z physical graph-decoder evidence, recovery probes and a PL reset transaction.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/surface/host.py --help
python -m pytest -q qec/tests/test_surface.py qec/tests/test_optional_board_id.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
