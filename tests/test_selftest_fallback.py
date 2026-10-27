"""S2: when the self-test's own cancel fails, the fallback (cancel EVERY order, flatten the WHOLE account) is not run
on any broker account while the desk is armed -- live, or funded / demo (Apex PA and Lucid accounts are live=False);
disarmed, or on a paper account, it runs as before. Fake adapter only."""
from __future__ import annotations

import pytest

from tests.test_netguard import DESK, desk  # noqa: F401  (the desk fixture: a fake adapter, no network, no broker)

BODY = {"account": "main", "symbol": "NQ", "ref_price": 24500.0, "plain": True}


def selftest(desk, *, live, armed, paper=False):
    a = desk.cfg.accounts["main"]
    a.live, a.paper, desk.cfg.armed = live, paper, armed
    desk.adapter.fail_cancel_ids = {"plain"}      # the test order's own cancel fails ...
    desk.adapter.net = 1                          # ... and a position is left on the account
    r = desk.post("/api/selftest-order", headers={"origin": DESK}, json=BODY)
    assert r.status_code == 200
    return r.json()["trace"]


@pytest.mark.parametrize("live", [True, False])   # False: a funded prop account (PAAPEX..., LTF...) or a demo one
def test_armed_on_a_broker_account_the_fallback_touches_nothing_and_says_why(desk, live):
    t = selftest(desk, live=live, armed=True)
    assert desk.adapter.cancel_all_calls == 0 and desk.adapter.flatten_calls == 0
    said = ("Not done: the desk is armed and main is a broker account (live, funded or demo), so the self-test does not "
            "cancel every order or flatten the account. Check it on the broker.")
    assert t["cancel_all_fallback"] == {"ok": False, "error": said}
    assert t["emergency_flatten"] == {"ok": False, "error": said}


@pytest.mark.parametrize("live,armed,paper", [(True, False, False), (False, False, False), (False, True, True)])
def test_disarmed_or_paper_the_fallback_runs_as_before(desk, live, armed, paper):
    t = selftest(desk, live=live, armed=armed, paper=paper)
    assert desk.adapter.cancel_all_calls == 1 and desk.adapter.flatten_calls == 1
    assert t["cancel_all_fallback"] == {"ok": True, "error": None}
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
