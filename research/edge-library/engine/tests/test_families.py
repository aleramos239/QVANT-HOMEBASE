"""The family registry (families/): contract checks, and for EVERY registered family x screen tf the same trades at 1 and at 8
worker processes (a Template subclass is split over workers: any state that survives a session would change its trades).
Runs on 8 fixed in-sample days (one per worker). Only equality and counts are asserted: no P&L is looked at.
L2_TEST_WORKERS (default 8) lowers the worker count on a busy machine."""
import importlib
import os

import pytest

import fam_fixtures as FX
import families
import l2ref
import l2sim
import screen

W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), l2sim.MAX_WORKERS))
DAYS = [d for d in screen.SMOKE_DAYS if d < "2024"] + ["2023-07-03"]       # 8 fixed BUILD days (PICK is the Admit stage's)
CASES = [(name, tf) for name, e in sorted(families.REGISTRY.items()) for tf in e[0].SCREEN_TFS]
REF = [(l2ref.Donchian, {"tf": "15"}), (l2ref.Straddle, {"tf": "30", "stop_val": 3.0, "off_atr": 0.25}), (l2ref.Orb, {"tf": "5", "or_min": "5"}),
       (FX.ToyImb, {"tf": "5"}), (FX.ToyBracket, {"tf": "5"})]


def pair(cls, params, cols, **kw):
    """The same run at 1 and at W workers -> (result 1, result W)."""
    if l2sim.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    try:
        feats = l2sim.L2Features(cols) if cols else None
        a = l2sim.run(cls, params, days=DAYS, workers=1, features=feats, **kw)
        b = l2sim.run(cls, params, days=DAYS, workers=W, features=feats, **kw)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    return a, b


def test_registry_loads_without_errors():
    assert families.ERRORS == {}, families.ERRORS
    assert set(families.MODULE_OF) == set(families.REGISTRY)
    for name, entry in families.REGISTRY.items():
        # the AUTHOR's entry (REGISTRY keeps its first four fields; an edge-library family -- FEATURES = () is legal there
        # only -- is a 5-tuple, and checking its 4-tuple would wrongly demand Level-2 features)
        full = getattr(importlib.import_module(f"families.{families.MODULE_OF[name]}"), "FAMILIES")[name]
        assert tuple(full[:4]) == entry and (len(full) == 5) == (name in families.LIBRARY)
        assert families.check_entry(name, full) == []
        assert families.columns(name) == entry[0].FEATURES and families.screen_inputs(name, "5")["sess"] == "all"


@pytest.mark.parametrize("name,tf", CASES, ids=[f"{n}-tf{t}" for n, t in CASES])
def test_registered_family_gives_identical_trades_at_1_and_8_workers(name, tf):
    cls, _, both, _ = families.REGISTRY[name]
    a, b = pair(cls, families.screen_inputs(name, tf), cls.FEATURES, **getattr(cls, "SCREEN_RUN", {}))
    assert a["skipped_by_error"] == 0 and b["skipped_by_error"] == 0, (a["no_trade"][:2], b["no_trade"][:2])
    assert a["trades"] == b["trades"]                        # every field of every trade, in order
    assert a["sessions"] == b["sessions"] == len(DAYS) and a["both_sides_sessions"] == b["both_sides_sessions"]
    assert a["meta"]["workers"] == 1 and b["meta"]["workers"] == (W if cls.session_independent else 1)
    if not both:                                             # declared one direction: the simulator must agree
        assert a["both_sides_sessions"] == 0 and not any(t["both_sides"] or t["oco"] for t in a["trades"])
    if cls.FEATURES:
        import score
        score.C2Features(cls.FEATURES, seed=1)               # the C2 null of the screen can be built for these columns


@pytest.mark.parametrize("cls,params", REF, ids=[c.__name__ for c, _ in REF])
def test_reference_families_give_identical_trades_at_1_and_8_workers(cls, params):
    a, b = pair(cls, params, getattr(cls, "FEATURES", None))
    assert a["trades"] == b["trades"] and len(a["trades"]) > 0 and a["skipped_by_error"] == 0
    assert a["meta"]["workers"] == 1 and b["meta"]["workers"] == W and a["both_sides_sessions"] == b["both_sides_sessions"]


def test_the_parity_check_catches_state_that_survives_a_session():
    a, b = pair(FX.Leaky, {"tf": "5", "n": 10}, FX.Leaky.FEATURES)
    assert a["skipped_by_error"] == 0 and len(a["trades"]) > 0
    assert a["trades"] != b["trades"]                        # 1 worker: every second day trades; W workers: fresh instances


def entry(cls=FX.ToyImb, inputs=None, both=False, notes="B1 test"):
    return (cls, {} if inputs is None else inputs, both, notes)


def test_check_entry_accepts_the_contract_and_names_every_violation():
    assert families.check_entry("toy_imb", entry()) == []
    assert families.check_entry("toy_imb", entry(inputs={"k": 0.3, "stop_val": 2.0})) == []

    def bad(name="toy", e=None, **attrs):
        e = e or entry(type("X", (FX.ToyImb,), attrs))
        out = families.check_entry(name, e)
        assert out, (name, attrs)
        return " | ".join(out)

    assert "lower-case" in bad(name="Toy-Imb", e=entry())
    assert "entry must be the tuple" in bad(e=(FX.ToyImb, {}, False))
    assert "subclass l2sim.Template" in bad(e=entry(l2ref.FeatureProbe))
    assert "both_sides must be" in bad(e=entry(both=None)) and "notes" in bad(e=entry(notes=" "))
    assert "must not set tf" in bad(e=entry(inputs={"tf": "1"})) and "must not set tf" in bad(e=entry(inputs={"sess": "nyam"}))
    assert "refused by resolve_inputs" in bad(e=entry(inputs={"k": 7.0})) and "refused" in bad(e=entry(inputs={"nope": 1}))
    assert "SCHEMA does not declare" in bad(DEFAULTS={"m": 5.0})
    assert "f_depth must stay 'off'" in bad(e=entry(inputs={"f_depth": "thin"}))
    assert "SCREEN_TFS" in bad(SCREEN_TFS=("2",)) and "SCREEN_TFS" in bad(SCREEN_TFS=()) and "SCREEN_TFS" in bad(SCREEN_TFS=["5"])
    assert "FEATURES must be" in bad(FEATURES=()) and "does not have" in bad(FEATURES=("imb10_z",))
    assert "research-tier" in bad(FEATURES=("imb10", "rt_size_imb")) and "nothing to shuffle" in bad(FEATURES=("bid_px", "f_c"))
    assert "SCREEN_RUN" in bad(SCREEN_RUN={"slip_ticks": 2}) and "SCREEN_RUN" in bad(SCREEN_RUN={"strict_limit": 1})
    assert families.check_entry("wall", entry(type("B4", (FX.ToyImb,), {"SCREEN_RUN": {"strict_limit": True}}))) == []
    tiers = families.feature_columns()
    assert tiers["imb10"] == tiers["f_delta"] == tiers["depth10_rel20d"] == "feature" and tiers["bid_px"] == tiers["f_c"] == "fixed"
    assert tiers["rt_size_imb"] == "research" and "date" not in tiers and "session" not in tiers
