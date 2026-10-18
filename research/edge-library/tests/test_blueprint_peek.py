"""LOCK of line 1.7 of the code check (blueprint/peek.py): NO LOOK-AHEAD, read by code on the card's own instances.

(a) THE CARD THAT FOOLED EVERY PHASE: nq_asia_liq_sweep (liq sweep, levels all, NQ, the evening session, 15-minute bars, entries
    from w_start, held to 01:55) FAILS on real build days -- on every cut inside its window, and the value that moves is the evening
    level asia2000 and no other level. The bug is PINNED by the fixture `uncapped`: levels.levels with the asia2000 read as it was
    until 2026-10-17 (all of 20:00-24:00 of the evening before, at any moment), so the proof holds whether or not levels.py is fixed.
(b) The same evening card on the prior day's levels only, and New York morning cards (the liq sweep on every level, a Donchian
    break with the level filter) PASS: the line names a real look-ahead, not the evening or the levels as such.
(c) The parts, without a tape: the cut times (inside the card's window, the same for the same day), the book rows a garbled pass
    rewrites (only those not usable at the cut), what counts as moved (`differ`), a store of the engine read through of_store.
Real days are build days only (2021-09-22 .. 2025-06-30). No P&L is read.
  pytest tests/test_blueprint_peek.py -q        (about a minute: the first real-day test reads the swing cache once)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import peek as P  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402

EXIT = {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 0.5}
# nq_asia_liq_sweep as its card runs it (~/.homebase/ideas/nq_asia_liq_sweep/spec.json, round 2: its default cell w_start 19:00, ATR 1.5, 0.5R)
ASIA = {"tf": "15", "sess": "eve", "hold_to": "day", "max_tr": 1, "mode": "sweep", "levels": "all", "w_flat": "01:55", **EXIT}
ASIA_VARIANTS = [{"w_start": w} for w in ("18:00", "19:00", "20:00", "21:00")]


@pytest.fixture
def uncapped(monkeypatch):
    """engine/levels.py as it was before the owner's fix of 2026-10-17: asia2000 = the high / low of every print of 20:00-24:00 of the
    evening before the trade date (at least EV_MIN of them), known at ANY moment -- inside that evening too. Written out here, so it
    does not lean on the module's own helpers; the levels keep the order of levels.NAMES (the liq trigger takes the first price)."""
    import levels as LV
    real = LV.levels

    def evening(st):
        s, d = st._cx._s, st._cx.date
        i, j = np.searchsorted(s.ts, [S.et_ns(d - dt.timedelta(days=1), "20:00"), S.et_ns(d, "00:00")])
        return (float(s.px[i:j].max()), float(s.px[i:j].min())) if j - i >= LV.EV_MIN else None

    def levels(st, which="all"):
        out = real(st, which)
        if which not in ("all", "asia2000"):
            return out
        out.pop("asia2000", None)
        v = evening(st)
        if v is not None:
            out["asia2000"] = v
        return {k: out[k] for k in (*LV.NAMES, *out) if k in out} if which == "all" else out

    monkeypatch.setattr(LV, "levels", levels)


def cells(fixed: dict, variants: list) -> list:
    """A store's cells as run.json keeps them: one exit (xi 0) per variant, the full inputs."""
    return [{"id": f"v{i}", "vi": i, "xi": 0, "variant": v, "exit": EXIT, "inputs": {**fixed, **v}} for i, v in enumerate(variants)]


def days(n: int = 4) -> list:
    """`n` real build days of NQ spread over the build range (skipped inside a no-compute window or without the NQ tapes)."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    got = P.build_days("NQ", 30)[:: max(1, 30 // n)][:n]
    if not got or any(S.load_tape(dt.date.fromisoformat(d), "NQ", allow_holdout=RUN.PERIOD) is None for d in got):
        pytest.skip("the NQ tapes of the build days are not on this machine")
    return got


# ================================================================ (a) the card that fooled every phase

def test_the_asia_liq_sweep_card_looks_ahead_and_the_evening_level_is_what_moves(uncapped):
    r = P.read("liq", "NQ", ["eve"], cells(ASIA, ASIA_VARIANTS), days=days())
    assert r["line"] == "1.7" and r["passed"] is False and r["text"].startswith("1.7 FAIL the rule looks ahead: on ")
    assert r["cuts"] >= 9 and r["number"] == r["cuts"]                         # every cut lies in 18:00-23:59, before the evening level's window ends
    assert r["moved"] and all(m["what"] == "level" for m in r["moved"])        # the first thing that moves, every time, is a level ...
    for m in r["moved"]:
        a, b = m["clean"], m["garbled"]
        assert {k for k in set(a) | set(b) if a.get(k) != b.get(k)} == {"asia2000"}, m["text"]       # ... and it is the evening level, alone
        assert m["at_ns"] < m["cut_ns"] < S.et_ns(dt.date.fromisoformat(m["date"]), "00:00")
        assert "level asia2000 " in m["text"] and "the evening before" in m["text"]
    assert "First: " in r["text"] and "level asia2000" in r["text"]


# ================================================================ (b) clean cards pass

def test_the_same_evening_card_on_the_prior_days_levels_passes():
    r = P.read("liq", "NQ", ["eve"], cells({**ASIA, "levels": "pd"}, ASIA_VARIANTS[1:2]), days=days())
    assert r["passed"] is True and r["number"] == 0 and r["moved"] == [] and r["read"]["level"] > 0, r["text"]
    assert r["text"].startswith("1.7 PASS no look-ahead: ") and "3 cut times inside its window" in r["text"] and "1 setting)" in r["text"]


def test_new_york_morning_cards_pass():
    ny = {"tf": "5", "sess": "nyam", "hold_to": "day", "max_tr": 1, **EXIT}
    r = P.read("liq", "NQ", ["nyam"], cells({**ny, "mode": "sweep"}, [{"levels": "all"}, {"levels": "ldn"}]), days=days())
    assert r["passed"] is True and r["read"]["level"] > 0 and r["read"]["bar"] > 0, r["text"]
    r = P.read("donchian", "NQ", ["nyam"], cells({**ny, "n": 10}, [{"f_level": "near"}, {"f_level": "clear"}]), days=days())
    assert r["passed"] is True and r["read"]["level"] > 0, r["text"]


# ================================================================ (c) the parts

def test_cut_times_lie_inside_the_window_and_are_the_same_for_the_same_day():
    cls = RUN._blocks().WRAPPED["liq"]
    eve = P.windows(cls, [{**ASIA, "w_start": "19:00"}])
    assert eve == [S.SESS["eve"]]
    assert P.windows(cls, [{**ASIA, "sess": "nyam", "tf": "5", "w_flat": ""}]) == [S.SESS["nyam"]]
    d = dt.date(2023, 3, 14)
    t0 = S.et_ns(d, "00:00")
    a = P.cut_times(d.isoformat(), eve, 50, 7)
    assert a == P.cut_times(d.isoformat(), eve, 50, 7) and a != P.cut_times("2023-03-15", eve, 50, 7)
    assert all(t0 + (S.SESS["eve"][0] + 60) * S.NS <= c < t0 + S.SESS["eve"][1] * S.NS and c % S.NS == 0 for c in a)


def test_a_garbled_book_rewrites_only_the_rows_not_usable_at_the_cut():
    usable = np.arange(10, dtype=np.int64) * 60 * S.NS
    inner = lambda d: S.Features(usable, {"imb10": np.linspace(-0.5, 0.5, 10).astype(np.float32), "book_ok": np.ones(10, bool)})  # noqa: E731
    inner.columns = ("imb10", "book_ok")
    f = P.Book(inner, cut=4 * 60 * S.NS, seed=3)("2023-03-14")
    clean = inner(None)
    assert P.Book(inner, 0, 1).columns == ("imb10", "book_ok")
    assert np.array_equal(f.cols["imb10"][:5], clean.cols["imb10"][:5]) and not np.array_equal(f.cols["imb10"][5:], clean.cols["imb10"][5:])
    assert f.cols["book_ok"].dtype == bool and np.array_equal(f.usable_ns, usable)


def test_differ_names_the_first_thing_that_moved_at_or_before_the_cut():
    res = lambda trades=(), err=False: {"trades": list(trades), "no_trade": [{"date": "x", "reason": "strategy error: boom"}] if err else []}  # noqa: E731
    lvl = lambda v: (100, "level", {"asia2000": v})  # noqa: E731
    order = (200, "order", ("long", "market", None, 1.0, 2.0))
    assert P.differ(([lvl((1.0, 0.0)), order], res()), ([lvl((1.0, 0.0)), order], res()), 300) is None
    assert P.differ(([lvl((1.0, 0.0))], res()), ([lvl((9.0, 0.0))], res()), 300) == (100, "level", {"asia2000": (1.0, 0.0)}, {"asia2000": (9.0, 0.0)})
    assert P.differ(([lvl((1.0, 0.0)), order], res()), ([lvl((1.0, 0.0))], res()), 300) == (200, "order", order[2], None)      # an order only the clean tape placed
    assert P.differ(([lvl((1.0, 0.0)), order], res()), ([lvl((1.0, 0.0))], res()), 150) is None                               # ... after the cut: not held
    t = {"entry_ms": 250, "side": "long", "entry_price": 10.0, "exit_ms": 10_000, "exit_price": 11.0, "exit_reason": "tp"}
    cut = 300 * 1_000_000
    moved = dict(t, entry_price=12.0)
    assert P.differ(([], res([t])), ([], res([moved])), cut) == (250 * 1_000_000, "trade", (250, "long", 10.0), (250, "long", 12.0))
    assert P.differ(([], res([t])), ([], res([moved], err=True)), cut) is None          # a session dropped by an error keeps no trade: its log holds the orders
    m = {"date": "2023-03-14", "cut_ns": S.et_ns(dt.date(2023, 3, 13), "21:00"), "setting": "w_start 19:00", "at_ns": S.et_ns(dt.date(2023, 3, 13), "19:15"),
         "what": "level", "clean": {"asia2000": (15040.0, 14960.0), "pd": (1.0, 0.0)}, "garbled": {"asia2000": (15398.25, 14960.0), "pd": (1.0, 0.0)}}
    assert P.words(m) == ("2023-03-14, prints garbled from 21:00:00 ET the evening before, setting w_start 19:00: at 19:15:00 ET the evening before "
                          "level asia2000 15,040 / 14,960 -> 15,398.25 / 14,960")


def test_of_store_reads_an_engine_store_and_not_a_hand_made_one(uncapped):
    with tempfile.TemporaryDirectory() as tmp:
        hand = Path(tmp) / "hand-NQ-tf5"
        hand.mkdir()
        (hand / "run.json").write_text(json.dumps({"family": "hand", "cells": [{"id": "x"}]}))
        t = {"kind": "store", "where": str(hand), "root": "NQ", "label": "stores/hand-NQ-tf5"}
        r = P.of_store(t)
        assert r["passed"] is None and "is not a store of the engine (family 'hand')" in r["text"]
        assert P.of_store({**t, "kind": "trades"})["passed"] is None
        eng = Path(tmp) / "nq_asia_liq_sweep_r2-NQ-tf15"
        eng.mkdir()
        (eng / "run.json").write_text(json.dumps({"family": "liq", "root": "NQ", "sessions": ["eve"], "filter": None, "cells": cells(ASIA, ASIA_VARIANTS[1:2])}))
        r = P.of_store({**t, "where": str(eng), "label": "runs_bp/nq_asia_liq_sweep_r2-NQ-tf15"}, days=days(2))
        assert r["passed"] is False and r["moved"][0]["what"] == "level" and "asia2000" in r["text"]
