import random

import torch

from flip7.cards import SWAP
from flip7.coach import facts, review
from flip7.engine import A_HIT, A_STAY, Game, a_card
from flip7.model import Net

NAMES = ["Ann", "Bo", "Cy"]


def test_review_scores_every_decision_and_explains_it():
    torch.manual_seed(0)
    g = Game(3, seed=2)
    rng = random.Random(0)
    decisions = []
    while not g.over and len(decisions) < 6:
        a = rng.choice(g.legal())
        if g.decision.player == 0 and len(g.legal()) > 1:
            decisions.append({"game": g.clone(random.Random(0)), "chosen": a, "round": g.round})
        g.step(a)
    out = review(Net(32, 2), decisions, NAMES, k=8)
    assert out["decisions"] == len(decisions) and 0 <= out["good"] <= out["decisions"]
    for m in out["moments"]:
        assert m["loss"] >= -1e-9 and m["ci"] >= 0
        assert any(o["a"] == m["chosen"] for o in m["options"])
        assert len(m["table"]["players"]) == 3


def test_facts_come_from_the_rules():
    # p0 holds 3 and 10, p1 holds 10 and 7; p2 swaps p0's 3 for p1's 10, which busts p0
    g = Game(3, dealer=2, deck=[3, 10, 5, 10, 7, SWAP] + [1, 2, 4, 6, 8, 9, 12, 13] * 3)
    for _ in range(3):
        g.step(A_HIT)
    g.step(a_card(0, 3))
    assert any("busts Ann" in f for f in facts(g, a_card(1, 10), NAMES))
    h = Game(2, dealer=1, deck=[5, 9, 5, 2] * 10)
    stay, hit = facts(h, A_STAY, NAMES), facts(h, A_HIT, NAMES)
    assert stay[0].startswith("Banks 5") and "bust you" in hit[0]
