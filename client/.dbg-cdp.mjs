import { spawn } from "node:child_process";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const URL_ = process.argv[2] || "http://localhost:3000/plan";
const COOKIE =
  "kT6N7vWGA8c1jscPyW6iiGytaxrqTw31.TLv%2B8IafIibWWOiDdS3UcLQm087pCI5nDgdsVumVF2g%3D";

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    "--user-data-dir=" + process.env.TEMP + "\\dbg-chrome-profile",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--window-size=1400,1000",
    "about:blank",
  ],
  { stdio: "ignore" }
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getWsUrl() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      const j = await r.json();
      if (j.webSocketDebuggerUrl) return j.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("chrome did not start");
}

const ws = new WebSocket(await getWsUrl());
let id = 0;
const pending = new Map();
const logs = [];
const errors = [];

ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
    return;
  }
  if (m.method === "Runtime.consoleAPICalled") {
    const txt = m.params.args
      .map((a) => a.value ?? a.description ?? a.type)
      .join(" ");
    logs.push(`[${m.params.type}] ${txt}`);
  }
  if (m.method === "Runtime.exceptionThrown") {
    const d = m.params.exceptionDetails;
    errors.push(
      (d.exception?.description || d.text || "") +
        "\n  url=" +
        d.url +
        " line=" +
        d.lineNumber +
        " col=" +
        d.columnNumber
    );
  }
  if (m.method === "Log.entryAdded") {
    const e = m.params.entry;
    if (e.level === "error" || e.level === "warning")
      logs.push(`[log:${e.level}] ${e.text}`);
  }
});

function send(method, params = {}, sessionId) {
  return new Promise((resolve) => {
    const msg = { id: ++id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    pending.set(msg.id, resolve);
    ws.send(JSON.stringify(msg));
  });
}

await new Promise((r) => ws.addEventListener("open", r));

// attach to a page target
const { result: targets } = await send("Target.getTargets");
const page = targets.targetInfos.find((t) => t.type === "page");
const { result: attached } = await send("Target.attachToTarget", {
  targetId: page.targetId,
  flatten: true,
});
const S = attached.sessionId;

await send("Runtime.enable", {}, S);
await send("Log.enable", {}, S);
await send("Page.enable", {}, S);
await send("Network.enable", {}, S);

await send(
  "Network.setCookie",
  {
    name: "better-auth.session_token",
    value: COOKIE,
    domain: "localhost",
    path: "/",
    httpOnly: true,
    sameSite: "Lax",
  },
  S
);

await send("Page.navigate", { url: URL_ }, S);
await sleep(6000);

const { result: dom } = await send(
  "Runtime.evaluate",
  {
    expression: `(() => {
      const t = document.querySelector('[data-slot="card-title"]');
      return JSON.stringify({
        cardTitleHTML: t ? t.outerHTML : null,
        cardTitleParent: t && t.parentElement ? t.parentElement.outerHTML.slice(0,600) : null,
        bodyText: document.body.innerText.slice(0,300),
      });
    })()`,
    returnByValue: true,
  },
  S
);

console.log("=== EXCEPTIONS ===");
console.log(errors.length ? errors.join("\n---\n") : "(none)");
console.log("\n=== CONSOLE/LOG (errors+warns) ===");
console.log(
  logs.filter((l) => /error|warn|hydrat|mismatch|insertBefore/i.test(l)).slice(0, 40).join("\n") ||
    "(none)"
);
console.log("\n=== DOM ===");
console.log(dom?.value);

chrome.kill();
process.exit(0);
