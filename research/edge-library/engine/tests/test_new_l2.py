"""families/l2ideas.py -- the new Level-2 ideas of the edge library (EDGE_SPEC D; NQ only).

  D1  bimb_follow_d1   the L2 screen's B1 at tf 5 (families/book.py, unchanged) as a library candidate with the menu
  D5  flow_exhaust     a top-percentile |delta| tf bar that makes a new session extreme in the delta's direction but closes in
                       the opposite half of its range -> fade
  D2 / D3 / D4         the engine's Level-2 signals (f_book / x_book / f_thin) as STAGE D VARIANTS of the breakout families
                       (orb, donchian, straddle, straddle_t_<HHMM>): same base family + one option, same cells, same days;
                       judged AT THE TRADE by the stage D class (l2ideas.StageD in front of the base's registered class)

What is proven here (synthetic tapes + tables, and the 10 fixed BUILD smoke days of run_menus; PICK and EXAM are never read):
  * the registry entries are the pre-registration of EDGE_SPEC (rationale strings, variants, tfs, NQ only);
  * D1 trades exactly what the L2 screen's bimb_follow trades; D5 signals exactly when its definition says so (an oracle that
    recomputes the definition from the raw rows and bars, without ctx and without the family);
  * NO LOOK-AHEAD: with every print and every feature row after a cut time replaced by garbage, every earlier decision
    (the entry verdicts, the state a signal read, the book-exit counter) and every earlier trade is unchanged -- synthetic
    and on real BUILD days, for D1, D5 and the stage D variants, with a cut in the day and one in the evening segment;
  * stage D on the breakout families conforms to EDGE_SPEC: a filtered MARKET entry reads the book at its decision; a
    RESTING bracket is the base's own and each fill is kept or skipped by the verdict of the 1-minute decision that began
    the fill's minute (l2ideas.kept): no kept fill into an opposing book or thick depth, no verdict a minute old, no trade
    that is not the base's; the book exit needs a FLIP (armed only once the book has not opposed the trade). On real days
    every verdict, every variant's trade list and every book exit equals an oracle on the raw prints and the raw table by
    row STAMP;
  * second looks and weak priors are labelled (D1, D5, D2 on the old picks);
  * a variant's grid is the base unit's WHOLE grid cell for cell (same ids, same sessions and tape), the run is refused
    unless the base's own BUILD store passed the plateau in a session, the variant is read in those sessions only, a member
    cell needs the variant's own BUILD plateau before PICK, and everything goes through run_menus' stores and the capped ledger;
  * the same trades at 1 and at 8 worker processes (L2_TEST_WORKERS lowers the count on a busy machine).
Counts, identity and timing only: no P&L is computed, printed or asserted anywhere."""
import copy
import datetime as dt
import os
import re
from collections import Counter

import numpy as np
import pytest

import families
import l2sim as S
import library as LB
import run_menus as RM
import score
import test_fam_book as TB
import test_fam_flow as TF
from families import book as B
from families import flow as F
from families import l2ideas as L2

W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
DAYS = list(RM.SMOKE_DAYS)        # 10 fixed BUILD days: early sample, a roll day and roll + 1, two half days, an FOMC day, plain days
assert len(DAYS) <= 10 and all(S.BUILD[0].isoformat() <= d <= S.BUILD[1].isoformat() for d in DAYS)
HALF_DAYS = ("2022-11-25", "2023-07-03")
SPEC = " ".join((S.W / "EDGE_SPEC.md").read_text().split())
D1, D5 = L2.BimbFollowD1, L2.FlowExhaust
NS, MIN = S.NS, S.MIN_NS
LIVE = 85_000_000                                  # the tester's order-placement latency (Strategy.placement_ms)


def quoted(text: str) -> bool:
    """`text` stands in EDGE_SPEC.md word for word (line breaks aside)."""
    return " ".join(text.split()) in SPEC


def reg(name):
    """The registered class and default inputs of a library family (the breakout bases are other authors' modules)."""
    assert name in families.LIBRARY, f"{name} is not a registered library family: {families.ERRORS}"
    return families.REGISTRY[name][0], families.REGISTRY[name][1]


# ================================================================================================================================
# 1. the registry entries = the pre-registration
# ================================================================================================================================

def test_the_registry_entries_are_the_pre_registered_d1_and_d5():
    assert families.ERRORS == {}, families.ERRORS
    want = {"bimb_follow_d1": (D1, ("5",), [{"k": 1.5}, {"k": 2.0}, {"k": 2.5}], ("imb10",), 3),
            "flow_exhaust": (D5, ("1", "5"), [{"q": 85.0}, {"q": 90.0}, {"q": 95.0}], ("f_delta",), 5)}
    assert set(L2.FAMILIES) == set(want)
    for name, (cls, tfs, variants, shuffled, cx) in want.items():
        e, lib = families.REGISTRY[name], families.library(name)
        assert families.MODULE_OF[name] == "l2ideas" and e[0] is cls and e[1] == {} and e[2] is False
        assert families.check_entry(name, L2.FAMILIES[name]) == []
        assert cls.SCREEN_TFS == tfs and cls.session_independent is True and not hasattr(cls, "SCREEN_RUN")
        assert lib["roots"] == ("NQ",) and lib["l2"] is True and lib["weak"] is True and lib["ported"] is None and lib["penalty"] is None
        assert lib["variants"] == variants and lib["complexity"] == cx
        said, _, labels = lib["rationale"].partition(" [")
        assert quoted(said) and len(said) >= 20 and said.endswith(".")            # the EDGE_SPEC rationale sentence, word for word
        assert labels.startswith("WEAK PRIOR; ") and labels.endswith("]")         # ... then the labels a card must show
        assert set(cls.FEATURES) == set(shuffled) | {"t_utc", "book_ok"}
        assert score.C2Features(cls.FEATURES, seed=1).shuffle_cols == shuffled   # the C2 null shuffles the feature, nothing else
        for tf in tfs:
            g = families.unit_grid(name, "NQ", tf)
            assert len(g) == 96 and len({c["id"] for c in g}) == 96 and [c["exit"] for c in g[:32]] == S.menu("NQ")
            p = cls(g[40]["spec"][1]).p
            assert g[40]["spec"][0] is cls and g[40]["variant"] == variants[1] and p["tf"] == tf and p["sess"] == "all"
            assert {k: p[k] for k in variants[1]} == variants[1] and {k: p[k] for k in g[40]["exit"]} == g[40]["exit"]
            assert (p["f_depth"], p["f_book"], p["x_book"], p["f_thin"], p["f_trend"], p["f_vwap"]) == ("off",) * 6
            assert (p["dir"], p["max_tr"], p["trail_atr"], p["exit_bars"]) == ("both", 3, 0.0, 0)      # the Template defaults
        for root in ("ES", "GC"):
            with pytest.raises(ValueError, match="not registered for root"):
                families.unit_grid(name, root, tfs[0])
    with pytest.raises(ValueError, match="SCREEN_TFS"):
        families.unit_grid("bimb_follow_d1", "NQ", "1")                          # EDGE_SPEC D1: "bimb_follow tf5"
    assert families.unit_grid("bimb_follow_d1", "NQ", "5")[0]["id"] == "k1p5_atr1p5-r0"
    assert families.unit_grid("flow_exhaust", "NQ", "1")[-1]["id"] == "q95_pct0p2-r3"
    # the variants are EDGE_SPEC "PROPER RE-RUN" 4, read from the file itself
    z = re.search(r"bimb_follow z \{([^}]*)\}", SPEC).group(1)
    q = re.search(r"flow_exhaust percentile \{([^}]*)\}", SPEC).group(1)
    assert [float(x) for x in z.split(",")] == [v["k"] for v in want["bimb_follow_d1"][2]]
    assert [float(x) for x in q.split(",")] == [v["q"] for v in want["flow_exhaust"][2]]
    assert quoted("`bimb_follow` tf5") and "D1" in L2.FAMILIES["bimb_follow_d1"][3] and "D5" in L2.FAMILIES["flow_exhaust"][3]
    us = {u["key"]: u for u in RM.units(only=["bimb_follow_d1", "flow_exhaust"])}
    assert set(us) == {"bimb_follow_d1-NQ-tf5", "flow_exhaust-NQ-tf1", "flow_exhaust-NQ-tf5"}
    assert all(u["cells"] == 96 and u["null_cells"] == 192 and u["l2"] and not u["time_fired"] for u in us.values())


def test_d1_is_the_l2_screens_bimb_follow_with_nothing_changed():
    assert issubclass(D1, B.BimbFollow) and D1.fam_signal is B.BimbFollow.fam_signal and D1.SIGN == 1
    assert families.MODULE_OF["bimb_follow"] == "book"                             # the screen's own entry keeps its name
    p = D1({"tf": "5"}).p
    assert p == B.BimbFollow({"tf": "5"}).p and (p["k"], p["n_lv"]) == (2.0, "10")
    with pytest.raises(ValueError):
        D1({"tf": "5", "n_lv": "3"})                                              # imb3 is not loaded: the input is pinned
    assert "imb3" not in D1.FEATURES and (B.Z_WIN, B.Z_MIN) == (60, 30)


class SpyD1(TB.Spy, D1):
    pass


@pytest.mark.parametrize("k", [1.5, 2.0, 2.5])
def test_d1_signals_are_the_definition_at_every_decision_for_each_registered_z(k):
    """Synthetic day (tests/test_fam_book.py's tape + table): at every 5-minute decision the spy's signal = the z-score
    oracle recomputed from the table by row STAMP; the family reads only its own three columns."""
    n = 0
    for seed in range(1, 9):
        tb = TB.table(end="13:40", seed=seed)
        f = S.Features(tb["stamp"] + MIN, {c: tb[c] for c in D1.FEATURES})
        st = TB.spy(SpyD1, f, {"tf": "5", "sess": "all", "k": k}, tape=TB.make_tape(end="13:40", seed=seed))
        assert st.calls == TB.decisions(5, sess=("nyam", "mid", "pm"), last="13:40")
        want = [(t, TB.bimb_oracle(tb, "imb10", t, 1, k)) for t in st.calls]
        assert st.sig == [(t, s) for t, s in want if s]
        n += len(st.sig)
        a = S.run_session(D1({"tf": "5", "k": k}), TB.make_tape(end="13:40", seed=seed), features=f)
        b = S.run_session(B.BimbFollow({"tf": "5", "k": k}), TB.make_tape(end="13:40", seed=seed), features=TB.feats(tb))
        assert a.skip is None and a.trades == b.trades                            # the same trades as the screen's class
    assert n >= 3


# ================================================================================================================================
# 2. D5 flow_exhaust on synthetic days: the trigger is the definition
# ================================================================================================================================

def d5_world(seed: int, messy: bool = True, inject: int = 36) -> TF.World:
    """tests/test_fam_flow.py's random day + `inject` planted minutes that exercise each condition of D5: a heavy one-sided
    delta on a bar that does / does not take out the day's extreme and closes in the far / the near half of its range."""
    w = TF.World(seed, messy=messy)
    rng = np.random.default_rng(1000 + seed)
    cand = sorted(s for s in w.bars if TF.hm("09:36") <= s < TF.hm("13:35") and s in w.rows)
    for s in sorted(int(x) for x in rng.choice(cand, size=min(inject, len(cand)), replace=False)):
        hi = max(b[1] for k, b in w.bars.items() if k < s)
        lo = min(b[2] for k, b in w.bars.items() if k < s)
        o = w.bars[s][0]
        up, kind = bool(rng.random() < 0.5), int(rng.integers(0, 5))            # kind 0, 1: a true exhaustion bar
        ext = (-0.25 if kind == 2 else 0.5)                                       # 2: stops short of the extreme
        if up:
            h, l = max(hi + ext, o), min(o, hi + ext) - 2.0
            c = h - 0.25 if kind == 3 else l + 0.25                               # 3: closes in the near half
        else:
            l, h = min(lo - ext, o), max(o, lo - ext) + 2.0
            c = l + 0.25 if kind == 3 else h - 0.25
        w.bars[s] = (o, h, l, c)
        d = 400.0 * (1 if up else -1) * (-1 if kind == 4 else 1)                  # 4: the delta is against the move
        w.rows[s]["f_delta"] = d
    return w


def d5_oracle(world, tf: int, q: float = 90.0, sessions=("nyam", "mid", "pm")):
    """D5 recomputed from the day's raw bars and rows (module docstring of families/l2ideas.py), on the flow families'
    decision instants (TF.decisions: on-time tf close in a session, >= 3 tf bars, not in the last 5 minutes, fresh row,
    book_ok). -> ([(T, side)], counters of what the day exercised)."""
    bars = TF.tf_bars(world, tf)
    out, st = [], {"eq": 0, "zero": 0, "thin": 0, "n": 0, "first_bar": 0, "cold": 0, "no_extreme": 0, "wrong_half": 0,
                   "flat_bar": 0, "wick_only": 0}
    for T, sid, k in TF.decisions(world, tf, sessions):
        st["n"] += 1
        o, h, l, c, _ = bars[k]
        s0 = TF.SESS[sid][0]
        prev = [bars[b] for b in bars if s0 < b + tf * 60 < T]                    # the session's earlier tf bars
        if not prev:
            st["first_bar"] += 1
            continue
        cur, hot = TF.top(world, T, tf, ["f_delta"], q, st)
        if not hot:
            st["cold"] += 1
            continue
        d, mid = cur[0], (h + l) / 2.0
        new = h > max(b[1] for b in prev) if d > 0 else l < min(b[2] for b in prev)
        if not new:
            st["no_extreme"] += 1
            continue
        if h == l:
            st["flat_bar"] += 1
        if (d > 0 and c < mid) or (d < 0 and c > mid):
            out.append((T, "short" if d > 0 else "long"))
            st["wick_only"] += (c <= max(b[1] for b in prev)) if d > 0 else (c >= min(b[2] for b in prev))
        else:
            st["wrong_half"] += 1
    return out, st


@pytest.mark.parametrize("tf", ["1", "5"])
@pytest.mark.parametrize("seed", [11, 12, 13, 14, 62])
@pytest.mark.parametrize("q", [85.0, 90.0, 95.0])
def test_d5_signals_equal_the_oracle_on_randomised_days(tf, seed, q):
    w = d5_world(seed)
    want, st = d5_oracle(w, int(tf), q)
    assert TF.signals(D5, w, {"tf": tf, "q": q}) == want
    assert st["n"] > (150 if tf == "1" else 25)                                    # the day really offers that many decisions


def test_d5_randomised_days_exercise_both_sides_and_every_condition():
    """Power of the oracle test: both directions fire, and each condition (cold delta, no new extreme, the close in the
    near half, the first bar of a session) is what stops a signal at some decision; a wick alone is enough for the extreme."""
    sides, tot, n = set(), {}, 0
    for seed in (11, 12, 13, 14, 62):
        for tf in (1, 5):
            for q in (85.0, 90.0, 95.0):
                want, st = d5_oracle(d5_world(seed), tf, q)
                sides |= {s for _, s in want}
                n += len(want)
                for k, v in st.items():
                    tot[k] = tot.get(k, 0) + int(v)
    assert sides == {"long", "short"} and n >= 60
    assert all(tot[k] > 0 for k in ("cold", "no_extreme", "wrong_half", "first_bar", "thin", "wick_only")), tot


def test_d5_the_percentile_input_is_what_the_trigger_uses():
    differs = 0
    for seed in (11, 12, 13):
        w = d5_world(seed)
        for tf in ("1", "5"):
            sigs = {q: d5_oracle(w, int(tf), q)[0] for q in (60.0, 85.0, 99.0)}
            for q, want in sigs.items():
                assert TF.signals(D5, w, {"tf": tf, "q": q}) == want
            differs += sigs[60.0] != sigs[99.0]
            assert set(sigs[99.0]) <= set(sigs[60.0])                             # a higher percentile only removes signals
    assert differs > 0


def flat_day(end="11:30"):
    """A day without a D5 signal to build explicit cases on: one-tick bars, a delta of +-2 every minute."""
    w = TF.World(5, start="08:30", end=end, feat_start="06:00", messy=False)
    for s in w.bars:
        w.bars[s] = (18000.0, 18000.25, 18000.0, 18000.0)
    for i, s in enumerate(sorted(w.rows)):
        w.rows[s].update(f_delta=2.0 if i % 2 else -2.0, book_ok=True)
    return w


def test_d5_explicit_exhaustion_bar_fires_at_its_own_close_and_each_condition_is_needed():
    s = TF.hm("10:02")                                                             # the minute 10:02 - 10:03, decision at 10:03:00
    T = s + 60

    def sig(bar=None, delta=None, tf="1", edit=None):
        w = flat_day()
        w.bars[s] = bar or (18000.0, 18003.0, 18000.0, 18000.5)                    # new session high, close in the lower half
        w.rows[s]["f_delta"] = 500.0 if delta is None else delta
        if edit:
            edit(w)
        return TF.signals(D5, w, {"tf": tf})

    assert flat_day().bars[s] and TF.signals(D5, flat_day(), {"tf": "1"}) == []
    assert sig() == [(T, "short")]                                                # buyers absorbed at the high -> fade: short
    assert sig(bar=(18000.0, 18000.25, 17997.0, 17999.5), delta=-500.0) == [(T, "long")]          # the mirror
    assert sig(delta=-500.0) == []                                                # heavy SELLING on a bar that made a high: not D5
    assert sig(delta=1.0) == []                                                   # |1| < the trailing |2|: not a top-decile bar
    assert sig(delta=2.0) == [(T, "short")]                                       # ON the percentile (every trailing |D| is 2): inclusive
    assert sig(bar=(18000.0, 18003.0, 18000.0, 18002.0)) == []                    # closes in the UPPER half: the push held
    assert sig(bar=(18000.0, 18003.0, 18000.0, 18001.5)) == []                    # exactly the midpoint: not in the lower half
    assert sig(bar=(18000.0, 18003.0, 18000.0, 18001.25)) == [(T, "short")]       # one tick below the midpoint
    assert sig(bar=(18000.0, 18000.25, 17999.0, 17999.25)) == []                  # no new session high (18000.25 was the high)
    assert sig(bar=(18000.0, 18000.5, 17999.0, 17999.25)) == [(T, "short")]       # one tick above the prior high: a wick counts
    # the row is acted on one minute after its stamp: the same heavy row one minute later belongs to the next (quiet) bar
    assert sig(edit=lambda w: (w.rows[s].update(f_delta=1.0), w.rows[s + 60].update(f_delta=500.0))) == []
    # the first tf bar of a session has no earlier session bar: the 09:30 - 09:31 bar never signals
    first = TF.hm("09:30")

    def at_open(w):
        w.bars[s] = (18000.0, 18000.25, 18000.0, 18000.0)
        w.rows[s]["f_delta"] = 1.0
        w.bars[first] = (18000.0, 18003.0, 18000.0, 18000.5)
        w.rows[first]["f_delta"] = 500.0
    assert sig(edit=at_open) == []
    # tf 5: the bar is the clock bucket 10:00 - 10:05 (high from 10:02, close from 10:04), the delta its five rows' sum
    assert sig(tf="5") == [(TF.hm("10:05"), "short")]                             # the bucket closes at 18000.0, its low
    held = lambda w: w.bars.__setitem__(TF.hm("10:04"), (18002.5, 18002.75, 18002.5, 18002.5))       # noqa: E731
    assert sig(tf="5", edit=held) == []                                           # the 5-minute bar closes in its upper half


@pytest.mark.parametrize("tf", ["1", "5"])
def test_d5_rewriting_every_row_and_print_after_a_cut_changes_no_earlier_decision(tf):
    """NO LOOK-AHEAD, synthetic, with TEMPTING cuts: each cut is the close of a planted bar that is a price exhaustion (new
    session high, close in the lower half) on a COLD delta -- no signal. Every row stamped at / after the cut (usable only
    later) becomes a huge BUY delta with book_ok True and every later minute a wild bar. A family that read one row too far
    would take that delta for the bar's own and fade it at the cut; the real one changes no signal up to the cut, while the
    later ones do change (so the comparison is able to fail)."""
    step = int(tf) * 60
    base = d5_world(13, messy=False)
    plant = [TF.hm(t) for t in ("09:54", "10:29", "11:44", "12:59")]              # the last minute of a 5-minute bucket
    for s in plant:
        hi = max(b[1] for k, b in base.bars.items() if k < s)
        o = base.bars[s][0]
        h = max(hi + 0.5, o)
        base.bars[s] = (o, h, min(o, h) - 2.0, min(o, h) - 1.75)
        for k in range(s + 60 - step, s + 60, 60):
            base.rows[k]["f_delta"] = 0.0                                         # the whole signal bar: no aggression at all
    ref = TF.signals(D5, base, {"tf": tf})
    moved = 0
    for s in plant:
        cut = s + 60
        assert not [x for x in ref if x[0] == cut]
        hot = copy.deepcopy(base)
        hot.rows[s]["f_delta"] = 5000.0                                           # power: with ITS OWN row hot the bar is a signal
        assert (cut, "short") in TF.signals(D5, hot, {"tf": tf})
        w = copy.deepcopy(base)
        for r in range(cut, max(base.rows) + 60, 60):
            w.rows[r] = {"f_delta": 5000.0, "book_ok": True, "f_sweep_buy_vol": 0.0, "f_sweep_sell_vol": 0.0}
        for i, k in enumerate(x for x in sorted(base.bars) if x >= cut):
            w.bars[k] = (18100.0, 18110.0 + i, 18090.0 - i, 18091.0 - i) if i % 2 else (18100.0, 18110.0 + i, 18090.0 - i, 18109.0 + i)
        got = TF.signals(D5, w, {"tf": tf})
        assert [x for x in got if x[0] <= cut] == [x for x in ref if x[0] <= cut]
        moved += got != ref
    assert len(ref) >= 1 and moved > 0


@pytest.mark.parametrize("shift_s", [-3600, -120, -60, 60, 120, 3600])
def test_d5_a_table_on_the_wrong_clock_never_signals(shift_s):
    """A table usable a minute EARLY would show the forming minute at each close (look-ahead), a late one a stale row:
    the freshness guard (newest usable row = the minute that just ended) refuses both."""
    w = d5_world(14, messy=False)
    assert len(TF.signals(D5, w, {"tf": "1"})) > 0
    for tf in ("1", "5"):
        assert TF.signals(D5, w, {"tf": tf}, feats=w.features(D5.FEATURES, shift_s=shift_s)) == []
    assert TF.signals(D5, w, {"tf": "1"}, feats=w.features(D5.FEATURES, shift_s=-1)) == TF.signals(D5, w, {"tf": "1"})


@pytest.mark.parametrize("tf", ["1", "5"])
def test_d5_every_value_a_decision_reads_is_usable(tf, monkeypatch):
    w = d5_world(12)
    feats = w.features(D5.FEATURES)
    calls = []
    real_feat, real_win = S.Ctx.feat, S.Ctx.feat_window

    def feat(self, col, back=0, default=None):
        v = real_feat(self, col, back, default)
        calls.append(("feat", self.now_ns, col, back, v))
        return v

    def feat_window(self, col, n=None):
        v = real_win(self, col, n)
        calls.append(("win", self.now_ns, col, n, v))
        return v
    monkeypatch.setattr(S.Ctx, "feat", feat)
    monkeypatch.setattr(S.Ctx, "feat_window", feat_window)
    res = S.run_session(D5({"tf": tf}), w.tape(), features=feats)
    assert res.skip is None and len(calls) > 20 and {c[2] for c in calls} <= set(D5.FEATURES)
    for kind, now, col, arg, v in calls:
        assert isinstance(arg, int) and not isinstance(arg, bool) and arg >= 0
        n = int((feats.usable_ns <= now).sum())
        if kind == "feat":
            assert arg == 0 and (v is None if n == 0 else v == feats.cols[col][n - 1].item())
        else:
            want = feats.cols[col][max(0, n - arg):n]
            assert len(v) == len(want) and np.array_equal(v, want, equal_nan=True)
            if col == "t_utc" and len(v):
                assert (v.max() + 60) * NS <= now                                 # nothing stamped in the minute still forming


@pytest.mark.parametrize("tf", ["1", "5"])
def test_d5_trades_are_the_oracle_signals_one_position_at_a_time(tf):
    """The family as registered (market orders) on days where every minute prints: walking the oracle's signals with 'flat,
    < 3 entries this session' gives exactly the trades; each enters on the first print after its signal, with its side,
    one direction, a stop and (menu cell 1:2) a target."""
    n_tr = 0
    for seed in (61, 62, 63, 64):
        w = d5_world(seed, messy=False)
        res = S.run_session(D5({"tf": tf}), w.tape(), features=w.features(D5.FEATURES))
        assert res.skip is None and res.both_sides is False
        want, _ = d5_oracle(w, int(tf))
        took, per_sess, open_until = [], {}, -1
        exits = {t["entry_ns"]: t["exit_ns"] for t in res.trades}
        for T, side in want:
            sid = next(k for k, (a, b) in TF.SESS.items() if a < T <= b)
            if TF.MID_NS + T * NS <= open_until or per_sess.get(sid, 0) >= 3 or T not in w.bars:
                continue
            fill = TF.MID_NS + (T + 1) * NS                                       # the first print after T + 85 ms
            took.append((fill, side))
            per_sess[sid] = per_sess.get(sid, 0) + 1
            open_until = exits.get(fill, -1)
        assert sorted((t["entry_ns"], t["side"]) for t in res.trades) == took
        for t in res.trades:
            assert t["order_price"] is None and t["oco"] is False and t["both_sides"] is False and t["qty"] == 1
            sd = 1 if t["side"] == "long" else -1
            assert (t["entry_price"] - t["sl"]) * sd >= 2 * 0.25 and (t["tp"] - t["entry_price"]) * sd > 0
        n_tr += len(res.trades)
    assert n_tr > 0


def test_d5_no_signal_in_the_last_five_minutes_of_a_session_or_of_a_half_day():
    """Every minute is a D5 trigger bar (a new session high on a delta that sits ON its percentile, close in the lower
    half): the last signal of a session is 6 minutes before its end, and on a CME half day (the engine ends it at 13:15
    ET, the mid session's own end is 13:30) the last one is at 13:09."""
    full, half = dt.date(2023, 3, 14), dt.date(2023, 7, 3)                        # BUILD dates (the data below is synthetic)
    assert half in S.EARLY_CLOSES and full not in S.EARLY_CLOSES
    out = {}
    for day in (full, half):
        mid_ns = S.et_ns(day, "00:00")
        ts, px, t_utc, usable = [], [], [], []
        for i, s in enumerate(range(TF.hm("08:30"), TF.hm("13:45"), 60)):
            p = 18000.0 + 0.5 * i
            for off, v in zip((1, 15, 30, 45), (p, p + 1.0, p - 0.25, p)):       # high above the last high, close below the middle
                ts.append(mid_ns + (s + off) * NS)
                px.append(v)
        for s in range(TF.hm("02:00"), TF.hm("13:45"), 60):
            t_utc.append(mid_ns // NS + s)
            usable.append(mid_ns + (s + 60) * NS)
        n = len(t_utc)
        cols = {"t_utc": np.array(t_utc, np.int64), "book_ok": np.ones(n, bool), "f_delta": np.full(n, 500.0, np.float32)}
        st = TF.recorder(D5)({"tf": "1"})
        res = S.run_session(st, S.Tape("NQ", day, "NQM3", ts, px, [1] * len(ts)), features=S.Features(usable, cols),
                            window=S.effective_session_window(day, D5.session_window))
        assert res.skip is None and {sd for _, sd in st.sig} == {"short"}
        out[day] = [t for t, _ in st.sig]
    assert min(out[full]) == TF.hm("09:32")                                       # the second bar of the session: the first has no earlier one
    assert [t for t in out[full] if t <= TF.hm("11:00")][-1] == TF.hm("10:54") and TF.hm("11:02") in out[full]
    assert [t for t in out[full] if t <= TF.hm("13:30")][-1] == TF.hm("13:24") and max(out[half]) == TF.hm("13:09")
    assert max(out[full]) > TF.hm("13:30")                                        # the full day goes on into the pm session
    assert out[half] == [t for t in out[full] if t < TF.hm("13:10")]
    assert not [t for t in out[full] if any(b - 300 <= t <= b for _, b in TF.SESS.values())]


def test_d5_dir_input_restricts_the_side_and_the_evening_segment_has_no_half_day_cut():
    w = d5_world(61, messy=False)
    for d in ("long", "short"):
        res = S.run_session(D5({"tf": "1", "dir": d}), w.tape(), features=w.features(D5.FEATURES))
        assert res.skip is None and {t["side"] for t in res.trades} <= {d}

    class Ctx:                                                                    # what fam_day reads
        date = dt.date(2023, 7, 3)                                                # a CME half day (BUILD)
        segment = "eve"
    st = D5({"tf": "5", "sess": "eve"})
    assert st.session_window is None                                              # an evening-only instance has no day window
    st.t0 = S.et_ns(Ctx.date, "00:00")
    st.fam_day(Ctx)
    assert st._day_cut == st.t0                                                   # every evening decision is before 00:00 ET
    Ctx.segment = "day"
    st = D5({"tf": "5"})
    st.t0 = S.et_ns(Ctx.date, "00:00")
    st.fam_day(Ctx)
    assert st._day_cut == S.et_ns(Ctx.date, "13:10")                              # the half day ends 13:15: no signal from 13:10


# ================================================================================================================================
# 3. STAGE D: the table, the stage classes, the grids, the seal
# ================================================================================================================================
BASES = ("orb", "donchian", "straddle") + tuple("straddle_t_" + t.replace(":", "") for t in S.LISTED_TIMES)
OPTS = ("f_book", "x_book", "f_thin")


def test_stage_d_is_the_three_engine_signals_on_the_breakout_bases_with_the_edge_spec_rationales():
    assert L2.BREAKOUT_BASES == BASES and len(L2.STAGE_D) == 36 and not hasattr(L2, "DEAD")
    assert {k: v[:2] for k, v in L2.L2_OPTIONS.items()} == {"fbook": ("D2", {"f_book": "on"}), "xbook": ("D3", {"x_book": "on"}),
                                                           "thin": ("D4", {"f_thin": "on"})}
    for sfx, (sid, opt, rule, why) in L2.L2_OPTIONS.items():
        assert quoted(rule) and quoted(why) and len(opt) == 1                     # EDGE_SPEC's rule and rationale, word for word
        assert set(opt) < set(families.L2_OPTIONS) and S.template_feature_needs(opt) == S.L2_OPTION_COLS[next(iter(opt))]
    assert (S.BOOK_ROWS, S.BOOK_EXIT_N, S.THIN_AHEAD) == (5, 2, 0.8)              # the engine's constants = EDGE_SPEC D2 / D3 / D4
    assert quoted("breakout families (orb / donchian / straddle)")
    assert quoted("flips against the open trade for 2 consecutive minutes")       # D3 needs a FLIP: section 4 tests it
    for name, v in L2.STAGE_D.items():
        got = L2.variant(name)
        assert name == f"{v['base']}_{v['suffix']}" and got["base"] in BASES and got["breakout"] and got["option"] == v["option"]
        assert got["base"] in families.LIBRARY, f"the base of {name} is not a registered library family"
        assert name not in families.REGISTRY and L2.option(name) == v["option"]
        cls = families.REGISTRY[got["base"]][0]
        tf = cls.SCREEN_TFS[0]
        meta = L2.variant_meta(name, "NQ", tf)
        lib = families.library(got["base"])
        assert meta["base"] == got["base"] and meta["family"] == name and meta["option"] == v["option"] and meta["stage_d"] == v["spec"]
        assert meta["complexity"] == lib["complexity"] + 1 and meta["variants"] == lib["variants"] and meta["weak"] == lib["weak"]
        assert meta["base_rationale"] == lib["rationale"] and meta["l2_rationale"] == v["rationale"] and meta["penalty"] == lib["penalty"]
        assert meta["l2"] is True                    # a variant depends on Level 2: library.admission then demands C2
        assert meta["both_sides_declared"] == families.REGISTRY[got["base"]][2]
        assert (meta["both_sides_note"] is not None) == (got["base"] != "donchian" and v["suffix"] != "xbook")
        seen = meta["second_look"]
        assert seen == L2.second_look(name) and (seen is None or (seen in meta["notes"] and meta["rationale"].endswith(f" [{seen}]")))
        assert meta["rationale"].startswith(f"{lib['rationale']} + {v['spec']}: {v['rationale']}")
    assert L2.variant_meta("straddle_t_0000_xbook", "NQ", "30")["weak"] is True and L2.variant_meta("donchian_thin", "NQ", "15")["penalty"]
    # D2 / D3 are "on any member": any registered library family resolves; D4 is the breakout families' only
    v = L2.variant("vwap_z_fbook")
    assert (v["base"], v["option"], v["breakout"]) == ("vwap_z", {"f_book": "on"}, False)
    assert L2.variant("bimb_follow_d1_xbook")["base"] == "bimb_follow_d1"
    for bad in ("vwap_z_thin", "orb", "orb_fdepth", "nope_fbook", "bimb_follow_fbook", "_fbook"):
        with pytest.raises(KeyError):
            L2.variant(bad)


def test_second_looks_and_weak_priors_are_labelled_before_any_run():
    """EDGE_SPEC user rule 3 (a second look must be labelled) and rule 2 (a weak prior needs margin): D1 was already run and
    picked on BUILD + 2024 by the L2 screen, D5 sits next to a refuted program, D2 on the old picks is the screen's gate G1."""
    d1, d5 = families.library("bimb_follow_d1"), families.library("flow_exhaust")
    assert d1["weak"] is True and d5["weak"] is True and d1["penalty"] is None and d5["penalty"] is None
    n1, n5 = families.REGISTRY["bimb_follow_d1"][3], families.REGISTRY["flow_exhaust"][3]
    assert "WEAK PRIOR" in n1 and "SECOND LOOK (BUILD + PICK)" in n1 and L2.second_look("bimb_follow_d1") in n1
    assert "WEAK PRIOR" in n5 and "ADJACENT TO A REFUTED PROGRAM" in n5 and L2.second_look("flow_exhaust") is None
    # library.card prints the rationale (not the notes): the labels stand there too, after the EDGE_SPEC sentence
    assert L2.second_look("bimb_follow_d1") in d1["rationale"] and L2.ADJACENT["flow_exhaust"] in d5["rationale"]
    card = LB.card({"name": "x", "rationale": d1["rationale"], "complexity": 3, "weak": True}, {"admit": False, "tests": {}, "failed": [],
                                                                                              "summary": {}})
    assert "SECOND LOOK (BUILD + PICK)" in card and "WEAK" in card
    assert LB.WEAK_T == 3.0                          # what `weak` means at admission: t >= 3 on BUILD
    seen = {"bimb_follow_d1", "orb_fbook", "donchian_fbook", "straddle_fbook", "straddle_t_0300_fbook", "straddle_t_0930_fbook",
            "straddle_t_1330_fbook"}
    assert set(L2.SECOND_LOOK) == seen and all("SECOND LOOK" in L2.second_look(k) for k in seen)
    assert all(L2.second_look(k) is None for k in set(L2.STAGE_D) - seen)
    # the L2 screen's own files say so (names and ranges only: nothing of a result is read)
    lp = S.PP / "2026-10-01-l2"
    run = lp / "runs" / "bimb_follow-tf5" / "run.json"
    if run.exists():
        doc = __import__("json").loads(run.read_text())
        rng = doc.get("range") or doc.get("meta", {}).get("range") or {}
        assert str(rng.get("end", "2024-12-31"))[:4] == "2024"
        assert {p.name.split("_")[1] for p in (lp / "runs").glob("gate_*_G1")} == {"orb-tf5", "donchian-tf15", "straddle-tf30"}


def test_the_registry_itself_refuses_an_option_in_an_entry_which_is_why_stage_d_is_not_in_families():
    cls, inputs = reg("orb")
    lib = {"rationale": families.library("orb")["rationale"], "complexity": 4}
    for opt in ({"f_book": "on"}, {"x_book": "on"}, {"f_thin": "on"}):
        assert "must stay 'off'" in " | ".join(families.check_entry("orb_l2", (cls, {**inputs, **opt}, True, "D", lib)))
        assert "may not set" in " | ".join(families.check_entry("orb_l2", (cls, inputs, True, "D", {**lib, "variants": [opt]})))
    assert not set(L2.STAGE_D) & set(L2.FAMILIES) and not set(L2.STAGE_D) & set(families.REGISTRY)
    assert not any(u["family"] in L2.STAGE_D for u in RM.units())                 # the base menu plan never holds a stage D unit


def test_a_stage_class_is_the_mixin_in_front_of_the_registered_class_and_workers_can_import_it():
    import pickle
    for base in BASES + ("vwap_z",):
        cls, D = families.REGISTRY[base][0], L2.stage_class(base)
        assert D.__mro__[:3] == (D, L2.StageD, cls) and D.__module__ == L2.__name__ and D.__name__ == "D_" + base
        assert L2.stage_class(base) is D and getattr(L2, "D_" + base) is D and pickle.loads(pickle.dumps(D)) is D
        assert D.defaults() == cls.defaults() and D.schema() == cls.schema() and D.SCREEN_TFS == cls.SCREEN_TFS
        assert D.FEATURES == cls.FEATURES and D.session_independent is cls.session_independent
        assert RM.is_time_fired(D) == RM.is_time_fired(cls)
    own = {k for k in vars(L2.StageD) if not k.startswith("__")}
    assert own == {"on_session", "_verdict", "_arm", "_judge", "on_bar", "_lim", "_xbook"}
    assert not hasattr(L2.StageD, "allowed") and not hasattr(L2.StageD, "_mkt")   # a MARKET entry keeps the engine's own filter
    with pytest.raises(KeyError):
        L2.stage_class("bimb_follow")                                             # a 4-tuple screen entry is not a library family
    with pytest.raises(AttributeError):
        L2.D_nope


@pytest.mark.parametrize("name", sorted(L2.STAGE_D))
def test_a_variant_grid_is_the_base_units_whole_grid_cell_for_cell_with_the_option_on(name):
    v = L2.variant(name)
    cls, _ = reg(v["base"])
    D = L2.stage_class(v["base"])
    for tf in cls.SCREEN_TFS:
        base, grid = families.unit_grid(v["base"], "NQ", tf), L2.variant_grid(name, "NQ", tf)
        assert [(c["id"], c["vi"], c["xi"], c["variant"], c["exit"]) for c in grid] == \
               [(c["id"], c["vi"], c["xi"], c["variant"], c["exit"]) for c in base]
        for g, b in zip(grid, base):
            assert g["spec"][0] is D and b["spec"][0] is cls and g["spec"][1] == {**b["spec"][1], **v["option"]}
            assert [p["sess"] for _, p in RM.cell_specs(g)] == [p["sess"] for _, p in RM.cell_specs(b)]
        st = D(grid[0]["spec"][1])
        assert {k: st.p[k] for k in OPTS} == {"f_book": "off", "x_book": "off", "f_thin": "off", **v["option"]}
    tf = cls.SCREEN_TFS[0]
    f = L2.variant_features(name)
    assert isinstance(f, S.L2Features) and f.columns == S.template_feature_needs(v["option"]) and "t_utc" in f.columns
    c2 = L2.variant_features(name, c2_seed=2)
    assert isinstance(c2, score.C2Features) and c2.seed == 2 and c2.columns == f.columns
    assert set(c2.shuffle_cols) == set(f.columns) - {"t_utc"}                     # the null shuffles the book columns, not the clock tag
    plan = L2.variant_plan(name, tf)
    key = f"{name}-NQ-tf{tf}"
    assert [(p["key"], p["stage"]) for p in plan] == [(key, "build"), (key + "-c2s1", "null"), (key + "-c2s2", "null")]
    assert [p["meta"].get("control") for p in plan] == [None, "c2", "c2"] and [p["meta"].get("seed") for p in plan] == [None, 1, 2]
    assert all(len(p["grid"]) == len(families.unit_grid(v["base"], "NQ", tf)) and p["meta"]["l2"] is True for p in plan)
    assert len(L2.variant_plan(name, tf, nulls=False)) == 1
    for root in ("ES", "GC"):
        with pytest.raises(ValueError, match="Level-2 options exist for"):
            L2.variant_grid(name, root, tf)
    with pytest.raises(ValueError, match="SCREEN_TFS"):
        L2.variant_grid(name, "NQ", "7")


def test_a_variant_is_judged_over_the_same_cells_as_its_base_there_is_no_subset():
    import inspect
    for fn in (L2.variant_grid, L2.variant_plan, L2.run_variant):
        assert "variants" not in inspect.signature(fn).parameters and "base_plateau" not in inspect.signature(fn).parameters
    with pytest.raises(TypeError):
        L2.variant_grid("donchian_fbook", "NQ", "15", variants=[{"n": 40}])
    assert len(L2.variant_grid("donchian_fbook", "NQ", "15")) == len(families.library("donchian")["variants"]) * 32


SESS_AT = {"eve": (-1, 20, 0), "asia": (0, 1, 0), "london": (0, 4, 0), "pre": (0, 8, 40), "nyam": (0, 10, 0), "mid": (0, 12, 0),
           "pm": (0, 14, 0)}


def fake_store(runs, key: str, grid: list, nets: dict, meta: dict) -> None:
    """A unit store with INVENTED trades (one per cell and session, net = nets[session]): the seals read stores, and no
    strategy result may be computed for a test. nets: session -> net per trade."""
    def one(sess, net):
        off, h, m = SESS_AT[sess]
        ms = int(dt.datetime(2023, 3, 14 + off, h, m, tzinfo=S.ET).timestamp() * 1000)
        return {"date": "2023-03-14", "entry_ms": ms, "exit_ms": ms + 60000, "net": float(net), "mae_usd": 10.0, "side": "long",
                "exit_reason": "time", "entry_price": 15000.0, "sl": 14990.0}
    res = [{"trades": [one(s, n) for s, n in nets.items()], "meta": {"inputs": dict(c["spec"][1]), "engine": "fake", "root": "NQ"},
            "sessions": 1, "used": 1, "skipped": [], "no_trade": [], "elapsed_s": 0.0} for c in grid]
    LB.write_unit(key, meta, grid, res, runs)


def base_store(runs, base: str, tf: str, nets: dict, **meta) -> None:
    fake_store(runs, f"{base}-NQ-tf{tf}", families.unit_grid(base, "NQ", tf), nets,
               {"family": base, "tf": tf, "stage": "build", "period": "build", **meta})


def test_the_seal_is_the_base_units_own_build_store_session_by_session(tmp_path):
    runs = tmp_path / "runs"
    with pytest.raises(L2.StageDSealed, match="no BUILD store"):
        L2.base_sessions("orb_fbook", "5", runs_dir=runs)
    base_store(runs, "orb", "5", {"nyam": 50.0, "pm": -50.0, "eve": 20.0})
    assert L2.base_sessions("orb_fbook", "5", runs_dir=runs) == ["eve", "nyam"]   # library.SESS7 order; pm failed, the rest never traded
    assert L2.base_sessions("orb_thin", "5", runs_dir=runs) == ["eve", "nyam"]
    with pytest.raises(L2.StageDSealed, match="no BUILD store"):
        L2.base_sessions("orb_fbook", "15", runs_dir=runs)                        # another tf is another unit
    base_store(runs, "orb", "5", {"nyam": -1.0, "pm": -1.0})
    assert L2.base_sessions("orb_fbook", "5", runs_dir=runs) == []
    for wrong in ({"stage": "null"}, {"period": "pick"}, {"family": "straddle"}):   # not the base's BUILD store
        base_store(runs, "orb", "5", {"nyam": 50.0}, **wrong)
        with pytest.raises(L2.StageDSealed, match="not the BUILD store"):
            L2.base_sessions("orb_fbook", "5", runs_dir=runs)
    fake_store(runs, "orb-NQ-tf5", families.unit_grid("orb", "NQ", "5")[:32], {"nyam": 50.0},
               {"family": "orb", "tf": "5", "stage": "build", "period": "build"})
    with pytest.raises(L2.StageDSealed, match="registered grid"):                 # a partial grid is not the unit
        L2.base_sessions("orb_fbook", "5", runs_dir=runs)


def test_run_variant_is_sealed_until_the_base_passed_the_build_plateau_and_writes_the_base_grid_with_the_option(tmp_path, monkeypatch):
    """3 BUILD days, tmp_path stores and ledger. The base store is INVENTED (fake_store); the variant runs for real: counts
    and identity only."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    runs, led = tmp_path / "runs", tmp_path / "ledger.csv"
    kw = dict(root="NQ", workers=1, runs_dir=runs, ledger=led, log=tmp_path / "log.txt", days=DAYS[5:8])
    with pytest.raises(L2.StageDSealed, match="no BUILD store"):
        L2.run_variant("orb_fbook", "5", **kw)
    base_store(runs, "orb", "5", {"nyam": -5.0, "pm": -5.0})
    with pytest.raises(L2.StageDSealed, match="in no session"):
        L2.run_variant("orb_fbook", "5", **kw)
    assert sorted(p.name for p in runs.iterdir()) == ["orb-NQ-tf5"] and LB.read_ledger(led) == []      # nothing ran, nothing counted
    base_store(runs, "orb", "5", {"nyam": 5.0, "pm": -5.0})
    try:
        out = L2.run_variant("orb_fbook", "5", **kw)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    keys = ["orb_fbook-NQ-tf5", "orb_fbook-NQ-tf5-c2s1", "orb_fbook-NQ-tf5-c2s2"]
    assert out == [{"key": k, "ok": True, "cells": 96} for k in keys]             # the base's WHOLE grid: 3 variants x 32
    rows = LB.read_ledger(led)
    assert [(r["stage"], r["key"], r["kind"], r["cells"], r["family"], r["control"], r["seed"]) for r in rows] == [
        ("build", keys[0], "grid", "96", "orb_fbook", "", ""), ("null", keys[1], "null", "0", "orb_fbook", "c2", "1"),
        ("null", keys[2], "null", "0", "orb_fbook", "c2", "2")]
    # ORCHESTRATOR DECISIONS 6: the C2 nulls are tracked apart (null_cells) and do not count toward the 40,000 cap
    assert LB.ledger_used(path=led)["cells"] == 96 and LB.ledger_nulls(path=led) == 192
    want = [c["id"] for c in families.unit_grid("orb", "NQ", "5")]
    for k, loader in zip(keys, ("L2Features", "C2Features", "C2Features")):
        meta = LB.load_unit(k, runs)["meta"]
        assert [c["id"] for c in meta["cells"]] == want and meta["features_loader"] == loader
        assert meta["base"] == "orb" and meta["option"] == {"f_book": "on"} and meta["stage_d"] == "D2" and meta["period"] == "build"
        assert meta["base_pass_sessions"] == ["nyam"] and meta["l2"] is True and "SECOND LOOK" in meta["second_look"]
        assert all(c["inputs"]["f_book"] == "on" and c["skipped_by_error"] == 0 for c in meta["cells"])
        assert meta["features"] == ["imb10", "t_utc"] and meta["coverage"]["sessions"] == 3 and meta["passes"] == list(RM.DAY_PASSES)
        assert meta["hold_to"] == "day" and all(c["inputs"]["hold_to"] == "day" for c in meta["cells"])
        assert meta["complexity"] == families.library("orb")["complexity"] + 1 and quoted(meta["l2_rationale"])
    # the stores hold the KEPT trades: a fill the filter refused never reaches a store (and so no plateau, no member)
    grid = L2.variant_grid("orb_fbook", "NQ", "5")
    direct = RM.run_grid(grid, "NQ", features=L2.variant_features("orb_fbook"), workers=1, days=DAYS[5:8])
    stored = [c["trades"] for c in LB.load_unit(keys[0], runs)["meta"]["cells"]]
    assert stored == [len(L2.kept(r["trades"])) for r in direct] and sum(stored) < sum(len(r["trades"]) for r in direct)
    assert sum(stored) > 0 and int(rows[0]["trades"]) == sum(stored)
    # the variant is READ only in the sessions where its base passed
    assert [r["id"] for r in L2.variant_table("orb_fbook", "5", "nyam", runs_dir=runs)] == want
    assert len(L2.variant_table("orb_fbook", "5", "nyam", runs_dir=runs, c2_seed=2)) == 96
    for sess in ("pm", "eve", "all"):
        with pytest.raises(L2.StageDSealed, match="only in the sessions"):
            L2.variant_table("orb_fbook", "5", sess, runs_dir=runs)
    with pytest.raises(L2.StageDSealed, match="no store yet"):
        L2.variant_table("orb_xbook", "5", "nyam", runs_dir=runs)
    again = L2.run_variant("orb_fbook", "5", **kw)
    assert again == [{"key": k, "skipped": True} for k in keys] and len(LB.read_ledger(led)) == 3          # idempotent
    monkeypatch.setattr(LB, "CAPS", {**LB.CAPS, "cells": 96 + 95})                # a unit past the cap is refused as a whole
    with pytest.raises(LB.CapExceeded):
        L2.run_variant("orb_xbook", "5", **kw)
    assert len(LB.read_ledger(led)) == 3 and not (runs / "orb_xbook-NQ-tf5").exists()


def test_a_member_cell_runs_only_where_the_base_passed_and_pick_only_for_a_variant_that_survived_build(tmp_path):
    """l2ideas.run_member (the Admit stage's runner of a stage D cell). Stores are INVENTED; the one real run is 2 BUILD days,
    counts only. PICK is never read here: the last check shows a PICK run asked with BUILD days is refused before it starts."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    runs, led = tmp_path / "runs", tmp_path / "ledger.csv"
    cell, var = S.menu("NQ")[9], {"or_min": "15"}
    kw = dict(runs_dir=runs, ledger=led, days=DAYS[6:8])
    with pytest.raises(L2.StageDSealed, match="no store yet"):
        L2.run_member("orb_xbook", "5", var, cell, "build", sess="nyam", **kw)
    meta = {**L2.variant_meta("orb_xbook", "NQ", "5"), "stage": "build", "period": "build", "base_pass_sessions": ["nyam", "mid"]}
    fake_store(runs, "orb_xbook-NQ-tf5", L2.variant_grid("orb_xbook", "NQ", "5"), {"nyam": -5.0, "mid": 5.0, "pm": 5.0}, meta)
    with pytest.raises(L2.StageDSealed, match="only in the sessions"):
        L2.run_member("orb_xbook", "5", var, cell, "build", sess="pm", **kw)      # the base did not pass in pm
    with pytest.raises(LB.PickSealed):
        L2.run_member("orb_xbook", "5", var, cell, "pick", sess="nyam", **kw)     # the variant itself failed BUILD in nyam
    with pytest.raises(ValueError, match="inside the pick period"):
        L2.run_member("orb_xbook", "5", var, cell, "pick", sess="mid", **kw)      # seal open, but these are BUILD days: nothing runs
    for bad in (dict(variant_={"or_min": "10"}, exit_cell=cell), dict(variant_=var, exit_cell={**cell, "stop_val": 11.0})):
        with pytest.raises(ValueError, match="registered variant"):
            L2.run_member("orb_xbook", "5", period="build", sess="nyam", **bad, **kw)
    with pytest.raises(ValueError, match="one of"):
        L2.run_member("orb_xbook", "5", var, cell, "build", sess="all", **kw)
    with pytest.raises(ValueError, match="EXAM is sealed"):
        L2.run_member("orb_xbook", "5", var, cell, "exam", sess="nyam", **kw)
    try:
        r = L2.run_member("orb_xbook", "5", var, cell, "build", sess="nyam", **kw)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    assert r["session"] == "nyam" and r["meta"]["strategy"] == "families.l2ideas.D_orb" and r["meta"]["inputs"]["x_book"] == "on"
    assert r["meta"]["features"] == ["imb10", "t_utc"] and r["skipped_by_error"] == 0 and r["sessions"] == 2
    assert all(S.session_of(t["entry_ms"]) == "nyam" for t in r["trades"]) and r["key"] == "orb_xbook-NQ-tf5-nyam-or_min15_pts10-r1-build"
    assert LB.read_ledger(led) == []                                              # `days` = a test: nothing is recorded
    # a time-fired base: the clock time decides the session
    tmeta = {**L2.variant_meta("straddle_t_0930_thin", "NQ", "30"), "stage": "build", "period": "build", "base_pass_sessions": ["nyam"]}
    fake_store(runs, "straddle_t_0930_thin-NQ-tf30", L2.variant_grid("straddle_t_0930_thin", "NQ", "30"), {"nyam": 5.0}, tmeta)
    r = L2.run_member("straddle_t_0930_thin", "30", {"off": "atr0p5"}, cell, "build", c2_seed=1, stress=True, **kw)
    assert r["session"] == "nyam" and r["meta"]["features_loader"] == "C2Features" and r["meta"]["stress"] == S.STRESS
    assert r["meta"]["strategy"] == "families.l2ideas.D_straddle_t_0930" and r["skipped_by_error"] == 0
    assert all("tag" not in t for t in r["trades"])                               # only kept trades, as the base's own rows
    full = L2.run_member("straddle_t_0930_thin", "30", {"off": "atr0p5"}, cell, "build", **kw)
    base = S.run(families.REGISTRY["straddle_t_0930"][0], {**families.unit_inputs("straddle_t_0930", "30"), "off": "atr0p5", **cell},
                 days=DAYS[6:8], workers=1)
    assert all(t in base["trades"] for t in full["trades"]) and len(full["trades"]) <= len(base["trades"]) > 0


# ================================================================================================================================
# 4. STAGE D ON THE BREAKOUT FAMILIES, synthetic: the filter is judged at the trade, the book exit needs a flip
# ================================================================================================================================
SD = dt.date(2023, 3, 14)                          # a BUILD weekday (the tapes and tables below are synthetic)
WIDE = {"stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}                      # no stop / target is ever near


def sec(hhmm: str) -> int:
    return TF.hm(hhmm)


def syn_tape(price_at, start="09:00", end="11:05"):
    """A print every 10 s; price_at(second of the ET day, print index) -> price."""
    ts = np.arange(S.et_ns(SD, start), S.et_ns(SD, end), 10 * NS, dtype=np.int64)
    s0 = S.et_ns(SD, "00:00")
    px = np.array([price_at(int((t - s0) // NS), i) for i, t in enumerate(ts)], np.float64)
    return S.Tape("NQ", SD, "NQM3", ts, px, np.ones(len(ts), np.int64))


def syn_feats(cols: dict, start="08:55", end="11:05"):
    """One row per minute stamped [start, end), usable 60 s after its stamp. cols: name -> f('HH:MM' of the stamp) -> value."""
    m0 = np.arange(S.et_ns(SD, start), S.et_ns(SD, end), MIN, dtype=np.int64)
    hhmm = [dt.datetime.fromtimestamp(t / 1e9, S.ET).strftime("%H:%M") for t in m0]
    data = {"t_utc": (m0 // NS).astype(np.int64)}
    for k, fn in cols.items():
        data[k] = np.array([fn(h) for h in hhmm], np.float32)
    return S.Features(m0 + MIN, data)


def hms(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, S.ET).strftime("%H:%M:%S")


def shape(trades):
    """What a synthetic case asserts of a session's trades: (side, entry time, entry price, exit time, exit reason, OCO leg)."""
    return [(t["side"], hms(t["entry_ns"]), t["entry_price"], hms(t["exit_ns"]), t["exit_reason"], t["oco"]) for t in trades]


def orb_px(s, i):
    if s < sec("09:30"):
        return 15005.0 + 0.25 * (i % 2)
    if s < sec("09:35"):
        return 15000.0 if i % 2 else 15010.0       # the opening range 15000 .. 15010 -> stops at 15010.25 / 14999.75
    if s < sec("09:41"):
        return 15005.0
    if s < sec("10:00"):
        return 15020.0                             # the upside break at 09:41:00
    if s < sec("10:30"):
        return 14980.0                             # ... and a move through the low at 10:00:00
    return 15005.0


def don_px(s, i):
    return 15000.0 + 0.25 * (i % 3) if s < sec("09:40") else 15010.0      # the 09:40 bar closes above the 5-bar channel


def str_px(s, i):
    if s < sec("09:40"):
        return 15000.0 + 0.25 * (i % 2)
    return 15030.0 if s < sec("10:10") else 14960.0                        # up through +10 at 09:40:00, down through -10 at 10:10:00


def breakout_case(fam):
    """(base class, its stage D class, params, tape, the base's long trade, the decision / placement 'HH:MM')."""
    name = {"orb": "orb", "donchian": "donchian", "straddle_t": "straddle_t_0930"}[fam]
    cls, inp = reg(name)
    D = L2.stage_class(name)
    if fam == "orb":
        return cls, D, {**inp, "tf": "1", "sess": "nyam", "or_min": "5", **WIDE}, syn_tape(orb_px), \
            ("long", "09:41:00", 15020.25, "11:00:00", "time"), "09:35"
    if fam == "donchian":
        return cls, D, {**inp, "tf": "1", "sess": "nyam", "n": 5, **WIDE}, syn_tape(don_px), \
            ("long", "09:41:10", 15010.25, "11:00:00", "time"), "09:41"
    return cls, D, {**inp, "tf": "30", "off": "ptsA", **WIDE}, syn_tape(str_px, start="07:30"), \
        ("long", "09:40:00", 15030.25, "11:00:00", "time"), "09:30"


def raw(cls, params, tape, f=None):
    """One session through the simulator: the SessionResult as it comes out (a stage D run under an entry filter still holds
    the fills the filter refused, tagged)."""
    return S.run_session(cls(params), tape, features=f, daily=[], on_error="raise")


def go(cls, params, tape, f=None) -> list:
    """The session's trades as stage D reports them: l2ideas.kept of the simulator's rows."""
    return L2.kept(raw(cls, params, tape, f).trades)


def _minus(hhmm: str, minutes: int) -> str:
    s = sec(hhmm) - 60 * minutes
    return "%02d:%02d" % (s // 3600, s % 3600 // 60)


@pytest.mark.parametrize("fam", ["orb", "donchian", "straddle_t"])
def test_the_stage_class_with_every_option_off_trades_exactly_as_its_base(fam):
    cls, D, p, tape, long_tr, at = breakout_case(fam)
    base = raw(cls, p, tape)
    assert shape(base.trades) == [long_tr + (fam != "donchian",)] and base.both_sides is (fam != "donchian")
    for f in (None, syn_feats({"imb10": lambda h: -0.9, "ask10_rel15": lambda h: 0.5, "bid10_rel15": lambda h: 0.5})):
        got = raw(D, p, tape, f)
        assert got.trades == base.trades and got.both_sides is base.both_sides    # no option: the table is not read
        assert L2.kept(got.trades) == base.trades                                 # ... and `kept` passes untagged rows through


@pytest.mark.parametrize("fam", ["orb", "straddle_t"])
def test_under_an_entry_filter_the_simulator_runs_the_bases_own_bracket_and_tags_the_fill(fam):
    """A resting bracket is the base's, untouched: the same orders, the same fill, the same exit -- whatever the book says.
    The verdict rides on the trade row and `kept` turns it into the base's row or into nothing."""
    cls, D, p, tape, long_tr, at = breakout_case(fam)
    base = raw(cls, p, tape)
    for opt, cols in (("f_book", {"imb10": 0.2}), ("f_book", {"imb10": -0.2}), ("f_thin", {"ask10_rel15": 0.3, "bid10_rel15": 0.3}),
                      ("f_thin", {"ask10_rel15": -0.3, "bid10_rel15": -0.3})):
        f = syn_feats({k: (lambda h, v=v: v) for k, v in cols.items()})
        got = raw(D, {**p, opt: "on"}, tape, f)
        want = next(iter(cols.values())) in (0.2, -0.3)
        assert [{k: v for k, v in t.items() if k != "tag"} for t in got.trades] == base.trades and got.both_sides is base.both_sides
        assert [t["tag"] for t in got.trades] == [{"stage_d": want, "tag": None}]
        assert L2.kept(got.trades) == (base.trades if want else [])
        assert "tag" in got.trades[0]                                             # kept copies: the raw rows are not edited
    # `kept` by itself: only True is kept; None = never judged = no signal; a family's own tag is put back
    row = dict(base.trades[0])
    assert L2.kept([{**row, "tag": {"stage_d": None, "tag": None}}, {**row, "tag": {"stage_d": False, "tag": None}}]) == []
    assert L2.kept([{**row, "tag": {"stage_d": True, "tag": {"k": 1}}}]) == [{**row, "tag": {"k": 1}}]
    assert L2.kept([{**row, "tag": {"k": 1}}, row]) == [{**row, "tag": {"k": 1}}, row]


@pytest.mark.parametrize("fam", ["orb", "donchian", "straddle_t"])
def test_f_book_is_judged_at_the_trade_not_when_the_bracket_is_placed(fam):
    """EDGE_SPEC D2: "skip a trade when the 5-min mean imb10 opposes its side". donchian enters at market: the book of
    its decision. orb / straddle_t rest a bracket placed minutes before the break (orb 09:35 -> break 09:41, straddle_t
    09:30 -> break 09:40): the five rows usable when the fill's own minute began decide, not the book at placement."""
    cls, D, p, tape, long_tr, at = breakout_case(fam)
    rest = fam != "donchian"
    base = raw(cls, p, tape).trades
    on = {**p, "f_book": "on"}
    const = lambda v: syn_feats({"imb10": lambda h: v})        # noqa: E731
    # the bid side heavier all along (mean >= 0): the long is not opposed -> the base's trade, row for row
    assert go(D, on, tape, const(0.2)) == base
    # the ask side heavier all along: the upside break is skipped, and NOTHING is traded in its place -- the later move
    # through the low (orb 10:00, straddle_t 10:10) is not the base's trade either
    assert go(D, on, tape, const(-0.2)) == []
    # exactly balanced (mean 0): not opposed
    assert go(D, on, tape, const(0.0)) == base
    # no signal -> no entry: NaN, no table, a table that stopped long before
    assert go(D, on, tape, const(float("nan"))) == [] and go(D, on, tape, None) == []
    assert go(D, on, tape, syn_feats({"imb10": lambda h: 0.2}, end="09:20")) == []
    # one NaN row among the five at PLACEMENT: irrelevant for a resting bracket (the five rows before the fill minute are
    # clean); donchian's decision is that instant: no signal, no entry
    hole = syn_feats({"imb10": lambda h: float("nan") if h == _minus(at, 3) else 0.2})
    assert go(D, on, tape, hole) == (base if rest else [])
    # ... a NaN row among the five before the fill minute: no signal at the trade
    fm = long_tr[1][:5]
    assert go(D, on, tape, syn_feats({"imb10": lambda h: float("nan") if h == _minus(fm, 3) else 0.2})) == []
    # THE BOOK AT THE TRADE, not at placement. Supportive when the bracket is placed, opposed from then on: skipped.
    # donchian decides once, on the rows before its decision
    late_flip = syn_feats({"imb10": lambda h: 0.2 if h < at else -0.9})
    assert go(D, on, tape, late_flip) == ([] if rest else base)
    # opposed at placement, supportive from then on: the five rows before the fill minute are supportive -> traded
    early_flip = syn_feats({"imb10": lambda h: -0.9 if h < at else 0.2})
    assert go(D, on, tape, early_flip) == (base if rest else [])
    # the MEAN of the five rows before the fill minute, not the newest one: four opposed minutes outweigh one agreeing
    mixed = syn_feats({"imb10": lambda h: 0.2 if h == _minus(fm, 1) else -0.2})
    assert go(D, on, tape, mixed) == []
    # a row is usable only when its minute has ended: rows that turn supportive FROM the fill minute on come too late,
    # and rows that turn against the trade from the fill minute on are not yet known
    assert go(D, on, tape, syn_feats({"imb10": lambda h: -0.2 if h < fm else 0.9})) == []
    assert go(D, on, tape, syn_feats({"imb10": lambda h: 0.2 if h < fm else -0.9})) == base


def test_a_filtered_bracket_makes_the_bases_trade_or_none_never_another_one():
    cls, D, p, _, _, _ = breakout_case("straddle_t")
    on = {**p, "f_book": "on"}
    const = lambda v: syn_feats({"imb10": lambda h: v})        # noqa: E731

    def again_px(s, i):                            # up-break 09:40, back inside 09:50, a second up-break 10:10
        if s < sec("09:40"):
            return 15000.0 + 0.25 * (i % 2)
        return 15030.0 if s < sec("09:50") else 15000.0 if s < sec("10:10") else 15030.0

    def whip_px(s, i):                             # up through +10 at 09:40:00 and down through -10 at 09:40:30: one minute
        if s < sec("09:40"):
            return 15000.0 + 0.25 * (i % 2)
        return 15030.0 if s < sec("09:40") + 30 else 14960.0

    def late_px(s, i):                             # the break comes at 10:35, after the family's own 60-minute cancel
        return 15000.0 + 0.25 * (i % 2) if s < sec("10:35") else 15030.0
    # a second break of a skipped level is not traded, even when the book has turned supportive by then
    tape = syn_tape(again_px, start="07:30")
    assert [x[:2] for x in shape(raw(cls, p, tape).trades)] == [("long", "09:40:00")]
    assert go(D, on, tape, syn_feats({"imb10": lambda h: -0.2 if h < "09:45" else 0.2})) == []
    # a whipsaw minute: the base took the long; the book opposed it -> skipped; the short the book would have liked is
    # NOT traded (it is not the base's trade: the filter removes trades, it never picks a side)
    tape = syn_tape(whip_px, start="07:30")
    assert [x[:2] for x in shape(raw(cls, p, tape).trades)] == [("long", "09:40:00")]
    assert go(D, on, tape, const(-0.2)) == [] and len(go(D, on, tape, const(0.2))) == 1
    # no bracket, no trade: the family's cancel is the base's
    tape = syn_tape(late_px, start="07:30")
    assert raw(cls, p, tape).trades == [] and go(D, on, tape, const(0.2)) == []


def test_no_decision_at_the_fills_minute_is_no_signal():
    """(i) of the stated limits: the filter's verdict must be the one of the 1-minute decision that began the fill's own
    minute. The minute before the fill has no print here -> no decision there -> the trade is skipped, although the last
    verdict (two minutes old) allowed it."""
    cls, D, p, tape, long_tr, at = breakout_case("straddle_t")
    quiet = (tape.ts < S.et_ns(SD, "09:39")) | (tape.ts >= S.et_ns(SD, "09:40"))
    gap = S.Tape("NQ", SD, "NQM3", tape.ts[quiet], tape.px[quiet], tape.size[quiet])
    f = syn_feats({"imb10": lambda h: 0.2})
    assert shape(raw(cls, p, gap).trades) == [long_tr + (True,)]                  # the base trades the break all the same
    assert go(D, {**p, "f_book": "on"}, gap, f) == [] and len(go(D, {**p, "f_book": "on"}, tape, f)) == 1


@pytest.mark.parametrize("fam", ["orb", "donchian", "straddle_t"])
def test_f_thin_needs_thin_depth_on_the_break_side_at_the_trade(fam):
    """EDGE_SPEC D4: "only when depth on the break side is thin". One row decides (the minute that just ended): for a
    resting bracket the one before the fill's minute, not the one before the placement."""
    cls, D, p, tape, long_tr, at = breakout_case(fam)
    rest = fam != "donchian"
    base = raw(cls, p, tape).trades
    on = {**p, "f_thin": "on"}

    def f(ask, bid, **kw):
        return syn_feats({"ask10_rel15": lambda h: ask, "bid10_rel15": lambda h: bid}, **kw)
    # a long breaks into the ASK side: thin offers (0.75 x their 15-minute median) -> traded, whatever the bid side is
    assert go(D, on, tape, f(-0.25, 0.0)) == base and go(D, on, tape, f(-0.25, -0.25)) == base
    assert go(D, on, tape, f(0.0, -0.25)) == []                                   # thick offers: the up-break is skipped
    assert go(D, on, tape, f(-0.2, 0.0)) == base                                  # a ratio of exactly 0.80 is thin
    assert go(D, on, tape, f(-0.19, -0.19)) == []                                 # 0.81: not thin -> no entry
    assert go(D, on, tape, f(float("nan"), float("nan"))) == [] and go(D, on, tape, None) == []
    assert go(D, on, tape, f(-0.25, -0.25, end="09:20")) == []                    # a stale table is no signal
    # WHEN. Thin only in the minute before the placement: nothing to a resting bracket that fills minutes later
    was = syn_feats({"ask10_rel15": lambda h: -0.25 if h == _minus(at, 1) else 0.3, "bid10_rel15": lambda h: 0.3})
    assert go(D, on, tape, was) == ([] if rest else base)
    # thin only in the minute before the fill's minute: that row decides a resting fill
    fm = _minus(long_tr[1][:5], 1)
    just = syn_feats({"ask10_rel15": lambda h: -0.25 if h == fm else 0.3, "bid10_rel15": lambda h: 0.3})
    assert go(D, on, tape, just) == base
    # thin only from the fill's minute on: too late
    late = syn_feats({"ask10_rel15": lambda h: -0.25 if h >= long_tr[1][:5] else 0.3, "bid10_rel15": lambda h: 0.3})
    assert go(D, on, tape, late) == []


@pytest.mark.parametrize("fam", ["orb", "donchian", "straddle_t"])
def test_x_book_leaves_only_after_the_book_flipped_against_a_trade_it_had_not_opposed(fam):
    """EDGE_SPEC D3: "leave when the 5-min mean imb10 flips against the open trade for 2 consecutive minutes (rationale:
    the inventory that supported the trade is gone)"."""
    cls, D, p, tape, long_tr, at = breakout_case(fam)
    oco = fam != "donchian"
    base = raw(cls, p, tape)
    on = {**p, "x_book": "on"}
    left = lambda t: [long_tr[:3] + (t, "book", oco)]          # noqa: E731
    flip = syn_feats({"imb10": lambda h: 0.2 if h < "09:46" else -0.2})
    out = raw(D, on, tape, flip)
    # supportive at the entry. The 5-minute mean at T = the rows stamped T-5 .. T-1: 09:48 -> +0.04, 09:49 -> -0.04 (1),
    # 09:50 -> -0.12 (2) -> a market exit sent at 09:50:00, live 85 ms later: the 09:50:10 print, one tick against.
    # The ENTRY is the base's (the OCO pair too)
    px = float(tape.px[int(np.searchsorted(tape.ts, S.et_ns(SD, "09:50:10")))])
    assert shape(out.trades) == left("09:50:10") and out.trades[0]["exit_price"] == px - 0.25 and out.both_sides is oco
    assert L2.kept(out.trades) == out.trades                                      # an exit variant carries no entry tag
    # the book agrees with the long all along / no book at all / NaN: the base trade, untouched
    for f in (syn_feats({"imb10": lambda h: 0.2}), None, syn_feats({"imb10": lambda h: float("nan")})):
        assert raw(D, on, tape, f).trades == base.trades
    # NO FLIP, NO EXIT: the book opposed the long from its entry on -> it never supported the trade, nothing is "gone"
    assert raw(D, on, tape, syn_feats({"imb10": lambda h: -0.2})).trades == base.trades
    # ... until it has been on the trade's side once: opposed up to the 09:43 row, supportive 09:44 .. 09:49, opposed from
    # 09:50. Armed at 09:47 (mean +0.04); 09:53 -> -0.04 (1), 09:54 -> -0.12 (2) -> exit
    turn = syn_feats({"imb10": lambda h: -0.2 if h < "09:44" else 0.2 if h < "09:50" else -0.2})
    assert shape(raw(D, on, tape, turn).trades) == left("09:54:10")
    # the reading AT THE ENTRY counts (the five rows before the fill minute: the verdict D2 would use). Supportive up to
    # the fill, opposed from the fill minute on: the first close after the fill is opposed (1), the next (2) -> out two
    # minutes after the fill minute started
    fm = long_tr[1][:5]
    snap = syn_feats({"imb10": lambda h: 0.2 if h < fm else -0.9})
    two = "%02d:%02d:10" % divmod(sec(fm) // 60 + 2, 60)
    assert shape(raw(D, on, tape, snap).trades) == left(two)
    # a balanced book at the entry (mean 0) does not oppose: armed. 09:47 -> -0.04 (1), 09:48 (2) -> exit
    flat0 = syn_feats({"imb10": lambda h: 0.0 if h < "09:46" else -0.2})
    assert shape(raw(D, on, tape, flat0).trades) == left("09:48:10")
    # no reading at the entry (NaN rows up to the fill minute) and opposed ever after: never armed
    blind = syn_feats({"imb10": lambda h: float("nan") if h < fm else -0.2})
    assert raw(D, on, tape, blind).trades == base.trades
    # opposed long BEFORE the entry does not matter: the reading at the entry is the five rows before it
    pre = syn_feats({"imb10": lambda h: -0.2 if h < _minus(fm, 6) else 0.2})
    assert raw(D, on, tape, pre).trades == base.trades
    # a minute without a signal neither counts nor resets: flip at 09:46 and a NaN row at 09:49: 09:49 opposed (1), 09:50 ..
    # 09:54 no signal, 09:55 opposed (2) -> exit at 09:55
    gap = syn_feats({"imb10": lambda h: 0.2 if h < "09:46" else float("nan") if h == "09:49" else -0.2})
    assert shape(raw(D, on, tape, gap).trades) == left("09:55:10")
    # the ENGINE's own option on the base class has no flip rule (2 opposed minutes after the fill are enough): the stage
    # D class is the one that implements EDGE_SPEC, and this is the difference
    eng = shape(raw(cls, on, tape, syn_feats({"imb10": lambda h: -0.2})).trades)
    assert [x[4] for x in eng] == ["book"] and eng[0][3] < "09:45:00"


def test_the_engines_own_entry_filter_on_a_resting_base_is_not_stage_d():
    """Why library.run_member(base, extra={'f_book': 'on'}) must not be used for a stage D member: on the BASE class the
    engine reads the book once, at placement, and lets the surviving leg fill whatever the book says later."""
    cls, D, p, tape, long_tr, at = breakout_case("orb")
    on = {**p, "f_book": "on"}
    late_flip = syn_feats({"imb10": lambda h: 0.2 if h < at else -0.9})          # supportive at placement only
    assert [x[:2] for x in shape(raw(cls, on, tape, late_flip).trades)] == [long_tr[:2]]      # the engine: filled into an opposing book
    assert go(D, on, tape, late_flip) == []                                       # stage D: skipped
    dn = syn_feats({"imb10": lambda h: -0.2})
    assert [x[0] for x in shape(raw(cls, on, tape, dn).trades)] == ["short"]     # the engine: the filter picked the other leg
    assert go(D, on, tape, dn) == []                                              # stage D: the base's trade or none


def test_a_resting_limit_entry_under_an_entry_filter_is_refused():
    D = L2.stage_class("orb")
    tape = syn_tape(orb_px)

    class Probe(D):
        def fam_time(self, ctx, sec_):
            if self.sid is not None:
                self._lim(ctx, "long", 14000.0)
    with pytest.raises(NotImplementedError, match="resting limit"):
        raw(Probe, {"tf": "1", "sess": "nyam", "f_book": "on", **WIDE}, tape, syn_feats({"imb10": lambda h: 0.2}))
    assert raw(Probe, {"tf": "1", "sess": "nyam", "x_book": "on", **WIDE}, tape, syn_feats({"imb10": lambda h: 0.2})).skip is None


# ================================================================================================================================
# 5. REAL BUILD DAYS (the 10 smoke days, one process): spies, oracles by row stamp, garbage after a cut
# ================================================================================================================================
COLS = ("imb10", "bid10_rel15", "ask10_rel15", "f_delta", "t_utc", "book_ok")      # every column any family below reads
LOG: list = []                                     # what the spies of the in-process runs record, in run order
MENU_IDS = ("atr3-r0", "pts20-r1")                 # two cells of the menu: a wide stop without a target, a tight 1:1
PLAN = (       # (family or stage D variant, tf, family-variant ids): each runs both menu cells, sess all / pre / eve as run_menus
    ("bimb_follow_d1", "5", ("k1p5", "k2")), ("flow_exhaust", "1", ("q90",)), ("flow_exhaust", "5", ("q85", "q90")),
    ("orb", "5", ("or_min5", "or_min15")), ("orb_fbook", "5", ("or_min5", "or_min15")), ("orb_thin", "5", ("or_min5", "or_min15")),
    ("orb_xbook", "5", ("or_min5", "or_min15")),
    ("donchian", "5", ("n10", "n20")), ("donchian_fbook", "5", ("n10", "n20")), ("donchian_thin", "5", ("n10", "n20")),
    ("donchian_xbook", "5", ("n10", "n20")),
    ("straddle", "30", ("off_atr0p5",)), ("straddle_fbook", "30", ("off_atr0p5",)), ("straddle_xbook", "30", ("off_atr0p5",)),
    ("straddle_t_0930", "30", ("offatr0p5", "offptsA")), ("straddle_t_0930_fbook", "30", ("offatr0p5", "offptsA")),
    ("straddle_t_0930_thin", "30", ("offatr0p5", "offptsA")), ("straddle_t_0930_xbook", "30", ("offatr0p5", "offptsA")),
    ("straddle_t_0300", "30", ("offatr0p25",)), ("straddle_t_0300_thin", "30", ("offatr0p25",)),
    ("straddle_t_2000", "30", ("offatr0p5",)), ("straddle_t_2000_fbook", "30", ("offatr0p5",)),
    ("straddle_t_2000_xbook", "30", ("offatr0p5",)),
    ("straddle_t_1800", "30", ("offatr0p5",)), ("straddle_t_1800_fbook", "30", ("offatr0p5",)),
    ("straddle_t_1800_thin", "30", ("offatr0p5",)), ("straddle_t_1800_xbook", "30", ("offatr0p5",)),
)


class Spy:
    """Mixed in front of a family class for the in-process runs. It changes nothing; it records, with the decision time:
      allowed   every entry verdict of the Template (a MARKET entry's Level-2 filter acts here)
      verdict   every verdict a stage D class takes for a resting bracket (at placement and at each 1-minute close)
      arm       every bracket a stage D class placed under an entry filter (how many legs rest)
      signal    the state every fam_signal call saw
      xbook     the book-exit counter, flat or not, armed or not, after every 1-minute close."""
    LABEL = ""
    _quiet = False

    def _arm(self, ctx, legs, **kw):
        gate = getattr(self, "_gate", False)       # under an entry filter the bracket is placed with the filter off:
        self._quiet = gate                         # those `allowed` calls are the base's, not a Level-2 verdict
        try:
            out = super()._arm(ctx, legs, **kw)
        finally:
            self._quiet = False
        if gate:
            LOG.append(("arm", self.LABEL, self.day, ctx.now_ns, len(out)))
        return out

    def allowed(self, side):
        ok = super().allowed(side)
        if not self._quiet:
            LOG.append(("allowed", self.LABEL, self.day, self._cx.now_ns, side, ok))
        return ok

    def _verdict(self, ctx, sd):
        ok = super()._verdict(ctx, sd)
        LOG.append(("verdict", self.LABEL, self.day, ctx.now_ns, "long" if sd > 0 else "short", ok))
        return ok

    def fam_signal(self, ctx):
        LOG.append(("signal", self.LABEL, self.day, ctx.now_ns, ctx.last_price, self.atr, self.nb, self.sn))
        super().fam_signal(ctx)

    def _xbook(self, ctx):
        super()._xbook(ctx)
        LOG.append(("xbook", self.LABEL, self.day, ctx.now_ns, self.xb, ctx.flat, bool(getattr(self, "_armed", False))))


def plan_specs(spied: bool) -> list:
    """[(label, name, option dict, (cls, params))] of PLAN; label = name|tf|cell id|sess."""
    out = []
    for name, tf, vids in PLAN:
        if name in families.LIBRARY:
            grid, opt = families.unit_grid(name, "NQ", tf), {}
        else:
            grid, opt = L2.variant_grid(name, "NQ", tf), L2.option(name)
        cells = [c for c in grid if c["id"] in {f"{v}_{x}" for v in vids for x in MENU_IDS}]
        assert len(cells) == len(vids) * len(MENU_IDS), (name, tf, vids)
        for c in cells:
            for cls, params in RM.cell_specs(c, "session"):       # the OLD exit convention (all / pre / eve): what the oracles below state
                label = f"{name}|tf{tf}|{c['id']}|{'t' if RM.is_time_fired(cls) else params['sess']}"
                if spied:
                    cls = type("Spy" + cls.__name__, (Spy, cls), {"LABEL": label})
                out.append((label, name, opt, (cls, params)))
    assert len({x[0] for x in out}) == len(out)
    return out


def one_pass(plan, features, days=DAYS):
    LOG.clear()
    res = S.run_many([x[3] for x in plan], days=days, workers=1, features=features, keep_ns=True, on_error="raise")
    return {x[0]: r for x, r in zip(plan, res)}, list(LOG)


@pytest.fixture(scope="module")
def real():
    """ONE in-process pass of PLAN (spied) over the 10 BUILD smoke days + the raw tapes and tables of those days."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    try:
        loader = S.L2Features(COLS)
        plan = plan_specs(spied=True)
        res, log = one_pass(plan, loader)
        tapes = {iso: S.load_tape(S._date(iso)) for iso in DAYS}
        tabs = {}
        for iso in DAYS:
            f = loader(S._date(iso))
            assert np.array_equal(f.usable_ns, (f.cols["t_utc"] + 60) * NS)       # the table's own law: usable = stamp + 60 s
            tabs[iso] = {"row": {int(t): i for i, t in enumerate(f.cols["t_utc"])}, **f.cols}
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    if any(t is None for t in tapes.values()):
        pytest.skip("tape not cached")
    assert all(r["skipped_by_error"] == 0 and r["meta"]["exec_guard"] is None for r in res.values())
    return {"plan": plan, "res": res, "log": log, "tapes": tapes, "tabs": tabs, "loader": loader}


def mean5(tab, now_ns: int):
    """D2 / D3 signal by row STAMP, without ctx: the float64 mean of imb10 over the five rows stamped in the five minutes
    before the newest usable minute's end (all five present and finite), else None."""
    m = (now_ns // NS // 60 - 1) * 60                                              # stamp of the minute that just ended
    idx = [tab["row"].get(m - 60 * k) for k in range(4, -1, -1)]
    if None in idx:
        return None
    v = tab["imb10"][idx].astype(np.float64)
    return float(np.mean(v)) if np.isfinite(v).all() else None


def thin(tab, now_ns: int, sd: int):
    i = tab["row"].get((now_ns // NS // 60 - 1) * 60)
    v = None if i is None else float(tab["ask10_rel15" if sd > 0 else "bid10_rel15"][i])
    return None if v is None or v != v else bool(1.0 + v <= 0.8 + 1e-6)


def verdict(tab, opt: dict, now_ns: int, side: str) -> bool:
    """What Template.allowed must answer for an entry of `side` decided at now_ns under the option (everything else off)."""
    sd = 1 if side == "long" else -1
    if "f_book" in opt:
        m = mean5(tab, now_ns)
        return m is not None and m * sd >= 0
    if "f_thin" in opt:
        return thin(tab, now_ns, sd) is True
    return True


def resting(name: str) -> bool:
    """A stage D variant of PLAN whose base rests stop entries (orb, straddle, straddle_t); donchian enters at market."""
    return name in L2.STAGE_D and L2.variant(name)["base"] != "donchian"


def filtered(opt: dict) -> bool:
    return bool(set(opt) & {"f_book", "f_thin"})


def test_real_days_every_entry_verdict_equals_the_oracle_by_row_stamp(real):
    """Every verdict of every family of PLAN on the 10 BUILD days -- a market entry's (`allowed`) and a resting bracket's at
    its placement and at each 1-minute close (`verdict`) -- is what the oracle (raw table, by stamp) says the option allows.
    A base family and an x_book variant are never refused and never judge a bracket."""
    seen, of = {}, {x[0]: (x[1], x[2]) for x in real["plan"]}
    for kind, label, day, now, side, ok in (e for e in real["log"] if e[0] in ("allowed", "verdict")):
        name, opt = of[label]
        want = verdict(real["tabs"][day], opt, now, side)
        assert ok is want, (kind, label, day, hms(now), side, ok, want)
        seen.setdefault((name, tuple(opt), kind), set()).add(ok)
        assert kind == "allowed" or (resting(name) and filtered(opt)), (kind, label)
    for name, tf, _ in PLAN:
        opt = tuple(L2.option(name)) if name in L2.STAGE_D else ()
        if opt in (("f_book",), ("f_thin",)):
            kind = "verdict" if resting(name) else "allowed"
            assert seen[(name, opt, kind)] == {True, False}, name                 # the filter both allows and refuses on these days
            assert (name, opt, "allowed" if resting(name) else "verdict") not in seen
        else:
            assert seen[(name, opt, "allowed")] == {True} and (name, opt, "verdict") not in seen, name
    # a resting bracket is judged again at every 1-minute close while it rests: far more verdicts than brackets
    n_arm = sum(1 for e in real["log"] if e[0] == "arm" and e[4])
    n_ver = sum(1 for e in real["log"] if e[0] == "verdict")
    assert n_arm > 100 and n_ver > 10 * n_arm
    assert all(resting(of[e[1]][0]) and filtered(of[e[1]][1]) for e in real["log"] if e[0] == "arm")
    assert not real["tabs"]["2022-06-13"]["book_ok"].any()                        # the roll day: the book is masked all day
    assert any(real["res"][x[0]]["trades"] for x in real["plan"] if x[1] == "straddle_t_1800")


def seg_end(iso: str, at: int) -> int:
    """End of the engine segment an instant belongs to: midnight for the evening before, else the day window's end."""
    d = dt.date.fromisoformat(iso)
    mid = S.et_ns(d, "00:00")
    return mid if at < mid else S.et_ns(d, S.effective_session_window(d, ("00:00", "16:10"))[1])


def test_real_days_a_filtered_resting_variant_is_its_bases_trade_list_minus_the_fills_the_filter_refuses(real):
    """THE POINT OF D2 / D4 ON A RESTING ENTRY (EDGE_SPEC: "skip a trade when ... opposes its side", "only when depth on the
    break side is thin"), orb / straddle / straddle_t on the 10 BUILD days. With the BASE run of the same cell as the only
    input, the variant's kept trades are exactly: the base's trades whose side the option allows on the rows usable at the
    START OF THE FILL'S OWN MINUTE (raw table, by stamp), provided a decision was taken there (the placement instant, or a
    1-minute close = the minute before printed) and a 1-minute close followed the fill inside the session window.
    So: no kept fill went into an opposing book or thick depth, no verdict is a minute old, no trade is not the base's."""
    n = Counter()
    for label, name, opt, _ in real["plan"]:
        if not (resting(name) and filtered(opt)):
            continue
        base = real["res"][label.replace(name + "|", L2.variant(name)["base"] + "|", 1)]["trades"]
        got = real["res"][label]["trades"]
        arms = {}
        for e in real["log"]:
            if e[0] == "arm" and e[1] == label:
                arms.setdefault(e[2], []).append(e[3])
        # under the filter the simulator ran the base's own brackets: the same fills, the same exits, plus the verdict tag
        assert [{k: v for k, v in t.items() if k != "tag"} for t in got] == base, label
        assert all(set(t["tag"]) == {"stage_d", "tag"} and t["tag"]["tag"] is None for t in got), label
        want = []
        for t in base:
            tab, ts = real["tabs"][t["date"]], real["tapes"][t["date"]].ts
            t0 = t["entry_ns"] // MIN * MIN
            a, b = np.searchsorted(ts, [t0 - MIN, t0], side="left")
            placed = max(x for x in arms[t["date"]] if x <= t["entry_ns"])        # the bracket this fill belongs to
            decided = t0 == placed or (t0 > placed and b > a)
            judged = t0 + MIN < seg_end(t["date"], t["entry_ns"])
            ok = verdict(tab, opt, t0, t["side"])
            n["base"] += 1
            n["no decision"] += not decided
            n["never judged"] += not judged
            n["refused"] += decided and judged and not ok
            if decided and judged and ok:
                want.append(t)
        assert L2.kept(got) == want, label
        n["kept"] += len(want)
        n["long"] += sum(t["side"] == "long" for t in want)
    assert n["base"] > 500 and n["kept"] >= 100 and n["refused"] >= 100 and 0 < n["long"] < n["kept"], dict(n)
    assert n["no decision"] + n["never judged"] <= 0.02 * n["base"], dict(n)      # the stated limit (i) is rare on NQ


def test_real_days_a_filtered_market_entry_was_allowed_at_its_own_decision(real):
    """donchian under f_book / f_thin: the engine's own rule. Every fill follows a decision the filter allowed (by row
    stamp), and that decision began the fill's minute whenever the fill came within the minute."""
    n = late = 0
    for label, name, opt, _ in real["plan"]:
        if resting(name) or not filtered(opt):
            continue
        said = [(e[2], e[3], e[4], e[5]) for e in real["log"] if e[0] == "allowed" and e[1] == label]
        got = real["res"][label]["trades"]
        assert L2.kept(got) == got and all(t["order_price"] is None and "tag" not in t for t in got), label
        for t in got:
            last = max((now, ok) for day, now, side, ok in said if day == t["date"] and side == t["side"] and now <= t["entry_ns"])
            assert last[1] is True and verdict(real["tabs"][t["date"]], opt, last[0], t["side"]) is True, (label, t["date"])
            late += t["entry_ns"] - last[0] >= MIN                                # a market order waiting for the next print
            n += 1
    assert n >= 50 and late <= 0.05 * n


def book_exit(tab, ts, t):
    """D3 by row stamp for ONE trade (EDGE_SPEC: the mean "flips against the open trade for 2 consecutive minutes"): the
    exit is armed once the 5-minute mean has not opposed the position -- at its entry (the last 1-minute close of its
    engine segment at or before the fill) or at a usable minute since; armed, the first 1-minute close after the fill at
    which the mean has opposed it for 2 consecutive usable minutes -> its ns, or None. A minute without a signal neither
    counts nor resets. A 1-minute close exists for every minute of the segment that has a print."""
    sd = 1 if t["side"] == "long" else -1
    mid = S.et_ns(dt.date.fromisoformat(t["date"]), "00:00")
    lo = mid if t["entry_ns"] >= mid else mid - 6 * 60 * MIN                      # the day segment, or the evening before (18:00)
    a, b = np.searchsorted(ts, [lo, t["exit_ns"]], side="left")
    closes = [int(m + 1) * MIN for m in np.unique(ts[a:b + 1] // MIN)]
    before = [c for c in closes if c <= t["entry_ns"]]
    v0 = mean5(tab, before[-1]) if before else None
    armed = v0 is not None and v0 * sd >= 0
    cnt = 0
    for end in closes:
        if end <= t["entry_ns"] or end > t["exit_ns"]:
            continue
        v = mean5(tab, end)
        if v is None:
            continue
        if v * sd >= 0:
            armed, cnt = True, 0
        elif armed:
            cnt += 1
            if cnt >= 2:                             # EDGE_SPEC D3: "for 2 consecutive minutes" (written out: not the engine's constant)
                return end
    return None


def test_real_days_every_book_exit_is_a_flip_of_two_consecutive_opposed_minutes_and_no_other_trade_had_one(real):
    n_book = n_other = n_opposed_in = 0
    for label, name, opt, _ in real["plan"]:
        if "x_book" not in opt:
            assert not [t for t in real["res"][label]["trades"] if t["exit_reason"] == "book"], label
            continue
        for t in real["res"][label]["trades"]:
            tab, ts = real["tabs"][t["date"]], real["tapes"][t["date"]].ts
            at = book_exit(tab, ts, t)
            k = len(ts) if at is None else int(np.searchsorted(ts, at + LIVE, side="left"))
            m0 = mean5(tab, t["entry_ns"])           # the book of the fill's own minute start (the verifier's measure)
            opposed_in = m0 is not None and m0 * (1 if t["side"] == "long" else -1) < 0
            n_opposed_in += opposed_in
            if t["exit_reason"] == "book":
                # the exit is the market order sent at that minute close: the first print at / after it + 85 ms
                assert at is not None and k < len(ts) and t["exit_ns"] == int(ts[k]), (label, t["date"], hms(t["entry_ns"]))
                n_book += 1
                # a trade entered into an opposing book cannot be closed by the first two minute closes after its fill
                t0 = t["entry_ns"] // MIN * MIN
                a0, b0 = np.searchsorted(ts, [t0 - MIN, t0], side="left")
                assert not (opposed_in and at - t["entry_ns"] <= 2 * MIN and b0 > a0), (label, t["date"], hms(t["entry_ns"]))
            else:                                   # stop / target / time got there first, or the book never flipped
                assert at is None or k == len(ts) or int(ts[k]) >= t["exit_ns"], (label, t["date"], hms(t["entry_ns"]))
                n_other += 1
    assert n_book >= 20 and n_other >= 5 and n_opposed_in >= 20
    # the counter the stage class kept at every minute close is the oracle's walk: 0 whenever the strategy is flat, never
    # counting while unarmed
    xb = [e for e in real["log"] if e[0] == "xbook"]
    assert xb and all(e[4] == 0 for e in xb if e[5]) and {e[4] for e in xb} == {0, 1}
    assert all(e[6] for e in xb if e[4] == 1) and {e[6] for e in xb if not e[5]} == {True, False}


def first_per_session(trades: list) -> dict:
    """(trade date, session) -> the entry side of the first trade entered there."""
    out = {}
    for t in sorted(trades, key=lambda t: t["entry_ns"]):
        out.setdefault((t["date"], S.session_of(t["entry_ms"])), {k: t[k] for k in ENTRY_SIDE})
    return out


def test_real_days_base_and_variant_run_on_identical_days_and_the_option_off_is_the_base(real):
    """Coverage (sessions, used, skipped days) of a variant = its base's; the base in a pass that loads features = the
    base without any feature table; the stage D class with every option off = the base; the spies change nothing."""
    plain = plan_specs(spied=False)
    try:
        with_f = S.run_many([x[3] for x in plain], days=DAYS, workers=1, features=real["loader"], keep_ns=True)
        base_only = [x for x in plain if not x[2] and not x[3][0].FEATURES]
        no_f = S.run_many([x[3] for x in base_only], days=DAYS, workers=1, keep_ns=True)
        off = S.run_many([(L2.stage_class(x[1]), x[3][1]) for x in base_only], days=DAYS, workers=1, features=real["loader"],
                         keep_ns=True)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    got = {x[0]: r for x, r in zip(plain, with_f)}
    for label, r in got.items():
        assert r["trades"] == real["res"][label]["trades"], label                 # the spy is transparent
    assert len(base_only) >= 20 and {x[1] for x in base_only} <= set(L2.BREAKOUT_BASES)
    for x, r, o in zip(base_only, no_f, off):
        assert r["trades"] == got[x[0]]["trades"] and r["skipped"] == got[x[0]]["skipped"], x[0]
        assert o["meta"]["strategy"] == "families.l2ideas.D_" + x[1]              # the mixin by itself changes nothing
        assert o["trades"] == got[x[0]]["trades"] and o["both_sides_sessions"] == got[x[0]]["both_sides_sessions"], x[0]
    n_kept = n_base = 0
    for label, name, opt, _ in plain:
        if not opt:
            continue
        b = got[label.replace(name + "|", L2.variant(name)["base"] + "|", 1)]
        v = got[label]
        assert (v["sessions"], v["used"], v["skipped"], v["eve_skipped"]) == (b["sessions"], b["used"], b["skipped"], b["eve_skipped"])
        assert v["sessions"] == len(DAYS) and v["skipped_by_error"] == 0
        if "x_book" in opt:               # an exit changes no entry before it acts: the FIRST trade of every session is the base's
            assert first_per_session(v["trades"]) == first_per_session(b["trades"]), label
        elif resting(name):               # the kept trades are rows of the base's trade list
            kept = L2.kept(v["trades"])
            assert all(t in b["trades"] for t in kept) and len(kept) <= len(b["trades"]), label
            assert v["both_sides_sessions"] == b["both_sides_sessions"]           # the evidence is the base bracket's (conservative)
            n_kept, n_base = n_kept + len(kept), n_base + len(b["trades"])
    assert 0 < n_kept < n_base


def test_real_days_d5_and_d1_trade_the_evening_and_the_pre_open_session_and_respect_the_half_day(real):
    for name in ("bimb_follow_d1", "flow_exhaust"):
        by = {}
        for label, n, _, _ in real["plan"]:
            if n != name:
                continue
            r = real["res"][label]
            sess = label.rsplit("|", 1)[1]
            assert not [x for x in r["no_trade"] if x["reason"].startswith(S.ERROR_PREFIX)], label
            got = {S.session_of(t["entry_ms"]) for t in r["trades"]}
            assert got <= ({"eve"} if sess == "eve" else {"pre"} if sess == "pre" else set(S.ORDER)), (label, got)
            by[sess] = by.get(sess, 0) + len(r["trades"])
            for t in r["trades"]:
                assert t["order_price"] is None and t["oco"] is False and t["both_sides"] is False
                e = dt.datetime.fromtimestamp(t["entry_ns"] / 1e9, S.ET)
                if sess == "eve":                                                 # the evening BEFORE the trade date
                    assert e.date() < dt.date.fromisoformat(t["date"]) and e.hour >= 18
                    assert dt.datetime.fromtimestamp(t["exit_ns"] / 1e9, S.ET).date() == e.date()      # never across midnight
                elif name == "flow_exhaust" and t["date"] in HALF_DAYS:
                    assert e.strftime("%H:%M:%S") < "13:10:01"                    # decided before 13:10, filled on the next print
        assert all(by.get(s, 0) > 0 for s in ("all", "pre", "eve")), (name, by)
    # D5 on a half day: its own cut is 13:10 ET (the engine ends that day at 13:15)
    late = [e for e in real["log"] if e[0] == "allowed" and e[1].startswith("flow_exhaust|") and e[2] in HALF_DAYS
            and hms(e[3]) >= "13:10:00" and e[1].endswith("|all")]
    assert late == []


# the session table of EDGE_SPEC / ENGINE.md, written out (seconds after 00:00 ET of the trade date; not l2sim.SESS)
SESSIONS = {"asia": (0, 10800), "london": (10800, 30300), "pre": (30300, 34200), "nyam": (34200, 39600), "mid": (39600, 48600),
            "pm": (48600, 57480), "eve": (-21600, -60)}
INSTANCE = {"all": ("asia", "london", "nyam", "mid", "pm"), "pre": ("pre",), "eve": ("eve",)}


def d5_real(tab, tape, iso: str, T: int, tf: int, q: float, sessions: tuple, memo: dict):
    """D5 at the decision T (ns) of a REAL day, recomputed without ctx and without the family: bars from the raw tape's
    prints, deltas from the raw table by row STAMP. -> 'long' | 'short' | None."""
    ts, px, step = tape.ts, tape.px, tf * 60
    mid = S.et_ns(dt.date.fromisoformat(iso), "00:00")
    sec_, t_s = (T - mid) // NS, T // NS
    sid = next((n for n in sessions if SESSIONS[n][0] < sec_ <= SESSIONS[n][1]), None)
    if sid is None or T % (step * NS):
        return None
    if iso in HALF_DAYS and sec_ >= 13 * 3600 + 600:                             # a half day ends 13:15: nothing from 13:10 on
        return None
    a, b = np.searchsorted(ts, [T - MIN, T], side="left")
    if b <= a:                                                                    # the bar's last minute did not print: a late close
        return None
    i = tab["row"].get(t_s - 60)
    if i is None or not tab["book_ok"][i]:                                        # the minute that just ended: present, book_ok
        return None

    def delta(end_s):                                                             # sum over the rows stamped [end - tf, end)
        if end_s not in memo:
            vals = [float(tab["f_delta"][k]) for k in (tab["row"].get(x) for x in range(end_s - step, end_s, 60)) if k is not None]
            vals = [v for v in vals if v == v]
            memo[end_s] = sum(vals) if vals else None
        return memo[end_s]

    d = delta(t_s)
    hist = [abs(x) for x in (delta(t_s - j * step) for j in range(1, 61)) if x is not None]
    if d is None or len(hist) < 30 or not (abs(d) > 0 and abs(d) >= np.percentile(np.array(hist, float), q)):
        return None

    def bar(end_ns):                                                              # (high, low, close) of the bucket's prints
        x, y = np.searchsorted(ts, [end_ns - step * NS, end_ns], side="left")
        return None if y <= x else (float(px[x:y].max()), float(px[x:y].min()), float(px[y - 1]))

    prev, e = [], T - step * NS
    while (e - mid) // NS > SESSIONS[sid][0]:                                     # the session's earlier tf bars
        o = bar(e)
        if o:
            prev.append(o)
        e -= step * NS
    if not prev:
        return None
    h, l, c = bar(T)
    if d > 0:
        return "short" if h > max(x[0] for x in prev) and c < (h + l) / 2.0 else None
    return "long" if l < min(x[1] for x in prev) and c > (h + l) / 2.0 else None


def test_real_days_d5_signals_at_every_decision_equal_the_definition_recomputed_from_the_raw_tape_and_table(real):
    """Every instant the Template let flow_exhaust decide on the 10 BUILD days (sessions all / pre / eve, tf 1 and 5): it
    asked for an entry exactly when, and on the side that, the oracle derives from the raw prints and the raw rows."""
    n_dec = n_sig = 0
    sides = set()
    for label, name, _, (cls, params) in real["plan"]:
        if name != "flow_exhaust" or not label.split("|")[2].endswith("pts20-r1"):
            continue
        tf, q, inst = int(params["tf"]), float(params["q"]), params["sess"]
        memo = {iso: {} for iso in DAYS}
        calls = [(e[2], e[3]) for e in real["log"] if e[0] == "signal" and e[1] == label]
        asked = [(e[2], e[3], e[4]) for e in real["log"] if e[0] == "allowed" and e[1] == label]
        want = []
        for iso, T in calls:
            side = d5_real(real["tabs"][iso], real["tapes"][iso], iso, T, tf, q, INSTANCE[inst], memo[iso])
            if side:
                want.append((iso, T, side))
        assert asked == want, label
        n_dec, n_sig, sides = n_dec + len(calls), n_sig + len(want), sides | {x[2] for x in want}
        assert inst != "eve" or all(T < S.et_ns(dt.date.fromisoformat(iso), "00:00") for iso, T in calls)
    assert n_dec > 10000 and n_sig >= 30 and sides == {"long", "short"}


def test_real_days_d1_signals_at_every_decision_equal_the_z_score_oracle_by_row_stamp(real):
    n_dec = n_sig = 0
    for label, name, _, (cls, params) in real["plan"]:
        if name != "bimb_follow_d1" or not label.split("|")[2].endswith("pts20-r1"):
            continue
        for iso in DAYS:
            tab = real["tabs"][iso]
            tb = {"stamp": tab["t_utc"] * NS, "book_ok": tab["book_ok"], "imb10": tab["imb10"]}
            calls = [e[3] for e in real["log"] if e[0] == "signal" and e[1] == label and e[2] == iso]
            asked = [(e[3], e[4]) for e in real["log"] if e[0] == "allowed" and e[1] == label and e[2] == iso]
            want = [(T, TB.bimb_oracle(tb, "imb10", T, 1, float(params["k"]))) for T in calls]
            assert asked == [(T, sd) for T, sd in want if sd], (label, iso)
            assert all(T % (5 * MIN) == 0 for T in calls)
            n_dec, n_sig = n_dec + len(calls), n_sig + len(asked)
    assert n_dec > 3000 and n_sig >= 30


def test_the_module_reads_features_through_ctx_feat_only():
    """Source check: families/l2ideas.py never reaches around ctx (no data-layer import, no raw table, no row clock)."""
    from pathlib import Path
    src = Path(L2.__file__).read_text()
    for banned in ("._feat", "l2data", "usable_ns", ".cols", "load_features", "read_parquet", "open("):
        assert banned not in src, banned
    assert "ctx.feat" not in src.split('"""', 2)[2]             # no read of its own: D1 / D5 read through the screen families' helpers
    assert D1.fam_signal is B.BimbFollow.fam_signal and issubclass(D5, F._Flow)
    assert D5._on_time is F._Flow._on_time and D5._delta is F._Flow._delta and D5._bars is F._Flow._bars


# ---- garbage after a cut -----------------------------------------------------------------------------------------------------
CUTS = {"day": "10:15:23", "open": "09:30:23", "eve": "20:00:07"}       # seconds after a 1- / 5-minute close, a 09:30 and a 20:00 arm


def cut_of(iso: str, mode: str) -> int:
    d = dt.date.fromisoformat(iso)
    return S.et_ns(d - dt.timedelta(days=1) if mode == "eve" else d, CUTS[mode])


def garbled_tape(t: S.Tape, cut: int, seed: int) -> S.Tape:
    """The same print times; every print at / after the cut is a wild walk 150 points away, with junk sizes."""
    late = t.ts >= cut
    px, size = t.px.copy(), t.size.copy()
    n = int(late.sum())
    if n:
        rng = np.random.default_rng(seed)
        anchor = float(px[~late][-1]) if n < len(px) else float(px[0])
        px[late] = np.round((anchor + 150.0) * 4) / 4 + 0.25 * np.cumsum(rng.integers(-60, 61, n))
        size[late] = 7
    return S.Tape(t.root, t.date, t.contract, t.ts, px, size)


class Garbled:
    """`features=` loader: the real slice with every row that is NOT usable at the day's cut replaced by tempting garbage
    (a lopsided book, thin depth on both sides, a huge one-sided delta, book_ok True); the clock tags are left alone, so
    a decision that read one row too far would act on it."""

    def __init__(self, inner, mode: str):
        self.inner, self.columns, self.mode = inner, inner.columns, mode

    def __call__(self, d):
        f = self.inner(d)
        if f is None:
            return None
        late = f.usable_ns > cut_of(d.isoformat(), self.mode)
        n = int(late.sum())
        rng = np.random.default_rng(d.toordinal())
        cols = {k: v.copy() for k, v in f.cols.items()}
        flip = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
        cols["imb10"][late] = 0.9 * np.where(rng.random(n) < 0.5, 1.0, -1.0)
        cols["bid10_rel15"][late] = -0.6
        cols["ask10_rel15"][late] = -0.6
        cols["f_delta"][late] = 50000.0 * flip
        cols["book_ok"][late] = True
        return S.Features(f.usable_ns, cols)


ENTRY_SIDE = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ms", "entry_ns", "oco")


@pytest.mark.parametrize("mode", sorted(CUTS))
def test_real_days_with_everything_after_a_cut_replaced_by_garbage_no_earlier_decision_or_trade_changes(real, mode, monkeypatch):
    """NO LOOK-AHEAD on real BUILD days, every family of PLAN (D1, D5, the bases and their stage D variants) in one pass.
    The cut sits seconds after decisions: 10:15:23 ET (a 1- and 5-minute close), 09:30:23 (the 09:30 brackets) and 20:00:07
    the evening before (the 20:00 bracket), so the row a one-minute peek would read is already garbage. Prints at / after
    the cut and rows not usable at the cut are garbage. Unchanged: every spy record up to the cut (entry verdicts, the
    verdict a resting bracket got at every minute close, the brackets, the state each signal saw, the book-exit counter and
    whether it was armed), every trade closed before the cut (all fields, the stage D verdict tag included), the entry side
    of every trade open at the cut."""
    cuts = {iso: cut_of(iso, mode) for iso in DAYS}
    monkeypatch.setattr(S, "load_tape", lambda d, root="NQ", allow_holdout=False, allow_exam=False:
                        garbled_tape(real["tapes"][d.isoformat()], cuts[d.isoformat()], d.toordinal()))
    res, log = one_pass(real["plan"], Garbled(real["loader"], mode))
    before = lambda e: e[3] <= cuts[e[2]]                                         # noqa: E731
    ref_log, got_log = [e for e in real["log"] if before(e)], [e for e in log if before(e)]
    assert got_log == ref_log and len(ref_log) > (200 if mode == "eve" else 2000)
    assert {e[0] for e in ref_log} == {"allowed", "verdict", "arm", "signal", "xbook"}
    changed = n_closed = n_open = 0
    for label, r in res.items():
        a, b = real["res"][label]["trades"], r["trades"]

        def closed(tr):
            return [{k: v for k, v in t.items() if k != "both_sides"} for t in tr if t["exit_ns"] < cuts[t["date"]]]

        def still_open(tr):
            return [{k: t[k] for k in ENTRY_SIDE} for t in tr if t["entry_ns"] < cuts[t["date"]] <= t["exit_ns"]]
        assert closed(b) == closed(a), label
        assert still_open(b) == still_open(a), label
        n_closed, n_open, changed = n_closed + len(closed(a)), n_open + len(still_open(a)), changed + (a != b)
        assert r["skipped_by_error"] == 0
    assert n_closed > (10 if mode == "eve" else 100) and n_open > 0
    assert changed > 0 and log != real["log"]                                     # the garbage does change what comes after


def test_the_garbage_comparison_catches_a_table_that_leaks_one_minute(real, monkeypatch):
    """Power: the same comparison on a table whose rows are usable ONE MINUTE EARLY (row M shows at M instead of M + 60 s)
    must not pass -- the families' freshness guard then refuses the leaked rows, so verdicts and signals change."""
    class Leak:
        def __init__(self, inner):
            self.inner, self.columns = inner, inner.columns

        def __call__(self, d):
            f = self.inner(d)
            return None if f is None else S.Features(f.usable_ns - MIN, f.cols)
    res, log = one_pass(real["plan"], Leak(real["loader"]))
    assert [e for e in log if e[0] == "allowed"] != [e for e in real["log"] if e[0] == "allowed"]
    for label, name, opt, _ in real["plan"]:
        if set(opt) & {"f_book", "f_thin"} or name in ("bimb_follow_d1", "flow_exhaust"):
            assert L2.kept(res[label]["trades"]) == [], label                     # a leaked row is never acted on


# ================================================================================================================================
# 6. the same trades at 1 and at 8 workers
# ================================================================================================================================

def test_identical_trades_at_1_and_8_workers_for_d1_d5_and_the_stage_d_variants():
    """Every family of PLAN as the Run stage runs it (registered classes, sess all / pre / eve) on 8 BUILD days: one
    process and W processes give the same trades, field for field. Worker processes import the classes by name."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    plan = plan_specs(spied=False)
    specs = [x[3] for x in plan]
    try:
        a = S.run_many(specs, days=DAYS[:8], workers=1, features=S.L2Features(COLS))
        b = S.run_many(specs, days=DAYS[:8], workers=W, features=S.L2Features(COLS))
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    n = 0
    for x, ra, rb in zip(plan, a, b):
        assert ra["skipped_by_error"] == 0 and rb["skipped_by_error"] == 0, (x[0], ra["no_trade"][:2], rb["no_trade"][:2])
        assert ra["trades"] == rb["trades"], x[0]
        assert ra["sessions"] == rb["sessions"] == 8 and ra["both_sides_sessions"] == rb["both_sides_sessions"]
        assert ra["meta"]["workers"] == 1 and rb["meta"]["workers"] == W
        n += len(ra["trades"])
    assert n > 500
    for name in ("bimb_follow_d1", "flow_exhaust"):                               # declared one direction: the simulator agrees
        for x, ra in zip(plan, a):
            if x[1] == name:
                assert ra["both_sides_sessions"] == 0 and not any(t["both_sides"] or t["oco"] for t in ra["trades"])


def test_the_registry_worker_parity_test_covers_the_new_families():
    import test_families as TFAM
    assert {("bimb_follow_d1", "5"), ("flow_exhaust", "1"), ("flow_exhaust", "5")} <= set(TFAM.CASES)
    assert all(d < "2024-01-01" for d in TFAM.DAYS)                               # that test runs on BUILD days too


@pytest.mark.parametrize("name,tf", [("bimb_follow_d1", "5"), ("flow_exhaust", "1"), ("flow_exhaust", "5")])
def test_the_run_menus_smoke_of_the_new_families_is_clean_and_counts_only(name, tf):
    """run_menus.py smoke on 5 of the fixed BUILD days: the whole menu grid (3 variants x 32 exit cells, sess all / pre /
    eve), no dropped session, one direction, 1- vs 2-worker parity, the C2 null runs. Counts only."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    try:
        o = RM.smoke(name, "NQ", tf, 5, 1)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    assert o["ok"] and o["cells"] == 96 and o["variants"] == 3 and o["days"] == 5 and o["skipped_by_error"] == 0 and o["errors"] == []
    assert o["worker_parity"] and o["both_sides_ok"] and o["both_sides_sessions"] == 0 and o["both_sides_declared"] is False
    assert o["segments"] == ["eve", "day"] and {"eve", "nyam"} <= set(o["by_session"]) <= set(S.ORDER7) and len(o["by_session"]) >= 4
    assert o["entry_kind"]["resting"] == 0 and o["entry_kind"]["market"] == o["trades_total"] == o["long"] + o["short"] > 0
    assert o["long"] > 0 and o["short"] > 0 and o["cells_without_trades"] == 0 and set(o["by_stop_mode"]) == {"atr", "pts", "pct"}
    assert o["nulls"]["c2"]["skipped_by_error"] == 0 and o["nulls"]["c2"]["trades"] > 0
    blob = __import__("json").dumps(o).lower()
    for word in ("net", "pnl", "gross", "win", "exit_reason", "profit"):
        assert word not in blob, word
