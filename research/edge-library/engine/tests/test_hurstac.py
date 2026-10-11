"""hurstac: the two indicators against independent numpy calculations, the registry entry, the rule's defaults (the sheet's numbers)."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from families import hurstac as H          # noqa: E402


def _walk(n, seed, drift=0.0):
    r = np.random.default_rng(seed)
    return list(100 + np.cumsum(r.normal(drift, 1.0, n)))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_hurst_matches_numpy(seed):
    C = _walk(80, seed)
    win, k = 20, 5
    a = np.array(C)
    d1 = np.diff(a)[-win:]
    dk = (a[k:] - a[:-k])[-win:]
    want = 100 * 0.5 * math.log((dk ** 2).mean() / (d1 ** 2).mean()) / math.log(k)
    want = min(100.0, max(0.0, want))
    assert H.hurst_proxy(C, win, k) == pytest.approx(want, rel=1e-9)


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_autocorr_matches_numpy(seed):
    C = _walk(80, seed)
    win, lag = 20, 5
    d = np.diff(np.array(C))
    x, y = d[-win:], d[-win - lag:-lag]
    assert H.autocorr(C, win, lag) == pytest.approx(float(np.corrcoef(x, y)[0, 1]), rel=1e-9)


def test_warm_and_flat_series_are_none():
    assert H.hurst_proxy([1.0] * 10, 20, 5) is None and H.autocorr([1.0] * 10, 20, 5) is None
    assert H.hurst_proxy([5.0] * 60, 20, 5) is None and H.autocorr([5.0] * 60, 20, 5) is None


def test_trend_is_persistent_noise_is_not():
    up = list(np.linspace(100, 200, 80) + np.random.default_rng(1).normal(0, 0.2, 80))
    assert H.hurst_proxy(up, 20, 5) > 50
    assert H.hurst_proxy(list(np.linspace(100, 200, 80)), 20, 5) == pytest.approx(100.0)   # a straight line
    zig = [100 + (i % 2) for i in range(80)]            # strictly alternating: anti-persistent
    assert H.hurst_proxy(zig, 20, 5) < 50
    walks = [H.hurst_proxy(_walk(400, s), 20, 5) for s in range(40)]
    assert 40 < float(np.mean(walks)) < 62               # a random walk sits near 50 (the proxy is noisy on 20 bars)


def test_registered_with_the_sheets_numbers():
    import families
    assert families.ERRORS == {}
    e = families.REGISTRY["hurst_ac_break"]
    d = e[0].defaults()
    assert (d["h_min"], d["ac_max"], d["h_win"], d["h_k"], d["ac_win"], d["ac_lag"], d["brk_n"], d["atr_n"]) == (50.0, -0.1, 20, 5, 20, 5, 5, 20)
    assert (d["stop_atr"], d["tgt_r"], d["dir"], d["hold_to"], d["stop_mode"]) == (4.0, 1.25, "long", "day", "struct")
    assert tuple(e[0].FEATURES) == ()


# ---- the trailing stop on a synthetic day (no Hurst / autocorrelation: the filters are off, so only the 5-bar break and the exits are tested)
import datetime as dt                                   # noqa: E402
import l2sim as S                                       # noqa: E402
from test_blocks import D, TICK, minute_tape, rand_bars  # noqa: E402

BASE = {"hold_to": "day", "tf": "15", "sess": "nyam", "use_h": "off", "use_ac": "off", "dir": "long", "max_tr": 3}


def _day_bars(trail_after: str):
    """00:00-06:29 a seeded random walk (warm), then 15 minutes of +1.5 a minute (the break), 45 minutes of +0.4 (a stall below the
    5 ATR target), then a sell-off of -3 a minute; flat to 15:59."""
    b = rand_bars(390, 11, step=2.0)
    px = b[-1][3]
    for n, step in ((15, 1.5), (45, 0.4), (90, -3.0)):
        for i in range(n):
            o, c = px, px + step
            b.append((o, max(o, c) + TICK, min(o, c) - TICK, c, 40))
            px = c
    return b + [(px, px + TICK, px - TICK, px, 40)] * (960 - len(b))


def _run(params):
    bars = _day_bars("")
    tape = minute_tape(bars, "00:00", D)
    st = hurstac_cls()({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape, daily=[], on_error="raise")
    return st, res


def hurstac_cls():
    return H.HurstAcBreak


def test_trailing_stop_rises_with_the_highs_and_never_falls():
    _, on = _run({"trail": "on"})
    _, off = _run({"trail": "off"})
    ton, toff = on.trades, off.trades
    assert ton and toff, (len(ton), len(toff))
    a, b = ton[0], toff[0]
    assert a["entry_price"] == b["entry_price"]
    assert b["sl"] < a["entry_price"] < b["tp"] or b["exit_reason"] in ("sl", "tp", "eod")
    assert a["sl"] > b["sl"], (a["sl"], b["sl"])                  # trailed up: the closing stop is above the initial one
    assert a["exit_reason"] == "sl" and a["net"] > b["net"]       # the rally's profit is kept on the way down
