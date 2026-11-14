// Opt-in real-browser regression: QEC_WEB_URL=http://127.0.0.1:8766 node --test qec/tests/test_web_browser.cjs
// Uses Chrome + Node's native CDP WebSocket; no npm dependencies or synthetic results.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const delay = ms => new Promise(r => setTimeout(r, ms));

test('initial Play visibly runs gates, an explicit example fault, detectors and host correction', {
  skip: !process.env.QEC_WEB_URL, timeout: 30000,
}, async t => {
  const profile = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'qec-ui-chrome-'));
  const chrome = spawn(process.env.CHROME || 'google-chrome', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  t.after(async () => { chrome.kill(); await new Promise(r => chrome.once('exit', r)); fs.rmSync(profile, { recursive: true, force: true }); });
  let stderr = '';
  chrome.stderr.on('data', d => { stderr += d; });
  for (let i = 0; !stderr.includes('DevTools listening on ') && i < 100; i++) await delay(50);
  const endpoint = stderr.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
  assert.ok(endpoint, stderr);
  const target = await (await fetch(`http://${new URL(endpoint).host}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  t.after(() => ws.close());
  let id = 0;
  const requests = new Map();
  const errors = [];
  ws.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) {
      const entry = requests.get(message.id);
      requests.delete(message.id);
      message.error ? entry.reject(Error(JSON.stringify(message.error))) : entry.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
    else if (message.method === 'Fetch.requestPaused') {
      cdp('Fetch.fulfillRequest', { requestId: message.params.requestId, responseCode: 503,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(JSON.stringify({ error: 'Regression fixture: FPGA unavailable' })).toString('base64') });
    }
  };
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    requests.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }));
  });
  const js = async expression => {
    const result = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const until = async (expression, description) => {
    for (let i = 0; i < 150; i++) { if (await js(expression)) return; await delay(50); }
    assert.fail(`${description}: ${await js('document.body.innerText')}`);
  };
  await cdp('Runtime.enable');
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await cdp('Page.navigate', { url: process.env.QEC_WEB_URL });
  await until('document.getElementById("play") && !document.getElementById("play").disabled && document.querySelectorAll(".qubit").length === 17', 'ready');
  await js('document.getElementById("play").click()');
  assert.equal(await js('document.getElementById("position").textContent'), '1 / 22', 'Play must advance immediately, not look inert');
  assert.equal(await js('getComputedStyle(document.querySelector(".qubit.active")).backgroundColor'), 'rgb(173, 221, 246)', 'active gates have a distinct blue fill');
  assert.match(await js('document.querySelector(".qubit.active").textContent'), /H/, 'active gate name visible on qubit');
  assert.match(await js('document.getElementById("scenario").textContent'), /Example.*X.*q10.*8/, 'deliberate fault clearly labeled, not hidden noise');
  await js('document.getElementById("speed").value="4"');
  await until('document.querySelector(".has-error")', 'fault visible');
  await delay(150);
  assert.equal(await js('getComputedStyle(document.querySelector(".has-error")).backgroundColor'), 'rgb(244, 189, 97)');
  await until('document.querySelector(".detector.fired:not(.cleared)")', 'measurement-time detector flips visible');
  await delay(150);
  assert.equal(await js('getComputedStyle(document.querySelector(".detector.fired")).backgroundColor'), 'rgb(233, 144, 134)');
  await until('document.getElementById("tick-label").textContent === "Host correction"', 'host correction reached');
  assert.ok(await js('!!document.querySelector(".has-fix")'));
  await delay(150);
  assert.equal(await js('getComputedStyle(document.querySelector(".has-fix")).backgroundColor'), 'rgb(191, 230, 205)');
  assert.equal(await js('document.querySelector(".has-fix").querySelector("b").textContent'), 'I');
  assert.equal(await js('document.querySelectorAll(".detector.cleared").length'), 2);
  assert.match(await js('document.getElementById("result").textContent'), /Z preserved/);
  await js('document.getElementById("scrubber").value=13; document.getElementById("scrubber").dispatchEvent(new Event("input"))');
  assert.equal(await js('document.querySelectorAll(".detector.fired").length'), 0, 'backward scrub hides future detector flips');
  await js('document.getElementById("scrubber").value=22; document.getElementById("scrubber").dispatchEvent(new Event("input"))');
  await js('document.getElementById("play").click()');
  assert.equal(await js('document.getElementById("position").textContent'), '1 / 22', 'Play replays from completed state');
  await js('document.getElementById("reset").click()');
  await until('!document.getElementById("play").disabled', 'clear faults ready');
  assert.match(await js('document.getElementById("scenario").textContent'), /No faults/);
  assert.equal(await js('JSON.parse(document.getElementById("technical").textContent).faults.length'), 0);
  await js('document.getElementById("scrubber").value=22; document.getElementById("scrubber").dispatchEvent(new Event("input"))');
  assert.equal(await js('document.querySelectorAll(".has-error,.detector.fired,.has-fix").length'), 0, 'clear faults is genuinely a noiseless run');
  assert.deepEqual(errors, []);
  await cdp('Fetch.enable', { patterns: [{ urlPattern: '*/api/simulate', requestStage: 'Request' }] });
  await js('document.getElementById("example").click()');
  await until('document.getElementById("status").textContent.includes("Regression fixture: FPGA unavailable")', 'source failure visible');
  assert.equal(await js('document.getElementById("play").disabled'), true);
  assert.match(await js('document.getElementById("source").textContent'), /unavailable/);
  assert.ok(await js('document.getElementById("status").getBoundingClientRect().top < document.getElementById("lattice").getBoundingClientRect().top'));
  await cdp('Fetch.disable');
  await js('document.getElementById("example").click()');
  await until('!document.getElementById("play").disabled', 'source recovered');
  for (const width of [1280, 820, 390]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width === 390 });
    assert.equal(await js('document.documentElement.scrollWidth > innerWidth'), false, `no overflow at ${width}`);
    assert.ok(await js('document.getElementById("play").getBoundingClientRect().bottom < innerHeight'), `Play visible at ${width}`);
  }
  if (process.env.QEC_STALE_URL) {
    await cdp('Page.navigate', { url: process.env.QEC_STALE_URL });
    await until('document.getElementById("status")?.textContent.includes("Restart the QEC web server")', 'stale server actionable error');
    assert.equal(await js('document.getElementById("play").disabled'), true);
    assert.equal(await js('document.getElementById("source").textContent'), 'Unavailable');
    assert.deepEqual(errors, []);
  }
  console.log('Verified real API: moving ticks, blue H gates, X q10@8, two detector flips, I residual, replay and clear.');
});
