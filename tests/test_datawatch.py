"""The data watchdog (homebase.datawatch): late, thin, silent, refused, about to leave the broker.
Fakes and tmp dirs only: no broker, and it never writes under the archive."""
from __future__ import annotations

import datetime as dt
import json
import os

from homebase import datawatch as W
from homebase import tickarchive as A
from homebase import ticks as T
from tests.test_ticks import _minute_ticks, _write_live

ET = T.ET
D = dt.date(2026, 9, 29)                                  # a Tuesday; its session opened Monday 18:00 ET
HOUR = 3_600_000


def at(*hm, day=D):
    return dt.datetime.combine(day, dt.time(*hm), ET)


def ms(t):
    return int(t.timestamp() * 1000)


def live(base, root, rows, written: dt.datetime, date=D):
    """The chart service's live recording of `rows`, last written at `written`."""
    p = A.live_path(T.archive_path(root, date, T.symbols.front_month(root, date), base))
    _write_live(p, rows)
    os.utime(p, (written.timestamp(), written.timestamp()))
    return p


def upto(ticks, t):
    return [r for r in ticks if r["ts_ms"] <= ms(t)]


def snapshot(base):
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(base.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------ what a file holds, hour by hour
def test_what_is_held_and_missing_is_counted_by_the_clock_hour():
    s = ms(at(18, 0, day=D - dt.timedelta(days=1)))
    runs = [[1, 60, s, s + 59 * 60_000],                            # 18:00-18:59 whole
            [61, 70, s + HOUR, s + HOUR + 9 * 60_000],              # 19:00-19:09, then ids 71..110 never came
            [111, 120, s + HOUR + 50 * 60_000, s + HOUR + 59 * 60_000],
            [301, 301, s + 4 * HOUR + 60_000, s + 4 * HOUR + 60_000]]   # 22:01: 180 ids missing since 19:59
    got = A.hours_of(runs, s, s + 5 * HOUR)
    assert [h[0] for h in got] == [s + k * HOUR for k in range(5)]
    assert [h[1] for h in got] == [60, 20, 0, 0, 1]                   # held: nothing 20:00-22:00
    assert [h[2] for h in got] == [0, 41, 89, 89, 1]                  # the 40, and the 180 spread over the 122 minutes between
    assert A.hours_of(runs, s, s + HOUR) == [[s, 60, 0]]              # only what was asked for
    assert A.hours_of([], s, s + HOUR) == []


def test_hours_short_of_their_ids_are_joined_into_stretches():
    s = 1_790_000_000_000 // HOUR * HOUR
    hours = [[s, 100, 0], [s + HOUR, 10, 90], [s + 2 * HOUR, 5, 95], [s + 3 * HOUR, 0, 50], [s + 4 * HOUR, 99, 1],
             [s + 5 * HOUR, 2, 3]]
    assert A.short_hours(hours) == [[s + HOUR, s + 3 * HOUR, "thin", 185], [s + 3 * HOUR, s + 4 * HOUR, "empty", 50]]
    # 1 of 100 missing is not thin; 3 of 5 is too few ids to say


# ------------------------------------------------------------------ late
def test_a_feed_ten_minutes_late_is_measured_from_when_its_newest_tick_was_written(tmp_path):
    ticks = _minute_ticks(D)
    now = at(10, 5)
    for root in ("NQ", "ES"):
        live(tmp_path, root, upto(ticks, at(9, 55)), written=at(10, 5))     # 09:55's tick, written 10:05
    st = W.check(("NQ", "ES"), tmp_path, now, {})
    assert st["markets"]["NQ"]["late_s"] == 600 and st["late_s"] == 600 and st["late"] == ["NQ", "ES"]
    assert st["level"] == "warn" and "10 min late" in st["line"]


def test_a_feed_on_time_is_fine(tmp_path):
    ticks = _minute_ticks(D)
    live(tmp_path, "NQ", upto(ticks, at(10, 5)), written=at(10, 5, 1))
    st = W.check(("NQ",), tmp_path, at(10, 5, 30), {})
    assert st["markets"]["NQ"]["late_s"] == 1 and st["late"] == [] and st["thin"] == [] and st["silent"] == []
    assert st["level"] == "fine" and st["line"] == "data: fine"


def test_an_old_write_says_nothing_about_how_late_the_feed_is_now(tmp_path):
    """Sunday afternoon, the last recordings are Friday's -- written ten minutes late then. Nothing is
    open but Bitcoin, and its recording is on time: the feed is not late."""
    sun = dt.date(2026, 10, 4)
    btc = [dict(r, ts_ms=ms(at(13, 0, day=sun)) + i * 60_000) for i, r in enumerate(_minute_ticks(D)[:30])]
    live(tmp_path, "BTC", btc, written=at(13, 29, 1, day=sun), date=sun)
    fri = dt.date(2026, 10, 2)
    live(tmp_path, "NQ", _minute_ticks(fri), written=at(17, 9, 59, day=fri), date=fri)
    st = W.check(("NQ", "BTC"), tmp_path, at(13, 30, day=sun), {})
    assert st["markets"]["NQ"] == {"open": False} and st["markets"]["BTC"]["late_s"] == 1
    assert st["late_s"] == 1 and st["level"] == "fine"


def test_a_recording_stamped_after_the_jobs_own_clock_gives_no_reading(tmp_path):
    ticks = _minute_ticks(D)
    live(tmp_path, "NQ", upto(ticks, at(10, 0)), written=at(10, 0) + dt.timedelta(days=7))
    st = W.check(("NQ",), tmp_path, at(10, 10), {})
    assert st["markets"]["NQ"]["late_s"] is None and st["level"] == "fine"


# ------------------------------------------------------------------ thin
def test_a_thin_recording_is_measured_against_the_tick_ids_of_the_last_full_hour(tmp_path):
    """The live stream sends one print for a burst of fills: here every fifth trade. The broker's tick
    ids count every trade, so the ids the recording skipped say how much it never got."""
    ticks = upto(_minute_ticks(D), at(10, 5))
    thin = [r for r in ticks if r["ts_ms"] < ms(at(8, 0)) or r["id"] % 5 == 0]      # thinned from 08:00 on
    live(tmp_path, "NQ", thin, written=at(10, 4, 1))                                # its newest print: 10:04:00
    st = W.check(("NQ",), tmp_path, at(10, 6), {})
    m = st["markets"]["NQ"]
    assert (m["hour_utc"], m["received"], m["published"], m["share"]) == ("2026-09-29T13:00:00+00:00", 12, 60, 0.2)
    assert st["thin"] == ["NQ"] and st["level"] == "warn"
    assert "NQ got 20% of its ticks 09:00-10:00 ET" in st["line"]
    # for the chart: the hours of the session under way that are short of their ids, as [from, to, kind]
    assert m["holes"] == [[ms(at(8, 0)), ms(at(10, 0)), "thin"]]


def test_the_last_full_hour_is_the_feeds_own_when_the_feed_is_late(tmp_path):
    """10:05 on the wall, the feed ten minutes behind: its 09:00 hour is not over yet -- 08:00-09:00 is judged."""
    ticks = upto(_minute_ticks(D), at(9, 55))
    live(tmp_path, "NQ", [r for r in ticks if r["id"] % 4 == 0], written=at(10, 5))
    m = W.check(("NQ",), tmp_path, at(10, 5), {})["markets"]["NQ"]
    assert m["hour_utc"] == "2026-09-29T12:00:00+00:00" and m["share"] == 0.25


def test_what_the_archive_already_holds_is_not_a_hole_on_todays_chart(tmp_path):
    """The hourly fill put 08:00-09:00 into the archive file: the chart reads both, so only 09:00 on is thin."""
    ticks = upto(_minute_ticks(D), at(10, 5))
    live(tmp_path, "NQ", [r for r in ticks if r["ts_ms"] < ms(at(8, 0)) or r["id"] % 5 == 0], written=at(10, 4, 1))
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    s, e = T.session_bounds(D)
    A.merge_session(path, root="NQ", contract="NQZ6", date=D, start=s, end=e, include_live=False,
                    fetched=[A.row_of(r) for r in ticks if ms(at(8, 0)) <= r["ts_ms"] <= ms(at(9, 0))],
                    fetched_source={"kind": "history", "stop": "reached"})
    m = W.check(("NQ",), tmp_path, at(10, 6), {})["markets"]["NQ"]
    assert m["share"] == 0.2 and m["holes"] == [[ms(at(9, 0)), ms(at(10, 0)), "thin"]]


# ------------------------------------------------------------------ silent
def test_silence_counts_only_while_the_market_is_open(tmp_path):
    ticks = _minute_ticks(D)
    live(tmp_path, "NQ", upto(ticks, at(9, 40)), written=at(9, 40, 1))
    assert W.check(("NQ",), tmp_path, at(9, 50), {})["silent"] == []            # ten quiet minutes: not yet
    st = W.check(("NQ",), tmp_path, at(10, 0), {})                              # twenty, in regular hours
    assert st["silent"] == ["NQ"] and st["markets"]["NQ"]["silent_s"] == 1199 and "NQ silent 20 min" in st["line"]
    live(tmp_path, "ES", upto(ticks, at(2, 0)), written=at(2, 0, 1))
    assert W.check(("ES",), tmp_path, at(2, 40), {})["silent"] == []            # overnight a market may idle longer
    assert W.check(("ES",), tmp_path, at(3, 5), {})["silent"] == ["ES"]
    # 17:30: the daily halt. Nothing is open, nothing is silent
    live(tmp_path, "YM", ticks, written=at(17, 0, 1))
    assert W.check(("YM",), tmp_path, at(17, 30), {})["markets"]["YM"] == {"open": False}


def test_a_market_that_just_opened_is_not_silent_for_the_hour_it_was_closed(tmp_path):
    nxt = D + dt.timedelta(days=1)
    st = W.check(("NQ",), tmp_path, at(18, 20), {})                              # 20 min into the new session, no tick
    assert st["markets"]["NQ"]["session"] == nxt.isoformat() and st["silent"] == []
    assert W.check(("NQ",), tmp_path, at(19, 30), {})["silent"] == ["NQ"]       # 90 min and nothing recorded at all


# ------------------------------------------------------------------ refused merges, holes about to leave
def test_refused_merges_whose_files_are_still_as_they_were_are_listed(tmp_path):
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a gzip file")
    cache = {T.REFUSED: {
        f"NQ {D}": {"stamp": T.files_stamp(path), "rules": A.MERGE_RULES, "why": "MergeRefused: ids disagree", "at": "x"},
        f"ES {D}": {"stamp": [None, None], "rules": A.MERGE_RULES - 1, "why": "an older rule: tried again", "at": "x"}}}
    st = W.check((), tmp_path, at(10, 0), cache)
    assert [(r["root"], r["session"], r["broker_has_it"]) for r in st["refused"]] == [("NQ", "2026-09-29", True)]
    assert st["level"] == "warn" and "1 merge refused (NQ 09-29)" in st["line"]
    path.write_bytes(b"someone dealt with it")
    assert W.check((), tmp_path, at(10, 0), cache)["refused"] == []


def test_what_is_still_missing_and_leaves_the_broker_within_six_hours_is_named(tmp_path, capsys):
    """Monday's session, 03:00-09:00 never recorded and never fetched. The broker serves it until
    Tuesday 20:00 ET: from 14:00 on Tuesday the watchdog says so, every run."""
    mon = dt.date(2026, 9, 28)
    ticks = _minute_ticks(mon)
    live(tmp_path, "NQ", [r for i, r in enumerate(ticks) if not 9 * 60 <= i < 15 * 60], written=at(17, 0, 1, day=mon),
         date=mon)
    assert W.check(("NQ",), tmp_path, at(13, 30), {})["leaving"] == []           # six and a half hours to go
    st = W.check(("NQ",), tmp_path, at(14, 30), {})
    gone = [x for x in st["leaving"] if x["session"] == "2026-09-28"]
    assert gone and all(x["leaves_utc"] == "2026-09-30T00:00:00+00:00" for x in gone)
    assert any(x["why"].startswith("360 ticks") for x in gone)
    assert "leave the broker by 20:00 ET" in st["line"] and "NQ 09-28" in st["line"]
    # Monday 20:30, ES never recorded: its first hours left the broker half an hour ago. The fill's own plan says
    # so in the log, once, at its start -- the watchdog reads the same plan and must not say it a second time
    W.check(("ES",), tmp_path, at(20, 30, day=mon), {})
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ the state file, the log, read-only
def test_run_writes_the_state_and_speaks_only_while_something_is_wrong(tmp_path, capsys):
    base, out = tmp_path / "ticks", tmp_path / "state" / "data_watch.json"
    out.parent.mkdir()
    ticks = _minute_ticks(D)
    p = live(base, "NQ", upto(ticks, at(10, 5)), written=at(10, 5, 1))
    assert W.run(("NQ",), base, at(10, 6), {}, out)["level"] == "fine"
    assert capsys.readouterr().out == ""                                         # a healthy desk: not a word
    saved = json.loads(out.read_text())
    assert saved["level"] == "fine" and saved["at_utc"] == "2026-09-29T14:06:00+00:00" and "NQ" in saved["markets"]
    os.utime(p, (at(10, 15).timestamp(),) * 2)                                   # the same ticks, written 10 min late
    W.run(("NQ",), base, at(10, 16), {}, out)
    W.run(("NQ",), base, at(10, 17), {}, out)
    said = capsys.readouterr().out
    assert said.count("data: the live feed is 10 min late") == 2                 # every run while it lasts
    os.utime(p, (at(10, 5, 1).timestamp(),) * 2)
    W.run(("NQ",), base, at(10, 18), {}, out)
    W.run(("NQ",), base, at(10, 19), {}, out)
    assert capsys.readouterr().out.count("data: fine again") == 1                # once, then quiet


def test_the_watchdog_only_reads_the_archive(tmp_path):
    base = tmp_path / "ticks"
    ticks = _minute_ticks(D)
    live(base, "NQ", [r for r in ticks if r["id"] % 3 == 0], written=at(10, 5))
    path = T.archive_path("NQ", D, "NQZ6", base)
    s, e = T.session_bounds(D)
    A.merge_session(path, root="NQ", contract="NQZ6", date=D, start=s, end=e, include_live=False,
                    fetched=[A.row_of(r) for r in ticks[:100]], fetched_source={"kind": "history", "stop": "reached"})
    before = snapshot(base)
    W.run(("NQ", "ES", "BTC"), base, at(10, 6), {}, tmp_path / "data_watch.json")
    assert snapshot(base) == before


# ------------------------------------------------------------------ the job calls it
def test_every_run_of_the_job_ends_with_the_watchdog(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    now = at(10, 6)
    monkeypatch.setattr(T, "now_et", lambda: now)
    monkeypatch.setattr(T, "report_due", lambda p: False)

    async def nothing(*a, **k):
        return []
    monkeypatch.setattr(T, "record", nothing)
    ticks = upto(_minute_ticks(D), at(9, 55))
    live(tmp_path / "ticks", "NQ", ticks, written=at(10, 5))
    assert T.run(("NQ",), [D], tmp_path / "ticks") == 0
    st = json.loads((tmp_path / "state" / "data_watch.json").read_text())
    assert st["late_s"] == 600 and "10 min late" in capsys.readouterr().out
    saved = json.loads((tmp_path / "state" / "tick_runs.json").read_text())      # what it read is kept for the next run
    assert any(k.endswith("NQZ6.live.csv.gz") for k in saved)


def test_the_coverage_report_carries_the_watchdogs_last_reading(tmp_path, monkeypatch, capsys):
    """The connector reads homebase/.state/tick_coverage.json: whenever the job writes it, the watchdog's
    reading of that same run is in it."""
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(T, "now_et", lambda: at(10, 6))

    async def nothing(*a, **k):
        return []
    monkeypatch.setattr(T, "record", nothing)
    live(tmp_path / "ticks", "NQ", upto(_minute_ticks(D), at(9, 55)), written=at(10, 5))
    assert T.run(("NQ",), [D], tmp_path / "ticks", 2) == 0             # no report yet: one is due
    rep = json.loads((tmp_path / "state" / "tick_coverage.json").read_text())
    assert rep["watch"]["late_s"] == 600 and rep["watch"]["at_utc"] == "2026-09-29T14:06:00+00:00"
    assert rep["watch"] == json.loads((tmp_path / "state" / "data_watch.json").read_text())
    (tmp_path / "state" / "data_watch.json").unlink()                  # no watchdog reading: the report says nothing of it
    assert T.main(["--coverage", "--dir", str(tmp_path / "ticks"), "--roots", "NQ", "--sessions", "2"]) == 0
    assert "watch" not in json.loads((tmp_path / "state" / "tick_coverage.json").read_text())


def test_a_watchdog_that_fails_never_fails_the_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(T, "now_et", lambda: at(10, 6))
    monkeypatch.setattr(T, "report_due", lambda p: False)

    async def nothing(*a, **k):
        return []
    monkeypatch.setattr(T, "record", nothing)
    monkeypatch.setattr(W, "check", lambda *a, **k: 1 / 0)
    assert T.run(("NQ",), [D], tmp_path / "ticks") == 0
    assert "data watch failed: ZeroDivisionError" in capsys.readouterr().out
    assert (tmp_path / "state" / "tick_runs.json").exists()                      # the run still saved its cache
