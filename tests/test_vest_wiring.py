"""The Vest adapter on the desk: built from a `vest:` login, never a market-data source, fed by the CME bars, and
parked on 'needs a new wallet signature' until the login is signed again. No network."""
from __future__ import annotations

import asyncio
import datetime as dt
import time as _time
from types import SimpleNamespace

import httpx
import pytest

from homebase import config as config_mod
from homebase.broker import vest
from homebase.broker.login_budget import LoginBudget
from homebase.broker.tradovate import TradovateAdapter
from homebase.broker.vest import VestAdapter
from homebase.broker.vest_auth import DeviceKey, VestSession
from homebase.config import AccountCfg, AppCfg
from homebase.data.feed import Bar, MarketFeed
from homebase.desk_app import brokers
from homebase.desk_app.brokers import _key_env, build_adapter, build_feed, is_vest_key, md_source
from homebase.store import secrets_store
from tests.test_engine import run

VKEY = "vest:0xabc"
T0 = dt.datetime(2026, 10, 29, 14, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(secrets_store, "_migrate_from_keychain", lambda key: None)   # never the real Keychain
    monkeypatch.setattr(vest, "state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.data.marketdata.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(brokers, "_VEST_SESSIONS", {})                          # one shared session per login, per test


def bar(minutes=1, ts=T0, h=21010.0, root="NQ"):
    return Bar(ts=ts, o=21000.0, h=h, l=20990.0, c=21005.0, vol=1, root=root, minutes=minutes)


# ---- build_adapter / md_source / _key_env -----------------------------------------------------------------------
def test_build_adapter_vest():
    a = AccountCfg(keyring_key=VKEY, vest_account_id="123", floors={"max_drawdown_equity": 45000.0}, slip_frac=0.3)
    ad = build_adapter("v1", a)
    assert isinstance(ad, VestAdapter)
    assert (ad.vest_account_id, ad.floors, ad.slip_frac) == ("123", {"max_drawdown_equity": 45000.0}, 0.3)
    assert ad.feed_ok() is False                         # nothing fires until the feed is wired
    assert build_adapter("v2", AccountCfg(keyring_key=VKEY)).floors == {}     # no floors: refused, never defaulted
    assert build_adapter("probe", AccountCfg(keyring_key=VKEY)).vest_account_id == ""   # a probe (R3)
    assert isinstance(build_adapter("t1", AccountCfg(keyring_key="tv:demo:u")), TradovateAdapter)


def test_md_source_skips_vest():
    cfg = AppCfg(accounts={"v1": AccountCfg(keyring_key=VKEY, vest_account_id="1", live=True)})
    with pytest.raises(RuntimeError, match="no accounts configured for market data"):
        md_source(cfg, {})
    cfg.accounts["t1"] = AccountCfg(keyring_key="tv:demo:u")
    assert md_source(cfg, {})[0] == "tv:demo:u"


def test_key_env_vest():
    assert _key_env("vest:0xabc") == "vest"
    assert is_vest_key("vest:0xabc") and not is_vest_key("tv:live:u")
    assert _key_env("tv:live:u") == "live"
    assert _key_env("tv:demo:Google:1012") == "demo"


# ---- the feed's bar listeners -----------------------------------------------------------------------------------
def test_bar_listener_called_and_isolated():
    f = MarketFeed("k", "demo", token_provider=lambda: "t")
    got = []

    def boom(root, b):
        raise ValueError("listener bug")

    f.bar_listeners += [boom, lambda root, b: got.append((root, b))]
    b = bar()
    f._take(("NQ", 1), b)
    assert got == [("NQ", b)]
    assert f.current("NQ", 1) == b                       # the bar update went through
    f._take(("NQ", 1), bar(ts=T0 - dt.timedelta(minutes=1)))   # an older bar the feed ignores: no listener call
    f._warming.add(("NQ", 5))
    f._take(("NQ", 5), bar(minutes=5))                   # warm-up history is not a live push: no listener call
    assert got == [("NQ", b)]


def _feed_with(adapters):
    cfg = AppCfg(accounts={"t1": AccountCfg(keyring_key="tv:demo:u")})
    f = build_feed(cfg, adapters)
    f._ws = SimpleNamespace(connected=True)              # a live socket
    f._hist.setdefault(("NQ", 1), [])
    return f


def _spy(ad):
    calls = []
    ad.on_bar = lambda root, b: calls.append((root, b, ad.feed_ok()))
    return calls


def test_rebuilt_adapter_replaces_the_old_one_on_the_feed():
    """Exactly one adapter per account is hooked: the feed reaches whatever the desk's adapters dict holds now."""
    old = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    adapters = {"v1": old, "t1": object()}
    f = _feed_with(adapters)
    old_calls = _spy(old)
    f._take(("NQ", 1), bar())
    assert len(old_calls) == 1
    new = adapters["v1"] = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    new_calls = _spy(new)
    f._take(("NQ", 1), bar(h=21011.0))
    assert len(old_calls) == 1 and len(new_calls) == 1


def test_feed_ok_follows_the_socket_and_a_new_socket_resets_the_gap_memory():
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    resets = []
    ad.feed_reset = lambda: resets.append(1)
    f = _feed_with({"v1": ad})
    calls = _spy(ad)
    f._take(("NQ", 1), bar())
    f._take(("NQ", 1), bar(h=21011.0))
    assert [c[2] for c in calls] == [True, True] and resets == [1]     # reset once, at the socket's first push
    f._ws.connected = False
    assert ad.feed_ok() is False                         # the socket died: down
    f._ws = SimpleNamespace(connected=True)              # a reconnect: a new socket
    f._take(("NQ", 1), bar(h=21012.0))
    assert resets == [1, 1] and calls[-1][2] is True
    f2 = _feed_with({"v1": ad})                          # a rebuilt feed (the desk's reconnect)
    f2._take(("NQ", 1), bar(h=21013.0))
    assert resets == [1, 1, 1]


def test_only_the_smallest_timeframe_of_a_root_reaches_vest():
    """HeldBook.crossed keeps one 'last push' per root: two timeframes interleaved would each look like a new bar."""
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    f = _feed_with({"v1": ad})
    f._hist.setdefault(("NQ", 5), [])
    calls = _spy(ad)
    f._take(("NQ", 5), bar(minutes=5))
    f._take(("NQ", 1), bar())
    assert [c[1].minutes for c in calls] == [1]


def test_a_real_vest_adapter_gets_the_push_on_the_running_loop():
    """No spy: the real on_bar runs (sync) and never raises into the feed."""
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    f = _feed_with({"v1": ad})
    f._take(("NQ", 1), bar())
    assert "NQ" in ad._pushed                           # it saw the push with the feed up


# ---- needs a new wallet signature ---------------------------------------------------------------------------------
class _Stop(Exception):
    pass


def test_needs_signature_status(monkeypatch):
    cfg = AppCfg(accounts={"v1": AccountCfg(keyring_key=VKEY, vest_account_id="1",
                                            floors={"max_drawdown_equity": 1.0})})
    journal = []
    engine = SimpleNamespace(journal=lambda ev, **kw: journal.append(ev),
                             now_et=lambda: dt.datetime(2026, 10, 29, 10, 0))
    adapters, acct_status, calls = {}, {}, []

    def factory(aid, a):
        sess = VestSession(a.keyring_key, http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(500))))
        ad = VestAdapter(aid, keyring_key=a.keyring_key, vest_account_id=a.vest_account_id, session=sess)
        orig = ad.connect

        async def connect():
            calls.append(1)
            await orig()
        ad.connect = connect
        return ad

    acc = brokers.make(cfg=cfg, engine=engine, adapters=adapters, acct_status=acct_status, budget=LoginBudget(),
                       desk=SimpleNamespace(attach=lambda *a: None), paper_http=None, paper_client=None,
                       background=False, adapter_factory=factory, _kill_lock=asyncio.Lock)

    def passes(n):
        state = {"n": 0}

        async def fake_sleep(_s):
            state["n"] += 1
            if state["n"] >= n:
                raise _Stop
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        with pytest.raises(_Stop):
            run(acc.broker_loop())

    now = [1_000_000.0]
    monkeypatch.setattr(_time, "time", lambda: now[0])
    passes(1)                                            # never signed: the store holds no refresh token
    assert calls == [1]
    assert acct_status["v1"] == {"connected": False, "error": "needs a new wallet signature"}
    assert adapters["v1"].journal is engine.journal       # held-entry skips reach the desk journal
    assert journal.count("vest_needs_signature") == 1
    now[0] += 6 * 3600
    passes(3)                                            # hours later, still unsigned: never retried
    assert calls == [1]
    secrets_store.set_credentials(VKEY, primary_addr="0xabc", refresh_token="RT", refresh_token_id="RTID",
                                  refresh_expires_ms=4_000_000_000_000, device_pem=DeviceKey.new().pem())
    passes(1)                                            # signed again: the next pass tries it
    assert calls == [1, 1]
    assert acct_status["v1"]["error"] != "needs a new wallet signature"     # the mock gateway answers 500


def test_vest_fields_are_written_only_when_set():
    """Like day_lock: an older desk loading config.json with unknown keys refuses them, so a config with no Vest
    account is written byte for byte as before; a Vest account's fields round-trip."""
    import json
    cfg = AppCfg(accounts={"t1": AccountCfg(keyring_key="tv:demo:u"),
                           "v1": AccountCfg(keyring_key=VKEY, vest_account_id="9", floors={"daily_loss": 1000.0},
                                            slip_frac=0.25)})
    config_mod.save(cfg)
    raw = json.loads(config_mod.config_path().read_text())["accounts"]
    assert not {"vest_account_id", "floors", "slip_frac"} & set(raw["t1"])
    back = config_mod.load().accounts["v1"]
    assert (back.vest_account_id, back.floors, back.slip_frac) == ("9", {"daily_loss": 1000.0}, 0.25)


# ---- fix round 1 (R44, R46, R47, R48) ----------------------------------------------------------------------
def test_one_stream_per_price_root():
    """R44: NQ and MNQ are one price. With NQ 5m and MNQ 1m both watched only MNQ 1m reaches Vest."""
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    f = _feed_with({"v1": ad})
    f._hist.pop(("NQ", 1))
    f._hist[("NQ", 5)], f._hist[("MNQ", 1)] = [], []
    calls = _spy(ad)
    f._take(("NQ", 5), bar(minutes=5))
    f._take(("MNQ", 1), bar(root="MNQ"))
    f._take(("NQ", 5), bar(minutes=5, h=21011.0))
    assert [(c[0], c[1].minutes) for c in calls] == [("MNQ", 1)]


def test_a_smaller_stream_enabled_mid_day_is_a_first_push():
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    resets = []
    ad.feed_reset = lambda: resets.append(1)
    f = _feed_with({"v1": ad})
    f._hist.pop(("NQ", 1))
    f._hist[("NQ", 5)] = []
    calls = _spy(ad)
    f._take(("NQ", 5), bar(minutes=5))
    f._take(("NQ", 5), bar(minutes=5, h=21011.0))
    assert resets == [1] and len(calls) == 2
    f._hist[("MNQ", 1)] = []                                     # a 1m strategy is enabled
    f._take(("NQ", 5), bar(minutes=5, h=21012.0))                # no longer the chosen stream
    f._take(("MNQ", 1), bar(root="MNQ"))
    assert resets == [1, 1] and [(c[0], c[1].minutes) for c in calls][2:] == [("MNQ", 1)]


def test_reviewers_case_never_fires_below_the_level():
    """NQ 5m's high 21020 was printed before the Buy stop at 21015 was held; price then stays near 21005 on both
    streams. Mixed in one book, the NQ 5m push looked like a new bar with a high past the level: a buy fired below it."""
    from homebase.broker.vest_held import HeldEntry
    _sign()
    ad = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    fired = []

    async def fire(e, t, cme):
        fired.append((e.id, cme))
    ad._fire = fire
    f = _feed_with({"v1": ad})
    f._hist.pop(("NQ", 1))
    f._hist[("NQ", 5)], f._hist[("MNQ", 1)] = [], []
    nq5 = lambda c: Bar(T0, 21000.0, 21020.0, 20990.0, c, 1, "NQ", 5)                      # noqa: E731
    mnq1 = lambda c, m: Bar(T0 + dt.timedelta(minutes=m), c, c + 1, c - 2, c, 1, "MNQ", 1)  # noqa: E731

    async def go():
        f._take(("NQ", 5), nq5(21005.0))
        f._take(("MNQ", 1), mnq1(21005.0, 3))
        ad._book.entries.append(HeldEntry("h1", "NQZ6", "Buy", 1, 21015.0, 20.0, None, ad._desk_day(), None))
        for c, m in ((21005.5, 3), (21005.25, 3), (21006.0, 4)):
            f._take(("NQ", 5), nq5(c))
            f._take(("MNQ", 1), mnq1(c, m))
        await asyncio.sleep(0)
    run(go())
    assert fired == [] and [e.id for e in ad._book.entries] == ["h1"]


def test_an_expired_login_shows_on_the_card(monkeypatch):
    """R46: a connected Vest adapter whose session now needs a signature is closed and the card says so."""
    _sign()
    cfg = AppCfg(accounts={"v1": AccountCfg(keyring_key=VKEY, vest_account_id="1")})
    ad = build_adapter("v1", cfg.accounts["v1"])
    ad._connected = True
    acc, acct_status, _ = _make(cfg, {"v1": ad}, build_adapter)
    acct_status["v1"] = {"connected": True, "error": None}
    _passes(acc, monkeypatch, 1)
    assert acct_status["v1"]["connected"] is True                # still signed in: nothing happens
    secrets_store.set_credentials(VKEY, refresh_expires_ms=0)    # the 30-day login ran out
    _passes(acc, monkeypatch, 1)
    assert acct_status["v1"] == {"connected": False, "error": "needs a new wallet signature"}
    assert ad.connected is False


def test_one_session_per_login_shared_and_on_the_desks_budget(monkeypatch):
    """R47/R48: every Vest entry of one login rides one VestSession (rotating refresh tokens); closing one entry never
    closes it; it books against the desk's login budget."""
    a1 = build_adapter("v1", AccountCfg(keyring_key=VKEY, vest_account_id="1"))
    a2 = build_adapter("v2", AccountCfg(keyring_key=VKEY, vest_account_id="2"))
    probe = build_adapter("probe", AccountCfg(keyring_key=VKEY))
    other = build_adapter("v3", AccountCfg(keyring_key="vest:0xdef", vest_account_id="3"))
    assert a1.session is a2.session is probe.session and other.session is not a1.session
    closed = []

    async def aclose():
        closed.append(1)
    a1.session.aclose = aclose
    run(a1.close())
    run(probe.close())
    assert closed == []
    cfg = AppCfg(accounts={"v1": AccountCfg(keyring_key=VKEY, vest_account_id="1")})
    acc, acct_status, budget = _make(cfg, {}, build_adapter)
    _passes(acc, monkeypatch, 1)                                 # unsigned: the connect fails, the budget is set
    assert acct_status["v1"]["error"] == "needs a new wallet signature"
    assert brokers._VEST_SESSIONS[VKEY].budget is budget


def _make(cfg, adapters, factory):
    acct_status, budget = {}, LoginBudget()
    engine = SimpleNamespace(journal=lambda ev, **kw: None, now_et=lambda: dt.datetime(2026, 10, 29, 10, 0))
    acc = brokers.make(cfg=cfg, engine=engine, adapters=adapters, acct_status=acct_status, budget=budget,
                       desk=SimpleNamespace(attach=lambda *a: None), paper_http=None, paper_client=None,
                       background=False, adapter_factory=factory, _kill_lock=asyncio.Lock)
    return acc, acct_status, budget


def _passes(acc, monkeypatch, n):
    state = {"n": 0}

    async def fake_sleep(_s):
        state["n"] += 1
        if state["n"] >= n:
            raise _Stop
    with monkeypatch.context() as m:
        m.setattr(asyncio, "sleep", fake_sleep)
        with pytest.raises(_Stop):
            run(acc.broker_loop())


def _sign():
    secrets_store.set_credentials(VKEY, primary_addr="0xabc", refresh_token="RT", refresh_token_id="RTID",
                                  refresh_expires_ms=4_000_000_000_000, device_pem=DeviceKey.new().pem())
