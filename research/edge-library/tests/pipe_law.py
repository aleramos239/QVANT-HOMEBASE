"""pipe_law.py -- the pipeline's rules file AS IT WAS before the owner's word of 2026-10-10 (pipeline.json gates.mode "law": every line asks;
prop.eval 50 %; no fees). A test module that was written for those numbers says `PIPE_GATES = "law"` at module level: conftest.py then points
blueprint.pipe_rules.FILE at this file for each of its tests, so law mode stays verified while the shipped default is mode "prop"."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blueprint import rules as R  # noqa: E402

_made: list = []


def file() -> Path:
    """The law-mode copy of templates/pipeline.json (made once, in a temp folder that lives as long as the test run)."""
    if not _made:
        d = json.loads((R.T / "pipeline.json").read_text(encoding="utf-8"))
        d.pop("gates", None)
        d["prop"]["eval"] = 0.5
        d["prop"].pop("fees", None)
        tmp = Path(tempfile.mkdtemp(prefix="pipe_law_"))
        _made.append(tmp / "pipeline.json")
        _made[0].write_text(json.dumps(d), encoding="utf-8")
    return _made[0]
