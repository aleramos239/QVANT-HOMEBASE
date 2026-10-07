"""rules.py -- the blueprint's templates as data (plan step 1). Every threshold of BLUEPRINT.md section 2 is READ from
templates/*.json; none is typed in code. A change of a number is a change of the law (the owner's word), made in the JSON.

  rules.json       every numbered line 0.1 .. 6.8: its quoted text, its numbers (`need`) and how a value is held against
                   them (`op`: "above" / "more than" = >, "or more" = >=, "at most" / "or less" = <=)   rule() need() meets()
  ranges.json      build 2021-09-22 .. 2025-06-30 · test 2025-07-01 .. latest in two parts · the stored (old) build days
  exit_menu.json   the standard exit table, 8 stops x 6 targets (the 32 old cells, then the small targets)  exit_menu(root)
  control.json     the random tables: 10 seeds, 4,000 draws      montecarlo.json   1,000 runs of whole days, a fixed seed
  costs.json       the cost floor per market, normal and worse fills      sizes.json · idea.json   size steps · the empty spec
  compute.json     the workers of a run inside and outside desk hours, the day blocks of a tape pass (not a line of the law)

Standard library only: the connector reads the same files. A number the law states once but two files carry (the cost floor,
the Monte Carlo lines, the worse fills, the flat time) and the ranges (build and test must not share a day) are checked when
the templates load: a difference raises RuleError and nothing runs. Locked by tests/test_blueprint_rules.py.
"""
from __future__ import annotations

import datetime as dt
import json
import operator
from functools import lru_cache
from pathlib import Path

T = Path(__file__).resolve().parent / "templates"
NAMES = ("rules", "ranges", "exit_menu", "control", "montecarlo", "costs", "idea", "sizes", "compute")
OPS = {">": operator.gt, ">=": operator.ge, "<=": operator.le}


class RuleError(ValueError):
    """The templates do not say one thing, or a line / market / round was asked for that the law does not have."""


@lru_cache(maxsize=None)
def _all() -> dict:
    t = {n: json.loads((T / f"{n}.json").read_text(encoding="utf-8")) for n in NAMES}
    bad = check(t)
    if bad:
        raise RuleError("the blueprint templates do not agree: " + "; ".join(bad))
    return t


def check(t: dict) -> list:
    """What the template files disagree on (an empty list = they say one thing). A number of the law that sits in two files
    must be the same in both, and the test days must start the day after the build days end, in two parts without a gap."""
    r, c, mc, m, rg, bad = t["rules"], t["costs"], t["montecarlo"], t["exit_menu"], t["ranges"], []
    if not r["2.2"]["need"] == r["4.3"]["need"] == c["floor"]:
        bad.append("the cost floor (rules.json 2.2, 4.3 and costs.json floor)")
    for part in ("build", "test"):
        if r[mc[part]["line"]]["need"] != mc[part]["need"]:
            bad.append(f"the Monte Carlo line {mc[part]['line']} (rules.json and montecarlo.json {part})")
    if any(c["worse"][k] != v for k, v in r["4.5"]["need"].items()):
        bad.append("the worse fills (rules.json 4.5 and costs.json worse)")
    if (r["1.2"]["need"]["flat_et"], r["1.2"]["need"]["flat_et_half_day"]) != (m["flat_et"], m["flat_et_half_day"]):
        bad.append("the flat time (rules.json 1.2 and exit_menu.json)")
    parts = rg["test"]["parts"]
    ends = [rg["build"]["end"]] + [p["end"] for p in parts[:-1]]             # each of these days is followed by ...
    starts = [rg["test"]["start"]] + [p["start"] for p in parts[1:]]         # ... the start of the next stretch
    if any((dt.date.fromisoformat(a) + dt.timedelta(1)).isoformat() != b for a, b in zip(ends, starts)) \
            or parts[0]["start"] != rg["test"]["start"] or parts[-1]["end"] != rg["test"]["end"]:
        bad.append("the ranges (ranges.json: the test starts the day after the build ends and its parts follow each other)")
    if not rg["build"]["start"] <= rg["stored_build"]["start"] <= rg["stored_build"]["end"] <= rg["build"]["end"]:
        bad.append("the stored build days (ranges.json: they lie inside the build days)")
    return bad


def template(name: str) -> dict:
    """One template file (read once, checked against the others). Keys that start with '_' are notes for the reader."""
    if name not in NAMES:
        raise RuleError(f"template {name!r}: one of {NAMES}")
    return _all()[name]


def lines() -> list:
    """Every line number of BLUEPRINT.md section 2, in order: '0.1' .. '6.8'."""
    return [k for k in template("rules") if not k.startswith("_")]


def rule(line: str) -> dict:
    """The entry of one blueprint line: `text` (+ `number`) quoted from BLUEPRINT.md, and its `need` / `op` when it has numbers."""
    r = None if line.startswith("_") else template("rules").get(line)
    if r is None:
        raise RuleError(f"BLUEPRINT.md section 2 has no line {line!r}")
    return r


def need(line: str, key=None):
    """The number of a line. `key` picks one of several: a market for 2.2 / 4.3 ('NQ'), a round for 2.3 (1 .. 5)."""
    n = rule(line)["need"]
    if key is None:
        return n
    if str(key) not in n:
        raise RuleError(f"line {line} has no number for {key!r} (it has {', '.join(n)})")
    return n[str(key)]


def meets(line: str, value, key=None) -> bool:
    """`value` held against the line's number with the line's OWN comparison (rules.json `op`), so that "above 95 %" stays
    strict and "200 or more" does not."""
    return bool(OPS[rule(line)["op"]](value, need(line, key)))


def exit_menu(root: str) -> list:
    """THE 48 exit cells of the standard table for a market, in table order: the 32 of the old library's menu (stops outer,
    targets inner: engine l2sim.menu(root)), then the same stops x the small targets:
    [{'stop_mode', 'stop_val', 'tgt_r'}] -- the same cells, in the same order, as engine families/blocks.menu_blueprint(root)."""
    m = template("exit_menu")
    if root not in m["stops"]["pts"]:
        raise RuleError(f"no standard exit table for market {root!r} (it has {', '.join(m['stops']['pts'])})")
    stops = [(k, v) for k in m["stop_order"] for v in (m["stops"][k][root] if isinstance(m["stops"][k], dict) else m["stops"][k])]
    return [{"stop_mode": k, "stop_val": v, "tgt_r": r} for part in ("targets_r", "small_targets_r") for k, v in stops for r in m[part]]
