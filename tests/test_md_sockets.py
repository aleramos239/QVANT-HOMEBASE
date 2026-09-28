"""Market-data sockets around the 9:30 fire. An md socket dies when the token it was
authorized with expires; the desk renews its tokens early (09:10-09:19:30 ET), so:
  * every md socket starts on the freshest token (md_source, ticks.md_token);
  * the bars feed, if it still rides an older md token, is rebuilt before 09:20;
  * a non-urgent feed (re)connect never lands in 09:20-09:35 -- it waits for 09:35.
No network: fake adapters, fake feeds, tokens on a tmp disk."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from types import SimpleNamespace as NS

import homebase.config as config_mod
from homebase import ticks as T
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from tests.test_engine import FakeAdapter

ET = dt.timezone(dt.timedelta(hours=-4))           # EDT on these dates
MON = (2026, 9, 14)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def mon(h, m, s=0):
    return dt.datetime(*MON, h, m, s, tzinfo=ET)


def adapter(aid, md, expires):
    ad = FakeAdapter(aid)
    ad._auth = NS(tokens=NS(md_access_token=md, expires_at_unix=expires))
    return ad


# --- every md socket starts on the freshest token ------------------------------------------
def test_md_source_takes_the_freshest_token_of_the_preferred_login():
    from homebase.server import md_source
    cfg = AppCfg(accounts={
        "d1": AccountCfg(keyring_key="tv:demo:a", account_name="D1"),
        "d2": AccountCfg(keyring_key="tv:demo:b", account_name="D2"),
        "l1": AccountCfg(keyring_key="tv:live:me", account_name="L", live=True)})
    ads = {"d1": adapter("d1", "d1-md", 1000.0),
           "d2": adapter("d2", "d2-md", 5000.0),          # renewed early: expires last
           "l1": adapter("l1", "l1-md", 9000.0)}          # fresher still, but demo comes first
    assert (lambda k, e, tok: (k, e, tok()))(*md_source(cfg, ads)) == \
        ("tv:demo:b", "demo", "d2-md")
    ads["d2"]._auth.tokens.expires_at_unix = 1000.0       # a tie keeps config order
    assert md_source(cfg, ads)[2]() == "d1-md"
    ads["d1"]._connected = ads["d2"]._connected = False   # no demo up: the live login
    assert md_source(cfg, ads)[:2] == ("tv:live:me", "live")


def test_the_timers_md_socket_starts_on_the_renewed_md_token(tmp_path, monkeypatch):
    """The early renewal rolled the login's md token; the timer's md socket (09:20 gate /
    09:28:30 stage), built through md_source, is authorized with the NEW one."""
    import homebase.marketdata as md_mod
    from homebase.server import md_source
    monkeypatch.setattr(md_mod, "state_dir", lambda: tmp_path)
    authorized = []

    class WS:
        def __init__(self, token, env):
            self.token, self.connected, self.event_handlers = token, True, []

        async def connect(self): ...

        async def authorize(self):
            authorized.append(self.token)

    monkeypatch.setattr(md_mod, "TradovateWS", WS)
    cfg = AppCfg(accounts={"main": AccountCfg(keyring_key="tv:demo:me", account_name="M")})
    ad = adapter("main", "md-old", 1000.0)
    ad._auth.tokens.md_access_token, ad._auth.tokens.expires_at_unix = "md-new", 5800.0
    key, env, provider = md_source(cfg, {"main": ad})
    m = md_mod.TradovateMD(key, env, token_provider=provider)
    run(m.connect())
    assert authorized == ["md-new"] and m.rides_older_token() is False


def test_an_md_socket_knows_when_its_login_renewed_its_token(tmp_path, monkeypatch):
    import homebase.marketdata as md_mod
    monkeypatch.setattr(md_mod, "state_dir", lambda: tmp_path)
    cur = {"tok": "md-1"}
    m = md_mod.TradovateMD("k", "demo", token_provider=lambda: cur["tok"])
    assert m.rides_older_token() is False                 # no socket yet
    m._ws = NS(token="md-1", connected=True)
    assert m.rides_older_token() is False
    cur["tok"] = "md-2"                                   # the login renewed
    assert m.rides_older_token() is True
    cur["tok"] = ""                                       # its adapter is reconnecting: unknown
    assert m.rides_older_token() is False
    m._token_provider = lambda: 1 / 0
    assert m.rides_older_token() is False
    m._token_provider = None
    assert m.rides_older_token() is False


def test_md_token_on_disk_takes_the_freshest_token_of_the_preferred_login(tmp_path, monkeypatch):
    """The chart service and the tick archive read tokens from disk: within the login they
    prefer, the one that expires last -- the renewed one after an early renewal."""
    acct = lambda live, label: NS(live=live, label=label, account_name=label)   # noqa: E731
    cfg = NS(accounts={"demo1": acct(False, "D1"), "demo2": acct(False, "D2"),
                       "live1": acct(True, "L1"), "live2": acct(True, "L2")})
    monkeypatch.setattr(T.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    now = dt.datetime.now(dt.timezone.utc)
    for aid, mins in (("demo1", 30), ("demo2", 75), ("live1", 79), ("live2", 1)):
        (tmp_path / f"{aid}.tokens.json").write_text(json.dumps(
            {"md_access_token": f"tok-{aid}",
             "expiration_time": (now + dt.timedelta(minutes=mins)).isoformat()}))
    assert T.md_token(prefer_live=False) == ("tok-demo2", "demo")
    assert T.md_token() == ("tok-live1", "live")             # live2 expires within 2 min: invalid
    assert T.accounts_by_env() == {"live": "L1", "demo": "D2"}


# --- the bars feed: recycled before 09:20, never (re)connected 09:20-09:35 ---------------
class FakeFeed:
    """The price feed's surface as feed_step uses it; `current` is its login's md token now."""

    def __init__(self, log, current, token):
        self.log, self.current, self.token = log, current, token
        self.up, self.closed, self.watched = False, False, []

    @property
    def connected(self):
        return self.up and not self.closed

    async def connect(self):
        self.up = True
        self.log.append(("connect", self.token))

    async def close(self):
        self.closed = True
        self.log.append(("close", self.token))

    async def watch_bars(self, root, minutes, warmup=60):
        self.watched.append((root, minutes))
        self.log.append(("watch", root))
        return root

    def watching(self):
        return {w: 0 for w in self.watched}

    def tick(self, now):
        return []

    def status(self):
        return {"connected": self.connected, "watching": {}}

    def rides_older_token(self):
        return self.token != self.current["md"]


def bars_strategy(symbol="NQ", start="09:59", until="10:05"):
    return StrategyCfg(symbol=symbol, qty=1, offset_pts=0, sl_pts=0, tp_pts=0, enabled=True,
                       kind="bars", shadow=True, rule="nq_10am_continuation",
                       accept_from_et=start, accept_until_et=until)


def feed_app(tmp_path, monkeypatch, strategies):
    from homebase.server import create_app
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=True, webhook_secret="s",
                 accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                 book={}, strategies=strategies)
    log, current, made = [], {"md": "md-1"}, []

    def factory(c, a):
        made.append(FakeFeed(log, current, current["md"]))   # built on the token of the moment
        return made[-1]

    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid), feed_factory=factory)
    return app, log, current, made


def journal(tmp_path):
    p = tmp_path / "journal.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def test_a_feed_on_an_older_md_token_is_rebuilt_before_0920(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch, {"nq10am": bars_strategy()})
    step = app.state.feed_step
    run(step(mon(9, 0)))
    assert len(made) == 1 and made[0].connected and made[0].token == "md-1"
    run(step(mon(9, 9, 59)))                              # not renewed yet: nothing to do
    current["md"] = "md-2"                                # the early renewal rolled the md token
    run(step(mon(9, 9, 59)))                              # before 09:10: left alone
    assert len(made) == 1
    run(step(mon(9, 12)))
    assert len(made) == 2 and made[0].closed and made[1].connected and made[1].token == "md-2"
    assert made[1].watched == [("NQ", 1)]                 # its history reloaded
    assert log[-3:] == [("close", "md-1"), ("connect", "md-2"), ("watch", "NQ")]
    ev = [e for e in journal(tmp_path) if e["event"] in ("feed_stopped", "feed_started")]
    assert "recycled" in ev[-2]["reason"] and ev[-1]["event"] == "feed_started"
    run(step(mon(9, 13)))                                 # on the new token: stays
    assert len(made) == 2


def test_no_recycle_from_091930(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch, {"nq10am": bars_strategy()})
    run(app.state.feed_step(mon(9, 0)))
    current["md"] = "md-2"
    for t in (mon(9, 19, 30), mon(9, 25), mon(9, 40)):
        run(app.state.feed_step(t))
    assert len(made) == 1 and made[0].connected           # it dies at the old token's expiry,
                                                          # and then waits for 09:35 (below)


def test_a_non_urgent_feed_reconnect_waits_for_0935(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch, {"nq10am": bars_strategy()})
    step = app.state.feed_step
    run(step(mon(9, 0)))
    made[0].closed = True                                 # it died (its token expired)
    for t in (mon(9, 20), mon(9, 27), mon(9, 30), mon(9, 34, 59)):
        assert run(step(t)) == []
    assert len(made) == 1                                 # no md request 09:20-09:35
    run(step(mon(9, 35)))
    assert len(made) == 2 and made[1].connected and made[1].watched == [("NQ", 1)]


def test_a_feed_started_inside_the_window_waits_too(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch, {"nq10am": bars_strategy()})
    run(app.state.feed_step(mon(9, 22)))                  # e.g. a desk restart at 09:22
    assert made == []
    run(app.state.feed_step(mon(9, 19, 59)))              # before 09:20 it connects at once
    assert len(made) == 1


def test_a_strategy_that_needs_bars_inside_the_window_is_never_deferred(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch,
                                       {"early": bars_strategy(start="09:25", until="09:40")})
    run(app.state.feed_step(mon(9, 22)))
    assert len(made) == 1 and made[0].connected


def test_a_new_bars_subscription_waits_for_0935_too(tmp_path, monkeypatch):
    app, log, current, made = feed_app(tmp_path, monkeypatch, {"nq10am": bars_strategy()})
    step = app.state.feed_step
    run(step(mon(9, 0)))
    app.state.cfg.strategies["es10am"] = bars_strategy(symbol="ES")   # enabled mid-morning
    run(step(mon(9, 25)))
    assert made[0].watched == [("NQ", 1)]
    run(step(mon(9, 35)))
    assert made[0].watched == [("NQ", 1), ("ES", 1)]


def test_readiness_says_a_deferred_feed_is_waiting_not_broken():
    from zoneinfo import ZoneInfo
    from homebase.engine import Engine
    from homebase.server import compute_readiness
    cfg = AppCfg(armed=True, webhook_secret="s",
                 accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                 book={"nq10am": [{"account": "main", "qty": 1}]},
                 strategies={"nq10am": bars_strategy()})

    def feed_check(h, m, strategies=None):
        now = dt.datetime(*MON, h, m, tzinfo=ZoneInfo("America/New_York"))
        if strategies:
            cfg.strategies = strategies
        eng = Engine(cfg, {"main": FakeAdapter("main")},
                     now_fn=lambda: now.astimezone(dt.timezone.utc),
                     root=__import__("pathlib").Path("/tmp"))
        r = compute_readiness(now, cfg, eng, {"main": {"connected": True}},
                              {"connected": False, "watching": {}})
        return next(c for c in r["checks"] if c["label"] == "Price feed")

    got = feed_check(9, 25)
    assert got["level"] == "warn" and "09:35" in got["detail"]
    assert feed_check(9, 40)["level"] == "bad"
    assert feed_check(9, 25, {"early": bars_strategy(start="09:25", until="09:40")})["level"] == "bad"
