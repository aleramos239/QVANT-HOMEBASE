"""VWAP_BAND_PB (families/vwap_band_pb.py): the pullback to a VWAP sigma band with the trend. Synthetic days, no net or win rate read."""
import families
import l2sim as S
from families import blocks as B
from families import vwap_band_pb as VB  # noqa: F401  (registers the family)
from test_blocks import DAILY, TICK, minute_tape

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "lvl": 1.0}
PX = 15000.0


def quiet(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def day(edits):
    b = quiet(960)
    for t, x in edits.items():
        b[S._sec(t) // 60] = x
    return b


def run(bars, **params):
    st = B.WRAPPED["vwap_band_pb"]({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**VB.VwapBandPb.SCREEN_RUN), daily=list(DAILY), on_error="raise")
    return [(t["side"], round(t["entry_ms"] / 60000) % 1440) for t in res.trades]


# 09:30-09:59 a jittery base at 15000 (closes +/-10: sigma ~5), 10:00 a stretch up to 15030 (band ~15005.5), 10:01 a pullback close at
# 15006 (the band is then ~15006.4: inside it, above the VWAP ~15001)
BASEBARS = {f"09:{m:02d}": (PX, PX + 10, PX - 10, PX + (10 if m % 2 else -10), 40) for m in range(30, 60)}
UP = {**BASEBARS, "10:00": (PX, 15030.0, PX, 15030.0, 40)}
PULL = {**UP, "10:01": (15030.0, 15030.0, 15006.0, 15006.0, 40)}


def test_registered():
    assert "vwap_band_pb" in families.REGISTRY and B.WRAPPED["vwap_band_pb"].__name__ == "B_vwap_band_pb"


def test_quiet_day_trades_nothing():
    assert run(day(BASEBARS)) == []


def test_close_back_inside_buys_with_the_trend():
    tr = run(day(PULL), entry="close")
    assert tr and tr[0][0] == "long"


def test_short_only_never_buys_the_up_pullback():
    assert all(s == "short" for s, _ in run(day(PULL), entry="close", dir="short"))


def test_a_close_through_the_vwap_drops_the_arm():
    x = {**UP, "10:01": (15030.0, 15030.0, 14990.0, 14990.0, 40)}       # straight through the VWAP: no long
    assert all(s != "long" for s, _ in run(day(x), entry="close"))


def test_disp_needs_a_big_green_bar_after_the_touch():
    touch = {**UP, "10:01": (15030.0, 15030.0, 15005.0, 15008.0, 40)}
    assert [s for s, _ in run(day(touch), entry="disp", disp=3.0)] == []
    big = {**touch, "10:02": (15008.0, 15045.0, 15008.0, 15045.0, 40)}
    assert [s for s, _ in run(day(big), entry="disp", disp=1.0)][:1] == ["long"]


def test_limit_rests_at_the_band_and_fills_on_the_pullback():
    tr = run(day({**UP, "10:01": (15030.0, 15031.0, 15029.0, 15030.0, 40), "10:02": (15030.0, 15030.0, 15001.0, 15003.0, 40)}), entry="limit")
    assert tr and tr[0][0] == "long"
