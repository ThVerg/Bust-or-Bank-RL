"""Do the difficulty levels hold up under the other rules the app offers?

    python -m flip7.conditions --seeds 200 --workers 4 --out analysis/conditions.json

The bots were trained on Brutal Mode to 200 points, but the app also offers Standard rules and
other targets. For each rule set this runs the paired benchmark (flip7.benchmark) on tables of
SmartBots for two steps of the difficulty ladder, Shark (the network) against Rookie (an early
snapshot) and Boss (network + search) against Shark, at 2 and 4 players.
"""
from __future__ import annotations

import argparse
import json

from .benchmark import provenance, run

CONDITIONS = [("Brutal, to 200", True, 200), ("Standard, to 200", False, 200),
              ("Brutal, to 100", True, 100), ("Brutal, to 300", True, 300)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/flip7_rl.pt")
    ap.add_argument("--rookie", default="models/rl_rookie.pt")
    ap.add_argument("--players", default="2,4")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="analysis/conditions.json")
    a = ap.parse_args()
    pairs = [("Shark vs Rookie", f"nn:{a.model}", f"nn:{a.rookie}"),
             ("Boss vs Shark", f"search:{a.model}", f"nn:{a.model}")]
    rows = []
    for label, brutal, target in CONDITIONS:
        for name, cand, inc in pairs:
            for n in [int(x) for x in a.players.split(",")]:
                r = run(cand, inc, n, "smart", a.seeds, workers=a.workers, brutal=brutal, target=target)
                rows.append({"condition": label, "pair": name, **r})
                print(f"{label:17s} {name:16s} {n}p  {r['candidate']:.3f} vs {r['incumbent']:.3f}  "
                      f"diff {r['diff']:+.3f} ± {r['ci95']:.3f}", flush=True)
    with open(a.out, "w") as f:
        json.dump({"seeds": a.seeds, "lineup": "smart", "checkpoints": provenance([a.model, a.rookie]),
                   "rows": rows}, f, indent=1)


if __name__ == "__main__":
    main()
