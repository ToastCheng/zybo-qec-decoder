# Stim-backed local teaching API and optional serial prediction

Companion to [`web.py`](web.py).

## Configurable single-shot run

`POST /api/run` accepts exactly this object (all fields required):

```json
{
  "circuit": "surface_code:rotated_memory_z",
  "distance": 3,
  "rounds": 3,
  "noise": {
    "after_clifford_depolarization": 0.001,
    "before_round_data_depolarization": 0.001,
    "before_measure_flip_probability": 0.001,
    "after_reset_flip_probability": 0.001
  },
  "seed": 1,
  "faults": [{"tick": 9, "qubit": 10, "pauli": "X"}]
}
```

Use `faults: []` for stochastic noise alone. Circuit, distance and rounds are restricted to the committed `d3_z_r3.json` graph, including its detector order and observable definition. Other circuits are rejected before decoder I/O, even without a serial decoder. The distance/round counts must be integers, not booleans or floating-point equivalents. Each noise rate must be a finite, nonboolean number in **0..0.75**, inclusive. The seed must be an integer in **0..9007199254740991**. No extra noise/settings keys are accepted. Faults are at most 64 exact `tick`, `qubit`, `pauli` records, using data qubits, valid tick indices and X/Y/Z. They are injected before that tick's operations.

`Lab.run(settings)` generates the actual noisy flattened Stim circuit. One `stim.FlipSimulator(batch_size=1)` executes it operation by operation. Detector flips, the observable flip and each end-of-tick Pauli frame come from **that same simulation instance**. Stabilizer randomization is disabled deliberately: this fixed memory circuit has deterministic detectors and observable, and the visualization is a noise-error frame, not a quantum-state reconstruction. Preparation and measurement gauge randomness must not be misrepresented as sampled hardware faults.

At each generated Pauli noise operation, the simulator's pre/post frame delta supplies actual sampled per-qubit errors, with tick, generated operation index and operation name. Two-qubit depolarization can produce two entries for one operation. Identity outcomes have no entry. Explicit user faults are excluded from `sampled_noise.events` and remain in `settings.faults` and trace `faults`. These records are not inferred from the detector syndrome.

The run freezes sampled noise into probability-one Pauli errors in `sampled_circuit`. An independent deterministic Stim sample must reproduce its original syndrome and observable before decoding. Seed reproduction is scoped to the same Stim version, machine/SIMD support, batch size and exact operation-call sequence; it is not guaranteed across versions or platforms. `sampled_noise` records the seed, Stim version, simulator and randomization choice.

## Results and correction evidence

The response retains the existing timed-fault result schema:

- `syndrome`: packed detector bits; `observable`: actual sampled logical flip.
- `prediction`, `host_frame`: the selected prediction. A configured external decoder's returned bit is authoritative, even when it disagrees with host UF.
- `reference_prediction`, `correction_edges` and `error`: host UF evidence from the fixed committed graph. Hardware cycles live separately in `hardware.cycles`; graph edges are never FPGA-returned physical corrections.
- `trace`: per-tick `tick`, `operations`, `pauli_frame`, cumulative explicit `faults` and only detector events available by that tick.
- `source`: `FPGA` when an external decoder supplied the result, otherwise `Simulated`; `hardware`: the external result or null.
- `settings`, `injected_circuit`: submitted settings and actual noisy circuit including explicit faults.
- `sampled_noise`, `sampled_circuit`: actual noise provenance and a deterministic replay of the particular shot.
- `correction`, `correction_frame`, `corrected_circuit`, `residual_syndrome`, `residual_observable`, `correction_status`: host physical representative and counterfactual verification evidence, or null/unavailable evidence.

A GF(2) basis of actual singleton data-fault signatures across all valid ticks solves the full detector-plus-selected-prediction signature. Its Pauli representative is inserted into the **frozen sampled circuit**, never a fresh stochastic resample. Verification requires residual syndrome zero and residual observable equal to `observable XOR prediction`. A representative that cannot be solved or verified is returned as `correction: null`, `corrected_circuit: null`, null residuals, empty correction frame and `correction_status: "unavailable"`; verified results use `"verified_counterfactual"`. This is an illustrative host counterfactual across the full memory experiment, not causal feedback to a quantum device, and not necessarily a minimum-weight correction.

`logical_success` always compares actual sampled observable with selected prediction and requires no host UF error. Detector cancellation alone does not prove logical success. Failed or malformed external decoder replies raise; there is no silent software fallback.

## Existing APIs and model helpers

`Lab(decoder=None)` loads the fixed graph and ideal flattened circuit without opening serial. `_segments` splits the ideal circuit at TICKs. `_fault_circuit` inserts probability-one Pauli errors. `_sample` independently samples deterministic circuits. `_signature`, `_basis` and `_correction` build and solve singleton signatures; `_pauli_trace` propagates an illustrative fault frame through H/CX and erases reset errors. `_validate_faults` is shared by configurable and deterministic timed-fault runs.

`POST /api/simulate` remains backward compatible: exactly `{"faults": [...]}` calls `simulate_faults`; exactly `{"errors": {"10": "X"}}` calls legacy `simulate` without hardware, or converts to tick 8 with hardware after validating legacy input. These APIs have no stochastic noise settings. `simulate_faults` solves at the explicit fault ticks and independently verifies a deterministic counterfactual. Legacy `_circuit` injects after the first MR; `_representatives` uses dynamic programming for minimum-support same-signature legacy representatives.

`GET /api/layout` derives coordinates, supports, gate ticks and detector availability from the ideal circuit. It also returns `supported_circuits` metadata and `run_defaults` (all four noise rates 0.001, seed 1, no explicit faults). Changing noise does not recompile the committed decoder graph or load a new FPGA image.

## HTTP and serial boundaries

`make_server(port=8765, decoder=None)` keeps its signature and binds a threaded HTTP server to 127.0.0.1. The handler serves only three allowlisted local assets and the layout endpoint. Configurable run bodies are bounded to **1..16384 bytes**, adequate for a formatted 64-fault request; legacy simulation retains **1..4096 bytes**. Transfer encoding and cross-origin writes are rejected. Every GET and POST also requires a single `Host` authority of `127.0.0.1:PORT` or `localhost:PORT` for this server's actual port, rejecting DNS-rebinding hostnames before serving assets or invoking the decoder. Socket operations and decoder-lock acquisition are bounded, model access is serialized, invalid requests return 400 (413 for oversized bodies), and backend failures return 503 with source information. Responses include no-store, nosniff and restrictive CSP headers.

`SerialDecoder` lazily opens an explicitly selected exclusive UART for one complete-window transaction. It uses a bounded mutex and wrapping sequence, avoids deliberate handshake-line reset, and rejects malformed or zero-cycle replies. It assumes a matching loaded fixed d3 Z r3 memory image; this web endpoint does not establish board-image identity or program hardware. `main()` serves until interruption and closes the server.

## Verification

From the repository root with the configured environment:

```sh
qec/.venv/bin/python -m qec.surface.web --help
qec/.venv/bin/python -m pytest -q qec/tests/test_web.py qec/tests/test_web_run.py
```

The new regression suite checks deterministic seed reproduction, distinct sampled shots across seeds, zero/maximum noise, exact sampled and corrected replay, invalid settings before decoder I/O, a formatted maximum-fault HTTP request, authoritative external prediction and no fallback. No physical hardware is required or exercised by these tests.
