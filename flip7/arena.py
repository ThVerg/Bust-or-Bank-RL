"""Play bots against each other and measure win rates."""
from __future__ import annotations

import random

from .engine import Game, Rules


def play_game(bots, seed=None, rules=None, dealer=None):
    """Play one game; ``bots[p]`` controls seat p. Returns the finished Game."""
    rng = random.Random(seed)
    n = len(bots)
    g = Game(n, rules=rules, rng=rng, dealer=rng.randrange(n) if dealer is None else dealer)
    while not g.over:
        g.step(bots[g.decision.player].act(g))
    return g


def win_rates(make_bots, n_games, seed=0, rules=None):
    """Average win share per seat-role; ``make_bots(i)`` returns (bots, roles) for game i.

    Roles are labels like "smart"/"random"; seats are rotated by the caller as it likes.
    """
    totals = {}
    counts = {}
    for i in range(n_games):
        bots, roles = make_bots(i)
        g = play_game(bots, seed=seed * 1_000_003 + i, rules=rules)
        for r, share in zip(roles, g.returns()):
            totals[r] = totals.get(r, 0.0) + share
            counts[r] = counts.get(r, 0) + 1
    return {r: totals[r] / counts[r] for r in totals}, counts
