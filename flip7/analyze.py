"""Have the bots play thousands of games and summarise how they play.

    python -m flip7.analyze --model models/flip7_rl.pt --games 1500 --workers 4

Writes analysis/insights.json, which the web app's Insights page renders. Records every decision
of an all-RL table (and, for contrast, an all-SmartBot table) with the situation it was made in.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .cards import DIV2, FIRST_KEEPER, FIRST_MODIFIER, FLIP4, JOM, MOD_PENALTY, N_LINE_KINDS, N_NUMBER_KINDS, RANK, U7, ZERO
from .engine import (A_STAY, BUSTED, D_BOUNTY, D_DARE, D_DELIVER, D_DISCARD, D_FLIP7, D_HIT_STAY, D_MODIFIER,
                     D_PAY, D_SHAKEDOWN, D_SPITE, D_STEAL, D_SWAP1, D_SWAP2, D_TARGET, STAYED, Game, Rules,
                     decode_card, decode_player)
from .features import busting_kinds, next_card_pool, player_stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_COUNTS = (2, 3, 4, 5, 6)
PBUST_EDGES = [round(x * 0.05, 2) for x in range(13)]  # 0 … 60% bust chance


def _leader(stats, exclude):
    best, who = -1e9, -1
    for q, s in enumerate(stats):
        if q != exclude and s["total"] > best:
            best, who = s["total"], q
    return who


def _record(game, action, rows):
    """Describe one decision (before it is applied) and append it to ``rows``."""
    d = game.decision
    me = d.player
    n = game.n
    pool = next_card_pool(game)
    size = sum(pool)
    stats = [player_stats(game, q, pool, size) for q in range(n)]
    mine = stats[me]
    others_total = max(s["total"] for q, s in enumerate(stats) if q != me)
    others_tp = max(s["total"] + s["proj"] for q, s in enumerate(stats) if q != me)
    base = {"n": n, "gap": mine["total"] - others_total, "total": mine["total"],
            "rival_total": others_total, "rival_tp": others_tp, "round": game.round}
    if d.kind == D_HIT_STAY:
        rows["hit_stay"].append({**base, "score": mine["proj"], "count": mine["count"],
                                 "p_bust": mine["p_bust"], "zero": mine["zero"], "penalty": mine["penalty"],
                                 "stay": int(action == A_STAY),
                                 "end_threat": int(others_tp >= game.rules.target)})
        return
    leader = _leader(stats, me)
    if d.kind == D_PAY:
        rows["new"].append({**base, "kind": d.kind, "pay": int(action == A_STAY), "p_bust": mine["p_bust"],
                            "proj": mine["proj"], "stayed": int(mine["status"] == STAYED),
                            "bounty": int(game.players[me].bounty > 0), "by_leader": int(d.by == leader)})
        return
    if d.kind in (D_DELIVER, D_BOUNTY, D_DARE, D_SHAKEDOWN, D_SPITE):
        t = decode_player(action)
        opp = [decode_player(a) for a in d.options if decode_player(a) != me]
        row = {**base, "kind": d.kind, "self": int(t == me), "leader": int(t == leader),
               "leader_available": int(leader in opp), "n_opp": len(opp), "t_pbust": stats[t]["p_bust"],
               "max_pbust_opp": int(bool(opp) and t != me and stats[t]["p_bust"] >= max(stats[q]["p_bust"] for q in opp) - 1e-9)}
        if d.kind == D_DELIVER:
            c = d.card
            busts = lambda q: c < N_NUMBER_KINDS and c in busting_kinds(game.players[q].line)
            row.update(card_type="number" if c < N_NUMBER_KINDS else "modifier" if c < FIRST_KEEPER
                       else "keeper" if c < N_LINE_KINDS else "action",
                       busts_target=int(t != me and busts(t)), bust_possible=int(any(busts(q) for q in opp)),
                       busts_me=int(busts(me)))
        rows["new"].append(row)
        return
    if d.kind in (D_TARGET, D_MODIFIER, D_FLIP7):
        t = decode_player(action)
        s = stats[t]
        opts = [decode_player(a) for a in d.options]
        opp = [q for q in opts if q != me]
        row = {**base, "card": d.card if d.kind != D_FLIP7 else -1, "kind": d.kind,
               "self": int(t == me), "leader": int(t == leader),
               "leader_available": int(leader in opts),
               "t_status": s["status"], "t_pbust": s["p_bust"], "t_proj": s["proj"],
               "t_zero": int(s["zero"]), "t_sum": s["sum"], "t_count": s["count"],
               "t_gap": s["total"] - mine["total"],
               "max_pbust_opp": int(bool(opp) and t != me and s["p_bust"] >= max(stats[q]["p_bust"] for q in opp) - 1e-9),
               "max_sum_opp": int(bool(opp) and t != me and s["sum"] >= max(stats[q]["sum"] for q in opp)),
               "busted_available": int(any(stats[q]["status"] == BUSTED for q in opp)),
               "n_opp": len(opp), "my_pbust": mine["p_bust"], "my_proj": mine["proj"],
               "my_status": mine["status"], "my_count": mine["count"]}
        rows["target"].append(row)
        return
    if d.kind in (D_STEAL, D_SWAP1, D_SWAP2, D_DISCARD):
        q, c = decode_card(action)
        row = {**base, "kind": d.kind, "victim_self": int(q == me), "victim_leader": int(q == leader),
               "card": c, "value": RANK[c] if c < N_NUMBER_KINDS else -MOD_PENALTY.get(c, 0)}
        if d.kind == D_SWAP2:
            q1, c1 = decode_card(d.first)
            row.update(first_self=int(q1 == me), first_card=c1)
        rows["cards"].append(row)


def _play_batch(args):
    """Play ``games`` games of one table type; return decision rows and outcome stats."""
    model_path, kind, n, games, seed = args
    import torch
    torch.set_num_threads(1)
    from .bots import SmartBot
    rng = random.Random(seed)
    if kind == "rl":
        from .model import NeuralBot, load
        bot = NeuralBot(load(model_path)[0])
    else:
        bot = SmartBot()
    rows = {"hit_stay": [], "target": [], "cards": [], "new": []}
    out = {"rounds": [], "winner_pos": [], "round_scores": [], "busts": 0, "flip7s": 0,
           "player_rounds": 0, "flip7_choice": [], "events": defaultdict(float)}
    for _ in range(games):
        g = Game(n, rules=Rules(brutal=True), rng=random.Random(rng.random()), dealer=rng.randrange(n),
                 log=True)
        first_dealer = g.dealer
        while not g.over:
            a = bot.act(g)
            _record(g, a, rows)
            g.step(a)
        out["rounds"].append(g.round)
        for w in g.winners:
            out["winner_pos"].append(((w - first_dealer - 1) % n, 1 / len(g.winners)))
        for ev in g.events:
            if ev["t"] == "round_end":
                out["round_scores"].extend(ev["scores"])
                out["player_rounds"] += len(ev["scores"])
            elif ev["t"] == "bust":
                out["busts"] += 1
            elif ev["t"] == "flip7":
                out["flip7s"] += 1
            if ev["t"] in ("bounty_claim", "unlucky7", "spite", "robin", "pay", "refuse", "bounty", "dare", "shakedown"):
                out["events"][ev["t"]] += 1
            if ev["t"] in ("bounty_claim", "robin", "pay"):
                out["events"][ev["t"] + "_points"] += ev["amount"]
            if ev["t"] == "round_end":
                out["events"]["tax_points"] += sum(x["amount"] for x in ev.get("taxes", []))
    out["events"] = dict(out["events"])
    return kind, n, rows, out


def _bin_rate(xs, ys, edges):
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    res = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (xs >= lo) & (xs < hi)
        k = int(m.sum())
        res.append({"lo": lo, "hi": hi, "n": k, "rate": float(ys[m].mean()) if k else None})
    return res


def summarize(rows_by, outs_by):
    res = {"generated": time.strftime("%Y-%m-%d %H:%M"), "tables": {}}
    for kind in rows_by:
        hs = rows_by[kind]["hit_stay"]
        free = [r for r in hs if not r["zero"]]
        score_edges = list(range(0, 66, 3))
        T = {}
        T["stay_by_score"] = {}
        for n in ("all",) + PLAYER_COUNTS:
            sel = [r for r in free if n == "all" or r["n"] == n]
            T["stay_by_score"][str(n)] = _bin_rate([r["score"] for r in sel], [r["stay"] for r in sel], score_edges)
        T["stay_by_pbust"] = _bin_rate([r["p_bust"] for r in free], [r["stay"] for r in free],
                                       [round(x * 0.05, 2) for x in range(0, 15)])
        # heat map: cards in line x round score
        heat = []
        for cnt in range(1, 7):
            sel = [r for r in free if r["count"] == cnt]
            heat.append({"count": cnt, "bins": _bin_rate([r["score"] for r in sel], [r["stay"] for r in sel],
                                                         list(range(0, 61, 5)))})
        T["stay_heat"] = heat
        # risk appetite: where does P(stay) cross 50%, by score gap to the leading rival
        gap_edges = [-200, -100, -60, -30, -10, 10, 30, 60, 100, 200]
        risk = []
        for lo, hi in zip(gap_edges[:-1], gap_edges[1:]):
            sel = [r for r in free if lo <= r["gap"] < hi and not r["end_threat"]]
            risk.append({"lo": lo, "hi": hi, "n": len(sel), "threshold": _threshold(sel),
                         "stay_score": float(np.mean([r["score"] for r in sel if r["stay"]])) if any(r["stay"] for r in sel) else None})
        T["risk_by_gap"] = risk
        endgame = [r for r in free if r["end_threat"] and r["total"] + r["score"] < r["rival_tp"]]
        normal = [r for r in free if not r["end_threat"] and 15 <= r["score"] < 35]
        T["endgame"] = {
            "behind_when_rival_finishing_hit_rate": float(1 - np.mean([r["stay"] for r in endgame])) if endgame else None,
            "n": len(endgame),
            "normal_hit_rate_15_35": float(1 - np.mean([r["stay"] for r in normal])) if normal else None,
        }
        six = [r for r in free if r["count"] == 6]
        T["six_cards"] = {"hit_rate": float(1 - np.mean([r["stay"] for r in six])) if six else None, "n": len(six),
                          "by_pbust": _bin_rate([r["p_bust"] for r in six], [1 - r["stay"] for r in six],
                                                [0, 0.2, 0.3, 0.4, 0.5, 0.6, 1.01])}
        T["stay_threshold_by_n"] = {str(n): _threshold([r for r in free if r["n"] == n and not r["end_threat"]])
                                    for n in PLAYER_COUNTS}
        # Brutal Mode: a bust keeps your minus cards, so holding them should make you more careful
        calm = [r for r in free if not r["end_threat"]]
        held, clean = [r for r in calm if r.get("penalty")], [r for r in calm if not r.get("penalty")]
        T["minus_cards"] = {
            "n_held": len(held), "n_clean": len(clean),
            "pbust_threshold_held": _threshold(held, "p_bust"), "pbust_threshold_clean": _threshold(clean, "p_bust"),
            "score_threshold_held": _threshold(held), "score_threshold_clean": _threshold(clean),
            "stay_by_pbust_held": _bin_rate([r["p_bust"] for r in held], [r["stay"] for r in held], PBUST_EDGES),
            "stay_by_pbust_clean": _bin_rate([r["p_bust"] for r in clean], [r["stay"] for r in clean], PBUST_EDGES),
        }
        T["targeting"] = _targeting(rows_by[kind]["target"])
        T["cards"] = _card_choices(rows_by[kind]["cards"])
        T["new_cards"] = _new_cards(rows_by[kind].get("new", []), outs_by[kind])
        o = outs_by[kind]
        T["outcomes"] = {}
        for n in PLAYER_COUNTS:
            oo = o[n]
            pos = defaultdict(float)
            for p, w in oo["winner_pos"]:
                pos[p] += w
            games = len(oo["rounds"])
            T["outcomes"][str(n)] = {
                "games": games, "rounds": float(np.mean(oo["rounds"])),
                "avg_round_score": float(np.mean(oo["round_scores"])),
                "neg_round_rate": float(np.mean(np.asarray(oo["round_scores"]) < 0)),
                "bust_rate": oo["busts"] / oo["player_rounds"], "flip7_rate": oo["flip7s"] / oo["player_rounds"],
                "win_by_position": [pos[p] / games for p in range(n)],
            }
        res["tables"][kind] = T
    return res


def _threshold(rows, key="score"):
    """Value of ``key`` (round score by default) at which the stay probability crosses 50%
    (logistic fit)."""
    if len(rows) < 200:
        return None
    x = np.array([r[key] for r in rows], float)
    y = np.array([r["stay"] for r in rows], float)
    if y.min() == y.max():
        return None
    w, b = 0.1, -2.0
    for _ in range(300):  # Newton's method on 2 parameters
        z = np.clip(w * x + b, -30, 30)
        p = 1 / (1 + np.exp(-z))
        g = np.array([np.sum((p - y) * x), np.sum(p - y)])
        s = p * (1 - p)
        H = np.array([[np.sum(s * x * x), np.sum(s * x)], [np.sum(s * x), np.sum(s)]]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g)
        w, b = w - step[0], b - step[1]
        if np.abs(step).max() < 1e-7:
            break
    return float(-b / w) if w > 1e-6 else None


def _rate(rows, key):
    return float(np.mean([r[key] for r in rows])) if rows else None


def _targeting(rows):
    out = {}
    groups = {
        "jom": [r for r in rows if r["kind"] == D_TARGET and r["card"] == JOM],
        "flip4": [r for r in rows if r["kind"] == D_TARGET and r["card"] == FLIP4],
        "minus": [r for r in rows if r["kind"] == D_MODIFIER and r["card"] != DIV2],
        "div2": [r for r in rows if r["kind"] == D_MODIFIER and r["card"] == DIV2],
        "flip7": [r for r in rows if r["kind"] == D_FLIP7],
    }
    for name, rs in groups.items():
        opp = [r for r in rs if not r["self"]]
        g = {"n": len(rs), "self_rate": _rate(rs, "self"),
             "leader_rate": _rate([r for r in opp if r["leader_available"]], "leader"),
             "random_leader_rate": float(np.mean([1 / max(r["n_opp"], 1) for r in opp])) if opp else None,
             "stayed_rate": float(np.mean([r["t_status"] == STAYED for r in opp])) if opp else None,
             "busted_rate": float(np.mean([r["t_status"] == BUSTED for r in opp])) if opp else None,
             "busted_when_possible": float(np.mean([r["t_status"] == BUSTED for r in opp if r["busted_available"]])) if any(r["busted_available"] for r in opp) else None,
             "zero_rate": _rate(opp, "t_zero"),
             "max_pbust_rate": _rate(opp, "max_pbust_opp"),
             "max_sum_rate": _rate(opp, "max_sum_opp"),
             "target_pbust": _rate(opp, "t_pbust"),
             "target_proj": _rate(opp, "t_proj")}
        if name in ("jom", "flip4"):
            selfs = [r for r in rs if r["self"]]
            g["self_when_stayed"] = _rate([r for r in rs if r["my_status"] == STAYED], "self")
            g["self_my_pbust"] = _rate(selfs, "my_pbust")
            g["self_my_proj"] = _rate(selfs, "my_proj")
            g["self_by_my_pbust"] = _bin_rate([r["my_pbust"] for r in rs], [r["self"] for r in rs], [0, 0.1, 0.2, 0.3, 0.4, 0.6, 1.01])
            g["self_by_my_proj"] = _bin_rate([r["my_proj"] for r in rs], [r["self"] for r in rs], [-30, 0, 10, 20, 30, 45, 100])
        if name == "flip7":
            g["penalty_rate_by_n"] = {str(n): _rate([r for r in rs if r["n"] == n], "self") for n in PLAYER_COUNTS}
            g["penalty_rate_by_n"] = {k: (None if v is None else 1 - v) for k, v in g["penalty_rate_by_n"].items()}
            g["penalty_when_leading"] = _rate([dict(x=1 - r["self"]) for r in rs if r["gap"] > 0], "x")
            g["penalty_when_trailing"] = _rate([dict(x=1 - r["self"]) for r in rs if r["gap"] < 0], "x")
            g["penalty_leader_rate"] = _rate([r for r in rs if not r["self"]], "leader")
        out[name] = g
    return out


def _new_cards(rows, outs):
    """How the Bust or Bank cards are played: who gets them, and when a Shakedown is paid."""
    out = {}
    for kind, name in ((D_DELIVER, "deliver"), (D_BOUNTY, "bounty"), (D_DARE, "dare"), (D_SHAKEDOWN, "shakedown"),
                       (D_SPITE, "spite")):
        rs = [r for r in rows if r["kind"] == kind]
        opp = [r for r in rs if not r["self"]]
        g = {"n": len(rs), "self_rate": _rate(rs, "self"),
             "leader_rate": _rate([r for r in opp if r["leader_available"]], "leader"),
             "random_leader_rate": float(np.mean([1 / max(r["n_opp"], 1) for r in opp])) if opp else None,
             "max_pbust_rate": _rate(opp, "max_pbust_opp"), "target_pbust": _rate(opp, "t_pbust")}
        if kind == D_DELIVER:
            for t in ("number", "modifier", "keeper", "action"):
                sel = [r for r in rs if r["card_type"] == t]
                g[t] = {"n": len(sel), "self_rate": _rate(sel, "self"),
                        "leader_rate": _rate([r for r in sel if not r["self"] and r["leader_available"]], "leader")}
            nums = [r for r in rs if r["card_type"] == "number"]
            can = [r for r in nums if r["bust_possible"]]
            g["number"].update(bust_possible_rate=_rate(nums, "bust_possible"), busts_when_possible=_rate(can, "busts_target"),
                               self_when_safe=_rate([r for r in nums if not r["busts_me"] and not r["bust_possible"]], "self"))
        out[name] = g
    pays = [r for r in rows if r["kind"] == D_PAY]
    out["pay"] = {"n": len(pays), "pay_rate": _rate(pays, "pay"),
                  "pay_rate_stayed": _rate([r for r in pays if r["stayed"]], "pay"),
                  "pay_rate_active": _rate([r for r in pays if not r["stayed"]], "pay"),
                  "pay_rate_bounty": _rate([r for r in pays if r["bounty"]], "pay"),
                  "pay_by_pbust": _bin_rate([r["p_bust"] for r in pays], [r["pay"] for r in pays], [0, 0.1, 0.2, 0.3, 0.4, 0.6, 1.01]),
                  "pay_by_proj": _bin_rate([r["proj"] for r in pays], [r["pay"] for r in pays], [-30, 0, 10, 20, 30, 45, 100])}
    games = sum(len(o["rounds"]) for o in outs.values())
    ev = defaultdict(float)
    for o in outs.values():
        for k, v in o.get("events", {}).items():
            ev[k] += v
    out["per_game"] = {k: v / max(games, 1) for k, v in sorted(ev.items())}
    return out


def _card_choices(rows):
    out = {}
    names = {D_STEAL: "steal", D_DISCARD: "discard", D_SWAP1: "swap1", D_SWAP2: "swap2"}
    for k, name in names.items():
        rs = [r for r in rows if r["kind"] == k]
        cards = defaultdict(int)
        for r in rs:
            cards[r["card"]] += 1
        out[name] = {"n": len(rs), "victim_self": _rate(rs, "victim_self"),
                     "victim_leader": _rate([r for r in rs if not r["victim_self"]], "victim_leader"),
                     "avg_value": _rate(rs, "value"),
                     "cards": {str(c): v / max(len(rs), 1) for c, v in sorted(cards.items())}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "flip7_rl.pt"))
    ap.add_argument("--games", type=int, default=1200, help="games per player count per table type")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(ROOT, "analysis", "insights.json"))
    ap.add_argument("--matchups", default="", help="JSON file with head-to-head results to embed")
    a = ap.parse_args()
    jobs = []
    chunk = 100
    for kind in ("rl", "smart"):
        for n in PLAYER_COUNTS:
            for s in range(0, a.games, chunk):
                jobs.append((a.model, kind, n, min(chunk, a.games - s), (kind == "rl") * 1_000_003 + n * 10_007 + s))  # reproducible
    rows_by = {k: {"hit_stay": [], "target": [], "cards": [], "new": []} for k in ("rl", "smart")}
    outs_by = {k: {n: {"rounds": [], "winner_pos": [], "round_scores": [], "busts": 0, "flip7s": 0,
                       "player_rounds": 0, "events": defaultdict(float)} for n in PLAYER_COUNTS} for k in ("rl", "smart")}
    t0 = time.time()
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (kind, n, rows, out) in enumerate(ex.map(_play_batch, jobs)):
            for key in rows:
                rows_by[kind][key].extend(rows[key])
            o = outs_by[kind][n]
            for key in ("rounds", "winner_pos", "round_scores"):
                o[key].extend(out[key])
            for key in ("busts", "flip7s", "player_rounds"):
                o[key] += out[key]
            for key, v in out["events"].items():
                o["events"][key] += v
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{len(jobs)} batches, {time.time() - t0:.0f}s", flush=True)
    res = summarize(rows_by, outs_by)
    res["model"] = os.path.relpath(os.path.abspath(a.model), ROOT)
    res["decisions"] = {k: {key: len(v) for key, v in rows_by[k].items()} for k in rows_by}
    if a.matchups and os.path.exists(a.matchups):
        with open(a.matchups) as f:
            res["matchups"] = json.load(f)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
