"use strict";
class LabState {
  constructor() {
    this.reset();
  }
  reset() {
    this.errors = {};
    this.stage = 0;
  }
  toggle(id, pauli) {
    if (this.errors[id] === pauli) delete this.errors[id];
    else this.errors[id] = pauli;
    this.stage = 1;
  }
  next() {
    this.stage = Math.min(3, this.stage + 1);
  }
}
if (typeof module !== "undefined") module.exports = { LabState };

if (typeof document !== "undefined") {
  const $ = (id) => document.getElementById(id);
  const state = new LabState();
  let layout,
    result,
    pauli = "X",
    selectedCheck = null,
    requestId = 0,
    pending = false;
  const phases = [
    "Clean reference",
    "Errors injected",
    "Detection events extracted",
    "Correction replay verified",
  ];
  const frameText = (frame) =>
    Object.entries(frame || {})
      .map(([q, p]) => `${p} q${q}`)
      .join(" · ") || "Identity (no Pauli)";
  const combine = (a, b) => {
    if (!a) return b || "";
    if (!b) return a;
    return a === b ? "" : "XYZ".replace(a, "").replace(b, "");
  };
  const coords = (q) =>
    `${((q.coords[0] + 0.6) / 7.2) * 100}%, ${((q.coords[1] + 0.6) / 7.2) * 100}%`;

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
  async function simulate() {
    const id = ++requestId;
    pending = true;
    result = null;
    render();
    try {
      const data = await api("/api/simulate", { errors: { ...state.errors } });
      if (id !== requestId) return;
      result = data;
      pending = false;
      render();
    } catch (error) {
      if (id !== requestId) return;
      pending = false;
      $("status").textContent =
        `Simulation unavailable: ${error.message}. Change a qubit or Reset to retry.`;
      $("status").className = "failed";
      $("step").disabled = $("run").disabled = true;
    }
  }
  function drawLattice() {
    const lattice = $("lattice");
    const links = layout.checks
      .filter((c) => selectedCheck === null || c.id === selectedCheck)
      .flatMap((c) =>
        c.support.map((id) => {
          const q = layout.data.find((q) => q.id === id);
          return `<line x1="${(c.coords[0] + 0.6) * 100}" y1="${(c.coords[1] + 0.6) * 100}" x2="${(q.coords[0] + 0.6) * 100}" y2="${(q.coords[1] + 0.6) * 100}" class="${selectedCheck === null ? "" : "selected-link"}"/>`;
        }),
      );
    lattice.innerHTML = `<svg viewBox="0 0 720 720" aria-hidden="true">${links.join("")}</svg>`;
    for (const q of layout.data) {
      const fault = state.stage >= 1 ? state.errors[q.id] : "";
      const fix =
        state.stage === 3 && result ? (result.correction || {})[q.id] : "";
      const residual = combine(fault, fix);
      const button = document.createElement("button");
      button.className = `qubit data-qubit ${fault ? "has-error" : ""} ${fix ? "has-fix" : ""} ${state.stage === 3 && residual ? "residual" : ""}`;
      button.dataset.qubit = q.id;
      const [left, top] = coords(q).split(", ");
      button.style.left = left;
      button.style.top = top;
      button.setAttribute(
        "aria-label",
        `Data qubit ${q.id}, coordinates ${q.coords.join(", ")}, injected ${state.errors[q.id] || "none"}${fix ? ", correction " + fix : ""}. Toggle ${pauli}`,
      );
      button.setAttribute("aria-pressed", String(Boolean(state.errors[q.id])));
      button.innerHTML = `<span>q${q.id}</span><b>${state.stage === 3 ? residual || "I" : fault || "·"}</b>${fix ? `<small class="fix-label">+${fix}</small>` : ""}`;
      button.onclick = () => {
        state.toggle(String(q.id), pauli);
        simulate();
      };
      lattice.append(button);
    }
    for (const c of layout.checks) {
      const button = document.createElement("button");
      button.className = `qubit check-qubit ${c.basis.toLowerCase()}-check ${selectedCheck === c.id ? "selected-check" : ""}`;
      button.dataset.check = c.id;
      const [left, top] = coords(c).split(", ");
      button.style.left = left;
      button.style.top = top;
      const fires =
        state.stage >= 2 &&
        result &&
        layout.detectors.some(
          (d) =>
            d.coords[0] === c.coords[0] &&
            d.coords[1] === c.coords[1] &&
            result.detector_indices.includes(d.id),
        );
      if (fires)
        button.classList.add(
          state.stage === 3 ? "check-corrected" : "check-fired",
        );
      button.setAttribute(
        "aria-label",
        `${c.basis} check ancilla ${c.id}; support ${c.support.join(", ")}`,
      );
      button.setAttribute("aria-pressed", String(selectedCheck === c.id));
      button.innerHTML = `<b>${c.basis}</b><span>a${c.id}</span>`;
      button.onclick = () => {
        selectedCheck = selectedCheck === c.id ? null : c.id;
        render();
      };
      lattice.append(button);
    }
    const c = layout.checks.find((c) => c.id === selectedCheck);
    $("check-detail").textContent = c
      ? `${c.basis} check a${c.id} at (${c.coords.join(", ")}): ${c.basis} on ${c.support.map((q) => "q" + q).join(", ")}.`
      : "Select a check ancilla to inspect its actual CX support.";
    $("frame-label").textContent = [
      "Prepared reference",
      "Injected Pauli frame",
      "Error frame / before correction",
      "Representative correction overlay",
    ][state.stage];
    $("frame-detail").textContent =
      state.stage === 0
        ? "No injected errors in this view."
        : state.stage === 3 && result
          ? `Apply: ${frameText(result.correction)}. I = locally canceled.`
          : frameText(state.errors);
  }
  function drawTimeline() {
    let html =
      '<div class="timeline-corner">CHECK / TIME</div>' +
      [0, 1, 2, 3].map((t) => `<div class="time-header">t=${t}</div>`).join("");
    for (const c of layout.checks) {
      html += `<div class="check-row">${c.basis} <span>a${c.id}</span></div>`;
      for (let t = 0; t < 4; t++) {
        const d = layout.detectors.find(
          (d) =>
            d.coords[0] === c.coords[0] &&
            d.coords[1] === c.coords[1] &&
            d.coords[2] === t,
        );
        if (!d) {
          html +=
            '<div class="no-detector" aria-label="No detector defined">—</div>';
          continue;
        }
        const shown = state.stage >= 2 && result;
        const bit = shown
          ? Number(result.detector_indices.includes(d.id))
          : null;
        const after =
          state.stage === 3 && result && result.residual_syndrome !== null
            ? (result.residual_syndrome >> d.id) & 1
            : null;
        html += `<div class="detector ${bit ? (after === 0 ? "cleared" : "fired") : ""}" data-detector="${d.id}" title="D${d.id}, (${d.coords.join(", ")}): ${bit === null ? "not extracted" : bit}${after === null ? "" : ", replay " + after}"><small>D${d.id}</small><b>${bit === null ? "·" : after !== null && bit ? `${bit} → ${after}` : bit}</b></div>`;
      }
    }
    $("timeline").innerHTML = html;
    $("event-count").textContent =
      state.stage >= 2 && result
        ? `${result.detector_indices.length} ORIGINAL EVENTS${state.stage === 3 ? " / REPLAY BELOW" : ""}`
        : "AWAITING EXTRACTION";
  }
  function drawResult() {
    if (!result || state.stage < 2) {
      $("result").innerHTML =
        '<p class="waiting">' +
        (pending
          ? "Computing the circuit with Stim…"
          : "Step through extraction to see the decoder input.") +
        "</p>";
      $("edge-details").hidden = true;
      return;
    }
    const corrected = state.stage === 3;
    const cells = [
      ["Input syndrome", "0x" + result.syndrome.toString(16).padStart(6, "0")],
      ["True Z flip", result.observable],
      ["UF prediction", corrected ? result.prediction : "—"],
      ["Graph residual", corrected ? result.graph_residual : "—"],
      [
        "Replay syndrome",
        corrected ? (result.residual_syndrome ?? "unavailable") : "—",
      ],
      [
        "Replay Z flip",
        corrected ? (result.residual_observable ?? "unavailable") : "—",
      ],
    ];
    $("result").innerHTML =
      `<div class="metrics">${cells.map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`).join("")}</div>` +
      (corrected
        ? `<div id="logical-outcome" class="outcome ${result.logical_success ? "success" : "failure"}"><strong>${result.error ? "Decoder reported an error" : result.logical_success ? "Logical Z preserved" : "Logical failure — Z observable flipped"}</strong><span>${result.logical_success ? "Prediction matches the simulated observable." : "A cleared syndrome is not proof of recovery."} ${result.correction === null ? "No same-location representative is available." : "The physical overlay is an equivalent representative, not unique edge-to-gate recovery."}</span></div>`
        : '<p class="waiting">Detection events are ready. Next: decode and replay a correction.</p>');
    $("edge-details").hidden = !corrected;
    $("edges").innerHTML =
      '<p>Selected correction edges from the existing serial UF decoder. B denotes the graph boundary. L is the logical-Z observable label.</p><div class="edge-list">' +
      (result.correction_edges.length
        ? result.correction_edges
            .map((i) => {
              const [a, b, l] = layout.edges[i];
              return `<span class="edge">e${i}: D${a} ↔ ${b === 24 ? "B" : "D" + b} / L${l}</span>`;
            })
            .join("")
        : "<span>No selected edges (identity correction).</span>") +
      "</div>";
    $("circuit").textContent = result.injected_circuit;
    $("corrected-circuit").textContent =
      result.corrected_circuit ||
      "No representative at this injection location.";
  }
  function render() {
    if (!layout) return;
    const focus = document.activeElement?.dataset;
    const focusedQubit = focus?.qubit,
      focusedCheck = focus?.check;
    drawLattice();
    drawTimeline();
    drawResult();
    document.querySelectorAll("[data-stage]").forEach((b) => {
      const current = Number(b.dataset.stage) === state.stage;
      if (current) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    $("step").disabled = pending || !result || state.stage === 3;
    $("run").disabled = pending || !result;
    $("status").className = "";
    $("status").textContent = pending
      ? "Computing real Stim detector effects…"
      : phases[state.stage] +
        (state.stage === 3
          ? " · counterfactual replay, not live feedback"
          : "");
    if (focusedQubit)
      document
        .querySelector(`[data-qubit="${focusedQubit}"]`)
        ?.focus({ preventScroll: true });
    if (focusedCheck)
      document
        .querySelector(`[data-check="${focusedCheck}"]`)
        ?.focus({ preventScroll: true });
  }
  document.querySelectorAll("[data-pauli]").forEach(
    (button) =>
      (button.onclick = () => {
        pauli = button.dataset.pauli;
        document
          .querySelectorAll("[data-pauli]")
          .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
        render();
      }),
  );
  document.querySelectorAll("[data-stage]").forEach(
    (button) =>
      (button.onclick = () => {
        if (pending || !result) return;
        state.stage = Number(button.dataset.stage);
        render();
      }),
  );
  $("step").onclick = () => {
    state.next();
    render();
  };
  $("run").onclick = () => {
    state.stage = 3;
    render();
  };
  $("reset").onclick = () => {
    state.reset();
    selectedCheck = null;
    simulate();
  };
  api("/api/layout")
    .then((data) => {
      layout = data;
      $("code").textContent = data.code;
      simulate();
    })
    .catch((error) => {
      $("status").textContent =
        `Could not load lab: ${error.message}. Check the local server and reload.`;
      $("status").className = "failed";
      $("step").disabled = $("run").disabled = true;
    });
}
