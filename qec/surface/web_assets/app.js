"use strict";
class LabState {
  constructor(lastTick = 21, hostOverlay = true) {
    this.lastTick = lastTick;
    this.endTick = lastTick + Number(hostOverlay);
    this.reset();
  }
  reset() {
    this.faults = [];
    this.tick = 0;
  }
  seek(tick) {
    this.tick = Math.max(0, Math.min(this.endTick, Math.round(tick)));
  }
  next() {
    this.seek(this.tick + 1);
  }
  previous() {
    this.seek(this.tick - 1);
  }
  toggle(qubit, pauli, tick = Math.min(this.tick, this.lastTick)) {
    const i = this.faults.findIndex(
      (f) => f.tick === tick && f.qubit === qubit,
    );
    if (i >= 0) {
      const old = this.faults.splice(i, 1)[0];
      if (old.pauli === pauli) return;
    }
    this.faults.push({ tick, qubit, pauli });
  }
}
const visibleDetectors = (detectors, indices, tick) =>
  indices.filter(
    (i) => detectors.find((d) => d.id === i).available_tick <= tick,
  );
function validateLayout(data) {
  if (
    !Array.isArray(data.ticks) ||
    !data.ticks.length ||
    !data.ticks.every((t) => Array.isArray(t.operations)) ||
    !Array.isArray(data.data) ||
    !Array.isArray(data.checks) ||
    !Array.isArray(data.boundaries) ||
    !Array.isArray(data.rows) ||
    !Array.isArray(data.detectors) ||
    !data.detectors.every((d) => Number.isInteger(d.available_tick))
  ) {
    throw Error(
      "Incompatible replay API. Restart the QEC web server, then reload this page.",
    );
  }
  return data;
}
function validateReplay(data, tickCount) {
  if (
    !Array.isArray(data.detector_indices) ||
    !Array.isArray(data.trace) ||
    data.trace.length !== tickCount ||
    !data.trace.every((t) => t.pauli_frame && typeof t.pauli_frame === "object")
  ) {
    throw Error(
      "Incompatible replay API. Restart the QEC web server, then reload this page.",
    );
  }
  return data;
}
const noiseKeys = [
  "after_clifford_depolarization",
  "before_round_data_depolarization",
  "before_measure_flip_probability",
  "after_reset_flip_probability",
];
function runSettings(noise, seed, faults) {
  for (const key of noiseKeys) {
    if (!Number.isFinite(noise[key]) || noise[key] < 0 || noise[key] > 0.75)
      throw Error("Set each noise rate between 0 and 0.75.");
  }
  if (!Number.isSafeInteger(seed) || seed < 0)
    throw Error(
      "Choose a nonnegative integer seed (within JavaScript's safe integer range).",
    );
  return {
    circuit: "surface_code:rotated_memory_z",
    distance: 3,
    rounds: 3,
    noise: { ...noise },
    seed,
    faults: faults.map((fault) => ({ ...fault })),
  };
}
function circuitSettings(
  circuit,
  reference,
  seed,
  addedNoise,
  logicalCircuit = "",
  faults = [],
) {
  if (!circuit.trim()) throw Error("Enter an annotated Stim circuit.");
  if (!Number.isSafeInteger(seed) || seed < 0)
    throw Error("Choose a nonnegative safe integer seed.");
  if (!Number.isFinite(addedNoise) || addedNoise < 0 || addedNoise > 0.75)
    throw Error("Set added noise between 0 and 0.75.");
  return {
    circuit,
    reference: reference.trim() ? reference : null,
    seed,
    added_noise: addedNoise,
    ...(faults.length ? { faults: faults.map((fault) => ({ ...fault })) } : {}),
    ...(logicalCircuit.trim() ? { logical_circuit: logicalCircuit } : {}),
  };
}
function physicalGrid(qubits) {
  const coordinates =
    qubits.every(
      (q) =>
        q.coords?.length >= 2 && q.coords.slice(0, 2).every(Number.isFinite),
    ) &&
    new Set(qubits.map((q) => q.coords.slice(0, 2).join(","))).size ===
      qubits.length;
  const columns = Math.ceil(Math.sqrt(qubits.length));
  const minX = coordinates ? Math.min(...qubits.map((q) => q.coords[0])) : 0;
  const minY = coordinates ? Math.min(...qubits.map((q) => q.coords[1])) : 0;
  const points = qubits.map((q, i) => ({
    ...q,
    x: 40 + (coordinates ? q.coords[0] - minX : i % columns) * 64,
    y: 40 + (coordinates ? q.coords[1] - minY : Math.floor(i / columns)) * 64,
  }));
  return {
    points,
    label: coordinates
      ? "QUBIT_COORDS geometry"
      : "Index grid · no complete 2D geometry supplied",
    width: Math.max(160, ...points.map((q) => q.x + 40)),
    height: Math.max(120, ...points.map((q) => q.y + 40)),
  };
}
function latticeGrid(layout, availableWidth) {
  const qubits = [...layout.data, ...layout.checks];
  if (!layout.checks.length || !qubits.every((q) => q.coords?.length >= 2))
    return physicalGrid(qubits);
  // Extraction-check supports define patches; interpatch logical gates do not.
  const neighbors = new Map(qubits.map((q) => [q.id, new Set()]));
  for (const check of layout.checks) {
    for (const id of check.support || []) {
      neighbors.get(check.id).add(id);
      neighbors.get(id)?.add(check.id);
    }
  }
  const byId = new Map(qubits.map((q) => [q.id, q]));
  const remaining = new Set([...byId.keys()].sort((a, b) => a - b));
  const patches = [];
  while (remaining.size) {
    const pending = [remaining.values().next().value];
    const patch = [];
    while (pending.length) {
      const id = pending.pop();
      if (!remaining.delete(id)) continue;
      patch.push(byId.get(id));
      for (const other of neighbors.get(id))
        if (remaining.has(other)) pending.push(other);
    }
    patches.push(physicalGrid(patch));
  }
  const tileWidth =
    Math.ceil(Math.max(...patches.map((p) => p.width)) / 64) * 64;
  const tileHeight =
    Math.ceil(Math.max(...patches.map((p) => p.height)) / 64) * 64;
  const width = Math.max(1, availableWidth);
  const columns = Math.min(
    patches.length,
    Math.max(1, Math.floor(width / tileWidth)),
  );
  const scale = Math.min(1, width / tileWidth);
  const offset = (width - columns * tileWidth * scale) / 2;
  return {
    points: patches.flatMap((patch, i) =>
      patch.points.map((q) => ({
        ...q,
        x: offset + ((i % columns) * tileWidth + q.x) * scale,
        y: (Math.floor(i / columns) * tileHeight + q.y) * scale,
      })),
    ),
    width,
    height: Math.ceil(patches.length / columns) * tileHeight * scale,
    step: 64 * scale,
    offsetX: offset + 40 * scale,
    offsetY: 40 * scale,
    panels: patches.length,
    label: "Surface-code patches · QUBIT_COORDS geometry",
  };
}
function cycleSummary(result) {
  const cycles = result.hardware?.cycles ?? result.cycles ?? "N/A (software)";
  const count = result.hardware?.chunks?.length || 0;
  return count > 1
    ? `${cycles} (sum of ${count} core decodes; uploads excluded)`
    : String(cycles);
}
const maskBit = (mask, index) => Math.floor(mask / 2 ** index) % 2;
function productGroups(op) {
  if (op.kind === "pair") {
    const groups = [];
    for (let i = 0; i < op.targets.length; i += 2)
      groups.push(op.targets.slice(i, i + 2));
    return groups;
  }
  if (!["MPP", "SPP", "SPP_DAG"].includes(op.name))
    return [op.targets.filter((t) => t.qubit !== undefined)];
  const groups = [];
  let combine = false;
  for (const t of op.targets) {
    if (t.combiner) {
      combine = true;
      continue;
    }
    if (t.qubit === undefined) continue;
    if (!combine) groups.push([]);
    groups.at(-1).push(t);
    combine = false;
  }
  return groups;
}
const escapeMarkup = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
function circuitDiagram(qubits, ticks, selected, logical = false) {
  const row = new Map(qubits.map((q, i) => [q.id, 42 + i * 48]));
  const columns = [];
  for (const tick of ticks) {
    for (const op of tick.operations) {
      if (
        [
          "QUBIT_COORDS",
          "SHIFT_COORDS",
          "DETECTOR",
          "OBSERVABLE_INCLUDE",
        ].includes(op.name)
      )
        continue;
      const typed = {
        ...op,
        targets: op.targets.map((t) =>
          typeof t === "number" ? { qubit: t } : t,
        ),
      };
      if (
        !typed.kind &&
        ["CX", "CY", "CZ", "SWAP", "XCX", "YCX", "ISWAP"].includes(op.name)
      )
        typed.kind = "pair";
      for (const group of productGroups(typed))
        columns.push({ tick: tick.id, op: typed, group });
    }
  }
  const width = Math.max(320, columns.length * 76 + 100),
    height = Math.max(88, qubits.length * 48 + 28);
  let body = qubits
    .map(
      (q) =>
        `<g class="circuit-wire" data-qubit="${q.id}"><line x1="58" x2="${width - 12}" y1="${row.get(q.id)}" y2="${row.get(q.id)}"/><text x="8" y="${row.get(q.id) + 4}">${logical ? "L" : "q"}${q.id}</text></g>`,
    )
    .join("");
  for (const [i, { tick, op: typed, group }] of columns.entries()) {
    const op = typed;
    const x = 100 + i * 76;
    const targets = group.filter((t) => row.has(t.qubit));
    if (!targets.length) continue;
    const classical = group
      .filter((t) => t.record !== undefined || t.sweep !== undefined)
      .map((t) =>
        t.record !== undefined ? `rec[${t.record}]` : `sweep[${t.sweep}]`,
      )
      .join(",");
    body += `<g class="gate ${tick === selected ? "active" : ""}" data-gate="${escapeMarkup(op.name)}" data-tick="${tick}"><title>${escapeMarkup(op.text || op.name)}</title>`;
    {
      const ys = targets.map((t) => row.get(t.qubit));
      const gx = x;
      body += `<g class="${typed.kind === "pair" ? "pair-group" : "product-group"}">`;
      if (
        targets.length > 1 &&
        (typed.kind === "pair" || typed.kind === "product")
      )
        body += `<line x1="${gx}" x2="${gx}" y1="${Math.min(...ys)}" y2="${Math.max(...ys)}"/>`;
      for (const [j, t] of targets.entries()) {
        const y = row.get(t.qubit);
        if (op.name === "CX" && typed.kind === "pair" && !classical) {
          body +=
            j === 0
              ? `<circle class="control" cx="${gx}" cy="${y}" r="5"/>`
              : `<g class="target"><circle cx="${gx}" cy="${y}" r="12"/><path d="M${gx - 7},${y}h14 M${gx},${y - 7}v14"/></g>`;
        } else {
          body += `<rect x="${gx - 27}" y="${y - 13}" width="54" height="26" rx="3"/><text x="${gx}" y="${y + 4}" text-anchor="middle">${escapeMarkup(op.name + (t.pauli ? ":" + t.pauli : ""))}</text>`;
        }
      }
      if (classical)
        body += `<text x="${gx}" y="${Math.min(...ys) - 18}" text-anchor="middle">${escapeMarkup(classical)}</text>`;
      body += "</g>";
    }
    body += "</g>";
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" role="img" aria-label="${logical ? "Logical" : "Input"} circuit">${body}</svg>`;
}
function suppliedDiagram(text) {
  const lines = text
    .split("\n")
    .map((line) => line.split("#")[0].trim())
    .filter(Boolean);
  let cursor = 0,
    count = 0;
  function block(nested = false) {
    const out = [];
    while (cursor < lines.length) {
      const line = lines[cursor++];
      if (line === "}") {
        if (!nested) throw Error("Unexpected logical circuit brace.");
        return out;
      }
      const repeat = line.match(/^REPEAT\s+(\d+)\s*\{$/i);
      if (repeat) {
        const body = block(true),
          n = Number(repeat[1]);
        if (n * body.length + count > 10000)
          throw Error("Logical diagram is too large.");
        for (let i = 0; i < n; i++) out.push(...body);
        count += n * body.length;
      } else {
        if (++count > 10000) throw Error("Logical diagram is too large.");
        out.push(line);
      }
    }
    if (nested) throw Error("Unclosed logical circuit repeat.");
    return out;
  }
  const expanded = block(),
    ticks = [{ id: 0, operations: [] }],
    ids = new Set();
  for (const line of expanded) {
    if (line === "TICK") {
      ticks.push({ id: ticks.length, operations: [] });
      continue;
    }
    const match = line.match(/^([A-Z_][A-Z_0-9]*)(?:\([^)]*\))?(?:\s+(.*))?$/i);
    if (!match) throw Error("Cannot draw this logical circuit line.");
    const name = match[1].toUpperCase(),
      targets = [];
    for (const token of (match[2] || "").match(
      /rec\[-?\d+\]|sweep\[\d+\]|!?[XYZ]?\d+|\*/g,
    ) || []) {
      if (token === "*") targets.push({ combiner: true });
      else if (token.startsWith("rec"))
        targets.push({ record: Number(token.match(/-?\d+/)[0]) });
      else if (token.startsWith("sweep"))
        targets.push({ sweep: Number(token.match(/\d+/)[0]) });
      else {
        const qubit = Number(token.match(/\d+/)[0]);
        targets.push({
          qubit,
          ...(token.match(/[XYZ]/) ? { pauli: token.match(/[XYZ]/)[0] } : {}),
        });
        ids.add(qubit);
      }
    }
    ticks.at(-1).operations.push({ name, targets, text: line });
  }
  return {
    qubits: [...ids].sort((a, b) => a - b).map((id) => ({ id })),
    ticks,
  };
}
function stabilizerFaces(checks, points) {
  const byId = new Map(points.map((q) => [q.id, q]));
  return checks
    .map((check) => {
      const support = (check.support || [])
        .map((id) => byId.get(id))
        .filter(Boolean);
      if (support.length < 2) return "";
      // Boundary checks form triangles with their ancilla; bulk checks use four data sites.
      const vertices =
        support.length === 2 ? [...support, byId.get(check.id)] : support;
      if (vertices.some((q) => !q)) return "";
      const cx = vertices.reduce((sum, q) => sum + q.x, 0) / vertices.length;
      const cy = vertices.reduce((sum, q) => sum + q.y, 0) / vertices.length;
      vertices.sort(
        (a, b) =>
          Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx),
      );
      return `<polygon class="stabilizer-face basis-${check.basis}" data-check="${check.id}" points="${vertices.map((q) => `${q.x},${q.y}`).join(" ")}"/>`;
    })
    .join("");
}
function decoderMatrix(layout, result, tick, corrected = false) {
  const boundaries = layout.boundaries || [];
  const rows = layout.rows || [];
  const cells = new Map();
  for (const d of layout.detectors) {
    const key = `${d.row}:${d.boundary}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push(d);
  }
  let html =
    '<span class="matrix-corner">Check</span>' +
    boundaries
      .map(
        (b) =>
          `<span class="time-header" title="Tick ${b.available_tick}">${escapeMarkup(b.label)}</span>`,
      )
      .join("");
  for (const row of rows) {
    html += `<span class="check-row">${escapeMarkup(row.label)}</span>`;
    for (const boundary of boundaries) {
      const detectors = cells.get(`${row.id}:${boundary.id}`) || [];
      if (!detectors.length) {
        html += '<span class="no-detector">—</span>';
        continue;
      }
      html +=
        '<div class="detector-cell">' +
        detectors
          .map((d) => {
            const available = Boolean(result && d.available_tick <= tick);
            const bit = available
              ? Number(result.detector_indices.includes(d.id))
              : null;
            const residual =
              corrected && result?.residual_syndrome != null
                ? maskBit(result.residual_syndrome, d.id)
                : null;
            return `<div data-detector="${d.id}" data-available="${available}" class="detector ${bit ? "fired" : ""} ${bit && residual === 0 ? "cleared" : ""}" title="D${d.id} · tick ${d.available_tick}"><small>D${d.id}</small><b>${bit === null ? "·" : bit && residual !== null ? `${bit}→${residual}` : bit}</b></div>`;
          })
          .join("") +
        "</div>";
    }
  }
  return html;
}
if (typeof module !== "undefined")
  module.exports = {
    decoderMatrix,
    stabilizerFaces,
    cycleSummary,
    circuitSettings,
    maskBit,
    productGroups,
    physicalGrid,
    latticeGrid,
    circuitDiagram,
    suppliedDiagram,
    runSettings,
    LabState,
    visibleDetectors,
    validateLayout,
    validateReplay,
  };

if (typeof document !== "undefined") {
  const $ = (id) => document.getElementById(id);
  let layout,
    memoryLayout,
    layoutCurrent = true,
    experiment,
    state,
    result,
    pending = false,
    inFlight = false,
    failure = "",
    requestId = 0,
    timer = null,
    pauli = "X";
  async function api(path, body) {
    const response = await fetch(
      path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    const data = await response.json();
    if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
    return data;
  }
  function stop() {
    clearTimeout(timer);
    timer = null;
    $("play").textContent = "▶";
    $("play").setAttribute("aria-label", "Play");
    $("play").setAttribute("aria-pressed", "false");
    $("play").title = "Play";
  }
  function seek(tick) {
    state.seek(tick);
    $("fault-tick").value = Math.min(state.tick, state.lastTick);
    render();
  }
  function advance() {
    state.next();
    render();
    if (state.tick >= state.endTick) {
      stop();
      return;
    }
    timer = setTimeout(advance, 700 / Number($("speed").value));
  }
  function invalidate() {
    stop();
    ++requestId;
    pending = false;
    result = null;
    experiment = null;
    failure = "";
    state.seek(0);
    render();
  }
  function selectedExample() {
    return memoryLayout?.examples?.find(
      (e) => e.id === $("circuit-template").value,
    );
  }
  async function simulate() {
    if (
      !layout ||
      pending ||
      inFlight ||
      selectedExample()?.decoder_compatible === false
    )
      return;
    stop();
    const id = ++requestId;
    pending = true;
    inFlight = true;
    result = null;
    failure = "";
    render();
    try {
      const custom =
        $("circuit-template").value !== "surface_code:rotated_memory_z";
      const seed = $("seed").value === "" ? NaN : Number($("seed").value);
      const noise = Object.fromEntries(
        noiseKeys.map((key) => [
          key,
          $(key).value === "" ? NaN : Number($(key).value),
        ]),
      );
      const settings = custom
        ? circuitSettings(
            $("circuit-text").value,
            $("reference-text").value,
            seed,
            $("added-noise").value === ""
              ? NaN
              : Number($("added-noise").value),
            $("logical-text").value,
            state.faults,
          )
        : runSettings(noise, seed, state.faults);
      const data = await api(
        custom ? "/api/circuit-run" : "/api/run",
        settings,
      );
      if (id !== requestId) return;
      if (custom) {
        const nextLayout = validateLayout(data.layout);
        const nextResult = validateReplay(data.result, nextLayout.ticks.length);
        if (
          !Array.isArray(data.experiment?.trace) ||
          data.experiment.trace.length !== nextLayout.ticks.length ||
          !data.experiment.trace.every((t) => Array.isArray(t.diagram))
        )
          throw Error(
            "Missing typed circuit trace. Restart the QEC web server.",
          );
        layout = nextLayout;
        result = nextResult;
        experiment = data.experiment;
        const faults = state.faults;
        state = new LabState(layout.ticks.length - 1, false);
        state.faults = faults;
        layoutCurrent = true;
        $("fault-tick").max = state.lastTick;
        $("scrubber").max = state.endTick;
      } else result = validateReplay(data, layout.ticks.length);
      state.seek(0);
    } catch (e) {
      if (id !== requestId) return;
      failure = e.message;
    } finally {
      inFlight = false;
      pending = false;
      render();
    }
  }

  const combine = (a, b) =>
    !a ? b || "" : !b ? a : a === b ? "" : "XYZ".replace(a, "").replace(b, "");
  let diagramKey = "";
  function renderDiagram(custom, tick) {
    const logicalText = custom
      ? $("logical-text").value.trim()
      : layout.logical_circuit;
    const verified =
      !custom ||
      Boolean(
        layout.mapping_verified && logicalText === layout.logical_circuit,
      );
    const key = JSON.stringify([
      layout,
      Boolean(experiment),
      logicalText,
      verified,
    ]);
    $("diagram-title").textContent = logicalText
      ? "Logical circuit"
      : "Physical circuit";
    $("diagram-note").hidden = true;
    $("circuit-view").dataset.mapping = logicalText
      ? verified
        ? "verified"
        : "unverified"
      : "physical";
    $("diagram-title").title =
      logicalText && !verified
        ? "Supplied logical circuit; mapping unverified"
        : "";
    if (key !== diagramKey) {
      diagramKey = key;
      try {
        if (logicalText) {
          const supplied = suppliedDiagram(logicalText);
          $("circuit-diagram").innerHTML = circuitDiagram(
            supplied.qubits,
            supplied.ticks,
            -1,
            true,
          );
        } else {
          const ticks =
            experiment?.trace?.map((t) => ({
              id: t.tick,
              operations: t.diagram,
            })) || layout.ticks;
          $("circuit-diagram").innerHTML = circuitDiagram(
            [...layout.data, ...layout.checks],
            ticks,
            tick,
          );
        }
      } catch (error) {
        const pre = document.createElement("pre");
        pre.textContent = logicalText;
        $("circuit-diagram").replaceChildren(pre);
        $("diagram-title").title = error.message;
      }
    }
    if (!logicalText) {
      document
        .querySelectorAll("#circuit-diagram .gate")
        .forEach((g) =>
          g.classList.toggle("active", Number(g.dataset.tick) === tick),
        );
      if (timer)
        document
          .querySelector("#circuit-diagram .gate.active")
          ?.scrollIntoView({
            block: "nearest",
            inline: "nearest",
            behavior: "instant",
          });
    }
  }
  function render() {
    if (!layout) return;
    const focused = document.activeElement?.dataset.qubit;
    const corrected = state.tick > state.lastTick;
    const tick = Math.min(state.tick, state.lastTick);
    const operations = layout.ticks[tick].operations.filter(
      (op) =>
        ![
          "QUBIT_COORDS",
          "SHIFT_COORDS",
          "DETECTOR",
          "OBSERVABLE_INCLUDE",
        ].includes(op.name) &&
        !/^(?:[XYZ]_ERROR|DEPOLARIZE[12]|PAULI_CHANNEL_[12]|CORRELATED_ERROR|ELSE_CORRELATED_ERROR|E)$/.test(
          op.name,
        ),
    );
    const visible = result
      ? visibleDetectors(layout.detectors, result.detector_indices, tick)
      : [];
    const frame = result?.trace[tick].pauli_frame || {};
    const fixes = corrected ? result?.correction_frame || {} : {};
    $("tick-label").textContent = corrected
      ? "Host correction"
      : `Tick ${tick}`;
    $("operations").textContent = corrected
      ? "Pauli frame"
      : [...new Set(operations.map((op) => op.name))].join(" · ");
    $("position").textContent = `${state.tick} / ${state.endTick}`;
    $("scrubber").value = state.tick;
    $("scrubber").disabled = !result || pending;
    $("back").disabled = !result || pending || state.tick === 0;
    $("step").disabled = !result || pending || state.tick > state.lastTick;
    $("play").disabled = pending || !result;
    const example = selectedExample();
    const unsupported = example?.decoder_compatible === false;

    $("run").disabled = pending || inFlight || unsupported;
    $("run").textContent = pending ? "Running…" : "Simulate and decode";
    document
      .querySelectorAll(
        "#configure input, #configure select, #configure button, #circuit-editor input, #circuit-editor textarea, #circuit-editor select, .toolbar input, .toolbar button",
      )
      .forEach((control) => {
        control.disabled = pending;
      });
    $("run-title").textContent = "Simulate and decode";
    $("run-summary").textContent = result
      ? `Completed · ${result.source} · seed ${result.settings?.seed ?? experiment?.seed ?? "not reported"} · prediction ${result.prediction} · observable ${result.observable} · cycles ${cycleSummary(result)}`
      : "";

    $("status").className = failure ? "failed" : "";
    $("status").textContent =
      failure ||
      (unsupported ? "Unsupported circuit" : "") ||
      (pending ? "Simulating + decoding…" : result ? "Ready" : "");
    const custom = layout.kind === "circuit";
    const selectedCustom =
      $("circuit-template").value !== "surface_code:rotated_memory_z";
    $("physical-scroll").hidden = !layoutCurrent;
    const grid = latticeGrid(layout, $("physical-scroll").clientWidth || 328);
    const pointById = new Map(grid.points.map((q) => [q.id, q]));
    $("lattice").classList.add("index-lattice");
    $("lattice").style.width = `${grid.width}px`;
    $("lattice").style.height = `${grid.height}px`;
    $("physical-scroll").classList.toggle("patch-layout", Boolean(grid.panels));
    $("lattice").style.backgroundSize =
      `${grid.step || 64}px ${grid.step || 64}px`;
    $("lattice").style.backgroundPosition =
      `${grid.offsetX ?? 40}px ${grid.offsetY ?? 40}px`;
    $("grid-note").textContent = `${grid.points.length} physical qubits`;
    $("grid-note").title = grid.label;
    const active = new Set(operations.flatMap((op) => op.targets));

    const links = operations
      .filter((op) => op.name === "CX")
      .flatMap((op) => {
        const links = [];
        for (let i = 0; i < op.targets.length; i += 2) {
          const a = pointById.get(op.targets[i]),
            b = pointById.get(op.targets[i + 1]);
          if (!a || !b) continue;
          links.push(`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`);
        }
        return links;
      });
    $("lattice").innerHTML =
      `<svg viewBox="0 0 ${grid.width} ${grid.height}" aria-hidden="true">${stabilizerFaces(layout.checks, grid.points)}${corrected ? "" : links.join("")}</svg>`;
    for (const q of layoutCurrent ? [...layout.data, ...layout.checks] : []) {
      const data = !q.basis;
      const button = document.createElement("button");
      const fault = frame[q.id] || "",
        fix = fixes[q.id] || "";
      const residual = combine(fault, fix);
      const fired = layout.detectors.some(
        (d) =>
          d.coords?.[0] === q.coords?.[0] &&
          d.coords?.[1] === q.coords?.[1] &&
          visible.includes(d.id),
      );
      button.className = `qubit ${data ? "data-qubit" : `check-qubit basis-${q.basis}`} ${!corrected && active.has(q.id) ? "active" : ""} ${fault ? "has-error" : ""} ${fired ? "check-fired" : ""} ${fix ? "has-fix" : ""} ${corrected && residual ? "residual" : ""}`;
      button.dataset.qubit = q.id;
      const pos = pointById.get(q.id);
      button.style.left = `${pos.x}px`;
      button.style.top = `${pos.y}px`;
      button.setAttribute(
        "aria-label",
        data
          ? `Physical qubit ${q.id}, ${fault || "I"}${fix ? ", host correction " + fix : ""}${`. Inject ${pauli} at tick ${$("fault-tick").value}`}`
          : `${q.basis} check ${q.id}${fired ? ", detector flip" : ""}`,
      );
      const gates = corrected
        ? []
        : operations
            .filter((op) => op.targets.includes(q.id))
            .map((op) => op.name);
      button.innerHTML = `<span>${data ? "q" : q.basis}${q.id}</span><b>${corrected ? residual || (data ? "I" : "·") : fault || (fired ? "1" : "·")}</b>${gates.length ? `<em>${gates.join("/")}</em>` : ""}${fix ? `<small>+${fix}</small>` : ""}`;
      if (data) {
        button.disabled = pending;
        const selected = state.faults.some(
          (f) => f.qubit === q.id && f.tick === Number($("fault-tick").value),
        );
        button.setAttribute("aria-pressed", String(selected));
        button.onclick = () => {
          if (pending) return;
          const faultTick = Number($("fault-tick").value);
          if (
            !Number.isInteger(faultTick) ||
            faultTick < 0 ||
            faultTick > state.lastTick
          ) {
            failure = "Choose a valid fault tick";
            render();
            return;
          }
          state.toggle(q.id, pauli, faultTick);
          invalidate();
        };
      } else {
        button.tabIndex = -1;
        button.setAttribute("aria-disabled", "true");
      }
      $("lattice").append(button);
    }
    if (focused)
      document
        .querySelector(`[data-qubit="${focused}"]`)
        ?.focus({ preventScroll: true });
    $("timeline").style.gridTemplateColumns =
      `max-content repeat(${layout.boundaries?.length || 1}, minmax(48px, 1fr))`;
    $("timeline").innerHTML = decoderMatrix(layout, result, tick, corrected);
    $("event-count").textContent = `${visible.length} flips`;
    $("result").textContent =
      custom && result
        ? `prediction ${result.prediction} · observable ${result.observable} · ${result.logical_success ? "match" : "mismatch"}`
        : corrected && result
          ? `${result.logical_success ? "Z preserved" : "Logical failure"} · frame ${result.host_frame}${result.correction === null ? " · no representative" : ""}`
          : "";
    $("result").className =
      corrected && result
        ? result.logical_success
          ? "success"
          : "failed"
        : "";
    $("physical-scroll").hidden = !layoutCurrent;
    $("boundary-note").hidden = true;
    $("timeline").hidden = !layoutCurrent;
    $("operations").hidden = !layoutCurrent;
    if (!layoutCurrent) {
      $("grid-note").textContent = "";
      $("tick-label").textContent = "Physical layout";
    }
    document
      .querySelectorAll(".toolbar button, .toolbar input")
      .forEach((c) => {
        c.disabled = pending || !layoutCurrent;
      });

    $("scenario").replaceChildren();
    for (const fault of state.faults) {
      const item = document.createElement("li");
      item.textContent = `${fault.pauli} on q${fault.qubit} at tick ${fault.tick}`;
      $("scenario").append(item);
    }
    if (!state.faults.length) {
      const item = document.createElement("li");
      item.textContent = "No faults";
      $("scenario").append(item);
    }

    renderDiagram(selectedCustom, tick);
    if (!layoutCurrent && !$("logical-text").value.trim()) {
      $("circuit-diagram").replaceChildren();
      $("diagram-note").textContent =
        "Run to compile and display the input circuit.";
    }
    for (const key of noiseKeys) $(key).disabled = pending || selectedCustom;
    $("added-noise").disabled = pending || !selectedCustom;
  }
  document.querySelectorAll("[data-pauli]").forEach(
    (b) =>
      (b.onclick = () => {
        pauli = b.dataset.pauli;
        document
          .querySelectorAll("[data-pauli]")
          .forEach((other) =>
            other.setAttribute("aria-pressed", String(other === b)),
          );
        render();
      }),
  );
  $("run").onclick = simulate;
  $("circuit-template").onchange = () => {
    if (!state) return;
    const choice = $("circuit-template").value;
    const memory = choice === "surface_code:rotated_memory_z";
    const example = memoryLayout.examples?.find((e) => e.id === choice);
    if (memory || example) {
      $("circuit-text").value = memory ? memoryLayout.circuit : example.circuit;
      $("logical-text").value = memory ? "" : example.logical_circuit || "";
      $("reference-text").value = "";
    } else {
      $("reference-text").value = "";
      $("logical-text").value = "";
    }
    layout = memory ? memoryLayout : example?.layout || memoryLayout;
    layoutCurrent = memory || Boolean(example?.layout);
    state = new LabState(layout.ticks.length - 1, memory);
    $("fault-tick").value = 0;
    $("scrubber").max = state.endTick;
    $("fault-tick").max = state.lastTick;
    diagramKey = "";
    invalidate();
  };
  document
    .querySelectorAll(
      ".settings input, #circuit-editor input, #circuit-editor textarea",
    )
    .forEach((control) => {
      control.oninput = () => {
        if (!state) return;
        if (control.id === "circuit-text") {
          if ($("circuit-template").value === "surface_code:rotated_memory_z")
            $("reference-text").value = memoryLayout.reference_circuit || "";
          $("circuit-template").value = "custom";
          layoutCurrent = false;
          state.faults = [];
        }
        invalidate();
      };
      control.onchange = control.oninput;
    });
  $("back").onclick = () => {
    if (!result || pending) return;
    stop();
    seek(state.tick - 1);
  };
  $("step").onclick = () => {
    if (!result || pending) return;
    stop();
    seek(state.tick + 1);
  };
  $("scrubber").oninput = () => {
    if (!result || pending) return;
    stop();
    seek(Number($("scrubber").value));
  };
  $("fault-tick").oninput = () => render();
  $("play").onclick = () => {
    if (!result || pending) return;
    if (timer) {
      stop();
      return;
    }
    if (state.tick >= state.endTick) seek(0);
    $("play").textContent = "⏸";
    $("play").setAttribute("aria-label", "Pause");
    $("play").setAttribute("aria-pressed", "true");
    $("play").title = "Pause";
    advance();
  };

  $("reset").onclick = () => {
    if (pending || !state) return;
    state.reset();
    $("fault-tick").value = 0;
    invalidate();
  };
  document.addEventListener("keydown", (e) => {
    if (
      e.ctrlKey ||
      e.metaKey ||
      e.altKey ||
      (e.target instanceof Element &&
        e.target.closest("input,select,textarea,button,summary"))
    )
      return;
    if (!state || !result || pending) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      stop();
      seek(state.tick + (e.key === "ArrowLeft" ? -1 : 1));
    }
    if (e.key === " ") {
      e.preventDefault();
      $("play").click();
    }
  });
  let latticeWidth = 0;
  new ResizeObserver(([entry]) => {
    document.documentElement.style.setProperty(
      "--dock-height",
      `${entry.target.getBoundingClientRect().height}px`,
    );
  }).observe($("control-dock"));
  new ResizeObserver(([entry]) => {
    const width = entry.contentRect.width;
    if (width > 0 && Math.abs(width - latticeWidth) > 1) {
      latticeWidth = width;
      if (layout && state) render();
    }
  }).observe($("physical-scroll"));
  api("/api/layout")
    .then((data) => {
      layout = memoryLayout = validateLayout(data);
      $("circuit-text").value = data.circuit || "";
      $("reference-text").value = data.reference_circuit || "";
      for (const example of data.examples || []) {
        if (
          example.id === "surface_code:rotated_memory_z" ||
          example.id === "memory"
        )
          continue;
        const option = document.createElement("option");
        option.value = example.id;
        option.textContent = example.label;
        $("circuit-template").insertBefore(
          option,
          $("circuit-template").lastElementChild,
        );
      }
      state = new LabState(data.ticks.length - 1);
      $("fault-tick").value = 0;
      $("scrubber").max = state.lastTick + 1;
      $("fault-tick").max = state.lastTick;
      render();
    })
    .catch((e) => {
      $("status").className = "failed";
      $("status").textContent = e.message;
    });
}
