# `test_web_browser.cjs` — real Chrome run/replay regression

This opt-in test uses isolated headless Chrome and Node 22+ native fetch/WebSocket to drive CDP, without npm dependencies. Successful evidence comes from the real API; only the labeled 503 failure is synthetic.

## Run

From the repository root:

```sh
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# Separate terminal:
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_ui.cjs qec/tests/test_web_browser.cjs
```

Use a simulation-only server without `--serial-port`; a hardware-backed URL can perform actual board transactions. The test does not own the supplied server. Without QEC_WEB_URL it skips. `CHROME` overrides google-chrome; `TMPDIR` selects the private profile parent. The test removes its profile and Chrome process at teardown. Optional `QEC_STALE_URL` supplies a separate incompatible-layout endpoint; no stale server is created here.

## Harness and coverage

A correlated command map drives a target WebSocket; runtime exceptions are collected separately. Bounded semantic polling waits for controls/evidence. CDP Network records POST requests, while Fetch can fail a run or hold a real request for concurrency checks. A 30-second test timeout bounds execution; short delays settle CSS transitions.

- Startup renders the 17-qubit fixed template, leaves Replay disabled and sends no POST. Assert default seed 20261107 and four rates of 0.001, then set rates to zero for deterministic visual assertions; editing still sends no POST.
- Explicit Run sends `/api/run`. Initial Replay advances immediately to cursor 1, showing blue active H gates. The selected X q10@8 produces amber error, coral detector flips and host correction with mint tags/cleared detector cells. The corrected counterfactual has residual observable zero; an equivalent stabilizer frame need not be sitewise identity.
- Backward scrub hides future measurements; replay from the end restarts. All replay activity leaves POST count unchanged. Clear, Example and lattice edits invalidate evidence without requests. A new explicit Run accepts the cleared configuration.
- Inject a labeled 503, require actionable visible error/unavailable source/disabled Replay, then disable interception and recover through a real Run.
- Hold a real Run request and assert Run, seed, lattice edits and Replay are disabled. A synthetic input bypassing disabled controls invalidates it; releasing the old reply cannot restore Replay. A new explicit run displays the updated seed.
- Sweep 1280, 820, 760, 600, 390 and 360px for horizontal overflow and Replay visibility. Optionally verify incompatible-layout restart guidance at QEC_STALE_URL.

The test projects real server results but does not independently validate Stim, serial timing or hardware decoding. Host correction remains counterfactual evidence, not physical feedback.
