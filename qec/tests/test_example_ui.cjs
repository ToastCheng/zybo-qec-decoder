/**
 * Unit tests for the interactive Union-Find + Forest Peeling walkthrough at
 * /example (example.js and example.html).
 *
 * Runs purely in Node without a browser or web server.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const examplePath = path.join(__dirname, "../surface/web_assets/example.js");
const htmlPath = path.join(__dirname, "../surface/web_assets/example.html");
const example = require(examplePath);

test("boundary fault preset builds a 3-edge forest and peels off unused branches", () => {
  const { syndrome, truth } = example.syndromeFromFaults([1]);
  assert.equal(syndrome, 0b0010);
  assert.equal(truth, 1);

  const trace = example.buildTrace(syndrome);
  const forestStep = trace.find((s) => s.phaseClass === "phase-forest");
  assert.ok(forestStep, "expected a spanning-forest summary step");
  assert.deepEqual(forestStep.forest, [0, 2, 3]);

  const final = trace[trace.length - 1];
  assert.equal(final.phase, "Done");
  assert.equal(final.error, false);
  assert.deepEqual(final.selected, [3]);
  assert.deepEqual(final.discarded, [0, 2]);
  assert.equal(final.prediction, 1);
});

test("all four presets finish without error and match true Z_L", () => {
  for (const preset of example.PRESETS) {
    const { syndrome, truth } = example.syndromeFromFaults(preset.faults);
    const trace = example.buildTrace(syndrome);
    const final = trace[trace.length - 1];
    assert.equal(final.phase, "Done", preset.id);
    assert.equal(final.error, false, preset.id);
    assert.equal(final.prediction, truth, preset.id);
  }
});

test("all 16 syndromes terminate cleanly with valid correction parity", () => {
  for (let syndrome = 0; syndrome < 16; syndrome++) {
    const trace = example.buildTrace(syndrome);
    const final = trace[trace.length - 1];
    assert.equal(final.phase, "Done", `syndrome=${syndrome}`);
    assert.equal(final.error, false, `syndrome=${syndrome}`);
    assert.deepEqual(final.forest, [], `syndrome=${syndrome}`);
    assert.deepEqual(final.work.slice(0, 4), [0, 0, 0, 0], `syndrome=${syndrome}`);

    // Verify selected edges reproduce the exact input syndrome and prediction mask.
    let parity = 0;
    let obs = 0;
    for (const eid of final.selected) {
      const edge = example.EDGES[eid];
      parity ^= 1 << edge.a;
      if (edge.b < example.BOUNDARY) parity ^= 1 << edge.b;
      obs ^= edge.mask;
    }
    assert.equal(parity, syndrome, `syndrome=${syndrome}`);
    assert.equal(obs, final.prediction, `syndrome=${syndrome}`);
  }
});

test("example.html contains required controls and stays strict-CSP clean", () => {
  const html = fs.readFileSync(htmlPath, "utf8");
  for (const id of [
    "uf-graph",
    "preset-buttons",
    "uf-clear",
    "uf-phase-badge",
    "uf-narrative",
    "uf-vertex-rows",
    "uf-edge-rows",
    "uf-first",
    "uf-prev",
    "uf-play",
    "uf-next",
    "uf-last",
    "uf-scrubber",
    "uf-speed",
  ]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.doesNotMatch(html, /\sstyle="/i, "strict CSP forbids inline style attributes");
  assert.doesNotMatch(html, /<style\b/i, "strict CSP forbids inline style blocks");
  assert.doesNotMatch(html, /\son[a-z]+=/i, "strict CSP forbids inline event handlers");
});
