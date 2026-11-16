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
if (typeof module !== "undefined")
  module.exports = {
    cycleSummary,
    circuitSettings,
    maskBit,
    productGroups,
    physicalGrid,
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
    $("play").textContent = "Replay";
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
      failure = `${e.message} Check settings and the server/FPGA connection, then press Run to retry.`;
    } finally {
      inFlight = false;
      pending = false;
      render();
    }
  }
  const position = (q) => ({
    x: (q.coords[0] + 0.6) * 100,
    y: (q.coords[1] + 0.6) * 100,
  });
  const combine = (a, b) =>
    !a ? b || "" : !b ? a : a === b ? "" : "XYZ".replace(a, "").replace(b, "");
  let diagramKey = "";
  function renderDiagram(custom, tick) {
    const logicalText = custom ? $("logical-text").value.trim() : "";
    const verified = Boolean(result && layout.mapping_verified);
    const key = JSON.stringify([
      layout,
      Boolean(experiment),
      logicalText,
      verified,
    ]);
    if (key !== diagramKey) {
      diagramKey = key;
      if (!custom) {
        $("diagram-title").textContent = "Logical memory";
        $("diagram-note").textContent =
          "Known surface-memory experiment · one encoded Z-memory wire. Logical and physical ticks are not a gate mapping.";
        $("circuit-diagram").innerHTML = circuitDiagram(
          [{ id: 0 }],
          [
            { id: 0, operations: [{ name: "R", targets: [0] }] },
            { id: 1, operations: [{ name: "Memory Z", targets: [0] }] },
            { id: 2, operations: [{ name: "M", targets: [0] }] },
          ],
          -1,
          true,
        );
      } else if (logicalText) {
        $("diagram-title").textContent = verified
          ? "Known encoded example"
          : "Logical circuit · as supplied";
        $("diagram-note").textContent = verified
          ? "Known encoded example · physical and logical inputs match the supplied encoding. Logical gate positions are not physical replay ticks."
          : "Logical circuit as supplied · mapping not verified. Logical gate positions are not physical replay ticks.";
        try {
          const supplied = suppliedDiagram(logicalText);
          $("circuit-diagram").innerHTML = circuitDiagram(
            supplied.qubits,
            supplied.ticks,
            -1,
            true,
          );
        } catch (error) {
          $("diagram-note").textContent +=
            ` ${error.message} Supplied text is shown below.`;
          const pre = document.createElement("pre");
          pre.textContent = logicalText;
          $("circuit-diagram").replaceChildren(pre);
        }
      } else {
        $("diagram-title").textContent = "Input circuit";
        $("diagram-note").textContent =
          "No logical-to-physical mapping supplied. These wires are the annotated physical input.";
        const ticks =
          experiment?.trace?.map((t) => ({
            id: t.tick,
            operations: t.diagram,
          })) || layout.ticks;
        $("circuit-diagram").innerHTML = circuitDiagram(
          layout.data,
          ticks,
          tick,
        );
      }
    }
    if (custom && !logicalText) {
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
    const operations = layout.ticks[tick].operations;
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
      : operations.map((op) => op.name).join(" · ");
    $("position").textContent = `${state.tick} / ${state.endTick}`;
    $("scrubber").value = state.tick;
    $("scrubber").disabled = !result || pending;
    $("back").disabled = !result || pending || state.tick === 0;
    $("step").disabled = !result || pending || state.tick > state.lastTick;
    $("play").disabled = pending || !result;
    const example = selectedExample();
    const unsupported = example?.decoder_compatible === false;
    $("circuit-warning").hidden = !example;
    $("circuit-warning").className = unsupported ? "failed" : "";
    $("circuit-warning").textContent = example
      ? [
          example.semantic_adaptation,
          example.noise_model || example.decoder_limitation,
        ]
          .filter(Boolean)
          .join(" ")
      : "";
    $("run").disabled = pending || inFlight || unsupported;
    $("run").textContent = pending ? "Running…" : "Run";
    document
      .querySelectorAll(
        "#configure input, #configure select, #configure button, #circuit-editor input, #circuit-editor textarea, #circuit-editor select, .toolbar input, .toolbar button",
      )
      .forEach((control) => {
        control.disabled = pending;
      });
    $("run-title").textContent =
      layout.source === "FPGA"
        ? "2 Simulate + FPGA decode"
        : "2 Simulate + software decode";
    $("run-summary").textContent = result
      ? `Completed · ${result.source} · seed ${result.settings?.seed ?? experiment?.seed ?? "not reported"} · prediction ${result.prediction} · observable ${result.observable} · cycles ${cycleSummary(result)}`
      : "";
    $("source").textContent = failure
      ? `${layout.source} · unavailable`
      : result?.source || layout.source;
    $("status").className = failure ? "failed" : "";
    $("status").textContent =
      failure ||
      (unsupported
        ? "Selected encoded circuit is not supported by the graph-only decoder. See the circuit limitation above."
        : "") ||
      (pending
        ? "Simulating + decoding…"
        : result
          ? "Ready to replay · no new decoder requests"
          : "Run to update · configure settings or select faults, then press Run");
    const custom = layout.kind === "circuit";
    const selectedCustom =
      $("circuit-template").value !== "surface_code:rotated_memory_z";
    const grid = custom ? physicalGrid(layout.data) : null;
    const pointById = new Map(grid?.points.map((q) => [q.id, q]) || []);
    $("lattice").classList.toggle("index-lattice", custom);
    $("lattice").style.width = custom ? `${grid.width}px` : "";
    $("lattice").style.height = custom ? `${grid.height}px` : "";
    $("grid-note").textContent = custom
      ? `${layout.data.length} used physical qubits · ${grid.label}`
      : "Surface-memory physical qubits · QUBIT_COORDS geometry";
    const active = new Set(operations.flatMap((op) => op.targets));
    const byId = new Map(
      [...layout.data, ...layout.checks].map((q) => [q.id, q]),
    );
    const links = (custom ? [] : operations)
      .filter((op) => op.name === "CX")
      .flatMap((op) => {
        const links = [];
        for (let i = 0; i < op.targets.length; i += 2) {
          const a = position(byId.get(op.targets[i])),
            b = position(byId.get(op.targets[i + 1]));
          links.push(`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`);
        }
        return links;
      });
    $("lattice").innerHTML =
      `<svg viewBox="0 0 720 720" aria-hidden="true">${corrected ? "" : links.join("")}</svg>`;
    for (const q of layoutCurrent ? [...layout.data, ...layout.checks] : []) {
      const data = !q.basis;
      const button = document.createElement("button");
      const fault = frame[q.id] || "",
        fix = fixes[q.id] || "";
      const residual = combine(fault, fix);
      const fired =
        !custom &&
        layout.detectors.some(
          (d) =>
            d.coords?.[0] === q.coords?.[0] &&
            d.coords?.[1] === q.coords?.[1] &&
            visible.includes(d.id),
        );
      button.className = `qubit ${data ? "data-qubit" : "check-qubit"} ${!corrected && active.has(q.id) ? "active" : ""} ${fault ? "has-error" : ""} ${fired ? "check-fired" : ""} ${fix ? "has-fix" : ""} ${corrected && residual ? "residual" : ""}`;
      button.dataset.qubit = q.id;
      const pos = custom ? pointById.get(q.id) : position(q);
      button.style.left = custom ? `${pos.x}px` : `${pos.x / 7.2}%`;
      button.style.top = custom ? `${pos.y}px` : `${pos.y / 7.2}%`;
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
    let html =
      "<span></span>" +
      [0, 1, 2, 3]
        .map((t) => `<span class="time-header">r${t}</span>`)
        .join("");
    for (const check of layout.checks) {
      html += `<span class="check-row">${check.basis}${check.id}</span>`;
      for (let t = 0; t < 4; t++) {
        const d = layout.detectors.find(
          (d) =>
            d.coords[0] === check.coords[0] &&
            d.coords[1] === check.coords[1] &&
            d.coords[2] === t,
        );
        if (!d) {
          html += '<span class="no-detector">—</span>';
          continue;
        }
        const available = result && d.available_tick <= tick;
        const bit = available ? Number(visible.includes(d.id)) : null;
        const replay =
          corrected && result?.residual_syndrome !== null
            ? maskBit(result.residual_syndrome, d.id)
            : null;
        html += `<div data-detector="${d.id}" data-available="${Boolean(available)}" class="detector ${bit ? "fired" : ""} ${bit && replay === 0 ? "cleared" : ""}" title="D${d.id} · tick ${d.available_tick}"><small>D${d.id}</small><b>${bit === null ? "·" : bit && replay !== null ? `${bit}→${replay}` : bit}</b></div>`;
      }
    }
    if (custom) {
      html = layout.detectors
        .map((d) => {
          const available = Boolean(result && d.available_tick <= tick);
          const bit = available ? Number(visible.includes(d.id)) : null;
          return `<div data-detector="${d.id}" data-available="${available}" class="detector ${bit ? "fired" : ""}"><small>D${d.id} · t${d.available_tick}</small><b>${bit ?? "·"}</b></div>`;
        })
        .join("");
    }
    $("timeline").classList.toggle("generic-detectors", custom);
    $("timeline").innerHTML = html;
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
    $("boundary-note").hidden = custom || !layoutCurrent;
    $("timeline").hidden = !layoutCurrent;
    $("operations").hidden = !layoutCurrent;
    if (!layoutCurrent) {
      $("grid-note").textContent =
        "Run to compile the selected circuit's physical layout, then click a qubit to inject.";
      $("tick-label").textContent = "Physical layout pending Run";
    }
    document
      .querySelectorAll(".toolbar button, .toolbar input")
      .forEach((c) => {
        c.disabled = pending || !layoutCurrent;
      });
    $("example").hidden = selectedCustom;
    $("scenario").replaceChildren();
    for (const fault of state.faults) {
      const item = document.createElement("li");
      item.textContent = `${!selectedCustom && fault.tick === 8 && fault.qubit === 10 && fault.pauli === "X" ? "Example · " : ""}${fault.pauli} on q${fault.qubit} at tick ${fault.tick}`;
      $("scenario").append(item);
    }
    if (!state.faults.length) {
      const item = document.createElement("li");
      item.textContent = "No faults · click a physical qubit to inject";
      $("scenario").append(item);
    }
    $("technical").textContent = result
      ? JSON.stringify(
          {
            source: result.source,
            hardware: result.hardware,
            reference_prediction: result.reference_prediction,
            syndrome: result.syndrome,
            observable: result.observable,
            prediction: result.prediction,
            host_frame: result.host_frame,
            edges_source: "Host reference",
            correction_edges: result.correction_edges,
            correction: result.correction,
            residual_syndrome: result.residual_syndrome,
            residual_observable: result.residual_observable,
            faults: state.faults,
          },
          null,
          2,
        )
      : "";
    $("circuit").textContent = result?.injected_circuit || "";
    $("corrected-circuit").textContent = result?.corrected_circuit || "";
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
    layout = memoryLayout;
    layoutCurrent = memory;
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
    $("play").textContent = "Pause";
    advance();
  };
  $("example").onclick = () => {
    if (pending || !state) return;
    state.reset();
    state.toggle(10, "X", 8);
    $("fault-tick").value = 8;
    invalidate();
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
      state.toggle(10, "X", 8);
      $("fault-tick").value = 8;
      $("scrubber").max = state.lastTick + 1;
      $("fault-tick").max = state.lastTick;
      render();
    })
    .catch((e) => {
      $("source").textContent = "Unavailable";
      $("status").className = "failed";
      $("status").textContent = e.message;
    });
}
