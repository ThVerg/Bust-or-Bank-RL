"""Write the Insights page's headline findings from the numbers in analysis/insights.json.

    python -m flip7.findings            # after python -m flip7.analyze

Every number in the text is read from insights.json, so the findings stay true when the model or
the rules change. Each finding is "<b>Title.</b> explanation"; one whose data is missing is left out.
"""
from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pct(x):
    return f"{round(100 * x)}%"


def span(xs, fmt=lambda v: f"{round(v)}"):
    xs = [x for x in xs if x is not None]
    lo, hi = fmt(min(xs)), fmt(max(xs))
    return lo if lo == hi else f"{lo}–{hi}"


def pct_span(xs):
    return span([100 * x for x in xs]) + "%"


def crossing(bins, level=0.5):
    """Where a binned rate first rises through ``level`` (linear between bin centres)."""
    prev = None
    for b in bins:
        if b["rate"] is None or b["n"] < 50:
            continue
        mid = (b["lo"] + b["hi"]) / 2
        if b["rate"] >= level:
            if prev is None:
                return mid
            (m0, r0) = prev
            return m0 + (mid - m0) * (level - r0) / (b["rate"] - r0)
        prev = (mid, b["rate"])
    return None


def bin_at(bins, lo):
    for b in bins:
        if abs(b["lo"] - lo) < 1e-9:
            return b["rate"]
    return None


def _push(rl, sm):
    calm = max(b["rate"] for b in rl["stay_by_pbust"] if b["hi"] <= 0.15 + 1e-9 and b["rate"] is not None)
    cross = crossing(rl["stay_by_pbust"])
    bust = [o["bust_rate"] for o in rl["outcomes"].values()]
    sbust = [o["bust_rate"] for o in sm["outcomes"].values()]
    past = 5 * int(min(rl["stay_threshold_by_n"].values()) // 5)
    never = ("stays less than 1% of the time while its bust chance is under 15%" if calm < 0.01 else
             f"almost never stays while its bust chance is under 15% ({pct(calm)} of the time at most)")
    return (f"<b>Push past {past}.</b> The RL bot {never}. Staying only becomes more likely than hitting at about a "
            f"{pct(cross)} bust chance, which is about {span(rl['stay_threshold_by_n'].values())} points. "
            f"It busts in {pct_span(bust)} of its rounds, against {pct_span(sbust)} for SmartBot's careful play, "
            f"and still wins more: in a race to 200, big rounds matter more than safe ones.")


def _scoreboard(rl, sm):
    risk = rl["risk_by_gap"]
    behind, level, ahead = risk[0]["threshold"], next(b for b in risk if b["lo"] == -10)["threshold"], risk[-1]["threshold"]
    return (f"<b>Let the scoreboard set your risk.</b> 100+ points behind the leading rival, it keeps hitting "
            f"until about {round(behind)} points. Level, about {round(level)}. 100+ ahead, it banks at about "
            f"{round(ahead)}. SmartBot's stay point hardly moves ({span(b['threshold'] for b in sm['risk_by_gap'])}).")


def _weapons(rl, sm):
    t, s = rl["targeting"], sm["targeting"]
    self_rate = max(t["flip4"]["self_rate"], t["jom"]["self_rate"])
    lead = (t["flip4"]["leader_rate"] + t["jom"]["leader_rate"]) / 2
    rand = (t["flip4"]["random_leader_rate"] + t["jom"]["random_leader_rate"]) / 2
    use = "under 1%" if self_rate < 0.01 else pct(self_rate)
    return (f"<b>Flip Four and Just One More are weapons, never self-help.</b> It uses them on itself in {use} "
            f"of cases (SmartBot: {pct(s['flip4']['self_rate'])} and {pct(s['jom']['self_rate'])}), and aims them "
            f"at the leader {pct(lead)} of the time, where a random opponent would be {pct(rand)}.")


def _div2(rl, sm):
    d, s = rl["targeting"]["div2"], sm["targeting"]["div2"]
    return (f"<b>÷2 goes to the leader, not the biggest hand.</b> {pct(d['leader_rate'])} of ÷2 cards go to the "
            f"player with the highest total. SmartBot gives it to the biggest current hand "
            f"({pct(s['max_sum_rate'])} of the time), which is the leader only {pct(s['leader_rate'])} of the time.")


def _busted(rl, sm):
    m = rl["targeting"]["minus"]
    if m.get("busted_when_possible") is None or m["busted_when_possible"] < 0.35:  # no habit worth a headline
        return None
    return (f"<b>Kick them while they're down (Brutal Mode).</b> When a busted rival is available, it gives them "
            f"the minus card {pct(m['busted_when_possible'])} of the time. A busted player keeps their minus cards, "
            f"so busting doesn't protect a leader from losing points.")


def _minus_held(rl, sm):
    m = rl.get("minus_cards")
    if not m or None in (m.get("pbust_threshold_held"), m.get("pbust_threshold_clean"),
                         m.get("score_threshold_held"), m.get("score_threshold_clean")):
        return None
    pb_h, pb_c = m["pbust_threshold_held"], m["pbust_threshold_clean"]
    sc_h, sc_c = m["score_threshold_held"], m["score_threshold_clean"]
    if sc_h < sc_c - 1 and pb_h > pb_c - 0.02:
        return (f"<b>Minus cards are already paid for (Brutal Mode).</b> A bust keeps your minus cards, so they count "
                f"whether you stay or bust: hitting only risks your number cards. The bot plays it that way. Holding "
                f"minus cards it stays at a lower round score (about {round(sc_h)} vs {round(sc_c)} points) but at "
                f"{'a higher' if pb_h > pb_c + 0.04 else 'a slightly higher' if pb_h > pb_c + 0.01 else 'the same'} "
                f"bust chance ({pct(pb_h)} vs {pct(pb_c)}).")
    return (f"<b>Minus cards and the stopping point (Brutal Mode).</b> Holding minus cards it stays at about "
            f"{round(sc_h)} points and a {pct(pb_h)} bust chance; with a clean line at about {round(sc_c)} points "
            f"and {pct(pb_c)}.")


def _seventh(rl, sm):
    six = rl["six_cards"]
    risky = bin_at(six["by_pbust"], 0.4)
    f7 = [o["flip7_rate"] for o in rl["outcomes"].values()]
    sf7 = [o["flip7_rate"] for o in sm["outcomes"].values()]
    ratio = (sum(f7) / len(f7)) / max(sum(sf7) / len(sf7), 1e-9)
    times = "about twice as often as" if 1.7 <= ratio <= 2.3 else f"{ratio:.1f}× as often as"
    fmt = lambda v: f"{100 * v:.1f}".rstrip("0").rstrip(".")
    return (f"<b>Go for the seventh card.</b> Holding six different numbers it hits {pct(six['hit_rate'])} of the time, "
            f"and still {pct(risky)} of the time at a 40–50% bust risk: Flip 7 is worth +15 and ends the round before "
            f"rivals can catch up. It Flips 7 {times} SmartBot ({span(f7, fmt)}% vs {span(sf7, fmt)}% of rounds).")


def _flip7(rl, sm):
    f = rl["targeting"]["flip7"]
    by_n = f["penalty_rate_by_n"]
    many = [by_n[k] for k in ("4", "5", "6") if by_n.get(k) is not None]
    return (f"<b>+15 when ahead, −15 only to slow a runaway leader.</b> After a Flip 7 it takes the +15 "
            f"{pct(f['self_rate'])} of the time. "
            + ("It never chooses −15 while leading" if f["penalty_when_leading"] < 0.005 else
               f"It rarely chooses −15 while leading ({pct(f['penalty_when_leading'])})")
            + f", "
            f"but does so {pct(f['penalty_when_trailing'])} of the time while trailing, aimed at the leader "
            f"{pct(f['penalty_leader_rate'])} of the time. The more players, the less −15 is worth "
            f"({pct_span(many)} at 4–6 players vs {pct(by_n['2'])} one-on-one), because it only hurts one of several rivals.")


def _shakedown(rl, sm):
    p, s = rl["new_cards"]["pay"], sm["new_cards"]["pay"]
    risky = bin_at(p["pay_by_pbust"], 0.3)
    cross = crossing(p["pay_by_pbust"])
    title = "Don't pay the Shakedown." if p["pay_rate"] < 0.05 else "Pay the Shakedown only when a card is dangerous."
    when = (f"Paying only becomes more likely than drawing at about a {pct(cross)} bust chance" if cross is not None else
            f"Even at a 30–40% bust chance it pays only {pct(risky)} of the time")
    paid = f"under 1% of the time" if p["pay_rate"] < 0.01 else f"{pct(p['pay_rate'])} of the time"
    smart = ("SmartBot, which works the odds out card by card, comes to the same answer: it pays "
             + (f"under 1% of the time." if s["pay_rate"] < 0.01 else f"{pct(s['pay_rate'])} of the time.")
             if s["pay_rate"] < 0.05 else f"SmartBot pays {pct(s['pay_rate'])} of the time.")
    return (f"<b>{title}</b> Offered the choice between paying a rival 10 points and taking a card, it pays {paid}. "
            f"{when}. Paying moves 10 points to a rival for sure; a card that doesn't bust it adds to its own "
            f"round. {smart}")


def _delivery(rl, sm):
    d = rl["new_cards"]["deliver"]
    num = d["number"]
    return (f"<b>Special Delivery: a bust for a rival, or a gift to itself.</b> When the flipped number can bust "
            f"someone, it delivers the bust {pct(num['busts_when_possible'])} of the time, and {pct(d['leader_rate'])} of "
            f"the cards it hands to rivals go to the leader (a random rival would be {pct(d['random_leader_rate'])}). "
            f"A number that can't bust anyone it keeps {pct(num['self_when_safe'])} of the time, and it keeps "
            f"{pct(d['action']['self_rate'])} of the actions and {pct(d['keeper']['self_rate'])} of the keepers.")


FINDINGS = [_push, _scoreboard, _weapons, _div2, _busted, _minus_held, _seventh, _flip7, _shakedown, _delivery]


def build(insights):
    rl, sm = insights["tables"]["rl"], insights["tables"]["smart"]
    out = []
    for f in FINDINGS:
        try:
            text = f(rl, sm)
        except (KeyError, TypeError, ValueError, StopIteration):
            text = None
        if text:
            out.append(text)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insights", default=os.path.join(ROOT, "analysis", "insights.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "analysis", "findings.json"))
    a = ap.parse_args()
    with open(a.insights) as f:
        findings = build(json.load(f))
    with open(a.out, "w") as f:
        json.dump({"findings": findings}, f, indent=0, ensure_ascii=False)
    for x in findings:
        print("-", x)


if __name__ == "__main__":
    main()
