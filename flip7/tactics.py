"""Verified tactical positions: a fixed set of hard decisions whose answers are checked independently.

    python -m flip7.tactics build --model models/flip7_rl.pt --per-kind 50 --workers 10 --out data/tactics.pkl
    python -m flip7.tactics score data/tactics_v6.pkl nn:runs/big2/latest.pt search:models/flip7_rl.pt
    python -m flip7.tactics report data/tactics_v6_b.pkl --bot Boss=boss:models/flip7_rl.pt --out analysis/tactics.json

Positions come from games the network plays against itself (2-6 players, Brutal to 200), an equal
quota of each kind: Swap, Just One More / Flip Four targets, modifier targets, Steal, Discard, the
Flip 7 bonus, hit/stay when someone can reach the target this round, and other hit/stay decisions
where the policy is unsure (top move under 85%). At most one position of a kind per game.

Every candidate action is valued by playing the game *to the end* (no value head, no cut at the end
of the round), with the network playing every seat afterwards, on shared shuffles of the unseen
cards: the value of an action is the deciding player's win share if they take it and then everyone,
themselves included, plays as the network would (so after the first card of a Swap, the network
picks the second). Two disjoint sets of shuffles are used. The
selection set (``--select``) only picks a challenger, the best action other than the network's own
choice. The verification set (``--verify``, larger) values every candidate again; only its numbers
are stored, so picking the challenger can't flatter it.

A position is a *verified mistake* when the challenger beats the network's choice by more than two
standard errors on the verification set. ``score`` measures any bot on the saved positions: its
average gain over the network's choice (paired per shuffle, with a 95% interval), per kind, and how
many verified mistakes it avoids. An action outside the stored candidates is valued on the spot with
the same verification shuffles. ``report`` writes the per-kind summary, the scores of the named bots
and the costliest mistake of each kind (described in words) for the Insights page.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import torch

from .calibrate import _playout, _shuffled
from .engine import D_DISCARD, D_FLIP7, D_MODIFIER, D_STEAL, D_SWAP1, D_SWAP2, D_TARGET, Game, Rules
from .model import NeuralBot, load
from .search import RolloutBot, _endgame

KINDS = ("swap", "action target", "modifier target", "steal", "discard", "flip7 bonus",
         "endgame hit/stay", "unsure hit/stay")
_BY_DECISION = {D_SWAP1: "swap", D_SWAP2: "swap", D_TARGET: "action target", D_MODIFIER: "modifier target",
                D_STEAL: "steal", D_DISCARD: "discard", D_FLIP7: "flip7 bonus"}


def kind_of(g, probs):
    """The position's kind, or None for an easy hit/stay."""
    k = _BY_DECISION.get(g.decision.kind)
    if k:
        return k
    if _endgame(g):
        return "endgame hit/stay"
    return "unsure hit/stay" if max(probs.values()) < 0.85 else None


def action_values(model, g, actions, seeds):
    """[len(actions), len(seeds)] win shares of the deciding player: action, then the network in
    every seat to the end of the game, on the deck order fixed by each seed (shared by all actions)."""
    me = g.decision.player
    games = []
    for a in actions:
        for s in seeds:
            x = _shuffled(g, s)
            x.step(a)
            games.append(x)
    return _playout(model, games, me, set(range(g.n)), None).reshape(len(actions), len(seeds))


def _seeds(pid, which, k):
    rng = random.Random(f"{pid}/{which}")
    return [rng.random() for _ in range(k)]


def _diff(vals, i, j):
    """Mean and standard error of vals[i] - vals[j] over shared seeds."""
    d = vals[i] - vals[j]
    return float(d.mean()), float(d.std(ddof=1) / math.sqrt(len(d)))


def _evaluate(model, g, pid, select, verify, max_actions):
    net = NeuralBot(model)
    probs = net.evaluate(g)[0]
    policy = max(probs, key=probs.get)
    cands = RolloutBot(model, max_actions=max_actions)._candidates(g)
    sel = action_values(model, g, cands, _seeds(pid, "select", select)).mean(1)
    challenger = max((a for a in cands if a != policy), key=lambda a: sel[cands.index(a)])
    vals = action_values(model, g, cands, _seeds(pid, "verify", verify))
    i_pol = cands.index(policy)
    gain = {a: _diff(vals, k, i_pol) for k, a in enumerate(cands)}
    g_ch, se_ch = gain[challenger]
    return {"policy": policy, "policy_prob": probs[policy], "challenger": challenger, "candidates": cands,
            "value": {a: float(vals[k].mean()) for k, a in enumerate(cands)},
            "gain": gain,  # action -> (mean, se) of its value minus the policy's, verification set
            "mistake": g_ch > 2 * se_ch}


def _worker(args):
    model_path, quota, select, verify, max_actions, seed = args
    torch.set_num_threads(1)
    model = load(model_path)[0]
    net = NeuralBot(model)
    rng = random.Random(seed)
    left = dict(quota)
    out = []
    games = 0
    while any(left.values()) and games < 20000:
        games += 1
        n = rng.choice((2, 3, 4, 5, 6))
        g = Game(n, rules=Rules(), rng=random.Random(rng.random()), dealer=rng.randrange(n))
        seen = set()
        while not g.over:
            probs = net.evaluate(g)[0]
            if len(probs) > 1:
                k = kind_of(g, probs)
                if k and left.get(k) and k not in seen and rng.random() < 0.3:
                    seen.add(k)
                    left[k] -= 1
                    pid = f"{seed}/{len(out)}"
                    pos = {"id": pid, "kind": k, "n": n, "round": g.round, "game": g.clone(random.Random(0)),
                           "endgame": _endgame(g), **_evaluate(model, g, pid, select, verify, max_actions)}
                    out.append(pos)
            g.step(max(probs, key=probs.get))
    return out


def build(model_path, per_kind, select=192, verify=1024, max_actions=10, workers=4, seed=0):
    shares = [{k: per_kind // workers + (w < per_kind % workers) for k in KINDS} for w in range(workers)]
    jobs = [(model_path, q, select, verify, max_actions, seed * 1000 + w) for w, q in enumerate(shares)]
    with ProcessPoolExecutor(workers) as ex:
        positions = [p for part in ex.map(_worker, jobs) for p in part]
    from .benchmark import provenance
    return {"model": model_path, "checkpoint": provenance([model_path]).get(model_path), "select": select,
            "verify": verify, "positions": positions}


def _score_one(args):
    model_path, spec, pos, verify, k = args
    torch.set_num_threads(1)
    from .evaluate import make_bot
    g = pos["game"].clone(random.Random(0))
    a = make_bot(spec, seed=k).act(g)
    if a in pos["gain"]:
        return a, pos["gain"][a]
    model = load(model_path)[0]  # not a stored candidate: value it on the verification shuffles
    vals = action_values(model, g, [a, pos["policy"]], _seeds(pos["id"], "verify", verify))
    return a, _diff(vals, 0, 1)


def score(data, spec, workers=4):
    """A bot's gain over the network's choice on the saved positions, per kind and overall."""
    ps = data["positions"]
    jobs = [(data["model"], spec, p, data["verify"], k) for k, p in enumerate(ps)]
    with ProcessPoolExecutor(workers) as ex:
        picks = list(ex.map(_score_one, jobs))

    def block(rows):
        if not rows:
            return None
        gains = np.array([g for _, (g, _), _ in rows])
        ses = np.array([s for _, (_, s), _ in rows])
        mistakes = [g for _, (g, _), p in rows if p["mistake"]]
        return {"positions": len(rows), "gain": float(gains.mean()),
                "ci95": float(1.96 * math.sqrt((ses ** 2).sum()) / len(rows)),
                "agree": float(np.mean([a == p["policy"] for a, _, p in rows])),
                "mistakes": len(mistakes), "fixed": sum(g > 0 for g in mistakes)}

    rows = [(a, g, p) for (a, g), p in zip(picks, ps)]
    return {"bot": spec, "overall": block(rows),
            "kinds": {k: block([r for r in rows if r[2]["kind"] == k]) for k in KINDS}}


def summary(data):
    ps = data["positions"]
    lines = [f"{len(ps)} positions from {data['model']} (select {data['select']}, verify {data['verify']} shuffles)"]
    for k in KINDS:
        sel = [p for p in ps if p["kind"] == k]
        if sel:
            m = [p for p in sel if p["mistake"]]
            gap = np.mean([p["gain"][p["challenger"]][0] for p in m]) if m else 0.0
            lines.append(f"  {k:17s} {len(sel):4d} positions, {len(m):3d} verified mistakes"
                         + (f" (challenger better by {gap * 100:.1f} points on average)" if m else ""))
    return "\n".join(lines)


def _example(p):
    """The position and the two moves in words, for a verified mistake."""
    from .coach import describe
    g = p["game"]
    me = g.decision.player
    names = [f"player {(q - me) % g.n}" for q in range(g.n)]  # counted from the deciding player
    gain, se = p["gain"][p["challenger"]]
    return {"kind": p["kind"], "players": g.n, "round": p["round"],
            "totals": [g.players[(me + k) % g.n].total for k in range(g.n)],  # deciding player first
            "network": describe(g, p["policy"], names), "better": describe(g, p["challenger"], names),
            "network_value": p["value"][p["policy"]], "better_value": p["value"][p["challenger"]], "gain": gain, "se": se}


def report(data, bots, workers=4):
    """Per kind: the network's verified mistakes and their cost, each named bot's score, and the
    costliest mistake as an example. ``bots``: [(name, spec)] or [(name, spec, what it is)]."""
    ps = data["positions"]
    kinds, examples = {}, []
    for k in KINDS:
        sel = [p for p in ps if p["kind"] == k]
        m = sorted((p for p in sel if p["mistake"]), key=lambda p: -p["gain"][p["challenger"]][0])
        kinds[k] = {"positions": len(sel), "mistakes": len(m),
                    "mistake_cost": float(np.mean([p["gain"][p["challenger"]][0] for p in m])) if m else None}
        if m:
            examples.append(_example(m[0]))
    from .benchmark import provenance
    return {"model": data["model"], "checkpoint": data.get("checkpoint"), "select": data["select"],
            "verify": data["verify"], "positions": len(ps), "kinds": kinds, "examples": examples,
            "bots": [{"name": name, "spec": spec, "about": about[0] if about else None,
                      "checkpoint": provenance([spec]).get(spec.split(":", 1)[-1]), **score(data, spec, workers)}
                     for name, spec, *about in bots]}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--model", default="models/flip7_rl.pt")
    b.add_argument("--per-kind", type=int, default=50)
    b.add_argument("--select", type=int, default=192)
    b.add_argument("--verify", type=int, default=1024)
    b.add_argument("--max-actions", type=int, default=10)
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("data")
    s.add_argument("bots", nargs="+", help="bot specs, e.g. nn:<ckpt> search:<ckpt>")
    s.add_argument("--workers", type=int, default=4)
    r = sub.add_parser("report")
    r.add_argument("data")
    r.add_argument("--bot", action="append", default=[], help="NAME=SPEC[=WHAT IT IS], e.g. Boss=boss:models/flip7_rl.pt")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "report":
        with open(a.data, "rb") as f:
            data = pickle.load(f)
        out = report(data, [b.split("=", 2) for b in a.bot], a.workers)
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
        print(summary(data))
        for b in out["bots"]:
            o = b["overall"]
            print(f"{b['name']}: gain {o['gain'] * 100:+.2f} ± {o['ci95'] * 100:.2f}, fixes {o['fixed']}/{o['mistakes']}")
        return
    if a.cmd == "build":
        data = build(a.model, a.per_kind, a.select, a.verify, a.max_actions, a.workers, a.seed)
        with open(a.out, "wb") as f:
            pickle.dump(data, f)
        print(summary(data))
        return
    with open(a.data, "rb") as f:
        data = pickle.load(f)
    print(summary(data))
    for spec in a.bots:
        r = score(data, spec, a.workers)
        o = r["overall"]
        print(f"{spec}: gain {o['gain'] * 100:+.2f} ± {o['ci95'] * 100:.2f} points over the network's choice, "
              f"same move {o['agree'] * 100:.0f}%, fixes {o['fixed']}/{o['mistakes']} verified mistakes")
        for k, v in r["kinds"].items():
            if v:
                print(f"  {k:17s} {v['gain'] * 100:+6.2f} ± {v['ci95'] * 100:.2f}  same {v['agree'] * 100:3.0f}%  "
                      f"fixes {v['fixed']}/{v['mistakes']}")


if __name__ == "__main__":
    main()
