"""SIM VALIDATION GATE: replay the approved tester strategies on l2sim, in-sample only (2021-09-22 ->
2024-12-31), and compare trade-by-trade with the tester's grid-cell bundles (read-only).

Gate (SPEC): >= 95% identical trades (date, side, entry time +-1 s, entry price, exit price, exit_reason)
and total net within 2%, for each of the three gate configs. Writes SIM_VALIDATION.md + out/sim_validation.json.

Usage: python sim_validate.py [--workers 8] [--no-extra]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l2ref                                    # noqa: E402
import l2sim as S                               # noqa: E402

GRIDS = Path.home() / "ramos-quant-homebase" / "homebase" / ".state" / "tester" / "grids"
START, END = "2021-09-22", "2024-12-31"
# id -> (family, tester in-sample source 'grid#cell', pick's session, role); inputs come from the bundle's run.json
GATE = [
    ("hm2-straddle-tf30#10", "straddle", "20260930-001526-draft_pp_straddle-67c2#10", "nyam", "Flex eval pick"),
    ("hm-orb-tf5#10", "orb", "20260929-231930-draft_pp_orb-5276#10", "mid", "Pro noDLL funded pick"),
    ("fp-donchian-tf15#10", "donchian", "20260930-111627-draft_pp_donchian-cd3c#10", "pm", "Pro DLL funded pick"),
]
EXTRA = [   # the other baseline picks of L/SPEC.md (not part of the gate; same engine, more coverage)
    ("hm2-straddle-tf30#9", "straddle", "20260930-001526-draft_pp_straddle-67c2#9", "nyam", "Pro noDLL eval pick"),
    ("hm2-straddle-tf30#32", "straddle", "20260930-001526-draft_pp_straddle-67c2#32", "pm", "Flex funded pick"),
    ("fp-donchian-tf15#1", "donchian", "20260930-111627-draft_pp_donchian-cd3c#1", "nyam", "Apex PA pick"),
    ("fp-donchian-tf15#15", "donchian", "20260930-111627-draft_pp_donchian-cd3c#15", "pm", "Lucid Pro DLL eval single"),
]
KEY = ("date", "side", "entry_price", "exit_price", "exit_reason")
ALL_FIELDS = ("date", "side", "qty", "entry_price", "exit_price", "exit_reason", "order_price", "sl", "tp", "gross",
              "commission", "net", "mae_pts", "mfe_pts", "mae_usd", "mfe_usd", "bars", "seconds", "entry_ms", "exit_ms")


class DonchianNoLatency(l2ref.Donchian):
    """Ablation only: orders live at once instead of after the tester's 85 ms placement latency."""
    placement_ms = 0


class StraddleNoLatency(l2ref.Straddle):
    """Ablation only (stop entries: the latency rarely matters)."""
    placement_ms = 0


HB_TAPE = Path.home() / "futures_derived" / "homebase_tape" / "NQ"


def _tape_same(iso: str) -> tuple:
    """Is the ofb_tick session tape print-identical to the tester's own tape cache? (in-sample dates only)"""
    import numpy as np
    S.wait_compute_window()
    S.check_holdout(iso)
    p = HB_TAPE / f"{iso}.tape"
    if not p.exists():
        return iso, "no tester cache"
    magic = b"HBTAPE1\n"
    with open(p, "rb") as f:
        f.read(len(magic))
        head = json.loads(f.read(int.from_bytes(f.read(4), "little")))
        n = head["n"]
        ts = np.fromfile(f, dtype="<i8", count=n)
        px = np.fromfile(f, dtype="<f8", count=n)
        sz = np.fromfile(f, dtype="<i4", count=n)
    t = S.load_tape(iso)
    ok = (len(t.ts) == n and bool((t.ts == ts).all()) and bool((t.px == px).all()) and bool((t.size == sz).all())
          and t.contract == head["contract"])
    return iso, "same" if ok else "DIFFERENT"


def tape_identity(workers: int = 8) -> dict:
    days = [d.isoformat() for d in S.sessions(START, END)]
    S.wait_compute_window()
    with S.get_context("spawn").Pool(min(workers, S.MAX_WORKERS)) as pool:
        res = pool.map(_tape_same, days, chunksize=16)
    c = Counter(r[1] for r in res)
    return {"sessions": len(days), "same": c.get("same", 0), "other": [r for r in res if r[1] != "same"][:20]}


GRID_SWEEP = [("straddle", "20260930-001526-draft_pp_straddle-67c2"), ("orb", "20260929-231930-draft_pp_orb-5276"),
              ("donchian", "20260930-111627-draft_pp_donchian-cd3c")]


def grid_sweep(workers: int = 8) -> list:
    """EVERY cell of the three tester heat-maps the gate configs come from, each family in one tape pass."""
    out = []
    for fam, gid in GRID_SWEEP:
        n = json.loads((GRIDS / gid / "grid.json").read_text())["total"]
        cells = [load_bundle(f"{gid}#{i}") for i in range(n)]
        res = S.run_many([(l2ref.FAMILIES[fam], c[0]) for c in cells], START, END, workers=workers)
        cmp_ = [compare(r["trades"], c[1]) for r, c in zip(res, cells)]
        out.append({"family": fam, "grid": gid, "cells": n, "elapsed_s": res[0]["elapsed_s"],
                    "trades_ref": sum(c["n_ref"] for c in cmp_), "trades_sim": sum(c["n_sim"] for c in cmp_),
                    "matched": sum(c["matched"] for c in cmp_), "exact": sum(c["exact_all_fields"] for c in cmp_),
                    "min_match_rate": min(c["match_rate"] for c in cmp_),
                    "max_abs_net_diff": max(abs(c["net_diff"]) for c in cmp_),
                    "cells_identical": sum(1 for c in cmp_ if c["exact_all_fields"] == c["n_ref"] == c["n_sim"])})
    return out


def ablations(workers: int = 8) -> list:
    """Negative controls: the same strategies with ONE convention changed must stop matching the bundles."""
    out = []
    for cfg, cls, costs, label in (
            (GATE[0], l2ref.Straddle, S.Costs(4.0, 0.0), "slippage 0 ticks (instead of 1)"),
            (GATE[2], l2ref.Donchian, S.Costs(4.0, 0.0), "slippage 0 ticks (instead of 1)"),
            (GATE[2], DonchianNoLatency, S.Costs(), "placement latency 0 ms (instead of 85)"),
            (GATE[0], StraddleNoLatency, S.Costs(), "placement latency 0 ms (instead of 85)")):
        inputs, ref, cov, cost, engine = load_bundle(cfg[2])
        res = S.run(cls, inputs, START, END, workers=workers, costs=costs)
        c = compare(res["trades"], ref)
        out.append({"id": cfg[0], "change": label, **{k: c[k] for k in (
            "n_ref", "n_sim", "matched", "match_rate", "exact_rate", "net_ref", "net_sim", "net_diff", "net_diff_pct")}})
    return out


def stress(workers: int = 8) -> list:
    """Execution sensitivity of the three gate configs (NOT part of the gate): the same strategies with the
    slippage and / or the placement latency raised to the pre-agreed stress (l2sim.STRESS: 2 ticks, 250 ms)."""
    out = []
    for cid, fam, src, sess, role in GATE:
        inputs, ref, cov, cost, engine = load_bundle(src)
        for label, kw in (("tester law (1 tick, 85 ms)", {}), ("slip 2 ticks", {"slip_ticks": S.STRESS["slip_ticks"]}),
                          ("latency 250 ms", {"latency_ms": S.STRESS["latency_ms"]}), ("2 ticks + 250 ms", dict(S.STRESS))):
            res = S.run(l2ref.FAMILIES[fam], inputs, START, END, workers=workers, **kw)
            tr = res["trades"]
            pick = [t for t in tr if S.session_of(t["entry_ms"]) == sess]
            out.append({"id": cid, "pick_session": sess, "change": label, "stress": res["meta"]["stress"],
                        "trades": len(tr), "net": round(sum(t["net"] for t in tr), 2),
                        "pick_trades": len(pick), "pick_net": round(sum(t["net"] for t in pick), 2),
                        "skipped_by_error": res["skipped_by_error"]})
    return out


def load_bundle(src: str):
    """(inputs, trades in-sample, coverage) of a tester grid cell. Rows dated outside [START, END] are dropped
    before anything looks at them (the bundles here end 2024-12-31; the filter is the holdout seal)."""
    g, c = src.split("#")
    d = GRIDS / g / "cells" / f"{int(c):02d}"
    run = json.loads((d / "run.json").read_text())
    assert run["range"]["end"] < "2025-01-01", f"{src}: bundle range reaches the holdout"
    trades = [t for t in json.loads((d / "trades.json").read_text()) if START <= t["date"] <= END]
    cost = {k: run[k] for k in ("qty", "commission", "slippage_ticks")}
    return run["inputs"], trades, run["coverage"], cost, run["engine"]


def compare(sim: list, ref: list) -> dict:
    """Greedy one-to-one match on KEY with entry time within 1 s."""
    pool = defaultdict(list)
    for t in sim:
        pool[tuple(t[k] for k in KEY)].append(t)
    matched, exact, unmatched_ref = 0, 0, []
    for t in ref:
        c = pool.get(tuple(t[k] for k in KEY), [])
        j = next((i for i, x in enumerate(c) if abs(x["entry_ms"] - t["entry_ms"]) <= 1000), None)
        if j is None:
            unmatched_ref.append(t)
            continue
        x = c.pop(j)
        matched += 1
        exact += all(x.get(k) == t.get(k) for k in ALL_FIELDS)
    unmatched_sim = [x for c in pool.values() for x in c]
    net_s, net_r = sum(t["net"] for t in sim), sum(t["net"] for t in ref)
    denom = max(len(sim), len(ref), 1)
    return {"n_sim": len(sim), "n_ref": len(ref), "matched": matched, "exact_all_fields": exact,
            "match_rate": matched / denom, "exact_rate": exact / denom,
            "net_sim": round(net_s, 2), "net_ref": round(net_r, 2), "net_diff": round(net_s - net_r, 2),
            "net_diff_pct": (abs(net_s - net_r) / abs(net_r) * 100 if net_r else (0.0 if net_s == net_r else float("inf"))),
            "abs_net_ref": round(sum(abs(t["net"]) for t in ref), 2),
            "unmatched_ref": unmatched_ref[:20], "unmatched_sim": unmatched_sim[:20]}


def one(cid, fam, src, sess, role, workers):
    inputs, ref, cov, cost, engine = load_bundle(src)
    cls = l2ref.FAMILIES[fam]
    res = S.run(cls, inputs, START, END, workers=workers, qty=cost["qty"],
                costs=S.Costs(cost["commission"], cost["slippage_ticks"]))
    sim = res["trades"]
    out = {"id": cid, "family": fam, "tester_src": src, "tester_engine": engine, "role": role, "pick_session": sess,
           "inputs": inputs, "elapsed_s": res["elapsed_s"], "workers": res["meta"]["workers"],
           "sessions_sim": res["sessions"], "used_sim": res["used"], "skipped_by_error": res["skipped_by_error"],
           "unrealistic_winners": res["unrealistic_winners"], "stress": res["meta"]["stress"],
           "skipped_sim": [s["date"] for s in res["skipped"]],
           "skipped_ref": [s["date"] for s in cov["skipped"] if START <= s["date"] <= END],
           "all": compare(sim, ref),
           "pick": compare([t for t in sim if S.session_of(t["entry_ms"]) == sess],
                           [t for t in ref if S.session_of(t["entry_ms"]) == sess]),
           "by_reason_sim": dict(Counter(t["exit_reason"] for t in sim)),
           "by_reason_ref": dict(Counter(t["exit_reason"] for t in ref))}
    a, p = out["all"], out["pick"]
    out["gate_pass"] = bool(min(a["match_rate"], p["match_rate"]) >= 0.95 and max(a["net_diff_pct"], p["net_diff_pct"]) <= 2.0
                            and res["skipped_by_error"] == 0 and res["meta"]["stress"] is None)
    return out


def row(o, k):
    c = o[k]
    return (f"| {o['id']} | {o['role']} | {'all sessions' if k == 'all' else o['pick_session']} | {c['n_ref']} | {c['n_sim']} | "
            f"{c['matched']} | {c['match_rate'] * 100:.2f}% | {c['exact_rate'] * 100:.2f}% | {c['net_ref']:+,.0f} | "
            f"{c['net_sim']:+,.0f} | {c['net_diff']:+,.2f} ({c['net_diff_pct']:.3f}%) |")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


MD = """# SIM_VALIDATION — l2sim vs the Homebase Strategy Tester (in-sample 2021-09-22 → 2024-12-31)

Generated {when} by `sim_validate.py` (code sha256/16: {shas}). Raw numbers: `out/sim_validation.json`.

## Verdict: GATE {verdict}
Gate (SPEC.md): for each of the three approved tester strategies, >= 95% of trades identical on
(date, side, entry time ±1 s, entry price, exit price, exit_reason) AND total net within 2% of the tester bundle.
Match rate = matched / max(tester trades, sim trades); "all-20-fields identical" additionally requires qty,
order_price, sl, tp, gross, commission, net, mae/mfe (pts and usd), bars, seconds, entry_ms and exit_ms to be equal.
Each config is checked on every session of the run (sess = all) and on the approved pick's own session.

{gate}

Sessions: {sess} in-sample sessions with a tape, {used} used; the 5 coverage-hole days are skipped by the sim for the
same reason strings as the tester ({skips}). No row dated >= 2025-01-01 was read (bundles end 2024-12-31; the tape
loader raises on 2025+).

## Other baseline picks (not part of the gate, same check)
{extra}

## Which tape
The tester replays `~/futures_ticks/NQ/<YYYY>/<date>_<contract>.csv.gz` (front contract = the manifest with the most
ticks, stable-sorted by ts_ns), cached as `~/futures_derived/homebase_tape/NQ/<date>.tape`. The SPEC's execution tape
`~/futures_derived/ofb_tick/NQ/YYYY/MM/<date>.parquet` is built from the same archive files with the same front-month
rule. Checked on every in-sample session: **{tape_same} of {tape_n} sessions are print-identical** (ts_ns, price, size,
row order, contract){tape_note}. l2sim therefore reads the ofb_tick parquet (columns ts_ns, price, size only): it IS the
tester's tape, and the lagged OFB columns stay available to the data layer from the same file.

## Conventions reproduced (homebase/backtest/engine.py "tick-2", runner.py, strategies/base.py, tape.py)
* Stop orders (stop entries, stop-losses): market-on-touch, fill = max/min(trigger, print) ± 1 tick (a gap costs the gap).
* Limit orders (limit entries, targets): fill only on a 1-tick trade-through, at the limit price, no slip.
* Market orders: first print at/after the order goes live, ± 1 tick. Flatten: first print at/after the event, ∓ 1 tick.
* Orders go live 85 ms (`placement_ms`) after the event that sent them; cancel / flatten act at once.
* A strategy callback that raises costs that session only: orders cancelled, the session's trades dropped, the day
  listed under no_trade as "strategy error: ..." and counted in `skipped_by_error` (gate runs: {errs} such sessions).
* Inputs are validated and coerced like the tester's `resolve_inputs` (unknown key, wrong type, bad choice, out of
  range -> error); `session_independent` is opt-in as in the tester (the Template and the three families set it).
* SL/TP ride the entry and can trigger from the print after the entry print; one print hitting both -> SL
  (orders triggering on one print fill oldest first; the SL is created before the TP).
* `move_brackets_to_fill`: SL (and TP) keep their distance to `ref`; `tp_rr` re-derives the TP from the fill.
* Prices snapped to the tick grid; touch comparisons epsilon-tolerant (tick × 1e-6).
* Commission $4.00 per round turn per NQ, qty 1; gross = side × (exit − entry) × $20.
* MAE/MFE: extremes of the prints from the entry print's index to the exit print, against the slipped fill price.
* Events: session start, 1-minute bar closes (bars only for minutes with prints; a bar closing at 10:00:00 runs before
  the first print stamped >= 10:00:00 and sees only earlier prints), `times()`; same-time order session < bar < time;
  events at/after the session end never fire; end of session flattens everything ("eod").
* Calendar: weekday sessions with a tape; a session with an empty clock hour inside the window is skipped
  ("missing HH:MM–HH:MM ET"); CME half days clamp the window to 13:15 ET. Daily bars (prior-day H/L/C, daily ATR) =
  whole archive day, contract-roll days drop the prior-day levels (same 13 in-sample roll dates as the drafts).
* Trades: the tester's trades.json schema (date, side, qty, entry_price, exit_price, exit_reason, order_price, sl, tp,
  gross, commission, net, mae_pts, mfe_pts, mae_usd, mfe_usd, bars, seconds, entry_ms, exit_ms), sorted by (exit, entry).
The three strategies are re-implemented on `l2sim.Template` (the port of R/template.py: tf aggregation, Wilder ATR(14)
since 00:00 ET, sessions asia/london/nyam/mid/pm, atr|pts|struct stops, tgt_r, trail_atr, exit_bars, max_tr, no
entries in the last 5 minutes, flat at session end) in `l2ref.py`; inputs are read from each bundle's run.json.

## Every cell of the three source heat-maps (parameter coverage)
Each family's whole tester grid replayed in one tape pass (`l2sim.run_many`) and compared cell by cell:

| family | tester grid | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max abs net diff $ | sim time |
|---|---|---|---|---|---|---|---|---|---|
{grids}

## Negative controls (the comparison can fail)
Same strategies, ONE convention changed, full in-sample window:

| config | change | tester trades | sim trades | match rate | all-fields identical | net diff $ |
|---|---|---|---|---|---|---|
{abl}

## Engine-level differential tests (tests/test_l2sim_engine_diff.py)
The tester's own `run_session` (imported read-only, no bytecode written) and l2sim's are fed the same tape and the
same strategy object: a random order-flow fuzz over the whole ctx API (market / stop / limit entries, sl / tp / tp_rr
/ ref, OCO, cancel, flatten, off-grid prices, overlapping positions, same-timestamp bursts, empty minutes) on 12
synthetic tapes and 6 real in-sample days (2 half days, 2 roll days), plus the reference families incl. struct stops,
trail / exit_bars and both filters. Trades and final order states are identical in every case. This covers what the
three approved strategies do not exercise: limit entries, tp_rr, trailing / bar exits, overlapping positions.

## Speed
Full in-sample run (825 sessions, sess = all) on 8 worker processes: {speed}. SPEC target <= 60 s.
A grid shares one tape pass (`run_many`): {gspeed}. Per session-day: ~16 ms to read the tape, ~8 ms per cell.

## Execution sensitivity of the gate configs (not part of the gate)
`l2sim.run(..., slip_ticks=, latency_ms=, strict_limit=)`; defaults = the tester law above. Stress = `l2sim.STRESS`
(2 ticks of slip per market / stop / flatten fill, 250 ms placement latency). Full in-sample window:

| config | execution | trades | net $ (all sessions) | pick session | trades | net $ |
|---|---|---|---|---|---|---|
{stress}

## Open risks (read before screening)
**Where the fill law is NOT pessimistic.** These are the tester's conventions, reproduced on purpose (the gate needs
them); they are not port defects, and a new family must survive the stress run before it is believed.
1. **Market and flatten fills pay 1 tick from the last print, not the spread.** In-sample `l2data.spread_ticks` at
   minute ends (1.08 million book_ok rows): median 2 ticks in nyam / mid / pm (means 2.14 / 1.96 / 1.98), median 3 ticks
   in asia / london (means 2.87 / 2.85); the spread is wider than 2 ticks in 56.5% of asia and 59.9% of london minutes
   against 14–23% in RTH. One tick is about half the RTH spread and less than half overnight: asia / london market
   entries are optimistic by roughly half a tick to a tick per side. Check with `slip_ticks=2`.
2. **Cancels, flattens and OCO cancels have zero latency** while new orders wait 85 ms: a cancel at a bar close always
   beats a print 1 ms later, and an OCO sibling is cancelled the instant the other leg fills (no double fill in a fast
   market). The 'eod' flatten on a CME half day fills on the last print BEFORE 13:15 ET (∓ 1 tick), not on a print
   at/after the close (6 trades per gate config).
3. **Results move with the 85 ms figure, and live latency above it is not modelled.** fp-donchian-tf15#10 nets −8,064
   at 85 ms and +11,198 at 0 ms (about one tick per trade over 3,571 trades; see the negative controls). 85 ms is the
   desk's measured placement latency, not a bound. Check with `latency_ms=250`.
4. **A limit entry's stop is armed one print after the fill print.** A print that trades through the limit and is
   already at/through the stop does not stop the trade; some of these end as booked target wins that are losers live.
   Independent verifier's probe (out/build_reports/verify_sim_1.md; 59 in-sample days, a limit 1 tick passive every
   minute, target 1R): with a 2-tick stop 28.0% of 20,430 fills were through the stop on the fill print and 392 of
   them exited 'tp'; 4 ticks 7.2% (60 'tp'); 8 ticks 1.2%; 16 ticks 0.2%; net bias about zero (−$0.08 per trade at
   2 ticks). For every limit-entry family (B4 wall_bounce): `result["unrealistic_winners"]` /
   `l2sim.unrealistic_winners(trades)` lists the limit-entry trades with exit_reason 'tp' and mae_pts >= the stop
   distance; more than a handful -> judge the family on `strict_limit=True` (the stop is live ON the fill print),
   which removes them by construction.
5. **A limit fills on a 1-tick trade-through with no queue model** (this one IS pessimistic for passive fills, but a
   trade-through of several ticks still fills at the limit price in full size).

**Coverage of the validation.**
* 100% is by construction, not luck: same tape, a line-by-line port of the engine, same strategy logic. The gate
  proves the execution layer adds no drift; it says nothing about how close the tester's law is to live fills.
* No tester bundle exercises struct stops, trail_atr, exit_bars, f_trend / f_vwap, dir long / short, news_only or the
  new `_lim` limit-entry helper: their fidelity rests on code identity with R/template.py and on the engine
  differential tests, not on a trade-for-trade bundle match.
* `ctx.daily` / `datr()` are not covered by the gate (no gate strategy reads them). The daily cache starts 2021-09-22
  (first tape session) while the tester loads 400 days before the range start, so `datr()` is None for the first 15
  sessions and its Wilder seed differs from the tester's early in the sample and on sub-range runs.
* `on_bar` fires only for minutes that have prints (tester convention). A strategy that must act on a minute with no
  print should use `times()`.
* Feature rows are visible to a strategy only through `ctx.feat` / `ctx.feat_window` (usable_ns <= decision time; a
  negative `back` / `n` raises `LookAheadError`, which aborts the run); a strategy that reads the data layer directly
  bypasses that guard. The adapter's absolute clock is tested against the tape's (tests/test_l2sim_lookahead.py).
* A session dropped by a strategy error is NOT a flat day: check `result["skipped_by_error"] == 0` before scoring.
* A raw `Strategy` subclass runs on ONE process unless it sets `session_independent = True` (tester default: False).
* Holdout tapes (2025+) raise `HoldoutSealed` unless `allow_holdout=True`; the half-day table covers 2017–2026.
* The differential tests import the tester's engine as it is on disk today; if `homebase/backtest/engine.py` changes
  (ENGINE_VERSION != tick-2) the port must be re-diffed.

## Reproduce
`"~/ONYX TRADING/.venv/bin/python" sim_validate.py` (about {total:.0f} s) and
`"~/ONYX TRADING/.venv/bin/python" -m pytest` in this directory.
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-extra", action="store_true")
    ap.add_argument("--no-write", action="store_true", help="print only; leave SIM_VALIDATION.md alone")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    gate = [one(*c, a.workers) for c in GATE]
    extra = [] if a.no_extra else [one(*c, a.workers) for c in EXTRA]
    ok = all(o["gate_pass"] for o in gate)
    tapes = tape_identity(a.workers)
    abl = ablations(a.workers)
    strs = stress(a.workers)
    grids = grid_sweep(a.workers)
    gl = "\n".join(f"| {g['family']} | {g['grid']} | {g['cells']} | {g['cells_identical']} | {g['trades_ref']:,} | "
                   f"{g['trades_sim']:,} | {g['exact']:,} | {g['min_match_rate'] * 100:.2f}% | {g['max_abs_net_diff']:,.2f} | "
                   f"{g['elapsed_s']:.0f} s |" for g in grids)
    here = Path(__file__).resolve().parent
    shas = {f: sha(here / f) for f in ("l2sim.py", "l2ref.py", "sim_validate.py")}
    hdr = ("| config | role | scope | tester trades | sim trades | matched | match rate | all-20-fields identical | "
           "tester net $ | sim net $ | net diff |\n|---|---|---|---|---|---|---|---|---|---|---|")
    lines = "\n".join([hdr] + [row(o, k) for o in gate for k in ("all", "pick")])
    xl = "\n".join([hdr] + [row(o, k) for o in extra for k in ("all", "pick")]) if extra else "(not run)"
    al = "\n".join(f"| {x['id']} | {x['change']} | {x['n_ref']} | {x['n_sim']} | {x['match_rate'] * 100:.2f}% | "
                   f"{x['exact_rate'] * 100:.2f}% | {x['net_diff']:+,.0f} |" for x in abl)
    sl = "\n".join(f"| {x['id']} | {x['change']} | {x['trades']} | {x['net']:+,.0f} | {x['pick_session']} | "
                   f"{x['pick_trades']} | {x['pick_net']:+,.0f} |" for x in strs)
    total = time.monotonic() - t0
    print(lines)
    print(xl)
    print(al)
    print(sl)
    print(gl)
    for o in gate + extra:
        print(f"{o['id']}: {o['elapsed_s']} s on {o['workers']} workers; sessions {o['sessions_sim']} used {o['used_sim']}; "
              f"skipped same as tester: {o['skipped_sim'] == o['skipped_ref']}; gate_pass {o['gate_pass']}")
    print(f"tape identity: {tapes['same']}/{tapes['sessions']}  |  GATE {'PASS' if ok else 'FAIL'}  ({total:.0f} s total)")
    if a.no_write:
        return ok
    (here / "out").mkdir(exist_ok=True)
    (here / "out" / "sim_validation.json").write_text(json.dumps(
        {"generated_et": dt.datetime.now(S.ET).isoformat(timespec="seconds"), "window": [START, END],
         "gate_pass": ok, "gate": gate, "extra": extra, "tape_identity": tapes, "ablations": abl, "stress": strs,
         "grid_sweep": grids,
         "code_sha256_16": shas}, indent=1))
    g0 = gate[0]
    same_skips = all(o["skipped_sim"] == o["skipped_ref"] for o in gate + extra)
    (here / "SIM_VALIDATION.md").write_text(MD.format(
        when=dt.datetime.now(S.ET).strftime("%Y-%m-%d %H:%M ET"),
        shas=", ".join(f"{k} {v}" for k, v in shas.items()), verdict="PASS" if ok else "FAIL",
        gate=lines, extra=xl, abl=al, grids=gl, stress=sl, errs=sum(o["skipped_by_error"] for o in gate + extra),
        sess=g0["sessions_sim"], used=g0["used_sim"],
        skips=", ".join(g0["skipped_sim"]) + ("" if same_skips else " — SKIP LISTS DIFFER, see json"),
        tape_same=tapes["same"], tape_n=tapes["sessions"],
        tape_note="" if tapes["same"] == tapes["sessions"] else f"; NOT identical: {tapes['other']}",
        speed=", ".join(f"{o['id']} {o['elapsed_s']:.1f} s" for o in gate),
        gspeed=", ".join(f"{g['cells']} {g['family']} cells {g['elapsed_s']:.0f} s" for g in grids), total=total))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
