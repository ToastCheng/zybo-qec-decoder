'use strict';
// Only Run submits circuit work. Completed traces are immutable replay data.
const $ = id => document.getElementById(id);
let shot = null;
let timer = null;
let revision = 0;
let busy = false;
function pause() {
    clearInterval(timer);
    timer = null;
}
function state(kind, message) {
    $('status').dataset.state = kind;
    $('status').textContent = message;
}
function invalidate() {
    revision++;
    pause();
    shot = null;
    for (const id of ['play', 'pause', 'step', 'scrub']) $(id).disabled = true;
    for (const id of ['result', 'gates', 'qubits', 'detectors', 'circuit-data', 'graph-data', 'wire-data', 'circuit-diagram', 'diagram-notice']) $(id).textContent = '';
    $('tick').textContent = '—';
    $('scrub').value = '0';
    state('idle', 'Inputs changed. Run to produce a new shot.');
}
// SVG nodes are constructed as text/attributes; circuit text is never HTML.
function svgNode(tag, attrs, parent, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
}
function usedWires() {
    return [...new Set(shot.trace.flatMap(f => f.diagram.flatMap(op => op.targets
        .filter(t => t.qubit !== undefined).map(t => t.qubit))))].sort((a, b) => a - b);
}
function productGroups(op) {
    if (op.kind === 'pair') {
        const groups = [];
        for (let i = 0; i < op.targets.length; i += 2) groups.push(op.targets.slice(i, i + 2));
        return groups;
    }
    if (!['MPP', 'SPP', 'SPP_DAG'].includes(op.name)) return [op.targets.filter(t => t.qubit !== undefined)];
    const groups = [];
    let combine = false;
    for (const t of op.targets) {
        if (t.combiner) { combine = true; continue; }
        if (t.qubit === undefined) continue;
        if (!combine) groups.push([]);
        groups.at(-1).push(t);
        combine = false;
    }
    return groups;
}
function drawCircuit(index) {
    const svg = $('circuit-diagram');
    svg.replaceChildren();
    const used = usedWires(), wires = used.slice(0, 64);
    const y = new Map(wires.map((q, i) => [q, 68 + i * 44]));
    const height = Math.max(120, wires.length * 44 + 90);
    const start = Math.max(0, Math.min(index - 7, shot.trace.length - 16));
    const end = Math.min(shot.trace.length, start + 16);
    const notes = [`${used.length} used wires / ${shot.compiled.counts.qubits} indexed qubits. Unused indices are not drawn.`];
    if (used.length > wires.length) notes.push(`Wire cap 64: omitted used qubits q${used[64]}–q${used.at(-1)} (${used.length - 64} wires). Gates touching omitted wires are not drawn.`);
    if (start || end < shot.trace.length) notes.push(`Tick window ${start}–${end - 1}; omitted ticks ${start ? `0–${start - 1}` : 'none before'}, ${end < shot.trace.length ? `${end}–${shot.trace.length - 1}` : 'none after'}.`);
    let x = 92;
    for (let tick = start; tick < end; tick++) {
        const operations = shot.trace[tick].diagram.filter(op => op.targets.some(t => t.qubit !== undefined) && op.name !== 'QUBIT_COORDS');
        const shown = operations.slice(0, 32);
        if (operations.length > 32) notes.push(`TICK ${tick}: omitted operations 33–${operations.length} (32-column cap). See active Stim operations.`);
        const width = Math.max(1, shown.reduce((n, op) => n + productGroups(op).length, 0)) * 112 + 16;
        const column = svgNode('g', {class: `tick-column${tick === index ? ' active' : ''}`, 'data-tick': tick}, svg);
        svgNode('rect', {class: 'tick-background', x, y: 8, width, height: height - 16, rx: 6}, column);
        svgNode('text', {x: x + 8, y: 30, class: 'tick-label'}, column, `TICK ${tick}`);
        let offset = 0;
        shown.forEach(op => {
            const groups = productGroups(op);
            const cx = x + 56 + offset * 112;
            offset += groups.length;
            const targets = op.targets.filter(t => t.qubit !== undefined);
            if (targets.some(t => !y.has(t.qubit))) return;
            const gate = svgNode('g', {class: 'gate', 'data-gate': op.name}, column);
            svgNode('title', {}, gate, op.text);
            const box = (t, label, parent = gate) => {
                svgNode('rect', {class: 'gate-box', x: cx - 48, y: y.get(t.qubit) - 14, width: 96, height: 28, rx: 4}, parent);
                svgNode('text', {x: cx, y: y.get(t.qubit) + 5, class: 'gate-label'}, parent, label);
            };
            if (op.kind === 'pair') {
                groups.forEach(([a, b], i) => {
                    const pair = svgNode('g', {class: 'pair-group', transform: `translate(${i * 112} 0)`}, gate);
                    svgNode('line', {class: 'gate-link', x1: cx, x2: cx, y1: y.get(a.qubit), y2: y.get(b.qubit)}, pair);
                    if (['CX', 'CY', 'CZ'].includes(op.name)) {
                        svgNode('circle', {class: 'control', cx, cy: y.get(a.qubit), r: 5}, pair);
                        svgNode('circle', {class: 'target', cx, cy: y.get(b.qubit), r: 13}, pair);
                        svgNode('text', {class: 'gate-label', x: cx, y: y.get(b.qubit) + 5}, pair, op.name.slice(1));
                    } else { box(a, `${op.name}:1`, pair); box(b, `${op.name}:2`, pair); }
                });
            } else {
                // Product operations retain gate name and each basis; no fake CX decomposition.
                groups.forEach((product, i) => {
                    const group = svgNode('g', {class: 'product-group', transform: `translate(${i * 112} 0)`}, gate);
                    if (op.targets.some(t => t.pauli)) {
                        svgNode('line', {class: 'product-link', x1: cx, x2: cx, y1: Math.min(...product.map(t => y.get(t.qubit))), y2: Math.max(...product.map(t => y.get(t.qubit)))}, group);
                    }
                    product.forEach(t => {
                        svgNode('rect', {class: 'gate-box', x: cx - 48, y: y.get(t.qubit) - 14, width: 96, height: 28, rx: 4}, group);
                        svgNode('text', {x: cx, y: y.get(t.qubit) + 5, class: 'gate-label'}, group, `${op.name}${t.pauli ? ':' + t.pauli : ''}${t.inverted ? ' !' : ''}`);
                    });
                });
            }
        });
        x += width + 12;
    }
    // Put wires beneath gates, but keep labels in the same immutable SVG.
    const background = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    svg.prepend(background);
    wires.forEach(q => {
        svgNode('line', {class: 'circuit-wire', 'data-qubit': q, x1: 78, x2: x, y1: y.get(q), y2: y.get(q)}, background);
        const pauli = shot.trace[index].paulis[q] || '_';
        svgNode('text', {class: `wire-label pauli-${pauli}`, x: 8, y: y.get(q) + 5}, background, `q${q} ${pauli === '_' ? 'I' : pauli}`);
    });
    svg.setAttribute('width', x + 12);
    svg.setAttribute('height', height);
    $('diagram-notice').textContent = notes.join(' ');
    $('diagram-scroll').scrollLeft = index === start ? 0 : Math.max(0, Number(svg.querySelector('.active .tick-background').getAttribute('x')) - 8);
}
function render() {
    if (!shot) return;
    const index = Number($('scrub').value);
    const frame = shot.trace[index];
    $('tick').textContent = `${index} / ${shot.trace.length - 1}`;
    $('gates').textContent = frame.operations.join('\n') || '(no operations)';
    $('qubits').replaceChildren();
    drawCircuit(index);
    usedWires().slice(0, 64).forEach(i => {
        const pauli = frame.paulis[i] || '_';
        const node = document.createElement('span');
        node.className = `qubit pauli-${pauli}`;
        node.textContent = `q${i} ${pauli === '_' ? 'I' : pauli}`;
        $('qubits').append(node);
    });
    $('detectors').textContent = frame.detectors.map((bit, i) => `D${i}: ${bit ? 'event' : 'quiet'}`).join(' · ') || 'Detectors not yet available';
    // All masks are exact uint32-valued JS Numbers; never use signed bitwise ops.
    const complete = index === shot.trace.length - 1;
    $('result').textContent = complete
        ? `${shot.source} · observable prediction ${shot.prediction} · truth ${shot.observable_truth} · ${shot.prediction === shot.observable_truth ? 'match' : 'logical mismatch'}${shot.cycles === null ? '' : ` · ${shot.cycles} FPGA cycles`}`
        : `Sampled shot · ${shot.source} decoder result available at final tick`;
}
function step() {
    if (!shot) return;
    const next = Math.min(Number($('scrub').value) + 1, shot.trace.length - 1);
    $('scrub').value = String(next);
    render();
    if (next === shot.trace.length - 1) pause();
}
$('play').addEventListener('click', () => {
    if (!shot) return;
    pause();
    if (Number($('scrub').value) === shot.trace.length - 1) $('scrub').value = '0';
    render();
    timer = setInterval(step, Number($('speed').value));
});
$('pause').addEventListener('click', pause);
$('step').addEventListener('click', () => { pause(); step(); });
$('scrub').addEventListener('input', () => { pause(); render(); });
$('speed').addEventListener('change', pause);
for (const id of ['circuit', 'reference', 'seed', 'noise']) $(id).addEventListener('input', invalidate);
$('run').addEventListener('click', async () => {
    if (busy) return;
    invalidate();
    const current = revision;
    busy = true;
    $('run').disabled = true;
    state('busy', 'Simulating and decoding…');
    try {
        const seed = Number($('seed').value);
        const addedNoise = Number($('noise').value);
        if (!$('seed').value.trim() || !Number.isSafeInteger(seed) || seed < 0) {
            throw Error('Seed must be an integer in 0..2^53-1.');
        }
        if (!$('noise').value.trim() || !Number.isFinite(addedNoise) || addedNoise < 0 || addedNoise > 0.75) {
            throw Error('Added gate depolarization must be in 0..0.75.');
        }
        const response = await fetch('/api/run', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({circuit: $('circuit').value, reference: $('reference').value || null,
                seed, added_noise: addedNoise})
        });
        const data = await response.json();
        if (current !== revision) return;
        if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
        if (!Array.isArray(data.trace) || !data.trace.length || data.trace.some(f => !Array.isArray(f.diagram))) throw Error('Missing trace; restart the runtime server.');
        shot = data;
        $('source').textContent = data.source;
        $('scrub').max = String(data.trace.length - 1);
        $('scrub').value = '0';
        for (const id of ['play', 'pause', 'step', 'scrub']) $(id).disabled = false;
        $('circuit-data').textContent = JSON.stringify({counts: data.compiled.counts, circuit: data.compiled.circuit, sha256: data.compiled.sha256, stim_version: data.compiled.stim_version}, null, 2);
        $('graph-data').textContent = JSON.stringify({edges: data.compiled.edges, detectors: data.compiled.detectors, limitations: data.compiled.limitations}, null, 2);
        $('wire-data').textContent = JSON.stringify({source: data.source, identity: data.identity || null, transactions: data.transactions}, null, 2);
        render();
        state('ready', 'Shot complete. Replay without network requests.');
    } catch (error) {
        if (current === revision) state('error', error.message);
    } finally {
        busy = false;
        $('run').disabled = false;
    }
});
fetch('/api/config').then(response => {
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    return response.json();
}).then(config => {
    $('source').textContent = config.source;
    $('circuit').value = config.example;
    $('run').disabled = false;
    state('idle', 'Ready. Run explicitly to simulate and decode.');
}).catch(error => state('error', error.message));
