"""Grow a trained network into a bigger one that computes the same function, as a warm start.

    python -m flip7.grow models/flip7_rl.pt runs/grown.pt --hidden 512 --layers 4 --v_hidden 768 --v_layers 3

Wider layers copy existing units. A copy has the same incoming weights as its original, so the
same activation, and every outgoing weight of the original is split between the two in a random
proportion. The split is drawn per weight, not per unit: then the two units receive different
combinations of the next layer's gradients and drift apart in training (with a per-unit split
Adam would move them in lockstep forever). Extra layers are identity layers appended to a trunk:
ReLU outputs are never negative, so ReLU(I h) = h. The grown network's outputs match the
original's to float precision (``python -m flip7.grow`` checks this before saving).
"""
import argparse

import torch

from .encoding import OBS_DIM
from .engine import N_ACTIONS
from .model import Net, load, save


def _split(w, g, gen):
    """Columns of ``w`` (out x old_in) for the widened input ``g`` (new unit -> original unit),
    each original column split over its copies in random proportions per row."""
    r = torch.rand(w.shape[0], len(g), generator=gen) + 0.5
    total = torch.zeros(w.shape[0], w.shape[1]).index_add_(1, g, r)
    return w[:, g] * r / total[:, g]


def _grow_trunk(sd, prefix, head, layers, width, gen):
    """Widen trunk ``prefix``.0..n-1 to ``width`` and append identity layers up to ``layers``;
    ``head`` is the layer that reads the trunk's output. Returns the new state dict entries."""
    out, g = {}, None
    old = sum(1 for k in sd if k.startswith(prefix + ".") and k.endswith(".weight"))
    if layers < old:
        raise ValueError(f"can't remove layers from {prefix} ({old} -> {layers})")
    for i in range(old):
        w, b = sd[f"{prefix}.{i}.weight"], sd[f"{prefix}.{i}.bias"]
        if width < w.shape[0]:
            raise ValueError(f"can't narrow {prefix} ({w.shape[0]} -> {width})")
        if g is not None:
            w = _split(w, g, gen)
        n = w.shape[0]
        g = torch.cat([torch.arange(n), torch.randint(0, n, (width - n,), generator=gen)])
        out[f"{prefix}.{i}.weight"], out[f"{prefix}.{i}.bias"] = w[g].clone(), b[g].clone()
    for i in range(old, layers):
        out[f"{prefix}.{i}.weight"], out[f"{prefix}.{i}.bias"] = torch.eye(width), torch.zeros(width)
    out[f"{head}.weight"], out[f"{head}.bias"] = _split(sd[f"{head}.weight"], g, gen), sd[f"{head}.bias"].clone()
    return out


def grow(model, hidden, layers, v_hidden, v_layers, seed=0):
    """A bigger Net computing the same function as ``model`` (which must have a separate value trunk)."""
    if not model.config["v_hidden"]:
        raise ValueError("growing needs a network with its own value trunk")
    gen = torch.Generator().manual_seed(seed)
    sd = model.state_dict()
    big = Net(hidden, layers, v_hidden, v_layers, obs_dim=model.config["obs_dim"])
    big.load_state_dict({**_grow_trunk(sd, "trunk", "pi", layers, hidden, gen),
                         **_grow_trunk(sd, "v_trunk", "v", v_layers, v_hidden, gen)})
    return big.eval()


def max_difference(a, b, n=512, seed=0):
    """Largest difference in action probabilities and win probabilities on random observations."""
    gen = torch.Generator().manual_seed(seed)
    obs = torch.rand(n, OBS_DIM, generator=gen) * 2
    mask = torch.rand(n, N_ACTIONS, generator=gen) < 0.3
    mask[:, 0] = True
    players = torch.randint(2, 7, (n,), generator=gen)
    with torch.no_grad():
        (la, va), (lb, vb) = a(obs, mask, players), b(obs, mask, players)
    return max((la.softmax(1) - lb.softmax(1)).abs().max().item(), (va.softmax(1) - vb.softmax(1)).abs().max().item())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("out")
    ap.add_argument("--hidden", type=int, default=512)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--v_hidden", type=int, default=768)
    ap.add_argument("--v_layers", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    model, ckpt = load(a.checkpoint)
    big = grow(model, a.hidden, a.layers, a.v_hidden, a.v_layers, a.seed)
    diff = max_difference(model, big)
    if diff > 1e-4:
        raise SystemExit(f"grown network differs from the original by {diff:.2e}")
    save(big, a.out, version=ckpt.get("version"), grown_from=a.checkpoint)
    n0, n1 = (sum(p.numel() for p in m.parameters()) for m in (model, big))
    print(f"{a.checkpoint} ({n0 / 1e6:.2f}M parameters) -> {a.out} ({n1 / 1e6:.2f}M), "
          f"largest probability difference {diff:.1e}")


if __name__ == "__main__":
    main()
