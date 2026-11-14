const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const app = path.join(__dirname, "../surface/web_assets/app.js");

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

test("minimal page exposes replay, fault time, speed and collapsed evidence", () => {
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
    "source",
    "evidence",
  ]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.ok(html.includes('type="range"'));
  assert.ok(html.includes('aria-live="polite"'));
  assert.ok(!html.includes("See an error become"));
  assert.ok(!html.includes("<footer>"));
  assert.ok(html.includes("Host correction"));
});
