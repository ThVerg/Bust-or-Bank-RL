// Static build: runs the game rooms (web/browser.py over server/rooms.py) in Pyodide, off the page's
// thread. local.js sends {t: "call", id, fn, args}; replies are {t: "result"}, room messages {t: "ws"}
// and loading progress {t: "progress"}.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE + "pyodide.js");

const progress = (text, done = false) => postMessage({ t: "progress", text, done });

const host = (async () => {
  progress("Loading Python…");
  const py = await loadPyodide({ indexURL: PYODIDE });
  progress("Loading numpy…");
  await py.loadPackage("numpy");
  progress("Loading the bots…");
  const zip = await fetch(new URL("../py/app.zip", self.location)).then((r) => {
    if (!r.ok) throw new Error(`app.zip: HTTP ${r.status}`);
    return r.arrayBuffer();
  });
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  py.runPython("import sys; sys.path.insert(0, '/app')");
  const browser = py.pyimport("web.browser");
  const h = browser.Host("/app/models", (sid, text) => postMessage({ t: "ws", sid, text: text ?? null }));
  progress("Bots ready", true);
  return h;
})();
host.catch((e) => progress(`Could not load the bots: ${e.message}`, true));

// One call at a time, in order: a room message must not overtake the connect before it.
let queue = Promise.resolve();
onmessage = ({ data: m }) => {
  if (m.t !== "call") return;
  queue = queue.then(async () => {
    try {
      const value = await (await host)[m.fn](...m.args);
      postMessage({ t: "result", id: m.id, value: value ?? null });
    } catch (e) {
      postMessage({ t: "result", id: m.id, error: e.message || String(e) });
    }
  });
};
