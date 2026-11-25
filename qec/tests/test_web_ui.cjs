const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const app = path.join(__dirname, "../surface/web_assets/app.js");

/**
 * Check the fixed memory request dimensions, independently supplied rates, and
 * rejection of invalid noise or seed.
 */
test("run settings use the fixed hardware-compatible template and independent noise rates", () => {
  const { runSettings } = require(app);
  const faults = [{ tick: 8, qubit: 10, pauli: "X" }];
  const noise = {
    after_clifford_depolarization: 0.001,
    before_round_data_depolarization: 0.002,
    before_measure_flip_probability: 0.003,
    after_reset_flip_probability: 0.004,
  };
  assert.deepEqual(runSettings(noise, 20261107, faults), {
    circuit: "surface_code:rotated_memory_z",
    distance: 3,
    rounds: 3,
    noise,
    seed: 20261107,
    faults,
  });
  assert.throws(
    () => runSettings({ ...noise, after_clifford_depolarization: 0.76 }, 1, []),
    /0.*0.75/,
  );
  assert.throws(() => runSettings(noise, -1, []), /seed/i);
});

/**
 * Require actionable errors for incomplete layouts while accepting the current
 * schema unchanged.
 */
test("rejects stale server layouts with an actionable restart error", () => {
  const { validateLayout } = require(app);
  assert.throws(
    () => validateLayout({ data: [], checks: [], detectors: [] }),
    /restart.*server/i,
  );
  assert.throws(
    () => validateLayout({ ticks: [], data: [], checks: [], detectors: [] }),
    /restart.*server/i,
  );
  const layout = {
    ticks: [{ operations: [] }],
    data: [],
    checks: [],
    detectors: [],
    boundaries: [],
    rows: [],
  };
  assert.equal(validateLayout(layout), layout);
});

/**
 * Require one Pauli frame per physical tick before handing a result to the
 * renderer.
 */
test("rejects stale replay schema instead of breaking the render loop", () => {
  const { validateReplay } = require(app);
  assert.throws(
    () => validateReplay({ detector_indices: [] }, 2),
    /restart.*server/i,
  );
  assert.throws(
    () =>
      validateReplay({ detector_indices: [], trace: [{ pauli_frame: {} }] }, 2),
    /restart.*server/i,
  );
  const result = {
    detector_indices: [],
    trace: [{ pauli_frame: {} }, { pauli_frame: {} }],
  };
  assert.equal(validateReplay(result, 2), result);
});

/**
 * Check clamped, reversible playback and independent faults on the same qubit at
 * different ticks.
 */
test("arbitrary tick scrub, reversible stepping, and distinct multi-time faults", () => {
  const { LabState } = require(app);
  const s = new LabState(21);
  assert.equal(s.tick, 0);
  s.seek(8);
  s.toggle(10, "X");
  s.seek(16);
  s.toggle(10, "Z");
  assert.deepEqual(s.faults, [
    { tick: 8, qubit: 10, pauli: "X" },
    { tick: 16, qubit: 10, pauli: "Z" },
  ]);
  s.previous();
  assert.equal(s.tick, 15);
  s.next();
  assert.equal(s.tick, 16);
  s.seek(100);
  assert.equal(s.tick, 22);
  s.seek(-1);
  assert.equal(s.tick, 0);
  s.seek(8);
  s.toggle(10, "X");
  assert.deepEqual(s.faults, [{ tick: 16, qubit: 10, pauli: "Z" }]);
  s.reset();
  assert.equal(s.tick, 0);
  assert.deepEqual(s.faults, []);
});

/**
 * Check that fired detectors appear at their availability tick and disappear when
 * replay scrubs earlier.
 */
test("detectors stay unavailable before their measurement boundary, including backward scrub", () => {
  const { visibleDetectors } = require(app);
  const ds = [
    { id: 0, available_tick: 7 },
    { id: 1, available_tick: 14 },
  ];
  assert.deepEqual(visibleDetectors(ds, [0, 1], 6), []);
  assert.deepEqual(visibleDetectors(ds, [0, 1], 14), [0, 1]);
  assert.deepEqual(visibleDetectors(ds, [0, 1], 8), [0]);
});

/**
 * Check that Details contains only a run summary and that errors and replay
 * controls stay in their intended places.
 */
test("Details contains only the run summary, without explanatory dumps", () => {
  const html = fs.readFileSync(
    path.join(path.dirname(app), "index.html"),
    "utf8",
  );
  for (const id of [
    "lattice",
    "timeline",
    "scrubber",
    "back",
    "step",
    "play",
    "speed",
    "fault-tick",
    "reset",
    "result",
    "status",
  ]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.ok(html.includes('type="range"'));
  assert.ok(html.includes('aria-live="polite"'));
  assert.ok(!html.includes("See an error become"));
  assert.ok(!html.includes("<footer>"));
  assert.doesNotMatch(html, /id="technical"|id="source"|counterfactual/);
  assert.match(
    html,
    /<details id="evidence">\s*<summary>Details<\/summary>\s*<output id="run-summary"[^>]*><\/output>\s*<\/details>/,
  );
  assert.ok(
    html.indexOf('id="play"') > html.indexOf('id="control-dock"'),
    "Play belongs to the fixed bottom dock",
  );
  assert.ok(
    html.indexOf('id="status"') < html.indexOf('id="lattice"'),
    "load/API errors stay above the circuit",
  );
  assert.match(html, /id="play"[^>]*disabled/);
  assert.match(html, /id="configure-title">Configure<\/summary>/);
  assert.match(html, /Simulate and decode/);
  assert.match(html, /<h2[^>]*>Replay<\/h2>/);
  for (const id of [
    "run",
    "circuit-template",
    "seed",
    "after_clifford_depolarization",
    "before_round_data_depolarization",
    "before_measure_flip_probability",
    "after_reset_flip_probability",
    "run-summary",
  ]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.match(html, /id="play"[^>]*>▶/);
});
