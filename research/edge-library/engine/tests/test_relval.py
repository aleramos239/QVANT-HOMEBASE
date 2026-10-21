"""RELVAL: rv_fade (fade the own market's move its partner NQ <-> ES does not explain), families/relval.py, written with the family
(portfolio hunt 2026-10-21). Synthetic days: the own market from the test tape, the partner's 1-minute closes put in place of its tape
(relval.closes). No net, win rate or profit factor is read."""
import numpy as np
import pytest

import families
import l2sim as S
from families import blocks as B
from families import relval as RV
from test_blocks import D, DAILY, minute_tape
from test_vwap_touch import PX, day, sec

MS0 = S.et_ns(D, "00:00") // 1_000_000
BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "k": 4.0, "look": 60}
P0 = 4000.0
JUMP = 50.0 / PX                                       # the own market's 10:00 jump, as a share of its price


def partner(edits=None):
    """The partner's (start_ns, close) for every minute of the day from 00:00 ET: 4000 / 4000.25 alternating, `edits` {"HH:MM": close}
    (that minute and every later one shifted by the same amount)."""
    n = 960
    c = np.array([P0 + (0.25 if i % 2 else 0.0) for i in range(n)])
    for t, x in (edits or {}).items():
        i = S._sec(t) // 60
        c[i:] += x - c[i]
    return np.array([S.et_ns(D, "00:00") + i * S.MIN_NS for i in range(n)], np.int64), c


def run(params, own_edits, par, monkeypatch):
    monkeypatch.setattr(RV, "closes", lambda root, iso: par)
    st = RV.RvFade({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(day(own_edits), "00:00"), costs=S.Costs(), daily=list(DAILY), on_error="raise")
    return [((t["entry_ms"] - MS0) // 60000 * 60, t["side"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def up(px):
    return {f"{h:02d}:{m:02d}": (px, px + 0.25, px - 0.25, px, 40) for h in (10, 11, 12, 13, 14, 15) for m in range(60)}


def test_the_family_is_registered_wrapped_and_has_no_structure_level():
    assert families.ERRORS == {}
    assert families.MODULE_OF["rv_fade"] == "relval" and B.WRAPPED["rv_fade"].__name__ == "B_rv_fade"
    assert "rv_fade" not in B.STRUCT_FAMILIES
    assert families.LIBRARY["rv_fade"]["roots"] == ("NQ", "ES")


def test_gap_z_is_none_without_enough_common_minutes_or_a_flat_partner():
    t = np.arange(60, dtype=np.int64)
    assert RV.gap_z(t, np.full(60, 100.0) + t, t, np.full(60, 50.0), 60) is None              # a flat partner: no beta
    assert RV.gap_z(t[:40], 100.0 + t[:40], t[:40], 50.0 + (t[:40] % 2), 60) is None           # 40 common minutes < 0.8 x 60
    z = RV.gap_z(t, 100.0 + (t % 2) + 5.0 * (t == 59), t, 50.0 + (t % 2) * 0.5, 60)
    assert z is not None and z > 4                                                              # the last minute's own jump stands out


def test_a_jump_its_partner_does_not_share_is_faded_at_the_next_close(monkeypatch):
    got = run({}, up(PX + 50.0), partner(), monkeypatch)
    assert got == [(sec(10, 1), "short")]                                     # the 10:00 minute closes at 10:01: short the leader
    got = run({}, up(PX - 50.0), partner(), monkeypatch)
    assert got == [(sec(10, 1), "long")]                                      # it lagged: long


def test_a_jump_its_partner_shares_is_not_a_gap(monkeypatch):
    assert run({}, up(PX + 50.0), partner({"10:00": P0 * (1 + JUMP)}), monkeypatch) == []


def test_the_partner_minute_still_open_at_the_decision_is_not_read(monkeypatch):
    # the partner makes the same jump one minute LATER (10:01, ending 10:02): at the 10:01 decision it has not happened yet
    assert run({}, up(PX + 50.0), partner({"10:01": P0 * (1 + JUMP)}), monkeypatch) == [(sec(10, 1), "short")]


def test_no_partner_tape_no_trade(monkeypatch):
    assert run({}, up(PX + 50.0), None, monkeypatch) == []


def test_k_sets_the_bar(monkeypatch):
    assert run({"k": 9.0}, up(PX + 50.0), partner(), monkeypatch) == []        # z of one jump in 60 minutes is about sqrt(60) < 9
