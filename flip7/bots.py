"""Hand-written bots: baselines for the RL agents and sparring partners in the web app.

Every bot implements ``act(game) -> action`` for ``game.decision``.
"""
from __future__ import annotations

import random

from .cards import DIV2, FIRST_KEEPER, FIRST_MODIFIER, JOM, MOD_PENALTY, TAX, U7
from .engine import (A_HIT, A_STAY, BOUNTY_REWARD, BUSTED, D_BOUNTY, D_DARE, D_DELIVER, D_FLIP7,
                     D_HIT_STAY, D_MODIFIER, D_PAY, D_SHAKEDOWN, D_SPITE, D_STEAL, D_SWAP1, D_SWAP2, D_TARGET,
                     SHAKEDOWN_FINE, STAYED, TAX_RATE, busts, decode_card, decode_player, line_score, number_count)
from .features import next_card_pool, player_stats


class RandomBot:
    name = "Random"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, game):
        return self.rng.choice(game.legal())


class ThresholdBot:
    """Hits until its round score reaches a threshold; targets the leader with everything."""

    def __init__(self, threshold=25):
        self.threshold = threshold
        self.name = f"Threshold{threshold}"
        self._smart = SmartBot()

    def act(self, game):
        d = game.decision
        if d.kind == D_HIT_STAY:
            return A_STAY if game.projected(d.player) >= self.threshold else A_HIT
        return self._smart.act(game)


class SmartBot:
    """A strong card-counting human.

    * Hit/Stay: hit while the expected score after one more card beats the current score, with
      extra risk appetite when an opponent is about to win.
    * Card choices (Steal, Swap, Discard, Special Delivery): one-step lookahead on the lines,
      maximizing my round score minus a threat-weighted sum of the opponents' round scores.
    * Bounty, Double Dare, Shakedown, Spite: aimed at the most threatening opponent; a Shakedown is
      paid when that costs less than the expected loss from drawing.
    """

    name = "SmartBot"

    def __init__(self, risk=1.0):
        self.risk = risk

    # ---------------------------------------------------------------- helpers
    def _threat(self, game, me, stats):
        """Weight of each opponent: who are we most afraid of?"""
        mine = stats[me]["total"] + stats[me]["proj"]
        w = []
        for q, s in enumerate(stats):
            if q == me:
                w.append(0.0)
                continue
            theirs = s["total"] + s["proj"]
            x = 1.0 + max(0.0, theirs - mine) / 40.0
            if theirs >= game.rules.target - 30:
                x += 1.0
            w.append(x / max(1, game.n - 1) * 1.5)
        return w

    @staticmethod
    def _line_value(line, status, brutal, late=0):
        """Round value of a line (bust = 0, or minus late modifiers in Brutal)."""
        if status == BUSTED or busts(line):
            return -late if brutal else 0
        v = line_score(line, False, brutal)
        if number_count(line) >= 7:
            v = line_score(line, True, brutal) + 15
        return v

    def _utility(self, game, me, lines, w):
        brutal = game.rules.brutal
        players = game.players
        u = 0.0
        for q, pl in enumerate(players):
            late = sum(MOD_PENALTY[m] for m in pl.late_mods)
            v = self._line_value(lines[q], pl.status, brutal, late)
            busted_now = pl.status != BUSTED and busts(lines[q])
            if busted_now:
                v -= 3  # also loses any future of the round
                if q != me:
                    u += BOUNTY_REWARD * pl.bounty
            elif pl.status != BUSTED:  # a Tax Collector collects from everyone ahead
                v += lines[q].count(TAX) * TAX_RATE * sum(1 for r in players if r.total > pl.total)
            u += v if q == me else -w[q] * v
        return u

    # ---------------------------------------------------------------- decisions
    def act(self, game):
        d = game.decision
        me = d.player
        pool = next_card_pool(game)
        pool_size = sum(pool)
        stats = [player_stats(game, q, pool, pool_size) for q in range(game.n)]
        if d.kind == D_HIT_STAY:
            return self._hit_stay(game, me, stats)
        w = self._threat(game, me, stats)
        if d.kind == D_TARGET:
            return self._target(game, me, d, stats, w)
        if d.kind == D_MODIFIER:
            return self._modifier(game, me, d, stats, w)
        if d.kind == D_FLIP7:
            return self._flip7(game, me, d, stats)
        if d.kind == D_DELIVER:
            return self._deliver(game, me, d, stats, w)
        if d.kind == D_PAY:
            return self._pay(game, me, d, stats, w)
        if d.kind in (D_BOUNTY, D_DARE, D_SHAKEDOWN, D_SPITE):
            return self._aim(game, me, d, stats, w)
        return self._card_choice(game, me, d, w)

    def _hit_stay(self, game, me, stats):
        s = stats[me]
        proj, pb, pn, ev = s["proj"], s["p_bust"], s["p_new"], s["ev_new"]
        gain = ev / 2 if s["div2"] else ev
        p_other = max(0.0, 1.0 - pb - pn)  # actions/modifiers: roughly neutral
        ev_hit = pn * (proj + gain) + p_other * proj + pb * 0.0
        if s["count"] == 6:
            ev_hit += pn * 15
        # race awareness: if an opponent will reach the target this round, chase
        target = game.rules.target
        best_other = max(stats[q]["total"] + max(stats[q]["proj"], 0)
                         for q in range(game.n) if q != me)
        mine = s["total"] + proj
        if best_other >= target and mine <= best_other:
            return A_HIT
        if mine >= target and mine > best_other + 5:
            return A_STAY
        return A_HIT if ev_hit > proj + 0.5 / self.risk else A_STAY

    def _target(self, game, me, d, stats, w):
        best, best_v = None, -1e9
        for a in d.options:
            t = decode_player(a)
            s = stats[t]
            pb, proj, ev = s["p_bust"], max(s["proj"], 0), s["ev_new"]
            if d.card == JOM:
                # one more card, then a forced stay
                delta = -pb * proj + (1 - pb) * ev * 0.6
                if s["zero"]:
                    delta -= 12  # locks them on zero points
                if s["status"] != STAYED and proj < 15:
                    delta -= (15 - proj) * 0.4  # stops them from building a hand
            else:
                pb4 = 1 - (1 - pb) ** 3.2
                delta = -pb4 * proj + (1 - pb4) * ev * 2.5
                if s["count"] >= 3:
                    delta += (1 - pb4) * 4  # Flip 7 chances
            v = delta if t == me else -w[t] * delta
            if v > best_v:
                best, best_v = a, v
        return best

    def _modifier(self, game, me, d, stats, w, card=None):
        brutal = game.rules.brutal
        card = d.card if card is None else card
        best, best_v = None, -1e9
        for a in d.options:
            t = decode_player(a)
            s = stats[t]
            if card == DIV2:
                hit = 0 if (s["status"] == BUSTED or s["zero"]) else s["sum"] / 2
            else:
                pen = MOD_PENALTY[card]
                hit = pen if brutal else min(pen, max(s["proj"], 0))
            v = -hit if t == me else w[t] * hit + 0.01
            if v > best_v:
                best, best_v = a, v
        return best

    def _flip7(self, game, me, d, stats):
        """+15 for me or -15 for someone: judge by the standings after this round."""
        target = game.rules.target
        brutal = game.rules.brutal
        base = [s["total"] + s["proj"] for s in stats]
        base[me] = stats[me]["total"] + line_score(game.players[me].line, True, brutal)
        best_a, best_v = None, -1e9
        for a in d.options:
            t = decode_player(a)
            after = base[:]
            if t == me:
                after[me] += 15
            else:
                after[t] -= 15
            other = max(x for q, x in enumerate(after) if q != me)
            if max(after) >= target:
                v = 100.0 if after[me] > other else -100.0
            else:
                v = after[me] - other
                # ahead: shorten the race; behind: slow the leader down
                v += 2.0 if (t == me) == (after[me] >= other) else 0.0
            if v > best_v:
                best_a, best_v = a, v
        return best_a

    def _deliver(self, game, me, d, stats, w):
        x = d.card
        if FIRST_MODIFIER <= x < FIRST_KEEPER:
            return self._modifier(game, me, d, stats, w, card=x)
        if x >= FIRST_KEEPER:  # keepers and actions help whoever gets them: keep them
            return min(d.options, key=lambda a: decode_player(a) != me)
        lines = [pl.line[:] for pl in game.players]
        best, best_v = None, -1e9
        for a in d.options:
            t = decode_player(a)
            new = [l[:] for l in lines]
            new[t] = [U7] if x == U7 else new[t] + [x]
            v = self._utility(game, me, new, w)
            if v > best_v:
                best, best_v = a, v
        return best

    def _aim(self, game, me, d, stats, w):
        """Bounty, Double Dare, Shakedown, Spite: the most threatening target, weighted by what the
        card is likely to cost them."""
        def value(a):
            t = decode_player(a)
            s = stats[t]
            proj = max(s["proj"], 0)
            if d.kind == D_DARE:
                return w[t] * (1 - (1 - s["p_bust"]) ** 2) * proj
            if d.kind == D_BOUNTY:
                return w[t] * (s["p_bust"] + 0.2) * (s["total"] + proj + 10)
            return w[t] * (s["total"] + proj + 10)
        return max(d.options, key=value)

    def _pay(self, game, me, d, stats, w):
        """Shakedown: pay the fine, or take a card and risk the line (and any Bounty on me)."""
        s = stats[me]
        pl = game.players[me]
        fine = SHAKEDOWN_FINE if game.rules.brutal else min(SHAKEDOWN_FINE, max(0, pl.total))
        cost_pay = fine * (1 + w[d.by])
        proj = max(s["proj"], 0)
        gain = s["ev_new"] / 2 if s["div2"] else s["ev_new"]
        cost_draw = s["p_bust"] * (proj + BOUNTY_REWARD * pl.bounty * (1 + w[d.by])) - s["p_new"] * gain
        if s["count"] == 6:
            cost_draw -= s["p_new"] * 15
        return A_STAY if cost_pay < cost_draw else A_HIT

    def _card_choice(self, game, me, d, w):
        lines = [pl.line[:] for pl in game.players]
        if d.kind == D_SWAP1:
            best_pair, best_v = None, -1e9
            for a in d.options:
                q1, c1 = decode_card(a)
                for b in d.options:
                    q2, c2 = decode_card(b)
                    if q2 == q1:
                        continue
                    v = self._eval_swap(game, me, lines, w, q1, c1, q2, c2)
                    if v > best_v:
                        best_pair, best_v = a, v
            return best_pair
        if d.kind == D_SWAP2:
            q1, c1 = decode_card(d.first)
            return max(d.options, key=lambda b: self._eval_swap(game, me, lines, w, q1, c1,
                                                                *decode_card(b)))
        best, best_v = None, -1e9
        for a in d.options:
            q, c = decode_card(a)
            new = [l[:] for l in lines]
            new[q].remove(c)
            if d.kind == D_STEAL:
                if c == U7:
                    new[me] = [U7]
                else:
                    new[me].append(c)
            v = self._utility(game, me, new, w)
            if v > best_v:
                best, best_v = a, v
        return best

    def _eval_swap(self, game, me, lines, w, q1, c1, q2, c2):
        new = [l[:] for l in lines]
        new[q1].remove(c1)
        new[q2].remove(c2)
        new[q1] = [U7] if c2 == U7 else new[q1] + [c2]
        new[q2] = [U7] if c1 == U7 else new[q2] + [c1]
        return self._utility(game, me, new, w)


def make_bot(name):
    name = name.lower()
    if name == "random":
        return RandomBot()
    if name.startswith("threshold"):
        return ThresholdBot(int(name[len("threshold"):] or 25))
    if name == "smart":
        return SmartBot()
    raise ValueError(name)
