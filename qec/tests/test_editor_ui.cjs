/**
 * Unit tests for custom circuit editor controls, request builders, and SVG
 * diagram helpers in qec/surface/web_assets/app.js and index.html.
 *
 * Runs purely in Node without a browser or web server.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const app = require("../surface/web_assets/app.js");

// Verify index.html keeps circuit selection and the collapsed Advanced editor separate from noise inputs.
test("circuit dropdown and Advanced editor stay separate from noise parameters", () => {
  const html = fs.readFileSync(
    path.join(__dirname, "../surface/web_assets/index.html"),
    "utf8",
  );
  assert.match(html, /<section\s+id="circuit-editor"/);
  assert.ok(
    html.indexOf('id="circuit-template"') < html.indexOf('id="circuit-text"'),
  );
  assert.ok(
    html.indexOf('id="circuit-text"') < html.indexOf('class="settings"'),
  );
  assert.ok(html.indexOf('id="added-noise"') > html.indexOf('id="configure"'));
  assert.match(html, /<details id="advanced">/);
  assert.match(html, /<ul id="scenario"/);
  assert.ok(
    html.indexOf('class="toolbar"') > html.indexOf('id="physical-scroll"'),
  );
  assert.match(html, />Decoder bit<\/h2>/);
  assert.doesNotMatch(html, /circuit-warning|Measurement boundaries/);
  for (const id of ["circuit-text", "reference-text", "added-noise"])
    assert.ok(html.includes(`id="${id}"`));
  assert.match(html, /value="custom">Custom Clifford circuit/);
  assert.doesNotMatch(html, /Supported circuit/);
});

// Verify circuitSettings keeps Stim text intact, converts blank references to null, and rejects invalid inputs.
test("custom circuit settings preserve annotated Stim and explicit nullable reference", () => {
  const text = "R 0\nTICK\nM 0\nDETECTOR rec[-1]\n";
  assert.deepEqual(app.circuitSettings(text, "", 42, 0.002), {
    circuit: text,
    reference: null,
    seed: 42,
    added_noise: 0.002,
  });
  assert.equal(app.circuitSettings(text, text, 1, 0).reference, text);
  assert.throws(() => app.circuitSettings("", "", 1, 0), /circuit/i);
  assert.throws(() => app.circuitSettings(text, "", NaN, 0), /seed/i);
  assert.throws(() => app.circuitSettings(text, "", 1, 1), /0.*0.75/);
});

// Verify multi-chunk FPGA cycle totals are labeled separately from single-decode and zero counts.
test("chunked hardware cycles are labeled as summed core cycles, excluding uploads", () => {
  assert.equal(
    app.cycleSummary({ hardware: { cycles: 123, chunks: [{}, {}] } }),
    "123 (sum of 2 core decodes; uploads excluded)",
  );
  assert.equal(
    app.cycleSummary({ hardware: { cycles: 42, chunks: [{}] } }),
    "42",
  );
  assert.equal(app.cycleSummary({ cycles: 0 }), "0");
});

// Verify circuitSettings clones fault entries instead of sharing references with caller state.
test("custom circuit settings copy injected faults without mutating caller state", () => {
  const faults = [{ tick: 1, qubit: 0, pauli: "Y" }];
  const settings = app.circuitSettings("R 0\nTICK\nM 0", "", 4, 0, "", faults);
  assert.deepEqual(settings.faults, faults);
  assert.notEqual(settings.faults[0], faults[0]);
});

// Verify hostOverlay=false stops replay at the final physical tick, unlike the memory-code default.
test("generic replay ends at the last physical tick without a fabricated correction", () => {
  const state = new app.LabState(2, false);
  state.seek(100);
  assert.equal(state.tick, 2);
  assert.equal(state.endTick, 2);
  assert.equal(new app.LabState(21).endTick, 22);
});

// Verify pair gates keep classical feedback records and MPP products keep Pauli bases per group.
test("typed product and pair targets retain grouping, bases and feedback records", () => {
  assert.deepEqual(
    app.productGroups({
      kind: "pair",
      name: "CX",
      targets: [{ record: -1 }, { qubit: 4 }],
    }),
    [[{ record: -1 }, { qubit: 4 }]],
  );
  assert.deepEqual(
    app.productGroups({
      name: "MPP",
      targets: [
        { qubit: 0, pauli: "X" },
        { combiner: true },
        { qubit: 1, pauli: "Z" },
        { qubit: 2, pauli: "Y" },
      ],
    }),
    [
      [
        { qubit: 0, pauli: "X" },
        { qubit: 1, pauli: "Z" },
      ],
      [{ qubit: 2, pauli: "Y" }],
    ],
  );
});

// Verify physicalGrid honors complete 2D coordinates and falls back to a full 1024-qubit index grid.
test("all physical qubits keep their actual geometry or an explicit index grid", () => {
  const dense = Array.from({ length: 1024 }, (_, id) => ({ id }));
  const grid = app.physicalGrid(dense);
  assert.equal(grid.points.length, 1024);
  assert.equal(new Set(grid.points.map((q) => `${q.x},${q.y}`)).size, 1024);
  assert.match(grid.label, /Index grid/);
  assert.equal(grid.points.at(-1).id, 1023);
  const coords = app.physicalGrid([
    { id: 4, coords: [-2, 5] },
    { id: 9, coords: [8, 15] },
  ]);
  assert.match(coords.label, /QUBIT_COORDS/);
  assert.equal(
    coords.points[1].x - coords.points[0].x,
    coords.points[1].y - coords.points[0].y,
  );
  assert.match(
    app.physicalGrid([{ id: 4, coords: [1, 1] }, { id: 8 }]).label,
    /Index grid/,
  );
});

// Verify circuit-view HTML IDs and SVG wire rendering for multi-pair CX gates, feedback, and 1024 wires.
test("circuit view accompanies the physical grid without inventing logical metadata", () => {
  const html = fs.readFileSync(
    path.join(__dirname, "../surface/web_assets/index.html"),
    "utf8",
  );
  for (const id of [
    "circuit-view",
    "circuit-diagram",
    "diagram-note",
    "logical-text",
    "physical-scroll",
    "grid-note",
  ])
    assert.ok(html.includes(`id="${id}"`), id);
  assert.equal(
    app.circuitSettings("R 0", "", 4, 0, "H 0").logical_circuit,
    "H 0",
  );
  const text = app.circuitDiagram(
    [{ id: 0 }, { id: 5 }],
    [
      {
        id: 0,
        operations: [
          { name: "H", targets: [0] },
          { name: "CX", targets: [0, 5] },
        ],
      },
    ],
    0,
  );
  assert.equal((text.match(/class="circuit-wire"/g) || []).length, 2);
  assert.match(text, /data-gate="CX"/);
  assert.match(text, /class="control"/);
  const pairs = app.circuitDiagram(
    [{ id: 0 }, { id: 1 }],
    [{ id: 0, operations: [{ name: "CX", targets: [0, 1, 1, 0] }] }],
    0,
  );
  const controls = [...pairs.matchAll(/class="control" cx="(\d+)"/g)].map((m) =>
    Number(m[1]),
  );
  assert.ok(
    controls[1] - controls[0] >= 60,
    "successive pairs need separate gate columns",
  );
  const feedback = app.circuitDiagram(
    [{ id: 4 }],
    [
      {
        id: 0,
        operations: [
          { name: "CX", kind: "pair", targets: [{ record: -1 }, { qubit: 4 }] },
        ],
      },
    ],
    0,
  );
  assert.doesNotMatch(feedback, /class="control"/);
  assert.match(feedback, /rec\[-1\]/);
  const large = app.circuitDiagram(
    Array.from({ length: 1024 }, (_, id) => ({ id })),
    [{ id: 0, operations: [] }],
    0,
  );
  assert.equal((large.match(/class="circuit-wire"/g) || []).length, 1024);
});

// Verify suppliedDiagram expands REPEAT blocks for display and rejects oversized output.
test("supplied logical text keeps gates and explicit repeat structure", () => {
  const parsed = app.suppliedDiagram(
    "R 0 1\nREPEAT 2 {\nH 0\nCX 0 1\nTICK\n}\nM 0 1",
  );
  assert.deepEqual(
    parsed.qubits.map((q) => q.id),
    [0, 1],
  );
  assert.equal(
    parsed.ticks.flatMap((t) => t.operations).filter((op) => op.name === "H")
      .length,
    2,
  );
  assert.throws(() => app.suppliedDiagram("REPEAT 999999 {\nH 0\n}"), /large/);
});

// Verify maskBit reads bit 31 accurately without signed 32-bit shift truncation.
test("unsigned detector bit 31 is read without signed mask truncation", () => {
  assert.equal(app.maskBit(2147483648, 31), 1);
  assert.equal(app.maskBit(2147483648, 0), 0);
});
