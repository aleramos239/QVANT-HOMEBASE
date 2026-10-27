"""Audit 2026-10-27, chart group: homebase/routes/accounts.py (selftest-order, account remove)."""
import pytest

from tests.test_netguard import DESK, desk  # noqa: F401  (the fixture: one non-paper account "main" on a fake adapter)


def post(c, **body):
    return c.post("/api/selftest-order", headers={"origin": DESK},
                  json={"account": "main", "symbol": "NQ", "ref_price": 24500.0, "plain": True, **body})


def test_selftest_refuses_an_account_with_a_position(desk):
    async def metrics():
        return {"open_positions": [{"symbol": "NQZ6", "net": 2}], "working_orders": 0}
    desk.adapter.get_metrics = metrics
    r = post(desk)
    assert r.status_code == 409 and "idle account" in r.json()["detail"]
    assert desk.adapter.orders == [] and desk.adapter.flatten_calls == 0


def test_selftest_refuses_an_account_with_a_working_order(desk):
    async def metrics():
        return {"open_positions": [], "working_orders": 1}
    desk.adapter.get_metrics = metrics
    assert post(desk).status_code == 409 and desk.adapter.orders == []


def test_selftest_refuses_a_live_account(desk):
    desk.cfg.accounts["main"].live = True
    r = post(desk)
    assert r.status_code == 409 and desk.adapter.orders == []


def test_selftest_refuses_an_unreadable_account(desk):
    async def metrics():
        raise RuntimeError("socket")
    desk.adapter.get_metrics = metrics
    assert post(desk).status_code == 409 and desk.adapter.orders == []


def test_selftest_never_flattens_or_cancels_the_whole_account(desk):
    a = desk.adapter
    a.fail_cancel_ids.add("plain")                     # the cancel fails
    a.net = 1                                          # and the test order filled

    async def metrics():
        return {"open_positions": [], "working_orders": 0}
    a.get_metrics = metrics
    calls = []

    async def flat_sym(symbol):
        calls.append(symbol)
        from homebase.broker.base import OrderResult
        return OrderResult(ok=True)
    a.flatten_symbol = flat_sym

    async def net(symbol):
        return 0 if calls else 1
    a.get_net_position = net
    r = post(desk)
    assert r.status_code == 200
    assert a.cancel_all_calls == 0 and a.flatten_calls == 0 and calls == ["NQ"]


def test_ui_remove_refuses_a_connected_account_whose_caches_have_not_seeded(desk):
    r = desk.post("/api/accounts/remove", headers={"origin": DESK}, json={"account": "main"})
    assert r.status_code == 409 and "seeded" in r.json()["detail"]
    assert "main" in desk.cfg.accounts
