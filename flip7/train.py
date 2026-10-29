"""Self-play PPO with an opponent league.

    python -m flip7.train --name main --hours 2

Layout: worker processes play many games at once with batched network inference and stream
finished trajectories to the learner (this process), which runs PPO updates and publishes new
weights through shared memory. Workers pick up new weights between moves, so data is at most a
version or two stale; PPO's importance ratio uses the behaviour policy's log-probs, so that is fine.

Opponents per game: mostly pure self-play, plus past snapshots of the network (the "league") and
the hand-written bots, so the policy doesn't overfit to its current self. The reward is 1 for
winning the game (shared on ties) and 0 otherwise, so the bots maximise win probability, not
points.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import random
import time
from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.multiprocessing as mp
import torch.nn.functional as F
from torch.nn.utils import parameters_to_vector

from .bots import SmartBot, ThresholdBot
from .encoding import OBS_DIM, encode, rel_to_abs, winner_target
from .engine import MAX_PLAYERS, N_ACTIONS, Game, Rules
from .model import Net, NeuralBot, load, save

RUNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs")


@dataclass
class Config:
    name: str = "main"
    seed: int = 0
    hidden: int = 256
    layers: int = 3
    v_hidden: int = 512          # separate value trunk (0 = share the policy trunk)
    v_layers: int = 3
    workers: int = 12
    learner_threads: int = 4
    games_per_worker: int = 96
    chunk: int = 4096            # samples per worker->learner message
    batch: int = 131072          # samples per PPO update
    minibatch: int = 4096
    epochs: int = 3
    lr: float = 3e-4
    lr_final: float = 5e-5
    clip: float = 0.2
    ent_coef: float = 0.01
    ent_final: float = 0.002
    vf_coef: float = 1.0
    round_lambda: float = 0.6    # how much a round's target looks past the next round start
    value_warmup: int = 0        # updates that train only the value head (after a warm start)
    max_grad_norm: float = 0.5
    max_lag: int = 3             # drop decisions made by weights more than this many versions old
    hours: float = 2.0
    n_choices: tuple = (2, 3, 4, 5, 6)
    brutal: bool = True
    p_self: float = 0.6          # pure self-play games
    p_pool: float = 0.3          # league games: PFSP over snapshots + hand-written bots, mixed seats
                                 # (rest: vs hand-written bots only)
    snapshot_every: int = 20     # updates
    checkpoint_every: int = 10
    eval_games: int = 30         # fixed seeds per player count per evaluation (x n rotated seats)
    init: str = ""               # warm start from a checkpoint
    exploit: str = ""            # exploiter training: comma-separated checkpoints that fill every seat
                                 # but one learner seat in every game (no self-play, league or bots);
                                 # they play greedily, as deployed, while league snapshots sample
    anchor: str = ""             # checkpoint the evaluator compares against (default: init)


# ----------------------------------------------------------------------------- weights

def _load_shared(model, flat, version, lock):
    """Copy the published weights into the model's own storage and return their version.

    ``vector_to_parameters`` would make the parameters *views* of the shared buffer, so the
    learner's next publish would change the model in the middle of inference. Copying under the
    lock gives each reader a stable, consistent snapshot.
    """
    with lock:
        i = 0
        with torch.no_grad():
            for p in model.parameters():
                n = p.numel()
                p.copy_(flat[i:i + n].view_as(p))
                i += n
        return version.value


# ----------------------------------------------------------------------------- workers

class Running:
    __slots__ = ("game", "ctrl", "traj", "opponents")

    def __init__(self, game, ctrl, opponents=()):
        self.game = game
        self.ctrl = ctrl                  # per seat: "L" | ("S", path) | bot instance
        self.traj = {p: [] for p, c in enumerate(ctrl) if c == "L"}
        self.opponents = set(opponents)   # league keys at the table, for PFSP statistics


HEURISTIC_KEYS = ("smart", "thr20", "thr25", "thr30")


def _heuristic(key):
    return SmartBot() if key == "smart" else ThresholdBot(int(key[3:]))


class League:
    """Prioritised opponent sampling (PFSP), kept per worker.

    Tracks an exponential moving average of the learner's edge (win share x table size, so 1.0 is
    parity) against every opponent it meets, and samples opponents with weight
    ``max(0.1, 2 - edge) ** 2``: the ones the learner handles worst come up most often.
    """

    def __init__(self, decay=0.97):
        self.edge = {}
        self.decay = decay

    def weight(self, key):
        return max(0.1, 2.0 - self.edge.get(key, 1.0)) ** 2

    def sample(self, rng, keys):
        return rng.choices(keys, weights=[self.weight(k) for k in keys])[0]

    def update(self, keys, edge):
        for k in keys:
            self.edge[k] = self.decay * self.edge.get(k, 1.0) + (1 - self.decay) * edge

    def hardest(self, k=5):
        return dict(sorted(self.edge.items(), key=lambda kv: kv[1])[:k])


def _new_game(rng, cfg, rules, pool, league):
    """Mostly pure self-play. League games fill every non-learner seat independently by PFSP
    from past snapshots and the hand-written bots, so tables are mixed; the rest are vs the
    hand-written bots only. With ``cfg.exploit`` the learner instead takes one seat against the
    fixed checkpoints."""
    n = rng.choice(cfg.n_choices)
    game = Game(n, rules=rules, rng=random.Random(rng.random()), dealer=rng.randrange(n))
    r = rng.random()
    ctrl = ["L"] * n
    opponents = []
    if cfg.exploit:
        seat = rng.randrange(n)
        for p in range(n):
            if p != seat:
                key = rng.choice(cfg.exploit.split(","))
                opponents.append(key)
                ctrl[p] = ("S", key)
    elif r >= cfg.p_self:
        k = rng.randint(1, n - 1)                 # learner seats
        others = rng.sample(range(n), n - k)
        keys = list(pool) + list(HEURISTIC_KEYS) if r < cfg.p_self + cfg.p_pool else list(HEURISTIC_KEYS)
        for p in others:
            key = league.sample(rng, keys)
            opponents.append(key)
            ctrl[p] = _heuristic(key) if key in HEURISTIC_KEYS else ("S", key)
    return Running(game, ctrl, opponents)


def _finish(run, cfg, out):
    """Targets bootstrapped at round boundaries.

    Every decision in round r is judged by the predicted win chances at my first decision of
    round r+1, blended (``round_lambda``) with the targets of later rounds; the last round uses
    the actual result. A decision then carries the luck of (mostly) one round instead of the
    whole rest of the game, which makes the learning signal far less noisy.
    """
    g = run.game
    lam = cfg.round_lambda
    for p, steps in run.traj.items():
        if not steps:
            continue
        rounds = []
        first_vec = {}
        for st in steps:
            r = st[6]
            if r not in first_vec:
                first_vec[r] = st[5]
                rounds.append(r)
        target = winner_target(g, p)
        by_round = {}
        for r in reversed(rounds):
            by_round[r] = target
            target = (1 - lam) * first_vec[r] + lam * target
        for obs, mask, a, logp, v, _, r, ver in steps:
            vt = by_round[r]
            out["ver"].append(ver)
            out["obs"].append(obs)
            out["mask"].append(mask)
            out["act"].append(a)
            out["logp"].append(logp)
            out["adv"].append(float(vt[0]) - v)
            out["ret"].append(float(vt[0]))
            out["vt"].append(vt)
            out["n"].append(g.n)


FIELDS = ("obs", "mask", "act", "logp", "adv", "ret", "vt", "n", "ver")


def _empty_out():
    return {k: [] for k in FIELDS}


def _pack(out, stats):
    return {
        "obs": np.asarray(out["obs"], np.float16),
        "mask": np.asarray(out["mask"], bool),
        "act": np.asarray(out["act"], np.int16),
        "logp": np.asarray(out["logp"], np.float32),
        "adv": np.asarray(out["adv"], np.float32),
        "ret": np.asarray(out["ret"], np.float32),
        "vt": np.asarray(out["vt"], np.float32),
        "n": np.asarray(out["n"], np.int8),
        "ver": np.asarray(out["ver"], np.int32),   # behaviour-policy version of each decision
        "stats": stats,
    }


@torch.no_grad()
def _policy_step(model, games, sample=True):
    """Batched inference. Per game: (abs action, rel action, logp, v_me, v_vec, obs, mask)."""
    B = len(games)
    obs = np.empty((B, OBS_DIM), np.float32)
    mask = np.empty((B, N_ACTIONS), bool)
    mes = []
    for i, g in enumerate(games):
        _, _, me = encode(g, obs[i], mask[i])
        mes.append(me)
    n = torch.tensor([g.n for g in games])
    logits, v_logits = model(torch.from_numpy(obs), torch.from_numpy(mask), n)
    logp_all = F.log_softmax(logits, dim=1)
    if sample:
        u = torch.rand_like(logits).clamp_(1e-9, 1.0)
        a = torch.argmax(logits - torch.log(-torch.log(u)), dim=1)
    else:
        a = torch.argmax(logits, dim=1)
    logp = logp_all.gather(1, a[:, None])[:, 0].numpy()
    vv = torch.softmax(v_logits, dim=1).numpy()
    a = a.numpy()
    res = []
    for i, g in enumerate(games):
        res.append((rel_to_abs(int(a[i]), mes[i], g.n), int(a[i]), float(logp[i]), float(vv[i, 0]),
                    vv[i], obs[i], mask[i]))
    return res


def _samples(cfg, key):
    """Whether the seats played by ``key`` sample their moves: the learner explores and league
    snapshots vary, but an exploiter's targets play greedily, exactly as the deployed bot does."""
    return key == "L" or not cfg.exploit


def worker_main(wid, cfg, flat, version, lock, data_q, stop, pool_dir):
    torch.set_num_threads(1)
    rng = random.Random(cfg.seed * 7919 + wid)
    torch.manual_seed(cfg.seed * 7919 + wid)
    rules = Rules(brutal=cfg.brutal)
    model = Net(cfg.hidden, cfg.layers, cfg.v_hidden, cfg.v_layers)
    local_version = -1
    snapshots = {}                         # path -> model (small LRU)
    pool, pool_checked = [], 0.0
    runs = []
    out = _empty_out()
    stats = {"games": 0, "decisions": 0, "game_len": 0}
    league = League()
    while not stop.is_set():
        if version.value != local_version:
            local_version = _load_shared(model, flat, version, lock)
        if time.time() - pool_checked > 30:
            pool = sorted(glob.glob(os.path.join(pool_dir, "*.pt")))
            pool_checked = time.time()
        while len(runs) < cfg.games_per_worker:
            runs.append(_new_game(rng, cfg, rules, pool, league))

        groups = {}
        for r in runs:
            c = r.ctrl[r.game.decision.player]
            if c == "L":
                groups.setdefault("L", []).append(r)
            elif isinstance(c, tuple):
                groups.setdefault(c[1], []).append(r)
            else:
                r.game.step(c.act(r.game))
                stats["decisions"] += 1
        for key, rs in groups.items():
            if key == "L":
                net = model
            else:
                if key not in snapshots:
                    if len(snapshots) >= 6:
                        snapshots.pop(next(iter(snapshots)))
                    try:
                        snapshots[key] = load(key)[0]
                    except Exception:
                        snapshots[key] = model  # snapshot vanished/partial: fall back to self
                net = snapshots[key]
            results = _policy_step(net, [r.game for r in rs], sample=_samples(cfg, key))
            for r, (a_abs, a_rel, logp, v, vvec, obs, mask) in zip(rs, results):
                if key == "L":
                    r.traj[r.game.decision.player].append(
                        (obs.copy(), mask.copy(), a_rel, logp, v, vvec.copy(), r.game.round, local_version))
                r.game.step(a_abs)
            stats["decisions"] += len(rs)

        alive = []
        for r in runs:
            if r.game.over:
                _finish(r, cfg, out)
                if r.opponents:
                    shares = r.game.returns()
                    edge = np.mean([shares[p] for p in r.traj]) * r.game.n
                    league.update(r.opponents, edge)
                stats["games"] += 1
                stats["game_len"] += r.game.round
            else:
                alive.append(r)
        runs = alive
        if len(out["act"]) >= cfg.chunk:
            stats["league"] = {os.path.basename(k): round(v, 3) for k, v in league.hardest().items()}
            data_q.put(_pack(out, stats))
            out = _empty_out()
            stats = {"games": 0, "decisions": 0, "game_len": 0}


# ----------------------------------------------------------------------------- evaluation

def rotated_share(bot, opponent, n, seeds, rules):
    """Win share of ``bot`` against copies of ``opponent()``, rotating its seat through all n seats
    on each of a *fixed* list of seeds, so every evaluation plays the same deals and versions are
    compared on equal terms. Returns (share, 95% interval half-width) with seeds as blocks."""
    blocks = []
    for s in range(seeds):
        seed = s * 7919 + n * 104_729
        tot = 0.0
        for k in range(n):
            rng = random.Random(seed)
            bots = [opponent() for _ in range(n)]
            bots[k] = bot
            g = Game(n, rules=rules, rng=rng, dealer=rng.randrange(n))
            while not g.over:
                g.step(bots[g.decision.player].act(g))
            tot += g.returns()[k]
        blocks.append(tot / n)
    m = float(np.mean(blocks))
    return m, float(1.96 * np.std(blocks, ddof=1) / np.sqrt(len(blocks))) if len(blocks) > 1 else 0.0


def evaluator_main(cfg, flat, version, lock, stop, run_dir):
    """Evaluates frozen snapshots of the training weights vs SmartBot and vs the anchor (the warm start
    unless ``cfg.anchor`` names another checkpoint)."""
    torch.set_num_threads(1)
    rules = Rules(brutal=cfg.brutal)
    model = Net(cfg.hidden, cfg.layers, cfg.v_hidden, cfg.v_layers)
    anchor = cfg.anchor or cfg.init
    anchor = NeuralBot(load(anchor)[0]) if anchor else None
    last = -1
    while not stop.is_set():
        if version.value == last:
            time.sleep(5)
            continue
        last = _load_shared(model, flat, version, lock)
        bot = NeuralBot(model, temperature=0.0)
        res = {"version": last, "time": time.time(), "seeds": cfg.eval_games}
        for n in cfg.n_choices:
            res[f"smart_{n}p"], res[f"smart_{n}p_ci"] = rotated_share(bot, SmartBot, n, cfg.eval_games, rules)
            if anchor is not None:
                res[f"anchor_{n}p"], res[f"anchor_{n}p_ci"] = rotated_share(bot, lambda: anchor, n, cfg.eval_games, rules)
        res["smart_avg_edge"] = float(np.mean([res[f"smart_{n}p"] * n for n in cfg.n_choices]))
        if anchor is not None:
            res["anchor_avg_edge"] = float(np.mean([res[f"anchor_{n}p"] * n for n in cfg.n_choices]))
        with open(os.path.join(run_dir, "eval.jsonl"), "a") as f:
            f.write(json.dumps(res) + "\n")


# ----------------------------------------------------------------------------- learner

def warm_start(model, path, v_hidden):
    """Initialise ``model`` from a checkpoint; returns (tensors copied, total, value head kept).

    Every tensor whose name and shape match is copied (``load`` already widened old first layers
    to the current observation). The value output layer ("v.") only means the same thing on the
    same kind of trunk: it is reset when switching between a shared trunk and a separate value
    trunk, and kept when resuming the same architecture.
    """
    m, ckpt = load(path)
    same_value_arch = ckpt["config"].get("v_hidden", 0) == v_hidden
    own = model.state_dict()
    src = m.state_dict()
    copied = [k for k, v in src.items() if k in own and own[k].shape == v.shape
              and (same_value_arch or not k.startswith("v."))]
    model.load_state_dict({**own, **{k: src[k] for k in copied}})
    return len(copied), len(own), same_value_arch


def train(cfg: Config):
    run_dir = os.path.join(RUNS, cfg.name)
    pool_dir = os.path.join(run_dir, "pool")
    os.makedirs(pool_dir, exist_ok=True)
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump(asdict(cfg), f, indent=1)
    torch.manual_seed(cfg.seed)
    torch.set_num_threads(cfg.learner_threads)

    model = Net(cfg.hidden, cfg.layers, cfg.v_hidden, cfg.v_layers)
    start_version = 0
    if cfg.init:
        copied, total, kept = warm_start(model, cfg.init, cfg.v_hidden)
        print(f"warm start from {cfg.init}: copied {copied}/{total} tensors "
              f"({'kept' if kept else 'reset'} the value output layer)")
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr, eps=1e-5)

    ctx = mp.get_context("spawn")
    flat = parameters_to_vector(model.parameters()).detach().clone().share_memory_()
    version = ctx.Value("i", start_version)
    lock = ctx.Lock()
    stop = ctx.Event()
    data_q = ctx.Queue(maxsize=cfg.workers * 4)
    procs = [ctx.Process(target=worker_main, args=(w, cfg, flat, version, lock, data_q, stop, pool_dir),
                         daemon=True) for w in range(cfg.workers)]
    procs.append(ctx.Process(target=evaluator_main, args=(cfg, flat, version, lock, stop, run_dir),
                             daemon=True))
    for p in procs:
        p.start()

    log_f = open(os.path.join(run_dir, "log.jsonl"), "a")
    t0 = time.time()
    deadline = t0 + cfg.hours * 3600
    total_samples = 0
    total_games = 0
    upd = 0
    try:
        while time.time() < deadline:
            frac = min(1.0, (time.time() - t0) / (cfg.hours * 3600))
            lr = cfg.lr + (cfg.lr_final - cfg.lr) * frac
            ent_coef = cfg.ent_coef + (cfg.ent_final - cfg.ent_coef) * frac
            for g in opt.param_groups:
                g["lr"] = lr

            chunks, size, dropped = [], 0, 0
            lags = []
            league_view = {}
            gstats = {"games": 0, "decisions": 0, "game_len": 0}
            t_wait = time.time()
            while size < cfg.batch:
                c = data_q.get()
                for k in gstats:
                    gstats[k] += c["stats"][k]
                league_view = c["stats"].get("league", {})
                # games span several weight versions, so age is judged per decision
                lag = version.value - c["ver"]
                lags.append(lag)
                keep = lag <= cfg.max_lag
                dropped += int((~keep).sum())
                if keep.any():
                    chunks.append({k: c[k][keep] for k in FIELDS})
                    size += int(keep.sum())
            t_wait = time.time() - t_wait
            lags = np.concatenate(lags)
            cat = {k: np.concatenate([c[k] for c in chunks]) for k in FIELDS}
            obs = torch.from_numpy(cat["obs"].astype(np.float32))
            mask = torch.from_numpy(cat["mask"])
            act = torch.from_numpy(cat["act"].astype(np.int64))
            old_logp = torch.from_numpy(cat["logp"])
            adv = torch.from_numpy(cat["adv"])
            adv = (adv - adv.mean()) / (adv.std() + 1e-8)
            vt = torch.from_numpy(cat["vt"])
            nps = torch.from_numpy(cat["n"].astype(np.int64))

            t_upd = time.time()
            N = len(act)
            m = {"pg": 0.0, "vf": 0.0, "ent": 0.0, "kl": 0.0, "clipfrac": 0.0}
            nb = 0
            for _ in range(cfg.epochs):
                perm = torch.randperm(N)
                for s in range(0, N - cfg.minibatch + 1, cfg.minibatch):
                    idx = perm[s:s + cfg.minibatch]
                    logits, v_logits = model(obs[idx], mask[idx], nps[idx])
                    logp_all = F.log_softmax(logits, dim=1)
                    logp = logp_all.gather(1, act[idx][:, None])[:, 0]
                    ratio = torch.exp(logp - old_logp[idx])
                    a = adv[idx]
                    pg = -torch.min(ratio * a, ratio.clamp(1 - cfg.clip, 1 + cfg.clip) * a).mean()
                    p_all = logp_all.exp()
                    ent = -(p_all * logp_all.clamp(min=-30)).sum(1).mean()
                    vf = -(vt[idx] * F.log_softmax(v_logits, dim=1).clamp(min=-30)).sum(1).mean()
                    if upd < cfg.value_warmup:
                        loss = cfg.vf_coef * vf
                    else:
                        loss = pg + cfg.vf_coef * vf - ent_coef * ent
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
                    opt.step()
                    with torch.no_grad():
                        m["pg"] += pg.item()
                        m["vf"] += vf.item()
                        m["ent"] += ent.item()
                        m["kl"] += (old_logp[idx] - logp).mean().item()
                        m["clipfrac"] += ((ratio - 1).abs() > cfg.clip).float().mean().item()
                    nb += 1
            t_upd = time.time() - t_upd
            with lock:
                flat.copy_(parameters_to_vector(model.parameters()).detach())
                version.value += 1
            upd += 1
            total_samples += N
            total_games += gstats["games"]
            rec = {k: v / max(nb, 1) for k, v in m.items()}
            rec.update(update=upd, version=version.value, samples=N, total_samples=total_samples,
                       total_games=total_games, dropped=dropped, lr=lr, ent_coef=ent_coef,
                       wait_s=round(t_wait, 2), update_s=round(t_upd, 2),
                       lag_mean=float(lags.mean()), lag_p50=float(np.percentile(lags, 50)),
                       lag_p95=float(np.percentile(lags, 95)), lag_max=int(lags.max()),
                       elapsed_min=round((time.time() - t0) / 60, 2),
                       rounds_per_game=gstats["game_len"] / max(gstats["games"], 1),
                       adv_raw_std=float(cat["adv"].std()), league_hardest=league_view)
            log_f.write(json.dumps(rec) + "\n")
            log_f.flush()
            print(f"[{rec['elapsed_min']:7.1f}m] upd {upd} v{version.value} games {total_games} "
                  f"samples {total_samples} pg {rec['pg']:.4f} vf {rec['vf']:.4f} ent {rec['ent']:.3f} "
                  f"kl {rec['kl']:.4f} clip {rec['clipfrac']:.3f} lag {rec['lag_mean']:.2f}/p95 {rec['lag_p95']:.0f} "
                  f"drop {dropped} wait {t_wait:.1f}s upd {t_upd:.1f}s",
                  flush=True)
            if upd % cfg.checkpoint_every == 0:
                save(model, os.path.join(run_dir, "latest.pt"), version=version.value)
            if upd % cfg.snapshot_every == 0:
                save(model, os.path.join(pool_dir, f"v{version.value:06d}.pt"), version=version.value)
    finally:
        save(model, os.path.join(run_dir, "latest.pt"), version=version.value)
        stop.set()
        # drain so workers blocked on put() can exit
        try:
            while True:
                data_q.get_nowait()
        except queue.Empty:
            pass
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()


def main():
    ap = argparse.ArgumentParser()
    for f, v in asdict(Config()).items():
        if isinstance(v, bool):
            ap.add_argument(f"--{f}", type=lambda s: s.lower() in ("1", "true", "yes"), default=v)
        elif isinstance(v, tuple):
            ap.add_argument(f"--{f}", type=lambda s: tuple(int(x) for x in s.split(",")), default=v)
        else:
            ap.add_argument(f"--{f}", type=type(v), default=v)
    cfg = Config(**vars(ap.parse_args()))
    train(cfg)


if __name__ == "__main__":
    main()
