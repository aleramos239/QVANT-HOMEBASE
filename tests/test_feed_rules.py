"""Live bars (feed) + the rule registry + the one-leg signal path + the
server's feed step. No network: chart pushes are fed by hand."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.feed import Bar, MarketFeed
from homebase.rules import RULES, Signal, nq_10am_continuation
from tests.test_engine import Clock, FakeAdapter

UTC = dt.timezone.utc
ET = dt.timezone(dt.timedelta(hours=-4))          # EDT for these dates


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def push(feed, cid, bars, eoh=False):
    feed._on_chart({"e": "chart", "d": {"charts": [
        {"id": cid, "eoh": True} if eoh else
        {"id": cid, "bars": [{"timestamp": ts, "open": o, "high": h, "low": l, "close": c,
                              "upVolume": v, "downVolume": 0}
                             for ts, o, h, l, c, v in bars]}]}})


def mkfeed():
    f = MarketFeed("k", "demo", token_provider=lambda: "t")
    f._watch[7] = ("NQ", 1)
    f._hist[("NQ", 1)], f._cur[("NQ", 1)] = [], None
    f._warming.add(("NQ", 1))
    return f


# --- the feed ------------------------------------------------------------------
def test_history_warmup_then_live_closes():
    f = mkfeed()
    push(f, 7, [("2026-09-22T13:57Z", 1, 2, 0.5, 1.5, 10), ("2026-09-22T13:58Z", 1.5, 2, 1, 1.8, 11),
                ("2026-09-22T13:59Z", 1.8, 1.9, 1.7, 1.85, 3)])          # last = developing
    push(f, 7, [], eoh=True)
    assert [b.ts.minute for b in f.bars("NQ", 1)] == [57, 58]            # closed history
    assert f.current("NQ", 1).ts.minute == 59
    assert f.tick(dt.datetime(2026, 9, 22, 13, 59, 30, tzinfo=UTC)) == []   # warm-up is not an event
    push(f, 7, [("2026-09-22T13:59Z", 1.8, 2.1, 1.7, 2.0, 40)])           # update
    push(f, 7, [("2026-09-22T14:00Z", 2.0, 2.0, 2.0, 2.0, 1)])            # a new minute
    out = f.tick(dt.datetime(2026, 9, 22, 14, 0, 1, tzinfo=UTC))
    assert len(out) == 1 and out[0][2].ts.minute == 59 and out[0][2].c == 2.0 and out[0][2].h == 2.1
    assert f.tick(dt.datetime(2026, 9, 22, 14, 0, 2, tzinfo=UTC)) == []   # drained
    assert f.status()["watching"]["NQ/1m"]["bars"] == 3


def test_quiet_market_closes_on_the_clock():
    f = mkfeed()
    push(f, 7, [("2026-09-22T13:59Z", 1, 1, 1, 1, 1)])
    push(f, 7, [], eoh=True)
    assert f.tick(dt.datetime(2026, 9, 22, 14, 0, 2, tzinfo=UTC)) == []   # inside the grace
    out = f.tick(dt.datetime(2026, 9, 22, 14, 0, 4, tzinfo=UTC))
    assert len(out) == 1 and out[0][2].ts.minute == 59 and f.current("NQ", 1) is None


# --- the 10am rule --------------------------------------------------------------
def candle(o, h, l, c, day="2026-09-22", n=30):
    """30 one-minute bars 09:30..09:59 ET whose aggregate is (o, h, l, c)."""
    out = []
    for i in range(n):
        ts = dt.datetime(2026, 9, 22, 9, 30, tzinfo=ET) + dt.timedelta(minutes=i)
        if i == 0:
            b = (o, max(o, h if n == 1 else o), min(o, l if n == 1 else o), o)
        elif i == n // 2:
            b = (o, h, l, o)                                   # the range
        elif i == n - 1:
            b = (o, max(o, c), min(o, c), c)
        else:
            b = (o, o, o, o)
        out.append(Bar(ts.astimezone(UTC), *b, 5, "NQ", 1))
    return out


CFG = StrategyCfg(symbol="NQ", qty=1, offset_pts=0, sl_pts=0, tp_pts=0, kind="bars")
NOW = dt.datetime(2026, 9, 22, 10, 0, 0, tzinfo=ET)


def test_10am_long_in_the_top_quarter():
    bars = candle(30000, 30040, 29990, 30035)            # range 50, close 45/50 = 0.9 up
    sig = nq_10am_continuation(bars, NOW, CFG)
    assert sig.side == "Buy" and sig.entry == "Market"
    assert sig.sl_px == 29990 and sig.ref_px == 30035
    assert sig.tp_px == 30035 + 0.75 * 45                # 30068.75
    assert sig.tp_rr == 0.75 and sig.note["close_pos"] == 0.9


def test_10am_short_in_the_bottom_quarter():
    bars = candle(30000, 30010, 29950, 29960)            # down, close 10/60 = 0.167
    sig = nq_10am_continuation(bars, NOW, CFG)
    assert sig.side == "Sell" and sig.sl_px == 30010 and sig.tp_px == 29960 - 0.75 * 50


def test_10am_filter_doji_and_timing():
    assert nq_10am_continuation(candle(30000, 30040, 29990, 30020), NOW, CFG) is None  # 0.6: not top quarter
    assert nq_10am_continuation(candle(30000, 30040, 29990, 30000), NOW, CFG) is None  # doji
    bars = candle(30000, 30040, 29990, 30035)[:-1]         # 09:58 just closed: not yet
    assert nq_10am_continuation(bars, NOW, CFG) is None
    assert nq_10am_continuation(candle(30000, 30040, 29990, 30035, n=20), NOW, CFG) is None  # too few bars
    assert "nq_10am_continuation" in RULES


# --- the engine's one-leg path ---------------------------------------------------
def mkcfg(shadow=False, armed=True):
    return AppCfg(armed=armed, webhook_secret="s",
                  accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                  book={"nq10am": [{"account": "main", "qty": 2}]},
                  strategies={"nq10am": StrategyCfg(
                      symbol="NQ", qty=1, offset_pts=0, sl_pts=0, tp_pts=0, enabled=True,
                      kind="bars", shadow=shadow, rule="nq_10am_continuation",
                      accept_from_et="09:59", accept_until_et="10:05")})


def mkengine(tmp_path, **kw):
    cfg = mkcfg(**kw)
    ad = FakeAdapter("main")
    clock = Clock(14, 0)                                  # 10:00 ET
    return Engine(cfg, {"main": ad}, now_fn=clock, root=tmp_path), ad, clock


SIG = Signal("Buy", "Market", None, sl_px=29990.0, tp_px=30068.75, ref_px=30035.0, tp_rr=0.75)


def events(tmp_path):
    return [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()]


def test_shadow_journals_and_places_nothing(tmp_path):
    eng, ad, _ = mkengine(tmp_path, shadow=True)
    out = run(eng.handle_signal("nq10am", SIG))
    assert out["ok"] and out["armed"] is False and "shadow" in out["note"]
    assert ad.brackets == [] and ad.orders == []
    ev = [e for e in events(tmp_path) if e["event"] == "shadow_signal"][0]
    assert (ev["side"], ev["sl"], ev["tp"], ev["qty"]) == ("Buy", 29990.0, 30068.75, 2)
    assert ev["risk_usd"] == 45 * 20 * 2                 # 45 pts x $20 x 2
    assert eng.day_status("nq10am") == "idle"            # nothing happened on the book


def test_armed_places_one_bracket_per_account(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    out = run(eng.handle_signal("nq10am", SIG))
    assert out["ok"] and out["armed"]
    assert len(ad.brackets) == 1
    b = ad.brackets[0]
    assert (b.side, b.order_type, b.qty, b.stop_price, b.tp_price) == ("Buy", "Market", 2, 29990.0, 30068.75)
    st = eng._state("nq10am", "main")
    assert st.status == "placed" and st.upper_id and st.lower_id is None
    assert (st.sl_px, st.tp_px, st.tp_rr) == (29990.0, 30068.75, 0.75)
    assert run(eng.handle_signal("nq10am", SIG))["ok"] is False   # one per day


def test_fill_keeps_the_stop_and_moves_the_target_to_the_fill(tmp_path):
    from homebase.broker.base import FillEvent
    eng, ad, _ = mkengine(tmp_path)
    run(eng.handle_signal("nq10am", SIG))
    st = eng._state("nq10am", "main")
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy", qty=2,
                              price=30036.0, raw={"orderId": st.upper_id})))
    assert st.status == "live" and ad.cancelled == []          # no sibling to cancel
    # stop untouched; target = fill + 0.75 * (fill - stop) = 30036 + 34.5
    assert ad.modified == [(f"{st.upper_id}-tp", "Limit", 30070.5)]
    assert st.tp_px == 30070.5
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=2,
                              price=30070.5, raw={"orderId": "tp-child"})))
    assert st.status == "done" and st.exit_reason == "tp"
    assert st.pnl == round((30070.5 - 30036.0) * 20 * 2, 2)


def test_signal_guards(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    clock.set_et(11, 0)
    assert "window" in run(eng.handle_signal("nq10am", SIG))["reason"]
    clock.set_et(10, 0)
    bad = Signal("Buy", "Market", None, sl_px=30050.0, tp_px=30068.75, ref_px=30035.0)
    assert "wrong side" in run(eng.handle_signal("nq10am", bad))["reason"]
    assert run(eng.handle_alert({"strategy": "nq10am", "upper": 1, "lower": 0}))["ok"] is False
    assert ad.brackets == []


# --- the server's feed step -------------------------------------------------------
def test_feed_step_runs_the_rule_on_a_closed_bar(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import homebase.config as config_mod
    from homebase.server import create_app
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = mkcfg(shadow=True)
    feed = mkfeed()
    feed._connected_flag = True

    class F(MarketFeed):
        pass

    async def fake_connect():
        feed._ws = type("W", (), {"connected": True})()
    feed.connect = fake_connect

    async def fake_watch(root, minutes, warmup=60):
        return "NQZ6"
    feed.watch_bars = fake_watch
    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid),
                     feed_factory=lambda c, a: feed)
    with TestClient(app):
        now = dt.datetime(2026, 9, 22, 10, 0, 0, tzinfo=ET)
        app.state.engine._now = lambda: now.astimezone(UTC)      # the engine's own clock
        assert run(app.state.feed_step(now)) == []              # connects, nothing closed yet
        assert app.state.feed_box["feed"] is feed
        # the whole 09:30-10:00 candle as history, then the 09:59 close arrives live
        hist = candle(30000, 30040, 29990, 30035)
        feed._hist[("NQ", 1)] = hist[:-1]
        feed._warming.discard(("NQ", 1))
        feed._closed.append(("NQ", 1, hist[-1]))
        feed._hist[("NQ", 1)].append(hist[-1])
        out = run(app.state.feed_step(now))
        assert len(out) == 1 and out[0]["signal"].side == "Buy" and out[0]["result"]["ok"]
        ev = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()]
        assert any(e["event"] == "shadow_signal" for e in ev)
        # outside the window the feed is closed
        assert run(app.state.feed_step(dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET))) == []
        assert app.state.feed_box["feed"] is None


def test_watch_bars_clears_a_penalty_with_its_ticket():
    """A rate-limit penalty is a state: plain requests stay refused until one
    is resent WITH the p-ticket after p-time. watch_bars must do that dance."""
    f = MarketFeed("k", "demo", token_provider=lambda: "t")
    sent = []

    class W:
        connected = True

        async def request(self, ep, body):
            sent.append(body)
            if body.get("p-ticket") == "TKT":
                return {"mode": "RealTime", "historicalId": 9, "realtimeId": 9}
            return {"p-ticket": "TKT", "p-time": 0, "p-message": "Rate limit exceeded"}

    f._ws = W()
    sym = run(f.watch_bars("NQ", 1, warmup=5))
    assert sym.startswith("NQ")
    assert len(sent) == 2 and sent[0].get("p-ticket") is None and sent[1]["p-ticket"] == "TKT"
    assert f._watch[9] == ("NQ", 1)
