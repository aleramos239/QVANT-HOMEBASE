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
