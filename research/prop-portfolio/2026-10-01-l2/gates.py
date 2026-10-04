#!/usr/bin/env python3
"""Gates G1 / G2 / G3 on the approved picks' in-sample tester trade lists (SPEC.md "Gates on approved strategies" and
"Stage A screen"). THE DEFINITIONS ARE PRE-REGISTERED in FAMILIES.md, section "Gates G1 / G2 / G3 on the approved picks"
(written 2026-10-02 00:08 ET, before this file existed) + its addendum "Gates -- bug fixes after verification" (before any
gate run): this module implements exactly that text. Nothing here is a Template family and nothing is in the families registry.

    G1  skip a trade when sign(mean of imb10 over the 5 newest usable minutes) opposes its side      (veto; no signal -> keep)
    G2  keep a trade only when l2sim.depth_regime(depth10_rel20d) == "thin" at its entry             (permit; no signal -> skip)
    G3  size x0.5 / x1 / x1.5 by tercile of a = side * z(imb10, 60 min); terciles from this list's own earlier trades of the
        same session of the day in the trailing 250 calendar sessions                                  (no signal -> x1)

FEATURE ACCESS: only through a real l2sim.Ctx (ctx.feat / ctx.feat_window: the simulator's guarded accessor) whose clock is
`entry_ms * 1e6 - 1 ns`, i.e. a row is visible only when its usable_at lies STRICTLY before the trade's entry. The
simulator's SNAPSHOT-PHASE GUARD applies here as in l2sim.run: the trades of a month that failed the data layer's phase check get the
clock l2sim.EXEC_GUARD_MS (1 s) earlier, and a holdout month without a persisted check raises l2sim.PhaseGuardMissing.
A gate never creates, moves or re-prices a trade: G1 / G2 drop rows, G3 sizes rows.

G3 BUNDLE = the registered half-unit rows (`half_units.json`: 1 / 2 / 3 copies = x0.5 / x1 / x1.5; the ledger's trades / net
count them) + ONE BUNDLE PER SIZE TIER (`x0.5/`, `x1/`, `x1.5/`: each source trade once). A G3 bundle is SCORED AS A
PORTFOLIO OF ITS TIERS at micros u / 2u / 3u (u = half the pick's micros): `cell` returns the member list, `score_cell` /
`lift_cell` run it. The half-unit rows are NOT a scorer input (R's day walk would treat the copies as separate overlapping
trades: a take on copy 1 skips the others), so the G3 directory has no trades.json and score.py refuses it.

PERMUTATION NULL (2 seeds per gate; a CONTROL, never a tradable rule: it is matched to the real gate's full-sample counts
and its donors may be later sessions): the same gate function on score.C2Features(cols, seed) (the feature columns of a
seeded random other session at the same ET minute), then the null's categories are matched to the real gate's counts per
session of the day by moving the minimum number of seeded-random trades (`match_counts`), drawn among the trades whose
verdict rests on evidence in BOTH the real gate and the null (a trade the real gate cannot touch -- masked book, roll
days, no tercile yet -- is moved only when no other is left; `moved_without_basis` counts those).

OUTPUT: runs/gate_<pick>_<G>/ and runs/gate_<pick>_<G>-perms<seed>/ and one 'gate' row each in ledger.csv through
screen.record_gate (6 picks x 3 gates x (1 + 2) = 54 rows against the cap of 400; a batch that would pass the cap is refused
whole). A bundle is built in a temporary directory and moved in place only AFTER its ledger row exists (no uncounted result
on disk); a recorded key whose bundle is missing is rebuilt without a new row. One process, days in order (G3 state crosses
sessions). run.json carries counts only: categories, no-signal trades, entry timing, and how many verdicts change under the
1 s execution guard.

    python gates.py plan                      the job list (nothing runs)
    python gates.py status                    done / pending, cap
    python gates.py run   [--only pick[,pick]] [--gates G1,G2,G3]
    python gates.py guard [--ms 1000] [--only pick[,pick]] [--gates G1,G2,G3]
        ROBUSTNESS (FEATURES.md: the 1 s execution-guard line), stage 'gate_guard', keys gate_<pick>_<G>-guard<ms>[-perms<seed>]:
        the screened gates again with the gate clock <ms> earlier. Not part of the screen, not counted in the cap (no new
        config), refused for a gate that has no 'gate' row yet.
    python gates.py smoke [--days 10] [--only pick[,pick]]
        BUG CHECK on <= 10 fixed in-sample days: COUNTS only (no P&L, no exit reasons), nothing is written.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
import zlib
from bisect import bisect_left
from collections import Counter
from pathlib import Path

import numpy as np

L = Path(__file__).resolve().parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

import l2sim  # noqa: E402

TRADES = L / "trades"
RUNS = L / "runs"
ENGINE = "gates-1 (list gate on an in-sample tester bundle)"
STAGE, GUARD_STAGE = "gate", "gate_guard"       # ledger stages: the screen (counted in the cap) / the execution-guard robustness
GATES = ("G1", "G2", "G3")
FAMILY = {"G1": "gate_G1", "G2": "gate_G2", "G3": "gate_G3"}
NAME = {"G1": "gate_imb_side", "G2": "gate_thin", "G3": "gate_size"}
COLS = {"G1": ("imb10", "t_utc"), "G2": (l2sim.DEPTH_COL, "t_utc"), "G3": ("imb10", "t_utc")}     # every column a gate reads
ORDER = {"G1": ("keep", "skip"), "G2": ("keep", "skip"), "G3": (0.5, 1.0, 1.5)}                   # a gate's categories
TIERS = ((0.5, "x0.5"), (1.0, "x1"), (1.5, "x1.5"))                # G3: multiplier -> tier bundle (sub-directory) name
HALF_UNITS = "half_units.json"                                     # G3: the registered half-unit rows (accounting, not a scorer input)
NULL_SEEDS = (1, 2)
NULL_SEED_BASE = 20261001                       # = score.C2_SEED (asserted in the tests)
DEFAULTS = {"g1_rows": 5,                       # G1: the 5-minute mean (SPEC)
            "z_win": 60, "z_min": 30,           # G3: B1's z-score (trailing 60 minutes, >= 30 finite values)
            "g3_sessions": 250, "g3_min_pop": 60,      # G3: trailing 250 calendar sessions, >= 60 values for a tercile
            "guard_ms": 0}                      # > 0: the gate clock that much earlier (robustness stage 'gate_guard'; never a screen run)
PARAMS = {"G1": ("g1_rows",), "G2": (), "G3": ("z_win", "z_min", "g3_sessions", "g3_min_pop")}

PICKS = {   # pick id -> the exported in-sample tester trade list (trades/<file>.json), score.BASELINE key, tf, the pick's session
    "straddle-tf30_c10": {"file": "R__hm2-straddle-tf30_c10", "key": "hm2-straddle-tf30#10", "tf": "30", "sess": "nyam"},
    "straddle-tf30_c9": {"file": "R__hm2-straddle-tf30_c9", "key": "hm2-straddle-tf30#9", "tf": "30", "sess": "nyam"},
    "straddle-tf30_c32": {"file": "R__hm2-straddle-tf30_c32", "key": "hm2-straddle-tf30#32", "tf": "30", "sess": "pm"},
    "orb-tf5_c10": {"file": "R__hm-orb-tf5_c10", "key": "hm-orb-tf5#10", "tf": "5", "sess": "mid"},
    "donchian-tf15_c10": {"file": "R__fp-donchian-tf15_c10", "key": "fp-donchian-tf15#10", "tf": "15", "sess": "pm"},
    "donchian-tf15_c1": {"file": "R__fp-donchian-tf15_c1", "key": "fp-donchian-tf15#1", "tf": "15", "sess": "nyam"},
}

EXTRA_SLOTS = {   # scoring cells that are not in score.BASELINE / BASELINE_ALT
    # the Apex Legacy 300K PA bar (SCORING.md "Baseline to beat"; out/baseline_insample.json apex300_pa.bar.fresh): the user's
    # five accounts, start state 'fresh' (score_funded's default)
    "apex300_pa": dict(kind="funded", firm="apex300_pa", key="fp-donchian-tf15#1", sess="nyam", micros=100,
                       rules={"day_take": 3000, "day_lock": 3000, "day_stop": 0, "max_day_tr": 0}, policy="max"),
}


def _score():
    import score
    return score


# ------------------------------------------------------------------ the gate clock + the three signals

class _Clock:
    """What l2sim.Ctx needs from a simulator to serve features: the decision time (`now`, ns)."""
    __slots__ = ("root", "date", "tick", "pv", "now")

    def __init__(self, date):
        self.root, self.date, self.now = "NQ", date, 0
        self.pv, self.tick = l2sim.SPECS["NQ"]


def clock_ns(entry_ms: int, guard_ms: int = 0) -> int:
    """The gate's decision time for a trade: 1 ns before the first instant of `entry_ms` (so only rows usable STRICTLY
    before entry_ms are visible), minus an optional execution guard. A negative guard would look ahead: refused."""
    if isinstance(guard_ms, bool) or int(guard_ms) != guard_ms or int(guard_ms) < 0:
        raise l2sim.LookAheadError(f"guard_ms must be an integer >= 0, not {guard_ms!r}")
    return int(entry_ms) * 1_000_000 - 1 - int(guard_ms) * 1_000_000


def _fresh(ctx) -> bool:
    """The newest usable row is the minute that just ended: 0 <= clock - (t_utc + 60 s) < 60 s."""
    t = ctx.feat("t_utc")
    if t is None or t != t:
        return False
    age = ctx.now_ns - (int(t) + 60) * l2sim.NS
    return 0 <= age < l2sim.MIN_NS


def sig_imb5(ctx, p: dict = DEFAULTS):
    """G1 signal: float64 mean of imb10 over the 5 newest usable rows (all finite, consecutive minutes, fresh), else None."""
    n = int(p["g1_rows"])
    if not _fresh(ctx):
        return None
    w, t = ctx.feat_window("imb10", n), ctx.feat_window("t_utc", n)
    if len(w) < n or not np.isfinite(w).all() or int(t[-1]) - int(t[0]) != 60 * (n - 1):
        return None
    return float(np.mean(w.astype(np.float64)))


def sig_depth(ctx, p: dict = DEFAULTS):
    """G2 signal: the B6 regime 'thin' | 'mid' | 'thick' of the newest usable depth10_rel20d row (fresh), else None."""
    if not _fresh(ctx):
        return None
    return l2sim.depth_regime(ctx.feat(l2sim.DEPTH_COL))


def sig_z(ctx, p: dict = DEFAULTS):
    """G3 signal: B1's z-score of the newest usable imb10 row against the finite values of the 60 rows before it that lie
    within the 60 clock minutes before it (>= 30 values, population std > 0), else None."""
    n = int(p["z_win"])
    if not _fresh(ctx):
        return None
    w, t = ctx.feat_window("imb10", n + 1).astype(np.float64), ctx.feat_window("t_utc", n + 1)
    if not len(w) or not np.isfinite(w[-1]):
        return None
    h = w[:-1][np.isfinite(w[:-1]) & (t[:-1] >= t[-1] - 60 * n)]
    if len(h) < int(p["z_min"]):
        return None
    sd = float(h.std())
    if not sd > 0:
        return None
    return float((w[-1] - h.mean()) / sd)


SIGNAL = {"G1": sig_imb5, "G2": sig_depth, "G3": sig_z}


def _params(p: dict | None) -> dict:
    unknown = set(p or {}) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown gate parameters {sorted(unknown)}; the parameters are {sorted(DEFAULTS)}")
    return {**DEFAULTS, **(p or {})}


def check_rows(rows: list, allow_holdout: bool = False) -> None:
    """The contract of a source list: in-sample only (2025+ raises l2sim.HoldoutSealed before any feature is read, unless
    the orchestrator's allow_holdout=True), 1 NQ rows, a known side, `date` = the ET date of entry_ms."""
    for i, r in enumerate(rows):
        l2sim.check_holdout(r["date"], allow_holdout)
        if r["side"] not in l2sim.SIDE:
            raise ValueError(f"row {i}: side {r['side']!r}")
        if float(r.get("qty") or 1) != 1.0:
            raise ValueError(f"row {i}: qty {r.get('qty')!r} (a gate takes the 1 NQ tester rows)")
        if dt.datetime.fromtimestamp(int(r["entry_ms"]) / 1000, l2sim.ET).date().isoformat() != r["date"]:
            raise ValueError(f"row {i}: date {r['date']} is not the ET date of entry_ms")


def exec_guard_months(features, days) -> frozenset:
    """l2sim.run_many's snapshot-phase rule, for a gate (a gate builds its own l2sim.Ctx, so the simulator's runner cannot
    apply it): when the loader reads book columns, the months of `days` (ISO dates) that FAILED the data layer's
    snapshot-phase check (cache/phase_guard.json) -> their trades are judged with the clock l2sim.EXEC_GUARD_MS earlier.
    A holdout month without a persisted check raises l2sim.PhaseGuardMissing. Flow-only / clock-only loaders: no guard."""
    if not l2sim.needs_exec_guard(features):
        return frozenset()
    pg = l2sim.phase_guard()
    days = [str(d)[:10] for d in days]
    unchecked = sorted({d[:7] for d in days if dt.date.fromisoformat(d) >= l2sim.HOLDOUT_START and d[:7] not in pg["checked"]})
    if unchecked:
        raise l2sim.PhaseGuardMissing(f"holdout months {unchecked} have no persisted snapshot-phase check "
                                      f"({l2sim.PHASE_GUARD.name}): build the holdout cache first (the data layer's holdout "
                                      "build runs the phase check and persists the months that need the 1 s guard)")
    return frozenset({d[:7] for d in days} & pg["failed"])


def signals(rows: list, gate: str, features, params: dict | None = None, *, allow_holdout: bool = False) -> list:
    """The gate's signal at every trade's entry (None = no signal), read through l2sim.Ctx only.
    features: a callable date -> l2sim.Features | None (l2sim.L2Features(COLS[gate]), score.C2Features(...), a test table).
    The snapshot-phase guard of l2sim.run applies (`exec_guard_months`)."""
    p = _params(params)
    fn = SIGNAL[gate]
    check_rows(rows, allow_holdout)
    by_day: dict = {}
    for i, r in enumerate(rows):
        by_day.setdefault(r["date"], []).append(i)
    guard = exec_guard_months(features, by_day)
    clock_ns(0, p["guard_ms"])                                    # a negative / fractional / bool guard is refused here
    out = [None] * len(rows)
    for day in sorted(by_day):
        d = dt.date.fromisoformat(day)
        feat = features(d)
        if feat is None:
            continue
        if not isinstance(feat, l2sim.Features):
            raise TypeError(f"features({day}) returned {type(feat).__name__}: a gate reads l2sim.Features through l2sim.Ctx only")
        clock = _Clock(d)
        ctx = l2sim.Ctx(clock, 1, [], feat)
        g = int(p["guard_ms"]) + (l2sim.EXEC_GUARD_MS if day[:7] in guard else 0)
        for i in by_day[day]:
            clock.now = clock_ns(rows[i]["entry_ms"], g)
            out[i] = fn(ctx, p)
    return out


def _calendar(calendar) -> list:
    return sorted(str(d)[:10] for d in (_score().in_sample_sessions() if calendar is None else calendar))


def verdicts(rows: list, gate: str, sig: list, calendar=None, params: dict | None = None) -> tuple:
    """-> (categories, basis). categories: the gate's verdict per trade from its signal (G1 / G2 'keep' | 'skip'; G3 the
    multiplier 0.5 | 1.0 | 1.5). basis[i]: the verdict of trade i rests on evidence (G1 / G2: it has a signal; G3: it has
    a signal AND a tercile population of >= g3_min_pop values); without basis a trade got the gate's no-signal verdict."""
    p = _params(params)
    side = [l2sim.SIDE[r["side"]] for r in rows]
    if gate == "G1":
        return ["skip" if s is not None and sd * s < 0 else "keep" for s, sd in zip(sig, side)], [s is not None for s in sig]
    if gate == "G2":
        return ["keep" if s == "thin" else "skip" for s in sig], [s is not None for s in sig]
    if gate != "G3":
        raise KeyError(gate)
    cal = _calendar(calendar)
    a = [None if s is None else sd * s for s, sd in zip(sig, side)]
    pos = [bisect_left(cal, r["date"]) for r in rows]             # calendar sessions strictly before the trade's date
    sess = [l2sim.session_of(int(r["entry_ms"])) for r in rows]
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["date"], int(rows[i]["entry_ms"]), i))
    hist: dict = {}                                               # session of the day -> ([calendar pos], [a]) of EARLIER dates
    out, basis = [1.0] * len(rows), [False] * len(rows)
    k = 0
    while k < len(order):
        j = k
        while j < len(order) and rows[order[j]]["date"] == rows[order[k]]["date"]:
            j += 1
        day = order[k:j]
        for i in day:
            if a[i] is None or sess[i] is None:
                continue
            hp, ha = hist.get(sess[i], ((), ()))
            pop = ha[bisect_left(hp, pos[i] - int(p["g3_sessions"])):]
            if len(pop) < int(p["g3_min_pop"]):
                continue
            q1, q2 = np.quantile(np.asarray(pop, np.float64), [1.0 / 3.0, 2.0 / 3.0])
            out[i] = 1.5 if a[i] > q2 else (0.5 if a[i] < q1 else 1.0)
            basis[i] = True
        for i in day:                                             # the day's own values join the history only afterwards
            if a[i] is not None and sess[i] is not None:
                hp, ha = hist.setdefault(sess[i], ([], []))
                hp.append(pos[i])
                ha.append(a[i])
        k = j
    return out, basis


def categories(rows: list, gate: str, sig: list, calendar=None, params: dict | None = None) -> list:
    """The gate's verdict per trade from its signal: G1 / G2 'keep' | 'skip'; G3 the multiplier 0.5 | 1.0 | 1.5."""
    return verdicts(rows, gate, sig, calendar, params)[0]


def apply(rows: list, gate: str, cats: list) -> list:
    """The gated ledger. G1 / G2: the kept rows, verbatim. G3: HALF-UNIT rows, each trade repeated 2 x multiplier times
    (+ gate_mult, gate_unit, gate_units; scored through `tier_rows`, never directly). Row order = the source's."""
    if gate in ("G1", "G2"):
        return [dict(r) for r, c in zip(rows, cats) if c == "keep"]
    out = []
    for r, m in zip(rows, cats):
        n = int(round(2 * float(m)))
        out += [{**r, "gate_mult": float(m), "gate_unit": u, "gate_units": n} for u in range(1, n + 1)]
    return out


def tier_rows(trades: list) -> dict:
    """G3 half-unit rows -> {'x0.5': [...], 'x1': [...], 'x1.5': [...]}: every source trade ONCE (its gate_unit == 1 row,
    with gate_mult), in the tier of its multiplier. These are the scorer's inputs (one portfolio member per tier)."""
    out = {name: [] for _, name in TIERS}
    names = dict(TIERS)
    for t in trades:
        if t["gate_unit"] == 1:
            out[names[float(t["gate_mult"])]].append({k: v for k, v in t.items() if k not in ("gate_unit", "gate_units")})
    return out


def strata(rows: list) -> list:
    """Session of the day of every trade (asia / london / nyam / mid / pm / None), the offline split of the scorer."""
    return [l2sim.session_of(int(r["entry_ms"])) for r in rows]


def match_counts(null: list, real: list, strat: list, rng, order: tuple, tie=None, movable=None) -> list:
    """The null's categories with, per stratum, exactly the real gate's count of every category: the surplus of each
    over-represented category (seeded-random trades of it) is handed to the under-represented ones. Minimal: a trade whose
    category has no surplus is never touched. movable[i] False = a trade the gate cannot judge (no verdict basis): the
    surplus is drawn among the movable trades of the category, the others only when those run out."""
    bad = {c for c in list(null) + list(real) if c not in order}
    if bad or len(null) != len(real) or len(null) != len(strat) or (movable is not None and len(movable) != len(null)):
        raise ValueError(f"match_counts: categories {sorted(map(str, bad))} outside {order}, or lists of different length")
    out = list(null)
    groups: dict = {}
    for i, s in enumerate(strat):
        groups.setdefault(s, []).append(i)
    for s in sorted(groups, key=lambda x: (x is None, str(x))):
        idx = sorted(groups[s], key=tie) if tie is not None else groups[s]
        pool, need = [], []
        for c in order:
            have = [i for i in idx if out[i] == c]
            want = sum(1 for i in idx if real[i] == c)
            if len(have) > want:
                k = len(have) - want
                first = have if movable is None else [i for i in have if movable[i]]
                take = rng.choice(len(first), size=min(k, len(first)), replace=False)
                pool += [first[j] for j in sorted(take.tolist())]
                if k > len(first):                                # not enough judged trades: the rest comes from the others
                    rest = [i for i in have if not movable[i]]
                    take = rng.choice(len(rest), size=k - len(first), replace=False)
                    pool += [rest[j] for j in sorted(take.tolist())]
            elif len(have) < want:
                need += [c] * (want - len(have))
        pool = [pool[j] for j in rng.permutation(len(pool)).tolist()]
        for i, c in zip(pool, need):
            out[i] = c
    return out


def null_rng(key: str, seed: int):
    return np.random.default_rng([NULL_SEED_BASE, int(seed), zlib.crc32(key.encode())])


def _counts(rows: list, gate: str, sig: list, cats: list, basis: list, trades: list, guard: frozenset) -> dict:
    st = strata(rows)
    return {"source_trades": len(rows), "rows": len(trades), "no_signal": sum(s is None for s in sig), "basis": sum(map(bool, basis)),
            "cats": {str(c): sum(1 for x in cats if x == c) for c in ORDER[gate]},
            "rows_by_session": dict(sorted(Counter(str(s) for s in strata(trades)).items())),
            "cats_by_session": {str(s): {str(c): sum(1 for x, y in zip(cats, st) if x == c and y == s) for c in ORDER[gate]}
                                for s in sorted(set(st), key=lambda x: (x is None, str(x)))},
            "exec_guard": ({"ms": l2sim.EXEC_GUARD_MS, "months": sorted(guard), "trades": sum(r["date"][:7] in guard for r in rows)}
                           if guard else None)}


def run_gate(rows: list, gate: str, features, *, calendar=None, params: dict | None = None) -> dict:
    """One gate on one trade list -> {"trades", "cats", "sig", "basis", "counts"}."""
    sig = signals(rows, gate, features, params)
    cats, basis = verdicts(rows, gate, sig, calendar, params)
    trades = apply(rows, gate, cats)
    guard = exec_guard_months(features, {r["date"] for r in rows})
    return {"trades": trades, "cats": cats, "sig": sig, "basis": basis, "counts": _counts(rows, gate, sig, cats, basis, trades, guard)}


def run_null(rows: list, gate: str, features, real: dict, *, key: str, seed: int, calendar=None, params: dict | None = None) -> dict:
    """The permutation null of `real` (a run_gate result of the same rows): the same gate on the null features, then the
    categories matched to the real gate's counts per session of the day; the trades moved for that are drawn among those
    with a verdict basis in both the real gate and the null."""
    sig = signals(rows, gate, features, params)
    raw, basis = verdicts(rows, gate, sig, calendar, params)
    movable = [bool(a and b) for a, b in zip(real["basis"], basis)]
    cats = match_counts(raw, real["cats"], strata(rows), null_rng(key, seed), ORDER[gate],
                        tie=lambda i: (int(rows[i]["entry_ms"]), i), movable=movable)
    trades = apply(rows, gate, cats)
    guard = exec_guard_months(features, {r["date"] for r in rows})
    out = {"trades": trades, "cats": cats, "sig": sig, "basis": basis, "counts": _counts(rows, gate, sig, cats, basis, trades, guard)}
    out["counts"]["moved_to_match"] = sum(1 for x, y in zip(raw, cats) if x != y)
    out["counts"]["moved_without_basis"] = sum(1 for x, y, m in zip(raw, cats, movable) if x != y and not m)
    out["counts"]["same_verdict_as_real"] = sum(1 for x, y in zip(cats, real["cats"]) if x == y)
    return out


# ------------------------------------------------------------------ diagnostics (counts only)

def entry_timing(rows: list, tf=None) -> dict:
    """Where the entries sit on the clock (counts; no feature, no outcome is read).
    `under_1s_after_minute`: fills 1 ms .. 1000 ms after a minute boundary -- the row the gate reads became usable at most 1 s
    before the fill (a clock 1 s earlier does not see it): a live veto cannot act on it (FEATURES.md: report the 1 s guard).
    `market_over_60s_after_bar`: market entries that fill MORE than 60 s after the last tf-bar boundary -- assuming the order
    was sent at that bar close, the gate (clock = the fill) read a row that became usable after the decision."""
    out = {"under_1s_after_minute": sum(0 < int(r["entry_ms"]) % 60_000 <= 1000 for r in rows),
           "market_entries": sum(r.get("order_price") is None for r in rows)}
    if tf:
        bar = int(tf) * 60_000
        out["market_over_60s_after_bar"] = sum(r.get("order_price") is None and int(r["entry_ms"]) % bar > 60_000 for r in rows)
    return out


def guard_check(rows: list, gate: str, features, cats: list, *, calendar=None, params: dict | None = None,
                guard_ms: int = l2sim.EXEC_GUARD_MS) -> dict:
    """How many verdicts of the gate change when its clock is `guard_ms` earlier (the 1 s execution guard): a COUNT, no
    trade list and no P&L. The full robustness re-run is the 'gate_guard' stage (`python gates.py guard`)."""
    p = {**(params or {}), "guard_ms": int(_params(params)["guard_ms"]) + int(guard_ms)}
    sig = signals(rows, gate, features, p)
    other = categories(rows, gate, sig, calendar, p)
    return {"guard_ms": p["guard_ms"], "verdicts_changed": sum(x != y for x, y in zip(other, cats)), "no_signal": sum(s is None for s in sig)}


# ------------------------------------------------------------------ picks, keys, scoring cells

def pick_rows(pick: str, trades_dir=None) -> tuple:
    """-> (rows, sha256 of the file). The exported in-sample tester trade list of a pick, read-only."""
    p = (Path(trades_dir) if trades_dir is not None else TRADES) / (PICKS[pick]["file"] + ".json")
    raw = p.read_bytes()
    rows = json.loads(raw)
    return (rows if isinstance(rows, list) else rows.get("trades", [])), hashlib.sha256(raw).hexdigest()


def gate_key(pick: str, gate: str, seed=None, guard_ms: int = 0) -> str:
    """Run key = bundle directory under runs/ = ledger key."""
    return f"gate_{pick}_{gate}" + (f"-guard{int(guard_ms)}" if guard_ms else "") + (f"-perms{int(seed)}" if seed else "")


def slots(pick: str) -> dict:
    """The scoring cells that use this pick's trade list: name -> cell. The approved cells (score.BASELINE / BASELINE_ALT)
    in their order, then EXTRA_SLOTS (the Apex 300K PA bar)."""
    S = _score()
    return {n: dict(b) for n, b in {**S.BASELINE, **S.BASELINE_ALT, **EXTRA_SLOTS}.items() if b["key"] == PICKS[pick]["key"]}


def _cap(b: dict) -> int:
    """The firm's micro limit for a cell: the eval firm's cap, or the funded spec's cap -- for an Apex PA its HALF-SIZE limit
    (in force until the safety net: a larger tier would be cut there)."""
    S = _score()
    if b["kind"] == "eval":
        return int(S._firm(b["firm"]).cap)
    sp = S.funded_spec(b["firm"])
    return int(min(sp.cap, getattr(sp, "half", None) or sp.cap))


def _members(bundle: Path, key: str, sess, unit: int, tiers=None) -> list:
    """The tier portfolio of a G3 bundle: one member per size tier at unit x (1, 2, 3) micros. tiers: the tier names to
    include; default = the tier bundles on disk when the G3 bundle exists (an empty tier has none), else all three."""
    if tiers is None:
        tiers = [n for _, n in TIERS if not bundle.exists() or (bundle / n / "trades.json").exists()]
    return [{"src": str(bundle / n), "sess": sess, "micros": int(round(2 * m)) * unit, "label": f"{key}|{n}"}
            for m, n in TIERS if n in tiers]


def cell(pick: str, gate: str, slot: str | None = None, runs_dir=None, *, unit: int | None = None, guard_ms: int = 0,
         tiers=None, trades_dir=None) -> dict:
    """How to score a gate against its pick at one of the pick's cells (`slots`; default the first):
        real, nulls   the `trades` argument of score.score_eval / score.score_funded for the gated bundle and its permutation
                      nulls. G1 / G2: the bundle directory. G3: a MEMBER LIST, one member per size tier (x0.5, x1, x1.5) at
                      micros u / 2u / 3u, u = `unit` (default half the pick's micros) -- the sized position, one row per trade
        gate_kw       the keyword arguments for them (firm, rules, sess, policy ...; `micros` for G1 / G2 only: G3 members
                      carry their own)
        base, base_kw the ungated pick at its cell (the bar)
    G3 also: unit, tier_micros, cap (the firm's micro limit; an Apex PA's half-size limit), cap_ok (3u <= cap), unit_cap (the
    largest cap-compliant unit), and base_same_size_kw (the pick at 2u micros = an all-x1 G3) when that differs from the cell's micros.
    `score_cell` / `lift_cell` run the calls. guard_ms: the cell of the 'gate_guard' robustness bundles."""
    S = _score()
    sl = slots(pick)
    name = slot or next(iter(sl))
    b = sl[name]
    runs = Path(runs_dir) if runs_dir is not None else RUNS
    meta = dict(S.BASELINE_META.get(PICKS[pick]["key"], {}))
    kw = {"firm": b["firm"], "rules": dict(b["rules"]), "sess": b["sess"]}
    if b["kind"] == "funded":
        kw.update(policy=b["policy"], **meta)
    f = PICKS[pick]["file"]
    keys = [gate_key(pick, gate, s, guard_ms) for s in (None,) + NULL_SEEDS]
    out = {"slot": name, "kind": b["kind"], "base": "file:" + f if trades_dir is None else str(Path(trades_dir) / (f + ".json")),
           "base_kw": {**kw, "micros": b["micros"]}, "pick_meta": meta, "warnings": []}
    if gate != "G3":
        out.update(real=str(runs / keys[0]), nulls=[str(runs / k) for k in keys[1:]], gate_kw={**kw, "micros": b["micros"]})
        return out
    u = b["micros"] // 2 if unit is None else int(unit)
    if u < 1:
        raise ValueError(f"G3 unit {u!r}: the half-unit micros must be an integer >= 1")
    cap = _cap(b)
    real, *nulls = [_members(runs / k, k, b["sess"], u, tiers) for k in keys]
    out.update(real=real, nulls=nulls, gate_kw=dict(kw), unit=u, tier_micros={n: int(round(2 * m)) * u for m, n in TIERS},
               cap=cap, cap_ok=3 * u <= cap, unit_cap=cap // 3)
    if 2 * u != b["micros"]:
        out["base_same_size_kw"] = {**kw, "micros": 2 * u}
        out["warnings"].append(f"unit {u}: an all-x1 G3 is the pick at {2 * u} micros, not at the cell's {b['micros']} "
                               "(base_same_size_kw is the size-neutral reference)")
    if not out["cap_ok"]:
        out["warnings"].append(f"the x1.5 tier is {3 * u} micros, over the {b['firm']} limit of {cap}: the scorer would clip it "
                               f"(x1.5 = x1); the cap-compliant cell is unit={cap // 3}")
    out["warnings"].append("G3 is a tier portfolio: the lift over its permutation nulls is gates.lift_cell (score.lift_vs_control "
                           "takes one source); a C1 control would need the same three tiers")
    return out


def _cell_checked(pick, gate, slot, over_cap, kw) -> dict:
    c = cell(pick, gate, slot, **kw)
    if gate == "G3" and not c["cap_ok"] and not over_cap:
        raise ValueError(f"{pick} G3 at {c['slot']}: tiers {c['tier_micros']} pass the firm limit of {c['cap']} micros; "
                         f"score the cap-compliant cell (unit={c['unit_cap']}) or pass over_cap=True (the scorer clips x1.5)")
    return c


def score_cell(pick: str, gate: str, slot: str | None = None, which="real", *, over_cap: bool = False, runs_dir=None,
               unit: int | None = None, guard_ms: int = 0, trades_dir=None, **score_kw) -> dict:
    """score.score_eval / score.score_funded of one side of a cell. which: 'real' (the gated bundle) | 'base' (the ungated
    pick at its cell) | 'base_same_size' (the pick at an all-x1 G3's micros) | 1 | 2 (the permutation null of that seed).
    A G3 cell over the firm's micro limit is refused unless over_cap=True."""
    S = _score()
    c = _cell_checked(pick, gate, slot, over_cap or str(which).startswith("base"),
                      dict(runs_dir=runs_dir, unit=unit, guard_ms=guard_ms, trades_dir=trades_dir))
    if which == "base":
        src, kw = c["base"], c["base_kw"]
    elif which == "base_same_size":
        src, kw = c["base"], c.get("base_same_size_kw", c["base_kw"])
    elif which == "real":
        src, kw = c["real"], c["gate_kw"]
    else:
        src, kw = c["nulls"][NULL_SEEDS.index(int(which))], c["gate_kw"]
    return (S.score_eval if c["kind"] == "eval" else S.score_funded)(src, **kw, **score_kw)


def _lift_direct(kind: str, real, nulls: list, kw: dict, boots: int = 2000) -> dict:
    """score.lift_vs_control(mode='direct') for sources it does not take (member lists): the same paired differences, from
    score.score_eval / score_funded results at identical arguments. (Equal to lift_vs_control on single sources: tested.)"""
    S = _score()
    info = {"mode": "direct", "K": len(nulls), "kind": kind}
    if kind == "eval":
        r = S.score_eval(real, **kw, boots=0, arrays=True)
        cs = [S.score_eval(n, **kw, boots=0, arrays=True) for n in nulls]
        if "arrays" not in r or any("arrays" not in c for c in cs):
            return {**info, "firm": kw["firm"], "skipped": "the gate or a null has no trades on the calendar"}
        if any(c["window"] != r["window"] for c in cs):
            raise ValueError("a null covers a different span than the gate (bundle run ranges differ)")
        out = {**info, "firm": kw["firm"], "model": r["model"], "primary": r["primary"], "ctrl_trades": [c["n_trades"] for c in cs],
               "real_trades": r["n_trades"], "models": {}}
        for b in S.MODELS:
            ro, rd = r["arrays"][b]
            c = np.mean(np.stack([x["arrays"][b][0] == 1 for x in cs]), 0)
            diff = (ro == 1).astype(float) - c
            cp5 = [float((x["arrays"][b][0] == 1).mean()) for x in cs]
            o = {"real_p5": float((ro == 1).mean()), "ctrl_p5": float(c.mean()), "ctrl_p5_sd": float(np.std(cp5)), "lift": float(diff.mean()),
                 "ci": S.E.block_ci([diff], boots=boots)[0] if boots else [None, None], "ctrl_p5_each": cp5,
                 "real_bust5": float((ro == 2).mean()), "ctrl_bust5": float(np.mean([(x["arrays"][b][0] == 2).mean() for x in cs]))}
            for k in range(1, S.H_EVAL + 1):
                o[f"lift_p{k}"] = float(((ro == 1) & (rd <= k)).mean()
                                        - np.mean([((x["arrays"][b][0] == 1) & (x["arrays"][b][1] <= k)).mean() for x in cs]))
            out["models"][b] = o
        out.update(out["models"][out["model"]])
        out["walk"] = {"real": r["walk"], "nulls": [c["walk"] for c in cs]}
        out["lift_gt0"] = bool(out["lift"] > 0)
        return out
    r = S.score_funded(real, **kw, boots=0)
    cs = [S.score_funded(n, **kw, boots=0) for n in nulls]
    if "models" not in r or any("models" not in c for c in cs):
        return {**info, "variant": r.get("variant"), "skipped": r.get("skipped") or "a null's window is too short"}
    if any(c["window"] != r["window"] for c in cs):
        raise ValueError("a null covers a different span than the gate (bundle run ranges differ)")
    out = {**info, "variant": r["variant"], "model": r["model"], "primary": r["primary"], "policy": r["policy"], "start": r["start"],
           "ctrl_trades": [c["trades"] for c in cs], "real_trades": r["trades"], "models": {}}
    for b in r["models"]:
        ce = np.array([[c["models"][b]["e_net_40"], c["models"][b]["p_pay_40"], c["models"][b]["p_pay_20"], c["models"][b]["p_bust_pre_first"]]
                       for c in cs])
        out["models"][b] = {"real_e40": r["models"][b]["e_net_40"], "ctrl_e40": float(ce[:, 0].mean()),
                            "ctrl_e40_sd": float(ce[:, 0].std(ddof=1)) if len(ce) > 1 else None, "ctrl_p40": float(ce[:, 1].mean()),
                            "ctrl_p20": float(ce[:, 2].mean()), "ctrl_bust_pre": float(ce[:, 3].mean()),
                            "lift_e40": float(r["models"][b]["e_net_40"] - ce[:, 0].mean()), "ctrl_e40_each": ce[:, 0].tolist()}
    out.update(out["models"][out["model"]])
    out["lift"] = out["lift_e40"]
    out["lift_gt0"] = bool(out["lift"] > 0)
    return out


def lift_cell(pick: str, gate: str, slot: str | None = None, *, over_cap: bool = False, boots: int = 2000, runs_dir=None,
              unit: int | None = None, guard_ms: int = 0, trades_dir=None) -> dict:
    """Lift of a gate over its permutation nulls at a cell, identical micros + rules on both sides (the like-for-like control
    of a gate). G1 / G2: score.lift_vs_control(real, nulls, mode='direct'). G3: the same paired difference on the tier
    portfolios (`_lift_direct`). -> lift_vs_control's result ('lift', 'lift_gt0', 'ci' (eval), 'models', ...)."""
    c = _cell_checked(pick, gate, slot, over_cap, dict(runs_dir=runs_dir, unit=unit, guard_ms=guard_ms, trades_dir=trades_dir))
    kw = c["gate_kw"]
    if gate == "G3":
        return _lift_direct(c["kind"], c["real"], c["nulls"], kw, boots)
    extra = {"policy": kw["policy"]} if c["kind"] == "funded" else {}
    return _score().lift_vs_control(c["real"], c["nulls"], kw["firm"], kw["rules"], micros=kw["micros"], sess=kw["sess"], mode="direct",
                                    kind=c["kind"], boots=boots, **extra)


# ------------------------------------------------------------------ bundles + ledger

def _features(gate: str, seed=None):
    if not seed:
        return l2sim.L2Features(COLS[gate])
    return _score().C2Features(COLS[gate], seed=int(seed))


def write_bundle(out_dir, key: str, trades: list, meta: dict, half_units: bool | None = None) -> Path:
    """One gate bundle. G1 / G2 (and any plain list): trades.json + run.json (score.py reads the directory).
    G3 (half_units; default: the rows carry gate_unit): half_units.json (the registered rows; NOT a scorer input) + run.json
    + one scorer bundle per non-empty size tier (x0.5/ x1/ x1.5/: trades.json + run.json, each trade once). No trades.json at
    the top: score.py cannot read the half-unit rows by accident."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    half = any("gate_unit" in t for t in trades) if half_units is None else bool(half_units)
    rng = {"start": l2sim.IN_SAMPLE[0].isoformat(), "end": l2sim.IN_SAMPLE[1].isoformat(), "holdout": False}
    run = {"id": key, "engine": ENGINE, "range": rng, "holdout": False, "qty": 1, "trades": len(trades),
           "net": round(sum(float(t["net"]) for t in trades), 2), **meta}
    if half:
        tr = tier_rows(trades)
        run["tiers"] = {n: len(v) for n, v in tr.items()}
        run["score_with"] = "gates.cell / gates.score_cell / gates.lift_cell (a portfolio of the tier bundles); never half_units.json"
        for (m, n) in TIERS:
            if tr[n]:
                (out / n).mkdir(exist_ok=True)
                (out / n / "trades.json").write_text(json.dumps(tr[n], separators=(",", ":")))
                (out / n / "run.json").write_text(json.dumps({"id": f"{key}/{n}", "engine": ENGINE, "range": rng, "holdout": False,
                                                              "qty": 1, "trades": len(tr[n]), "tier": n, "gate_mult": m,
                                                              "parent": key}, indent=1))
    (out / (HALF_UNITS if half else "trades.json")).write_text(json.dumps(trades, separators=(",", ":")))
    (out / "run.json").write_text(json.dumps(run, indent=1))
    return out


def _complete(d: Path) -> bool:
    return (d / "run.json").exists() and ((d / "trades.json").exists() or (d / HALF_UNITS).exists())


def _publish(runs: Path, key: str, trades: list, meta: dict, record=None) -> None:
    """Build the bundle in a temporary directory, call `record` (the ledger row), then move it in place. A failing record
    leaves nothing on disk; a crash after it leaves a recorded key without a bundle, which run_all rebuilds."""
    if not key.startswith("gate_"):
        raise ValueError(f"not a gate key: {key!r}")
    runs.mkdir(parents=True, exist_ok=True)
    tmp = runs / f".{key}.tmp-{os.getpid()}"
    for old in runs.glob(f".{key}.tmp-*"):
        shutil.rmtree(old, ignore_errors=True)
    try:
        write_bundle(tmp, key, trades, meta)
        if record is not None:
            record()
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    final = runs / key
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp, final)


def jobs(only=None, gates=None, guard_ms: int = 0) -> list:
    """The job list in run order: per pick x gate the real gate, then its permutation nulls."""
    gs = tuple(gates or GATES)
    bad = [g for g in gs if g not in GATES] + [p for p in (only or []) if p not in PICKS]
    if bad:
        raise KeyError(f"unknown gate / pick {bad}; gates {GATES}, picks {sorted(PICKS)}")
    return [{"key": gate_key(p, g, s, guard_ms), "pick": p, "gate": g, "control": "perm" if s else "", "seed": s or ""}
            for p in PICKS if not only or p in only for g in gs for s in (None,) + NULL_SEEDS]


def _inputs(pick: str, gate: str, params: dict) -> dict:
    return {"pick": pick, "source": PICKS[pick]["file"], "gate": gate, "name": NAME[gate], "guard_ms": params["guard_ms"],
            **{k: params[k] for k in PARAMS[gate]},
            **({"rows": "half_units (scored as a tier portfolio: gates.cell)"} if gate == "G3" else {})}


def run_all(only=None, gates=None, *, guard_ms: int = 0, runs_dir=None, ledger=None, cap=None, log=None, trades_dir=None,
            features=None, calendar=None) -> dict:
    """Run every pending gate job on the WHOLE in-sample trade lists and record it (one ledger row, then the bundle).
    guard_ms = 0: THE SCREEN (stage 'gate', counted). Idempotent by key; the whole batch is refused (screen.CapExceeded,
    nothing runs) when used + pending would pass the cap. guard_ms > 0: the execution-guard robustness re-run (stage
    'gate_guard', keys ...-guard<ms>..., not counted), only for gates whose screen row exists.
    A key that is already in the ledger is recomputed only in memory (a null needs its real gate) and must reproduce the
    recorded row count: a different count means the definitions drifted after the first run -> RuntimeError; its bundle is
    rebuilt when it is missing (a crash between the row and the bundle).
    features: (gate, seed | None) -> loader, default l2sim.L2Features / score.C2Features.
    -> {"ran", "skipped", "restored"}."""
    import screen
    cap = screen.CAP if cap is None else cap
    feats = features or _features
    runs = Path(runs_dir) if runs_dir is not None else RUNS
    p = _params({"guard_ms": guard_ms})
    clock_ns(0, p["guard_ms"])                                      # a negative / fractional guard is refused before anything runs
    g_ms = int(p["guard_ms"])
    stage = GUARD_STAGE if g_ms else STAGE
    prm = {"guard_ms": g_ms} if g_ms else None
    plan = jobs(only, gates, g_ms)
    led = screen.read_ledger(ledger)
    done = {r["key"]: r for r in led if r["stage"] == stage}
    todo = [j for j in plan if j["key"] not in done]
    out = {"ran": [], "skipped": [j["key"] for j in plan if j["key"] in done], "restored": []}
    if stage == STAGE:
        used = screen.cap_used(led)
        if used + len(todo) > cap:
            screen._log(f"REFUSED: {len(todo)} pending gate runs + {used} used would pass the cap of {cap} screening runs; nothing was run", log)
            raise screen.CapExceeded(f"{used} used + {len(todo)} pending > cap {cap}")
    else:
        screened = {r["key"] for r in led if r["stage"] == STAGE}
        missing = sorted({gate_key(j["pick"], j["gate"]) for j in todo} - screened)
        if missing:
            raise RuntimeError(f"the execution-guard stage re-runs SCREENED gates only; no 'gate' row yet for {missing}")
    screen._log(f"{stage}: {len(plan)} jobs planned, {len(out['skipped'])} done, {len(todo)} to run", log)
    pend = {j["key"] for j in todo}
    broken = {k for k in done if k in {j["key"] for j in plan} and not _complete(runs / k)}
    for pick in dict.fromkeys(j["pick"] for j in plan if j["key"] in pend | broken):
        l2sim.wait_compute_window()
        rows, sha = pick_rows(pick, trades_dir)
        for gate in dict.fromkeys(j["gate"] for j in plan if j["pick"] == pick and j["key"] in pend | broken):
            t0 = time.monotonic()
            real = run_gate(rows, gate, feats(gate, None), calendar=calendar, params=prm)
            rk = gate_key(pick, gate, None, g_ms)
            res = {rk: (real, "", "", time.monotonic() - t0)}
            for s in NULL_SEEDS:
                k = gate_key(pick, gate, s, g_ms)
                if k in pend | broken:
                    t0 = time.monotonic()
                    res[k] = (run_null(rows, gate, feats(gate, s), real, key=rk, seed=s, calendar=calendar, params=prm),
                              "perm", s, time.monotonic() - t0)
            present = [n for (m, n) in TIERS if real["counts"]["cats"][str(m)]] if gate == "G3" else None
            for k, (r, control, seed, el) in res.items():
                if k in done and str(done[k]["trades"]) != str(len(r["trades"])):
                    raise RuntimeError(f"{k}: the ledger holds {done[k]['trades']} rows, the gate now gives {len(r['trades'])}: "
                                       "the definition or its inputs changed after the first run")
                if k not in pend | broken:
                    continue
                counts = dict(r["counts"])
                if not control:
                    counts["entry_timing"] = entry_timing(rows, PICKS[pick]["tf"])
                    if not g_ms:
                        counts["guard_check"] = guard_check(rows, gate, feats(gate, None), r["cats"], calendar=calendar)
                meta = {"strategy": f"gates.{gate}", "inputs": _inputs(pick, gate, p), "elapsed_s": round(el, 2),
                        "gate": {"gate": gate, "name": NAME[gate], "pick": pick, "pick_key": PICKS[pick]["key"], "tf": PICKS[pick]["tf"],
                                 "pick_sess": PICKS[pick]["sess"], "source": PICKS[pick]["file"], "source_sha256": sha, "stage": stage,
                                 "control": control, "seed": seed, "features": list(COLS[gate]), "counts": counts,
                                 "control_only": bool(control), "half_unit_rows": gate == "G3",
                                 "note": ("a permutation null: matched to the real gate's full-sample counts, donors may be later "
                                          "sessions -- a CONTROL, never a tradable rule" if control else
                                          "list gate: a survivor must be replayed through l2sim as a Template filter"),
                                 "cells": {n: cell(pick, gate, n, runs, guard_ms=g_ms, tiers=present, trades_dir=trades_dir)
                                           for n in slots(pick)}}}
                net = sum(float(t["net"]) for t in r["trades"])
                if k in done:
                    _publish(runs, k, r["trades"], meta)
                    out["restored"].append(k)
                    screen._log(f"{stage} {k}: bundle was missing, rebuilt ({len(r['trades'])} rows, no new ledger row)", log)
                    continue

                def rec():                                          # called by _publish before the bundle is moved in place
                    if stage == STAGE:
                        screen.record_gate(k, FAMILY[gate], meta["inputs"], len(r["trades"]), net, el, tf=PICKS[pick]["tf"],
                                           control=control, seed=seed, path=ledger, cap=cap)
                    else:
                        screen.append_row({"stage": stage, "key": k, "family": FAMILY[gate], "tf": PICKS[pick]["tf"],
                                           "inputs_json": json.dumps(meta["inputs"], sort_keys=True), "control": control, "seed": seed,
                                           "trades": len(r["trades"]), "net": round(net, 2), "elapsed_s": round(el, 2)}, ledger, cap)

                _publish(runs, k, r["trades"], meta, rec)
                out["ran"].append(k)
                screen._log(f"{stage} {k}: {len(r['trades'])} rows of {len(rows)} source trades, {el:.1f} s", log)
    return out


def status(ledger=None) -> dict:
    import screen
    led = screen.read_ledger(ledger)
    done = {r["key"] for r in led if r["stage"] == STAGE}
    plan = jobs()
    return {"planned": len(plan), "done": sum(j["key"] in done for j in plan), "pending": [j["key"] for j in plan if j["key"] not in done],
            "guard_runs": sum(r["stage"] == GUARD_STAGE for r in led),
            "cap": screen.CAP, "cap_used": screen.cap_used(led),
            "cap_after_pending": screen.cap_used(led) + sum(j["key"] not in done for j in plan)}


def smoke(n_days: int = 10, only=None, features=None, trades_dir=None, calendar=None) -> dict:
    """Bug check on the trades of <= 10 fixed in-sample days (screen.SMOKE_DAYS): every gate + its nulls in memory, COUNTS
    only, nothing written. G3 runs with g3_min_pop = 3 here (ten scattered days can never reach 60 values; the screen
    always uses the registered 60) so the tercile code is exercised."""
    import screen
    days = set(screen.SMOKE_DAYS[:max(1, min(int(n_days), len(screen.SMOKE_DAYS)))])
    feats = features or _features
    l2sim.wait_compute_window()
    out = {"days": len(days), "picks": {}}
    ok = True
    for pick in PICKS:
        if only and pick not in only:
            continue
        rows = [r for r in pick_rows(pick, trades_dir)[0] if r["date"] in days]
        o = {"source_trades": len(rows), "days_with_trades": len({r["date"] for r in rows}),
             "entry_kind": {"market": sum(r.get("order_price") is None for r in rows),
                            "resting": sum(r.get("order_price") is not None for r in rows)},
             "entry_timing": entry_timing(rows, PICKS[pick]["tf"])}
        for gate in GATES:
            prm = {"g3_min_pop": 3} if gate == "G3" else None
            real = run_gate(rows, gate, feats(gate, None), calendar=calendar, params=prm)
            again = run_gate(rows, gate, feats(gate, None), calendar=calendar, params=prm)
            g = {"rows": len(real["trades"]), "cats": real["counts"]["cats"], "no_signal": real["counts"]["no_signal"],
                 "basis": real["counts"]["basis"], "deterministic": again["trades"] == real["trades"],
                 "guard1000_changed": guard_check(rows, gate, feats(gate, None), real["cats"], calendar=calendar, params=prm)["verdicts_changed"],
                 "perm": {}}
            if gate == "G3":
                tr = tier_rows(real["trades"])
                g["tiers"] = {n: len(v) for n, v in tr.items()}
                ok &= sum(g["tiers"].values()) == len(rows)
            ok &= g["deterministic"]
            for s in NULL_SEEDS:
                nl = run_null(rows, gate, feats(gate, s), real, key=gate_key(pick, gate), seed=s, calendar=calendar, params=prm)
                same = nl["counts"]["cats_by_session"] == real["counts"]["cats_by_session"]
                g["perm"][str(s)] = {"rows": len(nl["trades"]), "counts_match": same, "moved_to_match": nl["counts"]["moved_to_match"],
                                     "moved_no_basis": nl["counts"]["moved_without_basis"], "no_signal": nl["counts"]["no_signal"]}
                ok &= same and len(nl["trades"]) == len(real["trades"])
            o[gate] = g
        out["picks"][pick] = o
    out["ok"] = bool(ok)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gates.py", description="Gates G1-G3 on the approved picks (see the module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("status")
    for name in ("run", "guard"):
        r = sub.add_parser(name)
        r.add_argument("--only", default="", help="comma list of pick ids")
        r.add_argument("--gates", default="", help="comma list of G1,G2,G3")
        if name == "guard":
            r.add_argument("--ms", type=int, default=l2sim.EXEC_GUARD_MS, help="the gate clock that many ms earlier (default 1000)")
    s = sub.add_parser("smoke")
    s.add_argument("--days", type=int, default=10)
    s.add_argument("--only", default="", help="comma list of pick ids")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        for j in jobs():
            print(j["key"])
        return 0
    if a.cmd == "status":
        st = status()
        print(f"gate jobs planned {st['planned']}  done {st['done']}  pending {len(st['pending'])}  guard re-runs {st['guard_runs']}")
        print(f"cap {st['cap_used']} of {st['cap']} used; after the pending gate runs: {st['cap_after_pending']}")
        return 0
    only = [x for x in a.only.split(",") if x] or None
    if a.cmd == "smoke":
        o = smoke(a.days, only)
        print(json.dumps(o, indent=1))
        return 0 if o["ok"] else 1
    import screen
    if a.cmd == "guard" and a.ms <= 0:
        print("REFUSED: --ms must be > 0 (the screen itself is `gates.py run`)", file=sys.stderr)
        return 2
    try:
        out = run_all(only, [x for x in a.gates.split(",") if x] or None, guard_ms=a.ms if a.cmd == "guard" else 0)
    except screen.CapExceeded as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: len(v) for k, v in out.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
