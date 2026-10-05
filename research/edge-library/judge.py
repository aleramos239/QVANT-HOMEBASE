#!/usr/bin/env python3
"""judge.py -- ADMISSION v2 as ONE permanent tool: a unit in -> verdict + card out (EDGE_SPEC "WORKBENCH PLAN" 1).
The rule: EDGE_SPEC "USER DIRECTION -- CORRECTION AND ADMISSION v2" (judge the AVERAGE of all variants), "PERIODS AMENDED"
(BUILD 2021-09-22..2023 -> PICK 2024 -> CHECK 2025, each year judged ON ITS OWN; EXAM 2026+ sealed: no entry here) and
"ADMISSION v2 -- CHECKER FIXES" F1-F6 (4,000 draws, every control seed on disk, strict 60 %, two speed shares, the BUILD variant
list on a later year, every store used is logged). Built from out/v2/ and locked to its numbers by tests/test_judge.py (`--as-v2`).
It only READS stores (runs*/<key>/): it never launches a simulation and never opens a period by itself. Doc: JUDGE.md.

  judge.py build <unit> [...]                 tests (1)-(3) on BUILD, one line per unit
  judge.py year  <unit> --period pick|check   tests (4)-(6) for that year on its own (+ the surviving set and default on pick)
  judge.py card  <unit> [--out DIR]           member card + surviving_set.csv (a row per period that exists)
  judge.py table [unit ...] [--stage s1,r1,ev,en,2a|members|placebo|all|<catalog.csv>] [--out PREFIX]   CSV + markdown
  every command: [--draws N] [--seeds N] [--upto build|pick|check] [--as-v2]   (defaults: 4,000 draws, every seed and year on disk)
  --exam = the explicit EXAM flag: `year --period exam` / `card` read 2026 for a unit on out/exam2026/allowed.json, and only for those

A UNIT = <family>-<ROOT>-tf<tf>-<session>[:<axis>=<value>][@<day filter>], e.g. orb-NQ-tf15-pre, gap-ES-tf15-nyam:mode=fill,
straddle_tight_0830-NQ-tf30-pre@A. The v2 uid `orb-NQ-tf15|pre|` is accepted too. `c1-NQ-tf1-eve:seed=2` = a PLACEBO unit
(one seed of the random-entry store judged as if it were a strategy; its control is the other seeds).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import zlib
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parent
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import library as LB  # noqa: E402

# ================================================================ THE RULE: every threshold, with the spec text it comes from
SHARE = 0.60        # (1) "> 60 % of variants profitable and the AVERAGE variant profitable". CHECKER FIX F3: strict, > 60 %
#                         (out/v2 read it as >= 60 %; a unit at exactly 60 % is flagged `exact60` and now fails (1))
DRAW_FLOOR = 0.50   # test (2) is drawn only for a positive average with >= 50 % of variants profitable (out/v2/judge_build.py:
#                         the near-misses of (1) are known; every other unit fails (1) and its control is not drawn)
P_NEED = 0.95       # (2) "beats the average of the same table run with random entries ... and beats >= 95 % of the random
#                         replicates' table averages" (BUILD: lift > 0 AND 95 %; a year: (5) "lift > 0" only)
DRAWS = 4000        # F1: "Test (2) uses 4,000 random draws for every unit (200 was a coin flip within ~2 points of the 95 % line)"
BLOCK = 200         # draws come in blocks of 200; block i uses the unit's seed + i. So `--draws 200` = out/v2's own draws (the
#                         checker's "seed 0") and 4,000 = the checker's 20 seeds (out/check_v2/chk_seed.py), draw for draw
SUBSETS = 4000      # random same-size day subsets of a day filter (already 4,000 in out/v2)
THIN_BELOW = 10     # F2: "the random-entry pools and the random-minute / random-direction stores have 10 seeds ...; the judge uses
#                         every seed on disk". A control with fewer real seeds is THIN and says so. A unit that passes all six with
#                         the first 2 seeds but fails a real-edge test -- (2) on BUILD (F2's words) or (5) on a year (the same
#                         reading, applied here) -- with every seed is DEMOTED: "luck not excluded", kept on file, not edge
MIN_TRADES = LB.MIN_TRADES   # (3) "the trade minimum, on the average variant's trade count": 100. On BUILD = the BUILD count
#                         scaled to BUILD + PICK at the same trades-per-day rate; re-checked on the real count once PICK is open
FAST_S = 5          # part A: "more than 50 % of your profits ... from trades held for 5 seconds or less": on the card, NOT a gate.
FAST_LIMIT = 0.50   # F4: two shares -- fast winners / all winners (gross) and net of the fast trades / total net; the FAST flag = net
OCO_MS = 100        # part C: stress of a two-sided bracket = 2 ticks + 250 ms + a 100 ms late cancel of the other side
SAME_SIDE, SAME_DAYS = 0.70, 30   # two members are the SAME IDEA (one per stack) when their defaults take the same side on >= 70 %
#                         of >= 30 shared trading days, or share family + market + session (out/v2/admit_v2.py group_ideas)
# (4) the AVERAGE of ALL variants is profitable and the median variant is profitable; (5) lift > 0 against every control used on
# BUILD; (6) the average stays profitable under stress. F5: a later year judges the BUILD variant list (no second de-duplication).
# SAVED = every variant profitable on BUILD, the year, and under stress in both. DEFAULT = the MIDDLE survivor by BUILD net:
# sorted by (BUILD net, vi, xi), index (n - 1) // 2 (never the best).
# CHECK verdicts ("PERIODS AMENDED"): CONFIRMED (4)+(5)+(6) / WEAK (average profitable, a test fails) / FAILED (average not profitable).
# RULE = the rule in force. seeds None = every control seed on disk; dirs None = every runs*/ folder; upto None = every year on disk
# exam False = the EXAM period (2026+) stays sealed. `--exam` sets it True: `year --period exam` then judges ONE unit that is on
# out/exam2026/allowed.json (EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES": members that pass (4)-(6) on 2025), nothing else.
RULE = {"draws": DRAWS, "seeds": None, "strict": True, "dedup_year": False, "dirs": None, "upto": None, "exam": False}

PERIODS = {"build": {"name": "BUILD", "range": ("2021-09-22", "2023-12-31"), "tag": "build"},
           "pick": {"name": "2024", "range": ("2024-01-01", "2024-12-31"), "tag": "pick"},
           "check": {"name": "2025", "range": ("2025-01-01", "2025-12-31"), "tag": "check"},
           "exam": {"name": "2026", "range": ("2026-01-01", "2026-12-31"), "tag": "exam"}}   # SEALED: exam_gate() opens it per unit
YEARS = ("pick", "check", "exam")             # judged in this order; a year is read only after everything before it passed
ALLOWED = W / "out" / "exam2026" / "allowed.json"   # the units 2026 may be read for + the last complete session per market
# A store belongs to the period its own date range lies in. Stores are looked for in every runs*/ folder: these first, in this
# order (out/v2's order), then any other (runs_check2025/, a folder of extra control seeds, ...). runs_void/ is never read.
PRIORITY = ("runs", "runs_v2", "runs_admit", "runs_admit_r1", "runs_deepen", "runs_events")
EARLIER = ("runs_admit", "runs_admit_r1", "runs_deepen", "runs_events")   # stages before v2: a store from them is RE-USED
VOID = ("runs_void",)
EXTRA_DIRS: list = []                         # more store folders (the tests add a temporary one)
# `--as-v2` = exactly as out/v2 coded and ran it (its six folders, BUILD + 2024 only): the regression lock, never a verdict
AS_V2 = {"draws": 200, "seeds": 2, "strict": False, "dedup_year": True, "dirs": PRIORITY, "upto": "pick"}
RUNNER = {"build": "python run_menus.py run --family <family> --roots <ROOT> --tf <tf>   (+ `run_menus.py nulls` for the c1 pool)",
          "pick": "python out/v2/run_v2.py run <jobs.json>   (stores -> runs_v2/, every 2024 read logged in out/v2/pick_reads.csv)",
          "check": "the 2025 runner of EDGE_SPEC \"PERIODS AMENDED\" (same job format with period \"check\"; stores as "
                   "<key>-<sess>-check[-stress|-shift|-c2sN] and c1-<ROOT>-tf<tf>-<sess>-check in a runs*/ folder; reads logged in out/check2025/reads.csv)",
          "exam": "python out/exam2026/run_exam.py run <jobs.json>   (allowed units only, allow_exam=True; stores -> runs_exam2026/ as "
                  "<key>-<sess>-exam[-stress|-shift] and c1-<ROOT>-tf<tf>-<sess>-exam; reads logged in out/exam2026/reads.csv)"}
EVENTS_CSV = W / "engine" / "cache" / "events.csv"
EXAM_START = "2026-01-01"                     # no calendar row on / after this is returned unless RULE["exam"] is True
TIER1 = ("NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE")
EVENT_GROUPS = {   # EDGE_SPEC "STAGE 3": (clock time of the calendar row, types or None = every type, plain words)
    "A": ("08:30", None, "days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims)"),
    "B": ("08:30", TIER1, "days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out)"),
    "C": ("10:00", None, "days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim)"),
}
SIDE_FILTERS = ("adx_hi", "adx_lo", "vol_hi", "vol_lo", "news_only", "news_never")   # EDGE_SPEC "STAGE 2a": out/deepen/labels.py
LEGACY_CODE = {"straddle_tight_0830": "E1", "straddle_t_0830": "E2", "straddle_tight_1000": "E3", "straddle_wide_0830": "W",
               "straddle_wide_1000": "W", "event_dir_0830": "D", "event_dir_1000": "D"}   # v2's uids = the seed names of its draws
CATALOGS = {"s1": "out/admit/build_units.csv", "r1": "out/admit_r1/build_units.csv", "ev": "out/events/build_units.csv",
            "en": "out/entries/build_units.csv"}
STAGE_2A = ("donchian-NQ-tf5-nyam@vol_lo", "straddle_t_0830-NQ-tf30-pre@news_only")
EARLIER_READS = ("admit", "admit_r1", "deepen", "events")     # out/<stage>/pick_reads.csv: 2024 reads before v2
READ_LOG = W / "out" / "judge" / "year_reads.csv"             # F6: every store a `judge.py year` verdict rests on
U64, MAXU = np.uint64, np.iinfo(np.uint64).max


class Refuse(Exception):
    """The judge will not answer (a store is missing, a period is sealed, a stage before it failed). `jobs` = what to run."""

    def __init__(self, msg: str, jobs: list | None = None):
        super().__init__(msg)
        self.jobs = jobs or []


def money(v) -> str:
    return "n/a" if v is None else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def pct(v, nd: int = 0) -> str:
    return "n/a" if v is None else f"{round(100 * v, nd) + 0.0:.{nd}f} %"


def share_ok(sp: float) -> bool:
    """Test (1)'s share: more than 60 % (F3); `--as-v2`: 60 % or more."""
    return sp > SHARE + 1e-12 if RULE["strict"] else sp >= SHARE - 1e-12


# ================================================================ units

ADDR = re.compile(r"^(?P<family>[A-Za-z0-9_]+)-(?P<root>[A-Z0-9]+)-tf(?P<tf>\d+)-(?P<sess>eve|asia|london|pre|nyam|mid|pm|all)"
                  r"(?::(?P<label>[^@|]+))?(?:@(?P<filt>\w+))?$")
_META: dict = {}


def build_meta(key: str) -> dict:
    if key not in _META:
        p = LB.RUNS / key / "run.json"
        if not p.exists():
            raise Refuse(f"no BUILD store runs/{key}: run the BUILD menu and its control first: {RUNNER['build']}")
        _META[key] = json.loads(p.read_text())
    return _META[key]


def unit(addr: str) -> dict:
    """A unit address (module docstring) or a v2 uid `key|sess|label[|side]` -> the unit: its BUILD store key, session, mirror
    label, day filter, and its TYPE (time-fired / Level 2 / Level 2 option / placebo), which fixes its controls:
      bar-based -> c1 · time-fired -> shift · Level 2 -> + c2 · Level 2 option of a base family -> + base · day filter -> days first."""
    addr = addr.strip()
    if "|" in addr:
        p = addr.split("|") + ["", ""]
        fam_key, sess, label, filt = p[0], p[1], p[2], p[3] or None
        m = re.match(r"^(?P<family>.+)-(?P<root>[A-Z0-9]+)-tf(?P<tf>\d+)$", fam_key)
        if not m:
            raise Refuse(f"unit {addr!r}: not <family>-<ROOT>-tf<tf>|<session>|<label>")
        family, root, tf = m["family"], m["root"], m["tf"]
    else:
        m = ADDR.match(addr)
        if not m:
            raise Refuse(f"unit {addr!r}: expected <family>-<ROOT>-tf<tf>-<session>[:<axis>=<value>][@<day filter>]")
        family, root, tf, sess, label, filt = m["family"], m["root"], m["tf"], m["sess"], m["label"] or "", m["filt"]
    if filt and filt not in EVENT_GROUPS and filt not in SIDE_FILTERS:
        raise Refuse(f"unit {addr!r}: day filter {filt!r} is not one of {sorted(EVENT_GROUPS)} / {list(SIDE_FILTERS)}")
    key = f"{family}-{root}-tf{tf}"
    meta = build_meta(key)
    placebo = (int(label[5:]) if re.fullmatch(r"seed=\d", label) else -1) if family == "c1" else 0
    if family == "c1" and (placebo not in (1, 2) or filt):
        raise Refuse(f"unit {addr!r}: a placebo unit is c1-<ROOT>-tf<tf>-<session>:seed=1|2")
    fam = meta.get("family", family)                      # the registered family name (the c1 pool's is 'random')
    base = meta.get("base") or None
    timed, penalty = False, False
    if not placebo:
        import families as F
        timed = "shift_seed" in F.REGISTRY[base or fam][0].defaults()          # run_menus.is_time_fired
        penalty = bool(F.penalty_for(base or fam, None if sess == "all" else sess))
    l2 = bool(base) or bool(meta.get("features"))
    ctl = (["days"] if filt else []) + (["shift"] if timed else ["c1"]) + (["c2"] if l2 else []) + (["base"] if base else [])
    group, side = (filt if filt in EVENT_GROUPS else None), (filt if filt in SIDE_FILTERS else None)
    if placebo:
        uid = f"placebo-{key}|{sess}|seed{placebo}"
    elif group and fam in LEGACY_CODE:
        uid = f"{LEGACY_CODE[fam]}-{group}-{root}"
    else:
        uid = f"{key}|{sess}|{label}" + (f"|{filt}" if filt else "")
    name = f"{fam}_{root}_tf{tf}_{sess}" + (f"_{label.replace('=', '')}" if label else "") + (f"_ev{group}" if group else "") + (
        f"_{side}" if side else "")
    return {"addr": f"{key}-{sess}" + (f":{label}" if label else "") + (f"@{filt}" if filt else ""), "uid": uid, "name": name, "key": key,
            "family": fam, "base": base, "root": root, "tf": str(tf), "sess": sess, "label": label, "filter": filt, "group": group,
            "side": side, "timed": timed, "l2": l2, "stage_d": bool(base), "weak": bool(meta.get("weak")), "penalty": penalty,
            "placebo": placebo, "controls": ctl}


def catalog(stage: str) -> list:
    """Unit addresses of a stage: s1 / r1 / ev / en (the stage catalogs v2 judged), 2a, members, placebo, all (= the 1,916 of
    out/v2), or a path to a catalog CSV with columns key (or family + root [+ tf]), sess [, label] [, group | side]."""
    if stage == "all":
        return [a for s in ("s1", "r1", "ev", "en", "2a") for a in catalog(s)]
    if stage == "2a":
        return list(STAGE_2A)
    if stage == "placebo":
        return [f"c1-{r}-tf{tf}-{s}:seed={k}" for r in ("NQ", "ES", "GC") for tf in ("1", "5", "15", "30") for s in LB.SESS7 for k in (1, 2)]
    if stage == "members":
        out = []
        for d in sorted(p for p in LB.MEMBERS.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "spec.json").exists()):
            out.append(spec_addr(json.loads((d / "spec.json").read_text())))
        return out
    path = W / CATALOGS[stage] if stage in CATALOGS else Path(stage)
    if not path.exists():
        raise Refuse(f"stage {stage!r}: one of {sorted(CATALOGS)} / 2a / members / placebo / all, or a catalog CSV")
    out = []
    for r in csv.DictReader(path.open()):
        key = r.get("key") or f"{r['family']}-{r['root']}-tf{r.get('tf') or 30}"
        filt = r.get("group") or r.get("side") or ""
        out.append(f"{key}-{r['sess']}" + (f":{r['label']}" if r.get("label") else "") + (f"@{filt}" if filt else ""))
    return out


def spec_addr(s: dict) -> str:
    filt = s.get("group") or s.get("side")
    return f"{s['family']}-{s['root']}-tf{s['tf']}-{s['sess']}" + (f":{s['label']}" if s.get("label") else "") + (f"@{filt}" if filt else "")


# ================================================================ days: calendars and day filters

_CAL: dict = {}
_EV: dict = {}


def calendar(period: str, root: str) -> list:
    """ISO session dates of a period for a root. BUILD / PICK: the engine's session calendar (as out/v2). A later year: every
    weekday of its range -- fixed, it needs no engine and reads no data (a day without a trade is a 0 day wherever a calendar
    is used: day-mixes, drawdowns)."""
    if (period, root) not in _CAL:
        if period in ("build", "pick"):
            _CAL[(period, root)] = LB.calendar(period, root)
        else:
            a, b = (dt.date.fromisoformat(x) for x in PERIODS[period]["range"])
            if period == "exam":                            # to the last complete session on disk of that market (allowed.json)
                b = dt.date.fromisoformat(exam_allowed()["period"]["end"][root])
            _CAL[(period, root)] = [(a + dt.timedelta(n)).isoformat() for n in range((b - a).days + 1) if (a + dt.timedelta(n)).weekday() < 5]
    return _CAL[(period, root)]


def exam_allowed() -> dict:
    """out/exam2026/allowed.json: {"units": [addresses 2026 may be read for], "period": {"end": {ROOT: last session}}}. Written
    once from the 2025 verdicts, BEFORE the first 2026 run. Missing = nothing is allowed."""
    if not ALLOWED.exists():
        raise Refuse(f"the EXAM period (2026+) is sealed: {ALLOWED.relative_to(W)} does not exist, so no unit may be read on it")
    return json.loads(ALLOWED.read_text())


def exam_gate(u: dict) -> None:
    """The EXAM seal of the judge. 2026 is read only with the explicit exam flag (RULE['exam'] is True, `--exam`) AND only for a
    unit listed in allowed.json; anything else is refused before a single 2026 store is looked at."""
    if RULE.get("exam") is not True:
        raise Refuse("the EXAM period (2026+) is sealed: it is judged only with the explicit exam flag (--exam)")
    if u["addr"] not in exam_allowed().get("units", []):
        raise Refuse(f"the EXAM period (2026+) is sealed for {u['addr']}: it is not on the allowed list {ALLOWED.relative_to(W)} "
                     "(members under the rule in force that pass tests (4)-(6) on 2025)")


def event_ords(group: str) -> np.ndarray:
    """Ordinals of the days of an event group (calendar rows only; nothing dated in the EXAM period is returned unless the
    exam flag is set)."""
    k = (group, RULE.get("exam") is True)
    if k not in _EV:
        at, types, _ = EVENT_GROUPS[group]
        with EVENTS_CSV.open() as fh:
            days = {r["date"] for r in csv.DictReader(fh) if (k[1] or r["date"] < EXAM_START) and r["time_et"] == at and (types is None or r["type"] in types)}
        _EV[k] = np.array(sorted(dt.date.fromisoformat(d).toordinal() for d in days), np.int64)
    return _EV[k]


def day_mask(u: dict, date, side=None) -> np.ndarray:
    """Trades (by trade-date ordinal) inside the unit's day filter (all True without one)."""
    date = np.asarray(date)
    if u["group"]:
        return np.isin(date.astype(np.int64), event_ords(u["group"]))
    if u["side"]:
        if str(W / "out" / "deepen") not in sys.path:
            sys.path.insert(0, str(W / "out" / "deepen"))
        import labels as L                                 # the stage-2a labels (daily bars before D only; sealed at 2025-01-01)
        return L.side_mask(u["side"], u["root"], date, np.zeros(len(date)) if side is None else side)
    return np.ones(len(date), bool)


def scope_days(u: dict, period: str) -> np.ndarray:
    cal = LB._ordinals(calendar(period, u["root"]))
    return cal[day_mask(u, cal)]


# ================================================================ stores: the index, tables

_INDEX: list = []
_IDXKEY: list = []
_BYKEY: dict = {}
_STORE: dict = {}
_REF: dict = {}


def reset() -> None:
    """Forget what was read from disk (stores are added while a round runs)."""
    for c in (_INDEX, _IDXKEY, _BYKEY, _STORE, _REF, _META):
        c.clear()


def _sig(c: dict) -> int:
    """Fingerprint of a control cell's inputs without its seed and session: two cells with the same one are the same control."""
    return zlib.crc32(json.dumps({k: v for k, v in (c.get("inputs") or {}).items() if k not in ("seed", "shift_seed", "sess")}, sort_keys=True).encode())


def index() -> list:
    """Every store under runs*/ (never runs_void/), from its run.json, read once: where it is, the date range it covers, whether
    it is a control (c1 random entries / shift random minute or direction / c2 shuffled book) and which seeds it holds."""
    key = (RULE["dirs"], tuple(str(d) for d in EXTRA_DIRS))
    if _IDXKEY != [key]:
        for c in (_INDEX, _BYKEY, _REF):
            c.clear()
        _IDXKEY[:] = [key]
        dirs = [W / n for n in (RULE["dirs"] or PRIORITY)]
        dirs += [] if RULE["dirs"] else sorted(d for d in W.glob("runs*") if d.is_dir() and d.name not in PRIORITY + VOID)
        for d in dirs + [Path(d) for d in EXTRA_DIRS]:
            for p in sorted(d.glob("*/run.json")):
                m = json.loads(p.read_text())
                rg, cells = m.get("range") or {}, m.get("cells") or []
                ctl = m.get("control") if m.get("control") in ("c1", "shift", "c2") else None
                ks = re.search(r"-c2s(\d+)$", p.parent.name)
                ids, pre = {c["id"] for c in cells}, {}
                for c in cells if ctl in ("c1", "shift") else []:   # a control seed = the cell's own seed input; s<n>_ = its id prefix
                    q = re.match(r"s(\d+)_", c["id"])
                    if q:
                        pre.setdefault(int((c.get("inputs") or {}).get("seed" if ctl == "c1" else "shift_seed") or q[1]), q[0])
                r = {"dir": d, "key": p.parent.name, "start": str(rg.get("start") or ""), "end": str(rg.get("end") or ""), "control": ctl,
                     "family": m.get("family"), "root": m.get("root"), "tf": str(m.get("tf")), "sess": m.get("sess_instance"),
                     "stress": bool(m.get("stress")), "oco": m.get("oco_cancel_ms") or 0, "ids": ids,
                     "seed": m.get("seed") or (int(ks[1]) if ks else None),
                     "pre": pre,
                     "sig": {c["id"]: _sig(c) for c in cells} if ctl in ("c1", "shift") else {}}
                _INDEX.append(r)
                _BYKEY.setdefault(r["key"], []).append(r)
    return _INDEX


def in_period(r: dict, period: str) -> bool:
    a, b = PERIODS[period]["range"]
    return bool(r["start"]) and a <= r["start"] and r["end"] <= b


def where(r: dict) -> str:
    return f"{r['dir'].name}/{r['key']}"


def store(r: dict) -> dict:
    k = (str(r["dir"]), r["key"])
    if k not in _STORE:
        if len(_STORE) > 40:
            _STORE.clear()
        s = LB.load_unit(r["key"], r["dir"])
        s["_idx"] = {c["id"]: i for i, c in enumerate(s["meta"]["cells"])}
        _STORE[k] = s
    return _STORE[k]


def find(key: str, period: str, ok=None):
    """The first store `key` whose date range lies inside `period` (and that `ok` accepts) -> (store, its index row) or (None, None)."""
    index()
    for r in _BYKEY.get(key, []):
        if in_period(r, period) and (ok is None or ok(r)):
            return store(r), r
    return None, None


def build_store(u: dict):
    s, r = find(u["key"], "build", lambda r: r["dir"] == LB.RUNS)
    if s is None:
        raise Refuse(f"no BUILD store runs/{u['key']}: run the BUILD menu and its control first: {RUNNER['build']}")
    return s, r


def skey(stem: str, u: dict, period: str, suffix: str = "") -> str:
    """Store key of `stem` for a period: BUILD stores hold every session, a year's store one session (<stem>-<sess>-<tag>)."""
    return stem + ("" if period == "build" else f"-{u['sess']}-{PERIODS[period]['tag']}") + suffix


def stress_store(u: dict, period: str, need: list):
    """The unit's menu under stress on a period (<key>-<sess>-<tag>-stress): 2 ticks + 250 ms, + the 100 ms late cancel for a
    two-sided bracket (a stress store without it is not used), holding every variant in `need`. -> (store, row) or (None, None)."""
    two = bool(build_meta(u["key"]).get("both_sides_declared"))
    return find(f"{u['key']}-{u['sess']}-{PERIODS[period]['tag']}-stress", period,
                lambda r: r["stress"] and (not two or r["oco"] == OCO_MS) and all(c in r["ids"] for c in need))


def _ref(kind: str, fam: str, root: str, tf: str) -> dict:
    """{cell id without its seed: inputs fingerprint} of the BUILD control: what "the same control, another seed" must match."""
    k = (kind, fam, root, tf)
    if k not in _REF:
        _REF[k] = {}
        for r in index():
            if r["control"] == kind and r["family"] == fam and r["root"] == root and r["tf"] == tf and not r["stress"] and r["pre"] and in_period(r, "build"):
                pre = r["pre"][min(r["pre"])]
                _REF[k] = {i[len(pre):]: g for i, g in r["sig"].items() if i.startswith(pre)}
                break
    return _REF[k]


def seed_stores(u: dict, period: str, kind: str, need: list) -> dict:
    """F2: EVERY seed of a control on disk for the unit and period -> {seed: (index row of the store that holds it, the id
    prefix of its cells)}. c1: stores of random entries (run.json control c1) of the unit's market and bar size with cells
    s<n>_<exit> for every exit in `need`; shift: the family's random-minute / random-direction stores with cells s<n>_<variant>;
    c2: the unit's shuffled-book stores (<key>...-c2s<seed>). The seed is the cell's own seed input. A seed counts when its store
    covers the period and the unit's session, holds every cell needed and is the same control as the BUILD one (same inputs but
    the seed). First folder in order wins a seed."""
    fam = "random" if kind == "c1" else (u["family"] if kind == "c2" else u["base"] or u["family"])
    ref, out = _ref(kind, fam, u["root"], u["tf"]), {}
    for r in index():
        if r["control"] != kind or r["family"] != fam or r["root"] != u["root"] or r["tf"] != u["tf"] or r["stress"] or not in_period(r, period):
            continue
        if r["sess"] not in (None, u["sess"]):
            continue
        if kind == "c2":
            if r["seed"] is not None and all(c in r["ids"] for c in need):
                out.setdefault(int(r["seed"]), (r, ""))
            continue
        for sd, pre in r["pre"].items():
            if sd not in out and all(pre + x in r["ids"] and r["sig"][pre + x] == ref.get(x, r["sig"][pre + x]) for x in need):
                out[sd] = (r, pre)
    keep = sorted(out)[:RULE["seeds"]] if RULE["seeds"] else sorted(out)
    return {sd: out[sd] for sd in keep}


def cellx(st: dict, cid: str, sess, u: dict | None = None) -> dict:
    """One cell's trades in a session (None / 'all' = every session) and inside the unit's day filter."""
    i = st["_idx"][cid]
    a, b = int(st["off"][i]), int(st["off"][i + 1])
    x = {k: st[k][a:b] for k in LB.FIELDS}
    m = np.ones(b - a, bool) if sess in (None, "all") else x["sess"] == LB.SESS_CODE[sess]
    if u is not None and u["filter"]:
        m = m & day_mask(u, x["date"], x["side"])
    return {k: v[m] for k, v in x.items()}


def table(st: dict, u: dict) -> list:
    """The unit's table on its BUILD store: library.session_table rows of its session and mirror label (a placebo: one seed's
    rows); with a day filter net / trades / sig are recomputed on the kept trades. `dead` stays the structural flag."""
    if u["placebo"]:
        rows = [dict(r) for r in LB.session_table(st, u["sess"]) if r["id"].startswith(f"s{u['placebo']}_")]
    else:
        rows = [dict(r) for r in LB.plateau_units(st, u["sess"])[u["label"]]]
    if u["filter"]:
        for r in rows:
            x = cellx(st, r["id"], u["sess"], u)
            s = LB.stats(x["net"])
            r.update(net=s["net"], trades=s["trades"], t=s["t"], sig=LB.trade_sig(x))
    return rows


def table_on(st: dict, u: dict, ref_rows: list) -> list:
    """The unit's table on another store (a year, stress). F5: the BUILD variant list -- the variants judged on BUILD, each
    with its net and trades from `st`, no second de-duplication. `--as-v2`: the BUILD rows' ids and dead / author flags, then
    de-duplicated again on `st`'s own trade lists (what out/v2 did). A needed variant missing from `st` = refused."""
    keep = None if RULE["dedup_year"] else set(table_stats(ref_rows)["ids"])
    out = []
    for r in ref_rows:
        if keep is not None and r["id"] not in keep:
            continue
        if r["id"] not in st["_idx"]:
            if not (r.get("dead") or r.get("info")):
                raise Refuse(f"store {st['meta'].get('key')} lacks the live variant {r['id']} of {u['addr']}: re-run the WHOLE menu")
            continue
        x = cellx(st, r["id"], u["sess"], u)
        s = LB.stats(x["net"])
        out.append({**{k: r.get(k) for k in ("id", "vi", "xi", "stop_mode", "tgt_r", "dead", "info")}, "net": s["net"], "trades": s["trades"],
                    "t": s["t"], "sig": LB.trade_sig(x) if keep is None else None})
    return out


def table_stats(rows: list) -> dict:
    """The judged table (library.judged_rows: dead and author cells out, identical trade lists once) -> its numbers."""
    j, n_dead, n_dup = LB.judged_rows(rows)
    if not j:
        return {"cells": 0, "ids": [], "share_pos": None, "avg_net": None, "median_net": None, "avg_trades": 0.0, "positive": 0,
                "dead": n_dead, "dup": n_dup, "v60": False, "v70": False, "v80": False}
    net = np.array([float(r["net"]) for r in j])
    tr = np.array([int(r["trades"]) for r in j])
    sp, avg = float((net > 0).mean()), float(net.mean())
    return {"cells": len(j), "ids": [r["id"] for r in j], "share_pos": sp, "avg_net": avg, "median_net": float(np.median(net)),
            "avg_trades": float(tr.mean()), "positive": int((net > 0).sum()), "dead": n_dead, "dup": n_dup,
            "v60": bool(avg > 0 and share_ok(sp)), "v70": bool(avg > 0 and sp >= 0.7 - 1e-12), "v80": bool(avg > 0 and sp >= 0.8 - 1e-12)}


def seed_of(name: str, what: str) -> int:
    return zlib.crc32(f"v2|{name}|{what}".encode()) % (2 ** 31)


def block_seeds(seed: int) -> list:
    """The seeds of the draw blocks (BLOCK draws each): the unit's seed, + 1, + 2, ..."""
    return [seed + i for i in range(-(-RULE["draws"] // BLOCK))]


# ================================================================ control c1: coupled random tables (bar-based units)

def _mix(x):
    x = (x ^ (x >> U64(30))) * U64(0xbf58476d1ce4e5b9)
    x = (x ^ (x >> U64(27))) * U64(0x94d049bb133111eb)
    return x ^ (x >> U64(31))


def _prio(codes: np.ndarray, seed: int, salt=0, k: int = BLOCK) -> np.ndarray:
    """(k, *codes.shape) random priorities, one per (replicate, pool slot): the same slot has the same priority in every
    variant of the table. That is the coupling: all variants of one replicate use the SAME random entries."""
    with np.errstate(over="ignore"):
        base = _mix(codes.astype(U64) + U64(seed) * U64(0x9e3779b97f4a7c15) + np.asarray(salt, U64) * U64(0xd1b54a32d192ed03))
        j = (np.arange(k, dtype=U64) + U64(1)).reshape((-1,) + (1,) * codes.ndim)
        return _mix(base[None, ...] + j * U64(0x2545f4914f6cdd1d))


def pool_arrays(S: dict, sess: str, xid: str):
    """The random-entry pool of one exit cell in one session over the seeds S (seed_stores), sorted by date:
    (date, net, slot code, cumulative net). A slot = (date, seed, n-th entry of that seed that day)."""
    D, N, C = [], [], []
    for sd in sorted(S):
        x = cellx(store(S[sd][0]), S[sd][1] + xid, sess)
        o = np.lexsort((x["entry_ms"], x["date"]))
        d, n = x["date"][o].astype(np.int64), x["net"][o].astype(np.float64)
        if len(d):
            first = np.r_[True, d[1:] != d[:-1]]
            start = np.maximum.accumulate(np.where(first, np.arange(len(d)), 0))
            rank = np.arange(len(d)) - start
            assert rank.max() < 2048
        else:
            rank = np.zeros(0, np.int64)
        D.append(d)
        N.append(n)
        C.append(d * 4096 + rank + ((sd - 1) * 2048 if sd <= 2 else (sd << 40)))    # seeds 1, 2: out/v2's codes; more: no clash
    d, n, c = np.concatenate(D), np.concatenate(N), np.concatenate(C)
    o = np.argsort(d, kind="stable")
    d, n, c = d[o], n[o], c[o].astype(U64)
    return d, n, c, np.r_[0.0, np.cumsum(n)]


def c1_cell(md: np.ndarray, pool, seeds: list) -> tuple:
    """Coupled draws for ONE variant, BLOCK per seed in `seeds` -> (nets, fallback trades, unmatched trades). For every date
    with n trades of the variant: the n lowest-priority pool slots of that date (library.c1_draws' matching rule); a shortfall
    is filled from the nearest dates."""
    pd_, pn, pc, cs = pool
    k = BLOCK
    out = np.zeros(k * len(seeds))
    if not len(md):
        return out, 0, 0
    ud, kk = np.unique(np.asarray(md, np.int64), return_counts=True)
    lo, hi = np.searchsorted(pd_, ud, "left"), np.searchsorted(pd_, ud, "right")
    n_own = hi - lo
    full = n_own <= kk
    out += float((cs[hi[full]] - cs[lo[full]]).sum())
    sel = np.flatnonzero(n_own > kk)
    if len(sel):
        order = sel[np.argsort(n_own[sel], kind="stable")]
        a = 0
        while a < len(order):
            b = a + 1
            while b < len(order) and k * (b - a + 1) * int(n_own[order[b]]) <= 3_000_000:
                b += 1
            g = order[a:b]
            a = b
            M = int(n_own[g].max())
            idx = lo[g][:, None] + np.arange(M)[None, :]
            valid = np.arange(M)[None, :] < n_own[g][:, None]
            idx = np.where(valid, idx, 0)
            nets = pn[idx]
            kg = kk[g]
            km = int(kg.max())
            for bi, sd in enumerate(seeds):
                P = _prio(pc[idx], sd, 0, k)
                P[:, ~valid] = MAXU
                if km == 1:
                    am = P.argmin(axis=-1)
                    out[bi * k:(bi + 1) * k] += np.take_along_axis(np.broadcast_to(nets, P.shape), am[..., None], -1)[..., 0].sum(axis=1)
                else:
                    od = np.argpartition(P, km - 1, axis=-1)[..., :km] if km < M else np.argsort(P, axis=-1)
                    ps = np.take_along_axis(P, od, -1)
                    o2 = np.argsort(ps, axis=-1)
                    od = np.take_along_axis(od, o2, -1)
                    ns = np.take_along_axis(np.broadcast_to(nets, P.shape), od, -1)
                    keep = np.arange(od.shape[-1])[None, None, :] < kg[None, :, None]
                    out[bi * k:(bi + 1) * k] += (ns * keep).sum(axis=(1, 2))
    fb = short = 0
    need_g = np.flatnonzero(n_own < kk)
    if len(need_g):
        upd, first, cnt = np.unique(pd_, return_index=True, return_counts=True)
        for g in need_g:
            d, need = int(ud[g]), int(kk[g] - n_own[g])
            ok = upd != d
            dist = np.abs(upd[ok] - d)
            if not len(dist):
                short += need
                continue
            o = np.argsort(dist, kind="stable")
            cum = np.cumsum(cnt[ok][o])
            j = int(np.searchsorted(cum, need, "left"))
            cut = dist[o][min(j, len(o) - 1)]
            use = np.flatnonzero(dist <= cut)
            ei = np.concatenate([np.arange(first[ok][t], first[ok][t] + cnt[ok][t]) for t in use])
            got = min(need, len(ei))
            fb += got
            short += need - got
            if got == len(ei):
                out += float(pn[ei].sum())
            else:
                for bi, sd in enumerate(seeds):
                    P = _prio(pc[ei], sd, d % 100003 + 7, k)
                    od = np.argpartition(P, got - 1, axis=-1)[:, :got]
                    out[bi * k:(bi + 1) * k] += pn[ei][od].sum(axis=1)
    return out, fb, short


def c1_table(st: dict, u: dict, ids: list, S: dict, seed: int) -> dict:
    """Control c1 at TABLE level: coupled replicates of the table average (same exit cell, same session, same days) drawn from
    the random entries of every seed in S."""
    pools: dict = {}
    bs = block_seeds(seed)
    draws = np.zeros(BLOCK * len(bs))
    fb = short = n = 0
    for cid in ids:
        xid = cid.rsplit("_", 1)[-1]
        if xid not in pools:
            pools[xid] = pool_arrays(S, u["sess"], xid)
        md = cellx(st, cid, u["sess"], u)["date"]
        d, f, s = c1_cell(md, pools[xid], bs)
        draws += d
        fb += f
        short += s
        n += len(md)
    draws = draws[:RULE["draws"]] / max(1, len(ids))
    return {"ok": True, "draws": draws, "mean": float(draws.mean()), "sd": float(draws.std(ddof=1)), "p95": float(np.percentile(draws, 95)),
            "fallback_share": fb / n if n else 0.0, "short": int(short), "replicates": len(draws), "real_replicates": len(S)}


# ================================================================ controls shift / c2: day-mixes of the seeds on disk

def seed_day_avg(cells: list, days: np.ndarray) -> np.ndarray:
    """Per-day table average of a list of cells: the sum of the cells' nets that day / the number of cells."""
    A = np.zeros(len(days))
    for x in cells:
        if len(x["net"]):
            i = np.searchsorted(days, x["date"])
            ok = (i < len(days)) & (days[np.minimum(i, len(days) - 1)] == x["date"])
            np.add.at(A, i[ok], x["net"][ok])
    return A / max(1, len(cells))


def mix_draws(A: list, seed: int) -> dict:
    """The real replicates are the seeds on disk (A = one per-day table average per seed). Draws = day-mixes: each day takes
    one seed for the whole table. Lift is measured against the mean of the seeds' own table totals."""
    A = np.stack(A)
    n, cols, out = len(A), np.arange(A.shape[1]), []
    for sd in block_seeds(seed):
        pick = np.random.default_rng(sd).integers(0, n, size=(BLOCK, A.shape[1]))
        out.append(A[n - 1 - pick, cols[None, :]].sum(axis=1))          # 2 seeds: 1 -> the first, 0 -> the second (as out/v2)
    draws = np.concatenate(out)[:RULE["draws"]]
    raw = [float(a.sum()) for a in A]
    return {"ok": True, "draws": draws, "mean": float(np.mean(raw)), "raw": raw, "sd": float(draws.std(ddof=1)),
            "p95": float(np.percentile(draws, 95)), "replicates": len(draws), "real_replicates": n}


def all_days(u: dict, period: str, extra=()) -> np.ndarray:
    cal = LB._ordinals(calendar(period, u["root"]))
    ex = [np.asarray(e, np.int64) for e in extra if len(e)]
    return np.unique(np.concatenate([cal] + ex)) if ex else cal


def shift_table(u: dict, ids: list, S: dict, period: str, seed: int) -> dict:
    """Control shift: the same table fired at random minutes / with a random direction, on the unit's days, every seed in S."""
    cells = [[cellx(store(S[sd][0]), S[sd][1] + cid, None, u) for cid in ids] for sd in sorted(S)]
    days = all_days(u, period, [x["date"] for c in cells for x in c])
    return mix_draws([seed_day_avg(c, days) for c in cells], seed)


def c2_table(u: dict, ids: list, S: dict, period: str, seed: int) -> dict:
    """Control c2: the same table with a shuffled book, same session, every seed in S."""
    cells = [[cellx(store(S[sd][0]), cid, u["sess"], u) for cid in ids] for sd in sorted(S)]
    days = all_days(u, period, [x["date"] for c in cells for x in c])
    return mix_draws([seed_day_avg(c, days) for c in cells], seed)


def verdict(avg: float, ctl: dict, need_p: bool) -> dict:
    """lift and share of replicates beaten; pass = lift > 0 (and >= 95 % on BUILD; and no unmatched trade for c1)."""
    lift = avg - ctl["mean"]
    p = float((avg > ctl["draws"]).mean())
    ok = lift > 0 and (p >= P_NEED or not need_p) and not ctl.get("short")
    out = {"pass": bool(ok), "lift": round(lift, 2), "p_beat": round(p, 4), "ctl_mean": round(ctl["mean"], 2), "ctl_p95": round(ctl["p95"], 2),
           "ctl_sd": round(ctl["sd"], 2), "replicates": ctl["replicates"], "real_replicates": ctl["real_replicates"],
           "thin": ctl["real_replicates"] < THIN_BELOW}
    for k in ("fallback_share", "short", "raw"):
        if k in ctl:
            out[k] = ctl[k] if k != "fallback_share" else round(ctl[k], 4)
    return out


# ================================================================ controls base (Level 2 option) and days (day filter)

def per_trade(st: dict, u: dict, ids: list) -> tuple:
    net = n = 0.0
    for cid in ids:
        x = cellx(st, cid, u["sess"], u)
        net += float(x["net"].sum())
        n += len(x["net"])
    return (net / n if n else 0.0), net, int(n)


def base_test(st: dict, bst: dict, u: dict, ids: list) -> dict:
    """Level 2 option: the table's net per trade must beat the same strategy WITHOUT the option (same variants)."""
    if any(c not in bst["_idx"] for c in ids):
        return {"pass": False, "why": "base store lacks cells"}
    a, an, at = per_trade(st, u, ids)
    b, bn, bt = per_trade(bst, u, ids)
    return {"pass": bool(a > b), "per_trade": round(a, 2), "base_per_trade": round(b, 2), "lift_per_trade": round(a - b, 2),
            "avg_net": round(an / len(ids), 2), "base_avg_net": round(bn / len(ids), 2), "trades_kept_share": round(at / bt, 4) if bt else None}


def days_test(st: dict, u: dict, ids: list, seed: int, need_p: bool) -> dict:
    """Day filter: net per trade of the filtered table vs the unfiltered table and vs SUBSETS random same-size subsets of the
    days the unfiltered table traded (BUILD: must beat >= 95 % of them)."""
    dates, nets = [], []
    for cid in ids:
        x = cellx(st, cid, u["sess"], None)
        dates.append(x["date"])
        nets.append(x["net"])
    d, n = np.concatenate(dates), np.concatenate(nets).astype(np.float64)
    if not len(d):
        return {"pass": False, "why": "no trade"}
    days, inv = np.unique(d, return_inverse=True)
    N, T = np.zeros(len(days)), np.zeros(len(days))
    np.add.at(N, inv, n)
    np.add.at(T, inv, 1.0)
    ins = day_mask(u, days)
    k, nd = int(ins.sum()), len(days)
    if k == 0 or T[ins].sum() == 0:
        return {"pass": False, "why": "no trade inside the filter"}
    obs, unf = float(N[ins].sum() / T[ins].sum()), float(N.sum() / T.sum())
    out = {"per_trade": round(obs, 2), "unfiltered_per_trade": round(unf, 2), "lift_per_trade": round(obs - unf, 2), "days_in": k,
           "days_all": nd, "replicates": SUBSETS, "real_replicates": SUBSETS, "thin": False}
    if k >= nd:
        return {**out, "pass": False, "why": "the filter keeps every day"}
    rng = np.random.default_rng(seed)
    vals = np.zeros(SUBSETS)
    for a in range(0, SUBSETS, 500):
        pick = np.argsort(rng.random((500, nd)), axis=1)[:, :k]
        vals[a:a + 500] = N[pick].sum(axis=1) / np.maximum(1.0, T[pick].sum(axis=1))
    p = float((obs > vals).mean())
    out.update(p_beat=round(p, 4), subset_p95=round(float(np.percentile(vals, 95)), 2), **{"pass": bool(obs > unf and (p >= P_NEED or not need_p))})
    return out


def controls(st: dict, u: dict, ts: dict, period: str) -> dict:
    """EVERY control of the unit's type on one period -> {name: verdict}; all must pass. BUILD needs lift > 0 and 95 % of the
    replicates beaten, a year lift > 0. A random control uses every seed on disk (`seeds`, `stores` = {store: its seeds}); with more than 2 it also
    carries `two_seed` = the same test on the first 2 (what out/v2 had). A control missing on BUILD = that control fails; missing
    for a year = refused."""
    ids, avg, need_p, out = ts["ids"], ts["avg_net"], period == "build", {}
    nm, why = PERIODS[period]["name"], {"c1": "no pool", "shift": "no random-minute store", "c2": "no shuffled-book store on disk"}

    def run(c, S, sd):
        t = c1_table(st, u, ids, S, sd) if c == "c1" else (shift_table if c == "shift" else c2_table)(u, ids, S, period, sd)
        return verdict(avg, t, need_p)

    for c in u["controls"]:
        sd = seed_of(u["uid"], f"{period}-{c}")
        if c == "days":
            out[c] = days_test(st, u, ids, sd, need_p)
        elif c == "base":
            bs, br = find(skey(f"{u['base']}-{u['root']}-tf{u['tf']}", u, period), period, lambda r: not r["stress"] and not r["control"])
            if bs is None and period != "build":
                raise Refuse(f"{nm} store of the same strategy without the Level 2 option is missing for {u['addr']}", year_jobs(u, period))
            out[c] = {**base_test(st, bs, u, ids), "stores": {where(br): []}} if bs else {"pass": False, "why": "no base store"}
        else:
            S = seed_stores(u, period, c, sorted({i.rsplit("_", 1)[-1] for i in ids}) if c == "c1" else list(ids))
            S.pop(u["placebo"], None)                       # a placebo's control = the OTHER seeds
            if len(S) < (1 if c == "c1" else 2):
                if period != "build":
                    raise Refuse(f"{nm} control `{c}` of {u['addr']} is not on disk ({why[c]})", year_jobs(u, period))
                out[c] = {"pass": False, "why": why[c]}
                continue
            out[c] = {**run(c, S, sd), "seeds": sorted(S), "stores": {}}
            for k in sorted(S):                              # which store each seed came from
                out[c]["stores"].setdefault(where(S[k][0]), []).append(k)
            if len(S) > 2:
                two = run(c, {k: S[k] for k in sorted(S)[:2]}, sd)
                out[c]["two_seed"] = {k: two[k] for k in ("pass", "lift", "p_beat")}
    return out


# ================================================================ the three stages

def fast_share(xs: list) -> dict:
    """Trades held <= 5 s over a list of variants (pooled), two ways (F4): `fast_profit_share` = fast winners / all winners
    (gross); `fast_net_share` = net of the fast trades / total net (None when the total is not a profit). The stores keep
    whole seconds, floored: fast = held < 5 whole seconds."""
    gw = fw = net = fnet = 0.0
    nf = 0
    for x in xs:
        n, d = np.asarray(x["net"], np.float64), np.asarray(x["dur_s"])
        f = d < FAST_S
        gw += float(n[n > 0].sum())
        fw += float(n[f & (n > 0)].sum())
        net += float(n.sum())
        fnet += float(n[f].sum())
        nf += int(f.sum())
    return {"fast_profit_share": round(fw / gw, 4) if gw > 0 else None, "net_fast": round(fnet / max(1, len(xs)), 2),
            "net": round(net / max(1, len(xs)), 2), "fast_net_share": round(fnet / net, 4) if net > 0 else None, "n_fast": nf}


def build(u: dict) -> dict:
    """Tests (1)-(3) on BUILD at table level -> a flat row (`controls` = the verdict of every control drawn)."""
    st, _ = build_store(u)
    ts = table_stats(table(st, u))
    nb, nn = len(scope_days(u, "build")), len(scope_days(u, YEARS[0]))
    r = {"unit": u["addr"], "uid": u["uid"], "name": u["name"], **{k: u[k] for k in ("key", "family", "root", "tf", "sess", "label")},
         "group": u["group"] or "", "side": u["side"] or "", **{k: u[k] for k in ("timed", "l2", "stage_d", "weak", "penalty")},
         "controls_used": "+".join(u["controls"]), **{k: ts[k] for k in ("cells", "dead", "dup", "share_pos", "avg_net", "median_net", "avg_trades")},
         "days_build": nb, "days_2024": nn, "draws": RULE["draws"], "controls": {}}
    if not ts["cells"]:
        return {**r, "t1": False, "t2": None, "t3": False, "build_pass": False, "fail": "1,3"}
    t1 = bool(share_ok(ts["share_pos"]) and ts["avg_net"] > 0)
    reach = ts["avg_trades"] * (1.0 + nn / nb) if nb else 0.0
    t3 = bool(reach >= MIN_TRADES)
    t2 = None
    r.update({k: ts[k] for k in ("v60", "v70", "v80")}, exact60=abs(ts["share_pos"] - SHARE) < 1e-9, t1=t1, t3=t3, reach_trades=round(reach, 1))
    if ts["avg_net"] > 0 and ts["share_pos"] >= DRAW_FLOOR:
        r["controls"] = det = controls(st, u, ts, "build")
        t2 = all(v["pass"] for v in det.values())
        f = fast_share([cellx(st, c, u["sess"], u) for c in ts["ids"]])
        r.update(fast_profit_share=f["fast_profit_share"], fast_net_share=f["fast_net_share"])
        if any("two_seed" in v for v in det.values()):      # F2: what the first 2 seeds said (a member that fails now = DEMOTED)
            r["two_seed_pass"] = bool(t1 and t3 and all(v.get("two_seed", v)["pass"] for v in det.values()))
    r.update(t2=t2, build_pass=bool(t1 and t2 and t3), fail=",".join(n for n, ok in (("1", t1), ("2", bool(t2)), ("3", t3)) if not ok))
    return r


def menu_ids(u: dict) -> list:
    return [r["id"] for r in table(build_store(u)[0], {**u, "filter": None}) if not r.get("info") and not r.get("dead")]


def year_jobs(u: dict, period: str, stress: bool = False, cells=None) -> list:
    """The runner jobs (out/v2/run_v2.py format) that produce the stores `year` reads: the WHOLE menu + every control, or the
    stress pass (`cells` = the variants to stress on BUILD for the surviving set)."""
    oco = bool(build_meta(u["key"]).get("both_sides_declared"))
    base = {"family": u["family"], "root": u["root"], "tf": u["tf"], "sess": u["sess"], "period": PERIODS[period]["tag"]}
    if u["placebo"]:
        return [{"c1": True, **{k: base[k] for k in ("root", "tf", "sess", "period")}, **({"stress": True} if stress else {})}]
    ids = sorted(cells) if cells is not None else sorted(menu_ids(u))
    if stress:
        return [{**base, "stress": True, "oco": oco, "cells": ids}]
    jobs = [{**base, "cells": ids}]
    for c in u["controls"]:
        if c == "c1":
            jobs.append({"c1": True, **{k: base[k] for k in ("root", "tf", "sess", "period")}})
        elif c == "shift":
            jobs.append({**base, "family": u["base"] or u["family"], "shift": True, "cells": ids})
        elif c == "c2":
            jobs += [{**base, "c2_seed": sd, "cells": ids} for sd in (1, 2)]
        elif c == "base":
            jobs.append({**base, "family": u["base"], "cells": ids})
    return jobs


def _used(role: str, where_: str, seeds=None) -> dict:
    return {"role": role, "store": where_, "seeds": seeds or [], "origin": "re-used" if where_.split("/")[0] in EARLIER else "new"}


def year(u: dict, period: str, b: dict | None = None) -> dict:
    """Tests (4)-(6) of one year ON ITS OWN, from the stores on disk. PICK also gives the surviving set, the default and the
    final verdict (all six + the trade minimum on the real count + a surviving variant). CHECK re-tunes nothing: it reports the
    saved default and the saved variants on the new year -> CONFIRMED / WEAK / FAILED. `stores` = every store the verdict rests
    on (F6). Refused: a unit that fails an earlier stage, the EXAM (2026) without the flag or off the allowed list, a missing store (the exception
    carries the runner jobs)."""
    if period not in YEARS:
        raise Refuse(f"period {period!r}: one of {YEARS}")
    if period == "exam":
        exam_gate(u)                                      # raises unless --exam AND the unit is on allowed.json
    nm = PERIODS[period]["name"]
    b = b or build(u)
    if not (b["build_pass"] or b.get("two_seed_pass")):
        raise Refuse(f"{u['addr']} fails BUILD test {b['fail']}: {nm} is not read for it")
    prev = None
    if period != YEARS[0]:
        if u["side"]:
            raise Refuse(f"day filter {u['side']!r} (out/deepen/labels.py) is sealed at 2025-01-01: it cannot be judged on {nm}")
        prev = year(u, YEARS[YEARS.index(period) - 1], b)
        if not (prev["admit"] or prev["demoted"]):
            raise Refuse(f"{u['addr']} is not a member ({prev['verdict']}): {nm} is not read for it")
        if period == "exam" and not prev["admit"]:        # a DEMOTED unit is information on 2025 only: never 2026
            raise Refuse(f"{u['addr']} is DEMOTED ({PERIODS['check']['name']} {prev['verdict']}): {nm} is not read for it")
    bst, brec = build_store(u)
    brows = table(bst, u)
    ids = table_stats(brows)["ids"]                                   # the BUILD-judged variants
    yst, yrec = find(skey(u["key"], u, period), period, lambda r: not r["stress"])
    if yst is None:
        raise Refuse(f"{nm} store {skey(u['key'], u, period)} is not on disk: run the WHOLE menu and its control on {nm} first", year_jobs(u, period))
    ts = table_stats(table_on(yst, u, brows))
    t4 = bool(ts["cells"] and ts["avg_net"] > 0 and ts["median_net"] > 0)
    det = controls(yst, u, ts, period) if ts["cells"] else {}
    t5 = bool(det) and all(v["pass"] for v in det.values())
    t5_two = bool(det) and all(v.get("two_seed", v)["pass"] for v in det.values())      # F2: what the first 2 control seeds say
    xs = [cellx(yst, c, u["sess"], u) for c in ts["ids"]]
    f = fast_share(xs) if xs else {}
    tr = b["avg_trades"] + ts["avg_trades"]
    used = [_used("BUILD menu", where(brec)), _used(f"{nm} menu", where(yrec))]
    used += [_used(f"{nm} control {c}", s, sds) for c, v in det.items() for s, sds in v.get("stores", {}).items()]
    r = {"unit": u["addr"], "uid": u["uid"], "name": u["name"], "period": period, "store": where(yrec), "second_look": yrec["dir"].name in EARLIER,
         **{k: ts[k] for k in ("cells", "positive", "share_pos", "avg_net", "median_net", "avg_trades", "v60", "v70", "v80")},
         "t4": t4, "t5": t5, "t5_two_seed": t5_two, "controls": det, "trades_total": round(tr, 1), "t3_final": bool(tr >= MIN_TRADES),
         "fast_profit_share": f.get("fast_profit_share"), "fast_net_share": f.get("fast_net_share"), "t6": None, "survivors": None,
         "default": None, "admit": False, "demoted": False, "todo": [], "stores": used}
    net = lambda s, c: float(cellx(s, c, u["sess"], u)["net"].sum())  # noqa: E731
    live = [x["id"] for x in brows if not (x.get("dead") or x.get("info"))] if RULE["dedup_year"] else ids
    sst, srec = stress_store(u, period, live)
    if sst is not None:
        ss = table_stats(table_on(sst, u, brows))
        r.update(t6=bool(ss["cells"] and ss["avg_net"] > 0), stress_avg_net=ss["avg_net"], stress_median_net=ss["median_net"],
                 stress_share_pos=ss["share_pos"], stress_positive=ss["positive"], stress_cells=ss["cells"], oco_cancel_ms=srec["oco"])
        used.append(_used(f"{nm} stress", where(srec)))
    elif t4 and (t5 or t5_two):
        r["todo"] = year_jobs(u, period, stress=True)
    if period == YEARS[0]:
        if t4 and (t5 or t5_two) and r["t6"]:
            cand = [c for c in ids if net(bst, c) > 0 and net(yst, c) > 0 and net(sst, c) > 0]
            bss, bsrec = stress_store(u, "build", cand)
            if not cand:
                r["survivors"] = []
            elif bss is None:
                r["todo"] = year_jobs(u, "build", stress=True, cells=cand)
            else:
                brow = {x["id"]: x for x in brows}
                surv = [c for c in cand if net(bss, c) > 0]
                r["survivors"] = sorted(surv, key=lambda c: (round(brow[c]["net"], 2), brow[c]["vi"], brow[c]["xi"]))
                used.append(_used("BUILD stress", where(bsrec)))
                if surv:
                    r["default"] = r["survivors"][(len(surv) - 1) // 2]
                    r["default_build_net"] = brow[r["default"]]["net"]
            six = bool(r["survivors"] and r["t3_final"])       # all six, were the control only its first 2 seeds
            r.update(admit=six and t5 and b["build_pass"], demoted=six and not (t5 and b["build_pass"]))
        r["failed"] = [k for k, ok in (("4", t4), ("5", t5), ("6", r["t6"] is not False), (f"3 (BUILD + {nm} trades)", r["t3_final"]),
                                       ("no surviving variant", r["survivors"] != [])) if not ok]
        r["not_judged"] = (["6"] if r["t6"] is None else []) + (["surviving set"] if r["t6"] and r["survivors"] is None else [])
        r["verdict"] = (("PLACEBO PASSES ALL SIX (luck)" if u["placebo"] else "MEMBER") if r["admit"] else
                        "DEMOTED: luck not excluded (" + " and ".join(w for w, bad in (("BUILD test (2)", not b["build_pass"]), (f"{nm} test (5)", not t5)) if bad)
                        + " fails with every control seed on disk; it passes with the first 2)" if r["demoted"] else
                        f"fails {nm}: " + ", ".join(r["failed"]) if r["failed"] else "nothing failed so far; not judged yet: " + ", ".join(r["not_judged"]))
    else:
        r.update(survivors=prev["survivors"], default=prev["default"], default_net=net(yst, prev["default"]), demoted=prev["demoted"],
                 saved_profitable=sum(1 for c in prev["survivors"] if net(yst, c) > 0),
                 default_stress_net=net(sst, prev["default"]) if sst is not None and prev["default"] in sst["_idx"] else None)
        r["failed"] = [k for k, ok in (("4", t4), ("5", t5), ("6", r["t6"] is not False)) if not ok]
        r["not_judged"] = ["6"] if r["t6"] is None else []
        r["verdict"] = ("FAILED" if not (ts["cells"] and ts["avg_net"] > 0) else "CONFIRMED" if (t4 and t5 and r["t6"]) else
                        "WEAK" if r["failed"] else "not judged yet: 6")
        r["admit"] = r["verdict"] == "CONFIRMED" and not prev["demoted"]
    return r


def judge(u: dict, periods=None) -> dict:
    """BUILD, then every year whose stores exist (in order; a year is read only when everything before it passed), up to
    RULE['upto'] (`--upto build|pick|check`)."""
    if periods is None:
        periods = YEARS if RULE["upto"] is None else YEARS[:YEARS.index(RULE["upto"]) + 1] if RULE["upto"] in YEARS else ()
    out = {"unit": u, "build": build(u)}
    for p in periods:
        prev = out.get(YEARS[YEARS.index(p) - 1], {}) if p != YEARS[0] else {"admit": True}
        if not (out["build"]["build_pass"] or out["build"].get("two_seed_pass")) or not (prev.get("admit") or prev.get("demoted")):
            break
        try:
            out[p] = year(u, p, out["build"])
        except Refuse as e:
            out[f"{p}_refused"] = str(e)
            break
    return out


def log_reads(r: dict, path=None) -> None:
    """F6: append every store a year's verdict used (new or re-used from an earlier stage) to the read log."""
    path = Path(path) if path else READ_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["utc", "unit", "period", "role", "store", "seeds", "origin", "draws", "verdict"])
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        for s in r["stores"]:
            w.writerow([now, r["unit"], r["period"], s["role"], s["store"], " ".join(str(k) for k in s["seeds"]), s["origin"], RULE["draws"], r["verdict"]])


# ================================================================ card

SESS_PLAIN = {"eve": "evening (18:00-23:59 ET, the evening before the trade date)", "asia": "Asia (00:00-03:00 ET)",
              "london": "London (03:00-08:25 ET)", "pre": "pre-market (08:25-09:30 ET)", "nyam": "New York morning (09:30-11:00 ET)",
              "mid": "midday (11:00-13:30 ET)", "pm": "afternoon (13:30-15:58 ET)", "all": "all sessions"}
CTL_PLAIN = {"c1": "random entries, same exits and session (day-matched random tables)",
             "shift": "the same table at random minutes / with a random direction (day-mixes of the seeds)",
             "c2": "the same table with a shuffled book (day-mixes of the seeds)", "base": "the same strategy without the Level 2 option (net per trade)",
             "days": "the same table on all days (net per trade) and 4,000 random same-size day subsets"}
CTL_STORE = {"c1": "random-entry pool", "shift": "random-minute store", "c2": "shuffled book"}
TIE_RULE = "survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones"


def avg_variant(xs: list, cal: np.ndarray, years: list) -> list:
    """The AVERAGE variant per year then combined. trades / net / max drawdown = mean over the variants (each variant's own
    daily drawdown inside the row's span); win rate, profit factor, average trade = pooled over all the variants' trades."""
    rows = []
    spans = [(str(y), np.array([dt.date.fromordinal(int(o)).year == y for o in cal])) for y in years] + [("combined", np.ones(len(cal), bool))]
    for name, dm in spans:
        days = cal[dm]
        tr = net = gw = gl = wins = 0.0
        dds = []
        for x in xs:
            m = np.isin(x["date"], days)
            n = np.asarray(x["net"], np.float64)[m]
            tr += len(n)
            net += float(n.sum())
            gw += float(n[n > 0].sum())
            gl += float(-n[n < 0].sum())
            wins += int((n > 0).sum())
            daily = np.zeros(len(days))
            if len(n):
                np.add.at(daily, np.searchsorted(days, x["date"][m]), n)
            eq = np.cumsum(daily)
            dds.append(float((np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq).max()) if len(eq) else 0.0)
        nv = max(1, len(xs))
        rows.append({"period": name, "trades": round(tr / nv, 1), "net": round(net / nv, 2), "win": round(wins / tr, 4) if tr else None,
                     "pf": round(gw / gl, 3) if gl > 0 else None, "max_dd": round(float(np.mean(dds)), 2) if dds else 0.0,
                     "avg_trade": round(net / tr, 2) if tr else None})
    return rows


def _cat(xs: list) -> dict:
    return {k: np.concatenate([x[k] for x in xs]) for k in LB.FIELDS}


def _flags(u: dict, j: dict, fast_net) -> list:
    """The card's flags (out/v2/admit_v2.py; F2: any random control under 10 seeds is thin; F4: FAST on the net share)."""
    import families as F
    meta, fam, flags, b = build_meta(u["key"]), u["base"] or u["family"], [], j["build"]
    if j["pick"]["demoted"]:
        flags.append("DEMOTED: luck not excluded (a real-edge test fails with every control seed on disk; kept on file, not counted as edge)")
    if u["weak"]:
        flags.append("WEAK reason (the idea's reason is weak or only restates the trigger)")
    if u["penalty"]:
        flags.append("2025-26 penalty (the family's old favourite failed on 2025-26)")
    if fam in F.LIBRARY and F.library(fam).get("second_look") and not u["penalty"]:
        flags.append("2025-26 was already seen once for this family's old favourite (an EXAM would be a second look)")
    reads = [r for f in EARLIER_READS if (W / "out" / f / "pick_reads.csv").exists() for r in csv.DictReader((W / "out" / f / "pick_reads.csv").open())]
    if j["pick"]["second_look"]:
        flags.append("SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage)")
    elif any(r["family"] == u["family"] and r["root"] == u["root"] and r["sess"] == u["sess"] and str(r["tf"]) != u["tf"] for r in reads):
        flags.append("2024 was already read for this idea at another bar size (an earlier stage)")
    if meta.get("both_sides_declared") and (u["sess"] == "pre" or u["group"]):
        flags.append("BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print "
                     "(out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went)")
    thin = [(c, len(v.get("seeds", []))) for c, v in b["controls"].items() if c in CTL_STORE and len(v.get("seeds", [])) < THIN_BELOW]
    for n in sorted({n for _, n in thin}):
        flags.append("thin control (" + ", ".join(CTL_STORE[c] for c, k in thin if k == n) + f": {n} seeds on disk)")
    if b.get("exact60"):
        flags.append("exactly 60 % of variants profitable on BUILD")
    if u["label"].startswith("dir="):
        flags.append("one-direction unit compared with two-sided random entries (a tilted control)")
    if fast_net is not None and fast_net > FAST_LIMIT:
        flags.append("FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit)")
    return flags


def _siblings(u: dict) -> list:
    """The same idea at other bar sizes (same market, session, label, day filter): each one's own verdict."""
    out = []
    stores = [p.name for p in LB.RUNS.glob(f"{u['family']}-{u['root']}-tf*") if re.fullmatch(rf"{re.escape(u['family'])}-{u['root']}-tf\d+", p.name)]
    for d in sorted(stores, key=lambda k: k + "|"):         # out/v2's order (by uid): 15-min before 1-min
        tf = d.rsplit("tf", 1)[1]
        if tf == u["tf"]:
            continue
        st, _ = find(d, "build", lambda r: r["dir"] == LB.RUNS)
        sessions = st["meta"].get("base_pass_sessions") if st["meta"].get("base") else LB.unit_sessions(st)
        if u["sess"] not in sessions or u["label"] not in LB.plateau_units(st, u["sess"]):
            continue
        s = unit(f"{d}-{u['sess']}" + (f":{u['label']}" if u["label"] else "") + (f"@{u['filter']}" if u["filter"] else ""))
        j = judge(s, YEARS[:1])
        if not j["build"]["build_pass"] and "pick" not in j:
            out.append(f"{tf}-min: fails BUILD test {j['build']['fail']}")
        elif "pick" not in j:
            out.append(f"{tf}-min: passes BUILD, 2024 not read")
        else:
            y = j["pick"]
            out.append(f"{tf}-min: " + ("member" if y["admit"] else "demoted (luck not excluded)" if y["demoted"] else
                                        "passes BUILD, fails 2024 test " + ", ".join(y["failed"])
                                        + (f" ({', '.join(y['not_judged'])} not run)" if y["not_judged"] else "")))
    return out


def _day_side(x: dict) -> dict:
    out = {}
    for i in np.argsort(x["entry_ms"], kind="stable"):
        out.setdefault(int(x["date"][i]), int(x["side"][i]))
    return out


def same_idea(u: dict, default: str, members_dir: Path) -> list:
    """Members that are the SAME IDEA as this one: same family + market + session, or the default variants take the same side
    on >= 70 % of >= 30 shared trading days; the union of both relations over every member folder (one strategy per stack)."""
    M = [(u["name"], u, default)]
    for d in sorted(p for p in Path(members_dir).iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "spec.json").exists()):
        s = json.loads((d / "spec.json").read_text())
        if d.name != u["name"] and s.get("cell"):
            M.append((d.name, unit(spec_addr(s)), s["cell"]))
    sides = []
    for _, m, cid in M:
        xs = [cellx(build_store(m)[0], cid, m["sess"], m)]
        yst, _ = find(skey(m["key"], m, "pick"), "pick", lambda r: not r["stress"])
        if yst is not None and cid in yst["_idx"]:
            xs.append(cellx(yst, cid, m["sess"], m))
        sides.append(_day_side(_cat(xs)))
    par = list(range(len(M)))

    def root(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i in range(len(M)):
        for j in range(i + 1, len(M)):
            a, b_ = M[i][1], M[j][1]
            sh = [d for d in sides[i] if d in sides[j]]
            same = sum(sides[i][d] == sides[j][d] for d in sh) / len(sh) if sh else 0.0
            if (a["family"], a["root"], a["sess"]) == (b_["family"], b_["root"], b_["sess"]) or (len(sh) >= SAME_DAYS and same >= SAME_SIDE):
                par[root(i)] = root(j)
    return [M[i][0] for i in range(1, len(M)) if root(i) == root(0)]


def member(u: dict, members_dir=None, periods=None) -> dict:
    """Everything the card shows, from the stores: the average variant per year then combined next to the default, the shares,
    the lifts, stress, speed, flags, the surviving set. Refused unless the unit passes all six on BUILD + PICK (a member, or a
    member DEMOTED by the all-seed control: kept on file)."""
    members_dir = Path(members_dir) if members_dir is not None else LB.MEMBERS
    j = judge(u, periods)
    b, y = j["build"], j.get("pick")
    if y is None or not (y["admit"] or y["demoted"]):
        raise Refuse(f"{u['addr']} is not a member: " + (y["verdict"] if y else j.get("pick_refused") or f"fails BUILD test {b['fail']}"))
    sess, cid, bst = u["sess"], y["default"], build_store(u)[0]
    ids = table_stats(table(bst, u))["ids"]
    per = ["build"] + [p for p in YEARS if p in j]
    S, SS, cal = {"build": bst}, {}, []
    for p in per:
        if p != "build":
            S[p], _ = find(skey(u["key"], u, p), p, lambda r: not r["stress"])
        SS[p] = stress_store(u, p, y["survivors"] if p == "build" else ids)[0]
        cal += calendar(p, u["root"])
    xs_p = {p: [cellx(S[p], c, sess, u) for c in ids] for p in per}
    xs = [_cat([xs_p[p][i] for p in per]) for i in range(len(ids))]
    xd = {p: cellx(S[p], cid, sess, u) for p in per}
    years = sorted({dt.date.fromisoformat(d).year for d in cal})
    fast_avg = {**{p: fast_share(xs_p[p]) for p in per}, "all": fast_share(xs)}
    # the default's exact holding times and open losses need its full trade rows (the member run): used when they are on disk
    # and are the same trades as the store's cell; otherwise whole seconds from the store
    rows_ok, trades = True, []
    for p in per:
        f = members_dir / u["name"] / f"trades_{p}.json"
        t = json.loads(f.read_text()) if f.exists() else []
        rows_ok &= bool(f.exists() and len(t) == len(xd[p]["net"]) and abs(sum(q["net"] for q in t) - float(xd[p]["net"].sum())) < 0.01)
        trades += t
    xall = _cat([xd[p] for p in per])
    if rows_ok:
        fa = [t for t in trades if t["exit_ms"] - t["entry_ms"] <= 1000 * FAST_S]
        gw, tot = sum(t["net"] for t in trades if t["net"] > 0), sum(t["net"] for t in trades)
        fast_def = {"share": sum(t["net"] for t in fa if t["net"] > 0) / gw if gw > 0 else None, "net_fast": sum(t["net"] for t in fa),
                    "n_fast": len(fa), "net_share": sum(t["net"] for t in fa) / tot if tot > 0 else None, "exact": True}
        worst = max([abs(t.get("mae_usd") or 0.0) for t in trades] + [0.0])
    else:
        f = fast_share([xall])
        fast_def = {"share": f["fast_profit_share"], "net_fast": f["net_fast"], "n_fast": f["n_fast"], "net_share": f["fast_net_share"], "exact": False}
        worst = float(np.abs(xall["mae"]).max()) if len(xall["mae"]) else 0.0
    net = lambda s, c: float(cellx(s, c, sess, u)["net"].sum())  # noqa: E731
    surv = []
    for c in y["survivors"]:
        xb, xp = xs_p["build"][ids.index(c)], xs_p["pick"][ids.index(c)]
        yr = {yy: float(xb["net"][np.array([dt.date.fromordinal(int(d)).year == yy for d in xb["date"]], bool)].sum()) if len(xb["net"]) else 0.0
              for yy in (2021, 2022, 2023)}
        s = LB.stats(np.concatenate([xb["net"], xp["net"]]))
        row = {"cell": c, "default": c == cid, "net_2021": round(yr[2021], 2), "net_2022": round(yr[2022], 2), "net_2023": round(yr[2023], 2),
               "net_build": round(float(xb["net"].sum()), 2), "net_2024": round(float(xp["net"].sum()), 2), "trades_build": len(xb["net"]),
               "trades_2024": len(xp["net"]), "stress_build": round(net(SS["build"], c), 2), "stress_2024": round(net(SS["pick"], c), 2),
               "win": round(s["win"], 4), "pf": round(s["pf"], 3) if s["pf"] else "", "net_combined": s["net"]}
        for p in per[2:]:                                  # later years: reported, never used to choose
            nm = PERIODS[p]["name"]
            row.update({f"net_{nm}": round(net(S[p], c), 2), f"trades_{nm}": len(cellx(S[p], c, sess, u)["net"])})
            if SS[p] is not None and c in SS[p]["_idx"]:
                row[f"stress_{nm}"] = round(net(SS[p], c), 2)
        surv.append(row)
    spec_p = members_dir / u["name"] / "spec.json"
    spec = json.loads(spec_p.read_text()) if spec_p.exists() else {}
    keep = spec.get("cell") == cid                         # the hand-checked idea / rule text of the folder is kept for the same default
    meta, cell = bst["meta"], next(c for c in bst["meta"]["cells"] if c["id"] == cid)
    ex = cell.get("exit") or {}
    filt = (f" Traded ONLY on {EVENT_GROUPS[u['group']][2]}." if u["group"] else f" Day filter: {u['side']}." if u["side"] else "")
    rule = spec["rule"] if keep and spec.get("rule") else (
        f"{(meta.get('notes') or u['family']).rstrip('. ')}. Variant {json.dumps(cell.get('variant'))}; stop {ex.get('stop_mode')} {ex.get('stop_val')}; "
        + ("no target" if not ex.get("tgt_r") else f"target {ex['tgt_r']:g} x the stop") + f". Session: {SESS_PLAIN[sess]}; flat by 15:58 ET.{filt}")
    return {"unit": u, "uid": u["uid"], "name": u["name"], "idea": spec["idea"] if keep and spec.get("idea") else u["family"] + (f" @{u['filter']}" if u["filter"] else ""),
            "rationale": meta.get("rationale"), "rule": rule, "default": cid, "periods": per, "judge": j, "variants_judged": len(ids),
            "flags": _flags(u, j, fast_avg["all"]["fast_net_share"]), "siblings": _siblings(u), "same": same_idea(u, cid, members_dir),
            "avg_rows": avg_variant(xs, LB._ordinals(cal), years), "default_rows": LB.per_year(xall, cal), "surviving": surv,
            "default_stress": {p: [round(float(xd[p]["net"].sum()), 2), round(net(SS[p], cid), 2) if SS[p] is not None and cid in SS[p]["_idx"] else None]
                               for p in per}, "fast_avg": fast_avg, "fast_default": fast_def, "worst_open_loss": worst,
            "tables": {"build": table_stats(table(bst, u))}}


def card_md(m: dict) -> str:
    u, j, per = m["unit"], m["judge"], m["periods"]
    b, yrs = j["build"], [p for p in m["periods"] if p != "build"]
    names = [PERIODS[p]["name"] for p in yrs]
    nxt = str(int(names[-1]) + 1)
    own = f"{names[0]} judged on its own" if len(names) == 1 else f"{' and '.join(names)} each judged on its own"
    L = [f"# {m['name']} — library member (admission v2: judged on the AVERAGE of all variants)", "",
         f"**Idea:** {m['idea']} · **market** {u['root']} · **session** {u['sess']} · **bar size** {u['tf']} min · 1 contract, after costs. "
         f"BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), {own}. {nxt}+ was never read.",
         "**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**"]
    if j["pick"]["demoted"]:
        L.append(f"**{j['pick']['verdict']}. Kept on file, NOT counted as edge.**")
    for p in yrs[1:]:
        y = j[p]
        L.append(f"**{PERIODS[p]['name']} (read once, after choosing; nothing re-tuned): {y['verdict']}** — default {money(y['default_net'])}, "
                 f"{y['saved_profitable']} of the {len(y['survivors'])} saved variants profitable.")
    same = [f"SAME IDEA as {', '.join(m['same'])}: one strategy for a stack, never two"] if m["same"] else []
    L += ["", f"**Reason (written before testing):** {m['rationale']}", "", f"**Rules (default variant `{m['default']}`):** {m['rule']}", "",
          "**Flags:** " + ("; ".join(m["flags"] + same) or "none"), "",
          "**The same idea at other bar sizes (same market and session):** " + ("; ".join(m["siblings"]) or "none stored") + ".", "",
          "## Average variant and default variant, per year then combined",
          f"Average = the {m['variants_judged']} judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). "
          f"Default = the middle of the {len(m['surviving'])} surviving variants by BUILD net ({TIE_RULE}).", "",
          "| | period | trades | net | win rate | profit factor | max drawdown | average trade |", "|---|---|---|---|---|---|---|---|"]
    for r in m["avg_rows"]:
        nm = "2021*" if r["period"] == "2021" else r["period"]
        L.append(f"| average variant | {nm} | {r['trades']:.0f} | {money(r['net'])} | {pct(r['win'])} | {'n/a' if r['pf'] is None else format(r['pf'], '.2f')} | "
                 f"{money(r['max_dd'])} | {money(r['avg_trade'])} |")
    for r in m["default_rows"]:
        nm = "2021*" if str(r["period"]).startswith("2021") else str(r["period"])
        L.append(f"| default `{m['default']}` | {nm} | {r['trades']} | {money(r['net'])} | {pct(r['win'])} | {'n/a' if r['pf'] is None else format(r['pf'], '.2f')} | "
                 f"{money(r['max_dd'])} | {money(r['avg_trade'])} |")
    L += ["", "## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)",
          "| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |", "|---|---|---|---|---|---|---|---|---|"]
    for nm, g in [("BUILD", m["tables"]["build"])] + [(PERIODS[p]["name"], j[p]) for p in yrs]:
        L.append(f"| {nm} | {g['cells']} | {g['positive']} | {pct(g['share_pos'])} | {'pass' if g['v60'] else 'fail'} | {'pass' if g['v70'] else 'fail'} | "
                 f"{'pass' if g['v80'] else 'fail'} | {money(g['avg_net'])} | {money(g['median_net'])} |")
        if nm != "BUILD" and g["t6"] is not None:
            L.append(f"| {nm} under stress | {g['stress_cells']} | {g['stress_positive']} | {pct(g['stress_share_pos'])} | | | | "
                     f"{money(g['stress_avg_net'])} | {money(g['stress_median_net'])} |")
    L += ["", f"## Real edge: the table average against random (lift = table average minus the control's average; {b['draws']:,} random tables per control)",
          "| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |", "|---|---|---|---|---|---|"]
    for nm, det in [("BUILD", b["controls"])] + [(PERIODS[p]["name"], j[p]["controls"]) for p in yrs]:
        for c, v in det.items():
            if c in ("base", "days"):
                lift = f"{money(v.get('lift_per_trade'))} a trade ({money(v.get('per_trade'))} vs {money(v.get('unfiltered_per_trade', v.get('base_per_trade')))})"
            else:
                lift = money(v.get("lift"))
            n = len(v.get("seeds", []))
            two = v.get("two_seed")
            L.append(f"| {CTL_PLAIN[c]} | {nm} | {(str(n) + (' (THIN)' if n < THIN_BELOW else '')) if n else ''} | {lift} | "
                     f"{pct(v.get('p_beat'), 1) if v.get('p_beat') is not None else 'n/a'} | "
                     f"{(money(two['lift']) + ', ' + pct(two['p_beat'], 1)) if two else ''} |")
    ds = m["default_stress"]
    oco = " + 100 ms late cancel of the other bracket side" if j["pick"].get("oco_cancel_ms") else ""
    fa, fd = m["fast_avg"], m["fast_default"]
    L += ["", f"## Stress (2 ticks of slippage + 250 ms delay{oco})"]
    L += [f"* Average variant, {PERIODS[p]['name']}: {money(j[p]['avg_net'])} -> {money(j[p].get('stress_avg_net'))} under stress." for p in yrs]
    L += ["* Default variant: " + "; ".join(f"{PERIODS[p]['name']} {money(ds[p][0])} -> {money(ds[p][1])}" for p in per) + ".",
          f"* Surviving set: {len(m['surviving'])} of {m['variants_judged']} variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).",
          "", "## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)",
          "* Average variant, trades held under 5 s, winners only (fast winners / all winners): "
          + ", ".join(f"{PERIODS[p]['name']} {pct(fa[p]['fast_profit_share'])}" for p in per) + f", combined {pct(fa['all']['fast_profit_share'])}.",
          "* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): "
          + ", ".join(f"{PERIODS[p]['name']} {pct(fa[p]['fast_net_share'])}" for p in per) + f", combined {pct(fa['all']['fast_net_share'])}.",
          f"* Default variant ({'exact times, held <= 5.000 s' if fd['exact'] else 'whole seconds from the store, held under 5 s'}): "
          f"{pct(fd['share'])} of the winners' profit, {pct(fd['net_share'])} of the net profit; those {fd['n_fast']} trades net {money(fd['net_fast'])}.",
          "", "## Size",
          f"* Worst open loss on one trade (default, 1 contract): {money(m['worst_open_loss'])} = {money(m['worst_open_loss'] / 10 + 1)} per micro -> "
          f"at most {int(2000 // (m['worst_open_loss'] / 10 + 1)) if m['worst_open_loss'] > 0 else 'n/a'} micros inside $2,000.",
          "", f"Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `{m['uid']}`."]
    return "\n".join(L) + "\n"


def card(u: dict, out_dir=None, members_dir=None, m: dict | None = None) -> Path:
    """Write / refresh <out_dir>/<name>/card.md and surviving_set.csv (out_dir default = members/). spec.json, the trade files
    and daily.csv belong to the member run (full trade rows of the default) and are left alone."""
    m = m or member(u, members_dir)
    d = (Path(out_dir) if out_dir is not None else LB.MEMBERS) / m["name"]
    d.mkdir(parents=True, exist_ok=True)
    with (d / "surviving_set.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(m["surviving"][0]))
        w.writeheader()
        w.writerows(m["surviving"])
    (d / "card.md").write_text(card_md(m))
    return d


# ================================================================ lines, the summary table, the command line

def _ctl_txt(det: dict) -> str:
    bits = []
    for c, v in det.items():
        n = f" ({len(v['seeds'])} seeds)" if v.get("seeds") else ""
        if "why" in v and "lift" not in v and "lift_per_trade" not in v:
            bits.append(f"{c}: {v['why']}")
        elif c in ("base", "days"):
            bits.append(f"{c}: {money(v['lift_per_trade'])} a trade" + (f", beats {100 * v['p_beat']:.1f} %" if v.get("p_beat") is not None else ""))
        else:
            bits.append(f"{c}{n}: lift {money(v['lift'])}, beats {100 * v['p_beat']:.1f} %"
                        + (f" [first 2 seeds: {100 * v['two_seed']['p_beat']:.1f} %]" if "two_seed" in v else ""))
    return "; ".join(bits)


def build_line(r: dict) -> str:
    if not r["cells"]:
        return f"{r['unit']:44s} BUILD FAIL 1,3 | no judged variant"
    t2 = "not drawn (fails (1))" if r["t2"] is None else _ctl_txt(r["controls"]) + f" [{r['draws']:,} draws]"
    return (f"{r['unit']:44s} BUILD {'PASS' if r['build_pass'] else 'FAIL ' + r['fail']} | (1) {100 * r['share_pos']:.1f} % of {r['cells']} variants "
            f"profitable, average {money(r['avg_net'])} | (2) {t2} | (3) {r['avg_trades']:.0f} trades, {r['reach_trades']:.0f} with 2024 at the same rate")


def year_line(r: dict) -> str:
    nm = PERIODS[r["period"]]["name"]
    s6 = "not run" if r["t6"] is None else f"stressed average {money(r['stress_avg_net'])}"
    tail = (f"saved {len(r['survivors'])}, default `{r['default']}`" if r["survivors"] else "") if r["period"] == YEARS[0] else (
        f"default {money(r['default_net'])}, {r['saved_profitable']} of {len(r['survivors'])} saved variants profitable")
    return (f"{r['unit']:44s} {nm} {r['verdict']} | (4) average {money(r['avg_net'])}, median {money(r['median_net'])}, {100 * r['share_pos']:.1f} % of "
            f"{r['cells']} profitable | (5) {_ctl_txt(r['controls'])} | (6) {s6}" + (f" | {tail}" if tail else ""))


def stores_line(r: dict) -> str:
    return "  stores used: " + " · ".join(f"{s['role']} {s['store']}" + (f" (seeds {', '.join(str(k) for k in s['seeds'])})" if s["seeds"] else "")
                                           + f" [{s['origin']}]" for s in r["stores"])


def flat(j: dict) -> dict:
    """One flat row per unit for the summary table (the BUILD columns carry the names of out/v2/build_units.csv)."""
    b = dict(j["build"])
    det = b.pop("controls")
    for c, v in det.items():
        b[f"{c}_pass"] = v["pass"]
        for k in ("lift", "p_beat", "ctl_mean", "lift_per_trade", "per_trade", "unfiltered_per_trade", "base_per_trade", "fallback_share", "why"):
            if k in v:
                b[f"{c}_{k}"] = v[k]
        if v.get("seeds"):
            b[f"{c}_seeds"] = len(v["seeds"])
        if "two_seed" in v:
            b[f"{c}_p_beat_2seed"] = v["two_seed"]["p_beat"]
    b["verdict"] = "fails BUILD " + b["fail"] if not b["build_pass"] else "passes BUILD; 2024 not read"
    for p in YEARS:
        y = j.get(p)
        if y is None:
            if f"{p}_refused" in j and p == YEARS[0]:
                b["note"] = j[f"{p}_refused"].split(":")[0]
            continue
        lifts = [v.get("lift", v.get("lift_per_trade")) for v in y["controls"].values()]
        b.update({f"{p}_{k}": y.get(k) for k in ("cells", "share_pos", "avg_net", "median_net", "avg_trades", "t4", "t5", "t6", "stress_avg_net")})
        b.update({f"{p}_lift": "/".join("" if v is None else f"{v:g}" for v in lifts), f"{p}_verdict": y["verdict"]})
        if p == YEARS[0]:
            b.update(t3_final=y["t3_final"], survivors=len(y["survivors"] or []), default=y["default"] or "", admit=y["admit"], demoted=y["demoted"],
                     verdict=y["verdict"])
        else:
            b.update({f"{p}_default_net": y["default_net"], f"{p}_saved_profitable": y["saved_profitable"]},
                     verdict=f"{'DEMOTED' if y['demoted'] else 'MEMBER'}; {PERIODS[p]['name']} {y['verdict']}")
    return b


def _judge_store(job: tuple) -> list:
    RULE.update(job[2])
    out = []
    for a in job[1]:
        try:
            out.append(flat(judge(unit(a))))
        except Refuse as e:
            out.append({"unit": a, "verdict": f"REFUSED: {e}"})
    return out


def table_rows(addrs: list, workers: int = 8) -> list:
    """Judge many units (grouped by BUILD store, in parallel) -> flat rows in the order given."""
    by: dict = {}
    for a in addrs:
        by.setdefault(a.split("|")[0] if "|" in a else re.sub(r"-(eve|asia|london|pre|nyam|mid|pm|all)(:[^@]*)?(@\w+)?$", "", a), []).append(a)
    jobs = [(k, v, dict(RULE)) for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))]
    if workers > 1 and len(jobs) > 1:
        from multiprocessing import Pool
        with Pool(workers) as pool:
            rows = [r for part in pool.imap_unordered(_judge_store, jobs, chunksize=1) for r in part]
    else:
        rows = [r for job in jobs for r in _judge_store(job)]
    by_addr: dict = {}
    for r in rows:
        by_addr.setdefault(r["unit"], r)
    canon = lambda a: a if a in by_addr else unit(a)["addr"]  # noqa: E731
    return [by_addr[canon(a)] for a in addrs]


def table_md(rows: list) -> str:
    f = lambda v, d=0: "" if v in (None, "") else (money(v) if d == 0 else f"{100 * v:.0f} %")  # noqa: E731
    yn = lambda v: "" if v in (None, "") else ("pass" if v else "FAIL")  # noqa: E731
    L = ["| unit | variants | BUILD share > 0 | BUILD average | trades | (1) | (2) | (3) | 2024 average | 2024 median | 2024 stressed | (4) | (5) | (6) | saved | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "cells" not in r:
            L.append(f"| `{r['unit']}` | | | | | | | | | | | | | | | {r['verdict']} |")
            continue
        L.append(f"| `{r['unit']}` | {r['cells']} | {f(r['share_pos'], 1)} | {f(r['avg_net'])} | {r['avg_trades']:.0f} | {yn(r['t1'])} | {yn(r['t2'])} | {yn(r['t3'])} | "
                 f"{f(r.get('pick_avg_net'))} | {f(r.get('pick_median_net'))} | {f(r.get('pick_stress_avg_net'))} | {yn(r.get('pick_t4'))} | {yn(r.get('pick_t5'))} | "
                 f"{yn(r.get('pick_t6'))} | {r.get('survivors', '')} | {r['verdict']} |")
    return "\n".join(L) + "\n"


def write_table(rows: list, prefix) -> tuple:
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with prefix.with_suffix(".csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    bp = sum(bool(r.get("build_pass")) for r in rows)
    head = (f"# ADMISSION v2 — {n} units judged by judge.py ({dt.date.today().isoformat()})\n\n{bp} pass BUILD (1)-(3); "
            f"{sum(bool(r.get('admit')) for r in rows)} pass all six and have a surviving set. Dollars: 1 contract after costs, the AVERAGE variant. "
            f"Test (2): {RULE['draws']:,} draws, {'every control seed on disk' if not RULE['seeds'] else 'the first ' + str(RULE['seeds']) + ' control seeds'}.\n\n")
    prefix.with_suffix(".md").write_text(head + table_md(rows))
    return prefix.with_suffix(".csv"), prefix.with_suffix(".md")


def main(argv=None) -> int:
    rule = argparse.ArgumentParser(add_help=False)
    rule.add_argument("--draws", type=int, default=None, help=f"random tables per control in test (2) (default {DRAWS:,}; 200 = out/v2's own draws)")
    rule.add_argument("--seeds", type=int, default=None, help="use only the first N control seeds on disk (default: all)")
    rule.add_argument("--upto", choices=("build",) + YEARS, default=None, help="judge no later than this period (default: every year on disk)")
    rule.add_argument("--exam", action="store_true", help="the explicit EXAM flag: lets `year --period exam` / `card` read 2026 for a unit on "
                      "out/exam2026/allowed.json (and only for those)")
    rule.add_argument("--as-v2", action="store_true", help="exactly as out/v2 coded and ran it (200 draws, 2 seeds, >= 60 %%, a year de-duplicated again, its six "
                      "folders, BUILD + 2024): the regression lock")
    ap = argparse.ArgumentParser(description="ADMISSION v2: judge a unit by the AVERAGE of all its variants (JUDGE.md).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", parents=[rule], help="tests (1)-(3) on BUILD")
    p.add_argument("units", nargs="+")
    p = sub.add_parser("year", parents=[rule], help="tests (4)-(6) of one year on its own, from stores on disk")
    p.add_argument("units", nargs="+")
    p.add_argument("--period", required=True, choices=YEARS)
    p.add_argument("--log", default=str(READ_LOG), help="append every store used to this CSV ('' = no log)")
    p = sub.add_parser("card", parents=[rule], help="write / refresh the member card and surviving_set.csv")
    p.add_argument("units", nargs="+")
    p.add_argument("--out", default=None, help="write to <out>/<name>/ instead of members/<name>/")
    p = sub.add_parser("table", parents=[rule], help="one line per unit: CSV + markdown")
    p.add_argument("units", nargs="*")
    p.add_argument("--stage", default="", help="comma list of s1,r1,ev,en,2a,members,placebo,all or a catalog CSV (default: all)")
    p.add_argument("--out", default=str(W / "out" / "judge" / "table"), help="output prefix (.csv and .md are added)")
    p.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    RULE.update(AS_V2 if a.as_v2 else {})
    RULE["exam"] = bool(a.exam) and not a.as_v2
    RULE.update({k: v for k, v in (("draws", a.draws), ("seeds", a.seeds), ("upto", a.upto)) if v})
    rc = 0
    if a.cmd == "table":
        t0 = time.monotonic()
        addrs = list(a.units) + [x for s in (a.stage.split(",") if a.stage else ([] if a.units else ["all"])) for x in catalog(s)]
        rows = table_rows(addrs, a.workers)
        c, m = write_table(rows, a.out)
        print(f"{len(rows)} units | pass BUILD {sum(bool(r.get('build_pass')) for r in rows)} | members {sum(bool(r.get('admit')) for r in rows)} | "
              f"{time.monotonic() - t0:.0f} s | {c} {m}")
        return 0
    for addr in a.units:
        try:
            u = unit(addr)
            if a.cmd == "build":
                r = build(u)
                print(build_line(r))
                rc |= 0 if r["build_pass"] else 1
            elif a.cmd == "year":
                r = year(u, a.period)
                print(year_line(r))
                print(stores_line(r))
                if a.log:
                    log_reads(r, a.log)
                if r["todo"]:
                    print(f"  not judged yet ({', '.join(r['not_judged'])}); run: {RUNNER.get(r['todo'][0]['period'], RUNNER['pick'])}\n  jobs.json = "
                          + json.dumps(r["todo"]))
                rc |= 0 if r["admit"] else 1
            else:
                d = card(u, a.out)
                print(f"{u['addr']:44s} card -> {d / 'card.md'}  (+ surviving_set.csv)")
        except Refuse as e:
            rc |= 2
            print(f"{addr:44s} REFUSED: {e}")
            if e.jobs:
                print(f"  run: {RUNNER[a.period] if a.cmd == 'year' else RUNNER['pick']}\n  jobs.json = " + json.dumps(e.jobs))
    return rc


if __name__ == "__main__":
    sys.exit(main())
