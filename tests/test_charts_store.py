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
