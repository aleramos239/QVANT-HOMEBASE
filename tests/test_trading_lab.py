"""Step B (B3): the chart's bot lock on a Lab strategy that trades in rounds. ChartDesk._day_state must be the pair's
round of TODAY at the plain key (the open one, when there is one) -- never a closed round filed under "#n", never a
block carried from an earlier day. The real engine and the real intake on fake adapters."""
from __future__ import annotations

import pytest

from homebase.config import StrategyCfg
from homebase.trading import ChartDesk, Refused
from tests.labdesk_util import DATE, LAB, entry, mkdesk, send
from tests.test_engine import run
from tests.test_engine_lab import fill_entry, fill_exit

NQC = "NQZ6"


def chart(d) -> ChartDesk:
    return ChartDesk(d.cfg, d.eng, d.ads, {})


def one_round(d, n, exit_=True):
    """Round n on a1: entered and filled; with exit_, closed at its target and its orders read ended."""
    out = send(d, entry(n), seq=n)
    assert out["results"][0]["status"] == "working", out
    st = d.eng.states[f"{LAB}@a1"]
    fill_entry(d.eng, d.ads["a1"], st, 110.25)
    if exit_:
        fill_exit(d.eng, d.ads["a1"], st, 120.0, "tp")
        d.eng._retry_at.clear()
        run(d.eng.clock_tick())
    return st


def test_round_two_live_locks_the_chart_though_round_one_is_filed_away(tmp_path):
    d = mkdesk(tmp_path)
    first = one_round(d, 1)
    second = one_round(d, 2, exit_=False)
    assert [k for k in d.eng.states] == [f"{LAB}@a1#1", f"{LAB}@a1"]               # the closed round comes first
    assert (first.status, second.status) == ("done", "live")
    desk = chart(d)
    assert desk._day_state("a1", LAB) is second
    with pytest.raises(Refused, match=f"belongs to the {LAB} bot right now \\(live\\)"):
        desk._lock("a1", NQC, "A1")


@pytest.mark.parametrize("status", ["placing", "placed"])
def test_an_open_round_that_is_not_filled_yet_locks_the_chart_too(tmp_path, status):
    d = mkdesk(tmp_path)
    one_round(d, 1)
    send(d, entry(2), seq=2)
    d.eng.states[f"{LAB}@a1"].status = status
    with pytest.raises(Refused, match="belongs to the lab_pp bot"):
        chart(d)._lock("a1", NQC, "A1")


def test_a_block_carried_from_an_earlier_day_never_locks_the_chart(tmp_path):
    d = mkdesk(tmp_path)
    d.eng.lab_open(LAB)
    assert d.eng._lab_carry_make((LAB, "a1"), {"date": "2026-09-11", "status": "live", "orders": []}, DATE)
    assert [s.status for s in d.eng.day_states_for_account("a1")] == ["error"]     # the block is all the pair has today
    desk = chart(d)
    assert desk._day_state("a1", LAB) is None
    desk._lock("a1", NQC, "A1")                                                    # the chart is free
    out = send(d, entry())                                                         # the block keeps the account out ...
    assert out["results"][0]["refused"] == "The Desk cannot check the last trade's orders."
    assert desk._day_state("a1", LAB) is None                                      # ... and the chart stays free


def test_with_no_round_open_it_is_the_pairs_state_at_the_plain_key_as_before(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": StrategyCfg(symbol="ES", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0)})
    desk = chart(d)
    assert desk._day_state("a1", LAB) is None and desk._day_state("a1", "nq930") is None
    done = one_round(d, 1)
    assert desk._day_state("a1", LAB) is done and done.status == "done"            # the last round, closed: not busy
    desk._lock("a1", NQC, "A1")
    one_round(d, 2)
    assert desk._day_state("a1", LAB) is d.eng.states[f"{LAB}@a1"]                  # round 2, never the filed round 1
    bot = d.eng._state("nq930", "a1")                                              # another kind: its one state, as ever
    bot.status = "live"
    assert desk._day_state("a1", "nq930") is bot
    with pytest.raises(Refused, match="belongs to the nq930 bot"):
        desk._lock("a1", "ESZ6", "A1")
    assert desk._day_state("a2", "nq930") is None
