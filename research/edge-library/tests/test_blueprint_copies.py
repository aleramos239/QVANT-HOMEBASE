"""Line 2.5: a neighbor table that is the home table's trades again counts once (BLUEPRINT: "tables that are the same trades
count once"). Read-only on the demo idea's build stores in runs_bp/ (skipped when they are not on disk)."""
import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(W / "engine")]
from blueprint import lines as L      # noqa: E402
from blueprint import tables as T     # noqa: E402

DEMO = "demo_range_break_nq"
needs_demo = pytest.mark.skipif(not (W / "runs_bp" / f"{DEMO}-NQ-tf15").exists(), reason="the demo idea's stores are not on disk")


@needs_demo
def test_a_bar_size_that_trades_like_the_home_table_is_a_copy_and_another_market_is_not():
    like = T.sigs(DEMO, "NQ", "15", "nyam")
    five, es = T.place(DEMO, "NQ", "5", "nyam", like=like), T.place(DEMO, "ES", "15", "nyam", like=like)
    assert five["variants"] == 128 and five["same"] == 96 and five["copy"] is True
    assert es["same"] == 0 and es["copy"] is False
    assert T.place(DEMO, "NQ", "5", "nyam")["copy"] is False          # nothing to hold it against: never a copy


def test_copies_are_named_and_not_counted():
    one = L.neighbors({"neighbors": [-4883.0], "copies": ["5-minute bars", "30-minute bars"]})
    assert one["passed"] is False and one["tables"] == 1 and "not counted" in one["text"] and "5-minute bars" in one["text"]
    none = L.neighbors({"neighbors": [], "copies": ["5-minute bars"]})
    assert none["passed"] is False and "no neighbor table of its own" in none["text"]
    plain = L.neighbors({"neighbors": [100.0, -5.0]})
    assert plain["passed"] is True and "not counted" not in plain["text"]
