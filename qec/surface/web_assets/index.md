# `index.html` — replay page and DOM contract

The page is a static semantic shell served at `/` by `qec.surface.web`. It loads `/style.css` and deferred `/app.js` from the same origin; it has no inline executable script or external asset dependency. Open it through the server, not a `file:` URL, because replay needs same-origin API endpoints.

## Document structure

1. The header names the lab and exposes `#source` (initially “Connecting…”).
2. `.toolbar` contains the X/Y/Z `data-pauli` buttons with `aria-pressed`, the integer `#fault-tick`, `#example`, `#reset`, fixed circuit description and `#scenario`.
3. `.replay` contains `.transport`: `#back`, `#play`, `#step`, speed selector `#speed` and position output `#position`, followed by range input `#scrubber`. Initial values describe 22 physical ticks plus the host-overlay cursor; JavaScript sets maxima from the layout.
4. `#status` is a polite live region **above** the visualization, so loading, decoding and API/schema failures do not require opening Details.
5. `.workspace` contains the circuit section (`#tick-label`, `#operations`, dynamic `#lattice`, color legend) and detector section (dynamic `#timeline`, `#event-count`, live `#result`).
6. Collapsed `#evidence` explains provenance and contains `#technical` JSON plus nested collapsed circuit panels `#circuit` and `#corrected-circuit`.
7. `noscript` explains that JavaScript is required.

## Interaction contract

IDs and `data-pauli` are binding hooks for `app.js`, not decorative names. The script creates qubit buttons and detector cells dynamically; the HTML does not hardcode circuit connectivity. Startup controls are disabled until their corresponding state is available, with Play requiring a valid replay. Data-qubit buttons are injection controls, whereas check buttons are non-tabbable display elements. The script retains qubit focus across redraws.

The injection selector uses pressed state; previous/next and the scrubber have accessible labels. Status and logical result use polite live regions. Native `<details>` provides keyboard-operable evidence disclosure without custom handlers. Arrow/Space replay shortcuts intentionally avoid buttons, inputs, select controls and summaries so native interaction remains intact.

## Data and evidence boundaries

`GET /api/layout` provides operation lists, coordinates and detector availability; `POST /api/simulate` receives tick-tagged Pauli faults and returns trace/evidence. See `app.md` for exact consumed fields. The initial example is deliberate X on q10 at tick 8, not hidden random noise. Fault injection precedes the tick's operations.

The evidence paragraph must remain consistent with the implementation: cursor 22 is a host correction overlay, FPGA requests decode complete windows, and graph edges/representative Pauli replay are host-derived counterfactuals rather than physical feedback. Keep this explanation beside evidence even if the server source is “FPGA”.

## Verification (repository root)

```sh
node --test qec/tests/test_web_ui.cjs
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# Separate terminal; do not add --serial-port to the server:
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
```

Offline tests check required IDs, range/live-region hooks, initial disabled Play and transport/status ordering. The opt-in Chrome test checks the actual DOM, playback, errors and responsive overflow. Preserve displayed text, binding attributes and whitespace-sensitive inline content during readability-only formatting; no visual redesign is intended.
