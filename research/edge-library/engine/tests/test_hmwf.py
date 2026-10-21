"""hmwf (the owner, 2026-10-20): every box of an idea's hm40 heat map run FIXED on the in-sample months of the 3:1 blocks, and the
in-sample table he picks from. The calendar is synthetic (3 in-sample days + 1 test-month day) and the engine is a fake that makes one
trade per instance and day: no tape is opened. Every store and ledger row goes to tmp_path."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
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
from blueprint import cli as CLI  # noqa: E402
from blueprint import hmwf as H  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import wfmonths as WM  # noqa: E402

CAL = ["2021-10-01", "2021-11-01", "2021-12-01", "2022-01-03"]      # Oct-Dec 2021 in-sample, Jan 2022 the test month
IS_DAYS = CAL[:3]
SPEC = {"name": "hwt_sweep", "reason": "a swept candle extreme that fails to hold tends to reverse back into the range",
        "family": "candle_sweep", "markets": ["NQ"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {"ema1h": [0, 50, 100]},
        "exits": "standard"}
COLUMNS = ["n", "box", "settings", "win_rate", "breakeven", "wr_minus_be", "trades", "per_week", "avg_trade", "avg_r", "net", "pf", "sharpe",
           "max_dd", "months_pos", "months_wr60", "worst_month_wr", "long_net", "short_net", "worse_fills_net", "beats_random", "random_vs", "seen"]


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
    with pytest.raises(J.Refuse, match="no market"):                         # never a fall back to NQ
        RUN.guard_wf({"period": S.ALLOW_WF_IS, "days": IS_DAYS}, "x")


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
    assert r["random_vs"] == "atr1p5-r0p75"                                   # the control cell an own-stop box was compared with
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


# ================================================================ the owner's pick and the out-of-sample read (Task 4)

BOX = "ema1h0_atr1-r1"


def _oos_calls(wf):
    return [c for c in wf["calls"] if c["allow_holdout"] == S.ALLOW_WF_OOS]


def _log():
    return [r for r in api.ideastore().reads() if r.get("kind") == "wf_oos"]


def test_pick_writes_lock_once(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    rows = H.is_table("hwt_sweep")
    with pytest.raises(J.Refuse, match="not a box"):
        H.pick("hwt_sweep", 999)
    assert H.show("hwt_sweep")["lock"] is None
    lock = H.pick("hwt_sweep", 3)
    assert set(lock) == {"box", "settings", "code", "at", "who"} and lock["who"] == "owner"
    assert lock["box"] == rows[2]["box"] and lock["settings"] == rows[2]["settings"] and lock["code"] == RUN.code("candle_sweep")
    assert json.loads((H.RUNS / "hwt_sweep-NQ-tf15" / "lock.json").read_text()) == lock
    assert H.pick("hwt_sweep", rows[2]["box"]) == lock                        # the same box again: the lock on file
    with pytest.raises(J.Refuse, match="new idea name"):
        H.pick("hwt_sweep", rows[3]["box"])
    s = H.show("hwt_sweep")
    assert s["lock"] == lock and s["oos"] is None and s["is"] == rows
    assert not _oos_calls(wf) and not _log()                                  # a pick runs nothing


def test_oos_refuses_without_lock(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    with pytest.raises(J.Refuse, match="picked"):
        H.run_oos("hwt_sweep", BOX, "run it", workers=1, ledger=wf["ledger"])
    assert not _oos_calls(wf) and not _log()


def test_oos_refuses_another_box(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)
    with pytest.raises(J.Refuse, match="picked box"):
        H.run_oos("hwt_sweep", "ema1h50_atr1-r1", "run it", workers=1, ledger=wf["ledger"])
    assert not _oos_calls(wf) and not _log()


def test_oos_refuses_empty_owner_said(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)
    for said in ("", "   ", None):
        with pytest.raises(J.Refuse, match="owner's word"):
            H.run_oos("hwt_sweep", BOX, said, workers=1, ledger=wf["ledger"])
    assert not _oos_calls(wf) and not _log()


def test_oos_claim_written_before_any_day(wf, monkeypatch):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)
    seen = []

    def boom(*a, **kw):
        seen.append(len(_log()))
        raise RuntimeError("engine down")
    monkeypatch.setattr(S, "run_many", boom)
    with pytest.raises(J.Refuse, match="box ema1h0_atr1-r1 of hwt_sweep-NQ-tf15 are used: this read stopped and is not run again") as e:
        H.run_oos("hwt_sweep", BOX, "  run it ", workers=1, ledger=wf["ledger"], who="the owner, in chat")
    assert isinstance(e.value.__cause__, RuntimeError)                        # the crash, chained
    assert seen == [1]                                                        # the claim was on file when the first day was opened
    (line,) = _log()
    assert line["box"] == BOX and line["state"] == "claimed" and line["owner_said"] == "  run it " and line["who"] == "the owner, in chat"
    with pytest.raises(J.Refuse, match="stopped and is not run again"):       # a read that died is over: never run twice
        H.run_oos("hwt_sweep", BOX, "run it", workers=1, ledger=wf["ledger"])
    assert not (H.RUNS / "hwt_sweep-NQ-tf15" / "oos").exists()
    assert H.show("hwt_sweep")["oos"] == {"state": "read used, no record (it stopped)", "claim": line}


def test_oos_refused_by_the_runner_before_the_claim_is_not_used(wf, monkeypatch):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)

    def shut():
        raise J.Refuse("nothing heavy starts now")
    monkeypatch.setattr(RUN, "may_start", shut)
    with pytest.raises(J.Refuse, match="nothing heavy"):
        H.run_oos("hwt_sweep", BOX, "run it", workers=1, ledger=wf["ledger"])
    assert not _log() and not _oos_calls(wf) and H.show("hwt_sweep")["oos"] is None
    monkeypatch.undo()                                                        # (the fixture's patches go too: set them again)
    monkeypatch.setattr(WM, "_sessions", lambda root, today: (tuple(CAL), "2022-02-01"))
    WM._sets.cache_clear()
    monkeypatch.setattr(S, "run_many", _fake_run_many(wf["calls"]))
    monkeypatch.setattr(H, "RUNS", wf["tmp"] / "runs_wf")
    monkeypatch.setattr(RUN, "RUNS", wf["tmp"] / "runs_bp")
    monkeypatch.setattr(RUN, "clock", lambda: dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET))
    monkeypatch.setenv("HOMEBASE_IDEAS_ROOT", str(wf["tmp"] / "ideas"))
    assert H.run_oos("hwt_sweep", BOX, "run it", workers=1, ledger=wf["ledger"])["record"]["trades"] == 1      # later, on his word: it runs


def test_pick_refuses_a_changed_idea(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    f = H.RUNS / "hwt_sweep-NQ-tf15" / "is" / "run.json"
    m = json.loads(f.read_text())
    f.write_text(json.dumps({**m, "variants": m["variants"][:2]}))          # the idea as rebuilt no longer matches the store's fingerprint
    with pytest.raises(J.Refuse, match="not the one its in-sample store was run from"):
        H.pick("hwt_sweep", BOX)
    assert not (H.RUNS / "hwt_sweep-NQ-tf15" / "lock.json").exists()
    assert not [p for p in (H.RUNS / "hwt_sweep-NQ-tf15").iterdir() if "lock.json" in p.name]      # no temp file left


def test_oos_runs_once(wf):
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)
    n = len(wf["calls"])
    r = H.run_oos("hwt_sweep", BOX, "run box 1", workers=1, ledger=wf["ledger"])
    calls = wf["calls"][n:]
    assert calls and all(c["allow_holdout"] == S.ALLOW_WF_OOS and c["days"] == ["2022-01-03"] for c in calls)
    assert list(r["record"]) == COLUMNS and r["record"]["box"] == BOX and r["record"]["trades"] == 1
    assert r["blocks"] == [{"i": 0, "oos": "2022-01", "trades": 1, "win_rate": r["record"]["win_rate"], "net": r["record"]["net"]}]
    u = LB.load_unit("oos", H.RUNS / "hwt_sweep-NQ-tf15")                     # the one picked box, its test month only
    assert [c["id"] for c in u["meta"]["cells"]] == [BOX] and u["meta"]["period"] == S.ALLOW_WF_OOS
    assert {dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in u["date"]} == {"2022-01"}
    (line,) = _log()
    assert line["name"] == "hwt_sweep" and line["box"] == BOX and line["who"] == "owner" and line["store"] == "hwt_sweep-NQ-tf15"
    assert line["owner_said"] == "run box 1"
    assert line["code"] == RUN.code("candle_sweep") and line["range"] == {"start": "2022-01-03", "end": "2022-01-03"}
    with pytest.raises(J.Refuse, match="on file"):
        H.run_oos("hwt_sweep", 1 + [x["box"] for x in H.is_table("hwt_sweep")].index(BOX), "again", workers=1, ledger=wf["ledger"])
    assert len(wf["calls"]) == n + len(calls) and len(_log()) == 1
    assert H.show("hwt_sweep")["oos"] == r
    assert {x["seen"] for x in H.is_table("hwt_sweep")} == {None}             # the 3:1 read is not a read of the old test days


def test_oos_one_month_a_call(wf, monkeypatch):
    cal = ["2021-10-01", "2021-11-01", "2021-12-01", "2022-01-03", "2022-02-01", "2022-03-01", "2022-04-01", "2022-05-02"]
    monkeypatch.setattr(WM, "_sessions", lambda root, today: (tuple(cal), "2022-06-01"))
    WM._sets.cache_clear()
    H.run_is(SPEC, workers=1, ledger=wf["ledger"])
    H.pick("hwt_sweep", BOX)
    n = len(wf["calls"])
    r = H.run_oos("hwt_sweep", BOX, "run it", workers=1, ledger=wf["ledger"])
    calls = wf["calls"][n:]
    assert sorted(d for c in calls for d in c["days"]) == ["2022-01-03", "2022-05-02"]
    assert all(len({d[:7] for d in c["days"]}) == 1 for c in calls)           # the engine's switch: one month a call
    assert [b["oos"] for b in r["blocks"]] == ["2022-01", "2022-05"] and r["record"]["trades"] == 2


def test_cache_builders_open_one_test_month(wf, monkeypatch, tmp_path):
    """The runner's caches (a family's prepare, the minute volume, the 5-minute bars) are built per month span under ALLOW_WF_OOS: one
    test month opens, an in-sample month or two months do not. Synthetic tapes (file names only) and a fake loader: no tape is read."""
    import families.round1 as R1
    for d in ("2021-12-01", "2022-01-03"):
        f = tmp_path / "tape" / "NQ" / d[:4] / d[5:7] / f"{d}.parquet"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
    monkeypatch.setattr(S, "TAPE_DIR", tmp_path / "tape")
    monkeypatch.setattr(S, "HB_TAPE", tmp_path / "hb")
    opened = []

    def load(d, root="NQ", allow_holdout=False, **kw):
        S.check_holdout(d, allow_holdout, root)
        opened.append(str(d))
        return None
    monkeypatch.setattr(S, "load_tape", load)
    blocks, levels = RUN._blocks(), RUN._levels()
    monkeypatch.setattr(blocks, "_mv_path", lambda root: tmp_path / "cache" / f"minvol_{root}.npz")
    monkeypatch.setattr(levels, "_fm_path", lambda root, tf=5: tmp_path / "cache" / f"bars{tf}m_{root}.npz")
    monkeypatch.setattr(R1, "_va_path", lambda root: tmp_path / "cache" / f"va70_{root}.json")
    fam = next(f for f, c in blocks.WRAPPED.items() if getattr(c, "prepare", None) and c.prepare.__func__.__module__ in ("families.round1", "families.vabreak"))
    month = ("2022-01-03", "2022-01-03")
    build = [lambda rg: RUN.prepare_family(fam, "NQ", rg, 1, S.ALLOW_WF_OOS), lambda rg: blocks.build_minvol("NQ", rg, 1, allow_holdout=S.ALLOW_WF_OOS),
             lambda rg: levels.build_bars_cache("NQ", rg, 1, allow_holdout=S.ALLOW_WF_OOS)]
    for fn in build:
        opened.clear()
        fn(month)
        assert opened == ["2022-01-03"]
        for rg in (("2021-12-01", "2021-12-01"), ("2021-12-01", "2022-01-03")):           # an in-sample month / more than the test month
            with pytest.raises(S.HoldoutSealed):
                fn(rg)


# ================================================================ bp.py wf: the blueprint's default route (Task 5)

def _bp(capsys, *argv):
    rc = CLI.main([*argv, "--json"])
    return rc, json.loads(capsys.readouterr().out)


@pytest.fixture
def cli(wf, monkeypatch, tmp_path):
    monkeypatch.setattr(LB, "LEDGER", wf["ledger"])                         # never the real ledger.csv
    f = tmp_path / "spec.json"
    f.write_text(json.dumps(SPEC))
    return f


def test_bp_wf_run_needs_owner_said(cli, capsys, wf):
    for said in ([], ["--owner-said="], ["--owner-said=   "]):
        rc, r = _bp(capsys, "wf", "run", str(cli), *said)
        assert rc == 2 and r["ok"] is False and "owner" in r["error"]
    assert not wf["calls"] and not (H.RUNS / "hwt_sweep-NQ-tf15").exists()


def test_bp_wf_run_show_pick_oos(cli, capsys, wf):
    rc, r = _bp(capsys, "wf", "run", str(cli), "--owner-said=run the heat map", "--workers=1")
    assert rc == 0 and r["command"] == "wf run" and r["name"] == "hwt_sweep" and r["owner_said"] == "run the heat map"
    assert len(r["wf"]["is"]) == 120 and r["wf"]["lock"] is None and r["wf"]["oos"] is None
    assert not _oos_calls(wf) and "pick" in r["next"] and "120 boxes" in r["text"]
    rc, again = _bp(capsys, "wf", "show", "hwt_sweep")
    assert rc == 0 and again["wf"] == r["wf"]
    rc, view = _bp(capsys, "heatmap", "hwt_sweep")                          # the read-only view: the 3:1 in-sample table
    assert rc == 0 and view["wf"]["is"] == r["wf"]["is"]
    rc, no = _bp(capsys, "wf", "oos", "hwt_sweep", BOX, "--owner-said=run it")
    assert rc == 2 and "picked" in no["error"]                                # no pick yet
    rc, r = _bp(capsys, "wf", "pick", "hwt_sweep", BOX)
    assert rc == 0 and r["wf"]["lock"]["box"] == BOX and r["wf"]["oos"] is None and "owner says" in r["next"]
    rc, no = _bp(capsys, "wf", "oos", "hwt_sweep", BOX, "--owner-said=  ")
    assert rc == 2 and "owner" in no["error"]
    assert not _oos_calls(wf) and not _log()                                  # a pick and a refusal run nothing
    rc, r = _bp(capsys, "wf", "oos", "hwt_sweep", BOX, "--owner-said= run box 1", "--workers=1")
    assert rc == 0 and r["wf"]["oos"]["record"]["box"] == BOX and r["owner_said"] == " run box 1"
    (line,) = _log()
    assert line["owner_said"] == " run box 1"                                 # his words, verbatim
    rc, no = _bp(capsys, "wf", "oos", "hwt_sweep", BOX, "--owner-said=again")
    assert rc == 2 and len(_log()) == 1


def test_blueprint_test_refuses_new_idea(wf, capsys):
    IS = api.ideastore()
    IS.create("hwt_new")
    IS.write_card("hwt_new", "# hwt_new -- idea card")
    IS.write_spec("hwt_new", {"name": "hwt_new", "version": 1, "card": {}, "run": {}})
    rc, r = _bp(capsys, "test", "hwt_new", "--confirm")
    assert rc == 2 and "new ideas use the 3:1 walk-forward: bp.py wf (blueprint_wf)" in r["error"]
    assert not IS.reads()


def test_a_card_may_say_hm40():
    from blueprint import rules as R
    assert "hm40" in R.EXIT_KINDS and len(R.exit_cells("hm40", "NQ")) == 40


def test_an_hm40_card_goes_to_the_walk_forward(wf):
    from blueprint import records as REC
    card = {"why": "a swept extreme that fails to hold reverses back into the range.", "loser": "late breakout buyers",
            "home": {"market": "NQ", "session": "nyam", "bar": "15"}, "neighbors": ["NQ nyam 5"], "main_setting": "ema1h", "sides": "both",
            "sides_why": "a sweep fails either way", "loses_when": "a trend day that never comes back"}
    root = wf["tmp"] / "ideas"
    r = REC.card("hwt_card", {"name": "hwt_card", "card": card, "run": {"family": "candle_sweep", "params": {"ema1h": [0, 50, 100]}, "exits": "hm40"}}, root)
    assert r["ok"] and r["plan"]["exits"] == "hm40" and "bp.py wf run hwt_card" in r["next"] and "WHAT A BUILD RUNS" not in r["text"]
    with pytest.raises(J.Refuse, match="3:1 walk-forward"):
        REC.start("hwt_card", "the plain idea", root)
    sp = api.wf_spec("hwt_card", root)
    assert (sp["markets"], sp["bar_sizes"], sp["sessions"]) == (["NQ"], ["15"], ["nyam"])      # its home table only
