"""pipe_rules.py -- the pipeline's gate numbers as data (pipeline plan A, task 1). Every number a pipeline gate holds a
result against is READ from templates/pipeline.json (or, for a line of the law, from rules.json through rules.py); none is
typed in code. A change of a number is a change of the pipeline's rules (the owner's word), made in the JSON.

  need(*keys)          one number, or one level, of pipeline.json: need("raw", "low", "share") -> 0.5 · need("raw", "low") ->
                       {"share", "floor_part", "trades"} · need() -> the whole file. A copy: a caller cannot change the rules.
                       A key the file does not have, a note ('_...'), a key under a number or a list: R.RuleError
  mode()               "variant" (the shipped default, the owner 2026-10-08: the hard rules are judged on ONE picked box, the map gets a loose
                       check) or "map" (the legacy behaviour: the whole 144-box map is judged); a file without the key reads "map"; any other
                       word: R.RuleError. `variant` = the numbers of variant mode (map_share, region_boxes, region_trades, floor_part)
  random_bar(tries)    the share of the random tables an idea must beat on its `tries`-th try: 1 - alpha / max(1, tries) --
                       the law's ladder of line 2.3 (95 %, 97.5 %, 98.3 %, 98.75 %, 99 %), carried on past its fifth round
  floor(root, part)    `part` of the market's cost floor of line 2.2, in dollars a trade: floor("NQ", 0.5) -> 35.0
  gates()              "prop" (the shipped default, the owner 2026-10-10: only three things ask -- the picked box makes money on the build days,
                       its eval odds are prop.eval or more, it still makes money on the unseen days; every other line is a LABEL) or "law"
                       (every line asks, the pipeline as it was). A file without `gates` reads "law". In "prop" the file's `gates.variant`
                       numbers are laid over `variant`, so need("variant") says what the mode asks; any other word: R.RuleError
  prop_gates()         gates() == "prop"
  winlane(unit=None)   "off" (the shipped default: no win-rate rows), "label" (rows P3.11 and P3.12 are printed on every box and ask nothing) or "ask"
                       (they ask); a file without `winlane` reads "off"; any other word: R.RuleError. The numbers: need("winlane", ...).
                       `winlane.cards` (a list of card names; empty or missing = every card) says WHICH ideas the lane is on: a heat map
                       of card C is named C_a5 / C_b1 ... (its unit starts with that), and any other unit reads "off" -- so a hunt for a win
                       rate does not change how the rest of the queue is judged. With `cards` set, a call without a unit reads "off".

THE TWO FILES NEVER DISAGREE. A number that pipeline.json and rules.json both carry is checked when the file loads (check):
raw.strict.share = line 2.1 · raw.strict.trades = line 2.4 · proof.reshuffle = line 2.8 · the random bar = line 2.3 in each
of its rounds, to the decimals the law prints · box.best_days_share = lines 3.8 and 4.6. A difference raises R.RuleError
and nothing answers. pipeline.json is the pipeline's own file, not a template of the law (rules.NAMES does not list it).
Standard library only. Locked by tests/test_pipe_rules.py.
"""
from __future__ import annotations

import copy
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from . import rules as R

PROFILES = {"live": ("LIVE PIPELINE", "pipeline.json"), "wr": ("WR PIPELINE", "pipeline_wr.json")}     # the pipelines to choose from (owner, 2026-10-13)
STATE = Path(os.environ.get("HB_PIPELINE_STATE") or Path.home() / ".homebase" / "pipeline_profile")     # the chosen one; no file = live
FILE = R.T / "pipeline.json"                       # the LIVE file; set to ANOTHER path (the tests point it at a copy) it is read instead of the profile's
MODES = ("map", "variant")
GATES = ("law", "prop")
WINLANE = ("off", "label", "ask")
DECIMALS = 3                                        # the law prints the ladder of 2.3 to three decimals (98.3 % for 98.33 %)


def _bar(alpha: float, tries) -> float:
    return 1 - alpha / max(1, int(tries))


def check(p: dict) -> list:
    """What pipeline.json (as `p`) and rules.json disagree on (an empty list = they say one thing)."""
    best = {R.need(k)["best_share"] for k in ("3.8", "4.6")}
    same = (("raw.strict.share", p["raw"]["strict"]["share"], "2.1", R.need("2.1")),
            ("raw.strict.trades", p["raw"]["strict"]["trades"], "2.4", R.need("2.4")),
            ("proof.reshuffle", p["proof"]["reshuffle"], "2.8", R.need("2.8")),
            ("box.best_days_share", {p["box"]["best_days_share"]}, "3.8 and 4.6", best))
    bad = [f"{key} = {mine!r} (pipeline.json) and rules.json {line} = {law!r}" for key, mine, line, law in same if mine != law]
    alpha = p["proof"]["random_alpha"]
    off = [k for k, v in R.need("2.3").items() if round(_bar(alpha, k) - v, DECIMALS) != 0]
    if off:
        bad.append(f"proof.random_alpha = {alpha!r} (pipeline.json: the random bar 1 - alpha / tries) and rules.json 2.3 in round {', '.join(off)}")
    return bad


def active() -> str:
    """The profile in use: HB_PIPELINE (the environment), else the word in the state file (`bp.py pipe profile wr`), else "live". An unknown word: R.RuleError."""
    try:
        word = (os.environ.get("HB_PIPELINE") or (STATE.read_text(encoding="utf-8").strip() if STATE.exists() else "") or "live").lower()
    except OSError:
        word = "live"
    if word not in PROFILES:
        raise R.RuleError(f"pipeline profile {word!r}: one of {', '.join(PROFILES)}")
    return word


def label(profile: str | None = None) -> str:
    """The profile's name for a person: LIVE PIPELINE or WR PIPELINE."""
    return PROFILES[profile or active()][0]


def use(profile: str) -> str:
    """Choose the profile every later read of the rules uses (the state file; a running process takes it at its next start or `_all.cache_clear()`)."""
    profile = str(profile).lower()
    if profile not in PROFILES:
        raise R.RuleError(f"pipeline profile {profile!r}: one of {', '.join(PROFILES)}")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(profile + "\n", encoding="utf-8")
    _all.cache_clear()
    return profile


def _file() -> Path:
    return Path(FILE) if Path(FILE) != R.T / PROFILES["live"][1] else R.T / PROFILES[active()][1]


@lru_cache(maxsize=None)
def _load(path: str) -> dict:
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    bad = check(p)
    if bad:
        raise R.RuleError("the pipeline's numbers and the blueprint's do not agree: " + "; ".join(bad))
    if p.get("mode", MODES[0]) not in MODES:
        raise R.RuleError(f"pipeline.json mode = {p['mode']!r}: the pipeline runs in one of {', '.join(MODES)}")
    g = (p.get("gates") or {}).get("mode", GATES[0])
    if g not in GATES:
        raise R.RuleError(f"pipeline.json gates.mode = {g!r}: the gates are one of {', '.join(GATES)}")
    w = (p.get("winlane") or {}).get("mode", WINLANE[0])
    if w not in WINLANE:
        raise R.RuleError(f"pipeline.json winlane.mode = {w!r}: the win-rate lane is one of {', '.join(WINLANE)}")
    c = (p.get("winlane") or {}).get("cards", [])
    if not isinstance(c, list) or not all(isinstance(x, str) and x for x in c):
        raise R.RuleError(f"pipeline.json winlane.cards = {c!r}: a list of card names (empty = every card)")
    if g == "prop":                                 # the numbers the prop gates ask, over the file's variant block (a copy: the file stays as written)
        p["variant"] = {**p["variant"], **(p["gates"].get("variant") or {})}
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _all() -> dict:
    return _load(str(_file()))


_all.cache_clear = _load.cache_clear               # (the tests clear the cache after pointing FILE elsewhere)


def need(*keys):
    """The number (or the level) of pipeline.json under `keys`; no key = the whole file without its notes."""
    d = _all()
    for i, k in enumerate(keys):
        if not isinstance(d, dict) or k not in d:
            raise R.RuleError(f"pipeline.json has no {'.'.join(str(x) for x in keys[:i + 1])}"
                              + (f" (it has {', '.join(d)})" if isinstance(d, dict) else " (a number has nothing under it)"))
        d = d[k]
    return copy.deepcopy(d)


def mode() -> str:
    """"variant" (judge ONE picked box after a loose check of the map) or "map" (judge the whole map); a file without a mode is "map"."""
    return _all().get("mode", MODES[0])


def gates() -> str:
    """"prop" (only the three gates of the owner's 2026-10-10 word ask; the rest are labels) or "law" (every line asks); a file without `gates` is "law"."""
    return (_all().get("gates") or {}).get("mode", GATES[0])


def prop_gates() -> bool:
    """Is the pipeline asking only the three gates of mode "prop" (module docstring)?"""
    return gates() == "prop"


def winlane(unit: str | None = None) -> str:
    """"off" (no win-rate rows), "label" (they are printed and ask nothing) or "ask" (a box must hold them) FOR THIS UNIT; a file without `winlane`
    is "off". `winlane.cards` limits the lane to those cards' heat maps (module docstring); no `cards` = every unit, whatever `unit` is."""
    lane = _all().get("winlane") or {}
    mode, cards = lane.get("mode", WINLANE[0]), lane.get("cards") or []
    if not cards:
        return mode
    on = unit is not None and any(re.match(re.escape(c) + r"_[a-z]\d+(?:-|$)", str(unit)) for c in cards)
    return mode if on else WINLANE[0]


def random_bar(tries: int) -> float:
    """The random bar of an idea's `tries`-th try (a share, held strictly as line 2.3 is): 1 - alpha / max(1, tries)."""
    return _bar(_all()["proof"]["random_alpha"], tries)


def floor(root: str, part: float) -> float:
    """`part` of the market's cost floor (line 2.2), in dollars a trade. A market without a floor: R.RuleError."""
    _all()
    return R.need("2.2", root) * part
