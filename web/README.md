# The static build (GitHub Pages)

GitHub Pages only serves files, but the web app normally talks to a Python server: the rooms, the game
engine and the bots all live there. The static build runs that same Python in the browser instead, with
[Pyodide](https://pyodide.org) (CPython compiled to WebAssembly), so the site works with no server at all.

```bash
.venv/bin/python -m web.build                        # writes _site/ (needs torch to read the checkpoints)
python -m http.server --directory _site 8000         # then open http://localhost:8000
```

Every push to `main` runs the tests, builds the site and deploys it (`.github/workflows/site.yml`).

## How it works

```
page (server/static/app.js)
  │  api("/api/...") and the room's WebSocket go to local.js instead of the network
  ▼
web/local.js ── postMessage ──▶ web/worker.js (Web Worker)
                                  │  loads Pyodide + numpy from the jsDelivr CDN, unpacks py/app.zip
                                  ▼
                                web/browser.py ──▶ server/rooms.py, server/bots.py, flip7/
```

- **The same code as the server.** `web/browser.py` creates rooms with `server.rooms.create_room` and
  hands each room a stand-in WebSocket whose `send_text` posts the message back to the page. The game
  loop, pacing, win chances, the coach and the post-game review are the server's own.
- **No torch.** The bots only need `model.predict(obs, mask, n_players)`. In the browser that is
  `flip7.infer.NumpyNet`, the same forward pass in numpy, reading the weights from `.npz` files that the
  build exports from `models/*.pt`. A test checks that it matches torch.
- **No threads.** The server runs bot moves in a thread pool; here they run inline
  (`server.rooms.COMPUTE = None`), and the post-game review yields after every decision. The page stays
  responsive because the worker is separate from it.
- **Files the server would generate.** The bot list and the Insights data are written to
  `api/bots.json` and `api/insights.json` at build time, so the home page and Insights don't wait for
  Python to load.

`app.js` switches to `local.js` when `window.STATIC_SITE` is set, which only the built `index.html`
does; served by the real server, the same files talk to it as usual.

## What's in `_site/`

| Path | |
|---|---|
| `index.html` | The app's page with relative paths and `window.STATIC_SITE = true` |
| `static/` | `server/static` (without the design mockups) plus `local.js` and `worker.js` |
| `api/bots.json`, `api/insights.json` | What `/api/bots` and `/api/insights` would return |
| `py/app.zip` | `flip7/`, `server/rooms.py`, `server/bots.py`, `web/browser.py` and the networks as `.npz` |

## Differences from the server

- **No tables with friends.** Everything runs in one browser tab, so nobody else can join. The home page
  links to the instructions for running the server instead, and the lobby hides invites and open seats.
- **A game lives in its tab.** Leaving the table or reloading the page ends it.
- **First visit: about 13 MB.** Pyodide (about 5.5 MB), numpy (3 MB) and `app.zip` (4 MB, mostly the
  networks). Browsers cache them, so later visits start in a few seconds.
- **Slower bots.** Python in WebAssembly is a few times slower than native. Most Boss moves take a few
  hundredths of a second; a Swap, which it plays out 32 times, about half a second and now and then a
  few seconds.
- **A lighter post-game review.** The coach plays each reviewed decision out 24 times instead of 64, and
  reviews one decision at a time, so you can deal the next game while it works.
