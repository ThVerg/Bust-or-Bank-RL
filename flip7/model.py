"""Policy/value network (torch). The bots run it through ``predict``; see ``flip7.infer``."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .encoding import OBS_DIM
from .engine import MAX_PLAYERS, N_ACTIONS
from .infer import NEG, NeuralBot  # noqa: F401  (NeuralBot lives in infer so it runs without torch)


def _mlp(in_dim, width, layers):
    dims = [in_dim] + [width] * layers
    return nn.ModuleList(nn.Linear(a, b) for a, b in zip(dims[:-1], dims[1:]))


def _run(trunk, x):
    for layer in trunk:
        x = F.relu(layer(x))
    return x


class Net(nn.Module):
    """Policy head (masked logits over the flat action space) and value head giving each table
    slot's probability of winning the game (slot 0 = the deciding player). With
    ``v_hidden > 0`` the value head gets its own trunk instead of sharing the policy's."""

    def __init__(self, hidden=256, layers=3, v_hidden=0, v_layers=3, obs_dim=OBS_DIM):
        super().__init__()
        self.trunk = _mlp(obs_dim, hidden, layers)
        self.pi = nn.Linear(hidden, N_ACTIONS)
        self.v_trunk = _mlp(obs_dim, v_hidden, v_layers) if v_hidden else None
        self.v = nn.Linear(v_hidden or hidden, MAX_PLAYERS)
        self.config = {"hidden": hidden, "layers": layers, "v_hidden": v_hidden, "v_layers": v_layers,
                       "obs_dim": obs_dim}

    def forward(self, obs, mask, n_players):
        x = _run(self.trunk, obs)
        logits = self.pi(x).masked_fill(~mask, NEG)
        xv = _run(self.v_trunk, obs) if self.v_trunk is not None else x
        slots = torch.arange(MAX_PLAYERS, device=obs.device)[None, :]
        v_logits = self.v(xv).masked_fill(slots >= n_players[:, None], NEG)
        return logits, v_logits

    @torch.no_grad()
    def predict(self, obs, mask, n_players):
        """``forward`` with numpy arrays in and out: the interface the bots use (see ``flip7.infer``)."""
        logits, v_logits = self(torch.from_numpy(obs), torch.from_numpy(mask), torch.as_tensor(n_players))
        return logits.numpy(), v_logits.numpy()


def n_players_from_obs(obs):
    # one-hot n_players lives in obs[:, 0:5] for n = 2..6
    return obs[:, 0:5].argmax(dim=1) + 2


def save(model, path, **meta):
    torch.save({"state_dict": model.state_dict(), "config": model.config, **meta}, path)


def load(path):
    """Load a checkpoint as a network for the current layout. Classic Flip 7 networks are carried over
    feature by feature, older Bust or Bank ones get the inputs added since (``flip7.remap``)."""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    cfg = dict(ckpt["config"])
    cfg.pop("obs_dim", None)
    sd = ckpt["state_dict"]
    if sd["pi.weight"].shape[0] != N_ACTIONS:
        from .remap import from_classic
        sd = {k: torch.from_numpy(v) for k, v in from_classic(sd).items()}
    elif sd["trunk.0.weight"].shape[1] != OBS_DIM:
        from .remap import pad_inputs
        sd = {k: torch.from_numpy(v) for k, v in pad_inputs(sd).items()}
    model = Net(**cfg)
    model.load_state_dict(sd)
    model.eval()
    return model, ckpt

