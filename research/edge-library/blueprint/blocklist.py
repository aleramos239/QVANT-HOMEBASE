"""blocklist.py -- `bp.py blocks`: ONE PLAIN LIST OF EVERYTHING A CHAT CAN REUSE WITHOUT WRITING CODE. An idea is a card and
settings built from tested blocks (bp.py card); this is the list of the blocks, read where the toolkit itself reads them --
nothing is typed here that a registry or a template already says:
    entry triggers   the engine's bar-based families (families/blocks.py WRAPPED, the registry's library entry): what each
                     does, its own settings with their values (the class's schema), the values the library tried, its
                     markets, bar sizes and the sessions it trades in; whether it runs on the build days yet
    filters          the filter blocks and their two sides, in the blocks module's own plain words
    limits           settings.limits (run_idea.LIMIT_KEYS)        exits     the standard table (exit_menu.json)
    sessions, bar sizes, markets with their cost floors (costs.json, rules.json 2.2)
    the random tables (control.json), the Monte Carlo (montecarlo.json), the size steps (sizes.json), the ranges, the
    accounts the prop simulator has a rule file for (the app's)
and WHAT VERSION 1 OF THE TOOLKIT REFUSES (REFUSED: each entry is held against the toolkit's own refusal by
tests/test_blueprint_blocklist.py). Each entry has one line of plain words (a family a second one for its settings);
`blocks` in the result is the same as JSON, with every sentence whole.
Reads code and templates only: no store, no tape, no run.
"""
from __future__ import annotations

import re

import judge as J
import l2sim as S
import run_idea as RI
import run_menus as RM

from . import api
from . import propodds as PO
from . import records as REC
from . import rules as R
from . import runner as RUN

HIDDEN = ("auth",)                                  # a family input that switches on its author's OWN exits: no block (the exits are the standard table's)
LIMITS = {"max_tr": "the most entries a session: a whole number from 1", "dir": "long | short: one side only (a one-sided card sets it by itself)",
          "exit_bars": "leave after N bars", "trail_atr": "a trailing stop of N x ATR"}
REFUSED = (                                         # (what, why) -- what version 1 refuses, in the toolkit's own reasons
    ('a home "all"', "version 1 judges ONE home table: name the market, session and bar size the reason fits best, and list the others as neighbors (line 2.5 reads them)"),
    ("limits.trail_atr / limits.exit_bars", "exits of their own: the exits come from the standard table only (the random tables hold its 48 cells and no other)"),
    ('exits "extended"', "the standard exit table only (line 0.2)"),
    ("a Level 2 filter on ES or GC", "Level 2 exists for NQ only: every place of a card with a Level 2 filter (home, neighbors, the place it should not work) must be NQ"),
    ("locking or testing an idea with a Level 2 filter", "the vendor's Level 2 history ends 2026-07-08 and the test days' feature table is not built: such an idea can be built "
                                                          "(phase 2) but not locked or tested; the owner decides how the test range of one ends"),
    ("more than one varied setting", "an idea varies ONE setting, its main setting with 3-4 values (line 0.5); the others are held at one value under `fixed` -- and "
                                     "values that are opposite ideas (ib break / fade, gap fill / go, a side) are each an idea of their own"),
    ("an entry trigger that is not bar-based", "the registry's time-fired and Level 2 families are no blocks: a clock-time idea comes later (toolkit plan, section 7)"),
    ("the first look (the entry alone with a plain time exit)", "it needs a no-stop exit cell: not in version 1 (line 2.3 decides anyway)"),
    ("a tester run as the code check's source (--run-id)", "tester runs are not read yet: give a store or a trades file"),
)


def _values(kind: tuple) -> str:
    """A setting's values in words, from the class's schema entry: ('choice', (...)) | ('int', lo, hi) | ('float', lo, hi) | ('bool',)."""
    return (" | ".join(str(v) for v in kind[1]) if kind[0] == "choice" else f"a whole number {kind[1]:g} .. {kind[2]:g}" if kind[0] == "int" else
            f"a number {kind[1]:g} .. {kind[2]:g}" if kind[0] == "float" else "true | false" if kind[0] == "bool" else str(kind))


def _does(name: str) -> str:
    """What an entry trigger does, in the registry's own words: the first sentence of its notes without the registry's label
    -- and the next sentence when that one says what a setting's values do (`break = ...; fade = ...`)."""
    parts = RUN._blocks().BASES[name][3].split(". ")
    said = parts[0].rstrip(".") + (f". {parts[1].rstrip('.')}" if len(parts) > 1 and re.match(r"\w+ = ", parts[1]) else "")
    head, sep, rest = said.partition(": ")
    return rest if sep and len(head) <= 30 else said


def families() -> list:
    """Every bar-based family an idea's settings may name: {name, does, why (the library's reason), settings [{name,
    default, values}], tried (the values the library ran), markets, bars, sessions (the ones it trades in), bracket (it
    rests entry orders on both sides: worse fills add the late cancel), mirror (a setting whose values are opposite ideas:
    held at ONE value under `fixed`), runs, why_not}."""
    fam, blocks = RM.registry(), RUN._blocks()
    skip = RI._reserved(blocks) | set(S.Template.DEFAULTS) | set(HIDDEN)
    out = []
    for name in sorted(blocks.WRAPPED):
        cls, lib = blocks.WRAPPED[name], fam.library(name)
        sc, d = cls.schema(), cls.defaults()
        out.append({"name": name, "does": _does(name), "why": lib["rationale"],
                    "settings": [{"name": k, "default": d[k], "values": _values(sc[k])} for k in sorted(d) if k not in skip and k in sc],
                    "tried": lib["variants"], "markets": list(lib["roots"]), "bars": list(cls.SCREEN_TFS),
                    "sessions": [s for s in RM.DAY_PASSES if cls({**lib["variants"][0], "tf": cls.SCREEN_TFS[0], "sess": s}).sessions()],
                    "bracket": bool(blocks.BASES[name][2]), "mirror": lib.get("mirror"), "runs": True, "why_not": None})
    return out


def blocks() -> dict:
    """`bp.py blocks`: the list (module docstring) -> the result: `blocks` = {families, other_families, filters, limits,
    exits, sessions, bars, markets, random_tables, montecarlo, sizes, ranges, accounts, refused}, `counts`, and `text` = the
    same as a plain list, one line an entry."""
    fam, eng = RM.registry(), RUN._blocks()
    m, c, mc, ctl, sz, rg = (R.template(n) for n in ("exit_menu", "costs", "montecarlo", "control", "sizes", "ranges"))
    F = families()
    filters = [{"block": b, "side": s, "words": eng.PLAIN[(b, s)], "runs": True, "why_not": None,
                "markets": ["NQ"] if b in eng.L2_BLOCKS else list(eng.BLOCK_MARKETS.get(b, ("NQ", "ES", "GC"))), "tested": b not in eng.L2_BLOCKS}
               for b, sides in eng.FILTERS.items() for s in sides]
    B = {"families": F, "other_families": sorted(set(fam.REGISTRY) - set(eng.WRAPPED)), "filters": filters,
         "limits": [{"name": k, "words": LIMITS[k], "runs": k not in REC.OWN_EXITS} for k in RI.LIMIT_KEYS],
         "exits": {"cells": m["cells"], "stops": m["stops"], "targets_r": sorted(m["targets_r"] + m["small_targets_r"]), "flat_et": m["flat_et"], "flat_et_half_day": m["flat_et_half_day"],
                   "by_market": {root: [S.cell_id(x) for x in R.exit_menu(root)] for root in m["stops"]["pts"]}},
         "sessions": [{"name": s, "words": J.SESS_PLAIN[s], "runs": True} for s in RM.DAY_PASSES], "bars": list(fam.TFS),
         "markets": [{"market": k, "floor": R.need("2.2", k), "point_value": v["point_value"], "tick": v["tick"]} for k, v in c["contract"].items()],
         "random_tables": {"seeds": ctl["seeds"], "draws": ctl["draws"]},
         "montecarlo": {"runs": mc["runs"], "seed": mc["seed"], "draw": "whole days, with replacement, the same days for every variant", "build": mc["build"], "test": mc["test"],
                        "eval_card": {"percentiles": mc["eval_card"]["percentiles"], "after_trades": R.need("6.4")["after_trades"]}},
         "sizes": {"unit": sz["unit"], "steps": sz["steps"], "stage_a": sz["stage_a"]},
         "ranges": {"build": {k: rg["build"][k] for k in ("start", "end")}, "test": {k: rg["test"][k] for k in ("start", "end")}},
         "accounts": [{k: a[k] for k in ("id", "name", "confirmed")} for a in PO.app().list_rules()],
         "refused": [{"what": what, "why": why} for what, why in REFUSED]}
    nums = lambda v: ", ".join(f"{x:g}" for x in v)  # noqa: E731
    wide = max(len(f["name"]) for f in F)

    def family(f: dict) -> list:
        """A family as two short lines: what it does (the registry's sentence, its side remarks cut where it runs long); its settings."""
        does = ""
        for part in f["does"].split("; "):
            if does and len(does) + len(part) > 230:
                break
            does = f"{does}; {part}" if does else part
        sets = "; ".join(f"{x['name']} = {x['values']} (default {x['default']}" + (", ONE value: its values are opposite ideas" if x["name"] == f["mirror"] else "") + ")"
                         for x in f["settings"]) or "none of its own"
        ran = ", ".join(f"{k} " + " / ".join(dict.fromkeys(str(v[k]) for v in f["tried"])) for k in f["tried"][0] if k != f["mirror"])
        return [f"  {f['name']:<{wide}s}  " + ("" if f["runs"] else "NOT YET -- ") + does,
                f"  {'':<{wide}s}  settings: {sets}" + (f"; the library ran {ran}" if ran else "")
                + (" · one side an idea: the card says long or short" if f["mirror"] == "dir" else "")
                + f" · {' '.join(f['markets'])} · bars {', '.join(f['bars'])} · sessions {' '.join(f['sessions'])}"
                + (" · rests orders on both sides" if f["bracket"] else "") + ("" if f["runs"] else f" · cannot run yet: {f['why_not']}")]

    text = ["THE BLOCKS: what an idea can be built from without writing code (BLUEPRINT.md section 2). An idea = a card + settings (bp.py card); every number below is "
            "the toolkit's own.",
            f"ENTRY TRIGGERS (settings.family; ONE an idea): {sum(f['runs'] for f in F)} run on the build days, {sum(not f['runs'] for f in F)} cannot yet",
            *[ln for f in F for ln in family(f)],
            "FILTERS (settings.filters: {block, side}; a filter is kept only if it wins alone, line 2.7; a card may name two, line 0.2: each runs alone and both together, and the pair is kept only if each wins alone AND the pair beats each one)",
            *[f"  {f['block'] + ' ' + f['side']:<18s}  " + ("" if f["runs"] else f"NOT IN VERSION 1 ({f['why_not']}) -- ") + f["words"]
              + ("" if f["tested"] else " [NQ only; can be built, not yet locked or tested]") for f in filters],
            "LIMITS (settings.limits)",
            *[f"  {x['name']:<18s}  " + ("" if x["runs"] else "NOT IN VERSION 1 (an exit of its own) -- ") + x["words"] for x in B["limits"]],
            f"EXITS: the standard table, the same for every idea -- {m['cells'] // len(B['exits']['targets_r'])} stops x {len(B['exits']['targets_r'])} targets = {m['cells']} cells; "
            "nobody adds or changes a cell",
            f"  stops    {nums(m['stops']['atr'])} x ATR(14) of the idea's bars · fixed points: " + " · ".join(f"{k} {nums(v)}" for k, v in m["stops"]["pts"].items())
            + f" · {nums(m['stops']['pct'])} percent of the entry price",
            f"  targets  {nums(B['exits']['targets_r'][1:])} x the stop distance, or none (the trade runs to its stop or to the flat time)",
            f"  flat     every trade is flat by {m['flat_et']} ET ({m['flat_et_half_day']} on half days)",
            "SESSIONS (card.home.session; New York time)",
            *[f"  {s['name']:<7s}  " + ("" if s["runs"] else "NOT IN VERSION 1 -- ") + s["words"] for s in B["sessions"]],
            f"BAR SIZES (card.home.bar): {', '.join(B['bars'])} minutes (a family may run on fewer: its line says)",
            "MARKETS (card.home.market)",
            *[f"  {x['market']:<3s}  the average trade must reach ${x['floor']:g} after costs at 1 contract (lines 2.2, 4.3) · ${x['point_value']:g} a point, tick {x['tick']:g}"
              for x in B["markets"]],
            f"RANDOM TABLES (lines 2.3, 4.4): {ctl['draws']:,} draws from {ctl['seeds']} seeds of random entries with the same exits, session and days",
            f"MONTE CARLO (lines 2.8, 3.7, 4.7): {mc['runs']:,} reshuffled runs of whole days drawn with replacement, the same days for every variant, fixed seed {mc['seed']}; "
            f"2.8 asks {100 * mc['build']['need']:g} % of the runs, 3.7 (the default variant alone) and 4.7 ask {100 * mc['test']['need']:g} %; the eval card reads the "
            f"{', '.join(str(p) + 'th' for p in mc['eval_card']['percentiles'])} percentile after {nums(R.need('6.4')['after_trades'])} trades",
            f"SIZE STEPS (phase 5, in micros): {nums(sz['steps'])}; stage A of an eval is {sz['stage_a']} micro",
            f"RANGES: build {rg['build']['start']} .. {rg['build']['end']} (all tuning) · the out-of-sample test {rg['test']['start']} on, read ONCE",
            "ACCOUNTS (bp.py sim --account=ID; the rule files of the app's prop simulator)",
            *[f"  {a['id']:<34s}  {a['name']}{'' if a['confirmed'] else ' · unconfirmed rules'}" for a in B["accounts"]],
            "WHAT VERSION 1 REFUSES",
            *[f"  {x['what']}: {x['why']}" for x in B["refused"]]]
    return api.result("blocks", None, blocks=B, text="\n".join(text),
                      counts={"families": sum(f["runs"] for f in F), "families_not_yet": sum(not f["runs"] for f in F), "filters": sum(f["runs"] for f in filters),
                              "filters_not_yet": sum(not f["runs"] for f in filters), "refused": len(REFUSED)},
                      next="Write the idea card from these blocks -- why it should make money and who loses, its home, its neighbors, its main setting with 3-4 values: "
                           "bp.py card <name> --spec=-")
