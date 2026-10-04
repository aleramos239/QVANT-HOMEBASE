"""The SIM VALIDATION GATE as a test: the three approved tester strategies replayed in-sample must reproduce the
tester's bundles (>= 95% identical trades, total net within 2%). Also checks that the comparison can fail."""
import pytest

import l2ref
import l2sim as S
import sim_validate as V


@pytest.mark.parametrize("cfg", V.GATE, ids=[c[0] for c in V.GATE])
def test_gate_config_reproduces_the_tester_bundle(cfg):
    o = V.one(*cfg, workers=8)
    for scope in ("all", "pick"):
        c = o[scope]
        assert c["n_ref"] > 500
        assert c["match_rate"] >= 0.95, (scope, c["match_rate"])
        assert c["net_diff_pct"] <= 2.0, (scope, c["net_diff_pct"])
    assert o["gate_pass"] and o["skipped_sim"] == o["skipped_ref"]
    assert o["skipped_by_error"] == 0 and o["stress"] is None        # the gate runs the tester law, no session dropped
    assert o["elapsed_s"] < 60.0                                 # SPEC target: a full in-sample run <= 60 s on 8 workers


def test_bundles_hold_no_sealed_rows_and_cover_the_in_sample_window():
    for cid, fam, src, sess, role in V.GATE + V.EXTRA:
        inputs, ref, cov, cost, engine = V.load_bundle(src)
        assert min(t["date"] for t in ref) >= V.START and max(t["date"] for t in ref) <= V.END < "2025-01-01"
        assert cost == {"qty": 1, "commission": 4.0, "slippage_ticks": 1.0} and engine == "tick-2"


def test_the_comparison_is_sensitive_to_the_fill_law():
    """Negative control: with no slippage / no placement latency the same strategy must NOT match the bundle."""
    cid, fam, src, sess, role = V.GATE[0]
    inputs, ref, cov, cost, engine = V.load_bundle(src)
    ref = [t for t in ref if "2024-10-01" <= t["date"] <= "2024-12-31"]
    ok = S.run(l2ref.Straddle, inputs, "2024-10-01", "2024-12-31", workers=1)["trades"]
    assert V.compare(ok, ref)["match_rate"] == 1.0 and len(ref) > 200
    noslip = S.run(l2ref.Straddle, inputs, "2024-10-01", "2024-12-31", workers=1, costs=S.Costs(4.0, 0.0))["trades"]
    assert V.compare(noslip, ref)["match_rate"] < 0.05
    cid, fam, src, sess, role = V.GATE[2]                       # market entries: the 85 ms latency decides the fill print
    inputs, ref, cov, cost, engine = V.load_bundle(src)
    ref = [t for t in ref if "2024-10-01" <= t["date"] <= "2024-12-31"]
    assert V.compare(S.run(l2ref.Donchian, inputs, "2024-10-01", "2024-12-31", workers=1)["trades"], ref)["match_rate"] == 1.0
    nolat = S.run(V.DonchianNoLatency, inputs, "2024-10-01", "2024-12-31", workers=1)["trades"]
    assert V.compare(nolat, ref)["match_rate"] < 0.6
