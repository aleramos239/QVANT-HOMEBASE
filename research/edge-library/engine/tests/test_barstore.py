"""barstore: the bars equal the engine's build_bars, 4h sits on the 18:00 ET grid, load() opens only in-sample months."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

import barstore as B
import l2sim as S


def _tape(d):
    rng = np.random.default_rng(1)
    a = B.session_open_ns(d)
    ts = np.sort(a + rng.integers(0, 23 * 3600 * B.SEC, 5000))
    return ts, 15000 + rng.normal(0, 5, 5000).cumsum(), rng.integers(1, 9, 5000).astype(np.int32)


def test_bars_equal_engine_build_bars():
    ts, px, sz = _tape(dt.date(2024, 3, 12))
    for m in (1, 5, 15, 60):
        want = S.build_bars(ts, px, sz, 0, len(ts), int(ts[0]), int(ts[-1]) + 1, m)
        t, o, h, l, c, v = B.bars(ts, px, sz, B.session_open_ns(dt.date(2024, 3, 12)), m * 60 * B.SEC)
        assert [(b.start_ns, b.o, b.h, b.l, b.c, b.v) for b in want] == list(zip(t, o, h, l, c, v))


def test_4h_on_the_session_open_grid():
    for d in (dt.date(2024, 1, 10), dt.date(2024, 7, 10)):          # EST and EDT both open at 18:00 ET
        ts, px, sz = _tape(d)
        t = B.bars(ts, px, sz, B.session_open_ns(d), B.TFS["4h"])[0]
        hours = {pd.Timestamp(x, tz="UTC").tz_convert("America/New_York").hour for x in t}
        assert hours <= {18, 22, 2, 6, 10, 14}


def test_load_opens_in_sample_months_only(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "BARS", tmp_path)
    (tmp_path / "NQ").mkdir()
    df = pd.DataFrame({"session": ["2021-10-06", "2022-01-05"], "t": [1, 2], "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1})
    df.to_parquet(tmp_path / "NQ" / "5m.parquet", index=False)
    assert B.load("NQ", "5m", fresh=False).session.tolist() == ["2021-10-06"]            # Jan 2022 is a test month
    assert B.load("NQ", "5m", allow=S.ALLOW_WF_OOS, fresh=False).session.tolist() == ["2022-01-05"]
    with pytest.raises(ValueError):
        B.load("NQ", "2m", fresh=False)
