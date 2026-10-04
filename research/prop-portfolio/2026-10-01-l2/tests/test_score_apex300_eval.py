"""score.py firm 'apex300_eval' (the Apex Legacy 300K EVALUATION): P(pass <= 10 / 20 trading days) and bust, hand-worked on
synthetic ledgers; the loader hardening (default label of an in-memory sim result, subset runs); score_baseline + the gate."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

pytestmark = pytest.mark.usefixtures("trades_tmp")      # exports go to a directory of this module's own, never to L/trades
ET = S.ET
CAL = S.in_sample_sessions()


def row(date, pts, t0="10:00", mins=5, mae_pts=0.0, mfe_pts=None, side="long", **kw):
    """One 1-NQ trade closing `pts` points in favour (negative = against), a market entry with a 30-pt stop and a 60-pt target."""
    h, m = (int(x) for x in t0.split(":"))
    ms = int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(h, m), tzinfo=ET).timestamp() * 1000)
    sg = 1.0 if side == "long" else -1.0
    gross = pts * 20.0
    mfe_pts = max(pts, 0.0) if mfe_pts is None else mfe_pts
    r = {"date": date, "side": side, "qty": 1, "entry_price": 15000.0, "exit_price": 15000.0 + sg * pts, "exit_reason": "time",
         "gross": gross, "commission": 4.0, "net": gross - 4.0, "mae_pts": mae_pts, "mfe_pts": mfe_pts, "mae_usd": mae_pts * 20.0,
         "mfe_usd": mfe_pts * 20.0, "entry_ms": ms, "exit_ms": ms + mins * 60000, "sl": 15000.0 - sg * 30.0, "tp": 15000.0 + sg * 60.0,
         "order_price": None}
    r.update(kw)
    return r


def every_day(pts, **kw):
    return [row(d, pts, **kw) for d in CAL]


def test_firm_is_the_help_centre_reading_of_the_legacy_300k_evaluation():
    r = S.score_eval(every_day(5.0), "apex300_eval", micros=300, boots=0)
    assert r["firm"] == "apex300_eval" and r["horizons"] == [10, 20] and r["primary"] == r["model"] == "pess"
    assert r["spec"] == {"target": 20000.0, "mll": 7500.0, "trail": "intraday", "lock_at": None, "cap": 350, "min_days": 7, "commission": "apex"}
    assert r["window"]["sessions"] == 825 and r["n_starts"] == 825 - 20 + 1 and r["n_trades"] == 825 and set(r["models"]) == {"pess", "nat", "opt"}
    assert "min_days" in r["unconfirmed"] and "trail" in r["unconfirmed"] and r["eval300"]["price_month"] == 797.0
    assert set(r["variants"]) == {"holder_rule_file", "min_days_1", "trail_eod"}
    assert "apex300_eval" not in S.EVAL_FIRMS and "apex300_eval" not in S.funded_variants()      # its own horizon: not a 5-day firm
    with pytest.raises(ValueError, match="350"):
        S.score_eval(every_day(5.0), "apex300_eval", micros=360, boots=0)
    with pytest.raises(ValueError, match="EVALUATION"):
        S.funded_spec(S._ext().make_eval_spec())
    with pytest.raises(ValueError):
        S.score_eval(every_day(5.0), "apex300_eval", model="realized", micros=300, boots=0)


def test_pass_within_10_and_20_trading_days_hand_worked():
    # +5 pts a day = +$100 per NQ. Apex commissions: $3.98 per NQ round turn (10 micros).
    # 300 micros: 3,000 - 119.40 = 2,880.60 a day -> 20,164.20 on day 7 (and 7 traded days): every start passes on day 7
    r = S.score_eval(every_day(5.0), "apex300_eval", micros=300, boots=200)
    assert (r["p_pass_10"], r["p_pass_20"], r["bust_10"], r["bust_20"], r["med_days"]) == (1.0, 1.0, 0.0, 0.0, 7.0)
    assert (r["p10"], r["p20"], r["bust10"], r["bust20"]) == (1.0, 1.0, 0.0, 0.0) and r["ci_p10"] == [1.0, 1.0] and r["ci_bust20"] == [0.0, 0.0]
    # 350 micros: the goal is reached on day 6 (6 x 3,360.70 = 20,164.20) but the 7-day minimum holds the pass until day 7;
    # the account holder's rule file (1 day, R's $4.00) passes on day 6
    r = S.score_eval(every_day(5.0), "apex300_eval", micros=350, boots=0)
    assert r["med_days"] == 7.0 and r["variants"]["holder_rule_file"]["med_days"] == 6.0 and r["variants"]["min_days_1"]["med_days"] == 6.0
    # 150 micros: 1,440.30 a day -> day 14: inside 20 days, not inside 10. 100 micros: 960.20 a day -> day 21: neither
    r = S.score_eval(every_day(5.0), "apex300_eval", micros=150, boots=0)
    assert (r["p_pass_10"], r["p_pass_20"], r["med_days"], r["neither_10"]) == (0.0, 1.0, 14.0, 1.0)
    r = S.score_eval(every_day(5.0), "apex300_eval", micros=100, boots=0)
    assert (r["p_pass_10"], r["p_pass_20"], r["bust_20"], r["neither_20"], r["med_days"]) == (0.0, 0.0, 0.0, 1.0, None)
    assert S.score_eval(every_day(5.0), "apex300_eval", {"micros": 100}, boots=0)["models"] == r["models"]      # micros in the rules dict
    # a trade every second session (+8 pts): the goal is there after 5 traded days, but 7 TRADED days take 13 or 14 sessions
    alt = S.score_eval([row(d, 8.0) for d in CAL[::2]], "apex300_eval", micros=300, boots=0, arrays=True)
    assert alt["p_pass_10"] == 0.0 and alt["p_pass_20"] == 1.0 and set(np.unique(alt["arrays"]["pess"][1]).tolist()) == {13, 14}
    # 'pess' = a winner is assumed to round-trip from its best point to its worst: a single +15 pt trade at 300 micros (best
    # +9,000, worst -commission) is a give-back above the $7,500 threshold -> bust; the optimistic order passes it
    big = S.score_eval(every_day(15.0), "apex300_eval", micros=300, boots=0)
    assert big["models"]["pess"]["bust_10"] == 1.0 and big["models"]["opt"]["p_pass_10"] == 1.0


def test_bust_on_the_live_balance_and_the_models():
    # -25 pts a day at 200 micros = -10,000 - 79.60: below -7,500 on day 1
    r = S.score_eval(every_day(-25.0, mae_pts=25.0), "apex300_eval", micros=200, boots=0)
    assert (r["bust_10"], r["bust_20"], r["p_pass_20"]) == (1.0, 1.0, 0.0)
    # a +10 pt day whose trade first ran +200 pts (open profit 300 micros x 200 pts x $2 = +120,000 ... far above), then closed +10:
    # the threshold trails the LIVE balance -> the give-back from the high busts under every event order; under the account
    # holder's EOD trail nothing happens
    spike = every_day(10.0, mfe_pts=200.0)
    r = S.score_eval(spike, "apex300_eval", micros=300, boots=0)
    assert all(r["models"][m]["bust_10"] == 1.0 for m in ("pess", "nat", "opt"))
    assert r["variants"]["trail_eod"]["bust_20"] == 0.0 and r["variants"]["holder_rule_file"]["bust_20"] == 0.0
    # an open loss that is recovered: -30 pts adverse (300 micros: -18,000) then +5 at the close -> bust on the open loss
    dip = every_day(5.0, mae_pts=30.0)
    r = S.score_eval(dip, "apex300_eval", micros=300, boots=0)
    assert r["bust_10"] == 1.0 and S.score_eval(dip, "apex300_eval", micros=100, boots=0)["bust_20"] == 0.0      # 100 micros: -6,000


def test_rules_target_take_and_coast_and_the_score_level_equals_apex300():
    ax = S._ext()
    led = [row(d, (9.0 if i % 4 else -12.0), mae_pts=(2.0 if i % 4 else 12.0), mfe_pts=(10.0 if i % 4 else 1.0)) for i, d in enumerate(CAL)]
    rules = {"day_take": 4000, "day_stop": 5000, "target_take": 1}
    r = S.score_eval(led, "apex300_eval", rules, micros=250, boots=0, arrays=True)
    assert r["rules"] == {"day_take": 4000.0, "day_lock": 0.0, "day_stop": 5000.0, "max_day_tr": 0, "target_take": True}
    P = ax.port_from_trades(led, micros=250, sess="all", calendar=CAL)
    spec = ax.make_eval_spec()
    for m in ("pess", "nat", "opt"):
        o, d = ax.eval_lifecycle(spec, ax.eval_src(spec, P, {"day_take": 4000, "day_stop": 5000}, 250), 20, m, target_take=True)
        assert (o == r["arrays"][m][0]).all() and (d == r["arrays"][m][1]).all() and r["models"][m] == ax.eval_metrics(o, d)
    assert 0.0 < r["p_pass_20"] < 1.0 or r["bust_20"] > 0.0 or r["p_pass_20"] in (0.0, 1.0)
    c1 = S.score_apex300_eval(led, rules, micros=250, boots=0, coast=1)
    assert c1["coast"] == 1 and c1["models"]["pess"] == r["coast1"] and r["coast"] == 0
    assert S.score_apex300_eval(led, rules, micros=250, boots=0, variants=False).get("variants") is None
    h = S.score_apex300_eval(led, rules, micros=250, boots=0, **ax.EVAL_VARIANTS["holder_rule_file"])
    assert h["models"]["pess"] == r["variants"]["holder_rule_file"] and h["spec"]["min_days"] == 1
    # sess filter and the session calendar of a sub-window
    assert S.score_eval(led, "apex300_eval", micros=250, sess="pm", boots=0)["skipped"].startswith("no trades")
    sub = S.score_eval([x for x in led if x["date"] <= CAL[59]], "apex300_eval", micros=250, boots=0, calendar=CAL[:60])
    assert sub["n_starts"] == 41 and sub["window"]["sessions"] == 60


def test_one_direction_applies_to_the_evaluation_too():
    led = every_day(5.0)
    r = S.score_eval(led, "apex300_eval", micros=300, boots=0)
    assert r["compliance"] == {"one_direction": "UNCHECKED"} and r["compliant"] is False            # market entries, nothing declared
    r = S.score_eval(led, "apex300_eval", micros=300, boots=0, both_sides=False)
    assert r["compliance"] == {"one_direction": "ok"} and r["compliant"] is True and r["one_direction_basis"] == "market_entries"
    stamped = [dict(x, order_price=15000.0, both_sides=False, oco=False) for x in led]              # l2sim rows of a one-sided limit family
    assert S.score_eval(stamped, "apex300_eval", micros=300, boots=0)["one_direction_basis"] == "sim_rows"
    oco = [dict(x, order_price=15000.0, both_sides=True, oco=True) for x in led]
    for kw in (dict(), dict(both_sides=False)):
        assert S.score_eval(oco, "apex300_eval", micros=300, boots=0, **kw)["compliance"] == {"one_direction": "FAIL"}
    assert S.score_eval(led, "apex300_eval", micros=300, boots=0, strategy="straddle", both_sides=False)["compliant"] is False
    assert any(w.startswith("AUTOMATION_PROHIBITED") for w in r["warnings"])
    # R's eval firms ignore the gate arguments
    a = S.score_eval(led, "apex", micros=40, boots=0)
    assert S.score_eval(led, "apex", micros=40, boots=0, strategy="x", inputs={"tgt_r": 2.0}, both_sides=False)["models"] == a["models"]


def test_search_apex300_eval_grid_rows_and_picks(tmp_path):
    led = [row(d, (9.0 if i % 4 else -12.0), mae_pts=(2.0 if i % 4 else 12.0), mfe_pts=(10.0 if i % 4 else 1.0)) for i, d in enumerate(CAL)]
    g = {"micros": [150, 250, 350], "day_lock": [0], "day_take": [0, 3000], "day_stop": [0], "max_day_tr": [0], "target_take": [0, 1]}
    s = S.search_rules(led, "apex300_eval", grid=g, boots=0, out_csv=str(tmp_path / "ev.csv"))
    assert s["firm"] == "apex300_eval" and s["cells"] == 12 and len(s["rows"]) == 12 and s["shape"] == [3, 1, 2, 1, 1, 2]
    for r in s["rows"]:
        one = S.score_eval(led, "apex300_eval", {k: r[k] for k in S.AX[1:]}, micros=r["micros"], boots=0)
        assert (r["p10"], r["p20"], r["bust10"], r["bust20"]) == (one["p_pass_10"], one["p_pass_20"], one["bust_10"], one["bust_20"])
    for nm, k in (("primary", "p20"), ("p10", "p10")):
        p = s["picks"][nm]
        best = max(r[f"stab_{k}"] for r in s["rows"])
        assert p["stab"] == best and p["detail"]["rules"]["target_take"] == bool(p["rules"]["target_take"]) and p["detail"]["micros"] == p["rules"]["micros"]
    assert (tmp_path / "ev.csv").read_text().splitlines()[0].startswith("firm,model,micros,day_lock,day_take,day_stop,max_day_tr,target_take")
    assert S.APEX300_EVAL_GRID["micros"][-1] == 350 and int(np.prod([len(S.APEX300_EVAL_GRID[a]) for a in S.AX])) == 1008
    assert S.search_apex300_eval(led, grid={**g, "micros": [400]}, boots=0)["rows"] == []           # above the 35-mini limit: not scored
    with pytest.raises(ValueError, match="ONE trade source"):
        S.search_apex300_eval([{"src": led, "sess": "nyam"}, {"src": led, "sess": "pm"}], grid=g)


# ------------------------------------------------------------------ loader hardening / baseline gate

def test_sim_result_label_and_subset_refusal():
    rows = every_day(5.0)[:100]
    meta = {"strategy": "families.b_imbalance.BimbFollow", "inputs": {"tf": "5", "k": 2.0, "sess": "all"}, "range": {"start": S.IS_START, "end": S.IS_END}}
    res = {"trades": rows, "sessions": 825, "used": 820, "skipped_by_error": 0, "both_sides_sessions": 0, "meta": meta}
    t = S.load_trades(res)
    assert t.label == "BimbFollow|k=2.0,sess=all,tf=5" == S.sim_label(meta) and t.both_sides_sessions == 0
    other = S.load_trades({**res, "meta": {**meta, "inputs": {**meta["inputs"], "k": 3.0}}})
    assert other.label != t.label and S.default_seed(other.label, "nyam") != S.default_seed(t.label, "nyam")
    assert S.load_trades(res, label="mine").label == "mine" and S.load_trades(rows).label == "inline" and S.sim_label({}) is None
    sub = {**res, "sessions": 10}
    with pytest.raises(ValueError, match="covered 10 sessions, the calendar .* has 825"):
        S.load_trades(sub)
    with pytest.raises(ValueError, match="covered 10 sessions"):
        S.score_eval(sub, "lucid", micros=20, boots=0)
    assert S.load_trades(sub, calendar=CAL[:100]).n == 100 and S.load_trades(sub, strict=False).n == 100
    assert S.score_eval(sub, "lucid", micros=20, boots=0, calendar=CAL[:100])["window"]["sessions"] == 100
    short = {**res, "sessions": 60, "meta": {**meta, "range": {"start": CAL[0], "end": CAL[59]}}}        # a full run of a shorter range
    assert S.load_trades({**short, "trades": rows[:60]}).range == (CAL[0], CAL[59])
    # the run-level both-side count reaches the Apex gate
    two = S.score_funded({**res, "both_sides_sessions": 4}, "apex300_pa", 500, micros=20, boots=0, both_sides=False)
    assert two["compliance"]["one_direction"] == "FAIL" and "OCO_both_side_orders" in two["apex_flags"]
    one = S.score_funded(res, "apex300_pa", 500, micros=20, boots=0, both_sides=False)
    assert one["compliance"]["one_direction"] == "ok" and one["one_direction_basis"] == "market_entries"


def test_score_baseline_passes_the_family_metadata_to_the_gate():
    """The recheck's case: out/baseline_insample.json recorded the approved Apex 50K PA pick as non-compliant because
    score_baseline did not hand BASELINE_META (strategy, inputs, both_sides) to the gate."""
    b = S.score_baseline("apex_pa_funded", boots=0)
    assert b["compliance"] == {"one_direction": "ok", "stop_5x_target": "ok", "mae_rule": "ok"} and b["compliant"] is True
    assert b["e_net_40"] == pytest.approx(1093.08, abs=0.01)                                           # the number is the bar's
    bare = S.score_funded(S._baseline_src(S.BASELINE["apex_pa_funded"], "file"), "apex", 1000, micros=30, sess="nyam", boots=0,
                          rules=S.BASELINE["apex_pa_funded"]["rules"])
    assert bare["compliance"]["one_direction"] == "UNCHECKED" and bare["e_net_40"] == b["e_net_40"]
    # an OCO family stays non-compliant with its metadata, on the 300K PA too (tester rows carry no stamp: the family table and
    # the declaration fail it)
    x = S.score_funded(S._baseline_src(S.BASELINE["flex_eval"], "file"), "apex300_pa", 500, micros=30, sess="nyam", boots=0,
                       **S.BASELINE_META["hm2-straddle-tf30#10"])
    assert x["compliance"]["one_direction"] == "FAIL" and x["compliant"] is False
    y = S.score_funded(S._baseline_src(S.BASELINE["flex_eval"], "file"), "apex300_pa", 500, micros=30, sess="nyam", boots=0, both_sides=False)
    assert y["compliance"]["one_direction"] == "UNCHECKED"          # the hole: straddle rows, no family name, 'one direction' declared


def test_export_bundle_uses_a_temp_name_of_its_own(trades_tmp, tmp_path):
    src = S.BASELINE["apex_pa_funded"]["src"]
    p = S.export_bundle(src, "zz_export_test")
    assert p.parent == trades_tmp and not list(trades_tmp.glob("*.tmp"))
    q = S.export_bundle(src, "zz_export_test", out_dir=tmp_path)
    assert q == tmp_path / "zz_export_test.json" and q.read_text() == p.read_text() and not list(tmp_path.glob("*.tmp"))
    import inspect
    assert ".json.tmp" not in inspect.getsource(S.export_bundle)
