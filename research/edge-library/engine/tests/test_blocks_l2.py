"""The LEVEL-2 filter blocks of engine/families/blocks.py (book, depth, ahead, wall, stack) and engine/bpfeat.py (the build range's table).

  (i)   every block on a hand-built feature table: what each side allows, at the thresholds, and no signal on NaN / a stale row;
  (ii)  NO LOOK-AHEAD: feature rows not yet usable at a decision change nothing decided up to it;
  (iii) bpfeat: the loader carries the blueprint BUILD seal (2025-07-01 raises, before a row is read), the table ends with the last
        build day, the 2025 first half joins the 2024 table without a seam, and the blocks give identical trades at 1 and 8 workers
        on real days of 2024 and of 2025's first half.
Real-day tests compare trades by equality and assert counts only: no net, win rate or profit factor is printed or read."""
import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

import bpfeat
import l2data as D
import l2sim as S
from families import blocks as B
from test_blocks import QUIET, W, flat_bars, minute_tape, ns, real_days

START = 34200


def table(cols: dict, start="08:55", end="11:05"):
    """One row per minute stamped [start, end), usable 60 s after its stamp; cols = {name: f(hh:mm) -> value} (t_utc is the stamp)."""
    m0 = np.arange(ns(start), ns(end), S.MIN_NS, dtype=np.int64)
    hhmm = [dt.datetime.fromtimestamp(t / 1e9, S.ET).strftime("%H:%M") for t in m0]
    out = {"t_utc": (m0 // S.NS).astype(np.int64)}
    for k, fn in cols.items():
        out[k] = np.array([fn(h) for h in hhmm], np.float32)
    return S.Features(m0 + S.MIN_NS, out)


class Probe(B.Blocks, S.Template):
    """Asks allowed(go) at every tf-bar close of the session and places nothing (the block's verdict at EVERY decision)."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()
    asked: list = []

    def fam_signal(self, ctx):
        type(self).asked.append(((ctx.now_ns - ns("00:00")) // S.NS, self.allowed(self.p["go"])))


def probe(params, feats, n=120):
    cls = type("P", (Probe,), {"asked": []})
    S.run_session(cls({"hold_to": "day", **QUIET, **params}), minute_tape(flat_bars(n), "09:00"), daily=[], features=feats, on_error="raise")
    return dict(cls.asked)


def hhmm(s):
    return dt.datetime.fromtimestamp(ns("00:00") / 1e9 + s, S.ET).strftime("%H:%M")


NAN = float("nan")


# ---- (i) every block ---------------------------------------------------------------------------------------------------------

def test_the_wall_block_looks_at_the_opposing_side_within_8_ticks_at_5_times_the_median():
    # asks: a wall of 50 (median 10 = exactly 5 x) 8 ticks away from 09:40 on, 9 ticks away from 10:00 on, a 49 wall at 10:20 on;
    # bids: no wall until 10:30
    def ask_sz(h): return 50 if "09:40" <= h < "10:20" else 49 if "10:20" <= h < "10:30" else 12
    def ask_d(h): return 8 if "09:40" <= h < "10:00" else 9 if "10:00" <= h < "10:20" else 3
    f = table({"ask_wall_sz": ask_sz, "ask_med_sz": lambda h: 10, "ask_wall_dist": ask_d,
               "bid_wall_sz": lambda h: 60 if h >= "10:30" else 12, "bid_med_sz": lambda h: 10, "bid_wall_dist": lambda h: 2})
    rows = {(m, go): probe({"go": go, "f_wall": m}, f) for m in ("clear", "blocked") for go in ("long", "short")}
    for s in sorted(rows['blocked', 'long']):
        h = hhmm(s - 60)                              # the row stamped a minute before the decision is the newest usable
        wall_ahead_long = "09:40" <= h < "10:00"      # exactly 5 x and exactly 8 ticks: a wall; 9 ticks: not; 49 < 5 x 10: not
        wall_ahead_short = h >= "10:30"
        for go, w in (("long", wall_ahead_long), ("short", wall_ahead_short)):
            assert rows["blocked", go][s] is w and rows["clear", go][s] is (not w), (go, h)
    # no signal: a NaN field, a median of 0, a stale table -> both sides blocked
    for bad in ({"ask_wall_sz": lambda h: NAN}, {"ask_med_sz": lambda h: 0}, {"ask_wall_dist": lambda h: NAN}):
        g = table({"ask_wall_sz": lambda h: 50, "ask_med_sz": lambda h: 10, "ask_wall_dist": lambda h: 3, **bad})
        for m in ("clear", "blocked"):
            assert not any(probe({"go": "long", "f_wall": m}, g).values())
    stale = table({"ask_wall_sz": lambda h: 50, "ask_med_sz": lambda h: 10, "ask_wall_dist": lambda h: 3}, end="09:20")
    assert not any(probe({"go": "long", "f_wall": "blocked"}, stale).values()) and not any(probe({"go": "long", "f_wall": "clear"}, stale).values())
    assert not any(probe({"go": "long", "f_wall": "clear"}, None).values())


def test_the_stack_block_reads_the_minutes_size_change_on_the_trades_side_against_5_percent_of_the_depth():
    depth = 100
    # bids +6 / asks 0 (x = +0.06) until 09:50, bids +5 / asks 0 (exactly 0.05) until 10:00, bids 0 / asks +7 (x = -0.07) until 10:10,
    # a +4 / -0 change (0.04: too small for either) after
    def bc(h): return 6 if h < "09:50" else 5 if h < "10:00" else 0 if h < "10:10" else 4
    def ac(h): return 0 if h < "09:50" or h >= "10:10" else 0 if h < "10:00" else 7
    f = table({"bid10_chg": bc, "ask10_chg": ac, "depth10": lambda h: depth})
    for mode in ("with", "against"):
        for go, sd in (("long", 1), ("short", -1)):
            got = probe({"go": go, "f_stack": mode}, f)
            for s in sorted(got):
                h = hhmm(s - 60)
                x = (bc(h) - ac(h)) * sd / depth
                want = x >= 0.05 - 1e-9 if mode == "with" else x <= -0.05 + 1e-9
                assert got[s] is want, (mode, go, h, x)
    assert any(probe({"go": "long", "f_stack": "with"}, f).values()) and any(probe({"go": "short", "f_stack": "with"}, f).values())
    for bad in ({"bid10_chg": lambda h: NAN}, {"depth10": lambda h: 0}, {"depth10": lambda h: NAN}):
        g = table({"bid10_chg": lambda h: 9, "ask10_chg": lambda h: 0, "depth10": lambda h: 100, **bad})
        for m in ("with", "against"):
            assert not any(probe({"go": "long", "f_stack": m}, g).values())


def test_the_ahead_block_is_the_templates_thin_ahead_and_its_mirror():
    # long: the offers ahead (ask10_rel15 = ratio - 1); short: the bids. ratio 0.8 is inside "thin" (the SPEC's <= 0.8)
    f = table({"ask10_rel15": lambda h: -0.2 if h < "09:50" else 0.3 if h < "10:10" else NAN, "bid10_rel15": lambda h: 0.5 if h < "10:00" else -0.4})
    for go in ("long", "short"):
        thin, thick = probe({"go": go, "f_ahead": "thin"}, f), probe({"go": go, "f_ahead": "thick"}, f)
        for s in sorted(thin):
            h = hhmm(s - 60)
            v = (-0.2 if h < "09:50" else 0.3 if h < "10:10" else NAN) if go == "long" else (0.5 if h < "10:00" else -0.4)
            want = None if v != v else 1.0 + v <= 0.8 + 1e-6
            assert thin[s] is (want is True) and thick[s] is (want is False), (go, h, v)
    assert any(probe({"go": "long", "f_ahead": "thin"}, f).values()) and any(probe({"go": "long", "f_ahead": "thick"}, f).values())


def test_the_depth_block_is_the_templates_regime_filter():
    f = table({"depth10_rel20d": lambda h: -0.3 if h < "09:50" else 0.0 if h < "10:10" else 0.25})
    for go in ("long", "short"):
        thin, thick = probe({"go": go, "f_depth": "thin"}, f), probe({"go": go, "f_depth": "thick"}, f)
        for s in sorted(thin):
            h = hhmm(s - 60)
            assert thin[s] is (h < "09:50") and thick[s] is (h >= "10:10"), (go, h)
    assert B.FILTERS["depth"] == {"thin": {"f_depth": "thin"}, "thick": {"f_depth": "thick"}}


def test_no_look_ahead_in_the_level_2_blocks_rows_not_yet_usable_change_nothing_decided_before():
    rng = np.random.default_rng(3)

    def rnd(lo, hi): return lambda h, r=np.random.default_rng(int(rng.integers(1 << 30))), cache={}: cache.setdefault(h, float(r.uniform(lo, hi)))
    cols = {"ask_wall_sz": rnd(0, 80), "ask_med_sz": lambda h: 10, "ask_wall_dist": rnd(0, 12), "bid_wall_sz": rnd(0, 80), "bid_med_sz": lambda h: 10,
            "bid_wall_dist": rnd(0, 12), "bid10_chg": rnd(-12, 12), "ask10_chg": rnd(-12, 12), "depth10": lambda h: 100, "ask10_rel15": rnd(-0.6, 0.6),
            "bid10_rel15": rnd(-0.6, 0.6), "depth10_rel20d": rnd(-0.5, 0.5), "imb10": rnd(-0.5, 0.5)}
    f = table(cols)
    for extra in ({"f_wall": "clear"}, {"f_wall": "blocked", "go": "short"}, {"f_stack": "with"}, {"f_stack": "against", "go": "short"},
                  {"f_ahead": "thin"}, {"f_ahead": "thick", "go": "short"}, {"f_depth": "thin"}, {"f_bookopp": "on"}, {"f_book": "on"}):
        clean = probe(extra, f)
        assert len(set(clean.values())) == 2, extra
        for cut in (START + 1500, START + 2700, START + 3900):
            late = f.usable_ns > ns("00:00") + cut * S.NS
            g = np.random.default_rng(9)
            c2 = {k: v.copy() for k, v in f.cols.items() if k != "t_utc"}
            for k in c2:
                c2[k][late] = g.uniform(-100, 100, int(late.sum())).astype(np.float32)
            c2["t_utc"] = f.cols["t_utc"]
            dirty = probe(extra, S.Features(f.usable_ns, c2))
            assert {s: v for s, v in dirty.items() if s <= cut} == {s: v for s, v in clean.items() if s <= cut}, (extra, cut)


# ---- (iii) bpfeat: the build range's table ---------------------------------------------------------------------------------------

def test_the_loader_carries_the_build_seal_and_refuses_any_other_switch():
    f = bpfeat.BpL2Features(B.BOOK_COLS)
    assert f.allow_holdout == S.ALLOW_BP and f.columns == tuple(B.BOOK_COLS)
    with pytest.raises(S.HoldoutSealed):
        f(dt.date(2025, 7, 1))                       # the first test day: refused before any row is read
    with pytest.raises(S.HoldoutSealed):
        f(dt.date(2026, 3, 2))
    for other in (True, False, S.ALLOW_BT, "check"):
        with pytest.raises(S.HoldoutSealed):
            bpfeat.BpL2Features(B.BOOK_COLS, other)
    import pickle
    assert pickle.loads(pickle.dumps(f)).columns == f.columns and "bp_build" in repr(f)


def test_the_build_table_ends_with_the_last_build_day_and_joins_2024_without_a_seam():
    if not bpfeat.cache_file().exists():
        pytest.skip("the 2025 first-half table is not built here (python engine/bpfeat.py)")
    df = D.load_features(S.TABLE_START, bpfeat.BUILD_END, allow_holdout=True, columns=["imb10", "depth10", "depth10_rel20d", "bid10_chg", "t_utc"])
    assert df["date"].max() == bpfeat.BUILD_END and df.index.is_monotonic_increasing and not df.index.has_duplicates
    assert df.index.max() <= pd.Timestamp("2025-06-30 21:00", tz="UTC")                        # nothing after 17:00 ET of the last build day
    t = df["t_utc"].to_numpy()
    gap = np.diff(t[(t > 0) & ~np.isnan(t)].astype(np.int64))
    assert gap.min() > 0                              # strictly increasing minutes: nothing doubled at the 2024 / 2025 join
    jan = df[(df["date"] >= dt.date(2025, 1, 2)) & (df["date"] <= dt.date(2025, 1, 10))]
    dec = df[(df["date"] >= dt.date(2024, 12, 16)) & (df["date"] <= dt.date(2024, 12, 24))]
    assert len(jan) > 5000 and len(dec) > 5000
    # the 20-session median (depth10_rel20d) and the one-minute change (bid10_chg) are warm across the join
    for c in ("depth10_rel20d", "bid10_chg", "imb10"):                # (the share of rows with a valid book is ~54 % of all rows: weekends, breaks, roll days)
        assert jan[c].notna().mean() > 0.8 * dec[c].notna().mean() > 0.3, c


def test_the_phase_check_of_the_2025_first_half_is_persisted():
    import json
    pg = json.loads(D.PHASE_GUARD.read_text())
    assert set(bpfeat.BUILD_MONTHS) <= set(pg["months"]), "run engine/bpfeat.py: the months are checked and persisted by it"


def _specs():
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "sess": "nyam", "n": 10}
    out = [(B.WRAPPED["donchian"], {**hd, **x}) for x in ({"f_wall": "clear"}, {"f_wall": "blocked"}, {"f_stack": "with"}, {"f_stack": "against"},
                                                         {"f_ahead": "thin"}, {"f_ahead": "thick"}, {"f_depth": "thin"}, {"f_depth": "thick"},
                                                         {"f_book": "on"}, {"f_bookopp": "on"}, {})]
    return out


def test_identical_trades_at_1_and_8_workers_on_days_of_2024_and_of_2025s_first_half():
    real_days()
    if not bpfeat.cache_file().exists():
        pytest.skip("the 2025 first-half table is not built here")
    have = {d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)}
    days = [d for d in ("2024-03-12", "2024-06-18", "2024-11-14", "2025-01-14", "2025-02-20", "2025-03-25", "2025-04-30", "2025-06-12", "2025-06-30")
            if d in have]
    assert len(days) >= 8
    specs = _specs()
    f = bpfeat.BpL2Features(B.BOOK_COLS)
    a = S.run_many(specs, period=S.ALLOW_BP, days=days, root="NQ", workers=1, features=f)
    b = S.run_many(specs, period=S.ALLOW_BP, days=days, root="NQ", workers=W, features=f)
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        n += len(x["trades"])
    assert n > 0 and len(a[-1]["trades"]) > 0
    assert a[0]["meta"]["range"]["period"] == S.ALLOW_BP
    # the month check was enforced: 2025's months are all in the persisted file, so no run was refused for them
    assert not any(x["no_trade"] for x in a[:1] if any("PhaseGuard" in str(r) for r in x["no_trade"]))
    # the test day is refused by the engine whatever the loader says
    with pytest.raises(S.HoldoutSealed):
        S.run_many(specs[:1], period=S.ALLOW_BP, days=["2025-07-01"], root="NQ", workers=1, features=f)
    # a Level-2 table is NQ only
    with pytest.raises(ValueError):
        S.run_many(specs[:1], period=S.ALLOW_BP, days=["2024-03-12"], root="ES", workers=1, features=f)
