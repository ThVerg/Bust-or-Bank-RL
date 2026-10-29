import random

import numpy as np
import torch

from flip7.cards import FLIP4, JOM, M10
from flip7.encoding import OBS_DIM, encode
from flip7.engine import D_MODIFIER, N_ACTIONS, Game, a_player
from flip7.model import Net, load, save
from flip7.train import Config, Running, _empty_out, _finish, _load_shared, warm_start


def _queue_state(order):
    # 2 players, dealer 0: p1 is dealt Flip Four, targets itself and draws 3 then three specials
    g = Game(2, dealer=0, deck=[FLIP4, 3] + order + [9, 5, 6, 8])
    g.step(a_player(1))
    assert g.decision.kind == D_MODIFIER and g.decision.card == M10
    return g


def test_queued_card_order_is_observable():
    a = _queue_state([M10, JOM, FLIP4])
    b = _queue_state([M10, FLIP4, JOM])
    oa, ma, _ = encode(a)
    ob, mb, _ = encode(b)
    assert (ma == mb).all()
    assert not np.array_equal(oa, ob)


def test_turn_resume_seat_is_observable():
    from flip7.encoding import X_TURNS
    rng = random.Random(2)
    for seed in range(20):
        g = Game(3, seed=seed)
        while not g.over:
            obs, _, _ = encode(g)
            assert obs[X_TURNS:X_TURNS + 6].sum() == (0 if g.flip7_player >= 0 else 1)  # Flip 7: round is over
            g.step(rng.choice(g.legal()))


def test_classic_network_is_carried_over_feature_by_feature(tmp_path):
    from flip7.encoding import ACTIONS, FEATURES
    from flip7.remap import CLASSIC_ACTIONS, CLASSIC_OBS_DIM, classic_actions, classic_features
    torch.manual_seed(0)
    old = Net(64, 2, 48, 2, obs_dim=CLASSIC_OBS_DIM)
    old.pi = torch.nn.Linear(64, CLASSIC_ACTIONS)  # a classic Flip 7 network: 595 inputs, 140 actions
    path = tmp_path / "classic.pt"
    torch.save({"state_dict": old.state_dict(), "config": dict(old.config)}, path)
    new, _ = load(path)
    # the same position in both layouts: every classic input moved to its feature of the same name
    x_old = torch.rand(8, CLASSIC_OBS_DIM)
    where = {name: i for i, name in enumerate(FEATURES)}
    cols = [where[name] for name in classic_features()]
    x_new = torch.zeros(8, OBS_DIM)
    x_new[:, cols] = x_old
    n = torch.full((8,), 4)
    l_old, v_old = old(x_old, torch.ones(8, CLASSIC_ACTIONS, dtype=torch.bool), n)
    l_new, v_new = new(x_new, torch.ones(8, N_ACTIONS, dtype=torch.bool), n)
    rows = [ACTIONS.index(name) for name in classic_actions()]
    assert torch.allclose(l_old, l_new[:, rows], atol=1e-5) and torch.allclose(v_old, v_new, atol=1e-5)
    # the plain 14 has no classic counterpart: it starts as a copy of the 13
    w = new.trunk[0].weight
    assert torch.equal(w[:, where[("deck", 14)]], w[:, where[("deck", 13)]])


def test_older_bust_or_bank_network_plays_the_same_with_the_new_inputs(tmp_path):
    from flip7.encoding import X_DELIVERY
    torch.manual_seed(0)
    old = Net(64, 2, 48, 2, obs_dim=X_DELIVERY)  # before the Special Delivery inputs
    path = tmp_path / "bob1.pt"
    save(old, path)
    new, _ = load(path)
    x = torch.rand(8, OBS_DIM)  # whatever the new inputs say, it plays as before
    mask, n = torch.ones(8, N_ACTIONS, dtype=torch.bool), torch.full((8,), 4)
    l_old, v_old = old(x[:, :X_DELIVERY], mask, n)
    l_new, v_new = new(x, mask, n)
    assert torch.allclose(l_old, l_new, atol=1e-6) and torch.allclose(v_old, v_new, atol=1e-6)


def test_delivery_inputs_say_what_the_card_does_to_each_player():
    from flip7.cards import DELIVERY
    from flip7.encoding import DLV_BUSTS, DLV_FIELDS, DLV_GAIN, X_DELIVERY
    from flip7.engine import D_DELIVER
    # 2 players, dealer 0: p1 is dealt a 5, p0 a Special Delivery that reveals another 5
    g = Game(2, dealer=0, deck=[5, DELIVERY, 5, 9, 8, 6])
    assert g.decision.kind == D_DELIVER and g.decision.player == 0 and g.decision.card == 5
    obs, _, _ = encode(g)
    me, rival = X_DELIVERY, X_DELIVERY + len(DLV_FIELDS)
    assert obs[me + DLV_BUSTS] == 0 and obs[me + DLV_GAIN] == np.float32(5 / 60)
    assert obs[rival + DLV_BUSTS] == 1 and obs[rival + DLV_GAIN] == np.float32(-5 / 60)
    g.step(a_player(0))
    assert not encode(g)[0][X_DELIVERY:].any()  # only set while a Delivery is being decided


def test_shared_snapshot_is_a_private_copy():
    import multiprocessing as mp
    from torch.nn.utils import parameters_to_vector
    src = Net(32, 2, 32, 2)
    flat = parameters_to_vector(src.parameters()).detach().clone()
    dst = Net(32, 2, 32, 2)
    ver = mp.Value("i", 7)
    assert _load_shared(dst, flat, ver, mp.Lock()) == 7
    before = dst.pi.weight.detach().clone()
    flat.add_(1.0)  # the learner publishing new weights must not touch a running model
    assert torch.equal(dst.pi.weight, before)
    assert torch.allclose(dst.pi.weight, src.pi.weight)


def test_each_decision_keeps_its_behaviour_version():
    g = Game(2, seed=3)
    rng = random.Random(0)
    run = Running(g, ["L", "L"])
    k = 0
    while not g.over:
        p = g.decision.player
        vvec = np.full(6, 0.5, np.float32)
        run.traj[p].append((np.zeros(OBS_DIM, np.float32), np.zeros(N_ACTIONS, bool), 0, -0.1, 0.5, vvec, g.round, 10 + k // 50))
        g.step(rng.choice(g.legal()))
        k += 1
    out = _empty_out()
    _finish(run, Config(), out)
    assert sorted(set(out["ver"])) == sorted({10 + i // 50 for i in range(k)})
    assert len(out["ver"]) == len(out["act"]) == k


def test_resume_keeps_value_head_but_architecture_switch_resets_it(tmp_path):
    torch.manual_seed(1)
    trained = Net(32, 2, 48, 2)
    save(trained, tmp_path / "sep.pt")
    same = Net(32, 2, 48, 2)
    _, _, kept = warm_start(same, tmp_path / "sep.pt", 48)
    assert kept and torch.equal(same.v.weight, trained.v.weight)
    shared = Net(48, 2)  # shared trunk whose v head happens to have the same shape
    save(shared, tmp_path / "shared.pt")
    switched = Net(32, 2, 48, 2)
    fresh_v = switched.v.weight.detach().clone()
    _, _, kept = warm_start(switched, tmp_path / "shared.pt", 48)
    assert not kept and torch.equal(switched.v.weight, fresh_v)


def test_league_prefers_hard_opponents_and_mixes_tables():
    from flip7.engine import Rules
    from flip7.train import HEURISTIC_KEYS, League, _new_game
    league = League()
    for _ in range(200):
        league.update(["easy"], 1.8)
        league.update(["hard"], 0.5)
    rng = random.Random(0)
    picks = [league.sample(rng, ["easy", "hard"]) for _ in range(2000)]
    assert picks.count("hard") > 5 * picks.count("easy")
    cfg = Config(p_self=0.0, p_pool=1.0, n_choices=(6,))
    kinds = set()
    for _ in range(50):
        run = _new_game(rng, cfg, Rules(), ["a.pt", "b.pt"], League())
        seats = {c[1] if isinstance(c, tuple) else ("L" if c == "L" else "bot") for c in run.ctrl}
        kinds.add(len(seats - {"L"}) > 1)
        assert run.opponents <= {"a.pt", "b.pt", *HEURISTIC_KEYS}
    assert True in kinds  # some tables mix different kinds of opponents


def test_exploiter_takes_one_seat_against_the_fixed_checkpoints():
    from flip7.engine import Rules
    from flip7.train import League, _new_game, _samples
    rng = random.Random(0)
    cfg = Config(exploit="target.pt")
    for _ in range(50):
        run = _new_game(rng, cfg, Rules(), ["own_snapshot.pt"], League())
        assert run.ctrl.count("L") == 1
        assert all(c == ("S", "target.pt") for c in run.ctrl if c != "L")
        assert run.opponents == {"target.pt"}
    # the targets play as deployed (greedy); the learner and ordinary league snapshots sample
    assert not _samples(cfg, "target.pt") and _samples(cfg, "L") and _samples(Config(), "own_snapshot.pt")


def test_grown_network_computes_the_same_and_its_copies_can_drift_apart():
    import torch
    from flip7.encoding import OBS_DIM
    from flip7.engine import N_ACTIONS
    from flip7.grow import grow, max_difference
    from flip7.model import Net
    small = Net(32, 2, 48, 2).eval()
    big = grow(small, 64, 3, 96, 3)
    assert big.config["hidden"] == 64 and len(big.trunk) == 3 and len(big.v_trunk) == 3
    assert max_difference(small, big) < 1e-5
    # a unit and its copy start with identical incoming weights; Adam must not keep them identical
    # (units that never fire get no gradient at all, so only live ones are checked)
    w0 = big.trunk[1].weight.detach().clone()
    same = [(i, j) for i in range(64) for j in range(i + 1, 64) if torch.equal(w0[i], w0[j])]
    assert len(same) >= 32
    opt = torch.optim.Adam(big.parameters(), lr=1e-3)
    fired = torch.zeros(64)
    for _ in range(3):
        obs, mask = torch.rand(256, OBS_DIM), torch.ones(256, N_ACTIONS, dtype=torch.bool)
        with torch.no_grad():
            fired += (big.trunk[1](torch.relu(big.trunk[0](obs))) > 0).sum(0)
        logits, v = big(obs, mask, torch.full((256,), 4))
        target = torch.randint(0, N_ACTIONS, (256, 1))
        loss = -(logits.log_softmax(1).gather(1, target).mean() + v.log_softmax(1)[:, 0].mean())
        opt.zero_grad()
        loss.backward()
        opt.step()
    w1 = big.trunk[1].weight.detach()
    live = [(i, j) for i, j in same if fired[i] > 0]
    assert len(live) >= 16 and all(not torch.allclose(w1[i], w1[j]) for i, j in live)


def test_targeted_distillation_asks_the_teacher_only_about_the_chosen_decisions(tmp_path):
    import torch
    from flip7.distill import _collect
    from flip7.engine import DECISION_NAMES
    from flip7.model import Net, save
    torch.manual_seed(0)
    path = str(tmp_path / "tiny.pt")
    save(Net(32, 2, 48, 2), path)
    kinds = ("steal", "discard", "target")
    obs, mask, tgt, imp, gap, kind = _collect((path, 150, 0, "search", 1, -1.0, False, 1.0, 0.5, kinds))
    names = {DECISION_NAMES[k] for k in kind}
    assert imp.any() and {DECISION_NAMES[k] for k in kind[imp]} <= set(kinds)
    assert "hit_stay" in names                     # other decisions are kept, as anchors only
    assert (gap[kind == 0] == 0).all() and not imp[kind == 0].any()
