"use strict";

// Local editing/transport state only. Physical frames and decoder evidence come
// from the server; moving the cursor never advances a decoder or contacts a board.
class LabState {
  constructor(lastTick = 21) {
    this.lastTick = lastTick;
    this.reset();
  }
  reset() {
    this.faults = [];
    this.tick = 0;
  }
  seek(tick) {
    // The extra position is a host-correction overlay, not another circuit tick.
    this.tick = Math.max(0, Math.min(this.lastTick + 1, Math.round(tick)));
  }
  next() {
    this.seek(this.tick + 1);
  }
  previous() {
    this.seek(this.tick - 1);
  }
  toggle(qubit, pauli, tick = Math.min(this.tick, this.lastTick)) {
    // One fault per (tick, qubit): repeat removes it, a different Pauli replaces it.
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
// Recompute from the cursor so backward scrub hides future measurements.
const visibleDetectors = (detectors, indices, tick) =>
  indices.filter(
    (i) => detectors.find((d) => d.id === i).available_tick <= tick,
  );
// Compatibility guards catch older servers, not every malformed field. The
// server remains responsible for full circuit/input validation.
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
// Export pure helpers for Node without executing browser setup.
if (typeof module !== "undefined")
  module.exports = {
    LabState,
    visibleDetectors,
    validateLayout,
    validateReplay,
  };

if (typeof document !== "undefined") {
  const $ = (id) => document.getElementById(id);
  // A new request clears old evidence. Monotonic IDs prevent a late response
  // overwriting a newer edit; requests themselves are not aborted.
  let layout,
    state,
    result,
    pending = false,
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
    $("play").textContent = "Play";
  }
  function seek(tick) {
    state.seek(tick);
    $("fault-tick").value = Math.min(state.tick, state.lastTick);
    render();
  }
  function advance() {
    // Play advances immediately. Speed affects the next scheduled delay, not
    // circuit physics or server-side decoder execution.
    state.next();
    render();
    if (state.tick > state.lastTick) {
      stop();
      return;
    }
    timer = setTimeout(advance, 700 / Number($("speed").value));
  }
  async function simulate() {
    stop();
    const id = ++requestId;
    pending = true;
    result = null;
    failure = "";
    render();
    try {
      const data = await api("/api/simulate", {
        faults: state.faults.map((f) => ({ ...f })),
      });
      if (id !== requestId) return;
      result = validateReplay(data, layout.ticks.length);
    } catch (e) {
      if (id !== requestId) return;
      failure = e.message;
    }
    pending = false;
    render();
  }
  const position = (q) => ({
    x: (q.coords[0] + 0.6) * 100,
    y: (q.coords[1] + 0.6) * 100,
  });
  const combine = (a, b) =>
    !a ? b || "" : !b ? a : a === b ? "" : "XYZ".replace(a, "").replace(b, "");
  // combine above multiplies Paulis modulo global phase for residual display.
  function render() {
    if (!layout) return;
    const focused = document.activeElement?.dataset.qubit;
    const corrected = state.tick > state.lastTick;
    const tick = Math.min(state.tick, state.lastTick);
    const operations = layout.ticks[tick].operations;
    const visible = result
      ? visibleDetectors(layout.detectors, result.detector_indices, tick)
      : [];
    // Server trace frames are post-operation. Only the extra final position
    // adds the host-derived correction; this is not physical feedback.
    const frame = result?.trace[tick].pauli_frame || {};
    const fixes = corrected ? result?.correction_frame || {} : {};
    $("tick-label").textContent = corrected
      ? "Host correction"
      : `Tick ${tick}`;
    $("operations").textContent = corrected
      ? "Pauli frame"
      : operations.map((op) => op.name).join(" · ");
    $("position").textContent = `${state.tick} / ${state.lastTick + 1}`;
    $("scrubber").value = state.tick;
    $("scrubber").disabled = false;
    $("back").disabled = state.tick === 0;
    $("step").disabled = state.tick > state.lastTick;
    $("play").disabled = pending || !result;
    $("example").disabled = false;
    $("reset").disabled = false;
    $("source").textContent = failure
      ? `${layout.source} · unavailable`
      : result?.source || layout.source;
    $("status").className = failure ? "failed" : "";
    $("status").textContent = failure || (pending ? "Decoding…" : "");
    const active = new Set(operations.flatMap((op) => op.targets));
    const byId = new Map(
      [...layout.data, ...layout.checks].map((q) => [q.id, q]),
    );
    // CX targets arrive as ordered control/target pairs in one flattened list.
    const links = operations
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
    for (const q of [...layout.data, ...layout.checks]) {
      const data = !q.basis;
      const button = document.createElement("button");
      const fault = frame[q.id] || "",
        fix = fixes[q.id] || "";
      const residual = combine(fault, fix);
      const fired = layout.detectors.some(
        (d) =>
          d.coords[0] === q.coords[0] &&
          d.coords[1] === q.coords[1] &&
          visible.includes(d.id),
      );
      button.className = `qubit ${data ? "data-qubit" : "check-qubit"} ${!corrected && active.has(q.id) ? "active" : ""} ${fault ? "has-error" : ""} ${fired ? "check-fired" : ""} ${fix ? "has-fix" : ""} ${corrected && residual ? "residual" : ""}`;
      button.dataset.qubit = q.id;
      const pos = position(q);
      button.style.left = `${pos.x / 7.2}%`;
      button.style.top = `${pos.y / 7.2}%`;
      button.setAttribute(
        "aria-label",
        data
          ? `Data qubit ${q.id}, ${fault || "I"}${fix ? ", host correction " + fix : ""}. Inject ${pauli} at tick ${$("fault-tick").value}`
          : `${q.basis} check ${q.id}${fired ? ", detector flip" : ""}`,
      );
      const gates = corrected
        ? []
        : operations
            .filter((op) => op.targets.includes(q.id))
            .map((op) => op.name);
      button.innerHTML = `<span>${data ? "q" : q.basis}${q.id}</span><b>${corrected ? residual || (data ? "I" : "·") : fault || (fired ? "1" : "·")}</b>${gates.length ? `<em>${gates.join("/")}</em>` : ""}${fix ? `<small>+${fix}</small>` : ""}`;
      if (data) {
        const selected = state.faults.some(
          (f) => f.qubit === q.id && f.tick === Number($("fault-tick").value),
        );
        button.setAttribute("aria-pressed", String(selected));
        button.onclick = () => {
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
          simulate();
        };
      } else {
        button.tabIndex = -1;
        button.setAttribute("aria-disabled", "true");
      }
      $("lattice").append(button);
    }
    // Rebuilding buttons must not lose the selected qubit's keyboard focus.
    if (focused)
      document
        .querySelector(`[data-qubit="${focused}"]`)
        ?.focus({ preventScroll: true });
    // Four detector-time columns represent measurement boundaries, not ticks.
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
            ? (result.residual_syndrome >> d.id) & 1
            : null;
        html += `<div data-detector="${d.id}" data-available="${Boolean(available)}" class="detector ${bit ? "fired" : ""} ${bit && replay === 0 ? "cleared" : ""}" title="D${d.id} · tick ${d.available_tick}"><small>D${d.id}</small><b>${bit === null ? "·" : bit && replay !== null ? `${bit}→${replay}` : bit}</b></div>`;
      }
    }
    $("timeline").innerHTML = html;
    $("event-count").textContent = `${visible.length} flips`;
    $("result").textContent =
      corrected && result
        ? `${result.logical_success ? "Z preserved" : "Logical failure"} · frame ${result.host_frame}${result.correction === null ? " · no representative" : ""}`
        : "";
    $("result").className =
      corrected && result
        ? result.logical_success
          ? "success"
          : "failed"
        : "";
    $("scenario").textContent = !state.faults.length
      ? "No faults · click a data qubit to inject"
      : `${state.faults.length === 1 && state.faults[0].tick === 8 && state.faults[0].qubit === 10 && state.faults[0].pauli === "X" ? "Example" : "Injected"} · ${state.faults.map((f) => `${f.pauli} on q${f.qubit} at tick ${f.tick}`).join(" · ")}`;
    // Even with FPGA prediction/cycles, edges and representative Pauli/circuit
    // replay are host-derived. Preserve provenance alongside raw evidence.
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
  }
  // Selection/cursor changes redraw only. Fault edits/example/reset request a
  // fresh complete-window simulation; playback traverses that response locally.
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
  $("back").onclick = () => {
    stop();
    seek(state.tick - 1);
  };
  $("step").onclick = () => {
    stop();
    seek(state.tick + 1);
  };
  $("scrubber").oninput = () => {
    stop();
    seek(Number($("scrubber").value));
  };
  $("fault-tick").oninput = () => render();
  $("play").onclick = () => {
    if (timer) {
      stop();
      return;
    }
    if (state.tick > state.lastTick) seek(0);
    $("play").textContent = "Pause";
    advance();
  };
  $("example").onclick = () => {
    state.reset();
    state.toggle(10, "X", 8);
    $("fault-tick").value = 8;
    simulate();
  };
  $("reset").onclick = () => {
    state.reset();
    $("fault-tick").value = 0;
    simulate();
  };
  document.addEventListener("keydown", (e) => {
    // Leave native controls, text entry and modified browser shortcuts alone.
    if (
      e.ctrlKey ||
      e.metaKey ||
      e.altKey ||
      (e.target instanceof Element &&
        e.target.closest("input,select,textarea,button,summary"))
    )
      return;
    if (!state) return;
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
  // Start with the explicit X q10@8 example, not hidden background noise.
  api("/api/layout")
    .then((data) => {
      layout = validateLayout(data);
      state = new LabState(data.ticks.length - 1);
      state.toggle(10, "X", 8);
      $("fault-tick").value = 8;
      $("scrubber").max = state.lastTick + 1;
      $("fault-tick").max = state.lastTick;
      simulate();
    })
    .catch((e) => {
      $("source").textContent = "Unavailable";
      $("status").className = "failed";
      $("status").textContent = e.message;
    });
}
