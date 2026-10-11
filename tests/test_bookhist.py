import gzip, json, datetime as dt
from pathlib import Path
from homebase.charts import bookhist as bh

TICK = 0.25
D = dt.date(2026, 10, 7)
T0 = int(dt.datetime(2026, 10, 7, 14, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 10:00 ET

def levels(bid, big=None):
    big = big or {}
    b = [[bid - i * TICK, big.get(('b', i), 10)] for i in range(10)]
    a = [[bid + TICK + i * TICK, big.get(('a', i), 10)] for i in range(10)]
    return b, a

def write_depth(base: Path, lines):
    p = base / "NQ" / "2026" / f"{D.isoformat()}_NQZ6.depth.jsonl.gz"
    p.parent.mkdir(parents=True)
    body = "".join(json.dumps({"t": t, "b": b, "a": a}) + "\n" for t, b, a in lines)
    p.write_bytes(gzip.compress(body.encode()))
    return p

def write_ticks(base: Path, rows):
    p = base / "NQ" / "2026" / f"{D.isoformat()}_NQZ6.csv.gz"
    p.parent.mkdir(parents=True)
    body = "ts_ms,price,size,bid,ask,id\n" + "".join(f"{t},{px},{sz},{bid},{ask},{i}\n" for i, (t, px, sz, bid, ask) in enumerate(rows, 1))
    p.write_bytes(gzip.compress(body.encode()))

def scenario(tmp_path):
    lines = []
    for s in range(60):
        big = {('b', 2): 300} if 20 <= s < 30 else None
        lines.append((T0 + s * 1000, *levels(100.0, big)))
    write_depth(tmp_path / "depth", lines)
    # sellers hit the 99.50 bid (the big level, 300 shown) at 25 s: 640 contracts over 4 prints
    ticks = [(T0 + 25_000 + k * 100, 99.5, 160, 99.5, 99.75) for k in range(4)]
    write_ticks(tmp_path / "ticks", ticks)
    return tmp_path / "depth", tmp_path / "ticks"

def test_window_has_samples_and_the_episode_with_its_trades(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000))
    assert len(out["samples"]) == 60 and out["step"] == 1000
    ep = [e for e in out["episodes"] if e["p"] == 99.5]
    assert len(ep) == 1 and ep[0]["s"] == "b" and ep[0]["tr"] == 640 and ep[0]["end"] == "traded"
    assert ep[0]["ab"] is not None            # 640 traded >= 2 x the 300 shown, level still stands at flag time

def test_window_cuts_samples_and_keeps_overlapping_episodes(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0 + 40_000, T0 + 50_000, T0 + 3_600_000))
    assert len(out["samples"]) == 10
    assert out["episodes"] == []              # the episode ended at 30 s, before this window

def test_far_future_is_clamped_to_now(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0, T0 + 10 * 3_600_000, T0 + 30_000))
    assert out["t1"] == T0 + 30_000 and len(out["samples"]) == 30

def test_paused_window_refuses_to_decode(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, quiet=lambda: "paused for the 9:30 window", tick_of=lambda r: TICK)
    try:
        h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000)
    except bh.Paused as e:
        assert "9:30" in str(e)
    else:
        raise AssertionError("expected Paused")

def test_average_buckets():
    rows = [[0, 10, 20, .1, .1, .1, 100.0, 1], [1000, 30, 40, .3, .3, .3, 102.0, 3], [2000, 50, 60, 0, 0, 0, None, None]]
    out = bh._average(rows, 2000)
    assert out[0] == [0, 20.0, 30.0, 0.2, 0.2, 0.2, 101.0, 2.0]
    assert out[1] == [2000, 50.0, 60.0, 0.0, 0.0, 0.0, None, None]


# ---- fix round 1

def _old_replay_day(lines, ticks, tick_size, finished):
    """The list-based merge this module had before it streamed (the reference for the equality test)."""
    from homebase.charts.bookflow import BookTracker
    tr, samples, eps = BookTracker(tick_size), [], {}

    def take(evs):
        for e in evs:
            if e["k"] == "sample":
                samples.append(e["row"])
            else:
                eps[e["id"]] = {k: v for k, v in e.items() if k != "k"}

    i = j = 0
    n, m = len(lines), len(ticks)
    while i < n or j < m:
        if j >= m or (i < n and lines[i][0] <= ticks[j].ts_ms):
            t, b, a = lines[i]
            i += 1
            take(tr.on_book(t, b, a))
        else:
            tk = ticks[j]
            j += 1
            take(tr.on_print(tk.ts_ms, tk.price, tk.size, tk.side))
    take(tr.finish() if finished else tr.flush(10 ** 18))
    return samples, eps


def test_paused_refuses_even_from_the_cache_and_for_a_root_with_no_files(tmp_path):
    d, t = scenario(tmp_path)
    state = {"why": None}
    h = bh.BookHistory(d, t, quiet=lambda: state["why"], tick_of=lambda r: TICK)
    assert len(json.loads(h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000))["samples"]) == 60   # warms the cache
    state["why"] = "paused for the 9:30 window"
    for root in ("NQ", "ES"):
        try:
            h.window(root, T0, T0 + 60_000, T0 + 3_600_000)
        except bh.Paused as e:
            assert "9:30" in str(e)
        else:
            raise AssertionError(f"expected Paused for {root}")


def test_nothing_in_the_answer_is_later_than_to(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    to = T0 + 22_000
    out = json.loads(h.window("NQ", T0, T0 + 60_000, to))
    assert out["t1"] == to and all(r[0] < to for r in out["samples"])
    ep = [e for e in out["episodes"] if e["p"] == 99.5]
    assert len(ep) == 1 and ep[0]["t0"] < to
    assert ep[0]["t1"] is None and ep[0]["end"] == "open" and ep[0]["ab"] is None
    for e in out["episodes"]:
        assert e["t1"] is None or e["t1"] <= to
        assert e["ab"] is None or e["ab"] <= to
    # a window that reaches past the end of the episode still reports it as it ended
    full = json.loads(h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000))
    done = [e for e in full["episodes"] if e["p"] == 99.5][0]
    assert done["t1"] is not None and done["end"] == "traded" and done["ab"] is not None


def test_streamed_replay_is_the_same_as_the_list_merge(tmp_path):
    from homebase.charts.store import TickStore
    d, t = scenario(tmp_path)
    path = next((d / "NQ" / "2026").glob("*.depth.jsonl.gz"))
    lines = list(bh.depth_lines(path))
    assert len(lines) == 60 and lines == sorted(lines, key=lambda x: x[0])
    ticks = TickStore(t).load("NQ", D).ticks
    assert len(ticks) == 4 and ticks[0].ts_ms == lines[25][0]      # a print on a book line's own stamp
    for finished in (True, False):
        assert bh.replay_day(iter(lines), ticks, TICK, finished) == _old_replay_day(lines, ticks, TICK, finished)
    assert bh.replay_day(bh.depth_lines(path), ticks, TICK, True)[1]       # and from the generator itself


def test_depth_lines_puts_a_stray_older_line_back_and_drops_a_far_late_one(tmp_path):
    b, a = levels(100.0)
    rows = [(T0 + s * 1000, b, a) for s in range(10)]
    stray = (T0 + 3_500, b, a)                              # 5 s late: back in its place
    far = (T0 + 1_000, b, a)                                # 2 min late by the time it shows: dropped
    seq = rows[:9] + [stray] + [(T0 + 130_000, b, a), far]
    p = write_depth(tmp_path, seq)
    got = [x[0] for x in bh.depth_lines(p)]
    assert got == sorted(x[0] for x in seq if x is not far)
