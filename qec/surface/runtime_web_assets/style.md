# Runtime circuit lab styles

`style.css` supplies the dark, dependency-free responsive layout for [index.html](index.md). The main content is capped at 1100px with a flexible editor and wrapped control rows. Global border-box sizing, min-width:0, bounded inputs and wrapping evidence prevent long circuit/source text from widening the document. Evidence preformatted blocks wrap and scroll vertically within a maximum height.

At widths <=600px main padding shrinks, numeric labels become full-row controls and the editor height reduces. Buttons and inputs have a minimum 44px height. There are no fixed geometry/lattice assumptions. Qubit sampled Pauli badges use separate X/Y/Z colors and text labels, retaining meaning without color alone. Software/FPGA source, error status and busy status use separate foreground colors against the dark canvas.

SVG gates retain fixed-size legible labels rather than shrinking a large timeline to phone width. The diagram region owns horizontal scrolling and caps vertical height at 430px; Pauli chips cap their height separately. Active TICK background/stroke and inactive styling are distinct; sampled Pauli wire-label colors are independent of gate styling.

The Chromium regression measures document scrollWidth <= innerWidth at 1280, 820, 390 and 360 CSS pixels after real decoding and replay. Screenshots can be generated with RUNTIME_WEB_SCREENSHOTS_DIR; these check contrast and visual hierarchy in addition to numeric geometry. Mobile content naturally extends below the fold; it is not hidden or horizontally clipped.
