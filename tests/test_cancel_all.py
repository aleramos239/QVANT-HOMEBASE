"""POST /api/trade/cancel-all {client_id, account}: cancel every working order of ONE account (package 9, D8).
It never flattens, never reaches another account, and keeps cancel-by-id's bot guards. No broker, no network."""
from __future__ import annotations

import pytest

from homebase.charts.desk import ACTIONS as CHART_ACTIONS
from homebase.desk.trading import parse_cancel_all
from tests.test_trading_guards import WORKING
from tests.trading_util import ESC, NQC, journal, mkdesk, run

STOP = {**WORKING, "order_id": "88", "type": "Stop", "side": "Sell", "price": None, "stop_price": 95.0}


def cancel_all(desk, cid="k1", account="a1", **kw):
    return run(desk.cancel_all({"client_id": cid, "account": account, **kw}))["results"]


def test_the_chart_service_relays_the_new_action():
    assert "cancel-all" in CHART_ACTIONS


def test_the_body_is_one_account_and_a_client_id():
    assert parse_cancel_all({"client_id": "c", "account": "a1"}) == ("c", "a1")
    for bad in ({"account": "a1"}, {"client_id": "c"}, {"client_id": "c", "accounts": ["a1"]},
                {"client_id": "c", "account": ""}):
        with pytest.raises(ValueError):
            parse_cancel_all(bad)


def test_it_cancels_every_working_order_of_that_account_and_nothing_else(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    a1, a2 = ads["a1"], ads["a2"]
    a1.net = 2
    a1.view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.0}]
    a1.view["orders"] = [dict(WORKING), {**STOP, "order_id": "55", "symbol": ESC}]
    a2.view["orders"] = [{**WORKING, "order_id": "300"}]
    r = cancel_all(desk)["a1"]
    assert r["ok"] is True and r["cancelled"] == 2
    assert sorted(a1.cancelled) == ["55", "77"]
    assert a2.cancelled == [] and a2.sym_cancelled == []          # another account is never touched
    assert a1.flattened == [] and a1.flatten_calls == 0           # never a flatten
    assert a1.cancel_all_calls == 0 and a1.sym_cancelled == []    # the adapter's own sweeps are not used
    assert a1.orders == [] and a1.net == 2                         # no order placed, the position stays


def test_the_account_in_the_body_is_the_only_one_named_in_the_answer(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a2"].view["orders"] = [{**WORKING, "order_id": "300"}]
    out = cancel_all(desk, account="a1")
    assert list(out) == ["a1"] and out["a1"]["refused"] is True and "no working orders" in out["a1"]["error"]
    assert ads["a2"].cancelled == []


def test_works_with_chart_trading_off_like_cancel(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, enabled=False)
    ads["a1"].view["orders"] = [dict(WORKING)]
    assert cancel_all(desk)["a1"]["ok"] is True and ads["a1"].cancelled == ["77"]


def test_a_failed_cancel_is_named_and_the_rest_still_go(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [dict(WORKING), {**WORKING, "order_id": "78"}]
    ads["a1"].fail_cancel_ids.add("77")
    r = cancel_all(desk)["a1"]
    assert r["ok"] is False and "77" in r["error"] and r["cancelled"] == 1
    assert sorted(ads["a1"].cancelled) == ["77", "78"]


def test_a_bot_order_refuses_the_whole_action_and_nothing_is_cancelled(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    st = eng._state("nq930", "a1")
    st.status, st.upper_id = "done", "88"                           # a finished bot's own stop is still the bot's
    ads["a1"].view["orders"] = [dict(WORKING), dict(STOP)]
    r = cancel_all(desk)["a1"]
    assert r["refused"] is True and "belongs to the nq930 bot" in r["error"]
    assert ads["a1"].cancelled == []


@pytest.mark.parametrize("status", ["placing", "placed", "live"])
def test_a_busy_bot_on_the_contract_refuses_unless_the_orders_are_from_the_chart(tmp_path, status):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    eng._state("nq930", "a1").status = status
    ads["a1"].view["orders"] = [dict(WORKING)]                       # not placed from the chart: may be the bot's
    r = cancel_all(desk)["a1"]
    assert r["refused"] is True and "use Kill" in r["error"]
    assert ads["a1"].cancelled == []


def test_an_order_with_no_contract_yet_refuses_everything(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [dict(WORKING), {**WORKING, "order_id": "9", "symbol": None}]
    r = cancel_all(desk)["a1"]
    assert r["refused"] is True and "not resolved" in r["error"] and ads["a1"].cancelled == []


def test_a_repeat_of_the_same_client_id_cancels_once_and_is_journaled(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [dict(WORKING)]
    first = cancel_all(desk)
    assert cancel_all(desk) == first and ads["a1"].cancelled == ["77"]
    ev = [e for e in journal(tmp_path) if e["event"] == "manual_cancel"]
    assert len(ev) == 1 and ev[0]["scope"] == "account" and ev[0]["account"] == "a1" and ev[0]["source"] == "chart"
    assert ev[0]["order_ids"] == ["77"]


def test_an_unknown_account_is_refused(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    r = cancel_all(desk, account="zz")["zz"]
    assert r["refused"] is True and r["error"] == "unknown account 'zz'"
