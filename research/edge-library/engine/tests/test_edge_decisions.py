"""EDGE_SPEC "ORCHESTRATOR DECISIONS 2026-10-03" 2-7 in the registry, library.py and run_menus.py: mirror units, identical
trade lists counted once, dead cells left out, the central cell, WEAK / penalty / second-look flags and the card fields,
null cells outside the 40,000 cap, the metric set per year then combined, the share verdicts at 60 / 70 / 80 %, the
$1,000-risk view in micros. Synthetic numbers only: nothing here reads a run."""
import datetime as dt

import numpy as np
import pytest

import l2sim as S
import library as LB
import run_menus as RM


# ---- decision 6: null cells are tracked apart from the 40,000 candidate cap ------------------------------------------------------

def test_null_cells_do_not_count_toward_the_candidate_cap_and_are_tracked_separately(tmp_path):
    led = tmp_path / "ledger.csv"
    caps = {"runs": 5, "cells": 100, "wfs": 1}
    LB.ledger_add("build", "u1", "grid", cells=90, path=led, caps=caps)
    LB.ledger_add("null", "u1-shift", "null", cells=180, path=led, caps=caps)          # twice the cap: fine, it is a null
    LB.ledger_add("null", "c1-NQ-tf5", "null", cells=64, path=led, caps=caps)
    assert LB.ledger_used(path=led) == {"runs": 0, "cells": 90, "wfs": 0} and LB.ledger_nulls(path=led) == 244
    LB.ledger_add("build", "u2", "grid", cells=10, path=led, caps=caps)                # the cap is still whole for candidates
    with pytest.raises(LB.CapExceeded):
        LB.ledger_add("build", "u3", "grid", cells=1, path=led, caps=caps)
    rows = LB.read_ledger(led)
    assert tuple(rows[0]) == LB.COLS and "null_cells" in LB.COLS
    assert [(r["kind"], r["cells"], r["null_cells"]) for r in rows] == [("grid", "90", "0"), ("null", "0", "180"), ("null", "0", "64"),
                                                                       ("grid", "10", "0")]
    # a null can not be booked as a candidate grid, nor a candidate as a null (the cap may not be dodged either way)
    with pytest.raises(ValueError, match="null / control"):
        LB.ledger_add("null", "x", "grid", cells=5, path=led, caps=caps)
    with pytest.raises(ValueError, match="null / control"):
        LB.ledger_add("build", "y", "null", cells=5, path=led, caps=caps)
    LB.ledger_add("null_error", "u9-c2s1", "null", cells=7, path=led, caps=caps)       # a failed null pass: tracked, not capped
    LB.ledger_add("build_error", "u9", "grid", cells=0 + 1, path=tmp_path / "l2.csv", caps=caps)      # a failed candidate batch counts
    assert LB.ledger_nulls(path=led) == 251 and LB.ledger_used(path=tmp_path / "l2.csv")["cells"] == 1
    assert LB.CAPS == {"runs": 2000, "cells": 50000, "wfs": 40}        # 40,000 -> 50,000: EDGE_SPEC "STAGE 2b"


def test_the_plan_counts_candidate_cells_and_null_cells_apart():
    us = RM.units()
    t = RM.plan_totals(us)
    assert t["candidate_cells"] == sum(u["cells"] for u in us) and t["hold_to"] == "day"
    assert t["null_cells"] == t["unit_null_cells"] + t["c1_null_cells"] and t["c1_null_cells"] == 64 * t["c1_pools"]
    assert t["candidate_cells"] <= LB.CAPS["cells"] and t["cap_left_after"] == LB.CAPS["cells"] - t["candidate_cells"]
    one = RM.plan_totals(RM.units(only=["straddle_t_0930"], roots=["NQ"]))
    assert one == {**one, "run_units": 1, "candidate_cells": 160, "unit_null_cells": 320, "c1_pools": 1, "c1_null_cells": 64,
                   "null_cells": 384}
    l2 = RM.plan_totals(RM.units(only=["bimb_follow_d1"]))
    assert (l2["candidate_cells"], l2["unit_null_cells"]) == (96, 192)
    mirror = {u["family"] for u in us if u["mirror"]}
    assert mirror == {"tod_drift", "ib", "gap", "orb_confirm"} and t["mirror_run_units"] == sum(1 for u in us if u["mirror"])


# ---- decision 2 + 3: judged cells, the central cell ---------------------------------------------------------------------------

def rows(nets, **kw):
    out = [{"id": f"c{k}", "vi": k // 4, "xi": k % 4, "net": v, "trades": 50, "sig": f"s{k}", "dead": False} for k, v in enumerate(nets)]
    for k, v in kw.items():
        for r, x in zip(out, v):
            r[k] = x
    return out


def test_cells_with_identical_trade_lists_count_once():
    """ib fade / gap fill ignore the target: the four cells of a stop are ONE trade list. Counted four times a plateau of
    2 distinct winners + 1 distinct loser reads 8 of 12; counted once it is 2 of 3."""
    t = rows([100, 100, 100, 100, 50, 50, 50, 50, -70, -70, -70, -70], sig=["a"] * 4 + ["b"] * 4 + ["c"] * 4)
    p = LB.plateau(t)
    assert (p["cells"], p["cells_all"], p["duplicates"], p["dead"]) == (3, 12, 9, 0)
    assert p["positive"] == 2 and p["share_pos"] == round(2 / 3, 4) and p["median_net"] == 50.0 and p["pass"]
    assert p["member"] == "c4" and p["best"] == "c0"                                   # a group is named by its first cell
    # a duplicated LOSER can not be diluted either: 3 distinct winners + 5 copies of one loser = 3 of 4, not 3 of 8
    q = LB.plateau(rows([10, 20, 30, -5, -5, -5, -5, -5], sig=["a", "b", "c"] + ["z"] * 5))
    assert (q["cells"], q["positive"], q["share_pos"]) == (4, 3, 0.75)
    # rows without a fingerprint are never merged (a bare table), and an explicit None neither
    assert LB.plateau([{"id": f"c{k}", "net": 5.0} for k in range(6)])["cells"] == 6
    assert LB.plateau(rows([5, 5, 5], sig=[None] * 3))["cells"] == 3


def test_structurally_dead_cells_are_left_out_of_the_plateau():
    nets = [100, 200, 300, 400, 0, 0, 0, 0]
    dead = [False] * 4 + [True] * 4
    p = LB.plateau(rows(nets, dead=dead))
    assert (p["cells"], p["cells_all"], p["dead"], p["share_pos"], p["pass"]) == (4, 8, 4, 1.0, True)
    live = LB.plateau(rows(nets, sig=["a", "b", "c", "d"] + ["empty"] * 4))            # alive but never traded: ONE cell that is not > 0
    assert (live["cells"], live["duplicates"], live["positive"], live["share_pos"]) == (5, 3, 4, 0.8)
    none = LB.plateau(rows([0, 0], dead=[True, True]))
    assert none["pass"] is False and none["cells"] == 0 and none["member"] is None and none["dead"] == 2


def test_the_central_cell_is_the_positive_judged_cell_closest_to_the_median_ties_to_the_lowest_index():
    p = LB.plateau(rows([100, 900, 300, 5000, 250, 240, 260, -50, -60, 10]))
    assert p["median_net"] == 245.0 and p["member"] == "c4" and p["member_net"] == 250.0 and p["best"] == "c3"
    assert LB.plateau(rows([240, 250, 260, 250, 240, 260, 250]))["member"] == "c1"
    # the median is the JUDGED cells' median: a dead cell and a duplicate do not pull it
    q = LB.plateau(rows([100, 100, 300, 500, 0], sig=["a", "a", "b", "c", "empty"], dead=[False, False, False, False, True]))
    assert q["cells"] == 3 and q["median_net"] == 300.0 and q["member"] == "c2"
    assert LB.plateau(rows([-10, -20, -30, 70]))["member"] == "c3" and not LB.plateau(rows([-10, -20, -30, 70]))["pass"]


def test_share_of_cells_overall_by_stop_type_and_per_reward_ratio_with_verdicts_at_60_70_80():
    menu = S.menu("NQ")                                                                # 8 stops x 4 targets
    assert len(menu) == 32
    net = []
    for x in menu:                                                                     # fixed stops win except with no target;
        if x["stop_mode"] == "pts":                                                    # ATR stops win only at 1:1; percent loses
            net.append(-100.0 if x["tgt_r"] == 0 else 200.0)
        elif x["stop_mode"] == "atr":
            net.append(150.0 if x["tgt_r"] == 1 else -50.0)
        else:
            net.append(-20.0)
    t = [{"id": S.cell_id(x), "vi": 0, "xi": k, "net": n, "trades": 80, "sig": f"s{k}", "dead": False, "stop_mode": x["stop_mode"],
          "tgt_r": x["tgt_r"]} for k, (x, n) in enumerate(zip(menu, net))]
    p = LB.plateau(t)
    sh = p["shares"]
    assert sh["overall"]["cells"] == 32 and sh["overall"]["positive"] == 14 and sh["overall"]["share_pos"] == round(14 / 32, 4)
    assert p["verdicts"] == {"60": False, "70": False, "80": False} == sh["overall"]["verdicts"] and not p["pass"]
    assert set(sh["by_stop"]) == {"fixed", "ATR", "percent"} and set(sh["by_target"]) == {"r0", "r1", "r2", "r3"}
    assert sh["by_stop"]["fixed"] == {"cells": 16, "positive": 12, "share_pos": 0.75, "median_net": 200.0,
                                      "verdicts": {"60": True, "70": True, "80": False}}
    assert sh["by_stop"]["ATR"]["share_pos"] == 0.25 and sh["by_stop"]["percent"]["positive"] == 0
    assert sh["by_target"]["r0"]["positive"] == 0 and sh["by_target"]["r1"]["share_pos"] == 0.75
    assert sh["by_target"]["r2"] == {"cells": 8, "positive": 4, "share_pos": 0.5, "median_net": 90.0,
                                     "verdicts": {"60": False, "70": False, "80": False}}
    allpos = LB.plateau([dict(r, net=10.0 + k) for k, r in enumerate(t)])
    assert allpos["verdicts"] == {"60": True, "70": True, "80": True} and allpos["pass"]
    md = "\n".join(LB.shares_md(p))
    assert "stop: fixed" in md and "target: none" in md and "target: 1:2" in md and "pass 80 %" in md and "75.0 %" in md
    # a share above the bar with a median at or below 0 is not a pass
    assert LB.plateau(rows([1, 1, 1, 0, 0, -9, -9, -9, -9, -9][:5]))["verdicts"]["60"] is True
    assert LB.plateau(rows([1, 1, -9, -9]))["verdicts"] == {"60": False, "70": False, "80": False}


def fake_unit(tmp_path, key, variants, nets_of, mirror=None, sess="nyam", dead_vi=()):
    """A unit store whose cell (vi, xi) has 3 trades of net nets_of(vi, xi) / 3 each in `sess` (none for a dead variant)."""
    d0 = dt.date(2023, 3, 14)
    hhmm = {"nyam": "09:40", "pm": "13:40", "asia": "01:00"}[sess]
    cells, res = [], []
    for c in S.menu_grid(S.Template, {"tf": "5"}, "NQ", variants):
        cells.append(c)
        tr = []
        if c["vi"] not in dead_vi:
            for k in range(3):
                d = d0 + dt.timedelta(days=k)
                ms = S.et_ns(d, hhmm) // 1_000_000
                tr.append({"date": d.isoformat(), "side": "long", "entry_price": 100.0, "sl": 95.0, "exit_reason": "tp", "mae_usd": 10.0,
                           "net": nets_of(c["vi"], c["xi"]) / 3.0, "entry_ms": ms, "exit_ms": ms + 60000 * (1 + c["xi"] + 40 * c["vi"])})
        res.append({"trades": tr, "meta": {"inputs": {}, "root": "NQ"}, "sessions": 3, "used": 3, "skipped": [], "no_trade": [],
                    "elapsed_s": 0.0})
    LB.write_unit(key, {"family": key.split("-")[0], "tf": "5", "mirror": mirror, "variants": variants}, cells, res, tmp_path)
    return LB.load_unit(key, tmp_path)


def test_session_table_marks_dead_variants_and_fingerprints_and_mirror_families_split_into_units(tmp_path):
    variants = [{"off_min": m, "dir": d} for m in (0, 15) for d in ("long", "short")]
    # long makes money, short loses the same (the mirror); the off_min 15 short variant never trades in this session
    u = fake_unit(tmp_path, "tod_drift-NQ-tf5", variants, lambda vi, xi: (300.0 + xi) * (1 if vi % 2 == 0 else -1), mirror="dir",
                  dead_vi=(3,))
    t = LB.session_table(u, "nyam")
    assert len(t) == 128 and {r["dead"] for r in t if r["vi"] == 3} == {True} and not any(r["dead"] for r in t if r["vi"] != 3)
    assert all(r["sig"] == "empty" for r in t if r["vi"] == 3) and len({r["sig"] for r in t if r["vi"] != 3}) == 96
    assert t[0]["stop_mode"] == "atr" and t[0]["tgt_r"] == 0.0 and t[31]["stop_mode"] == "pct" and t[31]["tgt_r"] == 3.0
    whole = LB.plateau(t)                                                              # the whole table: 96 judged, 32 dead
    assert (whole["cells"], whole["cells_all"], whole["dead"], whole["positive"]) == (96, 128, 32, 64)
    units = LB.plateau_units(u, "nyam")
    assert list(units) == ["dir=long", "dir=short"] and [len(v) for v in units.values()] == [64, 64]
    j = LB.judge(u, "nyam")
    assert j["dir=long"]["pass"] and j["dir=long"]["cells"] == 64 and j["dir=long"]["share_pos"] == 1.0
    assert not j["dir=short"]["pass"] and j["dir=short"]["cells"] == 32 and j["dir=short"]["dead"] == 32 and j["dir=short"]["positive"] == 0
    assert LB.mirror_axis(u) == "dir" and LB.unit_sessions(u) == ["nyam"]
    # a family without a mirror axis is one unit
    v = fake_unit(tmp_path, "donchian-NQ-tf5", [{"n": 10}, {"n": 20}], lambda vi, xi: 50.0 + xi, sess="pm")
    assert list(LB.plateau_units(v, "pm")) == [""] and LB.judge(v, "pm")[""]["cells"] == 64 and LB.unit_sessions(v) == ["pm"]
    assert LB.plateau_units(v, "nyam")[""][0]["dead"] is True                          # no trade in that session at all
    # identical trade lists inside a store are found by the fingerprint (same entries, exits and nets)
    w = fake_unit(tmp_path, "gap-NQ-tf5", [{"mode": "fill"}, {"mode": "go"}], lambda vi, xi: 90.0 if vi == 0 else 30.0 + xi, mirror="mode")
    tw = LB.session_table(w, "nyam")
    assert len({r["sig"] for r in tw if r["vi"] == 0}) == 32                           # different exits (durations): distinct lists
    x = LB.unit_cell(w, 0)
    assert LB.trade_sig(x) == LB.trade_sig({k: a.copy() for k, a in x.items()}) != LB.trade_sig(LB.unit_cell(w, 1))
    assert LB.trade_sig(LB.pack([])) == "empty"


# ---- decision 4 + 5: the flags in the registry -----------------------------------------------------------------------------------

def test_the_orchestrator_flags_are_laid_over_the_registry():
    import families as F
    assert F.ERRORS == {}
    weak = {n for n, lb in F.LIBRARY.items() if lb["weak"]}
    assert set(F.WEAK_FAMILIES) == {"straddle_t_0000", "straddle_t_1105", "tod_drift", "vwap_ema_x", "ema_ribbon", "tema_slope",
                                    "ema_pullback", "supertrend"} <= weak
    assert weak - set(F.WEAK_FAMILIES) == {"bimb_follow_d1", "flow_exhaust"}           # their author's own flag: kept (stricter)
    assert {n: lb["mirror"] for n, lb in F.LIBRARY.items() if lb["mirror"]} == {"tod_drift": "dir", "ib": "mode", "gap": "mode",
                                                                                    "orb_confirm": "dir"}      # + STAGE 2b N3
    for n, axis in F.MIRROR.items():
        assert len({v[axis] for v in F.LIBRARY[n]["variants"]}) == 2
    # the failure penalty: first_bar_mom (every session) and donchian in the pm session only
    assert {n for n, lb in F.LIBRARY.items() if lb["penalty"]} == {"first_bar_mom", "donchian"}
    assert F.LIBRARY["donchian"]["penalty_sess"] == ("pm",) and F.LIBRARY["first_bar_mom"]["penalty_sess"] is None
    assert F.penalty_for("donchian", "pm") and F.penalty_for("donchian", "nyam") is None and F.penalty_for("donchian")
    assert all(F.penalty_for("first_bar_mom", s) for s in LB.SESS7) and F.penalty_for("orb", "pm") is None
    # second look: every family whose 2025-26 was already read carries the label for its card
    seen = {n for n, lb in F.LIBRARY.items() if lb["second_look"]}
    assert {"orb", "straddle", "donchian", "straddle_t_0300", "straddle_t_0930", "straddle_t_1330", "first_bar_mom", "tod_drift",
            "rsi2", "ema_pullback", "tema_slope", "vwap_z", "vwap_flip", "bimb_follow_d1"} <= seen
    assert not {"straddle_t_1800", "straddle_t_2000", "squeeze", "lon_break", "pinbar", "mid_fade"} & seen
    assert all("second look" in F.LIBRARY[n]["second_look"].lower() for n in seen)
    # decision 5: 20:00 ET stays 20:00 ET all year -- on the card through the notes
    assert "20:00 ET all year" in F.LIBRARY["straddle_t_2000"]["notes"] and "19:00 ET" in F.LIBRARY["straddle_t_2000"]["notes"]
    assert all(lb["notes"].startswith(F.REGISTRY[n][3].strip()) for n, lb in F.LIBRARY.items())
    m = LB.member_meta("tod_drift", "pm", {"off_min": 15, "dir": "short"})
    assert m["weak"] is True and m["mirror"] == "dir=short" and m["hold_to"] == "day" and m["second_look"] and m["penalty"] is None
    assert LB.member_meta("donchian", "pm")["penalty"] and LB.member_meta("donchian", "mid")["penalty"] is None
    assert LB.member_meta("ema_ribbon", "nyam")["weak"] is True and LB.member_meta("orb", "nyam")["weak"] is False


def test_a_broken_overlay_is_a_registry_error(monkeypatch):
    import families as F
    monkeypatch.setitem(F.MIRROR, "orb", "nope")
    monkeypatch.setitem(F.CARD_NOTES, "no_such_family", "x")
    try:
        F.load()
        assert "MIRROR axis" in F.ERRORS["orb"] and "not registered" in F.ERRORS["no_such_family"] and "orb" not in F.LIBRARY
    finally:
        monkeypatch.undo()
        F.load()
    assert F.ERRORS == {} and "orb" in F.LIBRARY


# ---- decision 7: the metric set per year, then combined; the $1,000-risk view -------------------------------------------------------

def tr(date, net, mae=50.0, risk=10.0, hhmm="09:40", mins=30):
    d = dt.date.fromisoformat(date)
    ms = S.et_ns(d, hhmm) // 1_000_000
    return {"date": date, "side": "long", "entry_price": 15000.0, "sl": 15000.0 - risk, "exit_reason": "tp", "mae_usd": mae, "net": net,
            "commission": 4.0, "entry_ms": ms, "exit_ms": ms + mins * 60000}


def test_metrics_are_reported_per_year_first_then_combined():
    cal = [d.isoformat() for d in S.sessions("2021-09-22", "2023-12-29")]
    trades = [tr("2021-10-05", 200.0), tr("2021-10-06", -100.0, mae=150.0), tr("2022-03-15", 300.0), tr("2022-03-16", -500.0, mae=520.0),
              tr("2022-06-13", 100.0), tr("2023-03-22", 400.0), tr("2023-08-09", 50.0)]
    rws = LB.per_year(LB.pack(trades), cal)
    assert [r["period"] for r in rws] == ["2021*", "2022", "2023", "combined"]          # 2021 is a partial year: starred
    y21, y22, y23, al = rws
    assert set(LB.METRIC_KEYS) <= set(y21) and LB.METRIC_KEYS == ("trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade",
                                                                    "worst_open_loss")
    assert (y21["trades"], y21["net"], y21["win"], y21["pf"], y21["avg_trade"]) == (2, 100.0, 0.5, 2.0, 50.0)
    assert y21["max_dd"] == 100.0 and y21["worst_open_loss"] == 154.0                  # the losing day: MAE 150 + commission 4
    assert (y22["trades"], y22["net"], y22["max_dd"], y22["worst_open_loss"]) == (3, -100.0, 500.0, 524.0)
    assert (y23["trades"], y23["net"], y23["max_dd"], y23["pf"]) == (2, 450.0, 0.0, None)
    assert (al["trades"], al["net"], al["avg_trade"]) == (7, 450.0, round(450 / 7, 2)) and al["max_dd"] == 500.0
    assert al["days"] == len(cal) and y21["days"] + y22["days"] + y23["days"] == len(cal)
    # Sharpe: the DAILY net over every session of the year (0 on a day without a trade), annualised with sqrt(252)
    d22 = np.zeros(y22["days"])
    d22[:3] = [300.0, -500.0, 100.0]
    assert y22["sharpe"] == pytest.approx(d22.mean() / d22.std(ddof=1) * np.sqrt(252.0))
    assert LB.metrics(LB.pack([]), cal[:5])["sharpe"] is None and LB.metrics(LB.pack([]), cal[:5])["trades"] == 0
    pick = LB.per_year(LB.pack(trades + [tr("2024-02-06", 80.0)]), cal + [d.isoformat() for d in S.sessions("2024-01-02", "2024-12-31")])
    assert [r["period"] for r in pick] == ["2021*", "2022", "2023", "2024", "combined"] and pick[3]["net"] == 80.0
    with pytest.raises(ValueError, match="off the calendar"):
        LB.metrics(LB.pack([tr("2024-02-06", 1.0)]), cal)
    md = "\n".join(LB.metrics_md(rws))
    assert md.splitlines()[0].startswith("| period | trades | net | win rate | PF | max drawdown | Sharpe") and "| combined | 7 |" in md
    # two trades of one day: the max drawdown is on the DAILY net, the worst open loss inside the day
    same = [tr("2022-03-15", -200.0, mae=250.0, hhmm="09:40"), tr("2022-03-15", 300.0, mae=20.0, hhmm="13:40")]
    m = LB.metrics(LB.pack(same), ["2022-03-15", "2022-03-16"])
    assert m["max_dd"] == 0.0 and m["worst_open_loss"] == 254.0 and m["net"] == 100.0


def test_trades_sized_to_about_1000_usd_of_risk_in_micros():
    """NQ micro = $2 a point, $1 a round turn. A 10-point stop -> 50 micros ($1,000); 45 points -> 11 micros ($990);
    600 points -> 1 micro (never 0); no stop -> not sized."""
    trades = [tr("2022-03-15", 396.0, mae=100.0, risk=10.0), tr("2022-03-16", -904.0, mae=900.0, risk=45.0),
              tr("2022-03-17", 96.0, mae=40.0, risk=600.0), dict(tr("2022-03-18", 50.0), sl=None)]
    z = LB.sized(LB.pack(trades), "NQ")
    assert z["micros"].tolist() == [50, 11, 1, 0] and z["unsized"] == 1 and z["risk_usd"] == 1000.0
    # 1 contract: gross = net + $4 = 400 / -900 / 100 -> per micro 40 / -90 / 10, minus $1
    assert z["net"].tolist() == pytest.approx([50 * 39.0, 11 * -91.0, 1 * 9.0, 0.0])
    assert z["mae"].tolist() == pytest.approx([50 * 10.0, 11 * 90.0, 4.0, 0.0]) and z["cost"].tolist() == [50.0, 11.0, 1.0, 0.0]
    assert LB.sized(LB.pack(trades[:1]), "ES")["micros"].tolist() == [20]              # MES $5 a point: 10 points = $50
    assert LB.sized(LB.pack(trades[:1]), "GC")["micros"].tolist() == [10]              # MGC $10 a point
    cal = ["2022-03-15", "2022-03-16", "2022-03-17", "2022-03-18"]
    rws = LB.per_year(z, cal, z["cost"])
    assert rws[-1]["period"] == "combined" and rws[-1]["net"] == pytest.approx(1950.0 - 1001.0 + 9.0)
    assert rws[-1]["worst_open_loss"] == pytest.approx(11 * 90.0 + 11.0) and rws[-1]["sharpe"] is not None
    md = "\n".join(LB.report_md(LB.pack(trades), "NQ", cal))
    assert "1 contract" in md and "sized to about $1,000 of risk per trade in micros" in md and "median 11, min 1, max 50" in md
    assert "1 trades without a stop left out" in md and md.count("| combined |") == 2


def test_the_card_shows_weak_second_look_penalty_notes_the_share_verdicts_and_the_yearly_tables():
    cal_b = [d.isoformat() for d in S.sessions("2023-01-03", "2023-03-31")]
    cal_p = [d.isoformat() for d in S.sessions("2024-01-02", "2024-03-28")]
    b = [tr(d, 60.0 if k % 3 else -40.0) for k, d in enumerate(cal_b)]
    p = [tr(d, 50.0 if k % 2 else -30.0) for k, d in enumerate(cal_p)]
    menu = S.menu("NQ")
    table = [{"id": S.cell_id(x), "vi": 0, "xi": k, "net": 10.0 + k, "trades": 60, "sig": f"s{k}", "dead": False,
              "stop_mode": x["stop_mode"], "tgt_r": x["tgt_r"]} for k, x in enumerate(menu)]
    meta = LB.member_meta("donchian", "pm", {"n": 20})
    member = {"name": "donchian-NQ-tf15-pm", "root": "NQ", "tf": "15", "sess": "pm", "cell": "n20_atr1p5-r2", "inputs": {"n": 20}, **meta,
              "plateau": {"build": LB.plateau(table)}, "build": {"trades": b, "calendar": cal_b}, "pick": {"trades": p, "calendar": cal_p}}
    res = LB.admission(member)
    card = LB.card(member, res)
    assert "**WEAK:** no" in card and "**Second look:** 2025-26 was already seen once" in card
    assert "**Penalty (EDGE_SPEC C):** in-sample favourite (donchian pm) FAILED on 2025-26" in card and "needs the plateau on BUILD and PICK" in card
    assert "* Notes: " in card and "flat at 15:58 ET of the trade date (13:13 on a half day)" in card and "hold_to = day" in card
    assert "| 2023* |" in card and "| 2024* |" in card and "| combined |" in card and "Sharpe (daily, ann.)" in card
    assert "sized to about $1,000 of risk per trade in micros" in card
    assert "Share of cells with net > 0 — build" in card and "pass 60 %" in card and "stop: fixed" in card and "target: 1:3" in card
    assert "plateau_pick" in res["failed"]                                             # the pm penalty: the PICK plateau is demanded
    # the same family in another session carries no penalty; a weak, mirror family says so
    m2 = {**member, **LB.member_meta("donchian", "nyam", {"n": 20}), "sess": "nyam"}
    assert "plateau_pick" not in LB.admission(m2)["tests"] and "**Penalty (EDGE_SPEC C):** none" in LB.card(m2, LB.admission(m2))
    m3 = {**member, **LB.member_meta("tod_drift", "pm", {"off_min": 15, "dir": "long"})}
    c3 = LB.card(m3, LB.admission(m3))
    assert "**WEAK:** YES — admission needs t >= 3.00 on BUILD" in c3 and "Mirror unit: `dir=long`" in c3 and "weak_margin" in LB.admission(m3)["tests"]
    m4 = {**member, **LB.member_meta("straddle_t_2000")}
    assert "20:00 ET stays 20:00 ET all year" in LB.card(m4, LB.admission(m4)) and "**Second look:** no" in LB.card(m4, LB.admission(m4))


def test_a_unit_report_shows_each_mirror_unit_its_share_verdicts_and_the_central_cell_per_year(tmp_path):
    variants = [{"mode": "fill"}, {"mode": "go"}]
    u = fake_unit(tmp_path, "gap-NQ-tf5", variants, lambda vi, xi: (90.0 + xi) if vi == 0 else -(30.0 + xi), mirror="mode")
    u["meta"].update(root="NQ", period="build", hold_to="day", weak=False, second_look=None, penalty="favourite FAILED", penalty_sess=["pm"],
                     notes="C: gap", rationale="the opening gap fills or runs")
    md = LB.unit_report_md(u, "nyam")
    assert md.startswith("# gap-NQ-tf5 — session nyam (build, hold_to = day)") and "penalty: none" in md        # the penalty is pm's
    assert "## unit mode=fill — plateau PASS" in md and "## unit mode=go — plateau fail" in md
    assert md.count("| all judged cells | 32 |") == 2 and "stop: percent" in md and "target: 1:1" in md and "pass 70 %" in md
    # the passing unit shows its central cell per year (the BUILD calendar: 2021*, 2022, 2023) at 1 contract and sized
    assert "central cell `modefill_" in md and "| 2021* | 0 |" in md and "| 2023 | 3 |" in md and md.count("| combined | 3 |") == 2
    assert "sized to about $1,000 of risk per trade in micros (micros per trade: median 100, min 100, max 100)" in md
    u["meta"]["penalty_sess"] = ["nyam"]
    assert "penalty: favourite FAILED" in LB.unit_report_md(u, "nyam")
