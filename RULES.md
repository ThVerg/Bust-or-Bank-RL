# Bust or Bank — rules as implemented

Bust or Bank is a variant of Flip 7: With a Vengeance (a game by The Op Games; this is an unofficial fan project,
and the text below is our own). It keeps the push-your-luck core and adds a bigger deck and more ways to hurt your
rivals. This is the rule set the engine (`flip7/engine.py`) implements; where a choice had to be made, it is
marked **[interpretation]**.

## Deck — 138 cards

| Kind | Cards |
|---|---|
| Numbers (106) | The Zero ×1, 1 ×1, 2 ×2, 3 ×3 … 13 ×13, 14 ×14. One of the 7s is the **Unlucky Frozen 7**, one of the 14s is the **Lucky 14**. |
| Modifiers (6) | −2, −4, −6, −8, −10, ÷2 (one each) |
| Keepers (4) | Tax Collector ×2, Spite ×2 |
| Actions (22) | Just One More! ×2, Flip Four! ×2, Swap ×4, Steal ×2, Discard ×2, Special Delivery ×2, Bounty ×2, Double Dare ×2, Shakedown ×2, Robin Hood ×2 |

The deck is **not** reshuffled between rounds. Used cards go to a discard pile, which is shuffled into a
new deck only when the draw pile runs out (also mid-round; cards on the table stay where they are).
Everything is dealt face up, so the composition of the draw pile is public knowledge for anyone who counts.

## Round

1. **Deal.** Starting left of the dealer and ending with the dealer, each player who is still active gets one
   card. Action, modifier and keeper cards are resolved as soon as they appear; nobody gets a replacement card.
2. **Turns.** Clockwise from the dealer's left, each *active* player either **Hits** (takes one card) or
   **Stays** (banks their line and takes no more normal turns). Repeat until nobody is active.
3. **Bust.** Holding two Number cards of the same number busts you: your line is turned face down and you
   score 0 (Brutal: your minus cards stay, so you score 0 minus every modifier you hold, including any given
   to you after busting, and the round can go negative). Cards that arrive by Swap, Steal or Special Delivery
   bust you too, and a Swap can bust two players at once. Modifiers and keepers never bust.
4. **Flip 7.** Holding seven Number cards (without busting) ends the round immediately for everyone.
   Modifiers and keepers do not count. A Flip 7 can also happen through Steal, Swap or Special Delivery.

The dealer button moves one seat left each round.

## Special number cards

Effects belong to the card: when it moves, the old holder loses the effect and the new holder gains it.

- **The Zero** — worth 0 and counts toward the seven. While you hold it your number total is 0 unless you
  Flip 7, and on your turn you **must Hit** (you can't voluntarily Stay). A forced Stay (Just One More) still
  applies. **[interpretation: modifiers still subtract from that 0, so in Brutal it can go negative]**
- **Unlucky Frozen 7** — when it enters your line (by any route: drawn, dealt, swapped, stolen or delivered),
  every other card in your line is discarded, you keep only the 7, and you **freeze**: you stay at once and
  can't take cards from the deck again this round. Frozen players can't be targeted by Just One More, Flip
  Four, Double Dare or a numbered Special Delivery, and a Shakedown leaves them only the option to pay.
  Their line can still be Swapped, Stolen or Discarded, and they can still be given modifiers. You can't bust
  by receiving it; a 7 that reaches your line later (by Swap, say) busts you. You stay frozen for the rest of the
  round even if the 7 leaves your line. A Flip Four on a player who freezes stops; cards it had already queued
  are still resolved.
- **Lucky 14** — while you hold it you may hold one additional 14. Both score and both count toward the seven.
  A third 14 busts you.

## Action cards

The player who receives an action card resolves it immediately, then it is discarded. It **must** be used if
a legal use exists, otherwise it is discarded without effect. Unless a card says otherwise, valid target players
are all non-busted players, including yourself and players who have stayed.

- **Just One More!** — choose a player who isn't frozen: they take the next card (resolving it if it is an
  action), then they must Stay. A stayed target takes the card and stays inactive. A player targeted during the
  opening deal, before their own deal card, gets the Just One More card instead: having stayed, they are
  skipped when the deal reaches them.
- **Flip Four!** — choose a player who isn't frozen: they take the next four cards one at a time, stopping early
  on a bust or Flip 7. Numbers take effect immediately; actions, modifiers and keepers drawn are queued and
  resolved by that player in order afterwards, only if they didn't bust and the round didn't end. A stayed
  target stays inactive afterwards.
- **Swap** — exchange two face-up cards (numbers, modifiers or keepers) that belong to two different non-busted
  players. One of them may be you. Both lines are then checked for busts and Flip 7.
- **Steal** — take any face-up card (number, modifier or keeper) from another non-busted player's line and add
  it to yours. A duplicate busts you.
- **Discard** — choose any card in any non-busted player's line (yours included) and it is discarded.
- **Special Delivery** — flip the next card of the deck face up and choose who gets it:
  - a **number** goes into the chosen player's line (any non-busted player who isn't frozen, you included);
    it can bust them or complete their Flip 7;
  - a **modifier** lands on the chosen player directly, with no further choice (Brutal: busted players too);
  - a **keeper** goes into the chosen player's line;
  - an **action** is resolved by the chosen player, who makes its choices.
  If nobody can take the card, it is discarded.
- **Bounty** — put it on another non-busted player. If that player busts this round because of another
  player's card, that player banks **+10** on their total immediately (per Bounty on the victim). The cards that
  count: a Swap (the swapper), a Special Delivery (the deliverer), a Just One More or Flip Four (whoever played
  it), a hit forced by a Double Dare (the darer), and the card taken instead of paying a Shakedown (whoever
  shook them down). A bust on your own hit, deal card or Steal pays nobody. Bounties stack and are removed at the
  end of the round.
- **Double Dare** — choose another player who is still taking turns: on their next two turns they must Hit.
  Two Dares on the same player add up. A Just One More still makes them stay.
- **Shakedown** — choose another non-busted player. They choose: **pay you 10 points** from their total, or
  **take a card** right now instead (which can bust them; a stayed player stays). A frozen player must pay.
- **Robin Hood** — 10 points move from the player with the highest total to the player with the lowest. Ties
  go to the seat nearest the left of whoever resolved the card (they can be that player). Nothing happens if
  everyone is level. Nobody chooses.

## Keeper cards

Keepers go into the line of whoever resolves them and stay there like a modifier: they can be Swapped, Stolen,
Discarded or wiped by the Unlucky Frozen 7. They are worth 0, never bust you and don't count toward Flip 7. A line
may hold both copies of a keeper.

- **Tax Collector** — when the round is scored, if you haven't busted, every player whose total (before this
  round's points) is higher than yours pays you **5 points** per Tax Collector you hold.
- **Spite** — if you bust while holding it, choose another player (busted or not): they lose **10 points** from
  this round's score, per Spite you held. The Spite is then discarded with your line.

## Modifier cards

When revealed, the receiving player gives the modifier to a player. Standard: any non-busted player
(including stayed players and yourself). **Brutal: any player, including busted ones.** Modifiers can be moved
by Swap/Steal and removed by Discard.

## Scoring a round

For each non-busted player:

1. Add the Number cards (The Zero without Flip 7 → total is 0).
2. ÷2 → halve, rounding down.
3. Subtract −2…−10 modifiers. Standard: never below 0. **Brutal: may go negative.**
4. Subtract Spite penalties.
5. Flip 7 → +15. **Brutal: the player who flipped 7 chooses +15 for themselves or −15 for another player.**

Busted players score 0 (Standard), or −(every −2…−10 they hold) − Spite penalties (Brutal). ÷2 does nothing to a
busted player. Standard: no round score is below 0.

Then the Tax Collectors collect, comparing the totals from before this round. Under Standard rules no payment
(Shakedown, Robin Hood, Tax Collector) takes a total below 0: the payer pays what they have.

## End of game

At the end of a round in which someone has 200+ points, the highest total wins.
**[interpretation: a tie for the highest total is a shared win]** Bounties and other payments during a round
count toward that total, but the game only ends at the end of a round.

## Player count

The engine supports 2–6 players.
