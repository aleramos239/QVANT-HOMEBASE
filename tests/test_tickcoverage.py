"""The coverage report (homebase/.state/tick_coverage.json) and --rescan. Tmp dirs only."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json

from homebase import tickarchive as A
from homebase import tickcoverage as C
from homebase import ticks as T

ET = T.ET
NOW = dt.datetime(2026, 9, 28, 17, 30, tzinfo=ET)


def minute_ms(date, minutes):
    start, _ = T.session_bounds(date)
    s = int(start.timestamp() * 1000)
    return [s + m * 60_000 for m in minutes]


def et(*a):
    return dt.datetime(*a, tzinfo=ET)


def write_file(base, root, date, contract, ts_list, *, massive=False, first_id=1, manifest=None, ids=None):
    """An archive file the way the desk (8 columns) or the Massive backfill (+ ts_ns) wrote it.
    ids: the broker's tick id of each row (default: consecutive from first_id -- nothing missing between them)."""
    p = T.archive_path(root, date, contract, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(T.FIELDS + (("ts_ns",) if massive else ()))
        for i, t in enumerate(ts_list):
            row = [t, "1.0", 1, "" if massive else "0.75", "" if massive else "1.0", "", "",
                   ids[i] if ids else first_id + i]
            w.writerow(row + ([t * 1_000_000] if massive else []))
    start, end = T.session_bounds(date, root)
    man = {"root": root, "contract": contract, "session_date": date.isoformat(), "ticks": len(ts_list),
           "session_start_utc": start.astimezone(A.UTC).isoformat(),
           "session_end_utc": end.astimezone(A.UTC).isoformat(),
           "first_tick_utc": A.iso_ms(ts_list[0]), "last_tick_utc": A.iso_ms(ts_list[-1]),
           "complete": True, "bytes": p.stat().st_size, **(manifest or {})}
    if massive:
        man.update(source="massive", bid_ask=False)
    A.manifest_path(p).write_text(json.dumps(man))
    return p


def archive(base):
    """NQ's last sessions, one of each kind the archive holds."""
    full = range(23 * 60)
    write_file(base, "NQ", dt.date(2026, 9, 25), "NQZ6", minute_ms(dt.date(2026, 9, 25), range(120, 23 * 60)),
               manifest={"complete": False})                       # a nightly file from 20:00 ET
    live = T.archive_path("NQ", dt.date(2026, 9, 23), "NQZ6", base)
    live = live.with_name("2026-09-23_NQZ6.live.csv.gz")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(gzip.compress(("\n".join([",".join(T.FIELDS)] + [
        f"{t},1.0,1,0.75,1.0,1,1,{i}" for i, t in enumerate(minute_ms(dt.date(2026, 9, 23), full))]) + "\n")
        .encode()))
    write_file(base, "NQ", dt.date(2026, 9, 22), "NQZ6",               # Massive's own 13:00-15:00 hole
               minute_ms(dt.date(2026, 9, 22), [m for m in full if not 19 * 60 <= m < 21 * 60]), massive=True)
    labor = T.session_bounds(dt.date(2026, 9, 7))[0]                  # Sunday 18:00 ET
    s = int(labor.timestamp() * 1000)
    write_file(base, "NQ", dt.date(2026, 9, 8), "NQU6",               # Labor Day's trades filed here
               [s + m * 60_000 for m in range(47 * 60)], massive=True)
    for d in (dt.date(2026, 9, 21), dt.date(2026, 9, 18), dt.date(2026, 9, 17), dt.date(2026, 9, 16),
              dt.date(2026, 9, 15), dt.date(2026, 9, 14), dt.date(2026, 9, 11), dt.date(2026, 9, 10),
              dt.date(2026, 9, 9)):
        write_file(base, "NQ", d, "NQZ6" if d.day >= 11 else "NQU6", minute_ms(d, full), massive=True)
    d = dt.date(2026, 9, 28)
    s0, e0 = T.session_bounds(d)
    A.merge_session(T.archive_path("NQ", d, "NQZ6", base), root="NQ", contract="NQZ6", date=d,
                    start=s0, end=e0, fetched=[A.row_of({"ts_ms": t, "price": 1.0, "size": 1, "bid": 0.75,
                                                         "ask": 1.0, "id": 10_000 + i})
                                               for i, t in enumerate(minute_ms(d, full))],
                    fetched_source={"kind": "history", "stop": "reached"})


def test_the_report_lists_every_hole_by_root_session_and_hour(tmp_path, capsys):
    archive(tmp_path)
    out = tmp_path / "state" / "tick_coverage.json"
    rep = C.write_report(("NQ",), tmp_path, NOW, out, n=16)
    got = {e["session"]: e for e in rep["roots"]["NQ"]}
    assert list(got) == ["2026-09-28", "2026-09-25", "2026-09-24", "2026-09-23", "2026-09-22", "2026-09-21",
                         "2026-09-18", "2026-09-17", "2026-09-16", "2026-09-15", "2026-09-14", "2026-09-11",
                         "2026-09-10", "2026-09-09", "2026-09-08", "2026-09-07"]
    assert got["2026-09-28"]["status"] == "complete"
    assert got["2026-09-25"]["status"] == "partial"
    assert [(h["from_et"], h["to_et"], h["at"]) for h in got["2026-09-25"]["holes"]] == [("18:00", "20:00", "open")]
    assert got["2026-09-24"] == {"session": "2026-09-24", "contract": "NQZ6", "status": "missing", "flags": [],
                                 "needs_massive": True, "class": "lost", "hours": {"lost": 23.0},
                                 "why": "nothing recorded, and it has left the broker"}
    assert got["2026-09-23"]["status"] == "live_only" and got["2026-09-23"]["holes"] == []
    assert got["2026-09-22"]["source"] == "massive"
    assert [(h["from_et"], h["to_et"], h["at"]) for h in got["2026-09-22"]["holes"]] == [("13:00", "15:00", "inside")]
    assert got["2026-09-07"]["flags"] == ["filed_under_next_session"]
    s = rep["summary"]
    assert {k: s[k] for k in ("roots", "sessions", "complete", "partial", "live_only", "missing", "hole_hours",
                              "missing_ids")} == {"roots": 1, "sessions": 16, "complete": 11, "partial": 2,
                                                  "live_only": 1, "missing": 2, "hole_hours": 4.0, "missing_ids": 0}
    assert got["2026-09-25"]["holes"][0]["needs_massive"] and got["2026-09-24"]["needs_massive"]
    assert json.loads(out.read_text())["summary"] == rep["summary"]
    assert "not_modelled" in rep and "Thanksgiving" in rep["not_modelled"]
    # every session is one of five classes -- and only the LOST ones need bought data
    assert {d: e["class"] for d, e in got.items() if e["class"] != "whole"} == {
        "2026-09-25": "lost",              # 18:00-20:00 ET never fetched: it left the broker on the 25th at 20:00
        "2026-09-24": "lost",              # nothing recorded at all
        "2026-09-22": "vendor_gap",        # the bought file itself has no ticks 13:00-15:00: nobody can fill it
        "2026-09-07": "not_a_hole"}        # Labor Day: its trades are filed under the 8th
    assert got["2026-09-23"]["class"] == "whole" and got["2026-09-28"]["class"] == "whole"
    assert s["classes"] == {"whole": 12, "filling": 0, "lost": 2, "vendor_gap": 1, "not_a_hole": 1}
    assert s["needs_massive"] == 2 and not got["2026-09-22"]["needs_massive"] and not got["2026-09-07"]["needs_massive"]
    assert got["2026-09-22"]["holes"][0]["class"] == "vendor_gap" and got["2026-09-25"]["holes"][0]["class"] == "lost"
    assert got["2026-09-22"]["why"] == "the bought file itself has no ticks 13:00-15:00 ET"
    assert got["2026-09-07"]["why"] == "exchange holiday: its trades are filed under the next session"
    line = capsys.readouterr().out
    assert "coverage, last 16 sessions x 1 roots: 12 whole, 0 filling, 2 lost (25 hole-hours, 0 tick ids), " \
           "1 vendor gap, 1 not a hole" in line                # 18:00-20:00 of the 25th, and all 23 hours of the 24th


def test_a_second_report_reads_only_the_files_that_changed(tmp_path, monkeypatch):
    archive(tmp_path)
    out = tmp_path / "state" / "tick_coverage.json"
    C.write_report(("NQ",), tmp_path, NOW, out, n=16)
    read = []
    real = A.iter_rows
    monkeypatch.setattr(A, "iter_rows", lambda p: (read.append(p.name), real(p))[1])
    C.write_report(("NQ",), tmp_path, NOW, out, n=16)
    assert read == []
    p = T.archive_path("NQ", dt.date(2026, 9, 25), "NQZ6", tmp_path)
    write_file(tmp_path, "NQ", dt.date(2026, 9, 25), "NQZ6", minute_ms(dt.date(2026, 9, 25), range(23 * 60)))
    rep = C.write_report(("NQ",), tmp_path, NOW, out, n=16)
    assert read == [p.name] and rep["roots"]["NQ"][1]["status"] == "complete"


def test_both_spellings_of_a_contract_count_as_the_front(tmp_path):
    d = dt.date(2026, 9, 22)
    write_file(tmp_path, "NG", d, "NGX26", minute_ms(d, range(23 * 60)), massive=True)
    write_file(tmp_path, "NG", d, "NGX6", minute_ms(d, range(120, 23 * 60)), manifest={"complete": False})
    e = C.session_entry(tmp_path, "NG", d, {})
    assert e["status"] == "complete" and e["file"].endswith("NGX26.csv.gz")
    assert e["other_files"] == ["2026-09-22_NGX6.csv.gz"]
    assert C.same_contract("NGX6", "NGX26") and not C.same_contract("NGX6", "NGZ6")


def test_rescan_makes_old_manifests_tell_the_truth_and_leaves_the_data(tmp_path):
    archive(tmp_path)
    p22 = T.archive_path("NQ", dt.date(2026, 9, 22), "NQZ6", tmp_path)
    p25 = T.archive_path("NQ", dt.date(2026, 9, 25), "NQZ6", tmp_path)
    data = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (p22, p25)}
    assert A.load_manifest(p22)["complete"] is True                  # the backfill's first/last-tick verdict
    changed = C.rescan(("NQ",), tmp_path, NOW, n=16)
    m22 = A.load_manifest(p22)
    assert m22["complete"] is False and m22["coverage"]["hole_hours"] == 2.0 and m22["source"] == "massive"
    assert A.load_manifest(p25)["coverage"]["holes"][0]["at"] == "open"
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == data[p] for p in data)   # data untouched
    assert changed == 12                     # every front file but the merged 09-28 (already current)
    assert C.rescan(("NQ",), tmp_path, NOW, n=16) == 0


def test_the_cli_writes_the_report_after_the_night_run_even_when_it_fails(tmp_path, monkeypatch, capsys):
    archive(tmp_path / "arch")
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(T, "now_et", lambda: NOW)
    monkeypatch.setattr(T, "deadline_passed", lambda now=None: False)

    async def broken(*a, **k):
        raise RuntimeError("md socket refused")
    monkeypatch.setattr(T, "record", broken)
    assert T.main(["--dir", str(tmp_path / "arch"), "--roots", "NQ", "--sessions", "4"]) == 1
    rep = json.loads((tmp_path / "state" / "tick_coverage.json").read_text())
    assert rep["summary"]["sessions"] == 4
    out = capsys.readouterr().out
    assert "run failed: RuntimeError: md socket refused" in out and "coverage, last 4 sessions x 1 roots" in out


def test_coverage_needs_no_market_data_and_rescan_waits_for_no_other_writer(tmp_path, monkeypatch, capsys):
    archive(tmp_path / "arch")
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(T, "now_et", lambda: NOW)
    monkeypatch.setattr(T, "connect_md", lambda *a, **k: (_ for _ in ()).throw(AssertionError("md")))
    assert T.main(["--coverage", "--dir", str(tmp_path / "arch"), "--roots", "NQ", "--sessions", "3"]) == 0
    assert json.loads((tmp_path / "state" / "tick_coverage.json").read_text())["summary"]["sessions"] == 3
    with T.archive_lock(tmp_path / "state" / "ticks.lock"):              # a night run in progress
        assert T.main(["--rescan", "--dir", str(tmp_path / "arch"), "--roots", "NQ"]) == 1
    assert "another tick-archive run holds" in capsys.readouterr().out
    assert T.main(["--rescan", "--dir", str(tmp_path / "arch"), "--roots", "NQ", "--sessions", "16"]) == 0
    assert "rescan: 12 manifest(s) rewritten" in capsys.readouterr().out


# ------------------------------------------------------------------ the five classes
FRI = dt.date(2026, 9, 25)


def holed(base, root="NQ", contract="NQZ6", date=FRI, skip=range(18 * 60, 20 * 60), jump=500):
    """A desk file with no tick in `skip` (minutes from the 18:00 open; default 12:00-14:00 ET) and `jump`
    tick ids missing there: trades happened, the file does not hold them."""
    mins = [m for m in range(23 * 60) if m not in skip]
    return write_file(base, root, date, contract, minute_ms(date, mins), manifest={"complete": False},
                      ids=[1 + k + (jump if m >= skip[0] else 0) for k, m in enumerate(mins)])


def test_a_hole_the_broker_still_has_is_filling_and_says_until_when(tmp_path):
    holed(tmp_path)
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 17, 30))
    assert e["status"] == "partial" and e["class"] == "filling" and e["until_utc"] == "2026-09-27T00:00:00+00:00"
    assert e["why"] == "2 hole-hours and 500 tick ids are still at the broker, until 09-26 20:00 ET"
    h = e["holes"][0]
    assert (h["class"], h["until_utc"], h["needs_massive"]) == ("filling", "2026-09-27T00:00:00+00:00", False)
    assert e["ids"] == {"filling": 500} and e["hours"] == {"filling": 2.0} and not e["needs_massive"]
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 26, 20, 0))        # Saturday 20:00 ET: gone
    assert e["class"] == "lost" and "until_utc" not in e and e["ids"] == {"lost": 500} and e["needs_massive"]
    assert e["why"] == "2 hole-hours and 500 tick ids have left the broker"


def test_a_session_half_gone_is_filling_until_the_rest_has_left_too(tmp_path):
    """18:00-22:00 ET missing. The first two hours leave the broker at 20:00 ET that day, the rest a day later."""
    holed(tmp_path, skip=range(0, 4 * 60))
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 17, 30))        # the close: all of it still there
    assert (e["class"], e["until_utc"]) == ("filling", "2026-09-26T00:00:00+00:00")
    assert e["why"] == "4 hole-hours are still at the broker, until 09-25 20:00 ET"
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 21, 0))         # 21:00: the first two are gone
    assert e["class"] == "filling" and e["until_utc"] == "2026-09-27T00:00:00+00:00"   # filling while any of it is there
    assert e["holes"][0]["class"] == "filling" and e["holes"][0]["until_utc"] == "2026-09-27T00:00:00+00:00"
    assert e["hours"] == {"lost": 2.0, "filling": 2.0} and not e["needs_massive"]
    assert e["why"] == "2 hole-hours have left the broker; the rest is at the broker until 09-26 20:00 ET"
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 26, 20, 0))         # a day on: lost
    assert e["class"] == "lost" and e["hours"] == {"lost": 4.0} and e["needs_massive"]


def test_missing_tick_ids_flag_a_session_that_has_ticks_in_every_hour(tmp_path):
    """The thinned stream: a print in every hour, three trades in four never recorded from 09:00 to 12:00 ET.
    No hour is empty, so the hole-hours say 0 -- the tick ids say 135 trades are missing, and where."""
    mins = [m for m in range(23 * 60) if not 15 * 60 <= m < 18 * 60 or m % 4 == 0]
    write_file(tmp_path, "NQ", FRI, "NQZ6", minute_ms(FRI, mins), manifest={"complete": False}, ids=[1 + m for m in mins])
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 17, 30))
    assert (e["hole_hours"], e["missing_ids"], e["class"]) == (0, 135, "filling")
    assert e["why"] == "135 tick ids are still at the broker, until 09-26 20:00 ET"
    assert [(t["from_et"], t["to_et"], t["missing_ids"], t["class"]) for t in e["thin"]] == [("09:00", "12:00", 135, "filling")]
    late = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 28, 17, 30))
    assert late["class"] == "lost" and late["ids"] == {"lost": 135} and late["thin"][0]["class"] == "lost"
    assert late["needs_massive"] and late["why"] == "135 tick ids have left the broker"


def test_the_hours_are_read_from_a_file_once(tmp_path, monkeypatch):
    holed(tmp_path)
    cache, n = {}, []
    real = A.file_runs
    monkeypatch.setattr(A, "file_runs", lambda p, c: (n.append(p.name), real(p, c))[1])
    a = C.session_entry(tmp_path, "NQ", FRI, cache, et(2026, 9, 25, 17, 30))
    b = C.session_entry(tmp_path, "NQ", FRI, json.loads(json.dumps(cache)), et(2026, 9, 25, 17, 30))
    assert a == b and len(n) == 1


def test_bitcoins_1700_hour_and_its_weekends_are_not_holes(tmp_path):
    """CME crypto is filed as trading 24/7, but its 17:00 ET hour and its weekends are thin or halted: an hour
    there without a trade is the market, not a hole. Tick ids missing there are still missing trades."""
    thu, sat = dt.date(2026, 9, 24), dt.date(2026, 9, 26)
    s = int(T.session_bounds(thu, "BTC")[0].timestamp() * 1000)
    mins = list(range(23 * 60))                                    # 18:00 -> 17:00: nothing in the 17:00 hour
    write_file(tmp_path, "BTC", thu, "BTCV6", [s + m * 60_000 for m in mins], massive=True, manifest={"complete": False})
    e = C.session_entry(tmp_path, "BTC", thu, {}, et(2026, 9, 28, 17, 30))
    assert [(h["from_et"], h["to_et"]) for h in e["holes"]] == [("17:00", "18:00")]
    assert (e["class"], e["holes"][0]["class"], e["holes"][0]["why"]) == ("not_a_hole", "not_a_hole", "the 17:00 hour")
    assert not e["needs_massive"] and e["why"] == "the 17:00 hour"
    s = int(T.session_bounds(sat, "BTC")[0].timestamp() * 1000)    # Saturday's session: Friday 18:00 -> Saturday 18:00
    mins = [m for m in range(24 * 60) if m >= 14 * 60]             # nothing until Saturday 08:00, 30 ids missing after
    write_file(tmp_path, "BTC", sat, "BTCV6", [s + m * 60_000 for m in mins], manifest={"complete": False},
               ids=[1 + m + (30 if m >= 20 * 60 else 0) for m in mins])
    e = C.session_entry(tmp_path, "BTC", sat, {}, et(2026, 9, 30, 17, 30))
    assert e["holes"][0]["class"] == "not_a_hole" and e["holes"][0]["why"] == "weekend"
    assert e["class"] == "lost" and e["ids"] == {"lost": 30} and e["why"] == "30 tick ids have left the broker"
    # a weekend session with no file at all: thin weekend trading, filed under Monday by the vendor
    e = C.session_entry(tmp_path, "BTC", dt.date(2026, 9, 27), {}, et(2026, 9, 30, 17, 30))
    assert (e["status"], e["class"], e["why"], e["needs_massive"]) == ("missing", "not_a_hole", "weekend", False)
    # ... but a weekday one is as lost as any market's
    e = C.session_entry(tmp_path, "BTC", dt.date(2026, 9, 23), {}, et(2026, 9, 30, 17, 30))
    assert (e["status"], e["class"]) == ("missing", "lost")


def test_a_missing_session_the_broker_still_has_is_filling(tmp_path):
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 17, 30))
    assert (e["status"], e["class"], e["until_utc"]) == ("missing", "filling", "2026-09-26T00:00:00+00:00")
    assert e["why"] == "nothing recorded: still at the broker, until 09-25 20:00 ET" and not e["needs_massive"]
    assert e["hours"] == {"filling": 23.0}
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 21, 0))         # its first two hours left at 20:00
    assert (e["class"], e["until_utc"], e["needs_massive"]) == ("filling", "2026-09-27T00:00:00+00:00", False)
    assert e["why"] == "nothing recorded: part has left the broker, the rest is there until 09-26 20:00 ET"
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 26, 21, 0))
    assert e["class"] == "lost" and "until_utc" not in e and e["why"] == "nothing recorded, and it has left the broker"


def test_a_sliver_at_the_edge_of_bought_rows_is_whole(tmp_path):
    """Where Massive rows stand in for a gap, half a second at each of its edges cannot be filled (the merge's
    guard against counting one trade twice). The manifest is honest -- not complete -- but nothing is to be done."""
    cov = {"version": A.COVERAGE_VERSION, "holes": [], "hole_hours": 0, "missing_ids": 0, "massive_edge_ms": 1000,
           "head_ok": True, "tail_ok": True, "early_close_et": None, "complete": False}
    write_file(tmp_path, "NQ", FRI, "NQZ6", minute_ms(FRI, range(23 * 60)), manifest={"complete": False, "coverage": cov})
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 28, 17, 30))
    assert (e["status"], e["class"]) == ("partial", "whole") and "why" not in e
    cov["massive_edge_ms"] = 9000
    write_file(tmp_path, "NQ", FRI, "NQZ6", minute_ms(FRI, range(23 * 60)), manifest={"complete": False, "coverage": cov})
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 28, 17, 30))
    assert e["class"] == "lost" and e["why"] == "9 s at the edges of bought rows cannot be filled"


def test_ticks_that_start_late_or_stop_early_are_a_piece_too(tmp_path):
    write_file(tmp_path, "NQ", FRI, "NQZ6", minute_ms(FRI, range(10, 23 * 60 - 10)),
               manifest={"complete": False, "sources": []})                      # no fetch vouches for either end
    e = C.session_entry(tmp_path, "NQ", FRI, {}, et(2026, 9, 25, 21, 0))         # the open's hours left at 20:00
    assert (e["head_ok"], e["tail_ok"], e["hole_hours"]) == (False, False, 0)
    assert e["class"] == "filling" and e["edges"] == [{"at": "open", "class": "lost"},
                                                      {"at": "close", "class": "filling", "until_utc": "2026-09-27T00:00:00+00:00"}]
    assert e["why"] == "the open has left the broker; the close is still at the broker, until 09-26 20:00 ET"


def test_without_a_clock_nothing_is_classed(tmp_path):
    holed(tmp_path)
    e = C.session_entry(tmp_path, "NQ", FRI, {})
    assert "class" not in e and "needs_massive" not in e and "class" not in e["holes"][0]


# ------------------------------------------------------------------ what changed since the previous report
def test_the_report_says_what_changed_since_the_previous_one(tmp_path, capsys):
    base, out = tmp_path / "arch", tmp_path / "state" / "tick_coverage.json"
    holed(base)                                                              # Friday: 12:00-14:00 missing
    write_file(base, "NQ", dt.date(2026, 9, 24), "NQZ6", minute_ms(dt.date(2026, 9, 24), range(23 * 60)))
    C.write_report(("NQ",), base, et(2026, 9, 25, 17, 30), out, n=2)
    said = capsys.readouterr().out
    assert "1 whole, 1 filling (2 hole-hours, 500 tick ids at the broker until 09-26 20:00 ET), 0 lost" in said
    assert "coverage changes" not in said                                    # the first report: nothing to compare
    C.write_report(("NQ",), base, et(2026, 9, 25, 18, 30), out, n=2)
    assert "coverage changes" not in capsys.readouterr().out                 # nothing moved: not a word
    holed(base, skip=range(18 * 60, 19 * 60), jump=200)                      # the fill fetched 13:00-14:00
    rep = C.write_report(("NQ",), base, et(2026, 9, 25, 19, 30), out, n=2)
    assert rep["changes"] == ["NQ 09-25 filling: 2 -> 1 hole-hours, 500 -> 200 tick ids"]
    assert "coverage changes since 18:30 ET: NQ 09-25 filling: 2 -> 1 hole-hours, 500 -> 200 tick ids" in capsys.readouterr().out
    rep = C.write_report(("NQ",), base, et(2026, 9, 26, 20, 5), out, n=2)    # Saturday 20:05: it left the broker
    assert rep["changes"] == ["NQ 09-25 filling -> lost"]
    write_file(base, "NQ", FRI, "NQZ6", minute_ms(FRI, range(23 * 60)))      # bought data filled it
    rep = C.write_report(("NQ",), base, et(2026, 9, 26, 21, 0), out, n=2)
    assert rep["changes"] == ["NQ 09-25 lost -> whole"] and rep["previous_generated_at_utc"]
    assert json.loads(out.read_text())["changes"] == rep["changes"]


def test_a_session_new_to_the_report_is_said_when_it_is_not_whole(tmp_path, capsys):
    base, out = tmp_path / "arch", tmp_path / "state" / "tick_coverage.json"
    write_file(base, "NQ", dt.date(2026, 9, 24), "NQZ6", minute_ms(dt.date(2026, 9, 24), range(23 * 60)))
    C.write_report(("NQ",), base, et(2026, 9, 24, 17, 30), out, n=3)
    holed(base)
    rep = C.write_report(("NQ",), base, et(2026, 9, 25, 17, 30), out, n=3)
    assert rep["changes"] == ["NQ 09-25 new: filling until 09-26 20:00 ET",
                              "NQ 09-23 filling -> lost"]                    # never recorded: its last hours left at 20:00
    write_file(base, "NQ", dt.date(2026, 9, 28), "NQZ6", minute_ms(dt.date(2026, 9, 28), range(23 * 60)))
    rep = C.write_report(("NQ",), base, et(2026, 9, 28, 17, 30), out, n=3)   # a whole new session: nothing to say of it
    assert rep["changes"] == ["NQ 09-25 filling -> lost"]


def test_a_previous_report_without_classes_is_not_compared(tmp_path, capsys):
    out = tmp_path / "state" / "tick_coverage.json"
    out.parent.mkdir()
    out.write_text(json.dumps({"generated_at_utc": "2026-09-25T21:00:00+00:00",
                               "roots": {"NQ": [{"session": "2026-09-25", "status": "partial", "needs_massive": True}]}}))
    holed(tmp_path / "arch")
    rep = C.write_report(("NQ",), tmp_path / "arch", et(2026, 9, 25, 17, 30), out, n=1)
    assert rep["changes"] == [] and "coverage changes" not in capsys.readouterr().out
