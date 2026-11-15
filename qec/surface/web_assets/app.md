# `app.js` — configure, run and local replay

The dependency-free deferred controller supports only the hardware-compatible rotated d3 Z-memory circuit with three rounds. It does not run Stim or a decoder in JavaScript.

## State and helpers

`LabState` owns selected timed Pauli faults and the cursor, clamped to physical ticks plus one host-correction position. Identical fault selections toggle off; a different Pauli replaces the same tick/qubit. `visibleDetectors` recomputes measurement availability on every render, including backward scrubbing. `validateLayout` and `validateReplay` reject incompatible server schemas with an actionable restart error. `runSettings` validates independent finite noise rates in 0–0.75 and a nonnegative safe-integer seed, and snapshots faults with the fixed circuit/distance/rounds. These helpers are CommonJS exports for offline tests.

Browser state separates `layout`, editable `state`, accepted `result`, pending/failure state, a monotonic request ID and a local timeout. Startup fetches only `GET /api/layout`, selects the explicitly labeled X q10@8 example and renders it without running. Defaults are four noise rates of 0.001 and seed 20261107.

## Explicit run contract

Only `#run` invokes `simulate()`, which clears previous evidence, stops playback and sends `POST /api/run`:

```json
{"circuit":"surface_code:rotated_memory_z","distance":3,"rounds":3,"noise":{"after_clifford_depolarization":0.001,"before_round_data_depolarization":0.001,"before_measure_flip_probability":0.001,"after_reset_flip_probability":0.001},"seed":20261107,"faults":[{"tick":8,"qubit":10,"pauli":"X"}]}
```

The response contains the replay schema plus `settings`. The renderer requires `detector_indices` and one trace `{pauli_frame}` per layout tick. It consumes prediction/observable/source/hardware, host correction/residual evidence and circuit strings. The completed summary displays response seed, prediction, observable, source and measured hardware cycles, or N/A for software. Full server validation remains authoritative.

Settings and fault edits, Example and Clear never submit requests: `invalidate()` stops playback, clears evidence, resets the cursor and disables all replay controls with “Run to update”. Pauli-tool and injection-time selection alone only redraw, because they do not alter selected faults. Pending runs disable Run and editing controls, including lattice injection buttons. Request IDs additionally reject stale replies if a synthetic edit bypasses disabled controls. Failed requests show a retry action and never fall back to another decoder.

## Replay and rendering

Replay/Pause, back/next, scrub, speed and keyboard navigation are local. Replay advances immediately, then schedules at `700 / speed` milliseconds. At the end it restarts from zero; cursor controls stop playback. Space/arrow shortcuts avoid native interactive controls and modified shortcuts. Replay remains disabled until an explicit successful run.

`render()` derives CX SVG links, active gates, propagated Pauli terms and measurement-boundary detector cells from the server layout/trace. Qubit focus survives redraws. The extra final position overlays the host correction; an equivalent stabilizer residual need not be sitewise identity. Green cleared detector cells are host counterfactual evidence, not erased physical measurements. FPGA source means complete-window prediction/measured cycles only; correction edges and representative Pauli replay remain host-derived, not live feedback.

## Verification

From the repository root:

```sh
node --test qec/tests/test_web_ui.cjs
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# Separate terminal, simulation-only server:
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
```

The browser test uses real API results, CDP request counting, explicit failure injection and held real requests for stale-response protection. It does not establish hardware correctness.
