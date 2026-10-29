# Results

Everything here is on the Bust or Bank rules as the engine plays them by default (busted players keep their
minus cards, Flip 7 is +15 or −15 for a rival, race to 200). "Shark" is the network on the site
(`models/flip7_rl.pt`) on its own, "Boss" the network plus search (`BossBot`). The network is run `bob2`
(12 hours of self-play) plus a fine-tune on Special Delivery and Shakedown targets (below).

## Win rates

One bot against copies of another, seats rotated (`flip7.matchups`); the fair share is 50% / 33% / 25% /
20% / 17% at 2–6 players. 1000 games per row (± 3 points), 400 with the Boss (± 5).

| Table | Shark vs SmartBot | Boss vs SmartBot | Boss vs Shark |
|---|---|---|---|
| 2 players | 61.8% | 64.5% | 52.8% |
| 3 players | 43.2% | | |
| 4 players | 34.2% | 38.9% | 30.5% |
| 5 players | 25.8% | | |
| 6 players | 27.0% | 29.8% | |

Against Steady Eddie (hits to 25) the Shark wins 68.1% heads-up and 45.4% at 4 players. Against three
random players it wins 92.9%, a little less than SmartBot's 96.6%: it keeps its aggressive style when a
safer one would do.

## Training

`flip7.benchmark` plays the candidate and the incumbent on identical deals, seats and opponents, so the
luck of the cards cancels out. Differences are in points of win share, ± a 95% interval, 300 seeds per row.

The starting point was a network trained on the original Flip 7: With a Vengeance rules, carried over
input by input (`flip7/remap.py`). It already beat SmartBot at the new game (58.8% heads-up, 32.0% at 4
players, 23.3% at 6). After a short first run (`bob1`, 67,000 games), `bob2` trained for 12 hours (1.5
million games). After 3 hours it was level with the start in every row. At the end:

| Line-up | 2 players | 4 players | 6 players |
|---|---|---|---|
| vs the start (self) | +0.7 ± 3.6 | +2.2 ± 2.6 | +2.1 ± 1.7 |
| vs SmartBot | +1.0 ± 4.4 | +2.2 ± 3.5 | +3.6 ± 2.7 |
| mixed (start, SmartBot, Steady Eddie) | +0.7 ± 4.6 | −1.9 ± 3.3 | +1.4 ± 2.9 |

Clearly better at 6 players, level at 2 and 4. Most of what changed is how it plays the new cards, and
those decisions are too rare to move a game benchmark much. With 200 games per table size of each network
against itself (`flip7.analyze`):

| | Start | After `bob2` |
|---|---|---|
| Shakedowns paid (instead of taking a card) | 14.5% | 0.2% |
| … at a 20–30% bust risk | 50% | 0% |
| … while already stayed | 32% | 0.3% |
| Special Delivery numbers kept when they bust nobody | 0% | 5% |
| Special Delivery actions kept | 0% | 21% |
| Special Delivery keepers kept | 0% | 20% |

The starting network paid a Shakedown the way it stayed: paying is the "stay" action, so it inherited its
hit-or-stay judgement. Paying hands a rival 10 points for sure, while a card that doesn't bust you adds to
your own round; SmartBot, which works the odds out card by card, almost never pays either.

## Special Delivery

After `bob2`, Special Delivery was the network's weakest decision: it handed numbers that bust nobody to
the leader instead of keeping them, and gave up about 2 points of win chance per Delivery (see the probes
below). Fine-tuning it towards the Boss's choices (`flip7.distill`: the Boss is asked about every Delivery
and Shakedown target in the network's games, about 21,000 positions, and a KL term on 280,000 other
decisions holds the network to its own moves everywhere else) barely helped at first: on fresh positions
the loss went from 2.00 to 1.80 points (−0.21 ± 0.47).

The network couldn't see what a Delivery would do. It saw the revealed card and every player's line, but
"this card busts player 3" is an interaction between the two that it had to learn from a decision that
comes up two or three times a game. With three inputs per player added for Delivery decisions (the card
would bust them, would complete their Flip 7, and the change to their round score), the same fine-tune
took: it picks the Boss's move on 63% of held-out positions where it used to disagree (56% without the
inputs), keeps its own move on 97.7% of the other decisions, and on fresh positions its loss per
Delivery went from 2.21 to 0.71 points (−1.50 ± 0.38). Older networks load with the new inputs at zero, so
they play exactly as before.

In games the fine-tuned network is level with `bob2` (every row within ± 2.1 points, none clearly
different), as expected for a decision this rare. What it does with a Delivery now:

| | Before | After |
|---|---|---|
| Delivers a bust when the number allows one | 44% | 74% |
| Keeps a number that busts nobody | 5% | 56% |
| Keeps an action card | 21% | 70% |
| Keeps a keeper | 21% | 82% |

## Move by move

`flip7.probe` samples positions of each kind from the network's own games and plays every legal move out
to the end of the round on 192 shared deck orders (the network plays the rest of the round, its value head
scores the next round's start). The table shows how many points of win chance each bot's move gives up
against the best one, on average, ± a standard error; 96–120 positions per row.

| Decision | `bob2` | Shark (site) | Boss | SmartBot |
|---|---|---|---|---|
| Special Delivery | 1.07 ± 0.16 | 0.30 ± 0.07 | 0.24 ± 0.06 | 0.49 ± 0.09 |
| Shakedown target | 0.61 ± 0.13 | 0.46 ± 0.09 | 0.54 ± 0.09 | 0.57 ± 0.14 |
| Bounty target | 0.19 ± 0.04 | 0.16 ± 0.03 | 0.16 ± 0.03 | 0.20 ± 0.04 |
| Double Dare target | 0.20 ± 0.04 | 0.20 ± 0.04 | 0.28 ± 0.06 | 0.21 ± 0.05 |
| Pay or draw (Shakedown) | 0.04 ± 0.03 | 0.04 ± 0.03 | 0.04 ± 0.03 | 0.36 ± 0.29 |
| Spite target | 0.07 ± 0.01 | 0.08 ± 0.02 | 0.08 ± 0.02 | 0.08 ± 0.02 |
| Just One More / Flip Four target | 0.62 ± 0.12 | 0.55 ± 0.11 | 0.39 ± 0.09 | 3.89 ± 0.67 |
| Modifier target | 0.34 ± 0.09 | 0.34 ± 0.09 | 0.27 ± 0.08 | 0.26 ± 0.08 |
| Steal | 1.97 ± 0.49 | 2.08 ± 0.51 | 0.44 ± 0.11 | 1.47 ± 0.33 |
| Discard | 0.90 ± 0.18 | 0.88 ± 0.18 | 0.46 ± 0.10 | 1.05 ± 0.19 |
| Flip 7: +15 or −15 | 0.04 ± 0.03 | 0.46 ± 0.43 | 0.01 ± 0.01 | 0.75 ± 0.44 |
| Hit or stay | 0.03 ± 0.01 | 0.03 ± 0.01 | 0.01 ± 0.01 | 0.06 ± 0.04 |

- **Hit-or-stay, the bulk of the game, is nearly clean**: 0.03 points per decision.
- **Steal and Discard are where the Shark still goes wrong**: about 2 and 0.9 points per decision. The
  Boss's search brings both under 0.5, which is most of why it beats the Shark.
- The Shark's Flip 7 row comes from a single bad position (± 0.43): the fine-tune changed 31 of 1,500
  Flip 7 choices, in both directions.
- The scores use the network's own value head at the next round, so they favour moves that network likes;
  the Boss uses the same head. SmartBot's numbers are the most independent check.

## The levels under other rules

Do Rookie < Shark < Boss hold when the rules change? Paired benchmarks against SmartBot tables
(`flip7.conditions`, 200 seeds, points of win share ± a 95% interval):

| Rules | Shark vs Rookie, 2p | Shark vs Rookie, 4p | Boss vs Shark, 2p | Boss vs Shark, 4p |
|---|---|---|---|---|
| Brutal, to 200 | +9.4 ± 6.3 | +11.9 ± 4.2 | +4.4 ± 5.6 | +8.0 ± 4.4 |
| Standard, to 200 | +15.2 ± 6.3 | +8.2 ± 4.3 | −4.2 ± 5.6 | +4.8 ± 4.6 |
| Brutal, to 100 | +9.5 ± 5.2 | +9.9 ± 3.8 | +4.1 ± 5.3 | +3.9 ± 4.2 |
| Brutal, to 300 | +3.4 ± 6.6 | +9.4 ± 3.9 | +3.6 ± 6.9 | +5.4 ± 4.4 |

The Shark beats the Rookie everywhere. The Boss is ahead of the Shark at 4 players under every rule set;
heads-up the rows are within noise.

## Calibration

`flip7.calibrate` compares the value network's win chances with the share of 40 playouts won from the same
1,204 positions. They are off by 6.9 points on average, against a playout noise floor of 5.3. At
all-network tables the error is near the floor (5.6 vs 5.2). Against SmartBot it underrates itself by 7.7
points, because it learned by playing itself. It picks the best of the ranked actions 62% of the time,
with the policy and with the value head alike, and 89% in endgames. Its least reliable estimates are for
Swaps, where the value head picks the best exchange only 10% of the time: the reason the Boss plays Swaps
out instead.

## How it plays

From `analysis/insights.json` (`flip7.analyze`, about 1.27 million of the network's decisions and 1.22
million of SmartBot's); the Insights page has the charts.

- It almost never stays while its bust chance is under 15%, and stays at about 34–38 points. It busts in
  42–46% of its rounds, against 33–39% for SmartBot, and still wins more: in a race to 200, big rounds
  matter more than safe ones.
- The scoreboard sets its risk: 100+ points behind the leading rival it hits until about 46 points, level
  about 35, 100+ ahead it banks at about 23. SmartBot's stay point hardly moves (25–29).
- Flip Four and Just One More are weapons: it uses them on itself in under 1% of cases (SmartBot: 91% and
  54%) and aims them at the leader 70% of the time, where a random opponent would be 44%. ÷2 goes to the
  leader 63% of the time.
- Holding six different numbers it hits 87% of the time, and 66% of the time even at a 40–50% bust risk.
  It Flips 7 about twice as often as SmartBot (2.7–3.7% vs 1.3–1.6% of rounds).
- After a Flip 7 it takes the +15 93% of the time and never gives −15 while leading.
- It pays a Shakedown under 1% of the time, and delivers a bust with Special Delivery 74% of the time when
  the card allows one.
