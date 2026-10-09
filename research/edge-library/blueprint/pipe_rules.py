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

THE TWO FILES NEVER DISAGREE. A number that pipeline.json and rules.json both carry is checked when the file loads (check):
raw.strict.share = line 2.1 · raw.strict.trades = line 2.4 · proof.reshuffle = line 2.8 · the random bar = line 2.3 in each
of its rounds, to the decimals the law prints · box.best_days_share = lines 3.8 and 4.6. A difference raises R.RuleError
and nothing answers. pipeline.json is the pipeline's own file, not a template of the law (rules.NAMES does not list it).
Standard library only. Locked by tests/test_pipe_rules.py.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

from . import rules as R

FILE = R.T / "pipeline.json"
MODES = ("map", "variant")
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


@lru_cache(maxsize=None)
def _all() -> dict:
    p = json.loads(FILE.read_text(encoding="utf-8"))
    bad = check(p)
    if bad:
        raise R.RuleError("the pipeline's numbers and the blueprint's do not agree: " + "; ".join(bad))
    if p.get("mode", MODES[0]) not in MODES:
        raise R.RuleError(f"pipeline.json mode = {p['mode']!r}: the pipeline runs in one of {', '.join(MODES)}")
    return {k: v for k, v in p.items() if not k.startswith("_")}


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


def random_bar(tries: int) -> float:
    """The random bar of an idea's `tries`-th try (a share, held strictly as line 2.3 is): 1 - alpha / max(1, tries)."""
    return _bar(_all()["proof"]["random_alpha"], tries)


def floor(root: str, part: float) -> float:
    """`part` of the market's cost floor (line 2.2), in dollars a trade. A market without a floor: R.RuleError."""
    _all()
    return R.need("2.2", root) * part
