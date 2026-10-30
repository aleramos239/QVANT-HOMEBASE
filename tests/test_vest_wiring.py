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
