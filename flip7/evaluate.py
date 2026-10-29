"""Head-to-head evaluation of bots, in parallel.

    python -m flip7.evaluate --hero search:models/flip7_rl.pt --villain smart --players 2,4 --games 1000

Bot specs: smart | random | threshold25 | nn:<ckpt> | search:<ckpt> | rollout[K][t<temp>]:<ckpt> |
adaptive[MAXK]:<ckpt> | boss[K][s]:<ckpt>.
The hero takes one seat (rotating), the villain takes all the others.
"""
from __future__ import annotations

import argparse
import math
import random
from concurrent.futures import ProcessPoolExecutor

from .engine import Game, Rules

_cache = {}


def make_bot(spec, seed=None):
    from .bots import RandomBot, SmartBot, ThresholdBot
    if spec == "smart":
        return SmartBot()
    if spec == "random":
        return RandomBot(seed)
    if spec.startswith("threshold"):
        return ThresholdBot(int(spec[9:]))
    kind, path = spec.split(":", 1)
    if path not in _cache:
        from .model import load
        _cache[path] = load(path)[0]
    model = _cache[path]
    if kind == "nn":
        from .model import NeuralBot
        return NeuralBot(model)
    if kind == "search":
        from .search import SearchBot
        return SearchBot(model, seed=seed)
    if kind.startswith("boss"):  # boss[K][s]: K rollout deck orders for Swaps; s: search endgame hit/stay too
        from .search import BossBot
        k = kind[4:].rstrip("s")
        return BossBot(model, k=int(k or 32), seed=seed, endgame_policy=not kind.endswith("s"))
    if kind.startswith("adaptive"):  # adaptive[MAXK], e.g. adaptive or adaptive128
        from .search import AdaptiveBot
        return AdaptiveBot(model, k_max=int(kind[8:] or 128), seed=seed)
    if kind.startswith("rollout"):  # rollout[K][t<temp>], e.g. rollout32 or rollout64t1
        from .search import RolloutBot
        k, _, temp = kind[7:].partition("t")
        return RolloutBot(model, k=int(k or 32), rollout_temp=float(temp or 0), seed=seed)
    raise ValueError(spec)


def _run(args):
    hero, villain, n, start, count, brutal = args
    import torch
    torch.set_num_threads(1)
    total = 0.0
    for i in range(start, start + count):
        rng = random.Random(1_000_003 * n + i)
        seat = i % n
        bots = [make_bot(villain, seed=i * 10 + k) for k in range(n)]
        bots[seat] = make_bot(hero, seed=i)
        g = Game(n, rules=Rules(brutal=brutal), rng=rng, dealer=rng.randrange(n))
        while not g.over:
            g.step(bots[g.decision.player].act(g))
        total += g.returns()[seat]
    return total, count


def evaluate(hero, villain, n, games, workers=4, brutal=True):
    per = math.ceil(games / workers)
    jobs = [(hero, villain, n, w * per, min(per, games - w * per), brutal) for w in range(workers) if games - w * per > 0]
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_run, jobs))
    wins = sum(r[0] for r in res)
    cnt = sum(r[1] for r in res)
    p = wins / cnt
    se = math.sqrt(max(p * (1 - p), 1e-9) / cnt)
    return p, se, cnt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hero", required=True)
    ap.add_argument("--villain", default="smart")
    ap.add_argument("--players", default="2,4")
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--standard", action="store_true", help="standard rules instead of Brutal")
    a = ap.parse_args()
    for n in [int(x) for x in a.players.split(",")]:
        p, se, cnt = evaluate(a.hero, a.villain, n, a.games, a.workers, not a.standard)
        print(f"{n}p  {a.hero} vs {a.villain}: win {p:.3f} ± {1.96 * se:.3f}  (fair {1 / n:.3f}, edge x{p * n:.2f}, {cnt} games)", flush=True)


if __name__ == "__main__":
    main()
