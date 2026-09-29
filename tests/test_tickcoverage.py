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


def write_file(base, root, date, contract, ts_list, *, massive=False, first_id=1, manifest=None):
    """An archive file the way the desk (8 columns) or the Massive backfill (+ ts_ns) wrote it."""
    p = T.archive_path(root, date, contract, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(T.FIELDS + (("ts_ns",) if massive else ()))
        for i, t in enumerate(ts_list):
            row = [t, "1.0", 1, "" if massive else "0.75", "" if massive else "1.0", "", "", first_id + i]
            w.writerow(row + ([t * 1_000_000] if massive else []))
    start, end = T.session_bounds(date)
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
    assert got["2026-09-24"] == {"session": "2026-09-24", "contract": "NQZ6", "status": "missing", "flags": []}
    assert got["2026-09-23"]["status"] == "live_only" and got["2026-09-23"]["holes"] == []
    assert got["2026-09-22"]["source"] == "massive"
    assert [(h["from_et"], h["to_et"], h["at"]) for h in got["2026-09-22"]["holes"]] == [("13:00", "15:00", "inside")]
    assert got["2026-09-07"]["flags"] == ["filed_under_next_session"]
    assert rep["summary"] == {"roots": 1, "sessions": 16, "complete": 11, "partial": 2, "live_only": 1,
                              "missing": 2, "hole_hours": 4.0, "missing_ids": 0}
    assert json.loads(out.read_text())["summary"] == rep["summary"]
    assert "not_modelled" in rep and "Thanksgiving" in rep["not_modelled"]
    line = capsys.readouterr().out
    assert "coverage, last 16 sessions x 1 roots: 11 complete, 2 partial (4 hole-hours, 0 missing tick ids), " \
           "1 live-only, 2 missing" in line


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
    assert "run failed: md socket refused" in out and "coverage, last 4 sessions x 1 roots" in out


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
