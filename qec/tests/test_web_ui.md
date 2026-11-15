# `test_web_ui.cjs` — offline frontend contracts

Run `node --test qec/tests/test_web_ui.cjs` from the repository root. The six Node built-in tests require no npm packages, server, browser or board. Importing `app.js` exports pure helpers without starting browser setup.

Coverage:

- `runSettings` constructs only rotated d3 Z-memory/three-round requests, preserves independent noise values and snapshots timed faults; invalid rates and negative seeds throw actionable errors.
- Layout/replay compatibility guards reject missing/empty tick data and missing or wrong-length traces with restart guidance.
- `LabState` supports reversible seek/step, cursor clamping including the host overlay, multi-time fault selection and clearing.
- Detector availability is inclusive at measurement time and reversible under backward scrubbing.
- HTML exposes the numbered Configure/Simulate/Replay steps, settings/Run/summary IDs, initially disabled Replay, live error region and prominent lattice/timeline. Evidence remains collapsed and transport/status precede the workspace.

Small synthetic inputs here are unit fixtures, not simulation/FPGA results. Source-string assertions cannot prove browser layout, timers, concurrency or fetch behavior. The adjacent opt-in Chrome test covers those integration boundaries using a real simulation server; see `test_web_browser.md`.
