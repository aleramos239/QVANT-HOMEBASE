"""Data export (homebase.charts.export): coverage/availability helpers, row shaping (candle
aggregation at bar boundaries, RTH filter, timezones, the front-month roll, level 1/2 formats),
validation, output naming, and the job manager (a real child process; cancel; one at a time; the
09:20-09:35 ET quiet window). Every archive/depth/out dir is a tmp_path: nothing here reads or
writes ~/futures_ticks, ~/futures_depth or a real ~/Downloads."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from homebase.charts import export as E
from homebase.charts.session import ET
from homebase.charts.store import TickStore, gaps_path, read_table, ticks_from_table
from tests.charts_util import D, rows, session_ms, write_archive, write_gz

D2 = D + dt.timedelta(days=1)             # the next session (a Friday, D is a Thursday)
SAT = D + dt.timedelta(days=2)


# --------------------------------------------------------------------------------------- helpers

def depth_line(t, bids, asks) -> bytes:
    return (json.dumps({"t": t, "b": bids, "a": asks}, separators=(",", ":")) + "\n").encode()


def write_depth(base: Path, root: str, d: dt.date, contract: str, lines: list[bytes]) -> Path:
    p = base / root / str(d.year) / f"{d.isoformat()}_{contract}.depth.jsonl.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(b"".join(lines)))
    return p


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as fh:
        r = csv.reader(fh)
        header = next(r)
        return header, list(r)


# ------------------------------------------------------------------------------- expected_sessions

def test_expected_sessions_skips_weekends_for_a_classic_root():
    got = E.expected_sessions("NQ", D, SAT)                 # Thu, Fri, Sat
    assert got == [D, D2]


def test_expected_sessions_includes_every_day_for_a_247_root():
    got = E.expected_sessions("BTC", D, SAT)
    assert got == [D, D2, SAT]


def test_expected_sessions_handles_a_reversed_range():
    assert E.expected_sessions("NQ", D2, D) == [D, D2]


# ------------------------------------------------------------------------------ archive discovery

def test_list_contracts_and_tick_range(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQU6", rows(session_ms(D, 9, 30), [1.0]))
    write_archive(tmp_path, "NQ", D2, "NQZ6", rows(session_ms(D2, 9, 30), [1.0]))
    st = TickStore(tmp_path)
    assert E.list_contracts(st, "NQ") == ["NQU6", "NQZ6"]
    assert E.tick_range(st, "NQ") == (D.isoformat(), D2.isoformat())
    assert E.tick_range(st, "ES") is None


def test_quotes_range_stops_at_the_first_non_quote_session_walking_back(tmp_path):
    """Massive backfill (no bid/ask) on D, a desk recording (bid/ask) on D2: quotes_range must
    report only D2, and must not scan the whole archive to find that."""
    r = rows(session_ms(D, 9, 30), [1.0, 2.0])
    for x in r:
        x["bid"] = x["ask"] = ""
    write_archive(tmp_path, "NQ", D, "NQU6", r, bid_ask=False)
    write_archive(tmp_path, "NQ", D2, "NQZ6", rows(session_ms(D2, 9, 30), [1.0]), bid_ask=True)
    st = TickStore(tmp_path)
    assert E.quotes_range(st, "NQ") == (D2.isoformat(), D2.isoformat())
    assert E.quotes_range(st, "ES") is None


def test_depth_sessions_and_range(tmp_path):
    write_depth(tmp_path, "NQ", D, "NQU6", [depth_line(session_ms(D, 9, 30), [[100.0, 1]], [[100.25, 1]])])
    write_depth(tmp_path, "NQ", D2, "NQZ6", [depth_line(session_ms(D2, 9, 30), [[101.0, 1]], [[101.25, 1]])])
    assert E.depth_sessions(tmp_path, "NQ") == [D, D2]
    assert E.depth_range(tmp_path, "NQ") == (D.isoformat(), D2.isoformat())
    assert E.depth_range(tmp_path, "ES") is None


def test_depth_file_picks_the_busiest_contract_on_a_roll_day_not_the_alphabetically_last(tmp_path):
    """A roll day can list both the outgoing and incoming contract's depth file (NQU6 rolls to
    NQZ6 -- 'Z' sorts after 'U', so the old alphabetically-last bug always picked NQZ6 even on a
    day NQU6 was still the one actually subscribed and busy)."""
    t0 = session_ms(D, 9, 30)
    busy = [depth_line(t0 + i * 1000, [[100.0 + i, 1]], [[100.25 + i, 1]]) for i in range(50)]
    write_depth(tmp_path, "NQ", D, "NQU6", busy)                                     # busy: still the front month
    write_depth(tmp_path, "NQ", D, "NQZ6", [depth_line(t0, [[200.0, 1]], [[200.25, 1]])])   # thin: barely subscribed
    got = E.depth_file(tmp_path, "NQ", D)
    assert got.name.startswith(f"{D.isoformat()}_NQU6")
    rows = list(E.iter_level2(tmp_path, "NQ", D, 1, E.TsFmt("et", "epoch", False)))
    assert len(rows) == 50 and rows[0][1] == 100.0   # the busy contract's own rows, not the thin one's


# ---------------------------------------------------------------------------- missing / gaps

def test_missing_ticks_and_missing_depth(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQU6", rows(session_ms(D, 9, 30), [1.0]))
    st = TickStore(tmp_path)
    assert E.missing_ticks(st, "NQ", [D, D2]) == [D2.isoformat()]
    assert E.missing_ticks(st, "NQ", [D, D2], contract="NQZ6") == [D.isoformat(), D2.isoformat()]
    write_depth(tmp_path, "NQ", D, "NQU6", [depth_line(session_ms(D, 9, 30), [[1, 1]], [[2, 1]])])
    assert E.missing_depth(tmp_path, "NQ", [D, D2]) == [D2.isoformat()]


def test_session_gaps_reads_the_live_sidecar_cheaply(tmp_path):
    live = write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQU6.live.csv.gz", rows(session_ms(D, 9, 30), [1.0, 2.0]))
    gaps_path(live).write_text(json.dumps([[1, 2]]))
    write_archive(tmp_path, "NQ", D2, "NQU6", rows(session_ms(D2, 9, 30), [1.0]))   # archive-complete: no gaps file
    st = TickStore(tmp_path)
    got = E.session_gaps(st, "NQ", [D, D2])
    assert got == {D.isoformat(): [[1, 2]]}


# ------------------------------------------------------------------------------------- TsFmt / RTH

def test_tsfmt_et_utc_and_epoch():
    ms = session_ms(D, 9, 30, 0)
    assert E.TsFmt("et", "iso", False).fmt(ms) == dt.datetime.fromtimestamp(ms / 1000, ET).isoformat(timespec="milliseconds")
    assert E.TsFmt("utc", "iso", False).fmt(ms) == dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="milliseconds")
    assert E.TsFmt("et", "epoch", False).fmt(ms) == ms


def test_rth_boundary_is_0930_inclusive_1600_exclusive_et():
    assert E._in_rth(session_ms(D, 9, 29, 59)) is False
    assert E._in_rth(session_ms(D, 9, 30, 0)) is True
    assert E._in_rth(session_ms(D, 15, 59, 59)) is True
    assert E._in_rth(session_ms(D, 16, 0, 0)) is False


# --------------------------------------------------------------------------------- candle boundaries

def test_candle_aggregation_at_a_minute_boundary_and_session_close_flush(tmp_path):
    """Two ticks share the 09:30 minute, a third starts 09:31: the chart's own BarBuilder must
    close exactly at the boundary, and the session's last (developing) bar is flushed as closed
    too (history.py's own rule -- the session is over, there is no "later" for it)."""
    t0 = session_ms(D, 9, 30, 0)
    r = [{"ts_ms": t0, "price": 100.0, "size": 1, "bid": "", "ask": "", "bid_size": "", "ask_size": "", "id": 1},
        {"ts_ms": t0 + 59_000, "price": 100.5, "size": 2, "bid": "", "ask": "", "bid_size": "", "ask_size": "", "id": 2},
        {"ts_ms": t0 + 60_000, "price": 101.0, "size": 3, "bid": "", "ask": "", "bid_size": "", "ask_size": "", "id": 3}]
    write_archive(tmp_path, "NQ", D, "NQZ6", r, bid_ask=False)
    st = TickStore(tmp_path)
    spec = E.BarSpec("time", 60)
    ts = E.TsFmt("et", "epoch", False)
    got = list(E.iter_candles(st, "NQ", D, "front", spec, ts))
    assert got == [
        (t0, 100.0, 100.5, 100.0, 100.5, 3),          # 09:30:00 + 09:30:59 -- closed by the 09:31 tick
        (t0 + 60_000, 101.0, 101.0, 101.0, 101.0, 3),  # 09:31:00 -- the session ends here, so it counts as closed
    ]


def test_candle_rth_filter_drops_bars_starting_before_0930_or_at_1600(tmp_path):
    pre = session_ms(D, 9, 29, 0)      # a 1-minute bar starting before the open
    mid = session_ms(D, 9, 30, 0)
    close = session_ms(D, 16, 0, 0)    # a bar starting exactly at 16:00 -- outside RTH
    r = rows(pre, [1.0]) + rows(mid, [2.0]) + rows(close, [3.0])
    write_archive(tmp_path, "NQ", D, "NQZ6", r)
    st = TickStore(tmp_path)
    ts = E.TsFmt("et", "epoch", True)
    got = list(E.iter_candles(st, "NQ", D, "front", E.BarSpec("time", 60), ts))
    assert [row[0] for row in got] == [mid]


def test_front_month_rolls_per_session_and_an_explicit_contract_stays_pinned(tmp_path):
    """D: NQU6 is busiest (front). D2: NQZ6 is busiest (rolled). "front" tracks the roll;
    an explicit contract stays on its own symbol and reports the OTHER day missing."""
    write_archive(tmp_path, "NQ", D, "NQU6", rows(session_ms(D, 9, 30), [100.0] * 5))
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 31), [200.0]))
    write_archive(tmp_path, "NQ", D2, "NQZ6", rows(session_ms(D2, 9, 30), [300.0] * 5))
    st = TickStore(tmp_path)
    ts = E.TsFmt("et", "epoch", False)
    spec = E.BarSpec("time", 86400)
    front = [row for d in (D, D2) for row in E.iter_candles(st, "NQ", d, "front", spec, ts)]
    assert [round(row[1]) for row in front] == [100, 300]          # D's open from NQU6, D2's from NQZ6
    pinned = [row for d in (D, D2) for row in E.iter_candles(st, "NQ", d, "NQU6", spec, ts)]
    assert [round(row[1]) for row in pinned] == [100]               # D2 has no NQU6 file at all
    assert E.missing_ticks(st, "NQ", [D, D2], contract="NQU6") == [D2.isoformat()]


# ---------------------------------------------------------------- _ordered vs. ticks_from_table

def test_ordered_matches_ticks_from_table(tmp_path):
    """export._ordered() is a hand-rolled copy of store.ticks_from_table's live dedup/sort rule
    (kept separate so it can keep bid_size/ask_size, which ticks_from_table's Tick objects drop --
    see both functions' docstrings). One fixture, fed to both: a duplicate id (a gap refill can
    resend a row) and rows arriving out of time order, exactly what a live file's later flushes
    can produce. If the two ever disagree, this fails -- not a silent mismatch between what an
    export shows and what the live chart / TickStore.load would show for the same session."""
    t0 = session_ms(D, 9, 30)
    recs = (rows(t0, [100.0, 100.25, 100.5], first_id=1)          # ids 1, 2, 3 at t0, t0+1s, t0+2s
            + rows(t0 + 500, [99.0], first_id=2)                    # id 2's RESEND (a gap refill):
            + rows(t0 - 2000, [98.0], first_id=0))                  # id 0: an OLDER row, refilled late
    path = write_gz(tmp_path / "f.live.csv.gz", recs)
    header, raw = read_table(path)

    got_ordered = E._ordered(header, raw, live=True)
    idx = {k: i for i, k in enumerate(header)}
    ordered_ids = [int(r[idx["id"]]) for r in got_ordered]

    ticks, _ = ticks_from_table(header, raw, live=True)
    tick_ids = [t.id for t in ticks]

    # id 2's resend (the later, ts=t0+500ms copy) is dropped -- the FIRST-seen copy (ts=t0+1s)
    # survives; id 0 (ts before everything else) sorts to the front
    assert ordered_ids == tick_ids == [0, 1, 2, 3]
    assert len(got_ordered) == len(ticks) == 4


# ------------------------------------------------------------------------------------- ticks / L1

def test_ticks_carry_bid_ask_sizes_when_recorded_and_blank_otherwise(tmp_path):
    r = rows(session_ms(D, 9, 30), [100.0, 100.25], spread=0.25)
    write_archive(tmp_path, "NQ", D, "NQZ6", r, bid_ask=True)
    st = TickStore(tmp_path)
    got = list(E.iter_ticks(st, "NQ", D, "front", E.TsFmt("et", "epoch", False)))
    assert got[0] == (session_ms(D, 9, 30), 100.0, 1, 99.75, 100.0, 5, 5)

    r2 = rows(session_ms(D2, 9, 30), [50.0])
    for x in r2:
        x["bid"] = x["ask"] = x["bid_size"] = x["ask_size"] = ""
    write_archive(tmp_path, "NQ", D2, "NQZ6", r2, bid_ask=False)
    got2 = list(E.iter_ticks(st, "NQ", D2, "front", E.TsFmt("et", "epoch", False)))
    assert got2[0] == (session_ms(D2, 9, 30), 50.0, 1, "", "", "", "")


def test_level1_skips_a_massive_session_and_a_quote_less_row(tmp_path):
    t0 = session_ms(D, 9, 30)
    r = [{"ts_ms": t0, "price": 100.0, "size": 1, "bid": 99.75, "ask": 100.0, "bid_size": 3, "ask_size": 4, "id": 1},
        {"ts_ms": t0 + 1000, "price": 100.5, "size": 2, "bid": "", "ask": "", "bid_size": "", "ask_size": "", "id": 2}]
    write_archive(tmp_path, "NQ", D, "NQZ6", r, bid_ask=True)
    massive = rows(session_ms(D2, 9, 30), [1.0])
    for x in massive:
        x["bid"] = x["ask"] = ""
    write_archive(tmp_path, "NQ", D2, "NQZ6", massive, bid_ask=False)
    st = TickStore(tmp_path)
    ts = E.TsFmt("et", "epoch", False)
    got = list(E.iter_level1(st, "NQ", D, "front", ts))
    assert got == [(t0, 99.75, 3, 100.0, 4, 100.0, 1)]             # the quote-less second trade is skipped
    assert list(E.iter_level1(st, "NQ", D2, "front", ts)) == []    # Massive backfill: no L1 at all


# ---------------------------------------------------------------------------------------- level 2

def test_level2_flattens_and_pads_missing_levels(tmp_path):
    t0 = session_ms(D, 9, 30)
    write_depth(tmp_path, "NQ", D, "NQZ6", [
        depth_line(t0, [[100.0, 2], [99.75, 3]], [[100.25, 1]]),           # 2 bid levels, 1 ask level
    ])
    ts = E.TsFmt("et", "epoch", False)
    got = list(E.iter_level2(tmp_path, "NQ", D, 3, ts))
    assert got == [(t0, 100.0, 2, 99.75, 3, "", "", 100.25, 1, "", "", "", "")]
    assert E.columns("level2", 3) == ["time", "bid_px_1", "bid_sz_1", "bid_px_2", "bid_sz_2",
                                      "bid_px_3", "bid_sz_3", "ask_px_1", "ask_sz_1",
                                      "ask_px_2", "ask_sz_2", "ask_px_3", "ask_sz_3"]


def test_level2_rth_filter(tmp_path):
    write_depth(tmp_path, "NQ", D, "NQZ6", [
        depth_line(session_ms(D, 9, 0), [[1, 1]], [[2, 1]]),
        depth_line(session_ms(D, 10, 0), [[3, 1]], [[4, 1]]),
    ])
    got = list(E.iter_level2(tmp_path, "NQ", D, 1, E.TsFmt("et", "epoch", True)))
    assert [row[0] for row in got] == [session_ms(D, 10, 0)]


# ----------------------------------------------------------------------------------------- validate

BASE_BODY = {"root": "nq", "type": "candles", "timeframe": "5m", "start": "2026-09-01", "end": "2026-09-02"}


def test_validate_normalizes_a_good_request():
    got = E.validate(BASE_BODY)
    assert got["root"] == "NQ" and got["contract"] == "front" and got["hours"] == "full" and got["format"] == "csv"


@pytest.mark.parametrize("patch,msg_has", [
    ({"root": "XX"}, "root:"),
    ({"type": "level3"}, "Tradovate's feed"),
    ({"type": "bogus"}, "type:"),
    ({"type": "level2", "root": "GC"}, "level 2 is recorded"),
    ({"contract": "n$q"}, "contract:"),
    ({"timeframe": "2m"}, "timeframe:"),
    ({"start": "not-a-date"}, "start:"),
    ({"end": "2026-08-01"}, "end must not be before start"),
    ({"hours": "evening"}, "hours:"),
    ({"tz": "mars"}, "tz:"),
    ({"ts_format": "roman"}, "ts_format:"),
    ({"format": "xlsx"}, "format:"),
])
def test_validate_rejects_bad_input(patch, msg_has):
    body = {**BASE_BODY, **patch}
    with pytest.raises(ValueError, match=msg_has.replace("(", r"\(")):
        E.validate(body)


def test_validate_level2_levels_range():
    body = {"root": "NQ", "type": "level2", "start": "2026-09-01", "end": "2026-09-01", "levels": 0}
    with pytest.raises(ValueError, match="levels:"):
        E.validate(body)
    ok = E.validate({**body, "levels": 5})
    assert ok["levels"] == 5


def test_validate_rejects_a_non_dict_body():
    with pytest.raises(ValueError):
        E.validate(["not", "a", "dict"])


# ------------------------------------------------------------------------------------- output naming

def test_output_name_and_unique_path(tmp_path):
    req = E.validate(BASE_BODY)
    name = E.output_name(req)
    assert name == "NQ_candles_5m_2026-09-01_2026-09-02.csv"
    p1 = E.unique_path(tmp_path, name)
    assert p1 == tmp_path / name
    p1.write_text("x")
    p2 = E.unique_path(tmp_path, name)
    assert p2 == tmp_path / "NQ_candles_5m_2026-09-01_2026-09-02 (2).csv"
    p2.write_text("x")
    assert E.unique_path(tmp_path, name) == tmp_path / "NQ_candles_5m_2026-09-01_2026-09-02 (3).csv"


def test_unique_path_handles_the_double_gz_suffix(tmp_path):
    (tmp_path / "NQ_ticks_2026-09-01_2026-09-01.csv.gz").write_text("x")
    got = E.unique_path(tmp_path, "NQ_ticks_2026-09-01_2026-09-01.csv.gz")
    assert got == tmp_path / "NQ_ticks_2026-09-01_2026-09-01 (2).csv.gz"


# --------------------------------------------------------------------------------------- run_export

def test_run_export_writes_only_the_one_file_and_reads_the_archive_only(tmp_path):
    archive = tmp_path / "ticks"
    write_archive(archive, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0, 100.25]))
    before = sorted(p.relative_to(archive) for p in archive.rglob("*") if p.is_file())

    out_dir = tmp_path / "downloads"
    req = E.validate({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    out_path = out_dir / E.output_name(req)
    seen_progress = []
    result = E.run_export(req, archive, tmp_path / "depth", out_path,
                          on_progress=lambda done, total, rows_: seen_progress.append((done, total, rows_)))

    assert result == {"rows": 2, "sessions_total": 1}
    assert seen_progress == [(1, 1, 2)]
    files = [p for p in out_dir.rglob("*") if p.is_file()]
    assert files == [out_path]                                     # nothing else was written
    header, data = read_rows(out_path)
    assert header == ["time", "price", "size", "bid", "ask", "bid_size", "ask_size"]
    assert len(data) == 2
    after = sorted(p.relative_to(archive) for p in archive.rglob("*") if p.is_file())
    assert before == after                                         # the archive itself is untouched


def test_run_export_gz_round_trips(tmp_path):
    archive = tmp_path / "ticks"
    write_archive(archive, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0]))
    req = E.validate({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat(), "format": "gz"})
    out_path = tmp_path / "out" / E.output_name(req)
    assert out_path.suffix == ".gz"
    E.run_export(req, archive, tmp_path / "depth", out_path)
    header, data = read_rows(out_path)
    assert len(data) == 1 and header[0] == "time"


# ----------------------------------------------------------------------------------- ExportManager

def app_manager(tmp_path, **kw):
    return E.ExportManager(tmp_path / "state", archive=tmp_path / "ticks", depth_base=tmp_path / "depth",
                           out_dir=tmp_path / "downloads", **kw)


def poll(mgr, jid, timeout=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = mgr.status(jid)
        if st.get("status") in E.FINAL:
            return st
        time.sleep(0.05)
    raise AssertionError(f"export {jid} never finished: {mgr.status(jid)}")


def test_export_manager_runs_a_real_child_process_to_done(tmp_path):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0, 100.25, 100.5]))
    mgr = app_manager(tmp_path)
    jid = mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    assert E.JOB_ID_RE.match(jid)
    st = poll(mgr, jid)
    assert st["status"] == "done" and st["rows"] == 3
    result = st["result"]
    p = Path(result["path"])
    assert p.parent == tmp_path / "downloads" and p.is_file()
    assert result["rows"] == 3 and result["bytes"] == p.stat().st_size
    header, data = read_rows(p)
    assert len(data) == 3


def test_export_manager_refuses_a_second_job_while_one_is_active(tmp_path):
    mgr = app_manager(tmp_path)
    mgr._active = ("fake", None)                 # simulate an in-flight job without a real subprocess
    with pytest.raises(ValueError, match="already running"):
        mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})


def test_export_manager_refuses_to_start_in_the_930_quiet_window(tmp_path):
    monday_925 = dt.datetime(2026, 9, 28, 9, 25, tzinfo=ET)
    assert monday_925.weekday() == 0
    mgr = app_manager(tmp_path, clock=lambda: monday_925)
    with pytest.raises(ValueError, match="09:20"):
        mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})


def test_export_manager_cancel_kills_the_child_cleans_the_part_file_and_marks_cancelled(tmp_path):
    """Drives cancel()'s mechanics directly against a real (but otherwise unrelated) child
    process standing in for an in-flight export -- deterministic, unlike racing a real export
    against a timer. The genuine subprocess path is covered end to end by the "runs to done" test
    above; this one is about what cancel() DOES to whatever is running."""
    mgr = app_manager(tmp_path)
    jid = "20260101-000000-deadbeef"
    d = mgr.jobs / jid
    d.mkdir(parents=True)
    tmp_file = tmp_path / "downloads" / "partial.csv.part"
    tmp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file.write_text("half a row")
    E.write_json(d / "status.json", {"id": jid, "status": "running", "phase": "running",
                                     "tmp_path": str(tmp_file), "updated": E._now()})
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    mgr._active = (jid, proc)
    try:
        st = mgr.cancel(jid)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert st["status"] == "cancelled"
    assert proc.poll() is not None                 # actually terminated, not left running
    assert not tmp_file.exists()                    # the half-written file is cleaned up
    assert mgr.status(jid)["status"] == "cancelled"


def test_export_manager_recovers_a_stale_running_job_from_a_dead_pid(tmp_path):
    base = tmp_path / "state"
    d = base / "jobs" / "20260101-000000-deadbeef"
    d.mkdir(parents=True)
    E.write_json(d / "status.json", {"id": d.name, "status": "running", "pid": 999_999_999, "updated": E._now()})
    E.ExportManager(base, archive=tmp_path / "ticks", depth_base=tmp_path / "depth", out_dir=tmp_path / "downloads")
    st = json.loads((d / "status.json").read_text())
    assert st["status"] == "error" and "interrupted" in st["error"]


def test_export_manager_adopts_a_still_alive_job_after_an_unclean_restart(tmp_path):
    """A restart of the chart service does not kill an export child (its own process, no --archive
    tie to the parent's lifetime): the NEW ExportManager instance must pick it back up as _active,
    not just leave it dangling while accepting a second job on top of it."""
    base = tmp_path / "state"
    d = base / "jobs" / "20260101-000000-deadbeef"
    d.mkdir(parents=True)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    # this test process IS proc's real parent (unlike production: there, the chart service that
    # launched an export is the one that restarted, so the export reparents to init and is reaped
    # promptly on its own) -- reap it as soon as it dies, in the background, so _alive() (os.kill)
    # stops seeing a lingering zombie and _AdoptedProc.wait() does not sit out the full timeout.
    reaper = threading.Thread(target=proc.wait, daemon=True)
    reaper.start()
    try:
        E.write_json(d / "status.json", {"id": d.name, "status": "running", "pid": proc.pid, "updated": E._now()})
        mgr = E.ExportManager(base, archive=tmp_path / "ticks", depth_base=tmp_path / "depth",
                              out_dir=tmp_path / "downloads")
        assert mgr._active is not None and mgr._active[0] == d.name
        with pytest.raises(ValueError, match="already running"):
            mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
        st = mgr.cancel(d.name)                 # also proves the adopted stand-in answers terminate()/wait()
        assert st["status"] == "cancelled"
        reaper.join(timeout=5)
        assert not reaper.is_alive(), "cancel() must actually have killed it"
    finally:
        if proc.poll() is None:
            proc.kill()
        reaper.join(timeout=5)


def test_export_manager_reveal_only_offers_that_jobs_own_finished_file(tmp_path):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0]))
    mgr = app_manager(tmp_path)
    jid = mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    with pytest.raises(ValueError, match="no finished file"):
        mgr.reveal(jid)                            # still queued/running
    st = poll(mgr, jid)
    p = mgr.reveal(jid)
    assert str(p) == st["result"]["path"]


def test_export_manager_active_is_empty_with_no_job_ever_submitted(tmp_path):
    assert app_manager(tmp_path).active() == {}


def test_export_manager_active_returns_the_finished_job_after_it_completes(tmp_path):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0]))
    mgr = app_manager(tmp_path)
    jid = mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    poll(mgr, jid)
    got = mgr.active()
    assert got["id"] == jid and got["status"] == "done" and got["rows"] == 1


def test_export_manager_active_prefers_the_running_job_over_an_older_finished_one(tmp_path):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0]))
    mgr = app_manager(tmp_path)
    jid1 = mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    poll(mgr, jid1)
    assert mgr.active()["id"] == jid1
    # simulate a second, still-running job without racing a real one (same trick as the cancel test)
    jid2 = "20260101-000000-deadbeef"
    d = mgr.jobs / jid2
    d.mkdir(parents=True)
    E.write_json(d / "status.json", {"id": jid2, "status": "running", "updated": E._now()})
    mgr._active = (jid2, subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]))
    try:
        got = mgr.active()
        assert got["id"] == jid2 and got["status"] == "running"
    finally:
        mgr._active[1].kill()


def _fake_job_dir(base, n):
    jid = f"202601{(n % 28) + 1:02d}-{n:06d}-{n:08x}"
    d = base / "jobs" / jid
    d.mkdir(parents=True)
    E.write_json(d / "status.json", {"id": jid, "status": "done", "updated": E._now()})
    return jid


def test_prune_keeps_only_the_most_recent_max_jobs_dirs_at_startup(tmp_path):
    base = tmp_path / "state"
    ids = [_fake_job_dir(base, n) for n in range(E.MAX_JOBS + 5)]
    E.ExportManager(base, archive=tmp_path / "ticks", depth_base=tmp_path / "depth", out_dir=tmp_path / "downloads")
    left = sorted(p.name for p in (base / "jobs").iterdir())
    assert len(left) == E.MAX_JOBS
    assert left == sorted(ids)[-E.MAX_JOBS:]    # the oldest 5 are gone, the newest MAX_JOBS remain


def test_prune_runs_after_every_submit_and_never_touches_the_active_job(tmp_path):
    base = tmp_path / "state"
    for n in range(E.MAX_JOBS):   # already at the cap, so the new (active) job pushes out the oldest fake
        _fake_job_dir(base, n)
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0]))
    mgr = E.ExportManager(base, archive=tmp_path / "ticks", depth_base=tmp_path / "depth",
                          out_dir=tmp_path / "downloads")
    jid = mgr.submit({"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()})
    left = {p.name for p in mgr.jobs.iterdir()}
    assert len(left) == E.MAX_JOBS               # one fake pruned to make room for the new one
    assert jid in left                            # the just-submitted (and still active) job always survives
    poll(mgr, jid)
