const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const app = path.join(__dirname, "../surface/web_assets/app.js");

test("lab state transitions preserve injected Paulis and reset completely", () => {
  assert.ok(fs.existsSync(app), "browser application is missing");
  const { LabState } = require(app);
  const s = new LabState();
  assert.equal(s.stage, 0);
  s.toggle("10", "X");
  assert.equal(s.stage, 1);
  assert.deepEqual(s.errors, { 10: "X" });
  s.next();
  assert.equal(s.stage, 2);
  s.next();
  assert.equal(s.stage, 3);
  s.next();
  assert.equal(s.stage, 3);
  s.toggle("10", "Z");
  assert.equal(s.stage, 1);
  assert.deepEqual(s.errors, { 10: "Z" });
  s.toggle("10", "Z");
  assert.deepEqual(s.errors, {});
  s.toggle("1", "Y");
  s.reset();
  assert.equal(s.stage, 0);
  assert.deepEqual(s.errors, {});
});

test("page exposes semantic controls and local assets", () => {
  const html = fs.readFileSync(
    path.join(path.dirname(app), "index.html"),
    "utf8",
  );
  for (const id of [
    "lattice",
    "timeline",
    "step",
    "run",
    "reset",
    "result",
    "status",
  ]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.ok(html.includes('aria-live="polite"'));
  assert.ok(html.includes("app.js"));
  assert.ok(html.includes("style.css"));
});
