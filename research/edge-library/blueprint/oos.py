"""oos.py -- THE OUT-OF-SAMPLE TEST (BLUEPRINT.md phase 4; `bp.py test <name> --confirm [--wait=S] [--second-look]`; toolkit
plan, step 8). The test days -- 2025-07-01 to the home market's last complete session, as the idea's lock froze them -- are
READ ONCE, for a frozen idea, and the read is written to the app's one-read log BEFORE anything of those days is opened.

REFUSED (exit 2; nothing is run, nothing is written, no read is used), in this order:
  not frozen                    no lock.json: the freeze comes first (bp.py lock)
  the lock no longer matches    its own hash, the card on file, the engine or family code, a build store (freeze.verify)
  --confirm is missing          the owner has to have said so: a read cannot be taken back
  a job of the idea is running
  a read is on file             for the idea itself (ideastore.read_on_file) -- or for a SAME-IDEA RELATIVE (reads.used: the
                                same entry trigger, market and session, or default variants that take the same side on 70 %
                                of 30 shared days; the judge's check) -- or the idea is one of the OLD SAVED STRATEGIES, whose
                                test days were read before the blueprint (the old read logs; `bp.py seed-reads`)
  --second-look without a read  nothing is used: it would be the FIRST read, and it is not labelled as a second
  what the runner refuses before a pass (the no-start window, the ledger's cap, another run in the folder, a store of
  the read already on disk)
--second-look is THE ONLY WAY PAST A USED READ of a relative (never past the idea's own read of the same lock), and the
verdict is then labelled SECOND LOOK everywhere: on every line, in the text, in test.json, in the one-read log, on the
tester run. A second look says less than a first read (BLUEPRINT.md section 12).
`relatives_ok` (start, test: a keyword of the code, NOT of `bp.py test` and not of the chat tool -- by hand the rule holds) is
THE PIPELINE'S: every pipeline idea gets its own read of the test days (the owner, 2026-10-08; pipeline.json
test.one_read_a_slot). With it the read of a RELATIVE does not refuse, and nothing else changes: the idea's OWN read on file
refuses as ever, the lock has to match, --confirm is asked, the read is claimed first. It is no second look and is not
labelled as one. What was waived is never silent: the claim's line in the one-read log, test.json and the result carry
`relatives` -- [{name, kind, utc, verdict}] of every relative with a read (an empty list: none) -- and the text says so in
one line. Without the keyword there is no such key.

THE ORDER OF WORK
  start()   every refusal above; then THE READ IS CLAIMED (ideastore.claim_read: state "claimed"; of two claims at the same
            moment one is refused) -- the last thing before anything runs.
  run()     runner.run_test (the one caller of the engine's switch for the test days; it looks the claim up again): the
            locked variants, their 10-seed random control and the worse-fills table on the test days. Then lines 4.1-4.9
            (lines.TEST, on tables.tested), test.json through the app's idea store with EVERY line 4.x in it, the read
            marked "judged" with its verdict, the default variant's test trades as a tester run (records.imported: the
            same path the build uses), and the app's copies: PROVEN ON HISTORY, or shelved.
A RUN THAT FAILS after the claim -- a refusal inside the pass, a crash, a killed job -- leaves the read ON FILE as claimed,
and a second `test` is refused: the days are read once. That is said in the error.
A FAIL IS FINAL: NOT PROVEN is not re-tuned and re-tested on this period (BLUEPRINT.md phase 4).

4.1  Jul-Dec 2025 and Jan-Sep 2026 each: the average variant above $0        4.5  the average variant above $0 with worse fills
4.2  the whole test: the average AND the middle (median) variant above $0    4.6  ... and without its best 1 % of days
4.3  the average trade at the market's floor                                 4.7  ... and in 80 % of 1,000 reshuffles of whole days
4.4  above 95 % of the random tables (strict)
TEST ONLY: BP_TEST_RUN (records.TEST_RUN) may name `test_days`, `test_out`, `ledger`, `workers`, `tester`: a read of a few
named days into a temp folder that COUNTS, for the tests. It is refused for the app's own idea folder.

AN EARLY LOOK (`bp.py test <name> --confirm --early-look`; the owner's decision of 2026-10-06: "warn, then run if I say
yes"). The one exception to "no test day for an idea that is not frozen": the owner himself asks for a look at the test days
of an idea as it stands -- its build lines may fail, its code check may be missing. Without the flag NOTHING changes: an idea
that is not frozen is refused, and the refusal says the owner may ask for an early look.
  WHAT IT DOES  freeze.early freezes what is there (a lock MARKED early_look, with the build lines that failed and whether a
                code check stands); every refusal of a test applies but "not frozen" (a frozen idea is refused instead: it
                has its proper test); THE READ IS CLAIMED in the one-read log exactly as a test's, before the pass; the same
                pass, the same lines 4.1-4.9.
  WHAT IT SAYS  EARLY: on every line, on the result (early_look true, label), in the text, in the one-read log's verdict,
                on the tester run. Its verdict is "holds" or "fails ..": never the law's two.
  WHAT IT CAN NEVER DO  make the idea PROVEN ON HISTORY, or shelve it. It is saved BESIDE the idea's own files --
                <idea>/early_look/lock.json and test.json, its stores in runs_bp_early/ -- and never as the idea's lock.json
                or test.json: the app's idea store reads the status off those two and so cannot count an early look,
                whatever its lines say and whatever the build says later; the idea is not frozen by it and goes on.
  AFTERWARDS    the test days are USED for the idea: its read is on file. A proper test of it (frozen in the proper way)
                is refused as used; --second-look is the only way past, labelled so. The same early look again is refused
                for good (the same idea = the same lock: freeze.early), a changed idea's is a second look too.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import judge as J

from . import api
from . import freeze as FRZ
from . import jobs as JOBS
from . import lines as L
from . import reads as READS
from . import records as REC
from . import runner as RUN
from . import tables as T

LINES = L.TEST                                      # lines 4.1 .. 4.9, in the law's order (a test puts its own in)
MARK = "SECOND LOOK"
PROVEN, NOT_PROVEN = "PROVEN ON HISTORY", "NOT PROVEN"
EARLY = "EARLY LOOK — the test days are used for this idea"       # what everything of an early look says
EARLY_OUT = RUN.TESTS.with_name("runs_bp_early")    # the stores of an early look: never among those of THE one read (a later proper test writes there)
WAIVED = ("name", "kind", "utc", "verdict")         # what is written down of a relative whose read did not stop this one (relatives_ok)


def _keep(path: Path, data: dict) -> Path:
    """A file of an early look, whole or not at all: in the idea's folder early_look/, beside the files the app's idea
    store reads (lock.json, test.json) and never one of them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else os.fspath(o)) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _who(r: dict) -> str:
    """A relative with a read, in words."""
    return (f"the saved strategy {r['unit']}" if r["kind"] == "old" and r.get("unit") else f"the idea {r['name']}") + f" ({r['why']}; "\
        + (f"its test days were read: {r['verdict']}" if r.get("verdict") else f"its read of the test days is on file, {r.get('state')} {r.get('utc')}") + ")"


def start(name, confirm=False, second_look=False, root=None, workers=None, out=None, ledger=None, days=None, block=None, tester=None, early_look=False,
          relatives_ok=False) -> dict:
    """EVERY REFUSAL OF THE TEST, THEN THE CLAIM -> the arguments of run() (JSON: a job keeps them). Module docstring.
    out, ledger, days, block, workers = runner.run_test's; tester = the tester's base folder the default variant's run goes
    to (the app's own for the app's own idea folder). early_look = the owner's early look at an idea that is NOT frozen
    (module docstring): its lock is freeze.early's, written beside the idea's files just before the claim. relatives_ok =
    the pipeline's: the read of a relative does not refuse, and the relatives are written down (module docstring)."""
    test = REC._test_run(root)
    IS, d = api.ideastore(), REC._carded(name, root)
    lock, early = REC._json(d / "lock.json"), bool(early_look)
    cmd = f"bp.py test {name} --confirm" + " --early-look" * early
    if early:
        lock = FRZ.early(name, root, test.get("out"), test.get("draws"))        # what is there, frozen as it is (in memory): refused for a frozen idea, or without a build
    elif lock is None:
        raise J.Refuse(f"{name} is not frozen (no lock.json): the freeze comes before the test, and nothing may change after it (bp.py lock {name}). The owner "
                       f"may ask for an EARLY LOOK instead ({cmd} --early-look): it reads the test days for the idea as it stands, uses them up for it, and "
                       "can never prove it")
    else:
        bad = FRZ.verify(lock, REC._json(d / "spec.json"))
        if bad:
            raise J.Refuse(f"the lock of {name} ({lock.get('hash')}) no longer matches the files on disk: {'; '.join(bad)}. Nothing changes after the freeze: "
                           "put the files back, or build the changed rule as a new version")
    if confirm is not True:
        raise J.Refuse(f"the test days are read ONCE for an idea, and a read cannot be taken back: run it only when the owner has said to, with --confirm ({cmd})")
    job = JOBS.running(name, root)
    if job:
        raise J.Refuse(f"a job of {name} is still running ({job}): bp.py job {job} picks its wait back up -- nothing is read again")
    h, look, waive = lock["home"], bool(second_look), relatives_ok is True
    rng = {k: lock["test_range"][h["market"]][k] for k in ("start", "end")}
    use = READS.used(name, lock, root)
    own, rel = use["own"], use["relatives"]
    if own:
        same = (own.get("version"), own.get("lock")) == (lock["version"], lock["hash"])
        if same or not look:
            raise J.Refuse(f"a read of the test days is already on file for {name} ({own.get('state')}, {own.get('utc')}"
                           + (f": {own['verdict']}" if own.get("verdict") else ": the run did not finish, and the read stays on file") + "): the test days are "
                           "read once" + (", and a fail is final" if own.get("verdict") and NOT_PROVEN in str(own["verdict"]) else "")
                           + (" -- a second look is never a second read of the same lock" if look else "")
                           + ("" if same or look else f" -- that read was of another lock of {name} (an early look, or an earlier version): the only way past it "
                              f"is an explicit second look ({cmd} --second-look), and its verdict is labelled {MARK} everywhere"))
    if rel and not (look or waive):
        old = [r for r in rel if r["kind"] == "old"]
        raise J.Refuse((f"{name} is one of the old saved strategies whose history is used: it is the same idea as " if old else
                        f"a read of the test days is on file for a same-idea relative of {name}: ")
                       + "; ".join(_who(r) for r in [*old, *(r for r in rel if r["kind"] != "old")])
                       + f". For {name} the test days are not unseen. The only way past a used read is an explicit second look ({cmd} "
                       f"--second-look), and its verdict is labelled {MARK} everywhere")
    if look and not (own or rel):
        raise J.Refuse(f"--second-look: no read of the test days is on file for {name} or for a relative of it -- this would be the FIRST read, and a first "
                       "read is not labelled as a second: run it without the flag")
    days, out = (days or test.get("test_days")), (out or test.get("test_out") or (str(EARLY_OUT) if early else None))
    ledger, workers, tester = ledger or test.get("ledger"), workers or test.get("workers"), tester or test.get("tester")
    sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
    read = {"version": lock["version"], "lock": lock["hash"]}
    pre = RUN.run_test(name, read, sp, h["key"], h["session"], lock["variants"], lock["store"], rng["end"], workers, out, ideas=root, ledger=ledger, days=days,
                       block=block, dry=True)
    there = [s["key"] for s in pre["stores"] if s["skipped"]]
    if there:
        raise J.Refuse(f"{', '.join(there)}: a store of this lock's read is on disk, and no read of {name} is in the one-read log -- the test days WERE read "
                       "for it; the log has to say so before anything else happens")
    if early:                                       # an early look's lock: on file before its read is claimed, and never the idea's lock.json
        _keep(d / api.EARLY_LOOK / "lock.json", lock)
    said = {"relatives": [{k: r.get(k) for k in WAIVED} for r in rel]} if waive else {}        # the relatives whose reads did not stop this one: never silent
    try:                                            # ---- THE CLAIM: the read is in the log before anything of the test days is opened
        line = IS.claim_read(name, version=lock["version"], lock=lock["hash"], rng=rng, second_look=look, root=root, **said)
    except IS.ReadOnFile as e:
        raise J.Refuse(str(e)) from None
    IS.append_log(name, "test_claimed", root, lock=lock["hash"], range=rng, second_look=look, **({api.EARLY_LOOK: True} if early else {}))
    return {"idea": name, "read": {**read, "utc": line.get("utc")}, "rng": rng, "second_look": look, "second_of": [r["name"] for r in rel] if look else [], **said,
            "root": None if root is None else str(root), "workers": workers, "out": None if out is None else str(out),
            "ledger": None if ledger is None else str(ledger), "days": days, "block": block, "tester": None if tester is None else str(tester),
            "test": bool(test), "early_look": early}


def _show(name: str, lock: dict, trades: list, t: dict, rng: dict, marks: list, root, tester) -> dict:
    """THE DEFAULT VARIANT'S TEST TRADES IN THE APP: the rows the read's own pass kept (a store keeps no prices), held against
    the store (the same number of trades, the same net) and written as a finished run of the tester under the idea's Lab
    draft (records.imported), named by what the read was (`marks`: a second look, an early look). A mirror, never a gate:
    what could not be shown is said in `note`."""
    h, cell = lock["home"], lock["default"]
    out = {"cell": cell, "trades": len(trades), "run_id": None, "note": None}
    short = ", ".join(m.split(" — ")[0] for m in marks)                    # (a run's name is short: the label's first words)
    try:
        x = J.cellx(t["_st"], cell, h["session"], t["_u"])
        if len(trades) != len(x["net"]) or abs(sum(r["net"] for r in trades) - float(x["net"].sum())) >= 0.01:
            raise J.Refuse(f"the pass kept {len(trades):,} trades of {cell} where its store has {len(x['net']):,} (or another net)")
        a, b = (t["calendar"][0], t["calendar"][-1]) if t["calendar"] else (rng["start"], rng["end"])
        out["run_id"] = REC.imported(
            name, trades, h["market"], f"{name} TEST{' (' + short + ')' if short else ''}: {cell} ({h['market']} {h['session']} {h['bar']}m)", a, b, len(t["calendar"]),
            f"blueprint out-of-sample test of {name} (lock {lock['hash']}{''.join(', ' + m for m in marks)}): the default variant {cell} on the test days "
            f"{rng['start']} .. {rng['end']} (home {h['market']} {h['session']}, {h['bar']}-minute bars; 1 contract after costs)", root, tester)
    except (J.Refuse, ValueError, OSError, subprocess.SubprocessError) as e:
        out["note"] = f"not shown on the tester page: {e}"
    return out


def run(idea, read, rng, second_look=False, second_of=None, root=None, workers=None, out=None, ledger=None, days=None, block=None, tester=None, test=False,
        early_look=False, progress=None, relatives=None) -> dict:
    """THE READ ITSELF, with what start() returned (module docstring) -> the result: every line 4.1-4.9 as pass or fail with
    its number, the verdict, the status. Beyond the agreed keys: verdict, passed, failed, second_look, label,
    second_look_of, lock, version, range, home, unit, days, table, stores, default, read, notes, dry_run (false: a read
    counts), lab. Raises J.Refuse when the pass does not come through: the read stays on file, and the error says so.
    AN EARLY LOOK (early_look; module docstring) is the same pass on the lock freeze.early made. Its result adds early_look
    true, held (did the seven lines hold), build_failed and code_check (off its lock); `label` and every line say EARLY;
    `passed` is false whatever the lines say, the verdict is no verdict of the law, and the status is the one the saved
    results gave before it. It is saved as <idea>/early_look/test.json -- never the idea's test.json.
    relatives = what start() wrote down under `relatives_ok` (a list, or None: the read was not made under it): the result
    and test.json carry it as `relatives`, and one line of the text names them when there are any."""
    IS, name, look, early = api.ideastore(), idea, bool(second_look), bool(early_look)
    d = IS.idea_dir(name, root)
    lock = REC._json(d / api.EARLY_LOOK / "lock.json" if early else d / "lock.json")
    if lock is None or lock.get("hash") != read.get("lock") or bool(lock.get(api.EARLY_LOOK)) != early:
        raise J.Refuse(f"the {'early-look lock' if early else 'lock'} of {name} on file is not the one this read was claimed for ({read.get('lock')})")
    h = lock["home"]
    try:
        sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
        got = RUN.run_test(name, read, sp, h["key"], h["session"], lock["variants"], lock["store"], rng["end"], workers, out, ideas=root, ledger=ledger, days=days,
                           block=block, progress=progress, keep=[lock["default"]])
        t = T.tested(sp, lock, out)
        rows = [f(t) for f in LINES]
    except api.REFUSALS as e:
        IS.append_log(name, "test_did_not_finish", root, lock=lock["hash"], error=str(e))
        raise J.Refuse(f"{e} -- THE READ STAYS ON FILE (claimed {read.get('utc')}): the test days are read once, and bp.py test {name} is refused from "
                       "here on") from None
    except BaseException as e:
        IS.append_log(name, "test_did_not_finish", root, lock=lock["hash"], error=f"{type(e).__name__}: {e}")
        raise
    marks = [m for m, on in ((MARK, look), (EARLY, early)) if on]
    if marks:
        rows = [{**x, "text": x["text"] + "".join(f" [{m}]" for m in marks), **({"second_look": True} if look else {}), **({api.EARLY_LOOK: True} if early else {})}
                for x in rows]
    failed = [x["line"] for x in rows if x["passed"] is not True]
    if early:                                       # NO VERDICT OF THE LAW: an early look passes nothing, fails nothing and moves no status
        verdict, status = f"{EARLY}: " + ("every line 4.1-4.9 holds" if not failed else f"fails {', '.join(failed)}"), IS.status(name, root)
    else:
        verdict, status = (PROVEN, "proven_on_history") if not failed else (NOT_PROVEN, "shelved")
    label, cal = (f"{MARK}: {verdict}" if look else verdict), t["calendar"]
    r = api.result("test", name, status=status, round=lock["round"], lines=rows, verdict=label, passed=not failed and not early, failed=failed, second_look=look,
                   label=" · ".join(marks) or None, second_look_of=list(second_of or []), lock=lock["hash"], version=lock["version"], range=rng, home=h["table"],
                   unit=t["unit"], dry_run=False,
                   days={"start": rng["start"], "end": rng["end"], "sessions": len(cal), "named": list(days) if days else None,
                         "parts": [{"name": p["name"], "start": p["start"], "end": p["end"], "sessions": int(p["days"].sum())} for p in t["parts"]]},
                   table={"store": t["store"], "variants": len(t["ids"])}, stores=got["stores"], read={**read, "state": "judged", "verdict": label},
                   default={"cell": lock["default"], "trades": None, "run_id": None, "note": None})
    if early:
        r.update({api.EARLY_LOOK: True, "held": not failed, "build_failed": lock["build_failed"], "code_check": lock["code_check"]})
    if test:
        r["test_run"] = True
    if relatives is not None:
        r["relatives"] = [dict(x) for x in relatives]
    sides = (lock.get("plan") or {}).get("sides") or "both"
    r["notes"] = ([f"a {sides}-only idea is read against random entries of BOTH sides (its pool holds no one-sided table): for line 4.4 that is a tilted control"]
                  if sides != "both" else [])
    head = ([f"{MARK}: not a first read of the test days -- a read was on file for " + ", ".join(second_of or [name]) + ". It says less than a first read."]
            if look else [])
    if early:
        bf, n = lock["build_failed"], lock["round"]
        why = "; ".join(x for x in ((f"build line{'s' * (len(bf) != 1)} {', '.join(bf)} failed in round {n}" if bf else
                                     f"every build line of round {n} passed, and it was never frozen (bp.py lock)"),
                                    "no code check stands for its home store" if lock["code_check"]["missing"] else "") if x)
        head = [f"{EARLY}. NOT the law's test: {name} is not frozen -- {why}. An early look can never prove an idea.", *head]
    text = [*head,
            (f"TEST RUN on {len(days)} named days of the test range ({rng['start']} .. {rng['end']}): it counts only because {REC.TEST_RUN} is set." if test and days
             else f"OUT-OF-SAMPLE TEST {rng['start']} .. {rng['end']} ({len(cal):,} session days), ONE read: logged {read.get('utc')}, before the pass."),
            f"{name} · {'early-look lock' if early else 'lock'} {lock['hash']} · version {lock['version']} · home {REC._nice(h)} · {len(t['ids'])} locked variants · "
            f"store {t['store']}",
            *[x["text"] for x in rows],
            (f"RESULT: {label} -- no pass and no fail of the law: an early look proves nothing, and for {name} the test days are no longer unseen." if early else
             f"RESULT: {label}: " + ("every line 4.1-4.9 is true -- approved for a real eval." if not failed else
                                     f"fails {', '.join(failed)}. A FAIL IS FINAL: the idea is not re-tuned and re-tested on this period.")),
            *[f"NOTE: {x}." for x in r["notes"]],
            *([f"{len(relatives)} relative{'s' * (len(relatives) != 1)} of this idea {'was' if len(relatives) == 1 else 'were'} read on these days before it "
               f"({', '.join(str(x.get('name')) for x in relatives)}): the pipeline reads every idea."] if relatives else []),
            (f"STATUS: {status.replace('_', ' ').upper()} (as it was: an early look changes no status) · the test days are USED for {name}" if early else
             f"STATUS: {status.replace('_', ' ').upper()}{' (' + MARK + ')' if look else ''} · phase 4")]
    r["next"] = (f"{MARK}: " if look else "") + (
        f"{EARLY}: {name} goes on where its build stands, and its test days are no longer unseen -- a proper test of it (frozen first: bp.py lock {name}) can "
        f"only be a {MARK}, the one way past a used read (bp.py test {name} --confirm --second-look)" if early else
        f"Proven on history: before an eval is bought the prop simulator reads the test-period trades for the account in question (bp.py sim {name} "
        "--account=<rule set> --attempts=N --fee-budget=USD: the owner's numbers)" if not failed else
        f"NOT PROVEN, and a fail is final: {name} is SHELVED -- it is not re-tuned and re-tested on this period; only new unseen days or real fills can change that")
    file = d / api.EARLY_LOOK / "test.json" if early else d / "test.json"      # an early look: beside the idea's files, where no status is read
    saved = [s["path"] for s in got["stores"] if not s["skipped"]] + [str(file), *([str(file.with_name("lock.json"))] if early else []),
                                                                      str(IS.ideas_root(root) / IS.READS_FILE)]
    r.update(saved=saved, text="\n".join(text))
    keep = (lambda: _keep(file, r)) if early else (lambda: IS.write_test(name, r, root))
    keep()                                          # THE VERDICT IS ON FILE: every line 4.1-4.9 is in it ...
    IS.log_read(name, version=lock["version"], lock=lock["hash"], rng=rng, state="judged", verdict=label, root=root)      # ... and the read is judged
    IS.append_log(name, "tested", root, lock=lock["hash"], verdict=label, failed=failed, **({api.EARLY_LOOK: True} if early else {}))
    r["default"] = _show(name, lock, got["trades"].get(lock["default"], []), t, rng, marks, root, tester)
    text.append(f"DEFAULT VARIANT {lock['default']}: its {r['default']['trades']:,} trades of the test days -> tester run {r['default']['run_id']}"
                if r["default"]["run_id"] else f"DEFAULT VARIANT {lock['default']}: {r['default']['note']}")
    r["text"] = "\n".join(text)
    keep()                                          # (once more, with the run its trades can be looked at in)
    r["lab"], said, idea = REC._lab(name, root)
    if idea["status"] != r["status"]:               # the app's reading of what is saved is the status: never passed over
        said.append(f"NOTE: the app reads the saved results as {idea['status'].upper()}.")
        r["status"] = idea["status"]
    r["text"] = "\n".join([*text, *said])
    return r


def test(name, confirm=False, second_look=False, root=None, **kw) -> dict:
    """`bp.py test <name> --confirm [--early-look]` in the foreground: start(), then run(). kw = start()'s other arguments
    (relatives_ok among them: the pipeline's, never the command line's)."""
    return run(**start(name, confirm, second_look, root, **kw))
