"""BATCH 1 filter blocks of engine/families/blocks.py: ema20, ema50, trend, vwap, avwap, vwma, channel, adx, rvol and the strong RSI sides.

  (i)   each block against an INDEPENDENT calculation on synthetic minute bars: the verdict at EVERY decision of a session is what the
        reference says (EMA, VWMA, anchored and session VWAP, channel position, Wilder's ADX, RSI, relative volume);
  (ii)  the edges: a close exactly on the line, too few bars, too few reference dates, a median of 0, equality -> no signal on both sides;
  (iii) NO LOOK-AHEAD: prints from a decision on (and the reference days' later dates) change nothing decided up to it;
  (iv)  on real BUILD days the blocks give identical trades at 1 and 8 workers on NQ, ES and GC (counts only).
No net, win rate or profit factor is printed or read."""
import numpy as np
import pytest

import l2sim as S
from families import blocks as B
from test_blocks import (DAILY, QUIET, W, _profiles, daily_rows, days_of, garble, minute_tape, ns, prior_dates, rand_bars, real_days, rsi_ref)
from test_blocks_l2 import Probe

START = 34200                                       # 09:30 ET, seconds after 00:00
T0 = 8 * 3600                                       # the synthetic tape starts at 08:00 ET


def tape_of(bars, start="08:00"):
    return minute_tape(bars, start)


def probe(params, tape, daily=None):
    """{decision second: allowed} of one session (the block's verdict at EVERY decision, nothing placed)."""
    cls = type("P", (Probe,), {"asked": []})
    S.run_session(cls({"hold_to": "day", **QUIET, **params}), tape, daily=list(DAILY if daily is None else daily), on_error="raise")
    return dict(cls.asked)


def bars_until(bars, s, start=T0):
    """The minute bars completed at second s (a decision at a minute close): bars[:k]."""
    return bars[:(s - start) // 60]


def want_line(verdict_sd, close, line, mode):
    """The verdict of a price-vs-line block for one side: None = no signal."""
    if line is None or close == line:
        return False
    return ((close - line) * verdict_sd > 0) == (mode == "with")


BARS = rand_bars(300, seed=11, step=4.0)
TAPE = tape_of(BARS)


def decisions(got):
    return sorted(got)


# ---- (i) each block against an independent calculation -------------------------------------------------------------------------

def ema_ref(c, n):
    if len(c) < n:
        return None
    e = c[0]
    for x in c[1:]:
        e = e + (x - e) * 2.0 / (n + 1)
    return e


@pytest.mark.parametrize("n", [20, 50])
@pytest.mark.parametrize("go,sd", [("long", 1), ("short", -1)])
def test_the_ema_blocks_compare_the_close_with_the_emas_of_the_closed_bars(n, go, sd):
    outs = set()
    for mode in ("with", "against"):
        got = probe({"go": go, f"f_ema{n}": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            c = [b[3] for b in bars_until(BARS, s)]
            assert ok is want_line(sd, c[-1], ema_ref(c, n), mode), (n, mode, s)
            outs.add((mode, ok))
    assert outs == {("with", True), ("with", False), ("against", True), ("against", False)}


def test_the_trend_block_is_the_slope_of_the_ema50_and_vwap_is_the_sessions_vwap():
    for go, sd in (("long", 1), ("short", -1)):
        for mode in ("with", "against"):
            got = probe({"go": go, "f_trend": mode}, TAPE)
            for s, ok in got.items():
                c = [b[3] for b in bars_until(BARS, s)]
                e, ep = (None, None) if len(c) < 2 else (ema_ref_all(c), ema_ref_all(c[:-1]))
                want = ep is not None and ((e - ep) * sd > 0) == (mode == "with") and (e - ep) != 0
                assert ok is want, (go, mode, s)
            got = probe({"go": go, "f_vwap": mode}, TAPE)
            for s, ok in got.items():
                nyam = [(i, b) for i, b in enumerate(BARS[:(s - T0) // 60]) if T0 + 60 * i >= START]
                v = sum(b[4] for _, b in nyam)
                vw = sum(b[4] * (b[1] + b[2] + b[3]) / 3.0 for _, b in nyam) / v
                close = BARS[(s - T0) // 60 - 1][3]
                assert ok is (((close - vw) * sd > 0) == (mode == "with") and close != vw), (go, mode, s)


def ema_ref_all(c, n=50):
    e = c[0]
    for x in c[1:]:
        e = e + (x - e) * 2.0 / (n + 1)
    return e


@pytest.mark.parametrize("go,sd", [("long", 1), ("short", -1)])
def test_vwma_and_the_anchored_vwap(go, sd):
    for mode in ("with", "against"):
        got = probe({"go": go, "f_vwma": mode}, TAPE)
        for s, ok in got.items():
            b = bars_until(BARS, s)
            line = None if len(b) < 20 else sum(x[3] * x[4] for x in b[-20:]) / sum(x[4] for x in b[-20:])
            assert ok is want_line(sd, b[-1][3], line, mode), (mode, s)
        got = probe({"go": go, "f_avwap": mode}, TAPE)
        for s, ok in got.items():
            b = [x for i, x in enumerate(bars_until(BARS, s)) if T0 + 60 * i >= START]              # the anchor of the NY sessions: 09:30
            line = sum(x[4] * (x[1] + x[2] + x[3]) / 3.0 for x in b) / sum(x[4] for x in b)
            assert ok is want_line(sd, bars_until(BARS, s)[-1][3], line, mode), (mode, s)
    # an anchored VWAP of a midday instance still starts at 09:30
    got = probe({"go": "long", "f_avwap": "with", "sess": "mid"}, tape_of(BARS))
    assert got and any(got.values()) and not all(got.values())
    s = sorted(got)[3]
    b = [x for i, x in enumerate(bars_until(BARS, s)) if T0 + 60 * i >= START]
    line = sum(x[4] * (x[1] + x[2] + x[3]) / 3.0 for x in b) / sum(x[4] for x in b)
    assert got[s] is want_line(1, bars_until(BARS, s)[-1][3], line, "with")


@pytest.mark.parametrize("go,sd", [("long", 1), ("short", -1)])
def test_the_channel_block_reads_the_position_in_the_20_bars_before_the_signal_bar(go, sd):
    outs = set()
    for mode in ("with", "against"):
        got = probe({"go": go, "f_channel": mode}, TAPE)
        for s, ok in got.items():
            b = bars_until(BARS, s)
            if len(b) < 21:
                want = False
            else:
                hi, lo = max(x[1] for x in b[-21:-1]), min(x[2] for x in b[-21:-1])
                pos = (b[-1][3] - lo) / (hi - lo)
                top, bot = pos >= 2 / 3, pos <= 1 / 3
                want = (top if sd > 0 else bot) if mode == "with" else (bot if sd > 0 else top)
            assert ok is want, (mode, s)
            outs.add((mode, ok))
    assert outs == {("with", True), ("with", False), ("against", True), ("against", False)}


def adx_ref(H, L, C, n=14):
    """Wilder's ADX in the 'average' form (the toolkit uses the 'sum' form): DI = 100 x avg DM / avg TR, ADX = the smoothed DX."""
    H, L, C = (np.asarray(x, float) for x in (H, L, C))
    N = len(C)
    if N < 2 * n:
        return None
    up, dn = H[1:] - H[:-1], L[:-1] - L[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([H[1:] - L[1:], np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])])
    a_tr, a_p, a_m = tr[:n].mean(), pdm[:n].mean(), mdm[:n].mean()
    dx = []
    for i in range(n - 1, len(tr)):
        if i >= n:
            a_tr, a_p, a_m = (a_tr * (n - 1) + tr[i]) / n, (a_p * (n - 1) + pdm[i]) / n, (a_m * (n - 1) + mdm[i]) / n
        pi, mi = (0.0, 0.0) if a_tr <= 0 else (100 * a_p / a_tr, 100 * a_m / a_tr)
        dx.append(0.0 if pi + mi == 0 else 100 * abs(pi - mi) / (pi + mi))
    a = float(np.mean(dx[:n]))
    for x in dx[n:]:
        a = (a * (n - 1) + x) / n
    return a


def test_adx_is_wilders_adx_and_the_block_has_a_dead_zone_between_20_and_25():
    # the function against the independent form on several walks
    for seed in range(6):
        bars = rand_bars(200, seed=seed + 40, step=2.0 + seed)
        H, L, C = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
        for k in (28, 29, 40, 100, 200):
            assert abs(B.adx_last(H[:k], L[:k], C[:k]) - adx_ref(H[:k], L[:k], C[:k])) < 1e-9, (seed, k)
        assert B.adx_last(H[:27], L[:27], C[:27]) is None and adx_ref(H[:27], L[:27], C[:27]) is None
    # a straight rise is a trend (ADX near 100); a sawtooth is not
    up = [(100 + i, 100.5 + i, 99.5 + i, 100.2 + i) for i in range(60)]
    saw = [(100, 101, 99, 100 + (1 if i % 2 else -1) * 0.2) for i in range(60)]
    assert B.adx_last([b[1] for b in up], [b[2] for b in up], [b[3] for b in up]) > 90
    assert B.adx_last([b[1] for b in saw], [b[2] for b in saw], [b[3] for b in saw]) < 15
    # the block: strong >= 25, weak < 20, between: no signal on either side
    seen = set()
    for mode in ("strong", "weak"):
        for go in ("long", "short"):
            got = probe({"go": go, "f_adx": mode}, TAPE)
            for s, ok in got.items():
                b = bars_until(BARS, s)
                a = adx_ref([x[1] for x in b], [x[2] for x in b], [x[3] for x in b])
                want = bool(a is not None and (a >= 25.0 if mode == "strong" else a < 20.0))
                assert ok is want, (mode, s, a)
                seen.add((mode, ok, a is not None and 20 <= a < 25))
    assert ("strong", True, False) in seen and ("strong", False, False) in seen and ("weak", True, False) in seen
    assert ("strong", False, True) in seen and ("weak", False, True) in seen          # the dead zone blocks both modes


@pytest.mark.parametrize("go,sd", [("long", 1), ("short", -1)])
def test_the_strong_rsi_sides(go, sd):
    for mode in ("strong_with", "extreme_against", "with", "against"):
        got = probe({"go": go, "f_rsi": mode}, TAPE)
        n = 0
        for s, ok in got.items():
            r = rsi_ref([b[3] for b in bars_until(BARS, s)])
            d = None if r is None else (r - 50.0) * sd
            want = bool(d is not None and (d >= 10 if mode == "strong_with" else d <= -20 if mode == "extreme_against" else d > 0 if mode == "with" else d < 0))
            assert ok is want, (mode, s, r)
            n += ok
        assert n > 0 or mode == "extreme_against" and go == "short"


def test_rvol_compares_the_closed_bar_with_the_same_clock_bar_of_the_14_dates_before(monkeypatch):
    # 20 prior dates; the last 14 trade 100 .. 113 contracts a minute (median 106.5): the older 6 trade 5000 and must not count
    per = [5000] * 6 + [100 + k for k in range(14)]
    dates = prior_dates(20)
    memo = {("NQ", iso): np.concatenate(([0], np.cumsum(np.full(B.NMIN, v, np.int64)))) for iso, v in zip(dates, per)}
    monkeypatch.setattr(B, "_CUM", memo)
    daily = daily_rows([100.0] * 20)
    # today: minute volumes 40 -> 400 in steps; the bar is one minute (tf 1) or five (tf 5)
    vols = [4 * (10 + (7 * i) % 100) for i in range(150)]                              # 40 .. 436, multiples of 4
    bars = [(15000.0, 15000.25, 15000.0, 15000.0, v) for v in vols]
    tape = tape_of(bars, "09:00")
    for tf in (1, 5):
        med = 106.5 * tf
        for mode in ("high", "low", "spike"):
            got = probe({"go": "long", "f_rvol": mode, "tf": str(tf)}, tape, daily)
            assert got
            outs = set()
            for s, ok in got.items():
                today = sum(vols[(s - 32400) // 60 - tf:(s - 32400) // 60])               # the tf bar that just closed
                want = today > med if mode == "high" else today < med if mode == "low" else today >= 2 * med
                assert ok is want, (tf, mode, s, today, med)
                outs.add(ok)
            assert outs == {True, False}, (tf, mode)
    # fewer than 10 reference dates, a median of 0, equality: no signal on either mode
    for keep, why in ((9, "nine dates"), (0, "none")):
        kept = set(list(memo)[len(memo) - keep:]) if keep else set()                    # (a date without a tape is None in the memo)
        monkeypatch.setattr(B, "_CUM", {k: (v if k in kept else None) for k, v in memo.items()})
        for mode in ("high", "low", "spike"):
            assert not any(probe({"go": "long", "f_rvol": mode}, tape, daily).values()), why
    monkeypatch.setattr(B, "_CUM", {k: np.zeros(B.NMIN + 1, np.int64) for k in memo})
    assert not any(probe({"go": "long", "f_rvol": "high"}, tape, daily).values())
    ten = {k: (v if k in list(memo)[-10:] else None) for k, v in memo.items()}         # exactly 10 are enough
    monkeypatch.setattr(B, "_CUM", ten)
    assert any(probe({"go": "long", "f_rvol": "high"}, tape, daily).values())


def test_rvol_reads_prior_dates_only(monkeypatch):
    per = [100 + k for k in range(20)]
    dates = prior_dates(20)
    memo = {("NQ", iso): np.concatenate(([0], np.cumsum(np.full(B.NMIN, v, np.int64)))) for iso, v in zip(dates, per)}
    monkeypatch.setattr(B, "_CUM", memo)
    daily = daily_rows([100.0] * 20)
    bars = [(15000.0, 15000.25, 15000.0, 15000.0, 4 * (10 + (7 * i) % 100)) for i in range(150)]
    tape = tape_of(bars, "09:00")
    clean = probe({"go": "long", "f_rvol": "high"}, tape, daily)
    memo[("NQ", "2023-03-14")] = np.concatenate(([0], np.cumsum(np.full(B.NMIN, 10 ** 9, np.int64))))
    memo[("NQ", "2023-03-15")] = memo[("NQ", "2023-03-14")]
    assert probe({"go": "long", "f_rvol": "high"}, tape, daily) == clean                 # today's and later dates' rows are never read


# ---- (iii) no look-ahead ------------------------------------------------------------------------------------------------------------

NEW = [{"f_ema20": "with"}, {"f_ema50": "against"}, {"f_vwma": "with"}, {"f_avwap": "against"}, {"f_channel": "with"}, {"f_channel": "against"},
       {"f_adx": "strong"}, {"f_adx": "weak"}, {"f_rsi": "strong_with"}, {"f_rsi": "extreme_against"}, {"f_trend": "with"}, {"f_vwap": "with"}]


def test_no_look_ahead_prints_from_a_decision_on_change_nothing_decided_before(monkeypatch):
    daily = _profiles(monkeypatch, [40 + 4 * k for k in range(20)])
    monkeypatch.setitem(B._CUM, ("NQ", "2023-03-14"), np.zeros(B.NMIN + 1, np.int64) + 10 ** 12)         # today's own row is poison
    for extra in NEW + [{"f_rvol": "high"}, {"f_rvol": "spike"}]:
        for go in ("long", "short"):
            clean = probe({"go": go, **extra}, TAPE, daily)
            assert len(set(clean.values())) == 2 or extra.get("f_adx") == "weak" or extra.get("f_rvol") or extra.get("f_rsi") == "extreme_against", extra
            for cut in (ns("09:47"), ns("10:20:30"), ns("10:51")):
                dirty = probe({"go": go, **extra}, garble(TAPE, cut), daily)
                c = (cut - ns("00:00")) // S.NS
                assert {s: v for s, v in dirty.items() if s <= c} == {s: v for s, v in clean.items() if s <= c}, (extra, go, cut)


# ---- (iv) real days -------------------------------------------------------------------------------------------------------------------

def _specs():
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "sess": "nyam", "n": 10}
    out = [(B.WRAPPED["donchian"], {**hd, **x}) for x in NEW + [{"f_rvol": "high"}, {"f_rvol": "low"}, {"f_rvol": "spike"}]]
    return out + [(B.WRAPPED["donchian"], hd)]


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_batch_1_blocks_on(root):
    real_days()
    days = days_of(root)
    specs = _specs()
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        n += len(x["trades"])
    assert len(a[-1]["trades"]) >= 10 and n > len(a[-1]["trades"])
    # a filter that blocks nothing is the plain family; one that blocks something trades less than 'everything it could'
    assert any(len(x["trades"]) != len(a[-1]["trades"]) for x in a[:-1])
