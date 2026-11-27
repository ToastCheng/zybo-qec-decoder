/**
 * Interactive Union-Find + Forest Peeling walkthrough on the single-slice
 * distance-3 rotated Z-memory decoding graph (4 Z detectors, 7 edges, B = 4).
 *
 * The trace builder mirrors qec/surface/decoder.py bit-for-bit: edges are
 * scanned in sorted input order, boundary B wins merges (otherwise the lower
 * root index), and forest peeling removes the lowest-index degree-1 detector
 * leaf via its lowest-index incident forest edge.
 */

const NUM_DETECTORS = 4;
const BOUNDARY = 4;

// Sorted (a, b, mask) edges matching qec/surface/graph.py on the t=0 Z slice.
const EDGES = [
  { id: 0, a: 0, b: 1, mask: 0, kind: "space", qubits: [8] },
  { id: 1, a: 0, b: 4, mask: 0, kind: "bottom", qubits: [15] },
  { id: 2, a: 1, b: 2, mask: 0, kind: "space", qubits: [10] },
  { id: 3, a: 1, b: 4, mask: 1, kind: "top", qubits: [1, 3] },
  { id: 4, a: 2, b: 3, mask: 0, kind: "space", qubits: [12] },
  { id: 5, a: 2, b: 4, mask: 0, kind: "bottom", qubits: [17, 19] },
  { id: 6, a: 3, b: 4, mask: 1, kind: "top", qubits: [5] },
];

// Physical 3x3 rotated surface-code data qubits (Stim coordinates).
const DATA_QUBITS = [
  { id: 1, x: 1, y: 1, detectors: [1], onZL: true },
  { id: 3, x: 3, y: 1, detectors: [1], onZL: true },
  { id: 5, x: 5, y: 1, detectors: [3], onZL: true },
  { id: 8, x: 1, y: 3, detectors: [0, 1], onZL: false },
  { id: 10, x: 3, y: 3, detectors: [1, 2], onZL: false },
  { id: 12, x: 5, y: 3, detectors: [2, 3], onZL: false },
  { id: 15, x: 1, y: 5, detectors: [0], onZL: false },
  { id: 17, x: 3, y: 5, detectors: [2], onZL: false },
  { id: 19, x: 5, y: 5, detectors: [2], onZL: false },
];

const DETECTORS = [
  { id: 0, x: 0, y: 4 },
  { id: 1, x: 2, y: 2 },
  { id: 2, x: 4, y: 4 },
  { id: 3, x: 6, y: 2 },
];

const PRESETS = [
  {
    id: "boundary",
    label: "Boundary fault (q1 → D1)",
    faults: [1],
  },
  {
    id: "bulk",
    label: "Bulk fault (q10 → D1, D2)",
    faults: [10],
  },
  {
    id: "two-bulk",
    label: "Two faults (q8, q10 → D0, D2)",
    faults: [8, 10],
  },
  {
    id: "corners",
    label: "Two trees (q15, q5 → D0, D3)",
    faults: [15, 5],
  },
];

function vertexName(v) {
  return v === BOUNDARY ? "B" : `D${v}`;
}

function syndromeFromFaults(faultIds) {
  let syndrome = 0;
  let truth = 0;
  const faultSet = new Set(faultIds);
  for (const q of DATA_QUBITS) {
    if (!faultSet.has(q.id)) continue;
    for (const d of q.detectors) {
      syndrome ^= 1 << d;
    }
    if (q.onZL) truth ^= 1;
  }
  return { syndrome, truth };
}

function formatSyndromeBits(syndrome) {
  let s = "";
  for (let i = NUM_DETECTORS - 1; i >= 0; i--) {
    s += (syndrome >> i) & 1;
  }
  return s;
}

/**
 * Run exact ordered unweighted Union-Find + forest peeling and capture every
 * meaningful step for visualization.
 */
function buildTrace(syndrome) {
  if (!Number.isInteger(syndrome) || syndrome < 0 || syndrome >= 1 << NUM_DETECTORS) {
    throw new Error("syndrome out of range for 4-detector graph");
  }

  const n = NUM_DETECTORS;
  const labels = Array.from({ length: n + 1 }, (_, i) => i);
  const parity = Array.from({ length: n }, (_, i) => (syndrome >> i) & 1).concat([0]);
  const growth = new Array(EDGES.length).fill(0);
  const halfFrom = EDGES.map(() => ({ a: false, b: false }));
  const forest = new Set();
  const degree = new Array(n + 1).fill(0);
  const selected = [];
  const discarded = [];
  const work = Array.from({ length: n }, (_, i) => (syndrome >> i) & 1).concat([0]);
  let prediction = 0;

  const steps = [];
  function snapshot(meta) {
    steps.push({
      phase: meta.phase,
      phaseClass: meta.phaseClass,
      title: meta.title,
      narrative: meta.narrative,
      sweep: meta.sweep ?? 0,
      activeEdge: meta.activeEdge ?? null,
      activeLeaf: meta.activeLeaf ?? null,
      peelDecision: meta.peelDecision ?? null,
      labels: labels.slice(),
      parity: parity.slice(),
      growth: growth.slice(),
      halfFrom: halfFrom.map((h) => ({ a: h.a, b: h.b })),
      forest: Array.from(forest).sort((x, y) => x - y),
      degree: degree.slice(),
      work: work.slice(),
      selected: selected.slice(),
      discarded: discarded.slice(),
      prediction,
      error: Boolean(meta.error),
    });
  }

  const fired = [];
  for (let i = 0; i < n; i++) {
    if ((syndrome >> i) & 1) fired.push(`D${i}`);
  }

  snapshot({
    phase: "Init",
    phaseClass: "phase-init",
    title: "Initialize clusters",
    narrative:
      fired.length === 0
        ? "No detectors fired (syndrome 0000). Zero-syndrome fast path returns prediction 0 immediately."
        : `Defects at ${fired.join(", ")}. Every detector starts in its own cluster; odd clusters will grow outward in edge order.`,
  });

  if (syndrome === 0) {
    snapshot({
      phase: "Done",
      phaseClass: "phase-done",
      title: "Zero-syndrome fast path",
      narrative: "All detector bits are 0, so no growth or peeling runs. Predicted observable flip L0 = 0.",
    });
    return steps;
  }

  // Phase 1: ordered half-edge union-find growth
  let converged = false;
  for (let sweep = 1; sweep <= 2 * (n + 1); sweep++) {
    if (!parity.slice(0, n).some((p) => p !== 0)) {
      converged = true;
      break;
    }
    for (let i = 0; i < EDGES.length; i++) {
      const { a, b, mask } = EDGES[i];
      const ra = labels[a];
      const rb = labels[b];
      const growA = ra !== n && parity[ra] !== 0;
      const growB = rb !== n && parity[rb] !== 0;
      const active = (growA ? 1 : 0) + (growB ? 1 : 0);
      if (ra === rb || active === 0) continue;

      const prevGrowth = growth[i];
      growth[i] = Math.min(2, growth[i] + active);
      if (growA) halfFrom[i].a = true;
      if (growB) halfFrom[i].b = true;

      if (growth[i] < 2) {
        const grower = growA ? vertexName(a) : vertexName(b);
        snapshot({
          phase: `Grow · S${sweep}`,
          phaseClass: "phase-grow",
          title: `Grow e${i} (${vertexName(a)}–${vertexName(b)})`,
          narrative: `Sweep ${sweep}: ${grower}'s cluster is odd, so edge e${i} grows from ${prevGrowth}/2 to 1/2.`,
          sweep,
          activeEdge: i,
        });
        continue;
      }

      const winner = ra === n || rb === n ? n : Math.min(ra, rb);
      const loser = winner === ra ? rb : ra;
      parity[winner] = parity[ra] ^ parity[rb];
      parity[loser] = 0;
      for (let v = 0; v <= n; v++) {
        if (labels[v] === loser) labels[v] = winner;
      }
      forest.add(i);
      degree[a] += 1;
      degree[b] += 1;

      const how =
        active === 2
          ? `both ${vertexName(a)} and ${vertexName(b)} are odd (+2)`
          : `${growA ? vertexName(a) : vertexName(b)} is odd (${prevGrowth}/2 → 2/2)`;
      const outcome =
        winner === n
          ? "merges into boundary B (stops growing)"
          : parity[winner] === 0
            ? `merges into even cluster ${vertexName(winner)} (neutralized)`
            : `merges into odd cluster ${vertexName(winner)} (still odd)`;
      const maskNote = mask ? " [mask=1]" : "";

      snapshot({
        phase: `Grow · S${sweep}`,
        phaseClass: "phase-grow",
        title: `Merge on e${i} (${vertexName(a)}–${vertexName(b)})`,
        narrative: `Sweep ${sweep}: on e${i}${maskNote}, ${how}. Edge reaches 2/2, ${outcome}, and joins the spanning forest.`,
        sweep,
        activeEdge: i,
      });
    }
    if (!parity.slice(0, n).some((p) => p !== 0)) {
      converged = true;
      break;
    }
  }

  if (!converged) {
    snapshot({
      phase: "Error",
      phaseClass: "phase-peel",
      title: "Decode error",
      narrative: "Growth did not neutralize all odd clusters.",
      error: true,
    });
    return steps;
  }

  const leavesNow = [];
  for (let i = 0; i < n; i++) {
    if (degree[i] === 1) leavesNow.push(`D${i}`);
  }
  snapshot({
    phase: "Forest",
    phaseClass: "phase-forest",
    title: "Spanning forest ready",
    narrative: `All odd clusters are paired or anchored to B. Forest edges: {${Array.from(forest)
      .sort((x, y) => x - y)
      .map((e) => `e${e}`)
      .join(", ")}}. Current degree-1 detector leaves: ${leavesNow.join(", ")}. Copy syndrome bits into working bits and start peeling from the lowest-index leaf.`,
  });

  // Phase 2: peel forest from lowest-index degree-1 detector leaf
  while (forest.size > 0) {
    let leaf = -1;
    for (let i = 0; i < n; i++) {
      if (degree[i] === 1) {
        leaf = i;
        break;
      }
    }
    if (leaf === -1) {
      snapshot({
        phase: "Error",
        phaseClass: "phase-peel",
        title: "Peeling stalled",
        narrative: "No degree-1 detector leaf found in forest.",
        error: true,
      });
      return steps;
    }

    const sortedForest = Array.from(forest).sort((x, y) => x - y);
    const e = sortedForest.find((idx) => EDGES[idx].a === leaf || EDGES[idx].b === leaf);
    const { a, b, mask } = EDGES[e];
    const other = a === leaf ? b : a;
    const leafWork = work[leaf];

    if (leafWork === 1) {
      work[other] ^= 1;
      prediction ^= mask;
      selected.push(e);
    } else {
      discarded.push(e);
    }
    work[leaf] = 0;
    degree[a] -= 1;
    degree[b] -= 1;
    forest.delete(e);

    const decision = leafWork === 1 ? "select" : "discard";
    const narrative =
      leafWork === 1
        ? `Pick lowest-index leaf ${vertexName(leaf)} (work = 1). Select e${e} (${vertexName(a)}–${vertexName(b)}, mask = ${mask}), flip ${vertexName(other)}'s work bit to ${work[other]}, and XOR mask into prediction → L0 = ${prediction}.`
        : `Pick lowest-index leaf ${vertexName(leaf)} (work = 0). Discard unused forest edge e${e} (${vertexName(a)}–${vertexName(b)}) without changing L0 = ${prediction}.`;

    snapshot({
      phase: "Peel",
      phaseClass: "phase-peel",
      title: `${leafWork === 1 ? "Select" : "Discard"} e${e} from leaf ${vertexName(leaf)}`,
      narrative,
      activeEdge: e,
      activeLeaf: leaf,
      peelDecision: decision,
    });
  }

  const leftover = work.slice(0, n).some((w) => w !== 0);
  snapshot({
    phase: leftover ? "Error" : "Done",
    phaseClass: leftover ? "phase-peel" : "phase-done",
    title: leftover ? "Verification failed" : "Decoding complete",
    narrative: leftover
      ? "Nonzero detector work bit remained after peeling."
      : `Peeling finished with all detector work bits = 0. Selected edges: ${
          selected.length ? selected.map((e) => `e${e}`).join(", ") : "none"
        } → predicted observable flip L0 = ${prediction}.`,
    error: leftover,
  });

  return steps;
}

// ---- SVG rendering & UI binding (browser only) ----

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, text = null) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  if (text !== null) el.textContent = text;
  return el;
}

// Map Stim grid coordinates (x in 0..6, y in 0..6) into SVG 640x520 space.
function toSvg(x, y) {
  return {
    x: 80 + x * 80,
    y: 78 + (y - 0.5) * 68,
  };
}

function edgeEndpoints(edge) {
  const pa = toSvg(DETECTORS[edge.a].x, DETECTORS[edge.a].y);
  if (edge.b !== BOUNDARY) {
    return {
      x1: pa.x,
      y1: pa.y,
      x2: toSvg(DETECTORS[edge.b].x, DETECTORS[edge.b].y).x,
      y2: toSvg(DETECTORS[edge.b].x, DETECTORS[edge.b].y).y,
    };
  }
  const by = edge.kind === "top" ? 42 : 478;
  return { x1: pa.x, y1: pa.y, x2: pa.x, y2: by };
}

function edgePillPosition(edge, ep) {
  if (edge.b === BOUNDARY) {
    return {
      x: ep.x1 + 36,
      y: edge.kind === "top" ? 72 : 446,
    };
  }
  const mx = (ep.x1 + ep.x2) / 2;
  const my = (ep.y1 + ep.y2) / 2;
  // Offset perpendicular to diagonal so the middle data qubit stays unobstructed
  const offsets = {
    0: { dx: -34, dy: -32 },
    2: { dx: 36, dy: -30 },
    4: { dx: 36, dy: 30 },
  };
  const off = offsets[edge.id] || { dx: 0, dy: -26 };
  return { x: mx + off.dx, y: my + off.dy };
}

function edgeStateLabel(edge, step) {
  const inPeel =
    step.phaseClass === "phase-forest" ||
    step.phaseClass === "phase-peel" ||
    step.phaseClass === "phase-done";
  if (step.selected.includes(edge.id)) return "selected";
  if (step.discarded.includes(edge.id)) return "discarded";
  if (step.forest.includes(edge.id)) return "forest";
  if (step.growth[edge.id] === 1) return inPeel ? "unused" : "growing";
  return "idle";
}

function initPage() {
  const svg = document.getElementById("uf-graph");
  const presetBox = document.getElementById("preset-buttons");
  const clearBtn = document.getElementById("uf-clear");
  const syndromeTag = document.getElementById("uf-syndrome-tag");
  const phaseBadge = document.getElementById("uf-phase-badge");
  const stepTitle = document.getElementById("uf-step-title");
  const stepCounter = document.getElementById("uf-step-counter");
  const narrativeEl = document.getElementById("uf-narrative");
  const forestListEl = document.getElementById("uf-forest-list");
  const selectedListEl = document.getElementById("uf-selected-list");
  const predictionEl = document.getElementById("uf-prediction");
  const truthEl = document.getElementById("uf-truth");
  const vertexCol4 = document.getElementById("uf-vertex-col4");
  const vertexRows = document.getElementById("uf-vertex-rows");
  const edgeRows = document.getElementById("uf-edge-rows");

  const firstBtn = document.getElementById("uf-first");
  const prevBtn = document.getElementById("uf-prev");
  const playBtn = document.getElementById("uf-play");
  const nextBtn = document.getElementById("uf-next");
  const lastBtn = document.getElementById("uf-last");
  const scrubber = document.getElementById("uf-scrubber");
  const dockPos = document.getElementById("uf-dock-pos");
  const speedSel = document.getElementById("uf-speed");

  let faults = new Set(PRESETS[0].faults);
  let customSyndrome = null; // non-null when user flips detectors directly
  let activePresetId = PRESETS[0].id;
  let trace = [];
  let stepIndex = 0;
  let timer = null;

  function currentSyndromeAndTruth() {
    if (customSyndrome !== null) {
      return { syndrome: customSyndrome, truth: null };
    }
    return syndromeFromFaults(faults);
  }

  function stopPlayback() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    playBtn.textContent = "▶";
    playBtn.setAttribute("aria-label", "Play");
  }

  function startPlayback() {
    if (stepIndex >= trace.length - 1) {
      stepIndex = 0;
    }
    stopPlayback();
    playBtn.textContent = "⏸";
    playBtn.setAttribute("aria-label", "Pause");
    const delayMs = Number(speedSel.value) || 850;
    timer = setInterval(() => {
      if (stepIndex < trace.length - 1) {
        stepIndex += 1;
        render();
      } else {
        stopPlayback();
      }
    }, delayMs);
    render();
  }

  function recompute(resetToStep = 0) {
    stopPlayback();
    const { syndrome } = currentSyndromeAndTruth();
    trace = buildTrace(syndrome);
    stepIndex = Math.max(0, Math.min(resetToStep, trace.length - 1));
    scrubber.max = String(Math.max(0, trace.length - 1));
    render();
  }

  function renderPresets() {
    presetBox.innerHTML = "";
    for (const preset of PRESETS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "preset-btn" + (activePresetId === preset.id ? " active" : "");
      btn.textContent = preset.label;
      btn.dataset.preset = preset.id;
      btn.addEventListener("click", () => {
        faults = new Set(preset.faults);
        customSyndrome = null;
        activePresetId = preset.id;
        recompute(0);
      });
      presetBox.appendChild(btn);
    }
  }

  function renderSvg(step, syndrome) {
    svg.innerHTML = "";
    const inPeel =
      step.phaseClass === "phase-forest" ||
      step.phaseClass === "phase-peel" ||
      step.phaseClass === "phase-done";

    // 1. Stabilizer plaquettes (X then Z)
    const xPolys = [
      [[3, 1], [5, 1], [5, 3], [3, 3]],
      [[1, 3], [3, 3], [3, 5], [1, 5]],
      [[1, 1], [3, 1], [2, 0.25]],
      [[3, 5], [5, 5], [4, 5.75]],
    ];
    const zPolys = [
      [[1, 1], [3, 1], [3, 3], [1, 3]],
      [[3, 3], [5, 3], [5, 5], [3, 5]],
      [[1, 3], [1, 5], [0, 4]],
      [[5, 1], [5, 3], [6, 2]],
    ];

    for (const pts of xPolys) {
      const str = pts.map(([x, y]) => {
        const p = toSvg(x, y);
        return `${p.x},${p.y}`;
      }).join(" ");
      svg.appendChild(svgEl("polygon", { points: str, class: "svg-plaquette-x" }));
    }
    for (const pts of zPolys) {
      const str = pts.map(([x, y]) => {
        const p = toSvg(x, y);
        return `${p.x},${p.y}`;
      }).join(" ");
      svg.appendChild(svgEl("polygon", { points: str, class: "svg-plaquette-z" }));
    }
    for (const [cx, cy] of [[4, 2], [2, 4]]) {
      const p = toSvg(cx, cy);
      svg.appendChild(svgEl("text", { x: p.x, y: p.y, class: "svg-x-label" }, "X"));
    }

    // 2. Logical Z_L highlight band on top data row (q1, q3, q5)
    const zlStart = toSvg(0.65, 0.62);
    const zlEnd = toSvg(5.35, 1.38);
    svg.appendChild(
      svgEl("rect", {
        x: zlStart.x,
        y: zlStart.y,
        width: zlEnd.x - zlStart.x,
        height: zlEnd.y - zlStart.y,
        rx: 12,
        class: "svg-zl-band",
      }),
    );
    svg.appendChild(
      svgEl("text", { x: zlStart.x - 10, y: (zlStart.y + zlEnd.y) / 2, class: "svg-zl-label" }, "Z_L (L0)"),
    );

    // 3. Top and bottom Boundary B strips
    svg.appendChild(svgEl("rect", { x: 84, y: 12, width: 516, height: 30, rx: 6, class: "svg-boundary-top" }));
    svg.appendChild(
      svgEl("text", { x: 342, y: 27, class: "svg-boundary-text-top" }, "Boundary B = 4  (top — mask = 1, flips L0)"),
    );
    svg.appendChild(svgEl("rect", { x: 40, y: 478, width: 472, height: 30, rx: 6, class: "svg-boundary-bot" }));
    svg.appendChild(
      svgEl("text", { x: 276, y: 493, class: "svg-boundary-text-bot" }, "Boundary B = 4  (bottom — mask = 0)"),
    );

    // 4. Decoding graph edges (e0..e6)
    for (const edge of EDGES) {
      const ep = edgeEndpoints(edge);
      const state = edgeStateLabel(edge, step);
      const isActive = step.activeEdge === edge.id;

      if (isActive) {
        svg.appendChild(
          svgEl("line", {
            x1: ep.x1,
            y1: ep.y1,
            x2: ep.x2,
            y2: ep.y2,
            class: "edge-halo",
          }),
        );
      }

      if (state === "growing" || state === "unused") {
        // Dashed background + half-edge from growing end(s)
        svg.appendChild(
          svgEl("line", {
            x1: ep.x1,
            y1: ep.y1,
            x2: ep.x2,
            y2: ep.y2,
            class: "edge-base edge-growing-bg",
          }),
        );
        const mx = (ep.x1 + ep.x2) / 2;
        const my = (ep.y1 + ep.y2) / 2;
        const hf = step.halfFrom[edge.id];
        const halfCls = state === "growing" ? "edge-half" : "edge-half-unused";
        if (hf.a) {
          svg.appendChild(
            svgEl("line", { x1: ep.x1, y1: ep.y1, x2: mx, y2: my, class: halfCls }),
          );
        }
        if (hf.b) {
          svg.appendChild(
            svgEl("line", { x1: ep.x2, y1: ep.y2, x2: mx, y2: my, class: halfCls }),
          );
        }
      } else {
        const cls =
          state === "selected"
            ? "edge-base edge-selected"
            : state === "forest"
              ? "edge-base edge-forest"
              : state === "discarded"
                ? "edge-base edge-discarded"
                : "edge-base edge-idle";
        svg.appendChild(
          svgEl("line", {
            x1: ep.x1,
            y1: ep.y1,
            x2: ep.x2,
            y2: ep.y2,
            class: cls,
            "data-edge": edge.id,
            "data-state": state,
          }),
        );
      }

      // Edge pill label
      const pill = edgePillPosition(edge, ep);
      const maskTag = edge.mask ? "·L0" : "";
      const suffix =
        state === "selected"
          ? " ✓"
          : state === "discarded"
            ? " ×"
            : state === "growing"
              ? " ½"
              : "";
      const labelText = `e${edge.id}${maskTag}${suffix}`;
      const pillW = Math.max(40, labelText.length * 7.2 + 12);
      const pillClass =
        state === "selected"
          ? "pill-selected"
          : state === "forest"
            ? "pill-forest"
            : state === "growing"
              ? "pill-grow"
              : state === "discarded" || state === "unused"
                ? "pill-discarded"
                : "";
      svg.appendChild(
        svgEl("rect", {
          x: pill.x - pillW / 2,
          y: pill.y - 10,
          width: pillW,
          height: 20,
          rx: 5,
          class: `edge-pill-bg ${pillClass}`,
        }),
      );
      svg.appendChild(
        svgEl("text", { x: pill.x, y: pill.y, class: `edge-pill-text ${pillClass}` }, labelText),
      );
    }

    // 5. Interactive data qubits (9 qubits)
    for (const q of DATA_QUBITS) {
      const p = toSvg(q.x, q.y);
      const hasFault = customSyndrome === null && faults.has(q.id);
      const g = svgEl("g", {
        class: `data-node${q.onZL ? " on-zl" : ""}${hasFault ? " has-fault" : ""}`,
        role: "button",
        tabindex: "0",
        "aria-label": `Data qubit q${q.id}${hasFault ? " (X fault active)" : ""}`,
        "aria-pressed": hasFault ? "true" : "false",
        "data-qubit": q.id,
      });
      g.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 22, class: "data-hit" }));
      g.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 15, class: "data-circle" }));
      g.appendChild(svgEl("text", { x: p.x, y: p.y, class: "data-label" }, hasFault ? "X" : `q${q.id}`));
      const toggleQubit = () => {
        if (customSyndrome !== null) {
          customSyndrome = null;
          faults = new Set([q.id]);
        } else if (faults.has(q.id)) {
          faults.delete(q.id);
        } else {
          faults.add(q.id);
        }
        activePresetId = null;
        recompute(0);
      };
      g.addEventListener("click", toggleQubit);
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggleQubit();
        }
      });
      svg.appendChild(g);
    }

    // 6. Interactive detector vertices (D0..D3)
    for (const det of DETECTORS) {
      const p = toSvg(det.x, det.y);
      const root = step.labels[det.id];
      const isDefect = Boolean((syndrome >> det.id) & 1);
      const isLeaf = step.activeLeaf === det.id;
      const workBit = step.work[det.id];

      let nodeClass = "det-node";
      if (inPeel) {
        nodeClass += workBit ? " is-peel-one" : " is-peel-zero";
      } else if (isDefect) {
        nodeClass += " is-defect";
      }

      const g = svgEl("g", {
        class: nodeClass,
        role: "button",
        tabindex: "0",
        "aria-label": `Detector D${det.id}, syndrome ${isDefect ? 1 : 0}`,
        "aria-pressed": isDefect ? "true" : "false",
        "data-detector": det.id,
      });
      g.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 28, class: "det-hit" }));
      if (isLeaf) {
        g.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 28, class: "det-leaf-ring" }));
      }
      g.appendChild(
        svgEl("circle", { cx: p.x, cy: p.y, r: 23, class: `det-cluster-ring cluster-${root}` }),
      );
      g.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 19, class: "det-circle" }));
      g.appendChild(svgEl("text", { x: p.x, y: p.y, class: "det-label" }, `D${det.id}`));

      // Compact live status badge beside each detector
      let badgeText = "";
      let badgeClass = "";
      if (inPeel) {
        badgeText = `w=${workBit} d=${step.degree[det.id]}`;
        badgeClass = workBit ? "badge-work1" : "badge-work0";
      } else if (root === BOUNDARY) {
        badgeText = "→ B";
        badgeClass = "badge-boundary";
      } else {
        badgeText = step.parity[root] ? "odd" : "even";
        badgeClass = step.parity[root] ? "badge-odd" : "";
      }

      const bx = p.x;
      const by = det.y === 2 ? p.y + 34 : p.y - 34;
      const bw = Math.max(40, badgeText.length * 6.8 + 10);
      g.appendChild(
        svgEl("rect", {
          x: bx - bw / 2,
          y: by - 9,
          width: bw,
          height: 18,
          rx: 4,
          class: `det-badge-bg ${badgeClass}`,
        }),
      );
      g.appendChild(svgEl("text", { x: bx, y: by, class: "det-badge-text" }, badgeText));

      const toggleDetector = () => {
        const cur = currentSyndromeAndTruth().syndrome;
        customSyndrome = cur ^ (1 << det.id);
        faults = new Set();
        activePresetId = null;
        recompute(0);
      };
      g.addEventListener("click", toggleDetector);
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggleDetector();
        }
      });
      svg.appendChild(g);
    }
  }

  function renderTables(step, syndrome) {
    const inPeel =
      step.phaseClass === "phase-forest" ||
      step.phaseClass === "phase-peel" ||
      step.phaseClass === "phase-done";
    vertexCol4.textContent = inPeel ? "Deg / Work" : "Parity";

    vertexRows.innerHTML = "";
    for (let v = 0; v <= NUM_DETECTORS; v++) {
      const tr = document.createElement("tr");
      if (step.activeLeaf === v) tr.className = "row-active";
      const root = step.labels[v];
      const bit = v === BOUNDARY ? "—" : String((syndrome >> v) & 1);
      const col4 =
        v === BOUNDARY
          ? inPeel
            ? `deg ${step.degree[v]}`
            : "absorbs"
          : inPeel
            ? `deg ${step.degree[v]} · w=${step.work[v]}`
            : root === BOUNDARY
              ? "at B"
              : step.parity[root]
                ? "odd (1)"
                : "even (0)";

      const td0 = document.createElement("td");
      td0.textContent = vertexName(v);
      const td1 = document.createElement("td");
      td1.textContent = bit;
      const td2 = document.createElement("td");
      const dot = document.createElement("span");
      dot.className = `cluster-dot dot-${root}`;
      td2.appendChild(dot);
      td2.appendChild(document.createTextNode(vertexName(root)));
      const td3 = document.createElement("td");
      td3.textContent = col4;
      tr.append(td0, td1, td2, td3);
      vertexRows.appendChild(tr);
    }

    edgeRows.innerHTML = "";
    for (const edge of EDGES) {
      const state = edgeStateLabel(edge, step);
      const tr = document.createElement("tr");
      if (step.activeEdge === edge.id) tr.className = "row-active";
      else if (state === "selected") tr.className = "row-selected";
      else if (state === "forest") tr.className = "row-forest";
      else if (state === "discarded") tr.className = "row-discarded";

      const cells = [
        `e${edge.id}`,
        `${vertexName(edge.a)}–${vertexName(edge.b)}`,
        String(edge.mask),
        `${step.growth[edge.id]}/2`,
        state,
      ];
      for (const text of cells) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      }
      edgeRows.appendChild(tr);
    }
  }

  function render() {
    const step = trace[stepIndex];
    const { syndrome, truth } = currentSyndromeAndTruth();

    renderPresets();
    syndromeTag.textContent = `syndrome ${formatSyndromeBits(syndrome)} (D3..D0)`;
    phaseBadge.textContent = step.phase;
    phaseBadge.className = `phase-badge ${step.phaseClass}`;
    stepTitle.textContent = step.title;
    stepCounter.textContent = `Step ${stepIndex} / ${trace.length - 1}`;
    narrativeEl.textContent = step.narrative;

    forestListEl.textContent = step.forest.length
      ? step.forest.map((e) => `e${e}`).join(", ")
      : "none";
    selectedListEl.textContent = step.selected.length
      ? step.selected.map((e) => `e${e}`).join(", ")
      : "none";
    predictionEl.textContent = String(step.prediction);

    truthEl.className = "summary-value";
    if (truth === null) {
      truthEl.textContent = "custom";
    } else if (step.phaseClass === "phase-done") {
      const ok = step.prediction === truth;
      truthEl.textContent = `${truth} (${ok ? "match" : "mispredicted"})`;
      truthEl.classList.add(ok ? "match-ok" : "match-fail");
    } else {
      truthEl.textContent = String(truth);
    }

    scrubber.value = String(stepIndex);
    dockPos.textContent = `${stepIndex} / ${trace.length - 1}`;
    firstBtn.disabled = stepIndex === 0;
    prevBtn.disabled = stepIndex === 0;
    nextBtn.disabled = stepIndex >= trace.length - 1;
    lastBtn.disabled = stepIndex >= trace.length - 1;

    renderSvg(step, syndrome);
    renderTables(step, syndrome);
  }

  clearBtn.addEventListener("click", () => {
    faults = new Set();
    customSyndrome = null;
    activePresetId = null;
    recompute(0);
  });

  firstBtn.addEventListener("click", () => {
    stopPlayback();
    stepIndex = 0;
    render();
  });
  prevBtn.addEventListener("click", () => {
    stopPlayback();
    if (stepIndex > 0) {
      stepIndex -= 1;
      render();
    }
  });
  nextBtn.addEventListener("click", () => {
    stopPlayback();
    if (stepIndex < trace.length - 1) {
      stepIndex += 1;
      render();
    }
  });
  lastBtn.addEventListener("click", () => {
    stopPlayback();
    stepIndex = trace.length - 1;
    render();
  });
  playBtn.addEventListener("click", () => {
    if (timer !== null) stopPlayback();
    else startPlayback();
  });
  scrubber.addEventListener("input", () => {
    stopPlayback();
    stepIndex = Number(scrubber.value);
    render();
  });
  speedSel.addEventListener("change", () => {
    if (timer !== null) startPlayback();
  });

  document.addEventListener("keydown", (ev) => {
    if (
      ev.target instanceof Element &&
      ev.target.closest("input, select, textarea, button")
    ) {
      return;
    }
    if (ev.key === "ArrowRight") {
      ev.preventDefault();
      stopPlayback();
      if (stepIndex < trace.length - 1) {
        stepIndex += 1;
        render();
      }
    } else if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      stopPlayback();
      if (stepIndex > 0) {
        stepIndex -= 1;
        render();
      }
    } else if (ev.key === " ") {
      ev.preventDefault();
      if (timer !== null) stopPlayback();
      else startPlayback();
    }
  });

  recompute(0);
}

if (typeof document !== "undefined") {
  initPage();
}

if (typeof module !== "undefined") {
  module.exports = {
    NUM_DETECTORS,
    BOUNDARY,
    EDGES,
    DATA_QUBITS,
    DETECTORS,
    PRESETS,
    syndromeFromFaults,
    buildTrace,
  };
}
