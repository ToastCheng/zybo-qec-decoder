const { test } = require("node:test");
const assert = require("node:assert/strict");
const app = require("../surface/web_assets/app.js");

/**
 * Check initial control markup: collapsed configuration, accessible Play in the
 * dock, and no decoder source in the header.
 */
test("configuration and editor are collapsed and controls live in the bottom dock", () => {
  const html = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../surface/web_assets/index.html"),
    "utf8",
  );
  assert.doesNotMatch(
    html,
    /id="technical"|id="corrected-circuit"|counterfactual|representative Pauli/,
  );
  assert.match(html, /<details\s+id="configure"/);
  assert.match(html, /<summary id="configure-title">Configure<\/summary>/);
  assert.match(html, /id="control-dock"/);
  assert.match(html, /id="play"[^>]*aria-label="Play"[^>]*>▶<\/button>/);
  assert.ok(html.indexOf('id="advanced"') < html.indexOf('id="circuit-text"'));
  assert.doesNotMatch(
    html.slice(html.indexOf("<header>"), html.indexOf("</header>")),
    /id="source"/,
  );
});

/**
 * Build six disconnected supports and verify patch wrapping keeps every qubit in
 * bounds at several widths.
 */
test("preset patches wrap within the available width without losing qubits", () => {
  const layout = { data: [], checks: [] };
  for (let patch = 0; patch < 6; patch++) {
    const base = patch * 3;
    layout.data.push(
      { id: base, coords: [8 * patch + 1, 1] },
      { id: base + 1, coords: [8 * patch + 3, 1] },
    );
    layout.checks.push({
      id: base + 2,
      coords: [8 * patch + 2, 0],
      basis: "X",
      support: [base, base + 1],
    });
  }
  for (const width of [1100, 700, 328]) {
    const grid = app.latticeGrid(layout, width);
    assert.equal(grid.points.length, 18);
    assert.ok(grid.width <= width);
    assert.equal(grid.panels, 6);
    assert.ok(
      new Set(grid.points.map((q) => q.y)).size > 2,
      "patches wrap into rows",
    );
    for (const q of grid.points) {
      assert.ok(q.x >= 22 && q.x <= width - 22);
      assert.ok(q.y >= 22 && q.y <= grid.height - 22);
    }
  }
});

/** Require short section headings and no built-in example fault control. */
test("headings are concise and the example-fault control is absent", () => {
  const html = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../surface/web_assets/index.html"),
    "utf8",
  );
  assert.match(html, /id="configure-title">Configure<\/summary>/);
  assert.match(html, /id="run-title"[^>]*>Simulate and decode<\/h2>/);
  assert.match(html, /<h2[^>]*>Replay<\/h2>/);
  assert.doesNotMatch(html, /id="example"|Example fault/);
});

/**
 * Check matrix row and round labels and retain both detectors before revealing
 * their measured values.
 */
test("decoder matrix labels rows and rounds and retains every detector", () => {
  const layout = {
    rows: [
      { id: "2", label: "X2" },
      { id: "9", label: "Z9" },
    ],
    boundaries: [
      { id: 0, label: "r0", available_tick: 7 },
      { id: 1, label: "r1", available_tick: 7 },
    ],
    detectors: [
      { id: 0, row: "2", boundary: 0, available_tick: 7 },
      { id: 1, row: "9", boundary: 1, available_tick: 7 },
    ],
  };
  const before = app.decoderMatrix(layout, null, 0);
  assert.match(before, /r0/);
  assert.match(before, /r1/);
  assert.match(before, /X2/);
  assert.match(before, /Z9/);
  assert.equal((before.match(/data-detector=/g) || []).length, 2);
  assert.match(before, /data-available="false"/);
  const after = app.decoderMatrix(layout, { detector_indices: [1] }, 7);
  assert.match(after, /data-detector="1"[^>]*class="detector fired/);
});

/**
 * Check that a two-site boundary support yields an X-check face with finite
 * coordinates.
 */
test("stabilizer faces use actual supports, including boundary checks", () => {
  const grid = app.physicalGrid([
    { id: 0, coords: [1, 1] },
    { id: 1, coords: [3, 1] },
    { id: 2, coords: [2, 0], basis: "X", support: [0, 1] },
  ]);
  const markup = app.stabilizerFaces(
    [{ id: 2, basis: "X", support: [0, 1] }],
    grid.points,
  );
  assert.match(markup, /class="stabilizer-face basis-X"/);
  assert.match(markup, /data-check="2"/);
  assert.doesNotMatch(markup, /undefined|NaN/);
});
