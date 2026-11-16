const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

test(
  "explicit Run creates evidence; Replay is local and edits invalidate it",
  {
    skip: !process.env.QEC_WEB_URL,
    timeout: 30000,
  },
  async (t) => {
    const profile = fs.mkdtempSync(
      path.join(process.env.TMPDIR || os.tmpdir(), "qec-ui-chrome-"),
    );
    const chrome = spawn(
      process.env.CHROME || "google-chrome",
      [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--no-first-run",
        "--remote-debugging-port=0",
        `--user-data-dir=${profile}`,
        "about:blank",
      ],
      { stdio: ["ignore", "ignore", "pipe"] },
    );
    t.after(async () => {
      chrome.kill();
      await new Promise((r) => chrome.once("exit", r));
      fs.rmSync(profile, { recursive: true, force: true });
    });
    let stderr = "";
    chrome.stderr.on("data", (d) => {
      stderr += d;
    });
    for (let i = 0; !stderr.includes("DevTools listening on ") && i < 100; i++)
      await delay(50);
    const endpoint = stderr.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
    assert.ok(endpoint, stderr);
    const target = await (
      await fetch(`http://${new URL(endpoint).host}/json/new?about:blank`, {
        method: "PUT",
      })
    ).json();
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });
    t.after(() => ws.close());
    let id = 0;
    const requests = new Map();
    const errors = [];
    const posts = [];
    let holdRun = false,
      heldRequest;
    ws.onmessage = ({ data }) => {
      const message = JSON.parse(data);
      if (message.id) {
        const entry = requests.get(message.id);
        requests.delete(message.id);
        message.error
          ? entry.reject(Error(JSON.stringify(message.error)))
          : entry.resolve(message.result);
      } else if (
        message.method === "Network.requestWillBeSent" &&
        message.params.request.method === "POST"
      )
        posts.push(message.params.request);
      else if (message.method === "Runtime.exceptionThrown")
        errors.push(message.params.exceptionDetails.text);
      else if (message.method === "Fetch.requestPaused") {
        if (holdRun) {
          heldRequest = message.params.requestId;
          return;
        }
        cdp("Fetch.fulfillRequest", {
          requestId: message.params.requestId,
          responseCode: 503,
          responseHeaders: [
            { name: "Content-Type", value: "application/json" },
          ],
          body: Buffer.from(
            JSON.stringify({ error: "Regression fixture: FPGA unavailable" }),
          ).toString("base64"),
        });
      }
    };
    const cdp = (method, params = {}) =>
      new Promise((resolve, reject) => {
        requests.set(++id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    const js = async (expression) => {
      const result = await cdp("Runtime.evaluate", {
        expression,
        returnByValue: true,
        awaitPromise: true,
      });
      assert.ok(
        !result.exceptionDetails,
        JSON.stringify(result.exceptionDetails),
      );
      return result.result.value;
    };
    const until = async (expression, description) => {
      for (let i = 0; i < 150; i++) {
        if (await js(expression)) return;
        await delay(50);
      }
      assert.fail(`${description}: ${await js("document.body.innerText")}`);
    };
    await cdp("Runtime.enable");
    await cdp("Network.enable");
    await cdp("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp("Page.navigate", { url: process.env.QEC_WEB_URL });
    await until(
      'document.getElementById("run") && !document.getElementById("run").disabled',
      "configuration ready",
    );
    assert.equal(await js('document.getElementById("play").disabled'), true);
    await delay(200);
    assert.equal(
      await js(
        'document.getElementById("lattice").getBoundingClientRect().top < 1000',
      ),
      true,
      "configuration keeps the lattice prominent on desktop",
    );
    assert.equal(posts.length, 0, "page load must never run");
    assert.equal(await js('document.querySelector("#example")'), null);
    assert.equal(
      await js('document.querySelector("#scenario").textContent'),
      "No faults",
    );
    assert.equal(await js('document.getElementById("seed").value'), "20261107");
    assert.deepEqual(
      await js(
        '[...document.querySelectorAll(".settings input:not(#seed):not(#added-noise)")].map(e => e.value)',
      ),
      ["0.001", "0.001", "0.001", "0.001"],
    );
    await js(
      '[...document.querySelectorAll(".settings input:not(#seed):not(#added-noise)")].forEach(e => {e.value="0";e.dispatchEvent(new Event("input"));})',
    );
    assert.equal(posts.length, 0, "settings edits must never run");
    // Inject the regression fault explicitly; the page must start fault-free.
    await js(
      'document.querySelector("#fault-tick").value=8;document.querySelector("#lattice [data-qubit=\\"10\\"]").click()',
    );
    await js('document.getElementById("run").click()');
    await until(
      'document.getElementById("play") && !document.getElementById("play").disabled && document.querySelectorAll(".qubit").length === 17',
      "ready",
    );
    await js('document.getElementById("play").click()');
    assert.equal(await js('document.getElementById("play").textContent'), "⏸");
    assert.equal(
      await js('document.getElementById("play").getAttribute("aria-label")'),
      "Pause",
    );
    assert.equal(
      await js('document.getElementById("position").textContent'),
      "1 / 22",
      "Play must advance immediately, not look inert",
    );
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector(".qubit.active")).backgroundColor',
      ),
      "rgb(56, 198, 196)",
      "active gates have a distinct teal fill",
    );
    assert.match(
      await js('document.querySelector(".qubit.active").textContent'),
      /H/,
      "active gate name visible on qubit",
    );
    assert.match(
      await js('document.getElementById("scenario").textContent'),
      /X.*q10.*8/,
      "explicitly injected regression fault is labeled",
    );
    await js('document.getElementById("speed").value="4"');
    await until('document.querySelector(".has-error")', "fault visible");
    await delay(150);
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector(".has-error")).backgroundColor',
      ),
      "rgb(244, 189, 97)",
    );
    await until(
      'document.querySelector(".detector.fired:not(.cleared)")',
      "measurement-time detector flips visible",
    );
    await delay(150);
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector(".detector.fired")).backgroundColor',
      ),
      "rgb(233, 144, 134)",
    );
    await until(
      'document.getElementById("tick-label").textContent === "Host correction"',
      "host correction reached",
    );
    assert.ok(await js('!!document.querySelector(".has-fix")'));
    await delay(150);
    assert.equal(
      await js(
        'getComputedStyle(document.querySelector(".has-fix small")).backgroundColor',
      ),
      "rgb(191, 230, 205)",
    );
    assert.equal(
      await js(
        'JSON.parse(document.getElementById("technical").textContent).residual_observable',
      ),
      0,
    );
    assert.equal(
      await js('document.querySelectorAll(".detector.cleared").length'),
      2,
    );
    assert.match(
      await js('document.getElementById("result").textContent'),
      /Z preserved/,
    );
    await js(
      'document.getElementById("scrubber").value=13; document.getElementById("scrubber").dispatchEvent(new Event("input"))',
    );
    assert.equal(
      await js('document.querySelectorAll(".detector.fired").length'),
      0,
      "backward scrub hides future detector flips",
    );
    await js(
      'document.getElementById("scrubber").value=22; document.getElementById("scrubber").dispatchEvent(new Event("input"))',
    );
    await js('document.getElementById("play").click()');
    assert.equal(
      await js('document.getElementById("position").textContent'),
      "1 / 22",
      "Play replays from completed state",
    );
    await js(
      'document.getElementById("play").click(); document.getElementById("back").click(); document.getElementById("step").click()',
    );
    assert.equal(await js('document.getElementById("play").textContent'), "▶");
    await delay(100);
    assert.equal(
      posts.length,
      1,
      "Replay, Pause, back/step, backward scrub and restart must never request decoding",
    );
    assert.match(posts[0].url, /\/api\/run$/);
    assert.equal(JSON.parse(posts[0].postData).seed, 20261107);
    await js('document.getElementById("reset").click()');
    assert.equal(await js('document.getElementById("play").disabled'), true);
    assert.match(
      await js('document.getElementById("status").textContent'),
      /^$/,
    );
    assert.equal(
      await js('document.getElementById("technical").textContent'),
      "",
    );
    await delay(100);
    assert.equal(posts.length, 1, "clear must never run");

    await js('document.querySelector(".data-qubit").click()');
    await delay(100);
    assert.equal(posts.length, 1, "fault edits must never run");
    await js(
      'document.getElementById("reset").click(); document.getElementById("run").click()',
    );
    await until(
      '!document.getElementById("play").disabled',
      "explicit clear run ready",
    );
    assert.equal(
      await js(
        'JSON.parse(document.getElementById("technical").textContent).faults.length',
      ),
      0,
    );
    assert.deepEqual(errors, []);
    await cdp("Fetch.enable", {
      patterns: [{ urlPattern: "*/api/run", requestStage: "Request" }],
    });
    await js('document.getElementById("run").click()');
    await until(
      'document.getElementById("status").textContent.includes("Regression fixture: FPGA unavailable")',
      "source failure visible",
    );
    assert.equal(await js('document.getElementById("play").disabled'), true);
    assert.match(
      await js('document.getElementById("source").textContent'),
      /unavailable/,
    );
    assert.ok(
      await js(
        'document.getElementById("status").getBoundingClientRect().top < document.getElementById("lattice").getBoundingClientRect().top',
      ),
    );
    await cdp("Fetch.disable");
    await js('document.getElementById("run").click()');
    await until(
      '!document.getElementById("play").disabled',
      "source recovered",
    );
    holdRun = true;
    await cdp("Fetch.enable", {
      patterns: [{ urlPattern: "*/api/run", requestStage: "Request" }],
    });
    await js('document.getElementById("run").click()');
    for (let i = 0; !heldRequest && i < 100; i++) await delay(20);
    assert.ok(heldRequest);
    assert.equal(
      await js(
        'document.getElementById("run").disabled && document.getElementById("seed").disabled && document.querySelector(".data-qubit").disabled && document.getElementById("play").disabled',
      ),
      true,
    );
    await js(
      'document.getElementById("seed").value="7"; document.getElementById("seed").dispatchEvent(new Event("input"))',
    );
    assert.equal(
      await js('document.getElementById("run").disabled'),
      true,
      "an invalidated request still blocks overlapping runs",
    );
    await cdp("Fetch.continueRequest", { requestId: heldRequest });
    await cdp("Fetch.disable");
    await delay(200);
    assert.equal(
      await js('document.getElementById("play").disabled'),
      true,
      "stale response cannot restore replay",
    );
    assert.match(
      await js('document.getElementById("status").textContent'),
      /^$/,
    );
    await until(
      '!document.getElementById("run").disabled',
      "stale request finished",
    );
    await js('document.getElementById("run").click()');
    await until(
      '!document.getElementById("play").disabled',
      "run after stale reply",
    );
    assert.match(
      await js('document.getElementById("run-summary").textContent'),
      /seed 7.*prediction.*observable.*cycles/,
    );
    for (const width of [1280, 820, 760, 600, 390, 360]) {
      await cdp("Emulation.setDeviceMetricsOverride", {
        width,
        height: 900,
        deviceScaleFactor: 1,
        mobile: width === 390,
      });
      await until(
        "document.documentElement.scrollWidth <= innerWidth",
        `responsive lattice settled at ${width}`,
      );
      assert.equal(
        await js("document.documentElement.scrollWidth > innerWidth"),
        false,
        `no overflow at ${width}`,
      );
      await js(
        'document.getElementById("play").scrollIntoView({behavior:"instant",block:"center"})',
      );
      assert.ok(
        await js(
          'document.getElementById("play").getBoundingClientRect().bottom < innerHeight',
        ),
        `Play visible at ${width}`,
      );
    }
    if (process.env.QEC_STALE_URL) {
      await cdp("Page.navigate", { url: process.env.QEC_STALE_URL });
      await until(
        'document.getElementById("status")?.textContent.includes("Restart the QEC web server")',
        "stale server actionable error",
      );
      assert.equal(await js('document.getElementById("play").disabled'), true);
      assert.equal(
        await js('document.getElementById("source").textContent'),
        "Unavailable",
      );
      assert.deepEqual(errors, []);
    }
    console.log(
      "Verified real API: explicit Run, network-free Replay, edit invalidation, gate/error/correction states and recovery.",
    );
  },
);
