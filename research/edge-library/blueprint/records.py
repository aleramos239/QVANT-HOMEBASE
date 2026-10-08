"""records.py -- THE IDEA'S RECORD (toolkit plan, steps 5 and 6): the idea card (phase 0), the build with its counted rounds
(phase 2) and the status. Everything is saved in the app's idea folder through homebase/ideastore.py (one folder per idea;
its status is READ OFF the saved results there, never set here), with the idea's record draft in the Lab.

    card(name, spec)       `bp.py card <name> --spec=-`          lines 0.1-0.7 off the card -> card.md, spec.json, the Lab draft
    build(name, reason)    `bp.py build <name> --reason=TEXT`    ONE ROUND: the reason first, the run, lines 2.1-2.9, the status
    status([name])         `bp.py status [<name>]`               one line an idea, or the full record of one

THE SPEC (plan section 3)   {"name", "version", "card": {why, loser, home {market, session, bar}, neighbors [...], not_here,
main_setting, sides, sides_why, loses_when}, "run": {family, params, fixed, filters, exits: "standard", limits}}.

FROM A CARD TO WHAT IS RUN (decided 2026-10-06 for the owner; each line is easy to change)
  THE HOME TABLE   = the card's market, session and bar size: the 48 exit cells of the standard table x the 3-4 values of
                   the main setting. Lines 2.1-2.4, 2.6 and 2.8 are read on it; 2.3 against the random-entry pool of its
                   market and bar size (10 seeds).
  ITS NEIGHBORS    (line 2.5) = the places the card names under "where else it should work", and no other. An entry names
                   a market, a session or a bar size in the card's own words ("ES", "midday", "5-minute bars", "GC pre 5");
                   what it leaves out is the home's. Each is a table of its own -- another session of the home's store, or
                   the store of another market or bar size -- and 2.5 asks half of them or more to have a profitable
                   average variant. A named place where no variant traded is a table that is not profitable.
  NOT HERE         the one place it should NOT work is run like a neighbor and SHOWN. No line reads it.
  THE SIDES        (line 2.6) are the card's: a one-sided card runs that side only (limits.dir) and is judged on it; a
                   two-sided card needs each side above $0, and a side without a trade made none. The random tables of
                   2.3 stay two-sided (the pool holds no one-sided table): for a one-sided idea the result says so.
  A FILTER         (line 2.7): a rule with a filter is read on its tables WITH the filter on (home and neighbors), and
                   held against the same home table without it. Filters come one a round, each with its reason.
  THE STORES       one engine spec (run_idea's format) per market and bar size the card names, each with the sessions it
                   names there: `<store>-<ROOT>-tf<tf>`, + `<store>__<block>_<side>-...` with a filter on.
What version 1 refuses, in words: a home that says "all" (it judges ONE home table: name it, list the others as neighbors);
the evening session (plan section 7); a rule with two filters at once (the table with both on is not run yet: each filter
first wins alone, one a round); an exit of its own (limits.trail_atr / exit_bars: the random tables hold the standard cells
and no other); more than one varied setting.

THE ROUNDS (line 2.9). Round n = the builds on file + 1; a round whose run fails leaves no result and is not used up.
start() refuses what needs no run -- no card, no reason, round 6, a frozen idea, a control pool with fewer seeds than the
law asks, a day outside the build range, whatever the runner refuses -- and then saves the REASON and the round's settings
BEFORE anything runs. run() runs what is missing (runner.run_build), reads 2.1-2.9 at the round's bar (rules.json 2.3) and
saves the result; the app's idea store then says idea, lead (every line passes) or shelved (not passed after round 5).
  THE STORE NAME of a round: a store is never written twice, so the round takes the first name -- the earlier rounds'
  names, latest first, then <idea> (round 1) or <idea>_r<n> -- under which no store on disk was written from other inputs.
  A round with the settings of an earlier one reads that round's stores; a filter adds its own stores only; a changed base
  setting (a value, a limit, a place of the card) gets stores of its own.
THE DEFAULT VARIANT, IN THE APP. After a round that counts, the middle of the variants that made money on build (never the
best; judge.TIE_RULE) is run once more for its prices (a store keeps no prices), held against its store trade for trade,
and written as a finished tester run by homebase/backtest/importrun.py; the run id is kept with the idea. The freeze (line
3.1) picks the default again among the variants that also make money with worse fills -- that table is the lock's.

A RUN ON NAMED DAYS (--days) is a smoke run: its lines are printed, nothing is saved, no round is used.
TEST ONLY: BP_TEST_RUN = a JSON object {days, cells, out, ledger, workers, tester, draws, box, build_avg_trade} hands a build its days, exit
cells, store folder and ledger and lets that small run COUNT as a real one, so that the tests (and the app's own tests of
its connector) can save rounds without 45 months of tape. It is refused for the app's own idea folder.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import judge as J
import l2sim as S
import run_idea as RI
import run_menus as RM

from . import api
from . import jobs as JOBS
from . import lines as L
from . import rules as R
from . import runner as RUN
from . import tables as T

TEST_RUN = "BP_TEST_RUN"                            # TEST ONLY (module docstring)
CARD_KEYS = ("why", "loser", "home", "neighbors", "not_here", "main_setting", "sides", "sides_why", "loses_when")
RUN_KEYS = ("family", "params", "fixed", "filters", "exits", "filter_exits", "limits")
SIDES = ("both", "long", "short")
STAGED = os.environ.get("BP_STAGED", "1") != "0"    # a round runs the control pools only when every other line passes (the owner, 2026-10-07); BP_STAGED=0 = always (the old flow)
OWN_EXITS = ("trail_atr", "exit_bars")              # limits that are exits of their own: not of the standard table (line 0.2)
LINES = (*L.BUILD, L.rounds)                        # lines 2.1 .. 2.9, in the law's order (a test puts its own in)
LATER = re.compile(r"_r\d[a-h]?$")                  # how the stores of an idea's later rounds end: no idea is named so
BAR = re.compile(r"(?:tf)?(\d+)-?(?:m|min|mins|minute|minutes)?")
MARKETS = {"gold": "GC", "nasdaq": "NQ"}            # a market in words (besides its own root)
SESSIONS = {"asia": "asia", "asian": "asia", "london": "london", "pre": "pre", "premarket": "pre", "pre-market": "pre", "nyam": "nyam",
            "morning": "nyam", "mid": "mid", "midday": "mid", "pm": "pm", "afternoon": "pm", "eve": "eve", "evening": "eve"}
FILLER = frozenset("the a an and on in at of to its same session sessions bar bars min mins minute minutes market markets new york ny".split())
EVENING = "the evening session comes later (toolkit plan, section 7)"


def _json(path):
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def _text(v) -> str:
    return " ".join(v.split()) if isinstance(v, str) else ""


def _usd(v) -> str:
    return L._n(float(v), unit="$")


def _own(root) -> bool:
    """Is this the app's own idea folder (~/.homebase/ideas)? A folder that was moved -- a test, a trial -- is not."""
    return api.ideastore().ideas_root(root).resolve() == (Path.home() / ".homebase" / "ideas").resolve()


# ================================================================ phase 0: the card

def _family(name):
    """(the class an idea runs, its library entry) of an entry trigger, or None: one of the engine's bar-based families."""
    fam, blocks = RM.registry(), RUN._blocks()
    return (blocks.WRAPPED[name], fam.library(name)) if isinstance(name, str) and name in blocks.WRAPPED else None


def _short(sess: str) -> str:
    return J.SESS_PLAIN[sess].split(" (")[0]


def _nice(p: dict) -> str:
    return f"{p['market']} {_short(p['session'])} {p['bar']}-minute bars"


def place(said, home: dict) -> dict:
    """A place in the card's own words -> {market, session, bar, table, said}: the words name a market, a session or a bar
    size (ONE of each at most), and what they do not say is the home's. ValueError says what was not read."""
    got: dict = {}
    for tok in re.split(r"[\s,;/]+", said.strip()) if isinstance(said, str) else []:
        w = tok.strip(".:()'\"").lower()
        if not w or w in FILLER:
            continue
        m = BAR.fullmatch(w)
        kind, v = (("market", w.upper()) if w.upper() in S.SPECS else ("market", MARKETS[w]) if w in MARKETS else ("session", SESSIONS[w]) if w in SESSIONS
                   else ("bar", str(int(m[1]))) if m else (None, None))
        if kind is None:
            raise ValueError(f"{tok!r} is no market ({', '.join(S.SPECS)}), session ({', '.join(RM.DAY_PASSES[:-1])}) or bar size (5, 15m, 30-minute)")
        if got.setdefault(kind, v) != v:
            raise ValueError(f"names two {kind}s ({got[kind]} and {v}): ONE place an entry")
    if not got:
        raise ValueError("names no place: a market, a session or a bar size")
    if got.get("session") == "eve":
        raise ValueError(EVENING)
    p = {**{k: home[k] for k in ("market", "session", "bar")}, **got}
    return {**p, "table": f"{p['market']}-tf{p['bar']}-{p['session']}", "said": said.strip()}


def _trades_there(cls, run: dict, p: dict) -> bool:
    """Does the entry trigger trade in this place at all (its own session filter)? What cannot be told here is the engine's
    to refuse."""
    try:
        v = {k: x[0] for k, x in (run.get("params") or {}).items()}
        return bool(cls({**(run.get("fixed") or {}), **v, "tf": p["bar"], "sess": p["session"]}).sessions())
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return True


def _filters(run: dict) -> tuple:
    """The filters of the settings -> ([(block, side)], "") or (None, what is wrong with them)."""
    blocks, need, F = RUN._blocks(), R.need("0.2"), run.get("filters", [])
    if not isinstance(F, list) or not all(isinstance(f, dict) and set(f) == {"block", "side"} and f["side"] in blocks.FILTERS.get(f["block"], {}) for f in F):
        return None, "filters: a list of {block, side}; blocks and sides are " + ", ".join(f"{b} {' | '.join(s)}" for b, s in blocks.FILTERS.items())
    F = [(f["block"], f["side"]) for f in F]
    return (None, f"{len(F)} filters (at most {need['max_filters']})") if len(F) > need["max_filters"] else \
        (None, f"filters {' '.join(F[0])} and {' '.join(F[1])} are the two sides of one block: a rule holds one of them") if len({b for b, _ in F}) < len(F) else (F, "")


def _home(card: dict, known) -> tuple:
    """Line 0.3 -> (the home {market, session, bar, table, said} | None, what is missing)."""
    h = card.get("home")
    if not isinstance(h, dict) or not all(str(h.get(k) or "").strip() for k in ("market", "session", "bar")):
        gone = [k for k in ("market", "session", "bar") if not (isinstance(h, dict) and str(h.get(k) or "").strip())]
        return None, f"the home does not say its {', '.join(gone)} (card.home: market, session and bar size)"
    said = {k: str(h[k]).strip() for k in ("market", "session", "bar")}
    alls = [k for k, v in said.items() if v.lower() == "all"]
    if alls:
        return None, (f"the home says \"all\" for its {', '.join(alls)}: version 1 judges ONE home table -- name the {', '.join(alls)} the reason fits best "
                      "and list the others under \"where else it should work\" (line 2.5 reads them)")
    roots, tfs = (known[1]["roots"], known[0].SCREEN_TFS) if known else (tuple(S.SPECS), RM.registry().TFS)
    mk = said["market"].upper() if said["market"].upper() in S.SPECS else MARKETS.get(said["market"].lower(), said["market"])
    ss, m = SESSIONS.get(said["session"].lower()), BAR.fullmatch(said["bar"].lower())
    bar = str(int(m[1])) if m else said["bar"]
    why = (f"market {said['market']}: {'the entry trigger runs on' if known else 'one of'} {', '.join(roots)}" if mk not in roots else
           f"session {said['session']}: one of {', '.join(RM.DAY_PASSES[:-1])}" if ss is None else EVENING if ss == "eve" else
           f"bar size {said['bar']}: {'the entry trigger runs on' if known else 'one of'} {', '.join(tfs)} minutes" if bar not in tfs else "")
    return (None, why) if why else ({"market": mk, "session": ss, "bar": bar, "table": f"{mk}-tf{bar}-{ss}", "said": "home"}, "")


def _places(card: dict, home, known, run: dict) -> tuple:
    """Line 0.4 -> (the neighbors, the place it should not work, what is missing). Without a home (line 0.3 failed) the
    entries are only read as places."""
    nb, nh = card.get("neighbors"), card.get("not_here")
    if not isinstance(nb, list) or not nb or not all(_text(x) for x in nb):
        return None, None, "it does not say where else it should work (card.neighbors: the next bar sizes, the other sessions or markets it should fit)"
    base = home or {"market": "?", "session": "?", "bar": "?"}
    P = []
    for i, said in enumerate([*nb, *([nh] if _text(nh) else [])]):          # (the place it should NOT work is optional since 2026-10-07: none named = none run)
        try:
            P.append(place(said, base))
        except ValueError as e:
            return None, None, (f"the place it should NOT work, {said!r}, {e}" if i == len(nb) else f"neighbor {said!r} {e}")
    nbs, nh = (P[:-1], P[-1]) if _text(nh) else (P, None)
    if home is None:
        return nbs, nh, ""
    seen = {home["table"]: "the home itself"}
    for p in nbs:
        if p["table"] in seen:
            return None, None, f"neighbor {p['said']!r} is {seen[p['table']]}" + ("" if p["table"] == home["table"] else ": named twice")
        seen[p["table"]] = f"the same place as {p['said']!r}"
    if nh and nh["table"] in seen:
        return None, None, f"the place it should NOT work, {nh['said']!r}, is " + ("the home itself" if nh["table"] == home["table"] else "also listed as a place it should work")
    for p in P if known else []:
        cls, lib = known
        why = (f"market {p['market']}: the entry trigger runs on {', '.join(lib['roots'])}" if p["market"] not in lib["roots"] else
               f"bar size {p['bar']}: the entry trigger runs on {', '.join(cls.SCREEN_TFS)} minutes" if p["bar"] not in cls.SCREEN_TFS else
               f"{run.get('family')} never trades there (its own session filter)" if not _trades_there(cls, run, p) else "")
        if why:
            return None, None, f"{p['said']!r}: {why}"
    return nbs, nh, ""


def card_lines(spec: dict) -> tuple:
    """LINES 0.1-0.7 read off an idea's spec -> (the seven rows, the plan of its tables). The plan is None while a line
    fails. plan = {home, neighbors, not_here (each {market, session, bar, table, said}), sides, filters ['<block>_<side>'],
    main_setting, values, variants (a table), stores [{market, bar, sessions}]}: module docstring."""
    card, run = spec["card"], spec["run"]
    known, rows = _family(run.get("family")), []
    if known:                                       # a choice written as a number (ib_min: 5) is the same choice ("5"): the
        d = known[0].defaults()                     # engine names its choices in text, a chat sends numbers

        def text(k, x):
            if isinstance(d.get(k), str) and isinstance(x, (int, float)) and not isinstance(x, bool):
                return str(int(x)) if float(x).is_integer() else str(x)
            return x
        for part in ("params", "fixed"):
            if isinstance(run.get(part), dict):
                run[part] = {k: [text(k, x) for x in v] if isinstance(v, list) else text(k, v) for k, v in run[part].items()}
    # 0.1 the reason, in one sentence, and who loses
    why, loser, need = _text(card.get("why")), _text(card.get("loser")), R.need("0.1")
    n = len([s for s in re.split(r"(?<=[.!?])\s+", why) if s.strip()])
    bad = ("it does not say why it should make money (card.why, one sentence)" if not why else
           "it does not say who is on the losing side (card.loser)" if not loser else
           f"the reason is {n} sentences (need {need['sentences']}): say it in one" if n != need["sentences"] else "")
    rows.append(L._row("0.1", not bad, n, need, bad or f"the reason in one sentence, and who loses: {why} Losing side: {loser}"))
    # 0.2 one entry trigger, at most 2 filters, exits from the standard table only
    need, (F, bad), limits = R.need("0.2"), _filters(run), run.get("limits") or {}
    kind = run.get("exits") if run.get("exits") in R.EXIT_KINDS else need["exits"]       # "standard", or the owner's session-anchored table ("open")
    own = [k for k in OWN_EXITS if isinstance(limits, dict) and limits.get(k)]
    bad = (f"no entry trigger: settings.family names ONE of the engine's bar-based families ({', '.join(sorted(RUN._blocks().WRAPPED))})" if not known else bad or (
           "settings.fixed and settings.limits are objects {input: value}" if not (isinstance(limits, dict) and isinstance(run.get("fixed") or {}, dict)) else
           f"exits {run.get('exits')!r}: the exits come from the standard table (or the session-anchored one, \"open\")" if (run.get("exits"), run.get("filter_exits", run.get("exits"))) != (kind, kind) else
           f"limits.{own[0]} is an exit of its own: the exits come from the standard table only (the random tables hold its cells and no other)" if own else ""))
    rows.append(L._row("0.2", not bad, len(F or []), need, bad or f"one entry trigger ({run['family']}), "
                       + ("no filter" if not F else f"{len(F)} filter{'s' * (len(F) > 1)}: {', '.join(' '.join(f) for f in F)}") + f" (at most {need['max_filters']}), "
                       + ("exits from the standard table" if kind == "standard" else "exits from the owner's session-anchored table (10 stops x 6 targets)")))
    # 0.3 its home
    home, bad = _home(card, known)
    rows.append(L._row("0.3", not bad, None, R.rule("0.3").get("need"), bad or f"home: {home['market']}, {J.SESS_PLAIN[home['session']]}, {home['bar']}-minute bars"))
    # 0.4 where else it should work, and one place it should not
    nbs, nh, bad = _places(card, home, known, run)
    rows.append(L._row("0.4", not bad, len(nbs or []), R.rule("0.4").get("need"), bad or f"{len(nbs)} place{'s' * (len(nbs) > 1)} it should also work "
                       f"({' · '.join(p['said'] for p in nbs)})" + (f" and one where it should NOT ({nh['said']})" if nh else "")))
    l2 = [f for f in (F or []) if f[0] in RUN._blocks().L2_BLOCKS]          # Level 2 exists for NQ only: every place of the card is NQ
    away = [p for p in (home, *(nbs or []), nh) if l2 and p and p["market"] != "NQ"]       # (nh may be None)
    if away and rows[1]["passed"]:
        rows[1] = L._row("0.2", False, rows[1]["number"], rows[1]["need"], f"filter {' '.join(l2[0])} reads Level 2, which exists for NQ only: "
                                                                          f"{away[0]['said']!r} is {away[0]['market']}")
    for f in (F or []):                                                      # SMT compares NQ with ES: its places are NQ or ES
        ok = RUN._blocks().BLOCK_MARKETS.get(f[0])
        away = [p for p in (home, *(nbs or []), nh) if ok and p and p["market"] not in ok]
        if away and rows[1]["passed"]:
            rows[1] = L._row("0.2", False, rows[1]["number"], rows[1]["need"], f"filter {f[0]} runs on {' and '.join(ok)} only: "
                                                                              f"{away[0]['said']!r} is {away[0]['market']}")
    # 0.5 the main setting and its 3-4 values
    ms, params, (lo, hi) = _text(card.get("main_setting")), run.get("params"), R.need("0.5")["values"]
    keys = list(params) if isinstance(params, dict) else []
    v = params.get(ms) if ms in keys else None
    bad = ("it does not name the main setting (card.main_setting: the key of settings.params that carries its values)" if not ms else
           f"the main setting {ms} is not a key of settings.params (it has {', '.join(keys) or 'none'})" if ms not in keys else
           f"settings.params varies {', '.join(keys)}: an idea varies ONE setting, its main setting; the others are held at one value under `fixed`" if len(keys) > 1 else
           f"{ms} has {len(v) if isinstance(v, list) else 0} values (need {lo} or {hi}, each once)"
           if not (isinstance(v, list) and lo <= len(v) <= hi and len({str(x) for x in v}) == len(v)) else
           f"the values of {ms} are opposite ideas, each an idea of its own: hold one of them under `fixed`" if known and known[1].get("mirror") == ms else "")
    rows.append(L._row("0.5", not bad, len(v) if isinstance(v, list) else 0, R.need("0.5"),
                       bad or f"the main setting {ms} and its {len(v)} values ({', '.join(str(x) for x in v)})"))
    # 0.6 both sides or one, and why
    sides, sw, d = card.get("sides"), _text(card.get("sides_why")), limits.get("dir") if isinstance(limits, dict) else None
    bad = (f"sides {sides!r}: both, long or short (card.sides)" if sides not in SIDES else "it does not say why (card.sides_why)" if not sw else
           f"the card says {sides}, settings.limits.dir says {d}" if d not in (None, sides) else "")
    rows.append(L._row("0.6", not bad, None, R.rule("0.6").get("need"), bad or f"{'both sides' if sides == 'both' else sides + ' only'}: {sw}"))
    # 0.7 when it should lose (law v1.1): said in words before any run; nobody checks a motive by machine
    lw = _text(card.get("loses_when"))
    rows.append(L._row("0.7", bool(lw), None, R.need("0.7"), f"when it should lose: {lw}" if lw else
                       "it does not say when it should lose: one stretch or kind of market in which the idea must lose money (card.loses_when)"))
    if not all(x["passed"] for x in rows):
        return rows, None
    pairs: dict = {}
    for p in (home, *nbs, *([nh] if nh else [])):
        pairs.setdefault((p["market"], p["bar"]), set()).add(p["session"])
    plan = {"home": home, "neighbors": nbs, "not_here": nh, "sides": sides, "filters": ["_".join(f) for f in F], "main_setting": ms, "values": list(v),
            "exits": kind, "variants": len(v) * len(R.exit_cells(kind, home["market"])),
            "stores": [{"market": mk, "bar": b, "sessions": [s for s in RM.DAY_PASSES if s in ss]} for (mk, b), ss in pairs.items()]}
    try:                                            # the engine's own check of every store's settings (run_idea, the build range)
        for e in engine(spec, plan, spec["name"]):
            RUN.checked(e)
    except J.Refuse as e:
        i, words = (0, f"the engine does not take the reason: {e}") if "reason is REQUIRED" in str(e) else (1, f"the rule cannot be run as it is written: {e}")
        rows[i] = L._row(rows[i]["line"], False, rows[i]["number"], rows[i]["need"], words)
        return rows, None
    return rows, plan


def engine(spec: dict, plan: dict, store: str) -> list:
    """THE ENGINE'S SETTINGS of an idea's stores, in run_idea's format: ONE spec per market and bar size the card names,
    each with the sessions it names there, all under the store name of the round. The reason is the card's; a one-sided
    card runs its side only."""
    card, run = spec["card"], spec["run"]
    limits = {**(run.get("limits") or {}), **({} if plan["sides"] == "both" else {"dir": plan["sides"]})}
    return [{"name": store, "reason": f"{_text(card['why'])} Losing side: {_text(card['loser'])}", "family": run["family"], "markets": [s["market"]],
             "bar_sizes": [s["bar"]], "sessions": list(s["sessions"]), "params": run["params"], "fixed": run.get("fixed") or {}, "filters": run.get("filters") or [],
             "exits": plan.get("exits", "standard"), "limits": limits} for s in plan["stores"]]


def _name(name) -> str:
    """An idea's name: the app's rule for it (it is also the name of its Lab draft) and the engine's (it is the name of its
    stores). Refused otherwise."""
    try:
        api.ideastore().validate_name(name)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    why = ("is a family of the engine: its stores would collide with the family's" if name in RM.registry().REGISTRY else
           "starts with c1, the prefix of the control pools" if name.startswith("c1") else "has '__', which marks a filter in a store's name" if "__" in name else
           f"ends like the stores of an idea's later round ({LATER.search(name)[0]})" if LATER.search(name) else "")
    if why:
        raise J.Refuse(f"name {name!r} {why}: pick another name")
    return name


def _spec(name: str, spec) -> dict:
    """An idea's spec as it is saved: {name, version, card, run}. Refused: no JSON object, another idea's name, a field the
    card or the settings do not have (a date least of all: the days are the law's)."""
    if not isinstance(spec, dict):
        raise J.Refuse("the idea's spec: a JSON object {name, card, run}")
    card, run = spec.get("card"), spec.get("run")
    extra = sorted(set(spec) - {"name", "version", "card", "run"})
    why = (f"unknown fields {extra}: an idea's spec is {{name, version, card, run}}" if extra else
           f"the spec is {spec['name']!r}'s, not {name}'s" if spec.get("name", name) != name else
           f"card: an object with the idea card's fields ({', '.join(CARD_KEYS)})" if not isinstance(card, dict) else
           f"settings (run): an object with the fields {', '.join(RUN_KEYS)}" if not isinstance(run, dict) else
           "version: a whole number from 1" if type(spec.get("version", 1)) is not int or spec.get("version", 1) < 1 else "")
    for what, obj, keys in (("the card", card, CARD_KEYS), ("the settings", run, RUN_KEYS)) if not why else ():
        extra = sorted(set(obj) - set(keys))
        why = why or (f"unknown fields {extra} in {what}: its fields are {', '.join(keys)}" if extra else "")
    if why:
        raise J.Refuse(why)
    return {"name": name, "version": spec.get("version", 1), "card": dict(card), "run": dict(run)}


def _trigger(family: str) -> str:
    """The entry trigger in the registry's own words: the first sentence of its notes, without the registry's label."""
    said = RUN._blocks().BASES[family][3].split(". ")[0].rstrip(".")
    head, _, rest = said.partition(": ")
    return rest if rest and head.endswith(family) else said


def _card_md(spec: dict, plan: dict) -> str:
    """card.md: the card in plain words, its seven lines by their numbers."""
    c, run, blocks = spec["card"], spec["run"], RUN._blocks()
    F = [tuple(f.split("_", 1)) for f in plan["filters"]]
    limits, fixed = run.get("limits") or {}, run.get("fixed") or {}
    said = lambda d: ", ".join(f"{k} = {v}" for k, v in d.items())  # noqa: E731
    return "\n".join([
        f"# {spec['name']} -- idea card (version {spec['version']})", "",
        f"0.1 Why it should make money: {_text(c['why'])}",
        f"    Who is on the losing side: {_text(c['loser'])}",
        f"0.2 The rule: entry trigger {run['family']} ({_trigger(run['family'])}); "
        + ("no filter" if not F else "filters: " + "; ".join(f"{b} {s} ({blocks.PLAIN[(b, s)]})" for b, s in F)) + ("; exits from the standard table (8 stops x 6 targets)" if plan.get("exits", "standard") == "standard" else
           "; exits from the owner's session-anchored table (5 stops of the mean true range since the session started and 5 of its range, x 6 targets)")
        + (f"; limits: {said(limits)}" if limits else ""),
        f"0.3 Home: {plan['home']['market']}, {J.SESS_PLAIN[plan['home']['session']]}, {plan['home']['bar']}-minute bars",
        "0.4 Where else it should work: " + "; ".join(f"{p['said']} ({_nice(p)})" for p in plan["neighbors"]),
        *([f"    Where it should NOT work: {plan['not_here']['said']} ({_nice(plan['not_here'])})"] if plan.get("not_here") else []),
        f"0.5 Main setting: {plan['main_setting']} = {', '.join(str(x) for x in plan['values'])}" + (f"; held fixed: {said(fixed)}" if fixed else ""),
        f"0.6 Sides: {'both' if plan['sides'] == 'both' else plan['sides'] + ' only'} -- {_text(c['sides_why'])}",
        f"0.7 When it should lose: {_text(c.get('loses_when'))}"]) + "\n"


def _plan_text(name: str, plan: dict) -> list:
    """What a build of the card runs and which line reads what, in plain words."""
    rg, h, key = R.template("ranges")["build"], plan["home"], lambda s: RI.unit_key({"name": name}, s["market"], s["bar"])  # noqa: E731
    F = [f.replace("_", " ", 1) for f in plan["filters"]]
    return [f"WHAT A BUILD RUNS ({rg['start']} .. {rg['end']}; a table = the {len(R.exit_cells(plan.get('exits', 'standard'), plan['home']['market']))} exit cells of the {'standard' if plan.get('exits', 'standard') == 'standard' else 'session-anchored'} table x the {len(plan['values'])} values of "
            f"{plan['main_setting']} = {plan['variants']} variants):",
            f"  HOME      {_nice(h)}: lines 2.1-2.4, 2.6 and 2.8 are read on this table, 2.3 against the random-entry pool {RUN.pool_key(h['market'], h['bar'], plan.get('exits', 'standard') == 'open' and RUN.OPEN or RUN.EXITS)} "
            f"({R.template('control')['seeds']} seeds; the Monte Carlo and the control are run only when every cheaper line passes: first the tables, then the Monte Carlo, then the pool)",
            *[f"  NEIGHBOR  {_nice(p)} (\"{p['said']}\"): a table of its own; line 2.5 asks half of the neighbors or more to be profitable" for p in plan["neighbors"]],
            *([f"  NOT HERE  {_nice(plan['not_here'])} (\"{plan['not_here']['said']}\"): run and shown; no line reads it"] if plan.get("not_here") else []),
            "  SIDES     " + ("both: line 2.6 asks long and short each above $0" if plan["sides"] == "both" else f"{plan['sides']} only: line 2.6 is read on that side"),
            "  FILTER    " + ("none: line 2.7 does not apply" if not F else
                              f"{F[0]}: every table is read with it on; line 2.7 holds the home table against the same table without it" if len(F) == 1 else
                              f"{', '.join(F)}: version 1 builds a rule with ONE filter -- each wins alone first, one a round (line 2.7); the build refuses "
                              "the two together"),
            "  STORES    " + ", ".join(f"{key(s)} (sessions {', '.join(s['sessions'])})" for s in plan["stores"])
            + (f", each also with the filter on ({name}__{plan['filters'][0]}-...)" if len(F) == 1 else "")
            + f": one tape pass each; a later round that changes a base setting gets stores of its own ({name}_r2 ...), a filter does not"]


def _lab(name: str, root) -> tuple:
    """Bring the app's copies up to date (ideastore.sync: idea.json, the record block on the Lab draft, its Lab group) ->
    ({filed, notes}, the lines that say it, idea.json). The Lab is a mirror: what could not be written is said, never raised."""
    IS = api.ideastore()
    got = IS.sync(name, root)
    said = ([f"Lab: {IS.draftstore.draft_id(name)} is filed under {got['filed']}."] if got["filed"] else []) + [f"Lab: {n}." for n in got["notes"]]
    return {"filed": got["filed"], "notes": got["notes"]}, said, got["idea"]


def card(name, spec, root=None) -> dict:
    """`bp.py card <name> --spec=-`: PHASE 0. Reads lines 0.1-0.7 off the card. A card with a line missing is REFUSED (the
    result has `ok` false, every line as pass or fail, the missing ones named in `error`) and nothing is written. A whole
    card is saved in the app: the idea's folder (card.md in plain words, spec.json) and its record draft in the Lab with
    the card on top, filed under Ideas. Beyond the agreed keys: plan (what a build runs), lab.
    The card may be written again until the idea is frozen; once a round is on file the entry trigger stays (a different
    trigger is a new idea), and what changed is run by the next round. Refused outright: a name that is no idea's, a spec
    that is no card, a frozen idea."""
    IS, name = api.ideastore(), _name(name)
    spec = _spec(name, spec)
    d = IS.idea_dir(name, root)
    if (d / "lock.json").exists():
        raise J.Refuse(f"{name} is frozen (lock.json): from here nothing changes -- a change is a new version, back to the build (line 3.2)")
    first = next((s for s in (_json(d / "rounds" / str(n) / "spec.json") for n in (IS.rounds(name, root) if d.is_dir() else [])) if s), None)
    if first and first.get("run", {}).get("family") != spec["run"].get("family"):
        raise J.Refuse(f"{name} was built on the entry trigger {first['run'].get('family')}: {spec['run'].get('family')} is a different trigger, and a different "
                       "trigger is a new idea (BLUEPRINT.md section 7) -- give it its own name")
    rows, plan = card_lines(spec)
    head = [f"IDEA CARD of {name} (phase 0)", *[x["text"] for x in rows]]
    if plan is None:
        why = "the card is not whole: " + "; ".join(x["text"] for x in rows if x["passed"] is False)
        return api.result("card", name, ok=False, lines=rows, error=why, text="\n".join([*head, "REFUSED: " + why]),
                          next="Write what is missing and send the card again: nothing was saved.")
    spec["card"]["home"] = {k: plan["home"][k] for k in ("market", "session", "bar")}        # as the engine names them (the Lab draft reads the market)
    IS.create(name, root, exist_ok=True)
    saved = [str(IS.write_card(name, _card_md(spec, plan), root)), str(IS.write_spec(name, spec, root))]
    lab, said, idea = _lab(name, root)
    try:
        draft = IS.draftstore.path_for(name, IS.lab_dir(root))
        saved += [str(draft)] * draft.is_file()
    except ValueError:
        pass                                        # no Lab for this idea folder: `said` has the note
    n = len(IS.rounds(name, root))
    return api.result("card", name, status=idea["status"], lines=rows, saved=saved, plan=plan, lab=lab,
                      text="\n".join([*head, *_plan_text(name, plan), f"The card and the settings are on file ({d})." + (f" {n} round{'s' * (n > 1)} on file: the next "
                                      "round runs the card as it now stands." if n else ""), *said]),
                      next=_step(name, idea["status"], _last(name, root), root))


# ================================================================ phase 2: the build, round by round

def _test_run(root) -> dict:
    """BP_TEST_RUN (TEST ONLY; module docstring) -> its settings, or {} when it is not set. Never for the app's own idea
    folder: a small run must not become a verdict there."""
    raw = os.environ.get(TEST_RUN)
    if not raw:
        return {}
    if _own(root):
        raise J.Refuse(f"{TEST_RUN} is set: it is for the tests and is never taken for the app's own idea folder")
    try:
        got = json.loads(raw)
    except ValueError:
        got = None
    if not isinstance(got, dict):
        raise J.Refuse(f"{TEST_RUN}: a JSON object {{days, cells, out, ledger, workers, tester, draws, box, build_avg_trade}}")
    return got


def _carded(name, root) -> Path:
    """The idea's folder -- with its card on file, or refused: phase 0 comes before any run."""
    try:
        d = api.ideastore().idea_dir(name, root)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    if not ((d / "card.md").is_file() and _json(d / "spec.json")):
        raise J.Refuse(f"{name} has no card on file: the card is written before any run (bp.py card {name} --spec=FILE). A spec in run_idea's format that has "
                       "no record is built with --spec-file=PATH, as one table and never as a round")
    return d


def _store(name: str, n: int, spec: dict, plan: dict, earlier: list, out, days, cells) -> str:
    """THE STORE NAME of round n (module docstring): the first of [the earlier rounds' names, latest first · <idea> or
    <idea>_r<n> · that name + b, c ...] under which no store of the idea on disk was written from other inputs."""
    folder = RUN.RUNS if out is None else Path(out)

    def fits(store: str) -> bool:
        for e in engine(spec, plan, store):
            for p in RUN.parts(RUN.checked(e), cells):
                m = _json(folder / p["key"] / "run.json") if p["kind"] != "pool" else None
                if m is not None and m.get("inputs_hash") != RUN.fingerprint(p, days):
                    return False
        return True

    own = name if n == 1 else f"{name}_r{n}"
    for store in dict.fromkeys([*earlier, own, *(f"{name}_r{n}{c}" for c in "bcdefgh")]):
        if fits(store):
            return store
    raise J.Refuse(f"{name}: no free store name for round {n} in {folder} (every one up to {name}_r{n}h holds other inputs)")


def _seeds(market: str, bar: str, out, exits: str = "standard") -> None:
    """Refused: the control pool of the home's market and bar size is on disk with fewer seeds than the law asks for
    (control.json). A pool that is not there yet is run by the build, with all of them."""
    key, want, folder = RUN.pool_key(market, bar, RUN.OPEN if exits == "open" else RUN.EXITS), R.template("control")["seeds"], RUN.RUNS if out is None else Path(out)
    meta = _json(folder / key / "run.json")
    if meta is None:
        return
    RUN.guard(meta, f"{folder.name}/{key}")
    have = {m[1] for c in meta.get("cells") or [] for m in [re.match(r"s(\d+)_", str(c.get("id")))] if m}
    if len(have) < want:
        raise J.Refuse(f"control pool {folder.name}/{key} holds {len(have)} of the {want} seeds the law asks for ({R.template('control')['draws']:,} draws from "
                       f"{want} seeds): a build is not read against a thin control")


def start(name, reason, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, tester=None) -> dict:
    """EVERYTHING OF A ROUND THAT NEEDS NO RUN -> the arguments of run() (JSON: a job keeps them). Refused here, at once and
    never as a job: no card · no reason · round 6 · a frozen idea · a card on file that is no longer whole · a rule with two
    filters · a thin control pool · a day outside the build range, the no-start window, the ledger's cap, another run in
    the store folder, a missing tape (runner.run_build, dry) · a build of this idea that is still running.
    Then THE REASON AND THE ROUND'S SETTINGS ARE SAVED, before anything runs (line 2.9) -- unless the run is on named days
    (a smoke run: nothing is saved). out, ledger, days, cells, block, workers = runner.run_build's; tester = the tester's
    base folder the default variant's run goes to (the app's own for the app's own idea folder)."""
    test = _test_run(root)
    IS, d = api.ideastore(), _carded(name, root)
    reason = _text(reason if isinstance(reason, str) else "")
    if not reason:
        raise J.Refuse(f"no reason: every round has its reason written before the run (line 2.9): bp.py build {name} --reason=\"why this round is run\"")
    if (d / "lock.json").exists():
        raise J.Refuse(f"{name} is frozen (lock.json): from here nothing changes -- a change is a new version, back to the build (line 3.2)")
    done, most = [n for n in IS.rounds(name, root) if (d / "rounds" / str(n) / "build.json").is_file()], R.need("2.9")
    n = max(done, default=0) + 1                    # the builds on file + 1
    if n > most:
        raise J.Refuse(f"round {n}: at most {most} rounds, each with its reason (line 2.9) -- {name} has had its {most} and is shelved, with what was tried on file")
    spec = _spec(name, _json(d / "spec.json"))
    rows, plan = card_lines(spec)
    if plan is None:
        raise J.Refuse(f"the card of {name} on file is no longer whole ({next(x['text'] for x in rows if x['passed'] is False)}): write it again (bp.py card)")
    if len(plan["filters"]) > 1:
        raise J.Refuse(f"{name}'s rule has {len(plan['filters'])} filters: version 1 reads a rule with one filter at most -- the table with both on is not run "
                       "yet. A filter is kept only if it wins alone (line 2.7): bring them one a round")
    days, cells = (days or test.get("days")), (cells or test.get("cells"))
    out, ledger, workers, tester = out or test.get("out"), ledger or test.get("ledger"), workers or test.get("workers"), tester or test.get("tester")
    days = None if days is None else RUN.seal(days)
    earlier = [s["store"] for s in (_json(d / "rounds" / str(k) / "spec.json") for k in reversed(IS.rounds(name, root))) if s and s.get("store")]
    store = _store(name, n, spec, plan, earlier, out, days, cells)
    _seeds(plan["home"]["market"], plan["home"]["bar"], out, plan.get("exits", "standard"))
    job = JOBS.running(name, root)
    if job:
        raise J.Refuse(f"a build of {name} is still running (job {job}): one build of an idea at a time -- bp.py job {job} picks its wait back up")
    RUN.run_build(engine(spec, plan, store), workers, out, ledger=ledger, days=days, cells=cells, block=block, dry=True)
    rspec, counted = {**spec, "round": n, "store": store, "plan": plan}, days is None or bool(test)
    if counted:
        try:
            IS.write_reason(name, n, reason, root)
            IS.write_round_spec(name, n, rspec, root)
        except ValueError as e:                     # (the idea store's own word, e.g. a result that landed meanwhile)
            raise J.Refuse(str(e)) from None
    return {"idea": name, "round_": n, "reason": reason, "rspec": rspec, "counted": counted, "test": bool(test), "root": None if root is None else str(root),
            "workers": workers, "out": None if out is None else str(out), "ledger": None if ledger is None else str(ledger), "days": days, "cells": cells,
            "block": block, "tester": None if tester is None else str(tester), "draws": test.get("draws")}


def middle(rows: list, ids: list, worse=None) -> tuple:
    """THE DEFAULT VARIANT: the middle of the survivors, never the best (line 3.1) -> (its cell | None, the survivors in
    order). rows = the table's rows (id, net, vi, xi), ids = its judged variants. At a build the survivors are the judged
    variants that made money on build, in the judge's own order and with its tie rule (judge.TIE_RULE: by net, then by
    variant order; an even count takes the lower of the two middle ones). At the freeze `worse` = {cell: its net on build
    with worse fills}: a survivor makes money on build AND there (the order stays the build net's)."""
    by = {r["id"]: r for r in rows}
    surv = sorted((c for c in ids if L._profitable(by[c]["net"]) and (worse is None or L._profitable(worse[c]))),
                  key=lambda c: (round(by[c]["net"], 2), by[c]["vi"], by[c]["xi"]))
    return (surv[(len(surv) - 1) // 2] if surv else None), surv


def show(name: str, n: int, spec: dict, key: str, cell: str, sess: str, st: dict, days, survivors: int, root=None, tester=None) -> dict:
    """THE DEFAULT VARIANT IN THE APP: the cell's trades, run again for their prices (runner.cell_trades), held against the
    store (the same number of trades, the same net: else the code changed since the store was written -- line 1.6 -- and
    nothing is shown), written as a finished run of the tester by homebase/backtest/importrun.py (the app's own Python)
    under the idea's Lab draft, and its run id kept with the idea. -> {cell, survivors, trades, run_id, note}.
    A mirror, never a gate: what could not be shown is said in `note`. An idea folder that was moved (a test, a trial)
    never writes the app's own tester: without `tester` nothing is shown."""
    out = {"cell": cell, "survivors": survivors, "trades": None, "run_id": None, "note": None}
    try:
        if not tester and not _own(root):
            raise J.Refuse("the idea folder is not the app's own, and a moved idea folder never writes the app's tester: say where the runs go (--tester=DIR)")
        trades, x = RUN.cell_trades(spec, key, cell, sess, days), J.cellx(st, cell, sess)
        if len(trades) != len(x["net"]) or abs(sum(t["net"] for t in trades) - float(x["net"].sum())) >= 0.01:
            raise J.Refuse(f"run again, {cell} has {len(trades):,} trades where its store has {len(x['net']):,} (or another net): the code changed since the store "
                           "was written, and the earlier trade list is reproduced before a new run counts (line 1.6)")
        rg, market, bar = R.template("ranges")["build"], spec["markets"][0], spec["bar_sizes"][0]
        a, b = (days[0], days[-1]) if days else (rg["start"], rg["end"])
        out.update(trades=len(trades), run_id=imported(
            name, trades, market, f"{name} round {n}: {cell} ({market} {sess} {bar}m)", a, b,
            len(days) if days else len(S.sessions(*S.period(RUN.PERIOD), market, allow_holdout=RUN.PERIOD)),
            f"blueprint build of {name}, round {n}: the default variant {cell} = the middle of the variants that made money on "
            f"build ({survivors} of them; home {market} {sess}, {bar}-minute bars; 1 contract after costs)", root, tester))
    except (J.Refuse, ValueError, OSError, subprocess.SubprocessError) as e:
        out["note"] = f"not shown on the tester page: {e}"
    return out


def imported(name: str, trades: list, market: str, title: str, start: str, end: str, sessions: int, note: str, root=None, tester=None) -> str:
    """A TRADE LIST OF THE ENGINE AS A FINISHED RUN OF THE TESTER, listed under the idea's Lab draft: written by
    homebase/backtest/importrun.py (the app's own Python), its run id kept with the idea (idea.json `runs`) -> the run id.
    An idea folder that was moved (a test, a trial) never writes the app's own tester: without `tester` it is refused.
    Raises J.Refuse / OSError / subprocess errors: the caller says what was not shown (a mirror, never a gate)."""
    if not tester and not _own(root):
        raise J.Refuse("the idea folder is not the app's own, and a moved idea folder never writes the app's tester: say where the runs go (--tester=DIR)")
    with tempfile.TemporaryDirectory(prefix="bp_show_") as tmp:
        f = Path(tmp) / "trades.json"
        f.write_text(json.dumps({"trades": trades}))
        p = subprocess.run([str(S.REPO / ".venv" / "bin" / "python"), "-B", "-m", "homebase.backtest.importrun", str(f), "--strategy", f"draft_{name}",
                            "--root", market, "--name", title[:80], "--start", start, "--end", end, "--sessions", str(sessions),      # (a name: 80 characters there)
                            "--note", note, *(["--base", str(tester)] if tester else [])],
                           cwd=str(S.REPO), capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    if p.returncode != 0 or not p.stdout.strip():
        raise J.Refuse(f"importrun answered {p.returncode}: {(p.stderr or p.stdout).strip()[-300:] or 'nothing'}")
    run_id = p.stdout.strip().splitlines()[-1]
    api.ideastore().add_run(name, run_id, root)
    return run_id


def _last(name, root):
    """What the idea's latest round with a result says, for the next step: (round, failed lines, the store key the code
    check reads) -- or None before the first."""
    IS, d = api.ideastore(), api.ideastore().idea_dir(name, root)
    for n in reversed(IS.rounds(name, root) if d.is_dir() else []):
        b = _json(d / "rounds" / str(n) / "build.json")
        if b:
            return n, b.get("failed") or [], b.get("home_store")
    return None


def _checked(name, root) -> bool:
    """Is a passed code check of the idea on file (phase 1)?"""
    return (_json(api.ideastore().idea_dir(name, root) / "check.json") or {}).get("passed") is True


def _step(name: str, status: str, last, root, checked=None) -> str:
    """THE NEXT STEP of an idea, in one sentence, from what is on file."""
    most, d = R.need("2.9"), api.ideastore().idea_dir(name, root)
    if status == "shelved":
        return (f"NOT PROVEN on the out-of-sample test: a fail is final -- {name} is SHELVED, and it is not re-tuned and re-tested on that period"
                if (d / "test.json").is_file() else f"Not passed after round {most}: {name} is SHELVED, with what was tried on file")
    if status not in ("idea", "lead"):
        return api.ideastore().read_idea(name, root).get("next") or ""          # tested and beyond: the later phases say their own
    if status == "lead" and (d / "lock.json").is_file():                        # frozen: the one read is what is left of the history
        try:
            read = api.ideastore().read_on_file(name, root=root)
        except ValueError:                                                      # (the app's word for a log with a line that does not read)
            read = {"state": "not readable", "utc": "the one-read log has a line that does not read"}
        other = read and read.get("lock") not in (None, (_json(d / "lock.json") or {}).get("hash"))      # a read of ANOTHER lock: an early look, an earlier version
        return (f"{name} is FROZEN and its test days are USED (a read of another lock is on file: {read.get('state')}, {read.get('utc')} -- an early look, or "
                f"an earlier version): its out-of-sample test can only be a SECOND LOOK -- bp.py test {name} --confirm --second-look, only when the owner has "
                "said to" if other else
                f"{name} is FROZEN and its read of the test days is on file ({read.get('state')}, {read.get('utc')}): the test days are read once -- "
                f"bp.py status {name} shows a job that is still running" if read else
                f"{name} is FROZEN: the out-of-sample test is next and it is ONE read of the test days, never repeated -- bp.py test {name} --confirm, "
                "only when the owner has said to")
    if last is None:
        return (f"The card is on file and the build is next: bp.py build {name} --reason=\"why round 1 is run\" (round 1 of at most {most}; with --days it is a "
                "smoke run that gives the code check its store)")
    n, failed, key = last
    checked = _checked(name, root) if checked is None else checked
    check = f"bp.py code-check {name}" + (f" --store={key}" if key else "")
    if status == "lead":
        return (f"Every build line passes and the code is checked: {name} is a LEAD, and the freeze is next (bp.py lock {name})" if checked else
                f"Every build line passes: before the freeze, the code check has to pass on the round's home store ({check}, then --looked)")
    return (f"Fails {', '.join(failed)}: round {n + 1} of at most {most} needs its reason first (bp.py build {name} --reason=\"why\"; its random bar is "
            f"{100 * R.need('2.3', n + 1):g} %), or leave the idea" + ("" if checked else f" -- and the code check has not passed yet ({check})"))


def run(idea, round_, reason, rspec, counted, test=False, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, tester=None,
        draws=None, progress=None) -> dict:
    """THE ROUND ITSELF, with what start() returned: runs what is missing of the idea's stores (runner.run_build: a store
    that is there is never run again), reads lines 2.1-2.9 on the home table at the round's bar -- 2.5 on the neighbors the
    card names, 2.6 by the card's sides, 2.7 for a rule with a filter -- and, for a round that counts, shows the default
    variant in the app, saves the result (rounds/<n>/build.json: every line 2.1-2.9, null = it does not apply and its text
    says why) and brings the idea's status, its Lab block and its Lab group up to date.
    Beyond the agreed keys: idea, counted, dry_run (a run on named days: never saved), smoke, test_run, bar, store, home,
    unit, home_store, filter, reason, days, table, neighbors, not_here, sides, stores, failed, not_applicable, thin, passed,
    default, code_check, notes, lab. Refused: the runner's refusals; a strategy error in a pass (no store was written)."""
    IS, name, n, plan, store = api.ideastore(), idea, round_, rspec["plan"], rspec["store"]
    specs = [RUN.checked(e) for e in engine(rspec, plan, store)]
    keep = J.RULE["draws"]
    try:
        if draws:
            J.RULE["draws"] = int(draws)            # (a test run only)
        def dropped(stores):
            bad = [s for s in stores if not s["ok"]]
            if bad:
                raise J.Refuse(f"{bad[0]['key']}: sessions were dropped by a strategy error ({bad[0]['error']}): no store was written; the family has to be fixed first")

        # STAGE 1: the idea's own tables and the cheap lines (2.1, 2.2, 2.4-2.7, 2.9). STAGE 2, only when those pass: the Monte Carlo
        # (line 2.8). STAGE 3, only when all of those pass: the control pools (10 seeds x every exit cell x 7 sessions: the slow
        # part) and line 2.3 (the owner, 2026-10-07: a control or a Monte Carlo run for an idea that has failed already is a waste --
        # a round with a failed line is a failed round either way).
        stores = RUN.run_build(specs, workers, out, ledger=ledger, days=days, cells=cells, progress=progress, block=block, stage="units" if STAGED else "all")
        dropped(stores)
        h, filt = plan["home"], (plan["filters"][0] if plan["filters"] else None)
        f = T.filter_of(specs[0], filt)
        like = T.sigs(store, plan["home"]["market"], plan["home"]["bar"], plan["home"]["session"], f, out)
        nbs = [{**p, **T.place(store, p["market"], p["bar"], p["session"], f, out, like)} for p in plan["neighbors"]]
        nh = ({**plan["not_here"], **T.place(store, plan["not_here"]["market"], plan["not_here"]["bar"], plan["not_here"]["session"], f, out)}
              if plan.get("not_here") else None)          # (none named, none run)

        def read(control, mc):
            t = T.built(specs[0], h["table"], filt, out, days, n, control=control)
            t.update(neighbors=[x["avg_net"] if x["variants"] else 0.0 for x in nbs if not x["copy"]],      # a table that is the home
                     copies=[x["said"] for x in nbs if x["copy"]], sides=plan["sides"], reason=reason, mc_skipped=not mc)        # table's trades counts once
            return t, [fn(t) for fn in LINES]
        clean = lambda rows: not [x for x in rows if x["passed"] is False]  # noqa: E731
        t, rows = read(not STAGED, not STAGED)
        if STAGED and clean(rows):                  # stage 2: the Monte Carlo (reshuffled runs: line 2.8) ...
            t, rows = read(False, True)
            if clean(rows):                         # ... stage 3: the control pools and line 2.3, only when everything before them passes
                more = RUN.run_build(specs, workers, out, ledger=ledger, days=days, cells=cells, progress=progress, block=block, stage="pools")
                dropped(more)
                stores = stores + more
                t, rows = read(True, True)
    finally:
        J.RULE["draws"] = keep
    failed, most, rg, d = [x["line"] for x in rows if x["passed"] is False], R.need("2.9"), R.template("ranges")["build"], IS.idea_dir(name, root)
    default = None
    if counted:
        cell, surv = middle(J.table(t["_st"], t["_u"]), t["ids"])
        default = ({"cell": None, "survivors": 0, "trades": None, "run_id": None, "note": "no variant made money on build: there is no default variant to show"}
                   if cell is None else show(name, n, specs[0], t["_u"]["key"], cell, h["session"], t["_st"], days, len(surv), root, tester))
    r = api.result("build", name, round=n, lines=rows, idea=name, counted=counted, dry_run=not counted, smoke=bool(days), bar=R.need("2.3", n), store=store,
                   home=h["table"], unit=t["unit"], home_store=t["_u"]["key"], filter=filt, reason=reason,
                   days={"start": rg["start"], "end": rg["end"], "months": rg["months"], "sessions": len(t["days"]), "named": list(days) if days else None},
                   table={"store": t["store"], "variants": len(t["ids"]), "dead": t["dead"], "duplicates": t["dup"]}, neighbors=nbs, not_here=nh, sides=plan["sides"],
                   stores=stores, failed=failed, not_applicable=[x["line"] for x in rows if x["passed"] is None and not x.get("skipped")],
                   skipped=[x["line"] for x in rows if x.get("skipped")], thin=[x["line"] for x in rows if x.get("thin")],
                   passed=not failed, default=default, code_check={"on_file": (d / "check.json").is_file(), "passed": (_json(d / "check.json") or {}).get("passed")})
    if test:
        r["test_run"] = True
    r["status"] = ("lead" if not failed else "shelved" if n >= most else "idea") if counted else IS.status(name, root)
    table = lambda x: (f"average variant {_usd(x['avg_net'])}, {x['positive']} of {x['variants']} variants profitable" if x["variants"] else  # noqa: E731
                       "no variant traded there")
    old = [s["key"] for s in stores if s.get("code_same") is False]
    r["notes"] = ([f"{', '.join(old)} {'was' if len(old) == 1 else 'were'} written by other code than today's: after a change to the code the earlier trade list is "
                   f"reproduced exactly before a new run counts (line 1.6: bp.py code-check {name} --store=<a fresh run> --same-as=<the store>)"] if old else []) \
        + ([f"a {plan['sides']}-only idea is read against random entries of BOTH sides (the pool holds no one-sided table): for line 2.3 that is a tilted control"]
           if plan["sides"] != "both" else [])
    text = [(f"TEST RUN on {len(days)} named days of the build range ({rg['start']} .. {rg['end']}): it counts only because {TEST_RUN} is set." if test and days else
             api.headline(r["days"])),
            f"{name} · round {n} of at most {most} · random bar {100 * r['bar']:g} % · home {_nice(h)} · {len(t['ids'])} variants · {len(t['days']):,} session days · "
            f"store {t['store']}",
            *[x["text"] for x in rows],
            *[f"NEIGHBOR  {x['said']} ({x['table']}): {table(x)} -> {'profitable' if x['profitable'] else 'not profitable'}" for x in nbs],
            *([f"NOT HERE  {nh['said']} ({nh['table']}): {table(nh)} (shown; no line reads it)"] if nh else []),
            f"RESULT{' of the smoke run' if not counted else ''}: " + (("fails " + ", ".join(failed)) if failed else "every line that applies passes") + ".",
            *[f"NOTE: {x}." for x in r["notes"]]]
    if not counted:
        r.update(saved=[s["path"] for s in stores if not s["skipped"]], text="\n".join([*text, f"STATUS: {r['status'].upper()} (a smoke run changes nothing)"]),
                 next="A smoke run is no verdict and no round: the build on the whole range (no --days) is the round")
        return r
    text += [f"STATUS: {r['status'].replace('_', ' ').upper()} · phase 2 · round {n}",
             (f"DEFAULT VARIANT {default['cell']}: the middle of the {default['survivors']} variant{'s' * (default['survivors'] != 1)} that made money on build -> "
              f"tester run {default['run_id']}"
              if default["run_id"] else f"DEFAULT VARIANT {default['cell'] or '(none)'}: {default['note']}")]
    r.update(saved=[s["path"] for s in stores if not s["skipped"]] + [str(d / "rounds" / str(n) / x) for x in ("reason.txt", "spec.json", "build.json")],
             text="\n".join(text), next=_step(name, r["status"], (n, failed, t["_u"]["key"]), root))
    IS.write_build(name, n, r, root)
    r["lab"], said, idea_json = _lab(name, root)
    if idea_json["status"] != r["status"]:          # the app's reading of what is saved is the status: never passed over
        said.append(f"NOTE: the app reads the saved results as {idea_json['status'].upper()}.")
        r["status"] = idea_json["status"]
    r["text"] = "\n".join([*text, *said])
    return r


def build(name, reason, root=None, **kw) -> dict:
    """`bp.py build <name> --reason=TEXT` in the foreground: start(), then run()."""
    return run(**start(name, reason, root, **kw))


# ================================================================ the status

def status(name=None, root=None) -> dict:
    """`bp.py status [<name>]`: where things stand. Runs nothing. Without a name: every idea on file, one line each (status,
    phase, round, next step; a build that is still running) -- `ideas`. With a name: the full record of that idea --
    `record` = {idea (idea.json), card, spec, check, rounds [{round, bar, reason, store, passed, failed}], job, log} -- and
    its latest verdict as `lines`. Each idea.json is brought up to date with the saved results first. Refused: no such idea."""
    IS, most = api.ideastore(), R.need("2.9")
    head = lambda i: (f"{i['status'].replace('_', ' ').upper()} · phase {i['phase']}" + (f" · round {i['round']} of {most}" if i["round"] else ""))  # noqa: E731
    if name is None:
        ideas = []
        for i in IS.list_ideas(root):
            i = IS.refresh(i["name"], root)
            ideas.append({**{k: i[k] for k in ("name", "status", "phase", "round", "group", "runs")}, "next": _step(i["name"], i["status"], _last(i["name"], root), root),
                          "job": JOBS.running(i["name"], root)})
        said = [f"{i['name']}: {head(i)} · next: {i['next']}" + (f" · job {i['job']} is running" if i["job"] else "") for i in ideas]
        return api.result("status", None, ideas=ideas, text="\n".join([f"{len(ideas)} idea{'s' * (len(ideas) != 1)} in {IS.ideas_root(root)}", *said]) if ideas else
                          f"No idea on file in {IS.ideas_root(root)}: bp.py card <name> --spec=FILE writes the first one.")
    try:
        d = IS.idea_dir(name, root)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    if not d.is_dir():
        raise J.Refuse(f"no idea {name} in {IS.ideas_root(root)}")
    i, rounds, full = IS.refresh(name, root), [], {}
    for n in IS.rounds(name, root):
        b, s, f = _json(d / "rounds" / str(n) / "build.json") or {}, _json(d / "rounds" / str(n) / "spec.json") or {}, d / "rounds" / str(n) / "reason.txt"
        rounds.append({"round": n, "bar": R.need("2.3", n), "reason": f.read_text(encoding="utf-8").strip() if f.is_file() else None, "store": s.get("store"),
                       "passed": b.get("passed"), "failed": b.get("failed")})
        full = {x["line"]: x for x in b.get("lines") or []} or full
    full = {**full, **{x["line"]: x for x in (_json(d / "test.json") or {}).get("lines") or [] if isinstance(x, dict)}}      # (a tested idea: its 4.x lines)
    card_md = (d / "card.md").read_text(encoding="utf-8") if (d / "card.md").is_file() else None
    rows = [{"line": x["line"], "passed": x["passed"], "number": full.get(x["line"], {}).get("number"), "need": full.get(x["line"], {}).get("need"), "text": x["text"]}
            for x in i["lines"]]
    job, lock = JOBS.running(name, root), _json(d / "lock.json")
    try:
        read = IS.read_on_file(name, root=root)
    except ValueError as e:                         # (a one-read log that does not read: said, and the test will refuse)
        read = {"state": "unreadable", "utc": None, "verdict": str(e)}
    home = (lock or {}).get("home") or {}
    rng = ((lock or {}).get("test_range") or {}).get(home.get("market")) or {}
    early = _json(d / api.EARLY_LOOK / "test.json")     # an early look at the test days (oos.py): shown, and never part of the status
    text = [f"{name} · {head(i)}" + (f" · Lab group {i['group']}" if i["group"] else "")
            + (f" · {len(i['runs'])} tester run{'s' * (len(i['runs']) != 1)}" if i["runs"] else "") + (f" · job {job} is running" if job else ""),
            *(["CARD", *["  " + ln for ln in card_md.splitlines() if ln.strip()]] if card_md else ["NO CARD on file"]),
            *(["ROUNDS", *[f"  round {x['round']} · random bar {100 * x['bar']:g} % · store {x['store']} · "
                           + ("no result on file" if x["passed"] is None else "every line that applies passes" if x["passed"] else "fails " + ", ".join(x["failed"] or []))
                           + f" · reason: {x['reason']}" for x in rounds]] if rounds else []),
            *([f"FROZEN · lock {lock.get('hash')} of {lock.get('locked_utc')} · round {lock.get('round')} · default variant {lock.get('default')} · test range "
               f"{home.get('market')} {rng.get('start')} .. {rng.get('end')}"] if lock else []),
            *([f"TEST DAYS READ · {read.get('state')} {read.get('utc') or ''}".rstrip() + (f" · {read['verdict']}" if read.get("verdict") else "")] if read else []),
            *(["EARLY LOOK (no verdict of the law: the status does not read it)", *["  " + str(x.get("text")) for x in early.get("lines") or [] if isinstance(x, dict)]]
              if early else []),
            *(["LATEST VERDICT", *["  " + x["text"] for x in rows]] if rows else []),
            *([f"TESTER RUNS: {', '.join(i['runs'])}"] if i["runs"] else [])]
    return api.result("status", name, status=i["status"], phase=i["phase"], round=i["round"], lines=rows, text="\n".join(text),
                      next=_step(name, i["status"], _last(name, root), root),
                      record={"idea": i, "card": card_md, "spec": _json(d / "spec.json"), "check": _json(d / "check.json"), "rounds": rounds, "job": job,
                              "lock": None if lock is None else {k: lock.get(k) for k in ("hash", "version", "round", "locked_utc", "default", "test_range")},
                              "read": read,
                              "early_look": None if early is None else {k: early.get(k) for k in ("verdict", "label", "held", "failed", "lock", "range", "build_failed")},
                              "log": [json.loads(x) for x in (d / "log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()] if (d / "log.jsonl").is_file() else []})
