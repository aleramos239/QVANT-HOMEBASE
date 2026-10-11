"""A study on a longer timeframe (studies.HTF, wire key "ema:20@3600")."""
import datetime as dt
import zoneinfo

import pytest

from homebase.charts import hub
from homebase.charts.bars import Bar
from homebase.charts.studies import make, split_timeframe

ET = zoneinfo.ZoneInfo("America/New_York")


def minute(i, start=dt.datetime(2026, 10, 9, 9, 30, tzinfo=ET)):
    p = 100 + i * 0.1
    t = start + dt.timedelta(minutes=i)
    return Bar(t=int(t.timestamp() * 1000), session="2026-10-09", o=p, h=p + 0.2, l=p - 0.2, c=p + 0.1, v=10)


def test_key_split_and_refusals():
    assert split_timeframe("ema:20") == ("ema:20", 0)
    assert split_timeframe("ema:20@3600") == ("ema:20", 3600)
    assert split_timeframe("sma:50:hl2@900") == ("sma:50:hl2", 900)
    assert split_timeframe("ema:20@77") == ("ema:20", 77)           # any length, typed on the page
    for bad in ("vwap@3600", "levels@3600", "orb:15@3600", "ema:20@0", "ema:20@86401", "ema:20@", "ema:20@x"):
        with pytest.raises(ValueError):
            make(bad)


def test_hour_sma_reads_the_developing_hour():
    st = make("sma:2@3600")
    vals = [st.push(minute(i)) for i in range(120)]
    # buckets sit on the hour: 09:30-10:00 is the first (30 bars), the second opens at chart bar 30
    first = next(i for i, v in enumerate(vals) if v is not None)
    assert first == 30
    assert vals[29] is None
    # at chart bar 30 the average is of (the finished 09:00 bar, the new 10:00 bar so far)
    assert vals[30] == pytest.approx((minute(29).c + minute(30).c) / 2)


def test_preview_never_commits():
    st = make("ema:5@900")
    for i in range(40):
        st.push(minute(i))
    before = st.state
    a = st.preview(minute(40))
    b = st.preview(minute(40))
    assert a == b and st.state is before


def test_no_later_bar_is_read():
    """The value on a chart bar is the same whether or not later bars exist."""
    bars = [minute(i) for i in range(100)]
    full = make("rsi:5@600")
    short = make("rsi:5@600")
    fv = [full.push(b) for b in bars]
    sv = [short.push(b) for b in bars[:60]]
    assert fv[:60] == sv


def test_warm_and_prime_scale_with_the_timeframe():
    assert hub.warm_bars("sma:50") == 50
    assert hub.warm_bars("sma:50@3600") == 50 * 60
    assert hub.prime_sessions("sma:50") == 0
    assert hub.prime_sessions("sma:50@3600") >= 3
    assert hub.prime_sessions("ema:200@86400") == 60       # capped
