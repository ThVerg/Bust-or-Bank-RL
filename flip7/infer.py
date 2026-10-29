"""Running the network with numpy alone, and the neural bot that plays with it.

The bots only need ``model.predict(obs, mask, n_players)``: numpy arrays in, (masked policy logits
[B, N_ACTIONS], value logits [B, 6]) out. The torch ``Net`` (``flip7.model``) has it for training
and the server; ``NumpyNet`` has it with no torch at all, for the browser build (``web/``), which
loads the same weights exported as ``.npz``:

    python -m flip7.infer models/flip7_rl.pt out/flip7_rl.npz
"""
from __future__ import annotations

import json

import numpy as np

from .encoding import encode, rel_to_abs
from .engine import MAX_PLAYERS

NEG = -1e9


def softmax(x, axis=-1):
    z = np.exp(x - x.max(axis=axis, keepdims=True))
    return z / z.sum(axis=axis, keepdims=True)


class NumpyNet:
    """The forward pass of ``flip7.model.Net`` from its state dict (arrays keyed like torch's)."""

    def __init__(self, params, config):
        self.config = dict(config)
        lin = lambda key: (np.ascontiguousarray(params[f"{key}.weight"].T, np.float32), params[f"{key}.bias"].astype(np.float32))
        stack = lambda prefix: [lin(f"{prefix}.{i}") for i in range(len(params)) if f"{prefix}.{i}.weight" in params]
        self.trunk = stack("trunk")
        self.pi = lin("pi")
        self.v_trunk = stack("v_trunk") or None
        self.v = lin("v")

    @staticmethod
    def _run(layers, x):
        for w, b in layers:
            x = np.maximum(x @ w + b, 0)
        return x

    def predict(self, obs, mask, n_players):
        x = self._run(self.trunk, obs)
        logits = np.where(mask, x @ self.pi[0] + self.pi[1], np.float32(NEG))
        xv = self._run(self.v_trunk, obs) if self.v_trunk is not None else x
        v_logits = xv @ self.v[0] + self.v[1]
        v_logits[np.arange(MAX_PLAYERS)[None, :] >= np.asarray(n_players)[:, None]] = NEG
        return logits, v_logits


def save_npz(params, config, path, **meta):
    """Weights (numpy arrays keyed like the torch state dict) plus JSON metadata (title, blurb...)."""
    np.savez(path, **params, __meta__=np.array(json.dumps({"config": config, **meta})))


def load_npz(path):
    """(NumpyNet, metadata) from ``save_npz``."""
    with np.load(path) as f:
        meta = json.loads(str(f["__meta__"]))
        params = {k: f[k] for k in f.files if k != "__meta__"}
    return NumpyNet(params, meta.pop("config")), meta


class NeuralBot:
    """Plays with a trained network. ``temperature=0`` is greedy (strongest)."""

    def __init__(self, model, temperature=0.0, name="RL", seed=None):
        self.model = model
        self.temperature = temperature
        self.name = name
        self.rng = np.random.default_rng(seed)

    def evaluate(self, game):
        """(probabilities over legal absolute actions, win prob per absolute seat, raw logits)."""
        obs, mask, me = encode(game)
        n = game.n
        logits, v_logits = self.model.predict(obs[None], mask[None], np.array([n]))
        probs = softmax(logits[0])
        win = softmax(v_logits[0])
        legal = np.flatnonzero(mask)
        action_probs = {rel_to_abs(int(a), me, n): float(probs[a]) for a in legal}
        seat_win = [0.0] * n
        for s in range(n):
            seat_win[(me + s) % n] = float(win[s])
        return action_probs, seat_win, logits[0]

    def act(self, game):
        probs, _, logits = self.evaluate(game)
        acts = list(probs)
        if self.temperature <= 0:
            return max(acts, key=lambda a: probs[a])
        p = np.array([probs[a] for a in acts]) ** (1.0 / self.temperature)
        return acts[self.rng.choice(len(acts), p=p / p.sum())]


def export(checkpoint, out):
    """A torch checkpoint as an ``.npz`` (needs torch to read the checkpoint, not to use the result)."""
    from .model import load

    model, ckpt = load(checkpoint)
    params = {k: v.numpy() for k, v in model.state_dict().items()}
    meta = {k: ckpt[k] for k in ("title", "blurb", "version") if ckpt.get(k) is not None}
    save_npz(params, model.config, out, **meta)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("out")
    a = ap.parse_args()
    export(a.checkpoint, a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
