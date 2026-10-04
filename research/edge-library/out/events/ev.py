"""STAGE 3 day labels (EDGE_SPEC "STAGE 3 — NEW-IDEA ROUND 2: EVENT STRADDLES"). Calendar only: engine/cache/events.csv
(official release dates; never checked against the tape). Nothing dated on / after 2025-01-01 is ever returned.
FIXED BEFORE ANY EVENT-SPLIT NUMBER WAS READ (2026-10-04):
  A   every day with a calendar row at 08:30 ET (NFP, CPI, PPI, RETAIL, GDP, PCE, CLAIMS)
  B   tier-1 only: a row at 08:30 ET of NFP, CPI, PPI, RETAIL, GDP or PCE
  C   every day with a calendar row at 10:00 ET (ISM_MFG, ISM_SVC, JOLTS, UMICH; PCE on the two days it came out at 10:00:
      "every 10:00 release day" read literally; a PCE released at 10:00 is NOT an 08:30 release)
  non-event days of test (c): days with NO calendar row at the unit's clock time (the complement of A for E1 / E2 in both
      groups A and B; the complement of C for E3). For B the lift over "every day outside B" is printed as information.
  bars of test (d), as written in the section: NQ 2.56 and GC 1.63 = the checker's pooled random-minute bars
      (out/check_r1/check_gates.json shift_all-*), ES = out/admit/null_bars.json shift-ES. The stage-1 file's own NQ / GC
      numbers (2.616 / 1.639) are printed beside them; a unit whose verdict hangs on the difference is flagged."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))

EVENTS = W / "engine" / "cache" / "events.csv"
SEAL = "2025-01-01"
T0830 = ("NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE", "CLAIMS")
TIER1 = ("NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE")
T1000 = ("ISM_MFG", "ISM_SVC", "JOLTS", "UMICH")
GROUP_TIME = {"A": "08:30", "B": "08:30", "C": "10:00"}
PLAIN = {"A": "days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims)",
         "B": "days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out)",
         "C": "days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim)"}
UNITS = [("E1", "straddle_tight_0830", "pre", ("A", "B")), ("E2", "straddle_t_0830", "pre", ("A", "B")),
         ("E3", "straddle_tight_1000", "nyam", ("C",))]
ROOTS = ("NQ", "ES", "GC")
_BARS = json.loads((W / "out" / "check_r1" / "check_gates.json").read_text())["bars"]
_S1 = json.loads((W / "out" / "admit" / "null_bars.json").read_text())
BAR = {"NQ": _BARS["shift_all-NQ"]["bar"], "GC": _BARS["shift_all-GC"]["bar"], "ES": _S1["shift-ES"]["bar"]}
BAR_S1 = {r: _S1[f"shift-{r}"]["bar"] for r in ROOTS}
ALPHA = 1.0 - 0.05 / 15.0                         # 99.67 %: test (e) pays for 15 units
DRAWS = 4000
# 2024 was ALREADY READ for these (the section's NOTE): a member from them is SECOND LOOK on 2024
SECOND_LOOK = {("straddle_tight_0830", "NQ"): "2024 was already read for straddle_tight_0830 NQ on all days (stage 2b)",
               ("straddle_tight_0830", "GC"): "2024 was already read for straddle_tight_0830 GC on all days (stage 2b)",
               ("straddle_t_0830", "NQ"): "2024 was already read for straddle_t_0830 NQ on CPI / NFP / FOMC days (stage 2a)"}


def rows() -> list:
    with EVENTS.open() as fh:
        return [r for r in csv.DictReader(fh) if r["date"] < SEAL]


_MEMO: dict = {}


def days(group: str) -> set:
    """ISO dates (< 2025) of an event group A / B / C, or of one type at its listed time: 'NFP', ..., 'FOMC' (14:00)."""
    if group not in _MEMO:
        R = rows()
        if group == "A":
            s = {r["date"] for r in R if r["time_et"] == "08:30"}
        elif group == "B":
            s = {r["date"] for r in R if r["time_et"] == "08:30" and r["type"] in TIER1}
        elif group == "C":
            s = {r["date"] for r in R if r["time_et"] == "10:00"}
        elif group == "FOMC":
            s = {r["date"] for r in R if r["type"] == "FOMC"}
        elif group in T0830:
            s = {r["date"] for r in R if r["type"] == group and r["time_et"] == "08:30"}
        elif group in T1000:
            s = {r["date"] for r in R if r["type"] == group and r["time_et"] == "10:00"}
        else:
            raise ValueError(group)
        assert all(d < SEAL for d in s)
        _MEMO[group] = s
    return _MEMO[group]


def ords(group: str) -> np.ndarray:
    return np.array(sorted(dt.date.fromisoformat(d).toordinal() for d in days(group)), np.int64)


def mask(group: str, date) -> np.ndarray:
    """Trades (by trade-date ordinal) on the group's days."""
    return np.isin(np.asarray(date, np.int64), ords(group))


def solo(typ: str) -> set:
    """Days on which `typ` is the ONLY calendar row at its clock time."""
    R = rows()
    t = "10:00" if typ in T1000 else "08:30"
    by: dict = {}
    for r in R:
        if r["time_et"] == t:
            by.setdefault(r["date"], set()).add(r["type"])
    return {d for d, s in by.items() if s == {typ}}
