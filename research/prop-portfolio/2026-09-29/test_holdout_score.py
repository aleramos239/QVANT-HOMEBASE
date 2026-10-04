"""holdout_score / build_holdout_manifest guards (no 2025+ data is read)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holdout_score as HS   # noqa: E402


def test_code_hashes_cover_scoring_code():
    h = HS.code_hashes()
    assert set(h) == {"evalcore.py", "funded.py", "portfolio.py", "holdout_score.py"} and all(len(v) == 64 for v in h.values())


def test_verify_frozen_flags_changed_code():
    man = {"code_sha256": {f: "0" * 64 for f in HS.CODE_FILES}, "inputs_sha256": {}}
    bad = HS.verify_frozen(man)
    assert bad and (any("changed since the freeze" in b for b in bad) or any("no holdout_manifest.sha256" in b for b in bad))


def test_parse_rules():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_holdout_manifest as B
    assert B.parse_rules("m40 L750 K1500 S- T- TT") == (40, {"day_lock": 750, "day_take": 1500, "day_stop": 0, "max_day_tr": 0, "target_take": 1})
    assert B.parse_rules("m80 L- K- S2000 T1 tt-")[1]["target_take"] == 0
