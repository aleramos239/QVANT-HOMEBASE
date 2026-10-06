"""The archive repairs itself: every run of the job (hourly, on load, 17:20,
05:30) finds exactly what the archive file and the live recording lack -- by
runs of broker tick ids -- and fetches only that. Fakes and tmp dirs only."""
from __future__ import annotations

import collections
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
    assert len(broker.asked) == T.DAY_ROOT_PAGES              # one root: its share of the run's pages
    hole_start = T.session_bounds(D)[0].timestamp() * 1000 + 9 * 3_600_000
    with gzip.open(path, "rt") as f:                          # the earliest tick the capped run got
        reached = min(int(line.split(",")[0]) for line in list(f)[1:] if int(line.split(",")[0]) > hole_start)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == 2 * T.DAY_ROOT_PAGES
    assert broker.asked[T.DAY_ROOT_PAGES][1] == reached       # picked up where the last run stopped
    for _ in range(30):
        run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert held(path, ticks[:16 * 60 + 1])


def test_a_daytime_run_gives_each_root_its_share_of_the_pages(tmp_path, monkeypatch):
    """2026-10-05 14:54, the live stream thinned and every root's tape to fetch: NQ took 38 of the
    run's 45 pages, ES the other 7, thirteen roots none. Now DAY_ROOT_PAGES a root, in priority
    order, DAY_PAGES in all -- and what a root's share paged is on disk."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    roots = ("NQ", "ES", "YM", "RTY")
    broker = HistoryWindow(nw, {T.symbols.front_month(r, D): _minute_ticks(D) for r in roots}, page=2)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    assert T.DAY_PAGES == 3 * T.DAY_ROOT_PAGES
    out = run(T.record(roots=roots, dates=[D], base=tmp_path, ws=object(), day=True))
    assert collections.Counter(c for c, _ in broker.asked) == {"NQZ6": 15, "ESZ6": 15, "YMZ6": 15}
    assert sorted(m["root"] for m in out) == ["ES", "NQ", "YM"] and {m["ticks"] for m in out} == {16}


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
    assert len(got) == 121                                  # 18:00 -> 20:00 ET, the hours published so far


def test_every_request_of_a_run_is_paced_even_a_jobs_first(tmp_path, monkeypatch):
    """Review 1: the 36 s pace held within a fetch but not between jobs (0 s at 17:20)."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 17, 50, tzinfo=ET))
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


def test_a_refused_merge_is_tried_again_while_the_broker_has_the_session_then_left_alone(
        tmp_path, monkeypatch, capsys):
    """Review 7: a merge refused (here: an archive file that does not read) used to be re-fetched,
    and refused, every hour for ever -- so it was left alone at once, until its files changed. But
    after the close they never change: 2026-10-05, 28 sessions were refused once and their ticks
    left the broker un-merged. Now a run tries again while the broker still has the session, and
    leaves it alone after."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    path.write_bytes(b"not a gzip file")
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    asked = len(broker.asked)
    assert asked and capsys.readouterr().out.count("MERGE REFUSED") == 1
    nw.now = dt.datetime(2026, 9, 29, 11, 10, tzinfo=ET)        # an hour on: the broker still has it
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == 2 * asked and capsys.readouterr().out.count("MERGE REFUSED") == 1
    nw.now = dt.datetime(2026, 9, 30, 20, 30, tzinfo=ET)        # the session has left the broker
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=False))
    assert len(broker.asked) == 2 * asked and capsys.readouterr().out == ""
    nw.now = dt.datetime(2026, 9, 29, 12, 10, tzinfo=ET)
    path.unlink()                                                # someone deals with it
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) > 2 * asked and held(path, ticks[:16 * 60 + 1])


def test_a_refusal_ends_that_sessions_pieces_for_the_run(tmp_path, monkeypatch, capsys):
    """Tried again every run -- but one piece of it: a session that keeps being refused must not
    spend the login's pages hour after hour while the other roots wait behind it."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    path.write_bytes(b"not a gzip file")
    es = T.archive_path("ES", D, "ESZ6", tmp_path)
    broker.ticks["ESZ6"] = ticks
    _write_live(A.live_path(es), ticks[:-30])
    run(T.record(roots=("NQ", "ES"), dates=[D], base=tmp_path, ws=object(), cache={}, day=False))
    out = capsys.readouterr().out
    assert out.count("NQ 2026-09-29 NQZ6: MERGE REFUSED") == 1
    assert collections.Counter(c for c, _ in broker.asked) == {"NQZ6": 4, "ESZ6": 1}    # the hole; not NQ's close
    assert _ids(es) == [r["id"] for r in ticks]                  # the root behind it had its turn


def test_store_remembers_a_refusal_with_the_files_stamps(tmp_path, capsys):
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a gzip file")
    cache = {}
    start, end = T.session_bounds(D)
    assert T.store("NQ", D, "NQZ6", path, start, end, [A.row_of(_minute_ticks(D)[0])], cache=cache) is None
    assert "MERGE REFUSED" in capsys.readouterr().out and T.refused_still(cache, "NQ", D, path)
    nw = dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET)            # the broker still has the session:
    assert not T.refused_still(cache, "NQ", D, path, nw) and T.missing("NQ", D, tmp_path, nw, cache)[0]   # tried again
    gone = dt.datetime(2026, 9, 30, 20, 0, tzinfo=ET)           # 00:00 UTC two days on: it has left the broker
    assert T.refused_still(cache, "NQ", D, path, gone)
    assert T.missing("NQ", D, tmp_path, gone, cache)[0] == []   # left alone ...
    path.write_bytes(b"someone fixed it, or not")
    assert not T.refused_still(cache, "NQ", D, path, gone)      # ... until its file changes


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


def test_each_piece_is_on_disk_before_the_next_is_asked_for(tmp_path, monkeypatch):
    """Review 10 made it one merge a session a run: each piece used to rewrite the whole file (ES:
    1.3M rows, per restart gap). Since then gaps a few ticks apart are one piece (BRIDGE_TICKS) --
    and 2026-10-05 a run held 2 h 43 min of fetched pages in memory, to merge them at its end.
    Now a piece is merged as it lands: whatever ends the run later, it is in the file."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    lp = path.with_name("2026-09-29_NQZ6.live.csv.gz")
    lp.unlink()
    lost = [ticks[i]["id"] for i in (200, 300, 500, 700)]                 # four restarts after 20:00 ET
    _write_live(lp, [r for r in ticks if r["id"] not in lost])
    merges, on_disk = [], []
    real = A.merge_session
    monkeypatch.setattr(A, "merge_session", lambda *a, **k: (merges.append(1), real(*a, **k))[1])

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        on_disk.append(set(_ids(path)) if path.exists() else set())      # the file as each request goes out
        return await broker.pager(ws, contract, before_ms)
    monkeypatch.setattr(T, "fetch_page", pager)
    out = run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache={}, day=False))
    assert len(merges) == 2              # the four gaps (one piece: a few ticks apart), then the close
    assert on_disk[0] == set() and on_disk[-1] >= set(lost)               # the first piece, before the second
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


# ---- waiting for the desk's md token (2026-09-30: the 09:03 run started right after a wake, before the
# desk had reconnected and written its token at 09:05, and waited a whole hour for the next run)
class TokenDesk:
    """A run whose record() fails with NoMdToken until `after` polls have passed, a fake sleep that
    is the only clock, and the token file the desk writes (read for real by _wait_for_token)."""

    def __init__(self, tmp_path, monkeypatch, *, after, now=dt.datetime(2026, 9, 30, 9, 3, tzinfo=ET)):
        from types import SimpleNamespace
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.after, self.sleeps, self.calls, self.now = after, [], 0, now
        monkeypatch.setattr(T, "state_dir", lambda: self.state)
        monkeypatch.setattr(T.config_mod, "load", lambda: SimpleNamespace(
            accounts={"acct": SimpleNamespace(live=True)}))
        monkeypatch.setattr(T, "now_et", lambda: self.now)
        monkeypatch.setattr(T, "report_due", lambda p: False)

        async def record(*a, **k):
            self.calls += 1
            if not (self.state / "acct.tokens.json").exists():
                raise T.NoMdToken("no valid md token on disk — is the desk running and connected?")
            return []
        monkeypatch.setattr(T, "record", record)

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += dt.timedelta(seconds=s)
        if self.after is not None and len(self.sleeps) >= self.after:
            exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
            (self.state / "acct.tokens.json").write_text(
                '{"md_access_token": "t", "expiration_time": "%s"}' % exp)


def test_a_run_before_the_desk_has_a_token_waits_and_retries_within_itself(tmp_path, monkeypatch, capsys):
    d = TokenDesk(tmp_path, monkeypatch, after=4)
    assert T.run(("NQ",), [D], tmp_path, sleep=d.sleep) == 0
    assert d.sleeps == [30, 30, 30, 30] and d.calls == 2          # tried, waited 2 min, tried again
    out = capsys.readouterr().out
    assert "waiting for the desk" in out and "still no valid md token" not in out and "run failed" not in out


def test_no_token_within_five_minutes_gives_up_quietly_until_the_next_run(tmp_path, monkeypatch, capsys):
    d = TokenDesk(tmp_path, monkeypatch, after=None)
    assert T.run(("NQ",), [D], tmp_path, sleep=d.sleep) == 0       # not a failure: the next hourly run tries again
    assert d.sleeps == [30] * 10 and d.calls == 1                  # 10 x 30 s = 5 min, then out
    out = capsys.readouterr().out
    assert "still no valid md token" in out and "run failed" not in out


def test_the_wait_ends_at_0920_and_a_late_run_does_not_wait_into_the_window(tmp_path, monkeypatch, capsys):
    d = TokenDesk(tmp_path, monkeypatch, after=None, now=dt.datetime(2026, 9, 30, 9, 18, 45, tzinfo=ET))
    assert T.run(("NQ",), [D], tmp_path, sleep=d.sleep) == 0
    assert d.sleeps == [30, 30] and d.now == dt.datetime(2026, 9, 30, 9, 19, 45, tzinfo=ET)   # the next 30 s would cross 09:20
    assert d.calls == 1 and "still no valid md token" in capsys.readouterr().out


def test_only_a_missing_token_is_waited_out(tmp_path, monkeypatch, capsys):
    d = TokenDesk(tmp_path, monkeypatch, after=None)

    async def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(T, "record", broken)
    assert T.run(("NQ",), [D], tmp_path, sleep=d.sleep) == 1
    assert d.sleeps == [] and "run failed: RuntimeError: boom" in capsys.readouterr().out


def test_md_token_says_NoMdToken_only_when_there_is_no_token_at_all(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(T.config_mod, "load", lambda: SimpleNamespace(
        accounts={"demo1": SimpleNamespace(live=False)}))
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    with pytest.raises(T.NoMdToken, match="no valid md token on disk"):
        T.md_token()
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    (tmp_path / "demo1.tokens.json").write_text('{"md_access_token": "t", "expiration_time": "%s"}' % exp)
    with pytest.raises(RuntimeError, match="never pages on the other login") as e:
        T.md_token(strict=True)                 # a token exists, for the wrong login: not "not yet"
    assert not isinstance(e.value, T.NoMdToken)


def test_a_refusal_under_an_older_merge_rule_is_tried_again(tmp_path):
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    cache = {T.REFUSED: {f"NQ {D}": {"stamp": T.files_stamp(path), "why": "old"}}}     # no rules recorded
    assert not T.refused_still(cache, "NQ", D, path)
    cache[T.REFUSED][f"NQ {D}"]["rules"] = A.MERGE_RULES
    assert T.refused_still(cache, "NQ", D, path)


def test_a_recorder_that_kept_a_tick_a_minute_is_one_job_not_one_per_minute(tmp_path, monkeypatch):
    """GC 2026-09-29 05:00-06:00 ET: 75 one-minute gaps were 75 paced pages (45 minutes)."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    ticks = _minute_ticks(D)
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    kept = [r for i, r in enumerate(ticks) if i < 6 * 60 or i % 2 == 0 or i > 7 * 60]   # 00:00-01:00 ET: every other tick
    _write_live(path.with_name("2026-09-29_NQZ6.live.csv.gz"), kept)
    gaps = T.missing("NQ", D, tmp_path, nw.now, {})[0]
    inside = [g for g in gaps if g[2].endswith("gaps")]
    assert len(inside) == 1 and inside[0][2].startswith("30 ticks in 30 gaps")       # one job for the hour
    assert inside[0][0] < inside[0][1]


# ---- 2026-10-05: the live stream thinned, 28 sessions refused, what was fetched thrown away
@pytest.mark.parametrize("hhmm,upto", [((19, 44), None), ((19, 45), "19:00"), ((19, 58), "19:00"),
                                       ((20, 44), "19:00"), ((20, 45), "20:00"), ((23, 0), "22:00")])
def test_only_hours_that_ended_45_minutes_ago_are_asked_for(tmp_path, hhmm, upto):
    """The broker's history of an hour it has not published yet is thinned like the live stream: NQ's
    19:00 ET hour asked at 19:58 held 84 of 2,166 ids -- and the job wrote those rows into the archive."""
    nxt = dt.date(2026, 9, 30)                                   # the session that opened at 18:00 tonight
    gaps, _ = T.missing("NQ", nxt, tmp_path, dt.datetime(2026, 9, 29, *hhmm, tzinfo=ET), {})
    assert [(_hm(a), _hm(b), why) for a, b, why in gaps] == ([("18:00", upto, "nothing recorded")] if upto else [])


def _hm(ms):
    return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%H:%M")


def test_a_run_leaves_the_unpublished_hours_to_a_later_one(tmp_path, monkeypatch):
    """19:58 ET, the recorder alive and thinned (one tick in four): the gaps between its ticks are
    fetched up to 19:00, the hour in progress not at all; an hour later the next one is in."""
    nxt = dt.date(2026, 9, 30)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 29, 19, 58, tzinfo=ET))
    ticks = _minute_ticks(nxt)
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=500)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    path = T.archive_path("NQ", nxt, "NQZ6", tmp_path)
    _write_live(A.live_path(path), [r for r in ticks[:118] if r["id"] % 4 == 1])      # 18:00 ... 19:56
    cache = {}
    run(T.record(roots=("NQ",), dates=[nxt], base=tmp_path, ws=object(), cache=cache, day=False))
    seven = _ms(dt.datetime(2026, 9, 29, 19, 0, tzinfo=ET))
    assert broker.asked and all(b <= seven for _, b in broker.asked)
    assert _ids(path) == [r["id"] for r in ticks[:61]]                              # 18:00 -> 19:00, whole
    nw.now = dt.datetime(2026, 9, 29, 20, 58, tzinfo=ET)
    _write_live(A.live_path(path), [r for r in ticks[118:178] if r["id"] % 4 == 1])
    run(T.record(roots=("NQ",), dates=[nxt], base=tmp_path, ws=object(), cache=cache, day=False))
    assert _ids(path) == [r["id"] for r in ticks[:121]]                             # ... -> 20:00


def test_pages_already_fetched_survive_a_dropped_line(monkeypatch):
    """2026-10-05 18:52: ES's 09:58-14:49 ET -- 55 minutes of pages, then a page that never answered
    ("FAILED" and nothing after it: a timeout has no text), and every one of them was gone."""
    NoWait(monkeypatch)
    d = dt.date(2026, 9, 22)
    start, end = T.session_bounds(d)
    rows, calls = _minute_ticks(d), []

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls.append(before_ms)
        if len(calls) == 4:
            raise TimeoutError()
        return [r for r in rows if r["ts_ms"] <= before_ms][-100:]
    got, stats = run(T.fetch_session(None, "ESZ6", start, end, page_fn=pager))
    assert stats["stop"] == "failed" and isinstance(stats["error"], TimeoutError) and stats["pages"] == 3
    assert got == rows[-298:] and stats["earliest_ms"] == got[0]["ts_ms"]     # three pages, a tick shared each
    calls[:] = [0, 0, 0]
    with pytest.raises(TimeoutError):                         # nothing paged yet: nothing to keep, raised as before
        run(T.fetch_session(None, "ESZ6", start, end, page_fn=pager))
    ok, stats = run(T.fetch_session(None, "ESZ6", start, end, page_fn=pager))
    assert stats["error"] is None and stats["stop"] == "exhausted" and ok == rows


def test_a_run_cut_short_merges_what_it_had_paged_and_the_next_goes_on_from_there(tmp_path, monkeypatch, capsys):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET),
                                          page=50)
    calls = []

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls.append(before_ms)
        if len(calls) == 4:
            raise OSError("[Errno 8] nodename nor servname provided, or not known")
        return await broker.pager(ws, contract, before_ms)
    monkeypatch.setattr(T, "fetch_page", pager)
    cache = {}
    out = run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=False))
    said = capsys.readouterr().out
    assert said.count("FAILED") == 1 and "148 ticks, 3 pages" in said and len(calls) == 4    # the run ended there
    hole = [r["id"] for r in ticks[9 * 60:15 * 60]]                      # 03:00-09:00 ET, lost to the battery
    assert [i for i in _ids(path) if i in hole] == hole[-147:]           # the three pages (148 less the 09:00 tick held)
    cut = next(x for x in out[0]["sources"] if x["kind"] == "history")
    assert cut["stop"] == "failed" and cut["pages"] == 3 and "error" not in cut
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=False))
    assert calls[4] == cut["earliest_ms"]                                # the next run: from where it was cut
    assert _ids(path) == [r["id"] for r in ticks]


def test_a_day_run_out_of_budget_keeps_its_pages(tmp_path, monkeypatch, capsys):
    """The login's hour spent mid-fetch (the chart service shares it) used to throw the fetch away:
    with ten pages left an hour, a stretch of more than ten was paged again every run, never merged."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET),
                                          page=2)
    usage = tmp_path / "md_usage.json"
    usage.write_text(__import__("json").dumps({"requests": {
        "live": [nw.now.timestamp() - 20 * i for i in range(T.SHARED_MD_CAP - 10)]}}))
    run(_record_with_conn(tmp_path, usage))
    assert len(broker.asked) == 10 and "the next run goes on" in capsys.readouterr().out
    assert len(_ids(path)) == 11                                          # ten pages of two, a tick shared each


class NoTokenYet:
    """The job's own socket (ws=None) with the desk's token files read for real: connect_md says
    NoMdToken until `after` polls of the wait have passed (the desk then writes its token)."""

    def __init__(self, tmp_path, monkeypatch, nw, after):
        from types import SimpleNamespace
        self.state, self.nw, self.after, self.sleeps = tmp_path / "state", nw, after, []
        self.state.mkdir()
        monkeypatch.setattr(T, "state_dir", lambda: self.state)
        monkeypatch.setattr(T.config_mod, "load", lambda: SimpleNamespace(
            accounts={"acct": SimpleNamespace(live=True)}))
        monkeypatch.setattr(T, "coverage_report", lambda *a, **k: None)

        class Sock:
            connected = True

            async def close(self):
                pass

        async def connect(**kw):
            T.md_token(**kw)                                   # NoMdToken while no token file is valid
            return Sock()
        monkeypatch.setattr(T, "connect_md", connect)

    def sleep(self, s):
        self.sleeps.append(s)
        self.nw.now += dt.timedelta(seconds=s)
        if self.after is not None and len(self.sleeps) >= self.after:
            exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
            (self.state / "acct.tokens.json").write_text(
                '{"md_access_token": "t", "expiration_time": "%s"}' % exp)


def test_a_fetch_without_a_token_reaches_the_wait_for_the_desk(tmp_path, monkeypatch, capsys):
    """The wait (2026-09-30) only ever met a faked record(): the real one caught NoMdToken itself --
    16 "FAILED no valid md token" lines in the log, not one "waiting for the desk"."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    desk = NoTokenYet(tmp_path, monkeypatch, nw, after=2)
    assert T.run(("NQ",), [D], tmp_path, sleep=desk.sleep) == 0
    out = capsys.readouterr().out
    assert "waiting for the desk" in out and "FAILED" not in out and "still no valid md token" not in out
    assert desk.sleeps == [30, 30] and held(path, ticks[:16 * 60 + 1])   # waited a minute, then fetched


def test_with_no_token_the_live_recordings_are_merged_all_the_same(tmp_path, monkeypatch, capsys):
    """No token, no fetch -- but a finished session's live recording needs none (the weekend of
    2026-10-03 the desk was off for hours and the recordings went in)."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET))
    desk = NoTokenYet(tmp_path, monkeypatch, nw, after=None)
    reported = []
    monkeypatch.setattr(T, "report_due", lambda p: False)
    monkeypatch.setattr(T, "coverage_report", lambda *a, **k: reported.append(1))
    assert T.run(("NQ",), [D], tmp_path, sleep=desk.sleep) == 0
    out = capsys.readouterr().out
    assert "live recording merged" in out and "still no valid md token" in out and "FAILED" not in out
    assert broker.asked == [] and len(_ids(path)) == 9 * 60 + 61 and desk.sleeps == [30] * 10
    assert reported == [1]                                         # ... and the coverage report says so


def test_a_token_lost_mid_fetch_keeps_the_pages_and_asks_for_the_desk(tmp_path, monkeypatch):
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 21, 0, tzinfo=ET),
                                          page=50)
    calls = []

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls.append(before_ms)
        if len(calls) == 3:
            raise T.NoMdToken("no valid md token on disk — is the desk running and connected?")
        return await broker.pager(ws, contract, before_ms)
    monkeypatch.setattr(T, "fetch_page", pager)
    with pytest.raises(T.NoMdToken):
        run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache={}, day=False))
    hole = [r["id"] for r in ticks[9 * 60:15 * 60]]
    assert [i for i in _ids(path) if i in hole] == hole[-98:] and len(calls) == 3    # two pages: in the file


def test_the_sessions_refused_under_the_size_rule_are_tried_again(tmp_path):
    """The 28 sessions frozen 2026-10-02 / 10-05 were refused under merge rules 2 ('not one feed')."""
    path = T.archive_path("NQ", D, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    cache = {T.REFUSED: {f"NQ {D}": {"stamp": T.files_stamp(path), "rules": 2, "why": "sizes"}}}
    assert A.MERGE_RULES == 3 and not T.refused_still(cache, "NQ", D, path)


def test_ids_still_missing_after_a_thinned_fetch_are_asked_again_until_the_broker_has_them(tmp_path, monkeypatch):
    """ES 2026-10-05 02:00-04:00 ET, asked at 13:27 -- nine hours on: 185 ticks where 28,000 ids are.
    The broker serves thinned rows for hours long over, the fetch "reached" its start all the same,
    and the stretch was logged as served in full: nothing ever asked again. Between two held
    ticks the ids decide: asked again each run (a page, while it is thinned) until they are in."""
    nw, ticks, broker, path = battery_day(tmp_path, monkeypatch, dt.datetime(2026, 9, 29, 10, 10, tzinfo=ET))
    hole = ticks[9 * 60:15 * 60]                                 # 03:00-09:00 ET
    thinned = [r for r in ticks if r not in hole or r["id"] % 20 == 0]
    broker.ticks["NQZ6"] = thinned
    cache = {}
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == 1 and len(_ids(path)) == 20      # 18 of the hole's 360, and its two edges
    assert A.load_manifest(path)["sources"][-1]["stop"] == "reached"
    nw.now = dt.datetime(2026, 9, 29, 10, 25, tzinfo=ET)         # the next run: still thinned
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == 2 and len(_ids(path)) == 20      # asked again: one page, nothing new
    broker.ticks["NQZ6"] = ticks                                  # the broker has published the hours
    nw.now = dt.datetime(2026, 9, 29, 10, 40, tzinfo=ET)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert held(path, ticks[:16 * 60 + 1]) and len(broker.asked) == 6
    asked = len(broker.asked)
    nw.now = dt.datetime(2026, 9, 29, 10, 44, tzinfo=ET)
    run(T.record(roots=("NQ",), dates=[D], base=tmp_path, ws=object(), cache=cache, day=True))
    assert len(broker.asked) == asked                             # whole: nothing more to ask
