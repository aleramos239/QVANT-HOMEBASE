"""The burst detector + reaction log (spec `docs/superpowers/specs/2026-09-27-charts-news-design.md`,
Part A #2/#3): the rule's edges (4x, 8 ticks, refractory, the 20-minute
warm-up), news<->burst linking, the reaction math at +10s/+1m/+5m including
no-print -> null, and storage + retention. Pure cores: no network, no
fastapi app."""
from __future__ import annotations

import datetime as dt
import json

from homebase.charts.bursts import (RATIO_MIN, REACTION_MARKS, TICKS_MIN, WARMUP_MS, WINDOW_MS, BurstBook,
                                     BurstDetector, ReactionBook, ReactionTracker, configured_roots, near_news,
                                     prune_old)

MIN = 60_000


def feed_baseline(det: BurstDetector, move_ticks: float, tick_size: float, n_buckets: int = 45,
                  start_ms: int = 0, base_price: float = 1000.0):
    """`n_buckets` quiet 30 s windows (two ticks each, `move_ticks` apart):
    enough history (>= 20 minutes at 45 x 30 s) for a stable median of
    `move_ticks`. Returns (next_free_ts_ms, last_price) -- push a spike
    starting >= 30 s after next_free_ts_ms so its own window is clean."""
    price = base_price
    ts = start_ms
    for _ in range(n_buckets):
        det.push(ts, price)
        price += move_ticks * tick_size
        det.push(ts + WINDOW_MS - 1000, price)
        ts += WINDOW_MS
    return ts, price


def test_no_burst_before_20_minutes_of_history_however_big_the_move():
    det = BurstDetector(tick_size=1.0)
    ts = 0
    for _ in range(3):                          # a few quiet buckets, well under WARMUP_MS
        det.push(ts, 1000.0)
        ts += WINDOW_MS
    fired = det.push(ts, 1000.0 + 100)          # a huge, instant spike -- still too early to judge
    assert fired is None
    assert ts < WARMUP_MS


def test_fires_at_4x_the_trailing_median_and_at_least_8_ticks():
    det = BurstDetector(tick_size=1.0)
    next_ts, price = feed_baseline(det, move_ticks=2.0, tick_size=1.0)
    spike_start = next_ts + WINDOW_MS           # a clean gap: the baseline's last tick falls out of the window
    assert det.push(spike_start, price) is None                    # one point alone: no window yet
    fired = det.push(spike_start + 29_000, price + 40.0)            # 40-tick move, median is 2 -> ratio 20
    assert fired is not None
    assert fired["dir"] == "up" and fired["move_ticks"] == 40.0 and fired["ratio"] == 20.0
    assert fired["from_px"] == price and fired["to_px"] == price + 40.0
    assert fired["t_ms"] == spike_start + 29_000


def test_dir_is_down_when_price_falls():
    det = BurstDetector(tick_size=1.0)
    next_ts, price = feed_baseline(det, move_ticks=2.0, tick_size=1.0)
    spike_start = next_ts + WINDOW_MS
    det.push(spike_start, price)
    fired = det.push(spike_start + 29_000, price - 40.0)
    assert fired["dir"] == "down" and fired["move_ticks"] == 40.0


def test_ratio_must_reach_4x_independent_of_the_tick_floor():
    # median 3 ticks: the ratio floor (4x -> 12 ticks) is well above the 8-tick floor
    det = BurstDetector(tick_size=1.0)
    next_ts, price = feed_baseline(det, move_ticks=3.0, tick_size=1.0)
    spike_start = next_ts + WINDOW_MS
    det.push(spike_start, price)
    assert det.push(spike_start + 29_000, price + 11.9) is None     # ratio 3.97x: just short
    det2 = BurstDetector(tick_size=1.0)
    next_ts2, price2 = feed_baseline(det2, move_ticks=3.0, tick_size=1.0)
    spike_start2 = next_ts2 + WINDOW_MS
    det2.push(spike_start2, price2)
    fired = det2.push(spike_start2 + 29_000, price2 + 12.0)          # ratio exactly 4.0x: fires
    assert fired is not None and fired["ratio"] == 4.0


def test_the_8_tick_floor_applies_even_when_the_ratio_is_far_over_4x():
    # median 0.5 ticks: a 7.9-tick move is already a 15.8x ratio, but still under the 8-tick floor
    det = BurstDetector(tick_size=1.0)
    next_ts, price = feed_baseline(det, move_ticks=0.5, tick_size=1.0)
    spike_start = next_ts + WINDOW_MS
    det.push(spike_start, price)
    assert det.push(spike_start + 29_000, price + 7.9) is None
    det2 = BurstDetector(tick_size=1.0)
    next_ts2, price2 = feed_baseline(det2, move_ticks=0.5, tick_size=1.0)
    spike_start2 = next_ts2 + WINDOW_MS
    det2.push(spike_start2, price2)
    fired = det2.push(spike_start2 + 29_000, price2 + 8.0)
    assert fired is not None and fired["move_ticks"] == 8.0


def test_refractory_period_holds_a_root_quiet_for_120s_after_firing():
    det = BurstDetector(tick_size=1.0)
    next_ts, price = feed_baseline(det, move_ticks=2.0, tick_size=1.0)
    spike_start = next_ts + WINDOW_MS
    det.push(spike_start, price)
    first = det.push(spike_start + 29_000, price + 40.0)
    assert first is not None
    again_ts = spike_start + 29_000 + WINDOW_MS + 1000       # a fresh, clean window, still inside the 120s hold
    assert again_ts - first["t_ms"] < 120_000
    det.push(again_ts, price + 40.0)
    blocked = det.push(again_ts + 29_000, price + 90.0)      # an even bigger spike: still refused
    assert blocked is None
    later_ts = first["t_ms"] + 120_000 + WINDOW_MS + 1000    # past the 120s hold, another clean window
    det.push(later_ts, price + 90.0)
    fired_again = det.push(later_ts + 29_000, price + 140.0)
    assert fired_again is not None


def test_configured_roots_reads_the_env_or_falls_back_to_default():
    assert configured_roots("") == configured_roots(None)
    assert configured_roots("nq, es , gc") == ("NQ", "ES", "GC")


def test_near_news_links_by_t_ms_or_seen_ms_within_3_minutes():
    burst = {"t_ms": 1_000_000}
    items = [
        {"id": "a", "t_ms": 1_000_000 - 3 * MIN, "seen_ms": 1_000_000 - 3 * MIN},        # exactly at the edge
        {"id": "b", "t_ms": 1_000_000 - 3 * MIN - 1, "seen_ms": 1_000_000 + MIN},        # t_ms too far, seen_ms in
        {"id": "c", "t_ms": 1_000_000 + 10 * MIN, "seen_ms": 1_000_000 + 10 * MIN},       # nowhere near
        {"id": "d", "t_ms": 1_000_000 + 2 * MIN, "seen_ms": 1_000_000 + 2 * MIN},
    ]
    got = [it["id"] for it in near_news(burst, items)]
    assert got == ["b", "a", "d"]                           # earliest t_ms first, "c" excluded


def news_item(t_ms: int, seen_ms=None, **kw) -> dict:
    return {"id": kw.get("id", f"n{t_ms}"), "source": "financialjuice", "title": kw.get("title", "headline"),
            "tags": kw.get("tags", []), "t_ms": t_ms, "seen_ms": seen_ms if seen_ms is not None else t_ms}


def test_reaction_tracker_measures_moves_at_10s_1m_5m_and_waits_for_the_5m_mark():
    tick_size_of = {"NQ": 0.25, "ES": 0.25, "GC": 0.1, "CL": 0.01, "BTC": 5.0}.get
    tr = ReactionTracker(tick_size_of)
    t0 = 10_000_000
    tr.add_item(news_item(t0, seen_ms=t0 + 1500))
    for root, base in (("NQ", 20000.0), ("ES", 6000.0), ("GC", 3800.0), ("CL", 70.0), ("BTC", 90000.0)):
        tr.push_tick(root, t0 - 500, base)                  # the baseline print, just before t_ms
        tr.push_tick(root, t0 + 10_000, base + 1.0)
        tr.push_tick(root, t0 + 60_000, base + 2.0)
        tr.push_tick(root, t0 + 300_000, base + 4.0)
    assert tr.due(t0 + 299_999) == []                        # not yet: the 5m mark hasn't passed
    recs = tr.due(t0 + 300_000)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["t_ms"] == t0 and rec["delay_s"] == 1.5
    nq = rec["roots"]["NQ"]
    assert nq["m10s"] == {"pts": 1.0, "ticks": 4.0}
    assert nq["m1m"] == {"pts": 2.0, "ticks": 8.0}
    assert nq["m5m"] == {"pts": 4.0, "ticks": 16.0}
    gc = rec["roots"]["GC"]
    assert gc["m10s"]["ticks"] == 10.0                       # 1.0 pt / 0.1 tick size


def test_a_root_with_no_prints_before_t_ms_gets_null_marks_even_if_it_prints_later():
    """"A root with no prints in the window gets null" (spec): the baseline
    (the last print at or before t_ms) is what a mark's move is measured
    from, so a root that never printed before t_ms is null across the board
    -- even if it goes on to print well before some of the later marks."""
    tick_size_of = {"NQ": 0.25, "GC": 0.1}.get
    tr = ReactionTracker(tick_size_of)
    t0 = 0
    tr.add_item(news_item(t0))
    tr.push_tick("NQ", t0 - 100, 100.0)
    tr.push_tick("NQ", t0 + 10_000, 101.0)
    tr.push_tick("GC", t0 + 5_000, 3800.0)      # GC's first print is AFTER t_ms: no usable baseline
    rec = tr.due(t0 + 300_000)[0]
    assert rec["roots"]["GC"] == {"m10s": None, "m1m": None, "m5m": None}
    assert rec["roots"]["NQ"]["m10s"] == {"pts": 1.0, "ticks": 4.0}


def test_reaction_uses_the_last_print_at_or_before_each_mark_not_after():
    tick_size_of = {"NQ": 0.25}.get
    tr = ReactionTracker(tick_size_of)
    t0 = 0
    tr.add_item(news_item(t0))
    tr.push_tick("NQ", t0 - 1, 100.0)
    tr.push_tick("NQ", t0 + 5_000, 100.5)     # before +10s: this is the +10s reading
    tr.push_tick("NQ", t0 + 10_001, 999.0)    # just AFTER +10s: must not count for m10s
    rec = tr.due(t0 + 300_000)[0]
    assert rec["roots"]["NQ"]["m10s"] == {"pts": 0.5, "ticks": 2.0}


def test_burstbook_stores_bursts_linked_to_news_and_tracks_last_per_root():
    tick_size_of = {"NQ": 1.0}.get
    day = dt.date(2026, 9, 26)
    day_start = int(dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)

    def folder_book(folder):
        return BurstBook(folder, ["NQ"], tick_size_of)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        book = folder_book(tmp)
        assert book.status() == {"roots": ["NQ"], "last": {"NQ": None}}
        next_ts, price = feed_baseline(BurstDetector(1.0), 2.0, 1.0)   # just to compute a matching ts range
        # feed the same baseline directly through the book so its detector warms up
        book2 = folder_book(tmp)
        ts = day_start
        p = 1000.0
        for _ in range(45):
            book2.push("NQ", ts, p, [])
            p += 2.0
            book2.push("NQ", ts + WINDOW_MS - 1000, p, [])
            ts += WINDOW_MS
        spike_start = ts + WINDOW_MS
        news_items = [news_item(spike_start + 29_000, title="Trump: strike")]
        book2.push("NQ", spike_start, p, news_items)
        fired = book2.push("NQ", spike_start + 29_000, p + 40.0, news_items)
        assert fired is not None
        assert fired["root"] == "NQ" and len(fired["near_news"]) == 1
        assert book2.status()["last"]["NQ"]["move_ticks"] == 40.0
        stored = (list(__import__("pathlib").Path(tmp).glob("bursts-*.jsonl")))
        assert len(stored) == 1
        lines = [json.loads(l) for l in stored[0].read_text().splitlines()]
        assert len(lines) == 1 and lines[0]["root"] == "NQ"


def test_reactionbook_writes_reactions_and_prunes_by_retention():
    tick_size_of = {"NQ": 0.25}.get
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        rb = ReactionBook(tmp, tick_size_of, retention_days=90)
        t0 = int(dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
        rb.add_item(news_item(t0))
        rb.push_tick("NQ", t0 - 100, 100.0)
        rb.push_tick("NQ", t0 + 10_000, 101.0)
        recs = rb.flush_due(t0 + 300_000)
        assert len(recs) == 1
        p = list(__import__("pathlib").Path(tmp).glob("reactions-*.jsonl"))
        assert len(p) == 1


def test_prune_old_deletes_files_past_retention_by_their_date_suffix():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        old = folder / "bursts-2020-01-01.jsonl"
        recent = folder / "bursts-2026-09-20.jsonl"
        old.write_text("{}\n")
        recent.write_text("{}\n")
        now_ms = int(dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc).timestamp() * 1000)
        prune_old(folder, "bursts", now_ms, retention_days=90)
        assert not old.exists() and recent.exists()
