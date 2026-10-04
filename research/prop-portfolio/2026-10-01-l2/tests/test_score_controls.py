"""CONTROL lens of the score.py verification (2026-10-01): the two mandatory controls must be free of leakage and bias.

  calendar   the in-sample calendar is R's EXACTLY and is the one every component uses (sim, data layer, apex300)
  C2         feature-shuffle null: donor map (bijection, no session keeps a real feature, in-sample donors only, seeded and
             process-independent), price-carrying columns CANNOT be shuffled, C2Features == l2sim.L2Features in everything
             but the shuffled columns, a timing-only family is untouched by the null
  C1         day-matched random control: same (date, session) trade counts, no pool trade reused inside a draw, fallbacks from
             the same session only, sealed pool, seeds
  apex300    search_funded / score_funded use L/apex300's grid, flags and compliance gate (never R's 50K-scaled constants)
"""
import datetime as dt
import json
import pickle
import subprocess
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

pytestmark = pytest.mark.usefixtures("trades_tmp")      # exports go to a directory of this module's own, never to L/trades

E, F, P = S.E, S.F, S.P
KEY, SRC, SESS = "hm2-straddle-tf30#10", S.BASELINE["flex_eval"]["src"], "nyam"
DON, DON_SRC = "fp-donchian-tf15#1", S.BASELINE["apex_pa_funded"]["src"]
COLS = ["imb10", "imb3", "depth10_rel20d", "bid10_rel15", "f_delta", "f_volume", "f_c", "f_o", "bid_px", "ask_px"]
FEATS = ["imb10", "imb3", "depth10_rel20d", "bid10_rel15", "f_delta", "f_volume"]


@pytest.fixture(scope="module")
def files():
    for k, s in ((KEY, SRC), (DON, DON_SRC)):
        S.export_bundle(s, S.export_name(k))
    return {KEY: "file:" + S.export_name(KEY), DON: "file:" + S.export_name(DON)}


@pytest.fixture(scope="module")
def layer():
    l2data = pytest.importorskip("l2data")
    l2sim = pytest.importorskip("l2sim")
    try:
        base = l2data.load_features(l2sim.TABLE_START, l2sim.IN_SAMPLE[1], columns=COLS + ["globex_date", "et_min", "date"])
    except FileNotFoundError:
        pytest.skip("data-layer cache not built")
    return l2data, l2sim, base


# ------------------------------------------------------------------ calendar

def test_in_sample_calendar_is_Rs_exactly_and_shared_by_every_component():
    cal = S.in_sample_sessions()
    raw = json.loads((S.R / "bundles_cache" / "nq_sessions.json").read_text())
    assert cal == [d for d in raw if "2021-09-22" <= d <= "2024-12-31"] == raw           # R's cache holds exactly the in-sample sessions
    assert len(cal) == 825 and cal == sorted(set(cal)) and max(cal) < S.HOLDOUT
    assert cal == E.tape_sessions("2021-01-01", "2024-12-31")                            # R's own calendar function
    assert [dt.date.fromordinal(int(o)).isoformat() for o in P.Ctx.calendar()] == cal    # ... and portfolio.py's
    assert S.make_calendar().iso == cal and S.make_calendar().S == 821
    port = E.build({"members": [{"src": SRC, "sess": "all", "micros": 10}]})             # R's Port of a native bundle
    assert port.iso == cal
    l2sim = pytest.importorskip("l2sim")
    assert [d.isoformat() for d in l2sim.sessions(*l2sim.IN_SAMPLE)] == cal              # the sim's sessions (tape file names)
    ax = pytest.importorskip("apex300")
    assert ax.default_calendar(ax.IS_START, ax.IS_END) == cal


def test_every_sim_session_has_feature_rows(layer):
    _, _, base = layer
    gs = {str(x) for x in base["globex_date"].unique()}
    assert set(S.in_sample_sessions()) <= gs and str(base["date"].max()) <= "2024-12-31" and max(gs) < S.HOLDOUT


# ------------------------------------------------------------------ C2: donor map

def _map_stats(dm, cal):
    pos = {s: i for i, s in enumerate(sorted(dm))}
    moved = {k: v for k, v in dm.items() if k != v}
    gaps = np.array([abs(pos[k] - pos[v]) for k, v in moved.items()])
    return moved, gaps


@pytest.mark.parametrize("strata", [None, "year"])
def test_c2_null_moves_every_sim_session_to_another_in_sample_session(layer, strata):
    cal = S.in_sample_sessions()
    maps = []
    for seed in (1, 2, 3):
        a = S.C2Features(COLS, seed=seed, strata=strata).frame().attrs
        dm = a["c2_map"]
        moved, gaps = _map_stats(dm, cal)
        assert set(moved) == set(cal)                                   # NO sim session keeps a real feature (no same-session reuse)
        assert sorted(moved.values()) == sorted(moved)                  # bijection: every session donates exactly once
        assert set(moved.values()) <= set(cal) and max(moved.values()) < S.HOLDOUT       # donors: in-sample sim sessions only
        assert set(a["c2_fixed"]) == set(dm) - set(cal) == set(a["c2_dead"])             # only the non-sim holiday stubs stay put
        assert (gaps >= 1).all() and (gaps < 5).sum() <= 12             # week gap; a few sessions of the small special groups are closer
        special = set(a["c2_partial_sessions"])                         # roll block / warm-up groups: permuted inside the group
        assert (gaps[[k not in special for k in moved]] >= 5).all() and 30 <= len(special) <= 80
        if strata == "year":
            assert all(k[:4] == v[:4] for k, v in moved.items())
        # opportunity set: per feature the null has the same rows available within 1 pp (reported, never larger than the real)
        for c, (real, null) in a["c2_valid"].items():
            assert 0.0 <= real - null < 0.01, (c, real, null)
        assert a["c2_coverage"] > 0.995
        maps.append(dm)
    assert maps[0] != maps[1] != maps[2]


def test_c2_partly_dead_sessions_are_permuted_inside_their_group(layer):
    _, _, base = layer
    fr = S.C2Features(COLS, seed=4).frame()
    a, dm = fr.attrs, fr.attrs["c2_map"]
    assert a["c2_partial"].get("depth10_rel20d") == 10                              # the 20-day normalisation's first sessions
    book = "+".join(c for c in FEATS if not c.startswith("f_"))
    assert a["c2_partial"].get(book, 0) >= 30                                       # roll block: book masked, flow live
    by = base.groupby(base["globex_date"].map(str))
    dead_book = set(by["imb10"].apply(lambda v: v.notna().sum() == 0).pipe(lambda x: x[x].index)) & set(S.in_sample_sessions())
    assert len(dead_book) >= 30
    for s in dead_book:                                                             # a roll session receives ANOTHER roll session's flow
        assert dm[s] != s and dm[s] in dead_book
        got = fr.loc[fr["globex_date"].map(str) == s]
        assert got["imb10"].isna().all() and got["f_delta"].notna().any()
        don = base.loc[base["globex_date"].map(str) == dm[s]].set_index("et_min")["f_delta"]
        exp = don.reindex(got["et_min"]).to_numpy()
        exp = np.where(base.loc[got.index, "f_delta"].isna().to_numpy(), np.nan, exp)
        assert np.array_equal(got["f_delta"].to_numpy(), exp, equal_nan=True)
    live = set(S.in_sample_sessions()) - dead_book
    assert not ({dm[s] for s in live} & dead_book)                                  # a live session never receives a dead donor


def test_c2_map_is_identical_in_another_process_and_hash_seed(layer):
    """Workers are spawned: every process must build the same donor map (no dependence on set / dict hash order)."""
    code = ("import sys, json, hashlib; sys.path.insert(0, %r); import score as S; "
            "a = S.C2Features(%r, seed=3).frame().attrs; "
            "print(hashlib.sha1(json.dumps(sorted(a['c2_map'].items())).encode()).hexdigest())") % (str(L), COLS)
    import hashlib
    import os
    here = hashlib.sha1(json.dumps(sorted(S.C2Features(COLS, seed=3).frame().attrs["c2_map"].items())).encode()).hexdigest()
    for hs in ("0", "12345"):
        r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": hs})
        assert r.returncode == 0, r.stderr[-2000:]
        assert r.stdout.strip().splitlines()[-1] == here


# ------------------------------------------------------------------ C2: price columns cannot be shuffled

def _toy(n_sess=40):
    rows = []
    rng = np.random.default_rng(0)
    for i, d in enumerate(S.in_sample_sessions()[:n_sess]):
        for m in range(570, 630):
            px = 15000.0 + 20 * i + rng.normal()
            rows.append({"globex_date": dt.date.fromisoformat(d), "date": dt.date.fromisoformat(d), "et_min": m, "imb10": rng.normal(),
                         "f_delta": rng.normal() * 50, "f_volume": abs(rng.normal()) * 3000 + 1500, "bid_top10": 40 + abs(rng.normal()) * 30,
                         "f_c": px, "f_o": px, "f_h": px + 1, "f_l": px - 1, "bid_px": px - 0.25, "ask_px": px, "anchor": px,
                         "book_ok": True})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("col", ["f_c", "f_o", "f_h", "f_l", "bid_px", "ask_px", "book_ok", "date", "globex_date", "et_min"])
def test_price_tag_and_flag_columns_cannot_be_shuffled(col):
    df = _toy()
    with pytest.raises(ValueError):
        S.c2_shuffle(df, ["imb10", col], seed=1)
    with pytest.raises(ValueError):
        S.c2_shuffle(df, col, seed=1)
    assert S.c2_is_fixed(col)


def test_an_unlisted_price_level_column_is_refused_by_the_level_check():
    df = _toy()
    assert not S.c2_is_fixed("anchor")
    with pytest.raises(ValueError, match="price level"):
        S.c2_shuffle(df, ["imb10", "anchor"], seed=1)
    out = S.c2_shuffle(df, ["imb10", "f_delta", "f_volume", "bid_top10"], seed=1)           # sizes / volumes / deltas are not prices
    for c in ("f_c", "f_o", "f_h", "f_l", "bid_px", "ask_px", "anchor", "book_ok"):
        assert out[c].equals(df[c])                                                         # the receiving session's own, bit for bit
    assert not out["imb10"].equals(df["imb10"]) and not out["f_volume"].equals(df["f_volume"])
    assert S.c2_shuffle(df.rename(columns={"anchor": "level"}), ["level"], seed=1, level_check=False) is not None
    for name in ("mid_px", "entry_price", "vwap", "f_vwap", "wall_px", "close", "f_close"):
        assert S.c2_is_fixed(name), name
    for name in ("imb10", "imb3", "depth10_rel20d", "bid10_rel15", "f_delta", "f_cum_delta", "f_sweep_buy_vol", "bid_wall_dist",
                 "spread_ticks", "f_big_order_levels", "rt_pulled_bid", "bid_top1"):
        assert not S.c2_is_fixed(name), name


def test_data_layer_price_anchors_tags_and_flags_are_all_fixed(layer):
    l2data, _, _ = layer
    for c in list(getattr(l2data, "PX_COLS", [])) + list(l2data.TAG_COLS) + list(l2data.FLAG_COLS) + ["f_o", "f_h", "f_l", "f_c"]:
        assert S.c2_is_fixed(c), c
    feats = [c for c in l2data.BOOK_COLS + l2data.FLOW_COLS + l2data.RT_COLS if c not in ("f_o", "f_h", "f_l", "f_c")]
    assert feats and not [c for c in feats if S.c2_is_fixed(c)]                             # every real feature stays shufflable


def test_c2features_shuffles_every_feature_it_loads_and_never_a_price():
    c2 = S.C2Features(COLS, seed=1)
    assert c2.shuffle_cols == tuple(FEATS)                                                  # auto: all features, no price / anchor
    for bad in (["imb10", "f_c"], ["bid_px"], "f_o"):
        with pytest.raises(ValueError, match="price"):
            S.C2Features(COLS, bad, seed=1)
    with pytest.raises(ValueError, match="REAL"):                                           # a feature left real = a leaky null
        S.C2Features(COLS, ["imb10"], seed=1)
    part = S.C2Features(COLS, ["imb10"], seed=1, allow_partial=True)
    assert part.shuffle_cols == ("imb10",) and part.partial
    with pytest.raises(ValueError):
        S.C2Features(["f_c", "bid_px"], seed=1)                                             # nothing to shuffle
    with pytest.raises(ValueError):
        S.C2Features(COLS, seed=1, strata="month")
    again = pickle.loads(pickle.dumps(S.C2Features(COLS, seed=7, strata="year")))           # ships to spawn workers
    assert (again.seed, again.strata, again.shuffle_cols, again.columns) == (7, "year", tuple(FEATS), tuple(COLS))


# ------------------------------------------------------------------ C2Features == L2Features except the shuffled columns

def test_c2features_matches_l2features_slicing_and_fixed_columns(layer):
    l2data, l2sim, base = layer
    cal = S.in_sample_sessions()
    null = S.C2Features(COLS, seed=2)
    fr = null.frame()
    dm = fr.attrs["c2_map"]
    rolls = sorted(l2sim.default_rolls("NQ"))
    days = [cal[0], cal[1], "2022-03-14", "2023-03-15", "2023-07-03", "2024-11-29", cal[-1], str(rolls[3])]
    days.append(next(d for d in cal if dt.date.fromisoformat(d).weekday() == 0 and d > "2022-06-01"))       # a Monday (Sunday-evening lookback)
    for lookback in (360, 60, 0):
        real_l, null_l = l2sim.L2Features(COLS, lookback_min=lookback), S.C2Features(COLS, seed=2, lookback_min=lookback)
        for iso in days:
            d = dt.date.fromisoformat(iso)
            a, b = real_l(d), null_l(d)
            assert (a is None) == (b is None)
            assert type(b) is l2sim.Features and np.array_equal(a.usable_ns, b.usable_ns) and set(a.cols) == set(b.cols) == set(COLS)
            for c in ("f_c", "f_o", "bid_px", "ask_px"):                                     # prices / anchors: bit-identical
                assert np.array_equal(a.cols[c], b.cols[c], equal_nan=True), (iso, c)
                assert a.cols[c].dtype == b.cols[c].dtype
            for c in FEATS:                                                                  # features: same dtype, donor's values
                assert a.cols[c].dtype == b.cols[c].dtype
            if lookback == 360 and iso not in (cal[0],):
                assert not np.array_equal(a.cols["f_delta"], b.cols["f_delta"], equal_nan=True), iso
    # the null's values are the donor session's values at the same ET minute (whole Globex session = one donor, incl. the evening)
    d = dt.date(2023, 3, 15)
    f = S.C2Features(COLS, seed=2)(d)
    lo = l2sim.et_ns(d, "00:00") - 360 * l2sim.MIN_NS
    rows = fr.loc[(fr.index.asi8 >= lo) & (fr.index.asi8 < l2sim.et_ns(d + dt.timedelta(days=1), "00:00"))]
    assert np.array_equal(rows.index.asi8, f.usable_ns)
    sess = rows["globex_date"].map(str).to_numpy()
    assert set(sess) == {"2023-03-15", "2023-03-16"} and (sess[:360] == "2023-03-15").all()   # evening lookback + day = ONE session
    donor = base.loc[base["globex_date"].map(str) == dm["2023-03-15"]].set_index("et_min")
    own = rows.loc[sess == "2023-03-15"]
    for c in ("imb10", "f_delta"):
        exp = donor[c].reindex(own["et_min"]).to_numpy()
        exp = np.where(base.loc[own.index, c].isna().to_numpy(), np.nan, exp)
        assert np.array_equal(f.cols[c][: len(own)], exp, equal_nan=True), c
    assert abs((dt.date.fromisoformat(dm["2023-03-15"]) - d).days) >= 5
    with pytest.raises(Exception):
        null(dt.date(2025, 1, 2))                                                            # sealed
    assert max(str(x) for x in fr["date"].unique()) < S.HOLDOUT


def test_c2features_real_is_the_sim_loader(layer):
    _, l2sim, _ = layer
    c2 = S.C2Features(COLS, seed=1, lookback_min=45, mask_bad_book=True)
    r = c2.real()
    assert type(r) is l2sim.L2Features and r.columns == c2.columns and r.lookback_min == 45
    assert callable(getattr(l2sim.L2Features, "_frame", None))                                # the hook C2Features swaps the table through


# ------------------------------------------------------------------ C2 end to end through the simulator

def _days(n=40, start=300):
    return S.in_sample_sessions()[start:start + n]


def test_timing_only_family_is_untouched_by_the_null_and_a_feature_family_is_not(layer):
    _, l2sim, _ = layer
    l2ref = pytest.importorskip("l2ref")
    if S.blackout_wait_s():
        pytest.skip("inside an offline compute window")
    cols = ["imb10", "f_delta", "f_c"]
    days = _days()

    class ImbToy(l2sim.Template):                               # trades on the book: long when the top-10 imbalance is positive
        DEFAULTS = {"k": 0.15}

        def fam_signal(self, ctx):
            v = ctx.feat("imb10")
            if v is not None and v == v and abs(v) >= self.p["k"]:
                self._mkt(ctx, "long" if v > 0 else "short")

    try:
        probe_real = l2sim.run(l2ref.FeatureProbe, {}, days=days, workers=1, features=l2sim.L2Features(cols))
        probe_null = l2sim.run(l2ref.FeatureProbe, {}, days=days, workers=1, features=S.C2Features(cols, seed=1))
        toy_real = l2sim.run(ImbToy, {"tf": "5", "sess": "nyam", "max_tr": 1}, days=days, workers=1, features=l2sim.L2Features(cols))
        toy_null = [l2sim.run(ImbToy, {"tf": "5", "sess": "nyam", "max_tr": 1}, days=days, workers=1, features=S.C2Features(cols, seed=k))
                    for k in (1, 2)]
    except FileNotFoundError as e:
        pytest.skip(f"tape / cache not available: {e}")
    key = ("date", "side", "entry_price", "exit_price", "entry_ms", "exit_ms", "net")

    def led(res):
        return [tuple(t[k] for k in key) for t in res["trades"]]

    assert len(probe_real["trades"]) >= 30 and led(probe_real) == led(probe_null)            # timing-only: identical ledger
    tags = [(a.get("tag") or {}).get("imb10") for a in probe_real["trades"]], [(a.get("tag") or {}).get("imb10") for a in probe_null["trades"]]
    if any(t is not None for t in tags[0]):
        assert tags[0] != tags[1]                                                            # ... while the features it saw DID change
    lift = S.lift_vs_control(probe_real, [probe_null], "lucid", {}, micros=20, mode="direct", boots=0, calendar=days)
    assert lift["lift"] == 0.0 and all(lift["models"][m]["lift"] == 0.0 for m in S.MODELS)
    assert len(toy_real["trades"]) >= 20 and all(led(n) != led(toy_real) for n in toy_null) and led(toy_null[0]) != led(toy_null[1])
    for n in toy_null:                                                                       # same family, same opportunity count +- 25%
        assert abs(len(n["trades"]) - len(toy_real["trades"])) <= 0.25 * len(toy_real["trades"]) + 3
    out = S.lift_vs_control(toy_real, toy_null, "lucid", {}, micros=20, sess="nyam", mode="direct", boots=0, calendar=days)
    assert out["K"] == 2 and out["mode"] == "direct" and out["ctrl_trades"] == [len(n["trades"]) for n in toy_null]
    assert S.load_trades(toy_real, calendar=days).range == ("2021-09-22", "2024-12-31")      # an l2sim result: its run range is carried
    with pytest.raises(ValueError, match="covered 40 sessions"):                             # ... and a subset run needs its calendar
        S.load_trades(toy_real)
    assert S.load_trades(toy_real, calendar=days).label.startswith("ImbToy|") and S.load_trades(toy_real, calendar=days, label="x").label == "x"


def test_l2sim_result_dict_is_refused_when_sessions_were_dropped_or_holdout():
    rows = json.loads(S.trade_file("file:" + S.export_name(KEY)).read_text()) if S.trade_file(S.export_name(KEY)).exists() else None
    if rows is None:
        S.export_bundle(SRC, S.export_name(KEY))
        rows = json.loads(S.trade_file(S.export_name(KEY)).read_text())
    res = {"trades": rows[:200], "skipped": [], "no_trade": [], "sessions": 825, "used": 820, "skipped_by_error": 0,
           "meta": {"range": {"start": "2021-09-22", "end": "2024-12-31", "holdout": False}}}
    assert S.load_trades(res).n == 200
    with pytest.raises(ValueError, match="DROPPED"):
        S.load_trades({**res, "skipped_by_error": 3})
    assert S.load_trades({**res, "skipped_by_error": 3}, strict=False).n == 200
    with pytest.raises(S.HoldoutError):
        S.load_trades({**res, "meta": {"range": {"start": "2021-09-22", "end": "2025-06-30", "holdout": True}}})
    short = S.score_eval({**res, "meta": {"range": {"start": "2021-09-22", "end": "2022-03-31", "holdout": False}}}, "lucid", {}, micros=20, boots=0)
    assert short["window"]["end"] == "2022-03-31" and short["window"]["sessions"] < 200       # scored on the span the run covered


# ------------------------------------------------------------------ C1: day-matched random control

def _pool(man):
    return [man["controls"][i]["in_sample_src"] for i in man["configs"][KEY]["ctrl_eval"]["ids"]]


@pytest.fixture(scope="module")
def man():
    p = S.R / "out" / "holdout_manifest.json"
    if not p.exists():
        pytest.skip("R/out/holdout_manifest.json not found")
    return json.loads(p.read_text())


def test_c1_draws_match_the_config_day_by_day_without_reuse_or_leak(files, man):
    pool_srcs = _pool(man)
    pool = E.concat_tr([S.load_trades(s) for s in pool_srcs])
    tr = S.load_trades(files[KEY])
    m = E._sess_mask(tr, SESS)
    cs = S.daymatched(files[KEY], pool_srcs, sess=SESS, K=6, seed=11)
    cal = set(S.make_calendar().cal.tolist())
    cfg_counts = dict(zip(*np.unique(tr.date[m], return_counts=True)))
    for c in cs:
        assert len(set(c["pi"].tolist())) == len(c["pi"])                       # a pool trade is used at most once per draw
        assert c["short"] == 0 and c["n"] == int(m.sum())
        assert dict(zip(*np.unique(c["date"], return_counts=True))) == cfg_counts            # same trades per (date, session)
        assert set(c["sess"].tolist()) == {E.SESS_CODE[SESS]}                   # control trades come from the SAME session
        assert set(c["date"].tolist()) <= cal and int(c["date"].max()) < S._HOLDOUT_ORD
        own = ~c["fb"]
        assert np.array_equal(pool.date[c["pi"]][own], c["date"][own])          # not a fallback: the pool trade of that very date
        shift = c["te"] - pool.te[c["pi"]]
        assert (shift[own] == 0).all() and (shift % E.DAY_MS == 0).all()        # fallbacks are moved by whole days only
        assert c["fb_share"] <= 0.05
        mod = np.array([(lambda a: a.hour * 60 + a.minute)(dt.datetime.fromtimestamp(t / 1000, E.ET)) for t in c["te"][own]])
        assert ((mod >= E.SESS[SESS][0]) & (mod < E.SESS[SESS][1])).all()
    assert len({tuple(c["pi"].tolist()) for c in cs}) == 6                      # K different draws
    again = S.daymatched(files[KEY], pool_srcs, sess=SESS, K=6, seed=11)
    assert all(np.array_equal(a["pi"], b["pi"]) for a, b in zip(cs, again))     # seeded
    other = S.daymatched(files[KEY], pool_srcs, sess=SESS, K=6, seed=12)
    assert not all(np.array_equal(a["pi"], b["pi"]) for a, b in zip(cs, other))


def test_c1_default_seed_names_the_config_not_the_container(files, man):
    assert S.default_seed("cfg", "nyam+pm") == S.default_seed("cfg", ["nyam", "pm"]) == S.default_seed("cfg", ("nyam", "pm"))
    assert S.default_seed("cfg", None) == S.default_seed("cfg", "all") != S.default_seed("cfg2", "all")
    rows = json.loads(S.trade_file(files[KEY]).read_text())
    rules = {"day_lock": 750, "day_take": 1500, "target_take": 1}
    kw = dict(micros=40, sess=SESS, K=3, boots=0)
    a = S.lift_vs_control(rows, _pool(man), "lucid", rules, label=KEY, **kw)                 # an in-memory list, named
    b = S.lift_vs_control(files[KEY], _pool(man), "lucid", rules, seed=S.default_seed(KEY, SESS), **kw)
    assert a["seed"] == b["seed"] == S.default_seed(KEY, SESS) and a["lift"] == b["lift"] and a["ctrl_p5_each"] == b["ctrl_p5_each"]
    c = S.lift_vs_control(rows, _pool(man), "lucid", rules, **kw)                            # unnamed: the 'inline' seed
    assert c["seed"] == S.default_seed("inline", SESS) != a["seed"]
    assert a["fallback_share"] <= 0.05 and a["short"] == 0 and a["ctrl_empty"] == 0


def test_c1_pool_resolver_is_Rs_catalog(man):
    for tf in ("1", "5", "15"):                                                  # the screen defaults (atr 1.5 x 2R) have exact pools
        pl = S.c1_pool({"tf": tf})
        assert pl["exact"] and pl["flag"] == "" and len(pl["srcs"]) == 6 and pl["profile"]["tf"] == int(tf)
        assert all(S.load_trades(x).n > 1000 for x in pl["srcs"])                # in-sample tester bundles (the loader refuses 2025+)
    pl = S.c1_pool({"tf": "30", "stop_val": 3.0, "tgt_r": 2.0})                  # the approved straddle's exit profile
    assert pl["exact"] and set(pl["srcs"]) == set(_pool(man))
    assert not S.c1_pool({"tf": "1", "trail_atr": 2.0})["exact"] and "NEAREST" in S.c1_pool({"tf": "1", "trail_atr": 2.0})["flag"]


def test_c1_pool_is_sealed_and_portfolios_are_refused(files, man):
    rows = json.loads(S.trade_file(files[KEY]).read_text())
    bad = [dict(r) for r in rows[:50]]
    bad[-1].update(date="2025-01-02", entry_ms=bad[-1]["entry_ms"] + 3 * 365 * 86_400_000, exit_ms=bad[-1]["exit_ms"] + 3 * 365 * 86_400_000)
    with pytest.raises(S.HoldoutError):
        S.lift_vs_control(files[KEY], [bad], "lucid", {}, micros=40, sess=SESS, K=2, boots=0)
    with pytest.raises(S.HoldoutError):
        S.daymatched(files[KEY], [bad], sess=SESS, K=2)
    with pytest.raises(ValueError, match="ONE config"):
        S.lift_vs_control([{"src": files[KEY], "sess": SESS, "micros": 20}], _pool(man), "lucid", {}, K=2, boots=0)


def test_direct_control_without_trades_counts_as_never_passing(files):
    rules = {"day_lock": 750, "day_take": 1500, "target_take": 1}
    rows = json.loads(S.trade_file(files[KEY]).read_text())
    pm_only = [rows[i] for i in np.flatnonzero(S.load_trades(rows).sess == E.SESS_CODE["pm"])[:5]]      # a 'null' that never trades in nyam
    real = S.score_eval(files[KEY], "lucid", rules, micros=40, sess=SESS, boots=0)
    out = S.lift_vs_control(files[KEY], [pm_only, files[KEY]], "lucid", rules, micros=40, sess=SESS, mode="direct", boots=0)
    assert out["ctrl_empty"] == 1 and out["K"] == 2
    assert out["ctrl_p5_each"] == [0.0, real["p5"]] and out["lift"] == pytest.approx(real["p5"] / 2, abs=1e-12)


# ------------------------------------------------------------------ Apex 300K: grid, flags, gate, start states, baseline

def test_apex300_search_uses_the_300k_grid_flags_and_gate(files):
    ax = pytest.importorskip("apex300")
    S3 = S.funded_spec("apex300_pa")
    g = S.funded_grid("apex300_pa")
    assert g == {**{a: list(ax.GRID[a]) for a in F.AXES}, "micros": [m for m in ax.GRID["micros"] if m <= S3.cap]}
    assert g["micros"] != F.default_micros(F.make_spec("apex")) and max(g["micros"]) > 100 and max(g["day_take"]) > max(F.GRID["day_take"])
    assert g["policy"] == list(ax.POLICIES["apex300_pa"]) != list(F.POLICIES)
    assert S.funded_grid("apex50_pa")["micros"] == F.default_micros(F.make_spec("apex"))     # the 50K keeps R's 50K grid
    assert S.start_states("apex300_pa") == ("fresh", "plus3000", "plus7600") == tuple(ax.STARTS) and S.start_states("flex") == ("fresh",)
    small = {"micros": [20, 150], "day_take": [0, 1500], "day_lock": [0], "day_stop": [0, 2250], "max_day_tr": [0], "policy": [500]}
    kw = dict(sess="nyam", grid=small, strategy="donchian", inputs={"tgt_r": 0.4})
    r = S.search_funded(files[DON], "apex300_pa", both_sides=False, **kw)
    assert r["variant"] == "apex300_pa" and len(r["rows"]) == 8 and r["grid"]["micros"] == [20, 150]
    # R's 50K constant flags ANY day stop >= $2,000; on the 300K (threshold $7,500) a $2,250 day stop is fine
    assert "day_stop_acts_as_trailing_threshold" in F.apex_flags("donchian", {"tgt_r": 0.4}, {"day_stop": 2250}, 0.0)
    assert not [x for x in r["rows"] if "day_stop_acts_as_trailing_threshold" in x["apex_flags"]]
    ref = ax.search(ax.port_from_trades(json.loads(S.trade_file(files[DON]).read_text()), sess="nyam"), ax.make_spec("apex300_pa"), small,
                    strategy="donchian", inputs={"tgt_r": 0.4}, both_sides=False)
    assert json.loads(json.dumps(r["rows"])) == json.loads(json.dumps(ref))                  # the adapter adds nothing of its own
    assert r["eligible"] == len(ax.compliant(ref)) and r["picks"] == F.pick_cells(ax.compliant(r["rows"]))
    assert all((x["apex_noncompliant"] is False) == (x in ax.compliant(r["rows"])) for x in r["rows"])
    # fail closed: without the one-direction declaration no row is eligible; an OCO family never is
    assert S.search_funded(files[DON], "apex300_pa", **kw)["eligible"] == 0
    oco = S.search_funded(files[KEY], "apex300_pa", sess="nyam", grid=small, strategy="straddle", inputs={"tgt_r": 2.0}, both_sides=True)
    assert oco["eligible"] == 0 and oco["gate"]["apex_one_direction"] == ["FAIL"] and oco["picks"]["e40_raw"] is None
    one = S.score_funded(files[DON], "apex300_pa", 500, micros=20, rules={"day_take": 1500}, sess="nyam", boots=0, strategy="donchian",
                         inputs={"tgt_r": 0.4}, both_sides=False)
    row = [x for x in r["rows"] if x["micros"] == 20 and x["day_take"] == 1500 and x["day_stop"] == 0][0]
    assert one["e_net_40"] == row["e_net_40"] and one["compliant"] == (row["apex_noncompliant"] is False)
    alt = one["cons_alt"]["cons_base"]
    assert one["cons_alt"]["pess"]["e_net_40"] == row[f"e_net_40_cons_{alt}"] and one["cons_base"] == row["cons_base"] != alt
    with pytest.raises(ValueError):
        S.search_funded(files[DON], "flex", sess="nyam", grid=small, start="plus3000")       # start states: apex300 firms only


def test_start_states_are_exposed_and_change_the_account(files):
    pytest.importorskip("apex300")
    kw = dict(micros=30, rules={"day_take": 1000, "day_lock": 1000}, sess="nyam", boots=0, strategy="donchian", inputs={"tgt_r": 0.4},
              both_sides=False)
    by = S.score_funded_starts(files[DON], "apex300_pa", 500, **kw)
    assert list(by) == ["fresh", "plus3000", "plus7600"] and [by[k]["start"] for k in by] == list(by)
    assert by["fresh"]["p_bust_pre_first"] >= by["plus3000"]["p_bust_pre_first"] >= by["plus7600"]["p_bust_pre_first"]
    assert by["plus7600"]["e_net_40"] > by["fresh"]["e_net_40"]                              # a locked threshold + cushion pays sooner
    num = S.score_funded(files[DON], "apex300_pa", 500, start=3000.0, **kw)
    assert num["models"] == by["plus3000"]["models"] and num["start"] == "plus3000"
    for r in by.values():
        assert set(r["compliance"]) == {"one_direction", "stop_5x_target", "mae_rule"} and r["compliant"] == (not r["noncompliant"])
        assert r["cons_alt"]["cons_base"] != r["cons_base"] and len(r["warnings"]) >= 3


def test_baseline_on_apex300_scores_every_approved_source_and_never_lets_an_oco_family_set_the_bar():
    pytest.importorskip("apex300")
    srcs = S.baseline_sources()
    assert len(srcs) == 5 and {p for v in srcs.values() for p in v["picks"]} == set(S.BASELINE)      # #10 nyam serves both eval picks
    assert set(S.BASELINE) == {"flex_eval", "pro_nodll_eval", "flex_funded", "pro_nodll_funded", "pro_dll_funded", "apex_pa_funded"}
    x = S.score_baseline_apex300(starts=("fresh", "plus7600"))
    assert x["firm"] == "apex300_pa" and x["starts"] == ["fresh", "plus7600"] and set(x["rows"]) == set(srcs)
    for sid, row in x["rows"].items():
        for st in x["starts"]:
            for cn, c in row["starts"][st]["cells"].items():
                assert c["micros"] == S.APEX300_BASE_CELLS[cn]["micros"] and f"e_net_40_cons_{x['cons_alt']}" in c
                if row["both_sides"]:
                    assert c["compliant"] is False and c["compliance"]["one_direction"] == "FAIL", sid
    for st, bar in x["bar"].items():
        assert bar is None or ("donchian" in bar["from"] and bar["compliant"] is True)
