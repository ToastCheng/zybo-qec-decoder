# Real Chromium runtime-editor regression

`test_runtime_web_ui.cjs` uses Node's built-in WebSocket and Chrome DevTools Protocol, without npm dependencies. Node with native WebSocket and an installed Chromium/Chrome are required. CHROME overrides the default /usr/bin/google-chrome. The test creates a private browser profile under TMPDIR, launches headless Chrome with an ephemeral debugging port, and removes only its own profile/process in finally.

Start a **Software-only** isolated preview from the repository root:

```sh
python -m qec.surface.runtime_web --port 18767
```

In a separate shell:

```sh
RUNTIME_WEB_URL=http://127.0.0.1:18767 node qec/tests/test_runtime_web_ui.cjs
RUNTIME_WEB_URL=http://127.0.0.1:18767 make test
```

Use a URL without trailing slash. Stop the owned preview after testing; leave any existing user preview on 8765 untouched. With no URL the direct Node script reports SKIP; the pytest wrapper likewise skips. Source must be Software, so a mistakenly configured hardware preview fails before Run.

The test selects IDs defined by index.html: #circuit, #run, #source, #status, #gates, #scrub, #play, #pause, #step, #seed and #result. It runs the actual default phase-Bell circuit, checks status ready and one Run request, then verifies initial Replay advances both the tick and visible operation text. Pause must hold the tick, backward scrub plus Step must select tick 1, and all playback reuses the same network response. Evidence details remain closed.

The primary SVG assertions check two real wires, H/S/CX gates, distinct controls/targets, separate MPP product groups/basis labels, and actual computed active/inactive fills while the initial Replay timer advances. At 360px the active column must move into the internal scroll viewport. A sparse q0/q1023 circuit checks two wires/chips, separate sequential CX pair columns, honest SPP labeling, uint32 bit31 and replay without requests. A 1024-used-qubit circuit checks the 64-wire cap, explicit q64–q1023 omission notice, bounded DOM and 430px scroll height. X error color and detector bits are asserted separately.

Geometry assertions verify no horizontal document overflow at 1280/820/390/360px. Editing invalidates the result and disables replay; an empty seed is rejected locally without a request instead of silently becoming zero, and an invalid gate surfaces a server error with no stale evidence. Finally an unlisted three-qubit annotated circuit runs real Stim with deterministic X_ERROR(1), OBSERVABLE_INCLUDE(31), and compares displayed prediction/truth 2147483648. Replay from the end resets to zero and advances without another request.

CDP captures requests from before navigation: zero initial POSTs, exactly five explicit /api/run POSTs overall (default, invalid, unlisted, sparse, dense-cap), and no automatic validate requests. A browser-side fetch counter additionally checks replay paths. This is Software UI evidence, not a fake FPGA success or physical board acceptance.

Set RUNTIME_WEB_SCREENSHOTS_DIR=build/runtime-web-qa to save actual 1280px and 390px Software screenshots using CDP, paused on the three-qubit observable-bit-31 example before the sparse/dense stress cases. Desktop capture is 1440px tall so the diagram and result are visible together. The saved phone screenshot captures the initial viewport; lower evidence remains reachable by vertical scroll. Failures propagate a nonzero exit status, and pytest imposes a 90-second overall subprocess timeout.
