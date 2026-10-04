#!/usr/bin/python3
"""Tests for portfolio_final.py (pool builder, exact specs, risk curve, by-day). Uses real research bundles (read-only, small pools).
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 -m pytest test_portfolio_final.py -q"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as PF                     # noqa: E402
import portfolio_final as F                # noqa: E402


def test_pool_dedup_and_top25():
    for f in ("lucid", "apex"):
        p = F.build_pool(f)
        cids = [c["cid"] for c in p]
        assert len(cids) == len(set(cids))
        assert sum(1 for c in p if "top" in c["how"]) == 25
        assert all(c["src"] and c["fam"] and c["tf"] for c in p)
        assert all(("ctrl_srcs" in c) == (c["cand_pass"] == "2") or c["cand_pass"] == "2" for c in p)


def test_risk_curve_scale1_equals_headline_and_by_day_monotone():
    fm = PF.firm("lucidpro")
    orig = F.build_pool
    F.build_pool = lambda f, **k: orig(f, top=3, per_group=0, near_max=0)
    try:
        ctx, pools = F.make_ctx(("lucidpro",))
    finally:
        F.build_pool = orig
    b = pools["lucidpro"][0]
    ms = [(b, 20)]
    ci = fm.cell_index(dict(day_lock=0, day_take=0, day_stop=0, max_day_tr=0, target_take=1))
    x = F.extras(ctx, fm, ms, ci)
    rc = {r["scale"]: r for r in x["risk_curve"]}
    res = PF.grid_outcomes(ctx, fm, PF.PV(ms, ctx.D), (fm.prim,), cells=[ci])
    p5 = float((res[fm.prim][0][ci] == 1).mean())
    assert abs(rc[1.0]["fixed"]["headline"]["p5"] - p5) < 1e-12
    bd = x["by_day"][fm.prim]
    assert all(np.diff(bd["pass_by_day"]) >= -1e-12) and abs(bd["pass_by_day"][-1] - p5) < 1e-12
    assert abs(bd["pass_by_day"][-1] + bd["bust_by_day"][-1] + bd["neither_5d"] - 1) < 1e-9
    assert x["specs"][0]["micros"] == 20 and x["specs"][0]["tester_inputs"]["sess"] == "all"
    assert rc[1.25]["total_micros"] == min(fm.cap, round(20 * 1.25))
