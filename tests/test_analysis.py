from flip7.analyze import PLAYER_COUNTS, _play_batch, summarize
from flip7.findings import build


def _smart_tables(games=6):
    rows = {"hit_stay": [], "target": [], "cards": [], "new": []}
    outs = {}
    for n in PLAYER_COUNTS:
        _, _, r, o = _play_batch(("", "smart", n, games, n))
        for k in rows:
            rows[k].extend(r[k])
        outs[n] = o
    return summarize({"smart": rows}, {"smart": outs})["tables"]["smart"]


def test_summary_compares_stays_with_and_without_minus_cards():
    T = _smart_tables()
    m = T["minus_cards"]
    assert m["n_held"] > 0 and m["n_clean"] > m["n_held"]
    assert len(m["stay_by_pbust_held"]) == len(m["stay_by_pbust_clean"]) == 12


def test_findings_are_written_from_the_numbers():
    T = _smart_tables()
    out = build({"tables": {"rl": T, "smart": T}})
    assert len(out) >= 6
    assert all(x.startswith("<b>") and "None" not in x and "nan" not in x for x in out)


def test_exploitability_bundles_each_exploiter_with_its_benchmark(tmp_path):
    import json
    from flip7.exploitability import build
    runs = []
    for name, init in (("xg4", "t.pt"), ("xs2", "")):
        run = tmp_path / name
        run.mkdir()
        (run / "config.json").write_text(json.dumps({"exploit": "t.pt", "init": init, "hours": 4.0, "n_choices": [4]}))
        (run / "eval.jsonl").write_text("".join(json.dumps({"time": 1000 + 1800 * v, "anchor_avg_edge": e}) + "\n"
                                                for v, e in enumerate((0.0, 0.6, 0.97, 1.01))))
        (run / "log.jsonl").write_text(json.dumps({"update": 900, "total_games": 1500000}) + "\n")
        bench = tmp_path / f"{name}.json"
        bench.write_text(json.dumps({"seeds": 600, "split": "dev", "rows": [
            {"lineup": "self", "n": 4, "games": 2400, "candidate": 0.247, "incumbent": 0.25, "diff": -0.003, "ci95": 0.017}]}))
        runs.append((str(run), str(bench)))
    out = build(runs)
    warm, scratch = out["exploiters"]
    assert out["target"] == "t.pt" and warm["games"] == 1500000 and not warm["from_scratch"]
    assert "reached_level_hours" not in warm and scratch["reached_level_hours"] == 1.0  # first eval within 5%
    assert warm["bench"]["rows"] == [{"n": 4, "games": 2400, "candidate": 0.247, "incumbent": 0.25, "diff": -0.003, "ci95": 0.017}]


def test_tactical_positions_are_valued_on_shared_shuffles_and_scored_against_the_policy(tmp_path):
    import random
    import torch
    from flip7.engine import Game, Rules
    from flip7.model import Net, load, save
    from flip7.tactics import _evaluate, action_values, score
    torch.manual_seed(0)
    path = str(tmp_path / "tiny.pt")
    save(Net(32, 2, 48, 2), path)
    model = load(path)[0]
    g = Game(3, rules=Rules(), rng=random.Random(5))
    while len(g.legal()) < 2:
        g.step(g.legal()[0])
    a = g.legal()[0]
    vals = action_values(model, g, [a, a], [0.1, 0.2, 0.3, 0.4])
    assert vals.shape == (2, 4) and (vals[0] == vals[1]).all()  # same action, same shuffles: same games
    pos = {"id": "t/0", "kind": "swap", "game": g.clone(random.Random(0)),
           **_evaluate(model, g, "t/0", select=4, verify=8, max_actions=10)}
    assert pos["gain"][pos["policy"]] == (0.0, 0.0) and pos["challenger"] != pos["policy"]
    r = score({"model": path, "verify": 8, "positions": [pos]}, f"nn:{path}", workers=1)
    assert r["overall"]["gain"] == 0 and r["overall"]["agree"] == 1  # the network scores itself as zero


def test_probe_scores_each_bot_against_the_best_move():
    from flip7.probe import _work
    rows = _work(("models/flip7_rl.pt", ["nn:models/flip7_rl.pt", "random"], ["deliver", "hit_stay"], 1, 4, 3, 3))
    assert set(rows) == {"deliver", "hit_stay"}
    assert all(r["random"] >= 0 and r["nn:models/flip7_rl.pt"] >= 0 for rs in rows.values() for r in rs)
