"""taught.py -- THE TAUGHT LANE: a rule run EXACTLY AS A VIDEO TAUGHT IT (the owner, 2026-10-10).

Until now every idea went through the pipeline: ONE entry rule plus a fixed table of 8 stops x 6 targets, a 144-box heat map and a
pick. A video's own stop, target, trade cap and window were replaced by the table, so what was tested was not what was taught.
This lane runs the video's rule as it was said: the entry rule with its own settings, ONE exit cell with the video's own stop and
target, its own cap, and a small neighbourhood so that fragility shows. No heat map, no pick, no search, no tuning.

    bp.py taught check <sheet>                       the sheet is validated and what will run is printed (nothing runs)
    bp.py taught run <sheet> [--root=DIR] [--workers=N] [--days=d1,d2]
    bp.py taught show <name> [--root=DIR]            the last result again
    bp.py taught list [--root=DIR]                   one row a sheet on file
    root = --root, else HOMEBASE_TAUGHT_ROOT, else ~/.homebase/taught.  <root>/<name>/{sheet.json, runs/, ledger.csv, runner.log,
    result.json}; a run on named days (--days) is a SMOKE RUN: <root>/<name>/smoke/ and never a verdict.

THE SHEET (JSON, written by a person; `check` says what is wrong, part by part)
    name        a-z 0-9 and single '_'                       source   {video, title, channel, url}: one of video / title / url
    market      NQ | ES | GC                                  bars     every bar size the video allows: "1" | "5" | "15" | "30"
    sessions    session passes the entry may trade in (engine names), and / or
    window      "HH:MM-HH:MM": honoured only when the engine can cut it (module text below), else the sheet is REFUSED
    dir         both | long | short
    entry       {family, settings: {setting: value}, words: the entry in the video's own words}
    exits       {stop_pts | stop_ticks, target_pts | target_ticks, exit_bars | exit_minutes, max_trades}
                or {"stop": "struct", target_r, exit_bars | exit_minutes, max_trades}  (the family's own structure level)
    taught      one sentence per rule, as the video says it, with its time mark
    not_run     everything the video does that the engine cannot ([] says: nothing was left out -- the person says so)
    control     "random"

WHAT RUNS (every number is the sheet's own; the lane adds none)
    cells    the taught cell (centre) and its neighbours: stop x {0.75, 1, 1.25} crossed with target x {0.75, 1, 1.25}, each
             rounded to the market's tick (halves up): 9 cells. A structure stop has no size to scale: target_r x {0.75, 1,
             1.25} only: 3 cells. Every cell: stop_mode pts (or struct), tgt_r = target / stop, the sheet's cap, exit_bars, dir,
             the family's settings as the sheet gives them, hold_to day, one run per bar over the sheet's session passes.
    control  the pipeline's own random entries (l2ref.Random, p_entry 0.5, the 10 seeds of control.json) at the SAME exit cells
             and session passes, per bar -- and, for a one-sided sheet, the same random entries on that side only (the drift
             control: a long-only rule must beat random LONGS, not random coin flips). Day- and pass-matched, drawn by the
             judge's own c1_table (4,000 draws), per pass, then added over the passes. A STRUCTURE stop has no level for a
             random entry: the random entries take the MEDIAN stop distance of the taught trades (read off their store; a
             size, never a result) at the same target_r.
    reads    for the centre box and for the average of the nine cells: the metrics of library.metrics, per year then combined,
             the prop odds (pipe_prop.odds: the plain row is the number, `stress` beside it), the pipeline's own lines on the
             centre box -- P3.2 P3.3 P3.4 P3.7 P3.8 P3.9 P3.10, the lock's 3.3-3.8, the reshuffled runs P4.1, the random line
             P4.2 -- each as the pipeline words it. Build days only (2021-09-22 .. 2025-06-30): the seal is the runner's.

HONEST LIMITS (printed with every result): one video's rule; in-sample (the build days); the family's settings are the video's
own and nothing was tuned; the neighbours are for fragility, never to pick from; the unseen days are not read (a person asks, once).

THE PASS IS NOT THE DAY. The engine runs each session pass as its own instance (hold_to day: one session per instance). A cap
(`max_trades`) and a family's own loss stop (vwap_trend_pull's max_loss) count inside ONE pass. With several passes in `sessions`
a day can hold up to passes x the cap, and a trade of one pass may still be open when another pass enters. `check` says so
beside the Run lines; a sheet with ONE pass whose window holds the video's window has an honest per-day cap.

Reads and runs everything through the toolkit's own functions (runner._run for the stores, tables / judge for the reads,
pipe_gates / lines / pipe_prop for the lines); it edits none of the hashed engine files. Locked by tests/test_taught.py.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import datetime as dt
import hashlib
import inspect
import json
import math
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_menus as RM

from . import api
from . import lines as L
from . import pipe_gates as G
from . import pipe_prop as PP
from . import pipe_rules as PR
from . import pipe_stages as ST
from . import rules as R
from . import runner as RUN
from . import tables as T

ENV = "HOMEBASE_TAUGHT_ROOT"
SHEET_KEYS = ("name", "source", "market", "bars", "sessions", "window", "dir", "entry", "exits", "taught", "not_run", "control")
REQUIRED = ("name", "source", "market", "bars", "dir", "entry", "exits", "taught", "not_run")
SOURCE_KEYS = ("video", "title", "channel", "url")
ENTRY_KEYS = ("family", "settings", "words")
EXIT_KEYS = ("stop", "stop_pts", "stop_ticks", "target_pts", "target_ticks", "target_r", "exit_bars", "exit_minutes", "max_trades")
NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
BARS = ("1", "5", "15", "30")
SIDES = ("both", "long", "short")
STEPS = (0.75, 1.0, 1.25)                           # the neighbours: 75 %, 100 % and 125 % of the taught stop and of the taught target
CENTRE = 1.0
WINDOW = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
CHECK, RUN_, SHOW, LIST = "taught check", "taught run", "taught show", "taught list"
STEADY = ("P3.8", "P3.9", "P3.10")                  # the rows of how steadily the box made its money: `kind` steadiness (a later change is one line)
LIMITS = ("One video's rule, read on the build days (2021-09-22 .. 2025-06-30): in-sample.",
          "The family's settings and the exits are the video's own: nothing was tuned, searched or picked.",
          "The neighbours are shown to see how fragile the rule is; they are not alternatives to choose from.",
          "The unseen days (2025-07-01 on) were not read: a person has to ask for that, and it is read once.",
          "The random entries are the pipeline's own (any bar of the session pass, matched by day and pass): they do not wait for the "
          "family's entry window.")


# ================================================================ small things

def where(arg=None) -> Path:
    """The taught root: the argument, else HOMEBASE_TAUGHT_ROOT, else ~/.homebase/taught."""
    return Path(arg or os.environ.get(ENV) or (Path.home() / ".homebase" / "taught")).expanduser()


def _num(v: float) -> str:
    return ("%g" % v).replace(".", "p")


def _tick_round(v: float, tick: float) -> float:
    """The nearest tick, halves up (a rule, not a search)."""
    return round(math.floor(v / tick + 0.5 + 1e-9) * tick, 6)


def _is_num(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and v == v


def _usd(v) -> str:
    return "n/a" if v is None else (f"-${abs(v):,.0f}" if round(v) < 0 else f"${v:,.0f}")


def _pc(v) -> str:
    return "n/a" if v is None else f"{100 * v:.1f} %"


def _g(v) -> str:
    return f"{v:g}"


def _clean(x):
    """JSON-ready: numpy types plain, inf / nan -> None, keys strings."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, Path):
        return str(x)
    return x


def _write(path: Path, doc) -> None:
    """A JSON file whole or not at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_clean(doc), indent=1))
    tmp.replace(path)


def _canon(doc) -> str:
    return json.dumps(doc, sort_keys=True)


def load(sheet) -> dict:
    """A sheet: a dict, or the path of its JSON file -> a copy. Refused: no file, not JSON."""
    if isinstance(sheet, dict):
        return copy.deepcopy(sheet)
    try:
        return json.loads(Path(sheet).read_text(encoding="utf-8"))
    except OSError as e:
        raise J.Refuse(f"sheet {sheet}: {e}") from None
    except ValueError as e:
        raise J.Refuse(f"sheet {sheet} does not read as JSON: {e}") from None


def _clock(sec: int) -> str:
    sec %= 86400
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


def _parse_window(text: str):
    m = WINDOW.match(str(text).strip())
    if not m:
        return None
    a, b = int(m[1]) * 3600 + int(m[2]) * 60, int(m[3]) * 3600 + int(m[4]) * 60
    if int(m[1]) > 23 or int(m[3]) > 23 or int(m[2]) > 59 or int(m[4]) > 59:
        return None
    a, b = (a - 86400 if a >= 64800 else a), (b - 86400 if b >= 64800 else b)          # the evening (18:00 on) is the evening BEFORE the trade date
    return (a, b) if a < b else None


PASS_CLOCK = {s: S.SESS[s] for s in RM.DAY_PASSES}                      # the engine's own clock window of each pass, seconds after 00:00 ET


def _pass_words(s: str) -> str:
    a, b = PASS_CLOCK[s]
    return f"{s} {_clock(a)}-{_clock(b)}"


# ================================================================ does a family pass a structure level?

def passes_structure(family: str):
    """True when the family's code hands the engine a STRUCTURE LEVEL with an order -- `_mkt(..., struct=x)`, `_lim(..., struct=x)` or a
    leg (side, price, struct, target) of `_arm` -- read off its source (the family's class and its bases, up to the Template); False when
    it never does (then stop_mode struct would silently become `stop_val` x ATR); None when the source cannot be read."""
    cls = RUN._blocks().BASES[family][0]
    flagged = False
    for k in cls.__mro__:
        if k is object or k.__module__ == S.__name__:
            continue
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(k)))
        except (OSError, TypeError, SyntaxError):
            return None
        none = lambda n: isinstance(n, ast.Constant) and n.value is None  # noqa: E731
        for fn in ast.walk(tree):
            arms = False
            for n in ast.walk(fn) if isinstance(fn, ast.FunctionDef) else ():
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    at = n.func.attr
                    if at in ("_mkt", "_lim"):
                        pos = 2 if at == "_mkt" else 3                       # (ctx, side[, px], struct)
                        if any(kw.arg == "struct" and not none(kw.value) for kw in n.keywords) or (len(n.args) > pos and not none(n.args[pos])):
                            flagged = True
                    elif at == "_arm":
                        arms = True
            if arms:                                                         # legs (side, px, struct, tp_px): any such tuple of the function
                for n in ast.walk(fn):
                    if isinstance(n, ast.Tuple) and len(n.elts) == 4 and not none(n.elts[2]):
                        flagged = True
    return flagged


# ================================================================ the sheet -> the plan

def _family_notes(family: str) -> str:
    cls = RUN._blocks().BASES[family][0]
    notes = RUN._blocks().BASES[family][3]
    doc = inspect.getdoc(cls) or ""
    return notes + ("\n" + doc if doc else "")


def _setting_problem(k: str, v, spec: tuple, family: str):
    """Why a value is not the setting's (the class's schema) -> words, or None."""
    kind = spec[0]
    if kind == "choice":
        return None if (not isinstance(v, bool) and v in spec[1]) else f"setting {k} {v!r}: one of {', '.join(map(str, spec[1]))}"
    if kind == "bool":
        return None if isinstance(v, bool) else f"setting {k} {v!r}: true or false"
    if kind == "str":
        return None if isinstance(v, str) else f"setting {k} {v!r}: text"
    if kind in ("int", "float"):
        if not _is_num(v):
            return f"setting {k} {v!r}: a number"
        if kind == "int" and float(v) != int(v):
            return f"setting {k} {v!r}: a whole number"
        lo, hi = (tuple(spec[1:3]) + (None, None))[:2]
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            return f"setting {k} {v!r}: a {'whole ' if kind == 'int' else ''}number from {_g(lo)} to {_g(hi)}"
    return None


def _plan(raw) -> tuple:
    """The sheet -> (plan, problems). Every problem is one sentence that names its part; no plan when there is one."""
    bad: list = []

    def no(part, why):
        bad.append(f"{part}: {why}")
    if not isinstance(raw, dict):
        return None, ["a sheet is a JSON object"]
    unknown = sorted(set(raw) - set(SHEET_KEYS))
    if unknown:
        no(", ".join(unknown), f"not a field of a sheet (the fields are {', '.join(SHEET_KEYS)})")
    for k in REQUIRED:
        if k not in raw or raw[k] is None:
            no(k, "required" + (" -- write what the engine cannot do, or [] to say that nothing was left out" if k == "not_run" else ""))
    name = raw.get("name")
    if "name" in raw and not (isinstance(name, str) and NAME.match(name) and len(name) <= 60):
        no("name", "lower-case letters, digits and single '_' (a-z 0-9 _), at most 60: it becomes the folder and the store keys")
    src = raw.get("source")
    if "source" in raw and raw["source"] is not None:
        if not (isinstance(src, dict) and set(src) <= set(SOURCE_KEYS) and any(isinstance(src.get(k), str) and src[k].strip() for k in ("video", "title", "url"))):
            no("source", f"an object with at least one of video, title, url (fields: {', '.join(SOURCE_KEYS)})")
    taught = raw.get("taught")
    if "taught" in raw and raw["taught"] is not None:
        if not (isinstance(taught, list) and taught and all(isinstance(x, str) and x.strip() for x in taught)):
            no("taught", "a non-empty list of sentences, one per rule, as the video says it, with its time mark")
    nr = raw.get("not_run")
    if "not_run" in raw and nr is not None and not (isinstance(nr, list) and all(isinstance(x, str) and x.strip() for x in nr)):
        no("not_run", "a list of sentences (or [] to say that nothing was left out)")
    if raw.get("control", "random") != "random":
        no("control", f"{raw.get('control')!r}: the only control the lane has is 'random' (the pipeline's random entries)")
    costs = R.template("costs")["contract"]
    market = raw.get("market")
    if "market" in raw and market not in costs:
        no("market", f"{market!r}: one of {', '.join(costs)}")
    bars = raw.get("bars")
    if "bars" in raw and bars is not None:
        ok = isinstance(bars, list) and bars and len({str(b) for b in bars}) == len(bars) and all(str(b) in BARS for b in bars)
        if not ok:
            no("bars", f"{bars!r}: a non-empty list without repeats out of {', '.join(BARS)} (minutes)")
            bars = None
        else:
            bars = [str(b) for b in bars]
    side = raw.get("dir")
    if "dir" in raw and side not in SIDES:
        no("dir", f"{side!r}: one of {', '.join(SIDES)}")

    # ---- the family and its settings
    entry, family, cls, own, settings = raw.get("entry"), None, None, {}, {}
    if "entry" in raw and raw["entry"] is not None:
        if not isinstance(entry, dict) or set(entry) - set(ENTRY_KEYS) or not entry.get("family"):
            no("entry", f"an object {{family, settings, words}} (got {entry!r})")
        else:
            try:
                fam, blocks = RM.registry(), RUN._blocks()
            except RM.RegistryBroken as e:
                return None, [f"the families registry is broken: {e}"]
            family = entry["family"]
            if family not in blocks.WRAPPED:
                if family in fam.REGISTRY:
                    no("entry.family", f"{family}: a family of the registry, but not a bar-based block the lane can run (time-fired and Level 2 families come later)")
                else:
                    said = entry.get("words") if isinstance(entry.get("words"), str) and entry["words"].strip() else "the sheet's entry words"
                    no("entry.family", f"{family!r}: no such family -- the sheet needs a rule that: {said} (an entry rule that does not exist yet has to be built "
                                       f"first; the bar-based ones the lane has are {', '.join(sorted(blocks.WRAPPED))})")
                family = None
            else:
                cls = blocks.WRAPPED[family]
                if getattr(cls, "FEATURES", ()):
                    no("entry.family", f"{family} reads Level 2 data: the lane runs families without it only")
                    family = None
            if not (isinstance(entry.get("words"), str) and entry["words"].strip()):
                no("entry.words", "required: the entry in the video's own plain words")
            settings = entry.get("settings") or {}
            if not isinstance(settings, dict):
                no("entry.settings", "an object {setting: value}")
                settings = {}
            if cls is not None and family:
                import run_idea as RI
                skip = RI._reserved(blocks) | set(S.Template.DEFAULTS) | {"auth"}
                sc, d = cls.schema(), cls.defaults()
                own = {k: d[k] for k in sorted(d) if k not in skip and k in sc}
                for k, v in settings.items():
                    if k in ("max_tr", "dir", "exit_bars", "trail_atr", "hold_to", "stop_mode", "stop_val", "tgt_r"):
                        no(f"entry.settings.{k}", "an exit or a limit, not a setting of the entry: it belongs under exits (max_trades, exit_bars) or at the top (dir)")
                    elif k not in own:
                        no(f"entry.settings.{k}", f"not a setting of {family} (its settings: {', '.join(own) or 'none'})")
                    else:
                        w = _setting_problem(k, v, sc[k], family)
                        if w:
                            no("entry.settings", w)
                if "market" in raw and market in costs:
                    roots = fam.library(family)["roots"]
                    if market not in roots:
                        no("market", f"{family} trades {', '.join(roots)}, not {market}")
                if bars:
                    miss = [b for b in bars if b not in cls.SCREEN_TFS]
                    if miss:
                        no("bars", f"{family} runs on {', '.join(cls.SCREEN_TFS)}-minute bars, not {', '.join(miss)}")
    # ---- exits
    ex, tick = raw.get("exits"), (costs[market]["tick"] if market in costs else None)
    out_exits: dict = {}
    struct = False
    if "exits" in raw and raw["exits"] is not None:
        if not isinstance(ex, dict):
            no("exits", "an object {stop_pts | stop_ticks, target_pts | target_ticks, exit_bars, max_trades}")
        else:
            ex = {k: v for k, v in ex.items() if v is not None}
            odd = sorted(set(ex) - set(EXIT_KEYS))
            if odd:
                no("exits." + ", ".join(odd), f"not a field of exits (the fields are {', '.join(EXIT_KEYS)})")
            struct = ex.get("stop") == "struct"
            if "stop" in ex and not struct:
                no("exits.stop", f"{ex['stop']!r}: only \"struct\" (the family's own structure level); a stop in points is stop_pts or stop_ticks")
            sch = S.Template.schema()

            def pts(part: str):
                a, b = ex.get(f"{part}_pts"), ex.get(f"{part}_ticks")
                if a is not None and b is not None:
                    no(f"exits.{part}_pts / exits.{part}_ticks", "both given: give one of them")
                    return None
                if a is None and b is None:
                    no(f"exits.{part}", f"give {part}_pts or {part}_ticks")
                    return None
                v, unit = (a, "pts") if a is not None else (b, "ticks")
                if not _is_num(v) or v <= 0:
                    no(f"exits.{part}_{unit}", f"{v!r}: a positive number")
                    return None
                if unit == "ticks":
                    if float(v) != int(v):
                        no(f"exits.{part}_ticks", f"{v!r}: a whole number of ticks")
                        return None
                    return round(float(v) * tick, 6) if tick else None
                if tick and abs(v / tick - round(v / tick)) > 1e-9:
                    no(f"exits.{part}_pts", f"{v!r} is not a multiple of the tick of {market} ({_g(tick)})")
                    return None
                return float(v)
            stop = target = rr = None
            if struct:
                for k in ("stop_pts", "stop_ticks", "target_pts", "target_ticks"):
                    if k in ex:
                        no(f"exits.{k}", "a structure stop has no size in points and its target is a multiple of the stop distance: give target_r")
                rr = ex.get("target_r")
                if not (_is_num(rr) and rr > 0):
                    no("exits.target_r", "required with a structure stop: a positive multiple of the stop distance (2 = 2R)")
                    rr = None
                elif max(STEPS) * rr > sch["tgt_r"][2]:
                    no("exits.target_r", f"{_g(rr)}: the engine's limit is {_g(sch['tgt_r'][2])} times the stop (the neighbour at 125 % is {_g(max(STEPS) * rr)})")
                    rr = None
                if family and cls is not None and passes_structure(family) is False:
                    no("exits.stop", f"\"struct\": {family} never passes a structure level with its orders, so the engine would stop it at {sch['stop_val'][1]:g} x ATR "
                                     "instead of at a level of the rule; use stop_pts or stop_ticks")
                elif family and cls is not None and passes_structure(family) is None:
                    no("exits.stop", f"\"struct\": the code of {family} cannot be read to see whether it passes a structure level")
            else:
                if "target_r" in ex:
                    no("exits.target_r", "a target in R belongs to a structure stop (\"stop\": \"struct\"); with a stop in points give target_pts or target_ticks")
                stop, target = pts("stop"), pts("target")
                if stop is not None and tick:
                    if stop < 2 * tick - 1e-9:
                        no("exits.stop", f"{_g(stop)} points is under two ticks ({_g(2 * tick)}): the engine never puts a stop closer than two ticks")
                        stop = None
                    elif not sch["stop_val"][1] <= stop <= sch["stop_val"][2]:
                        no("exits.stop", f"{_g(stop)} points: the engine takes {_g(sch['stop_val'][1])} .. {_g(sch['stop_val'][2])}")
                        stop = None
                if stop is not None and target is not None and target / stop > sch["tgt_r"][2] + 1e-12:
                    no("exits.target", f"{_g(target)} points is {target / stop:g} times the stop of {_g(stop)}: the engine's limit is {_g(sch['tgt_r'][2])} times")
                    target = None
            mt = ex.get("max_trades", cls.defaults().get("max_tr") if cls is not None and family else None)
            if "max_trades" in ex or mt is not None:
                lim = sch["max_tr"]
                fam_sch = cls.schema().get("max_tr") if cls is not None and family else None
                lo, hi = (fam_sch[1], fam_sch[2]) if fam_sch and fam_sch[0] == "int" else (lim[1], lim[2])
                if not (_is_num(mt) and float(mt) == int(mt) and lo <= mt <= hi):
                    no("exits.max_trades", f"{mt!r}: a whole number from {lo} to {hi}" + (f" ({family}'s own range)" if fam_sch else ""))
                    mt = None
            if "exit_bars" in ex and "exit_minutes" in ex:
                no("exits.exit_bars / exits.exit_minutes", "both given: give one of them")
            ebars: dict = {}
            if bars:
                if "exit_minutes" in ex:
                    m = ex["exit_minutes"]
                    if not (_is_num(m) and m > 0 and float(m) == int(m)):
                        no("exits.exit_minutes", f"{m!r}: a positive whole number of minutes")
                    else:
                        for b in bars:
                            if int(m) % int(b):
                                no("exits.exit_minutes", f"{int(m)} minutes is not a whole number of {b}-minute bars")
                            else:
                                ebars[b] = int(m) // int(b)
                else:
                    n = ex.get("exit_bars", 0)
                    if not (_is_num(n) and float(n) == int(n) and 0 <= n <= sch["exit_bars"][2]):
                        no("exits.exit_bars", f"{n!r}: a whole number from 0 (none) to {sch['exit_bars'][2]}")
                    else:
                        ebars = {b: int(n) for b in bars}
                over = [b for b, n in ebars.items() if n > sch["exit_bars"][2]]
                if over:
                    no("exits.exit_minutes", f"more than {sch['exit_bars'][2]} bars of {', '.join(over)}-minute bars")
            ok_pts = struct and rr is not None or (stop is not None and target is not None)
            out_exits = {"struct": struct, "stop_pts": stop, "target_pts": target, "target_r": rr, "max_trades": mt, "exit_bars": ebars,
                         "exit_minutes": ex.get("exit_minutes"), "ok": bool(ok_pts)}
            if stop is not None and tick:
                out_exits["stop_ticks"] = int(round(stop / tick))
            if target is not None and tick:
                out_exits["target_ticks"] = int(round(target / tick))
            if stop is not None and target is not None:
                out_exits["tgt_r"] = target / stop
    # ---- the cells: the taught one and its neighbours
    cells: list = []
    if out_exits.get("ok") and tick:
        if struct:
            for i, f in enumerate(STEPS):
                r = round(out_exits["target_r"] * f, 6)
                cells.append({"id": f"struct-r{_num(r)}", "stop_pts": None, "target_pts": None, "tgt_r": r, "centre": f == CENTRE,
                              "stop_scale": None, "target_scale": f})
        else:
            stops = [_tick_round(out_exits["stop_pts"] * f, tick) for f in STEPS]
            targets = [_tick_round(out_exits["target_pts"] * f, tick) for f in STEPS]
            if len(set(stops)) < 3 or len(set(targets)) < 3:
                no("neighbours", f"at 75 % and 125 % the stop {_g(out_exits['stop_pts'])} falls on {', '.join(_g(x) for x in stops)} and the target "
                                 f"{_g(out_exits['target_pts'])} on {', '.join(_g(x) for x in targets)} at the tick {_g(tick)}: the nine cells would not be nine "
                                 "different cells (a wider stop, or a market with a finer tick)")
            else:
                for si, sf in enumerate(STEPS):
                    for ti, tf_ in enumerate(STEPS):
                        s_, t_ = stops[si], targets[ti]
                        r = t_ / s_
                        if r > S.Template.schema()["tgt_r"][2] + 1e-12:
                            no("neighbours", f"stop {_g(s_)} with target {_g(t_)} is {r:g} times the stop: over the engine's limit")
                        cells.append({"id": S.cell_id({"stop_mode": "pts", "stop_val": s_, "tgt_r": r}), "stop_pts": s_, "target_pts": t_, "tgt_r": r,
                                      "centre": sf == CENTRE and tf_ == CENTRE, "stop_scale": sf, "target_scale": tf_})
    # ---- the passes and the window
    sessions = raw.get("sessions")
    window = raw.get("window")
    chosen, by = None, None
    if sessions is None and window is None and "sessions" not in raw:
        no("sessions", "give the session passes the entry may trade in (or a window): " + ", ".join(RM.DAY_PASSES))
    if sessions is not None:
        if not (isinstance(sessions, list) and sessions and len(set(map(str, sessions))) == len(sessions)):
            no("sessions", f"{sessions!r}: a non-empty list without repeats out of {', '.join(RM.DAY_PASSES)}")
        else:
            unk = [s for s in sessions if s not in RM.DAY_PASSES]
            if unk:
                no("sessions", f"{', '.join(map(str, unk))}: not a session pass (the passes: {', '.join(RM.DAY_PASSES)})")
            else:
                chosen = list(sessions)
    trade = None
    if cls is not None and family:
        trade = []
        for s in RM.DAY_PASSES:
            try:
                if cls({"tf": (bars or [cls.SCREEN_TFS[0]])[0], "sess": s, "hold_to": "day"}).sessions():
                    trade.append(s)
            except ValueError:
                pass
        if chosen:
            never = [s for s in chosen if s not in trade]
            if never:
                no("sessions", f"{', '.join(never)}: {family} never trades there (it trades {', '.join(trade)})")
                chosen = None
    win_by = None
    if window is not None:
        w = _parse_window(window)
        if w is None:
            no("window", f"{window!r}: HH:MM-HH:MM on the New York clock, the start before the end")
        elif cls is not None and family:
            fw = getattr(sys.modules[fam.REGISTRY[family][0].__module__], "ENTRY_WINDOWS", {}).get(family)
            if chosen is None and sessions is None:
                chosen = [s for s in RM.DAY_PASSES if s in (trade or []) and PASS_CLOCK[s][0] < w[1] and PASS_CLOCK[s][1] > w[0]]
            if chosen:
                cur = w[0]
                for a, b in sorted(PASS_CLOCK[s] for s in chosen):
                    if a <= cur < b:
                        cur = b
                if cur < w[1]:
                    no("window", f"{window}: the passes {', '.join(chosen)} do not cover it (they run {', '.join(_pass_words(s) for s in chosen)})")
                elif fw is not None:
                    if (fw[0], fw[1] // 60 * 60) == w:
                        win_by = f"the family's own entry window ({_clock(fw[0])}-{_clock(fw[1] // 60 * 60)})"
                    else:
                        no("window", f"{window}: {family} enters only inside {_clock(fw[0])}-{_clock(fw[1] // 60 * 60)} (its own written window) and the engine cannot "
                                     "cut another one; the sheet says what the family cannot do under not_run")
                else:
                    union = (min(PASS_CLOCK[s][0] for s in chosen), max(PASS_CLOCK[s][1] for s in chosen))
                    if union == w:
                        win_by = "the session passes " + ", ".join(chosen)
                    else:
                        no("window", f"{window}: the engine opens an entry window only as whole session passes ({'; '.join(_pass_words(s) for s in chosen)}) or "
                                     f"as a family's own written window ({family} has none): it cannot cut {window}")
            elif sessions is None:
                no("window", f"{window}: no session pass of {family} lies in it")
    if chosen is not None and not bad:
        chosen = [s for s in RM.DAY_PASSES if s in chosen]
    plan = None
    if not bad and family and cls is not None:
        full = {**{k: v for k, v in cls.defaults().items() if k in own}, **settings}
        cap = out_exits["max_trades"]
        eng = {}
        for tf in bars:
            rows = []
            for c in cells:
                p = {**settings, "tf": tf, "sess": "all", "dir": side, "max_tr": cap, "exit_bars": out_exits["exit_bars"][tf],
                     "stop_mode": "struct" if struct else "pts", "tgt_r": c["tgt_r"]}
                if not struct:
                    p["stop_val"] = c["stop_pts"]
                rows.append({"id": c["id"], "params": p, "sessions": list(chosen), "hold_to": RM.HOLD,
                             "class": RUN._blocks().BASES[family][0].__name__})
            eng[tf] = rows
        seeds = R.template("control")["seeds"]
        plan = {"name": name, "source": src, "market": market, "tick": tick, "point_value": costs[market]["point_value"], "bars": bars, "sessions": chosen,
                "window": None if window is None else {"text": window, "by": win_by}, "dir": side, "family": family, "settings": dict(settings),
                "effective": full, "words": entry["words"], "exits": out_exits, "cells": cells, "engine": eng, "taught": list(taught), "not_run": list(nr or []),
                "nothing_left_out": not nr, "control": {"kind": "random", "p_entry": RM.C1_P_ENTRY, "seeds": seeds,
                                                         "sides": ["both"] + ([side] if side != "both" else [])},
                "struct": struct, "family_words": _family_notes(family)}
        plan["lane_notes"] = _lane_notes(plan)
    return plan, bad


def _lane_notes(plan: dict) -> list:
    """What is true of the run whatever the sheet says: the facts a reader holding the video next to the Run lines needs."""
    n, notes = len(plan["sessions"]), []
    cap = plan["exits"]["max_trades"]
    if n > 1:
        notes.append(f"CAPPED PER SESSION PASS, NOT PER DAY: max_trades {cap} counts inside each pass ({n} passes: {', '.join(plan['sessions'])}), so a day can "
                     f"hold up to {cap * n} trades; a family's own loss or trade count ({', '.join(k for k in plan['effective'] if 'loss' in k or k.startswith('max_')) or 'none'}) "
                     "counts inside one pass too.")
        notes.append("The passes are independent: a trade of one pass may still be open when another pass enters (one position at a time holds inside a pass only).")
    else:
        a, b = PASS_CLOCK[plan["sessions"][0]]
        notes.append(f"ONE session pass ({plan['sessions'][0]}, {_clock(a)}-{_clock(b)}): the cap of {cap} trade{'s' * (cap != 1)} is a cap of that window, which is the day's cap of "
                     "the rule as far as the video's window lies inside it.")
    notes.append(f"Every trade is flat by {S.DAY_FLAT} ET ({S.HALF_DAY_FLAT} on an equity half day); no entry in the last 5 minutes of a pass.")
    notes.append("Costs: $4.00 a round turn and 1 tick of slippage on market and stop fills, 1 contract (the engine's own).")
    if plan["struct"]:
        notes.append("The stop is the family's structure level of each entry (its size differs from trade to trade; the engine never puts it closer than two ticks "
                     "or 0.25 ATR); `stop_val` is not used.")
    return notes


# ================================================================ check

def _run_lines(p: dict) -> list:
    e = p["exits"]
    side = {"both": "both sides", "long": "long only", "short": "short only"}[p["dir"]]
    sets = ", ".join(f"{k} {_g(v) if _is_num(v) else v}" for k, v in p["effective"].items()) or "no settings of its own"
    given = ", ".join(f"{k} {_g(v) if _is_num(v) else v}" for k, v in p["settings"].items())
    out = [f"entry     {p['family']} with {sets}" + (f" (the sheet's own: {given})" if given else " (the family's defaults)"),
           f"side      {side} (dir={p['dir']})",
           f"market    {p['market']} (tick {_g(p['tick'])}, ${_g(p['point_value'])} a point)",
           f"bars      {' and '.join(p['bars'])}-minute bars, one run each",
           f"passes    {' '.join(p['sessions'])} ({'; '.join(_pass_words(s) for s in p['sessions'])}), each its own pass, hold to the day (flat {S.DAY_FLAT} ET)"]
    if p["window"]:
        out.append(f"window    {p['window']['text']} ET, honoured by {p['window']['by']}")
    if e["struct"]:
        out.append(f"stop      the family's structure level (stop_mode struct)")
        out.append(f"target    {_g(e['target_r'])} x the stop distance (tgt_r {_g(e['target_r'])})")
    else:
        out.append(f"stop      stop {_g(e['stop_pts'])} points ({e['stop_ticks']} ticks), stop_mode pts")
        out.append(f"target    target {_g(e['target_pts'])} points ({e['target_ticks']} ticks) = tgt_r {_g(round(e['tgt_r'], 6))} x the stop")
    bars = e["exit_bars"]
    same = len(set(bars.values())) == 1
    out.append("time exit " + ("none" if not any(bars.values()) else
                               (f"after {next(iter(bars.values()))} bars" if same else "after " + ", ".join(f"{v} bars of {k}" for k, v in bars.items()))
                               + (f" ({e['exit_minutes']} minutes)" if e["exit_minutes"] else "")))
    out.append(f"cap       at most {e['max_trades']} trade{'s' * (e['max_trades'] != 1)} a session pass (max_tr)")
    c = p["cells"]
    if p["struct"]:
        out.append(f"cells     {len(c)}: the taught cell and its neighbours, target {', '.join(_g(x['tgt_r']) for x in c)} x the stop")
    else:
        out.append(f"cells     {len(c)}: the taught cell and its 8 neighbours, stops {', '.join(_g(x) for x in sorted({y['stop_pts'] for y in c}))} x targets "
                   f"{', '.join(_g(x) for x in sorted({y['target_pts'] for y in c}))} points")
    sides = p["control"]["sides"]
    out.append(f"control   random entries, p 0.5 a bar, {p['control']['seeds']} seeds, same exits and passes: " +
               " and ".join("both sides" if s == "both" else f"{s} only" for s in sides))
    return out


def _text_check(p: dict) -> str:
    src = p["source"] or {}
    head = ", ".join(str(src[k]) for k in ("title", "channel", "url", "video") if src.get(k))
    out = [f"SHEET {p['name']}: {p['family']} on {p['market']}, {' and '.join(p['bars'])}-minute bars, {p['dir']} -- NOTHING WAS RUN",
           f"source: {head}", "", f"THE ENTRY, as the video says it: {p['words']}", "", "TAUGHT (the sheet's own sentences)"]
    out += [f"  {i}. {x}" for i, x in enumerate(p["taught"], 1)]
    out += ["", "RUN (the exact engine inputs; every number is the sheet's own)"] + [f"  {x}" for x in _run_lines(p)]
    out += ["", "NOT RUN (the person who wrote the sheet says the engine cannot do these)"]
    out += ([f"  - {x}" for x in p["not_run"]] if p["not_run"] else
            ["  nothing was left out: the person who wrote the sheet says so"])
    out += ["", "ALSO TRUE OF THE RUN (said by the lane, whatever the sheet says)"] + [f"  - {x}" for x in p["lane_notes"]]
    out += ["", "THE FAMILY, in the registry's words and its own"] + [f"  {x}" for x in textwrap.wrap(p["family_words"].replace("\n", " "), 118)[:14]]
    return "\n".join(out)


def check(sheet) -> dict:
    """`bp.py taught check <sheet>`: the sheet is validated and what will run is printed. Nothing is run and nothing is written.
    -> api.result with `plan` (None when refused), `problems` (every one, a sentence naming its part), `text`."""
    try:
        raw = load(sheet)
    except J.Refuse as e:
        r = api.refused(CHECK, str(e))
        return {**r, "plan": None, "problems": [str(e)]}
    plan, bad = _plan(raw)
    name = raw.get("name") if isinstance(raw, dict) else None
    if bad or plan is None:
        why = "; ".join(bad) or "the sheet cannot be read"
        r = api.refused(CHECK, f"the sheet is not whole: {why}", name)
        return {**r, "plan": None, "problems": bad, "text": "REFUSED: the sheet is not whole\n" + "\n".join(f"  - {x}" for x in bad)}
    return api.result(CHECK, name, plan=plan, problems=[], text=_text_check(plan),
                      next=f"bp.py taught run {name if isinstance(sheet, dict) else sheet} runs it on the build days (it can take a while: the controls are 10 seeds).")


# ================================================================ the stores

def _unit_key(name: str, market: str, tf: str) -> str:
    return f"{name}-{market}-tf{tf}"


def _ctl_key(name: str, market: str, tf: str, side: str) -> str:
    return f"{name}__ctl{'' if side == 'both' else '_' + side}-{market}-tf{tf}"


def _exit(plan: dict, tf: str, cell: dict, stop_pts=None) -> dict:
    """A cell's exit as a Template's inputs (the control's too: a structure stop is a size in points there)."""
    return {"stop_mode": "pts", "stop_val": stop_pts if plan["struct"] else cell["stop_pts"], "tgt_r": cell["tgt_r"],
            "exit_bars": plan["exits"]["exit_bars"][tf], "max_tr": plan["exits"]["max_trades"]}


def _unit_part(plan: dict, tf: str) -> dict:
    blocks = RUN._blocks()
    cls = blocks.WRAPPED[plan["family"]]
    grid = []
    for k, (c, e) in enumerate(zip(plan["cells"], plan["engine"][tf])):
        x = {kk: e["params"][kk] for kk in ("stop_mode", "tgt_r", "exit_bars", "max_tr") + (() if plan["struct"] else ("stop_val",))}
        grid.append({"id": c["id"], "variant": {}, "exit": x, "vi": 0, "xi": k, "spec": (cls, dict(e["params"]))})
    meta = {"family": plan["family"], "idea": plan["name"], "taught": True, "tf": tf, "sessions": plan["sessions"], "variants": [{}], "fixed": plan["settings"],
            "limits": {"max_tr": plan["exits"]["max_trades"], "dir": plan["dir"], "exit_bars": plan["exits"]["exit_bars"][tf]}, "filter": None,
            "exits": "taught", "both_sides_declared": bool(blocks.BASES[plan["family"]][2]), "mirror": None,
            "note": f"taught rule {plan['name']}: {plan['family']}, the sheet's own exits ({'structure stop' if plan['struct'] else 'stop ' + _g(plan['exits']['stop_pts']) + ' pts'})"}
    return RUN._part(_unit_key(plan["name"], plan["market"], tf), "unit", plan["market"], tf, grid, plan["sessions"], None, meta, plan["family"],
                     RUN._kw(plan["family"]), None)


def _control_part(plan: dict, tf: str, side: str, stop_pts=None) -> dict:
    import l2ref
    seeds = list(range(1, plan["control"]["seeds"] + 1))
    grid = []
    for sd in seeds:
        for k, c in enumerate(plan["cells"]):
            x = _exit(plan, tf, c, stop_pts)
            grid.append({"id": f"s{sd}_{c['id']}", "variant": {"seed": sd}, "exit": x, "vi": sd - 1, "xi": k,
                         "spec": (l2ref.Random, {"tf": tf, "sess": "all", "p_entry": RM.C1_P_ENTRY, "seed": sd, "dir": side, **x})})
    meta = {"family": "random", "tf": tf, "control": "c1", "p_entry": RM.C1_P_ENTRY, "seeds": seeds, "sessions": plan["sessions"], "side": side,
            "note": f"{len(seeds)}-seed random entries of the taught rule {plan['name']}: {'both sides' if side == 'both' else side + ' only'}, the same exits and passes"}
    return RUN._part(_ctl_key(plan["name"], plan["market"], tf, side), "pool", plan["market"], tf, grid, plan["sessions"], None, meta, None, {}, None)


def _unit_row(plan, tf, name=None) -> dict:
    return {"id": f"{plan['name']}|{tf}", "addr": _unit_key(plan["name"], plan["market"], tf), "uid": f"{plan['name']}|{tf}", "key": _unit_key(plan["name"], plan["market"], tf),
            "family": plan["family"], "root": plan["market"], "tf": tf, "sess": None, "label": "", "filter": None, "group": None, "side": None, "placebo": 0,
            "controls": ["c1"]}


@contextlib.contextmanager
def _draws(n):
    keep = J.RULE["draws"]
    try:
        if n:
            J.RULE["draws"] = int(n)
        yield
    finally:
        J.RULE["draws"] = keep


def _median_stop(st: dict, plan: dict) -> float | None:
    """The size, in points, of the taught trades' own stops: the median of |entry - stop| of the centre cell (a structure stop only:
    random entries have no level of their own). A size, never a result. None: no trade with a stop."""
    cid = next(c["id"] for c in plan["cells"] if c["centre"])
    r = J.cellx(st, cid, None, None)["risk"]
    r = np.asarray(r, np.float64)
    r = r[np.isfinite(r) & (r > 0)]
    if not len(r):
        return None
    return max(_tick_round(float(np.median(r)), plan["tick"]), 2 * plan["tick"])


# ================================================================ the reads

def _metrics(x: dict, cal) -> dict:
    m = LB.metrics(x, cal)
    net = np.asarray(x["net"], np.float64)
    w, l_ = net[net > 0], net[net < 0]
    aw = float(w.mean()) if len(w) else None
    al = float(l_.mean()) if len(l_) else None
    return {"trades": m["trades"], "net": m["net"], "win": m["win"], "avg_trade": m["avg_trade"], "pf": m["pf"], "avg_win": aw, "avg_loss": al,
            "win_loss": (aw / abs(al)) if aw is not None and al else None, "max_dd": m["max_dd"], "sharpe": m["sharpe"], "worst_open_loss": m["worst_open_loss"],
            "days": m["days"]}


def _kind(line: str) -> str:
    return "steadiness" if line in STEADY else "gate" if line.startswith("P3") else "proof" if line.startswith("P4") else "lock"


def _beats(st: dict, u: dict, cid: str, sessions: list, pool: dict, real_net: float, what: str) -> dict:
    """The judge's c1 reading of ONE cell against one random-entry pool: drawn pass by pass (the same exit cell, the same days of that pass;
    judge.c1_table with a seed of its own per pass), the draws added over the passes, then judge.verdict."""
    draws, fb, short, n = None, 0.0, 0, 0
    for s in sessions:
        us = {**u, "sess": s}
        v = J.c1_table(st, us, [cid], pool, J.seed_of(f"{u['uid']}|{s}|{cid}", what))
        draws = v["draws"] if draws is None else draws + v["draws"]
        k = len(J.cellx(st, cid, s, us)["date"])
        fb, n, short = fb + v["fallback_share"] * k, n + k, short + v["short"]
    ctl = {"draws": draws, "mean": float(draws.mean()), "sd": float(draws.std(ddof=1)), "p95": float(np.percentile(draws, 95)), "replicates": len(draws),
           "real_replicates": len(pool), "short": int(short), "fallback_share": fb / n if n else 0.0}
    return J.verdict(real_net, ctl, True)


def _random_row(line: str, verdict, tries: int, what: str, side_word: str = "") -> dict:
    row = G.random(None if verdict is None else verdict["p_beat"], tries, what)
    row = {**row, "line": line, "text": line + row["text"][len("P4.2"):]}
    if verdict is not None:
        row.update(seeds=verdict["real_replicates"], lift=verdict["lift"], unmatched=verdict.get("short", 0))
        if verdict.get("short"):
            row["text"] += f"; {verdict['short']:,} trades had no random match"
    return row


def _row_not_run(line: str, why: str) -> dict:
    return L._row(line, None, None, PR.random_bar(1), f"not run: {why}")


def _prop(x: dict, cal) -> dict:
    o = PP.odds(x, cal)
    return {"account": o["account"]["name"], "confirmed": o["account"]["confirmed"], "size": o["size"], "payout_size": o["payout_size"], "eval": o["eval"],
            "payout": o["payout"], "label": o["label"], "days": o["days"], "need": o["need"],
            "stress": {k: o["stress"][k] for k in ("size", "payout_size", "eval", "payout")}}


def _mean(vals):
    v = [x for x in vals if x is not None]
    return float(np.mean(v)) if v else None


def _read_bar(plan: dict, tf: str, out: Path, named, pools: dict, stop_c, tries: int = 1) -> dict:
    """Everything the lane reads of ONE bar size: the nine cells (or three), the centre box's lines, the averages."""
    key = _unit_key(plan["name"], plan["market"], tf)
    st, where = T._open(out, key)
    if st["meta"].get("period") != RUN.PERIOD or (st["meta"].get("days") or None) != named:
        raise J.Refuse(f"store {where} is not the store asked for: it is of period {st['meta'].get('period')!r}"
                       + (f", run on {len(st['meta']['days'])} named days" if st["meta"].get("days") else "") + f" (asked: {RUN.PERIOD}"
                       + (f", {len(named)} named days)" if named else ", the whole range)"))
    u = _unit_row(plan, tf)
    ids = [c["id"] for c in plan["cells"]]
    gone = [i for i in ids if i not in st["_idx"]]
    if gone:
        raise J.Refuse(f"store {where} lacks the cell {gone[0]}: it is not the store of this sheet")
    cal = T.build_days(u, named)
    ords = LB._ordinals(cal)
    t = {**T._data(st, u, {"ids": ids, "dead": 0, "dup": 0}, ords, where), "sides": plan["dir"]}
    sess = plan["sessions"]
    cells = []
    for i, c in enumerate(plan["cells"]):
        x = J.cellx(st, c["id"], None, u)
        bx = T.box(st, u, c["id"], named)
        b = ST._one_box(t, c["id"])
        rows = [r for r in G.variant_rows(b, []) if r["line"] != "P3.6"] + [fn(bx) for fn in L.BOX] + [G.reshuffle_box(b)]
        real = float(t["net"][i].sum())
        for side in plan["control"]["sides"]:
            line = "P4.2" if side == "both" else "P4.2s"
            what = ("random-entry runs of the same box" + ("" if plan["dir"] == "both" else " (both sides: the pipeline's own control)") if side == "both" else
                    f"random-entry runs of the same box ({side} entries only: the drift of the market on that side)")
            pool = pools.get(side)
            if pool is None:
                rows.append(_row_not_run(line, "no taught trade to take a stop size from" if plan["struct"] else "the control is not on disk"))
            else:
                v = _beats(st, u, c["id"], sess, pool, real, f"taught-c1-{side}")
                row = _random_row(line, v, tries, what)
                rows.append(row)
        rows = [{**r, "kind": _kind(r["line"])} for r in rows]
        steady = {r["line"]: r["number"] for r in rows if r["line"] in STEADY}
        m = _metrics(x, ords)
        m.update(dd_open=L._drawdown(bx["day"], bx["open"]), months_won=steady.get("P3.8"), best_month_share=steady.get("P3.9"), losing_day_run=steady.get("P3.10"))
        held = [r for r in rows if r["passed"] in (True, False)]
        cells.append({**{k: c[k] for k in ("id", "stop_pts", "target_pts", "tgt_r", "centre", "stop_scale", "target_scale")}, "metrics": m,
                      "years": LB.per_year(x, ords), "prop": _prop(x, cal), "lines": rows, "held": sum(r["passed"] is True for r in held), "of": len(held),
                      "failed": [r["line"] for r in held if r["passed"] is False]})
    centre = next(c for c in cells if c["centre"])
    neigh = [c for c in cells if not c["centre"]]
    keys = ("trades", "net", "win", "pf", "avg_win", "avg_loss", "win_loss", "max_dd", "dd_open", "sharpe", "worst_open_loss", "months_won", "best_month_share",
            "losing_day_run")
    avg = {k: _mean([c["metrics"][k] for c in cells]) for k in keys}
    avg["avg_trade"] = (avg["net"] / avg["trades"]) if avg["trades"] else None
    navg = {k: _mean([c["metrics"][k] for c in neigh]) for k in ("trades", "net")}
    navg["avg_trade"] = (navg["net"] / navg["trades"]) if navg["trades"] else None
    years = []
    for y in centre["years"]:
        row = [next((z for z in c["years"] if z["period"] == y["period"]), None) for c in cells]
        row = [z for z in row if z]
        tr, nt = _mean([z["trades"] for z in row]), _mean([z["net"] for z in row])
        years.append({"period": y["period"], "trades": tr, "net": nt, "avg_trade": (nt / tr) if tr else None, "win": _mean([z["win"] for z in row]),
                      "pf": _mean([z["pf"] for z in row]), "max_dd": _mean([z["max_dd"] for z in row])})
    prop = {"eval": _mean([c["prop"]["eval"] for c in cells]), "payout": _mean([c["prop"]["payout"] for c in cells]),
            "stress_eval": _mean([c["prop"]["stress"]["eval"] for c in cells]), "stress_payout": _mean([c["prop"]["stress"]["payout"] for c in cells])}
    return {"tf": tf, "store": where, "range": {"start": cal[0] if cal else None, "end": cal[-1] if cal else None, "sessions": len(cal)},
            "cells": cells, "centre": centre, "neighbours": {**navg, "held": _mean([c["held"] for c in neigh]), "of": centre["of"]},
            "average": {**avg, "held": _mean([c["held"] for c in cells]), "prop": prop}, "years_average": years, "lines": centre["lines"],
            "control_stop_pts": stop_c}


# ================================================================ the words

def _table(rows: list, head: list) -> list:
    w = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    fmt = lambda r: "  ".join(str(v).ljust(w[i]) if i == 0 else str(v).rjust(w[i]) for i, v in enumerate(r))  # noqa: E731
    return [fmt(head), *[fmt(r) for r in rows]]


def _fv(k: str, v) -> str:
    if v is None:
        return "n/a"
    if k in ("net", "avg_trade", "avg_win", "avg_loss", "max_dd", "dd_open", "worst_open_loss"):
        return _usd(v)
    if k in ("win", "months_won", "best_month_share"):
        return _pc(v)
    if k == "trades":
        return f"{v:,.0f}"
    if k == "losing_day_run":
        return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"
    return "inf" if v == float("inf") else f"{v:.2f}"


def _headline(plan: dict, bars: dict, smoke: bool) -> str:
    sets = ", ".join(f"{k} {_g(v) if _is_num(v) else v}" for k, v in plan["effective"].items())
    e = plan["exits"]
    exits = ("a structure stop, target " + _g(e["target_r"]) + "R" if plan["struct"] else f"stop {_g(e['stop_pts'])} / target {_g(e['target_pts'])} points")
    per = "passes" if len(plan["sessions"]) > 1 else "pass"
    what = (f"{plan['name']}: {plan['family']} ({sets or 'defaults'}), {plan['dir']}{' only' if plan['dir'] != 'both' else ' sides'}, "
            f"{' and '.join(plan['bars'])}-minute bars, {exits}, up to {e['max_trades']} trades a session pass over {len(plan['sessions'])} {per} ({' '.join(plan['sessions'])})")
    left = (f"the sheet leaves out {len(plan['not_run'])} thing{'s' * (len(plan['not_run']) != 1)} the video says (listed below)" if plan["not_run"]
            else "nothing was left out, the person who wrote the sheet says")
    v = []
    for tf, b in bars.items():
        c, n = b["centre"], b["neighbours"]
        m = c["metrics"]
        miss = f" (misses {', '.join(c['failed'])})" if c["failed"] else ""
        v.append(f"{tf}-minute bars make {_usd(m['avg_trade'])} a trade on {m['trades']:,} trades and hold {c['held']} of {c['of']} lines{miss}; the neighbours average "
                 f"{_usd(n['avg_trade'])} a trade")
    return (("SMOKE RUN, no verdict: " if smoke else "") + what + "; " + left + "; verdict: " + "; ".join(v) + ".")


def _text_run(plan: dict, bars: dict, head: str, smoke) -> str:
    out = [head, ""]
    rng = next(iter(bars.values()))["range"]
    out.append((f"SMOKE RUN on {len(smoke) if smoke else 0} named build days" if smoke else f"BUILD DAYS {rng['start']} .. {rng['end']}") +
               f" ({rng['sessions']:,} session days), 1 contract after costs. The unseen days (2025-07-01 on) were not read.")
    for tf, b in bars.items():
        c, a, n = b["centre"], b["average"], b["neighbours"]
        out += ["", f"=== {tf}-MINUTE BARS ===", ""]
        names = [("trades", "trades"), ("net", "net"), ("win", "win rate"), ("avg_trade", "average trade"), ("pf", "profit factor"),
                 ("avg_win", "average win"), ("avg_loss", "average loss"), ("win_loss", "average win / average loss"), ("max_dd", "worst drawdown, daily"),
                 ("dd_open", "worst drawdown, open losses counted"), ("sharpe", "Sharpe"), ("months_won", "months won"),
                 ("best_month_share", "best month, share of the profit"), ("losing_day_run", "longest run of losing days")]
        rows = [[lab, _fv(k, c["metrics"].get(k)), _fv(k, a.get(k))] for k, lab in names]
        rows.append(["prop eval odds, 30 days (LucidPro 50K, no DLL)", _pc(c["prop"]["eval"]), _pc(a["prop"]["eval"])])
        rows.append(["prop payout odds (stress, \"live is worse\", beside)", f"{_pc(c['prop']['payout'])} ({_pc(c['prop']['stress']['payout'])})",
                     f"{_pc(a['prop']['payout'])} ({_pc(a['prop']['stress_payout'])})"])
        rows.append(["prop eval odds, stress", _pc(c["prop"]["stress"]["eval"]), _pc(a["prop"]["stress_eval"])])
        what = "the taught cell" if plan["struct"] else f"the taught cell (stop {_g(c['stop_pts'])} / target {_g(c['target_pts'])})"
        out += _table(rows, ["", what, f"average of the {len(b['cells'])} cells"])
        out += ["", f"The neighbours (the {len(b['cells']) - 1} others): average trade {_usd(n['avg_trade'])}, they hold {n['held']:.1f} of {n['of']} lines on average "
                    f"(the taught cell holds {c['held']})."]
        if plan["struct"]:
            rows = [[f"target {_g(x['tgt_r'])}R", _usd(x["metrics"]["avg_trade"]), f"{x['metrics']['trades']:,}", _usd(x["metrics"]["net"]),
                     f"{x['held']} of {x['of']}", _pc(x["prop"]["eval"])] for x in b["cells"]]
            out += ["", *_table(rows, ["cell", "average trade", "trades", "net", "lines held", "eval odds"])]
        else:
            tg = sorted({x["target_pts"] for x in b["cells"]})
            sp = sorted({x["stop_pts"] for x in b["cells"]})
            by = {(x["stop_pts"], x["target_pts"]): x for x in b["cells"]}
            rows = [[f"stop {_g(s)}", *[f"{_usd(by[(s, t)]['metrics']['avg_trade'])} ({by[(s, t)]['held']}/{by[(s, t)]['of']})" for t in tg]] for s in sp]
            out += ["", "THE NINE CELLS: average trade (lines held)", *_table(rows, ["", *[f"target {_g(t)}" for t in tg]])]
        out += ["", "LINES on the taught cell (the pipeline's own functions and words)"] + [f"  {r['text']}" for r in b["lines"]]
        rows = [[y["period"], f"{y['trades']:,.0f}", _usd(y["net"]), _usd(y["avg_trade"]), _pc(y["win"]), _fv("pf", y["pf"]), _usd(y["max_dd"])] for y in c["years"]]
        out += ["", "PER YEAR, then combined: the taught cell", *_table(rows, ["year", "trades", "net", "avg trade", "win", "PF", "drawdown"])]
        rows = [[y["period"], f"{y['trades']:,.0f}", _usd(y["net"]), _usd(y["avg_trade"]), _pc(y["win"]), _fv("pf", y["pf"]), _usd(y["max_dd"])] for y in b["years_average"]]
        out += ["", f"PER YEAR, then combined: the average of the {len(b['cells'])} cells", *_table(rows, ["year", "trades", "net", "avg trade", "win", "PF", "drawdown"])]
        if b.get("control_stop_pts"):
            out.append(f"(the random entries used the median stop of the taught trades, {_g(b['control_stop_pts'])} points, at the same target in R)")
    out += ["", "NOT RUN (the person who wrote the sheet)"]
    out += [f"  - {x}" for x in plan["not_run"]] if plan["not_run"] else ["  nothing was left out: the person who wrote the sheet says so"]
    out += ["", "ALSO TRUE OF THE RUN (the lane)"] + [f"  - {x}" for x in plan["lane_notes"]]
    out += ["", "HONEST LIMITS"] + [f"  - {x}" for x in LIMITS]
    return "\n".join(out)


# ================================================================ run

def _base(root, name: str, named) -> Path:
    b = where(root) / name
    return b / "smoke" if named else b


def _code(family: str) -> dict:
    return {**RUN.code(family), "blueprint/taught.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]}


def run(sheet, root=None, workers=None, days=None, progress=None, draws=None) -> dict:
    """`bp.py taught run <sheet>`: the rule as taught on the build days (module docstring). `days` = named build days: a SMOKE RUN (its own
    folder, never a verdict). Refused: a day after 2025-06-30 (before anything is read); a sheet that is not whole; a sheet of a name that is
    on file with other contents (a changed rule is a new sheet with its own name); what the runner refuses (the no-start window, a store of
    other inputs). -> api.result with `result` (the saved document) and `text`."""
    named = None if days is None else RUN.seal(list(days))                    # THE SEAL, first
    raw = load(sheet)
    plan, bad = _plan(raw)
    if bad or plan is None:
        raise J.Refuse("the sheet is not whole: " + "; ".join(bad or ["it cannot be read"]) + " (bp.py taught check says each part)")
    name = plan["name"]
    base = _base(root, name, named)
    f = base / "sheet.json"
    if f.exists():
        try:
            on_file = json.loads(f.read_text())
        except ValueError:
            on_file = None
        if on_file is not None and _canon(on_file) != _canon(raw):
            raise J.Refuse(f"{name}: a sheet of this name is on file ({f}) with other contents: a changed rule is a new sheet with its own name "
                           f"(for example {name}_v2), as a changed idea is a new round")
    out, ledger = base / "runs", base / "ledger.csv"
    pr = progress
    units = [_unit_part(plan, tf) for tf in plan["bars"]]
    ctl_sides = plan["control"]["sides"]
    stops = {tf: None for tf in plan["bars"]}
    rows = []
    n = None if workers is None else int(workers)
    if not plan["struct"]:
        todo = units + [_control_part(plan, tf, s) for tf in plan["bars"] for s in ctl_sides]
        rows = RUN._run(todo, n, out, ledger, named, None, pr, None, False, f"taught {name}")
    else:
        rows = RUN._run(units, n, out, ledger, named, None, pr, None, False, f"taught {name}")
        bad_rows = [r for r in rows if r["ok"] is False]
        if not bad_rows:
            J.reset()
            for tf in plan["bars"]:
                st, _ = T._open(out, _unit_key(name, plan["market"], tf))
                stops[tf] = _median_stop(st, plan)
            ctl = [_control_part(plan, tf, s, stops[tf]) for tf in plan["bars"] if stops[tf] for s in ctl_sides]
            if ctl:
                rows += RUN._run(ctl, n, out, ledger, named, None, pr, None, False, f"taught {name}")
    broke = [r for r in rows if r["ok"] is False]
    if broke:
        why = broke[0].get("error") or "sessions were dropped by a strategy error"
        raise J.Refuse(f"{broke[0]['key']}: {why}: no store was written; the family has to be fixed first (a code problem, not a verdict on the rule)")
    J.reset()
    bars = {}
    with _draws(draws):
        for tf in plan["bars"]:
            pools = {}
            for s in ctl_sides:
                k = _ctl_key(name, plan["market"], tf, s)
                if (out / k / "run.json").exists():
                    pools[s] = T.pool_seeds(out, k, [c["id"] for c in plan["cells"]], plan["control"]["seeds"])
            bars[tf] = _read_bar(plan, tf, out, named, pools, stops[tf])
    head = _headline(plan, bars, bool(named))
    smoke = named or False
    text = _text_run(plan, bars, head, smoke)
    doc = {"name": name, "smoke": bool(named), "days": named, "headline": head, "plan": plan, "bars": bars, "limits": list(LIMITS), "code": _code(plan["family"]),
           "stores": [{k: r.get(k) for k in ("key", "kind", "trades", "skipped", "code_same")} for r in rows],
           "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "text": text}
    _write(f, raw)
    _write(base / "result.json", doc)
    lines = [{**r, "bar": tf} for tf, b in bars.items() for r in b["lines"]]
    return api.result(RUN_, name, status="smoke" if named else "done", lines=_clean(lines), text=text, saved=[str(base / "result.json")], result=doc, dry_run=bool(named),
                      next="This is the rule as taught, in-sample. The unseen days are read once, and only when a person asks for it.")


# ================================================================ show, list

def show(name: str, root=None) -> dict:
    """`bp.py taught show <name>`: the last result again (the full run when there is one, else the smoke run)."""
    base = where(root) / str(name)
    for f in (base / "result.json", base / "smoke" / "result.json"):
        if f.exists():
            doc = json.loads(f.read_text())
            return api.result(SHOW, name, status="smoke" if doc.get("smoke") else "done", text=doc["text"], result=doc, saved=[str(f)])
    raise J.Refuse(f"{name}: no result on file under {where(root)} (bp.py taught run <sheet> makes one)")


def listing(root=None) -> dict:
    """`bp.py taught list`: one row a sheet on file: its name, whether it has a full result, and the first line of it."""
    top = where(root)
    rows = []
    for d in sorted(p for p in top.glob("*") if p.is_dir()) if top.exists() else []:
        full, smoke = d / "result.json", d / "smoke" / "result.json"
        f = full if full.exists() else smoke if smoke.exists() else None
        if f is None and not (d / "sheet.json").exists():
            continue
        doc = json.loads(f.read_text()) if f else {}
        rows.append({"name": d.name, "status": "done" if full.exists() else "smoke only" if smoke.exists() else "sheet only", "utc": doc.get("utc"),
                     "headline": doc.get("headline")})
    text = "\n".join(f"{r['name']}: {r['status']}" + (f" -- {r['headline']}" if r["headline"] else "") for r in rows) or f"no sheet on file under {top}"
    return api.result(LIST, None, rows=rows, text=text)


def command(sub: str, arg=None, root=None, *, days=None, workers=None, draws=None, progress=None) -> dict:
    """The command line's one entry (blueprint/cli.py): `taught <sub>`."""
    if sub == "check":
        if arg is None:
            raise J.Refuse("taught check needs the sheet: bp.py taught check <sheet.json>")
        return check(arg)
    if sub == "run":
        if arg is None:
            raise J.Refuse("taught run needs the sheet: bp.py taught run <sheet.json>")
        if not isinstance(arg, dict) and not Path(arg).exists() and (where(root) / str(arg) / "sheet.json").exists():
            arg = where(root) / str(arg) / "sheet.json"           # a name on file: run it again (a run that is stored does no work)
        return run(arg, root, workers=workers, days=days, progress=progress, draws=draws)
    if sub == "show":
        if arg is None:
            raise J.Refuse("taught show needs the sheet's name: bp.py taught show <name>")
        return show(arg, root)
    if sub == "list":
        return listing(root)
    raise J.Refuse(f"taught {sub}: one of check, run, show, list")
