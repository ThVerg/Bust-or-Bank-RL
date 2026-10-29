"""Card-counting statistics derived from the public state.

Every card is dealt face up, so the multiset of the draw pile is public knowledge; only its
order is hidden (uniformly random). These helpers turn that into per-player probabilities.
"""
from __future__ import annotations

from .cards import DIV2, FIRST_MODIFIER, FIRST_KEEPER, L14, MOD_PENALTY, N_KINDS, N_NUMBER_KINDS, RANK, U7, ZERO
from .engine import BUSTED


def next_card_pool(game):
    """Counts of the cards the next draw comes from (the discard pile if the deck is empty)."""
    counts = [0] * N_KINDS
    for c in (game.deck if game.deck else game.discard):
        counts[c] += 1
    return counts


def busting_kinds(line):
    """Number kinds that would bust a player holding ``line`` if drawn next."""
    held = set()
    fourteens = 0
    has_l14 = L14 in line
    for c in line:
        if c < N_NUMBER_KINDS:
            r = RANK[c]
            if r == 14:
                fourteens += 1
            else:
                held.add(r)
    out = []
    for c in range(N_NUMBER_KINDS):
        if c == U7:
            continue  # the Unlucky Frozen 7 never busts on arrival
        r = RANK[c]
        if r == 14:
            limit = 2 if (has_l14 or c == L14) else 1
            if fourteens + 1 > limit:
                out.append(c)
        elif r in held:
            out.append(c)
    return out


def draw_stats(line, pool, pool_size):
    """(p_bust, p_new_number, expected rank of a safe new number) for the next card."""
    if pool_size == 0 or line is None:
        return 0.0, 0.0, 0.0
    bust = set(busting_kinds(line))
    p_bust = 0
    p_new = 0
    ev = 0
    for c in range(N_NUMBER_KINDS):
        k = pool[c]
        if not k:
            continue
        if c in bust:
            p_bust += k
        elif c != U7:
            p_new += k
            ev += k * RANK[c]
    return p_bust / pool_size, p_new / pool_size, (ev / p_new if p_new else 0.0)


def player_stats(game, p, pool=None, pool_size=None):
    """Dict of handy numbers about player p (used by the heuristic bot and analysis)."""
    if pool is None:
        pool = next_card_pool(game)
        pool_size = sum(pool)
    pl = game.players[p]
    nums = [c for c in pl.line if c < N_NUMBER_KINDS]
    out = {
        "status": pl.status,
        "count": len(nums),
        "sum": sum(RANK[c] for c in nums),
        "zero": ZERO in pl.line,
        "div2": DIV2 in pl.line,
        "penalty": sum(MOD_PENALTY[c] for c in pl.line if FIRST_MODIFIER <= c < FIRST_KEEPER),
        "proj": game.projected(p),
        "total": pl.total,
    }
    if pl.status == BUSTED:
        out.update(p_bust=0.0, p_new=0.0, ev_new=0.0)
    else:
        out["p_bust"], out["p_new"], out["ev_new"] = draw_stats(pl.line, pool, pool_size)
    return out
