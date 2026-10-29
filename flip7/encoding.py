"""Observation / action encoding for neural bots.

Everything is relative to the deciding player ("me"): player slot k is the player k seats to
my left, so slot 0 is always me. Actions use the engine's flat layout with seats replaced by
slots, which makes one network work for every seat and table size.

Every input has a name in ``FEATURES`` (e.g. ``("deck", 14)``: the share of the 14s still in the
draw pile), so a network trained on another layout can be carried over feature by feature
(``flip7.remap``).
"""
from __future__ import annotations

import numpy as np

from .cards import COUNTS, DECK_SIZE, FIRST_MODIFIER, FLIP4, JOM, MOD_PENALTY, MODIFIER_IDS, N_KINDS, \
    N_LINE_KINDS, N_NUMBER_KINDS, RANK, U7
from .engine import (A_CARD0, A_PLAYER0, BUSTED, D_DELIVER, D_HIT_STAY, D_PAY, D_SWAP2, MAX_PLAYERS,
                     N_ACTIONS, N_DECISION_KINDS, T_DEAL, T_FLIP4, T_JOM_STAY, T_QUEUE, T_TURNS, decode_card,
                     decode_player, line_score)
from .features import busting_kinds, draw_stats

FEATURES = []


def _block(name, labels=None):
    """Append named inputs; returns the index of the first."""
    start = len(FEATURES)
    if labels is None:
        FEATURES.append((name,))
    else:
        FEATURES.extend((name, x) for x in labels)
    return start


CARD_SLOTS = (JOM, FLIP4) + MODIFIER_IDS   # the card a target/modifier decision is about
QUEUE_KINDS = N_KINDS - FIRST_MODIFIER     # cards a Flip Four can queue: everything but numbers
MAX_TASKS = 4
MAX_QUEUE = 4                              # a Flip Four queues at most four cards

# global block
G_NPLAYERS = _block("nplayers", range(2, MAX_PLAYERS + 1))
G_BRUTAL = _block("brutal")
G_KIND = _block("kind", range(N_DECISION_KINDS))          # decision kind
G_CARD = _block("card", CARD_SLOTS)                       # card being resolved
G_SWAP_SLOT = _block("swap_slot", range(MAX_PLAYERS))     # SWAP2: slot of the first card
G_SWAP_CARD = _block("swap_card", range(N_LINE_KINDS))    # SWAP2: kind of the first card
G_DELIVER = _block("deliver", range(N_KINDS))             # DELIVER: the card being delivered
G_BY = _block("by_slot", range(MAX_PLAYERS))              # PAY: slot of the player asking
G_DECK = _block("deck", range(N_KINDS))                   # share of each kind left in the draw pile
G_DECKSIZE = _block("decksize")
G_DISC = _block("disc", range(N_KINDS))                   # share of each kind in the discard pile
G_DISCSIZE = _block("discsize")
G_ROUND = _block("round")
G_GAP = _block("gap")                                     # (target - best total) / target

# per-player block, repeated for slots 0..5; offsets relative to the slot's start
P_FIELDS = (["present"] + [("status", s) for s in range(3)] + [("line", c) for c in range(N_LINE_KINDS)]
            + ["count", "sum", "proj", "total", "totproj", "reach", "margin", "bust", "new", "ev", "f7",
               "late", "dealer", "turnpos", "forced", "queued", "jom", "todeal",
               "frozen", "bounty", "dare", "spite"])
P_DIM = len(P_FIELDS)
_P = {f: i for i, f in enumerate(P_FIELDS)}
P_PRESENT, P_STATUS, P_LINE = _P["present"], _P[("status", 0)], _P[("line", 0)]
(P_COUNT, P_SUM, P_PROJ, P_TOTAL, P_TOTPROJ, P_REACH, P_MARGIN, P_BUST, P_NEW, P_EV, P_F7, P_LATE, P_DEALER,
 P_TURNPOS, P_FORCED, P_QUEUED, P_JOM, P_TODEAL, P_FROZEN, P_BOUNTY, P_DARE, P_SPITE) = (
    _P[f] for f in ("count", "sum", "proj", "total", "totproj", "reach", "margin", "bust", "new", "ev", "f7",
                    "late", "dealer", "turnpos", "forced", "queued", "jom", "todeal",
                    "frozen", "bounty", "dare", "spite"))
G_PLAYERS = len(FEATURES)
for _s in range(MAX_PLAYERS):
    FEATURES.extend(("p", _s) + (f if isinstance(f, tuple) else (f,)) for f in P_FIELDS)

# pending resolutions: where normal turns resume, the opening deal, the ordered task stack
X_TURNS = _block("turns", range(MAX_PLAYERS))
X_DEAL = _block("deal")
TASK_FIELDS = ([("type", t) for t in range(3)] + [("owner", s) for s in range(MAX_PLAYERS)] + ["draws"]
               + [("queue", j, FIRST_MODIFIER + q) for j in range(MAX_QUEUE) for q in range(QUEUE_KINDS)])
TASK_DIM = len(TASK_FIELDS)
T_TYPE, T_OWNER, T_DRAWS, T_QUEUE_CARDS = 0, 3, 9, 10
X_TASKS = len(FEATURES)
for _k in range(MAX_TASKS):
    FEATURES.extend(("task", _k) + (f if isinstance(f, tuple) else (f,)) for f in TASK_FIELDS)

# DELIVER: what the revealed card would do to each player who can get it: bust them, complete their Flip 7,
# and the change to their round score. Last in the layout, so networks from before it are a prefix (remap.pad_inputs).
DLV_FIELDS = ("busts", "f7", "gain")
DLV_BUSTS, DLV_F7, DLV_GAIN = range(3)
X_DELIVERY = len(FEATURES)
for _s in range(MAX_PLAYERS):
    FEATURES.extend(("dlv", _s, f) for f in DLV_FIELDS)
OBS_DIM = len(FEATURES)
FEATURES = tuple(FEATURES)

_CARD_SLOT = {c: i for i, c in enumerate(CARD_SLOTS)}
_INV_COUNTS = [1.0 / k if k else 0.0 for k in COUNTS]


def action_name(a):
    """The relative action's name: ("stay",), ("hit",), ("player", slot) or ("card", slot, card)."""
    if a < A_PLAYER0:
        return ("stay",) if a == 0 else ("hit",)
    if a < A_CARD0:
        return ("player", a - A_PLAYER0)
    return ("card",) + divmod(a - A_CARD0, N_LINE_KINDS)


ACTIONS = tuple(action_name(a) for a in range(N_ACTIONS))


def rel_to_abs(a, me, n):
    if a < A_PLAYER0:
        return a
    if a < A_CARD0:
        return A_PLAYER0 + (me + a - A_PLAYER0) % n
    s, c = divmod(a - A_CARD0, N_LINE_KINDS)
    return A_CARD0 + ((me + s) % n) * N_LINE_KINDS + c


def abs_to_rel(a, me, n):
    if a < A_PLAYER0:
        return a
    if a < A_CARD0:
        return A_PLAYER0 + (a - A_PLAYER0 - me) % n
    p, c = divmod(a - A_CARD0, N_LINE_KINDS)
    return A_CARD0 + ((p - me) % n) * N_LINE_KINDS + c


def encode(game, obs=None, mask=None):
    """Encode the pending decision from the deciding player's point of view.

    Fills (or allocates) ``obs`` [OBS_DIM] and ``mask`` [N_ACTIONS]; returns (obs, mask, me).
    """
    if obs is None:
        obs = np.zeros(OBS_DIM, np.float32)
    else:
        obs.fill(0.0)
    if mask is None:
        mask = np.zeros(N_ACTIONS, bool)
    else:
        mask.fill(False)
    d = game.decision
    me = d.player
    n = game.n
    rules = game.rules
    brutal = rules.brutal
    target = rules.target
    players = game.players

    obs[G_NPLAYERS + n - 2] = 1.0
    obs[G_BRUTAL] = brutal
    obs[G_KIND + d.kind] = 1.0
    if d.kind == D_DELIVER:
        obs[G_DELIVER + d.card] = 1.0
    elif d.card in _CARD_SLOT:
        obs[G_CARD + _CARD_SLOT[d.card]] = 1.0
    if d.kind == D_SWAP2:
        q, c = decode_card(d.first)
        obs[G_SWAP_SLOT + (q - me) % n] = 1.0
        obs[G_SWAP_CARD + c] = 1.0
    elif d.kind == D_PAY:
        obs[G_BY + (d.by - me) % n] = 1.0

    deck_counts = [0] * N_KINDS
    for c in game.deck:
        deck_counts[c] += 1
    disc_counts = [0] * N_KINDS
    for c in game.discard:
        disc_counts[c] += 1
    for k in range(N_KINDS):
        obs[G_DECK + k] = deck_counts[k] * _INV_COUNTS[k]
        obs[G_DISC + k] = disc_counts[k] * _INV_COUNTS[k]
    obs[G_DECKSIZE] = len(game.deck) / DECK_SIZE
    obs[G_DISCSIZE] = len(game.discard) / DECK_SIZE
    obs[G_ROUND] = game.round / 20.0
    best_total = max(pl.total for pl in players)
    obs[G_GAP] = (target - best_total) / target

    if game.deck:
        pool, pool_size = deck_counts, len(game.deck)
    else:
        pool, pool_size = disc_counts, len(game.discard)

    forced = [0] * n
    queued = [0] * n
    jom = [0] * n
    todeal = [0] * n
    k = 0
    for task in reversed(game.stack):   # top of the stack resolves next
        t = task[0]
        if t == T_TURNS:
            obs[X_TURNS + (task[1] - me) % n] = 1.0
            continue
        if t == T_DEAL:
            obs[X_DEAL] = 1.0
            for i in range(task[1], n + 1):
                todeal[(game.dealer + i) % n] = 1
            continue
        if t == T_FLIP4:
            forced[task[1]] += task[2]
            queued[task[1]] += len(task[3])
            queue, ttype, draws = task[3], 0, task[2]
        elif t == T_QUEUE:
            queued[task[1]] += len(task[2])
            queue, ttype, draws = task[2], 1, 0
        elif t == T_JOM_STAY:
            jom[task[1]] = 1
            queue, ttype, draws = (), 2, 0
        else:
            continue
        if k < MAX_TASKS:
            base = X_TASKS + k * TASK_DIM
            obs[base + T_TYPE + ttype] = 1.0
            obs[base + T_OWNER + (task[1] - me) % n] = 1.0
            obs[base + T_DRAWS] = draws / 4.0
            for j, c in enumerate(queue[:MAX_QUEUE]):
                obs[base + T_QUEUE_CARDS + j * QUEUE_KINDS + (c - FIRST_MODIFIER)] = 1.0
            k += 1
    if d.kind == D_HIT_STAY:
        # the turn continuation is only pushed once this decision is made: turns go on to my left
        obs[X_TURNS + 1 % n] = 1.0

    projs = [game.projected(p) for p in range(n)]
    tp = [players[p].total + projs[p] for p in range(n)]
    for p in range(n):
        pl = players[p]
        slot = (p - me) % n
        base = G_PLAYERS + slot * P_DIM
        obs[base + P_PRESENT] = 1.0
        obs[base + P_STATUS + pl.status] = 1.0
        cnt = 0
        s = 0
        for c in pl.line:
            obs[base + P_LINE + c] += 1.0   # keepers can be held twice
            if c < N_NUMBER_KINDS:
                cnt += 1
                s += RANK[c]
        obs[base + P_COUNT] = cnt / 7.0
        obs[base + P_SUM] = s / 60.0
        obs[base + P_PROJ] = projs[p] / 60.0
        obs[base + P_TOTAL] = pl.total / target
        obs[base + P_TOTPROJ] = tp[p] / target
        obs[base + P_REACH] = tp[p] >= target
        other_best = max(tp[q] for q in range(n) if q != p)
        obs[base + P_MARGIN] = (tp[p] - other_best) / 100.0
        if pl.status != BUSTED:
            pb, pn, ev = draw_stats(pl.line, pool, pool_size)
            obs[base + P_BUST] = pb
            obs[base + P_NEW] = pn
            obs[base + P_EV] = ev / 13.0
            if cnt == 6:
                obs[base + P_F7] = pn
        else:
            obs[base + P_LATE] = sum(MOD_PENALTY[m] for m in pl.late_mods) / 30.0
        obs[base + P_DEALER] = p == game.dealer
        obs[base + P_TURNPOS] = ((p - game.dealer - 1) % n) / n
        obs[base + P_FORCED] = forced[p] / 4.0
        obs[base + P_QUEUED] = queued[p] / 4.0
        obs[base + P_JOM] = jom[p]
        obs[base + P_TODEAL] = todeal[p] and pl.status == 0
        obs[base + P_FROZEN] = pl.frozen
        obs[base + P_BOUNTY] = pl.bounty / 2.0
        obs[base + P_DARE] = pl.dare / 2.0
        obs[base + P_SPITE] = pl.spite / 20.0

    if d.kind == D_DELIVER:
        c = d.card
        for a in d.options:
            p = decode_player(a)
            base = X_DELIVERY + ((p - me) % n) * len(DLV_FIELDS)
            line = players[p].line
            if c < N_NUMBER_KINDS and c in busting_kinds(line):
                obs[base + DLV_BUSTS] = 1.0
                after = -sum(MOD_PENALTY.get(x, 0) for x in line) if brutal else 0
            else:
                new = [c] if c == U7 else line + [c] if c < N_LINE_KINDS else line
                after = line_score(new, False, brutal)
                if c < N_NUMBER_KINDS and c != U7 and sum(x < N_NUMBER_KINDS for x in new) == 7:
                    obs[base + DLV_F7] = 1.0
            obs[base + DLV_GAIN] = (after - line_score(line, False, brutal)) / 60.0

    for a in d.options:
        mask[abs_to_rel(a, me, n)] = True
    return obs, mask, me


def winner_target(game, me):
    """Win shares of the finished game in slot order relative to ``me`` [MAX_PLAYERS]."""
    out = np.zeros(MAX_PLAYERS, np.float32)
    r = game.returns()
    for p in range(game.n):
        out[(p - me) % game.n] = r[p]
    return out
