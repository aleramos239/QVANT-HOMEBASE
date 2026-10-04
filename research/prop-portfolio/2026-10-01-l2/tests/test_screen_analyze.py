"""screen_analysis.py (command line: screen_analyze.py): the pure rules of the Stage A analysis (trade statistics, the null p95, the binomial count, the
round-robin top 15, the family verdict, the shortlist, the task cache). Synthetic inputs only; scratch = tmp_path."""
import json
import math

import pytest

import screen_analysis as A


def _t(net, exit_ms, side="long", entry_ms=None):
    return {"net": float(net), "exit_ms": exit_ms, "entry_ms": exit_ms - 1 if entry_ms is None else entry_ms, "side": side}


def test_trade_stats_known_values():
    s = A.trade_stats([_t(100, 1), _t(-50, 2), _t(-80, 3), _t(200, 4)])
    assert s["trades"] == 4 and s["net"] == 170.0 and s["win"] == 0.5
    assert s["pf"] == pytest.approx(300 / 130)
    assert s["maxdd"] == 130.0                                   # peak 100 -> trough -30
    x = [100.0, -50.0, -80.0, 200.0]
    m = sum(x) / 4
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / 3)
    assert s["t"] == pytest.approx(m / (sd / 2))
    assert A.trade_stats([]) == {"trades": 0, "net": 0.0, "t": None, "pf": None, "maxdd": 0.0, "win": None}
    one = A.trade_stats([_t(-5, 1)])
    assert one["t"] is None and one["pf"] == 0.0 and one["maxdd"] == 5.0
    assert A.trade_stats([_t(5, 1), _t(7, 2)])["pf"] is None     # no losing trade: no profit factor


def test_trade_stats_orders_by_exit_time():
    a = A.trade_stats([_t(-100, 2), _t(100, 1)])
    b = A.trade_stats([_t(100, 1), _t(-100, 2)])
    assert a == b and a["maxdd"] == 100.0


def test_binom_crit():
    for n in (1, 10, 60, 120):
        k = A.binom_crit(n)
        tail = lambda kk: sum(math.comb(n, i) * 0.05 ** i * 0.95 ** (n - i) for i in range(kk, n + 1))  # noqa: E731
        assert tail(k) <= 0.05 and (k == 0 or tail(k - 1) > 0.05)
    assert A.binom_crit(120) == 11 and A.binom_crit(0) == 1


def _cell(firm, fam_tf, sess, c1, c2, family=None, status="ok", metric=0.5, informative=True):
    q = bool(status == "ok" and c1 is not None and c2 is not None and c1 > 0 and c2 > 0 and informative)
    return {"firm": firm, "fam_tf": fam_tf, "family": family or fam_tf.split("-tf")[0], "tf": fam_tf.split("-tf")[1], "sess": sess, "status": status,
            "metric": metric, "c1_lift": c1, "c2_opt_lift": c2, "c2_informative": informative, "qualifies": q,
            "strength": min(c1, c2) if q else None}


def test_top_configs_is_a_round_robin_over_the_firms():
    cells = [_cell("lucid", "a-tf1", "nyam", 0.3, 0.2), _cell("lucid", "b-tf1", "nyam", 0.1, 0.5), _cell("lucid", "c-tf5", "pm", 0.05, 0.05),
             _cell("flex", "d-tf5", "mid", 900.0, 100.0), _cell("flex", "a-tf1", "nyam", 50.0, 60.0), _cell("flex", "e-tf1", "asia", -1.0, 500.0),
             _cell("apex", "f-tf1", "pm", 0.2, 0.2, informative=False)]
    assert A.top_configs(cells, 15) == [("a-tf1", "nyam"), ("d-tf5", "mid"), ("b-tf1", "nyam"), ("c-tf5", "pm")]
    assert A.top_configs(cells, 2) == [("a-tf1", "nyam"), ("d-tf5", "mid")]
    assert A.top_configs([], 15) == []


def test_null_p95_strata_and_fallback():
    cache = {}
    for i in range(30):
        cache[("lucid", f"x{i}-c2s1", "nyam")] = {"variant": "c2s1", "status": "ok", "metric": i / 100, "family": "bimb_follow"}
    for i in range(5):
        cache[("lucid", f"y{i}-c2s1", "asia")] = {"variant": "c2s1", "status": "ok", "metric": 0.9, "family": "open_dir_book"}
    cache[("lucid", "z-c2s2", "asia")] = {"variant": "c2s2", "status": "no_compliant_cell", "metric": None, "family": "open_dir_flow"}
    cache[("lucid", "r", "nyam")] = {"variant": "real", "status": "ok", "metric": 5.0, "family": "bimb_follow"}       # real runs are not part of the null
    cache[("lucid", "e-c2s1", "nyam")] = {"variant": "c2s1", "status": "error", "metric": None, "family": "bimb_follow"}
    n = A.null_p95(cache)["lucid"]
    assert n[("atr", "nyam")]["n"] == 30 and n[("open", "asia")]["n"] == 6 and n[("all", "pooled")]["n"] == 36 and n[("all", "asia")]["n"] == 6
    assert n[("all", "pooled")]["max"] == 0.9 and n[("open", "pooled")]["n"] == 6
    np95 = {"lucid": n}
    p, strat = A.p95_of(np95, "lucid", "nyam", "bimb_follow")    # its own exit group and session
    assert strat == "atr/nyam" and p == pytest.approx(0.2755)
    p, strat = A.p95_of(np95, "lucid", "asia", "open_dir_book")  # group has < 20 nulls in the session AND pooled: the firm's pooled p95
    assert strat == "all/pooled" and p == n[("all", "pooled")]["p95"]
    p, strat = A.p95_of(np95, "lucid", "mid", "bimb_fade")       # no null in that session: the group pooled over sessions
    assert strat == "atr/pooled" and p == pytest.approx(0.2755)
    p, strat = A.p95_of(np95, "lucid", "nyam")                   # the rule as first written: the session over every family
    assert strat == "all/nyam" and p == pytest.approx(0.2755)
    assert A.p95_of(np95, "lucid", "asia")[1] == "all/pooled"
    assert A.p95_of(np95, "flex", "nyam", "bimb_follow") == (None, None)
    assert [A.exit_group(f) for f in ("open_dir_both", "wall_bounce", "wall_break", "thin_side", "cvd_div")] == ["open", "wall", "wall", "atr", "atr"]


def test_family_verdicts():
    np95 = {"lucid": {("all", "pooled"): {"n": 100, "p95": 0.4, "mean": 0.2, "sd": 0.1, "max": 0.6}}}
    good = [{**_cell("lucid", "g-tf1", s, 0.1, 0.1, metric=0.5), "null_metric": [0.3, 0.45]} for s in A.SESSIONS]
    bad = [{**_cell("lucid", "b-tf1", s, 0.1, -0.1, metric=0.1), "null_metric": [0.3, 0.05]} for s in A.SESSIONS]
    mixed = [_cell("lucid", "m-tf1", s, 0.1, 0.1 if i < 3 else -0.1, metric=0.1) for i, s in enumerate(A.SESSIONS)]
    wall = [_cell("lucid", "wall_break-tf1", s, 0.1, 0.1, metric=0.5, informative=False) for s in A.SESSIONS]
    raw = {"g": (100.0, [-50.0, 20.0]), "b": (-100.0, [-50.0, 20.0]), "m": (100.0, [-50.0, 20.0]), "wall_break": (100.0, [0.0, 0.0])}
    v = A.family_verdicts(good + bad + mixed + wall, np95, raw)
    assert v["g"]["verdict"] == "information beats both nulls" and v["g"]["above_p95"] == 5 and v["g"]["crit"] == A.binom_crit(5)
    assert (v["g"]["own_top"], v["g"]["own_n"]) == (5, 5) and (v["b"]["own_top"], v["b"]["own_n"]) == (0, 5) and v["m"]["own_n"] == 0
    assert v["b"]["verdict"] == "worse" and v["b"]["c2pos"] == 0
    assert v["m"]["verdict"] == "no better than shuffled book"
    assert v["wall_break"]["verdict"] == "no better than shuffled book (C2 uninformative = not passed)" and v["wall_break"]["c2pos"] == 0
    # raw net not above BOTH C2 seeds -> no 'beats', whatever the cells say
    assert A.family_verdicts(good, np95, {"g": (10.0, [-50.0, 20.0])})["g"]["verdict"] == "no better than shuffled book"


def test_shortlist_needs_a_stress_survivor():
    cells = [_cell("lucid", f"f{i}-tf1", "nyam", 0.1 + i / 100, 0.2) for i in range(10)] + [_cell("lucid", "n-tf1", "pm", -0.1, 0.2)]
    stress = {"cells": {f"lucid|f{i}-tf1|nyam": {"survives": i != 9} for i in range(1, 10)}}       # f0 was not stressed, f9 fails
    sl = A.shortlist(cells, stress)["lucid"]
    assert [c["fam_tf"] for c in sl["picked"]] == [f"f{i}-tf1" for i in range(8, 0, -1)]
    assert sl["qualified"] == 10 and sl["survive"] == 8 and sl["unstressed"] == 1 and sl["failed_stress"] == 1
    assert A.shortlist(cells, {})["flex"] == {"picked": [], "qualified": 0, "survive": 0, "unstressed": 0, "failed_stress": 0}


def test_run_task_caches_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "CACHE", tmp_path / "cache")
    t = {"key": "toy-tf1", "fam_tf": "toy-tf1", "family": "toy", "tf": "1", "inputs": {}, "variant": "real", "sess": "asia", "firm": "lucid", "n_trades": 0}
    r = A.run_task(t)
    assert r["status"] == "no_trades"
    rec = json.loads(A.cache_path("lucid", "toy-tf1", "asia").read_text())
    assert rec["status"] == "no_trades" and rec["metric"] == 0.0 and rec["n_trades"] == 0
    assert A.run_task(t) == {"key": "toy-tf1", "sess": "asia", "firm": "lucid", "cached": True}
    bad = {**t, "sess": "nyam", "n_trades": 5}                    # runs/toy-tf1 does not exist: recorded as an error, not raised
    assert A.run_task(bad)["status"] == "error"
    assert "error" in json.loads(A.cache_path("lucid", "toy-tf1", "nyam").read_text())
    assert A.load_cache()[("lucid", "toy-tf1", "asia")]["status"] == "no_trades"


def test_firm_table_and_formatting():
    assert list(A.FIRMS)[:6] == ["lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod", "apex300_eval"]
    assert list(A.FIRMS)[6:] == ["flex", "flex_dll", "pro_dll", "pro_nodll", "apex50_pa", "apex300_pa"]
    # SPEC 'USER FACTS 2026-10-02 07:20 ET': intraday is the primary breach model of EVERY account (Apex PA: its own real-time 'pess')
    assert all(A.FIRMS[f]["prim"] == "intraday" and A.FIRMS[f]["side"] == "realized" for f in ("lucid", "lucidpro", "lucidpro_nodll", "flex", "flex_dll", "pro_dll", "pro_nodll"))
    assert A.FIRMS["apex"]["prim"] == "intraday" and A.FIRMS["apex300_pa"]["prim"] == "pess" and "side" not in A.FIRMS["apex"]
    assert A.ns("lucid") == "lucid@intraday" and A.ns("lucid", side=True) == "lucid" and A.ns("apex") == "apex" == A.ns("apex", side=True)
    assert A.prim_of("flex") == "intraday" and A.prim_of("flex", side=True) == "realized" and A.prim_of("apex300_pa", side=True) == "pess"
    assert A.cache_path("flex", "k", "nyam").parent.name == "flex@intraday" and A.cache_path("flex", "k", "nyam", side=True).parent.name == "flex"
    assert A._fm("lucid", 0.3349) == ".33" and A._fm("flex", 1234.4, True) == "+1,234" and A._fm("flex", None) == "-"
    assert A._cell_txt("lucid", {"micros": 40, "day_lock": 0, "day_take": 1500, "day_stop": 0, "max_day_tr": 0, "target_take": 1}) == "m40 lk0 tk1500 st0 mt0 tt1"
    assert A._cell_txt("flex", {"micros": 40, "day_lock": 300, "day_take": 600, "day_stop": 0, "max_day_tr": 1, "policy": "max"}) == "m40 tk600 lk300 st0 mt1 Tmax"
    assert A.run_key("a-tf5") == "a-tf5" and A.run_key("a-tf5", "c2s2") == "a-tf5-c2s2"


def test_apex_search_fast_path_equals_score_search_funded():
    """apex_search (no second consistency reading per cell) gives the rows, the eligible set and the pick of score.search_funded."""
    key = "thin_side-tf5-c2s1"
    if not (A.RUNS / key / "trades.json").exists():
        pytest.skip("the screen bundles are not on disk")
    import score as S
    if S.blackout_wait_s() > 0:
        pytest.skip("inside an offline compute window")
    inputs = json.loads((A.RUNS / key / "run.json").read_text())["inputs"]
    keep = ("micros", "day_take", "day_lock", "day_stop", "max_day_tr", "policy", "e_net_40", "p_pay_20", "p_pay_40", "p_bust_pre_first",
            "stab_e_net_40", "score_e_net_40", "apex_noncompliant", "apex_mae_rule", "apex_one_direction", "apex_stop_5x_target")
    for firm, grid in (("apex300_pa", {"micros": [20, 150], "day_take": [0, 1500], "day_lock": [0], "day_stop": [0, 1500], "max_day_tr": [0], "policy": [500, "max"]}),
                       ("apex50_pa", {"micros": [10, 50], "day_take": [0, 600], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500]})):
        a = A.apex_search(str(A.RUNS / key), firm, "nyam", "thin_side", inputs, grid=grid)
        b = S.search_funded(str(A.RUNS / key), firm, sess="nyam", grid=grid, workers=1, strategy="thin_side", inputs=inputs)
        assert len(a["rows"]) == len(b["rows"]) > 0 and a["eligible"] == b["eligible"] and a["gate"] == b["gate"]
        assert [{k: r[k] for k in keep} for r in a["rows"]] == [{k: r[k] for k in keep} for r in b["rows"]]
        pa, pb = a["picks"]["e40_stable"], b["picks"]["e40_stable"]
        assert (pa is None) == (pb is None) and (pa is None or {k: pa[k] for k in keep} == {k: pb[k] for k in keep})


def test_period_extra_splits_build_and_pick_year(monkeypatch):
    rows = [{"date": "2022-05-02", "net": 100.0, "entry_price": 100.0, "sl": 95.0, "mae_usd": -40.0, "exit_ms": 1, "entry_ms": 0, "side": "long", "_sess": "mid"},
            {"date": "2023-12-29", "net": -30.0, "entry_price": 100.0, "sl": 110.0, "mae_usd": -200.0, "exit_ms": 2, "entry_ms": 1, "side": "short", "_sess": "mid"},
            {"date": "2024-01-02", "net": 50.0, "entry_price": 100.0, "sl": None, "mae_usd": -10.0, "exit_ms": 3, "entry_ms": 2, "side": "long", "_sess": "mid"},
            {"date": "2024-06-03", "net": 70.0, "entry_price": 100.0, "sl": 99.0, "mae_usd": -5.0, "exit_ms": 4, "entry_ms": 3, "side": "long", "_sess": "pm"}]
    monkeypatch.setattr(A, "load_rows", lambda key, runs=None: rows)
    x = A.period_extra("any", "mid")
    assert (x["trades_build"], x["net_build"], x["trades_pick2024"], x["net_pick2024"]) == (2, 70.0, 1, 50.0)
    assert x["stop_usd_median_1nq"] == 150.0 and x["stop_usd_p95_1nq"] == pytest.approx(195.0)      # stops of 5 and 10 points at $20
    assert A.period_extra("any", "asia")["trades_build"] == 0 and A.period_extra("any", "asia")["stop_usd_median_1nq"] is None


def test_the_name_screen_analyze_still_resolves_to_the_previous_pilots_module():
    """R's own modules (wf_offline, a3p3 ...; reached through score.walk_forward) do `import screen_analyze`: with L first on
    sys.path that must still be R/screen_analyze.py, not this pilot's command-line file of the same name."""
    import score  # noqa: F401  (puts R on sys.path the way every scorer does)
    import screen_analyze as SA
    assert hasattr(SA, "cal_for") and not hasattr(SA, "stage_report")
    assert SA.__spec__.origin.endswith("2026-09-29/screen_analyze.py")
    assert hasattr(A, "stage_report") and A.__name__ == "screen_analysis"
