# `app.js` — replay controller and renderer

This dependency-free script is loaded with `defer` by `index.html`. It displays the fixed rotated distance-three Z-memory, three-round teaching circuit. It does not run Stim or a decoder in JavaScript, and animation is not live hardware telemetry.

## Structure and state

- `LabState(lastTick = 21)` owns the editable `faults` array and replay cursor. `reset()` clears both; `seek()` rounds and clamps to `0..lastTick+1`; `next()`/`previous()` delegate to it. The extra position is the **host correction** overlay, not a circuit operation. `toggle(qubit, pauli, tick)` removes an identical selection or replaces a different Pauli at the same `(tick, qubit)`; faults on different ticks stay independent. Its default injection time clamps the cursor to the last physical tick.
- `visibleDetectors(detectors, indices, tick)` filters fired IDs by `available_tick`. Backward scrubbing recomputes availability; previously seen events are not latched.
- `validateLayout()` and `validateReplay()` return the original object after minimal compatibility checks, or throw an actionable restart error. They are not complete JSON-schema validators. These helpers and `LabState` are CommonJS exports for the offline tests.
- The `document` guard contains browser-only setup. `layout` describes the circuit; `state` describes edits/cursor; `result` is the latest accepted server response; `pending`/`failure` drive status; `requestId` rejects out-of-order responses; `timer` is the local playback timeout; `pauli` is the current injection tool.
- `api()` performs same-origin GET or JSON POST and propagates the server's JSON error. `simulate()` stops playback, snapshots faults, clears old results, posts them, validates the response and redraws. Older requests are ignored, not cancelled.
- `stop()`, `seek()` and `advance()` manage transport. Play moves immediately, then schedules steps at `700 / speed` milliseconds. Changing speed affects a subsequently scheduled delay. Explicit seeking updates the fault-tick input; timed advance does not.
- `position()` maps circuit coordinates to the 720-unit SVG/percentage lattice. `combine()` composes Pauli letters modulo global phase. `render()` rebuilds CX links, qubit buttons, the four-column detector timeline, status/result labels, evidence JSON and circuit text. It restores focused qubits after rebuilding buttons.

## Server data contract

`GET /api/layout` supplies nonempty `ticks`, each with `operations: [{name, targets}]`; `data` and `checks` contain `{id, coords}` with `basis` on checks; `detectors` contain `{id, coords: [x,y,time], available_tick}`; `source` labels provenance. CX `targets` are consecutive control/target pairs. Current rendering assumes four detector-time columns and the teaching layout's coordinate scale.

`POST /api/simulate` sends only `{faults: [{tick, qubit, pauli}]}`. Each fault enters **before** its selected tick's operations. The server validates integer times/data-qubit IDs, Pauli X/Y/Z and request limits.

The renderer requires `detector_indices` and `trace` with one `{pauli_frame}` entry per physical tick. Frames map qubit IDs to nonidentity Pauli letters **after** that tick's operations. It also consumes `correction_frame`, nullable `correction`, nullable `residual_syndrome`, `logical_success`, `host_frame`, `source`, and circuit strings. Details expose `hardware`, `reference_prediction`, `syndrome`, `observable`, `prediction`, `correction_edges` and `residual_observable`.

Detector flips are withheld until their measurement boundary, independent of error-frame visibility. At the extra final cursor, the host correction combines with the last frame and detector cells can show `1→0`. An absent representative (`correction === null`) is labeled, not silently treated as a demonstrated correction.

## Interaction and evidence boundary

Pauli selection and fault-time editing redraw locally. Clicking a data qubit, loading the example (X on q10 at tick 8), or clearing faults requests a fresh full-window result. Checks are not injection controls. Back/next/scrub stop playback; replay from the final position starts again at zero. Arrow keys and Space work outside native interactive controls and without Ctrl/Meta/Alt.

An FPGA-backed server supplies prediction and measured cycles for a **complete window**. Graph correction edges, representative Pauli replay and residual circuit evidence are host-derived. Source labels and `edges_source: "Host reference"` keep that distinction explicit. No animation step sends a board command or demonstrates live feedback.

## Verification (repository root)

```sh
node --test qec/tests/test_web_ui.cjs
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# In another terminal, simulation mode only (no --serial-port):
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
```

The browser command needs Chrome and Node with native WebSocket/fetch support (Node 22+). See adjacent test docs for coverage and optional stale-server checks. Neither test establishes board timing or hardware correctness.
