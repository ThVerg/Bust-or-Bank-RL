"""Search on top of the trained network.

``SearchBot``: one-ply expectimax over the next card. For every legal action the bot considers
each kind of card that could be drawn first, weighted by how many of them are in the pile at the
moment of that draw (the composition is public), applies the action, plays on until the next
decision point and scores that position with the value head. The pile is taken at the draw
itself, after any deterministic effects of the action: if the action ends the round, the table's
cards reach the discard pile before an empty deck is reshuffled. The rest of the pile is shuffled
for every evaluation, so the bot never peeks. Action value = expected probability of winning.

``RolloutBot``: truncated rollouts with common random numbers (see its docstring).

``AdaptiveBot``: rollouts that stop as soon as the best action is clear (see its docstring).

``BossBot``: per kind of decision, whichever of the above the verified tactical positions
(``flip7.tactics``) show works best (see its docstring).

A Swap is two decisions by the same player (first card, then second card). Both bots judge the
first card by the best exchange it allows, evaluated *after* the cards have moved, instead of
scoring the half-finished position between the two choices.
"""
from __future__ import annotations

import math
import random
import time
from collections import Counter

import numpy as np

from .encoding import OBS_DIM, abs_to_rel, encode, rel_to_abs
from .engine import A_CARD0, A_PLAYER0, D_HIT_STAY, D_SWAP1, D_SWAP2, N_ACTIONS, Game, decode_card
from .infer import NeuralBot, softmax


def _forward(model, games):
    """(logits [B, N_ACTIONS], win probabilities [B, 6], deciding player per game)."""
    B = len(games)
    obs = np.empty((B, OBS_DIM), np.float32)
    mask = np.empty((B, N_ACTIONS), bool)
    deciders = []
    for i, g in enumerate(games):
        _, _, who = encode(g, obs[i], mask[i])
        deciders.append(who)
    logits, v_logits = model.predict(obs, mask, np.array([g.n for g in games]))
    return logits, softmax(v_logits, 1), deciders


def _values(model, games, me):
    """My win probability in each position (exact result for finished games)."""
    vals = np.zeros(len(games))
    pending = [i for i, g in enumerate(games) if not g.over]
    for i, g in enumerate(games):
        if g.over:
            vals[i] = g.returns()[me]
    if pending:
        _, win, deciders = _forward(model, [games[i] for i in pending])
        for j, i in enumerate(pending):
            vals[i] = win[j, (me - deciders[j]) % games[i].n]
    return vals


def _target_of(a):
    """The player an action is aimed at (target player or owner of the card), or -1."""
    if a < A_PLAYER0:
        return -1
    if a < A_CARD0:
        return a - A_PLAYER0
    return decode_card(a)[0]


def _forced_first_draw(g, card):
    """A replacement for g._draw whose first draw is ``card``: the pile as it stands at that draw
    (reshuffled from the discards if the deck is empty) is shuffled and ``card`` put on top."""
    state = {"first": True}

    def draw():
        if not state["first"]:
            return Game._draw(g)
        state["first"] = False
        if not g.deck:
            g.deck, g.discard = g.discard, []
        g.rng.shuffle(g.deck)
        i = g.deck.index(card)
        g.deck[i], g.deck[-1] = g.deck[-1], g.deck[i]
        g.draws += 1
        return g.deck.pop()
    return draw


class SearchBot:
    def __init__(self, model, name="RL+Search", seed=None, samples_per_kind=1):
        self.model = model
        self.name = name
        self.rng = random.Random(seed)
        self.samples = samples_per_kind

    def _children(self, game, action):
        """[(weight, game_after)] for one action, enumerating the kind of the first card drawn."""
        probe = game.clone(random.Random(self.rng.random()))
        probe.rng.shuffle(probe.deck)
        seen = []

        def spy():  # record what the first draw draws from, then draw normally
            if not seen:
                seen.append(Counter(probe.deck if probe.deck else probe.discard))
            return Game._draw(probe)

        probe._draw = spy
        probe.step(action)
        del probe._draw
        if not seen or not seen[0]:  # no card drawn: deterministic
            return [(1.0, probe)]
        counts = seen[0]
        total = sum(counts.values())
        out = []
        for c, k in counts.items():
            for _ in range(self.samples):
                g = game.clone(random.Random(self.rng.random()))
                g._draw = _forced_first_draw(g, c)
                g.step(action)
                del g._draw
                out.append((k / total / self.samples, g))
        return out

    def _complete(self, g, me):
        """Positions to judge for a child: all my possible second Swap cards, or just the child."""
        d = g.decision
        if g.over or d is None or d.kind != D_SWAP2 or d.player != me:
            return [g]
        seed = g.rng.random()
        out = []
        for b in d.options:  # clones share the deck order and RNG, so the options are compared fairly
            g2 = g.clone(random.Random(seed))
            g2.step(b)
            out.append(g2)
        return out

    def evaluate(self, game):
        """Expected win probability of each legal action for the deciding player."""
        me = game.decision.player
        groups = []  # (action, weight, positions); a group is worth its best position (my choice)
        for a in game.legal():
            for w, g in self._children(game, a):
                groups.append((a, w, self._complete(g, me)))
        vals = _values(self.model, [g for _, _, gs in groups for g in gs], me)
        q = {}
        i = 0
        for a, w, gs in groups:
            q[a] = q.get(a, 0.0) + w * float(vals[i:i + len(gs)].max())
            i += len(gs)
        return q

    def act(self, game):
        q = self.evaluate(game)
        return max(q, key=q.get)


class RolloutBot:
    """Truncated rollout search with common random numbers.

    Candidate actions are tried on the same ``k`` random deck orders; the rest of the round is
    played out by the policy network and the position at the start of the next round is scored
    by the value head. Using the same decks for every action means differences in the averages
    come from the action, not from the luck of the draw.

    * Up to ``max_actions`` candidates. When there are more legal actions, half the slots go to
      the policy's favourites and the rest make sure every target player / card owner is tried
      at least once, so the search isn't limited to what the policy already likes.
    * Swaps are searched as (first card, second card) pairs: the policy's ``pair_width`` best
      second cards for each first card.
    * ``rollout_temp`` > 0 makes the simulated players sample moves (softmax with temperature)
      instead of always playing the network's top move.
    """

    def __init__(self, model, k=32, max_actions=8, pair_width=2, rollout_temp=0.0,
                 name="RL+Rollouts", seed=None):
        self.model = model
        self.k = k
        self.max_actions = max_actions
        self.pair_width = pair_width
        self.rollout_temp = rollout_temp
        self.name = name
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(self.rng.randrange(1 << 31))

    def _ranked(self, game):
        me = game.decision.player
        logits = _forward(self.model, [game])[0][0]
        return sorted(game.legal(), key=lambda a: -float(logits[abs_to_rel(a, me, game.n)]))

    def _candidates(self, game):
        ranked = self._ranked(game)
        if len(ranked) <= self.max_actions:
            return ranked
        picked = ranked[:max(1, self.max_actions // 2)]
        covered = {_target_of(a) for a in picked}
        for a in ranked:  # best-ranked action for each target not yet covered
            if len(picked) >= self.max_actions:
                break
            if _target_of(a) not in covered:
                picked.append(a)
                covered.add(_target_of(a))
        for a in ranked:
            if len(picked) >= self.max_actions:
                break
            if a not in picked:
                picked.append(a)
        return picked

    def _sequences(self, game):
        """Candidate action sequences; Swap first cards are paired with likely second cards."""
        me = game.decision.player
        seqs = []
        for a in self._candidates(game):
            if game.decision.kind != D_SWAP1:
                seqs.append((a,))
                continue
            probe = game.clone(random.Random(0))
            probe.step(a)
            d = probe.decision
            if probe.over or d is None or d.kind != D_SWAP2 or d.player != me:
                seqs.append((a,))   # the second card was forced
                continue
            for b in self._ranked(probe)[:self.pair_width]:
                seqs.append((a, b))
        return seqs

    def _rollout_actions(self, logits, deciders, games):
        if self.rollout_temp > 0:
            cum = softmax(logits.astype(np.float64) / self.rollout_temp, 1).cumsum(1)
            u = (1.0 - self.np_rng.random(len(cum)))[:, None] * cum[:, -1:]  # in (0, total]: never a masked action
            rel = (cum < u).sum(1)
        else:
            rel = logits.argmax(1)
        return [rel_to_abs(int(r), deciders[j], games[j].n) for j, r in enumerate(rel)]

    def evaluate(self, game):
        seqs = self._sequences(game)
        seeds = [self.rng.random() for _ in range(self.k)]
        q = {}
        for seq, v in self._simulate(game, seqs, seeds).items():  # a first Swap card is worth its best pairing
            q[seq[0]] = max(q.get(seq[0], -1.0), float(v.mean()))
        return q

    def _simulate(self, game, seqs, seeds):
        """Win probability of every action sequence on every deck order: {seq: array[len(seeds)]}.
        The same seeds give the same deck orders, so differences between sequences are paired."""
        me = game.decision.player
        start_round = game.round
        sims = []  # (sequence, game)
        for s in seeds:
            for seq in seqs:
                g = game.clone(random.Random(s))
                random.Random(s).shuffle(g.deck)
                for x in seq:
                    g.step(x)
                sims.append((seq, g))
        values = [None] * len(sims)
        active = []
        for i, (_, g) in enumerate(sims):
            if g.over:
                values[i] = g.returns()[me]
            else:
                active.append(i)
        while active:
            games = [sims[i][1] for i in active]
            logits, win, deciders = _forward(self.model, games)
            acts = self._rollout_actions(logits, deciders, games)
            still = []
            for j, i in enumerate(active):
                g = games[j]
                if g.round != start_round:   # reached the next round: score with the value head
                    values[i] = float(win[j, (me - deciders[j]) % g.n])
                    continue
                g.step(acts[j])
                if g.over:
                    values[i] = g.returns()[me]
                else:
                    still.append(i)
            active = still
        out = {seq: np.empty(len(seeds)) for seq in seqs}
        for i, ((seq, _), v) in enumerate(zip(sims, values)):  # sims are seed-major
            out[seq][i // len(seqs)] = v
        return out

    def act(self, game):
        q = self.evaluate(game)
        return max(q, key=q.get)


def _endgame(game):
    """Someone can reach the target this round: the round may decide the game."""
    t = game.rules.target
    return any(pl.total + max(0, game.projected(p)) + 15 >= t for p, pl in enumerate(game.players))


class AdaptiveBot(RolloutBot):
    """Rollout search that spends its effort where the decision is close.

    * Obvious decisions (the network puts at least ``obvious`` on one action, outside endgames)
      are played straight from the policy, with no search at all.
    * Otherwise the candidates are rolled out in batches of ``batch`` shared deck orders. After
      ``k_min`` orders, any action whose paired difference to the leader is clearly negative
      (more than ``z`` standard errors) is dropped; the search stops when one action is left,
      after ``k_max`` orders, or when the time budget is spent.
    * In an endgame (someone can reach the target this round) the order and time budgets double.
    """

    def __init__(self, model, k_min=16, k_max=128, batch=8, z=2.0, obvious=0.97, budget_s=0.6,
                 max_actions=8, pair_width=2, name="RL+Adaptive", seed=None):
        super().__init__(model, k=k_max, max_actions=max_actions, pair_width=pair_width, name=name, seed=seed)
        self.k_min, self.k_max, self.batch, self.z = k_min, k_max, batch, z
        self.obvious, self.budget_s = obvious, budget_s
        self.last_orders = 0  # deck orders used for the last decision (0: answered by the policy)

    def act(self, game):
        legal = game.legal()
        self.last_orders = 0
        if len(legal) == 1:
            return legal[0]
        me = game.decision.player
        logits = _forward(self.model, [game])[0][0]
        rel = [abs_to_rel(a, me, game.n) for a in legal]
        p = softmax(logits[rel])
        end = _endgame(game)
        if not end and float(p.max()) >= self.obvious:
            return legal[int(p.argmax())]
        k_max = self.k_max * (2 if end else 1)
        deadline = time.perf_counter() + self.budget_s * (2 if end else 1)
        alive = self._sequences(game)
        vals = {seq: np.empty(0) for seq in alive}
        n = 0
        while True:
            seeds = [self.rng.random() for _ in range(self.batch)]
            new = self._simulate(game, alive, seeds)
            for seq in alive:
                vals[seq] = np.concatenate([vals[seq], new[seq]])
            n += self.batch
            best = self._best_per_action(alive, vals)  # first action -> its best sequence so far
            lead = max(best, key=lambda a: vals[best[a]].mean())
            if n >= self.k_min:
                keep = {lead}
                for a, seq in best.items():
                    if a == lead:
                        continue
                    d = vals[best[lead]] - vals[seq]
                    se = d.std(ddof=1) / math.sqrt(len(d)) if len(d) > 1 else 1.0
                    if d.mean() - self.z * max(se, 1e-9) <= 0:
                        keep.add(a)
                alive = [seq for seq in alive if seq[0] in keep]
                if len(keep) == 1 or n >= k_max or time.perf_counter() > deadline:
                    self.last_orders = n
                    return lead

    @staticmethod
    def _best_per_action(seqs, vals):
        best = {}
        for seq in seqs:
            a = seq[0]
            if a not in best or vals[seq].mean() > vals[best[a]].mean():
                best[a] = seq
        return best


class BossBot:
    """The network plus, for each kind of decision, the search that did best on the first set of verified
    tactical positions (``flip7.tactics``: every move played to the end of the game on 1024 fresh shuffles):

    * Swap: rollouts (``RolloutBot``, ``k`` shared deck orders, first and second card searched as
      pairs).
    * Hit/stay when someone can reach the target this round: the network's own move. Every search
      variant was at best level with it there; the one-ply search was slightly worse.
    * Everything else: one-ply expectimax (``SearchBot``).

    It is the site's Boss. On the held-out set its Swaps beat ``SearchBot``'s by 1.5 standard errors (not
    significant on its own; ahead on both sets), and in games the two are level.

    ``endgame_policy=False`` searches endgame hit/stay too, so only Swaps differ from ``SearchBot``.
    """

    def __init__(self, model, k=32, name="RL+Boss", seed=None, endgame_policy=True):
        self.policy = NeuralBot(model)
        self.search = SearchBot(model, seed=seed)
        self.rollout = RolloutBot(model, k=k, seed=seed)
        self.endgame_policy = endgame_policy
        self.name = name

    def _searcher(self, game):
        d = game.decision
        if d.kind in (D_SWAP1, D_SWAP2):
            return self.rollout
        if self.endgame_policy and d.kind == D_HIT_STAY and _endgame(game):
            return None
        return self.search

    def evaluate(self, game):
        """Action -> score (win probability, or the policy's probability where the policy decides)."""
        searcher = self._searcher(game)
        return searcher.evaluate(game) if searcher else self.policy.evaluate(game)[0]

    def act(self, game):
        legal = game.legal()
        if len(legal) == 1:
            return legal[0]
        q = self.evaluate(game)
        return max(q, key=q.get)
