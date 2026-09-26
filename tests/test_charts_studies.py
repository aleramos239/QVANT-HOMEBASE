"""Studies: incremental == full recompute, preview never commits, ADX pinned to the house gate."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from homebase.charts.bars import Bar, BarSpec, build
from homebase.charts.studies import (ADX, EMA, SMA, VWAP, VWMA, CumDelta, Levels, Profile,
                                     make, profile_from)
from homebase.charts.tick import BUY, SELL, Tick
from homebase.gate import adx_series
from tests.charts_util import D, session_ms

TS = 0.25


def bar(c, v=1, session="2026-09-24", t=0, h=None, l=None, o=None):
    return Bar(t=t, session=session, o=c if o is None else o, h=c if h is None else h,
               l=c if l is None else l, c=c, v=v)


def test_preview_values_the_developing_bar_without_committing():
    e = EMA(3)
    e.push(bar(10.0))
    s = e.state
    assert e.preview(bar(20.0)) == e.preview(bar(20.0)) == 10.0 + (20.0 - 10.0) * 0.5
    assert e.state == s


def test_sma_ema_vwma_values():
    sma, ema, vwma = SMA(3), EMA(3), VWMA(2)
    got = [(sma.push(b), ema.push(b), vwma.push(b)) for b in
           (bar(1.0, 1), bar(2.0, 3), bar(3.0, 1), bar(4.0, 1))]
    assert [g[0] for g in got] == [None, None, 2.0, 3.0]
    assert [g[1] for g in got] == [1.0, 1.5, 2.25, 3.125]           # alpha 0.5, seeded with the first close
    assert [g[2] for g in got] == [None, 1.75, 2.25, 3.5]


def test_vwap_is_exact_from_every_trade_and_resets_each_session():
    m = session_ms(D, 9, 30)
    ticks = [Tick(m + i * 20_000, 100 + (i % 4) * 0.25, 1 + i % 3, BUY, i) for i in range(20)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    v = VWAP()
    vals = [v.push(b) for b in closed]
    done = [t for t in ticks if t.ts_ms < closed[-1].t + 60_000]
    want = sum(t.price * t.size for t in done) / sum(t.size for t in done)
    assert vals[-1]["vwap"] == pytest.approx(want, abs=1e-9) and vals[-1]["sd"] > 0
    nxt = bar(50.0, session="2026-09-25")
    nxt.pv, nxt.p2v, nxt.v = 50.0, 2500.0, 1
    assert v.push(nxt) == {"vwap": 50.0, "sd": 0.0}


def test_rth_vwap_ignores_the_overnight():
    v = VWAP("rth")
    on = bar(10.0, t=session_ms(D, 3, 0))
    on.pv, on.v = 10.0, 1
    rth = bar(20.0, t=session_ms(D, 9, 30))
    rth.pv, rth.p2v, rth.v = 20.0, 400.0, 1
    assert v.push(on) is None
    assert v.push(rth)["vwap"] == 20.0


def test_adx_matches_the_house_gate_bit_for_bit():
    fix = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())
    ref = adx_series(fix["bars"])
    st = ADX(14)
    got = []
    for i, x in enumerate(fix["bars"]):
        v = st.push(Bar(t=i, session="s", o=x["c"], h=x["h"], l=x["l"], c=x["c"]))
        got.append(None if v is None else v["adx"])
    assert got == ref


def test_cum_delta_resets_each_session():
    cd = CumDelta()
    a = bar(1.0); a.buy, a.sell = 5, 2
    b = bar(1.0); b.buy, b.sell = 1, 4
    c = bar(1.0, session="2026-09-25"); c.buy, c.sell = 2, 0
    assert [cd.push(x) for x in (a, b, c)] == [3, 0, 2]


def test_levels_prior_session_overnight_and_rth_open():
    p = D - dt.timedelta(days=1)
    bars = [bar(105, session=p.isoformat(), t=session_ms(p, 10, 0), h=110, l=100),
            bar(104, t=session_ms(D, 18, 0), h=107, l=103),
            bar(106, t=session_ms(D, 3, 0), h=108, l=101),
            bar(111, t=session_ms(D, 9, 30), h=112, l=106, o=106.5)]
    st = Levels()
    vals = [st.push(b) for b in bars]
    assert vals[-1] == {"pdh": 110, "pdl": 100, "pdc": 105, "onh": 108, "onl": 101, "rth_open": 106.5}
    assert vals[1]["rth_open"] is None


def test_profile_poc_and_value_area():
    p = profile_from({400: 10, 401: 50, 402: 30, 403: 5, 404: 5}, TS)
    assert (p["poc"], p["val"], p["vah"]) == (100.25, 100.25, 100.5)
    assert p["rows"][0] == [100.0, 10]
    assert profile_from({}, TS) is None


def test_profile_accumulates_and_previews_the_live_bar():
    m = session_ms(D, 9, 30)
    ticks = [Tick(m + i * 15_000, 100 + (i % 5) * 0.25, 1 + i % 2, BUY if i % 2 else SELL, i)
             for i in range(30)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    acc = Profile(TS)
    for b in closed:
        acc.push(b)
    vol: dict = {}
    for b in closed + [cur]:
        for k, (s, bu) in b.fp.items():
            vol[k] = vol.get(k, 0) + s + bu
    assert acc.value(cur) == profile_from(vol, TS)


def test_make_parses_keys():
    assert make("ema:20").n == 20
    assert make("vwap:rth").anchor == "rth"
    assert isinstance(make("levels"), Levels)
    for bad in ("nope", "vwap:xyz"):
        with pytest.raises(ValueError):
            make(bad)


def test_make_bounds_lengths_and_rejects_extra_parameters():
    """A study length is 1..1000 and a study takes only its own parameters;
    anything else is a ValueError (sma:0 built a window that never trims,
    ema:20:30 / levels:3 raised TypeError, adx:0 ZeroDivisionError, and a
    million-bar window was free CPU/memory for any page on the desk)."""
    for bad in ("sma:0", "ema:1001", "vwma:-5", "adx:0", "ema:20:30", "sma:1.5",
                "vwap:rth:x", "levels:3", "cumdelta:1", "ema:"):
        with pytest.raises(ValueError):
            make(bad)
    assert make("sma:1").n == 1 and make("ema:1000").n == 1000 and make("adx").n == 14
