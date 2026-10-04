"""score.py: trade sources, the sealed holdout, the session calendar, schema validation, compute windows."""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

E, P = S.E, S.P
ET = S.ET


def _ms(date: str, hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(h, m), tzinfo=ET).timestamp() * 1000)


def trade(date="2023-03-15", t0="09:35", t1="10:05", side="long", entry=12000.0, exit_=12010.0, mae_pts=5.0, mfe_pts=15.0, qty=1, **kw):
    sgn = 1 if side == "long" else -1
    gross = sgn * (exit_ - entry) * 20.0 * qty
    r = {"date": date, "side": side, "qty": qty, "entry_price": entry, "exit_price": exit_, "exit_reason": "tp", "gross": gross,
         "commission": 4.0 * qty, "net": gross - 4.0 * qty, "mae_pts": mae_pts, "mfe_pts": mfe_pts, "mae_usd": mae_pts * 20.0 * qty,
         "mfe_usd": mfe_pts * 20.0 * qty, "entry_ms": _ms(date, t0), "exit_ms": _ms(date, t1), "sl": entry - sgn * 30.0}
    r.update(kw)
    return r


def ledger(n=40, start=0, every=3):
    """n winning/losing trades on in-sample sessions (deterministic)."""
    days = S.in_sample_sessions()[start::every][:n]
    return [trade(d, exit_=12000.0 + (25.0 if i % 3 else -20.0), mae_pts=22.0 if i % 3 == 0 else 4.0, mfe_pts=27.0 if i % 3 else 3.0)
            for i, d in enumerate(days)]


# ------------------------------------------------------------------ sources

def test_in_memory_list_equals_file_and_R_loader(tmp_path):
    rows = ledger()
    p = tmp_path / "cfg_a.json"
    p.write_text(json.dumps(rows))
    a, b, c = S.load_trades(rows), S.load_trades(str(p)), S.load_trades({"trades": rows})
    q = tmp_path / "wrapped.json"
    q.write_text(json.dumps({"trades": rows}))
    d = S.load_trades({"path": str(q)})
    ref = S._R_LOAD(rows)                                           # R's loader on the same list
    for t in (a, b, c, d):
        assert t.n == len(rows) == ref.n
        for f in ("date", "te", "tx", "side", "g", "mae", "mfe", "sess", "risk"):
            assert np.array_equal(getattr(t, f), getattr(ref, f))
        assert t.range == (S.IS_START, S.IS_END)
    assert b.label == "cfg_a" and set(a.sess.tolist()) == {E.SESS_CODE["nyam"]}
    assert np.allclose(a.net, a.g - 4.0)


def test_config_name_resolves_to_L_trades(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "TRADES", tmp_path)
    (tmp_path / "b1_imb3_tf5.json").write_text(json.dumps(ledger(10)))
    for src in ("file:b1_imb3_tf5", "b1_imb3_tf5", {"file": "b1_imb3_tf5"}, "file:b1_imb3_tf5.json"):
        assert S.load_trades(src).n == 10 and S.is_file_source(src)
    with pytest.raises(FileNotFoundError):
        S.load_trades("file:nope")
    with pytest.raises(FileNotFoundError):
        S.load_trades("no-such-config-or-run")
    assert S.trade_file("x").parent == tmp_path


def test_qty_is_normalised_like_R():
    one = S.load_trades([trade(qty=1)])
    three = S.load_trades([trade(qty=3)])
    assert one.g[0] == three.g[0] == 200.0 and one.mae[0] == three.mae[0] == 100.0 and one.mfe[0] == three.mfe[0] == 300.0


def test_file_cache_follows_rewrites(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(ledger(5)))
    assert S.load_trades(str(p)).n == 5
    p.write_text(json.dumps(ledger(9)))
    assert S.load_trades(str(p)).n == 9


def test_R_accepts_file_members_through_the_wrappers(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "TRADES", tmp_path)
    (tmp_path / "cfg.json").write_text(json.dumps(ledger(60)))
    assert E.load is S._load_wrapper
    t = E.load("file:cfg")
    assert t.n == 60 and E._src_dir("file:cfg") == tmp_path / "cfg.json"
    Pn = E.build({"members": [{"src": "file:cfg", "sess": "nyam", "micros": 20}]})
    assert len(Pn.days) == 825 and Pn.n_trades == 60 and Pn.window == ("2021-09-22", "2024-12-31")
    res = E.evaluate({"members": [{"src": "file:cfg", "sess": "nyam", "micros": 20}], "firms": ["lucid"]}, mc=0, boots=0, eventual=0, funded=False)
    mine = S.score_eval("file:cfg", "lucid", {"target_stop": False}, micros=20, sess="nyam", boots=0)
    assert res["firms"][E.firm_rules("lucid")[0]]["realized"]["p_pass"] == mine["p5"]
    ctx = P.Ctx(P.Ctx.calendar())
    b = ctx.base({"cid": "cfg|nyam", "src": "file:cfg", "sess": "nyam"})
    assert b.n == 60


def test_wrapper_leaves_R_native_sources_to_R(tmp_path, l_tmp):
    """In-memory lists and paths outside this pilot directory keep R's loader and R's semantics inside R (other L modules and
    their tests build portfolios from minimal lists through evalcore.build); only the L source types are taken over."""
    minimal = [{"date": "2023-03-15", "entry_ms": _ms("2023-03-15", "09:35"), "gross": 100.0},
               {"date": "2025-01-02", "entry_ms": _ms("2025-01-02", "09:35"), "gross": 100.0}]
    t = E.load(minimal)                                             # R: accepted as is, the 2025 row silently dropped
    assert t.n == 1 and t.label == "inline" and t.range == (None, None)
    assert E.build({"members": [{"src": minimal, "micros": 10}]}).n_trades == 1
    p = tmp_path / "outside.json"
    p.write_text(json.dumps(minimal))
    assert S._wrapped(str(p)) is None and S._wrapped(minimal) is None and E.load(str(p)).n == 1
    assert E._src_dir(str(p)) == p and E._src_dir(minimal) is None
    with pytest.raises(ValueError):
        S.load_trades(minimal[:1])                                  # ... while the adapter's own loader validates
    with pytest.raises(S.HoldoutError):
        S.load_trades(minimal, strict=False)                        # ... and seals
    inside = l_tmp / "score_wrap_test.json"                         # a real path, even inside L, is R's own source type
    inside.write_text(json.dumps(minimal))
    assert S._wrapped(str(inside)) is None and E.load(str(inside)).n == 1


def test_bundle_directory_keeps_its_run_range(tmp_path):
    """A sim bundle (trades.json + run.json) is scored on the span its run covered, as evalcore.build does."""
    days = S.in_sample_sessions()[100:160]
    rows = [trade(d, exit_=12015.0) for d in days[::2]]
    b = tmp_path / "b1_sim_run"
    b.mkdir()
    (b / "trades.json").write_text(json.dumps(rows))
    (b / "run.json").write_text(json.dumps({"range": {"start": days[0], "end": days[-1], "holdout": False}}))
    t = S.load_trades(str(b))
    ref = S._R_LOAD(str(b))
    assert t.range == ref.range == (days[0], days[-1]) and t.label == ref.label == "b1_sim_run" and t.n == ref.n == 30
    r = S.score_eval(str(b), "lucid", micros=20, boots=0)
    assert r["window"]["sessions"] == 60 and r["window"]["start"] == days[0] and r["window"]["end"] == days[-1]
    Pn = E.build({"members": [{"src": str(b), "micros": 20}]})
    assert len(Pn.days) == 60 and S.score_eval(rows, "lucid", micros=20, boots=0)["window"]["sessions"] == 825
    f = S.score_funded(str(b), "flex", micros=20, boots=0)
    assert f["n_starts"] == 1
    (b / "run.json").write_text(json.dumps({"range": {"start": "2025-01-01", "end": "2025-06-30", "holdout": True}}))
    (b / "trades.json").write_text("NOT JSON")
    with pytest.raises(S.HoldoutError):
        S.load_trades(str(b))                                       # refused from run.json, trades.json never parsed


def test_evalcore_save_is_redirected_out_of_R(tmp_path):
    p = E.save({"tag": "zz_score_test", "x": 1}, tmp_path)
    assert p.parent == tmp_path
    import inspect
    assert "OUT" in inspect.getsource(S._save_wrapper) and S.OUT == L / "out" and E.save is S._save_wrapper


# ------------------------------------------------------------------ holdout seal

def test_holdout_rows_raise_everywhere(tmp_path, monkeypatch):
    bad = ledger(5) + [trade("2025-01-02")]
    with pytest.raises(S.HoldoutError):
        S.load_trades(bad)
    p = tmp_path / "ho.json"
    p.write_text(json.dumps(bad))
    monkeypatch.setattr(S, "TRADES", tmp_path)
    for fn in (lambda: S.load_trades(str(p)), lambda: S.score_eval(str(p), "lucid"), lambda: S.score_funded(bad, "flex"),
               lambda: S.search_rules(bad, "lucid"), lambda: S.lift_vs_control(ledger(5), bad, "lucid"),
               lambda: S.lift_vs_control(bad, ledger(5), "lucid"), lambda: S.daymatched(ledger(5), bad),
               lambda: S.search_funded(bad, "flex"), lambda: S.score_eval({"path": str(p)}, "apex"),
               lambda: E.load("file:ho"), lambda: E.load({"file": "ho"}), lambda: E.build({"members": [{"src": "file:ho"}]}),
               lambda: E.evaluate({"members": [{"src": "file:ho"}]})):
        with pytest.raises(S.HoldoutError):
            fn()
    t = S.load_trades(bad, allow_holdout=True)                      # only with the explicit switch
    assert t.n == 6 and t.range == (None, None)


def test_holdout_guard_looks_at_timestamps_not_only_the_date_field():
    sneaky = trade("2024-12-31")
    sneaky["entry_ms"], sneaky["exit_ms"] = _ms("2025-01-02", "09:35"), _ms("2025-01-02", "10:00")
    with pytest.raises(S.HoldoutError):
        S.load_trades([sneaky], strict=False)
    late_exit = trade("2024-12-31")
    late_exit["exit_ms"] = _ms("2025-01-02", "10:00")
    with pytest.raises(S.HoldoutError):
        S.load_trades([late_exit], strict=False)


def test_holdout_calendar_raises():
    with pytest.raises(S.HoldoutError):
        S.make_calendar(["2024-12-30", "2024-12-31", "2025-01-02"])
    with pytest.raises(S.HoldoutError):
        S.score_eval(ledger(5), "lucid", calendar=S.in_sample_sessions() + ["2025-01-02"])
    with pytest.raises(S.HoldoutError):
        S.tape_sessions("2024-01-01", "2025-06-30")
    assert S.make_calendar(["2025-01-02", "2025-01-03"], allow_holdout=True).D == 2


def test_explicit_holdout_switch_scores_on_a_given_calendar():
    """The holdout stage (orchestrator only): allow_holdout=True + an explicit calendar. SYNTHETIC 2025 rows, no real data."""
    import pandas as pd
    days = [d.isoformat() for d in pd.bdate_range("2025-01-02", periods=80).date]
    rows = [trade(d, exit_=12020.0, mae_pts=1.0, mfe_pts=21.0) for d in days[::2]]
    with pytest.raises(S.HoldoutError):
        S.score_eval(rows, "lucidpro_nodll", micros=40, calendar=days)
    with pytest.raises(ValueError, match="off the session calendar"):                   # the default calendar is in-sample only:
        S.score_eval(rows, "lucidpro_nodll", micros=40, allow_holdout=True)             # the holdout calendar must be given
    r = S.score_eval(rows, "lucidpro_nodll", {"target_stop": False}, micros=40, calendar=days, allow_holdout=True, boots=0)
    assert r["window"] == {"start": days[0], "end": days[-1], "sessions": 80, "starts5": 76, "starts60": 21}
    assert r["p5"] == 1.0 and r["p3"] == 0.5                                             # +1,584 every other day: 2 trade days needed
    f = S.score_funded(rows, "pro_nodll", 500, micros=40, calendar=days, allow_holdout=True, boots=0)
    assert f["n_starts"] == 21 and f["p_pay_20"] > 0
    late = rows + [trade((pd.Timestamp(days[-1]) + pd.offsets.BDay(3)).date().isoformat())]
    with pytest.raises(ValueError, match="off the session calendar"):
        S.score_eval(late, "lucid", calendar=days, allow_holdout=True)
    assert S.score_eval(late, "lucid", calendar=days, allow_holdout=True, off_calendar="drop", boots=0)["n_trades"] == 40


def test_native_guard_on_R_run_ids(monkeypatch, tmp_path):
    """A native R source whose run.json reaches 2025 raises through load_trades AND through evalcore.load (the wrapper),
    BEFORE its trades.json is read (the file here is not even JSON)."""
    runs = tmp_path / "runs"
    (runs / "ho-run").mkdir(parents=True)
    (runs / "ho-run" / "run.json").write_text(json.dumps({"range": {"start": "2025-01-01", "end": "2026-09-30"}}))
    (runs / "ho-run" / "trades.json").write_text("NOT JSON")
    (runs / "is-run").mkdir()
    (runs / "is-run" / "run.json").write_text(json.dumps({"range": {"start": "2021-01-01", "end": "2024-12-31"}, "holdout": False}))
    (runs / "is-run" / "trades.json").write_text(json.dumps(ledger(7)))
    monkeypatch.setattr(E, "RUNS", runs)
    with pytest.raises(S.HoldoutError):
        S.load_trades("ho-run")
    with pytest.raises(S.HoldoutError):
        E.load("ho-run")
    with pytest.raises(S.HoldoutError):
        S.export_bundle("ho-run", "zz_never_written")
    assert not S.trade_file("zz_never_written").exists()
    assert S.load_trades("is-run").n == 7 and E.load("is-run").n == 7
    E._CACHE.pop((str(runs / "is-run"), False), None)


# ------------------------------------------------------------------ schema validation

def test_validation_catches_sim_contract_breaks():
    ok = trade()
    assert S.validate_trades([ok]) == []
    cases = {"missing": {k: v for k, v in ok.items() if k != "mae_usd"},
             "gross": dict(ok, gross=ok["gross"] + 5.0, net=ok["net"] + 5.0),
             "net": dict(ok, net=ok["net"] - 1.0),
             "side": dict(ok, side="buy"),
             "qty": dict(ok, qty=0.5, gross=ok["gross"] * 0.5, net=ok["gross"] * 0.5 - 4.0),
             "date": dict(ok, date="2023-03-16"),
             "exit": dict(ok, exit_ms=ok["entry_ms"] - 1)}
    for name, row in cases.items():
        assert S.validate_trades([row]), name
        with pytest.raises(ValueError):
            S.load_trades([row])
    assert S.load_trades([cases["net"]], strict=False).n == 1       # R's loader itself does not read net


def test_short_side_and_points_value():
    t = trade(side="short", entry=12000.0, exit_=11990.0)
    assert t["gross"] == 200.0 and S.validate_trades([t]) == []
    tr = S.load_trades([t])
    assert tr.side[0] == -1 and tr.g[0] == 200.0 and tr.risk[0] == 30.0


# ------------------------------------------------------------------ calendar

def test_in_sample_calendar_is_Rs():
    ds = S.in_sample_sessions()
    assert len(ds) == 825 and ds[0] == "2021-09-22" and ds[-1] == "2024-12-31"
    assert ds == json.loads((S.R / "bundles_cache" / "nq_sessions.json").read_text())
    assert all(dt.date.fromisoformat(d).weekday() < 5 for d in ds)
    cal = S.make_calendar()
    assert cal.D == 825 and cal.S == 821 and cal.idx5.shape == (821, 5) and cal.window["starts60"] == 766
    assert np.array_equal(cal.cal, P.Ctx.calendar())


def test_tape_archive_listing_matches_the_cached_calendar():
    """R builds its calendars from the tick-archive manifests (TapeStore.sessions); in-sample it must equal the cache."""
    assert S.tape_sessions("2021-01-01", "2024-12-31") == S.in_sample_sessions()


def test_ofb_tick_tape_sessions_equal_the_calendar():
    """The offline sim's execution tape (ofb_tick, one parquet per session) covers exactly the calendar in-sample (file names only)."""
    root = Path.home() / "futures_derived" / "ofb_tick" / "NQ"
    if not root.exists():
        pytest.skip("ofb_tick tape not on this machine")
    names = sorted(p.stem for y in ("2021", "2022", "2023", "2024") for p in (root / y).rglob("*.parquet"))
    assert names == S.in_sample_sessions()


def test_no_trade_weekdays_are_sessions_and_off_calendar_dates_raise():
    rows = ledger(30)
    r = S.score_eval(rows, "lucid", micros=10, boots=0)
    assert r["window"]["sessions"] == 825 and r["series"]["n_sessions"] == 825 and r["series"]["trade_days"] == 30
    sat = trade("2023-03-18")                                       # a Saturday: not a session
    with pytest.raises(ValueError, match="off the session calendar"):
        S.score_eval(rows + [sat], "lucid", micros=10, boots=0)
    u = S.score_eval(rows + [sat], "lucid", micros=10, boots=0, off_calendar="union")       # R's own convention
    assert u["window"]["sessions"] == 826 and u["series"]["trade_days"] == 31
    d = S.score_eval(rows + [sat], "lucid", micros=10, boots=0, off_calendar="drop")
    assert d["window"]["sessions"] == 825 and d["p5"] == r["p5"] and d["n_trades"] == 30


def test_sub_window_calendar():
    ds = [d for d in S.in_sample_sessions() if d.startswith("2023")]
    rows = [t for t in ledger(200, every=4) if t["date"].startswith("2023")]
    r = S.score_eval(rows, "apex", micros=20, boots=0, calendar=ds)
    assert r["window"]["sessions"] == len(ds) and r["window"]["starts5"] == len(ds) - 4


# ------------------------------------------------------------------ results sanity on a hand-made ledger

def test_score_eval_hand_case():
    """One +$1,600 day at 40 micros (4 NQ): Lucid Pro noDLL needs $3,000 -> two consecutive such days pass on day 2."""
    ds = S.in_sample_sessions()
    rows = [trade(d, exit_=12020.0, mae_pts=1.0, mfe_pts=21.0) for d in ds]          # +20 pts = +$400 per NQ, every session
    r = S.score_eval(rows, "lucidpro_nodll", {"target_stop": False}, micros=40, boots=0)
    # per day: 4 NQ * $400 - cost(40) = 1600 - 16 = 1584 -> 2 days = 3168 >= 3000
    assert r["series"]["mean_day"] == pytest.approx(1584.0)
    assert r["p1"] == 0.0 and r["p2"] == 1.0 and r["p5"] == 1.0 and r["bust5"] == 0.0 and r["med_days"] == 2.0
    lose = [trade(d, exit_=11940.0, mae_pts=61.0, mfe_pts=1.0) for d in ds]          # -60 pts = -$1,200 per NQ
    b = S.score_eval(lose, "lucidpro_nodll", micros=20, boots=0)                     # 2 NQ: -2,408 a day <= -2,000 floor
    assert b["p5"] == 0.0 and b["bust5"] == 1.0 and b["bust_by"][0] == 1.0
    for m in S.MODELS:
        assert b["models"][m]["bust5"] == 1.0
    assert S.score_eval([], "lucid").get("skipped")


def test_micros_and_rules_inputs():
    rows = ledger(60)
    a = S.score_eval(rows, "lucid", {"micros": 30, "day_lock": 750}, boots=0)
    b = S.score_eval(rows, "lucid", {"day_lock": 750}, micros=30, boots=0)
    assert a["members"][0]["micros"] == 30 and a["p5"] == b["p5"] and a["series"] == b["series"]
    assert S.score_eval(rows, "lucid", boots=0)["members"][0]["micros"] == 10        # R's member default
    with pytest.raises(ValueError):
        S.score_eval(rows, "lucid", {"daytake": 1500})
    with pytest.raises(ValueError):
        S.score_eval(rows, "topstep")
    with pytest.raises(ValueError):
        S.score_eval(rows, "lucid", model="pess")
    clip = S.score_eval(rows, "lucid", micros=80, boots=0)                           # above the 40-micro cap: R clips and flags
    assert clip["walk"]["clipped"] == 60 and clip["walk"]["cap_ok"] is False


def test_primary_models():
    rows = ledger(60)
    assert S.score_eval(rows, "lucid", boots=0)["model"] == "realized"
    assert S.score_eval(rows, "lucidpro", boots=0)["model"] == "realized"
    assert S.score_eval(rows, "apex", boots=0)["model"] == "intraday"
    assert S.score_eval(rows, "apex_eod", boots=0)["model"] == "intraday"
    r = S.score_eval(rows, "lucid", model="intraday", boots=50)
    assert r["p5"] == r["models"]["intraday"]["p5"] and set(r["models"]) == set(S.MODELS) and "ci_p5" in r["models"]["eod"]
    assert S.score_funded(rows, "flex", micros=20, boots=0)["model"] == "realized"
    assert S.score_funded(rows, "apex", micros=20, boots=0)["model"] == "pess"


# ------------------------------------------------------------------ offline compute windows

def _et(y, mo, d, h, mi, s=0):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=ET)


def test_compute_windows():
    assert S.blackout_wait_s(_et(2026, 10, 1, 9, 17, 30)) > 0                        # Thu, 30 s before 09:18 (60 s lead)
    assert S.blackout_wait_s(_et(2026, 10, 1, 9, 16, 30)) == 0
    assert S.blackout_wait_s(_et(2026, 10, 1, 9, 20)) == pytest.approx(16 * 60 + 5)
    assert S.blackout_wait_s(_et(2026, 10, 1, 9, 36)) == 0
    assert S.blackout_wait_s(_et(2026, 10, 3, 9, 20)) == 0                           # Saturday
    assert S.blackout_wait_s(_et(2026, 10, 2, 8, 20)) == pytest.approx(30 * 60 + 5)  # Fri 2026-10-02 NFP window
    assert S.blackout_wait_s(_et(2026, 10, 2, 8, 50)) == 0
    assert S.blackout_wait_s(_et(2026, 10, 2, 9, 30)) > 0
    assert S.blackout_wait_s(_et(2026, 10, 9, 8, 20)) == 0                           # a later Friday: no NFP window
    assert S.blackout_wait_s(dt.datetime(2026, 10, 1, 13, 20, tzinfo=dt.timezone.utc)) > 0      # 09:20 ET given in UTC
    slept = []
    assert S.desk_window_wait(_et(2026, 10, 1, 9, 20), sleep=slept.append) == pytest.approx(965.0) and slept == [pytest.approx(965.0)]
    assert S.desk_window_wait(_et(2026, 10, 1, 12, 0), sleep=slept.append) == 0.0 and len(slept) == 1
    assert S.F.desk_window_wait is S.desk_window_wait                                # R's funded search cells use it too
