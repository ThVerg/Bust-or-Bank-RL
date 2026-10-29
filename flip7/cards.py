"""Card ids for Bust or Bank (see RULES.md).

Ids are grouped by what the card does:

* 0..16 numbers: 0..14 are the plain cards with value == id (0 is The Zero), then the Unlucky Frozen 7
  and the Lucky 14,
* 17..22 modifiers, 23..24 keepers (they sit in a line like a modifier),
* 25..34 actions.

Ids below ``N_LINE_KINDS`` can sit in a player's line. Within one non-busted line every number
and modifier appears at most once; a line can hold both copies of a keeper.
"""

# Numbers: ids 0..14 are the plain number cards with value == id (0 is The Zero).
ZERO = 0
U7 = 15   # Unlucky Frozen 7
L14 = 16  # Lucky 14
# Modifiers
M2, M4, M6, M8, M10, DIV2 = 17, 18, 19, 20, 21, 22
# Keepers
TAX, SPITE = 23, 24
# Actions
JOM, FLIP4, SWAP, STEAL, DISCARD = 25, 26, 27, 28, 29
DELIVERY, BOUNTY, DARE, SHAKEDOWN, ROBIN = 30, 31, 32, 33, 34

N_NUMBER_KINDS = 17
FIRST_MODIFIER = 17
FIRST_KEEPER = 23
N_LINE_KINDS = 25
N_KINDS = 35

NUMBER_IDS = tuple(range(N_NUMBER_KINDS))
MODIFIER_IDS = (M2, M4, M6, M8, M10, DIV2)
KEEPER_IDS = (TAX, SPITE)
ACTION_IDS = (JOM, FLIP4, SWAP, STEAL, DISCARD, DELIVERY, BOUNTY, DARE, SHAKEDOWN, ROBIN)

# Rank (the number printed) and value of number cards; -1 for the rest.
RANK = tuple(list(range(15)) + [7, 14] + [-1] * (N_KINDS - N_NUMBER_KINDS))
MOD_PENALTY = {M2: 2, M4: 4, M6: 6, M8: 8, M10: 10, DIV2: 0}

COUNTS = [0] * N_KINDS
COUNTS[ZERO] = 1
for _n in range(1, 15):
    COUNTS[_n] = _n
COUNTS[7] -= 1   # one 7 is the Unlucky Frozen 7
COUNTS[14] -= 1  # one 14 is the Lucky 14
COUNTS[U7] = 1
COUNTS[L14] = 1
for _m in MODIFIER_IDS:
    COUNTS[_m] = 1
for _c in KEEPER_IDS + ACTION_IDS:
    COUNTS[_c] = 2
COUNTS[SWAP] = 4
COUNTS = tuple(COUNTS)
DECK_SIZE = sum(COUNTS)
assert DECK_SIZE == 138

NAMES = tuple(
    ["The Zero"] + [str(i) for i in range(1, 15)]
    + ["Unlucky Frozen 7", "Lucky 14", "-2", "-4", "-6", "-8", "-10", "÷2", "Tax Collector", "Spite",
       "Just One More", "Flip Four", "Swap", "Steal", "Discard", "Special Delivery", "Bounty", "Double Dare",
       "Shakedown", "Robin Hood"]
)
SHORT = tuple(
    [str(i) for i in range(15)]
    + ["7f", "14L", "-2", "-4", "-6", "-8", "-10", "/2", "TAX", "SPT",
       "JOM", "F4", "SWP", "STL", "DSC", "DLV", "BTY", "DAR", "SHK", "ROB"]
)


def is_number(c):
    return c < N_NUMBER_KINDS


def is_modifier(c):
    return FIRST_MODIFIER <= c < FIRST_KEEPER


def is_keeper(c):
    return FIRST_KEEPER <= c < N_LINE_KINDS


def is_action(c):
    return c >= N_LINE_KINDS


def full_deck():
    deck = []
    for c, k in enumerate(COUNTS):
        deck.extend([c] * k)
    return deck
