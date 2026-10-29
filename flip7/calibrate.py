"""How well the value network's win estimates hold up, and how well it ranks actions.

    python -m flip7.calibrate --model models/flip7_rl.pt --positions 1200 --playouts 40 \\
        --workers 4 --out analysis/calibration.json

Positions are sampled from games the network plays, at all-network tables ("self") and at
tables where every other seat is SmartBot ("smart"), with 2-6 players, Brutal Mode to 200. For
each position we compare

* the value head's win probability for the deciding player, with
* the share of ``--playouts`` games, played to the end from that position by the same line-up
  (each on its own shuffle of the unseen cards), that this player wins.

For a share of the positions with several legal actions we also measure action ranking: up to
six candidate actions are each played out ``--action-playouts`` times on shared deck orders, and
the best of them is compared with the policy's choice and with the value head's one-ply choice
(the SearchBot estimate, which search and distillation rely on). Everything is broken down by
player count, line-up, decision kind, Swap and Flip Four decisions, and endgames (someone can
reach the target this round).
"""
from __future__ import annotations

import argparse
import json
import math
import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import torch

from .bots import SmartBot
from .cards import FLIP4
from .engine import DECISION_NAMES, Game, Rules
from .model import NeuralBot, load
from .search import SearchBot, _endgame, _forward
from .encoding import abs_to_rel, rel_to_abs


def _playout(model, games, me, net_seats, smart):
    """Play every game to the end; ``me``'s win share in each. Network seats play greedily and
    are batched into one forward pass per step."""
    out = np.zeros(len(games))
    active = list(range(len(games)))
    while active:
        batch = []
        for i in active:
            g = games[i]
            if g.over:
                continue
            if g.decision.player in net_seats:
                batch.append(i)
            else:
                g.step(smart.act(g))
        if batch:
            logits, _, deciders = _forward(model, [games[i] for i in batch])
            acts = logits.argmax(1)
            for j, i in enumerate(batch):
                games[i].step(rel_to_abs(int(acts[j]), deciders[j], games[i].n))
        still = []
        for i in active:
            if games[i].over:
                out[i] = games[i].returns()[me]
            else:
                still.append(i)
        active = still
    return out


def _shuffled(game, seed):
    g = game.clone(random.Random(seed))
    random.Random(seed).shuffle(g.deck)  # the order of unseen cards is unknown to everyone
    return g


def _categories(g, lineup):
    d = g.decision
    kind = DECISION_NAMES[d.kind]
    cats = [f"{g.n} players", f"vs {lineup}", f"decision: {kind}"]
    if kind in ("swap1", "swap2"):
        cats.append("Swap")
    if kind == "target" and d.card == FLIP4:
        cats.append("Flip Four target")
    cats.append("endgame" if _endgame(g) else "not endgame")
    return cats


def _candidates(model, g, limit=6):
    me = g.decision.player
    logits = _forward(model, [g])[0][0]
    return sorted(g.legal(), key=lambda a: -float(logits[abs_to_rel(a, me, g.n)]))[:limit]


def _worker(args):
    model_path, positions, playouts, action_playouts, p_rank, seed = args
    torch.set_num_threads(1)
    model = load(model_path)[0]
    net = NeuralBot(model)
    search = SearchBot(model, seed=seed)
    smart = SmartBot()
    rng = random.Random(seed)
    rows = []
    while len(rows) < positions:
        n = rng.choice((2, 3, 4, 5, 6))
        lineup = rng.choice(("self", "smart"))
        hero = rng.randrange(n)
        net_seats = set(range(n)) if lineup == "self" else {hero}
        g = Game(n, rules=Rules(), rng=random.Random(rng.random()), dealer=rng.randrange(n))
        taken = 0
        while not g.over and len(rows) < positions and taken < 3:
            d = g.decision
            if d.player in net_seats and len(d.options) > 1 and rng.random() < 0.05:
                me = d.player
                _, win, _ = net.evaluate(g)
                games = [_shuffled(g, rng.random()) for _ in range(playouts)]
                vals = _playout(model, games, me, net_seats, smart)
                row = {"pred": float(win[me]), "mc": float(vals.mean()),
                       "se": float(vals.std(ddof=1) / math.sqrt(len(vals))), "cats": _categories(g, lineup)}
                if rng.random() < p_rank:
                    cands = _candidates(model, g)
                    seeds = [rng.random() for _ in range(action_playouts)]
                    q_mc = {}
                    for a in cands:
                        gs = []
                        for s in seeds:
                            x = _shuffled(g, s)
                            x.step(a)
                            gs.append(x)
                        q_mc[a] = _playout(model, gs, me, net_seats, smart)
                    q_vh = search.evaluate(g)
                    probs, _, _ = net.evaluate(g)
                    best = max(cands, key=lambda a: q_mc[a].mean())
                    vh_pick = max(cands, key=lambda a: q_vh.get(a, -1))
                    pol_pick = max(cands, key=lambda a: probs[a])
                    gap = lambda a: float(q_mc[best].mean() - q_mc[a].mean())
                    se = lambda a: float((q_mc[best] - q_mc[a]).std(ddof=1) / math.sqrt(len(seeds))) if a != best else 0.0
                    row["rank"] = {"n_actions": len(cands), "vh_agree": vh_pick == best, "pol_agree": pol_pick == best,
                                   "vh_regret": gap(vh_pick), "vh_regret_se": se(vh_pick),
                                   "pol_regret": gap(pol_pick), "pol_regret_se": se(pol_pick)}
                rows.append(row)
                taken += 1
            if d.player in net_seats:
                g.step(net.act(g))
            else:
                g.step(smart.act(g))
    return rows


def summarize(rows):
    def block(rs):
        if not rs:
            return None
        pred = np.array([r["pred"] for r in rs])
        mc = np.array([r["mc"] for r in rs])
        out = {"positions": len(rs), "mae": float(np.abs(pred - mc).mean()), "bias": float((pred - mc).mean()),
               "noise_floor": float(np.mean([r["se"] for r in rs]) * math.sqrt(2 / math.pi))}
        ranked = [r["rank"] for r in rs if "rank" in r]
        if ranked:
            out.update({"ranked": len(ranked),
                        "vh_agree": float(np.mean([x["vh_agree"] for x in ranked])),
                        "pol_agree": float(np.mean([x["pol_agree"] for x in ranked])),
                        "vh_regret": float(np.mean([x["vh_regret"] for x in ranked])),
                        "pol_regret": float(np.mean([x["pol_regret"] for x in ranked]))})
        return out

    pred = np.array([r["pred"] for r in rows])
    mc = np.array([r["mc"] for r in rows])
    bins = []
    edges = np.linspace(0, 1, 11)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (pred >= lo) & ((pred < hi) | (hi == 1))
        if sel.sum():
            bins.append({"lo": float(lo), "hi": float(hi), "n": int(sel.sum()),
                         "pred": float(pred[sel].mean()), "mc": float(mc[sel].mean())})
    ece = sum(b["n"] * abs(b["pred"] - b["mc"]) for b in bins) / len(rows)
    cats = sorted({c for r in rows for c in r["cats"]})
    by_cat = {c: block([r for r in rows if c in r["cats"]]) for c in cats}
    overall = block(rows)
    overall["ece"] = float(ece)
    return {"overall": overall, "reliability": bins, "categories": by_cat}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/flip7_rl.pt")
    ap.add_argument("--positions", type=int, default=1200)
    ap.add_argument("--playouts", type=int, default=40)
    ap.add_argument("--action-playouts", type=int, default=24)
    ap.add_argument("--rank-share", type=float, default=0.4, help="share of positions whose actions are ranked")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="analysis/calibration.json")
    a = ap.parse_args()
    per = -(-a.positions // a.workers)
    jobs = [(a.model, per, a.playouts, a.action_playouts, a.rank_share, a.seed * 1000 + w) for w in range(a.workers)]
    with ProcessPoolExecutor(a.workers) as ex:
        rows = [r for part in ex.map(_worker, jobs) for r in part]
    from .benchmark import provenance
    out = {"model": a.model, "checkpoint": provenance([a.model]).get(a.model), "playouts": a.playouts,
           "action_playouts": a.action_playouts, **summarize(rows)}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    o = out["overall"]
    print(f"{o['positions']} positions: MAE {o['mae']:.3f} (noise floor {o['noise_floor']:.3f}), bias {o['bias']:+.3f}, "
          f"ECE {o['ece']:.3f}; action ranking on {o.get('ranked', 0)}: value top-1 {o.get('vh_agree', 0):.2f}, "
          f"policy top-1 {o.get('pol_agree', 0):.2f}")
    worst = sorted((v["mae"] - v["noise_floor"], k) for k, v in out["categories"].items() if v and v["positions"] >= 30)[-4:]
    print("largest errors above noise:", ", ".join(f"{k} ({e:+.3f})" for e, k in reversed(worst)))


if __name__ == "__main__":
    main()
