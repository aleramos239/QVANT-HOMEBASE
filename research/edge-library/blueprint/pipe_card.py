"""pipe_card.py -- THE PIPELINE CARD (pipeline plan A, task 2; the design's section 2, stage 0). A pipeline card names ONE idea
and everything the pipeline will try for it: up to 3 ways to enter, each a family with ONE main setting of 3 values, and up
to 5 indicators, each with its reason. This module reads the card and turns it into ordinary toolkit ideas; it runs nothing.

    {"name", "why", "loser", "source": owner | video | claude | wiki | paper | book | course, "market", "session",
     "sides": both | long | short, "sides_why", "ways": [{"family", "main_setting", "values": [3], "fixed": {}, "limits": {}}],
     "indicators": [{"block", "side", "why"}], "ref": optional, which paper / book / video / course it came from (300 characters at most)}

  check(card)       -> (rows, subs). rows = the four lines of stage 0, each a row of lines._row (line, passed, number, need, text):
                        P0.1  why it should make money and who loses: one sentence each, 8 words or more together
                        P0.2  the ways: their count; each a family of the block list, a main setting that is a setting of
                              that family, 3 values each once; the card's session is one of the pipeline's (the evening
                              session is not in this version); the family runs on the card's market, in its session and on
                              at least one of the pipeline's bar sizes; no way twice -- and each heat map is a card the
                              TOOLKIT takes (records.card_lines: what it refuses fails this line, in its own words)
                        P0.3  the indicators: their count; each a filter block and one of its sides, with a why; no block
                              twice; a block only on a market it runs on (Level 2: NQ only)
                        P0.4  the sides: both, or one side and why
                       subs = None while a line fails, else the card's HEAT MAPS, one a way and a bar size the family runs on:
                        {"name": "<card>_<a|b|c><bar>", "way": its index, "bar": "1" | "5", "spec": the toolkit spec}
                       A family without one of the two bar sizes gets the other only.
  signature(card)   -> the sha1 of what makes two cards THE SAME IDEA: market, session, sides and the ways (family, main
                       setting, values, fixed, limits) -- in any order, a number typed as text or not. Not the name, the
                       reason, the source or the indicators. Of a card that check() passed.
  family_of(card)   -> the first way's family.
  neighbors(market, family, bar, block=None)
                    -> where else a heat map should work, as its toolkit card says it (below); `block` = the indicator
                       of a stage 3 heat map: only the markets that indicator runs on as well (Level 2: NQ alone)

A HEAT MAP'S SPEC is a standard idea card of the toolkit (records.py, THE SPEC): why and loser are the card's; home = the
card's market and session and the heat map's bar; neighbors = the pipeline's other markets that the family runs on, as
records.place reads a market ("ES") -- and when none is left the other bar size ("5-minute bars"), since the toolkit asks
for one neighbor at least (neighbors(): the ONE place that says it, for stage 3's heat maps too); no filter (an indicator
is tried at stage 3, never part of a heat map); exits from the standard table; sides_why "both sides: the rule is symmetric"
unless the card says; loses_when "not named on a pipeline card" (the pipeline dropped that line). A value written as text
("0.25") is typed as the family's schema types it.

REFUSED OUTRIGHT (judge.Refuse): what is no card -- no JSON object, a field a card does not have, a source that is not one
of the four, a name that is not ^[a-z][a-z0-9_]{1,33}$ or whose heat maps the toolkit would not take as idea names
(records._name: '__', the c1 prefix, the app's reserved words). A card with a line missing is NOT refused: its row fails.
THE LIMITS (ways 1-3, 3 values, indicators 0-5, bars 1 and 5, the markets, the sessions) are pipe_rules.need("card"); none is typed here.
check() WRITES NOTHING and reads no tape: code and templates only (records.card_lines is pure; the idea folder is not
touched). The card it is handed is not changed. Locked by tests/test_pipe_card.py.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import string
from functools import lru_cache

import judge as J
import run_menus as RM

from . import blocklist as BL
from . import lines as L
from . import pipe_rules as P
from . import records as REC
from . import rules as R
from . import runner as RUN

KEYS = ("name", "why", "loser", "source", "market", "session", "sides", "sides_why", "ways", "indicators")
WAY_KEYS = ("family", "main_setting", "values", "fixed", "limits")
IND_KEYS = ("block", "side", "why")
SOURCES = ("owner", "video", "claude", "wiki", "paper", "book", "course")
OPTIONAL = ("ref",)                 # ref: which paper / book / video / course (the owner, 2026-10-08); no part of the signature
REF_MAX = 300
NAME = re.compile(r"^[a-z][a-z0-9_]{1,33}$")        # 34 characters: + "_a1" + a later round's "_r5" = the app's 40 (draftstore.NAME_RE)
LETTERS = string.ascii_lowercase                    # a way's letter in its heat maps' names
WORDS = 8                                           # the engine's own floor for a reason (run_idea.check_spec), held here on why + loser
SIDES_WHY = "both sides: the rule is symmetric"
LOSES_WHEN = "not named on a pipeline card"
L2_MARKETS = ("NQ",)                                # Level 2 exists for NQ only (runner.checked)
NUM = re.compile(r"-?\d+(?:\.\d+)?")
SENTENCE = re.compile(r"(?<=[.!?])\s+")             # as line 0.1 counts sentences (records.card_lines)


def _txt(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def _scalar(x) -> bool:
    return isinstance(x, (str, int, float))


@lru_cache(maxsize=None)
def _families() -> dict:
    """The entry triggers as the block list reads them (blocklist.families: settings, markets, bars, sessions, runs), by
    name, each with its class's `schema`. Code only: read once a process."""
    W = RUN._blocks().WRAPPED
    return {f["name"]: {**f, "schema": W[f["name"]].schema()} for f in BL.families()}


def sub_name(name: str, way: int, bar: str) -> str:
    """The name of a card's heat map: fvg_open, way 0, bar "5" -> fvg_open_a5."""
    return f"{name}_{LETTERS[way]}{bar}"


def _whole(card) -> dict:
    """The card, or judge.Refuse for what is no card (module docstring)."""
    if not isinstance(card, dict):
        raise J.Refuse(f"a pipeline card: a JSON object {{{', '.join(KEYS)}}}")
    extra = sorted(str(k) for k in set(card) - set(KEYS) - set(OPTIONAL))
    if extra:
        raise J.Refuse(f"unknown fields {extra}: a pipeline card is {{{', '.join(KEYS)}}}")
    name, lim = card.get("name"), P.need("card")
    if not (isinstance(name, str) and NAME.fullmatch(name)):
        raise J.Refuse(f"name {name!r}: 2-34 characters of a-z, 0-9 and '_', starting with a letter (e.g. fvg_open)")
    for sub in (sub_name(name, i, b) for i in range(lim["ways"][1]) for b in lim["bars"]):
        try:
            REC._name(sub)
        except J.Refuse as e:
            raise J.Refuse(f"name {name!r}: its heat maps are named like {sub}, which the toolkit does not take -- {e}") from None
    if card.get("source") not in SOURCES:
        raise J.Refuse(f"source {card.get('source')!r}: one of {', '.join(SOURCES)}")
    ref = card.get("ref")
    if ref is not None and not (isinstance(ref, str) and ref.strip() and len(ref) <= REF_MAX):
        raise J.Refuse(f"ref: one line that names the paper, book, video or course ({REF_MAX} characters at most), or leave it out")
    return card


def _why(card: dict) -> dict:
    """Line P0.1."""
    why, loser, need = REC._text(card.get("why")), REC._text(card.get("loser")), {**R.need("0.1"), "words": WORDS}
    count = lambda t: len([s for s in SENTENCE.split(t) if s.strip()])  # noqa: E731
    n = len(f"{why} {loser}".split())
    bad = ("it does not say why it should make money (why, one sentence)" if not why else
           "it does not say who is on the losing side (loser, one sentence)" if not loser else
           f"the reason is {count(why)} sentences (need {need['sentences']}): say it in one" if count(why) != need["sentences"] else
           f"who loses is {count(loser)} sentences (need {need['sentences']}): say it in one" if count(loser) != need["sentences"] else
           f"the reason and who loses are {n} words together (need {need['words']} or more)" if n < need["words"] else "")
    return L._row("P0.1", not bad, n, need, bad or f"the reason in one sentence, and who loses: {why} Losing side: {loser}")


def _typed(kind, x):
    """A value written as text ("0.25", "9", "true") as the family's schema types it: ('float', lo, hi) | ('int', lo, hi) |
    ('bool',) | ('choice', (...)). Anything else stays as it is: the toolkit refuses what does not fit."""
    if not (isinstance(x, str) and kind):
        return x
    t = x.strip()
    return (int(t) if kind[0] == "int" and re.fullmatch(r"-?\d+", t) else float(t) if kind[0] == "float" and NUM.fullmatch(t) else
            {"true": True, "false": False}.get(t.lower(), x) if kind[0] == "bool" else
            next((o for o in kind[1] if str(o) == t), x) if kind[0] == "choice" else x)


def _way(w, mk, ss, lim: dict) -> tuple:
    """One way of the card -> (what is wrong with it, the way as the family types it, its family, its bars)."""
    if not (isinstance(w, dict) and set(w) <= set(WAY_KEYS)):
        extra = sorted(str(k) for k in set(w) - set(WAY_KEYS)) if isinstance(w, dict) else []
        return (f"unknown fields {extra}: " if extra else "") + f"an object {{{', '.join(WAY_KEYS)}}}", None, None, None
    fam, ms, v, fixed, limits = w.get("family"), w.get("main_setting"), w.get("values"), w.get("fixed", {}), w.get("limits", {})
    F = _families().get(fam) if isinstance(fam, str) else None
    if F is None:
        return f"family {fam!r} is no entry trigger: one of {', '.join(sorted(_families()))}", None, None, None
    own, n, bars = [s["name"] for s in F["settings"]], len(v) if isinstance(v, list) else 0, [b for b in lim["bars"] if b in F["bars"]]
    kind = F["schema"].get(ms) if isinstance(ms, str) else None
    v = [_typed(kind, x) for x in v] if isinstance(v, list) else []
    why = (f"{fam} cannot run on the build days yet: {F['why_not']}" if not F["runs"] else
           f"main setting {ms!r} is no setting of {fam} (" + (f"its settings: {', '.join(own)}" if own else "it has none of its own") + ")" if ms not in own else
           f"the values of {ms} are text or a number" if not all(_scalar(x) for x in v) else
           f"{ms} has {n} values (need {lim['values']}, each once)" if n != lim["values"] or len({str(x) for x in v}) != n else
           "fixed and limits are objects {setting: value}, each value text or a number"
           if not all(isinstance(d, dict) and all(_scalar(x) for x in d.values()) for d in (fixed, limits)) else
           f"{fam} does not run on {mk} (its markets: {', '.join(F['markets'])})" if mk not in F["markets"] else
           f"{fam} does not trade in {J.SESS_PLAIN[ss]} (its sessions: {', '.join(F['sessions'])})" if ss not in F["sessions"] else
           f"{fam} does not run on {'- or '.join(lim['bars'])}-minute bars (its bars: {', '.join(F['bars'])})" if not bars else "")
    if why:
        return why, None, None, None
    return "", {"family": fam, "main_setting": ms, "values": v, "fixed": {k: _typed(F["schema"].get(k), x) for k, x in fixed.items()}, "limits": dict(limits)}, F, bars


def _ways(card: dict, lim: dict) -> tuple:
    """Line P0.2 as the card alone says it -> (the row, [(way index, the way as typed, its family, its bars)])."""
    W, mk, ss, (lo, hi) = card.get("ways"), card.get("market"), card.get("session"), lim["ways"]
    n, out, keys = len(W) if isinstance(W, list) else 0, [], []
    own = [s for s in lim["sessions"] if s in RM.DAY_PASSES]
    bad = (f"market {mk!r}: one of {', '.join(lim['markets'])}" if mk not in lim["markets"] else
           f"session {ss!r}: the {J.SESS_PLAIN[ss].split(' (')[0]} session is not in this version of the pipeline (one of {', '.join(own)})"
           if ss in RM.DAY_PASSES and ss not in own else
           f"session {ss!r}: one of {', '.join(own)}" if ss not in own else
           f"{n} ways to enter (need {lo} to {hi}): ways is a list of {{{', '.join(WAY_KEYS)}}}" if not lo <= n <= hi else "")
    for i, w in enumerate(W if not bad else []):
        why, way, F, bars = _way(w, mk, ss, lim)
        if not why and _key(way) in keys:
            why = f"is the same as way {LETTERS[keys.index(_key(way))]}"
        if why:
            bad = f"way {LETTERS[i]}{' ' if why.startswith('is the same') else ': '}{why}"
            break
        out.append((i, way, F, bars))
        keys.append(_key(way))
    words = bad or (f"{n} way{'s' * (n > 1)} to enter on {mk}, {J.SESS_PLAIN[ss]}: " + " · ".join(
        f"{LETTERS[i]} {w['family']}, {w['main_setting']} {' / '.join(str(x) for x in w['values'])}, {'- and '.join(bars)}-minute bars" for i, w, _, bars in out))
    return L._row("P0.2", not bad, n, {k: lim[k] for k in ("ways", "values", "bars", "markets", "sessions")}, words), out


def _indicators(card: dict, lim: dict) -> dict:
    """Line P0.3."""
    I, mk, eng, (lo, hi), seen = card.get("indicators", []), card.get("market"), RUN._blocks(), lim["indicators"], []
    n = len(I) if isinstance(I, list) else 0
    bad = (f"indicators: a list of {{{', '.join(IND_KEYS)}}}" if not isinstance(I, list) else
           f"{n} indicators ({f'need {lo} to {hi}' if lo else f'at most {hi}'}), each tried alone" if not lo <= n <= hi else "")
    for i, x in enumerate(I if not bad else []):
        if not (isinstance(x, dict) and set(x) <= set(IND_KEYS) and isinstance(x.get("block"), str) and isinstance(x.get("side"), str)):
            extra = sorted(str(k) for k in set(x) - set(IND_KEYS)) if isinstance(x, dict) else []
            why = (f"unknown fields {extra}: " if extra else "") + f"an object {{{', '.join(IND_KEYS)}}}"
        else:
            b, s = x["block"], x["side"]
            ok = L2_MARKETS if b in eng.L2_BLOCKS else eng.BLOCK_MARKETS.get(b)
            why = (f"block {b!r} is no filter block (`bp.py blocks` lists them)" if b not in eng.FILTERS else
                   f"{b} has no side {s!r} ({' | '.join(eng.FILTERS[b])})" if s not in eng.FILTERS[b] else
                   f"{b} {s} does not say why it should help (why)" if not REC._text(x.get("why")) else
                   f"block {b} is named twice: a card tries one side of a block" if b in seen else
                   f"{b} {'reads Level 2, which exists for' if b in eng.L2_BLOCKS else 'runs on'} {' and '.join(ok)} only: the card's market is {mk}"
                   if ok and mk not in ok else "")
            seen.append(b)
        if why:
            bad = f"indicator {i + 1}: {why}"
            break
    return L._row("P0.3", not bad, n, lim["indicators"], bad or ("no indicator" if not n else
                  f"{n} indicator{'s' * (n > 1)}, each tried alone, in this order: {', '.join(x['block'] + ' ' + x['side'] for x in I)}"))


def _sides(card: dict) -> dict:
    """Line P0.4."""
    sides, sw = card.get("sides"), REC._text(card.get("sides_why"))
    bad = (f"sides {sides!r}: both, long or short" if sides not in REC.SIDES else
           f"it trades {sides} only and does not say why (sides_why)" if sides != "both" and not sw else "")
    return L._row("P0.4", not bad, None, None, bad or (f"{sides} only: {sw}" if sides != "both" else "both sides" + (f": {sw}" if sw else "")))


def neighbors(market: str, family: str, bar: str, block=None) -> list:
    """WHERE ELSE A HEAT MAP SHOULD WORK, in the words of its toolkit card: the pipeline's other markets that the family
    runs on ("ES", "GC") -- with an indicator `block` on (stage 3), those of them the block runs on as well (a Level 2 block:
    NQ alone; SMT: NQ and ES) -- and, when no market is left, the other bar size ("5-minute bars"): the toolkit asks for
    one neighbor at least. [] = the family has no other bar size either (the toolkit then refuses the card)."""
    F, lim, eng = _families()[family], P.need("card"), RUN._blocks()
    ok = None if block is None else L2_MARKETS if block in eng.L2_BLOCKS else eng.BLOCK_MARKETS.get(block)
    return ([m for m in lim["markets"] if m != market and m in F["markets"] and (not ok or m in ok)]
            or [f"{b}-minute bars" for b in lim["bars"] if b != bar and b in F["bars"]][:1])


def _spec(card: dict, name: str, way: dict, bar: str) -> dict:
    """The toolkit spec of one heat map (module docstring), as records._spec saves an idea's."""
    return REC._spec(name, {"name": name, "version": 1,
                            "card": {"why": card["why"], "loser": card["loser"], "home": {"market": card["market"], "session": card["session"], "bar": bar},
                                     "neighbors": neighbors(card["market"], way["family"], bar), "main_setting": way["main_setting"], "sides": card["sides"],
                                     "sides_why": REC._text(card.get("sides_why")) or SIDES_WHY, "loses_when": LOSES_WHEN},
                            "run": {"family": way["family"], "params": {way["main_setting"]: list(way["values"])}, "fixed": dict(way["fixed"]), "filters": [],
                                    "exits": R.need("0.2")["exits"], "limits": copy.deepcopy(way["limits"])}})


def check(card) -> tuple:
    """LINES P0.1-P0.4 read off a pipeline card -> (the four rows, its heat maps | None): module docstring. The toolkit's
    own card check is asked only when the card's own lines hold (a missing reason would fail there as well, under P0.2)."""
    card, lim = _whole(card), P.need("card")
    p2, ways = _ways(card, lim)
    rows = [_why(card), p2, _indicators(card, lim), _sides(card)]
    if not all(rows[i]["passed"] for i in (0, 1, 3)):
        return rows, None
    subs = [{"name": sub_name(card["name"], i, bar), "way": i, "bar": bar, "spec": _spec(card, sub_name(card["name"], i, bar), w, bar)}
            for i, w, _, bars in ways for bar in bars]
    for s in subs:
        got, plan = REC.card_lines(s["spec"])       # pure; it writes the engine's own spelling of a choice into the spec (5 -> "5")
        if plan is None:
            rows[1] = L._row("P0.2", False, p2["number"], p2["need"], f"way {LETTERS[s['way']]} on {s['bar']}-minute bars: the toolkit's card check does not take it -- "
                             + "; ".join(x["text"] for x in got if x["passed"] is False))
            return rows, None
    return rows, subs if rows[2]["passed"] else None


def _canon(x):
    """A value as the signature reads it: a number and the same number as text are ONE value (5, 5.0, "5", "5.0")."""
    if isinstance(x, bool) or not isinstance(x, (int, float, str)):
        return x
    t = x.strip() if isinstance(x, str) else x
    return float(t) if not isinstance(t, str) or NUM.fullmatch(t) else {"true": True, "false": False}.get(t.lower(), t)


def _key(way: dict) -> list:
    """What makes two ways the same way: family, main setting, its values, fixed and limits -- sorted, numbers as numbers."""
    items = lambda d: sorted(([str(k), _canon(v)] for k, v in (d or {}).items()), key=_txt)  # noqa: E731
    return [way.get("family"), way.get("main_setting"), sorted((_canon(v) for v in way.get("values") or []), key=_txt), items(way.get("fixed")), items(way.get("limits"))]


def signature(card: dict) -> str:
    """The sha1 (40 hex characters) of what makes two cards the same idea (module docstring)."""
    body = {"market": card["market"], "session": card["session"], "sides": card["sides"], "ways": sorted((_key(w) for w in card["ways"]), key=_txt)}
    return hashlib.sha1(_txt(body).encode("utf-8")).hexdigest()


def family_of(card: dict) -> str:
    """The card's family: its first way's."""
    return card["ways"][0]["family"]
