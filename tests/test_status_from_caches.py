"""/api/status never costs Tradovate a request (2026-09-29).

The desk page polls /api/status every 2.5 s; each poll used to read cashBalance/list +
position/list for every connected account (~3 requests a second on the Apex user).
Balances and positions now come from the push-fed caches; one background refresh per
Tradovate user a minute covers what the pushes miss. Fake sockets only.
"""
from __future__ import annotations

import datetime as dt

from homebase.broker.login_budget import LoginBudget
from homebase.broker.tradovate import TradovateAdapter
from homebase.broker.tradovate_ws import TradovateWS
from tests.test_adapter_caches import broker, push
from tests.test_login_budget import KEY, S429, desk  # noqa: F401 — the two-entry desk
from tests.test_tradovate import FakeSocket, run

ME, SIB = 66121477, 66121478


def _adapter(tmp_path, answer, aid="acct", acct=ME):
    ad = TradovateAdapter(aid, env="demo", keyring_key=KEY, state_dir=tmp_path / aid)
    ws = TradovateWS(token="t")
    ws.ws = FakeSocket(ws, answer)
    ws.connected = True
    ad._ws, ad._acct_num, ad._acct_name, ad._connected = ws, acct, aid.upper(), True
    ad.caches_seeded = True
    ad._contracts[3267315] = "NQZ6"
    return ad


def test_get_metrics_reads_the_caches_and_sends_nothing(tmp_path):
    answer, sent = broker(positions=[], cash=[])
    ad = _adapter(tmp_path, answer)
    push(ad, "cashBalance", {"accountId": ME, "amount": 51234.5, "realizedPnL": 120.0})
    push(ad, "position", {"accountId": ME, "contractId": 3267315, "netPos": -2})
    push(ad, "position", {"accountId": ME + 5, "contractId": 3267315, "netPos": 9})  # not ours
    for _ in range(20):                      # 20 page polls
        m = run(ad.get_metrics())
    assert sent == []
    assert m["balance"] == 51234.5 and m["realized_pnl"] == 120.0
    assert m["open_positions"] == [{"symbol": "NQZ6", "net": -2}]
    assert m["cache_seeded"] is True and 0 <= m["cache_age_s"] < 5


def test_one_refresh_per_user_covers_the_siblings_and_a_push_in_flight_wins(tmp_path):
    lists = {"positions": [{"accountId": ME, "contractId": 3267315, "netPos": 1},
                           {"accountId": SIB, "contractId": 3267315, "netPos": 4}],
             "cash": [{"accountId": ME, "amount": 50000.0},
                      {"accountId": SIB, "amount": 48000.0}]}
    answer, sent = broker(positions=lists["positions"], cash=lists["cash"])
    a = _adapter(tmp_path, answer, "a", ME)
    b_answer, b_sent = broker()
    b = _adapter(tmp_path, b_answer, "b", SIB)
    # a push lands on b while a's read is in flight: newer than the snapshot
    orig = a._ws.position_list

    async def slow_list():
        out = await orig()
        push(b, "position", {"accountId": SIB, "contractId": 3267315, "netPos": 0})
        return out

    a._ws.position_list = slow_list
    run(a.refresh_snapshot([b]))
    assert [e for e, *_ in sent] == ["position/list", "cashBalance/list"]
    assert b_sent == []                                         # b's socket untouched
    assert run(a.get_metrics())["open_positions"] == [{"symbol": "NQZ6", "net": 1}]
    mb = run(b.get_metrics())
    assert mb["balance"] == 48000.0 and mb["open_positions"] == []   # the push won


def test_the_refresh_is_one_per_user_and_skipped_in_a_cooldown_and_at_the_fire(desk):
    calls = []
    for aid, ad in desk.adapters.items():
        async def refresh(siblings=(), aid=aid):
            calls.append((aid, [s.account_id for s in siblings]))
        ad.refresh_snapshot = refresh
    et = {"now": dt.datetime(2026, 9, 29, 11, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))}
    desk.app.state.engine.now_et = lambda: et["now"]
    run(desk.app.state.refresh_snapshots())
    assert calls == [("dead", ["live"])]                        # both entries, one read
    et["now"] = et["now"].replace(hour=9, minute=29)
    run(desk.app.state.refresh_snapshots())
    assert len(calls) == 1                                      # never around the fire
    et["now"] = et["now"].replace(hour=10)
    desk.app.state.login_budget.note_error(KEY, S429)
    run(desk.app.state.refresh_snapshots())
    assert len(calls) == 1                                      # never in a cool-down


def test_status_polls_never_reach_the_broker(desk):
    reads = []
    for ad in desk.adapters.values():
        ad.get_balance = lambda: reads.append(1)                # would be a request
        ad.get_net_position = lambda s: reads.append(1)
    for _ in range(10):
        st = desk.get("/api/status").json()
    assert reads == [] and set(st["accounts"]) == {"dead", "live"}
