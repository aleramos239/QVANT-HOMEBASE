"""Costs.oco_cancel_ms (robustness probe): the delayed cancel of the other OCO leg.
0 (default) = the law: the sibling is cancelled ON the fill print -> the same trades as before the setting existed
(synthetic prints here; one admitted member on real BUILD days against its stored rows: equality only, no P&L printed).
> 0: the sibling works on for that many ms; a trigger inside the window is a DOUBLE FILL (a second, independent position)."""
import datetime as dt
import json
from pathlib import Path

import pytest

import l2sim as S
from test_l2sim_fill_law import Script, at_session, tape

W = Path(__file__).resolve().parents[2]


def bracket(seen):
    def act(c):
        a = c.stop_entry("long", 101.0, sl=99.5, tp=103.0)
        b = c.stop_entry("short", 99.0, sl=100.5, tp=97.0)
        c.oco(a, b)
        seen["a"], seen["b"] = a, b
    return at_session(act)


def run(prints, ms, seen):
    return S.run_session(Script(bracket(seen)), tape(prints), costs=S.Costs(oco_cancel_ms=ms)).trades


def test_a_sibling_that_triggers_inside_the_cancel_window_is_a_double_fill():
    # long fills at 2.000 s; 30 ms later the tape is back through the short stop: inside a 50 ms window
    pr = [(1, 100.0), (2.0, 101.0), (2.03, 99.0), (10, 96.5), (1700, 96.5)]
    seen = {}
    tr = run(pr, 50, seen)
    assert seen["a"].status == "filled" and seen["b"].status == "filled" and len(tr) == 2
    lg, sh = tr                                                    # the long is stopped on the print that fills the short
    assert (lg["side"], lg["entry_price"], lg["exit_reason"], lg["exit_price"], lg["double_fill"]) == ("long", 101.25, "sl", 98.75, 1)
    assert (sh["side"], sh["entry_price"], sh["exit_reason"], sh["exit_price"], sh["double_fill"]) == ("short", 98.75, "tp", 97.0, 2)
    assert sh["sl"] == 100.5 and sh["tp"] == 97.0                  # the second position has its own stop and target
    assert lg["net"] == -2.5 * 20 - 4 and sh["net"] == 1.75 * 20 - 4
    assert sh["entry_ms"] - lg["entry_ms"] == 30
    # the law (0 ms): the short was cancelled on the long's fill print -> one trade, no tag
    one = run(pr, 0, seen)
    assert seen["b"].status == "cancelled" and len(one) == 1 and "double_fill" not in one[0]
    assert one[0] == {k: v for k, v in lg.items() if k != "double_fill"}


def test_a_late_cancel_without_a_fill_changes_nothing():
    # the short stop is touched 60 ms after the long's fill: the 50 ms cancel has landed
    pr = [(1, 100.0), (2.0, 101.0), (2.06, 99.0), (10, 96.5), (1700, 96.5)]
    seen = {}
    tr = run(pr, 50, seen)
    assert seen["a"].status == "filled" and seen["b"].status == "cancelled"
    assert len(tr) == 1 and "double_fill" not in tr[0] and tr == run(pr, 0, seen)
    # the window is [fill, fill + ms): a print exactly ms later is too late, one 1 ms earlier fills
    assert len(run([(1, 100.0), (2.0, 101.0), (2.05, 99.0), (1700, 99.0)], 50, seen)) == 1
    assert len(run([(1, 100.0), (2.0, 101.0), (2.049, 99.0), (1700, 99.0)], 50, seen)) == 2


def test_a_first_leg_closed_before_the_late_fill_is_tagged_too_and_the_setting_is_validated():
    # the long is stopped at 2.010 s (its own stop, above the short entry); the short fills at 2.030 s
    def act(c):
        c.oco(c.stop_entry("long", 101.0, sl=100.0), c.stop_entry("short", 99.0, sl=100.5))
    pr = [(1, 100.5), (2.0, 101.0), (2.01, 100.0), (2.03, 99.0), (1700, 99.0)]
    tr = S.run_session(Script(at_session(act)), tape(pr), costs=S.Costs(oco_cancel_ms=50)).trades
    assert [(t["side"], t["exit_reason"], t["double_fill"]) for t in tr] == [("long", "sl", 1), ("short", "eod", 2)]
    with pytest.raises(ValueError):
        S.Costs(oco_cancel_ms=-1)
    assert S.Costs().oco_cancel_ms == 0


def test_default_is_bit_identical_on_a_member():
    """straddle_tight_0830_GC evA (OCO bracket at 08:29:59) on its first 12 BUILD trade days: default Costs and
    oco_cancel_ms = 0 both reproduce the member's stored rows field by field."""
    import families as F
    d = W / "members" / "straddle_tight_0830_GC_tf30_pre_evA"
    if not d.exists():
        pytest.skip("member folder not on this machine")
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    spec = json.loads((d / "spec.json").read_text())
    stored = json.loads((d / "trades_build.json").read_text())
    days = sorted({t["date"] for t in stored})[:12]
    if any(S.load_tape(dt.date.fromisoformat(x), "GC") is None for x in days[:2]):
        pytest.skip("GC tapes not cached")
    ref = [t for t in stored if t["date"] in days]
    cls = F.REGISTRY[spec["family"]][0]
    for costs in (None, S.Costs(oco_cancel_ms=0)):
        got = S.run(cls, spec["inputs"], days=days, root="GC", workers=1, costs=costs)["trades"]
        assert len(got) == len(ref) >= 10 and all(t["oco"] for t in got)
        assert [{k: t[k] for k in r} for t, r in zip(got, ref)] == ref
        assert not any("double_fill" in t for t in got)
