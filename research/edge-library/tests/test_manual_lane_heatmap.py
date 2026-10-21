"""LOCK of the manual lane's heat map page (manual_lane/heatmap.py; the owner, 2026-10-20: the default table is hm40, run on the 3:1
in-sample months). An hm40 in-sample store is drawn as what it is: its own months, the own stop named, no "no target" column. An old
store of the build days keeps its old label. Hand-made stores in tmp_path, no tape.

  pytest tests/test_manual_lane_heatmap.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE / "engine"), str(HERE / "manual_lane")]

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import heatmap as HM  # noqa: E402


def _store(home: Path, period: str, days: list, exits: list) -> Path:
    cells = [{"id": S.cell_id(x), "vi": 0, "xi": k, "variant": {}, "exit": x} for k, x in enumerate(exits)]
    res = []
    for k, _ in enumerate(cells):
        trades = [{"date": d, "entry_ms": S.et_ns(dt.date.fromisoformat(d), "10:00") // 1_000_000, "exit_ms": 0, "net": float(50 - 40 * (k % 3)),
                   "mae_usd": 10.0, "side": "long", "exit_reason": "tp", "entry_price": 100.0, "sl": 90.0} for d in days]
        res.append({"trades": trades, "meta": {"inputs": {}, "root": "NQ", "engine": "fake", "range": {"start": days[0], "end": days[-1]}},
                    "sessions": len(days), "used": len(days), "skipped": [], "elapsed_s": 0.0})
    LB.write_unit("is", {"idea": "my_idea", "period": period, "days": days}, cells, res, home)
    return home / "is"


def test_manual_lane_default_exits_hm40(tmp_path):
    hm40 = RUN._blocks().menu_hm40("NQ", True)
    assert len(hm40) == 40
    p = _store(tmp_path / "my_idea-NQ-tf5", S.ALLOW_WF_IS, ["2021-10-01", "2021-11-01", "2021-12-01"], hm40)
    out = tmp_path / "heat.html"
    assert HM.main([str(out), str(p)]) == 0
    page = out.read_text()
    assert "3:1 in-sample months 2021-10 .. 2021-12" in page and "test months not read" in page and "build days" not in page
    assert "0.5x own stop" in page and "2x ATR" in page and "no target" not in page
    old = _store(tmp_path / "old-NQ-tf5", RUN.PERIOD, ["2022-03-15"], [{"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 0.0}])
    assert HM.main([str(out), str(old)]) == 0
    assert "build days 2021-09-22 to 2025-06-30" in out.read_text()        # an old store keeps its old label
