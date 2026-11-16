const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test(
  "paper editor keeps circuit and every physical qubit visible",
  { skip: !process.env.QEC_WEB_URL, timeout: 90000 },
  async (t) => {
    const profile = fs.mkdtempSync(
      path.join(process.env.TMPDIR, "qec-circuit-chrome-"),
    );
    const chrome = spawn(process.env.CHROME || "google-chrome", [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "about:blank",
    ]);
    let log = "",
      socket;
    chrome.stderr.on("data", (data) => (log += data));
    t.after(async () => {
      socket?.close();
      chrome.kill();
      await delay(200);
      fs.rmSync(profile, { recursive: true, force: true });
    });
    for (let i = 0; i < 100 && !log.includes("DevTools listening on"); i++)
      await delay(50);
    const endpoint = log.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
    assert.ok(endpoint, log);
    const target = await (
      await fetch(`http://${new URL(endpoint).host}/json/new?about:blank`, {
        method: "PUT",
      })
    ).json();
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve) => (socket.onopen = resolve));
    let seq = 0;
    const pending = new Map(),
      posts = [],
      errors = [];
    socket.onmessage = ({ data }) => {
      const msg = JSON.parse(data);
      if (msg.id) {
        const waiter = pending.get(msg.id);
        pending.delete(msg.id);
        msg.error
          ? waiter.reject(Error(JSON.stringify(msg.error)))
          : waiter.resolve(msg.result);
      } else if (
        msg.method === "Network.requestWillBeSent" &&
        msg.params.request.method === "POST"
      )
        posts.push(msg.params.request);
      else if (msg.method === "Runtime.exceptionThrown")
        errors.push(msg.params.exceptionDetails);
    };
    const cdp = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const id = ++seq;
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    const js = async (expression) => {
      const result = await cdp("Runtime.evaluate", {
        expression,
        awaitPromise: true,
        returnByValue: true,
      });
      assert.ok(
        !result.exceptionDetails,
        JSON.stringify(result.exceptionDetails),
      );
      return result.result.value;
    };
    const until = async (expression, label) => {
      for (let i = 0; i < 300; i++) {
        if (await js(expression)) return;
        await delay(50);
      }
      assert.fail(`${label}: ${await js("document.body.innerText")}`);
    };
    const viewport = (width) =>
      cdp("Emulation.setDeviceMetricsOverride", {
        width,
        height: 1000,
        deviceScaleFactor: 1,
        mobile: width < 500,
      });
    const screenshot = async (name) => {
      if (!process.env.QEC_SCREENSHOTS_DIR) return;
      fs.mkdirSync(process.env.QEC_SCREENSHOTS_DIR, { recursive: true });
      await js(
        "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
      );
      const result = await cdp("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
      });
      const file = path.join(process.env.QEC_SCREENSHOTS_DIR, name + ".png");
      fs.writeFileSync(file, Buffer.from(result.data, "base64"));
      console.log(`Screenshot: ${file}`);
    };
    await cdp("Network.enable");
    await cdp("Runtime.enable");
    await viewport(1280);
    await cdp("Page.navigate", { url: process.env.QEC_WEB_URL });
    await until(
      'document.querySelectorAll("#lattice .qubit").length === 17',
      "initial lattice",
    );
    assert.equal(posts.length, 0);
    assert.equal(await js('document.querySelector(".toolbar").previousElementSibling.id'), "physical-scroll");
    assert.equal(await js('document.querySelector("#scenario").tagName'), "UL");
    assert.equal(await js('document.querySelector("#circuit-text").closest("details")'), null);
    assert.equal(await js('document.querySelector("#circuit-template").closest("section").id'), "circuit-editor");
    assert.equal(await js('document.querySelector("#seed").closest("section").id'), "configure");
    assert.match((await js('document.querySelector("#boundary-note").textContent')).replace(/\s+/g, " "), /r0: first.*tick 7.*r1: second.*tick 14.*r2: third.*tick 21.*r3: final.*also tick 21/);
    assert.equal(
      await js('document.querySelector("#advanced").open'),
      false,
    );
    assert.equal(await js('document.querySelector("#evidence").open'), false);
    assert.equal(
      await js(
        'document.querySelectorAll("#circuit-diagram .circuit-wire").length',
      ),
      1,
    );
    assert.match(
      await js('document.querySelector("#diagram-note").textContent'),
      /one encoded/,
    );
    assert.equal(
      await js("getComputedStyle(document.body).backgroundColor"),
      "rgb(242, 242, 237)",
    );
    assert.equal(
      await js(
        'document.querySelector("#lattice").getBoundingClientRect().top < 1000',
      ),
      true,
    );
    await screenshot("paper-default-desktop");
    assert.equal(await js('document.querySelector("#circuit-text").getBoundingClientRect().height > 80'), true);
    assert.match(await js('document.querySelector("#circuit-text").value'), /QUBIT_COORDS/);
    const suppliedExamples = await js('fetch("/api/layout").then(r=>r.json()).then(d=>d.examples)');
    const exampleIds = suppliedExamples.map(e => e.id);
    assert.equal(exampleIds.length, 2);
    for (const choice of exampleIds) {
      await js(`document.querySelector('#circuit-template').value='${choice}';document.querySelector('#circuit-template').dispatchEvent(new Event('change'))`);
      assert.equal(await js('document.querySelector("#circuit-template").value'), choice);
      assert.ok(await js('document.querySelector("#logical-text").value.length > 0'));
      assert.equal(await js('document.querySelectorAll("#lattice .qubit").length'), 0, "never relabel old memory geometry as selected input");
      assert.match(await js('document.querySelector("#grid-note").textContent'), /Run/);
      assert.equal(posts.length, 0, "preset selection is local");
    }
    await js(`document.querySelector('#circuit-template').value='surface_code:rotated_memory_z';document.querySelector('#circuit-template').dispatchEvent(new Event('change'));document.querySelector('#circuit-text').dispatchEvent(new Event('input'))`);
    assert.equal(await js('document.querySelector("#circuit-template").value'), "custom");
    assert.equal(posts.length, 0);
    await js(`document.querySelector('#circuit-template').value='surface_code:rotated_memory_z';document.querySelector('#circuit-template').dispatchEvent(new Event('change'))`);

    for (const pauli of ["X", "Y", "Z"]) {
      await js(
        `document.querySelector('[data-pauli=${pauli}]').click();document.querySelector('#fault-tick').value=2;document.querySelector('#lattice [data-qubit]').click()`,
      );
      assert.match(
        await js('document.querySelector("#scenario").textContent'),
        new RegExp(`${pauli}.*tick 2`),
      );
    }
    assert.equal(posts.length, 0, "fault editing is local");
    await js(
      'document.querySelector("#circuit-template").value="custom";document.querySelector("#circuit-template").dispatchEvent(new Event("change"))',
    );
    const run = async (circuit, logical = "") => {
      await js(
        `document.querySelector('#circuit-text').value=${JSON.stringify(circuit)};document.querySelector('#logical-text').value=${JSON.stringify(logical)};document.querySelector('#circuit-text').dispatchEvent(new Event('input'));document.querySelector('#run').click()`,
      );
      await until('!document.querySelector("#run").disabled', "run finished");
      assert.equal(
        await js('document.querySelector("#play").disabled'),
        false,
        await js('document.querySelector("#status").textContent'),
      );
    };
    await run(
      "QUBIT_COORDS(-2, 3) 0\nQUBIT_COORDS(4, 9) 1\nR 0 1\nH 0\nTICK\nH 0\nCX 0 1\nX_ERROR(1) 1\nM 0 1\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]",
    );
    assert.equal(
      await js('document.querySelectorAll("#lattice .qubit").length'),
      2,
    );
    assert.equal(
      await js(
        'document.querySelectorAll("#circuit-diagram .circuit-wire").length',
      ),
      2,
    );
    assert.match(
      await js('document.querySelector("#diagram-note").textContent'),
      /No logical.*mapping/i,
    );
    assert.match(
      await js('document.querySelector("#grid-note").textContent'),
      /QUBIT_COORDS/,
    );
    const count = posts.length;
    await js('document.querySelector("#play").click()');
    assert.equal(await js('document.querySelector("#scrubber").value'), "1");
    await js('document.querySelector("#play").click()');
    const tick = await js('document.querySelector("#scrubber").value');
    await delay(800);
    assert.equal(await js('document.querySelector("#scrubber").value'), tick);
    await js(
      'document.querySelector("#scrubber").value=0;document.querySelector("#scrubber").dispatchEvent(new Event("input"));document.querySelector("#step").click()',
    );
    assert.equal(
      posts.length,
      count,
      "replay, pause, seek and step are network-free",
    );
    await delay(150);
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector("#lattice .has-error")).backgroundColor',
      ),
      "rgb(244, 189, 97)",
    );
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector("#timeline .fired")).backgroundColor',
      ),
      "rgb(233, 144, 134)",
    );
    assert.match(
      await js('document.querySelector("#result").textContent'),
      /2147483648/,
    );
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector("#circuit-diagram .gate.active rect")).fill',
      ),
      "rgb(173, 221, 246)",
    );
    await screenshot("paper-input-two");
    await js(`document.querySelector('[data-pauli=Z]').click();document.querySelector('#fault-tick').value=1;document.querySelector('#lattice [data-qubit="1"]').click()`);
    assert.equal(posts.length, count, "custom injection is local until Run");
    assert.match(await js('document.querySelector("#scenario li").textContent'), /Z on q1 at tick 1/);
    await js('document.querySelector("#run").click()');
    await until('!document.querySelector("#play").disabled', "injected custom replay");
    assert.deepEqual(JSON.parse(posts.at(-1).postData).faults, [{tick:1,qubit:1,pauli:"Z"}]);
    assert.match(await js('document.querySelector("#scenario li").textContent'), /Z on q1 at tick 1/, "returned layout preserves faults");
    await run(
      "R 0 1 2 3 4 5\nH 2\nTICK\nH 2\nX_ERROR(1) 5\nM 5\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]",
      "H 0\nS 0\nCX 0 1",
    );
    assert.equal(
      await js('document.querySelectorAll("#lattice .qubit").length'),
      6,
    );
    assert.equal(
      await js(
        'document.querySelectorAll("#circuit-diagram .circuit-wire").length',
      ),
      2,
    );
    assert.equal(
      await js(
        'document.querySelectorAll("#circuit-diagram [data-gate=CX] .control").length',
      ),
      1,
    );
    assert.match(
      await js('document.querySelector("#diagram-note").textContent'),
      /as supplied.*mapping not verified/i,
    );
    assert.match(
      await js('document.querySelector("#grid-note").textContent'),
      /Index grid/,
    );
    await screenshot("paper-logical-and-physical");
    await run(
      `R ${Array.from({ length: 1024 }, (_, i) => i).join(" ")}\nTICK\nX_ERROR(1) 1023\nM 1023\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]`,
    );
    assert.equal(
      await js('document.querySelectorAll("#lattice .qubit").length'),
      1024,
    );
    assert.equal(
      await js(
        'document.querySelectorAll("#circuit-diagram .circuit-wire").length',
      ),
      1024,
    );
    assert.equal(
      await js('!!document.querySelector("#lattice [data-qubit=\\"1023\\"]")'),
      true,
    );
    assert.doesNotMatch(
      await js('document.querySelector("#grid-note").textContent'),
      /omit|first 64/i,
    );
    assert.equal(
      await js(
        'document.querySelector("#physical-scroll").getBoundingClientRect().height <= 472',
      ),
      true,
    );
    assert.equal(
      await js(
        'document.querySelector("#diagram-scroll").getBoundingClientRect().height <= 432',
      ),
      true,
    );
    for (const width of [1280, 820, 390, 360]) {
      await viewport(width);
      assert.equal(
        await js("document.documentElement.scrollWidth > innerWidth"),
        false,
        `overflow at ${width}`,
      );
      assert.equal(
        await js(
          'document.querySelector("#physical-scroll").scrollHeight > document.querySelector("#physical-scroll").clientHeight',
        ),
        true,
      );
    }
    await js('document.querySelector("#advanced").open=true');
    assert.equal(
      await js("document.documentElement.scrollWidth > innerWidth"),
      false,
      "expanded editor fits phone",
    );
    await js(
      'const grid=document.querySelector("#physical-scroll");grid.scrollTo(grid.scrollWidth,grid.scrollHeight);grid.scrollIntoView({behavior:"instant",block:"start"})',
    );
    assert.equal(
      await js(
        '(() => {const q=document.querySelector("#lattice [data-qubit=\\"1023\\"]").getBoundingClientRect(), box=document.querySelector("#physical-scroll").getBoundingClientRect();return q.left>=box.left && q.right<=box.right && q.top>=box.top && q.bottom<=box.bottom})()',
      ),
      true,
      "last physical qubit is reachable inside the scroll viewport",
    );
    await screenshot("paper-dense-360");
    await js(
      'const diagram=document.querySelector("#diagram-scroll");diagram.scrollTo(0,0);diagram.scrollIntoView({behavior:"instant",block:"start"})',
    );
    await screenshot("paper-dense-input-360");
    assert.equal(
      await js(
        'document.querySelector("#circuit-diagram .circuit-wire").getBoundingClientRect().top >= document.querySelector("#diagram-scroll").getBoundingClientRect().top',
      ),
      true,
      "first input wire is reachable",
    );
    // These small unencoded fixtures are compiler/UI smoke tests, not presets.
    for (const [name, count] of [["bare_phase_bell", 2], ["bare_two_repetition_echo", 6]]) {
      await run(fs.readFileSync(path.join(__dirname, "fixtures", name + ".stim"), "utf8"));
      assert.equal(await js('document.querySelectorAll("#lattice .qubit").length'), count);
    }
    let runnableExamples = 0;
    for (const choice of exampleIds) {
      const before = posts.length;
      await js(`document.querySelector('#circuit-template').value='${choice}';document.querySelector('#circuit-template').dispatchEvent(new Event('change'))`);
      assert.equal(posts.length, before, "named selection never runs");
      assert.equal(await js('document.querySelector("#play").disabled'), true);
      assert.match(await js('document.querySelector("#scenario").textContent'), /No faults/);
      const entry = suppliedExamples.find(e => e.id === choice);
      if (entry.decoder_compatible === false) {
        assert.equal(await js('document.querySelector("#run").disabled'), true);
        assert.equal(await js('document.querySelector("#circuit-warning").textContent'), entry.decoder_limitation);
        await js('document.querySelector("#run").click()');
        assert.equal(posts.length, before, "unsupported encoding fails closed without decoder I/O");
        continue;
      }
      runnableExamples++;
      const selectedText = await js('document.querySelector("#circuit-text").value');
      const selectedLogical = await js('document.querySelector("#logical-text").value');
      await js('document.querySelector("#run").click()');
      await until('!document.querySelector("#run").disabled', "encoded example finished");
      assert.equal(await js('document.querySelector("#play").disabled'), false, await js('document.querySelector("#status").textContent'));
      assert.ok(await js('document.querySelectorAll("#lattice .qubit").length > 17'), "encoded two-logical-qubit example is not a bare two-qubit circuit");
      assert.equal(posts.at(-1).url.endsWith("/api/circuit-run"), true);
      assert.equal(JSON.parse(posts.at(-1).postData).circuit, selectedText);
      assert.equal(JSON.parse(posts.at(-1).postData).logical_circuit, selectedLogical);
      assert.match(await js('document.querySelector("#diagram-title").textContent'), /Known encoded example/);
      await js('document.querySelector("#logical-text").value += "\\nI 0";document.querySelector("#logical-text").dispatchEvent(new Event("input"))');
      assert.match(await js('document.querySelector("#diagram-note").textContent'), /mapping not verified/);
      assert.equal(posts.length, before + 1, "logical edits do not run or retain a verified mapping claim");
    }
    assert.deepEqual(errors, []);
    assert.equal(posts.length, 6 + runnableExamples);
    assert(posts.every((p) => p.url.endsWith("/api/circuit-run")));
    console.log(
      "Verified: paper lattice, initial no POST, visible editor, fault editing, 2/6 qubits, bit31, supplied logical view, full 1024-qubit grid and diagram, bounded scroll, local replay, computed colors, 360px layout.",
    );
  },
);
