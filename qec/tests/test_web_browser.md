# `test_web_browser.cjs` — opt-in Chrome replay regression

This CommonJS test drives a real isolated headless Chrome via the Chrome DevTools Protocol (CDP). It uses Node built-ins plus native `fetch` and `WebSocket` (Node 22+), not npm browser libraries. Successful simulation evidence is obtained from the supplied running server; only the explicit failure phase is synthetic.

## Configuration and runnable verification

From the repository root, start a **simulation-only** server:

```sh
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
```

In another terminal:

```sh
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
# Or include offline tests in the same run:
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/*.cjs
```

Do not provide `--serial-port` for board-free verification. The test does not start/stop the web server; stop the server you started afterward. Without `QEC_WEB_URL`, its single test is explicitly skipped, not passed browser coverage.

- `CHROME` overrides the executable (default `google-chrome`). It must accept Chrome headless/CDP flags. The test uses `--no-sandbox`, so run against a trusted local app, not arbitrary untrusted pages.
- `TMPDIR` selects the temporary profile parent, falling back to `os.tmpdir()`. Each invocation gets an independent profile/cache, removed during cleanup.
- Optional `QEC_STALE_URL` points to a separate server serving current assets but an incompatible old layout API. No such fixture server is created by this test. When absent, the stale-server branch is not exercised; offline schema tests still cover helper rejection.

## Harness structure

`delay()` supports bounded polling and color-settle waits. The test spawns Chrome with an ephemeral debug port, reads its stderr endpoint, creates a target with HTTP PUT to `/json/new`, then connects the target's native WebSocket. Teardown hooks kill the owned Chrome, remove its profile and close the socket.

A monotonically increasing command ID and `requests` map pair CDP responses with promises. `Runtime.exceptionThrown` events collect uncaught errors. `cdp()` sends protocol commands; `js()` evaluates expressions with `returnByValue`/`awaitPromise` and rejects expression exceptions; `until()` polls a semantic condition up to 150 times at 50ms intervals and includes body text on timeout. The entire test has a 30-second timeout. Short 150ms delays allow the stylesheet's 120ms color transitions to settle before computed-style assertions.

## Interaction coverage

- At 1280×900, wait for enabled Play and 17 qubits; click initial Play and assert immediate cursor `1 / 22`, visible H label and blue active-gate fill.
- Confirm the explicit X q10@8 example, accelerate playback, observe amber error, coral detector flips, then the final **Host correction** label, mint correction, identity residual, two cleared detector cells and “Z preserved”.
- Scrub backward to tick 13 and require future flips to disappear; replay from cursor 22 must restart immediately at cursor 1.
- Clear faults, wait for a real fresh response, verify zero injected faults in evidence and a genuinely noiseless final display.
- Intercept only `/api/simulate` with CDP Fetch and return a labeled JSON 503 (`Regression fixture: FPGA unavailable`). Assert visible error above the lattice, unavailable source and disabled Play. Disable interception and retry the example through the real server to verify recovery.
- Sweep widths 1280, 820 and 390, asserting no horizontal overflow and Play inside the viewport.
- If configured, navigate to the stale server and require the actionable restart message, disabled Play and unavailable source, without uncaught runtime errors.

## Data and evidence boundary

The server must expose `/`, `/app.js`, `/style.css`, `/api/layout` and `/api/simulate` with the contracts consumed by `app.js` (see `../surface/web_assets/app.md`). This test assumes the maintained d3 Z three-round teaching circuit, its 17 qubits, 22 physical tick frames and the default example's two detector flips. It is not a generic arbitrary-code UI test.

The test validates UI projection of actual server responses, not independent correctness of Stim, the decoder or serial hardware. “Host correction”, cleared detectors and identity residual are counterfactual host replay evidence, not proof of physical correction or live feedback. The deliberately injected 503 proves failure handling only; its FPGA wording does not imply a board was accessed. A supplied FPGA-backed URL may contact hardware, so use the simulation command above when board use is prohibited.
