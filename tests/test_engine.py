import random

import pytest

from flip7.cards import (BOUNTY, COUNTS, DARE, DELIVERY, DIV2, DISCARD, FIRST_KEEPER, FLIP4, JOM, L14, M10, M2,
                         M4, ROBIN, SHAKEDOWN, SPITE, STEAL, SWAP, TAX, U7, ZERO, DECK_SIZE)
from flip7.engine import (A_HIT, A_STAY, ACTIVE, BUSTED, D_BOUNTY, D_DELIVER, D_FLIP7, D_HIT_STAY, D_MODIFIER,
                          D_PAY, D_STEAL, D_SWAP1, D_TARGET, D_DISCARD, STAYED, T_FLIP4, T_QUEUE, Game, Rules,
                          a_card, a_player, busts, line_score)

BRUTAL = Rules(brutal=True)
STANDARD = Rules(brutal=False)


def all_cards(g):
    cards = list(g.deck) + list(g.discard)
    for pl in g.players:
        cards += pl.line + pl.dead + pl.late_mods
    for task in g.stack:
        if task[0] == T_FLIP4:
            cards += list(task[3])
        elif task[0] == T_QUEUE:
            cards += list(task[2])
    if g.decision is not None and g.decision.kind in (D_MODIFIER, D_DELIVER):
        cards.append(g.decision.card)  # the card being handed out
    return cards


def check_invariants(g):
    cards = all_cards(g)
    assert len(cards) == DECK_SIZE
    counts = [0] * len(COUNTS)
    for c in cards:
        counts[c] += 1
    assert tuple(counts) == COUNTS
    for pl in g.players:
        if pl.status == BUSTED:
            assert pl.line == []
        else:
            assert not busts(pl.line)
            unique = [c for c in pl.line if c < FIRST_KEEPER]  # a line may hold both copies of a keeper
            assert len(set(unique)) == len(unique)
        if pl.frozen:
            assert pl.status != ACTIVE
    if not g.over:
        assert g.decision is not None and len(g.decision.options) >= 2


@pytest.mark.parametrize("rules", [BRUTAL, STANDARD])
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_random_games_keep_invariants(rules, n):
    rng = random.Random(n)
    for seed in range(40):
        g = Game(n, seed=seed, rules=rules)
        steps = 0
        while not g.over:
            check_invariants(g)
            g.step(rng.choice(g.legal()))
            steps += 1
            assert steps < 20000
        check_invariants(g)
        assert max(p.total for p in g.players) >= rules.target
        assert abs(sum(g.returns()) - 1) < 1e-9
        if not rules.brutal:
            assert all(p.total >= 0 for p in g.players)


def make(deck, n=2, rules=BRUTAL, dealer=0, totals=None):
    return Game(n, rules=rules, dealer=dealer, deck=deck, totals=totals, log=True)


def test_bust_on_duplicate():
    # deal: p1 gets 5, p0 gets 9; p1 hits a 5 -> bust
    g = make([5, 9, 5, 3])
    assert g.decision.kind == D_HIT_STAY and g.decision.player == 1
    g.step(A_HIT)
    assert g.players[1].status == BUSTED
    assert g.players[1].dead == [5, 5]
    assert g.decision.player == 0


def test_stay_and_round_scoring():
    g = make([5, 9, 6, 12, 1])
    g.step(A_HIT)   # p1: 5, 6
    g.step(A_HIT)   # p0: 9, 12
    g.step(A_STAY)  # p1 stays with 11
    g.step(A_STAY)  # p0 stays with 21 -> round end
    assert g.last_round_scores == [21, 11]
    assert g.round == 2


def test_lucky_14_allows_one_extra_14():
    g = make([14, 2, L14, 3, 14])
    g.step(A_HIT)  # p1: 14, L14 -> fine
    assert g.players[1].status == ACTIVE
    g.step(A_HIT)  # p0: 2, 3
    g.step(A_HIT)  # p1: third 14 -> bust
    assert g.players[1].status == BUSTED
    assert busts([13, 13]) and not busts([13, 14])


def test_unlucky_frozen_7_wipes_line_and_freezes():
    # p0 hits the Unlucky Frozen 7: the 2 is discarded, p0 stays frozen on 7. p1 then draws Just One
    # More: p0 can't take cards any more, so p1 must aim it at themselves.
    g = make([7, 2, 9, U7, JOM, 4, 5, 6, 8, 10, 11, 12, 13] * 2)
    g.step(A_HIT)  # p1: 7, 9
    g.step(A_HIT)  # p0: Unlucky Frozen 7
    assert g.players[0].line == [U7] and g.players[0].frozen and g.players[0].status == STAYED
    assert any(e["t"] == "unlucky7" and e["wiped"] == [2] for e in g.events)
    g.step(A_HIT)  # p1 draws JOM: the only target is p1, who takes the 4 and stays: round over
    assert g.last_round_scores == [7, 20]
    assert not g.players[0].frozen  # a new round thaws everyone


def test_unlucky_frozen_7_on_top_of_a_7_does_not_bust():
    g = make([7, 2, U7, 3, 4])
    g.step(A_HIT)
    assert g.players[1].line == [U7] and g.players[1].status == STAYED and g.players[1].frozen


def test_frozen_player_must_pay_a_shakedown():
    for rules, totals in ((BRUTAL, [-10, 10]), (STANDARD, [0, 0])):
        g = make([7, 2, 9, U7, SHAKEDOWN, 3, 4, 5, 6, 8], rules=rules)
        g.step(A_HIT)  # p1: 7, 9
        g.step(A_HIT)  # p0 freezes
        g.step(A_HIT)  # p1 shakes p0 down: frozen, p0 can only pay
        assert [p.total for p in g.players] == totals


def test_special_delivery_can_bust_and_collects_the_bounty():
    # 3 players, deal p0, p1, p2: p1 is dealt a Bounty and puts it on p0. p2 then delivers a 5 to p0.
    g = make([5, BOUNTY, 9, 3, 4, DELIVERY, 5], n=3, dealer=2)
    assert g.decision.kind == D_BOUNTY and g.decision.player == 1
    g.step(a_player(0))
    g.step(A_HIT)  # p0: 5, 3
    g.step(A_HIT)  # p1: 4
    g.step(A_HIT)  # p2 draws Special Delivery: the 5 is revealed
    assert g.decision.kind == D_DELIVER and g.decision.card == 5
    assert set(g.decision.options) == {a_player(0), a_player(1), a_player(2)}
    g.step(a_player(0))
    assert g.players[0].status == BUSTED and g.players[2].total == 10 and g.players[0].bounty == 0


def test_bounty_is_lost_when_the_target_busts_on_their_own():
    g = make([5, BOUNTY, 9, 5, 3, 4], n=3, dealer=2)
    g.step(a_player(0))
    g.step(A_HIT)  # p0 hits a second 5
    assert g.players[0].status == BUSTED
    assert [p.total for p in g.players] == [0, 0, 0] and g.players[0].bounty == 0


def test_special_delivery_of_a_modifier_lands_directly():
    g = make([9, 3, DELIVERY, M4, 5, 6])
    g.step(A_HIT)  # p1 delivers the −4
    g.step(a_player(0))
    assert g.players[0].line == [3, M4] and g.players[1].line == [9]


def test_double_dare_forces_two_hits():
    g = make([DARE, 3, 4, 5, 6, 8])
    # p1 is dealt Double Dare: the only other active player is p0
    assert g.players[0].dare == 2
    g.step(A_STAY)  # p1 stays on nothing
    # p0's next two turns are forced hits, then p0 may stay again
    assert g.players[0].line == [3, 4, 5]
    assert g.decision.kind == D_HIT_STAY and g.decision.player == 0 and A_STAY in g.decision.options


def test_a_bust_on_a_dared_hit_pays_the_darer_the_bounty():
    # p1 puts a Bounty on p0, p2 dares p0; p0's forced hit busts them, so p2 collects
    g = make([5, BOUNTY, DARE, 5, 3, 4], n=3, dealer=2)
    g.step(a_player(0))  # Bounty on p0
    g.step(a_player(0))  # Double Dare on p0
    assert g.players[0].status == BUSTED and g.players[2].total == 10


def test_shakedown_pay_or_take_a_card():
    g = make([SHAKEDOWN, 3, 4, 5], totals=[30, 0])
    assert g.decision.kind == D_PAY and g.decision.player == 0
    g.step(A_STAY)
    assert [p.total for p in g.players] == [20, 10]
    g = make([SHAKEDOWN, 3, 4, 5], totals=[30, 0])
    g.step(A_HIT)  # p0 takes the 3 instead, then gets their deal card
    assert g.players[0].line == [3, 4] and [p.total for p in g.players] == [30, 0]


def test_robin_hood_moves_ten_from_the_top_to_the_bottom():
    g = make([ROBIN, 3, 4, 5], totals=[50, 10])
    assert [p.total for p in g.players] == [40, 20]
    # ties go to the seat nearest the player's left: p0 draws it, p1 and p2 tie for the lead
    g = make([ROBIN, 3, 4, 5, 6], n=3, dealer=2, totals=[10, 50, 50])
    assert [p.total for p in g.players] == [20, 40, 50]
    g = make([ROBIN, 3, 4, 5], totals=[5, 5])
    assert [p.total for p in g.players] == [5, 5]


def test_tax_collector_collects_from_everyone_ahead():
    g = make([3, TAX, 4] + [5, 6, 8, 9, 10, 11, 12] * 2, n=3, dealer=2, totals=[50, 20, 30])
    assert g.players[1].line == [TAX]
    for _ in range(3):
        g.step(A_STAY)
    assert g.last_round_scores == [3, 0, 4]
    assert [p.total for p in g.players] == [53 - 5, 20 + 10, 34 - 5]


def test_spite_costs_the_chosen_player_ten():
    g = make([5, 9, SPITE, 3, 5] + [6, 8, 10, 11, 12] * 2)
    g.step(A_HIT)  # p1: 5 + Spite
    assert g.players[1].line == [5, SPITE]
    g.step(A_HIT)  # p0: 9, 3
    g.step(A_HIT)  # p1 busts: the Spite goes to the only other player
    assert g.players[0].spite == 10
    g.step(A_STAY)
    assert g.last_round_scores == [12 - 10, 0]


def test_keepers_can_be_stolen_and_never_bust():
    g = make([TAX, 4, STEAL, 5], n=3, dealer=2)
    assert g.decision.kind == D_STEAL
    assert set(g.decision.options) == {a_card(0, TAX), a_card(1, 4)}
    g.step(a_card(0, TAX))
    assert g.players[2].line == [TAX] and g.players[0].line == []
    assert not busts([TAX, TAX, 5])


def test_zero_forces_hit_and_scores_zero():
    g = make([ZERO, 9, 5, 1, 6])
    # p1 holds The Zero: the hit is forced and applied automatically
    assert g.players[1].line == [ZERO, 5]
    assert g.decision.player == 0
    g.step(A_STAY)
    # p1 keeps hitting until the deck is empty, then the round ends
    assert g.last_round_scores == [9, 0]


def test_zero_scores_zero_unless_flip7():
    assert line_score([ZERO, 5, 6], False, True) == 0
    assert line_score([ZERO, 5, 6, M2], False, True) == -2
    assert line_score([ZERO, 5, 6, M2], False, False) == 0
    assert line_score([ZERO, 1, 2, 3, 4, 5, 6], True, True) == 21


def test_div2_then_minus():
    assert line_score([9, 12, DIV2, M4], False, True) == 21 // 2 - 4
    assert line_score([3, DIV2, M10], False, True) == 1 - 10
    assert line_score([3, DIV2, M10], False, False) == 0


def test_flip7_standard_bonus_ends_round():
    g = make([1, 9, 2, 3, 4, 5, 6, 8], rules=STANDARD)
    g.step(A_HIT)   # p1: 1,2
    g.step(A_STAY)  # p0 stays 9
    for _ in range(5):
        g.step(A_HIT)  # p1: 3,4,5,6,8 -> seven numbers
    assert g.last_round_scores == [9, 1 + 2 + 3 + 4 + 5 + 6 + 8 + 15]


def test_flip7_brutal_choice_penalty():
    g = make([1, 9, 2, 3, 4, 5, 6, 8])
    g.step(A_HIT)
    g.step(A_STAY)
    for _ in range(5):
        g.step(A_HIT)
    assert g.decision.kind == D_FLIP7 and g.decision.player == 1
    g.step(a_player(0))  # -15 to player 0
    assert g.last_round_scores == [9 - 15, 29]


def test_just_one_more_forces_stay():
    # p1 is dealt JOM, targets p0 (not dealt yet): p0 takes 4 and must stay; deal skips p0
    g = make([JOM, 4, 10, 11])
    assert g.decision.kind == D_TARGET and g.decision.player == 1
    g.step(a_player(0))
    assert g.players[0].line == [4] and g.players[0].status == STAYED
    # p1 has no number card yet and is still active
    assert g.decision.kind == D_HIT_STAY and g.decision.player == 1


def test_flip_four_queues_actions_and_resolves_after():
    # p1 dealt F4 targets self: draws 3, STEAL, 5, 6 ; then STEAL resolves (p0 has 9)
    g = make([FLIP4, 3, STEAL, 5, 6, 9, 1])
    g.step(a_player(1))
    # after four cards the queued Steal resolves, but p0 has no cards yet, so it fizzles
    assert g.players[1].line == [3, 5, 6]
    assert g.players[0].line == [9]


def test_flip_four_bust_loses_queue():
    g = make([FLIP4, 3, M10, 3, 6, 9])
    g.step(a_player(1))
    assert g.players[1].status == BUSTED
    # the -10 never got assigned
    assert M10 in g.discard


def test_steal_can_bust_thief():
    g = make([9, 4, 9, 1, 2, STEAL], n=3, dealer=2)  # deal order p0, p1, p2
    g.step(A_HIT)  # p0: 9, 1
    g.step(A_HIT)  # p1: 4, 2
    g.step(A_HIT)  # p2 draws STEAL
    assert g.decision.kind == D_STEAL
    assert set(g.decision.options) == {a_card(0, 9), a_card(0, 1), a_card(1, 4), a_card(1, 2)}
    g.step(a_card(0, 9))
    assert g.players[2].status == BUSTED and g.players[0].line == [1]


def test_swap_can_bust_two_players():
    # 3 players, dealer 2: p0 dealt 10, p1 dealt 11, p2 dealt SWAP
    g = make([10, 11, SWAP, 11, 10, 2], n=3, dealer=2)  # deal p0=10, p1=11, p2=SWAP
    assert g.decision.kind == D_SWAP1
    g.step(a_card(0, 10))  # the only possible second card (p1's 11) is picked automatically
    assert g.players[0].line == [11] and g.players[1].line == [10]


def test_swap_double_bust():
    g = make([10, 11, 5, 11, 10, SWAP], n=3, dealer=2)
    # deal: p0=10 p1=11 p2=5 ; p0 hits 11, p1 hits 10, p2 hits SWAP
    g.step(A_HIT)
    g.step(A_HIT)
    g.step(A_HIT)
    assert g.decision.kind == D_SWAP1
    g.step(a_card(0, 10))
    g.step(a_card(1, 11))
    assert g.players[0].status == BUSTED and g.players[1].status == BUSTED


def test_discard_own_negative_modifier():
    g = make([9, 3, M10, DISCARD], n=2)
    # deal p1=9, p0=3; p1 hits -10 and gives it to p0
    g.step(A_HIT)
    assert g.decision.kind == D_MODIFIER
    g.step(a_player(0))
    assert M10 in g.players[0].line
    g.step(A_HIT)  # p0 hits DISCARD
    assert g.decision.kind == D_DISCARD
    g.step(a_card(0, M10))
    assert g.players[0].line == [3]


def test_brutal_modifier_on_busted_player_goes_negative():
    g = make([5, 9, 5, M4, 1])
    g.step(A_HIT)  # p1 busts
    g.step(A_HIT)  # p0 draws -4
    assert g.decision.kind == D_MODIFIER
    assert a_player(1) in g.decision.options
    g.step(a_player(1))
    g.step(A_STAY)
    assert g.last_round_scores == [9, -4]


def test_standard_modifier_cannot_target_busted():
    g = make([5, 9, 5, M4, 1], rules=STANDARD)
    g.step(A_HIT)
    g.step(A_HIT)  # only p0 non-busted -> keeps it automatically
    assert M4 in g.players[0].line


def test_deck_persists_between_rounds_and_reshuffles():
    from flip7.bots import SmartBot
    bot = SmartBot()  # random players stay too early to get through the 138 cards
    reshuffles = 0
    for seed in range(4):
        g = Game(4, seed=seed)
        while not g.over:
            before = len(g.deck)
            g.step(bot.act(g))
            reshuffles += len(g.deck) > before
    assert reshuffles


def test_holds_pause_for_the_ui_and_change_nothing_else():
    for seed in range(6):
        plain, held = Game(3, seed=seed, log=True), Game(3, seed=seed, log=True)
        held.hold_round_end = held.hold_draws = True
        rng = random.Random(seed)
        round_holds = draw_holds = 0
        while not plain.over:
            a = rng.choice(plain.legal())
            plain.step(a)
            held.step(a)
            while held.holding:
                if held.holding == "round_end":
                    round_holds += 1
                    assert held.decision is None and not held.over
                    assert held.events[-1]["t"] != "round_end"  # the final table, not yet scored
                else:
                    draw_holds += 1
                    assert held.events[-1].get("via") == "flip4" or held.events[-1]["t"] in ("bust", "flip7")
                held.resume()
            assert held.events == plain.events
            assert [p.total for p in held.players] == [p.total for p in plain.players]
        assert round_holds == plain.round and held.winners == plain.winners
        flip4_draws = sum(1 for e in plain.events if e.get("via") == "flip4")
        assert draw_holds == flip4_draws


def test_brutal_bust_keeps_the_minus_cards():
    # p0 (holding 5) gives themselves −4, busts on a second 5, then p1 hands them −2.
    # Brutal: both minus cards stay, round score −6. Standard: a bust scores 0.
    from flip7.cards import M2, M4
    from flip7.engine import Rules, a_player
    for brutal in (True, False):
        g = Game(2, dealer=1, rules=Rules(brutal=brutal), deck=[5, 9, M4, 3, 5, M2] + [4, 6, 7, 8, 10, 11] * 3)
        g.step(A_HIT)                # p0 draws −4...
        g.step(a_player(0))          # ...and keeps it
        g.step(A_HIT)                # p1 draws 3
        g.step(A_HIT)                # p0 draws a second 5: bust
        assert g.players[0].status == BUSTED
        assert g.projected(0) == (-4 if brutal else 0)
        g.step(A_HIT)                # p1 draws −2
        if brutal:
            g.step(a_player(0))      # Brutal: may go to the busted player
            assert g.projected(0) == -6 and sorted(g.players[0].late_mods) == sorted([M4, M2])
            assert g.players[0].dead == [5, 5]
        else:
            assert a_player(0) not in g.decision.options and g.projected(0) == 0
