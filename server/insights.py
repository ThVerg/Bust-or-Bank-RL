"""Everything the Insights page shows, gathered from analysis/ (served by the app, written out by the
static build)."""
import json
import os


def load(folder):
    """insights.json (python -m flip7.analyze), plus the optional hand-written findings.json,
    head-to-head matchups.json, calibration.json, conditions.json, exploitability.json and
    tactics.json next to it."""
    path = os.path.join(folder, "insights.json")
    if not os.path.exists(path):
        return {"ready": False}
    with open(path) as f:
        data = {"ready": True, **json.load(f)}
    for name in ("findings", "matchups"):
        path = os.path.join(folder, f"{name}.json")
        if os.path.exists(path):
            with open(path) as f:
                data.update(json.load(f))
    for name in ("calibration", "conditions", "exploitability", "tactics"):  # python -m flip7.<name>
        path = os.path.join(folder, f"{name}.json")
        if os.path.exists(path):
            with open(path) as f:
                data[name] = json.load(f)
    return data
