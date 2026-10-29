"""Carry a network trained on the classic Flip 7 rules over to Bust or Bank.

The classic networks (up to v6, 595 inputs and 140 actions) saw a smaller deck: numbers 0..13 with the
Unlucky 7 and Lucky 13, six modifiers and five actions. ``from_classic`` moves every input and action
weight to the feature of the same meaning in the current layout (``encoding.FEATURES`` /
``encoding.ACTIONS``): the Unlucky 7 to the Unlucky Frozen 7, the Lucky 13 to the Lucky 14, and so on.
The plain 14 starts as a copy of the 13; the other new inputs and actions (keepers, the new actions and
decisions, Bounty/Dare/Spite counters) start at zero, so the network plays the old cards as before and
learns the new ones in training.
"""
from __future__ import annotations

import numpy as np

from . import encoding
from .cards import FLIP4, JOM, MODIFIER_IDS, U7, L14

CLASSIC_ACTIONS = 140
LEGACY_OBS_DIM = 372   # v1/v2 networks: the classic layout without the pending-resolution block
CLASSIC_OBS_DIM = 595

# classic card id -> current card id
CARD = {**{c: c for c in range(14)}, 14: U7, 15: L14,
        **{16 + i: m for i, m in enumerate(MODIFIER_IDS)},
        22: JOM, 23: FLIP4, 24: 27, 25: 28, 26: 29}
_LINE, _ALL = range(22), range(27)


def classic_features():
    """Names of the classic network's 595 inputs, in order, in the current layout's terms."""
    f = [("nplayers", n) for n in range(2, 7)] + [("brutal",)] + [("kind", k) for k in range(8)]
    f += [("card", c) for c in (JOM, FLIP4) + MODIFIER_IDS]
    f += [("swap_slot", s) for s in range(6)] + [("swap_card", CARD[c]) for c in _LINE]
    f += [("deck", CARD[c]) for c in _ALL] + [("decksize",)] + [("disc", CARD[c]) for c in _ALL] + [("discsize",)]
    f += [("round",), ("gap",)]
    fields = (["present"] + [("status", s) for s in range(3)] + [("line", CARD[c]) for c in _LINE]
              + ["count", "sum", "proj", "total", "totproj", "reach", "margin", "bust", "new", "ev", "f7",
                 "late", "dealer", "turnpos", "forced", "queued", "jom", "todeal"])
    for s in range(6):
        f += [("p", s) + (x if isinstance(x, tuple) else (x,)) for x in fields]
    f += [("turns", s) for s in range(6)] + [("deal",)]
    task = ([("type", t) for t in range(3)] + [("owner", s) for s in range(6)] + ["draws"]
            + [("queue", j, CARD[16 + q]) for j in range(4) for q in range(11)])
    for k in range(4):
        f += [("task", k) + (x if isinstance(x, tuple) else (x,)) for x in task]
    assert len(f) == CLASSIC_OBS_DIM
    return f


def classic_actions():
    return [("stay",), ("hit",)] + [("player", s) for s in range(6)] + [("card", s, CARD[c]) for s in range(6) for c in _LINE]


def _copy_14(names):
    """Where a feature mentions the 13, the plain 14 (no classic equivalent) starts with the same weights."""
    out = {}
    for i, name in enumerate(names):
        if 13 in name[1:] and name[0] in ("deck", "disc", "swap_card", "p", "card"):
            twin = tuple(14 if x == 13 and j > 0 else x for j, x in enumerate(name))
            out[twin] = i
    return out


def _move(w, old_names, new_names, axis):
    idx = {name: i for i, name in enumerate(new_names)}
    shape = list(w.shape)
    shape[axis] = len(new_names)
    out = np.zeros(shape, w.dtype)
    sources = {name: i for i, name in enumerate(old_names)}
    sources.update({k: v for k, v in _copy_14(old_names).items() if k not in sources})
    for name, i in sources.items():
        j = idx.get(name)
        if j is not None:
            if axis == 1:
                out[:, j] = w[:, i]
            else:
                out[j] = w[i]
    return out


def pad_inputs(state_dict):
    """A Bust or Bank network from before newer inputs were added at the end of the layout (815 inputs
    before the Special Delivery ones): the new inputs start at zero, so it plays exactly as before."""
    sd = {k: np.asarray(v.detach().cpu().numpy() if hasattr(v, "detach") else v) for k, v in state_dict.items()}
    for key in ("trunk.0.weight", "v_trunk.0.weight"):
        if key in sd and sd[key].shape[1] < encoding.OBS_DIM:
            w = sd[key]
            sd[key] = np.concatenate([w, np.zeros((w.shape[0], encoding.OBS_DIM - w.shape[1]), w.dtype)], 1)
    return sd


def from_classic(state_dict):
    """A classic network's state dict (numpy or torch arrays) for the current layout, as numpy arrays."""
    sd = {k: np.asarray(v.detach().cpu().numpy() if hasattr(v, "detach") else v) for k, v in state_dict.items()}
    old_in, old_out = classic_features(), classic_actions()
    for key in ("trunk.0.weight", "v_trunk.0.weight"):
        if key in sd:
            w = sd[key]
            if w.shape[1] == LEGACY_OBS_DIM:  # v1/v2: the pending-resolution inputs came later, at the end
                w = np.concatenate([w, np.zeros((w.shape[0], CLASSIC_OBS_DIM - LEGACY_OBS_DIM), w.dtype)], 1)
            sd[key] = _move(w, old_in, encoding.FEATURES, 1)
    sd["pi.weight"] = _move(sd["pi.weight"], old_out, encoding.ACTIONS, 0)
    sd["pi.bias"] = _move(sd["pi.bias"], old_out, encoding.ACTIONS, 0)
    return sd
