"""api.py -- the toolkit's commands as functions. Every command returns ONE JSON-ready object in the shape the toolkit and the
connector agreed on (toolkit plan, section 8); cli.py prints it, or its `text`. Built so far (plan step 2): build_stored.

  {"ok", "command", "name", "status", "phase", "round", "lines": [{"line", "passed", "number", "need", "text"}], "text", "next",
   "job", "saved", "error"}         ok false = refused, `error` says why · passed null = the line does not apply
"""
from __future__ import annotations

from . import lines as L
from . import rules as R
from . import tables as T

DRY = "DRY RUN on the old build days"
PHASE = {"card": 0, "code-check": 1, "build": 2, "lock": 3, "test": 4, "sim": 5, "eval-card": 6}      # plan section 4


def result(command: str, name=None, **more) -> dict:
    """The one object of a command (plan section 8), with what the command adds to it in `more`."""
    return {"ok": True, "command": command, "name": name, "status": None, "phase": PHASE.get(command), "round": None, "lines": [],
            "text": "", "next": "", "job": None, "saved": [], "error": None, **more}


def refused(command, why: str, name=None) -> dict:
    """A refusal: nothing was run or written; `error` says why."""
    return result(command, name, ok=False, error=why, text=f"REFUSED: {why}")


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
