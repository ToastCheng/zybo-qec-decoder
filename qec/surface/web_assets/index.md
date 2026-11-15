# `index.html` — three-step lab shell

Served at `/` by `qec.surface.web`, this semantic shell loads same-origin deferred `/app.js` and `/style.css` without build tooling. Open through the server, not a file URL.

## DOM contract

1. **Configure:** `#configure` exposes the one supported `#circuit-template` (d3 Z memory, three rounds), `#seed` (20261107), four noise inputs (0.001 each, IDs matching API noise keys), X/Y/Z tools, `#fault-tick`, `#example`, `#reset` and selected-fault `#scenario`. Data-qubit buttons in the lattice also edit this configuration.
2. **Simulate + decode:** `#run-title` becomes “2 Simulate + FPGA decode” for FPGA layout source, otherwise “2 Simulate + software decode”. `#run` explicitly submits one run; `#run-summary` reports completed source, seed, prediction, observable and cycles (N/A for software).
3. **Replay:** `#play` retains its binding ID but is labeled Replay/Pause. `#back`, `#step`, `#speed`, `#position` and `#scrubber` control only the accepted result. Initially disabled replay becomes available only after a successful explicit run.

`#status` is a polite live region above the prominent lattice/timeline workspace. `#source` labels provenance in the header. `#lattice` contains dynamic qubit buttons/CX links, while `#timeline` holds four measurement-boundary columns. `#tick-label`, `#operations`, `#event-count` and `#result` describe the selected cursor. Collapsed `#evidence` contains technical JSON and original/corrected circuit text. Native details, labels, focus outlines and pressed tool states preserve keyboard access.

## Behavior and evidence boundary

Page load requests only `/api/layout`. Example selection, Clear and fault/settings edits never run automatically. Only `/api/run` submits the fixed circuit/settings/fault JSON; edits invalidate results with “Run to update”. Pending requests lock editing and Run. Failure keeps replay disabled and reports an actionable retry message. See `app.md` for exact payload and state semantics.

Faults enter before tick operations. The extra final cursor is a host-correction overlay, not another physical gate. FPGA decoding handles complete windows and returns prediction/cycles; graph edges and counterfactual representative replay are host-derived, not live feedback. The fixed selector does not promise arbitrary circuits.

## Verification

```sh
node --test qec/tests/test_web_ui.cjs
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# Separate terminal:
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
```

Offline checks cover bindings and step labels. Chrome checks actual explicit Run/local Replay, errors, pending safety, colors and responsive overflow.
