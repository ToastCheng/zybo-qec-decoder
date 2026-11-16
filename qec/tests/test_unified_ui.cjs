const { test } = require("node:test");
const assert = require("node:assert/strict");
const app = require("../surface/web_assets/app.js");

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
