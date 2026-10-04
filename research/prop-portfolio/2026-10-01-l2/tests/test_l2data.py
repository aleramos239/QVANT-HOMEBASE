"""Tests of the L2 data layer (l2data.py). Real-data tests read IN-SAMPLE rows only (< 2025-01-01) and are skipped
when the OFB files / cache are not on this machine. Desk DOM lines (2026-09-25 ->) are used for live parity of the
feature function only."""
import datetime as dt
import gzip
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import l2data as D

ONYX = Path.home() / "ONYX TRADING"
OFB_TICK = Path.home() / "futures_derived" / "ofb_tick" / "NQ"


def _have_ofb():
    try:
        return all(p.exists() for p in D.ofb_files("depth") + D.ofb_files("hist"))
    except FileNotFoundError:
        return False


HAVE_OFB = _have_ofb()
HAVE_CACHE = all(D.cache_path(y).exists() for y in (2021, 2022, 2023, 2024))
need_ofb = pytest.mark.skipif(not HAVE_OFB, reason="OFB binaries not on this machine")
need_cache = pytest.mark.skipif(not HAVE_CACHE, reason="feature cache not built (python l2data.py build)")

DESK_LINE = {"t": 1790632800072,
             "b": [[30562.75, 4], [30560.0, 2], [30558.75, 2], [30556.75, 2], [30554.0, 2], [30553.75, 11],
                   [30550.75, 5], [30550.5, 1], [30550.0, 8], [30547.75, 5]],
             "a": [[30570.0, 2], [30571.25, 3], [30573.5, 3], [30575.5, 2], [30576.25, 2], [30577.75, 1],
                   [30578.75, 1], [30579.75, 1], [30580.0, 1], [30583.25, 1]]}


def _eq(a, b, tol=1e-6):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return bool(np.all((np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= tol * np.maximum(1.0, np.abs(b)))))


# ------------------------------------------------------------------------------------------------ pure function
def test_features_from_book_desk_line_by_hand():
    f = D.features_from_book(DESK_LINE["b"], DESK_LINE["a"])
    assert f["book_valid"] is True
    exp = {"bid_top1": 4, "bid_top3": 8, "bid_top10": 42, "ask_top1": 2, "ask_top3": 8, "ask_top10": 17,
           "imb3": 0.0, "imb10": 25 / 59, "spread_ticks": 29, "bid_wall_sz": 11, "bid_wall_dist": 36,
           "ask_wall_sz": 3, "ask_wall_dist": 5, "bid_med_sz": 3.0, "ask_med_sz": 1.5, "bid_n": 10, "ask_n": 10,
           "depth10": 59}
    assert set(exp) == set(D.STATIC_COLS)
    for k, v in exp.items():
        assert f[k] == pytest.approx(v), k


def test_far_cluster_gap_nonmonotone_and_zero_slots_are_dropped():
    asks = [[100.25, 1], [100.5, 2]]
    # near book of 4 levels, then far-cluster slots (19 pt gap, unordered)
    f = D.features_from_book([[100, 2], [99.75, 3], [99.5, 1], [99.25, 4], [80, 50], [95, 60]], asks)
    assert (f["bid_n"], f["bid_top10"], f["bid_wall_sz"], f["bid_wall_dist"]) == (4, 10, 4, 3)
    # a step back towards the touch ends the near book
    f = D.features_from_book([[100, 2], [99.75, 3], [99.9, 70], [99.0, 9]], asks)
    assert (f["bid_n"], f["bid_top10"]) == (2, 5)
    # zero-size slots are not levels
    f = D.features_from_book([[100, 2], [99.75, 0], [99.5, 1]], asks)
    assert (f["bid_n"], f["bid_top3"], f["bid_wall_dist"]) == (2, 3, 0)
    # exactly 10 points is still near (ladder_split: break only when the step is > max_gap)
    f = D.features_from_book([[100, 2], [90, 5]], asks)
    assert f["bid_n"] == 2
    # more than 10 levels: only the first 10 count
    bids = [[100 - 0.25 * i, 1] for i in range(14)]
    f = D.features_from_book(bids, asks)
    assert (f["bid_n"], f["bid_top10"]) == (10, 10)
    # tie on the wall -> the level nearest the touch
    f = D.features_from_book([[100, 5], [99.75, 5], [99.5, 1]], asks)
    assert f["bid_wall_dist"] == 0


def test_invalid_books_give_nan_and_flag():
    for bids, asks in (([[100.25, 1]], [[100.0, 1]]),            # crossed
                       ([[100.0, 1]], [[100.0, 1]]),             # locked
                       ([], [[100.0, 1]]), ([[100.0, 1]], []),   # one-sided
                       ([[100.0, 0]], [[100.25, 1]])):           # best slot empty and nothing behind
        f = D.features_from_book(bids, asks)
        assert f["book_valid"] is False
        assert all(np.isnan(f[c]) for c in D.STATIC_COLS)


def test_scale_and_price_invariance():
    """Features are relative: shifting every price by a constant changes nothing."""
    f0 = D.features_from_book(DESK_LINE["b"], DESK_LINE["a"])
    sh = lambda side: [[p - 12345.25, s] for p, s in side]
    f1 = D.features_from_book(sh(DESK_LINE["b"]), sh(DESK_LINE["a"]))
    assert f0 == f1


def test_usable_at_and_sessions():
    assert D.usable_at(1646144940) == 1646145000
    got = D.session_of(np.array([0, 179, 180, 504, 505, 569, 570, 659, 660, 809, 810, 957, 958, 1080]))
    assert list(got) == ["asia", "asia", "london", "london", "", "", "nyam", "nyam", "mid", "mid", "pm", "pm", "", ""]


def test_key_to_utc_dst():
    k = np.array([20220301093000, 20220705093000, 20211107180000, 20220313180000, 20241231165900])
    exp = [pd.Timestamp(s, tz=D.ET).value // 10**9 for s in
           ("2022-03-01 09:30", "2022-07-05 09:30", "2021-11-07 18:00", "2022-03-13 18:00", "2024-12-31 16:59")]
    assert list(D.key_to_utc(k)) == exp


def test_key_to_utc_matches_onyx_reader():
    sys.path.insert(0, str(ONYX))
    try:
        from onyx.lab.ofb import _key_to_utc
    except Exception:
        pytest.skip("onyx.lab.ofb not importable")
    rng = np.random.default_rng(1)
    days = pd.date_range("2021-09-22", "2024-12-31", freq="D")
    keys = np.array([int(d.strftime("%Y%m%d")) * 10**6 + int(h) * 10000 + int(m) * 100
                     for d, h, m in zip(days[rng.integers(0, len(days), 300)], rng.integers(0, 24, 300),
                                        rng.integers(0, 60, 300))])
    assert list(D.key_to_utc(keys)) == [_key_to_utc(int(k)) for k in keys]


def test_dynamic_batch_equals_live_state():
    rng = np.random.default_rng(3)
    t0 = 1_700_000_040
    st = D.LiveFeatureState()
    ts, bid, ask, live = [], [], [], []
    for i in range(400):
        if rng.random() < 0.10:
            continue                                            # minute with no snapshot at all
        m = t0 + 60 * i
        b, a = int(rng.integers(5, 80)), int(rng.integers(5, 80))
        if rng.random() < 0.08:                                 # crossed book = invalid snapshot
            f = st.update(m, [[100.5, b]], [[100.0, a]])
            b = a = np.nan
        else:
            f = st.update(m, [[100.0, b]], [[100.25, a]])
        assert f["usable_at"] == m + 60
        ts.append(m), bid.append(b), ask.append(a), live.append(f)
    dyn = D.dynamic_features(ts, bid, ask)
    for c in D.DYN_COLS:
        assert _eq([f[c] for f in live], dyn[c]), c
    assert np.isfinite(dyn["bid10_rel15"]).sum() > 100


def test_dynamic_features_are_backward_looking():
    rng = np.random.default_rng(4)
    t = 1_700_000_040 + 60 * np.arange(300)
    b, a = rng.integers(5, 80, 300).astype(float), rng.integers(5, 80, 300).astype(float)
    full = D.dynamic_features(t, b, a)
    cut = D.dynamic_features(t[:200], b[:200], a[:200])
    for c in D.DYN_COLS:
        assert _eq(full[c][:200], cut[c]), c
    # by hand at one point
    i = 100
    assert full["bid10_chg"][i] == b[i] - b[i - 1]
    assert full["bid10_rel15"][i] == pytest.approx(b[i] / np.median(b[i - 15:i]) - 1)


# ------------------------------------------------------------------------------------------------ binary reader
def _write_depth(path, rows, n=3):
    with open(path, "wb") as f:
        f.write(struct.pack("<4sIII", b"2DBF", 1, len(rows), n))
        for key, bids, asks in rows:
            flat = [x for lv in bids for x in lv] + [x for lv in asks for x in lv]
            f.write(struct.pack("<q", key) + struct.pack(f"<{4 * n}f", *flat))


def test_bin_reader_guard_bounds_and_chain(tmp_path):
    """The seal is the 2025-01-01 Globex session: the last in-sample key is 2024-12-31 16:59 ET, the New Year's Eve
    evening (18:00 ->) is already sealed."""
    assert D.SEAL_KEY == 20241231170000
    b, a = [(100.0, 2), (99.75, 3), (99.5, 1)], [(100.25, 1), (100.5, 4), (100.75, 2)]
    p1, p2 = tmp_path / "a.depth.bin", tmp_path / "b.depth.bin"
    _write_depth(p1, [(20241231165800, b, a), (20241231165900, b, a), (20241231180000, b, a), (20241231180100, b, a)])
    _write_depth(p2, [(20241231180100, b, a), (20250101000200, b, a)])
    got = np.concatenate([x["key"] for x in D.iter_bin("depth", 20241231000000, D.SEAL_KEY, files=[p1, p2])])
    assert list(got) == [20241231165800, 20241231165900]
    for hi in (D.SEAL_KEY + 100, 20241231180100, 20250101000000):          # the evening of 12-31 is sealed too
        with pytest.raises(D.HoldoutSealed):
            list(D.iter_bin("depth", 20241231000000, hi, files=[p1, p2]))
    got = np.concatenate([x["key"] for x in D.iter_bin("depth", 20241231165900, 20250102000000, allow_holdout=True,
                                                       files=[p1, p2])])
    assert list(got) == [20241231165900, 20241231180000, 20241231180100, 20250101000200]     # overlap dropped once
    blk = next(D.iter_bin("depth", 20241231000000, D.SEAL_KEY, files=[p1]))
    f = D.book_features_arrays(blk["bid"][:, :, 0], blk["bid"][:, :, 1], blk["ask"][:, :, 0], blk["ask"][:, :, 1])
    assert list(f["bid_top10"]) == [6, 6] and list(f["ask_wall_dist"]) == [1, 1] and list(f["spread_ticks"]) == [1, 1]
    with open(p1, "r+b") as fh:
        fh.write(b"XXXX")
    with pytest.raises(ValueError):
        D.BinFile(p1, "depth")


def test_binfile_accessor_refuses_sealed_rows(tmp_path):
    b, a = [(100.0, 2), (99.75, 3), (99.5, 1)], [(100.25, 1), (100.5, 4), (100.75, 2)]
    p = tmp_path / "a.depth.bin"
    _write_depth(p, [(20241231165800, b, a), (20241231165900, b, a), (20241231180000, b, a), (20250102093000, b, a)])
    bf = D.BinFile(p, "depth")
    assert bf.count == 4 and bf.open_n == 2
    assert [bf.key(i) for i in range(4)] == [20241231165800, 20241231165900, 20241231180000, 20250102093000]
    assert int(bf.row(1)["key"]) == 20241231165900 and list(bf.rows(0, 2)["key"]) == [20241231165800, 20241231165900]
    assert len(bf.rows(2, 2)) == 0                                    # an empty range reads nothing
    for call in (lambda: bf.row(2), lambda: bf.row(3), lambda: bf.rows(0, 3), lambda: bf.rows(2, 4), lambda: bf.mm):
        with pytest.raises(D.HoldoutSealed):
            call()
    for call in (lambda: bf.row(-1), lambda: bf.row(4), lambda: bf.rows(-1, 2), lambda: bf.rows(1, 5), lambda: bf.key(-1)):
        with pytest.raises(IndexError):                               # no negative-index route to the last rows
            call()
    ho = D.BinFile(p, "depth", allow_holdout=True)
    assert ho.open_n == 4 and int(ho.row(3)["key"]) == 20250102093000 and len(ho.mm) == 4
    assert D.BinFile(p, "depth", allow_holdout=1).open_n == 2         # only the literal True unseals


def test_holdout_guards_raise():
    for end in ("2025-01-01", dt.date(2026, 7, 8), "2025-06-30"):
        with pytest.raises(D.HoldoutSealed):
            D.load_features("2024-12-01", end)
        with pytest.raises(D.HoldoutSealed):
            D.build_features("2024-12-30", end, verbose=False)
        with pytest.raises(D.HoldoutSealed):
            D.build_cache("2024-12-30", end, verbose=False)
    with pytest.raises(D.HoldoutSealed):
        list(D.iter_bin("depth", 20241231000000, 20250101000100))
    with pytest.raises(D.HoldoutSealed):
        list(D.iter_bin("hist", 20241231000000, 20260101000000))
    with pytest.raises(D.HoldoutSealed):
        list(D.iter_bin("depth", 20241231000000, 20241231180000))        # New Year's Eve evening
    with pytest.raises(D.HoldoutSealed):
        D.phase_check(["2024-12", "2025-01"])
    assert issubclass(D.HoldoutSealed, PermissionError)


def test_holdout_build_runs_the_phase_check_itself_and_persists_the_failed_months(tmp_path, monkeypatch):
    """The old gate was an honour flag (phase_checked=True). Now the holdout build measures its own months BEFORE any feature
    is computed and writes the verdicts to cache/phase_guard.json, which l2sim enforces. SYNTHETIC rows only (2025 dates on a
    made-up tape): no sealed row is read."""
    feb = [dt.date(2025, 2, 10), dt.date(2025, 2, 11)]
    mar = [dt.date(2025, 3, 10), dt.date(2025, 3, 11)]
    _phase_fixture(tmp_path, monkeypatch, [59.3, 59.3, 60.2, 60.2], days=feb + mar)       # March: the book is taken AFTER the boundary
    guard = tmp_path / "cache" / "phase_guard.json"
    monkeypatch.setattr(D, "PHASE_GUARD", guard)
    order = []
    real_check = D.phase_check

    def check(*a, **k):
        order.append("phase_check")
        return real_check(*a, **k)

    def build(*a, **k):
        order.append("build_features")
        raise RuntimeError("stop after the phase check")

    monkeypatch.setattr(D, "phase_check", check)
    monkeypatch.setattr(D, "build_features", build)
    with pytest.raises(D.HoldoutSealed):                                  # the seal still comes first: nothing measured, nothing written
        D.build_cache("2024-12-30", "2025-03-31", verbose=False)
    assert order == [] and not guard.exists()
    with pytest.raises(RuntimeError, match="stop after the phase check"):  # phase_checked is ignored: no flag can skip the check
        D.build_cache("2024-12-30", "2025-03-31", allow_holdout=True, phase_checked=True, verbose=False)
    assert order == ["phase_check", "build_features"]
    g = json.loads(guard.read_text())
    assert sorted(g["months"]) == ["2025-01", "2025-02", "2025-03"] and g["failed"] == ["2025-03"] and g["guard_ms"] == 1000
    assert g["months"]["2025-03"]["failed_parts"] == ["rth"] and g["months"]["2025-02"]["ok"] and g["months"]["2025-01"]["ok"]
    assert D.guard_months(guard) == ["2025-03"] and D.build_cache.last_phase["failed"] == ["2025-03"]
    # an in-sample build measures nothing and leaves the file alone
    order.clear()
    before = guard.read_text()
    with pytest.raises(RuntimeError, match="stop after the phase check"):
        D.build_cache("2024-12-02", "2024-12-06", verbose=False)
    assert order == ["build_features"] and guard.read_text() == before and D.build_cache.last_phase is None


def test_persist_phase_merges_months_and_recomputes_the_failed_list(tmp_path):
    p = tmp_path / "g.json"
    row = lambda ok, parts: {"ok": ok, "failed_parts": parts, "phase_s": 59.3, "sess_max_s": 59.3, "on_phase_s": 59.3}
    D.persist_phase({"max_phase_s": 59.99, "overnight": True, "months": {"2024-01": row(True, []), "2024-02": row(False, ["overnight"])}}, p)
    assert D.guard_months(p) == ["2024-02"]
    D.persist_phase({"max_phase_s": 59.99, "overnight": True, "months": {"2024-03": row(False, ["rth", "overnight"])}}, p)
    assert D.guard_months(p) == ["2024-02", "2024-03"] and sorted(json.loads(p.read_text())["months"]) == ["2024-01", "2024-02", "2024-03"]
    D.persist_phase({"max_phase_s": 59.99, "overnight": True, "months": {"2024-02": row(True, [])}}, p)     # re-measured: passes now
    assert D.guard_months(p) == ["2024-03"] and D.guard_months(tmp_path / "absent.json") == []
    assert not list(tmp_path.glob("*.tmp"))


@need_ofb
def test_holdout_file_not_listed_by_default():
    assert len(D.ofb_files("depth")) == 1 and len(D.ofb_files("hist")) == 1
    assert all("20260601_20260708" not in str(p) for p in D.ofb_files("depth") + D.ofb_files("hist"))


@need_ofb
def test_real_binfile_is_sealed_from_new_years_eve_evening():
    for kind in ("depth", "hist"):
        bf = D.BinFile(D.ofb_files(kind)[0], kind)
        n = bf.open_n
        assert 0 < n < bf.count                                       # the main file holds sealed rows
        assert bf.key(n - 1) < D.SEAL_KEY <= bf.key(n)                # stamps only: no sealed payload is read
        assert int(bf.row(n - 1)["key"]) == bf.key(n - 1) == 20241231165900
        for call in (lambda: bf.row(n), lambda: bf.rows(n - 1, n + 1), lambda: bf.rows(bf.count - 1, bf.count),
                     lambda: bf.mm):
            with pytest.raises(D.HoldoutSealed):
                call()


@need_ofb
def test_in_sample_build_never_asks_for_sealed_rows(monkeypatch):
    """build_features(end=2024-12-31) caps the OFB key range and the flow cut at 2024-12-31 17:00 ET."""
    seen = {"keys": [], "cut": []}
    real_iter, real_flow = D.iter_bin, D._flow

    def spy_iter(kind, key_lo, key_hi, allow_holdout=False, **kw):
        seen["keys"].append((kind, key_hi, allow_holdout))
        for blk in real_iter(kind, key_lo, key_hi, allow_holdout, **kw):
            assert int(blk["key"].max()) < D.SEAL_KEY
            yield blk

    def spy_flow(cut_utc, lo_utc):
        seen["cut"].append(cut_utc)
        fl = real_flow(cut_utc, lo_utc)
        assert int(fl["t_utc"].max()) < seal_utc
        return fl

    seal_utc = pd.Timestamp("2024-12-31 17:00", tz=D.ET).value // 10**9
    monkeypatch.setattr(D, "iter_bin", spy_iter)
    monkeypatch.setattr(D, "_flow", spy_flow)
    df = D.build_features("2024-12-30", "2024-12-31", verbose=False)
    assert seen["keys"] == [("depth", D.SEAL_KEY, False), ("hist", D.SEAL_KEY, False)] and seen["cut"] == [seal_utc]
    assert df.index.max() == pd.Timestamp("2024-12-31 17:00", tz=D.ET) and len(df) == 2 * 1380
    assert df["globex_date"].max() == dt.date(2024, 12, 31)


# ------------------------------------------------------------------------------------------------ real OFB rows
def _sample_rows(n, seed, minute_lo=0, minute_hi=1440):
    """Random in-sample depth rows on plain weekdays (structured rows)."""
    rng = np.random.default_rng(seed)
    bf = D.BinFile(D.ofb_files("depth")[0], "depth")
    days = [d for d in pd.bdate_range("2021-09-22", "2024-12-30") if d.month not in (3, 6, 9, 12)]
    out = []
    while len(out) < n:
        d = days[int(rng.integers(len(days)))]
        m = int(rng.integers(minute_lo, minute_hi))
        key = int(d.strftime("%Y%m%d")) * 10**6 + (m // 60) * 10000 + (m % 60) * 100
        assert key < 20250101000000
        row = bf.row(bf._bisect(key))
        if int(row["key"]) == key and row["bid"][0, 1] > 0 and row["ask"][0, 1] > 0:
            out.append(row)
    return out


@need_ofb
def test_near_book_equals_onyx_ladder_split():
    sys.path.insert(0, str(ONYX))
    try:
        from onyx.lab.ofb import ladder_split
    except Exception:
        pytest.skip("onyx.lab.ofb not importable")
    checked = 0
    for row in _sample_rows(300, 11):
        for side, desc in (("bid", True), ("ask", False)):
            near, _far = ladder_split([(float(p), float(s)) for p, s in row[side]])
            px, sz, keep = D._near(row[side][None, :, 0], row[side][None, :, 1], desc)
            mine = [(float(p), float(s)) for p, s, k in zip(px[0], sz[0], keep[0]) if k]
            assert mine == near[:D.NLEV]
            checked += 1
    assert checked == 600


@need_ofb
@need_cache
def test_cache_equals_features_from_book_on_ofb_rows_truncated_to_10():
    df = D.load_features("2021-09-22", "2024-12-31", columns=D.STATIC_COLS + ["book_valid"], mask_bad_book=False)
    n = 0
    for row in _sample_rows(400, 21, 9 * 60, 16 * 60):
        if not ((row["bid"][:10, 1] > 0).all() and (row["ask"][:10, 1] > 0).all()):
            continue
        ua = pd.Timestamp(int(D.key_to_utc([row["key"]])[0]) + 60, unit="s", tz="UTC")
        if ua not in df.index:
            continue
        c = df.loc[ua]
        full = D.features_from_book(row["bid"].tolist(), row["ask"].tolist())           # all 64 slots
        top = D.features_from_book(row["bid"][:10].tolist(), row["ask"][:10].tolist())  # desk-shaped: 10 levels
        assert bool(c["book_valid"]) == top["book_valid"] == full["book_valid"]
        for k in D.STATIC_COLS:
            assert _eq(full[k], top[k]) and _eq(c[k], top[k]), (int(row["key"]), k)
        n += top["book_valid"]
    assert n >= 300


@need_ofb
@need_cache
def test_live_state_reproduces_cached_dynamic_columns():
    day = dt.date(2023, 5, 10)
    df = D.load_features(day, day, mask_bad_book=False)
    st, rows = D.LiveFeatureState(), []
    for blk in D.iter_bin("depth", 20230510090000, 20230510120000):
        for r in blk:
            m = int(D.key_to_utc([r["key"]])[0])
            rows.append(st.update(m, r["bid"][:10].tolist(), r["ask"][:10].tolist()))
    assert len(rows) == 180
    for f in rows[D.MED_WIN:]:                                  # the live state has no history before 09:00
        c = df.loc[pd.Timestamp(f["usable_at"], unit="s", tz="UTC")]
        assert c["t_utc"] == f["t_utc"]
        for k in D.STATIC_COLS + D.DYN_COLS + D.PX_COLS:
            assert _eq(c[k], f[k]), (f["t_utc"], k)


@need_ofb
@need_cache
def test_short_build_reproduces_cache_rows():
    """Causality: a 2-session build equals the same rows of the full build (only the 20-day TOD column needs
    history the short build does not have)."""
    short = D.build_features("2022-03-01", "2022-03-02", verbose=False)
    full = D.load_features("2022-02-28", "2022-03-02", mask_bad_book=False).loc[short.index]
    # two full sessions + the evening of the end date (the next session's first 359 minutes)
    assert len(short) == 2 * 1380 + 359 and list(short.columns) == list(full.columns)
    for c in short.columns:
        if c in D.TOD_COLS:
            continue
        if short[c].dtype.kind == "f":
            assert _eq(short[c], full[c]), c
        else:
            assert (short[c].fillna("") == full[c].fillna("")).all(), c


@need_ofb
def test_timestamp_law_end_of_minute():
    """A row stamped M matches the tape at M + 60 s (end of minute), not at M (start)."""
    rng = np.random.default_rng(5)
    bf = D.BinFile(D.ofb_files("depth")[0], "depth")
    d_start, d_end, d_snap = [], [], []
    for day in (dt.date(2021, 11, 3), dt.date(2022, 7, 5), dt.date(2023, 4, 25), dt.date(2024, 10, 9)):
        p = OFB_TICK / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.parquet"
        if not p.exists():
            pytest.skip("ofb_tick cache not on this machine")
        tk = pd.read_parquet(p, columns=["ts_ns", "price"])
        ts, px = tk["ts_ns"].to_numpy(), tk["price"].to_numpy()
        for mod in rng.choice(np.arange(9 * 60 + 31, 15 * 60 + 58), 15, replace=False):
            key = int(day.strftime("%Y%m%d")) * 10**6 + (int(mod) // 60) * 10000 + (int(mod) % 60) * 100
            row = bf.row(bf._bisect(key))
            assert int(row["key"]) == key
            bid, ask = float(row["bid"][0, 0]), float(row["ask"][0, 0])
            m_ns = int(D.key_to_utc([key])[0]) * 10**9
            for off, acc in ((0.0, d_start), (60.0, d_end), (D.SNAPSHOT_OFFSET_S, d_snap)):
                p_last = px[np.searchsorted(ts, m_ns + int(off * 1e9), side="left") - 1]
                acc.append(max(bid - p_last, p_last - ask, 0.0))
    d_start, d_end, d_snap = map(np.array, (d_start, d_end, d_snap))
    assert len(d_end) == 60
    assert (d_end < d_start).sum() > 5 * (d_start < d_end).sum()
    assert d_end.mean() < 0.25 * d_start.mean()
    assert d_snap.mean() <= d_end.mean() + 1e-9               # the snapshot sits just BEFORE the boundary


# ------------------------------------------------------------------------------------------------ cache / loader
@need_cache
def test_load_features_contract():
    df = D.load_features("2022-03-01", "2022-03-04")
    assert isinstance(df.index, pd.DatetimeIndex) and str(df.index.tz) == "UTC" and df.index.name == "usable_at"
    assert df.index.is_unique and df.index.is_monotonic_increasing
    assert (df.index.asi8 // 10**9 == df["t_utc"] + 60).all()
    et = df.index.tz_convert(D.ET)
    assert (pd.Series(et.date, index=df.index) == df["date"]).all()
    assert ((et.hour * 60 + et.minute) == df["et_min"]).all()
    assert list(df["session"]) == list(D.session_of(df["et_min"].to_numpy()))
    assert df["date"].min() == dt.date(2022, 3, 1) and df["date"].max() == dt.date(2022, 3, 4)
    assert list(df.columns) == D.TAG_COLS + D.FLAG_COLS + D.BOOK_COLS + D.PX_COLS + D.FLOW_COLS + D.RT_COLS
    # the only absolute prices: the two anchors (best bid / ask) and our own tape's OHLC
    assert [c for c in df.columns if any(w in c for w in ("best", "px", "mid", "price"))] == D.PX_COLS == ["bid_px", "ask_px"]
    assert not set(D.PX_COLS) & set(D.BOOK_COLS)                         # anchors are not features
    stamp = (df.index - pd.Timedelta(seconds=60)).tz_convert(D.ET)
    assert not ((stamp.hour == 17) | (stamp.dayofweek == 5)).any()      # no maintenance hour, no Saturday
    # 09:30:00 ET decision row = minute 09:29, tagged nyam
    r = df.loc[pd.Timestamp("2022-03-01 09:30", tz=D.ET).tz_convert("UTC")]
    assert r["session"] == "nyam" and r["et_min"] == 570
    assert r["t_utc"] == pd.Timestamp("2022-03-01 09:29", tz=D.ET).value // 10**9
    sub = D.load_features("2022-03-01", "2022-03-01", columns=["imb10"])
    assert {"imb10", "date", "book_ok"} <= set(sub.columns)


@need_cache
def test_default_load_is_in_sample_only():
    df = D.load_features(columns=["t_utc"])
    assert df["date"].min() == dt.date(2021, 9, 21) and df["date"].max() == dt.date(2024, 12, 31)
    assert df.index.max() == pd.Timestamp("2024-12-31 17:00", tz=D.ET)      # last stamp 16:59 ET
    assert D.load_features("2024-12-01", columns=["globex_date"])["globex_date"].max() == dt.date(2024, 12, 31)
    assert df.index.min() == pd.Timestamp("2021-09-21 18:01", tz=D.ET)
    assert len(df) > 1_100_000


@need_cache
def test_roll_block_and_book_ok():
    rolls, sessions = D.roll_days()
    assert [str(r) for r in rolls] == ["2021-12-10", "2022-03-14", "2022-06-13", "2022-09-12", "2022-12-12",
                                       "2023-03-13", "2023-06-12", "2023-09-11", "2023-12-11", "2024-03-11",
                                       "2024-06-17", "2024-09-16", "2024-12-17"]
    assert max(sessions) < D.HOLDOUT_START
    block = D.roll_block_dates(rolls, sessions)
    assert {dt.date(2022, 6, 10), dt.date(2022, 6, 13), dt.date(2022, 6, 14)} <= block and len(block) == 39
    raw = D.load_features(columns=["globex_date", "roll_block", "ofb_mismatch", "book_ok", "book_valid", "in_tape",
                                   "imb10", "rt_size_imb", "f_delta"], mask_bad_book=False)
    in_block = raw["globex_date"].isin(block)
    assert (raw["roll_block"] == in_block).all()
    assert not raw.loc[in_block, "book_ok"].any()
    whole = raw.groupby("globex_date")["ofb_mismatch"].all()
    assert set(whole.index[whole]) <= block                               # every other-contract SESSION is in the block
    assert (raw["book_ok"] == (raw["book_valid"] & raw["in_tape"] & ~raw["roll_block"] & ~raw["ofb_mismatch"])).all()
    assert raw.loc[in_block, "imb10"].notna().any()                       # raw values exist ...
    masked = D.load_features("2022-06-09", "2022-06-14", columns=["globex_date", "imb10", "rt_size_imb", "f_delta"])
    masked = masked[masked["globex_date"].isin(block)]
    assert masked["globex_date"].nunique() == 3
    assert masked["imb10"].isna().all() and masked["rt_size_imb"].isna().all()   # ... and the loader hides them
    assert masked["f_delta"].notna().any()                                # own flow is not a book feature
    ok = D.load_features("2022-06-15", "2022-06-15", columns=["imb10"])
    assert ok["imb10"].notna().mean() > 0.95


@need_cache
def test_flow_join_matches_source():
    df = D.load_features("2023-03-01", "2023-03-02")
    lo, hi = int(df["t_utc"].min()), int(df["t_utc"].max())
    assert hi < pd.Timestamp("2025-01-01", tz=D.ET).value // 10**9
    fl = pd.read_parquet(D.FLOW_1M, columns=["t_utc", "delta", "cum_delta", "volume", "sweep_buy_vol", "c"],
                         filters=[("t_utc", ">=", lo), ("t_utc", "<=", hi)]).set_index("t_utc")
    j = df.set_index("t_utc")
    both = j.index.intersection(fl.index)
    assert len(both) > 2000 and len(both) == j["f_volume"].notna().sum()
    for src, col in (("delta", "f_delta"), ("cum_delta", "f_cum_delta"), ("volume", "f_volume"),
                     ("sweep_buy_vol", "f_sweep_buy_vol"), ("c", "f_c")):
        assert _eq(j.loc[both, col], fl.loc[both, src]), col
    t = df[df["f_volume"].notna()]
    assert _eq(t["f_buy_vol"] - t["f_sell_vol"], t["f_delta"])


@need_cache
def test_feature_ranges():
    df = D.load_features("2024-01-01", "2024-03-01")
    ok = df[df["book_ok"]]
    assert ok["imb3"].abs().max() <= 1 and ok["imb10"].abs().max() <= 1
    assert (ok["bid_top1"] <= ok["bid_top3"]).all() and (ok["bid_top3"] <= ok["bid_top10"]).all()
    assert (ok["spread_ticks"] >= 1).all()
    assert (ok["bid_wall_sz"] >= ok["bid_med_sz"]).all() and (ok["bid_wall_sz"] <= ok["bid_top10"]).all()
    assert ok["bid_n"].between(1, 10).all() and ok["ask_n"].between(1, 10).all()
    assert _eq(ok["depth10"], ok["bid_top10"] + ok["ask_top10"])
    assert df.loc[~df["book_ok"], D.BOOK_COLS + D.RT_COLS].isna().all().all()


# ------------------------------------------------------------------------------------------------ desk parity
def _desk_file():
    files = [p for p in sorted(D.DESK_DEPTH_DIR.glob("2026/*.depth.jsonl.gz")) if p.stat().st_size > 1_000_000]
    return files[0] if files else None


@pytest.mark.skipif(_desk_file() is None, reason="no desk depth recording")
def test_desk_lines_and_minute_snapshots():
    import gzip
    p = _desk_file()
    with gzip.open(p, "rt") as fh:
        lines = [json.loads(next(fh)) for _ in range(300)]
    for j in lines:
        f = D.features_from_book(j["b"], j["a"])
        assert set(f) == set(D.STATIC_COLS) | {"book_valid"}
        if not f["book_valid"]:
            continue
        b = np.array(j["b"], dtype=float)
        nb = int(f["bid_n"])
        assert 1 <= nb <= min(10, len(b)) and f["bid_top1"] == b[0, 1]
        assert f["bid_top10"] == b[:nb, 1].sum() and f["bid_wall_sz"] == b[:nb, 1].max()
        assert abs(f["imb10"]) <= 1 and f["spread_ticks"] == round((j["a"][0][0] - b[0, 0]) / D.TICK)
    st, prev, n = D.LiveFeatureState(), None, 0
    for m, bids, asks in D.desk_minute_books(p):
        assert m % 60 == 0 and (prev is None or m > prev)
        f = st.update(m, bids, asks)
        assert f["usable_at"] == m + 60
        prev, n = m, n + 1
        if n >= 120:
            break
    assert n == 120


@need_cache
def test_tod_20_session_median_by_hand():
    """depth10_rel20d = depth10 / median(depth10 at the same ET minute over the PREVIOUS 20 sessions, ok rows) - 1."""
    df = D.load_features("2022-11-01", "2023-03-10", columns=["et_min", "depth10", "depth10_rel20d", "globex_date"])
    g = df[df["et_min"] == 600]                                  # the 10:00 ET decision row of every session
    assert g["globex_date"].is_unique and len(g) > 80
    d10, got, n = g["depth10"].to_numpy(dtype=float), g["depth10_rel20d"].to_numpy(dtype=float), 0
    for i in range(40, len(g)):
        prev = d10[i - 20:i]
        exp = d10[i] / np.nanmedian(prev) - 1 if np.isfinite(prev).sum() >= 10 else np.nan
        assert _eq(got[i], exp, tol=1e-5), g.index[i]
        n += np.isfinite(exp)
    assert n > 40


# ------------------------------------------------------------------------------------------------ per-minute mismatch
def test_mismatch_minutes_synthetic():
    """A book on another contract for part of a session is flagged minute by minute, with a sharp edge; fast-market
    minutes and missing prints are not."""
    rng = np.random.default_rng(7)
    n = 600
    t = 1_700_000_040 + 60 * np.arange(n)
    c = 15000 + np.cumsum(rng.normal(0, 2.0, n)).round(2)
    bid, ask = c - 0.25, c + 0.25
    assert not D.mismatch_minutes(t, bid, ask, c).any()
    # the first 120 minutes sit 3 points away (old contract), then the book switches
    b2, a2 = bid.copy(), ask.copy()
    b2[:120] += 3.0
    a2[:120] += 3.0
    f = D.mismatch_minutes(t, b2, a2, c)
    assert f[:120].all() and not f[120 + D.MISMATCH_PAD:].any() and f.sum() <= 120 + D.MISMATCH_PAD
    # ... the same in the middle of the series, and with the offset below the tolerance
    b3, a3 = bid.copy(), ask.copy()
    b3[300:420] -= 250.0
    a3[300:420] -= 250.0
    f = D.mismatch_minutes(t, b3, a3, c)
    assert f[300:420].all() and f.sum() <= 120 + 2 * D.MISMATCH_PAD and not f[:290].any() and not f[430:].any()
    b4, a4 = bid + 0.75, ask + 0.75                                  # 3 ticks off for the whole series: tolerated
    assert not D.mismatch_minutes(t, b4, a4, c).any()
    # isolated fast-market minutes (tape 15 points through the book) never move the 61-minute median
    c5 = c.copy()
    c5[[50, 51, 200, 333, 334, 335]] += 15.0
    assert not D.mismatch_minutes(t, bid, ask, c5).any()
    # minutes without a print or without a valid book carry no evidence
    c6, b6 = c.copy(), b2.copy()
    c6[::3] = np.nan
    b6[1::7] = np.nan
    f = D.mismatch_minutes(t, b6, a2, c6)
    assert f[:118].all() and not f[125:].any()
    assert D.mismatch_minutes([], [], [], []).shape == (0,)


@need_cache
def test_roll_plus2_evening_is_masked_minute_by_minute():
    """OFB stays on the old contract through the first 1-2 evening hours of roll day + 2: those rows must be
    ofb_mismatch / book_ok False, the rest of the session (every R session) untouched."""
    rolls, sessions = D.roll_days()
    block = D.roll_block_dates(rolls, sessions)
    raw = D.load_features(columns=["globex_date", "et_min", "session", "roll_block", "ofb_mismatch", "book_ok",
                                   "book_valid", "in_tape", "bid_px", "ask_px", "f_c", "bid10_chg", "bid10_rel15"],
                          mask_bad_book=False)
    out = raw[raw["ofb_mismatch"] & ~raw["roll_block"]]
    plus2 = {sessions[sessions.index(r) + 2] for r in rolls}
    assert set(out["globex_date"]) <= plus2 and out["globex_date"].nunique() == 11
    assert (out["session"] == "").all() and out["et_min"].between(18 * 60 + 1, 20 * 60 + 5).all()
    assert 1100 <= len(out) <= 1250 and not out["book_ok"].any()
    n = out.groupby("globex_date").size()
    assert n[dt.date(2024, 3, 13)] >= 120 and n[dt.date(2024, 12, 19)] >= 59 and n[dt.date(2022, 3, 16)] >= 120
    # nothing a contract away is left among the book_ok rows of the roll weeks (isolated fast minutes aside)
    ok = raw[raw["book_ok"] & raw["globex_date"].isin(plus2)]
    off = ((ok["bid_px"] + ok["ask_px"]) / 2 - ok["f_c"]).abs()
    assert (off > 20).sum() == 0 and off.median() <= 0.5
    # ... and anywhere: the tape close sits within 1 point of [bid, ask] in the median of every 61 book_ok minutes
    okk = raw[raw["book_ok"] & raw["f_c"].notna()]
    d = np.where(okk["f_c"] > okk["ask_px"], okk["f_c"] - okk["ask_px"],
                 np.where(okk["f_c"] < okk["bid_px"], okk["f_c"] - okk["bid_px"], 0.0))
    assert np.abs(pd.Series(d).rolling(61, center=True, min_periods=31).median()).max() <= D.MISMATCH_MIN_PTS
    # the masked loader hides the anchors and the features there
    m = D.load_features("2024-03-12", "2024-03-13", columns=["globex_date", "et_min", "imb10", "bid_px", "ask_px"])
    eve = m[(m["globex_date"] == dt.date(2024, 3, 13)) & (m["et_min"] > 18 * 60) & (m["et_min"] <= 20 * 60)]
    assert len(eve) == 120 and eve[["imb10", "bid_px", "ask_px"]].isna().all().all()
    late = m[(m["globex_date"] == dt.date(2024, 3, 13)) & (m["et_min"] > 20 * 60 + 30)]
    assert late["bid_px"].notna().mean() > 0.95
    # trailing columns never span the switch: no change vs an old-contract snapshot, no median built on them
    g = raw[raw["globex_date"] == dt.date(2024, 3, 13)]
    first_ok = int(np.flatnonzero(g["book_ok"].to_numpy())[0])
    assert g["ofb_mismatch"].iloc[:first_ok].all()
    assert np.isnan(g["bid10_chg"].iloc[first_ok]) and g["bid10_rel15"].iloc[first_ok:first_ok + D.MED_MIN].isna().all()
    assert g["bid10_rel15"].iloc[first_ok + D.MED_MIN:first_ok + 60].notna().mean() > 0.9


# ------------------------------------------------------------------------------------------------ price anchors
def test_price_anchors_from_book_and_live_state():
    f = D.features_from_book(DESK_LINE["b"], DESK_LINE["a"], with_px=True)
    assert (f["bid_px"], f["ask_px"]) == (30562.75, 30570.0)
    assert f["ask_px"] - f["bid_px"] == f["spread_ticks"] * D.TICK
    # the wall's price = anchor -/+ wall distance: the 11-lot bid at 30553.75, the first 3-lot ask at 30571.25
    assert f["bid_px"] - f["bid_wall_dist"] * D.TICK == 30553.75
    assert f["ask_px"] + f["ask_wall_dist"] * D.TICK == 30571.25
    assert "bid_px" not in D.features_from_book(DESK_LINE["b"], DESK_LINE["a"])         # opt-in: features stay relative
    bad = D.features_from_book([[100.25, 1]], [[100.0, 1]], with_px=True)               # crossed book: no anchor
    assert np.isnan(bad["bid_px"]) and np.isnan(bad["ask_px"])
    # an empty best slot is not the anchor
    f = D.features_from_book([[100.0, 0], [99.5, 3]], [[100.25, 1]], with_px=True)
    assert f["bid_px"] == 99.5
    live = D.LiveFeatureState().update(1_700_000_040, DESK_LINE["b"], DESK_LINE["a"])
    assert (live["bid_px"], live["ask_px"]) == (30562.75, 30570.0)


@need_cache
def test_price_anchors_are_tape_coordinates_and_equal_ofb_tick_prev_best():
    """bid_px / ask_px == ofb_tick prev_best_bid / prev_best_ask of the same stamp (the SPEC's source), consistent
    with spread_ticks, NaN wherever book_ok is False, and within reach of our own tape's close."""
    for day in (dt.date(2022, 7, 5), dt.date(2024, 10, 9)):
        p = OFB_TICK / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.parquet"
        if not p.exists():
            pytest.skip("ofb_tick cache not on this machine")
        tk = pd.read_parquet(p, columns=["flow_t", "prev_best_bid", "prev_best_ask"]).dropna()
        tk = tk.groupby("flow_t").first()
        df = D.load_features(day - dt.timedelta(days=1), day, columns=["t_utc", "bid_px", "ask_px", "spread_ticks"])
        j = df.dropna(subset=["bid_px"]).set_index("t_utc").join(tk, how="inner")
        assert len(j) > 1200
        assert (j["bid_px"] == j["prev_best_bid"]).all() and (j["ask_px"] == j["prev_best_ask"]).all()
        assert _eq(j["ask_px"] - j["bid_px"], j["spread_ticks"] * D.TICK)
    df = D.load_features("2023-01-01", "2023-12-31", columns=["bid_px", "ask_px", "f_c", "imb10"])
    assert df["bid_px"].dtype == np.float64
    assert df.loc[~df["book_ok"], D.PX_COLS].isna().all().all() and df.loc[df["book_ok"], D.PX_COLS].notna().all().all()
    ok = df[df["book_ok"] & df["f_c"].notna()]
    off = ((ok["bid_px"] + ok["ask_px"]) / 2 - ok["f_c"]).abs()
    assert off.median() <= 0.5 and off.quantile(0.99) <= 4.0 and (ok["bid_px"] % D.TICK == 0).all()


@need_ofb
def test_wall_price_points_at_the_wall_level():
    """anchor -/+ wall_dist * tick is the price of the level holding wall_sz in the raw OFB row."""
    n = 0
    for row in _sample_rows(200, 31, 9 * 60, 16 * 60):
        f = D.features_from_book(row["bid"].tolist(), row["ask"].tolist(), with_px=True)
        if not f["book_valid"]:
            continue
        for side, sgn in (("bid", -1), ("ask", 1)):
            px = f[f"{side}_px"] + sgn * f[f"{side}_wall_dist"] * D.TICK
            lv = {float(p): float(z) for p, z in row[side][:12] if z > 0}
            assert lv[px] == f[f"{side}_wall_sz"], (int(row["key"]), side)
        n += 1
    assert n >= 150


# ------------------------------------------------------------------------------------------------ desk snapshots
def test_desk_minute_books_never_yields_the_in_progress_minute(tmp_path):
    p = tmp_path / "x.depth.jsonl.gz"
    m0 = 1_790_900_040                                             # a minute start (UTC s)
    off = int(D.LIVE_SNAPSHOT_S * 1000)

    def line(t_ms, sz):
        return json.dumps({"t": t_ms, "b": [[100.0, sz]], "a": [[100.25, 1]]})

    rows = [line(m0 * 1000 + 10_000, 1), line(m0 * 1000 + off, 2),            # minute m0: the line AT the instant counts
            line(m0 * 1000 + off + 1, 3), line((m0 + 60) * 1000 + 20_000, 4)]  # minute m0+60, still in progress
    with gzip.open(p, "wt") as fh:
        fh.write("\n".join(rows) + "\n" + '{"t": 17909')                      # + a truncated last line
    inst = (m0 + 60) * 1000 + off                                              # snapshot instant of the trailing minute
    for now in ((m0 + 60) * 1000 + 21_000, inst, inst + 5000):                 # in progress / just reached / settling
        got = list(D.desk_minute_books(p, now_ms=now))
        assert [(m, b[0][1]) for m, b, a in got] == [(m0, 2)]
    got = list(D.desk_minute_books(p, now_ms=inst + 5001))                     # finished: the trailing minute counts
    assert [(m, b[0][1]) for m, b, a in got] == [(m0, 2), (m0 + 60, 4)]
    assert [(m, b[0][1]) for m, b, a in D.desk_minute_books(p)] == [(m0, 2), (m0 + 60, 4)]     # wall clock: long past
    assert list(D.desk_minute_books(p, now_ms=m0 * 1000)) == [(m0, [[100.0, 2]], [[100.25, 1]])]


# ------------------------------------------------------------------------------------------------ phase check
def _phase_fixture(tmp_path, monkeypatch, phases, days=None, on_phases=None):
    """Synthetic OFB depth file + tape: session i's book is the bracket of the tape price at ``M + phases[i]`` s.
    on_phases (optional): also OVERNIGHT rows (stamps 03:00 .. 05:59 ET) whose book is taken at ``M + on_phases[i]`` s."""
    rng = np.random.default_rng(9)
    days = days or [dt.date(2023, 5, 10) + dt.timedelta(days=i) for i in range(len(phases))]
    rows = []
    for n, (d, ph) in enumerate(zip(days, phases)):
        spans = [(9 * 60 + 29, 392, 9 * 60 + 30, 16 * 60, ph)]                     # (tape start, tape minutes, first stamp, end, phase)
        if on_phases is not None:
            spans.insert(0, (2 * 60 + 59, 182, 3 * 60, 6 * 60, on_phases[n]))
        ts = np.concatenate([pd.Timestamp(f"{d} {a // 60:02d}:{a % 60:02d}", tz=D.ET).value
                             + np.arange(0, k * 60 * 10**9, 25_000_000, dtype=np.int64) for a, k, _, _, _ in spans])   # a print every 25 ms
        px = 14000 + np.round(np.cumsum(rng.normal(0, 0.12, len(ts))) / 0.25) * 0.25
        out = tmp_path / "tape" / f"{d:%Y}" / f"{d:%m}"
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"ts_ns": ts, "price": px}).to_parquet(out / f"{d:%Y-%m-%d}.parquet")
        for _, _, m0, m1, phase in spans:
            for mod in range(m0, m1):
                key = int(d.strftime("%Y%m%d")) * 10**6 + (mod // 60) * 10000 + (mod % 60) * 100
                m_ns = int(D.key_to_utc([key])[0]) * 10**9
                last = px[np.searchsorted(ts, m_ns + int(phase * 1e9), side="left") - 1]   # the book the vendor saw
                rows.append((key, [(last - 0.25, 2), (last - 0.5, 3), (last - 0.75, 1)],
                             [(last + 0.25, 1), (last + 0.5, 4), (last + 0.75, 2)]))
    rows.sort(key=lambda r: r[0])
    f = tmp_path / "syn.depth.bin"
    _write_depth(f, rows)
    monkeypatch.setattr(D, "ofb_files", lambda kind, allow_holdout=False: [f])
    monkeypatch.setattr(D, "OFB_TICK_DIR", tmp_path / "tape")
    monkeypatch.setattr(D, "roll_days", lambda allow_holdout=False: ([], days))
    return days


def test_phase_check_passes_before_the_boundary_and_fails_at_or_after_it(tmp_path, monkeypatch):
    _phase_fixture(tmp_path, monkeypatch, [59.30, 59.30])
    r = D.phase_check(["2023-05"])
    m = r["months"]["2023-05"]
    assert r["ok"] and r["failed"] == [] and m["sessions"] == 2 and m["minutes"] == 780
    assert abs(m["phase_s"] - 59.30) <= 0.03 and m["sess_max_s"] < 59.99 and abs(m["margin_s"] - 0.70) <= 0.03
    # a month with no OFB rows has no book feature to protect: vacuous pass
    r = D.phase_check(["2023-04", "2023-05"])
    assert r["ok"] and r["months"]["2023-04"]["sessions"] == 0 and r["months"]["2023-04"]["ofb_rows"] == 0
    # the same data fails a stricter limit
    with pytest.raises(D.PhaseCheckFailed) as e:
        D.phase_check(["2023-05"], max_phase_s=59.2)
    assert e.value.result["failed"] == ["2023-05"] and not e.value.result["ok"]


@pytest.mark.parametrize("phases", [[60.0, 60.0], [60.4, 60.4], [59.3, 60.2]])
def test_phase_check_fails_when_the_snapshot_is_not_before_the_boundary(tmp_path, monkeypatch, phases):
    """Snapshot at the boundary, after it, or after it in ONE session of the month: all must fail."""
    _phase_fixture(tmp_path, monkeypatch, phases)
    with pytest.raises(D.PhaseCheckFailed) as e:
        D.phase_check(["2023-05"])
    m = e.value.result["months"]["2023-05"]
    assert m["ok"] is False and m["sess_max_s"] >= 59.99 and abs(m["sess_max_s"] - max(phases)) <= 0.03
    r = D.phase_check(["2023-05"], raise_on_fail=False)
    assert r["failed"] == ["2023-05"] and r["ok"] is False


def test_phase_check_unmeasurable_month_fails(tmp_path, monkeypatch):
    """OFB rows exist but there is no tape to measure against: not proven, so not passed."""
    _phase_fixture(tmp_path, monkeypatch, [59.3])
    monkeypatch.setattr(D, "OFB_TICK_DIR", tmp_path / "nowhere")
    r = D.phase_check(["2023-05"], raise_on_fail=False)
    assert r["failed"] == ["2023-05"] and r["months"]["2023-05"]["ofb_rows"] == 390


def test_phase_check_overnight_bucket_catches_a_late_overnight_snapshot(tmp_path, monkeypatch):
    """The RTH-only check was blind to a snapshot phase that is late only overnight (asia, london, the 03:00 open). The
    overnight minutes are pooled per month: a late overnight book fails the month although RTH passes."""
    monkeypatch.setattr(D, "PHASE_ON_MIN_MINUTES", 300)                    # two synthetic sessions x 180 overnight minutes
    _phase_fixture(tmp_path, monkeypatch, [59.30, 59.30], on_phases=[59.50, 59.50])
    r = D.phase_check(["2023-05"])
    m = r["months"]["2023-05"]
    assert r["ok"] and m["failed_parts"] == [] and m["on_minutes"] == 360 and abs(m["on_phase_s"] - 59.50) <= 0.03
    assert abs(m["phase_s"] - 59.30) <= 0.03 and abs(m["on_margin_s"] - 0.50) <= 0.03 and r["on_range_s"] == [m["on_phase_s"]] * 2


@pytest.mark.parametrize("on", [[60.0, 60.0], [60.3, 60.3]])
def test_phase_check_fails_a_month_whose_overnight_book_is_late(tmp_path, monkeypatch, on):
    monkeypatch.setattr(D, "PHASE_ON_MIN_MINUTES", 300)
    guard = tmp_path / "guard.json"
    monkeypatch.setattr(D, "PHASE_GUARD", guard)
    _phase_fixture(tmp_path, monkeypatch, [59.30, 59.30], on_phases=on)
    with pytest.raises(D.PhaseCheckFailed) as e:
        D.phase_check(["2023-05"], persist=True)                           # persisted BEFORE it raises
    m = e.value.result["months"]["2023-05"]
    assert m["failed_parts"] == ["overnight"] and m["on_phase_s"] >= 59.99 and m["sess_max_s"] < 59.99 and m["ok"] is False
    assert D.guard_months(guard) == ["2023-05"]
    assert D.phase_check(["2023-05"], overnight=False)["ok"]               # the old, RTH-only check passes the same month
    # overnight rows that cannot be measured (too few minutes for the month) are not a pass
    monkeypatch.setattr(D, "PHASE_ON_MIN_MINUTES", 10_000)
    r = D.phase_check(["2023-05"], raise_on_fail=False)
    assert r["months"]["2023-05"]["failed_parts"] == ["overnight"] and r["months"]["2023-05"]["on_phase_s"] is None


@need_ofb
def test_phase_check_in_sample_months():
    """Real data: the vendor phase is constant within a month and differs between months; the latest in-sample
    months sit 0.02-0.08 s before the boundary and still pass."""
    if not (OFB_TICK / "2022" / "01").exists():
        pytest.skip("ofb_tick cache not on this machine")
    r = D.phase_check(["2022-01", "2023-11", "2024-12"])
    m = r["months"]
    assert r["ok"] and r["max_phase_s"] == 59.99
    assert abs(m["2022-01"]["phase_s"] - 59.04) <= 0.04 and m["2022-01"]["sessions"] >= 18
    assert 59.88 <= m["2023-11"]["phase_s"] < 59.99 and 59.90 <= m["2024-12"]["phase_s"] < 59.99
    for v in m.values():
        assert v["sess_max_s"] - v["sess_min_s"] <= 0.08 and v["sess_max_s"] < 59.99 and v["margin_s"] > 0
        # the pooled overnight bucket (evening, asia, london, pre-open, 16:00-16:59) agrees with RTH and is before the boundary
        assert v["failed_parts"] == [] and v["on_minutes"] > 10_000 and abs(v["on_phase_s"] - v["phase_s"]) <= 0.04
        assert v["on_phase_s"] < 59.99 and v["on_margin_s"] > 0


@need_ofb
def test_persisted_in_sample_phase_guard_covers_every_month_and_has_no_failed_month():
    """cache/phase_guard.json (written by `python l2data.py phase`) is what l2sim enforces: all 40 in-sample months checked
    with the overnight bucket, none failed -> no in-sample session runs with the 1 s execution guard."""
    if not D.PHASE_GUARD.exists():
        pytest.skip("phase_guard.json not built on this machine (python l2data.py phase)")
    g = json.loads(D.PHASE_GUARD.read_text())
    ins = {m: v for m, v in g["months"].items() if m <= "2024-12"}
    assert sorted(ins) == [str(x) for x in pd.period_range("2021-09", "2024-12", freq="M")]
    assert all(v["ok"] and v["overnight"] for v in ins.values()) and not [m for m in g["failed"] if m <= "2024-12"]


# ------------------------------------------------------------------------------------------------ FEATURES.md contract
@need_cache
def test_columns_reach_a_family_through_l2sim_as_documented():
    """FEATURES.md: the slice of a session starts 18:01 ET the evening before, rows are contiguous minutes, the newest
    usable row at a decision at T is stamped T - 60 s, and the masked anchors / features are NaN on a roll day."""
    S = pytest.importorskip("l2sim")
    cols = ["t_utc", "et_min", "book_ok", "imb10", "bid_px", "ask_px", "bid_wall_dist", "bid_wall_sz", "f_delta"]
    day = dt.date(2022, 3, 1)
    F = S.L2Features(cols)(day)
    assert set(F.cols) == set(cols)                                    # numeric / bool columns all reach ctx
    assert F.usable_ns[0] == S.et_ns(day - dt.timedelta(days=1), "18:01") and (np.diff(F.usable_ns[:1380]) == S.MIN_NS).all()
    assert F.n_usable(S.et_ns(day, "00:00")) == 360                    # the asia open already has 6 hours of rows
    now = S.et_ns(day, "09:30")
    k = F.n_usable(now) - 1
    assert F.usable_ns[k] == now and F.cols["t_utc"][k] + 60 == now // S.NS and F.cols["et_min"][k] == 570
    ref = D.load_features(day, day, columns=cols).loc[pd.Timestamp("2022-03-01 09:30", tz=D.ET)]
    for c in ("imb10", "bid_px", "ask_px", "bid_wall_dist", "f_delta"):
        assert _eq(F.cols[c][k], ref[c]), c
    wall = F.cols["bid_px"][k] - F.cols["bid_wall_dist"][k] * D.TICK   # the documented wall price
    assert wall <= F.cols["bid_px"][k] < F.cols["ask_px"][k] and wall % D.TICK == 0
    R = S.L2Features(cols)(dt.date(2022, 6, 13))                       # a roll day: book NaN, own flow present
    rth = (R.cols["et_min"] >= 570) & (R.cols["et_min"] < 958) & (R.usable_ns >= S.et_ns(dt.date(2022, 6, 13), "00:00"))
    assert rth.sum() == 388 and not R.cols["book_ok"][rth].any()
    assert np.isnan(R.cols["bid_px"][rth]).all() and np.isnan(R.cols["imb10"][rth]).all()
    assert np.isfinite(R.cols["f_delta"][rth]).mean() > 0.99
