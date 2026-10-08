"""Holdout seal, compute windows, calendar / coverage parity with the tester, tape identity, runner plumbing."""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

import l2ref
import l2sim as S

ET = S.ET
HB_TAPE = Path.home() / "futures_derived" / "homebase_tape" / "NQ"


# ---- holdout ----------------------------------------------------------------------------------------------
def test_holdout_loaders_raise_before_touching_any_file(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a sealed file path was resolved")
    monkeypatch.setattr(S, "tape_path", boom)
    for d in ("2025-01-01", "2025-01-02", dt.date(2026, 7, 8)):
        with pytest.raises(S.HoldoutSealed):
            S.load_tape(d)
        with pytest.raises(S.HoldoutSealed):
            S.load_tape(d, allow_holdout=1)                    # only the literal True opens the seal
    with pytest.raises(S.HoldoutSealed):
        S.sessions("2024-12-01", "2025-01-01")
    with pytest.raises(S.HoldoutSealed):
        S.run(l2ref.Donchian, {}, "2024-12-01", "2025-01-02", workers=1)
    with pytest.raises(S.HoldoutSealed):
        S.run(l2ref.Donchian, {}, "2024-12-01", "2024-12-31", days=["2024-12-30", "2025-01-02"], workers=1)
    with pytest.raises(S.HoldoutSealed):
        S._run_days(([(l2ref.Donchian, {})], "NQ", ["2025-03-03"], S.Costs(), 1, False, None, None, None, False))
    with pytest.raises(S.HoldoutSealed):
        S.build_daily(end="2025-06-30", workers=1)
    with pytest.raises(S.HoldoutSealed):
        S.L2Features(["imb10"])(dt.date(2025, 1, 2))


def test_in_sample_calendar_and_daily_cache_hold_no_sealed_row():
    days = S.sessions(*S.IN_SAMPLE)
    assert len(days) == 825 and days[0] == dt.date(2021, 9, 22) and days[-1] == dt.date(2024, 12, 31)
    assert all(d.weekday() < 5 for d in days)
    daily = S.load_daily()
    assert [r["date"] for r in daily] == [d.isoformat() for d in days]
    assert max(r["date"] for r in daily) < "2025-01-01"
    raw = json.loads((S.CACHE / "daily_NQ.json").read_text())["rows"]
    assert max(r["date"] for r in raw) < "2025-01-01"


# ---- compute windows ----------------------------------------------------------------------------------------
def et(y, m, d, hh, mm, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=ET)


def test_the_weekday_open_window_is_off_by_the_owners_order():
    assert S.OPEN_WINDOW is None
    assert S.compute_window_end(et(2026, 10, 1, 9, 20)) is None and S.compute_window_end(et(2026, 10, 1, 9, 35)) is None
    assert S.compute_window_end(et(2026, 10, 2, 8, 20)) == et(2026, 10, 2, 8, 50)      # the one-off NFP window stays


def test_compute_window_bounds(monkeypatch):
    monkeypatch.setattr(S, "OPEN_WINDOW", (dt.time(9, 18), dt.time(9, 36)))             # the window, put back for this test
    w = S.compute_window_end
    assert w(et(2026, 10, 1, 9, 17, 59)) is None                         # Thursday
    assert w(et(2026, 10, 1, 9, 18)) == et(2026, 10, 1, 9, 36)
    assert w(et(2026, 10, 1, 9, 35, 59)) == et(2026, 10, 1, 9, 36)
    assert w(et(2026, 10, 1, 9, 36)) is None
    assert w(et(2026, 10, 3, 9, 20)) is None                             # Saturday
    assert w(et(2026, 10, 1, 8, 20)) is None                             # NFP window is Friday 2026-10-02 only
    assert w(et(2026, 10, 2, 8, 15)) == et(2026, 10, 2, 8, 50)
    assert w(et(2026, 10, 2, 8, 49, 59)) == et(2026, 10, 2, 8, 50)
    assert w(et(2026, 10, 2, 8, 50)) is None
    assert w(et(2026, 10, 2, 9, 20)) == et(2026, 10, 2, 9, 36)
    assert w(dt.datetime(2026, 10, 1, 13, 20, tzinfo=dt.timezone.utc)) == et(2026, 10, 1, 9, 36)   # any tz in


def test_wait_compute_window_sleeps_to_the_end_and_not_outside():
    now = [et(2026, 10, 2, 8, 30)]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += dt.timedelta(seconds=s)
    assert S.wait_compute_window(sleep=sleep, clock=lambda: now[0]) == pytest.approx(20 * 60 + 1)
    assert now[0] >= et(2026, 10, 2, 8, 50) and len(slept) == 1
    now[0] = et(2026, 10, 2, 12, 0)
    assert S.wait_compute_window(sleep=sleep, clock=lambda: now[0]) == 0.0 and len(slept) == 1
    assert 1 <= S.MAX_WORKERS <= 8                  # EDGE_MAX_WORKERS may lower the cap, never raise it


# ---- parity with the tester's calendar / coverage / tape ---------------------------------------------------
def test_early_closes_and_coverage_match_the_tester():
    T = pytest.importorskip("homebase.backtest.tape")
    assert {d for d in S.EARLY_CLOSES if d.year >= 2021} == set(T.EARLY_CLOSES)
    win = ("00:00", "16:10")
    for d in (dt.date(2023, 11, 24), dt.date(2024, 7, 3), dt.date(2024, 12, 24), dt.date(2024, 7, 5)):
        assert S.effective_session_window(d, win) == T.effective_session_window("NQ", d, win)
    assert S.effective_session_window(dt.date(2023, 11, 24), win) == ("00:00", "13:15")
    assert S.effective_session_window(dt.date(2023, 11, 24), ("09:30", "11:00")) == ("09:30", "11:00")
    for iso in ("2021-12-01", "2022-06-21", "2023-04-07", "2023-11-24", "2024-03-11"):
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d)
        w = S.effective_session_window(d, win)
        assert S.missing_hours(tape.ts, d, w) == T.missing_hours(tape.ts.tolist(), d, w)
        assert S.et_ns(d, "09:30") == T.et_ns(d, "09:30") and S.et_ns(d, "08:29:30") == T.et_ns(d, "08:29:30")
    assert S.missing_hours(S.load_tape("2023-04-07").ts, dt.date(2023, 4, 7), win) == [("10:00", "16:10")]


@pytest.mark.parametrize("iso", ["2021-09-22", "2022-12-12", "2024-12-31"])
def test_tape_is_print_identical_to_the_tester_cache(iso):
    p = HB_TAPE / f"{iso}.tape"
    if not p.exists():
        pytest.skip("tester tape cache not present")
    magic = b"HBTAPE1\n"
    with open(p, "rb") as f:
        assert f.read(len(magic)) == magic
        head = json.loads(f.read(int.from_bytes(f.read(4), "little")))
        n = head["n"]
        ts = np.fromfile(f, dtype="<i8", count=n)
        px = np.fromfile(f, dtype="<f8", count=n)
        sz = np.fromfile(f, dtype="<i4", count=n)
    t = S.load_tape(iso)
    assert len(t.ts) == n and (t.ts == ts).all() and (t.px == px).all() and (t.size == sz).all()
    assert t.contract == head["contract"] and t.daily == head["daily"]
    row = next(r for r in S.load_daily() if r["date"] == iso)
    assert {k: row[k] for k in "hlc"} == head["daily"] and row["contract"] == head["contract"]


def test_rolls_equal_the_tester_drafts_list():
    want = {'2021-12-10', '2022-03-14', '2022-06-13', '2022-09-12', '2022-12-12', '2023-03-13', '2023-06-12',
            '2023-09-11', '2023-12-11', '2024-03-11', '2024-06-17', '2024-09-16', '2024-12-17'}   # pp_*.py ROLLS < 2025
    assert set(S.rolls(S.load_daily())) == want


# ---- runner -------------------------------------------------------------------------------------------------
PARAMS = {"tf": "15", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 0.6}


def test_workers_do_not_change_the_result_and_schema_is_the_bundle_schema():
    a = S.run(l2ref.Donchian, PARAMS, "2024-11-18", "2024-12-06", workers=1)
    b = S.run(l2ref.Donchian, PARAMS, "2024-11-18", "2024-12-06", workers=4)
    assert a["trades"] == b["trades"] and len(a["trades"]) > 20
    assert a["sessions"] == 14 and a["used"] == 14 and a["skipped"] == []      # no Thanksgiving-day tape
    keys = ["date", "side", "qty", "entry_price", "exit_price", "exit_reason", "order_price", "sl", "tp", "gross",
            "commission", "net", "mae_pts", "mfe_pts", "mae_usd", "mfe_usd", "bars", "seconds", "entry_ms", "exit_ms",
            "oco", "both_sides"]                                         # the tester's 20 fields + the one-direction evidence
    assert all(list(t) == keys for t in a["trades"])
    assert [(t["exit_ms"], t["entry_ms"]) for t in a["trades"]] == sorted((t["exit_ms"], t["entry_ms"]) for t in a["trades"])
    half = [t for t in a["trades"] if t["date"] == "2024-11-29"]            # half day: flat by 13:15 ET
    assert half and all(t["exit_ms"] <= S.et_ns(dt.date(2024, 11, 29), "13:15") // 1_000_000 for t in half)
    with pytest.raises(ValueError):
        S.run(l2ref.Donchian, {"nope": 1}, "2024-12-02", "2024-12-03", workers=1)


def test_coverage_holes_are_skipped_like_the_tester():
    r = S.run(l2ref.Donchian, PARAMS, "2023-04-05", "2023-04-10", workers=1)
    assert r["skipped"] == [{"date": "2023-04-07", "reason": "missing 10:00–16:10 ET"}]
    assert r["sessions"] == 4 and r["used"] == 3 and not [t for t in r["trades"] if t["date"] == "2023-04-07"]


def test_bundle_is_written_under_the_pilot_only_and_evalcore_reads_it(tmp_path, l_tmp):
    r = S.run(l2ref.Donchian, PARAMS, "2024-12-02", "2024-12-13", workers=1)
    with pytest.raises(ValueError):
        S.write_bundle(r, tmp_path / "x")
    out = l_tmp / "bundle"
    try:
        S.write_bundle(r, out)
        assert json.loads((out / "trades.json").read_text()) == r["trades"]
        meta = json.loads((out / "run.json").read_text())
        assert meta["range"] == {"start": "2024-12-02", "end": "2024-12-13", "holdout": False, "period": "pick"}
        assert meta["commission"] == 4.0 and meta["slippage_ticks"] == 1.0 and meta["qty"] == 1
        sys.path.insert(0, str(S.R))
        try:
            E = pytest.importorskip("evalcore")
        finally:
            sys.path.remove(str(S.R))
        t = E.load(str(out))
        assert t.n == len(r["trades"]) and t.range == ("2024-12-02", "2024-12-13")
        assert float(t.g.sum()) == pytest.approx(sum(x["gross"] for x in r["trades"]))
        want = [S.session_of(x["entry_ms"]) for x in r["trades"]]
        code = {v: k for k, v in E.SESS_CODE.items()}
        assert [code.get(int(c)) for c in t.sess] == want
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_feature_loader_respects_the_timestamp_law_on_real_data():
    if not (S.CACHE / "l2feat_NQ_2023.parquet").exists():
        pytest.skip("data-layer cache not built")
    d = dt.date(2023, 5, 3)
    f = S.L2Features(["imb10", "f_delta"])(d)
    assert f is not None and (np.diff(f.usable_ns) > 0).all()
    seen = []

    class Probe(S.Strategy):
        session_window = ("09:30", "09:40")

        def on_bar(self, ctx, bar):
            k = ctx.feat_n()
            seen.append((bar.end_ns, int(f.usable_ns[k - 1]), ctx.feat("f_delta"), float(f.cols["f_delta"][k - 1])))
    S.run_session(Probe(), S.load_tape(d), features=f)
    assert len(seen) == 9
    for end_ns, usable, got, want in seen:
        assert usable == end_ns                      # at the close of minute M the newest visible row is M's (usable M+60s)
        assert got == want


def test_run_many_equals_separate_runs_and_shares_one_pass():
    specs = [(l2ref.Donchian, PARAMS), (l2ref.Straddle, {"tf": "30", "off_atr": 0.25, "stop_val": 3.0, "tgt_r": 2.0}),
             (l2ref.Donchian, {**PARAMS, "tgt_r": 1.0}), (l2ref.Straddle, {"news_only": True, "tf": "5"})]
    many = S.run_many(specs, "2024-12-02", "2024-12-20", workers=3)
    for (cls, prm), m in zip(specs, many):
        one = S.run(cls, prm, "2024-12-02", "2024-12-20", workers=1)
        assert m["trades"] == one["trades"] and m["skipped"] == one["skipped"]
        assert (m["sessions"], m["used"]) == (one["sessions"], one["used"])
        assert m["meta"]["inputs"] == one["meta"]["inputs"] and m["meta"]["cells_in_pass"] == 4
    assert many[0]["sessions"] == 15 and len(many[0]["trades"]) > 20
    # news_only straddle: only CPI/NFP/FOMC days are sessions (trades_on), bracket at 08:29:30 / 13:59:30 ET
    news = many[3]
    assert news["sessions"] == 3                                   # 2024-12-06 NFP, 12-11 CPI, 12-18 FOMC
    assert {t["date"] for t in news["trades"]} <= {"2024-12-06", "2024-12-11", "2024-12-18"}


def test_features_reach_the_strategy_through_worker_processes_under_the_timestamp_law():
    if not (S.CACHE / "l2feat_NQ_2024.parquet").exists():
        pytest.skip("data-layer cache not built")
    import pickle
    loader = S.L2Features(["imb10", "f_delta"])
    assert pickle.loads(pickle.dumps(loader)).columns == ("imb10", "f_delta")
    res = S.run(l2ref.FeatureProbe, {"at": "10:07:00"}, "2024-12-02", "2024-12-06", workers=2, features=loader)
    assert len(res["trades"]) == 5 and res["meta"]["features"] == ["imb10", "f_delta"]
    import l2data
    df = l2data.load_features("2024-11-29", "2024-12-06", columns=["imb10", "f_delta"])     # incl. the evenings before
    ns = df.index.as_unit("ns").asi8 if hasattr(df.index, "as_unit") else df.index.asi8
    for t in res["trades"]:
        d = dt.date.fromisoformat(t["date"])
        decision = S.et_ns(d, "10:07:00")
        k = int(np.searchsorted(ns, decision, side="right")) - 1
        assert ns[k] == decision                                   # the row of minute 10:06 (usable at 10:07:00) ...
        assert t["tag"]["f_delta"] == float(df["f_delta"].iloc[k])  # ... and never the 10:07 minute still forming
        lo = int(np.searchsorted(ns, S.et_ns(d, "00:00") - 360 * S.MIN_NS, side="left"))
        assert t["tag"]["n"] == k - lo + 1 and t["tag"]["n"] > 607       # rows since 18:00 ET the evening before
        assert t["entry_ms"] >= decision // 1_000_000 + 85 and t["exit_reason"] == "time"


def test_cli_run_writes_a_bundle_under_out(capsys, l_tmp):
    out = l_tmp / "cli"
    try:
        rc = S.main(["run", "l2ref:Donchian", "--inputs", json.dumps(PARAMS), "--start", "2024-12-02", "--end",
                     "2024-12-04", "--workers", "1", "--out", str(out)])
        line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert rc == 0 and line["sessions"] == 3 and line["trades"] == len(json.loads((out / "trades.json").read_text()))
    finally:
        shutil.rmtree(out, ignore_errors=True)
