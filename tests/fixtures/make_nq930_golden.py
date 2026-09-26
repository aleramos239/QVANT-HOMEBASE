"""Regenerate tests/fixtures/nq930_golden.json from the RESEARCH replay — read-only.

    "/Users/ramoscapital/ONYX TRADING/.venv/bin/python" tests/fixtures/make_nq930_golden.py
    "/Users/ramoscapital/ONYX TRADING/.venv/bin/python" tests/fixtures/make_nq930_golden.py --select

Runs research/nq_930_straddle_ticks.py's OWN functions (front_month, load_day,
replay_day) on the pinned CASES and writes what the research says, trade by
trade. It only reads ~/futures_ticks (2021-2024, the research window); it writes one
file, tests/fixtures/nq930_golden.json. --select re-scans 2022-2024 and prints a
fresh CASES list to paste below (pinned so the fixture never drifts).

Two research quirks the tester deliberately does not copy (spec rulings):
  * a time exit: research fills at the last print <= 15:55:00 ET; the tester at
    the FIRST print >= 15:55:00 ET (spec: "flats happen at the first print at or
    after the time"). Both prices are recorded; the test checks exit_price_spec.
  * research lets rows that share the entry's ts_ns but sit BEFORE the entry row
    trigger the exit; the tester is strict row order. --select skips such days.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

ONYX = Path("/Users/ramoscapital/ONYX TRADING")
sys.path.insert(0, str(ONYX / "research"))
import nq_930_straddle_ticks as R  # noqa: E402

OUT = Path(__file__).resolve().parent / "nq930_golden.json"
BASE = (10.0, 5.0, 15.0)            # offset / SL / TP — the research spec
WIDE = (10.0, 150.0, 300.0)         # forces time exits
NOFILL = (150.0, 5.0, 15.0)         # NQ always travels 10 pts by 12:55; 150 it rarely does
# (date, offset, sl, tp, slip_ticks, category) — pinned by --select, 2026-09-26
CASES: list[tuple] = [
    ("2023-01-30", 10.0, 5.0, 15.0, 1.0, "tp_long"),
    ("2023-12-13", 10.0, 5.0, 15.0, 1.0, "tp_long"),
    ("2022-10-07", 10.0, 5.0, 15.0, 1.0, "tp_short"),
    ("2024-09-16", 10.0, 5.0, 15.0, 1.0, "tp_short"),
    ("2024-08-07", 10.0, 5.0, 15.0, 1.0, "sl_long"),
    ("2024-09-25", 10.0, 5.0, 15.0, 1.0, "sl_long"),
    ("2024-03-21", 10.0, 5.0, 15.0, 1.0, "sl_short"),
    ("2024-12-17", 10.0, 5.0, 15.0, 1.0, "sl_short"),
    ("2022-07-05", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2024-03-22", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2023-03-13", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2023-10-04", 10.0, 5.0, 15.0, 1.0, "sl_gap"),
    ("2022-10-24", 10.0, 5.0, 15.0, 1.0, "sl_gap"),
    ("2024-04-12", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2024-06-18", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2023-03-08", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2022-08-29", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2023-05-31", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2024-02-01", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2023-10-06", 10.0, 5.0, 15.0, 0.0, "slip0_tp"),
    ("2022-02-08", 10.0, 5.0, 15.0, 0.0, "slip0_sl"),
]


def replay(d: dt.date, off: float, sl: float, tp: float, slip_t: float) -> dict | None:
    path = R.front_month(R.ARCHIVE / str(d.year), d)
    if path is None:
        return None
    tape = R.load_day(path, R.ns(d, 9, 25), R.ns(d, 16, 0))
    if tape is None:
        return None
    slip = slip_t * R.TICK
    r = R.replay_day(tape, d, slip, sl, tp, off)
    if r is None:
        return None
    t_fire, t_flat = R.ns(d, *R.FIRE), R.ns(d, *R.FLAT)
    out = {"date": d.isoformat(), "contract": path.name.split("_")[1].split(".")[0],
           "offset": off, "sl": sl, "tp": tp, "slip_ticks": slip_t,
           "anchor": r["anchor"], "filled": r["filled"]}
    if not r["filled"]:
        return {**out, "_tape": tape}
    side = 1 if r["side"] == "long" else -1
    entry_ns = t_fire + round(r["entry_ms"] * 1e6)
    after = tape[tape[:, 0] >= t_flat]
    spec_px = float(after[0][1]) - side * slip if len(after) else None
    out.update({"side": r["side"], "entry_ns": int(entry_ns), "entry_price": r["entry_price"],
                "why": r["why"], "exit_price": r["exit_price"], "net": r["net"],
                "exit_price_spec": spec_px if r["why"] == "FLAT" else r["exit_price"],
                "net_spec": (round(side * (spec_px - r["entry_price"]) * R.PV - R.COMM, 2)
                             if r["why"] == "FLAT" else r["net"]),
                "_tape": tape})
    return out


def clean(rec: dict, d: dt.date) -> bool:
    """Every clock hour of 09:25-16:00 has prints, and no same-ts-before-entry exit."""
    tape = rec["_tape"]
    ts = tape[:, 0]
    cuts = [R.ns(d, 9, 25)] + [R.ns(d, h, 0) for h in range(10, 17)]
    if any(((ts >= a) & (ts < b)).sum() == 0 for a, b in zip(cuts, cuts[1:])):
        return False
    if not rec["filled"]:
        return True
    side = 1 if rec["side"] == "long" else -1
    sl = rec["entry_price"] - side * rec["sl"]
    tp = rec["entry_price"] + side * rec["tp"]
    same = tape[ts == rec["entry_ns"]]
    first = int(np.flatnonzero(ts == rec["entry_ns"])[0])
    entry_row = first + int(np.flatnonzero(
        (same[:, 1] >= rec["anchor"] + rec["offset"]) | (same[:, 1] <= rec["anchor"] - rec["offset"]))[0])
    for px in tape[first:entry_row, 1]:
        if (side == 1 and (px <= sl or px >= tp + R.TICK)) or (side == -1 and (px >= sl or px <= tp - R.TICK)):
            return False
    return True


def category(rec: dict) -> str | None:
    if not rec["filled"]:
        return "no_fill"
    side = 1 if rec["side"] == "long" else -1
    slip = rec["slip_ticks"] * R.TICK
    trig = rec["anchor"] + side * rec["offset"]
    if rec["why"] == "FLAT":
        return "time_exit"
    if abs(rec["entry_price"] - (trig + side * slip)) > 1e-9:
        return "gap_entry"
    sl_lvl = rec["entry_price"] - side * rec["sl"]
    if rec["why"] == "SL" and abs(rec["exit_price"] - (sl_lvl - side * slip)) > 1e-9:
        return "sl_gap"
    return f"{rec['why'].lower()}_{rec['side']}"


WANT = {"tp_long": 2, "tp_short": 2, "sl_long": 2, "sl_short": 2, "gap_entry": 3,
        "sl_gap": 2, "no_fill": 3}


def select() -> None:
    days = sorted(set(R.sessions(dt.date(2022, 1, 1), dt.date(2024, 12, 31))))
    random.Random(20260926).shuffle(days)
    got: dict[str, list] = {k: [] for k in [*WANT, "time_exit", "slip0_tp", "slip0_sl"]}
    for d in days:
        if all(len(got[k]) >= WANT.get(k, 3 if k == "time_exit" else 1) for k in got):
            break
        rec = replay(d, *BASE, 1.0)
        if rec is None or not clean(rec, d):
            continue
        c = category(rec)
        if c in WANT and len(got[c]) < WANT[c]:
            got[c].append((d.isoformat(), *BASE, 1.0, c))
            continue
        if len(got["no_fill"]) < WANT["no_fill"]:
            n = replay(d, *NOFILL, 1.0)
            if n and not n["filled"] and clean(n, d):
                got["no_fill"].append((d.isoformat(), *NOFILL, 1.0, "no_fill"))
                continue
        if len(got["time_exit"]) < 3:
            w = replay(d, *WIDE, 1.0)
            if w and w["filled"] and w["why"] == "FLAT" and clean(w, d):
                got["time_exit"].append((d.isoformat(), *WIDE, 1.0, "time_exit"))
                continue
        for k, why in (("slip0_tp", "TP"), ("slip0_sl", "SL")):
            if not got[k]:
                z = replay(d, *BASE, 0.0)
                if z and z["filled"] and z["why"] == why and clean(z, d):
                    got[k].append((d.isoformat(), *BASE, 0.0, k))
                    break
    for k, v in got.items():
        for c in v:
            print(f"    {c!r},")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true")
    if ap.parse_args().select:
        select()
        return
    assert CASES, "run --select first and paste its output into CASES"
    rows = []
    for d, off, sl, tp, slip_t, cat in CASES:
        rec = replay(dt.date.fromisoformat(d), off, sl, tp, slip_t)
        assert rec is not None, d
        rec.pop("_tape")
        rows.append({**rec, "category": cat})
    OUT.write_text(json.dumps({"source": "research/nq_930_straddle_ticks.py replay_day",
                               "point_value": R.PV, "commission": R.COMM,
                               "placement_ms": R.PLACEMENT_MS, "cases": rows}, indent=1) + "\n")
    print(f"{len(rows)} cases -> {OUT}")


if __name__ == "__main__":
    main()
