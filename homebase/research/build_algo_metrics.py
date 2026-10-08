"""Build the "Backtest metrics" artifact of the gc_nfp desk algo: homebase/research/gc_nfp_equity.json.

Nothing is typed by hand.  Every point is one real backtest trade; every number is computed from that
trade list or read from the research's own result files.

  gc_nfp
      The NFP study (research/nfp-2026-10-02).  Every NFP day with a GC tape, replayed from the tick archive
      with the study's own nfp_lib.replay at the DESK's numbers (config: contracts, offset, SL, TP, fire /
      cancel / flat times).  The study's tables (out/summary_IS.csv, out/summary_HO.csv, its variant B) sit
      next to it in the prop table.  (The four NQ levels algos this script once also built were removed
      from Homebase 2026-10-08.)

The desk side is read from homebase.config's shipped defaults.

Run it with a Python that has numpy + pandas (nfp_lib needs them; the repo venv has neither):
    /usr/bin/python3 homebase/research/build_algo_metrics.py [--out DIR]
Paths (--nfp, --ticks, --out) default to the main checkout's research/ and the tick archive.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True       # this build imports the research's own modules: leave no .pyc next to them

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(REPO), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build_metrics import ledger_table, money, pct          # noqa: E402
from homebase.backtest.propsim import load_rules            # noqa: E402
from homebase.config import _defaults                       # noqa: E402

MAIN = Path.home() / "ramos-quant-homebase"                 # research/ lives in the main checkout
GC = "gc_nfp"
GC_RULES = "lucid-pro-50k-no-dll@2026-09-27b"               # the eval the NFP study sized for ($3,000 / $2,000)
GC_FEE_SIDE = 2.30                                          # $ a side per GC contract (Lucid; the study's verify runs)
GC_STUDY_B = "B_plain_4GC_off2pt_SL2000"                    # results.md variant B = the desk's stop, fired 08:30:00


def both(f, ho, ins) -> str:
    """'holdout / in-sample' with one formatter; a missing value prints as n/a."""
    return " / ".join("n/a" if v is None else f(v) for v in (ho, ins))


# ------------------------------------------------------------------ GC: the NFP study at the desk's numbers

def build_gc(a: argparse.Namespace) -> dict:
    cfg = _defaults().strategies[GC]
    if str(a.nfp) not in sys.path:
        sys.path.insert(0, str(a.nfp))
    import numpy as np                                      # noqa: PLC0415
    import nfp_lib as N                                     # noqa: PLC0415
    N.ARCH = a.ticks
    N.CAL = REPO / "homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv"
    rule_file = load_rules(GC_RULES)
    target, mll = float(rule_file["eval_target"]), float(rule_file["trailing_mll"])
    s = N.SPEC[cfg.symbol]
    pv, comm = s["pv"] * cfg.qty, 2 * GC_FEE_SIDE * cfg.qty

    def at(d, hms):
        p = [int(x) for x in hms.split(":")] + [0]
        return N.ns(d, p[0], p[1], p[2])

    rows, missing = [], []
    for d in [d for d, tag in N.events() if tag == "NFP"]:
        tape = N.load_event((cfg.symbol, d))[2]
        if tape is None:
            missing.append(d.isoformat())
            continue
        ts, px = tape
        res = {}
        for key, fire, live in (("desk", at(d, cfg.fire_et), at(d, cfg.fire_et)),                  # orders rest from the fire
                                ("study", at(d, "08:30:00"), at(d, "08:30:00") + N.PLACEMENT_NS)):  # the study's fire
            i = int(np.searchsorted(ts, fire, side="left")) - 1
            if i < 0:
                raise SystemExit(f"{GC}: no print before the fire on {d}")
            t2, p2 = ts[i:], px[i:]
            P = dict(ts=t2, px=p2, anchor=float(p2[0]), t_fire=fire,
                     i0=int(np.searchsorted(t2, live, side="left")),
                     i_c=int(np.searchsorted(t2, at(d, cfg.cancel_et), side="left")),
                     i_f=int(np.searchsorted(t2, at(d, cfg.flat_et), side="right")))
            # house fill model M1: the stop entry pays the gap + 1 tick, the stop + 1 tick, the target is a limit
            net, why = N.replay(P, cfg.offset_pts, cfg.sl_pts, cfg.tp_pts, s["tick"], pv, comm, 1, 1, False)
            res[key] = (round(float(net), 2), why)
        rows.append((d.isoformat(), res["desk"], res["study"]))

    dates = [r[0] for r in rows]
    pnl = [r[1][0] for r in rows]
    n = len(rows)
    points, c = [], 0.0
    for d, p in zip(dates, pnl):
        c = round(c + p, 2)
        points.append([d, c])
    split = N.HO_START.isoformat()
    first_ho = next(i for i, d in enumerate(dates) if d >= split)

    def rate(col, part, test):                # col 1 = the desk's fire, 2 = the study's; part "HO" = 2025+
        x = [r[col][0] for r in rows if (r[0] >= split) == (part == "HO")]
        return sum(1 for v in x if test(v)) / len(x)

    is_pass, is_bust = (lambda v: v >= target), (lambda v: v <= -mll)
    why = [r[1][1] for r in rows]
    flips = [r[0] for r in rows if (is_pass(r[1][0]), is_bust(r[1][0])) != (is_pass(r[2][0]), is_bust(r[2][0]))]

    def study(part, set_, col):
        f = a.nfp / f"out/summary_{part}.csv"       # IS = the whole grid; HO = the 5 frozen finalists, by name
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                b = (r.get("name") == GC_STUDY_B) if part == "HO" else (
                    r["root"] == "GC" and r["arm"] == "const" and r["unit"] == "4xGC" and r["offmode"] == "pts"
                    and float(r["off"]) == cfg.offset_pts and float(r["sl_usd"]) == mll
                    and float(r["tp_usd"]) == target)
                if b and r["model"] == "M1" and r["set"] == set_:
                    return float(r[col])
        raise SystemExit(f"{GC}: variant B ({set_}, M1) not found in {f}")

    T = [["As traded", "contracts", f"{cfg.qty} {cfg.symbol}"],
         ["As traded", "fire", f"{cfg.fire_et} ET"],
         ["As traded", "bracket", f"±{cfg.offset_pts:.1f} / SL {cfg.sl_pts:.1f} / TP {cfg.tp_pts:.1f}"],
         ["As traded", "TP / SL / time / no fill",
          " / ".join(str(why.count(k)) for k in ("TP", "SL", "FLAT", "NOFILL"))],
         ["As traded", f"pass (net ≥ ${target:,.0f})",
          f"{sum(map(is_pass, pnl))} of {n} ({pct(sum(map(is_pass, pnl)) / n)})"],
         ["As traded", f"bust (net ≤ -${mll:,.0f})",
          f"{sum(map(is_bust, pnl))} of {n} ({pct(sum(map(is_bust, pnl)) / n)})"],
         ["As traded", "NFP days with no GC tape", ", ".join(missing) or "none"]]
    T += ledger_table(dates, pnl, period="year", sharpe=False)

    P = [["account", "LucidPro 50K eval, one event"],
         ["numbers shown", "2025-26 / 2021-24"],
         ["events", both(str, n - first_ho, first_ho)],
         [f"pass, fired {cfg.fire_et}", both(pct, rate(1, "HO", is_pass), rate(1, "IS", is_pass))],
         [f"bust, fired {cfg.fire_et}", both(pct, rate(1, "HO", is_bust), rate(1, "IS", is_bust))],
         ["pass, fired 08:30:00", both(pct, rate(2, "HO", is_pass), rate(2, "IS", is_pass))],
         ["bust, fired 08:30:00", both(pct, rate(2, "HO", is_bust), rate(2, "IS", is_bust))],
         ["study B pass, NFP", both(pct, study("HO", "NFP", "p_win"), study("IS", "NFP", "p_win"))],
         ["study B bust, NFP", both(pct, study("HO", "NFP", "p_bust1"), study("IS", "NFP", "p_bust1"))],
         ["study B pass, NFP + CPI", both(pct, study("HO", "ALL", "p_win"), study("IS", "ALL", "p_win"))],
         ["study B bust, NFP + CPI", both(pct, study("HO", "ALL", "p_bust1"), study("IS", "ALL", "p_bust1"))]]
    note = (
        f"One trade per NFP release, {cfg.qty} {cfg.symbol}: stop entries {cfg.offset_pts:.1f} above and below the last "
        f"price before {cfg.fire_et} ET, stop {cfg.sl_pts:.1f}, target {cfg.tp_pts:.1f}, unfilled cancelled {cfg.cancel_et}, "
        f"flat {cfg.flat_et}. Events 1 to {first_ho} ({dates[0]} to {dates[first_ho - 1]}) are the window the "
        f"numbers were picked on. 2025 starts at event {first_ho + 1} ({dates[first_ho]}): those {n - first_ho} "
        f"events had already been used on this strategy family, so they are a consistency check, not a clean exam. "
        f"The line only adds the events up: each eval takes ONE event, a win passes it and a stop-out ends it. "
        f"The prop table below is the number that matters.")
    table_note = (
        f"Every number above is computed from this event list, replayed from the tick archive with the study's own "
        f"engine at the desk's numbers: first-print fills, 1 tick of slippage on the entry and on the stop, "
        f"${GC_FEE_SIDE:.2f} a side per contract. Bust = the trade closes at or below -${mll:,.0f} (closed balance); "
        f"the stop sits at the limit, so every stop-out is a bust and an open-loss rule would change nothing here. "
        f"A real fill at the release can be several points worse than the first print. "
        f"On file: {cfg.metrics['caveat']}.")
    study_tp = N.bracket(pv, N.COMM_MINI * cfg.qty, s["tick"], mll, target)[1]     # the study's own target, in points
    prop_note = (
        f"Per event, for one eval (${target:,.0f} target, ${mll:,.0f} max loss). \"Fired {cfg.fire_et}\" is this "
        f"ledger, the way the desk fires. \"Fired 08:30:00\" is the same bracket placed at the release, the way the "
        f"study fired"
        + (f": the earlier anchor changes pass or bust on {len(flips)} of {n} events ({', '.join(flips)})" if flips else "")
        + f". \"Study B\" is the study's own table (results.md, variant B: same stop, target {study_tp:.1f}, fired "
          f"08:30:00, its first events dropped as warm-up); NFP + CPI is the pooled set the study selected on.")
    return {
        "label": f"Tick replay · NFP days {dates[0]} → {dates[-1]} · {n} events · {cfg.qty} {cfg.symbol}",
        "note": note,
        "points": points,
        "table": T,
        "table_note": table_note,
        "prop_title": "ONE EVAL, ONE EVENT — PASS / BUST PER NFP",
        "prop_table": P,
        "prop_note": prop_note,
    }


# ------------------------------------------------------------------ main

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--nfp", type=Path, default=MAIN / "research/nfp-2026-10-02")
    ap.add_argument("--ticks", type=Path, default=Path.home() / "futures_ticks")
    ap.add_argument("--out", type=Path, default=HERE)
    a = ap.parse_args(argv)
    art = build_gc(a)
    texts = [art[k] for k in ("label", "note", "table_note", "prop_title", "prop_note")]
    if any("<" in t for t in texts + [x for r in art["table"] + art["prop_table"] for x in r]):
        raise SystemExit(f"{GC}: a text holds '<', which the page would read as markup")   # openRes writes them as they are
    (a.out / f"{GC}_equity.json").write_text(json.dumps(art) + "\n")
    net = art["points"][-1][1]
    dd = next(r[2] for r in art["table"] if r[1] == "max drawdown")
    print(f"{GC}: {len(art['points'])} trades, net {money(net)}, max drawdown {dd}")
    for k, v in art["prop_table"]:
        print(f"    {k:34} {v}")


if __name__ == "__main__":
    main()
