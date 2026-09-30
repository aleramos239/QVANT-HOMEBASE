"""Tick store: multi-member/torn gzip, one file per session, live re-sort."""
from __future__ import annotations

import datetime as dt
import gzip

from homebase.charts.store import TickStore, gaps_path, read_table
from tests.charts_util import D, rows, session_ms, write_archive, write_gz


def test_read_table_survives_multi_member_and_a_torn_tail(tmp_path):
    p = tmp_path / "x.csv.gz"
    p.write_bytes(gzip.compress(b"ts_ms,price\n1,10\n") + gzip.compress(b"2,11\n")
                  + gzip.compress(b"3,12\n4,13\n")[:-9])
    header, recs = read_table(p)
    assert header == ["ts_ms", "price"]
    assert recs[:2] == [["1", "10"], ["2", "11"]]
    assert all(len(r) == 2 for r in recs)


def test_pick_prefers_complete_archive_then_live_then_partial(tmp_path):
    r = rows(session_ms(D, 18, 0), [100.0, 100.25])
    write_archive(tmp_path, "NQ", D, "NQZ6", r, complete=False)
    st = TickStore(tmp_path)
    assert st.pick("NQ", D).live is False
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", r)
    assert st.pick("NQ", D).live is True
    write_archive(tmp_path, "NQ", D, "NQZ6", r, complete=True)
    f = st.pick("NQ", D)
    assert f.live is False and f.complete


def test_roll_day_picks_the_busiest_contract(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQU6", rows(session_ms(D, 9, 30), [1.0, 2.0]))
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0] * 5))
    assert TickStore(tmp_path).pick("NQ", D).contract == "NQZ6"


def test_a_front_month_with_an_honest_hole_never_loses_to_a_complete_back_month(tmp_path):
    """The archive's `complete` now checks every hour (a Massive front month with
    13:00-15:00 missing says so): the busiest contract is still the session's."""
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0] * 50), complete=False)
    write_archive(tmp_path, "NQ", D, "NQH7", rows(session_ms(D, 9, 30), [1.0] * 3), complete=True)
    f = TickStore(tmp_path).pick("NQ", D)
    assert f.contract == "NQZ6" and not f.live and not f.complete
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", rows(session_ms(D, 9, 30), [1.0] * 50))
    f = TickStore(tmp_path).pick("NQ", D)
    assert f.contract == "NQZ6" and f.live                  # its live file beats its partial archive


def test_a_contract_only_the_live_recorder_has_ranks_after_an_archived_one(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0] * 2), complete=True)
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQH7.live.csv.gz", rows(session_ms(D, 9, 30), [1.0] * 90))
    assert TickStore(tmp_path).pick("NQ", D).contract == "NQZ6"
    write_gz(tmp_path / "ES" / "2026" / f"{D}_ESZ6.live.csv.gz", rows(session_ms(D, 9, 30), [1.0] * 2))
    assert TickStore(tmp_path).pick("ES", D).live             # nothing archived: the live file


def test_load_live_sorts_dedupes_and_reads_gaps(tmp_path):
    r = rows(session_ms(D, 9, 30), [100.0, 100.25, 100.5])
    live = write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", [r[2], r[0], r[1], r[0]])
    gaps_path(live).write_text("[[1, 2]]")
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3]
    assert s.source == "live" and s.bid_ask and s.gaps == [[1, 2]] and s.contract == "NQZ6"


def test_massive_file_without_quotes_is_flagged(tmp_path):
    r = rows(session_ms(D, 9, 30), [100.0, 100.25, 100.0])
    for x in r:
        x["bid"] = x["ask"] = ""
    write_archive(tmp_path, "NQ", D, "NQZ6", r, bid_ask=False)
    st = TickStore(tmp_path)
    s = st.load("NQ", D)
    assert s.bid_ask is False and s.source == "archive" and s.gaps == []
    assert [t.side for t in s.ticks] == [1, 1, -1]          # tick rule
    assert st.pick("NQ", D).bid_ask is False


def test_sessions_lists_every_dated_file(tmp_path):
    p = D - dt.timedelta(days=1)
    write_archive(tmp_path, "NQ", p, "NQZ6", rows(session_ms(p, 9, 30), [1.0]))
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", rows(session_ms(D, 9, 30), [1.0]))
    assert TickStore(tmp_path).sessions("NQ") == [p, D]
    assert TickStore(tmp_path).load("ES", D) is None


def test_files_skips_a_dangling_symlink_next_to_a_real_file(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0, 2.0]))
    (tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz").symlink_to(tmp_path / "gone.csv.gz")
    st = TickStore(tmp_path)
    fs = st.files("NQ", D)
    assert len(fs) == 1 and fs[0].live is False and fs[0].contract == "NQZ6"
    f = st.pick("NQ", D)
    assert f is not None and f.live is False and f.complete
    s = st.load("NQ", D)
    assert s is not None and s.source == "archive" and len(s.ticks) == 2


def test_pick_and_load_are_none_when_only_file_is_a_dangling_symlink(tmp_path):
    (tmp_path / "NQ" / "2026").mkdir(parents=True)
    (tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz").symlink_to(tmp_path / "gone.csv.gz")
    st = TickStore(tmp_path)
    assert st.files("NQ", D) == []
    assert st.pick("NQ", D) is None
    assert st.load("NQ", D) is None


def test_the_desk_and_the_backfill_spelling_of_one_contract_are_one_contract(tmp_path):
    """Review nit: NGX6 (desk) and NGX26 (Massive) are the same November 2026 contract."""
    write_archive(tmp_path, "NG", D, "NGX26", rows(session_ms(D, 9, 30), [1.0] * 30), complete=False)
    write_archive(tmp_path, "NG", D, "NGX6", rows(session_ms(D, 9, 30), [1.0] * 20), complete=True)
    write_archive(tmp_path, "NG", D, "NGZ6", rows(session_ms(D, 9, 30), [1.0] * 25), complete=True)
    f = TickStore(tmp_path).pick("NG", D)
    assert f.contract == "NGX6" and f.complete          # X6/X26 (30 ticks) beats Z6 (25); its complete file


# ---- live + incomplete archive = one union (the repair job fills what a dead Mac never recorded) ----
from homebase.charts.store import splice_tail  # noqa: E402
from homebase.charts.tick import Tick  # noqa: E402


def _live(tmp_path, r, root="NQ", contract="NQZ6"):
    return write_gz(tmp_path / root / "2026" / f"{D}_{contract}.live.csv.gz", r)


def test_live_plus_incomplete_archive_loads_as_their_deduped_union(tmp_path):
    night = rows(session_ms(D, 1, 0), [100.0 + 0.25 * i for i in range(20)], step_ms=60_000, first_id=1)
    morning = rows(session_ms(D, 9, 30), [110.0 + 0.25 * i for i in range(20)], first_id=100)
    # the repair job fetched the night AND overlapped the first 5 morning ticks; the live file has only the morning
    write_archive(tmp_path, "NQ", D, "NQZ6", night + morning[:5], complete=False)
    _live(tmp_path, morning)
    st = TickStore(tmp_path)
    f = st.pick("NQ", D)
    assert f.live and f.merge_with is not None
    s = st.load("NQ", D)
    assert s.source == "live" and s.contract == "NQZ6"
    assert [t.id for t in s.ticks] == list(range(1, 21)) + list(range(100, 120))
    assert len({t.id for t in s.ticks}) == len(s.ticks) == 40
    assert [t.ts_ms for t in s.ticks] == sorted(t.ts_ms for t in s.ticks)


def test_a_shared_id_keeps_the_live_version(tmp_path):
    a = rows(session_ms(D, 9, 30), [100.0, 101.0], first_id=1)
    b = rows(session_ms(D, 9, 30), [100.0, 101.25], first_id=1)
    a[0].update(bid="", ask="")
    write_archive(tmp_path, "NQ", D, "NQZ6", a, complete=False)
    _live(tmp_path, b)
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.price for t in s.ticks] == [100.0, 101.25] and s.bid_ask


def test_an_id_less_archive_row_is_added_only_where_live_has_nothing_near(tmp_path):
    arch = rows(session_ms(D, 9, 30), [1.0, 2.0, 3.0], step_ms=10_000, first_id=1)
    for r in arch:
        r["id"] = ""
    write_archive(tmp_path, "NQ", D, "NQZ6", arch, complete=False)
    _live(tmp_path, rows(session_ms(D, 9, 30), [7.0], first_id=50))          # live has a tick at +0s only
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.price for t in s.ticks] == [7.0, 2.0, 3.0]


def test_a_complete_archive_wins_alone(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0, 2.0, 3.0], first_id=1), complete=True)
    _live(tmp_path, rows(session_ms(D, 9, 31), [9.0, 9.5], first_id=50))
    st = TickStore(tmp_path)
    f = st.pick("NQ", D)
    assert not f.live and f.complete and f.merge_with is None
    s = st.load("NQ", D)
    assert s.source == "archive" and [t.price for t in s.ticks] == [1.0, 2.0, 3.0]


def test_live_alone_and_incomplete_archive_alone_load_as_before(tmp_path):
    _live(tmp_path, rows(session_ms(D, 9, 30), [1.0, 2.0], first_id=1), root="NQ")
    write_archive(tmp_path, "ES", D, "ESZ6", rows(session_ms(D, 9, 30), [5.0], first_id=1), complete=False)
    st = TickStore(tmp_path)
    assert st.pick("NQ", D).merge_with is None and len(st.load("NQ", D).ticks) == 2
    assert st.pick("ES", D).merge_with is None and st.load("ES", D).source == "archive"


def test_an_archive_update_is_picked_up_and_the_union_is_cached_until_then(tmp_path):
    morning = rows(session_ms(D, 9, 30), [110.0, 110.25], first_id=100)
    arch = write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 1, 0), [100.0], first_id=1), complete=False)
    _live(tmp_path, morning)
    st = TickStore(tmp_path)
    before = st.archive_stamp("NQ", D)
    s1 = st.load("NQ", D)
    assert len(s1.ticks) == 3
    parsed = []
    import homebase.charts.store as mod
    real = mod.read_table
    mod.read_table = lambda p: parsed.append(p.name) or real(p)
    try:
        st.load("NQ", D)
        assert parsed == [f"{D}_NQZ6.live.csv.gz"]              # unchanged archive: only the live side is read again
        write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", morning + rows(session_ms(D, 9, 31), [1.0], first_id=300))
        parsed.clear()
        assert len(st.load("NQ", D).ticks) == 4 and parsed == [f"{D}_NQZ6.live.csv.gz"]
    finally:
        mod.read_table = real
    # the hourly repair lands more ticks (an atomic replace, as tickarchive does)
    write_gz(arch, rows(session_ms(D, 1, 0), [100.0, 100.25, 100.5, 100.75], first_id=1))
    assert st.archive_stamp("NQ", D) != before
    s2 = st.load("NQ", D)
    assert len(s2.ticks) == 7


def test_load_writes_nothing(tmp_path):
    arch = write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 1, 0), [100.0, 100.25], first_id=1),
                         complete=False)
    live = _live(tmp_path, rows(session_ms(D, 9, 30), [110.0], first_id=100))
    snap = lambda: {p: (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes())  # noqa: E731
                    for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    before = snap()
    st = TickStore(tmp_path)
    st.load("NQ", D)
    st.load("NQ", D)
    st.archive_stamp("NQ", D)
    assert snap() == before and arch.exists() and live.exists()


def test_an_archive_in_another_id_space_never_overrides_the_live_file(tmp_path):
    # the same ids with different trades everywhere: the live version of every shared id stays
    a = rows(session_ms(D, 9, 30), [100.0 + i for i in range(10)], first_id=1)
    b = rows(session_ms(D, 9, 30), [500.0 + i for i in range(10)], first_id=1)
    write_archive(tmp_path, "NQ", D, "NQZ6", a, complete=False)
    _live(tmp_path, b)
    st = TickStore(tmp_path)
    s = st.load("NQ", D)
    assert [t.price for t in s.ticks] == [500.0 + i for i in range(10)]


def test_splice_tail_keeps_only_what_the_files_lack():
    T = lambda ts, i, p=1.0: Tick(ts, p, 1, 1, i)  # noqa: E731
    loaded = [T(1000, 1), T(2000, 2), T(3000, 3)]
    tape = [T(1000, 1), T(2000, 2), T(3000, 3), T(3500, 4), T(3000, 0, 7.0)]
    out = splice_tail(loaded, tape, 2000)
    assert [(t.ts_ms, t.id) for t in out] == [(1000, 1), (2000, 2), (3000, 0), (3000, 3), (3500, 4)]
    assert splice_tail(loaded, tape[:3], 2000) is loaded
