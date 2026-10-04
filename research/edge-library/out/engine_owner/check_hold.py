#!/usr/bin/env python3
"""ENGINE OWNER check of hold_to='day' on the 10 smoke days -- COUNTS AND IDENTITIES ONLY (never a P&L, never an exit mix).

For every library family (first exit cells of its first / last variant) at one tf on NQ (+ ES / GC with --roots):
  A  hold_to='session': the five single-session instances together == the sess='all' instance, trade for trade
     (so splitting the sessions into instances changes nothing: hold_to='day' differs from the tester-matched run by the
     exit rule alone)
  B  hold_to='day' (seven instances): every entry inside its instance's session window; every exit <= the day's flatten
     minute; no two trades of an instance overlap; EVERY entry (date, side, time, price) is an entry of the same instance
     under hold_to='session' and vice versa; a trade the old rule did NOT close by the clock ('time' / 'eod') is identical
     in every field -- i.e. the new convention changes nothing but the exits the old rule forced at a session end.
     THREE expected differences, each counted apart (all follow from the rule, none from a trade's result):
       - on an equity half day the old rule still entered in the last 5 minutes before 13:13 (mid session, until the 13:15
         close); hold_to='day' takes no entry in the 5 minutes before the day's flatten time
       - on an equity half day a stop / target the old rule hit between 13:13 and the 13:15 close is a 13:13 flatten now
       - an EVENING entry of a trade date whose DAY window has an empty clock hour (GC 2022-11-25): the held evening
         instance skips that date (the day's own coverage rule), the old evening instance traded it
  C  EARLY_STOP on == off, trade for trade
Usage: python check_hold.py [--roots NQ,ES,GC] [--tf 5] [--only fam,fam]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l2sim as S          # noqa: E402
import run_menus as RM     # noqa: E402

KEY = ("date", "side", "entry_ms", "entry_price", "exit_ms", "exit_price", "exit_reason")
DAY5 = ("asia", "london", "nyam", "mid", "pm")
SEVEN = ("asia", "london", "pre", "nyam", "mid", "pm", "eve")


def key(t):
    return tuple(t[k] for k in KEY)


def flat_ms(date_iso: str, root: str) -> int:
    d = dt.date.fromisoformat(date_iso)
    return S.et_ns(d, S.day_flat(d, root)) // 1_000_000


def check(name: str, root: str, tf: str, days: list) -> dict:
    import families as F
    cls = F.REGISTRY[name][0]
    grid = F.unit_grid(name, root, tf)
    pick = sorted({0, 3, 9, 14, 31, len(grid) - 32, len(grid) - 1})          # a few exit cells of the first and the last variant
    cells = [grid[i] for i in pick if 0 <= i < len(grid)]
    feats = F.features_for(name)
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    out = {"family": name, "root": root, "tf": tf, "cells": len(cells)}
    timed = RM.is_time_fired(cls)
    run = lambda specs: S.run_many(specs, days=days, root=root, workers=1, features=feats, **kw)      # noqa: E731
    if not timed:
        a_all = run([(c["spec"][0], {**c["spec"][1], "sess": "all"}) for c in cells])
        a_one = run([(c["spec"][0], {**c["spec"][1], "sess": s}) for c in cells for s in DAY5])
        same = 0
        for i, r in enumerate(a_all):
            union = sorted((key(t) for k in range(5) for t in a_one[i * 5 + k]["trades"]))
            same += union == sorted(key(t) for t in r["trades"])
        out["A_single_sessions_equal_all"] = f"{same}/{len(cells)}"
        out["A_trades"] = sum(len(r["trades"]) for r in a_all)
    specs, owner = [], []
    for c in cells:
        for cl, p in RM.cell_specs(c):
            specs.append((cl, p))
            owner.append(p.get("sess") if not timed else S.clock_session(cl(p).p["at"]))
    day = run(specs)
    old = run([(cl, {**p, "hold_to": "session"}) for cl, p in specs])
    late = outside = overlap = first_diff = n = held_past = entry_diff = same_diff = last5 = hole = half_x = 0
    for r, o, sess in zip(day, old, owner):
        tr = sorted(r["trades"], key=lambda t: t["entry_ms"])
        n += len(tr)
        first_old = {}
        for t in sorted(o["trades"], key=lambda t: t["entry_ms"]):
            first_old.setdefault(t["date"], (t["side"], t["entry_ms"], t["entry_price"]))
        seen = set()
        for a, b in zip(tr, tr[1:]):
            overlap += b["entry_ms"] < a["exit_ms"]
        for t in tr:
            fm = flat_ms(t["date"], root)
            late += t["exit_ms"] >= fm + 60_000
            outside += S.session_of(t["entry_ms"]) != sess
            if t["date"] not in seen:
                seen.add(t["date"])
                first_diff += first_old.get(t["date"]) != (t["side"], t["entry_ms"], t["entry_price"])
        ends = {key(t)[:4] + (t["exit_ms"],) for t in o["trades"]}
        held_past += sum(1 for t in tr if key(t)[:4] + (t["exit_ms"],) not in ends)
        ent = lambda t: (t["date"], t["side"], t["entry_ms"], t["entry_price"])          # noqa: E731
        new_by = {ent(t): t for t in tr}
        gone = [t for t in o["trades"] if ent(t) not in new_by]
        skipped = {x["date"] for x in r["skipped"]} - {x["date"] for x in o["skipped"]}       # dates only the held evening skips
        holed = [t for t in gone if t["date"] in skipped]
        cut = [t for t in gone if t["date"] not in skipped and t["entry_ms"] >= flat_ms(t["date"], root) - 300_000]
        last5 += len(cut)                                                                   # the half-day no-entry line
        hole += len(holed)
        entry_diff += len(gone) - len(cut) - len(holed) + len(set(new_by) - {ent(t) for t in o["trades"]})
        for t in o["trades"]:
            if t["exit_reason"] in ("time", "eod") or ent(t) not in new_by or new_by[ent(t)] == t:
                continue
            if t["exit_ms"] >= flat_ms(t["date"], root) and new_by[ent(t)]["exit_reason"] == "time":
                half_x += 1                                                                 # hit between 13:13 and the 13:15 close
            else:
                same_diff += 1
    out.update(B_trades=n, B_exit_after_flat=late, B_entry_outside_session=outside, B_overlapping=overlap,
               B_first_entry_differs=first_diff, B_entries_not_shared_with_session_rule=entry_diff,
               B_non_clock_exits_changed=same_diff, B_old_entries_in_the_5min_before_the_day_flat=last5,
               B_old_eve_entries_on_a_date_whose_day_has_a_hole=hole, B_half_day_exits_between_flat_and_close=half_x,
               B_trades_whose_exit_differs_from_session_rule=held_past,
               B_errors=sum(r["skipped_by_error"] for r in day))
    S.EARLY_STOP = False
    try:
        full = run(specs)
    finally:
        S.EARLY_STOP = True
    out["C_early_stop_identical"] = all(a["trades"] == b["trades"] for a, b in zip(day, full))
    out["ok"] = bool(late == 0 and outside == 0 and overlap == 0 and first_diff == 0 and entry_diff == 0 and same_diff == 0
                     and out["C_early_stop_identical"]
                     and out["B_errors"] == 0 and (timed or out["A_single_sessions_equal_all"] == f"{len(cells)}/{len(cells)}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", default="NQ")
    ap.add_argument("--tf", default="5")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    import families as F
    bad = 0
    for root in a.roots.split(","):
        days = [d for d in RM.SMOKE_DAYS if S._date(d) in set(S.sessions(*S.period("build"), root))]
        for name in sorted(F.LIBRARY):
            if a.only and name not in a.only.split(","):
                continue
            cls = F.REGISTRY[name][0]
            if root not in F.LIBRARY[name]["roots"]:
                continue
            tf = a.tf if a.tf in cls.SCREEN_TFS else cls.SCREEN_TFS[0]
            o = check(name, root, tf, days)
            bad += not o["ok"]
            print(json.dumps(o), flush=True)
    print("ALL OK" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
