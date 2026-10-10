"""Step B (B3): a Lab strategy's past runs. It trades in ROUNDS, several a day on one account: a `lab_round` line
starts a new run and the row says which round it was; a round is not the 09:30 fire, so its row carries no fire_ms /
latency_ms. With no `lab_round` line in the journal the output is what it always was. Pure."""
from __future__ import annotations

from homebase.bothistory import runs
from tests.test_bothistory import TODAY, ms, placed, rec

LAB = "lab_pp"
D = "2026-09-14"


def history(records, strategy=LAB, today=TODAY):
    return runs(records, strategy, symbol="NQ", today=today, days=120)


def round_(n, hms, account="a1", date=D):
    return rec("lab_round", date, hms, strategy=LAB, account=account, round=n, qty=1, source="lab", iid={"Buy": n},
               legs=[{"iid": n, "side": "Buy", "entry": "Stop", "entry_price": 110.0, "sl_px": 105.0}])


def leg(hms, account="a1", date=D, px=110.0):
    return rec("placed", date, hms, strategy=LAB, account=account, source="lab", kind="bars", side="Buy",
               entry="Stop", entry_price=px, ref_px=px, sl=px - 5, tp=px + 10, qty=1, order_id="7", place_ms=40)


def fill(hms, px, account="a1", date=D):
    return rec("entry_fill", date, hms, strategy=LAB, account=account, side="Buy", fill=px, anchor=110.0, qty_filled=1)


def out(hms, px, reason, account="a1", date=D):
    return rec("exit_fill", date, hms, strategy=LAB, account=account, reason=reason, fill=px, pnl=0.0)


TWO = [round_(1, "09:40:00"), leg("09:40:00"), fill("09:41:00", 110.25), out("09:50:00", 120.25, "tp"),
       round_(2, "10:05:00"), leg("10:05:00", px=115.0), fill("10:06:00", 115.25), out("10:09:00", 110.25, "sl")]


def test_two_rounds_in_a_day_on_one_account_are_two_runs(tmp_path):
    one, two = history(TWO)
    assert (one["date"], one["account"], one["round"], one["status"]) == (D, "a1", 1, "traded")
    assert (two["date"], two["account"], two["round"], two["status"]) == (D, "a1", 2, "traded")
    assert one["legs"] == [{"side": "Buy", "price": 110.0, "ts": ms(D, "09:40:00")}]
    assert (one["entry"]["price"], one["exit"]["price"], one["exit"]["kind"], one["pnl_usd"]) == (110.25, 120.25, "tp", 196.0)
    assert (two["entry"]["price"], two["exit"]["price"], two["exit"]["kind"], two["pnl_usd"]) == (115.25, 110.25, "sl", -104.0)
    assert two["entry"]["ts"] == ms(D, "10:06:00") and two["legs"][0]["price"] == 115.0     # each round its own facts


def test_a_round_is_not_the_930_fire(tmp_path):
    for row in history(TWO):
        assert "fire_ms" not in row and "latency_ms" not in row
    assert [r["placed_ms"] for r in history(TWO)] == [ms(D, "09:40:00"), ms(D, "10:05:00")]


def test_with_no_lab_round_line_the_output_is_what_it_was():
    recs = [placed("2026-09-14", "a1"),
            rec("entry_fill", "2026-09-14", "09:30:02", strategy="nq930", account="a1", side="Buy", fill=30910.25,
                anchor=30910.0, qty_filled=2),
            rec("exit_fill", "2026-09-14", "09:41:10", strategy="nq930", account="a1", reason="tp", fill=30925.25, pnl=600.0)]
    row, = history(recs + TWO, strategy="nq930")                                   # the Lab's lines are another strategy's
    assert row == {"date": "2026-09-14", "account": "a1", "status": "traded",
                   "legs": [{"side": "Buy", "price": 30910.0, "ts": ms("2026-09-14", "09:30:00")},
                            {"side": "Sell", "price": 30890.0, "ts": ms("2026-09-14", "09:30:00")}],
                   "fire_ms": ms("2026-09-14", "09:30:00"), "placed_ms": ms("2026-09-14", "09:30:00"), "latency_ms": 0,
                   "entry": {"side": "Buy", "price": 30910.25, "ts": ms("2026-09-14", "09:30:02"), "slip_ticks": 1.0},
                   "exit": {"price": 30925.25, "ts": ms("2026-09-14", "09:41:10"), "kind": "tp"}, "pnl_usd": 592.0}
    assert "round" not in row


def test_a_round_the_broker_refused_and_the_trade_after_it():
    recs = [round_(1, "09:40:00"), rec("place_failed", D, "09:40:00", strategy=LAB, account="a1", error="margin"),
            round_(2, "10:05:00"), leg("10:05:00"), fill("10:06:00", 110.25), out("10:09:00", 120.25, "tp")]
    bad, good = history(recs)
    assert (bad["round"], bad["status"], bad["reason"], bad["legs"]) == (1, "error", "margin", [])
    assert (good["round"], good["status"], good["pnl_usd"]) == (2, "traded", 196.0)


def test_rounds_on_two_accounts_and_two_days_stay_apart():
    recs = [round_(1, "09:40:00", "a1"), round_(1, "09:40:00", "a2"), leg("09:40:00", "a1"), leg("09:40:00", "a2"),
            fill("09:41:00", 110.25, "a1"), fill("09:41:01", 110.5, "a2"), out("09:50:00", 120.25, "tp", "a1"),
            out("09:51:00", 105.5, "sl", "a2"),
            round_(1, "09:45:00", "a1", "2026-09-15"), leg("09:45:00", "a1", "2026-09-15"),
            fill("09:46:00", 110.25, "a1", "2026-09-15"), out("09:55:00", 120.25, "tp", "a1", "2026-09-15")]
    rows = history(recs)
    assert [(r["date"], r["account"], r["round"], r["exit"]["kind"]) for r in rows] == \
        [(D, "a1", 1, "tp"), (D, "a2", 1, "sl"), ("2026-09-15", "a1", 1, "tp")]


def test_todays_open_round_waits_for_its_result_and_the_closed_ones_are_there():
    recs = TWO + [round_(3, "10:30:00"), leg("10:30:00")]
    assert [r["round"] for r in history(recs, today=D)] == [1, 2]                   # round 3 is still working
    assert [(r["round"], r["status"]) for r in history(recs)] == [(1, "traded"), (2, "traded"), (3, "no_fill")]


def test_a_flatten_and_a_kill_end_the_round_that_is_running_not_the_ones_before():
    recs = TWO + [round_(3, "10:30:00"), leg("10:30:00"), fill("10:31:00", 110.25),
                  rec("manual_flatten", D, "10:40:00", strategy=LAB, results={"a1": ["market Sell 1: ok"]}),
                  out("10:40:01", 111.0, "manual_flat")]
    one, two, three = history(recs)
    assert (one["exit"]["kind"], two["exit"]["kind"], three["exit"]["kind"]) == ("tp", "sl", "flat")
    killed = TWO + [round_(3, "10:30:00"), leg("10:30:00"), fill("10:31:00", 110.25),
                    rec("strategy_killed", D, "10:40:00", strategy=LAB, results={"a1": {"ok": True, "acted": True}})]
    assert [r["status"] for r in history(killed)] == ["traded", "traded", "killed"]
