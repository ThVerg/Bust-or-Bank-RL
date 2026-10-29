"""Distill verified search improvements into the policy network.

    python -m flip7.distill collect --model models/flip7_rl.pt --teacher rollout64 --positions 20000 --out runs/distill.npz
    python -m flip7.distill collect --model models/flip7_rl.pt --teacher boss --kinds steal,swap1,swap2,discard,flip7 ...
    python -m flip7.distill train --model models/flip7_rl.pt --data runs/distill.npz --out runs/distilled.pt
    python -m flip7.benchmark --candidate runs/distilled.pt --incumbent models/flip7_rl.pt ...

collect: play games with the network and, at sampled decisions, ask a search teacher: either
a higher-budget one-ply search (``search``, several deck samples per next-card kind) or rollout
search (``rollout64`` etc.). A position counts as an *improvement* only if search's best action
beats the policy's own choice by more than ``--margin`` in estimated win probability, and, with
``--verify`` (the default), does so again in a second, independent search. Picking the best of
several noisy estimates favours lucky ones; the second search is not biased that way, and its gap
is the one recorded. A share of the positions where search agrees with the policy is kept as
anchors. With ``--kinds`` the teacher is only asked about those kinds of decision (the ones where
the tactical positions show it beats the network); other decisions are kept as anchors at the
same rate without asking it, so the policy is held in place there.

train: cross-entropy towards search's choice on improvement positions, plus a KL term keeping
the policy close to its original distribution on anchor positions, so it only moves where search
found something. The value head is left untouched. Promote the result only if the paired
benchmark confirms it.
"""
from __future__ import annotations

import argparse
import copy
import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import torch
import torch.nn.functional as F

from .encoding import abs_to_rel, encode
from .engine import DECISION_NAMES, Game, Rules
from .evaluate import make_bot
from .model import NeuralBot, load, save
from .search import SearchBot


def _collect(args):
    model_path, positions, seed, teacher, samples, margin, verify, p_eval, keep_agree, kinds = args
    torch.set_num_threads(1)
    model = load(model_path)[0]
    policy = NeuralBot(model)
    if teacher == "search":
        search = SearchBot(model, seed=seed, samples_per_kind=samples)
    else:
        search = make_bot(f"{teacher}:{model_path}", seed=seed)
    rng = random.Random(seed)
    obs_l, mask_l, tgt_l, imp_l, gap_l, kind_l = [], [], [], [], [], []
    seen = 0
    while seen < positions:
        n = rng.choice((2, 3, 4, 5, 6))
        g = Game(n, rules=Rules(), rng=random.Random(rng.random()), dealer=rng.randrange(n))
        while not g.over and seen < positions:
            a_pol = policy.act(g)
            if kinds and DECISION_NAMES[g.decision.kind] not in kinds:
                if len(g.legal()) > 1 and rng.random() < p_eval * keep_agree:
                    obs, mask, me = encode(g)
                    obs_l.append(obs)
                    mask_l.append(mask)
                    tgt_l.append(abs_to_rel(a_pol, me, g.n))
                    imp_l.append(False)
                    gap_l.append(0.0)
                    kind_l.append(g.decision.kind)
                    seen += 1
            elif rng.random() < p_eval:
                q = search.evaluate(g)
                a_best = max(q, key=q.get)
                gap = q[a_best] - q[a_pol]
                improvement = a_best != a_pol and gap > margin
                if improvement and verify:
                    q = search.evaluate(g)
                    gap = q[a_best] - q[a_pol]
                    improvement = gap > margin
                if improvement or rng.random() < keep_agree:
                    obs, mask, me = encode(g)
                    obs_l.append(obs)
                    mask_l.append(mask)
                    tgt_l.append(abs_to_rel(a_best if improvement else a_pol, me, g.n))
                    imp_l.append(improvement)
                    gap_l.append(gap)
                    kind_l.append(g.decision.kind)
                    seen += 1
            g.step(a_pol)
    return (np.array(obs_l, np.float32), np.array(mask_l, bool), np.array(tgt_l, np.int64),
            np.array(imp_l, bool), np.array(gap_l, np.float32), np.array(kind_l, np.int8))


def collect(model, positions, out, workers=3, teacher="search", samples=3, margin=0.01, verify=True,
            p_eval=0.25, keep_agree=0.15, seed=0, kinds=()):
    per = -(-positions // workers)
    jobs = [(model, per, seed * 1000 + w, teacher, samples, margin, verify, p_eval, keep_agree, tuple(kinds))
            for w in range(workers)]
    with ProcessPoolExecutor(workers) as ex:
        parts = list(ex.map(_collect, jobs))
    data = {k: np.concatenate([p[i] for p in parts])
            for i, k in enumerate(("obs", "mask", "target", "improvement", "gap", "kind"))}
    np.savez_compressed(out, **data)
    imp = data["improvement"]
    print(f"{len(imp)} positions, {imp.sum()} improvements ({imp.mean():.1%}), "
          f"mean gap on improvements {data['gap'][imp].mean() if imp.any() else 0:.4f}")


def _agreement(model, obs, mask, n_pl, tgt, imp):
    """(share of improvement positions where the policy now picks search's action,
        share of anchor positions where it still picks its original action)."""
    with torch.no_grad():
        pick = model(obs, mask, n_pl)[0].argmax(1)
    hit = pick == tgt
    return float(hit[imp].float().mean()), float(hit[~imp].float().mean())


def train(model_path, data_path, out, epochs=4, lr=1e-4, kl_coef=1.0, batch=1024, holdout=0.1, seed=0):
    model, ckpt = load(model_path)
    ref = copy.deepcopy(model).eval()
    model.train()
    d = np.load(data_path)
    obs = torch.from_numpy(d["obs"])
    mask = torch.from_numpy(d["mask"])
    tgt = torch.from_numpy(d["target"])
    imp = torch.from_numpy(d["improvement"])
    n_pl = obs[:, 0:5].argmax(1) + 2
    # hold out positions to check generalisation: search's moves learned vs original moves kept
    gen = torch.Generator().manual_seed(seed)
    order = torch.randperm(len(tgt), generator=gen)
    n_val = int(holdout * len(tgt))
    val, tr = order[:n_val], order[n_val:]
    vargs = (obs[val], mask[val], n_pl[val], tgt[val], imp[val])
    learned, kept = _agreement(model, *vargs)
    print(f"held out before: search move picked {learned:.3f}, original move kept {kept:.3f}")
    params = list(model.trunk.parameters()) + list(model.pi.parameters())  # value head untouched
    opt = torch.optim.Adam(params, lr=lr)
    with torch.no_grad():
        ref_logp = F.log_softmax(ref(obs, mask, n_pl)[0], 1)
    for ep in range(epochs):
        perm = tr[torch.randperm(len(tr))]
        tot = {"ce": 0.0, "kl": 0.0, "agree": 0.0}
        nb = 0
        for s in range(0, len(perm), batch):
            idx = perm[s:s + batch]
            logp = F.log_softmax(model(obs[idx], mask[idx], n_pl[idx])[0], 1)
            im = imp[idx]
            ce = -logp[im].gather(1, tgt[idx][im][:, None]).mean() if im.any() else logp.sum() * 0
            anchor = ~im
            kl = (ref_logp[idx][anchor].exp() * (ref_logp[idx][anchor] - logp[anchor].clamp(min=-30))).sum(1).mean() if anchor.any() else logp.sum() * 0
            loss = ce + kl_coef * kl
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot["ce"] += ce.item()
            tot["kl"] += kl.item()
            tot["agree"] += (logp.argmax(1) == tgt[idx]).float().mean().item()
            nb += 1
        learned, kept = _agreement(model, *vargs)
        print(f"epoch {ep + 1}: ce {tot['ce'] / nb:.4f} kl {tot['kl'] / nb:.4f} | held out: search move picked "
              f"{learned:.3f}, original move kept {kept:.3f}")
    model.eval()
    save(model, out, version=ckpt.get("version"), distilled_from=model_path)
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--model", required=True)
    c.add_argument("--positions", type=int, default=20000)
    c.add_argument("--out", required=True)
    c.add_argument("--workers", type=int, default=3)
    c.add_argument("--teacher", default="search", help="search | rollout[K][t<temp>] | boss[K], e.g. rollout64")
    c.add_argument("--kinds", default="", help="only ask the teacher about these decisions, e.g. steal,swap1,swap2")
    c.add_argument("--p_eval", type=float, default=0.25, help="share of decisions the teacher is asked about")
    c.add_argument("--keep_agree", type=float, default=0.15, help="share of agreeing positions kept as anchors")
    c.add_argument("--samples", type=int, default=3, help="deck samples per next-card kind (search teacher)")
    c.add_argument("--margin", type=float, default=0.01, help="win-prob gain search must show")
    c.add_argument("--no-verify", dest="verify", action="store_false",
                   help="skip the independent second search on improvements")
    c.add_argument("--seed", type=int, default=0)
    t = sub.add_parser("train")
    t.add_argument("--model", required=True)
    t.add_argument("--data", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--epochs", type=int, default=4)
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--kl_coef", type=float, default=1.0)
    a = ap.parse_args()
    if a.cmd == "collect":
        collect(a.model, a.positions, a.out, a.workers, a.teacher, a.samples, a.margin, a.verify,
                a.p_eval, a.keep_agree, a.seed, [k for k in a.kinds.split(",") if k])
    else:
        train(a.model, a.data, a.out, a.epochs, a.lr, a.kl_coef)


if __name__ == "__main__":
    main()
