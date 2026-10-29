"""Score bots' moves on fresh positions, decision kind by decision kind.

    python -m flip7.probe --ref models/flip7_rl.pt --bots nn:models/flip7_rl.pt,boss:models/flip7_rl.pt,smart

Positions come from games the reference network plays against itself (2-6 players). At a sample of
decisions of each kind, every bot picks a move, and every legal move is scored by rollouts to the end of
the round on ``k`` shared deck orders (the reference network plays the rest of the round, its value head
scores the next round's start). A bot's *regret* is how much win chance its move gives up against the best
move, in points. Game benchmarks can't see a change to a decision that comes up once or twice a game;
this can.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .engine import DECISION_NAMES, Game
from .evaluate import make_bot

KINDS = "deliver,shakedown,bounty,dare,pay,spite,target,modifier,steal,discard,flip7,hit_stay"


def _work(args):
    ref, specs, kinds, per, k, seed, n = args
    import torch
    torch.set_num_threads(1)
    from .search import RolloutBot
    play = make_bot(f"nn:{ref}")
    bots = {s: make_bot(s, seed=seed) for s in specs}
    truth = RolloutBot(play.model, k=k, max_actions=10 ** 4, seed=seed + 1)  # every legal move: a bot may pick any
    rng = random.Random(seed)
    got = defaultdict(list)
    games = 0
    while min(len(got[x]) for x in kinds) < per and games < 20 * per:
        g = Game(n, seed=rng.randrange(1 << 30))
        games += 1
        while not g.over:
            name = DECISION_NAMES[g.decision.kind]
            p = 0.05 if name == "hit_stay" else 0.5  # spread the samples over many games
            if name in kinds and len(got[name]) < per and len(g.legal()) > 1 and rng.random() < p:
                q = truth.evaluate(g)
                best = max(q.values())
                got[name].append({s: best - q[b.act(g)] for s, b in bots.items()})
            g.step(play.act(g))
    return {x: rs for x, rs in got.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="network that plays the games and the rollouts")
    ap.add_argument("--bots", required=True, help="comma-separated bot specs to score (see flip7.evaluate)")
    ap.add_argument("--kinds", default=KINDS)
    ap.add_argument("--per", type=int, default=4, help="positions per kind per job")
    ap.add_argument("--jobs", type=int, default=30, help="jobs, cycling through 2-6 players")
    ap.add_argument("--k", type=int, default=192, help="rollout deck orders per position")
    ap.add_argument("--seed", type=int, default=9000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    specs, kinds = a.bots.split(","), [x for x in a.kinds.split(",") if x]
    jobs = [(a.ref, specs, kinds, a.per, a.k, a.seed + i, 2 + i % 5) for i in range(a.jobs)]
    rows = defaultdict(list)
    with ProcessPoolExecutor(a.workers) as ex:
        for part in ex.map(_work, jobs):
            for x, rs in part.items():
                rows[x] += rs
    out = {}
    print(f"{'decision':10s} {'n':>4s}  " + "  ".join(f"{s[-28:]:>28s}" for s in specs))
    for x in kinds:
        if not rows[x]:
            continue
        r = {s: 100 * np.array([row[s] for row in rows[x]]) for s in specs}
        out[x] = {"n": len(rows[x]), "regret": {s: {"mean": float(v.mean()), "se": float(v.std(ddof=1) / np.sqrt(len(v)))}
                                                for s, v in r.items()}}
        print(f"{x:10s} {len(rows[x]):4d}  " + "  ".join(
            f"{v.mean():20.2f} ± {v.std(ddof=1) / np.sqrt(len(v)):.2f}" for v in r.values()))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"ref": a.ref, "k": a.k, "seed": a.seed, "kinds": out}, f, indent=1)


if __name__ == "__main__":
    main()
