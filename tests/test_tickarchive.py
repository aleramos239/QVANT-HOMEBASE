"""The tick archive's merge: never replace, union by the broker's tick id, atomic
and verified writes, the live recording only ever read. Tmp dirs only."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import json

import pytest

from homebase import tickarchive as A
from homebase import ticks as T
from homebase.charts import store

ET = T.ET
DAY = dt.date(2026, 9, 28)
START, END = T.session_bounds(DAY)
S = int(START.timestamp() * 1000)


def tick(i, *, quotes=True, price=None, ts=None):
    """A broker tick as the archive holds it (9 columns, ts_ns empty)."""
    px = price if price is not None else 20000.0 + (i % 7) * 0.25
    return A.row_of({"ts_ms": ts if ts is not None else S + i * 1000, "price": px, "size": 1 + i % 3,
                     "bid": px - 0.25 if quotes else "", "ask": px if quotes else "",
                     "bid_size": 5 if quotes else "", "ask_size": 4 if quotes else "", "id": 1000 + i})


def massive(ts_ms, seq, price=20000.0, size=1):
    return (str(ts_ms), str(price), str(size), "", "", "", "", str(seq), str(ts_ms * 1_000_000 + 7))


def write_live(p, rows, members=1):
    """The chart service's layout: header + rows, one gzip member per flush."""
    p.parent.mkdir(parents=True, exist_ok=True)
    chunks = [rows[i::members] for i in range(members)]
    with open(p, "wb") as f:
        for j, chunk in enumerate(chunks):
            lines = ([",".join(T.FIELDS)] if j == 0 else []) + [",".join(r[:8]) for r in chunk]
            f.write(gzip.compress(("\n".join(lines) + "\n").encode()))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def merge_session(path, **kw):
    return A.merge_session(path, root="NQ", contract="NQZ6", date=DAY, start=START, end=END, **kw)


def test_the_archive_speaks_the_recorders_and_the_stores_formats():
    assert A.BROKER_COLS == T.FIELDS
    assert A.LIVE_SUFFIX == store.LIVE_SUFFIX
    assert A.live_path(T.archive_path("NQ", DAY, "NQZ6")).name == "2026-09-28_NQZ6.live.csv.gz"


def test_the_fetch_and_the_live_recording_merge_by_tick_id(tmp_path):
    """Live: ids 0-99 minus a restart's loss (40-45); a few rows unquoted. History:
    20-119 (its first hours already gone); a few other rows unquoted. The file:
    0-119, each once, quotes from whichever source had them; the live file untouched."""
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    live = [tick(i, quotes=i % 10 != 3) for i in range(100) if not 40 <= i <= 45]
    lp = A.live_path(path)
    write_live(lp, live, members=3)
    before = sha(lp)
    fetched = [tick(i, quotes=i % 10 != 7) for i in range(20, 120)]
    man = merge_session(path, fetched=fetched, fetched_source={"kind": "history", "pages": 1})
    header, rows = A.read_rows(path)
    assert tuple(header) == T.FIELDS                          # broker-only: the recorder's columns
    assert [int(r[A.ID]) - 1000 for r in rows] == list(range(120))
    unquoted = sorted(int(r[A.ID]) - 1000 for r in rows if not (r[A.BID] and r[A.ASK]))
    assert unquoted == [3, 13, 107, 117]                      # quoted in neither source
    assert sha(lp) == before                                   # only ever read
    assert man["ticks"] == 120 and man["first_id"] == 1000 and man["last_id"] == 1119
    assert [s["kind"] for s in man["sources"]] == ["history", "live"]
    assert man["merge"]["only_in"] == {"history": 26, "live": 20}   # 100-119 + 40-45 / 0-19
    assert man["merge"]["quotes_filled"] == 8                  # 27, 37 ... 97 from the live file
    live_src = man["sources"][1]
    assert live_src["file"] == lp.name and live_src["bytes"] == lp.stat().st_size


def test_a_merged_live_file_is_not_read_again_until_it_changes(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    write_live(A.live_path(path), [tick(i) for i in range(10)])
    merge_session(path)
    man = merge_session(path, fetched=[tick(10)], fetched_source={"kind": "history"})
    assert man["merge"]["read"] == {"history": 1, "archive": 10}          # no second live read
    write_live(A.live_path(path), [tick(i) for i in range(12)])           # it grew
    man = merge_session(path)
    assert man["merge"]["read"]["live"] == 12 and man["ticks"] == 12


def test_a_tick_id_that_changes_between_sources_keeps_the_historys_version(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    write_live(A.live_path(path), [tick(1, price=20001.0)])
    man = merge_session(path, fetched=[tick(1, price=20000.0)], fetched_source={"kind": "history"})
    assert man["merge"]["id_conflicts"] == 1 and man["merge"]["conflict_ids"] == [1001]
    assert A.read_rows(path)[1][0][A.PX] == "20000.0"


def test_ids_that_disagree_wholesale_refuse_the_merge_and_leave_every_file(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(300)], fetched_source={"kind": "history"})
    kept, man_kept = sha(path), A.manifest_path(path).read_text()
    shifted = [tick(i, ts=S + i * 1000 + 5) for i in range(300)]          # not one id space
    with pytest.raises(A.MergeRefused, match="disagree"):
        merge_session(path, fetched=shifted, fetched_source={"kind": "history"})
    assert sha(path) == kept and A.manifest_path(path).read_text() == man_kept
    assert not list(path.parent.glob("*.tmp"))


def test_a_write_that_does_not_verify_leaves_the_original(tmp_path, monkeypatch):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(5)], fetched_source={"kind": "history"})
    kept = sha(path)

    def bad(p, m, fields):
        raise A.MergeRefused("simulated read-back mismatch")
    monkeypatch.setattr(A, "verify", bad)
    with pytest.raises(A.MergeRefused):
        merge_session(path, fetched=[tick(i) for i in range(10)], fetched_source={"kind": "history"})
    assert sha(path) == kept and not list(path.parent.glob("*.tmp"))


def test_verify_catches_a_missing_tick(tmp_path):
    m = A.merge([("history", [tick(i) for i in range(5)])])
    p = tmp_path / "x.csv.gz"
    A.write_rows(p, m)
    m.ids.add(99999)                                  # the file lacks a tick the merge holds
    with pytest.raises(A.MergeRefused, match="1 tick ids missing"):
        A.verify(p, m, A.BROKER_COLS)


def test_an_unreadable_archive_file_is_never_replaced(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a gzip file")
    with pytest.raises(A.MergeRefused, match="unreadable"):
        merge_session(path, fetched=[tick(1)], fetched_source={"kind": "history"})
    assert path.read_bytes() == b"not a gzip file"


def test_rows_without_an_id_are_never_collapsed(tmp_path):
    r = A.row_of({"ts_ms": S, "price": 1.0, "size": 1, "bid": 0.5, "ask": 1.0, "id": None})
    m = A.merge([("history", [r, r]), ("live", [r])])
    assert len(m.rows) == 2                            # max of the per-source counts, not a set


def test_a_torn_live_tail_is_dropped_not_raised(tmp_path):
    p = tmp_path / "x.live.csv.gz"
    write_live(p, [tick(i) for i in range(10)], members=2)
    good = p.read_bytes()
    torn = gzip.compress(b"".join(b"1790000000000,1.0,1,,,,,%d\n" % i for i in range(50)))
    p.write_bytes(good + torn[:15])                    # a crash mid-flush: the member's first bytes
    header, rows = A.read_rows(p)
    assert len(rows) == 10


def test_massive_rows_fill_only_stretches_no_broker_tick_covers():
    broker = [tick(i, ts=S + 60_000 + i * 100) for i in range(10)]          # S+60.0 s .. S+60.9 s
    old = [massive(S, 1), massive(S + 57_000, 2),      # 3 s and more from any broker tick: kept
           massive(S + 60_450, 3),                     # the same trade as a broker tick: dropped
           massive(S + 62_800, 4)]                     # 1.9 s after the last broker tick: dropped
    m = A.merge([("history", broker), ("archive", old)])
    kept = [r for r in m.rows if A.is_massive(r)]
    assert [r[A.ID] for r in kept] == ["1", "2"] and m.stats["massive_dropped_near_broker"] == 2
    new = [massive(S, 1), massive(S + 30_000, 9), massive(S + 60_010, 10)]
    m = A.merge([("history", broker), ("archive", old)], massive_new=new)
    assert [r[A.ID] for r in m.rows if A.is_massive(r)] == ["1", "9", "2"]
    assert (m.stats["massive_added"], m.stats["massive_already_on_file"],
            m.stats["massive_skipped_near_broker"]) == (1, 1, 1)


def test_a_file_with_massive_rows_keeps_their_ns_stamps(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    man = merge_session(path, fetched=[tick(100)], fetched_source={"kind": "history"},
                        massive_new=[massive(S, 5)], massive_source={"kind": "massive", "file": "x"})
    with gzip.open(path, "rt") as f:
        got = list(csv.DictReader(f))
    assert list(got[0]) == list(A.COLS)
    assert got[0]["ts_ns"] == str(S * 1_000_000 + 7) and got[1]["ts_ns"] == ""
    assert man["massive_rows"] == 1 and not man["bid_ask"] and man["source"] == "desk"
    assert man["sources"][-1]["rows_added"] == 1


def test_a_legacy_manifest_becomes_the_first_entry_of_the_merge_log(tmp_path):
    """A nightly file from before merges were logged paged back from the close
    until the broker ran dry: it vouches for everything from its first tick on."""
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(3)])
    A.manifest_path(path).write_text(json.dumps({
        "ticks": 3, "complete": False, "pages": 7, "session_end_utc": END.astimezone(A.UTC).isoformat(),
        "first_tick_utc": A.iso_ms(S), "recorded_at_utc": "2026-09-26T10:12:12+00:00"}))
    man = merge_session(path, fetched=[tick(3)], fetched_source={"kind": "history", "pages": 1})
    assert man["sources"][0] == {"kind": "history", "stop": "legacy", "to_utc": END.astimezone(A.UTC).isoformat(),
                                 "earliest_ms": S, "ticks": 3, "pages": 7,
                                 "at_utc": "2026-09-26T10:12:12+00:00"}
    assert man["pages"] == 8 and man["ticks"] == 4
    assert A.verified_spans(man["sources"]) == [(S, int(END.timestamp() * 1000))]
    assert T.segment_state(man, *T.utc_segments(START, END)[1]) == (True, None)


# ------------------------------------------------------------------ hour-by-hour coverage (item C)
def minute_rows(date, minutes, ids=None):
    """A broker tick at each minute offset from the session open; ids default to the offsets."""
    start, _ = T.session_bounds(date)
    s = int(start.timestamp() * 1000)
    ids = ids if ids is not None else list(minutes)
    return [A.row_of({"ts_ms": s + m * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
                      "id": 1 + i}) for m, i in zip(minutes, ids)]


def cov(rows, date=DAY, root="NQ", sources=()):
    start, end = T.session_bounds(date)
    return A.coverage(rows, root=root, date=date, start=start, end=end, sources=list(sources))


def test_a_full_session_is_complete_hour_by_hour():
    c = cov(minute_rows(DAY, range(23 * 60)))
    assert c["complete"] and c["expected_hours"] == 23 == c["hours_with_ticks"] and c["holes"] == []


def test_an_empty_hour_is_quiet_when_the_ids_run_on_and_a_hole_when_they_skip():
    kept = [m for m in range(23 * 60) if not 8 * 60 <= m < 9 * 60]      # 02:00-03:00 ET: no tick
    quiet = cov(minute_rows(DAY, kept, ids=list(range(len(kept)))))     # ids consecutive across it
    assert quiet["complete"] and quiet["quiet_hours"] == 1 and quiet["holes"] == []
    lost = cov(minute_rows(DAY, kept))                                  # 60 ids skipped across it
    assert not lost["complete"] and lost["missing_ids"] == 60
    assert [(h["from_et"], h["to_et"], h["at"]) for h in lost["holes"]] == [("02:00", "03:00", "inside")]


def test_the_brokers_window_edge_is_a_hole_at_the_open():
    c = cov(minute_rows(DAY, range(120, 23 * 60)))       # a nightly file from 20:00 ET on
    assert not c["complete"] and not c["head_ok"] and c["tail_ok"] and c["missing_ids"] == 0
    assert c["holes"] == [{"from_et": "18:00", "to_et": "20:00", "hours": 2.0, "at": "open",
                           "start_utc": "2026-09-27T22:00:00+00:00", "end_utc": "2026-09-28T00:00:00+00:00"}]
    assert c["hole_hours"] == 2.0


def test_a_history_fetch_that_went_past_a_quiet_first_hour_proves_it_quiet():
    kept = list(range(70, 23 * 60))                      # a thin market: first trade 19:10 ET
    head = {"kind": "history", "stop": "reached", "from_utc": START.astimezone(A.UTC).isoformat(),
            "to_utc": "2026-09-28T00:00:00+00:00", "earliest_ms": S - 60_000}
    tail = {"kind": "history", "stop": "exhausted", "from_utc": "2026-09-28T00:00:00+00:00",
            "to_utc": END.astimezone(A.UTC).isoformat(), "earliest_ms": S + 120 * 60_000}
    c = cov(minute_rows(DAY, kept, ids=list(range(len(kept)))), sources=[head, tail])
    assert c["complete"] and c["quiet_hours"] == 1 and c["head_ok"]
    assert not cov(minute_rows(DAY, kept, ids=list(range(len(kept)))))["complete"]   # unproven: a hole


def test_massive_rows_in_a_gap_stand_in_for_the_skipped_ids():
    rows = minute_rows(DAY, [m for m in range(23 * 60) if not 200 <= m < 400])    # ids 200-399 lost
    gap = cov(rows)
    assert gap["missing_ids"] == 200 and gap["hole_hours"] == 2.0            # 21:20-00:40: two whole hours
    fill = [massive(S + m * 60_000 + 30_000, 7000 + m) for m in range(200, 400)]
    c = cov(sorted(rows + fill, key=A.sort_key))
    assert c["missing_ids"] == 0 and c["holes"] == [] and c["complete"]


def test_the_equity_half_day_ends_at_1315_other_roots_are_flagged_not_guessed():
    fri = dt.date(2026, 11, 27)                          # the day after Thanksgiving (EST)
    until_1315 = range(0, 19 * 60 + 15)                  # 18:00 ET Thu -> 13:14 ET Fri
    nq = cov(minute_rows(fri, until_1315), date=fri, root="NQ")
    assert nq["complete"] and nq["early_close_et"] == "13:15" and nq["expected_hours"] == 20
    gc = cov(minute_rows(fri, until_1315), date=fri, root="GC")
    assert not gc["complete"] and gc["early_close_et"] is None
    assert [(h["from_et"], h["to_et"], h["at"]) for h in gc["holes"]] == [("14:00", "17:00", "close")]


def test_a_live_files_out_of_order_refill_is_sorted_first():
    rows = minute_rows(DAY, range(23 * 60))
    assert cov(rows[600:] + rows[:600])["complete"]      # a refill appended the older rows last


def test_the_manifest_complete_is_the_coverages(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    man = merge_session(path, fetched=minute_rows(DAY, range(120, 23 * 60)),
                        fetched_source={"kind": "history", "stop": "exhausted"})
    assert not man["complete"] and man["coverage"]["holes"][0]["at"] == "open"
    write_live(A.live_path(path), minute_rows(DAY, range(0, 130)))
    man = merge_session(path)
    assert man["complete"] and man["coverage"]["hole_hours"] == 0
