"""The exits run the accounts side by side (Engine.each_account): the desk's Kill, the clock's flatten
and the strategy flatten. Behind a fake broker with a round trip (tests/exits_util.py):
  (a) the accounts overlap in time -- EXIT_CONCURRENCY at once, never one after another;
  (b) every account the desk can reach ends flat with nothing working: with one account raising half
      way, one disconnected, one already flat, and a 429 answered once;
  (c) each account's own calls are the ones the desk made before, in the same order;
  (d) the journal says what it said before, per account.
"What it did before" was recorded on 25dba038 (accounts one after another) with the same fake."""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

import homebase.config as config_mod
from homebase.engine import EXIT_CONCURRENCY
from homebase.server import create_app
from tests.exits_util import (RATE_LIMITED, Wire, exit_cfg, go_live, mkadapters, mkexits)
from tests.test_engine import Clock
from tests.test_tradovate import mkadapter, tradovate_like

RT = 0.03               # the fake broker's round trip
N = 11                  # the desk's accounts today
FLAT_RTS = 3            # one account's flatten: the position read, the market-out, its cancels (together)
KILL_RTS = 5            # ... then cancel_all and flatten_all
UNREACHED = "position unreadable (adapter not connected) — stop/target left working"
REFUSED_429 = [f"market Sell 3: order/placeorder {RATE_LIMITED}", "not flat — stop/target left working"]
UNREAD_429 = [f"position unreadable (position/list {RATE_LIMITED}) — stop/target left working"]
BLEW_UP = ["internal error: RuntimeError: place_order blew up"]


def timed(coro):
    """-> (the result, seconds it took on the loop's clock)"""
    async def go():
        loop = asyncio.get_running_loop()
        t = loop.time()
        out = await coro
        return out, loop.time() - t
    return asyncio.run(go())


def journal(tmp_path, event=None) -> list[dict]:
    recs = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    return [r for r in recs if event is None or r["event"] == event]


def legs(a: str, n: int = 101) -> list[str]:
    """The six orders one run placed on `a`, in the order a flatten cancels them."""
    up, dn = f"{a}-{n}", f"{a}-{n + 1}"
    return [up, dn, f"{up}-sl", f"{up}-tp", f"{dn}-sl", f"{dn}-tp"]


def flatten_calls(a: str, qty: int = 3, n: int = 101) -> list[str]:
    """One live run's flatten on the wire, as recorded before: read, market-out, six cancels."""
    return ["get_net_position NQ", f"place_order Market Sell {qty}"] + [f"cancel {i}" for i in legs(a, n)]


def cancel_calls(a: str, n: int = 101) -> list[str]:
    """A run with no position left: the read, then its cancels."""
    return ["get_net_position NQ"] + [f"cancel {i}" for i in legs(a, n)]


def flatten_acts(a: str, qty: int = 3, n: int = 101) -> list[str]:
    return [f"market Sell {qty}: ok"] + [f"cancel {i}: ok" for i in legs(a, n)]


def status(eng, a: str, strategy: str = "nq930") -> tuple:
    st = eng._state(strategy, a)
    return st.status, st.exit_reason


def protected(ad, a: str) -> bool:
    """Still long 3 with its stop and target working: nothing was taken away."""
    return ad.broker.net == 3 and ad.working == {f"{a}-101-sl", f"{a}-101-tp"}


def trouble(ads) -> None:
    """One bad day on six of eight accounts (a02 was closed by its target in the morning)."""
    ads["a03"]._connected = False                       # its socket is down
    ads["a04"].limited = {"place_order"}                # 429 once, on the market-out
    ads["a05"].raises = {"place_order"}                 # blows up half way, every time
    ads["a06"].limited = {"get_net_position"}           # 429 once, on the position read
    ads["a07"].limited = {"cancel a07-101-sl"}          # 429 once, on its stop's cancel


def later(monkeypatch, seconds: float) -> None:
    """`seconds` later on the engine's wall clock (the clock's flat retries after 5 s)."""
    now = time.time() + seconds
    monkeypatch.setattr("homebase.engine.time", SimpleNamespace(
        time=lambda: now, perf_counter=time.perf_counter, monotonic=time.monotonic))


@pytest.fixture()
def kill_desk(tmp_path, monkeypatch):
    """build(n, ...) -> (the /api/kill endpoint, engine, adapters, wire): the desk app over the fake
    broker, `n` accounts live long 3 NQ."""
    for mod in ("homebase.paths", "homebase.engine", "homebase.server", "homebase.secrets_store"):
        monkeypatch.setattr(f"{mod}.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")

    def build(n, *, flat=(), same_broker=None):
        wire = Wire()
        cfg = exit_cfg(n)
        adapters = mkadapters(cfg, wire, same_broker)
        app = create_app(cfg, adapters, background=False)
        eng = app.state.engine
        eng._now = Clock()
        go_live(eng, adapters, flat=flat)
        wire.clear()
        wire.rt = RT
        kill = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/api/kill")
        return kill, eng, adapters, wire

    return build


# --- (a) side by side, (c) the same calls, (d) the same journal -----------------------------------
def test_the_strategy_flatten_runs_the_accounts_side_by_side(tmp_path):
    eng, ads, wire, _ = mkexits(tmp_path, N, rt=RT)
    res, wall = timed(eng.flatten_strategy("nq930"))
    assert wire.peak_accounts == EXIT_CONCURRENCY                 # (a) never one after another,
    assert wall < N * FLAT_RTS * RT / 2                           #     never all eleven at once
    assert all(ad.flat for ad in ads.values())                    # (b)
    for a in ads:                                                 # (c)
        assert wire.of(a) == flatten_calls(a)
        assert status(eng, a) == ("done", "manual_flat")
    (rec,) = journal(tmp_path, "manual_flatten")                  # (d)
    assert rec["strategy"] == "nq930"
    assert rec["results"] == res == {a: flatten_acts(a) for a in ads} and list(res) == list(ads)
    ms = rec["flatten_ms"]                                        # timing only: the parts overlapped
    assert list(ms["accounts"]) == list(ads) and ms["total"] < sum(ms["accounts"].values())


def test_the_clock_flatten_runs_the_accounts_side_by_side(tmp_path):
    eng, ads, wire, clock = mkexits(tmp_path, N, rt=RT)
    clock.set_et(15, 56)
    _, wall = timed(eng.clock_tick())
    assert wire.peak_accounts == EXIT_CONCURRENCY
    assert wall < N * FLAT_RTS * RT / 2
    assert all(ad.flat for ad in ads.values())
    for a in ads:                                                 # ... then its sibling check, from the cache
        assert wire.of(a) == flatten_calls(a) + [f"get_order_status {a}-102"]
        assert status(eng, a) == ("done", "flat")
    recs = journal(tmp_path, "clock_flat")
    assert sorted(r["account"] for r in recs) == sorted(ads)      # one each
    for r in recs:
        assert (r["strategy"], r["actions"]) == ("nq930", flatten_acts(r["account"]))
        assert r["flat_ms"] >= FLAT_RTS * RT * 1000 * 0.9         # timing only: its own three round trips
    assert not journal(tmp_path, "clock_flat_failed") and not journal(tmp_path, "clock_error")


def test_the_kill_runs_the_accounts_side_by_side(kill_desk, tmp_path):
    kill, eng, ads, wire = kill_desk(N)
    out, wall = timed(kill())
    assert wire.peak_accounts == EXIT_CONCURRENCY
    assert wall < N * KILL_RTS * RT / 2
    assert all(ad.flat for ad in ads.values())
    for a in ads:                                 # its own flatten first, then the account-wide sweep
        assert wire.of(a) == flatten_calls(a) + ["cancel_all", "flatten_all"]
        assert status(eng, a) == ("done", "killed")
    swept = {"cancel_all": {"ok": True, "error": None}, "flatten_all": {"ok": True, "error": None}}
    assert out["ok"] and out["armed"] is False
    assert out["results"] == {a: swept for a in ads} and list(out["results"]) == list(ads)
    assert out["strategies"] == {f"nq930@{a}": flatten_acts(a) for a in ads}
    assert list(out["strategies"]) == [f"nq930@{a}" for a in ads]
    (rec,) = journal(tmp_path, "kill_switch")
    assert (rec["results"], rec["strategies"]) == (out["results"], out["strategies"])
    ms = rec["kill_ms"]                                           # timing only
    assert list(ms["accounts"]) == list(ads) and ms["sweep"] < sum(ms["accounts"].values())
    assert ms["total"] >= ms["strategies"] + ms["sweep"] - 0.2
    events = [r["event"] for r in journal(tmp_path)]
    assert events[-2:] == ["chart_trading_set", "kill_switch"]    # nothing new in between


@pytest.mark.parametrize("path, rts", [("flatten", FLAT_RTS), ("clock", FLAT_RTS), ("kill", KILL_RTS)])
def test_up_to_the_bound_every_account_is_done_in_one_accounts_round_trips(path, rts, tmp_path, kill_desk):
    n = EXIT_CONCURRENCY
    if path == "kill":
        kill, _, ads, wire = kill_desk(n)
        job = kill()
    else:
        eng, ads, wire, clock = mkexits(tmp_path, n, rt=RT)
        clock.set_et(15, 56)
        job = eng.clock_tick() if path == "clock" else eng.flatten_strategy("nq930")
    _, wall = timed(job)
    assert wire.peak_accounts == n and all(ad.flat for ad in ads.values())
    assert wall < 2 * rts * RT                    # about ONE account's round trips, not n times them


def test_two_runs_on_one_account_still_go_one_after_the_other(tmp_path):
    """Two strategies in NQ on the same accounts: a flatten sells the account's WHOLE net, so one
    account's runs never read it together -- the first sells 6, the second finds it flat."""
    for go in ("kill", "clock"):
        root = tmp_path / go
        root.mkdir()
        eng, ads, wire, clock = mkexits(root, 3, rt=RT / 3, strategies=("nq930", "nq945"))
        clock.set_et(15, 56)
        asyncio.run(eng.flatten_today() if go == "kill" else eng.clock_tick())
        check = (lambda a, n: [f"get_order_status {a}-{n}"]) if go == "clock" else (lambda a, n: [])
        for a, ad in ads.items():
            assert wire.of(a) == (flatten_calls(a, qty=6) + check(a, 102)
                                  + cancel_calls(a, n=103) + check(a, 104))
            assert [(o.side, o.qty) for o in ad.orders if o.order_type == "Market"] == [("Sell", 6)]
            assert ad.flat
        assert wire.peak_accounts == 3


@pytest.mark.parametrize("go", ["kill", "clock", "flatten"])
def test_two_desk_entries_on_one_broker_account_take_turns(go, tmp_path):
    """a03 is not pinned and landed on a02's broker account (long 6 between them). Side by side both
    would read 6 and both sell 6 -- short 6. They share a turn: a02 sells 6, a03 then reads flat."""
    eng, ads, wire, clock = mkexits(tmp_path, 3, rt=RT / 3, same_broker={"a03": "a02"})
    assert ads["a02"].net == 6 and ads["a03"].broker_key == ads["a02"].broker_key
    clock.set_et(15, 56)
    asyncio.run({"kill": eng.flatten_today, "clock": eng.clock_tick,
                 "flatten": lambda: eng.flatten_strategy("nq930")}[go]())
    check = (lambda a: [f"get_order_status {a}-102"]) if go == "clock" else (lambda a: [])
    assert wire.of("a02") == flatten_calls("a02", qty=6) + check("a02")
    assert wire.of("a03") == cancel_calls("a03") + check("a03")              # nothing left to sell
    assert not wire.overlapped("a02", "a03") and wire.overlapped("a01", "a02")
    order = [a for a, _ in wire.calls if a != "a01"]
    assert order == sorted(order)                                 # all of a02, then all of a03
    assert ads["a02"].net == 0 and all(ad.flat for ad in ads.values())


def test_the_kills_sweep_takes_turns_on_one_broker_account_too(kill_desk):
    kill, _, ads, wire = kill_desk(3, same_broker={"a03": "a02"})
    out, _ = timed(kill())
    assert not wire.overlapped("a02", "a03") and wire.overlapped("a01", "a02")
    assert wire.of("a03") == cancel_calls("a03") + ["cancel_all", "flatten_all"]
    assert ads["a02"].net == 0 and all(ad.flat for ad in ads.values())
    assert list(out["results"]) == ["a01", "a02", "a03"]


def test_a_tradovate_entry_is_known_by_its_broker_account(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)                      # demo, account number 66121477
    assert ad.broker_key == ("demo", 66121477)
    ad._acct_num = None                                           # not resolved yet: its own desk id
    assert ad.broker_key == "acct"


def test_each_account_keeps_a_raise_to_its_own_account(tmp_path):
    eng, ads, _, _ = mkexits(tmp_path, 3)

    async def fn(a):
        await asyncio.sleep(0)
        if a == "a02":
            raise ValueError("boom")
        return a.upper()

    got, took = asyncio.run(eng.each_account(list(ads), fn))
    assert got["a01"] == "A01" and got["a03"] == "A03" and list(got) == list(took) == list(ads)
    assert isinstance(got["a02"], ValueError) and all(isinstance(v, float) for v in took.values())


# --- (b) one bad day: a raise, a dead socket, a flat account, a 429 -- none stops another ----------
def test_a_bad_day_never_stops_the_kill_on_another_account(kill_desk, tmp_path):
    kill, eng, ads, wire = kill_desk(8, flat=("a02",))
    trouble(ads)
    out, _ = timed(kill())
    s = out["strategies"]
    assert s["nq930@a01"] == flatten_acts("a01") and s["nq930@a08"] == flatten_acts("a08")
    assert s["nq930@a02"] == [f"cancel {i}: ok" for i in legs("a02")]       # flat already: no market order
    assert s["nq930@a03"] == [UNREACHED]
    assert s["nq930@a04"] == REFUSED_429 and s["nq930@a06"] == UNREAD_429
    assert s["nq930@a05"] == BLEW_UP                                        # said, and the Kill went on
    assert f"cancel a07-101-sl: order/cancelorder {RATE_LIMITED}" in s["nq930@a07"]
    assert list(s) == [f"nq930@{a}" for a in ads]
    # the account-wide sweep then covers what the strategy's own flatten could not do
    down = {"ok": False, "error": "adapter not connected"}
    assert out["results"]["a03"] == {"cancel_all": down, "flatten_all": down}
    assert all(r["cancel_all"]["ok"] and r["flatten_all"]["ok"]
               for a, r in out["results"].items() if a != "a03")
    for a, ad in ads.items():
        if a == "a03":
            assert protected(ad, a)               # unreachable: nothing sent, nothing taken away
        else:
            assert ad.flat, a                     # flat, nothing working -- and never sold twice
    assert wire.of("a04") == flatten_calls("a04")[:2] + ["cancel_all", "flatten_all"]
    assert status(eng, "a02") == ("done", "tp") and status(eng, "a01") == ("done", "killed")
    assert status(eng, "a05") == ("live", None)   # not marked killed by a flatten that never ran
    assert journal(tmp_path, "kill_switch")[0]["strategies"] == s


def test_a_bad_day_never_stops_the_clock_on_another_account(tmp_path, monkeypatch):
    eng, ads, wire, clock = mkexits(tmp_path, 8, rt=RT / 3, flat=("a02",))
    trouble(ads)
    clock.set_et(15, 56)
    asyncio.run(eng.clock_tick())                                 # never raises: every run gets its tick
    assert ads["a01"].flat and ads["a08"].flat and ads["a02"].flat
    assert wire.of("a02") == ["get_order_status a02-102"]         # closed this morning: left alone
    for a in ("a03", "a04", "a05", "a06"):
        assert protected(ads[a], a) and status(eng, a) == ("live", None)
    failed = {r["account"]: r["actions"] for r in journal(tmp_path, "clock_flat_failed")}
    assert failed == {"a03": [UNREACHED], "a04": REFUSED_429, "a06": UNREAD_429}
    (err,) = journal(tmp_path, "clock_error")                     # the raise: journaled, on its own run
    assert (err["strategy"], err["account"], err["error"]) == ("nq930", "a05", "place_order blew up")
    flat = {r["account"]: r["actions"] for r in journal(tmp_path, "clock_flat")}
    assert set(flat) == {"a01", "a07", "a08"} and flat["a01"] == flatten_acts("a01")
    # a cancel refused after the market-out is SAID, not retried (as before): a07 is flat, its stop is not gone
    assert f"cancel a07-101-sl: order/cancelorder {RATE_LIMITED}" in flat["a07"]
    assert ads["a07"].net == 0 and ads["a07"].working == {"a07-101-sl"}

    later(monkeypatch, 6)                                         # the clock's own retry, 5 s on
    asyncio.run(eng.clock_tick())
    assert ads["a04"].flat and ads["a06"].flat                    # the 429 was once: flat now
    assert status(eng, "a04") == status(eng, "a06") == ("done", "flat")
    check = ["get_order_status a04-102"]
    assert wire.of("a04") == flatten_calls("a04")[:2] + check + flatten_calls("a04") + check
    assert [o.qty for o in ads["a04"].orders if o.order_type == "Market"] == [3, 3]   # refused, then sold: once
    assert protected(ads["a03"], "a03") and protected(ads["a05"], "a05")
    assert len(journal(tmp_path, "clock_error")) == 2


def test_a_bad_day_never_stops_the_strategy_flatten_on_another_account(tmp_path):
    eng, ads, wire, _ = mkexits(tmp_path, 8, rt=RT / 3, flat=("a02",))
    trouble(ads)
    res = asyncio.run(eng.flatten_strategy("nq930"))
    assert res["a01"] == flatten_acts("a01") and res["a08"] == flatten_acts("a08")
    assert res["a02"] == [f"cancel {i}: ok" for i in legs("a02")]
    assert (res["a03"], res["a04"], res["a05"], res["a06"]) == ([UNREACHED], REFUSED_429, BLEW_UP, UNREAD_429)
    assert list(res) == list(ads) and journal(tmp_path, "manual_flatten")[0]["results"] == res
    assert ads["a01"].flat and ads["a02"].flat and ads["a08"].flat
    for a in ("a03", "a04", "a05", "a06"):                        # not flat, and SAID so: still protected
        assert protected(ads[a], a) and status(eng, a) == ("live", None)
    assert ads["a07"].net == 0 and ads["a07"].working == {"a07-101-sl"}
    # no retry of its own (as before): the second click finishes what the 429 refused
    res = asyncio.run(eng.flatten_strategy("nq930"))
    assert res["a04"] == flatten_acts("a04") and res["a06"] == flatten_acts("a06")
    for a in ("a04", "a06", "a07"):
        assert ads[a].flat, a
    assert protected(ads["a03"], "a03") and protected(ads["a05"], "a05")
    assert all(ad.broker.net >= 0 for ad in ads.values())         # nobody was sold twice
