"""What the tick job knows, for the charts (homebase.charts.known): the coverage report's holes per session
and the data watchdog's reading -- read off disk, never written."""
from __future__ import annotations

import datetime as dt
import json

from homebase import ticks as T
from homebase.charts.history import History
from homebase.charts.known import Known
from homebase.charts.store import TickStore
from tests.charts_util import D, rows, session_ms, write_archive

P = D - dt.timedelta(days=1)          # Wednesday 2026-09-23
PP = D - dt.timedelta(days=2)
UTC = dt.timezone.utc


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def hole(d, h0, h1, cls, **more):
    return {"start_utc": iso(session_ms(d, h0, 0)), "end_utc": iso(session_ms(d, h1, 0)), "class": cls, **more}


def report(tmp_path, roots):
    p = tmp_path / "tick_coverage.json"
    p.write_text(json.dumps({"generated_at_utc": "2026-09-24T21:30:00+00:00", "roots": roots}))
    return p


def known(tmp_path, roots=None, watch=None):
    if roots is not None:
        report(tmp_path, roots)
    if watch is not None:
        (tmp_path / "data_watch.json").write_text(json.dumps(watch))
    k = Known(tmp_path / "tick_coverage.json", tmp_path / "data_watch.json")
    k.refresh()
    return k


NQ = [{"session": D.isoformat(), "status": "partial", "class": "filling",
       "holes": [hole(D, 12, 14, "filling", until_utc="2026-09-26T00:00:00+00:00"), hole(D, 17, 18, "not_a_hole")],
       "thin": [hole(D, 9, 11, "filling")]},
      {"session": P.isoformat(), "status": "partial", "class": "lost", "holes": [hole(P, 15, 17, "lost")]},
      {"session": PP.isoformat(), "status": "partial", "class": "vendor_gap", "holes": [hole(PP, 13, 15, "vendor_gap")]}]


def test_each_sessions_holes_are_what_the_page_draws(tmp_path):
    """lost and vendor gap: grey (nobody has it); filling: amber; an hour short of its ids: a tint; not a hole: nothing."""
    k = known(tmp_path, {"NQ": NQ})
    assert k.holes("NQ", D) == [[session_ms(D, 9, 0), session_ms(D, 11, 0), "thin"],
                                [session_ms(D, 12, 0), session_ms(D, 14, 0), "filling"]]
    assert k.holes("NQ", P) == [[session_ms(P, 15, 0), session_ms(P, 17, 0), "lost"]]
    assert k.holes("NQ", PP) == [[session_ms(PP, 13, 0), session_ms(PP, 15, 0), "lost"]]
    assert k.holes("NQ", D + dt.timedelta(days=1)) == [] and k.holes("ES", D) == []


def test_a_session_never_recorded_is_a_hole_in_front_of_the_next_session_the_chart_has(tmp_path):
    """A missing session has no file, so no chart session to carry its band: the next one that has a file
    does -- and the session under way when the newest is the missing one."""
    es = [{"session": D.isoformat(), "status": "missing", "class": "filling"},
          {"session": P.isoformat(), "status": "complete", "class": "whole", "holes": []},
          {"session": PP.isoformat(), "status": "missing", "class": "lost"},
          {"session": "2026-09-21", "status": "missing", "class": "not_a_hole"}]       # a holiday: nothing to draw
    k = known(tmp_path, {"ES": es})
    s, e = (int(x.timestamp() * 1000) for x in T.session_bounds(PP))
    assert k.holes("ES", P) == [[s, e, "lost"]]
    s, e = (int(x.timestamp() * 1000) for x in T.session_bounds(D))
    assert k.holes("ES", D) == [] and k.holes("ES", D + dt.timedelta(days=1)) == [[s, e, "filling"]]


def test_no_report_an_old_report_or_a_broken_one_give_no_holes(tmp_path):
    assert known(tmp_path).holes("NQ", D) == []
    old = [{"session": D.isoformat(), "status": "partial", "holes": [{**hole(D, 12, 14, "x"), "needs_massive": True}]}]
    for h in old[0]["holes"]:
        del h["class"]                                               # a report written before the classes existed
    assert known(tmp_path, {"NQ": old}).holes("NQ", D) == []
    (tmp_path / "tick_coverage.json").write_text("{ not json")
    assert known(tmp_path).holes("NQ", D) == []


def test_refresh_reads_a_file_only_when_it_moved_and_names_the_roots_whose_holes_changed(tmp_path, monkeypatch):
    k = known(tmp_path, {"NQ": NQ, "ES": []})
    reads = []
    real = json.loads
    monkeypatch.setattr("homebase.charts.known.json.loads", lambda s: (reads.append(1), real(s))[1])
    assert k.refresh() == set() and reads == []                     # nothing moved: two stats, no read
    filled = [dict(NQ[0], holes=[], thin=[])] + NQ[1:]               # the fill landed: today's hole is gone
    report(tmp_path, {"NQ": filled, "ES": [{"session": P.isoformat(), "status": "missing", "class": "lost"}]})
    assert k.refresh() == {"NQ", "ES"} and len(reads) == 1
    assert k.holes("NQ", D) == [] and k.holes("NQ", P) != []
    report(tmp_path, {"NQ": filled, "ES": [{"session": P.isoformat(), "status": "missing", "class": "lost"}],
                      "YM": [{"session": D.isoformat(), "status": "complete", "class": "whole", "holes": []}]})
    assert k.refresh() == set()                                      # rewritten, the same holes: no chart reloads


def test_the_history_labels_a_session_with_its_holes_and_says_nothing_when_it_has_none(tmp_path):
    write_archive(tmp_path / "ticks", "NQ", P, "NQZ6", rows(session_ms(P, 9, 30), [100.0] * 5))
    write_archive(tmp_path / "ticks", "NQ", PP, "NQZ6", rows(session_ms(PP, 9, 30), [100.0] * 5))
    k = known(tmp_path, {"NQ": [e for e in NQ if e["session"] != PP.isoformat()]})
    h = History(TickStore(tmp_path / "ticks"), cache_dir=tmp_path / "cache", known=k)
    assert h.info("NQ", P)["holes"] == [[session_ms(P, 15, 0), session_ms(P, 17, 0), "lost"]]
    assert "holes" not in h.info("NQ", PP)
    assert "holes" not in History(TickStore(tmp_path / "ticks"), cache_dir=tmp_path / "cache").info("NQ", P)


WATCH = {"at_utc": "2026-09-24T13:55:00+00:00", "level": "warn", "late_s": 600, "late": ["NQ", "ES"], "thin": ["NQ"],
         "silent": [], "line": "data: the live feed is 10 min late (2 of 2 markets); thin: NQ got 16% of its ticks",
         "markets": {"NQ": {"open": True, "share": 0.16}}, "refused": [], "leaving": [{"root": "GC"}]}


def test_the_watchdogs_reading_as_the_status_message_carries_it(tmp_path):
    k = known(tmp_path, watch=WATCH)
    now = session_ms(D, 10, 0)                                       # 10:00 ET: checked five minutes ago
    assert k.data(now) == {"at_utc": "2026-09-24T13:55:00+00:00", "age_s": 300, "stale": False, "level": "warn",
                           "line": WATCH["line"], "late_s": 600, "late": ["NQ", "ES"], "thin": ["NQ"], "silent": [],
                           "refused": 0, "leaving": 1}
    assert k.data(session_ms(D, 14, 0))["stale"] is True             # four hours on: the tick job stopped checking
    assert known(tmp_path / "none").data(now) is None                # no reading yet: nothing said
    (tmp_path / "data_watch.json").write_text("[]")
    k.refresh()
    assert k.data(now) is None


def test_todays_thin_hours_are_given_only_when_the_reading_is_newer_than_the_tape(tmp_path):
    """The watchdog reads the files at the END of the tick job's run; the chart reloads today's tape the minute
    a fill lands, during the run. A reading older than the tape still calls the hour just repaired thin: it is
    not used -- no tint rather than a wrong one -- until the next reading."""
    spans = [[session_ms(D, 8, 0), session_ms(D, 9, 0), "thin"]]
    k = known(tmp_path, watch={**WATCH, "markets": {"NQ": {"open": True, "session": D.isoformat(), "holes": spans},
                                                    "ES": {"open": True, "session": P.isoformat(), "holes": spans},
                                                    "YM": {"open": False}}})
    read_at = session_ms(D, 9, 55)                                   # WATCH's at_utc
    assert k.today("NQ", D, tape_ms=read_at - 60_000, now_ms=read_at + 300_000) == spans
    assert k.today("NQ", D, tape_ms=read_at + 60_000, now_ms=read_at + 300_000) == []     # the tape is newer
    assert k.today("NQ", D, tape_ms=None, now_ms=read_at + 300_000) == []                 # no tape yet
    assert k.today("NQ", D, tape_ms=read_at - 60_000, now_ms=read_at + 4 * 3_600_000) == []   # the reading is stale
    assert k.today("ES", D, tape_ms=0, now_ms=read_at) == []                              # another session's reading
    assert k.today("YM", D, tape_ms=0, now_ms=read_at) == [] and k.today("CL", D, tape_ms=0, now_ms=read_at) == []
