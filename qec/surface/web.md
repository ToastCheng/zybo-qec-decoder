# Stim-backed local teaching API and optional serial prediction

Companion to [`web.py`](web.py).

## Contracts and flow

`Lab(decoder=None)` loads the fixed d3 Z graph and flattened ideal circuit. `_segments` derives tick boundaries; `_fault_circuit` injects probability-one X/Y/Z_ERROR operations before selected tick operations so Stim's noiseless reference does not absorb bare Pauli gates. `_sample` returns a packed 24-detector syndrome and observable. `_signature` caches singleton effects, and `_basis` builds bounded GF(2) pivots carrying Pauli representatives. `_correction` solves the full detector-plus-predicted-observable signature at selected fault ticks or returns None; it is not MWPM or a minimum-weight optimizer.

`simulate_faults` validates at most 64 exact tick/qubit/pauli records, decodes UF, derives detector availability and an illustrative propagated Pauli trace, optionally obtains external prediction, and independently samples the corrected counterfactual circuit. `_pauli_trace` conjugates H/CX and erases resets. Invalid external results raise rather than fallback. External prediction may replace prediction, but graph correction_edges remain host UF-derived; the API retains reference_prediction and hardware evidence separately. Zero syndrome alone never means logical success.

Legacy `simulate(errors)` accepts canonical data-ID strings to Pauli mappings and injects after first MR via `_circuit`. `_representatives` uses dynamic programming for minimum-support same-signature legacy representatives. `layout()` derives coordinates, supports, gates and detector availability from actual Stim operations rather than a hand-drawn lattice.

`SerialDecoder` lazily opens an explicit exclusive UART per call, uses a bounded mutex and wrapping sequence, disables deliberate handshake-line reset and rejects malformed/zero-cycle replies. It assumes the loaded fixed d3 memory image, not arbitrary compiler graphs.

`make_server(port, decoder)` returns a 127.0.0.1 ThreadingHTTPServer. Its nested Handler serves only three local assets and GET /api/layout; POST /api/simulate accepts exactly errors or faults in a 1..4096-byte JSON body. It rejects transfer encoding/cross-origin writes, bounds sockets and decoder-lock waits, serializes model access, maps invalid input to 400 and backend failure to 503, and sets no-store/nosniff/CSP headers. Legacy errors are converted to tick 8 when hardware is configured. `main()` serves until interruption and closes the server. Counterfactual replay and host frames are not physical feedback or PL-provided correction edges.

## Callable index

- `Lab` — Stim-backed d3 Z teaching model with optional external prediction and counterfactual replay.
- `Lab.__init__` — Load the committed decoder graph and flattened ideal circuit without opening serial.
- `Lab._segments` — Split the ideal circuit at TICKs, retaining the initial pre-TICK segment.
- `Lab._fault_circuit` — Inject probability-one Pauli errors before operations at each selected tick.
- `Lab._signature` — Cache a singleton fault as 24 detector bits followed by its observable bit.
- `Lab._basis` — Build a bounded GF(2) basis of real singleton signatures and their Pauli representatives.
- `Lab._correction` — Solve the requested syndrome/prediction signature at the injected ticks, or return None.
- `Lab._pauli_trace` — Propagate an illustrative Pauli frame through H/CX and erase reset-qubit errors.
- `Lab.simulate_faults` — Validate timed faults, obtain a prediction and independently replay a same-tick representative.
- `Lab._circuit` — Build the legacy injection circuit, placing errors after the first MR instruction.
- `Lab._sample` — Sample one deterministic fault circuit and return packed syndrome and observable.
- `Lab._representatives` — Find minimum-support legacy Pauli representatives by dynamic programming over signatures.
- `Lab.simulate` — Validate legacy qubit-to-Pauli input and return UF correction plus independent replay evidence.
- `Lab.layout` — Derive data/check supports, detector availability and operation ticks from the actual Stim circuit.
- `SerialDecoder` — One complete-window transaction; no reset or programming commands.
- `SerialDecoder.__init__` — Configure a port name, bounded lock timeout and sequence counter without opening it.
- `SerialDecoder.__call__` — Serialize one exclusive UART transaction; reject invalid replies without software fallback.
- `make_server` — Return a loopback-bound threaded HTTP server with bounded JSON input and serialized decoding.
- `main` — Serve the local teaching lab, optionally using an explicitly selected loaded memory-image UART.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python -m qec.surface.web --help
python -m pytest -q qec/tests/test_web.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
