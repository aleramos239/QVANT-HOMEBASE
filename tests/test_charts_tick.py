"""Chart engine basics: session maths, aggressor side, md login choice."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from homebase import contracts, ticks as T
from homebase.charts.session import et_wall_s, is_rth, session_date, session_range_ms
from homebase.charts.tick import BUY, SELL, SideClassifier, Tick, from_row
from tests.charts_util import ET, session_ms


def ms(y, mo, d, h, mi, s=0, us=0):
    return int(dt.datetime(y, mo, d, h, mi, s, us, ET).timestamp() * 1000)


def test_session_date_rolls_at_18_et_and_skips_weekends():
    assert session_date(ms(2026, 9, 20, 18, 0, 0, 10000)) == dt.date(2026, 9, 21)  # Sun open -> Mon
    assert session_date(ms(2026, 9, 21, 16, 59)) == dt.date(2026, 9, 21)
    assert session_date(ms(2026, 9, 21, 18, 0)) == dt.date(2026, 9, 22)
    assert session_date(ms(2026, 9, 25, 16, 0)) == dt.date(2026, 9, 25)
    s0, s1 = session_range_ms(dt.date(2026, 9, 21))
    assert (s0, s1) == (ms(2026, 9, 20, 18, 0), ms(2026, 9, 21, 17, 0))


def test_is_rth_and_et_wall_clock():
    assert not is_rth(ms(2026, 9, 23, 20, 0), "2026-09-24")     # the evening before
    assert not is_rth(ms(2026, 9, 24, 9, 29), "2026-09-24")
    assert is_rth(ms(2026, 9, 24, 9, 30), "2026-09-24")
    want = int(dt.datetime(2026, 9, 24, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    assert et_wall_s(ms(2026, 9, 24, 9, 30)) == want
    assert et_wall_s(session_ms(dt.date(2026, 9, 24), 9, 30)) == want


def test_side_from_a_sane_quote():
    c = SideClassifier()
    assert c.side(100.25, 100.0, 100.25) == BUY          # at the ask
    assert c.side(100.0, 100.0, 100.25) == SELL          # at the bid
    assert c.side(100.5, 100.0, 100.25) == BUY           # through the ask


def test_side_falls_back_to_the_tick_rule():
    c = SideClassifier()
    assert c.side(100.0, None, None) == BUY              # no history: buy
    assert c.side(99.75, None, None) == SELL             # down-tick
    assert c.side(99.75, None, None) == SELL             # unchanged: previous side
    assert c.side(100.0, 100.5, 99.5) == BUY             # crossed quote ignored -> up-tick
    assert c.side(100.0, 99.75, 100.25) == BUY           # inside the spread, unchanged -> previous


def test_from_row_parses_blank_quotes_and_strings():
    t = from_row({"ts_ms": "5", "price": "10", "size": "3", "bid": "", "ask": "", "id": "7"},
                 SideClassifier())
    assert t == Tick(5, 10.0, 3, BUY, 7)


def test_live_recorder_covers_every_root_of_the_nightly_archive():
    # the nightly job merges this recording into the archive: same six roots
    from homebase.charts import DEFAULT_ROOTS
    assert DEFAULT_ROOTS == T.ROOTS and len(T.ROOTS) == 6


def test_bitcoin_contract_spec():
    assert contracts.tick_size("BTC") == 5.0
    assert contracts.point_value("BTC") == 5.0
    assert contracts.tick_size("BTCV6") == 5.0


def test_md_token_prefers_the_requested_login(tmp_path, monkeypatch):
    cfg = SimpleNamespace(accounts={"demo1": SimpleNamespace(live=False),
                                    "live1": SimpleNamespace(live=True)})
    monkeypatch.setattr(T.config_mod, "load", lambda **k: cfg)
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    for aid in ("demo1", "live1"):
        (tmp_path / f"{aid}.tokens.json").write_text(
            json.dumps({"md_access_token": f"tok-{aid}", "expiration_time": exp}))
    assert T.md_token() == ("tok-live1", "live")
    assert T.md_token(prefer_live=False) == ("tok-demo1", "demo")
