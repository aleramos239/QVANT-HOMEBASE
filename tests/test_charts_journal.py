"""The chart's journal (homebase/charts/journal.py + routes/journal.py): past days' round trips, notes, tags.
Read-only on the desk's journal.jsonl; notes live in the chart service's own state. No broker, no network."""
from __future__ import annotations

import datetime as dt
import json
import threading
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.charts import journal as J
from homebase.charts.routes import journal as routes_journal

ET = ZoneInfO = ZoneInfo("America/New_York")
DAY = "2026-10-27"


def ms(h, m=0, s=0, day=dt.date(2026, 10, 27)):
    return int(dt.datetime.combine(day, dt.time(h, m, s), ET).timestamp() * 1000)


def fill(i, side, qty, price, t, account="a1", symbol="NQZ6", owner=None):
    return {"ms": t, "account": account, "id": i, "order_id": f"o{i}", "symbol": symbol, "side": side, "qty": qty,
            "price": price, "owner": owner}


# ---- the desk day ----------------------------------------------------------------------------------------------
def test_desk_day_starts_at_1800_et():
    assert J.desk_day_of_ms(ms(17, 59)) == DAY
    assert J.desk_day_of_ms(ms(18, 0)) == "2026-10-28"
    assert J.desk_day_of_et("2026-10-27T18:00:01-04:00") == "2026-10-28"
    assert J.desk_day_of_et("2026-10-27T09:30:00-04:00") == DAY
    assert J.desk_day_of_et("garbage") == "" and J.desk_day_of_et(None) == ""


# ---- the journal reader: never raises ----------------------------------------------------------------------------
def test_read_journal_missing_garbled_and_empty_day(tmp_path):
    assert J.read_journal(tmp_path / "nope.jsonl", DAY) == []
    p = tmp_path / "journal.jsonl"
    good = {"ts": 1.0, "et": "2026-10-27T10:00:00-04:00", "event": "manual_order"}
    other = {"ts": 2.0, "et": "2026-10-26T10:00:00-04:00", "event": "manual_order"}
    p.write_bytes(b"not json\n" + b"42\n" + b"[1,2]\n" + b"null\n" + b"\xff\xfe broken\n"
                  + json.dumps(good).encode() + b"\n" + json.dumps(other).encode() + b"\n"
                  + b'{"et": "2026-10-27T10:00:00-04:00", "event": "x"')          # a torn last line
    assert J.read_journal(p, DAY) == [good]
    assert J.read_journal(p, "2020-01-01") == []                                 # a day with nothing


def test_read_journal_is_a_directory_or_unreadable(tmp_path):
    assert J.read_journal(tmp_path, DAY) == []                                   # a folder where the file should be


# ---- round trips: pairing -----------------------------------------------------------------------------------------
def test_simple_long_and_short():
    trips = J.round_trips([fill(1, "Buy", 1, 100.0, ms(10)), fill(2, "Sell", 1, 101.0, ms(10, 5)),
                           fill(3, "Sell", 2, 102.0, ms(11)), fill(4, "Buy", 2, 100.5, ms(11, 3))])
    assert [(t["side"], t["qty"], t["entry"], t["exit"], t["pnl"]) for t in trips] == [
        ("Buy", 1, 100.0, 101.0, 20.0), ("Sell", 2, 102.0, 100.5, 60.0)]          # NQ: $20 a point
    assert trips[0]["entry_ms"] == ms(10) and trips[0]["exit_ms"] == ms(10, 5) and not trips[0]["open"]


def test_partial_fills_of_one_order_are_one_trip():
    trips = J.round_trips([fill(1, "Buy", 1, 100.0, ms(10)), fill(2, "Buy", 2, 101.0, ms(10, 0, 1)),
                           fill(3, "Sell", 1, 102.0, ms(10, 5)), fill(4, "Sell", 2, 103.0, ms(10, 6))])
    assert len(trips) == 1
    t = trips[0]
    assert t["qty"] == 3 and t["entry"] == pytest.approx(100.6666667) and t["exit"] == pytest.approx(102.6666667)
    assert t["pnl"] == pytest.approx(((102 + 2 * 103) - (100 + 2 * 101)) * 20)        # = sum(exits) - sum(entries)


def test_scale_in_and_out_keeps_the_total_pnl_exact():
    trips = J.round_trips([fill(1, "Buy", 1, 100.0, ms(10)), fill(2, "Buy", 1, 102.0, ms(10, 1)),
                           fill(3, "Sell", 1, 105.0, ms(10, 2)), fill(4, "Sell", 1, 99.0, ms(10, 3))])
    assert len(trips) == 1 and trips[0]["qty"] == 2
    assert trips[0]["pnl"] == pytest.approx(((105 + 99) - (100 + 102)) * 20)


def test_flip_through_zero_splits_the_crossing_fill():
    # long 2, then Sell 3 (closes 2, opens short 1), then Buy 1 closes the short
    trips = J.round_trips([fill(1, "Buy", 2, 100.0, ms(10)), fill(2, "Sell", 3, 101.0, ms(10, 5)),
                           fill(3, "Buy", 1, 100.0, ms(10, 9))])
    assert [(t["side"], t["qty"], t["entry"], t["exit"], t["pnl"], t["open"]) for t in trips] == [
        ("Buy", 2, 100.0, 101.0, 40.0, False), ("Sell", 1, 101.0, 100.0, 20.0, False)]
    assert trips[1]["entry_ms"] == ms(10, 5)


def test_a_trip_still_open_has_no_exit_or_pnl():
    trips = J.round_trips([fill(1, "Buy", 2, 100.0, ms(10)), fill(2, "Sell", 1, 101.0, ms(10, 5))])
    assert len(trips) == 1 and trips[0]["open"] and trips[0]["exit"] is None and trips[0]["pnl"] is None
    assert trips[0]["left"] == 1


def test_accounts_and_symbols_pair_apart_and_input_order_does_not_matter():
    fills = [fill(2, "Sell", 1, 101.0, ms(10, 5)), fill(1, "Buy", 1, 100.0, ms(10)),
             fill(3, "Buy", 1, 50.0, ms(10, 1), account="a2", symbol="ESZ6"),
             fill(4, "Sell", 1, 51.0, ms(10, 2), account="a2", symbol="ESZ6")]
    trips = J.round_trips(fills)
    assert sorted((t["account"], t["symbol"], t["pnl"]) for t in trips) == [("a1", "NQZ6", 20.0), ("a2", "ESZ6", 50.0)]


def test_bad_fills_are_skipped_and_an_unknown_contract_has_no_dollars():
    bad = [fill(1, "Buy", 0, 100.0, ms(10)), fill(2, "Hold", 1, 100.0, ms(10)), fill(3, "Buy", 1, float("nan"), ms(10)),
           {"side": "Buy"}, "junk", None]
    assert J.round_trips(bad) == []
    t = J.round_trips([fill(1, "Buy", 1, 10.0, ms(10), symbol="ZZZ9"), fill(2, "Sell", 1, 11.0, ms(10, 1), symbol="ZZZ9")])
    assert t[0]["pnl"] is None and t[0]["exit"] == 11.0                            # never a wrong $0


# ---- R from the stop the chart sent ------------------------------------------------------------------------------
def order(t, side="Buy", sl=99.0, account="a1", contract="NQZ6", ok=True):
    return {"ts": t / 1000, "event": "manual_order", "account": account, "contract": contract, "root": "NQ",
            "side": side, "sl": sl, "ok": ok}


def test_r_uses_the_stop_of_the_order_that_opened_the_trip():
    trips = J.round_trips([fill(1, "Buy", 1, 100.0, ms(10, 0, 1)), fill(2, "Sell", 1, 103.0, ms(10, 5))])
    J.attach_stops(trips, [order(ms(10), sl=98.0)])
    assert trips[0]["stop"] == 98.0 and trips[0]["r"] == pytest.approx(1.5)         # +3 points on 2 points of risk


def test_r_stays_empty_without_a_usable_stop():
    mk = lambda: J.round_trips([fill(1, "Buy", 1, 100.0, ms(10, 0, 1)), fill(2, "Sell", 1, 103.0, ms(10, 5))])
    for recs in ([], [order(ms(10), side="Sell", sl=102.0)],            # the other side's order
                 [order(ms(10), sl=101.0)],                              # a "stop" above a long's entry
                 [order(ms(10), sl=98.0, account="a2")],                 # another account
                 [order(ms(10), sl=98.0, ok=False)],                     # a refused order
                 [order(ms(10, 30), sl=98.0)],                           # sent after the fill
                 [{"event": "manual_order", "ts": "x"}, "junk", {}]):
        trips = mk()
        J.attach_stops(trips, recs)
        assert trips[0]["r"] is None and trips[0]["stop"] is None, recs


# ---- bot runs from the journal (days before the recorder) ---------------------------------------------------------
def test_bot_trips_from_entry_and_exit_lines():
    recs = [{"ts": ms(9, 30, 1) / 1000, "event": "entry_fill", "strategy": "b1", "account": "a1", "side": "Buy",
             "fill": 100.0, "qty_filled": 2},
            {"ts": ms(9, 30, 2) / 1000, "event": "brackets_moved", "strategy": "b1", "account": "a1", "sl": 98.0},
            {"ts": ms(10, 0) / 1000, "event": "exit_fill", "strategy": "b1", "account": "a1", "fill": 104.0, "qty": 2,
             "pnl": 160.0, "reason": "tp"},
            {"ts": ms(11, 0) / 1000, "event": "entry_fill", "strategy": "b1", "account": "a2", "side": "Sell",
             "fill": 90.0, "qty_filled": 1}]
    a, b = J.bot_trips(recs)
    assert (a["account"], a["owner"], a["side"], a["qty"], a["entry"], a["exit"], a["pnl"], a["open"]) == (
        "a1", "b1", "Buy", 2, 100.0, 104.0, 160.0, False)
    assert a["stop"] == 98.0 and a["r"] == pytest.approx(2.0) and a["source"] == "journal"
    assert b["open"] and b["pnl"] is None and b["account"] == "a2"
    assert J.bot_trips([{"event": "exit_fill"}, "x", {"event": "entry_fill", "ts": "bad"}]) == []


# ---- the fill log -------------------------------------------------------------------------------------------------
def desk_msg(i, t="2026-10-27T14:03:05.123Z", **kw):
    f = {"id": i, "order_id": "9", "symbol": "NQZ6", "side": "Buy", "qty": 1, "price": 100.25, "time": t, "owner": None}
    f.update(kw)
    return {"type": "desk", "event": "fill", "data": {"account": "a1", "fill": f}}


def test_record_fill_writes_one_line_per_fill_and_reads_back_deduped(tmp_path):
    d = tmp_path / "fills"
    J.record_fill(d, desk_msg(1))
    J.record_fill(d, desk_msg(1))                                   # the desk repeats a notice after a resync
    J.record_fill(d, desk_msg(2, t="2026-10-27T14:04:00Z", side="Sell", price=101.0))
    got = J.read_fills(d, DAY)
    assert [(f["id"], f["side"], f["price"], f["account"]) for f in got] == [(1, "Buy", 100.25, "a1"), (2, "Sell", 101.0, "a1")]
    assert got[0]["ms"] == int(dt.datetime(2026, 10, 27, 14, 3, 5, 123000, dt.timezone.utc).timestamp() * 1000)
    assert J.read_fills(d, "2026-10-26") == []


def test_record_fill_ignores_everything_else_and_never_raises(tmp_path):
    d = tmp_path / "fills"
    for msg in ({"type": "desk", "event": "state", "data": {}}, {"type": "desk", "down": "x"}, "junk", None, {},
                {"type": "desk", "event": "fill", "data": None}, {"type": "desk", "event": "fill", "data": {"fill": 5}},
                desk_msg(3, qty="x")):
        J.record_fill(d, msg)
    assert J.read_fills(d, DAY) == [] and not d.exists()
    (tmp_path / "blocker").write_text("a file where the folder should go")
    J.record_fill(tmp_path / "blocker" / "fills", desk_msg(4))       # a full disk or a bad path: swallowed


def test_read_fills_skips_garbled_lines(tmp_path):
    d = tmp_path / "fills"
    J.record_fill(d, desk_msg(1))
    (d / f"{DAY}.jsonl").open("a").write("garbage\n[1]\n")
    assert len(J.read_fills(d, DAY)) == 1


# ---- the notes store ----------------------------------------------------------------------------------------------
def test_notes_round_trip_and_clear(tmp_path):
    n = J.Notes(tmp_path / "notes.json")
    assert n.all() == {}
    n.put("a1|NQZ6|1", "late entry", ["fomo", "A setup", "fomo", " "])
    assert n.all() == {"a1|NQZ6|1": {"note": "late entry", "tags": ["fomo", "A setup"]}}
    n.put("a1|NQZ6|1", "", [])                                      # nothing left: the entry goes
    assert n.all() == {}


def test_notes_write_is_atomic_and_leaves_no_temp_file(tmp_path, monkeypatch):
    p = tmp_path / "sub" / "notes.json"
    n = J.Notes(p)
    n.put("k", "one", [])
    before = p.read_text()
    def boom(*a, **k): raise OSError("disk full")
    monkeypatch.setattr("homebase.core.atomic.os.replace", boom)
    with pytest.raises(OSError):
        n.put("k2", "two", [])
    assert p.read_text() == before                                  # the old file is whole
    monkeypatch.undo()
    assert json.loads(p.read_text()) == {"k": {"note": "one", "tags": []}}


def test_notes_torn_file_reads_as_empty_and_next_save_repairs(tmp_path):
    p = tmp_path / "notes.json"
    p.write_text('{"k": {"note": "x"')
    n = J.Notes(p)
    assert n.all() == {}
    n.put("k", "y", [])
    assert n.all()["k"]["note"] == "y"


def test_notes_concurrent_saves_lose_nothing(tmp_path):
    n = J.Notes(tmp_path / "notes.json")
    ts = [threading.Thread(target=n.put, args=(f"id{i}", f"note {i}", ["t"])) for i in range(40)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(n.all()) == sorted(f"id{i}" for i in range(40))
    json.loads((tmp_path / "notes.json").read_text())               # whole JSON on disk


@pytest.mark.parametrize("kw", [dict(key="", note="x", tags=[]), dict(key="k" * 200, note="x", tags=[]),
                                dict(key="k\n", note="x", tags=[]), dict(key="k", note=5, tags=[]),
                                dict(key="k", note="x" * 2001, tags=[]), dict(key="k", note="x", tags="a"),
                                dict(key="k", note="x", tags=["t"] * 9 + ["u"]), dict(key="k", note="x", tags=["x" * 25]),
                                dict(key="k", note="x", tags=[3])])
def test_notes_refuse_bad_input(tmp_path, kw):
    n = J.Notes(tmp_path / "notes.json")
    with pytest.raises(ValueError):
        n.put(kw["key"], kw["note"], kw["tags"])
    assert not (tmp_path / "notes.json").exists()


# ---- the day view and the routes ----------------------------------------------------------------------------------
HEAD = {"host": "127.0.0.1:8852"}


def make(tmp_path):
    jp, sd = tmp_path / "journal.jsonl", tmp_path / "charts"
    app = FastAPI()
    routes_journal.register(app, journal_path=jp, fills_dir=sd / "journal" / "fills", notes=J.Notes(sd / "journal" / "notes.json"),
                            browser_write_ok=lambda request: None)
    return TestClient(app, base_url="http://127.0.0.1:8852"), jp, sd


def seed(jp, sd):
    recs = [order(ms(10), sl=98.0)]
    recs[0]["et"] = "2026-10-27T10:00:00-04:00"
    jp.write_text("".join(json.dumps(r) + "\n" for r in recs))
    J.record_fill(sd / "journal" / "fills", desk_msg(1, t="2026-10-27T14:00:01Z", price=100.0))
    J.record_fill(sd / "journal" / "fills", desk_msg(2, t="2026-10-27T14:05:00Z", side="Sell", price=103.0))


def test_day_route_returns_trips_with_r_and_the_note(tmp_path):
    c, jp, sd = make(tmp_path)
    seed(jp, sd)
    trip = c.get("/api/journal/day", params={"date": DAY}).json()["trips"][0]
    assert (trip["side"], trip["qty"], trip["pnl"], trip["r"], trip["note"], trip["tags"]) == ("Buy", 1, 60.0, 1.5, "", [])
    r = c.put("/api/journal/note", json={"id": trip["id"], "note": "waited for the retest", "tags": ["A setup"]})
    assert r.status_code == 200
    again = c.get("/api/journal/day", params={"date": DAY}).json()["trips"][0]
    assert (again["note"], again["tags"]) == ("waited for the retest", ["A setup"])


def test_day_route_empty_day_missing_journal_and_bad_date(tmp_path):
    c, jp, sd = make(tmp_path)
    assert c.get("/api/journal/day", params={"date": DAY}).json()["trips"] == []        # no journal, no fills
    assert c.get("/api/journal/day", params={"date": "not-a-date"}).status_code == 400
    assert c.get("/api/journal/day").status_code == 400
    jp.write_text("garbage\n")
    assert c.get("/api/journal/day", params={"date": DAY}).json()["trips"] == []


def test_recorded_fills_win_over_the_journal_for_the_same_account(tmp_path):
    c, jp, sd = make(tmp_path)
    seed(jp, sd)
    with jp.open("a") as f:
        f.write(json.dumps({"ts": ms(9, 31) / 1000, "et": "2026-10-27T09:31:00-04:00", "event": "entry_fill", "strategy": "b1",
                            "account": "a1", "side": "Buy", "fill": 1.0, "qty_filled": 1}) + "\n")
        f.write(json.dumps({"ts": ms(9, 32) / 1000, "et": "2026-10-27T09:32:00-04:00", "event": "entry_fill", "strategy": "b1",
                            "account": "a9", "side": "Buy", "fill": 5.0, "qty_filled": 1}) + "\n")
    trips = c.get("/api/journal/day", params={"date": DAY}).json()["trips"]
    assert sorted((t["account"], t["source"]) for t in trips) == [("a1", "fills"), ("a9", "journal")]


def test_the_routes_never_write_to_the_journal(tmp_path):
    c, jp, sd = make(tmp_path)
    seed(jp, sd)
    before = (jp.read_bytes(), jp.stat().st_mtime_ns, sorted(p.name for p in tmp_path.iterdir()))
    for _ in range(3):
        trip = c.get("/api/journal/day", params={"date": DAY}).json()["trips"][0]
        assert c.put("/api/journal/note", json={"id": trip["id"], "note": "n", "tags": ["x"]}).status_code == 200
    assert c.put("/api/journal/note", json={"id": "", "note": "n"}).status_code == 400
    assert c.put("/api/journal/note", content=b"not json").status_code == 400
    after = (jp.read_bytes(), jp.stat().st_mtime_ns, sorted(p.name for p in tmp_path.iterdir()))
    assert after == before                                          # bytes, mtime and the folder around it
    assert "n" in (sd / "journal" / "notes.json").read_text()       # the note went to its own file


def test_the_routes_refuse_a_foreign_host_and_a_cross_site_write(tmp_path):
    jp, sd = tmp_path / "journal.jsonl", tmp_path / "charts"
    from homebase.charts.routes.common import browser_write_ok
    app = FastAPI()
    routes_journal.register(app, journal_path=jp, fills_dir=sd / "f", notes=J.Notes(sd / "n.json"), browser_write_ok=browser_write_ok)
    c = TestClient(app, base_url="http://127.0.0.1:8852")
    assert c.get("/api/journal/day", params={"date": DAY}, headers={"host": "evil.example"}).status_code == 403
    r = c.put("/api/journal/note", json={"id": "k", "note": "x"}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403 and not (sd / "n.json").exists()


def test_create_app_wires_the_journal_and_records_a_desk_fill(tmp_path):
    from homebase.charts.server import create_app
    seen = []
    def desk_factory(publish):
        seen.append(publish)
        return None
    app = create_app(roots=["NQ"], base=tmp_path / "ticks", state=tmp_path, desk_factory=desk_factory)
    seen[0](desk_msg(7, t="2026-10-27T14:00:01Z"))                    # what the desk link publishes for a fill
    c = TestClient(app, base_url="http://127.0.0.1:8852")
    assert c.get("/api/journal/day", params={"date": DAY}).status_code == 200
    assert [f["id"] for f in J.read_fills(tmp_path / "journal" / "fills", DAY)] == [7]
