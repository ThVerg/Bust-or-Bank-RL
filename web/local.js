// Static build (GitHub Pages): there is no server, so this stands in for the parts of it the page
// uses. The rooms run in a Web Worker (worker.js) with the real Python engine and bots; the bot list
// and the Insights data are files written by web/build.py. app.js loads this only when
// window.STATIC_SITE is set.
const worker = new Worker(new URL("./worker.js", import.meta.url));
const calls = new Map();
const sockets = new Map();
let nextId = 0;
let ready = false, failed = null, waiting = 0, progressText = "Loading the bots…";

// A pill at the bottom while someone is waiting for the bots to load (first visit: about 13 MB).
function showBoot() {
  let el = document.getElementById("bootbar");
  if (ready || (!waiting && !failed)) { el?.remove(); return; }
  if (!el) {
    el = document.createElement("div");
    el.id = "bootbar";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  const text = document.createElement("span");
  text.textContent = failed || progressText;
  el.replaceChildren(...(failed ? [] : [Object.assign(document.createElement("span"), { className: "spin" })]), text);
}

worker.onmessage = ({ data: m }) => {
  if (m.t === "result") {
    const c = calls.get(m.id);
    calls.delete(m.id);
    if (m.error) c?.reject(new Error(m.error));
    else c?.resolve(m.value);
  } else if (m.t === "ws") {
    const s = sockets.get(m.sid);
    if (!s) return;
    if (m.text == null) s._closed();
    else { s.readyState = 1; s.onmessage?.({ data: m.text }); }
  } else if (m.t === "progress") {
    progressText = m.text;
    if (m.done) { if (m.text === "Bots ready") ready = true; else failed = m.text; }
    showBoot();
  }
};

function call(fn, ...args) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const wait = !ready;
    if (wait) { waiting++; showBoot(); }
    const done = (f) => (v) => { if (wait) { waiting--; showBoot(); } f(v); };
    calls.set(id, { resolve: done(resolve), reject: done(reject) });
    worker.postMessage({ t: "call", id, fn, args });
  });
}

const getJSON = (path) => fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`); return r.json(); });

export async function api(path, body) {
  if (path === "/api/bots") return getJSON("api/bots.json");
  if (path === "/api/insights") return getJSON("api/insights.json");
  if (path === "/api/info") return { lan: [] };
  if (path === "/api/rooms") return body ? JSON.parse(await call("create_room", JSON.stringify(body))) : [];
  throw new Error(`${path} needs the server`);
}

// Enough of the WebSocket interface for app.js: readyState, send, close, onmessage, onclose.
export class Socket {
  constructor(room, token, name) {
    this.readyState = 0;
    this.sid = ++nextId;
    sockets.set(this.sid, this);
    call("connect", this.sid, room, token, name).then(() => { if (this.readyState === 0) this.readyState = 1; }, () => this._closed());
  }
  send(text) { if (this.readyState === 1) call("receive", this.sid, text); }
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    sockets.delete(this.sid);
    call("disconnect", this.sid);
  }
  _closed() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    sockets.delete(this.sid);
    this.onclose?.();
  }
}
