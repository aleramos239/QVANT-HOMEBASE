"""api.py -- the toolkit's commands as functions. Every command returns ONE JSON-ready object in the shape the toolkit and the
connector agreed on (toolkit plan, section 8); cli.py prints it, or its `text`.

  {"ok", "command", "name", "status", "phase", "round", "lines": [{"line", "passed", "number", "need", "text"}], "text", "next",
   "job", "saved", "error"}         ok false = refused, `error` says why · passed null = the line does not apply

  build_stored(unit)        phase 2 as a DRY RUN on the old build days, for a unit whose stores are on disk (plan step 2)
  build(spec, reason, ...)  phase 2 on the build range for ONE table of a spec in run_idea's format that has no record
                            (`--spec-file`): runs what is missing (runner.run_build), then lines 2.1-2.9          (step 4)
  pools(roots, tfs)         the random-entry control pools of the build range, alone
  code_check(name, ...)     phase 1: lines 1.1-1.6 on a store or a trades file (checks.py); saved as the idea's check.json
                            when the app has the idea on file (homebase/ideastore.py), only printed when it has not
THE IDEA'S RECORD -- the card (phase 0), the build of an idea with its counted rounds, the status -- is records.py (plan
steps 5 and 6): `bp.py card`, `bp.py build <name> --reason=...`, `bp.py status`.
`name` is the IDEA's name, as the connector passes it and as the app files it. A result marked `dry_run` (a dry run on
stored units, a smoke run on named days) never counts as a verdict: the idea store reads that field.
The later phases are modules of their own: the freeze and the one read (plan step 8), propodds.py = `bp.py sim` (phase 5,
step 9), evalcard.py = `bp.py eval-card` (phase 6, step 10); blocklist.py = `bp.py blocks`. quick.py = `bp.py heatmap` and
`bp.py mc`, two read-only views of a built idea. THE DEFAULT ROUTE OF A NEW IDEA since 2026-10-20 (hmwf.py, the owner): wf_run = every
hm40 box on the 3:1 in-sample months (`bp.py wf run`, only on the owner's words), wf_show, wf_pick = the owner's box, wf_oos = its test
months (`bp.py wf oos`, only on his words). An EARLY LOOK at the test days (`bp.py test <name> --confirm --early-look`:
oos.py) is kept in the idea's folder EARLY_LOOK, beside its own files and never as one of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import judge as J
import l2sim as S
import library as LB

from . import checks as CH
from . import lines as L
from . import rules as R
from . import runner as RUN
from . import tables as T

DRY = "DRY RUN on the old build days"
PHASE = {"card": 0, "code-check": 1, "build": 2, "pools": 2, "lock": 3, "test": 4, "sim": 5, "portfolio": 5, "eval-card": 6,      # plan section 4
         "heatmap": 2, "mc": 2,                     # the two views read a build (mc --on=test: a test, and says phase 4)
         "wf run": 2, "wf show": 2, "wf pick": 3, "wf oos": 4}      # the 3:1 walk-forward of every hm40 box (hmwf.py): the default since 2026-10-20
EARLY_LOOK = "early_look"                           # <idea>/early_look/{lock.json, test.json}: an early look's files, and the field that marks them
REFUSALS = (J.Refuse, R.RuleError, LB.CapExceeded, S.HoldoutSealed)       # what a command answers with `ok` false, exit 2


def result(command: str, name=None, **more) -> dict:
    """The one object of a command (plan section 8), with what the command adds to it in `more`."""
    return {"ok": True, "command": command, "name": name, "status": None, "phase": PHASE.get(command), "round": None, "lines": [],
            "text": "", "next": "", "job": None, "saved": [], "error": None, **more}


def refused(command, why: str, name=None) -> dict:
    """A refusal: nothing was run or written; `error` says why."""
    return result(command, name, ok=False, error=why, text=f"REFUSED: {why}")


def ideastore():
    """homebase/ideastore.py: the app's idea folders (one per idea; standard library only), imported from the repo by its
    path. The toolkit saves a phase's result there and reads nothing else of the app. No bytecode is written into homebase/
    (read-only for the toolkit). Where the ideas are: its ideas_root (an argument, HOMEBASE_IDEAS_ROOT, ~/.homebase/ideas)."""
    sys.dont_write_bytecode = True
    if str(S.REPO) not in sys.path:
        sys.path.append(str(S.REPO))
    from homebase import ideastore as store
    return store


# ================================================================ phase 2: the dry run on stored units

def build_stored(x: str, round_: int = 1) -> dict:
    """`bp.py build --stored <unit>`: lines 2.1 to 2.8 for ONE unit whose stores are on disk, each as pass or fail with its
    number. READ-ONLY and a DRY RUN: the stores hold the OLD build days (2021-09-22 .. 2023-12-31, 27 of the build's 45
    months), so this is never a blueprint verdict and nothing is saved (`status` and `round` stay null). On those days:
      2.3  the random tables are the judge's, from every seed on disk (2 for most units): fewer than 10 = THIN (`thin`)
      2.4  is read against 200 and also "on pace" (120 on 27 months); `failed_on_pace` = the failed lines with 2.4 read so
      2.5  the neighbors are the idea's other stored tables (same family and market)
      2.9  the rounds are not counted; 2.3 is held against the bar of round `round_`
    Beyond the agreed keys: dry_run, label, uid, days, table, failed, failed_on_pace, not_applicable, thin, passed,
    passed_on_pace. Raises judge.Refuse: no store, no judged variant, a store outside the stored build days."""
    t = T.controls(T.stored(x))
    t["round"], t["neighbors"] = round_, T.neighbors(t["_u"])
    rows, rg = [f(t) for f in L.BUILD], R.template("ranges")
    failed = [r["line"] for r in rows if r["passed"] is False]
    paced = [r["line"] for r in rows if r["passed"] is False and not r.get("on_pace", {}).get("passed")]
    r = result("build", t["unit"], lines=rows, dry_run=True, label=DRY, uid=t["uid"],
               next="A dry run saves nothing and is no verdict: a build that counts needs the idea's card and its tables on "
                    f"the build days {rg['build']['start']} .. {rg['build']['end']}.",
               days={**{k: rg["stored_build"][k] for k in ("start", "end", "months")}, "sessions": len(t["days"]),
                     "build_months": rg["build"]["months"]},
               table={"store": t["store"], "variants": len(t["ids"]), "dead": t["dead"], "duplicates": t["dup"]},
               failed=failed, failed_on_pace=paced, not_applicable=[r["line"] for r in rows if r["passed"] is None],
               thin=[r["line"] for r in rows if r.get("thin")], passed=not failed, passed_on_pace=not paced)
    r["text"] = _text(r)
    return r


def _text(r: dict) -> str:
    """A dry build as a person reads it: the label, the unit, one line per blueprint line, the result."""
    d, tb, said = r["days"], r["table"], lambda f: "fails " + ", ".join(f) if f else "every line that applies passes"  # noqa: E731
    out = [f"{r['label']} ({d['start']} .. {d['end']}: {d['months']} of the build's {d['build_months']} months). Not a blueprint verdict.",
           f"{r['name']} · {tb['variants']} variants · {d['sessions']} session days · store {tb['store']}"]
    out += [x["text"] for x in r["lines"]]
    res = "RESULT of the dry run: " + said(r["failed"])
    if r["failed"] != r["failed_on_pace"]:
        res += f"; with 2.4 read on pace: {said(r['failed_on_pace'])}"
    if r["thin"]:
        res += f". THIN (too few random-entry seeds): {', '.join(r['thin'])}"
    return "\n".join(out + [res + ". Line 2.9 (the rounds) is not counted in a dry run."])


# ================================================================ phase 2: the build range

def headline(d: dict) -> str:
    """The first line of a build: the range it was read on -- or, for a run on named days, that it is no verdict."""
    rng = f"{d['start']} .. {d['end']}"
    return (f"SMOKE RUN on {len(d['named'])} named days of the build range ({rng}): never a blueprint verdict." if d["named"] else
            f"BUILD {rng} ({d['months']} months, {d['sessions']:,} session days).")


def build(spec, name=None, reason: str = "", home=None, filt=None, round_: int = 1, workers=None, out=None, ledger=None, days=None, cells=None,
          block=None, progress=None, dry: bool = False) -> dict:
    """`bp.py build <name> --reason=... --spec-file=PATH`: PHASE 2 ON THE BUILD RANGE (2021-09-22 .. 2025-06-30) FOR ONE
    TABLE of a spec that has no record. (An idea on file is built by records.build: its card names the tables, its folder
    counts the rounds and keeps the results; nothing of that is read or written here, and no round is counted.) Runs what
    is missing of the spec's stores (runner.run_build: its table, its filter tables, the 10-seed control pool; a rerun
    does no work), then reads lines 2.1 to 2.9 for ONE table, each as pass or fail with its number -- lines 2.1-2.8 with
    the line functions of the dry run, the random tables drawn by the judge's own functions from the pool's 10 seeds
    (tables.built).
      spec     the idea's settings in the format of run_idea.py: a dict, or the path of its JSON file
      name     the idea (default: the spec's name; a later round's spec may be named <name>_<round>: its stores are its own)
      reason   why this round is run, written before the run: line 2.9. No reason = refused
      home     the table that is judged: <ROOT>-tf<tf>-<session> (default: the spec's first market, bar size and session);
               the spec's other tables are its neighbors (2.5)
      filt     <block>_<side>: judge the table with that ONE filter of the spec on, against the plain table (2.7)
      round_   1 .. 5: the bar of line 2.3 (said here: only an idea's record counts its rounds)
      workers, out, ledger, days, cells, block, progress    runner.run_build's (days + cells = a smoke run)
      dry      every refusal that needs no run, then stop: what a job is checked with before it is started
    Beyond the agreed keys: unit, home, filter, spec, reason, days, table, stores, failed, not_applicable, thin, passed,
    smoke, dry_run (true for a smoke run: it never counts). Refused: the runner's refusals; a home or filter that is not
    the spec's; a round the law does not have; no reason; a strategy error in a pass (no store was written)."""
    sp = RUN.checked(spec)
    name = name or sp["name"]
    if not sp["name"].startswith(name):
        raise J.Refuse(f"the settings are {sp['name']}'s, not {name}'s: a spec carries its idea's name (a later round: <name>_<round>)")
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise J.Refuse("no reason: every round has its reason written before the run (line 2.9): --reason=\"why this round is run\"")
    root, tf, sess, label = T.home_of(sp, home)
    T.filter_of(sp, filt)
    R.need("2.3", round_)                           # a round the law does not have is refused before anything runs
    stores = RUN.run_build(sp, workers, out, ledger=ledger, days=days, cells=cells, progress=progress, block=block, dry=dry)
    here = f"{root}-tf{tf}-{sess}" + (f":{label}" if label else "")
    if dry:
        return result("build", name, round=round_, stores=stores, home=here, filter=filt, spec=sp["name"], reason=reason, dry_run=True)
    bad = [s for s in stores if not s["ok"]]
    if bad:
        raise J.Refuse(f"{bad[0]['key']}: sessions were dropped by a strategy error ({bad[0]['error']}): no store was written; the family has to be fixed first")
    t = T.built(sp, home, filt, out, days, round_)
    t["reason"] = reason
    rows, rg = [f(t) for f in (*L.BUILD, L.rounds)], R.template("ranges")["build"]
    failed = [x["line"] for x in rows if x["passed"] is False]
    r = result("build", name, round=round_, lines=rows, saved=[s["path"] for s in stores if not s["skipped"]], unit=t["unit"], home=here, filter=filt,
               spec=sp["name"], reason=reason, smoke=bool(days), dry_run=bool(days),
               days={"start": rg["start"], "end": rg["end"], "months": rg["months"], "sessions": len(t["days"]), "named": list(days) if days else None},
               table={"store": t["store"], "variants": len(t["ids"]), "dead": t["dead"], "duplicates": t["dup"]}, stores=stores, failed=failed,
               not_applicable=[x["line"] for x in rows if x["passed"] is None], thin=[x["line"] for x in rows if x.get("thin")], passed=not failed)
    said = ("fails " + ", ".join(failed)) if failed else "every line that applies passes"
    old = [s["key"] for s in stores if s.get("code_same") is False]
    r["text"] = "\n".join(
        [headline(r["days"]), f"{t['unit']} · round {round_} · {len(t['ids'])} variants · {len(t['days']):,} session days · store {t['store']}"]
        + [x["text"] for x in rows] + [f"RESULT{' of the smoke run' if days else ''}: {said}."]
        + ([f"NOTE: {', '.join(old)} {'was' if len(old) == 1 else 'were'} written by other code than today's: after a change to the code the earlier trade "
            "list is reproduced exactly before a new run counts (line 1.6: bp.py code-check <name> --store=<a fresh run> --same-as=<the store>)."] if old else []))
    r["next"] = ("A smoke run is no verdict: run the build on the whole range (no --days)." if days else
                 "Every build line that applies passes: the idea is a LEAD; the freeze is next (bp.py lock: an idea on file, with its card and its code check)." if not failed else
                 f"Fails {', '.join(failed)}: write the next round's reason (at most {R.need('2.9')} rounds, the bar of 2.3 rises each round) or shelve the idea.")
    return r


def pools(roots, tfs, workers=None, out=None, ledger=None, days=None, cells=None, block=None, progress=None) -> dict:
    """`bp.py pools`: the random-entry control pools of the build range for the markets x bar sizes named, one tape pass
    each (runner.run_pools). A pool that is stored is skipped; a build would run a missing one by itself, in its own pass."""
    stores = RUN.run_pools(roots, tfs, workers, out, ledger=ledger, days=days, cells=cells, progress=progress, block=block)
    r = result("pools", None, saved=[s["path"] for s in stores if not s["skipped"]], stores=stores, smoke=bool(days), dry_run=bool(days))
    r["text"] = "\n".join(f"{s['key']}: {'already stored' if s['skipped'] else 'stored' if s['ok'] else 'NOT stored (a strategy error)'} "
                          f"({s['cells']} cells, {s['trades']:,} trades)" for s in stores)
    r["next"] = "The pools are what every later build of these markets and bar sizes is held against (line 2.3); they are never run twice."
    return r


# ================================================================ phase 1: the code check

def code_check(name: str, store=None, trades=None, run_id=None, same_as=None, looked: bool = False, cell=None, market=None, sessions=None, window=None,
               max_per_day=None, root=None, out=None) -> dict:
    """`bp.py code-check <name> [--store=K | --trades=FILE] [--looked]`: PHASE 1, lines 1.1 to 1.6 (checks.py) on a store
    of the research engine (its key in the store folder `out`, or its path) or on a plain trades file.
      same_as      the earlier store or file line 1.6 holds the list against (after a change to the code)
      looked       the owner looked at the 10 trades line 1.5 named, and each sits where the rule says
      cell         the store's cell those 10 trades are taken from (default: its first cell with 10 trades)
      market, sessions, window, max_per_day     what a trades file does not state itself (a store states its own)
    THE IDEA'S RECORD. When the app has the idea on file (homebase/ideastore.py, idea folder `root`), the result is saved as
    its check.json; an idea that is not on file is only printed. `asked` = the source and what was stated: with no source
    named, the one of the idea's check on file is read again -- so the owner's later `--looked` needs nothing repeated.
    Beyond the agreed keys: source, asked, look (the 10 trades), failed, not_applicable, passed. passed = lines 1.1-1.5
    all TRUE and 1.6 not failed (1.6 waits for a change to the code; a line that cannot be read is not a pass).
    Refused: any day on or after 2025-07-01 (checks.seal, runner.guard); no source; a tester run id (not built yet).
    A 3:1 idea: no source = its in-sample store (runs_wf/<store>/is); a trades file or an old store is refused (_wf_sources); a 3:1 store
    is read on its in-sample months only (checks.seal)."""
    given = {k: v for k, v in (("store", store), ("trades", trades), ("run_id", run_id)) if v is not None}
    if len(given) > 1:
        raise J.Refuse("give one of --store, --trades, --run-id")
    if run_id is not None:
        raise J.Refuse("--run-id: a tester run is not read yet (the import of tester runs is a later step): give --store=<store key> or --trades=<trades file>")
    asked = {k: v for k, v in (("store", store), ("trades", trades), ("same_as", same_as), ("cell", cell), ("market", market), ("sessions", sessions),
                               ("window", window), ("max_per_day", max_per_day)) if v is not None}
    file = _idea_file(name, root, "check.json")
    if not given:
        before = (_json(file) or {}).get("asked") if file else None
        if not before and wf_on_file(name):        # a 3:1 idea: its own in-sample store (the code check never reads a test month)
            from . import hmwf as H
            before = {"store": str(H.store(name) / H.IS)}
        if not before:
            raise J.Refuse(f"{name}: say what to check: --store=<store key> or --trades=<trades file> (no code check of this idea is on file to read again)")
        asked = {**before, **asked}
    if asked.get("max_per_day") is not None and int(asked["max_per_day"]) < 1:
        raise J.Refuse("--max-per-day: a whole number from 1")
    stated = {k: asked.get(k) for k in ("market", "sessions", "window", "max_per_day")}
    _wf_sources(name, root, out, asked)
    t = CH.load(asked.get("store"), asked.get("trades"), out, **stated)
    e = None if asked.get("same_as") is None else CH.load(*((asked["same_as"], None) if _is_store(asked["same_as"], out) else (None, asked["same_as"])),
                                                         out, market=stated["market"] or t["root"])
    rows = [CH.window(t), CH.one_position(t), CH.count(t), CH.payoff(t), CH.chart(t, looked, asked.get("cell")), CH.reproduced(t, e)]
    look = rows[4].pop("look")
    failed, na = [x["line"] for x in rows if x["passed"] is False], [x["line"] for x in rows if x["passed"] is None]
    passed = not failed and all(x["passed"] is True for x in rows[:5])
    asked = {**asked, **{"store" if "store" in asked else "trades": t["where"]}, **({"same_as": e["where"]} if e else {})}      # as they were found
    r = result("code-check", name, lines=rows, source={"kind": t["kind"], "where": t["where"], "market": t["root"], "lists": len(t["lists"]), "trades": len(t["net"])},
               asked=asked, look=look, failed=failed, not_applicable=na, passed=passed)
    res = ("every line is true. Phase 1 is passed." if passed and not na else
           f"every line that is read is true; {', '.join(na)} waits for a change to the code. Phase 1 is passed." if passed else
           "; ".join(x for x in (f"fails {', '.join(failed)}" if failed else "", f"not read: {', '.join(na)}" if na else "") if x)
           + ". Phase 1 is passed only when every line is true.")
    wide = max([3] + [len(str(k["trade"])) for k in look])
    r["text"] = "\n".join([f"CODE CHECK of {name}: {len(t['net']):,} trades in {len(t['lists']):,} list{'' if len(t['lists']) == 1 else 's'}, market {t['root']} ({t['where']})"]
                          + [x["text"] for x in rows]
                          + [f"  #{k['trade']:<{wide}d} {k['entry_et'] if ' ' in k['entry_et'] else k['date'] + ' ' + k['entry_et']} -> {k['exit_et']} ET  "
                             f"{k['side']:<5s}  {k['session'] or 'no session':<6s}" + (f"  ended {k['ended']}" if k["ended"] else "")
                             + (f"  (trade date {k['date']})" if " " in k["entry_et"] else "") + (f"  ({k['list']})" if t["kind"] == "store" else "") for k in look]
                          + [f"RESULT: {res}"])
    r["next"] = ("Phase 1 is passed: the numbers of this code can be trusted. The build is next (bp.py build)." if passed else
                 "Look at the 10 trades on the chart, then run the code check again with --looked." if failed == ["1.5"] and not [x for x in na if x != "1.6"] else
                 "Fix what fails, state what is not read, and run the code check again: nothing is built on numbers that are not checked.")
    if file:                                        # the idea is on file: the result is its check.json (it carries its own path)
        r["saved"] = [str(file)]
        ideastore().write_check(name, r, root)
    return r


def _wf_sources(name, root, out, asked) -> None:
    """A 3:1 idea (hmwf.route) is code-checked on 3:1 stores only (spec 4.7: nothing on the old build days): a trades file or an old
    store is refused before it is read; checks.load then seals the store to its in-sample months."""
    from . import hmwf as H
    if not H.route(name, root):
        return
    for k in ("store", "trades", "same_as"):
        v = asked.get(k)
        if v is None:
            continue
        d = CH.find(v, out)
        meta = _json(d / "run.json") if k != "trades" and d.is_dir() else None
        if (meta or {}).get("period") not in S.WF_SWITCHES:
            raise J.Refuse(f"{name} is a 3:1 idea: its code check reads its own 3:1 in-sample store only, never the old build days or a trades file "
                           f"({v}): give no source (its in-sample store) or --store=<its runs_wf store>/is")


def _idea_file(name, root, rel: str):
    """<the idea's folder>/<rel> when the app has the idea on file, else None (an idea that is not on file -- or a name
    that is no idea's -- is never given a folder here)."""
    try:
        store = ideastore()
        return store.idea_dir(name, root) / rel if store.exists(name, root) else None
    except (ValueError, ImportError):               # no idea's name; or the app's idea store is not in this checkout
        return None


def _json(path):
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_store(source, out) -> bool:
    d = CH.find(source, out)
    return (d / "run.json").exists() and (d / "cells.npz").exists()


# ================================================================ the 3:1 walk-forward of every hm40 box (hmwf.py; the owner, 2026-10-20)

def _said(owner_said) -> str:
    """The owner's words, as he said them (nothing is trimmed): refused when there are none."""
    if not isinstance(owner_said, str) or not owner_said.strip():
        raise J.Refuse("this runs only when the owner says so: --owner-said=\"<his words, word for word>\"")
    return owner_said


def wf_spec(spec, root=None) -> dict:
    """What `wf run` runs: a spec in run_idea's format (a dict) -- or the name of an idea on file: its card's home table (one market,
    one bar size, its home session)."""
    if isinstance(spec, dict):
        return spec
    from . import records as REC                    # (records imports this module)
    name = spec
    idea = REC._spec(name, REC._json(REC._carded(name, root) / "spec.json"))
    rows, plan = REC.card_lines(idea)
    if plan is None:
        raise J.Refuse(f"the card of {name} on file is not whole ({next(x['text'] for x in rows if x['passed'] is False)}): write it again (bp.py card)")
    return {**REC.engine(idea, plan, name)[0], "sessions": [plan["home"]["session"]]}


def _pct(v) -> str:
    return "  -  " if v is None else f"{100 * v:4.0f}%"


def _usd(v) -> str:
    return "-" if v is None else f"{v:,.0f}"


def _wf_text(name: str, s: dict) -> str:
    """The in-sample table (one row a box), the pick, the test months: short, for a person."""
    rows, lock, oos = s["is"], s["lock"], s["oos"]
    out = [f"3:1 IN-SAMPLE TABLE of {name}: {len(rows)} boxes, run fixed on the in-sample months only (this run opened no test month). Best win rate first.",
           "   n  box                          win    b/e  trades       net    pf  beats random"]
    for r in rows:
        pf = "-" if r["pf"] is None else f"{r['pf']:.2f}"
        out.append(f"{r['n']:4d}  {r['box']:<27s} {_pct(r['win_rate'])} {_pct(r['breakeven'])} {r['trades']:7d} {_usd(r['net']):>9s} {pf:>5s}  {_pct(r['beats_random'])}")
    out.append(f"PICKED: box {lock['box']} ({lock['at']}, {lock['who']}). It never changes." if lock else "NOT PICKED: the owner picks a box.")
    if oos is None:
        out.append("TEST MONTHS: not run.")
    elif oos.get("state"):
        out.append(f"TEST MONTHS: {oos['state']}.")
    else:
        x = oos["record"]
        out.append(f"TEST MONTHS of box {x['box']}: {x['trades']} trades, win {_pct(x['win_rate'])}, net {_usd(x['net'])}, {len(oos['blocks'])} months")
        out += [f"  {b['oos']}  {b['trades']:3d} trades  win {_pct(b['win_rate'])}  net {_usd(b['net'])}" for b in oos["blocks"]]
    return "\n".join(out)


def wf_show(name: str, command: str = "wf show") -> dict:
    """`bp.py wf show <name>`: the in-sample table, the pick, the test-month record if it was read. Runs nothing."""
    from . import hmwf as H                         # (hmwf imports this module)
    s = H.show(name)
    r = result(command, name, wf=s, text=_wf_text(name, s))
    r["next"] = (f"The owner picks a box by its number: bp.py wf pick {name} <n> (blueprint_wf_pick)." if s["lock"] is None else
                 f"The test months run only when the owner says so: bp.py wf oos {name} {s['lock']['box']} --owner-said=\"...\" (blueprint_wf_oos)."
                 if s["oos"] is None else "")
    return r


def wf_on_file(name: str) -> bool:
    """Has the idea a 3:1 in-sample table (hmwf)? (Then `bp.py heatmap <name>` shows it.)"""
    from . import hmwf as H
    return (H.RUNS / name / H.IS / "run.json").exists() or any(H.RUNS.glob(f"{name}-*-tf*/{H.IS}/run.json"))


def wf_run(spec, owner_said, workers=None, root=None, progress=None, worse: bool = True) -> dict:
    """`bp.py wf run <spec|name> --owner-said=...`: every hm40 box on the 3:1 in-sample months (hmwf.run_is: a rerun does no work, a
    changed idea under the same name is refused), then the table. Only on the owner's words."""
    from . import hmwf as H
    said, sp = _said(owner_said), wf_spec(spec, root)
    got = H.run_is(sp, workers, progress=progress, worse=worse)
    try:
        r = wf_show(sp["name"], "wf run")           # by the idea's name, as the chat tools name it
    except J.Refuse:                                # (the idea has stores on more than one market or bar size: the store's own name)
        r = wf_show(Path(got["store"]).parent.name, "wf run")
    return {**r, "owner_said": said}


def wf_pick(name: str, box, who: str = "owner") -> dict:
    """`bp.py wf pick <name> <box>`: the owner's box (its row number or id) = the lock, written once. who = who picked (the owner, or
    Claude under the owner's standing word: --who)."""
    from . import hmwf as H
    H.pick(name, box, who=who or "owner")
    return wf_show(name, "wf pick")


def wf_oos(name: str, box, owner_said, workers=None, progress=None, who: str = "owner") -> dict:
    """`bp.py wf oos <name> <box> --owner-said=...`: the test months of the picked box, once, on the owner's words (hmwf.run_oos)."""
    from . import hmwf as H
    said = _said(owner_said)
    H.run_oos(name, box, said, workers, progress=progress, who=who or "owner")
    return {**wf_show(name, "wf oos"), "owner_said": said}
