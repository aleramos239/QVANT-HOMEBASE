"""The bot's past runs, rebuilt from the desk journal. Pure: no broker, no network."""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from homebase.bothistory import JournalCache, parse_lines, runs

TODAY = "2026-09-18"      # a Friday


def rec(event, date, hms="09:30:00", **data):
    et = f"{date}T{hms}-04:00"
    return {"ts": dt.datetime.fromisoformat(et).timestamp(), "et": et, "event": event, **data}


def ms(date, hms):
    return int(dt.datetime.fromisoformat(f"{date}T{hms}-04:00").timestamp() * 1000)


def placed(date, account, upper=30910.0, lower=30890.0, qty=2, strategy="nq930"):
    return rec("placed", date, "09:30:00", strategy=strategy, account=account, source="timer",
               upper=upper, lower=lower, qty=qty, upper_id="1", lower_id="2", place_ms=90)


def history(records, days=120, strategy="nq930"):
    return runs(records, strategy, symbol="NQ", today=TODAY, days=days)


def test_a_tp_day_and_an_sl_day_with_net_dollars():
    recs = [
        placed("2026-09-14", "a1"),
        rec("entry_fill", "2026-09-14", "09:30:02", strategy="nq930", account="a1", side="Buy",
            fill=30910.25, anchor=30910.0, qty_filled=2),
        rec("exit_fill", "2026-09-14", "09:41:10", strategy="nq930", account="a1", reason="tp",
            fill=30925.25, pnl=600.0),
        placed("2026-09-15", "a1", upper=31010.0, lower=30990.0, qty=1),
        rec("entry_fill", "2026-09-15", "09:30:05", strategy="nq930", account="a1", side="Sell",
            fill=30989.75, anchor=30990.0, qty_filled=1),
        rec("exit_fill", "2026-09-15", "09:33:00", strategy="nq930", account="a1", reason="sl",
            fill=30994.75, pnl=-100.0),
    ]
    tp, sl = history(recs)
    assert tp == {
        "date": "2026-09-14", "account": "a1", "status": "traded",
        "legs": [{"side": "Buy", "price": 30910.0, "ts": ms("2026-09-14", "09:30:00")},
                 {"side": "Sell", "price": 30890.0, "ts": ms("2026-09-14", "09:30:00")}],
        "entry": {"side": "Buy", "price": 30910.25, "ts": ms("2026-09-14", "09:30:02")},
        "exit": {"price": 30925.25, "ts": ms("2026-09-14", "09:41:10"), "kind": "tp"},
        "pnl_usd": 592.0}                        # 15 pts x $20 x 2, less $4 x 2 round trips
    assert (sl["status"], sl["entry"]["side"], sl["exit"]["kind"], sl["pnl_usd"]) == \
        ("traded", "Sell", "sl", -104.0)          # -5 pts x $20 x 1 - $4


def test_a_skipped_account_and_a_gate_chop_day():
    recs = [rec("timer_skipped", "2026-09-14", "09:28:31", strategy="nq930", reason="manual_position",
                account="a1", net=1, orders=[]),
            rec("timer_skipped", "2026-09-15", "09:30:00", strategy="nq930", reason="gate_chop", adx=12.0)]
    a, b = history(recs)
    assert a == {"date": "2026-09-14", "account": "a1", "status": "skipped",
                 "reason": "manual_position", "legs": []}
    assert b == {"date": "2026-09-15", "account": None, "status": "skipped",   # every account
                 "reason": "gate_chop", "legs": []}


def test_refused_days_but_a_late_already_traded_refusal_never_hides_a_trade():
    recs = [rec("alert_refused", "2026-09-14", "09:30:00", strategy="nq930", reason="outside_window"),
            rec("signal_refused", "2026-09-15", "09:30:00", strategy="nq930", reason="bad_signal"),
            placed("2026-09-16", "a1"),
            rec("alert_refused", "2026-09-16", "09:30:01", strategy="nq930", reason="already_traded"),
            rec("cancelled_unfilled", "2026-09-16", "12:55:00", strategy="nq930", account="a1")]
    out = history(recs)
    assert [(r["date"], r["account"], r["status"], r.get("reason")) for r in out] == [
        ("2026-09-14", None, "refused", "outside_window"),
        ("2026-09-15", None, "refused", "bad_signal"),
        ("2026-09-16", "a1", "no_fill", None)]


def test_no_fill_keeps_its_legs_and_has_no_dollars():
    recs = [placed("2026-09-14", "a1"),
            rec("cancelled_unfilled", "2026-09-14", "12:55:00", strategy="nq930", account="a1")]
    (r,) = history(recs)
    assert r["status"] == "no_fill" and len(r["legs"]) == 2
    assert "entry" not in r and "exit" not in r and "pnl_usd" not in r


def test_malformed_lines_are_skipped():
    good = json.dumps(placed("2026-09-14", "a1"))
    lines = ["not json", "[1]", "null", "7", '{"event": "placed"', "\xff\xfe", good, ""]
    recs = parse_lines(lines)
    assert len(recs) == 1
    (r,) = history(recs + [{"event": "exit_fill"}, {"et": 5, "event": "placed", "strategy": "nq930"}])
    assert r["account"] == "a1"


def test_two_accounts_on_one_day():
    recs = [placed("2026-09-14", "a2", qty=1), placed("2026-09-14", "a1"),
            rec("entry_fill", "2026-09-14", "09:30:02", strategy="nq930", account="a1", side="Buy",
                fill=30910.0, qty_filled=2),
            rec("exit_fill", "2026-09-14", "09:40:00", strategy="nq930", account="a1", reason="tp",
                fill=30925.0),
            rec("cancelled_unfilled", "2026-09-14", "12:55:00", strategy="nq930", account="a2")]
    a1, a2 = history(recs)
    assert (a1["account"], a1["status"], a1["pnl_usd"]) == ("a1", "traded", 592.0)
    assert (a2["account"], a2["status"]) == ("a2", "no_fill")


def test_an_unmatched_exit_has_no_dollars_and_a_split_entry_uses_the_average():
    recs = [placed("2026-09-14", "a1"),
            rec("exit_fill", "2026-09-14", "09:40:00", strategy="nq930", account="a1", reason="exit",
                fill=30925.0),
            placed("2026-09-15", "a1"),
            rec("entry_fill", "2026-09-15", "09:30:02", strategy="nq930", account="a1", side="Buy",
                fill=30910.0, qty_filled=1),
            rec("entry_fill", "2026-09-15", "09:30:03", strategy="nq930", account="a1", side="Buy",
                fill=30910.5, qty_filled=2),
            rec("exit_fill", "2026-09-15", "09:40:00", strategy="nq930", account="a1", reason="tp",
                fill=30925.5)]
    a, b = history(recs)
    assert a["exit"]["kind"] == "other" and "pnl_usd" not in a and "entry" not in a
    assert b["entry"] == {"side": "Buy", "price": 30910.5, "ts": ms("2026-09-15", "09:30:02")}
    assert b["pnl_usd"] == 592.0


def test_errors_kills_and_flat_exits():
    recs = [rec("place_failed", "2026-09-14", "09:30:00", strategy="nq930", account="a1",
                leg="upper", error="rejected"),
            placed("2026-09-15", "a1"),
            rec("both_filled_emergency", "2026-09-15", "09:31:00", strategy="nq930", account="a1"),
            placed("2026-09-16", "a1"),
            rec("entry_fill", "2026-09-16", "09:30:02", strategy="nq930", account="a1", side="Buy",
                fill=30910.0, qty_filled=2),
            rec("kill_switch", "2026-09-16", "10:00:00", results={},
                strategies={"nq930@a1": ["market Sell 2: ok"], "es930@a1": []}),
            rec("exit_fill", "2026-09-16", "10:00:01", strategy="nq930", account="a1", reason="sl",
                fill=30905.0),
            rec("strategy_killed", "2026-09-17", "09:00:00", strategy="nq930", results={}),
            placed("2026-09-10", "a1"),
            rec("entry_fill", "2026-09-10", "09:30:02", strategy="nq930", account="a1", side="Buy",
                fill=30910.0, qty_filled=2),
            rec("clock_flat", "2026-09-10", "15:55:00", strategy="nq930", account="a1", actions=[]),
            rec("exit_fill", "2026-09-10", "15:55:01", strategy="nq930", account="a1", reason="tp",
                fill=30915.0)]
    out = {r["date"]: r for r in history(recs)}
    assert (out["2026-09-14"]["status"], out["2026-09-14"]["reason"]) == ("error", "rejected")
    assert (out["2026-09-15"]["status"], out["2026-09-15"]["reason"]) == ("error", "both_filled")
    k = out["2026-09-16"]
    assert (k["status"], k["exit"]["kind"], k["pnl_usd"]) == ("killed", "flat", -208.0)
    assert out["2026-09-17"] == {"date": "2026-09-17", "account": None, "status": "killed",
                                 "reason": "killed from the chart", "legs": []}
    assert (out["2026-09-10"]["status"], out["2026-09-10"]["exit"]["kind"]) == ("traded", "flat")


def test_a_chart_kill_marks_only_the_accounts_it_acted_on():
    recs = [placed("2026-09-14", "a1"), placed("2026-09-14", "a2"),
            rec("strategy_killed", "2026-09-14", "09:35:00", strategy="nq930",
                results={"a1": {"ok": True, "acted": True, "actions": ["cancel 1: ok"]},
                         "a2": {"ok": True, "note": "nothing to do"}}),
            rec("cancelled_unfilled", "2026-09-14", "12:55:00", strategy="nq930", account="a2")]
    a1, a2 = history(recs)
    assert a1["status"] == "killed" and a2["status"] == "no_fill"


def test_window_other_strategies_and_todays_unresolved_run():
    recs = [placed("2026-05-01", "a1"),                          # older than the window
            rec("cancelled_unfilled", "2026-05-01", "12:55:00", strategy="nq930", account="a1"),
            placed("2026-09-14", "a1", strategy="es930"),       # another strategy
            placed(TODAY, "a1")]                                 # today, no result yet
    assert history(recs, days=120) == []
    assert [r["date"] for r in history(recs, days=200)] == ["2026-05-01"]


def test_the_journal_is_parsed_incrementally(tmp_path):
    """Fix round 1 (review Minor 8): only the bytes appended since the last read are parsed;
    a partial last line waits; a shrunk (or replaced) file is read again from the start."""
    p = tmp_path / "journal.jsonl"
    first = json.dumps(placed("2026-09-14", "a1")) + "\nbroken\n"
    p.write_text(first)
    cache = JournalCache()
    reads = []
    orig = cache._read_from

    def counting(path, offset, size):
        reads.append((offset, size))
        return orig(path, offset, size)

    cache._read_from = counting
    assert len(cache.records(p)) == 1 and len(cache.records(p)) == 1
    assert reads == [(0, len(first))]                       # unchanged: no second read
    second = json.dumps(placed("2026-09-15", "a1"))
    with open(p, "a") as f:
        f.write(second[:20])                                 # a line still being written
    assert len(cache.records(p)) == 1
    with open(p, "a") as f:
        f.write(second[20:] + "\n")
    assert len(cache.records(p)) == 2
    assert reads[1][0] == len(first) and reads[2][0] == len(first)     # never from 0 again
    p.write_text(json.dumps(placed("2026-09-16", "a1")) + "\n")       # shrank: read from 0
    recs = cache.records(p)
    assert len(recs) == 1 and recs[0]["et"].startswith("2026-09-16") and reads[-1][0] == 0
    assert cache.records(tmp_path / "missing.jsonl") == []


def test_a_kill_after_the_exit_leaves_the_trade_as_it_was():
    """Fix round 1 (review Important 4): a TP day killed at 11:00 is still a TP day."""
    base = [placed("2026-09-14", "a1"),
            rec("entry_fill", "2026-09-14", "09:30:02", strategy="nq930", account="a1", side="Buy",
                fill=30910.0, qty_filled=2),
            rec("exit_fill", "2026-09-14", "09:41:00", strategy="nq930", account="a1", reason="tp",
                fill=30925.0)]
    for kill in (rec("strategy_killed", "2026-09-14", "11:00:00", strategy="nq930",
                     results={"a1": {"ok": True, "actions": []}}),
                 rec("strategy_killed", "2026-09-14", "11:00:00", strategy="nq930",
                     results={"a1": {"ok": True, "acted": True, "actions": []}}),
                 rec("kill_switch", "2026-09-14", "11:00:00", results={},
                     strategies={"nq930@a1": []})):
        (r,) = history(base + [kill])
        assert (r["status"], r["exit"]["kind"], r["pnl_usd"]) == ("traded", "tp", 592.0), kill["event"]


def test_a_non_string_account_is_skipped():
    recs = [placed("2026-09-14", "a1"),
            {**placed("2026-09-14", "a1"), "account": ["x"]},
            {**placed("2026-09-15", "a1"), "account": {"x": 1}},
            rec("cancelled_unfilled", "2026-09-14", "12:55:00", strategy="nq930", account="a1")]
    assert [(r["date"], r["account"]) for r in history(recs)] == [("2026-09-14", "a1")]


def test_a_kill_request_alone_marks_the_day_killed():
    recs = [rec("strategy_kill_requested", "2026-09-14", "09:10:00", strategy="nq930")]
    assert history(recs) == [{"date": "2026-09-14", "account": None, "status": "killed",
                              "reason": "killed from the chart", "legs": []}]


def test_days_are_1_to_400_default_120():
    from homebase.bothistory import parse_days
    assert (parse_days(None), parse_days("7"), parse_days(400), parse_days("1")) == (120, 7, 400, 1)
    for bad in (0, 401, "0", "401", "abc", "7.5", "", True, 7.0, [7]):
        with pytest.raises(ValueError, match="days: a whole number 1-400"):
            parse_days(bad)


def test_a_kill_that_landed_while_placing_marks_that_account_killed():
    recs = [placed("2026-09-14", "a1"),
            rec("strategy_killed", "2026-09-14", "09:30:00", strategy="nq930",
                results={"a1": {"ok": True, "pending": True}}),
            rec("strategy_killed_after_ack", "2026-09-14", "09:30:01", strategy="nq930", account="a1",
                ok=True, actions=["cancel 1: ok"])]
    (r,) = history(recs)
    assert (r["account"], r["status"]) == ("a1", "killed")
