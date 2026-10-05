"""MULTI-ROOT (EDGE_SPEC user rule 4): ES and GC replay the tester's own tape cache with the tester's contract arithmetic.
  * tick / point arithmetic of ES ($50 / pt, 0.25) and GC ($100 / pt, 0.10) on synthetic tapes (no market data);
  * ES: three ES-pilot in-sample tester bundles reproduced trade for trade on one quarter (the full-window gate is
    edge_validate.py -> EDGE_VALIDATION.md); the ES roll dates equal RE/SPEC.md's list;
  * GC: no GC tester run exists (homebase/.state/tester holds NQ and ES runs only), so GC rests on (a) the tape: a session
    built with the tester's own code is byte-identical to the tester's cached file, (b) the arithmetic tests, (c) an
    independent engine: research/nfp-2026-10-02/nfp_lib.py on 5 BUILD NFP days (same entries; TP / SL outcomes to the cent).
Only identity and arithmetic are asserted: no result is judged."""
import datetime as dt
import json
import sys

import numpy as np
import pytest

import l2ref
import l2sim as S
import sim_validate as V

D = dt.date(2023, 3, 14)
T0 = S.et_ns(D, "09:30")
RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
ES_BUNDLES = [("straddle", "20260930-172655-draft_pp_es_straddle-3074"), ("orb", "20260930-172525-draft_pp_es_orb-fe82"),
              ("donchian", "20260930-172817-draft_pp_es_donchian-a235")]            # RE screen runs (in-sample, sess all)


def tape(root, prints, d=D):
    ts = [T0 + int(round(p[0] * 1e9)) for p in prints]
    return S.Tape(root, d, root + "M3", ts, [p[1] for p in prints], [1] * len(prints))


class Script(S.Strategy):
    session_window = ("09:30", "10:00")
    bar_minutes = 0

    def __init__(self, fn):
        super().__init__({})
        self.fn = fn

    def on_session(self, ctx):
        self.fn(ctx)


def test_specs_are_the_testers_contract_table():
    sys.path.append(str(S.REPO))
    from homebase.contracts import point_value, tick_size
    assert set(S.SPECS) == {"NQ", "ES", "GC"}
    for root, (pv, tick) in S.SPECS.items():
        assert pv == point_value(root) and tick == tick_size(root)
    assert S.SPECS["ES"] == (50.0, 0.25) and S.SPECS["GC"] == (100.0, 0.10) and S.Costs().commission_rt == 4.0
    from homebase.backtest.tape import EQUITY_INDEX_ROOTS
    assert S.EQUITY_INDEX_ROOTS == frozenset(EQUITY_INDEX_ROOTS) and "GC" not in S.EQUITY_INDEX_ROOTS


def test_es_arithmetic_on_a_synthetic_tape():
    # market long: first print after 85 ms + 1 tick (0.25); target 2 pts = limit, needs a 1-tick trade-through
    pr = [(0.05, 4000.0), (0.1, 4000.5), (5, 4002.75), (6, 4003.0), (1700, 4003.0)]
    t = S.run_session(Script(lambda c: c.market("long", sl=3996.0, tp=4002.75)), tape("ES", pr)).trades[0]
    assert t["entry_price"] == 4000.75 and t["exit_reason"] == "tp" and t["exit_price"] == 4002.75
    assert t["gross"] == 2.0 * 50.0 and t["commission"] == 4.0 and t["net"] == 96.0 and t["mfe_usd"] == (4003.0 - 4000.75) * 50
    # stop-loss: touch, fill = min(stop, print) - 1 tick: a gap costs the gap
    pr = [(0.1, 4000.0), (5, 3994.0), (1700, 3994.0)]
    t = S.run_session(Script(lambda c: c.market("long", sl=3996.0)), tape("ES", pr)).trades[0]
    assert t["exit_reason"] == "sl" and t["exit_price"] == 3993.75 and t["gross"] == (3993.75 - 4000.25) * 50 == -325.0
    assert t["mae_pts"] == 6.25 and t["mae_usd"] == 312.5


def test_gc_arithmetic_on_a_synthetic_tape_with_a_tenth_tick():
    # GC: tick 0.10, $100 / pt = $10 a tick. Prices land a hair off the float grid: every comparison is tick-tolerant.
    pr = [(0.1, 1900.0), (2, 1900.4), (3, 1900.5), (4, 1902.5), (5, 1902.6), (1700, 1902.6)]
    t = S.run_session(Script(lambda c: c.stop_entry("long", 1900.5, sl=1898.5, tp=1902.5)), tape("GC", pr)).trades[0]
    assert t["order_price"] == 1900.5 and t["entry_price"] == 1900.6            # touch at 1900.5 -> trigger + 1 tick (0.1)
    assert t["exit_reason"] == "tp" and t["exit_price"] == 1902.5               # 1902.5 touched, filled on 1902.6 (trade-through)
    assert t["exit_ms"] == (T0 + 5_000_000_000) // 1_000_000
    assert t["gross"] == 190.0 and t["net"] == 186.0                            # (1902.5 - 1900.6) x $100, - $4
    pr = [(0.1, 1900.0), (2, 1899.7), (1700, 1899.7)]
    t = S.run_session(Script(lambda c: c.market("short", sl=1901.0)), tape("GC", pr)).trades[0]
    assert t["entry_price"] == 1899.9 and t["exit_reason"] == "eod" and t["exit_price"] == 1899.8      # -1 tick in, +1 tick out
    assert t["gross"] == 10.0 and S.to_tick(1900.5 + 0.1, 0.1) == 1900.6
    # the menu's percent stop on GC: 0.10 % of 1900 = 1.9 pts, on the tick grid
    assert S.to_tick(1900.0 - 0.10 / 100 * 1900.0, 0.1) == 1898.1


def test_template_pct_stop_is_a_percent_of_the_entry_reference():
    st = l2ref.Donchian({"tf": "15", "stop_mode": "pct", "stop_val": 0.20})
    st.atr = 5.0

    class Ctx:
        tick = 0.25
    assert st._dist(Ctx, 15000.0, None) == pytest.approx(30.0) and st._dist(Ctx, 4000.0, 3990.0) == pytest.approx(8.0)
    st.p["stop_val"] = 0.10
    assert st._dist(Ctx, 15000.0, None) == pytest.approx(15.0)
    r = S.run(l2ref.Donchian, {"tf": "15", "stop_mode": "pct", "stop_val": 0.10, "tgt_r": 1.0}, days=["2023-03-14"], workers=1)
    assert r["trades"] and r["skipped_by_error"] == 0
    for t in r["trades"]:                                      # market entries: the bracket moves to the fill, 0.10 % of the signal close
        assert abs(t["entry_price"] - t["sl"]) == pytest.approx(abs(t["tp"] - t["entry_price"]), abs=0.26)
        assert abs(t["entry_price"] - t["sl"]) / t["entry_price"] * 100 == pytest.approx(0.10, abs=0.004)


def test_half_days_clamp_equity_index_roots_only():
    half = dt.date(2022, 11, 25)
    assert S.effective_session_window(half, ("00:00", "16:10")) == ("00:00", "13:15")
    assert S.effective_session_window(half, ("00:00", "16:10"), "ES") == ("00:00", "13:15")
    assert S.effective_session_window(half, ("00:00", "16:10"), "GC") == ("00:00", "16:10")
    assert S.effective_session_window(D, ("00:00", "16:10"), "ES") == ("00:00", "16:10")


def test_level2_features_and_options_are_nq_only():
    with pytest.raises(ValueError, match="NQ"):
        S.run(l2ref.Donchian, {"tf": "15"}, days=["2023-03-14"], root="ES", workers=1, features=S.L2Features(["imb10"]))
    with pytest.raises(ValueError, match="Level-2 options"):
        S.run(l2ref.Donchian, {"tf": "15", "f_book": "on"}, days=["2023-03-14"], root="ES", workers=1)
    with pytest.raises(ValueError, match="root"):
        S.run(l2ref.Donchian, {"tf": "15"}, days=["2023-03-14"], root="CL", workers=1)


@pytest.mark.parametrize("fam,rid", ES_BUNDLES, ids=[b[0] for b in ES_BUNDLES])
def test_es_reproduces_the_es_pilot_tester_bundle_on_one_quarter(fam, rid):
    run = json.loads((RUNS / rid / "run.json").read_text())
    assert run["range"]["end"] < "2025-01-01" and not run["range"]["holdout"] and run["strategy"]["root"] == "ES"
    assert (run["qty"], run["commission"], run["slippage_ticks"], run["engine"]) == (1, 4.0, 1.0, "tick-2")
    a, b = "2022-01-03", "2022-03-31"
    ref = [t for t in json.loads((RUNS / rid / "trades.json").read_text()) if a <= t["date"] <= b]
    res = S.run(l2ref.FAMILIES[fam], run["inputs"], a, b, root="ES", workers=1)
    c = V.compare(res["trades"], ref)
    assert c["n_ref"] > 150 and c["n_sim"] == c["n_ref"] == c["matched"] == c["exact_all_fields"] and c["net_diff"] == 0.0
    assert res["skipped_by_error"] == 0 and res["meta"]["root"] == "ES" and res["meta"]["point_value"] == 50.0
    assert [s["date"] for s in res["skipped"]] == [s["date"] for s in run["coverage"]["skipped"] if a <= s["date"] <= b]


def test_es_sessions_and_rolls_are_the_es_pilots():
    days = [d.isoformat() for d in S.sessions(*S.IN_SAMPLE, "ES")]
    assert days == [d for d in json.loads((S.RE / "bundles_cache" / "es_sessions.json").read_text()) if d <= "2024-12-31"]
    assert len(days) == 825 and all(S.hb_tape_path(d, "ES") is not None for d in days[::40])
    assert sorted(S.rolls(S.load_daily("ES"))) == [
        "2021-12-10", "2022-03-11", "2022-06-10", "2022-09-09", "2022-12-12", "2023-03-13", "2023-06-12", "2023-09-11", "2023-12-11",
        "2024-03-11", "2024-06-17", "2024-09-16", "2024-12-16"]                 # RE/SPEC.md "ROLLS"
    assert all(r["date"] < "2025-01-01" for r in S.load_daily("ES"))


def test_gc_tape_is_the_testers_tape(tmp_path):
    sys.path.append(str(S.REPO))
    from homebase.backtest.tape import TapeStore
    d = dt.date(2021, 10, 8)                                    # an NFP day the tester itself cached
    shared = S.HB_TAPE / "GC" / f"{d}.tape"
    if not shared.exists():
        pytest.skip("the tester's GC cache does not hold this session")
    mine = TapeStore(S.ARCHIVE, tmp_path).build("GC", d)        # the code build_tapes uses, into a scratch cache
    assert mine.read_bytes() == shared.read_bytes()
    t = S.load_tape(d, "GC")
    h = S.read_hb_header(shared)
    assert t.root == "GC" and t.contract == h["contract"] and len(t.ts) == h["n"] and t.daily == h["daily"]
    assert bool((np.diff(t.ts) >= 0).all()) and t.daily == {"h": float(t.px.max()), "l": float(t.px.min()), "c": float(t.px[-1])}
    own = sorted(p.name for p in (S.OWN_TAPE / "GC").glob("*.tape")) if (S.OWN_TAPE / "GC").exists() else []
    # build_tapes never builds an EXAM session (2026+; the CHECK year 2025 is built with allow_check=True: test_check_period.py).
    # The only 2026 tapes that may be on disk are the EXAM stage's own (EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES",
    # out/exam2026/build_data.py, 2026-10-05): a market an ALLOWED unit trades, no later than allowed.json's end date for it.
    with pytest.raises(S.HoldoutSealed):
        S.build_tapes("GC", "2026-01-02", "2026-01-05")
    with pytest.raises(S.HoldoutSealed):
        S.build_tapes("GC", "2026-01-02", "2026-01-05", allow_check=True)
    allowed = S.L.parent / "out" / "exam2026" / "allowed.json"
    a = json.loads(allowed.read_text()) if allowed.exists() else {}
    end = a.get("period", {}).get("end", {}).get("GC") if any(u.split("-")[1] == "GC" for u in a.get("units", [])) else None
    assert all(x[:10] < "2026-01-01" or (end is not None and x[:10] <= end) for x in own)


class NfpStraddle(S.Strategy):
    """The 08:30 OCO straddle of research/nfp-2026-10-02/nfp_lib.py on l2sim's raw API (anchor = last print before 08:30,
    cancel 08:45, flat 09:55, brackets measured from the fill)."""
    root = "GC"
    session_window = ("08:20", "09:56")
    bar_minutes = 0
    session_independent = True
    DEFAULTS = {"off": 2.0, "sl": 5.0, "tp": 5.0}

    def times(self):
        return ["08:30", "08:45", "09:55"]

    def on_session(self, ctx):
        self.legs = []

    def on_time(self, ctx, t):
        if t == "08:30":
            a = ctx.last_price
            if a is None:
                return
            ctx.move_brackets_to_fill = True
            o, sl, tp = self.p["off"], self.p["sl"], self.p["tp"]
            self.legs = [ctx.stop_entry("long", a + o, sl=a + o - sl, tp=a + o + tp),
                         ctx.stop_entry("short", a - o, sl=a - o + sl, tp=a - o - tp)]
            ctx.oco(*self.legs)
        elif t == "08:45":
            for x in self.legs:
                ctx.cancel(x)
        else:
            ctx.flatten("time")


def test_gc_matches_the_independent_nfp_engine_on_five_nfp_days():
    """GC has no tester bundle to match: the cross-check is nfp_lib.replay (an independent numpy replay of the same straddle on
    the ARCHIVE csv). Entries and TP / SL exits must agree to the cent; a time exit differs by convention (nfp_lib takes
    the last print at / before 09:55:00, the tester law the first print at / after it), so only the entry is compared there."""
    sys.path.append(str(S.REPO / "research" / "nfp-2026-10-02"))
    import nfp_lib as N
    days = [d for d, tag in N.events() if tag == "NFP" and d <= S.BUILD[1] and S.hb_tape_path(d, "GC") is not None][::6][:5]
    assert len(days) == 5 and all(d < S.EXAM_START for d in days)
    pv, tick = S.SPECS["GC"]
    seen = {"TP": 0, "SL": 0, "FLAT": 0, "NOFILL": 0}
    exact = grid_miss = 0
    for d in days:
        root, _, ev = N.load_event(("GC", d))
        ts, px = ev
        tp_ = S.load_tape(d, "GC")
        a, b = np.searchsorted(tp_.ts, [ts[0], ts[-1]])
        assert np.array_equal(tp_.ts[a:b + 1], ts) and np.array_equal(tp_.px[a:b + 1], px)        # the tape IS the archive file
        P = N.prep(d, ts, px)
        for off, sl, tp in ((1.0, 3.0, 6.0), (2.0, 5.0, 5.0), (4.0, 2.0, 4.0)):
            net, why = N.replay(P, off, sl, tp, tick, pv, 4.0, 1.0, 1.0, False)
            res = S.run_session(NfpStraddle({"off": off, "sl": sl, "tp": tp}), tp_)
            seen[why] += 1
            if why == "NOFILL":
                assert res.trades == []
                continue
            assert len(res.trades) == 1
            t = res.trades[0]
            assert t["exit_reason"] == {"TP": "tp", "SL": "sl", "FLAT": "time"}[why]
            assert t["order_price"] == pytest.approx(P["anchor"] + (off if t["side"] == "long" else -off), abs=1e-6)
            if why != "FLAT":
                assert t["gross"] == pytest.approx((1 if t["side"] == "long" else -1) * (t["exit_price"] - t["entry_price"]) * pv, abs=0.011)
                if abs(t["net"] - net) <= 0.011:
                    exact += 1
                else:
                    # nfp_lib compares floats exactly: its stop level fill -/+ sl lands a hair off the 0.1 grid (1936.6000000000001),
                    # misses a print AT the stop and triggers one tick later. The tester law (and l2sim) is tick-tolerant: it
                    # stops on that print, one tick ($10) better. Nothing else may differ.
                    assert why == "SL" and t["net"] - net == pytest.approx(tick * pv, abs=0.011), (d, off, sl, tp, why, t["net"], net)
                    grid_miss += 1
    assert seen["TP"] + seen["SL"] >= 5 and exact >= 5 and grid_miss <= 2      # the comparison had teeth
