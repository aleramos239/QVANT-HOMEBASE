#!/usr/bin/python3
"""Tests for evalcore's day-matched control builder + profile resolver. Run: /usr/bin/python3 test_daymatch.py (or pytest)."""
import csv
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E  # noqa: E402

MIN = 60_000
D0 = 738_000                                         # an arbitrary ordinal


def mk(rows):
    """rows of (date_offset, sess, minute_of_entry, dur_min) -> TR-like."""
    t = E.TR()
    t.n = len(rows)
    t.date = np.array([D0 + r[0] for r in rows], np.int64)
    t.sess = np.array([r[1] for r in rows], np.int8)
    t.te = np.array([(D0 + r[0]) * 1440 * MIN + r[2] * MIN for r in rows], np.int64)
    t.tx = t.te + np.array([r[3] for r in rows], np.int64) * MIN
    t.side = np.ones(t.n, np.int8)
    t.g = np.arange(t.n, dtype=float)
    t.mae, t.risk = np.zeros(t.n), np.ones(t.n)
    return t


def rand_case(seed, nd=40, sessions=(0, 2, 3), cfg_max=3, pool_per=6):
    rg = np.random.default_rng(seed)
    cfg, pool = [], []
    for d in range(nd):
        for s in sessions:
            for i in range(rg.integers(0, cfg_max + 1)):
                cfg.append((d, s, 10 + 20 * i, 5))
            for i in range(rg.integers(pool_per // 2, pool_per + 1)):        # always >= cfg_max: pool suffices
                pool.append((d, s, 5 + 7 * i + int(rg.integers(0, 3)), 4))
    return mk(cfg), mk(pool)


def test_counts_and_days_equal_when_pool_suffices():
    for seed in range(5):
        cfg, pool = rand_case(seed)
        for ovl in (True, False):
            for c in E.daymatched_controls(cfg, pool, K=4, seed=seed, no_overlap=ovl):
                assert c["short"] == 0 and c["fb_share"] == 0.0 and not c["fb"].any()
                assert c["n"] == cfg.n
                kc = Counter(zip(cfg.date.tolist(), cfg.sess.tolist()))
                kk = Counter(zip(c["date"].tolist(), c["sess"].tolist()))
                assert kc == kk, "per (date,session) counts differ"
                assert set(c["date"].tolist()) == set(cfg.date.tolist())                    # trade-days equal exactly
                assert (c["date"][1:] >= c["date"][:-1]).all()                              # date-ordered
                assert len(set(c["pi"].tolist())) == c["n"], "drawn with replacement"
                assert (pool.date[c["pi"]] == c["date"]).all() and (pool.sess[c["pi"]] == c["sess"]).all()


def test_intraday_order_and_no_overlap():
    cfg, pool = rand_case(7)
    for c in E.daymatched_controls(cfg, pool, K=3, seed=1):
        for d, ss in set(zip(c["date"].tolist(), c["sess"].tolist())):        # sessions are disjoint windows in real data
            m = np.flatnonzero((c["date"] == d) & (c["sess"] == ss))
            te, tx = c["te"][m], c["tx"][m]
            assert (te[1:] >= te[:-1]).all()                                                # intraday order preserved
            assert (te[1:] >= tx[:-1]).all(), "overlapping picks with no_overlap=True"


def test_deterministic_and_seed_sensitive():
    cfg, pool = rand_case(3)
    a = E.daymatched_controls(cfg, pool, K=3, seed=5)
    b = E.daymatched_controls(cfg, pool, K=3, seed=5)
    c = E.daymatched_controls(cfg, pool, K=3, seed=6)
    assert all((x["pi"] == y["pi"]).all() for x, y in zip(a, b))
    assert any(not np.array_equal(x["pi"], y["pi"]) for x, y in zip(a, c))
    assert any(not np.array_equal(a[0]["pi"], a[k]["pi"]) for k in (1, 2))                  # K draws differ


def test_uniform_draw():
    cfg = mk([(0, 1, 10, 1)])                                                                # one trade on day 0
    pool = mk([(0, 1, 10 * i, 1) for i in range(1, 5)])                                       # 4 candidates
    hits = Counter()
    for k in range(2000):
        hits[int(E.daymatched_pick(cfg.date, cfg.sess, pool.date, pool.te, pool.tx, pool.sess, [1, k])["pi"][0])] += 1
    assert set(hits) == {0, 1, 2, 3} and min(hits.values()) > 400, hits


def test_fallback_nearest_dates_and_share():
    cfg = mk([(10, 1, 30, 5), (10, 1, 60, 5), (10, 1, 90, 5)])                               # 3 trades on day 10
    pool = mk([(10, 1, 40, 5),                                                                # 1 on the day
               (12, 1, 120, 5), (7, 1, 40, 5), (7, 1, 80, 5),                                  # +2 days, -3 days x2
               (11, 2, 40, 5), (9, 1, 200, 5)])                                               # other session / -1 day
    ok = 0
    for k in range(50):
        r = E.daymatched_pick(cfg.date, cfg.sess, pool.date, pool.te, pool.tx, pool.sess, [2, k])
        assert r["short"] == 0 and len(r["pi"]) == 3 and (r["date"] == D0 + 10).all()
        assert r["fb"].sum() == 2 and 0 in r["pi"].tolist()
        fbp = set(r["pi"][r["fb"]].tolist())
        assert 5 in fbp, "nearest date (-1) must be taken first"                            # index 5 = day 9
        assert 4 not in r["pi"].tolist(), "other session must never be used"
        assert len(fbp - {5}) == 1
        # second fallback: nearest remaining = day 12 (dist 2) before day 7 (dist 3)
        assert fbp == {5, 1}
        ok += 1
    assert ok == 50
    # shifted times land on the config's date
    c = E.daymatched_controls(cfg, pool, K=1)[0]
    assert (c["te"] // (1440 * MIN) == D0 + 10).all() and abs(c["fb_share"] - 2 / 3) < 1e-9


def test_pool_exhausted_reports_short():
    cfg = mk([(1, 0, 10 + 10 * i, 1) for i in range(4)])
    pool = mk([(1, 0, 10, 1), (5, 0, 100, 1)])
    r = E.daymatched_pick(cfg.date, cfg.sess, pool.date, pool.te, pool.tx, pool.sess, 1)
    assert len(r["pi"]) == 2 and r["short"] == 2


def test_first_pass_not_stolen_by_fallback():
    cfg = mk([(1, 0, 10, 1), (1, 0, 30, 1), (2, 0, 10, 1)])                                 # day1 needs 2, day2 needs 1
    pool = mk([(1, 0, 10, 1), (2, 0, 10, 1)])                                                # day1 short by 1, day2 has its own
    r = E.daymatched_pick(cfg.date, cfg.sess, pool.date, pool.te, pool.tx, pool.sess, 1)
    d2 = r["pi"][r["date"] == D0 + 2]
    assert d2.tolist() == [1] and not r["fb"][r["date"] == D0 + 2].any()
    assert r["short"] == 1                                                                   # day 1 second trade unfillable


def test_resolver():
    cols = "stage,key,kind,strategy,params_json,run_id,grid_id,cell,trades,net".split(",")
    rows = []
    for s in (1, 2):
        rows.append(["ctrl", f"ctrl-random-tf5-s{s}", "run", "draft_pp_random", json.dumps({"tf": "5", "seed": s}), f"RA{s}", "", "", 1, 0])
    rows.append(["ctrl", "ctrl2-random-tf5-s11", "run", "draft_pp_random", json.dumps({"tf": "5", "seed": 11, "p_entry": 0.5}), "RA11", "", "", 1, 0])
    rows.append(["ctrl", "ctrl-randomtod-tf5-s1", "run", "draft_pp_random",
                 json.dumps({"tf": "5", "tgt_r": 0.0, "exit_bars": 6, "max_tr": 1}), "RT1", "", "", 1, 0])
    rows.append(["ctrl", "ctrl-random-tf15-s1", "run", "draft_pp_random", json.dumps({"tf": "15"}), "RB1", "", "", 1, 0])
    for c, (sv, tg) in enumerate([(1.0, 0.5), (2.0, 2.0)]):
        rows.append(["ctrl", "hmctrl-random-tf5-s11", "grid", "draft_pp_random",
                     json.dumps({"tf": "5", "stop_val": sv, "tgt_r": tg}), "", "G1", c, 1, 0])
    rows.append(["screen", "screen-orb-tf5", "run", "draft_pp_orb", "{}", "SCR", "", "", 1, 0])
    with tempfile.TemporaryDirectory() as td:
        lp, jp = Path(td) / "l.csv", Path(td) / "j.jsonl"
        with lp.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols), w.writerows(rows)
        jp.write_text("".join(json.dumps({"key": r[1], "status": "done"}) + "\n" for r in rows))
        P = lambda fam, **kw: E.profile_from(fam, kw)
        r = E.resolve_pool(P("orb", tf="5"), lp, jp)                                          # screen default
        assert r["exact"] and sorted(r["srcs"]) == ["RA1", "RA11", "RA2"], r
        r = E.resolve_pool(P("tod_drift", tf=5), lp, jp)                                      # tod_drift -> randomtod
        assert r["exact"] and r["srcs"] == ["RT1"], r
        r = E.resolve_pool(P("orb", tf="5", stop_val=1.0, tgt_r=0.5), lp, jp)                 # heat-map cell
        assert r["exact"] and r["srcs"] == ["G1#0"], r
        r = E.resolve_pool(P("orb", tf="15"), lp, jp)
        assert r["exact"] and r["srcs"] == ["RB1"]
        r = E.resolve_pool(P("orb", tf="5", stop_val=2.2, tgt_r=2.0), lp, jp)                 # no equal profile -> nearest
        assert not r["exact"] and r["srcs"] == ["G1#1"] and r["flag"], r
        r = E.resolve_pool(P("orb", tf="30"), lp, jp)                                         # no tf30 pool: flagged nearest
        assert not r["exact"] and r["flag"] and r["srcs"]


def test_real_pool_smoke():
    """Real ctrl runs: day-matched control of a synthetic config drawn from real trades equals its days exactly."""
    r = E.resolve_pool(E.profile_from("orb", {"tf": "5"}))
    if not r["srcs"]:
        return
    pool = E.concat_tr([E.load(s) for s in r["srcs"]])
    rg = np.random.default_rng(0)
    keep = np.flatnonzero(pool.sess == E.SESS_CODE["nyam"])
    one_seed = E.load(r["srcs"][0])
    cfg_idx = np.flatnonzero((one_seed.sess == E.SESS_CODE["nyam"]))[::3]              # a thin subset of one seed's trades
    cfg = E.TR()
    cfg.n = len(cfg_idx)
    for a in ("date", "te", "tx", "sess"):
        setattr(cfg, a, getattr(one_seed, a)[cfg_idx])
    for c in E.daymatched_controls(cfg, pool, K=3, seed=1):
        if c["short"] == 0 and c["fb_share"] == 0:
            assert set(c["date"].tolist()) == set(cfg.date.tolist()) and c["n"] == cfg.n
        assert c["n"] + c["short"] == cfg.n


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
