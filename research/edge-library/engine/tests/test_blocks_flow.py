"""The DELTA filter blocks of engine/families/blocks.py (delta, cumdelta, sweep, bigorder) and engine/flowtab.py.

  (i)   flowtab turns the flow file's rows into the engine's minute grid: a hand-built file, DST included;
  (ii)  every block on a synthetic flow table with hand-computed answers: the window, the share, the size bar (median and
        80th percentile of the 20 reference dates), with / against, the series each block reads, the no-signal cases;
  (iii) NO LOOK-AHEAD: rows of the flow table from a decision on (and of any later date) change nothing decided up to it;
  (iv)  on real BUILD days: the flow file's minute volume is the engine's minute volume, the blocks give identical trades at
        1 and 8 workers on NQ, ES and GC, and two sides of a block never allow the same signal.
Real-day tests compare trades by equality and assert counts only: no net, win rate or profit factor is printed or read."""
import datetime as dt

import numpy as np
import pytest

import families
import flowtab as FT
import l2sim as S
import run_menus as RM
from families import blocks as B
from test_blocks import D, QUIET, W, daily_rows, days_of, flat_bars, minute_tape, ns, prior_dates, real_days

NMIN = FT.NMIN
START = 34200                                       # 09:30 ET, the NY sessions' anchor, seconds after 00:00
ROWS = {"delta": 1, "cumdelta": 1, "sweep": 2, "bigorder": 3}


def prefix(vol=0, delta=0, sweep=0, big=0):
    """A day's prefix sums [4, NMIN + 1] from per-minute series (scalars are held in every minute, or arrays of NMIN)."""
    day = np.stack([np.broadcast_to(np.asarray(x, np.int64), (NMIN,)) for x in (vol, delta, sweep, big)])
    return np.concatenate((np.zeros((4, 1), np.int64), np.cumsum(day, axis=1)), axis=1)


def minute_index(sec):
    return sec // 60 - FT.MIN0


def series_at(values: dict):
    """A per-minute array of NMIN zeros with {second after 00:00 ET: value} set (one value per minute starting there)."""
    a = np.zeros(NMIN, np.int64)
    for s, v in values.items():
        a[minute_index(s)] = v
    return a


def table(monkeypatch, today=None, ref_shares=None, root="NQ", volume=100):
    """A synthetic flow table: the 20 dates before D each with a constant per-minute delta of ref_shares[k] x volume (so that
    every window of that date has share ref_shares[k]), D with `today` = a dict of per-minute series (or None: no row)."""
    ref_shares = list(range(1, 21)) if ref_shares is None else ref_shares
    dates = prior_dates(len(ref_shares))
    tab = {iso: prefix(vol=volume, delta=int(round(s * volume / 100)) if False else s, sweep=s, big=s) for iso, s in zip(dates, ref_shares)}
    if today is not None:
        tab[D.isoformat()] = prefix(**today)
    monkeypatch.setattr(FT, "_table", lambda r: tab if r == root else {})
    return tab


class Probe(B.Blocks, S.Template):
    """Asks `allowed(go)` at every tf-bar close the Template allows an entry, and places nothing: the verdict of the block at
    EVERY decision, whatever a position or an order would have done to the next one."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()
    asked: list = []

    def fam_signal(self, ctx):
        type(self).asked.append(((ctx.now_ns - ns("00:00")) // S.NS, self.allowed(self.p["go"])))


def probe(params, tape, daily):
    """[(decision second after 00:00 ET, the block allows the entry)] of one session."""
    cls = type("P", (Probe,), {"asked": []})
    S.run_session(cls({"hold_to": "day", **QUIET, **params}), tape, daily=list(daily), on_error="raise")
    return list(cls.asked)


def attempts(log):
    return log


def run_mode(monkeypatch, block, mode, go, today, ref_shares=None, daily=None, root="NQ", n=120):
    """The verdicts [(decision second, allowed)] of an entry going `go` with one delta block on."""
    table(monkeypatch, today, ref_shares, root)
    return probe({"go": go, f"f_{block}": mode}, minute_tape(flat_bars(n), "09:00"), daily or daily_rows([100.0] * 20))


# ---- (i) flowtab ---------------------------------------------------------------------------------------------------------

def test_flowtab_puts_each_flow_row_on_the_engines_minute_grid(tmp_path, monkeypatch):
    import pandas as pd
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")

    def utc(d, hm):
        h, m = hm
        return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=et).timestamp())
    winter, summer = dt.date(2023, 1, 18), dt.date(2023, 7, 19)                 # EST and EDT
    rows = []
    for d in (winter, summer):
        for hm, v, dl, sb, ss, bo, bs in (((9, 30), 100, 30, 10, 4, 20, 1), ((9, 31), 50, -10, 0, 6, 12, -1), ((9, 32), 70, 20, 5, 0, 9, 1),
                                          ((18, 0), 10, 10, 0, 0, 5, 1), ((17, 30), 99, 99, 9, 0, 9, 1)):         # 17:30 is the break
            prev = d - dt.timedelta(days=1)
            rows.append({"t_utc": utc(prev if hm[0] >= 17 else d, hm), "session": d, "volume": v, "delta": dl, "sweep_buy_vol": sb,
                         "sweep_sell_vol": ss, "big_order": bo, "big_order_side": bs})
    pd.DataFrame(rows).to_parquet(tmp_path / "NQ.parquet")
    monkeypatch.setattr(FT, "FLOW", tmp_path)
    FT._table.cache_clear()
    try:
        for d in (winter, summer):
            iso = d.isoformat()
            # 09:30-09:33: volume 220, delta 40, net sweep (10-4) + (0-6) + (5-0) = 5, big 20 - 12 + 9 = 17
            assert FT.window("NQ", iso, START, START + 180) == (220, 40, 5, 17)
            assert FT.window("NQ", iso, START, START + 60) == (100, 30, 6, 20)          # one minute
            assert FT.window("NQ", iso, START + 60, START + 120) == (50, -10, -6, -12)
            assert FT.window("NQ", iso, START + 180, START + 240) == (0, 0, 0, 0)       # a minute without a print adds nothing
            assert FT.window("NQ", iso, -6 * 3600, -6 * 3600 + 60) == (10, 10, 0, 5)    # 18:00 of the evening before = index 0
            assert FT.window("NQ", iso, -6 * 3600 + 5 * 3600 // 10, START) is not None  # (a window inside the day is read)
            # the 17:30 minute of the previous day is outside the grid; a window outside the day is None
            assert FT.window("NQ", iso, 17 * 3600, 17 * 3600 + 60) is None and FT.window("NQ", iso, START, START) is None
        assert FT.window("NQ", "2023-01-19", START, START + 60) is None and FT.window("ES", winter.isoformat(), START, START + 60) is None
        assert FT.last_date("NQ") == summer.isoformat() and FT.last_date("ES") is None
    finally:
        FT._table.cache_clear()


# ---- (ii) every block, hand-computed ---------------------------------------------------------------------------------------------

# today's per-minute volume 100 everywhere; delta: minutes 09:30-09:34 +2 each (share +2 % ... see CASES), then as set below
REF = list(range(1, 21))                            # the 20 reference |shares| as the table makes them: 1 .. 20 (units of 1/100 of a % of volume)
MED, P80 = 10.5, 16.2                               # their median and 80th percentile (linear), hand-computed


def share_series(shares_by_minute: dict):
    """Per-minute delta of a day with volume 100 a minute: the share of a minute is its delta / 100."""
    return series_at({START + 60 * i: v for i, v in shares_by_minute.items()})


@pytest.mark.parametrize("block", ["delta", "sweep", "bigorder"])
def test_a_short_window_block_compares_the_5_minute_share_with_the_reference_bar_and_the_trades_direction(monkeypatch, block):
    series = {"delta": "delta", "sweep": "sweep", "bigorder": "big"}[block]
    # minutes 0-4 after 09:30: +12 each (share +12 %: above the median 10.5, below the 80th percentile 16.2);
    # minutes 5-9: +18 each (above both); minutes 10-14: +5 each (below both); minutes 15-19: -18 each (a big seller)
    per = {**{i: 12 for i in range(0, 5)}, **{i: 18 for i in range(5, 10)}, **{i: 5 for i in range(10, 15)}, **{i: -18 for i in range(15, 20)}}
    today = {"vol": 100, series: share_series(per)}
    seen = {}
    for mode in ("with", "against", "with_big", "against_big"):
        for go in ("long", "short"):
            seen[mode, go] = attempts_to_dict(run_mode(monkeypatch, block, mode, go, today))
    for s in range(START + 360, START + 1260, 60):             # every decision from 09:36 to 09:50 (a full window after the open)
        k = (s - START) // 60                                  # minutes completed since 09:30: the window is minutes k-5 .. k-1
        x = sum(per.get(i, 0) for i in range(k - 5, k)) / 5.0  # the share in % of volume (volume 100 a minute)
        if abs(x) == 0:
            continue
        for mode in ("with", "against", "with_big", "against_big"):
            for go in ("long", "short"):
                sd = 1 if go == "long" else -1
                bar = P80 if mode.endswith("big") else MED
                want = abs(x) >= bar and ((x * sd > 0) == mode.startswith("with"))
                assert seen[mode, go][s] == want, (block, mode, go, s, x)
    # the table really exercised both outcomes of each mode
    for mode in ("with", "against", "with_big", "against_big"):
        outs = {v for go in ("long", "short") for v in seen[mode, go].values()}
        assert outs == {True, False}, mode


def attempts_to_dict(att):
    return dict(att)


def test_cumdelta_reads_the_share_since_the_sessions_anchor(monkeypatch):
    # 09:30-09:39: +25 a minute; 09:40-09:59: -22 a minute. Cumulative share at decision k minutes after 09:30:
    per = {**{i: 25 for i in range(10)}, **{i: -22 for i in range(10, 30)}}
    today = {"vol": 100, "delta": share_series(per)}
    rows = {}
    for mode in ("with", "against", "with_big"):
        for go in ("long", "short"):
            rows[mode, go] = dict(run_mode(monkeypatch, "cumdelta", mode, go, today, n=100))
    n_with = 0
    for s in range(START + 120, START + 1740, 60):
        k = (s - START) // 60
        x = sum(per.get(i, 0) for i in range(k)) / k
        for mode in ("with", "against", "with_big"):
            for go in ("long", "short"):
                sd = 1 if go == "long" else -1
                bar = P80 if mode.endswith("big") else MED
                want = x != 0 and abs(x) >= bar and ((x * sd > 0) == mode.startswith("with"))
                assert rows[mode, go][s] == want, (mode, go, s, x)
                n_with += want
    assert n_with > 20
    # the first decision of the session (09:31) already holds one completed minute: +25 %, a signal for `with` / long and `against` / short
    assert rows["with", "long"][START + 60] is True and rows["against", "short"][START + 60] is True
    assert rows["with", "short"][START + 60] is False and rows["against", "long"][START + 60] is False


def test_each_block_reads_its_own_series_only(monkeypatch):
    loud = 30                                        # +30 a minute is above every reference bar
    for block, series in (("delta", "delta"), ("sweep", "sweep"), ("bigorder", "big")):
        for other in ("delta", "sweep", "big"):
            today = {"vol": 100, other: loud}
            rows = dict(run_mode(monkeypatch, block, "with", "long", today))
            late = [ok for s, ok in rows.items() if s >= START + 600]
            assert late and all(late) == (other == series) and any(late) == (other == series), (block, other)


def test_no_signal_blocks_both_sides(monkeypatch):
    today = {"vol": 100, "delta": 30, "sweep": 30, "big": 30}
    for block in ("delta", "cumdelta", "sweep", "bigorder"):
        for go in ("long", "short"):
            for mode in ("with", "against"):
                ok = [v for s, v in run_mode(monkeypatch, block, mode, go, today) if s >= START + 600]
                assert ok and (not any(ok)) == ((go == "long") != (mode == "with")), (block, go, mode)    # a signal: only the matching side
    # no row for today / fewer than 15 reference dates with volume / a zero share / a window without volume
    for mode in ("with", "against"):
        for go in ("long", "short"):
            assert not any(v for _, v in run_mode(monkeypatch, "delta", mode, go, None))                     # today has no flow
            assert not any(v for _, v in run_mode(monkeypatch, "delta", mode, go, today, ref_shares=REF[:14]))   # 14 reference dates
            assert not any(v for _, v in run_mode(monkeypatch, "delta", mode, go, {"vol": 100}))              # share exactly 0
            assert not any(v for _, v in run_mode(monkeypatch, "delta", mode, go, {"vol": 0, "delta": 0}))   # no volume
    # 15 reference dates are enough (they are the 15 latest of the 20)
    assert any(v for _, v in run_mode(monkeypatch, "delta", "with", "long", today, ref_shares=REF[:15], daily=daily_rows([100.0] * 15)))


def test_a_reference_date_without_volume_is_left_out_not_counted_as_zero(monkeypatch):
    today = {"vol": 100, "delta": 12}                # share 12 %: above the median of 1..20 (10.5) but not of 5..20 + five empty dates
    ok = [v for s, v in run_mode(monkeypatch, "delta", "with", "long", today) if s >= START + 600]
    assert ok and all(ok)
    tab = table(monkeypatch, today)
    for iso in prior_dates(20)[:5]:                  # five dates of the 20 trade nothing: 15 left, |shares| 6 .. 20, median 13
        tab[iso] = prefix()
    ok = [v for s, v in probe({"go": "long", "f_delta": "with"}, minute_tape(flat_bars(120), "09:00"), daily_rows([100.0] * 20)) if s >= START + 600]
    assert ok and not any(ok)                        # 12 < 13: the empty dates did not pull the median down


# ---- (iii) no look-ahead ---------------------------------------------------------------------------------------------------------

def test_no_look_ahead_flow_rows_from_a_decision_on_and_later_dates_change_nothing_before_it(monkeypatch):
    rng = np.random.default_rng(5)
    per = np.concatenate((rng.integers(10, 41, 15), -rng.integers(25, 46, 45)))     # buyers for 15 minutes, then sellers: every mode meets both outcomes
    today = {"vol": 100, "delta": share_series(dict(enumerate(per))), "sweep": share_series(dict(enumerate(per[::-1]))),
             "big": share_series(dict(enumerate(np.roll(per, 7))))}
    tape = minute_tape(flat_bars(120), "09:00")
    daily = daily_rows([100.0] * 20)
    for block in ("delta", "cumdelta", "sweep", "bigorder"):
        for mode in ("with", "against", "with_big"):
            params = {"go": "long", f"f_{block}": mode}
            table(monkeypatch, today)
            clean = probe(params, tape, daily)
            assert len({ok for _, ok in clean}) == 2, (block, mode)
            for cut in (START + 900, START + 1500, START + 2400):                      # 09:45, 09:55, 10:10
                tab = table(monkeypatch, today)
                k = minute_index(cut)
                d = tab[D.isoformat()].copy()
                d[:, k + 1:] += 10 ** 6 * np.arange(1, NMIN + 1 - k)                   # every minute from `cut` on rewritten
                tab[D.isoformat()] = d
                for later in ("2023-03-15", "2023-03-16"):                              # dates after D are never read
                    tab[later] = prefix(vol=10 ** 9, delta=10 ** 9, sweep=10 ** 9, big=10 ** 9)
                dirty = probe(params, tape, daily)
                assert [x for x in dirty if x[0] <= cut] == [x for x in clean if x[0] <= cut], (block, mode, cut)
                assert dirty != clean or cut >= START + 2400                            # the rewrite really was read after the cut


# ---- (iv) real BUILD days -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_the_flow_files_minute_volume_is_the_engines_minute_volume(root):
    real_days()
    FT._table.cache_clear()
    checked = 0
    for iso in days_of(root, 3):
        t = S.load_tape(iso, root)
        day = FT.day(root, iso)
        if t is None or day is None:
            pytest.skip(f"{root} {iso}: no tape or no flow row here")
        mine = np.diff(day[0])
        eng = B.minute_volume(t)
        diff = np.abs(mine - eng)
        assert diff.sum() <= 0.002 * eng.sum(), (root, iso, int(diff.sum()), int(eng.sum()))       # the same prints, to a rounding of the minute edge
        checked += 1
    assert checked == 3


def _flow_specs(root):
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0}
    out = []
    for blk in ("delta", "cumdelta", "sweep", "bigorder"):
        for mode in ("with", "against", "with_big", "against_big"):
            out.append((B.WRAPPED["donchian"], {**hd, "sess": "nyam", "n": 10, f"f_{blk}": mode}))
    out.append((B.WRAPPED["donchian"], {**hd, "sess": "nyam", "n": 10}))             # the same family with every block off
    return out


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_delta_blocks_on(root):
    real_days()
    FT._table.cache_clear()
    days = days_of(root)
    specs = _flow_specs(root)
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    assert a[0]["meta"]["workers"] == 1
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
    plain = {(t["entry_ms"], t["side"]) for t in a[-1]["trades"]}
    assert len(plain) >= 10
    against = 0
    for blk_i, blk in enumerate(("delta", "cumdelta", "sweep", "bigorder")):
        w, ag, wb, ab = ({(t["entry_ms"], t["side"]) for t in a[4 * blk_i + k]["trades"]} for k in range(4))
        assert w, blk                                                # a breakout meets buyers ahead of it often enough to trade
        # (no subset test: a blocked early signal frees the position for a later one the plain run could not take)
        assert not w & ag                                            # `with` and `against` never allow the same entry
        against += len(ag)
    assert against > 0                                               # (a breakout against the flow is rare: 10 days hold a few)
