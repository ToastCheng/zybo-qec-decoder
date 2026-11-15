# `style.css` — layout, replay-state cascade and motion

This stylesheet is loaded by `index.html`. It has no imports, build step, network resources or decoder logic. `app.js` supplies state classes and inline coordinate properties; CSS only presents those states.

## Organization

- `:root` defines paper/ink/panel colors, amber error, coral detector flip, mint correction and local font stacks. Base rules normalize box sizing, controls, disabled state and visible keyboard focus.
- Header/main/toolbar rules establish the outer width, wrapping injection controls and full-width scenario text. Pressed Pauli buttons use `[aria-pressed="true"]`. Numbered `.workflow-step` sections separate configuration and explicit Run; `.settings` uses zero-minimum grid tracks, four columns on desktop and two below 600px. The supported-template selector and seed span two tracks (the whole row on mobile), leaving a single row of noise controls on desktop to keep the lattice prominent. Run uses a dark filled control and its completed summary wraps without widening the page.
- `.workspace` is a two-column `minmax(0, 1fr)` grid; each section has `min-width: 0` to permit shrinking. `.physical` draws the dividing border.
- `#lattice` is a square, positioned, isolated coordinate container. Its absolute SVG fills the square and ignores pointer events. JavaScript maps positions to percentages in the same 720-unit coordinate system. `.qubit` buttons use a centered transform and 44px square targets; data qubits are round, checks square. Gate labels (`em`) and correction tags (`small`) are positioned around the buttons.
- `.legend` uses colored pseudo-elements corresponding to replay state colors.
- `#timeline` has one 44px label column and four detector-time columns. `.time-header`, `.check-row` and `.no-detector` distinguish headings/check labels from absent detector locations. `.detector` cells contain ID and bit text.
- Transport, status, result, disclosures and `pre` rules follow. Evidence text scrolls inside bounded blocks instead of expanding the page.
- The 760px media query stacks workspace panels, changes the divider direction, and tightens spacing. The final reduced-motion query adds color transitions only when motion is permitted.

## State/data contract and precedence

JavaScript attaches `.active` for current gate targets, `.has-error` for nonidentity server frame terms, `.check-fired` for available detector flips, `.has-fix` for the host correction, and `.residual` for a nonidentity corrected result. Multiple classes can coexist. Their order is significant: amber error overrides blue active fill; coral check flips follow; mint correction follows; residual amber is last. Do not reorder same-specificity rules as a cosmetic cleanup.

Detector `data-available="false"` dims unmeasured cells; it is not equivalent to a measured zero. `.fired` is coral and `.cleared` subsequently overrides it with mint for the host counterfactual. The renderer, not CSS, decides availability and whether a result can be called cleared.

Exact fills exercised by browser tests are active blue `#adddf6`, error amber `#f4bd61`, detector coral `#e99086`, and correction mint `#bfe6cd`. Native focus outline and active-gate outline have different purposes. Preserve selector specificity, declaration order and values during comment/format changes.

## Motion and evidence limits

The 0.12-second transitions interpolate only background/border colors. Replay timing is JavaScript's timeout, not CSS animation or board time. Reduced-motion users still receive all ticks and detector availability changes without interpolation. A green correction cell depicts host-derived replay; it does not prove that a physical device applied a gate or cleared a measurement.

## Verification (repository root)

```sh
node --test qec/tests/test_web_ui.cjs
uv run --with stim --with pymatching python -m qec.surface.web --port 18766
# In another terminal (Chrome and Node 22+ required):
QEC_WEB_URL=http://127.0.0.1:18766 node --test qec/tests/test_web_browser.cjs
```

The real-browser test waits for color transitions and checks computed fills during Replay after explicit Run, errors, detector flips and host correction tags. A valid stabilizer residual may remain amber rather than sitewise identity. It asserts no horizontal overflow and Replay visibility at 1280, 820, 760, 600, 390 and 360px. It does not exhaust every breakpoint or establish hardware behavior. The offline suite checks HTML/helper contracts, not rendered CSS.
