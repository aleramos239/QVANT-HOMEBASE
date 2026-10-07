"""engine/btfeat.py: the Level-2 table of the blueprint TEST days, its one-off build and its loader (the TEST seal).

  (i)   the loader carries the TEST switch and no other: a date before 2025-07-01 raises before any row is read, a date after the
        table's last date raises, any other switch is refused at construction, the table it reads is the test table's alone;
  (ii)  a SYNTHETIC vendor (small hand-made depth / hist / flow files, no real day): build_test() splits the sessions at 2025-07-01
        and cuts the evening of its end; a build of a shorter end gives the same rows (features look backwards only);
  (iii) the module is the one place of the engine that names the test switch for Level 2, and bpfeat never names it.
Nothing here reads a real test day: the real table is never opened (the loader's table is a synthetic file in tmp_path)."""
import datetime as dt
import json
import pickle
import re
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import bpfeat
import btfeat
import l2data as D
import l2sim as S
from families import blocks as B

COLS = list(B.BOOK_COLS)


# ---- a synthetic table in the shape of the real one ---------------------------------------------------------------------------

def synth_table(path: Path, days=("2025-06-30", "2025-07-01", "2025-07-02"), bad_minute=None) -> pd.DataFrame:
    """Rows of ET minutes 09:30..09:34 of each date (stamped; usable 60 s later) with the columns the loader reads. `bad_minute`: the index
    (within a day) of a minute whose book is not ok (the loader's mask must NaN its book columns)."""
    rows, idx = [], []
    for d in days:
        for m in range(5):
            t = pd.Timestamp(f"{d} 09:{30 + m}", tz=D.ET)
            ok = not (bad_minute is not None and m == bad_minute)
            rows.append({"date": dt.date.fromisoformat(d), "book_ok": ok, **{c: 10.0 + m + (k % 3) for k, c in enumerate(COLS)}})
            idx.append((t + pd.Timedelta(seconds=60)).tz_convert("UTC"))
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="usable_at"))
    df.to_parquet(path)
    return df


@pytest.fixture
def table(tmp_path, monkeypatch):
    p = tmp_path / "l2feat_NQ_test.parquet"
    monkeypatch.setattr(btfeat, "cache_file", lambda: p)
    btfeat._LAST.clear()
    S._FRAMES.clear()
    yield p
    btfeat._LAST.clear()
    S._FRAMES.clear()


# ---- (i) the loader and its seal ----------------------------------------------------------------------------------------------

def test_the_loader_carries_the_test_seal_and_refuses_any_other_switch():
    f = btfeat.BtL2Features(COLS)
    assert f.allow_holdout == S.ALLOW_BT == "bp_test" and f.columns == tuple(COLS) and f.mask is True
    for other in (True, False, None, S.ALLOW_BP, S.ALLOW_CHECK, "bp_test ", "BP_TEST", 1, ("bp_test",)):
        with pytest.raises(S.HoldoutSealed):
            btfeat.BtL2Features(COLS, other)
    g = pickle.loads(pickle.dumps(f))                                   # (workers import it by name)
    assert (g.columns, g.allow_holdout) == (f.columns, f.allow_holdout) and "bp_test" in repr(f) and repr(f) != repr(bpfeat.BpL2Features(COLS))
    assert isinstance(f, S.L2Features) and not isinstance(f, bpfeat.BpL2Features)
    with pytest.raises(S.HoldoutSealed):                                # the engine's own loader still has no switch strings
        S.L2Features(COLS, allow_holdout=S.ALLOW_BT)
    with pytest.raises(S.HoldoutSealed):                                # ... and the build loader no test switch
        bpfeat.BpL2Features(COLS, S.ALLOW_BT)


def test_a_build_day_raises_before_any_row_is_read(tmp_path, monkeypatch):
    nowhere = tmp_path / "not_built.parquet"                            # no table at all: a sealed date must raise the SEAL, not a missing file
    monkeypatch.setattr(btfeat, "cache_file", lambda: nowhere)
    S._FRAMES.clear()
    f = btfeat.BtL2Features(COLS)
    for d in ("2025-06-30", "2025-06-01", "2025-01-02", "2024-12-31", "2021-09-22", dt.date(2023, 5, 5)):
        with pytest.raises(S.HoldoutSealed):
            f(d)
    assert not nowhere.exists() and not S._FRAMES                       # nothing was read or cached
    with pytest.raises(FileNotFoundError):                              # a test day, no table: the table is what is missing
        f("2025-07-01")


def test_the_loader_reads_the_test_table_only_and_masks_a_bad_book(table):
    synth_table(table, bad_minute=2)
    f = btfeat.BtL2Features(COLS)
    a = f(dt.date(2025, 7, 1))                                          # the first test day: its evening rows (date 06-30) are in the lookback
    assert a is not None and len(a.usable_ns) == 5 and set(COLS) <= set(a.cols)      # (06-30's rows lie before the 360-minute lookback of 07-01)
    assert btfeat.last_date() == dt.date(2025, 7, 2)
    b = f(dt.date(2025, 7, 2))
    assert b is not None
    bad = b.cols["imb10"]
    assert np.isnan(bad[b.usable_ns == pd.Timestamp("2025-07-02 09:33", tz=D.ET).value]).all() and not np.isnan(bad).all()
    with pytest.raises(btfeat.TestTableEnds):                           # after the table's last day: no row to read
        f(dt.date(2025, 7, 3))
    with pytest.raises(S.HoldoutSealed):
        f(dt.date(2025, 6, 30))
    same = btfeat.BtL2Features(COLS)(dt.date(2025, 7, 2))               # (the frame is cached per process, per column set)
    assert np.array_equal(same.usable_ns, b.usable_ns)


def test_a_table_holding_a_build_day_is_not_read(table):
    synth_table(table, days=("2025-06-12", "2025-07-01"))
    with pytest.raises(S.HoldoutSealed):
        btfeat.BtL2Features(COLS)(dt.date(2025, 7, 1))


def test_last_date_says_when_the_table_is_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr(btfeat, "cache_file", lambda: tmp_path / "nope.parquet")
    btfeat._LAST.clear()
    with pytest.raises(FileNotFoundError, match="not built"):
        btfeat.last_date()


def test_the_built_table_is_one_continuous_file_after_the_build_half():
    """The real table (if it is built here): split from the build half at the session date, no row twice, none out of order."""
    if not btfeat.cache_file().exists() or not bpfeat.cache_file().exists():
        pytest.skip("the test table is not built here (python engine/btfeat.py)")
    t = pd.read_parquet(btfeat.cache_file(), columns=["date", "globex_date", "t_utc"])
    b = pd.read_parquet(bpfeat.cache_file(), columns=["globex_date", "t_utc"])
    assert t["globex_date"].min() == S.BP_TEST_START and b["globex_date"].max() <= S.BP_BUILD[1]
    assert t.index.is_monotonic_increasing and not t.index.has_duplicates and t["t_utc"].min() > b["t_utc"].max()
    assert btfeat.last_date() == t["date"].max() <= btfeat.VENDOR_END
    assert set(btfeat.meta()["months"]) <= set(json.loads(D.PHASE_GUARD.read_text())["months"])      # every month is checked and persisted


# ---- (ii) a synthetic vendor: the build and the end-independence ---------------------------------------------------------------

NLEV = 12                                                              # slots a side in the synthetic depth file (the real one has 64 / 40)


def _bin(path: Path, magic: bytes, n: int, dtype, rows) -> None:
    arr = np.zeros(len(rows), dtype=dtype)
    for i, r in enumerate(rows):
        for k, v in r.items():
            arr[i][k] = v
    with open(path, "wb") as f:
        f.write(struct.pack("<4sIII", magic, 1, len(rows), n))
        f.write(arr.tobytes())


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    """16 weekday sessions of 09:30..09:59 stamps from 2025-07-01 (no evening rows), a book around a slow random walk, its own flow."""
    rng = np.random.default_rng(7)
    days = [d for d in pd.bdate_range("2025-07-01", periods=16)]
    ddt = np.dtype([("key", "<i8"), ("bid", "<f4", (NLEV, 2)), ("ask", "<f4", (NLEV, 2))])
    hdt = np.dtype([("key", "<i8"), ("s", "<f8", (16,))])
    drows, hrows, flow = [], [], []
    mid = 22000.125
    for d in days:
        for m in range(30):
            key = int(d.strftime("%Y%m%d")) * 10**6 + (9 * 10000 + (30 + m) * 100)
            mid += float(rng.normal(0, 0.5))
            mid = round(mid * 4) / 4 + 0.125
            k = np.arange(NLEV)
            bid = np.stack([mid - 0.125 - 0.25 * k, rng.integers(1, 60, NLEV)], 1).astype(np.float32)
            ask = np.stack([mid + 0.125 + 0.25 * k, rng.integers(1, 60, NLEV)], 1).astype(np.float32)
            drows.append({"key": key, "bid": bid, "ask": ask})
            hrows.append({"key": key, "s": rng.normal(size=16)})
            t = int(D.key_to_utc([key])[0])
            flow.append({"t_utc": t, "session": d.strftime("%Y-%m-%d"), "contract": "NQU5", **{c: float(rng.integers(0, 50)) for c in D.FLOW_SRC},
                         "o": mid, "h": mid, "l": mid, "c": mid})
    _bin(tmp_path / "depth.bin", b"2DBF", NLEV, ddt, drows)
    _bin(tmp_path / "hist.bin", b"2HBF", 16, hdt, hrows)
    pd.DataFrame(flow).to_parquet(tmp_path / "flow.parquet")
    monkeypatch.setattr(D, "ofb_files", lambda kind, allow_holdout=False: [tmp_path / f"{kind}.bin"])
    monkeypatch.setattr(D, "FLOW_1M", tmp_path / "flow.parquet")
    monkeypatch.setattr(D, "roll_days", lambda allow_holdout=False: ([], [d.date() for d in days]))
    return [d.date() for d in days]


def test_last_complete_session_reads_stamps_only(tmp_path):
    ddt = np.dtype([("key", "<i8"), ("bid", "<f4", (2, 2)), ("ask", "<f4", (2, 2))])
    for last, want in ((20260707155900, dt.date(2026, 7, 7)), (20260707120000, dt.date(2026, 7, 6)), (20260709155900, dt.date(2026, 7, 8))):
        p = tmp_path / f"d{last}.bin"
        _bin(p, b"2DBF", 2, ddt, [{"key": 20260706093000}, {"key": last}])
        assert btfeat.last_complete_session([p]) == want, last


def test_the_build_splits_at_the_first_test_day_cuts_the_evening_of_its_end_and_never_overwrites(vendor, tmp_path):
    days = vendor
    out = tmp_path / "t.parquet"
    r = btfeat.build_test(end=days[-1], verbose=False, path=out, phase=False, wait=False)
    t = pd.read_parquet(out)
    assert r["rows"] == len(t) == 16 * 30 and r["first"] == "2025-07-01" and r["last"] == days[-1].isoformat() and r["phase_failed"] == []
    assert t["globex_date"].min() == S.BP_TEST_START and t["globex_date"].max() == days[-1]
    assert t.index.is_monotonic_increasing and t["book_ok"].mean() > 0.95 and t["depth10_rel20d"].iloc[-30:].notna().all()   # warm: 10+ prior sessions
    with pytest.raises(FileExistsError):
        btfeat.build_test(end=days[-1], verbose=False, path=out, phase=False, wait=False)
    for bad in ("2025-06-30", "2026-07-09"):
        with pytest.raises(ValueError):
            btfeat.build_test(end=bad, verbose=False, path=tmp_path / "x.parquet", phase=False, wait=False)
    assert not (tmp_path / "x.parquet").exists()


def test_rows_do_not_depend_on_the_end_of_the_build(vendor, tmp_path):
    """l2data's docstring: every feature is backward looking, so a longer build reproduces a shorter one row for row."""
    days = vendor
    short = btfeat.build_test(end=days[11], verbose=False, path=tmp_path / "s.parquet", phase=False, wait=False)
    full = btfeat.build_test(end=days[-1], verbose=False, path=tmp_path / "f.parquet", phase=False, wait=False)
    a, b = pd.read_parquet(tmp_path / "s.parquet"), pd.read_parquet(tmp_path / "f.parquet")
    assert short["rows"] == 12 * 30 < full["rows"] and len(a) < len(b)
    r = btfeat.verify_end_independent(a, b, tail_min=0)
    assert r["differing"] == {} and r["checked"] == len(a) == 360
    assert a["depth10_rel20d"].iloc[-30:].notna().all() and a["bid10_rel15"].iloc[-30:].notna().mean() > 0.5       # warm features were compared, not only NaNs
    # ... the check itself is not blind: a doctored longer table is caught, column by column
    c = b.copy()
    c.iloc[100, c.columns.get_loc("imb10")] += 0.5
    c.iloc[330, c.columns.get_loc("depth10_rel20d")] = np.nan
    assert btfeat.verify_end_independent(a, c, tail_min=0)["differing"] == {"imb10": 1, "depth10_rel20d": 1}
    assert btfeat.verify_end_independent(a, b.iloc[1:], tail_min=0)["differing"] == {"<index>": 1}


def test_the_table_loader_serves_what_the_build_wrote(vendor, tmp_path, monkeypatch):
    out = tmp_path / "t.parquet"
    btfeat.build_test(end=vendor[-1], verbose=False, path=out, phase=False, wait=False)
    monkeypatch.setattr(btfeat, "cache_file", lambda: out)
    btfeat._LAST.clear()
    S._FRAMES.clear()
    f = btfeat.BtL2Features(["imb10", "depth10"])
    got = f(vendor[3])
    assert got is not None and len(got.usable_ns) == 30 and btfeat.last_date() == vendor[-1]
    with pytest.raises(btfeat.TestTableEnds):
        f(vendor[-1] + dt.timedelta(days=3))
    S._FRAMES.clear()


# ---- (iii) who names the test switch ---------------------------------------------------------------------------------------------

def test_btfeat_is_the_one_engine_module_besides_l2sim_that_names_the_test_switch():
    here = Path(btfeat.__file__).resolve().parent
    use = re.compile(r"ALLOW_BT|BP_TEST_START|[\"']bp_test[\"']")
    hits = sorted(p.name for p in here.glob("*.py") if use.search(p.read_text()))
    assert hits == ["btfeat.py", "l2sim.py"], hits
    assert not use.search((here / "bpfeat.py").read_text())             # the build loader never names it
