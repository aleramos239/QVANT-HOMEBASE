"""hmwf (the owner, 2026-10-20): every box of an idea's hm40 heat map run FIXED on the in-sample months of the 3:1 blocks, and the
in-sample table he picks from. The calendar is synthetic (3 in-sample days + 1 test-month day) and the engine is a fake that makes one
trade per instance and day: no tape is opened. Every store and ledger row goes to tmp_path."""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

import judge as J
import l2sim as S
import library as LB

W = Path(__file__).resolve().parents[2]
if str(W) not in sys.path:
    sys.path.insert(0, str(W))
from blueprint import api  # noqa: E402
from blueprint import hmwf as H  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import wfmonths as WM  # noqa: E402

CAL = ["2021-10-01", "2021-11-01", "2021-12-01", "2022-01-03"]      # Oct-Dec 2021 in-sample, Jan 2022 the test month
IS_DAYS = CAL[:3]
SPEC = {"name": "hwt_sweep", "reason": "a swept candle extreme that fails to hold tends to reverse back into the range",
        "family": "candle_sweep", "markets": ["NQ"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {"ema1h": [0, 50, 100]},
        "exits": "standard"}
COLUMNS = ["n", "box", "settings", "win_rate", "breakeven", "wr_minus_be", "trades", "per_week", "avg_trade", "avg_r", "net", "pf", "sharpe",
           "max_dd", "months_pos", "months_wr60", "worst_month_wr", "long_net", "short_net", "worse_fills_net", "beats_random", "seen"]


def _fake_run_many(calls):
    def run_many(specs, *a, days=None, root="NQ", allow_holdout=False, **kw):
        calls.append({"days": list(days or []), "allow_holdout": allow_holdout, "args": a, "kw": sorted(kw)})
        out = []
        for cls, p in specs:
            trades = []
            for d in days:
                if p.get("sess") != "nyam":
                    continue
                h = int(hashlib.sha256(f"{cls.__name__}|{sorted(p.items())}|{d}|{kw.get('slip_ticks')}".encode()).hexdigest()[:8], 16)
                ent = S.et_ns(dt.date.fromisoformat(d), "10:00") // 1_000_000
                trades.append({"date": d, "entry_ms": ent, "exit_ms": ent + 60_000, "net": float(h % 700 - 300), "mae_usd": 50.0,
                               "side": "long" if h % 2 else "short", "exit_reason": "tp", "entry_price": 100.0, "sl": 90.0})
            out.append({"trades": trades, "skipped": [], "no_trade": [], "sessions": len(days), "used": len(days), "skipped_by_error": 0,
                        "unrealistic_winners": 0, "both_sides_sessions": 0, "elapsed_s": 0.0,
                        "meta": {"inputs": dict(p), "root": root, "engine": "fake",
                                 "range": {"start": min(days), "end": max(days), "holdout": True, "period": allow_holdout}}})
        return out
    return run_many


@pytest.fixture
def wf(monkeypatch, tmp_path):
    monkeypatch.setattr(WM, "_sessions", lambda root, today: (tuple(CAL), "2022-02-01"))
    WM._sets.cache_clear()
    calls = []
    monkeypatch.setattr(S, "run_many", _fake_run_many(calls))
    monkeypatch.setattr(H, "RUNS", tmp_path / "runs_wf")
    monkeypatch.setattr(RUN, "RUNS", tmp_path / "runs_bp")
    monkeypatch.setattr(RUN, "clock", lambda: dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET))     # a Saturday: no start window
    monkeypatch.setenv("HOMEBASE_IDEAS_ROOT", str(tmp_path / "ideas"))
    yield {"calls": calls, "ledger": tmp_path / "ledger.csv", "tmp": tmp_path}
    WM._sets.cache_clear()


def test_run_is_reads_only_is_days(wf):
    assert WM.is_days("NQ") == IS_DAYS
    r = H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    assert r["boxes"] == 120 and Path(r["store"]) == H.RUNS / "hwt_sweep-NQ-tf15" / "is"
    assert wf["calls"] and all(c["allow_holdout"] == S.ALLOW_WF_IS and "period" not in c["kw"] for c in wf["calls"])
    assert sorted({d for c in wf["calls"] for d in c["days"]}) == IS_DAYS
    u = LB.load_unit("is", H.RUNS / "hwt_sweep-NQ-tf15")
    assert u["meta"]["period"] == S.ALLOW_WF_IS and u["meta"]["days"] == IS_DAYS and len(u["meta"]["cells"]) == 120
    months = {dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in u["date"]}
    assert months and months <= {"2021-10", "2021-11", "2021-12"}             # never a trade of the test month
    for sub in (H.RUNS / "hwt_sweep-NQ-tf15").iterdir():                       # ... in no store of the idea, worse fills included
        if (sub / "cells.npz").exists():
            x = LB.load_unit(sub.name, sub.parent)
            assert all(dt.date.fromordinal(int(d)).strftime("%Y-%m") != "2022-01" for d in x["date"])
    assert RUN.guard_wf(u["meta"], "is")["period"] == S.ALLOW_WF_IS
    n = len(wf["calls"])
    assert H.run_is(SPEC, workers=1, ledger=wf["ledger"])["boxes"] == 120 and len(wf["calls"]) == n      # a rerun does no work
    with pytest.raises(J.Refuse, match="other inputs"):                       # a changed idea under the same name is refused
        H.run_is({**SPEC, "params": {"ema1h": [0, 50]}}, workers=1, ledger=wf["ledger"])


def test_guard_wf_refuses_a_store_with_a_test_month_day(wf):
    with pytest.raises(J.Refuse, match="in-sample"):
        RUN.guard_wf({"period": S.ALLOW_WF_IS, "root": "NQ", "days": IS_DAYS + ["2022-01-03"]}, "x")
    with pytest.raises(J.Refuse, match="in-sample"):
        RUN.guard_wf({"period": "bp_build", "root": "NQ", "days": IS_DAYS}, "x")


def test_run_is_refuses_level_2(wf):
    with pytest.raises(J.Refuse, match="Level 2 is not open on the 3:1 months yet"):
        H.run_is({**SPEC, "filters": [{"block": "book", "side": "agree"}]}, workers=1, ledger=wf["ledger"])
    assert not wf["calls"]


def test_is_table_columns_and_sort(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    rows = H.is_table("hwt_sweep")
    assert len(rows) == 120 and all(list(r) == COLUMNS for r in rows)
    assert [r["n"] for r in rows] == list(range(1, 121))
    wr = [r["win_rate"] for r in rows]
    assert wr == sorted(wr, reverse=True)
    r = next(x for x in rows if x["box"] == "ema1h50_own1p5-r0p75")
    assert r["settings"] == {"ema1h": 50, "stop_mode": "own", "stop_val": 1.5, "tgt_r": 0.75} and r["trades"] == 3
    assert r["worse_fills_net"] is not None and isinstance(r["beats_random"], float) and 0 <= r["beats_random"] <= 1
    assert r["seen"] is None
    assert H.is_table("hwt_sweep-NQ-tf15") == rows                            # the store's name reads the same table


def test_breakeven_formula():
    net = np.array([300.0, -100.0, -100.0, 300.0])
    d = [dt.date(2021, 10, k).toordinal() for k in (1, 4, 5, 6)]
    x = {"date": np.array(d), "entry_ms": np.zeros(4, np.int64), "dur_s": np.zeros(4, np.int32), "net": net, "mae": np.zeros(4),
         "side": np.array([1, -1, 1, -1]), "sess": np.zeros(4, np.int8), "reason": np.zeros(4, np.int8), "risk": np.full(4, np.nan)}
    m = H.numbers(x, ["2021-10-01", "2021-10-04", "2021-10-05", "2021-10-06", "2021-10-07"])
    assert m["breakeven"] == pytest.approx(0.25) and m["win_rate"] == 0.5 and m["wr_minus_be"] == pytest.approx(0.25)
    assert m["long_net"] == 200.0 and m["short_net"] == 200.0 and m["avg_r"] == pytest.approx(1.0) and m["per_week"] == pytest.approx(4.0)


def test_block_rows_have_no_oos(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    rows = H.block_rows("hwt_sweep", "ema1h0_atr1-r1")
    assert rows and list(rows[0]) == ["i", "is", "is_trades", "is_win_rate", "is_net"]
    assert rows[0]["i"] == 0 and rows[0]["is"] == ["2021-10", "2021-11", "2021-12"] and rows[0]["is_trades"] == 3
    assert not any("oos" in k for r in rows for k in r)


def test_seen_label(wf, monkeypatch):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    (RUN.RUNS / "hwt_sweep-NQ-tf15").mkdir(parents=True)                      # tuned on the build days ...
    store = api.ideastore()
    monkeypatch.setattr(store, "_now", lambda: "2026-10-18T15:00:00+00:00")
    store.log_read("hwt_sweep", version=1, lock="abc", rng={"start": "2025-07-01", "end": "2025-09-30"}, state="judged")      # ... and read once
    rows = H.is_table("hwt_sweep")
    assert {r["seen"] for r in rows} == {"build days 2021-09..2025-06 tuned; test days read 2026-10-18"}
