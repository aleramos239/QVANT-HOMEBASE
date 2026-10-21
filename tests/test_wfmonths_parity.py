"""The Lab's 3:1 block months (homebase/backtest/wfmonths.py) == the research layout (research/edge-library/blueprint/wfmonths.py)."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from homebase.backtest import wfmonths
from homebase.backtest.tape import ARCHIVE, TapeStore

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "research" / "edge-library"
PY = next((p for p in (REPO / ".venv-research/bin/python", REPO.parents[1] / ".venv-research/bin/python") if p.exists()), REPO / "none")


def _manifests(base: Path, root: str, days, complete=True):
    for d in days:
        p = base / root / str(d.year) / f"{d.isoformat()}_X.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"ticks": 10, "complete": complete}))


def _weekdays(a: dt.date, b: dt.date):
    return [a + dt.timedelta(n) for n in range((b - a).days + 1) if (a + dt.timedelta(n)).weekday() < 5]


def test_blocks_start_at_the_first_whole_month_and_skip_an_incomplete_session(tmp_path):
    arch = tmp_path / "ticks"
    _manifests(arch, "XX", _weekdays(dt.date(2021, 11, 3), dt.date(2022, 12, 30)) + _weekdays(dt.date(2025, 7, 1), dt.date(2025, 9, 30)))
    _manifests(arch, "XX", [dt.date(2025, 8, 12)], complete=False)
    store = TapeStore(archive=arch, cache=tmp_path / "cache")
    cal = wfmonths.calendar("XX", store)
    assert max(cal) == dt.date(2025, 8, 29)                       # Aug counts (the data runs past it), Sep does not
    assert dt.date(2025, 8, 12) not in cal and wfmonths.skipped("XX", store) == frozenset({dt.date(2025, 8, 12)})
    bl = wfmonths.blocks("XX", store)                                               # 2021-11-03 is Nov's 3rd weekday: Dec first
    assert [(b["is"], b["oos"]) for b in bl] == [(["2021-12", "2022-01", "2022-02"], "2022-03"),
                                                 (["2022-04", "2022-05", "2022-06"], "2022-07"),
                                                 (["2022-08", "2022-09", "2022-10"], "2022-11")]   # Dec 2022 + Jul-Aug 2025: a part-block


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_wfmonths_parity(root):
    if not (PY.exists() and (ARCHIVE / root).exists()):
        pytest.skip("needs the research Python and the tick archive")
    code = ("import sys, json; sys.path[:0] = ['engine', '.']\n"
            f"from blueprint import wfmonths as W\nprint(json.dumps(W.blocks({root!r})))")
    research = json.loads(subprocess.run([str(PY), "-c", code], cwd=RESEARCH, capture_output=True, text=True, check=True).stdout)
    mine = wfmonths.blocks(root)
    assert mine == research and len(mine) >= 15                   # the gappy Sep 2026 days are skipped, not a stop (2026-10-21)
    assert (mine[0]["is"], mine[0]["oos"]) == (["2021-10", "2021-11", "2021-12"], "2022-01")
