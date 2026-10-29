# Training and analysis

Everything runs on CPU. Training runs and their logs go to `runs/` (not in the repository).

## Train a network

```bash
# self-play PPO; uses about (workers + learner_threads + 1) cores
.venv/bin/python -m flip7.train --name r1 --hours 4 --workers 6 --learner_threads 3
# continue from a checkpoint
.venv/bin/python -m flip7.train --name r2 --hours 4 --workers 6 --learner_threads 3 --init runs/r1/latest.pt

# a bigger network that starts out computing exactly what a trained one does (copied units with
# randomly split outgoing weights, identity layers), then train it with its own size flags
.venv/bin/python -m flip7.grow models/flip7_rl.pt runs/grown.pt --hidden 512 --layers 4 --v_hidden 768 --v_layers 3
.venv/bin/python -m flip7.train --name g1 --init runs/grown.pt --hidden 512 --layers 4 --v_hidden 768 --v_layers 3
```

Training logs go to `runs/<name>/log.jsonl` (PPO statistics, including how old each decision's weights
were: `lag_*`) and `runs/<name>/eval.jsonl`. The evaluator plays frozen snapshots on a fixed set of seeds
with seat rotation, against SmartBot and against the starting checkpoint (`anchor_*`), with 95% intervals
(`*_ci`). `*_avg_edge` is the win rate divided by the fair share (1.0 = level). Those replay the same few
deals every time, so treat them as progress indicators and decide with `flip7.benchmark`.

## How the site's network was made

```bash
# 1. start from a network trained on the original Flip 7: With a Vengeance rules (not in this repository;
#    flip7.model.load carries such a checkpoint over input by input) and train on Bust or Bank:
#    a short first run, then 12 hours
.venv/bin/python -m flip7.train --name bob1 --init original.pt --hidden 256 --layers 3 --v_hidden 384 \
    --v_layers 3 --workers 4 --learner_threads 2
.venv/bin/python -m flip7.train --name bob2 --init runs/bob1/latest.pt --hidden 256 --layers 3 --v_hidden 384 \
    --v_layers 3 --workers 10 --learner_threads 4 --lr 0.0002 --lr_final 0.00003 --hours 12
# 2. fine-tune Special Delivery and Shakedown targets towards the Boss's choices, with the per-player
#    Delivery inputs (what the revealed card would do to each player), which older networks load as zeros
.venv/bin/python -m flip7.distill collect --model runs/bob2/latest.pt --teacher boss --kinds deliver,shakedown \
    --positions 300000 --p_eval 1 --workers 14 --seed 12 --out runs/distill/bob_ds2.npz
.venv/bin/python -m flip7.distill train --model runs/bob2/latest.pt --data runs/distill/bob_ds2.npz \
    --out runs/distill/bob_ds2.pt --kl_coef 30 --epochs 16 --lr 0.0002
.venv/bin/python -m flip7.promote runs/distill/bob_ds2.pt
```

Game benchmarks can't see a change to a decision that comes up once or twice a game. To judge one, score
moves on fresh positions instead: `flip7.probe` plays every option out to the end of the round on shared
deck orders and reports how much win chance each bot's choice gives up, per kind of decision:

```bash
.venv/bin/python -m flip7.probe --ref runs/bob2/latest.pt \
    --bots nn:runs/bob2/latest.pt,nn:runs/distill/bob_ds2.pt,boss:runs/bob2/latest.pt,smart --workers 14
```

## Compare and promote

```bash
# paired benchmark: candidate vs incumbent on identical deals, seats and opponents
#   lineups: self (vs the incumbent), smart (vs SmartBot), mixed (incumbent/SmartBot/history/Hit-to-25)
#   use --split dev while choosing, and --split final (disjoint seeds) once to confirm a promotion
.venv/bin/python -m flip7.benchmark --candidate runs/r2/latest.pt --incumbent models/flip7_rl.pt \
    --history runs/r1/pool/v000120.pt --players 2,4,6 --seeds 400 --split dev
# the candidate can also be a search bot: --candidate search:models/flip7_rl.pt or boss:models/flip7_rl.pt

# quick unpaired evaluation (hero in one rotating seat, villain in all others)
.venv/bin/python -m flip7.evaluate --hero nn:models/flip7_rl.pt --villain smart --players 2,4 --games 2000

# serve a checkpoint in the web app: archives the current models/flip7_rl.pt to models/archive/,
# writes the new one (keeping title and blurb, recording its source and SHA-256) and asks the
# running server to reload its bots (games in progress keep theirs)
.venv/bin/python -m flip7.promote runs/r2/latest.pt
```

Bot specs used by the benchmark, evaluation and probe tools: `nn:<ckpt>` (the network), `search:<ckpt>`
(one-move lookahead), `boss[K][s]:<ckpt>` (the Boss: K rollout deck orders for Swaps, default 32; a
trailing `s` searches endgame hit/stay too), `rollout[K][t<temp>]:<ckpt>`, `adaptive[MAXK]:<ckpt>`,
`smart`, `threshold<N>`, `random`.

If a change adds inputs to the network (`flip7/encoding.py`), add them at the end of `FEATURES`: older
checkpoints then load with the new inputs at zero and play exactly as before (`flip7.remap.pad_inputs`).

## Look for weaknesses

```bash
# exploiter: a copy trained only against frozen checkpoints (one learner seat), to find weaknesses;
# bundle its benchmarks for the Insights page with flip7.exploitability
.venv/bin/python -m flip7.train --name x1 --init models/flip7_rl.pt --exploit models/flip7_rl.pt --hours 3

# verified tactical positions: hard decisions from the network's games (Swaps, targets, Steals, Discards,
# the Flip 7 choice, hit/stay), every candidate move played to the end of the game on shared shuffles;
# then score bots on them (report writes analysis/tactics.json)
.venv/bin/python -m flip7.tactics build --model models/flip7_rl.pt --per-kind 60 --workers 10 --seed 1 \
    --out data/tactics.pkl
.venv/bin/python -m flip7.tactics score data/tactics.pkl search:models/flip7_rl.pt boss:models/flip7_rl.pt
.venv/bin/python -m flip7.tactics report data/tactics.pkl --bot "Boss=boss:models/flip7_rl.pt=what it is" \
    --out analysis/tactics.json

# distillation: ask a search teacher about chosen kinds of decision, fine-tune the network toward its moves
.venv/bin/python -m flip7.distill collect --model models/flip7_rl.pt --teacher boss --kinds steal,discard \
    --positions 300000 --p_eval 1 --workers 6 --out runs/distill.npz
.venv/bin/python -m flip7.distill train --model models/flip7_rl.pt --data runs/distill.npz --out runs/distilled.pt
```

## Regenerate the Insights data

Each step writes one file in `analysis/`:

```bash
.venv/bin/python -m flip7.matchups --model models/flip7_rl.pt --games 1000 --workers 3   # matchups.json
.venv/bin/python -m flip7.analyze --model models/flip7_rl.pt --games 1500 --workers 4 \
    --matchups analysis/matchups.json                                                    # insights.json
.venv/bin/python -m flip7.findings                                                       # findings.json
.venv/bin/python -m flip7.calibrate --model models/flip7_rl.pt --workers 4               # calibration.json
.venv/bin/python -m flip7.conditions --seeds 200 --workers 4                             # conditions.json
```

- `flip7.matchups`: head-to-head win rates (the network, the Boss, SmartBot, threshold and random bots).
- `flip7.analyze`: plays thousands of all-network and all-SmartBot games and records every decision with
  its situation: when it stays (by score, bust chance, player count, standing), where it sends weapons,
  what it does with minus cards, after a Flip 7 and with each Bust or Bank card.
- `flip7.findings`: writes the headline findings as text, reading every number from `insights.json`, so
  they stay true when the model or the rules change.
- `flip7.calibrate`: are the value network's win chances right? Compares them with the share of playouts
  won from the same positions, and checks how often the policy and the value head pick the best action.
- `flip7.conditions`: do the difficulty levels (Rookie < Shark < Boss) keep their order under Standard
  rules and other targets?
- `flip7/coach.py`: the post-game coach. It plays every option of a decision out on the same deck orders
  and reports the lost win chance with a 95% interval, plus exact facts from the engine (cards that would
  bust you, who a Swap busts, and so on).

The Insights page shows `tactics.json` and `exploitability.json` too when they exist (see *Look for
weaknesses*); the repository doesn't have them for Bust or Bank yet.
