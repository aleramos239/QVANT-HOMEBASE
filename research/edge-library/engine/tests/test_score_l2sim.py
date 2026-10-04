"""End to end: trades produced by the offline sim (l2sim) feed the scoring adapter unchanged (in-memory list, L/trades file,
l2sim.write_bundle directory). Light: one approved config replayed on 30 in-sample sessions, single process."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

E = S.E
B = S.BASELINE["flex_eval"]                    # hm2-straddle-tf30#10 (nyam): the approved Flex eval source


@pytest.fixture(scope="module")
def sim():
    l2sim = pytest.importorskip("l2sim")
    l2ref = pytest.importorskip("l2ref")
    if S.blackout_wait_s():
        pytest.skip("inside an offline compute window")
    d = S._R_SRC_DIR(B["src"])
    inputs = json.loads((d / "run.json").read_text())["inputs"]
    days = S.in_sample_sessions()[400:430]
    try:
        res = l2sim.run(l2ref.FAMILIES["straddle"], inputs, days=days, workers=1)
    except FileNotFoundError as e:
        pytest.skip(f"tape / cache not available: {e}")
    return l2sim, res, days


def test_sim_trades_satisfy_the_loader_contract(sim):
    l2sim, res, days = sim
    rows = res["trades"]
    assert len(rows) >= 30 and S.validate_trades(rows) == []
    assert set(S.REQUIRED) <= set(rows[0])
    tr = S.load_trades(rows)
    assert tr.n == len(rows) and set(tr.iso) <= set(days) and (tr.sess >= 0).all()
    ref = [r for r in json.loads(S.trade_file(S.export_name(B["key"])).read_text()) if r["date"] in set(days)] \
        if S.trade_file(S.export_name(B["key"])).exists() else None
    if ref is not None:                        # the sim replays the tester on these sessions (the sim's own gate is SIM_VALIDATION.md)
        same = {(r["date"], r["side"], r["entry_price"], r["exit_price"], r["exit_reason"]) for r in ref}
        got = {(r["date"], r["side"], r["entry_price"], r["exit_price"], r["exit_reason"]) for r in rows}
        assert len(same & got) >= 0.9 * len(same)


def test_sim_trades_score_through_every_entry_point(sim, tmp_path, monkeypatch, l_tmp):
    l2sim, res, days = sim
    rows = res["trades"]
    rules = {"day_lock": 750, "day_take": 1500, "target_take": 1}
    a = S.score_eval(rows, "lucid", rules, micros=40, sess="nyam", boots=0)
    monkeypatch.setattr(S, "TRADES", tmp_path)
    (tmp_path / "straddle_tf30_c10_sim.json").write_text(json.dumps(rows))
    b = S.score_eval("file:straddle_tf30_c10_sim", "lucid", rules, micros=40, sess="nyam", boots=0)
    bundle = l2sim.write_bundle(res, l_tmp / "score_test_bundle")
    # the run covered 30 of the 825 sessions (days=...): scored on the default calendar the other 795 would count as flat days,
    # so the sim result and its bundle are REFUSED until the caller names the calendar (a bare row list cannot be checked)
    for src in (res, str(bundle)):
        with pytest.raises(ValueError, match="covered 30 sessions, the calendar .* has 825"):
            S.score_eval(src, "lucid", rules, micros=40, sess="nyam", boots=0)
        with pytest.raises(ValueError, match="covered 30 sessions"):
            S.score_funded(src, "flex", 500, micros=20, sess="nyam", boots=0)
        with pytest.raises(ValueError, match="covered 30 sessions"):
            S.lift_vs_control(src, [rows], "lucid", rules, micros=40, sess="nyam", mode="direct", boots=0)
    sub = S.score_eval(res, "lucid", rules, micros=40, sess="nyam", boots=0, calendar=days)          # the days the run covered
    assert sub["window"]["sessions"] == 30 and sub["n_trades"] == a["n_trades"]
    assert S.score_eval(str(bundle), "lucid", rules, micros=40, sess="nyam", boots=0, calendar=days)["models"] == sub["models"]
    c = S.score_eval(str(bundle), "lucid", rules, micros=40, sess="nyam", boots=0, calendar=S.in_sample_sessions())
    assert S.is_file_source(str(bundle)) and S.load_trades(str(bundle), calendar=days).label == "score_test_bundle"
    # an in-memory sim result is named after its strategy + inputs (never 'inline': two configs must not share a C1 seed)
    lab = S.load_trades(res, calendar=days).label
    assert lab.startswith("Straddle|") and "off_atr=0.25" in lab and "tf=30" in lab and S.load_trades(rows).label == "inline"
    assert S.default_seed(lab, "nyam") != S.default_seed("inline", "nyam")
    for r in (b, c):
        assert r["models"] == a["models"] and r["series"] == a["series"]
    assert a["window"]["sessions"] == 825 and a["series"]["trade_days"] <= 30 and a["n_trades"] > 0
    f = S.score_funded(rows, "flex", 500, micros=20, rules={"day_take": 600}, sess="nyam", boots=0)
    assert f["n_starts"] == 766 and f["trades"] == a["n_trades"]
    x = S.score_funded(rows, "apex", 500, micros=20, sess="nyam", boots=0, strategy="straddle", inputs={"tgt_r": 2.0})
    assert "OCO_both_side_orders" in x["apex_flags"]               # straddles are non-compliant at Apex (SPEC)
    lift = S.lift_vs_control(rows, [rows], "lucid", rules, micros=40, sess="nyam", mode="direct", boots=0)
    assert lift["lift"] == 0.0
