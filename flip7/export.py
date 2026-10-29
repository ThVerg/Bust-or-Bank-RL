"""Copy a training checkpoint into models/ so the web app serves it.

    python -m flip7.export runs/bob2/latest.pt --as flip7_rl --title "Bust or Bank RL"
"""
import argparse
import os

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("--as", dest="name", default="flip7_rl")
    ap.add_argument("--title", default="Bust or Bank RL")
    ap.add_argument("--blurb", default="Self-play reinforcement learning bot. Counts every card and plays to win the game, not the round.")
    args = ap.parse_args()
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    ckpt["title"] = args.title
    ckpt["blurb"] = args.blurb
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    out = os.path.join(ROOT, "models", f"{args.name}.pt")
    tmp = out + ".tmp"
    torch.save(ckpt, tmp)
    os.replace(tmp, out)
    print(f"wrote {out} (version {ckpt.get('version')})")


if __name__ == "__main__":
    main()
