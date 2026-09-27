"""The liquidity heatmap's history (2026-09-27 charts-l2-news-ui plan, Task 3):
/api/depth/history reads the recorded depth files into a down-sampled grid.
Synthetic files in tmp dirs only: nothing here reads or writes ~/futures_depth."""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import threading

import pytest
from fastapi.testclient import TestClient

from homebase.charts import depthgrid
from homebase.charts.depthgrid import BIN_MS, HOLD_MS, MAX_COLS, MAX_SPAN_MS, DepthHistory, Paused
from tests.charts_util import D, session_ms
from homebase.charts.server import create_app
from tests.test_charts_desk_server import QuietFeed

T0 = session_ms(D, 10, 0)             # 10:00 ET on session D: well outside the 09:20-09:35 window
NQ_TICK = 0.25
BASE_URL = "http://127.0.0.1:8852"


def line(t, bids, asks) -> bytes:
    return (json.dumps({"t": t, "b": bids, "a": asks}, separators=(",", ":")) + "\n").encode()


def write_depth(base, members, root="NQ", date=D, contract="NQZ6", torn=b""):
    """One gzip member per list of lines (one per recorder flush); `torn` appended raw (a crash mid-flush)."""
    p = base / root / str(date.year) / f"{date.isoformat()}_{contract}.depth.jsonl.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "ab") as fh:
        for m in members:
            fh.write(gzip.compress(b"".join(m)))
        fh.write(torn)
    return p


def hist(base, **kw):
    return DepthHistory(base, lambda root: NQ_TICK, **kw)


def app_at(tmp_path, now_ms):
    return create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=QuietFeed, now_ms=lambda: now_ms,
                      state=tmp_path / "state", depth_base=tmp_path / "depth")


def grid(h, frm, to, cols, root="NQ", now_ms=None):
    return json.loads(h.grid(root, frm, to, cols, now_ms=now_ms))


def cells_at(g, t_idx):
    """{price: size} of column t_idx."""
    lo = g["prices"][0]
    return {lo + i * g["tick"]: s for c, i, s in g["cells"] if c == t_idx}


# ------------------------------------------------------------------ the grid

def test_each_column_shows_the_book_in_force_at_its_end(tmp_path):
    write_depth(tmp_path, [[
        line(T0, [[100.0, 5], [99.75, 2]], [[100.25, 7]]),
        line(T0 + 1500, [[100.0, 9]], [[100.25, 1], [100.5, 3]]),
    ]])
    g = grid(hist(tmp_path), T0, T0 + 4000, 4)
    assert g["t0"] == T0 and g["dt_ms"] == 1000 and g["tick"] == NQ_TICK
    assert g["prices"] == [99.75, 100.5]
    assert cells_at(g, 0) == {100.0: 5, 99.75: 2, 100.25: 7}          # the first book, until T0+1500
    assert cells_at(g, 1) == {100.0: 9, 100.25: 1, 100.5: 3}          # the second one ...
    assert cells_at(g, 2) == cells_at(g, 1) == cells_at(g, 3)         # ... held while nothing changed
    assert all(isinstance(v, int) for c in g["cells"] for v in c)     # [t_idx, price_idx, size], all ints


def test_the_column_count_is_capped_and_never_finer_than_a_second(tmp_path):
    write_depth(tmp_path, [[line(T0, [[100.0, 1]], [[100.25, 1]])]])
    h = hist(tmp_path)
    g = grid(h, T0, T0 + 3_600_000, 5000)                             # cols over the 600 cap
    assert g["dt_ms"] == 3_600_000 // MAX_COLS
    assert max(c for c, _, _ in g["cells"]) < MAX_COLS
    g = grid(h, T0, T0 + 10_000, 600)                                 # 10 s: one column a second, not 600
    assert g["dt_ms"] == BIN_MS
    assert max(c for c, _, _ in g["cells"]) == 9


def test_a_book_is_held_at_most_hold_ms(tmp_path):
    write_depth(tmp_path, [[line(T0, [[100.0, 4]], [[100.25, 4]])]])
    step = 60_000
    g = grid(hist(tmp_path), T0, T0 + 10 * step, 10)
    cols = sorted({c for c, _, _ in g["cells"]})
    assert cols == [c for c in range(10) if (c + 1) * step <= HOLD_MS] == [0, 1, 2, 3, 4]   # a gap stays blank


# ------------------------------------------------------------------ the file

def test_a_torn_tail_loses_only_the_last_flush(tmp_path):
    good = [[line(T0, [[100.0, 5]], [[100.25, 5]])], [line(T0 + 1000, [[100.0, 6]], [[100.25, 6]])]]
    torn = gzip.compress(line(T0 + 2000, [[100.0, 99]], [[100.25, 99]]))[:-7]
    write_depth(tmp_path, good, torn=torn)
    g = grid(hist(tmp_path), T0, T0 + 3000, 3)
    assert cells_at(g, 0) == {100.0: 5, 100.25: 5}
    assert cells_at(g, 1) == cells_at(g, 2) == {100.0: 6, 100.25: 6}  # the torn 99s never appear


def test_a_file_of_nothing_but_garbage_is_an_empty_grid(tmp_path):
    write_depth(tmp_path, [], torn=b"not gzip at all")
    g = grid(hist(tmp_path), T0, T0 + 3000, 3)
    assert g["cells"] == [] and g["prices"] is None


def test_malformed_lines_and_levels_are_skipped(tmp_path):
    write_depth(tmp_path, [[b"{not json\n", b"[1,2]\n", line(T0, [[100.0, 5], ["x", 1], [99.0, 0], [98.0]], [[100.25, 2]])]])
    g = grid(hist(tmp_path), T0, T0 + 1000, 1)
    assert cells_at(g, 0) == {100.0: 5, 100.25: 2}


def test_a_root_with_no_files_is_an_empty_grid(tmp_path):
    g = grid(hist(tmp_path), T0, T0 + 60_000, 60, root="ES")
    assert g == {"t0": T0, "dt_ms": 1000, "tick": NQ_TICK, "prices": None, "cells": []}


# ------------------------------------------------------------------ range clipping

def test_only_the_asked_range_is_read_and_never_past_now(tmp_path):
    write_depth(tmp_path, [[
        line(T0 - 10_000, [[90.0, 1]], [[90.25, 1]]),                    # long before: superseded
        line(T0 - 500, [[100.0, 2]], [[100.25, 2]]),                     # the book in force at `from`
        line(T0 + 5000, [[200.0, 3]], [[200.25, 3]]),                    # after `to`
    ]])
    h = hist(tmp_path)
    g = grid(h, T0, T0 + 3000, 3)
    assert {c for c, _, _ in g["cells"]} == {0, 1, 2}
    assert g["prices"] == [100.0, 100.25]                             # neither 90 nor 200 anywhere
    g = grid(h, T0, T0 + 10_000, 10, now_ms=T0 + 2000)                # to clipped to now
    assert max(c for c, _, _ in g["cells"]) == 1
    g = grid(h, T0, T0 + 10_000, 10, now_ms=T0 - 1)                   # a range wholly in the future
    assert g["cells"] == []


def test_a_range_across_two_sessions_reads_both_files(tmp_path):
    prev = D - dt.timedelta(days=1)
    frm = session_ms(prev, 16, 59)                                    # the last minute of session D-1
    write_depth(tmp_path, [[line(frm, [[50.0, 1]], [[50.25, 1]])]], date=prev)
    write_depth(tmp_path, [[line(session_ms(D, 18, 0), [[60.0, 2]], [[60.25, 2]])]])  # 18:00 opens session D
    g = grid(hist(tmp_path), frm, frm + 3 * 3_600_000, 180)
    prices = {g["prices"][0] + i * g["tick"] for _, i, _ in g["cells"]}
    assert prices == {50.0, 50.25, 60.0, 60.25}


def test_a_span_over_the_cap_or_a_bad_range_is_refused(tmp_path):
    h = hist(tmp_path)
    with pytest.raises(ValueError):
        h.grid("NQ", T0, T0 + MAX_SPAN_MS + 1, 100)
    with pytest.raises(ValueError):
        h.grid("NQ", T0, T0, 100)
    with pytest.raises(ValueError):
        h.grid("../NQ", T0, T0 + 1000, 1)


# ------------------------------------------------------------------ the size cap

def test_the_response_is_capped_keeping_the_largest_levels(tmp_path, monkeypatch):
    lines = []
    for k in range(20):
        bids = [[1000.0 - i * NQ_TICK, i + 1] for i in range(200)]     # the deepest level is the largest
        lines.append(line(T0 + k * 1000, bids, [[1000.25, 1]]))
    write_depth(tmp_path, [lines])
    full = hist(tmp_path).grid("NQ", T0, T0 + 20_000, 20)
    monkeypatch.setattr(depthgrid, "MAX_BYTES", len(full) // 3)
    body = hist(tmp_path).grid("NQ", T0, T0 + 20_000, 20)
    assert len(body) <= len(full) // 3
    g = json.loads(body)
    assert g["cells"] and len({c for c, _, _ in g["cells"]}) == 20      # every column kept ...
    col0 = cells_at(g, 0)
    assert max(col0.values()) == 200 and min(col0.values()) > 1         # ... with its largest levels


# ------------------------------------------------------------------ the cache

def test_decoded_files_are_cached_and_appended_flushes_read_incrementally(tmp_path, monkeypatch):
    p = write_depth(tmp_path, [[line(T0, [[100.0, 1]], [[100.25, 1]])]])
    parsed = []
    real = depthgrid._parse_member
    monkeypatch.setattr(depthgrid, "_parse_member", lambda raw: parsed.append(raw) or real(raw))
    h = hist(tmp_path)
    grid(h, T0, T0 + 2000, 2)
    grid(h, T0, T0 + 2000, 2)
    assert len(parsed) == 1                                           # (path, mtime, size) unchanged: cached
    write_depth(tmp_path, [[line(T0 + 1000, [[100.0, 8]], [[100.25, 8]])]])
    g = grid(h, T0, T0 + 2000, 2)
    assert len(parsed) == 2                                           # only the new member was decoded
    assert cells_at(g, 1) == {100.0: 8, 100.25: 8}
    # a rewritten file (the recorder's torn-tail repair: a new inode) is decoded again from the start
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(p.read_bytes())
    os.replace(tmp, p)
    grid(h, T0, T0 + 2000, 2)
    assert len(parsed) == 4


def test_the_quiet_window_pauses_every_decode(tmp_path):
    write_depth(tmp_path, [[line(T0, [[100.0, 1]], [[100.25, 1]])]])
    h = hist(tmp_path, quiet=lambda: True)
    with pytest.raises(Paused):
        h.grid("NQ", T0, T0 + 1000, 1)


def test_one_decode_at_a_time(tmp_path):
    write_depth(tmp_path, [[line(T0, [[100.0, 1]], [[100.25, 1]])]])
    h = hist(tmp_path)
    inside, peak, lock = [0], [0], threading.Lock()
    real = h._load

    def load(*a):
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        try:
            return real(*a)
        finally:
            with lock:
                inside[0] -= 1

    h._load = load
    ts = [threading.Thread(target=h.grid, args=("NQ", T0, T0 + 1000, 1)) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak[0] == 1


# ------------------------------------------------------------------ the route

def test_the_route_serves_the_grid_behind_the_host_guard(tmp_path):
    write_depth(tmp_path / "depth", [[line(T0, [[100.0, 5]], [[100.25, 7]])]])
    app = app_at(tmp_path, T0 + 60_000)
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/depth/history", params={"root": "nq", "from_ms": T0, "to_ms": T0 + 2000, "cols": 2})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
        g = r.json()
        assert g["prices"] == [100.0, 100.25] and len(g["cells"]) == 4
        assert c.get("/api/depth/history", params={"root": "NQ", "from_ms": T0, "to_ms": T0 + 2000},
                     headers={"host": "evil.example"}).status_code == 403
        assert c.get("/api/depth/history", params={"root": "ZZ", "from_ms": T0, "to_ms": T0 + 1}).status_code == 404
        for bad in ({"root": "NQ"}, {"root": "NQ", "from_ms": "x", "to_ms": T0},
                    {"root": "NQ", "from_ms": T0, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0 - MAX_SPAN_MS - 1, "to_ms": T0}):
            assert c.get("/api/depth/history", params=bad).status_code == 400, bad


def test_the_route_answers_503_in_the_930_window(tmp_path):
    write_depth(tmp_path / "depth", [[line(T0, [[100.0, 5]], [[100.25, 7]])]])
    app = app_at(tmp_path, session_ms(D, 9, 25))
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/depth/history", params={"root": "NQ", "from_ms": T0 - 3_600_000, "to_ms": T0})
        assert r.status_code == 503 and r.json()["detail"] == "paused for the 9:30 window"
