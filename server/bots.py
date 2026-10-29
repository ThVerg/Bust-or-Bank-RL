"""Bot registry for the web app."""
from __future__ import annotations

import glob
import os

from flip7.bots import RandomBot, SmartBot, ThresholdBot
from flip7.infer import NeuralBot, load_npz
from flip7.search import BossBot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")


class Registry:
    """Knows every available bot. Neural models are the ``*.pt`` checkpoints in ``models_dir``, or
    ``*.npz`` exports of them (``flip7.infer``), which need no torch: the browser build uses those."""

    def __init__(self, models_dir=MODELS):
        self.models_dir = models_dir
        self.models = {}
        self.reload()

    def reload(self):
        self.models = {}
        for path in sorted(glob.glob(os.path.join(self.models_dir, "*.pt")) + glob.glob(os.path.join(self.models_dir, "*.npz"))):
            key = os.path.splitext(os.path.basename(path))[0]
            try:
                if path.endswith(".npz"):
                    self.models[key] = load_npz(path)
                else:
                    from flip7.model import load  # torch
                    self.models[key] = load(path)
            except Exception as e:  # a half-written file shouldn't take the server down
                print(f"could not load {path}: {e}")

    def catalog(self):
        out = []
        if "flip7_rl" in self.models:
            title = self.models["flip7_rl"][1].get("title", "Bust or Bank RL")
            out.append({"id": "search:flip7_rl", "name": f"{title} + Search", "kind": "neural",
                        "blurb": "The RL network plus a one-move lookahead over every possible next card, and Swaps played "
                                 "out to the end of the round 32 times. The strongest option: the search adds a few points "
                                 "of win rate on top of the plain network."})
        for key, (_, ckpt) in self.models.items():
            out.append({"id": f"nn:{key}", "name": ckpt.get("title", key), "kind": "neural",
                        "blurb": ckpt.get("blurb", "Self-play reinforcement learning bot.")})
        out += [
            {"id": "smart", "name": "SmartBot", "kind": "heuristic",
             "blurb": "Card-counting heuristic: plays like a strong, careful human."},
            {"id": "threshold25", "name": "Steady Eddie", "kind": "heuristic",
             "blurb": "Hits until 25 points, then stays. Gangs up on the leader."},
            {"id": "random", "name": "Chaos Monkey", "kind": "heuristic",
             "blurb": "Every choice is random."},
        ]
        return out

    def default_id(self):
        cat = self.catalog()
        return cat[0]["id"]

    def make(self, bot_id):
        if bot_id.startswith("nn:"):
            model, _ = self.models[bot_id[3:]]
            return NeuralBot(model, temperature=0.0)
        if bot_id.startswith("search:"):
            model, _ = self.models[bot_id[7:]]
            return BossBot(model)
        if bot_id == "smart":
            return SmartBot()
        if bot_id.startswith("threshold"):
            return ThresholdBot(int(bot_id[len("threshold"):]))
        if bot_id == "random":
            return RandomBot()
        raise KeyError(bot_id)

    def name(self, bot_id):
        for b in self.catalog():
            if b["id"] == bot_id:
                return b["name"]
        return bot_id

    def analyst(self):
        """The network used to show win chances and move probabilities."""
        if not self.models:
            return None
        key = "flip7_rl" if "flip7_rl" in self.models else next(iter(self.models))
        return NeuralBot(self.models[key][0])
