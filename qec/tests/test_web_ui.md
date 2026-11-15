# `test_web_ui.cjs` — offline replay contract tests

This CommonJS suite uses only Node built-ins: `node:test`, strict assertions, filesystem and path helpers. It resolves `../surface/web_assets/app.js` relative to `__dirname`, so invoking it from the repository root requires no npm install. The application's `document` guard means requiring it exports pure helpers without starting browser initialization or fetching anything.

## Tests and contracts

1. **Stale layout rejection:** `validateLayout()` rejects missing/empty tick arrays with an actionable restart-server error and returns a compatible object unchanged. The sample layout has `ticks: [{operations: []}]`, `data`, `checks`, and `detectors` arrays.
2. **Stale replay rejection:** `validateReplay()` rejects missing trace and a trace shorter than the requested tick count; a compatible trace has one `{pauli_frame: {}}` per physical tick, with `detector_indices` alongside it. Return identity is asserted.
3. **Cursor and fault history:** `LabState(21)` supports arbitrary seek, previous/next, clamping to zero and extra cursor 22, distinct tick-8 X/tick-16 Z faults on q10, toggling an identical selection away, and resetting history/cursor.
4. **Measurement availability:** `visibleDetectors()` uses `available_tick` inclusively, and recomputes after backward scrubbing. A fired ID is hidden before its measurement boundary; viewing a later tick cannot permanently reveal it.
5. **HTML integration hooks:** the static shell exposes replay/fault/evidence IDs, range input, polite live region, “Host correction”, initially disabled Play, and puts Play/status before the lattice. The assertions also prohibit obsolete introductory/footer markup. This is source-string validation, not a browser accessibility tree or computed layout check.

The suite intentionally supplies small synthetic schema/state inputs. These are unit fixtures, not claimed simulation or FPGA results. Compatibility coverage is selective: passing does not imply exhaustive validation of malformed nested values, request concurrency, timers or server input limits.

## Run and interpret

From the repository root:

```sh
node --test qec/tests/test_web_ui.cjs
# Both maintained JS suites; real-browser case skips without QEC_WEB_URL:
node --test qec/tests/*.cjs
```

Expected standalone result is five passing tests with no skips. No server, Python environment, browser, UART or board is involved. A failure naming an ID/order concerns the HTML binding contract; a restart-error failure concerns the compatibility guard; state failures concern cursor or edit-history semantics.

To exercise actual loading, playback, computed colors and error recovery, run the adjacent `test_web_browser.cjs` with an explicitly started simulation server as documented in `test_web_browser.md`. These layers complement each other: offline tests cannot establish visual rendering or hardware evidence.
