import os
import sys

import torch

from flip7 import promote


def test_promote_archives_the_old_bot_and_keeps_its_title(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    torch.save({"version": 7, "title": "Bust or Bank RL", "blurb": "old blurb", "config": {}}, tmp_path / "models" / "flip7_rl.pt")
    run = tmp_path / "runs" / "v9"
    run.mkdir(parents=True)
    torch.save({"version": 12, "config": {}}, run / "latest.pt")
    monkeypatch.setattr(promote, "ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["promote", str(run / "latest.pt"), "--server", ""])
    promote.main()
    assert os.path.exists(tmp_path / "models" / "archive" / "flip7_rl_prev_ver7.pt")
    new = torch.load(tmp_path / "models" / "flip7_rl.pt", weights_only=False)
    assert new["version"] == 12 and new["title"] == "Bust or Bank RL" and new["blurb"] == "old blurb"
    assert new["source"]["path"] == os.path.join("runs", "v9", "latest.pt") and len(new["source"]["sha256"]) == 64
    monkeypatch.setattr(sys, "argv", ["promote", str(run / "latest.pt"), "--server", ""])
    promote.main()  # promoting again archives the v9 copy under its run name
    assert os.path.exists(tmp_path / "models" / "archive" / "flip7_rl_v9_ver12.pt")
