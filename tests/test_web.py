"""The static build: numpy inference, the rooms running without torch (as under Pyodide), the site."""
import json
import os
import random
import subprocess
import sys
import zipfile

import numpy as np

from flip7.encoding import encode
from flip7.engine import Game
from flip7.infer import load_npz, save_npz
from flip7.model import Net

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _export(net, path, **meta):
    save_npz({k: v.numpy() for k, v in net.state_dict().items()}, net.config, path, **meta)


def test_numpy_net_matches_torch(tmp_path):
    for net in (Net(32, 2), Net(32, 2, v_hidden=16, v_layers=2)):
        _export(net, tmp_path / "m.npz", title="T")
        np_net, meta = load_npz(tmp_path / "m.npz")
        assert meta["title"] == "T"
        g, rng = Game(4, rng=random.Random(3)), random.Random(4)
        obs, mask, n = [], [], []
        while not g.over and len(obs) < 30:
            o, m, _ = encode(g)
            obs.append(o)
            mask.append(m)
            n.append(g.n)
            g.step(rng.choice(g.legal()))
        args = np.stack(obs), np.stack(mask), np.array(n)
        for a, b in zip(net.predict(*args), np_net.predict(*args)):
            np.testing.assert_allclose(a, b, rtol=1e-4, atol=1e-4)


BROWSER_GAME = """
import asyncio, json, sys
sys.modules["torch"] = None  # as in the browser: any torch import fails
from web.browser import Host

async def main(models):
    sent = []
    host = Host(models, lambda sid, text: sent.append(text))
    spec = {"token": "t", "name": "T", "watch": True, "autostart": True,
            "seats": [{"kind": "bot", "bot_id": b} for b in ("search:m", "nn:m", "smart")]}
    rid = json.loads(await host.create_room(json.dumps(spec)))["id"]
    room = host.rooms[rid]
    room.pause_scale = 0
    await host.connect(1, rid, "t", "T")
    await asyncio.wait_for(room.task, 120)
    await asyncio.sleep(0.05)  # let the writer send the last state
    states = [json.loads(t) for t in sent if t]
    assert states[-1]["room"]["mode"] == "finished" and states[-1]["game"]["over"], states[-1]["room"]
    await host.disconnect(1)
    assert rid not in host.rooms
    print("ok", len(states))

asyncio.run(main(sys.argv[1]))
"""


def test_rooms_run_without_torch(tmp_path):
    _export(Net(32, 2), tmp_path / "m.npz", title="Test")
    r = subprocess.run([sys.executable, "-c", BROWSER_GAME, str(tmp_path)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("ok")


def test_static_site_build(tmp_path):
    from web.build import build

    out = tmp_path / "site"
    build(str(out))
    page = (out / "index.html").read_text()
    assert "window.STATIC_SITE = true" in page and '"/static/' not in page
    bots = json.loads((out / "api" / "bots.json").read_text())
    assert bots[0]["id"] == "search:flip7_rl"
    assert (out / "static" / "worker.js").exists() and (out / "static" / "local.js").exists()
    assert not (out / "static" / "mockups").exists()
    names = zipfile.ZipFile(out / "py" / "app.zip").namelist()
    assert {"web/browser.py", "server/rooms.py", "flip7/engine.py", "models/flip7_rl.npz"} <= set(names)
