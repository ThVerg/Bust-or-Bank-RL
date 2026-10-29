"""Rules engine for Bust or Bank (see RULES.md).

The game is a state machine that stops at every decision. ``Game.decision`` holds the pending
decision (who decides, what kind, which actions are legal) and ``Game.step(action)`` applies one.
Decisions with a single legal action are applied automatically, so every decision a caller sees
is a real choice.

Actions are small ints in one flat space shared by all decision kinds:
    0 = Stay, 1 = Hit, 2+p = "player p", 8 + p*25 + c = "card c in player p's line".
A player shaken down answers with Stay (pay) or Hit (take a card instead).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .cards import (BOUNTY, DARE, DELIVERY, DISCARD, DIV2, FIRST_KEEPER, FIRST_MODIFIER, FLIP4, JOM, L14,
                    MOD_PENALTY, N_LINE_KINDS, N_NUMBER_KINDS, RANK, SHAKEDOWN, SPITE, STEAL, SWAP, TAX, U7,
                    ZERO, COUNTS, full_deck)

MAX_PLAYERS = 6
ACTIVE, STAYED, BUSTED = 0, 1, 2

A_STAY, A_HIT = 0, 1
A_PLAYER0 = 2
A_CARD0 = A_PLAYER0 + MAX_PLAYERS
N_ACTIONS = A_CARD0 + MAX_PLAYERS * N_LINE_KINDS

# Decision kinds
(D_HIT_STAY, D_TARGET, D_MODIFIER, D_STEAL, D_SWAP1, D_SWAP2, D_DISCARD, D_FLIP7,
 D_DELIVER, D_BOUNTY, D_DARE, D_SHAKEDOWN, D_PAY, D_SPITE) = range(14)
N_DECISION_KINDS = 14
DECISION_NAMES = ("hit_stay", "target", "modifier", "steal", "swap1", "swap2", "discard", "flip7",
                  "deliver", "bounty", "dare", "shakedown", "pay", "spite")

# Internal tasks on the resolution stack
T_TURNS, T_DEAL, T_JOM_STAY, T_FLIP4, T_QUEUE, T_ROUND_END, T_SPITE = range(7)

BOUNTY_REWARD = 10   # banked by whoever busts a player carrying a Bounty
DARE_TURNS = 2       # turns a dared player must Hit
SHAKEDOWN_FINE = 10
ROBIN_AMOUNT = 10
SPITE_PENALTY = 10
TAX_RATE = 5         # paid to a Tax Collector by every player ahead of its holder
FLIP7_BONUS = 15


def a_player(p):
    return A_PLAYER0 + p


def a_card(p, c):
    return A_CARD0 + p * N_LINE_KINDS + c


def decode_player(a):
    return a - A_PLAYER0


def decode_card(a):
    return divmod(a - A_CARD0, N_LINE_KINDS)


@dataclass(frozen=True)
class Rules:
    brutal: bool = True
    target: int = 200
    zero_must_hit: bool = True


class Decision:
    __slots__ = ("kind", "player", "options", "card", "first", "by")

    def __init__(self, kind, player, options, card=-1, first=-1, by=-1):
        self.kind = kind
        self.player = player
        self.options = options
        self.card = card    # action/modifier card being resolved; DELIVER: the card being delivered
        self.first = first  # SWAP2: the card picked in SWAP1
        self.by = by        # PAY: the player who played the Shakedown

    def __repr__(self):
        return f"Decision({DECISION_NAMES[self.kind]}, p{self.player}, {len(self.options)} opts)"


class Player:
    __slots__ = ("line", "status", "dead", "late_mods", "total", "frozen", "bounty", "dare", "dared_by", "spite")

    def __init__(self):
        self.line = []       # face-up cards: numbers, modifiers and keepers
        self.status = ACTIVE
        self.dead = []       # face-down cards of a busted line (still on the table)
        self.late_mods = []  # Brutal: a busted player's modifiers, which still count
        self.total = 0
        self.new_round()

    def new_round(self):
        self.frozen = False  # holds the Unlucky Frozen 7: stayed, and takes no more cards from the deck
        self.bounty = 0      # Bounties on this player
        self.dare = 0        # turns left on which this player must Hit
        self.dared_by = -1
        self.spite = 0       # points this round's score loses to Spite

    def copy(self):
        p = Player.__new__(Player)
        p.line = self.line[:]
        p.status = self.status
        p.dead = self.dead[:]
        p.late_mods = self.late_mods[:]
        p.total = self.total
        p.frozen = self.frozen
        p.bounty = self.bounty
        p.dare = self.dare
        p.dared_by = self.dared_by
        p.spite = self.spite
        return p


def busts(line):
    """True if the line holds a forbidden duplicate."""
    seen = 0
    fourteens = 0
    for c in line:
        if c < N_NUMBER_KINDS:
            r = RANK[c]
            if r == 14:
                fourteens += 1
            elif seen >> r & 1:
                return True
            else:
                seen |= 1 << r
    return fourteens > (2 if L14 in line else 1)


def number_count(line):
    return sum(1 for c in line if c < N_NUMBER_KINDS)


def line_score(line, flip7, brutal):
    """Round score of a non-busted line, without the Flip 7 bonus and Spite."""
    total = 0
    pen = 0
    for c in line:
        if c < N_NUMBER_KINDS:
            total += RANK[c]
        else:
            pen += MOD_PENALTY.get(c, 0)
    if not flip7 and ZERO in line:
        total = 0
    if DIV2 in line:
        total //= 2
    total -= pen
    if not brutal and total < 0:
        total = 0
    return total


class Game:
    # Pauses for a UI (off for training and search). With hold_round_end the game stops just before
    # scoring each round so the final table can be shown; with hold_draws it also stops after every
    # card of a Flip Four. ``holding`` says why ("round_end" / "draw"); resume() carries on.
    hold_round_end = False
    hold_draws = False
    holding = None

    def __init__(self, n_players, seed=None, rules=None, dealer=0, totals=None, log=False, rng=None,
                 deck=None):
        """``deck`` (optional) fixes the draw order, first card drawn first; mainly for tests."""
        assert 2 <= n_players <= MAX_PLAYERS
        self.n = n_players
        self.rules = rules or Rules()
        self.rng = rng or random.Random(seed)
        if deck is None:
            self.deck = full_deck()
            self.rng.shuffle(self.deck)
        else:
            self.deck = list(reversed(deck))
        self.discard = []
        self.players = [Player() for _ in range(n_players)]
        if totals:
            for p, t in zip(self.players, totals):
                p.total = t
        self.dealer = dealer
        self.round = 0
        self.draws = 0
        self.stack = []
        self.decision = None
        self.flip7_player = -1
        self.flip7_penalty = -1
        self.over = False
        self.winners = []
        self.last_round_scores = None
        self.logging = log
        self.events = []
        self._start_round()
        self._run()

    # ------------------------------------------------------------------ public API
    def to_play(self):
        return self.decision.player if self.decision is not None else -1

    def legal(self):
        return self.decision.options

    def step(self, action):
        d = self.decision
        if d is None or action not in d.options:
            raise ValueError(f"illegal action {action} for {d}")
        self._apply(action)
        self._run()

    def resume(self):
        """Carry on after a hold: score the held round or take the next Flip Four card."""
        reason, self.holding = self.holding, None
        if reason == "round_end":
            self.stack.pop()  # the T_ROUND_END left by _round_over
            self._end_round()
        if reason:
            self._run()

    finish_round = resume

    def returns(self):
        """Win share per player (ties split) once the game is over."""
        r = [0.0] * self.n
        for w in self.winners:
            r[w] = 1.0 / len(self.winners)
        return r

    def projected(self, p):
        """Player p's round score if the round ended now (no Flip 7 bonus or penalty)."""
        return self._round_score(p, False)

    def clone(self, rng=None):
        g = Game.__new__(Game)
        g.n = self.n
        g.rules = self.rules
        g.rng = rng or random.Random(self.rng.random())
        g.deck = self.deck[:]
        g.discard = self.discard[:]
        g.players = [p.copy() for p in self.players]
        g.dealer = self.dealer
        g.round = self.round
        g.draws = self.draws
        g.stack = self.stack[:]
        g.decision = self.decision  # immutable once created
        g.flip7_player = self.flip7_player
        g.flip7_penalty = self.flip7_penalty
        g.over = self.over
        g.winners = self.winners[:]
        g.last_round_scores = self.last_round_scores
        g.logging = False
        g.events = []
        return g

    def deck_counts(self):
        counts = [0] * len(COUNTS)
        for c in self.deck:
            counts[c] += 1
        return counts

    # ------------------------------------------------------------------ internals
    def _log(self, **ev):
        self.events.append(ev)

    def _run(self):
        while True:
            d = self.decision
            if d is not None:
                if len(d.options) == 1:
                    if self.logging:
                        self._log(t="forced", p=d.player, kind=DECISION_NAMES[d.kind], a=d.options[0])
                    self._apply(d.options[0])
                    continue
                return
            if self.over or self.holding:
                return
            self._exec(self.stack.pop())

    def _start_round(self):
        self.round += 1
        for pl in self.players:
            pl.status = ACTIVE
            pl.new_round()
        self.flip7_player = -1
        self.flip7_penalty = -1
        self.stack = [(T_TURNS, (self.dealer + 1) % self.n), (T_DEAL, 1)]
        if self.logging:
            self._log(t="round", round=self.round, dealer=self.dealer)

    def _draw(self):
        if not self.deck:
            if not self.discard:
                return None
            self.deck = self.discard
            self.discard = []
            self.rng.shuffle(self.deck)
            if self.logging:
                self._log(t="reshuffle", size=len(self.deck))
        self.draws += 1
        return self.deck.pop()

    def _exec(self, task):
        kind = task[0]
        players = self.players
        if kind == T_TURNS:
            start = task[1]
            for k in range(self.n):
                p = (start + k) % self.n
                pl = players[p]
                if pl.status == ACTIVE:
                    if pl.dare > 0 or (self.rules.zero_must_hit and ZERO in pl.line):
                        opts = (A_HIT,)
                    else:
                        opts = (A_STAY, A_HIT)
                    self.decision = Decision(D_HIT_STAY, p, opts)
                    return
            self._round_over()
        elif kind == T_DEAL:
            i = task[1]
            if i > self.n:
                return
            self.stack.append((T_DEAL, i + 1))
            p = (self.dealer + i) % self.n
            if players[p].status == ACTIVE:
                self._take(p, "deal")
        elif kind == T_JOM_STAY:
            p = task[1]
            if players[p].status == ACTIVE:
                players[p].status = STAYED
                if self.logging:
                    self._log(t="stay", p=p, forced=True)
        elif kind == T_FLIP4:
            _, t, rem, queue, by = task
            if players[t].status == BUSTED:
                self.discard.extend(queue)
                return
            c = self._draw() if rem > 0 and not players[t].frozen else None
            if c is None:
                if queue:
                    self.stack.append((T_QUEUE, t, queue))
                return
            if self.logging:
                self._log(t="draw", p=t, card=c, via="flip4", left=rem - 1)
            if c < N_NUMBER_KINDS:
                self.stack.append((T_FLIP4, t, rem - 1, queue, by))
                self._insert(t, c)
                self._after_change((t,), by)
            else:
                self.stack.append((T_FLIP4, t, rem - 1, queue + (c,), by))
            if self.hold_draws:
                self.holding = "draw"
        elif kind == T_QUEUE:
            _, t, queue = task
            if players[t].status == BUSTED:
                self.discard.extend(queue)
                return
            if len(queue) > 1:
                self.stack.append((T_QUEUE, t, queue[1:]))
            self._special(t, queue[0])
        elif kind == T_ROUND_END:
            self._round_over()
        elif kind == T_SPITE:
            p = task[1]
            self.decision = Decision(D_SPITE, p, tuple(a_player(q) for q in range(self.n) if q != p))

    def _take(self, p, via, by=-1):
        """Player p takes the top card of the deck and resolves it. ``by``: the player who made them
        take it (for Bounties), -1 if nobody did."""
        c = self._draw()
        if c is None:  # every card is on the table: nothing left to take
            if self.players[p].status == ACTIVE:
                self.players[p].status = STAYED
            return
        if self.logging:
            self._log(t="draw", p=p, card=c, via=via)
        if c < N_NUMBER_KINDS:
            self._insert(p, c)
            self._after_change((p,), by)
        else:
            self._special(p, c)

    def _insert(self, p, c):
        pl = self.players[p]
        if c == U7:  # the rest of the line is discarded and the player freezes
            wiped = pl.line
            self.discard.extend(wiped)
            pl.line = [U7]
            pl.frozen = True
            pl.dare = 0
            if pl.status == ACTIVE:
                pl.status = STAYED
            if self.logging:
                self._log(t="unlucky7", p=p, wiped=wiped[:])
        else:
            pl.line.append(c)

    def _after_change(self, ps, by=-1):
        """Bust and Flip 7 checks after the lines of ``ps`` changed. ``by``: the player whose card did it."""
        players = self.players
        for p in ps:
            pl = players[p]
            if pl.status != BUSTED and busts(pl.line):
                pl.status = BUSTED
                if self.logging:
                    self._log(t="bust", p=p, line=pl.line[:])
                if self.rules.brutal:  # Brutal: the numbers are turned face down, the modifiers stay and count
                    pl.late_mods.extend(c for c in pl.line if FIRST_MODIFIER <= c < FIRST_KEEPER)
                    pl.dead.extend(c for c in pl.line if not FIRST_MODIFIER <= c < FIRST_KEEPER)
                else:
                    pl.dead.extend(pl.line)
                spites = pl.line.count(SPITE)
                pl.line = []
                pl.dare = 0
                if pl.bounty:
                    if 0 <= by != p:
                        players[by].total += BOUNTY_REWARD * pl.bounty
                        if self.logging:
                            self._log(t="bounty_claim", p=by, victim=p, amount=BOUNTY_REWARD * pl.bounty)
                    pl.bounty = 0
                for _ in range(spites):
                    self.stack.append((T_SPITE, p))
        for p in ps:
            pl = players[p]
            if pl.status != BUSTED and number_count(pl.line) >= 7:
                self._flip7(p)
                return

    def _flip7(self, p):
        self.flip7_player = p
        for task in self.stack:  # cards queued by an unfinished Flip Four are lost
            if task[0] == T_FLIP4:
                self.discard.extend(task[3])
            elif task[0] == T_QUEUE:
                self.discard.extend(task[2])
        self.stack = [(T_ROUND_END,)] + [t for t in self.stack if t[0] == T_SPITE]
        if self.logging:
            self._log(t="flip7", p=p)
        if self.rules.brutal:
            self.decision = Decision(D_FLIP7, p, tuple(a_player(q) for q in range(self.n)))

    def _special(self, p, c):
        """Player p resolves a modifier, keeper or action card."""
        players = self.players
        n = self.n
        brutal = self.rules.brutal
        if c < FIRST_KEEPER:  # modifier
            opts = tuple(a_player(q) for q in range(n) if brutal or players[q].status != BUSTED)
            self.decision = Decision(D_MODIFIER, p, opts, card=c)
            return
        if c < N_LINE_KINDS:  # keeper: it stays in the line of whoever resolves it
            players[p].line.append(c)
            if self.logging:
                self._log(t="keeper", p=p, card=c)
            return
        self.discard.append(c)
        alive = [q for q in range(n) if players[q].status != BUSTED]
        can_draw = [q for q in alive if not players[q].frozen]
        if c == JOM or c == FLIP4:
            opts, kind = tuple(a_player(q) for q in can_draw), D_TARGET
        elif c == STEAL:
            opts = tuple(a_card(q, x) for q in alive if q != p for x in players[q].line)
            kind = D_STEAL
        elif c == SWAP:
            owners = [q for q in alive if players[q].line]
            opts = tuple(a_card(q, x) for q in owners for x in players[q].line) if len(owners) >= 2 else ()
            kind = D_SWAP1
        elif c == DISCARD:
            opts = tuple(a_card(q, x) for q in alive for x in players[q].line)
            kind = D_DISCARD
        elif c == DELIVERY:
            x = self._draw()
            if x is None:
                opts = ()
            else:
                if self.logging:
                    self._log(t="reveal", p=p, card=x)
                if x < N_NUMBER_KINDS:
                    who = can_draw
                elif x < FIRST_KEEPER:
                    who = range(n) if brutal else alive
                else:
                    who = alive
                opts = tuple(a_player(q) for q in who)
                if not opts:
                    self.discard.append(x)
                else:
                    self.decision = Decision(D_DELIVER, p, opts, card=x)
                    return
            kind = D_DELIVER
        elif c == BOUNTY:
            opts, kind = tuple(a_player(q) for q in alive if q != p), D_BOUNTY
        elif c == DARE:
            opts = tuple(a_player(q) for q in range(n) if q != p and players[q].status == ACTIVE)
            kind = D_DARE
        elif c == SHAKEDOWN:
            opts, kind = tuple(a_player(q) for q in alive if q != p), D_SHAKEDOWN
        else:  # ROBIN
            self._robin(p)
            return
        if opts:
            self.decision = Decision(kind, p, opts, card=c)
        elif self.logging:
            self._log(t="fizzle", p=p, card=c)

    def _pay(self, payer, to, amount):
        """Move points between totals (Standard: nobody's total goes below 0). Returns the amount paid."""
        src = self.players[payer]
        if not self.rules.brutal:
            amount = max(0, min(amount, src.total))
        src.total -= amount
        self.players[to].total += amount
        return amount

    def _robin(self, p):
        """Robin Hood: 10 points from the highest total to the lowest; ties go to the seat nearest p's left."""
        order = [(p + k) % self.n for k in range(1, self.n + 1)]
        rich = max(order, key=lambda q: self.players[q].total)
        poor = min(order, key=lambda q: self.players[q].total)
        amount = 0
        if self.players[rich].total > self.players[poor].total:
            amount = self._pay(rich, poor, ROBIN_AMOUNT)
        if self.logging:
            self._log(t="robin", p=p, rich=rich, poor=poor, amount=amount)

    def _apply(self, a):
        d = self.decision
        self.decision = None
        k = d.kind
        p = d.player
        players = self.players
        log = self.logging
        if k == D_HIT_STAY:
            self.stack.append((T_TURNS, (p + 1) % self.n))
            if a == A_STAY:
                players[p].status = STAYED
                if log:
                    self._log(t="stay", p=p)
            else:
                pl = players[p]
                by = -1
                if pl.dare > 0:  # a dared player's forced hit counts as the darer's doing
                    pl.dare -= 1
                    by = pl.dared_by
                self._take(p, "hit", by)
        elif k == D_TARGET:
            t = a - A_PLAYER0
            if log:
                self._log(t="action", p=p, card=d.card, target=t)
            if d.card == JOM:
                self.stack.append((T_JOM_STAY, t))
                self._take(t, "jom", p)
            else:
                self.stack.append((T_FLIP4, t, 4, (), p))
        elif k == D_MODIFIER:
            t = a - A_PLAYER0
            if players[t].status == BUSTED:
                players[t].late_mods.append(d.card)
            else:
                players[t].line.append(d.card)
            if log:
                self._log(t="modifier", p=p, card=d.card, target=t)
        elif k == D_STEAL:
            q, c = decode_card(a)
            players[q].line.remove(c)
            if log:
                self._log(t="steal", p=p, victim=q, card=c)
            self._insert(p, c)
            self._after_change((p,), p)
        elif k == D_SWAP1:
            q, _ = decode_card(a)
            opts = tuple(a_card(r, x) for r in range(self.n) if r != q and players[r].status != BUSTED
                         for x in players[r].line)
            self.decision = Decision(D_SWAP2, p, opts, card=d.card, first=a)
        elif k == D_SWAP2:
            q1, c1 = decode_card(d.first)
            q2, c2 = decode_card(a)
            players[q1].line.remove(c1)
            players[q2].line.remove(c2)
            if log:
                self._log(t="swap", p=p, a=q1, card_a=c1, b=q2, card_b=c2)
            self._insert(q1, c2)
            self._insert(q2, c1)
            self._after_change((q1, q2), p)
        elif k == D_DISCARD:
            q, c = decode_card(a)
            players[q].line.remove(c)
            self.discard.append(c)
            if log:
                self._log(t="discard", p=p, victim=q, card=c)
        elif k == D_FLIP7:
            t = a - A_PLAYER0
            self.flip7_penalty = -1 if t == p else t
            if log:
                self._log(t="flip7_bonus", p=p, target=t)
        elif k == D_DELIVER:
            t, x = a - A_PLAYER0, d.card
            if log:
                self._log(t="delivery", p=p, card=x, target=t)
            if x < N_NUMBER_KINDS:
                self._insert(t, x)
                self._after_change((t,), p)
            elif x < FIRST_KEEPER and players[t].status == BUSTED:
                players[t].late_mods.append(x)
            elif x < N_LINE_KINDS:  # a modifier or keeper lands in the line as it is
                players[t].line.append(x)
            else:
                self._special(t, x)
        elif k == D_BOUNTY:
            t = a - A_PLAYER0
            players[t].bounty += 1
            if log:
                self._log(t="bounty", p=p, target=t)
        elif k == D_DARE:
            t = a - A_PLAYER0
            players[t].dare += DARE_TURNS
            players[t].dared_by = p
            if log:
                self._log(t="dare", p=p, target=t)
        elif k == D_SHAKEDOWN:
            t = a - A_PLAYER0
            if log:
                self._log(t="shakedown", p=p, target=t)
            opts = (A_STAY,) if players[t].frozen else (A_STAY, A_HIT)  # frozen: can't take a card
            self.decision = Decision(D_PAY, t, opts, card=d.card, by=p)
        elif k == D_PAY:
            if a == A_STAY:
                paid = self._pay(p, d.by, SHAKEDOWN_FINE)
                if log:
                    self._log(t="pay", p=p, to=d.by, amount=paid)
            else:
                if log:
                    self._log(t="refuse", p=p, to=d.by)
                self._take(p, "shakedown", d.by)
        elif k == D_SPITE:
            t = a - A_PLAYER0
            players[t].spite += SPITE_PENALTY
            if log:
                self._log(t="spite", p=p, target=t, amount=SPITE_PENALTY)

    def _round_over(self):
        if self.hold_round_end:
            self.holding = "round_end"
            self.stack.append((T_ROUND_END,))
        else:
            self._end_round()

    def _round_score(self, q, final):
        """Player q's score for the round; ``final`` adds the Flip 7 bonus and penalty."""
        pl = self.players[q]
        brutal = self.rules.brutal
        if pl.status == BUSTED:
            s = -sum(MOD_PENALTY[m] for m in pl.late_mods) if brutal else 0
        else:
            f7 = final and q == self.flip7_player
            s = line_score(pl.line, f7, brutal)
            if f7 and self.flip7_penalty < 0:
                s += FLIP7_BONUS
        if pl.status != BUSTED or brutal:
            s -= pl.spite
        if final and q == self.flip7_penalty:
            s -= FLIP7_BONUS
        return s if brutal else max(0, s)

    def _end_round(self):
        players = self.players
        before = [pl.total for pl in players]
        scores = [self._round_score(q, True) for q in range(self.n)]
        for pl, s in zip(players, scores):
            pl.total += s
        taxes = []  # Tax Collectors: every player ahead (before this round) pays each one's holder
        for q, pl in enumerate(players):
            k = pl.line.count(TAX) if pl.status != BUSTED else 0
            for r in range(self.n):
                if k and r != q and before[r] > before[q]:
                    taxes.append({"p": q, "from": r, "amount": self._pay(r, q, TAX_RATE * k)})
        for pl in players:
            self.discard.extend(pl.line)
            self.discard.extend(pl.dead)
            self.discard.extend(pl.late_mods)
            pl.line = []
            pl.dead = []
            pl.late_mods = []
        self.last_round_scores = scores
        self.stack = []
        best = max(pl.total for pl in players)
        if self.logging:
            self._log(t="round_end", scores=scores, totals=[pl.total for pl in players],
                      flip7=self.flip7_player, penalty=self.flip7_penalty, taxes=taxes)
        if best >= self.rules.target:
            self.over = True
            self.winners = [q for q, pl in enumerate(players) if pl.total == best]
            if self.logging:
                self._log(t="game_over", winners=self.winners)
        else:
            self.dealer = (self.dealer + 1) % self.n
            self._start_round()
