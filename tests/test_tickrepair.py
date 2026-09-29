"""The archive repairs itself: every run of the job (hourly, on load, 17:20,
05:30) finds exactly what the archive file and the live recording lack -- by
runs of broker tick ids -- and fetches only that. Fakes and tmp dirs only."""
from __future__ import annotations

import datetime as dt
import gzip
import os

import pytest

from homebase import tickarchive as A
from homebase import ticks as T
from tests.test_ticks import HistoryWindow, NoWait, _ids, _minute_ticks, _write_live, run

ET = T.ET
D = dt.date(2026, 9, 29)                                  # a Tuesday


def battery_day(tmp_path, monkeypatch, now, page=100):
    """The live recording of 09-29 with the machine dead from 03:00 to 09:00 ET
    (its tick ids skip those hours), recording again until 10:00."""
    nw = NoWait(monkeypatch, now=now)
    ticks = _minute_ticks(D)
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=page)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    kept = [r for i, r in enumerate(ticks) if not 9 * 60 <= i < 15 * 60 and i <= 16 * 60]
    _write_live(path.with_name("2026-09-29_NQZ6.live.csv.gz"), kept)
    return nw, ticks, broker, path


def held(path, ticks_upto):
    """Archive ids | live ids hold every one of those ticks."""
    live = _ids(path.with_name("2026-09-29_NQZ6.live.csv.gz"))
    have = set(_ids(path)) | set(live) if path.exists() else set(live)
    return have >= {r["id"] for r in ticks_upto}


def test_a_dead_battery_hole_is_filled_by_day_and_the_next_run_is_quiet(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert held(path, ticks[:16 * 60 + 1])                    # 18:00 -> 10:00, nothing missing
    man = A.load_manifest(path)
    assert [s["why"] for s in man["sources"]] == ["360 ticks"]   # the first tick is the 18:00:00.000 open
    assert [s["kind"] for s in man["sources"]] == ["history"]     # the growing live file: not merged yet
    out = capsys.readouterr().out
    assert "(360 ticks): 362 ticks, 4 pages" in out and len(broker.asked) == 4
    asked = len(broker.asked)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == asked and capsys.readouterr().out == ""      # nothing to do: silent


def test_a_daytime_run_spends_at_most_its_pages_and_the_next_one_goes_on(tmp_path, monkeypatch):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET),
                                          page=2)
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == T.DAY_PAGES
    hole_start = T.session_bounds(D)[0].timestamp() * 1000 + 9 * 3_600_000
    with gzip.open(path, "rt") as f:                          # the earliest tick the capped run got
        reached = min(int(line.split(",")[0]) for line in list(f)[1:] if int(line.split(",")[0]) > hole_start)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == 2 * T.DAY_PAGES
    assert broker.asked[T.DAY_PAGES][1] == reached            # picked up where the last run stopped
    for _ in range(10):
        run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert held(path, ticks[:16 * 60 + 1])


def test_not_one_request_between_0920_and_0935(tmp_path, monkeypatch):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 9, 19, 30, tzinfo=ET),
                                          page=2)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), day=True))
    assert len(broker.asked) == 1                              # 09:19:30; the next page would be 09:20:06
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path / "state")
    nw.now = dt.datetime(2026, 9, 29, 9, 25, tzinfo=ET)

    async def never(*a, **k):
        raise AssertionError("a run inside 09:20-09:35")
    monkeypatch.setattr(T, "record", never)
    assert T.run(("NQ",), [D], tmp_path) == 0


def test_a_rate_limit_reply_ends_the_daytime_run(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    asked = []

    async def limited(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        asked.append(before_ms)
        raise T.Penalty({"p-ticket": "t", "p-time": 30, "p-message": "Rate limit exceeded"})
    monkeypatch.setattr(T, "fetch_page", limited)
    assert run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), day=True)) == []
    assert len(asked) == 1 and "backing off until the next run" in capsys.readouterr().out


def test_a_refused_connection_ends_the_daytime_run(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    asked = []

    async def refused(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        asked.append(before_ms)
        raise RuntimeError("server rejected WebSocket connection: HTTP 429")
    monkeypatch.setattr(T, "fetch_page", refused)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), day=True))
    assert len(asked) == 1 and "HTTP 429" in capsys.readouterr().out


def test_a_run_already_going_is_left_to_it_and_nothing_to_do_says_nothing(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    state = tmp_path / "state"
    monkeypatch.setattr(T, "state_dir", lambda: state)
    with T.archive_lock(state / "ticks.lock"):
        assert T.run(("NQ",), [D], tmp_path) == 0
    assert capsys.readouterr().out == "" and broker.asked == []
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    (state / "tick_runs.json").write_text(__import__("json").dumps(cache))
    (state / "tick_coverage.json").write_text("{}")           # a fresh report: none due
    capsys.readouterr()
    asked = len(broker.asked)
    assert T.run(("NQ",), [D], tmp_path) == 0
    assert capsys.readouterr().out == "" and len(broker.asked) == asked


def test_the_live_file_is_read_only_where_it_grew(tmp_path, monkeypatch):
    p = tmp_path / "x.live.csv.gz"
    ticks = _minute_ticks(D)
    _write_live(p, ticks[:100])
    cache = {}
    assert A.file_runs(p, cache)["runs"] == [[1, 100, ticks[0]["ts_ms"], ticks[99]["ts_ms"]]]
    seen = []
    real = A._complete_members
    monkeypatch.setattr(A, "_complete_members", lambda data: (seen.append(len(data)), real(data))[1])
    before = p.stat().st_size
    _write_live(p, ticks[100:110])
    _write_live(p, ticks[150:160])                           # a restart lost 40 ticks
    with open(p, "ab") as f:
        f.write(gzip.compress(b"1790000000000,1.0,1,,,,,999\n")[:12])   # a member being written
    runs = A.file_runs(p, cache)["runs"]
    assert seen == [os.path.getsize(p) - before]             # only what was appended
    assert [r[:2] for r in runs] == [[1, 110], [151, 160]]
    assert cache[str(p)]["offset"] < os.path.getsize(p)     # the torn member: read next time


def test_the_cache_follows_a_rewritten_file(tmp_path):
    p = tmp_path / "a.csv.gz"
    ticks = _minute_ticks(D)
    _write_live(p, ticks[:10])
    cache = {}
    A.file_runs(p, cache)
    tmp = tmp_path / "b"
    _write_live(tmp, ticks[:5])
    os.replace(tmp, p)                                         # a merge: a new file, maybe smaller
    assert [r[:2] for r in A.file_runs(p, cache)["runs"]] == [[1, 5]]


@pytest.mark.parametrize("t,quiet", [((9, 19, 59), False), ((9, 20), True), ((9, 34, 59), True), ((9, 35), False)])
def test_the_quiet_window_is_the_charts_own(t, quiet):
    from homebase.charts import QUIET
    assert T.QUIET == QUIET
    assert T.in_quiet(dt.datetime(2026, 9, 29, *t, tzinfo=ET)) is quiet
    assert not T.in_quiet(dt.datetime(2026, 9, 27, *t, tzinfo=ET))     # Sunday


def test_a_lost_connection_ends_the_night_run_with_one_line(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    asked = []

    async def dns(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        asked.append(before_ms)
        raise OSError("[Errno 8] nodename nor servname provided, or not known")
    monkeypatch.setattr(T, "fetch_page", dns)
    run(T.record(roots=("NQ", "ES"), dates=[D], base=tmp_path, ws=object(), day=False))
    assert len(asked) == 1 and capsys.readouterr().out.count("FAILED") == 1


def test_a_symbol_the_feed_refuses_does_not_stop_the_night(tmp_path, monkeypatch, capsys):
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 19, 0, tzinfo=ET))    # its first hours: still there
    good = HistoryWindow(nw, {"ESZ6": _minute_ticks(D)}, page=500)

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        if contract == "NQZ6":
            raise RuntimeError("NQZ6: getChart refused: {'s': 400}")
        return await good.pager(ws, contract, before_ms)
    monkeypatch.setattr(T, "fetch_page", pager)
    out = run(T.record(roots=("NQ", "ES"), dates=[D], base=tmp_path, ws=object(), day=False))
    assert [m["contract"] for m in out] == ["ESZ6"] and out[0]["complete"]


def test_the_runs_cache_forgets_old_files():
    now = dt.datetime(2026, 9, 29, 12, 0, tzinfo=ET)
    cache = {"/x/NQ/2026/2026-07-01_NQU6.live.csv.gz": {}, "/x/NQ/2026/2026-09-28_NQZ6.csv.gz": {},
             T.ASKED: {"NQ 2026-07-01": [[1, 2]], "NQ 2026-09-28": [[1, 2]]}}
    T.prune_cache(cache, now)
    assert list(cache) == [T.ASKED] and list(cache[T.ASKED]) == ["NQ 2026-09-28"]   # (the file does not exist)


def test_a_mondays_open_is_checked_once_even_with_fridays_ticks_gone(tmp_path, monkeypatch):
    """Monday's open is Sunday 18:00 ET; the ticks before it are Friday's, long
    out of the broker's window: the check runs the broker dry a few ms after the
    open. That is everything there is -- it is not asked again next hour."""
    mon = dt.date(2026, 9, 28)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 28, 10, 0, tzinfo=ET))
    ticks = [dict(r, ts_ms=r["ts_ms"] + 37) for r in _minute_ticks(mon)]     # first print 18:00:00.037
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    path = T.archive_path("NQ", mon, "NQZ6", tmp_path)
    ten = _ms(nw.now)
    _write_live(path.with_name("2026-09-28_NQZ6.live.csv.gz"), [r for r in ticks if r["ts_ms"] <= ten])
    cache = {}
    run(T.record(roots=("NQ",), dates=[mon], base=tmp_path, ws=object(), cache=cache, day=True))
    asked = len(broker.asked)
    assert asked >= 1
    nw.now = dt.datetime(2026, 9, 28, 11, 0, tzinfo=ET)                  # the recorder kept recording
    _write_live(path.with_name("2026-09-28_NQZ6.live.csv.gz"),
                [r for r in ticks if ten < r["ts_ms"] <= _ms(nw.now)])
    run(T.record(roots=("NQ",), dates=[mon], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == asked


def _ms(t):
    return int(t.timestamp() * 1000)


def test_an_evening_run_already_covers_the_session_that_began_at_18(tmp_path, monkeypatch):
    """Back at 21:00 ET after the machine died at 17:30: the session that opened
    at 18:00 (tomorrow's date) is looked at now, not after midnight."""
    nxt = dt.date(2026, 9, 30)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    broker = HistoryWindow(nw, {"NQZ6": _minute_ticks(nxt)}, page=500)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    assert nxt in T.candidate_dates(nw.now)
    run(T.record(roots=("NQ",), base=tmp_path, ws=object(), day=False))
    got = _ids(T.archive_path("NQ", nxt, "NQZ6", tmp_path))
    assert len(got) == 176                                  # 18:00 -> 20:55 ET, the evening so far


def test_every_request_of_a_run_is_paced_even_a_jobs_first(tmp_path, monkeypatch):
    """Review 1: the 36 s pace held within a fetch but not between jobs (0 s at 17:20)."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 17, 20, tzinfo=ET))
    books, stamps = {}, []
    for r in ("NQ", "ES", "YM"):
        c = T.symbols.front_month(r, D)
        books[c] = _minute_ticks(D, first_id=1000)
        _write_live(A.live_path(T.archive_path(r, D, c, tmp_path)), books[c][:-30])
    hw = HistoryWindow(nw, books, page=4096)

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        stamps.append(nw.now)
        return await hw.pager(ws, contract, before_ms)
    monkeypatch.setattr(T, "fetch_page", pager)
    run(T.record(roots=("NQ", "ES", "YM"), dates=[D], base=tmp_path, ws=object(), day=False))
    assert len(stamps) >= 3
    assert all((b - a).total_seconds() >= T.PAGE_INTERVAL_S for a, b in zip(stamps, stamps[1:]))


def test_the_job_leaves_the_live_login_what_the_chart_service_uses(tmp_path, monkeypatch, capsys):
    """Review 5: the chart service publishes its hourly live-login requests; a
    daytime run spends only what is left under the shared cap."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET),
                                          page=2)
    usage = tmp_path / "md_usage.json"
    now_s = nw.now.timestamp()
    usage.write_text(__import__("json").dumps({"requests": {
        "live": [now_s - 20 * i for i in range(T.SHARED_MD_CAP - 10)], "demo": [now_s] * 500}}))
    run(_record_with_conn(tmp_path, usage))
    assert len(broker.asked) == 10 and "the next run goes on" in capsys.readouterr().out


def _record_with_conn(base, usage, day=True):
    cache = {}
    conn = T.MDConn(object(), T.Budget(cache.setdefault(T.MD_USED, []), usage, day))
    return T.record(roots=("NQ",), dates=[D], base=base, ws=conn, cache=cache, day=day)


def test_a_night_run_waits_for_the_login_hour_to_free_up(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    usage = tmp_path / "md_usage.json"
    now_s = nw.now.timestamp()
    usage.write_text(__import__("json").dumps({"requests": {"live": [now_s - 3000 + i for i in range(150)]}}))
    run(_record_with_conn(tmp_path, usage, day=False))
    assert broker.asked and "the live login's hour is spent" in capsys.readouterr().out
    assert nw.now.timestamp() >= now_s + 600                   # it waited until those aged out


def test_a_refused_merge_is_not_fetched_again_until_its_files_change(tmp_path, monkeypatch, capsys):
    """Review 7: a merge refused (here: an archive file that does not read) used
    to be re-fetched, and refused, every hour."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    path.write_bytes(b"not a gzip file")
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    asked = len(broker.asked)
    assert asked and capsys.readouterr().out.count("MERGE REFUSED") == 1
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == asked and capsys.readouterr().out == ""
    path.unlink()                                                # someone deals with it
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) > asked and held(path, ticks[:16 * 60 + 1])


def test_store_remembers_a_refusal_with_the_files_stamps(tmp_path, capsys):
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a gzip file")
    cache = {}
    start, end = T.session_bounds(D)
    assert T.store("NQ", D, "NQZ6", path, start, end, [A.row_of(_minute_ticks(D)[0])], cache=cache) is None
    assert "MERGE REFUSED" in capsys.readouterr().out and T.refused_still(cache, "NQ", D, path)
    nw = dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET)
    assert T.missing("NQ", D, tmp_path, nw, cache)[0] == []    # left alone ...
    path.write_bytes(b"someone fixed it, or not")
    assert not T.refused_still(cache, "NQ", D, path)            # ... until its file changes


def test_one_empty_reply_is_asked_again_once_before_it_is_believed(tmp_path, monkeypatch):
    """Review 9: a stretch was vouched for (never asked again) on a single empty
    reply -- which a glitch can give as well as a quiet market."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    broker = HistoryWindow(nw, {"NQZ6": []}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    cache = {}
    for _ in range(3):
        nw.now = dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET)       # the same stretch each time
        run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    one_run = len(broker.asked) // 2
    assert len(broker.asked) == 2 * one_run and one_run >= 1   # runs 1 and 2 asked, run 3 did not
    assert cache[T.ASKED] and not cache.get(T.EMPTY_ONCE)


def test_a_sessions_pieces_are_merged_once_a_run(tmp_path, monkeypatch):
    """Review 10: each fetched piece used to rewrite the whole session file (ES:
    1.3M rows read, written and verified again per restart gap)."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    lp = path.with_name("2026-09-29_NQZ6.live.csv.gz")
    lp.unlink()
    _write_live(lp, [r for i, r in enumerate(ticks) if i not in (200, 300, 500, 700)])   # four restarts after 20:00 ET
    merges = []
    real = A.merge_session
    monkeypatch.setattr(A, "merge_session", lambda *a, **k: (merges.append(1), real(*a, **k))[1])
    out = run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache={}, day=False))
    assert len(merges) == 1              # four gaps and the close, all leaving the broker together: one merge
    assert out[0]["complete"] and _ids(path) == [r["id"] for r in ticks]


def test_a_merge_that_brings_nothing_new_leaves_the_file_and_updates_the_manifest(tmp_path):
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    rows = [A.row_of(r) for r in _minute_ticks(D)[:50]]
    start, end = T.session_bounds(D)
    A.merge_session(path, root="NQ", contract="NQZ6", date=D, start=start, end=end, fetched=rows,
                    fetched_source={"kind": "history"})
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    man = A.merge_session(path, root="NQ", contract="NQZ6", date=D, start=start, end=end, fetched=rows[:5],
                          fetched_source={"kind": "history", "why": "the close", "stop": "reached"})
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert A.load_manifest(path)["sources"][-1]["why"] == "the close" and man["ticks"] == 50
