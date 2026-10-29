"""Post-game coach: what each decision cost in win chance, and why, in terms of the rules.

``review(model, decisions)`` takes the positions a player faced (game snapshots) and the action
they chose. Every candidate action is played out on the same shuffled deck orders (rollouts to
the end of the round, scored by the value head, as RolloutBot does), so "lost win chance" is the
paired difference between the best action and the chosen one, with a 95% interval. Each option
also gets facts computed exactly from the position: how many cards would bust you, who a swap
busts, what staying would bank, how likely a Flip Four target is to bust, and so on. Those facts
come from the engine, not from the network.
"""
from __future__ import annotations

import math
import random

import numpy as np

from .cards import FLIP4, L14, MOD_PENALTY, MODIFIER_IDS, N_NUMBER_KINDS, NAMES, RANK, U7
from .engine import (A_CARD0, A_HIT, A_PLAYER0, A_STAY, BUSTED, DECISION_NAMES, SHAKEDOWN_FINE, STAYED,
                     decode_card)
from .features import busting_kinds, next_card_pool
from .search import RolloutBot

MOD_NAME = dict(zip(MODIFIER_IDS, ("−2", "−4", "−6", "−8", "−10", "÷2")))


def card_name(c):
    return MOD_NAME.get(c) or NAMES[c]


def _who(names, p, me):
    return "you" if p == me else names[p]


def describe(g, a, names):
    d = g.decision
    me = d.player
    kind = DECISION_NAMES[d.kind]
    if kind == "hit_stay":
        return "Hit" if a == A_HIT else "Stay"
    if kind == "pay":
        return f"Pay {names[d.by]} {SHAKEDOWN_FINE}" if a == A_STAY else "Take a card instead"
    if a < A_CARD0:
        t = a - A_PLAYER0
        if kind == "flip7":
            return "+15 for yourself" if t == me else f"−15 to {names[t]}"
        if kind == "deliver":
            return f"The {card_name(d.card)} to {'yourself' if t == me else names[t]}"
        return f"{card_name(d.card)} on {'yourself' if t == me else names[t]}"
    q, c = decode_card(a)
    owner = "your" if q == me else f"{names[q]}'s"
    return {"steal": f"Steal {owner} {card_name(c)}", "swap1": f"Swap {owner} {card_name(c)} …",
            "swap2": f"… for {owner} {card_name(c)}", "discard": f"Discard {owner} {card_name(c)}"}[kind]


def _bust_chance_of_draws(g, p, draws, samples=400, seed=0):
    """Chance that player p busts while taking ``draws`` cards (numbers only; actions and
    modifiers drawn are set aside, as Flip Four does)."""
    rng = random.Random(seed)
    pool = list(g.deck) if len(g.deck) >= draws else list(g.deck) + list(g.discard)
    line0 = list(g.players[p].line)
    busts = 0
    for _ in range(samples):
        rng.shuffle(pool)
        line = list(line0)
        for c in pool[:draws]:
            if c >= N_NUMBER_KINDS:
                continue
            if c in busting_kinds(line):
                busts += 1
                break
            if c == U7:  # the Unlucky Frozen 7 wipes the rest of the line and ends the drawing
                break
            line = line + [c]
    return busts / samples


def _apply(g, a):
    """The deterministic consequences of an action: events up to the next card drawn."""
    x = g.clone(random.Random(0))
    x.logging, x.events = True, []
    x.step(a)
    out = []
    for ev in x.events:
        if ev["t"] == "draw":
            break
        out.append(ev)
    return x, out


def facts(g, a, names):
    d = g.decision
    me = d.player
    pl = g.players[me]
    kind = DECISION_NAMES[d.kind]
    target = g.rules.target
    out = []
    if kind == "hit_stay":
        proj = g.projected(me)
        if a == A_STAY:
            total = pl.total + proj
            out.append(f"Banks {proj} → {total} total")
            rivals = [q.total + (g.projected(i) if q.status == STAYED else 0)
                      for i, q in enumerate(g.players) if i != me]
            if total >= target:
                out.append("reaches the target: the game ends after this round"
                           + (", and you'd be ahead of every banked score" if total > max(rivals) else ""))
        else:
            pool = next_card_pool(g)
            size = sum(pool)
            bust = busting_kinds(pl.line)
            n_bust = sum(pool[c] for c in bust)
            if size:
                kinds = sorted(((pool[c], c) for c in bust if pool[c]), reverse=True)[:3]
                listed = ", ".join(f"{card_name(c)} ×{k}" for k, c in kinds)
                out.append(f"{n_bust} of {size} cards left bust you ({round(100 * n_bust / size)}%)"
                           + (f": {listed}" if listed else ""))
            numbers = len({RANK[c] for c in pl.line if c < N_NUMBER_KINDS}) + (1 if L14 in pl.line and 14 in pl.line else 0)
            if 7 - numbers <= 2:
                out.append(f"Flip 7 (+15) is {7 - numbers} new number{'s' if 7 - numbers > 1 else ''} away")
            if proj > 0:
                out.append(f"risks the {proj} points you have this round")
            held = sum(MOD_PENALTY[c] for c in pl.line if c in MOD_PENALTY)
            if g.rules.brutal and held:
                out.append(f"a bust keeps your minus cards: −{held} this round")
    elif kind == "target" and a < A_CARD0:
        t = a - A_PLAYER0
        who = _who(names, t, me)
        tp = g.players[t]
        if d.card == FLIP4:
            chance = _bust_chance_of_draws(g, t, 4)
            out.append(f"{who.capitalize()} would bust about {round(100 * chance)}% of the time over four cards")
        else:
            chance = _bust_chance_of_draws(g, t, 1)
            out.append(f"{who.capitalize()} would bust {round(100 * chance)}% of the time on the one card")
        if tp.status == STAYED and t != me:
            out.append(f"{names[t]} has already stayed, so they can't use more cards well")
        leader = max(range(g.n), key=lambda i: g.players[i].total)
        if t == leader and t != me:
            out.append(f"{names[t]} leads with {tp.total}")
    elif kind == "modifier" and a < A_CARD0:
        t = a - A_PLAYER0
        tp = g.players[t]
        if tp.status == BUSTED:
            out.append(f"{names[t] if t != me else 'You'} already busted: in Brutal Mode it still costs {MOD_PENALTY.get(d.card, 0) or 'half'}")
        else:
            before = g.projected(t)
            x, _ = _apply(g, a)
            out.append(f"{'Your' if t == me else names[t] + chr(39) + 's'} round score {before} → {x.projected(t)}")
        if t != me and t == max(range(g.n), key=lambda i: g.players[i].total):
            out.append(f"{names[t]} leads with {tp.total}")
    elif kind == "flip7" and a < A_CARD0:
        t = a - A_PLAYER0
        if t == me:
            out.append(f"Puts you on {pl.total + g.projected(me) + 15} after this round")
        else:
            out.append(f"{names[t]} drops to about {g.players[t].total + g.projected(t) - 15}")
    elif kind == "pay":
        if a == A_STAY:
            out.append(f"{names[d.by]} gains {SHAKEDOWN_FINE}, you keep your cards")
        else:
            chance = _bust_chance_of_draws(g, me, 1)
            out.append(f"You'd bust {round(100 * chance)}% of the time on the one card")
            if pl.bounty:
                out.append(f"a bust would also pay {names[d.by]} your Bounty")
    elif kind == "dare" and a < A_CARD0:
        t = a - A_PLAYER0
        chance = _bust_chance_of_draws(g, t, 2)
        out.append(f"{names[t]} would bust about {round(100 * chance)}% of the time over two forced hits")
    elif kind in ("bounty", "shakedown", "spite") and a < A_CARD0:
        t = a - A_PLAYER0
        leader = max(range(g.n), key=lambda i: g.players[i].total)
        if t == leader:
            out.append(f"{names[t]} leads with {g.players[t].total}")
    elif kind in ("steal", "swap2", "discard", "deliver"):
        x, evs = _apply(g, a)
        for ev in evs:
            if ev["t"] == "bust":
                out.append(f"busts {_who(names, ev['p'], me)}")
            elif ev["t"] == "flip7":
                out.append(f"gives {_who(names, ev['p'], me)} a Flip 7")
        for i in range(g.n):
            if g.players[i].status != BUSTED and x.players[i].status != BUSTED and x.projected(i) != g.projected(i):
                out.append(f"{'your' if i == me else names[i] + chr(39) + 's'} round score {g.projected(i)} → {x.projected(i)}")
    elif kind == "swap1":
        out.append("you pick the card to trade it for next")
    return out


def review(model, decisions, names, k=48, seed=0):
    """``decisions``: [{"game": snapshot, "chosen": action, "round": r}] for one player.
    Returns the summary the web app shows: per decision the options with estimated win chances,
    the lost win chance of the choice (with a 95% interval) and the facts behind each option."""
    return summarize([x for x in review_steps(model, decisions, names, k, seed) if x])


def review_steps(model, decisions, names, k=48, seed=0):
    """``review`` one decision at a time: yields each decision's item (None if there was no choice)."""
    bot = RolloutBot(model, k=k, max_actions=6, pair_width=2, seed=seed)
    for i, dec in enumerate(decisions):
        g, chosen = dec["game"], dec["chosen"]
        if len(g.legal()) < 2:
            yield None
            continue
        seqs = bot._sequences(g)
        if not any(s[0] == chosen for s in seqs):
            seqs.append((chosen,))
        seeds = [bot.rng.random() for _ in range(k)]
        vals = bot._simulate(g, seqs, seeds)
        best_seq = {}
        for s in seqs:
            if s[0] not in best_seq or vals[s].mean() > vals[best_seq[s[0]]].mean():
                best_seq[s[0]] = s
        per = {a: vals[s] for a, s in best_seq.items()}
        best = max(per, key=lambda a: per[a].mean())
        diff = per[best] - per[chosen]
        loss = float(diff.mean())
        ci = float(1.96 * diff.std(ddof=1) / math.sqrt(k)) if best != chosen else 0.0
        me = g.decision.player
        options = sorted(per, key=lambda a: -per[a].mean())
        if chosen not in options[:6]:
            options = options[:5] + [chosen]
        yield {
            "i": i, "round": dec["round"], "kind": DECISION_NAMES[g.decision.kind],
            "chosen": chosen, "best": best, "loss": round(loss, 4), "ci": round(ci, 4),
            "options": [{"a": a, "label": describe(g, a, names), "win": round(float(per[a].mean()), 4),
                         "facts": facts(g, a, names)} for a in options[:6]],
            "table": table(g, me),
        }


def summarize(items):
    """The summary ``review`` returns, from the decisions' items."""
    clear = [x for x in items if x["loss"] - x["ci"] > 0.005]
    return {"decisions": len(items), "good": sum(1 for x in items if x["loss"] - x["ci"] <= 0.005),
            "lost": round(sum(x["loss"] for x in clear), 4),
            "moments": sorted(items, key=lambda x: -x["loss"])}


def table(g, me):
    """A compact picture of the position for the replay view."""
    d = g.decision
    return {"me": me, "target": g.rules.target, "deck": len(g.deck), "kind": DECISION_NAMES[d.kind], "card": d.card,
            "first": list(decode_card(d.first)) if d.first >= 0 else None,
            "players": [{"total": p.total, "status": p.status, "line": list(p.line), "projected": g.projected(i)}
                        for i, p in enumerate(g.players)]}
