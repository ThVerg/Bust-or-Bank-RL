"""Make a checkpoint the bot the web app serves, keeping the old one.

    python -m flip7.promote runs/r2/latest.pt

1. copies the current models/flip7_rl.pt to models/archive/ (named after its run and version),
2. exports the checkpoint as models/flip7_rl.pt with the same title and blurb, recording where it
   came from (path and SHA-256),
3. asks the running web app (--server, default http://localhost:8077) to reload its bots. Games in
   progress keep the bots they started with; new games get the new network.
"""
import argparse
import hashlib
import os
import shutil
import urllib.request

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("--as", dest="name", default="flip7_rl")
    ap.add_argument("--server", default="http://localhost:8077", help="'' to skip the reload")
    a = ap.parse_args()
    out = os.path.join(ROOT, "models", f"{a.name}.pt")
    title, blurb = "Bust or Bank RL", None
    if os.path.exists(out):
        old = torch.load(out, map_location="cpu", weights_only=False)
        title, blurb = old.get("title", title), old.get("blurb")
        run = os.path.basename(os.path.dirname(old["source"]["path"])) if old.get("source") else "prev"
        os.makedirs(os.path.join(ROOT, "models", "archive"), exist_ok=True)
        dest = os.path.join(ROOT, "models", "archive", f"{a.name}_{run}_ver{old.get('version')}.pt")
        if not os.path.exists(dest):
            shutil.copy2(out, dest)
        print(f"archived the current {a.name} as {os.path.relpath(dest, ROOT)}")
    ckpt = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    ckpt["title"] = title
    if blurb:
        ckpt["blurb"] = blurb
    ckpt["source"] = {"path": os.path.relpath(os.path.abspath(a.checkpoint), ROOT), "sha256": sha256(a.checkpoint)}
    tmp = out + ".tmp"
    torch.save(ckpt, tmp)
    os.replace(tmp, out)
    print(f"wrote {os.path.relpath(out, ROOT)} from {ckpt['source']['path']} (version {ckpt.get('version')})")
    if a.server:
        req = urllib.request.Request(a.server.rstrip("/") + "/api/reload-bots", method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"web app reloaded its bots (HTTP {r.status})")


if __name__ == "__main__":
    main()
