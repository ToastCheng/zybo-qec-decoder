# Runtime circuit editor document

`index.html` defines the accessible, CSP-compatible controls consumed by [app.js](app.md), with external script and [stylesheet](style.md); there are no inline handlers or CDN dependencies.

The primary input is `#circuit`, a free-text Stim editor rather than a template selector. `#reference` is inside an optional compatible noisy-reference disclosure. `#seed` and `#noise` configure sampling and added unitary depolarization. `#source` identifies Software or FPGA; the nearby limitation explicitly excludes logical fault-tolerant synthesis.

`#run` is initially disabled until config loads. Replay controls `#play`, `#pause`, `#step` and `#scrub` are initially disabled until a successful explicit Run. `#speed` is a playback timer only; `#tick` counts circuit TICK segments, not syndrome rounds or FPGA cycles. `#circuit-diagram` is the primary SVG wire/gate timeline inside the keyboard-focusable `#diagram-scroll` region. `#diagram-notice` reports indexed versus used qubits and all rendering caps. `#gates` supports it in a collapsed active-operations disclosure. `#qubits` and separately headed `#detectors` are populated from the sampled circuit trace. `#result` is reserved for shot/source and final observable evidence, not inferred correction overlays.

`#status` has role=status and data-state idle/busy/ready/error. Circuit/graph/wire evidence details (`#circuit-evidence`, `#graph-evidence`, `#wire-evidence`) are closed by default. The page's final note separates sampled Pauli state and unweighted logical prediction from physical corrections and measured hardware timing. It accepts variable physical qubit counts without assuming a surface-code lattice.

The server maps `/` to this document, `/app.js` and `/style.css` to sibling assets, with no arbitrary file routing. Browser verification is documented in [test_runtime_web_ui](../../tests/test_runtime_web_ui.md).
