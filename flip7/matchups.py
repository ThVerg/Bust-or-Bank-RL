"""Run the standard head-to-head line-up and write analysis/matchups.json for the Insights page.

    python -m flip7.matchups --model models/flip7_rl.pt --games 1000 --workers 3
"""
import argparse
import json
import os

from .evaluate import evaluate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "flip7_rl.pt"))
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--boss", default="", help="the strongest level's bot spec (default: search:<model>)")
    ap.add_argument("--boss-games", type=int, default=400, help="games per Boss match-up (search is slower)")
    ap.add_argument("--out", default=os.path.join(ROOT, "analysis", "matchups.json"))
    a = ap.parse_args()
    rl = f"nn:{a.model}"
    boss = a.boss or f"search:{a.model}"
    names = {rl: "RL bot", boss: "RL + Search", "smart": "SmartBot", "threshold25": "Hit-to-25", "random": "Random"}
    lineup = [(rl, "smart", n) for n in (2, 3, 4, 5, 6)]
    lineup += [(rl, "threshold25", 2), (rl, "threshold25", 4), (rl, "random", 4),
               ("smart", "threshold25", 2), ("smart", "threshold25", 4), ("smart", "random", 4)]
    lineup += [(boss, "smart", n) for n in (2, 4, 6)] + [(boss, rl, 2), (boss, rl, 4)]
    table, vs_smart = [], {}
    for hero, villain, n in lineup:
        p, se, cnt = evaluate(hero, villain, n, a.boss_games if hero == boss else a.games, a.workers)
        print(f"{names[hero]} vs {names[villain]} ({n}p): {p:.3f} ± {1.96 * se:.3f}", flush=True)
        table.append({"hero": names[hero], "villain": names[villain], "n": n, "p": p, "se": se, "games": cnt})
        if hero == rl and villain == "smart":
            vs_smart[str(n)] = {"p": p, "se": se, "games": cnt}
    with open(a.out, "w") as f:
        json.dump({"matchups": vs_smart, "matchups_table": table}, f, indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
