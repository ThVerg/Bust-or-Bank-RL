import torch

from flip7.cards import SWAP
from flip7.engine import D_SWAP1, D_SWAP2, Game, a_card
from flip7.model import Net
from flip7.search import RolloutBot, SearchBot


def _swap_state():
    # 3 players, dealer 2. Deal: p0=10, p1=11, p2=5; p0 hits 3, p1 hits 7, p2 hits Swap
    g = Game(3, dealer=2, deck=[10, 11, 5, 3, 7, SWAP] + [1, 2, 4, 6, 8, 9, 12, 13] * 3)
    for _ in range(3):
        g.step(1)
    assert g.decision.kind == D_SWAP1 and g.decision.player == 2
    return g


def test_one_ply_search_judges_swaps_after_the_exchange():
    torch.manual_seed(0)
    bot = SearchBot(Net(32, 2), seed=1)
    g = _swap_state()
    w, child = bot._children(g, a_card(2, 5))[0]
    assert child.decision.kind == D_SWAP2  # the half-finished swap...
    done = bot._complete(child, 2)
    assert len(done) == 4  # ...is expanded into every second card
    assert all(x.decision is None or x.decision.kind != D_SWAP2 for x in done)
    assert {5} <= {c for x in done for p in (0, 1) for c in x.players[p].line}
    q = bot.evaluate(g)
    assert set(q) == set(g.legal())
    assert g.decision.kind == D_SWAP1  # searching never changes the real game


def test_rollouts_search_swap_pairs_and_cover_every_target():
    torch.manual_seed(0)
    bot = RolloutBot(Net(32, 2), k=4, max_actions=3, pair_width=2, seed=1)
    g = _swap_state()
    seqs = bot._sequences(g)
    assert any(len(s) == 2 for s in seqs)
    owners = {s[0] for s in seqs}
    assert len(owners) == 3  # pruned to 3 first cards, one per owner (p0, p1, p2)
    q = bot.evaluate(g)
    assert set(q) <= set(g.legal()) and len(q) == 3


def test_rollout_temperature_runs():
    torch.manual_seed(0)
    bot = RolloutBot(Net(32, 2), k=3, rollout_temp=1.0, seed=2)
    g = Game(2, seed=5)
    a = bot.act(g)
    assert a in g.legal()


def test_search_draws_from_the_pile_as_it_is_at_the_draw():
    # p1 stays with an empty deck and discards {3, 4}; that ends the round, the table's 5 and 9
    # join the discards, and the next deal comes from the reshuffled {3, 4, 5, 9}.
    from flip7.engine import A_STAY
    g = Game(2, dealer=1, deck=[5, 9])
    g.step(A_STAY)  # p0 stays on 5
    assert g.decision.player == 1 and not g.deck
    g.discard = [3, 4]
    bot = SearchBot(Net(32, 2), seed=1)
    children = bot._children(g, A_STAY)
    first = {}
    for w, child in children:  # new round: dealer p0, so p1 is dealt first
        c = child.players[1].line[0]
        first[c] = first.get(c, 0) + w
    assert set(first) == {3, 4, 5, 9}
    assert all(abs(w - 0.25) < 1e-9 for w in first.values())


def test_benchmark_games_do_not_depend_on_earlier_games(tmp_path):
    from flip7 import benchmark
    from flip7.model import save
    torch.manual_seed(0)
    path = str(tmp_path / "m.pt")
    save(Net(32, 2), path, version=1)
    spec = f"search:{path}"
    first = benchmark.play([spec, "smart"], 11)
    benchmark.play([spec, "smart"], 12)  # an unrelated game in between must not change game 11
    assert benchmark.play([spec, "smart"], 11) == first
    assert set(benchmark.provenance([spec])[path]) == {"sha256", "bytes"}


def test_adaptive_bot_skips_obvious_decisions_and_bounds_its_search():
    from flip7.search import AdaptiveBot
    torch.manual_seed(0)
    g = Game(3, seed=4)
    lazy = AdaptiveBot(Net(32, 2), obvious=0.0, seed=1)  # every non-endgame decision counts as obvious
    assert lazy.act(g) in g.legal() and lazy.last_orders == 0
    bot = AdaptiveBot(Net(32, 2), k_min=8, k_max=16, batch=8, obvious=1.1, budget_s=5.0, seed=1)
    for _ in range(6):
        if g.over:
            break
        a = bot.act(g)
        assert a in g.legal()
        assert len(g.legal()) == 1 or 8 <= bot.last_orders <= 32
        g.step(a)


def test_boss_uses_rollouts_for_swaps_and_the_network_for_endgame_hit_or_stay():
    from flip7.engine import D_HIT_STAY
    from flip7.model import NeuralBot
    from flip7.search import BossBot
    torch.manual_seed(0)
    net = Net(32, 2)
    boss = BossBot(net, k=4, seed=1)
    g = _swap_state()
    assert boss._searcher(g) is boss.rollout and boss.act(g) in g.legal()
    g = Game(3, seed=2)
    while g.decision.kind != D_HIT_STAY or len(g.legal()) < 2:
        g.step(g.legal()[0])
    assert boss._searcher(g) is boss.search
    end = Game(3, seed=2, totals=[195, 0, 0])  # someone can reach 200 this round
    while end.decision.kind != D_HIT_STAY or len(end.legal()) < 2:
        end.step(end.legal()[0])
    assert boss._searcher(end) is None and boss.act(end) == NeuralBot(net).act(end)
    swaps_only = BossBot(net, k=4, seed=1, endgame_policy=False)
    assert swaps_only._searcher(end) is swaps_only.search
