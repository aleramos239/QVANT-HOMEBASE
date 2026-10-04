"""C2 feature-shuffle null (score.c2_donor_map / c2_shuffle / c2_null / C2Features)."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402


def sessions(n=120, start=0):
    return S.in_sample_sessions()[start:start + n]


def table(n_sess=60, minutes=range(570, 600), seed=0, short=None):
    """Synthetic per-minute table: one row per (session, minute). feat_day = a session-specific signal (the 'information'),
    feat_tod = a pure time-of-day profile, px = the price column the family may also read. `short` = {session: n_minutes}."""
    rng = np.random.default_rng(seed)
    rows = []
    for i, d in enumerate(sessions(n_sess)):
        day_sig = rng.normal()
        mins = list(minutes)[: (short or {}).get(d, len(minutes))]
        for m in mins:
            rows.append({"globex_date": dt.date.fromisoformat(d), "date": dt.date.fromisoformat(d), "et_min": m,
                         "feat_day": day_sig + 0.01 * rng.normal(), "feat_tod": float(m), "px": 100.0 + i + 0.1 * m,
                         "ret_fwd": day_sig + 0.1 * rng.normal()})
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime([f"{r['date']} {r['et_min'] // 60:02d}:{r['et_min'] % 60:02d}" for r in rows]).tz_localize("America/New_York").tz_convert("UTC")
    df.index.name = "usable_at"
    return df


# ------------------------------------------------------------------ donor map

def test_donor_map_is_a_seeded_derangement_with_gap():
    ss = sessions(300)
    m = S.c2_donor_map(ss, seed=7)
    assert m == S.c2_donor_map(list(reversed(ss)), seed=7) == S.c2_donor_map(ss, seed=7)      # deterministic, order-free
    assert m != S.c2_donor_map(ss, seed=8)
    assert sorted(m) == sorted(ss) and sorted(m.values()) == sorted(ss)                     # bijection: every session donates once
    pos = {s: i for i, s in enumerate(sorted(ss))}
    gaps = [abs(pos[a] - pos[b]) for a, b in m.items()]
    assert min(gaps) >= 5                                                                    # no fixed point, no neighbour donor
    m1 = S.c2_donor_map(ss, seed=7, min_gap=1)
    assert all(a != b for a, b in m1.items())
    m40 = S.c2_donor_map(ss, seed=7, min_gap=40)
    assert min(abs(pos[a] - pos[b]) for a, b in m40.items()) >= 40


def test_donor_map_golden_values():
    """Pinned draw (numpy default_rng([C2_SEED, seed])): a change of the algorithm or the seed base must be deliberate."""
    m = S.c2_donor_map(sessions(10), seed=1, min_gap=2)
    assert S.C2_SEED == 20261001
    assert m == S.c2_donor_map(sessions(10), seed=1, min_gap=2)
    assert len({(a, b) for a, b in m.items()}) == 10 and all(a != b for a, b in m.items())
    many = {tuple(sorted(S.c2_donor_map(sessions(10), seed=k, min_gap=2).items())) for k in range(30)}
    assert len(many) > 20                                                                    # different seeds, different maps


def test_donor_map_strata_fixed_and_errors():
    ss = sessions(400)
    by_year = S.c2_donor_map(ss, seed=3, strata=lambda s: s[:4])
    assert all(a[:4] == b[:4] and a != b for a, b in by_year.items())
    fixed = ss[10:13]
    m = S.c2_donor_map(ss, seed=3, fixed=fixed)
    assert all(m[f] == f for f in fixed) and not (set(fixed) & {b for a, b in m.items() if a not in fixed})
    assert sorted(m.values()) == sorted(ss)
    with pytest.raises(ValueError):
        S.c2_donor_map(ss[:3], seed=1)                                                       # 3 sessions cannot be >= 5 apart
    with pytest.raises(RuntimeError):
        S.c2_donor_map(ss[:8], seed=1, min_gap=7)                                            # only the two ends are 7 apart
    with pytest.raises(S.HoldoutError):
        S.c2_donor_map(ss + ["2025-01-02", "2025-01-03"], seed=1)
    ho = [d.isoformat() for d in pd.bdate_range("2025-01-02", periods=40).date]
    assert len(S.c2_donor_map(ho, seed=1, allow_holdout=True)) == 40                         # holdout stage: explicit switch only


# ------------------------------------------------------------------ shuffle

def test_shuffle_replaces_features_with_the_donors_same_minute():
    df = table()
    out = S.c2_shuffle(df, ["feat_day", "feat_tod"], seed=5)
    dm = out.attrs["c2_map"]
    assert out.index.equals(df.index) and list(out.columns) == list(df.columns) + ["c2_donor"]
    for c in ("globex_date", "date", "et_min", "px", "ret_fwd"):
        assert out[c].equals(df[c])                                                         # price / time / everything else untouched
    key = df.set_index([df["globex_date"].map(str), "et_min"])["feat_day"]
    exp = [key[(dm[str(s)], m)] for s, m in zip(df["globex_date"], df["et_min"])]
    assert np.array_equal(out["feat_day"].to_numpy(), np.array(exp))
    assert np.array_equal(out["c2_donor"].to_numpy(), df["globex_date"].map(lambda d: dm[str(d)]).to_numpy())
    assert np.array_equal(out["feat_tod"].to_numpy(), df["feat_tod"].to_numpy())             # a pure time-of-day feature is invariant
    assert sorted(out["feat_day"]) == sorted(df["feat_day"])                                 # pooled distribution exactly preserved
    assert out.attrs["c2_coverage"] == 1.0 and out.attrs["c2_valid_null"] == out.attrs["c2_valid_real"] == 1.0
    assert not df.equals(out) and "c2_donor" not in df.columns                               # the input is not modified
    assert S.c2_shuffle(df, ["feat_day"], seed=5)["feat_day"].equals(out["feat_day"])        # deterministic
    assert not S.c2_shuffle(df, ["feat_day"], seed=6)["feat_day"].equals(out["feat_day"])


def test_shuffle_kills_session_information_but_keeps_time_of_day():
    df = table(n_sess=200, seed=2)

    def family(f):                                                 # f(features) -> signals: long when the feature is positive
        return np.sign(f["feat_day"].to_numpy())

    real = float((family(df) * df["ret_fwd"]).mean())
    nulls = S.c2_null(family, df, ["feat_day"], seeds=range(1, 9))
    null_pnl = [float((sig * df["ret_fwd"]).mean()) for _, sig in nulls]
    assert [s for s, _ in nulls] == list(range(1, 9))
    assert real > 0.6 and abs(np.mean(null_pnl)) < 0.1 and max(abs(x) for x in null_pnl) < 0.25
    tod = S.c2_null(lambda f: (f["feat_tod"] > 584).to_numpy(), df, ["feat_tod"], seeds=(1, 2))
    assert all(np.array_equal(sig, (df["feat_tod"] > 584).to_numpy()) for _, sig in tod)   # a timing-only family is unchanged by C2


def test_shuffle_nan_rules_dead_sessions_and_short_donors():
    ss = sessions(60)
    df = table(short={ss[20]: 10})                                 # one half-day session: 10 of 30 minutes
    df.loc[df["globex_date"] == dt.date.fromisoformat(ss[7]), "feat_day"] = np.nan          # a dead session (roll block)
    df.iloc[5, df.columns.get_loc("feat_day")] = np.nan            # one masked minute in a live session
    out = S.c2_shuffle(df, ["feat_day"], seed=11)
    dm = out.attrs["c2_map"]
    assert out.attrs["c2_dead"] == [ss[7]] and dm[ss[7]] == ss[7] and ss[7] not in [v for k, v in dm.items() if k != ss[7]]
    assert out.loc[out["globex_date"] == dt.date.fromisoformat(ss[7]), "feat_day"].isna().all()
    assert np.isnan(out["feat_day"].iloc[5])                       # keep_nan: the null never trades where the real family cannot
    recv = [k for k, v in dm.items() if v == ss[20]][0]            # the session that receives the half day
    got = out.loc[out["globex_date"] == dt.date.fromisoformat(recv), "feat_day"]
    assert got.notna().sum() <= 10 and got.isna().sum() >= 20 and out.attrs["c2_coverage"] < 1.0
    assert out.attrs["c2_valid_null"] < out.attrs["c2_valid_real"] < 1.0
    free = S.c2_shuffle(df, ["feat_day"], seed=11, keep_nan=False)
    donor5 = dm[str(df["globex_date"].iloc[5])]
    assert free["feat_day"].iloc[5] == df.loc[(df["globex_date"] == dt.date.fromisoformat(donor5)) & (df["et_min"] == df["et_min"].iloc[5]), "feat_day"].iloc[0]


def test_shuffle_sessions_argument_and_custom_keys():
    df = table(n_sess=40)
    ss = sessions(40)
    out = S.c2_shuffle(df, ["feat_day"], seed=3, sessions=ss[:30])
    dm = out.attrs["c2_map"]
    assert all(dm[s] == s for s in ss[30:]) and all(dm[s] != s and dm[s] in ss[:30] for s in ss[:30])
    assert out.attrs["c2_fixed"] == ss[30:]
    alt = df.rename(columns={"globex_date": "sess_day", "et_min": "hhmm"})
    o2 = S.c2_shuffle(alt, ["feat_day"], seed=3, session_col="sess_day", tod_col="hhmm", sessions=ss[:30])
    assert np.array_equal(o2["feat_day"].to_numpy(), out["feat_day"].to_numpy())
    bare = df[["feat_day", "px"]]                                   # no key columns: derived from the tz-aware index (ET date, minute)
    o3 = S.c2_shuffle(bare, "feat_day", seed=3, sessions=ss[:30])
    assert np.array_equal(o3["feat_day"].to_numpy(), out["feat_day"].to_numpy())
    given = S.c2_shuffle(df, ["feat_day"], seed=999, donor_map=dm)
    assert np.array_equal(given["feat_day"].to_numpy(), out["feat_day"].to_numpy())


def test_shuffle_guards():
    df = table(n_sess=20)
    with pytest.raises(ValueError):
        S.c2_shuffle(df, ["nope"], seed=1)
    with pytest.raises(ValueError):
        S.c2_shuffle(df, ["et_min"], seed=1)
    with pytest.raises(ValueError):
        S.c2_shuffle(pd.concat([df, df.iloc[:3]]), ["feat_day"], seed=1)                      # duplicate (session, minute)
    with pytest.raises(ValueError):
        S.c2_shuffle(df.reset_index(drop=True)[["feat_day", "px"]], ["feat_day"], seed=1)     # no keys, no time index
    ho = df.copy()
    ho.iloc[-1, ho.columns.get_loc("date")] = dt.date(2025, 1, 2)
    with pytest.raises(S.HoldoutError):
        S.c2_shuffle(ho, ["feat_day"], seed=1)
    # a Globex session LABEL after the last in-sample ROW date (the 2024-12-31 evening belongs to session 2025-01-01) is fine:
    ev = df.copy()
    last = ev["globex_date"] == ev["globex_date"].max()
    ev.loc[last, "globex_date"] = dt.date(2025, 1, 1)
    out = S.c2_shuffle(ev, ["feat_day"], seed=1)
    assert out.attrs["c2_map"]["2025-01-01"] == "2025-01-01" and "2025-01-01" in out.attrs["c2_fixed"]
    assert out.loc[last.to_numpy(), "feat_day"].equals(ev.loc[last, "feat_day"])


# ------------------------------------------------------------------ the l2sim loader on the real data-layer cache

def test_c2features_loader_on_the_data_layer():
    l2data = pytest.importorskip("l2data")
    l2sim = pytest.importorskip("l2sim")
    cols, shuf = ["imb10", "f_delta", "f_c"], ["imb10", "f_delta"]
    if not hasattr(l2sim, "L2Features"):
        pytest.skip("l2sim has no L2Features loader")
    try:                                                            # the table exactly as l2sim.L2Features loads it
        base = l2data.load_features(l2sim.TABLE_START, l2sim.IN_SAMPLE[1], columns=cols + ["globex_date", "et_min", "date"])
    except FileNotFoundError:
        pytest.skip("data-layer cache not built")
    null = S.C2Features(cols, shuf, seed=1)
    fr = null.frame()
    dm = fr.attrs["c2_map"]
    assert fr.index.equals(base.index) and fr["f_c"].equals(base["f_c"])                    # price column: the receiving session's own
    cal = set(S.in_sample_sessions())
    moved = {k for k, v in dm.items() if k != v}
    assert moved <= cal and len(moved) >= 750 and all(dm[k] in cal for k in moved)           # only sim sessions are permuted
    assert not (set(fr.attrs["c2_dead"]) & moved)
    assert abs(fr.attrs["c2_valid_null"] - fr.attrs["c2_valid_real"]) < 0.02                 # same opportunity set (within 2 pp)
    d = dt.date(2023, 3, 15)
    donor = dt.date.fromisoformat(dm[d.isoformat()])
    assert donor != d and abs((donor - d).days) >= 5
    a, b = fr[fr["globex_date"] == d], base[base["globex_date"] == donor].set_index("et_min")
    exp = b["imb10"].reindex(a["et_min"]).to_numpy()
    exp = np.where(base.loc[a.index, "imb10"].isna().to_numpy(), np.nan, exp)
    assert np.array_equal(a["imb10"].to_numpy(), exp, equal_nan=True) and np.isfinite(a["imb10"]).mean() > 0.8
    # same slicing as the real loader: identical usable_ns and price, different book / flow columns
    real_f, null_f = l2sim.L2Features(cols)(d), null(d)
    assert np.array_equal(real_f.usable_ns, null_f.usable_ns) and np.array_equal(real_f.cols["f_c"], null_f.cols["f_c"], equal_nan=True)
    assert not np.array_equal(real_f.cols["imb10"], null_f.cols["imb10"], equal_nan=True)
    import pickle
    assert pickle.loads(pickle.dumps(null)).seed == 1                                        # l2sim.run ships the loader to spawn workers
    with pytest.raises(Exception):
        null(dt.date(2025, 1, 2))                                                            # sealed
    with pytest.raises(ValueError):
        S.C2Features(cols, ["not_loaded"], seed=1)
