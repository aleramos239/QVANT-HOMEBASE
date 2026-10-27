"""S2 + the audit: when the self-test's own cancel fails, nothing sweeps the WHOLE account (no cancel_all, no flatten_all). A
test position left behind is closed on its symbol only -- and not at all on any broker account while the desk is armed (live,
or funded / demo: Apex PA and Lucid accounts are live=False), where the trace says why. Fake adapter only."""
from __future__ import annotations

import pytest

from tests.test_netguard import DESK, desk  # noqa: F401  (the desk fixture: a fake adapter, no network, no broker)

BODY = {"account": "main", "symbol": "NQ", "ref_price": 24500.0, "plain": True}


def selftest(desk, *, live, armed, paper=False):
    a = desk.cfg.accounts["main"]
    a.live, a.paper, desk.cfg.armed = live, paper, armed
    desk.adapter.fail_cancel_ids = {"plain"}      # the test order's own cancel fails ...
    desk.adapter.symbol_flats = []
    desk.adapter.net = 0                          # flat at the start (the audit refuses an account with a position) ...

    async def net(symbol):                        # ... and a position is left once the test order is out
        return 0 if desk.adapter.symbol_flats or not desk.adapter.orders else 1
    desk.adapter.get_net_position = net

    async def flat_sym(symbol):
        from homebase.broker.base import OrderResult
        desk.adapter.symbol_flats.append(symbol)
        return OrderResult(ok=True)
    desk.adapter.flatten_symbol = flat_sym
    r = desk.post("/api/selftest-order", headers={"origin": DESK}, json=BODY)
    assert r.status_code == 200
    return r.json()["trace"]


@pytest.mark.parametrize("live", [False])   # a funded prop account (PAAPEX..., LTF...) or a demo one (a live one is refused up front)
def test_armed_on_a_broker_account_the_fallback_touches_nothing_and_says_why(desk, live):
    t = selftest(desk, live=live, armed=True)
    assert desk.adapter.cancel_all_calls == 0 and desk.adapter.flatten_calls == 0 and desk.adapter.symbol_flats == []
    said = ("Not done: the desk is armed and main is a broker account (live, funded or demo), so the self-test does not "
            "cancel every order or flatten the account. Check it on the broker.")
    assert "cancel_all_fallback" not in t
    assert t["emergency_flatten"] == {"ok": False, "error": said}


@pytest.mark.parametrize("live,armed,paper", [(False, False, False), (False, True, True)])
def test_disarmed_or_paper_only_the_test_symbol_is_closed(desk, live, armed, paper):
    t = selftest(desk, live=live, armed=armed, paper=paper)
    assert desk.adapter.cancel_all_calls == 0 and desk.adapter.flatten_calls == 0 and desk.adapter.symbol_flats == ["NQ"]
    assert t["emergency_flatten"] == {"ok": True, "error": None}


def test_an_account_removed_during_the_wait_still_gets_its_test_order_cancelled_and_journaled(desk):
    """The paper flag is read once, at the top: the account going while the test order waits never skips its own cancel."""
    import json

    async def metrics_then_remove():
        desk.cfg.accounts.pop("main", None)       # removed while the test order is out
        return {}
    desk.adapter.get_metrics = metrics_then_remove
    desk.cfg.armed = True
    r = desk.post("/api/selftest-order", headers={"origin": DESK}, json=BODY)
    assert r.status_code == 200 and r.json()["trace"]["cancelled"] == {"ok": True, "error": None}
    assert desk.adapter.cancelled == ["plain"]
    lines = [json.loads(x) for x in (desk.tmp / "journal.jsonl").read_text().splitlines()]
    assert any(e["event"] == "selftest_order" and e.get("cancelled") == {"ok": True, "error": None} for e in lines)
