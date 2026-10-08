"""The two stops anchored at the session's start (engine/families/blocks.py): stop_mode = "atropen" and "rngopen".

  atropen   stop distance = stop_val x the MEAN TRUE RANGE of the tf bars closed since the session started (nyam: since 09:30)
  rngopen   stop distance = stop_val x (highest high - lowest low) of those bars

(i) the stop is exactly that on synthetic bars, for several multipliers and both bar sizes; (ii) the true range of the first
bar of the session reads the close before it, like the Template's own ATR; (iii) no look-ahead: rewriting every print from a
decision on changes nothing decided up to it; (iv) the menu: 10 stops x 6 targets, ids unique, in a fixed order; (v) the
plain family does not know the modes; (vi) the random control carries the same stops."""
import numpy as np
import pytest

import families
import l2ref
import l2sim as S
from families import blocks as B
from test_blocks import (BARS, MS, TICK, garble, minute_tape, placed, play, sec, tf_bars)

OPEN_S = 34200                                       # 09:30 ET, seconds after 00:00
FVG = {"sess": "nyam", "min_gap": 0.0, "mode": "go", "max_tr": 20, "exit_bars": 1, "tgt_r": 2.0}
TAPE = minute_tape(BARS, "03:00")


def since_open(tf, now_s, ms=MS):
    """The tf bars closed since 09:30 by second `now_s` as [(h, l, tr)], the true range of each against the close before it."""
    tb = tf_bars(ms, tf, now_s)
    out = []
    for i, (end, h, l, c) in enumerate(tb):
        if end <= OPEN_S:
            continue
        pc = tb[i - 1][3]
        out.append((h, l, max(h - l, abs(h - pc), abs(l - pc))))
    return out


def expected(mode, tf, now_s, ms=MS):
    bars = since_open(tf, now_s, ms)
    assert bars
    return sum(b[2] for b in bars) / len(bars) if mode == "atropen" else max(b[0] for b in bars) - min(b[1] for b in bars)


def params(mode, tf, sv):
    return {"tf": str(tf), "stop_mode": mode, "stop_val": sv, **FVG}


@pytest.mark.parametrize("mode", ("atropen", "rngopen"))
@pytest.mark.parametrize("tf", (1, 5))
def test_the_stop_is_stop_val_times_the_session_so_far(mode, tf):
    seen = 0
    for sv in (0.5, 1.0, 3.0):
        _, log, _ = play(B.WRAPPED["fvg"], params(mode, tf, sv), TAPE)
        for t, sd, ref, sl, tp in placed(log):
            now = sec(t)
            d = max(sv * expected(mode, tf, now), 2 * TICK)
            assert OPEN_S < now, "an entry before the session started"
            assert sl == S.to_tick(ref - sd * d, TICK) and tp == S.to_tick(ref + sd * 2.0 * d, TICK), (mode, tf, sv, now)
            seen += 1
    assert seen >= 6, "the synthetic bars must leave several gaps to price"


def test_the_first_bar_of_the_session_reads_the_close_before_it():
    # the 09:30 bar opens 40 points above the 09:29 close: its true range is 41, not its own 1-point high - low
    bars = [(15000.0, 15000.0 + TICK, 15000.0, 15000.0, 40)] * 90                  # 09:00 .. 10:29, flat
    bars[30] = (15040.0, 15041.0, 15040.0, 15041.0, 40)
    bars[31] = (15041.0, 15060.0, 15041.0, 15060.0, 40)
    bars[32] = (15060.0, 15062.0, 15045.0, 15061.0, 40)                            # its low is above bar 30's high: an up gap
    for i in range(33, 90):
        bars[i] = (15061.0, 15061.0 + TICK, 15061.0, 15061.0, 40)
    ms = [(S._sec("09:00") + 60 * i, *b) for i, b in enumerate(bars)]
    _, log, _ = play(B.WRAPPED["fvg"], params("atropen", 1, 1.0), minute_tape(bars, "09:00"))
    got = placed(log)
    assert got
    t, sd, ref, sl, _ = got[0]
    want = expected("atropen", 1, sec(t), ms)
    assert want > 10.0, "the jump must be inside the average"
    assert sl == S.to_tick(ref - sd * want, TICK)


def test_no_look_ahead_garbage_after_a_decision_changes_nothing_before_it():
    cut = S.et_ns(__import__("datetime").date(2023, 3, 14), "10:30")
    for mode in ("atropen", "rngopen"):
        _, clean, _ = play(B.WRAPPED["fvg"], params(mode, 5, 1.0), TAPE)
        _, dirty, _ = play(B.WRAPPED["fvg"], params(mode, 5, 1.0), garble(TAPE, cut))
        a = [x for x in placed(clean) if x[0] < cut]
        b = [x for x in placed(dirty) if x[0] < cut]
        assert a and a == b


def test_the_menu_is_ten_stops_by_six_targets_in_a_fixed_order():
    for root in ("NQ", "ES", "GC"):
        m = B.menu_open(root)
        assert len(m) == 60 and len({S.cell_id(x) for x in m}) == 60
        stops = [(x["stop_mode"], x["stop_val"]) for x in m[::6]]
        assert stops == [("atropen", v) for v in (0.5, 1.0, 1.5, 2.0, 3.0)] + [("rngopen", v) for v in (0.25, 0.5, 0.75, 1.0, 1.5)]
        assert {x["tgt_r"] for x in m} == {0.0, 0.5, 0.75, 1.0, 2.0, 3.0}
        assert B.exits("open", root, "fvg") == m


def test_the_plain_family_does_not_know_the_modes():
    for mode in ("atropen", "rngopen"):
        with pytest.raises(ValueError):
            families.REGISTRY["fvg"][0](params(mode, 5, 1.0))


def test_the_random_control_carries_the_same_stops():
    for mode in ("atropen", "rngopen"):
        p = {"tf": "5", "sess": "nyam", "p_entry": 1.0, "seed": 1, "max_tr": 20, "exit_bars": 1, "stop_mode": mode, "stop_val": 1.0, "tgt_r": 0.0}
        _, log, _ = play(B.CONTROL_OPEN, p, TAPE)
        got = placed(log)
        assert got
        for t, sd, ref, sl, _ in got:
            d = max(expected(mode, 5, sec(t)), 2 * TICK)
            assert sl == S.to_tick(ref - sd * d, TICK)
    # with any other stop it is plain l2ref.Random: same draws, same trades
    p = {"tf": "5", "sess": "nyam", "p_entry": 0.5, "seed": 2, "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "hold_to": "day"}
    from test_blocks import DAILY
    a = S.run_session(l2ref.Random(p), TAPE, daily=list(DAILY), on_error="raise").trades
    b = S.run_session(B.CONTROL_OPEN(p), TAPE, daily=list(DAILY), on_error="raise").trades
    assert a == b
