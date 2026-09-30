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
    assert man["merge"]["only_in"] == {"live": 20, "history": 26}   # 0-19 / 100-119 + 40-45
    assert man["merge"]["quotes_filled"] == 7                  # 23, 33, 53 ... 93 from the fetch
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


def test_a_tick_id_that_changes_between_sources_keeps_the_version_on_disk(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    write_live(A.live_path(path), [tick(1, price=20001.0)])
    man = merge_session(path, fetched=[tick(1, price=20000.0)], fetched_source={"kind": "history"})
    assert man["merge"]["id_conflicts"] == 1 and man["merge"]["conflict_ids"] == [1001]
    assert A.read_rows(path)[1][0][A.PX] == "20001.0"          # the live recording, already written
    merge_session(path, fetched=[tick(1, price=19999.0)], fetched_source={"kind": "history"})
    assert A.read_rows(path)[1][0][A.PX] == "20001.0"          # the archive's, once merged


def test_more_than_five_conflicting_ids_refuse_the_merge(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(10)], fetched_source={"kind": "history"})
    merge_session(path, fetched=[tick(i, price=1.0) if i < 5 else tick(i) for i in range(10)],
                  fetched_source={"kind": "history"})             # five: kept, counted
    kept = sha(path)
    with pytest.raises(A.MergeRefused, match="6 tick ids disagree"):
        merge_session(path, fetched=[tick(i, price=1.0) if i < 6 else tick(i) for i in range(10)],
                      fetched_source={"kind": "history"})
    assert sha(path) == kept


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
    broker = [tick(i, ts=S + 60_000 + i * 100) for i in range(10)]          # S+60.0 s .. S+60.9 s, ids run on
    old = [massive(S, 1), massive(S + 57_000, 2),      # before the broker's first tick, > 500 ms off: kept
           massive(S + 60_450, 3),                     # between consecutive ids: the broker has it: dropped
           massive(S + 60_950, 5),                     # 50 ms after the last broker tick: its edge: dropped
           massive(S + 62_800, 4)]                     # 1.9 s after it: nothing says the broker has it: kept
    m = A.merge([("history", broker), ("archive", old)])
    kept = [r for r in m.rows if A.is_massive(r)]
    assert [r[A.ID] for r in kept] == ["1", "2", "4"] and m.stats["massive_dropped_near_broker"] == 2
    new = [massive(S, 1), massive(S + 30_000, 9), massive(S + 60_010, 10)]
    m = A.merge([("history", broker), ("archive", old)], massive_new=new)
    assert [r[A.ID] for r in m.rows if A.is_massive(r)] == ["1", "9", "2", "4"]
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
    assert A.covers(A.verified_spans(man["sources"]), S + 60_000, int(END.timestamp() * 1000))


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
    assert c["missing_ids"] == 0 and c["holes"] == []
    assert c["massive_edge_ms"] == 1000 and not c["complete"]      # its two edges: unknown, said


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


def test_a_fetch_log_never_hides_ids_that_skip():
    """A 'reached' fetch vouches for its stretch, but where ticks stand on both
    sides of an empty hour their ids decide: 60 skipped ids are a hole."""
    kept = [m for m in range(23 * 60) if not 8 * 60 <= m < 9 * 60]
    whole = {"kind": "history", "stop": "reached", "from_utc": START.astimezone(A.UTC).isoformat(),
             "to_utc": END.astimezone(A.UTC).isoformat(), "earliest_ms": S - 60_000}
    c = cov(minute_rows(DAY, kept), sources=[whole])
    assert c["missing_ids"] == 60 and [h["from_et"] for h in c["holes"]] == ["02:00"]


def test_the_same_trades_under_other_ids_refuse_the_merge():
    """Review 3: rows identical in time, price, size and quote but under disjoint
    ids used to merge into a double count."""
    rows = [tick(i) for i in range(50)]
    other = [r[:A.ID] + (str(90_000 + i),) + ("",) for i, r in enumerate(rows)]
    with pytest.raises(A.MergeRefused, match="50 ticks appear under different ids"):
        A.merge([("history", rows), ("live", other)])
    m = A.merge([("history", rows[:5]), ("live", other[:5])])
    assert m.stats["id_twins"] == 5                               # a handful: kept, counted


def test_the_twin_guard_scales_with_seams():
    """2026-09-29 review: a fixed ID_SPACE_REFUSED=5 refused real busy-hour merges that were
    filling several holes at once (roughly one false twin per seam). `seams` raises the limit to
    max(ID_SPACE_REFUSED, seams * 2)."""
    rows = [tick(i) for i in range(8)]
    other = [r[:A.ID] + (str(90_000 + i),) + ("",) for i, r in enumerate(rows)]
    with pytest.raises(A.MergeRefused, match="8 ticks appear under different ids"):
        A.merge([("history", rows), ("live", other)])                      # seams=1 (default): max(5,2)=5, 8>5
    with pytest.raises(A.MergeRefused):
        A.merge([("history", rows), ("live", other)], seams=3)             # max(5,6)=6, 8>6
    m = A.merge([("history", rows), ("live", other)], seams=4)             # max(5,8)=8, 8 is not > 8
    assert m.stats["id_twins"] == 8


def test_merge_session_passes_seams_through_to_the_twin_guard(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    rows = [tick(i) for i in range(8)]
    other = [r[:A.ID] + (str(90_000 + i),) + ("",) for i, r in enumerate(rows)]
    assert A.merge_session(path, root="NQ", contract="NQZ6", date=DAY, start=START, end=END,
                           fetched=rows, fetched_source={"kind": "history"}) is not None
    with pytest.raises(A.MergeRefused):
        A.merge_session(path, root="NQ", contract="NQZ6", date=DAY, start=START, end=END,
                        fetched=other, fetched_source={"kind": "history"})   # default seams=1
    man = A.merge_session(path, root="NQ", contract="NQZ6", date=DAY, start=START, end=END,
                          fetched=other, fetched_source={"kind": "history"}, seams=4)
    assert man is not None and man["merge"]["id_twins"] == 8


def test_inside_an_id_gap_only_its_two_edge_ticks_are_guarded():
    """Review 4: a 500 s gap (1000 ids) in a tick-every-500 ms tape, Massive every
    100 ms inside. Rows within 500 ms of the gap's edge ticks are dropped (they
    may be those very trades); every other row lands; the edges stay unknown."""
    br, i, t, hole = [], 1, S, (S + 36_000_000, S + 36_500_000)
    while t < S + 40_000_000:
        if not hole[0] < t < hole[1]:
            br.append(tick(0, ts=t)[:A.ID] + (str(i), ""))
        i, t = i + 1, t + 500
    mv = [massive(x, 7) for x in range(hole[0] + 50, hole[1], 100)]
    m = A.merge([("history", br)], mv)
    added = [int(r[A.TS]) for r in m.rows if A.is_massive(r)]
    assert min(added) - hole[0] > 500 and hole[1] - max(added) > 500
    assert m.stats["massive_added"] == len(mv) - 10               # 5 at each edge
    c = cov(m.rows, sources=[{"kind": "history", "stop": "reached", "from_utc": A.iso_ms(S),
                              "to_utc": A.iso_ms(S + 40_000_000)}])
    assert c["missing_ids"] == 0 and c["massive_edge_ms"] == 1000 and not c["complete"]


def test_an_archive_that_does_not_read_whole_is_never_merged_over(tmp_path):
    """Review 6: the archive was read leniently (a torn tail dropped), so a cut
    file would have been rewritten short."""
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(2000)], fetched_source={"kind": "history"})
    data = path.read_bytes()
    path.write_bytes(data[:len(data) // 2])                       # cut mid-stream
    cut = sha(path)
    with pytest.raises(A.MergeRefused, match="does not read whole"):
        merge_session(path, fetched=[tick(3000)], fetched_source={"kind": "history"})
    assert sha(path) == cut


def test_fewer_rows_than_the_manifest_counts_refuse_the_merge(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    man = merge_session(path, fetched=[tick(i) for i in range(10)], fetched_source={"kind": "history"})
    A.write_manifest(path, {**man, "ticks": 12})                  # the file lost two somewhere
    kept = sha(path)
    with pytest.raises(A.MergeRefused, match="10 rows read back, its manifest says 12"):
        merge_session(path, fetched=[tick(20)], fetched_source={"kind": "history"})
    assert sha(path) == kept


def test_a_size_that_differs_at_the_same_id_time_and_price_is_counted_not_refused(tmp_path):
    """GC 2026-09-29: the live stream said 2 lots where the history said 1, at the same
    id, ms and price, on ~5% of ticks -- 50 of them refused a whole hour's repair."""
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    write_live(A.live_path(path), [tick(i) for i in range(400)])
    resized = [A.row_of({"ts_ms": int(r[A.TS]), "price": float(r[A.PX]), "size": int(r[A.SZ]) + 1,
                         "bid": r[A.BID], "ask": r[A.ASK], "bid_size": r[A.BIDSZ], "ask_size": r[A.ASKSZ],
                         "id": int(r[A.ID])}) if i % 20 == 0 else r
               for i, r in enumerate(tick(i) for i in range(400))]       # 20 of 400: 5%
    man = merge_session(path, fetched=resized + [tick(i) for i in range(400, 410)],
                        fetched_source={"kind": "history"})
    assert man["merge"]["size_disagreements"] == 20 and man["merge"]["id_conflicts"] == 0
    assert man["ticks"] == 410                                        # the new ids landed
    by_id = {int(r[A.ID]): r for r in A.read_rows(path)[1]}
    assert by_id[1000][A.SZ] == tick(0)[A.SZ]                         # on disk wins, as for any disagreement


def test_sizes_that_disagree_wholesale_refuse_the_merge(tmp_path):
    path = T.archive_path("NQ", DAY, "NQZ6", tmp_path)
    merge_session(path, fetched=[tick(i) for i in range(300)], fetched_source={"kind": "history"})
    kept = sha(path)
    doubled = [A.row_of({"ts_ms": int(r[A.TS]), "price": float(r[A.PX]), "size": int(r[A.SZ]) * 2,
                         "bid": r[A.BID], "ask": r[A.ASK], "bid_size": r[A.BIDSZ], "ask_size": r[A.ASKSZ],
                         "id": int(r[A.ID])}) for r in (tick(i) for i in range(300))]
    with pytest.raises(A.MergeRefused, match="different size"):
        merge_session(path, fetched=doubled, fetched_source={"kind": "history"})
    assert sha(path) == kept
