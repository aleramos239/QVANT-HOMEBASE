"""blueprint/real.py: the six real-or-luck lines (owner, 2026-10-25). Pure: no store, no tape."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blueprint import real  # noqa: E402


def row(box="a", **kw):
    return {"box": box, "net": 100.0, "trades": 300, "t_stat": 2.5, "years_n": 5, "years_green": 4, "best_year_share": 0.4,
            "worse_fills_net": 50.0, "beats_random": 0.97, **kw}


def marks(s, tries=1):
    return {r["line"]: r["ok"] for r in real.check(s, tries)}


def test_all_six_pass_and_a_weak_box_fails_each_line():
    ok = {"is": [row(), row("b")], "lock": {"box": "a"}, "oos": {"record": {"net": 40.0, "trades": 70}}}
    assert set(marks(ok).values()) == {True}
    for bad, line in ((row(trades=150), "trades"), (row(t_stat=1.5), "luck"), (row(years_green=2), "years"), (row(best_year_share=0.7), "years"),
                      (row(worse_fills_net=-1.0), "worse fills")):
        assert marks({**ok, "is": [bad, row("b")]})[line] is False
    assert marks({**ok, "oos": {"record": {"net": -5.0, "trades": 70}}})["test months"] is False
    assert marks({**ok, "oos": {"record": {"net": 5.0, "trades": 30}}})["test months"] is False
    assert marks({**ok, "is": [row(), row("b", net=-1.0), row("c", net=-1.0)]})["boxes"] is False


def test_the_t_bar_rises_with_the_tries_and_nothing_is_asked_before_the_pick_or_the_test():
    s = {"is": [row(t_stat=2.1)], "lock": {"box": "a"}, "oos": None}
    assert marks(s)["luck"] is True and marks(s, tries=3)["luck"] is False
    assert marks(s)["test months"] is None
    assert marks({**s, "lock": None})["picked box"] is None
    assert "REAL OR LUCK" in real.text(real.check(s))
