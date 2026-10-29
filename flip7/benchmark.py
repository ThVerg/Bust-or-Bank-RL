"""Paired benchmark of a candidate checkpoint against the incumbent.

    python -m flip7.benchmark --candidate runs/r2/latest.pt --incumbent models/flip7_rl.pt \\
        --history runs/r1/pool/v000060.pt --players 2,4,6 --seeds 300 --split dev

For every seed, table line-up and seat, the candidate and the incumbent each play the *same*
game: same deck order, same opponents, same seat. The statistic is the paired difference in win
share, averaged over seats (seat rotation) and seeds, with a 95% interval computed over seeds
(one seed = one block of correlated games). Line-ups:

* ``self``  - everyone else is the incumbent (candidate share vs the fair 1/n)
* ``smart`` - everyone else is SmartBot
* ``mixed`` - incumbent, SmartBot, historical checkpoints and Hit-to-25, cycled to fill the table

Use ``--split dev`` while choosing checkpoints and ``--split final`` (a disjoint seed range)
once, to confirm a promotion.

Every game builds its bots afresh with seeds derived from the game seed and the seat, so search
and rollout bots (which draw random numbers) play the same way however games are split across
workers. The JSON output records each checkpoint's SHA-256 and the exact bot specs, because a
path like runs/r2/latest.pt can be overwritten later.
"""
from __future__ import annotations

import argparse
import hashlib
import time
import json
import math
import os
import random
from concurrent.futures import ProcessPoolExecutor

from .engine import Game, Rules

SPLIT_BASE = {"dev": 0, "final": 1_000_000_000}


def play(specs, seed, brutal=True, target=200, timed=None):
    """Win shares of one game with ``specs[p]`` in seat p. The seed fixes the deck order and each
    seat's bot randomness (fresh bots per game; the networks themselves are cached). ``timed``:
    a seat whose thinking time is added to the returned (seconds, decisions)."""
    from .evaluate import make_bot
    n = len(specs)
    rng = random.Random(seed)
    g = Game(n, rules=Rules(brutal=brutal, target=target), rng=rng, dealer=rng.randrange(n))
    bots = [make_bot(s, seed=(seed * 31 + k) % (1 << 31)) for k, s in enumerate(specs)]
    secs, moves = 0.0, 0
    while not g.over:
        p = g.decision.player
        t0 = time.perf_counter()
        a = bots[p].act(g)
        if p == timed:
            secs += time.perf_counter() - t0
            moves += 1
        g.step(a)
    return (g.returns(), secs, moves) if timed is not None else g.returns()


def lineup(kind, n, incumbent, history):
    if kind == "self":
        return [incumbent] * n
    if kind == "smart":
        return ["smart"] * n
    pool = [incumbent, "smart"] + [f"nn:{h}" for h in history] + ["threshold25"]
    return [pool[i % len(pool)] for i in range(n)]


def _game_seed(s, n):
    return s * 7919 + n * 104_729


def _job(args):
    import torch
    torch.set_num_threads(1)
    cand, inc, base, n, seeds, brutal, target = args
    out = []  # per seed: (mean candidate share, mean incumbent share, candidate seconds, decisions)
    for s in seeds:
        seed = _game_seed(s, n)
        c_tot = r_tot = secs = 0.0
        moves = 0
        ref_cache = {}
        for k in range(n):
            c_specs = list(base)
            c_specs[k] = cand
            r_specs = list(base)
            r_specs[k] = inc
            share, t, m = play(c_specs, seed, brutal, target, timed=k)
            c_tot += share[k]
            secs, moves = secs + t, moves + m
            key = tuple(r_specs)
            if key not in ref_cache:
                ref_cache[key] = play(r_specs, seed, brutal, target)
            r_tot += ref_cache[key][k]
        out.append((c_tot / n, r_tot / n, secs, moves))
    return out


def _spec(x):
    """A checkpoint path means the greedy network; anything with a colon is a full bot spec."""
    return x if ":" in x else f"nn:{x}"


def run(candidate, incumbent, n, kind, seeds, history=(), workers=3, split="dev", brutal=True, target=200):
    cand, inc = _spec(candidate), _spec(incumbent)
    base = lineup(kind, n, inc, history)
    first = SPLIT_BASE[split]
    seed_ids = list(range(first, first + seeds))
    chunks = [seed_ids[i::workers] for i in range(workers)]
    with ProcessPoolExecutor(workers) as ex:
        res = [r for part in ex.map(_job, [(cand, inc, base, n, c, brutal, target) for c in chunks if c]) for r in part]
    diffs = [r[0] - r[1] for r in res]
    m = sum(diffs) / len(diffs)
    sd = math.sqrt(sum((d - m) ** 2 for d in diffs) / max(len(diffs) - 1, 1))
    return {
        "lineup": kind, "n": n, "seeds": len(res), "games": len(res) * n,
        "candidate": sum(r[0] for r in res) / len(res),
        "incumbent": sum(r[1] for r in res) / len(res),
        "diff": m, "ci95": 1.96 * sd / math.sqrt(len(diffs)),
        "candidate_ms": 1000 * sum(r[2] for r in res) / max(1, sum(r[3] for r in res)),
        "rules": {"brutal": brutal, "target": target},
    }


def provenance(specs):
    """SHA-256 and size of every checkpoint the specs mention."""
    out = {}
    for spec in specs:
        path = spec.split(":", 1)[1] if ":" in spec else spec
        if os.path.isfile(path) and path not in out:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            out[path] = {"sha256": h.hexdigest(), "bytes": os.path.getsize(path)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True, help="checkpoint path, or a bot spec like search:<ckpt>")
    ap.add_argument("--incumbent", required=True)
    ap.add_argument("--history", default="", help="comma-separated older checkpoints for mixed tables")
    ap.add_argument("--players", default="2,4,6")
    ap.add_argument("--lineups", default="self,smart,mixed")
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--split", choices=SPLIT_BASE, default="dev")
    ap.add_argument("--json", default="")
    ap.add_argument("--standard", action="store_true", help="Standard rules instead of Brutal Mode")
    ap.add_argument("--target", type=int, default=200, help="points needed to win")
    a = ap.parse_args()
    history = [h for h in a.history.split(",") if h]
    rows = []
    for kind in a.lineups.split(","):
        for n in [int(x) for x in a.players.split(",")]:
            r = run(a.candidate, a.incumbent, n, kind, a.seeds, history, a.workers, a.split, not a.standard, a.target)
            rows.append(r)
            verdict = "better" if r["diff"] - r["ci95"] > 0 else "worse" if r["diff"] + r["ci95"] < 0 else "no clear difference"
            print(f"{kind:5s} {n}p  candidate {r['candidate']:.3f}  incumbent {r['incumbent']:.3f}  "
                  f"diff {r['diff']:+.3f} ± {r['ci95']:.3f}  ({r['games']} games each, {verdict}, "
                  f"{r['candidate_ms']:.1f} ms/decision)", flush=True)
    if a.json:
        specs = [_spec(a.candidate), _spec(a.incumbent)] + [f"nn:{h}" for h in history]
        with open(a.json, "w") as f:
            json.dump({"candidate": _spec(a.candidate), "incumbent": _spec(a.incumbent), "history": history,
                       "split": a.split, "seeds": a.seeds, "rules": {"brutal": not a.standard, "target": a.target},
                       "checkpoints": provenance(specs), "rows": rows}, f, indent=1)


if __name__ == "__main__":
    main()
