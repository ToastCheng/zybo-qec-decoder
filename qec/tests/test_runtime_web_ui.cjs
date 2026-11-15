// Opt-in real Chromium test. No serial configuration and no hardware access.
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync, mkdirSync, writeFileSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.RUNTIME_WEB_URL;
if (!base) { console.log('SKIP: set RUNTIME_WEB_URL to an isolated simulation preview'); process.exit(0); }
const profile = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'runtime-web-chrome-'));
const chrome = spawn(process.env.CHROME || '/usr/bin/google-chrome', ['--headless=new','--no-sandbox','--disable-gpu','--remote-debugging-port=0',`--user-data-dir=${profile}`, 'about:blank']);
let log = '';
chrome.stderr.on('data', d => log += d);
const delay = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let socket;
  try {
    for(let i=0; i<100 && !log.includes('DevTools listening on');i++) await delay(100);
    const endpoint = log.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];
    assert(endpoint, log);
    const origin = endpoint.replace('ws:', 'http:').split('/devtools/')[0];
    const target = await (await fetch(`${origin}/json/new?about:blank`, {method:'PUT'})).json();
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise(r => socket.onopen = r);
    let seq = 0; const pending = new Map();
    const requests = [];
    socket.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.method === 'Network.requestWillBeSent') requests.push(msg.params.request);
      if(msg.id){ const p=pending.get(msg.id); pending.delete(msg.id); msg.error?p.reject(msg.error):p.resolve(msg.result); }
    };
    const send = (method, params={}) => new Promise((resolve,reject) => {const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
    const js = async expression => {const r = await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}); if(r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value;};
    await send('Network.enable');
    await send('Page.navigate',{url:base});
    for(let i=0;i<100;i++){ if(await js("!!document.querySelector('#run') && !!document.querySelector('#circuit')?.value"))break;await delay(100); }
    assert.equal(await js("document.querySelector('#source').textContent"),'Software');
    assert.equal(requests.filter(r => r.method === 'POST').length, 0, 'initial page must not compile or decode');
    await js("window.requests=0; const originalFetch=window.fetch;window.fetch=(...args)=>{window.requests++;return originalFetch(...args)};document.querySelector('#run').click()");
    for(let i=0;i<200;i++){if(await js("document.querySelector('#status').dataset.state !== 'busy'"))break;await delay(100);}
    assert.equal(await js("document.querySelector('#status').dataset.state"),'ready');
    assert.equal(await js('window.requests'),1);
    assert.equal(await js("document.querySelector('#circuit-evidence').open || document.querySelector('#graph-evidence').open || document.querySelector('#wire-evidence').open"),false);
    assert.equal(await js("document.querySelectorAll('#circuit-diagram .circuit-wire').length"),2);
    assert.deepEqual(await js("[...document.querySelectorAll('#circuit-diagram .gate[data-gate]')].map(n=>n.dataset.gate).filter(n=>['H','S','CX'].includes(n))"),['H','S','CX']);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=CX] .pair-group').length"),1);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=CX] .control').length"),1);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=CX] .target').length"),1);
    assert.match(await js("document.querySelector('.gate[data-gate=MPP]').textContent"), /MPP.*Y.*X.*Z/s);
    assert.deepEqual(await js("[...document.querySelectorAll('.gate[data-gate=MPP] .product-group')].map(g=>g.textContent)"), ['MPP:YMPP:X','MPP:ZMPP:Z']);
    assert.equal(await js("document.querySelector('.tick-column.active').dataset.tick"),'0');
    const firstActiveFill = await js("getComputedStyle(document.querySelector('.tick-column.active .tick-background')).fill");
    const firstGates = await js("document.querySelector('#gates').textContent");
    await send('Emulation.setDeviceMetricsOverride',{width:360,height:900,deviceScaleFactor:1,mobile:true});
    await js("document.querySelector('#play').click()"); await delay(1000);
    assert.equal(await js("document.querySelector('.tick-column.active').dataset.tick"),'1');
    assert.equal(await js("getComputedStyle(document.querySelector('.tick-column.active .tick-background')).fill"),firstActiveFill);
    assert.notEqual(await js("getComputedStyle(document.querySelector('.tick-column:not(.active) .tick-background')).fill"),firstActiveFill);
    assert.equal(await js("document.querySelector('.tick-column.active').getBoundingClientRect().left < document.querySelector('#diagram-scroll').getBoundingClientRect().right"),true,'timer should bring current tick into the scroll viewport');
    assert(Number(await js("document.querySelector('#scrub').value"))>0);
    assert.notEqual(await js("document.querySelector('#gates').textContent"), firstGates);
    await js("document.querySelector('#pause').click()");
    const paused = await js("document.querySelector('#scrub').value");
    await delay(850);
    assert.equal(await js("document.querySelector('#scrub').value"), paused);
    await js("document.querySelector('#pause').click();document.querySelector('#scrub').value=0;document.querySelector('#scrub').dispatchEvent(new Event('input'));document.querySelector('#step').click()");
    assert.equal(await js("document.querySelector('#scrub').value"),'1');
    assert.equal(await js('window.requests'),1);
    assert((await js("document.querySelector('#gates').textContent")).length>0);
    for(const width of [1280,820,390,360]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<500});
      assert.equal(await js('document.documentElement.scrollWidth > innerWidth'),false, `overflow at ${width}`);
    }
    await js("document.querySelector('#seed').value='5';document.querySelector('#seed').dispatchEvent(new Event('input'))");
    assert.equal(await js("document.querySelector('#play').disabled"),true);
    assert.equal(await js("document.querySelector('#result').textContent.trim()"),'');
    const beforeEmptySeed = await js('window.requests');
    await js("document.querySelector('#seed').value='';document.querySelector('#seed').dispatchEvent(new Event('input'));document.querySelector('#run').click()");
    for(let i=0;i<200;i++){if(await js("document.querySelector('#status').dataset.state !== 'busy'"))break;await delay(100);}
    assert.equal(await js("document.querySelector('#status').dataset.state"),'error', 'empty seed must not silently become zero');
    assert.equal(await js('window.requests'),beforeEmptySeed);
    await js("document.querySelector('#seed').value='5';document.querySelector('#seed').dispatchEvent(new Event('input'))");
    await js("document.querySelector('#circuit').value='BAD_GATE';document.querySelector('#circuit').dispatchEvent(new Event('input'));document.querySelector('#run').click()");
    for(let i=0;i<200;i++){if(await js("document.querySelector('#status').dataset.state !== 'busy'"))break;await delay(100);}
    assert.equal(await js("document.querySelector('#status').dataset.state"),'error');
    assert.equal(await js("document.querySelector('#result').textContent.trim()"),'');
    assert.equal(await js("document.querySelector('#play').disabled"),true);
    // Unlisted annotated Clifford circuit, real simulation and uint32 bit 31.
    const circuit = 'R 0 1 2\nH 2\nTICK\nH 2\nX_ERROR(1) 2\nM 2\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]\n';
    await js(`document.querySelector('#circuit').value=${JSON.stringify(circuit)};document.querySelector('#circuit').dispatchEvent(new Event('input'));document.querySelector('#run').click()`);
    for(let i=0;i<200;i++){if(await js("document.querySelector('#status').dataset.state !== 'busy'"))break;await delay(100);}
    assert.equal(await js("document.querySelector('#status').dataset.state"),'ready');
    const beforeReplay = await js('window.requests');
    await js("document.querySelector('#scrub').value=document.querySelector('#scrub').max;document.querySelector('#scrub').dispatchEvent(new Event('input'))");
    assert.match(await js("document.querySelector('#result').textContent"), /prediction 2147483648 · truth 2147483648 · match/);
    await js("document.querySelector('#play').click()");
    assert.equal(await js("document.querySelector('#scrub').value"),'0');
    await delay(850);
    assert.equal(await js("document.querySelector('#scrub').value"),'1');
    assert.equal(await js('window.requests'),beforeReplay);
    assert.equal(await js("document.querySelectorAll('.circuit-wire').length"),3);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=R]').length"),1);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=M]').length"),1);
    assert.equal(await js("getComputedStyle(document.querySelector('.wire-label.pauli-X')).fill"),'rgb(255, 173, 141)');
    assert.equal(await js("document.querySelector('#detectors').textContent"),'D0: event');
    assert.equal(await js("document.querySelectorAll('#circuit-diagram [data-detector]').length"),0);
    await js("document.querySelector('#pause').click()");
    if (process.env.RUNTIME_WEB_SCREENSHOTS_DIR) {
      mkdirSync(process.env.RUNTIME_WEB_SCREENSHOTS_DIR, {recursive:true});
      for (const width of [1280, 390]) {
        await send('Emulation.setDeviceMetricsOverride', {width,height:width > 500 ? 1440 : 1100,deviceScaleFactor:1,mobile:width<500});
        await delay(200);
        const screenshot = await send('Page.captureScreenshot', {format:'png',captureBeyondViewport:false});
        const path = join(process.env.RUNTIME_WEB_SCREENSHOTS_DIR, `runtime-web-software-${width}.png`);
        writeFileSync(path, Buffer.from(screenshot.data, 'base64'));
        console.log(`Screenshot: ${path}`);
      }
    }
    const runCircuit = async text => {
      await js(`document.querySelector('#circuit').value=${JSON.stringify(text)};document.querySelector('#circuit').dispatchEvent(new Event('input'));document.querySelector('#run').click()`);
      for(let i=0;i<200;i++){if(await js("document.querySelector('#status').dataset.state !== 'busy'"))break;await delay(100);}
      assert.equal(await js("document.querySelector('#status').dataset.state"),'ready',await js("document.querySelector('#status').textContent"));
    };
    await runCircuit('R 0 1023\\nH 0\\nS 0\\nCX 0 1023 1023 0\\nSPP Z0*Z1023\\nTICK\\nR 0 1023\\nX_ERROR(1) 1023\\nM 0 1023\\nDETECTOR rec[-1]\\nOBSERVABLE_INCLUDE(31) rec[-1]'.replaceAll('\\n','\n'));
    assert.deepEqual(await js("[...document.querySelectorAll('.circuit-wire')].map(n=>n.dataset.qubit)"),['0','1023']);
    assert.equal(await js("document.querySelectorAll('#qubits .qubit').length"),2,'sparse high indices must not create 1024 chips');
    assert.match(await js("document.querySelector('#diagram-notice').textContent"),/2 used wires \/ 1024 indexed/);
    assert.match(await js("document.querySelector('.gate[data-gate=SPP]').textContent"),/SPP:Z/);
    assert.equal(await js("document.querySelectorAll('.gate[data-gate=CX] .pair-group').length"),2);
    assert.equal(await js("new Set([...document.querySelectorAll('.gate[data-gate=CX] .pair-group')].map(n=>n.getBoundingClientRect().x)).size"),2,'successive CX pairs must not overlap');
    const sparseRequests = await js('window.requests');
    await js("document.querySelector('#play').click()"); await delay(850);
    assert.equal(await js('window.requests'),sparseRequests);
    assert.match(await js("document.querySelector('#result').textContent"),/prediction 2147483648 · truth 2147483648 · match/);
    for(const width of [1280,820,390,360]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<500});
      assert.equal(await js('document.documentElement.scrollWidth > innerWidth'),false,`sparse overflow at ${width}`);
      assert.equal(await js("document.querySelector('#diagram-scroll').scrollWidth > document.querySelector('#diagram-scroll').clientWidth"),true,'diagram should scroll internally');
    }
    await runCircuit(`R ${Array.from({length:1024},(_,i)=>i).join(' ')}\nX_ERROR(1) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-1]`);
    assert.equal(await js("document.querySelectorAll('.circuit-wire').length"),64);
    assert.match(await js("document.querySelector('#diagram-notice').textContent"),/omitted used qubits q64–q1023 \(960 wires\)/);
    assert((await js("document.querySelector('#circuit-diagram').querySelectorAll('*').length")) < 1000);
    assert.equal(await js("document.querySelector('#diagram-scroll').getBoundingClientRect().height <= 430"),true);
    assert.equal(await js('document.documentElement.scrollWidth > innerWidth'),false);
    assert.equal(requests.filter(r => r.method === 'POST').length, 5);
    assert(requests.filter(r => r.method === 'POST').every(r => r.url === `${base}/api/run`));
    console.log('PASS Chromium: SVG wires/H/S/CX controls and sequential pairs/MPP/SPP products, timer active computed styles and phone auto-scroll, explicit Run, pause/scrub/step/end replay without requests, invalidation/errors, uint32 bit31, sampled X color and separate detector bits, sparse q1023 and 1024-qubit bounded DOM, collapsed evidence, 1280/820/390/360px no overflow');
  } finally {socket?.close(); chrome.kill(); await delay(300);rmSync(profile,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
