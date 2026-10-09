"""cli.py -- the command line of bp.py (toolkit plan, section 4: one command per phase; the command line = the connector tool).
The connector (homebase/claude_mcp/blueprint_tools.py) writes every command as
    <python> bp.py <command> <the idea's name> --opt=value ... --root=<ideas root> --json
in this folder; the card comes on stdin (`--spec=-`), and so do an eval's live fills (`--fills=-`). A person may leave --root
and --json out.

  bp.py card <name> --spec=- | --spec=FILE                                PHASE 0: lines 0.1-0.7 off the card ({"name", "card",
                                                                             "run"} as JSON); a whole card is saved in the app
                                                                             (card.md, spec.json, the Lab draft), a card with a
                                                                             line missing is refused with the line named
  bp.py code-check <name> [--store=KEY | --trades=FILE] [--looked]        PHASE 1: lines 1.1-1.6 on a store of the engine (its
        [--same-as=STORE|FILE] [--cell=ID] [--market=NQ] [--sessions=a,b]    key in runs_bp/, or a path such as runs/orb-NQ-tf15)
        [--window=HH:MM-HH:MM] [--max-per-day=N]                             or on a trades file; saved as the idea's check.json
                                                                             when the app has the idea; no source = the one of
                                                                             the check on file again (the owner's --looked)
  bp.py build <name> --reason=TEXT [--wait=S]                             PHASE 2, ONE ROUND of the idea on file (records.py):
        [--tester=DIR]                                                       the reason is saved, what is missing is run on the
                                                                             build range (2021-09-22 .. 2025-06-30), lines
                                                                             2.1-2.9 are read at the round's bar and saved, the
                                                                             status follows. --tester = where the tester's runs
                                                                             go (the default variant, shown in the app)
  bp.py build <name> --reason=TEXT --spec-file=PATH [--wait=S]            the ONE-TABLE build of a spec in run_idea's format
        [--home=ROOT-tfN-session] [--filter=block_side] [--round=N]          that has no record: lines 2.1-2.9 for one table;
                                                                             nothing of an idea is read or saved, no round is
                                                                             counted
  bp.py build --stored <unit>                                             DRY RUN of lines 2.1-2.8 on the OLD build days for a
                                                                             unit whose stores are on disk (read-only): an address
                                                                             (`ib-NQ-tf15-mid:mode=break`) or a uid of
                                                                             out/v2/build_units.csv (`'orb-NQ-tf15|pre|'`, `E1-A-NQ`)
  bp.py status [<name>]                                                   every idea on file, one line each -- or the full
                                                                             record of one. Runs nothing
  bp.py job <id> [--wait=S]                                               keep waiting on a build that answered "running": by
                                                                             the id alone; the answer is the build's own
  bp.py pools [--roots=NQ,ES,GC] [--tf=1,5,15,30]                         the random-entry control pools of the build range
  bp.py lock <name> [--wait=S]                                            PHASE 3, THE FREEZE (freeze.py): refused unless the
                                                                             latest round passes 2.1-2.9 and the code check of
                                                                             its home store is passed; runs the worse-fills
                                                                             table of the build days, picks the default variant,
                                                                             writes lock.json under one hash. Prints the hash,
                                                                             the default and the test range
  bp.py test <name> --confirm [--wait=S] [--second-look]                  PHASE 4, THE ONE READ of the test days (oos.py): the
        [--tester=DIR]                                                       read is written to the one-read log FIRST, then
                                                                             the locked variants, their control and the worse
                                                                             fills are run, lines 4.1-4.9 are read and saved.
                                                                             Refused: not frozen, a lock that no longer matches,
                                                                             no --confirm, a read on file for the idea or for a
                                                                             same-idea relative (--second-look: the only way
                                                                             past, labelled so everywhere). A fail is final
  bp.py test <name> --confirm --early-look [--wait=S] [--second-look]     AN EARLY LOOK at the test days, the owner's own (2026-
                                                                             10-06: "warn, then run if I say yes"), for an idea
                                                                             that is NOT frozen -- its build lines may fail, its
                                                                             code check may be missing. What is there is frozen
                                                                             under a lock marked early_look, the read is claimed
                                                                             like any other, lines 4.1-4.9 are read, and all of it
                                                                             says EARLY LOOK. It uses the test days up for the
                                                                             idea and can never prove it: it is kept beside the
                                                                             idea's files (early_look/), never as its test.json
  bp.py heatmap <name> [--place=home|1|2|..|not_here] [--round=N]         THE HEAT MAP of a build round (quick.py; read-only):
                                                                             a row per value of the main setting, a column per
                                                                             exit cell, each cell that variant's net on the build
                                                                             days; what line 2.1 reads, the middle variant, the
                                                                             best and the worst cell (information), and one line
                                                                             for every other place of the card. Counts no round
  bp.py mc <name> [--on=build|test]                                       THE MONTE CARLO of an idea (quick.py; read-only): line
                                                                             2.8 on build -- or 4.7 on a test that is on file --
                                                                             then final net and worst drawdown of the same 1,000
                                                                             runs at the 5th .. 95th percentile, for the average
                                                                             and for the default variant
  bp.py seed-reads [--dry-run]                                            the one-read log filled from the OLD read logs, once
                                                                             (reads.py): the units whose test days were read
                                                                             before the blueprint. A second run adds nothing
  bp.py sim <name> --account=ID --attempts=N --fee-budget=USD             PHASE 5, BEFORE THE EVAL IS BOUGHT (propodds.py): the
                                                                             app's prop simulator on the test-period trades of
                                                                             an idea that passed its test, OPEN LOSSES COUNTED --
                                                                             per pre-set size the odds of the eval within 10
                                                                             trading days and of the maximum payout within 20,
                                                                             plain and "live is worse"; lines 5.1-5.5 (ONE
                                                                             strategy is judged on 5.5: a pass before a bust and
                                                                             a first payout before a bust, 50 % each). The
                                                                             attempts and the fee budget are the owner's numbers
  bp.py portfolio <name> <name> [...] --account=ID                        PHASE 5 FOR SEVERAL PROVEN IDEAS ON ONE ACCOUNT
                                                                             (propodds.portfolio): each member's default variant,
                                                                             every member at the same size, their days drawn
                                                                             together; lines 5.2, 5.3 (eval 60 % within 10
                                                                             trading days, maximum payout 75 % within 20), 5.6
                                                                             (no two the same idea on one market) and 5.7 (every
                                                                             member raises the eval odds)
  bp.py eval-card <name> [--fills=-|FILE] [--account=ID]                  PHASE 6, THE EVAL (evalcard.py): refused until a sim
                                                                             is on file. Without fills: lines 6.1-6.9 as the
                                                                             rules, and the drawdown table of its own test
                                                                             history. With the live fills ({"fills": [...]};
                                                                             the format: bp.py eval-card --help): 6.1-6.5 read
  bp.py blocks                                                            everything an idea can be built from without writing
                                                                             code, one line each, and what version 1 refuses
                                                                             (blocklist.py). Runs nothing
  bp.py blockcode                                                         the same blocks as a browsable list, each with the code
                                                                             that implements it, found in the engine's source
                                                                             (blockcode.py; the Lab's Toolkit view). Runs nothing
  bp.py pipe add --spec=-|FILE [--inbox]                                  THE STRATEGY PIPELINE (pipe_runner.py): a pipeline card
  bp.py pipe list | show <name> | book                                       ({"name", "why", "loser", "source", "market", "session",
  bp.py pipe start | pause | resume                                          "sides", "ways", "indicators"}) is checked (lines
  bp.py pipe approve <name> | refuse <name> --why=TEXT                       P0.1-P0.4) and queued -- a card with a line missing is
  bp.py pipe rerun <name> | pick <name> <cell> --why=TEXT                    refused with its rows; `start` = the runner, detached,
                                                                             that takes every queued idea through stages 0-7 by
                                                                             itself; `pause` stops it after the stage in hand;
                                                                             `list` = one row an idea, `show` = one idea's stage
                                                                             cards; `approve` / `refuse` = the owner's word on an
                                                                             idea that passed every stage; `book` = the approved;
                                                                             `rerun` = an idea that stopped (or was refused) starts again
                                                                             from stage 0: its stage cards move to stages_old/<time>/ (none
                                                                             is deleted), it goes last in the queue; refused while it is
                                                                             running, awaits the owner or is in the book.
                                                                             For `pipe`, --root is the PIPELINE's own folder
                                                                             (HOMEBASE_PIPELINE_ROOT, else ~/.homebase/pipeline):
                                                                             never the app's idea folder
  build, pools, lock, test: [--workers=N] (default 8, or 4 while the desk trades)
A SMOKE RUN (build, pools): --days=d1,d2 --cells=x,y --out=DIR --ledger=FILE = named build days and a few exit cells, into
its own store folder and ledger; never a verdict (`dry_run` true), never saved as a round, never runs_bp/ or ledger.csv.
With --json a command prints exactly ONE JSON object on stdout, on one line (api.result; plan section 8), otherwise its `text`
(and, for the commands of an idea's record, the next step); what a run is doing goes to stderr. Exit: 0 = done (lines may
still fail) · 2 = refused (the reason is printed; `ok` false) · 1 = crashed. --wait=S (build, test): past S seconds the answer
is job.state = running and the work goes on (jobs.py); no --wait = the command works in the foreground. (lock: its one tape
pass always runs as a job, and the command waits 240 s by itself.) --root (or HOMEBASE_IDEAS_ROOT) = the app's idea folder,
where the jobs and the one-read log are kept too.
Not built yet: a tester run as the code check's source (--run-id).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import judge as J

from . import api
from . import freeze as FRZ
from . import jobs as JOBS
from . import oos as OOS
from . import reads as READS
from . import records as REC

NOT_BUILT = ()                                                           # the connector's commands that are a later step of the plan: none is left
ONE_TABLE = ("home", "filter", "round")                                  # options of the one-table build (--spec-file) only


class _Parser(argparse.ArgumentParser):
    """A bad command line is a refusal like any other: exit 2 and, with --json, the one JSON object."""

    def error(self, message):
        raise J.Refuse(f"{message} ({self.format_usage().strip()})")


def _list(v):
    return None if v is None else [x for x in str(v).split(",") if x]


def _parser() -> _Parser:
    ap = _Parser(prog="bp.py", description="The blueprint toolkit (BLUEPRINT.md section 2).", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = lambda name, text: sub.add_parser(name, help=text, allow_abbrev=False)  # noqa: E731 - an option is spelled out: --store is never --stored
    k = add("card", "phase 0: the idea card, lines 0.1-0.7")
    k.add_argument("name", help="the idea's name")
    k.add_argument("--spec", metavar="-|FILE", help="the idea's spec as JSON {name, card, run}: - = on stdin, else a file")
    b = add("build", "phase 2: lines 2.1-2.9, each as pass or fail with its number")
    b.add_argument("name", nargs="?", help="the idea's name")
    b.add_argument("--stored", metavar="UNIT", help="DRY RUN on the old build days (2021-09-22 .. 2023-12-31) for a unit whose stores are on disk")
    b.add_argument("--spec-file", metavar="PATH", help="the one-table build of a spec in run_idea's format that has no record")
    b.add_argument("--reason", help="why this round is run, written before the run (line 2.9)")
    b.add_argument("--home", metavar="ROOT-tfN-SESSION", help="--spec-file: the table that is judged (default: the spec's first market, bar size and session)")
    b.add_argument("--filter", metavar="BLOCK_SIDE", help="--spec-file: judge the table with this one filter of the spec on (line 2.7)")
    b.add_argument("--round", type=int, help="--spec-file: 1 .. 5, the bar of line 2.3 (default 1)")
    b.add_argument("--wait", type=float, metavar="S", help="answer within S seconds; past them the build goes on as a job")
    b.add_argument("--tester", metavar="DIR", help="the tester's base folder the default variant's run goes to (default: the app's own)")
    c = add("code-check", "phase 1: lines 1.1-1.6 on a store or a trades file")
    c.add_argument("name", help="the idea's name")
    c.add_argument("--store", metavar="KEY", help="a store of the engine: its key in the store folder, or its path")
    c.add_argument("--trades", metavar="FILE", help="a trades file: a JSON list of trades")
    c.add_argument("--run-id", metavar="ID", help="a tester run (not built yet)")
    c.add_argument("--looked", action="store_true", help="the owner looked at the 10 trades on the chart (line 1.5)")
    c.add_argument("--same-as", metavar="STORE|FILE", help="the earlier store or file: line 1.6")
    c.add_argument("--cell", help="the store's cell the 10 trades are taken from")
    c.add_argument("--market", help="NQ, ES or GC (a trades file)")
    c.add_argument("--sessions", help="the stated sessions, e.g. nyam,mid")
    c.add_argument("--window", metavar="HH:MM-HH:MM", help="the stated window on the New York clock")
    c.add_argument("--max-per-day", type=int, help="the stated maximum of trades a day")
    s = add("status", "every idea on file, or the full record of one")
    s.add_argument("name", nargs="?", help="an idea's name (left out: every idea)")
    j = add("job", "keep waiting on a job")
    j.add_argument("id")
    j.add_argument("--wait", type=float, metavar="S", help="seconds to wait (default: the wait the job was started with; 0 = how it stands now)")
    p = add("pools", "the random-entry control pools of the build range")
    p.add_argument("--roots", default="NQ,ES,GC")
    p.add_argument("--tf", default="1,5,15,30")
    lk = add("lock", "phase 3: the freeze -- the rule, the variant list, the default variant, the control and the costs under one hash")
    lk.add_argument("name", help="the idea's name")
    t = add("test", "phase 4: the ONE read of the test days (2025-07-01 on), lines 4.1-4.9")
    t.add_argument("name", help="the idea's name")
    t.add_argument("--confirm", action="store_true", help="the owner has said to run the one read: it cannot be taken back")
    t.add_argument("--second-look", action="store_true", help="go past a USED read of a relative: the verdict is labelled SECOND LOOK everywhere")
    t.add_argument("--early-look", action="store_true", help="the owner's EARLY LOOK at the test days for an idea that is NOT frozen: it uses them up for the "
                                                              "idea, is labelled EARLY LOOK everywhere and can never prove it")
    t.add_argument("--tester", metavar="DIR", help="the tester's base folder the default variant's test trades go to (default: the app's own)")
    hm = add("heatmap", "the heat map of an idea's build round: every variant's net on the build days (read-only)")
    hm.add_argument("name", help="the idea's name")
    hm.add_argument("--place", metavar="home|1|2|..|not_here", help="the table shown: home (default), a neighbor by its number in the card's order, or the place it should NOT work")
    hm.add_argument("--round", type=int, metavar="N", help="the build round (default: the latest one with a result)")
    q = add("mc", "the Monte Carlo of an idea: the law's line and the reshuffled runs as two small tables (read-only)")
    q.add_argument("name", help="the idea's name")
    q.add_argument("--on", choices=("build", "test"), help="build (default): line 2.8 on the latest build round · test: line 4.7 on a test that is on file")
    sr = add("seed-reads", "the one-read log of the test days filled from the old read logs, once")
    sr.add_argument("--dry-run", action="store_true", help="write nothing: say what would be added")
    m = add("sim", "phase 5: the prop simulator on the test-period trades, for one account (open losses count)")
    m.add_argument("name", help="the idea's name")
    m.add_argument("--account", metavar="ID", help="the account in question: a rule file of the app's prop simulator, e.g. lucid-pro-50k@2026-09-27b (bp.py blocks lists them)")
    m.add_argument("--attempts", type=int, metavar="N", help="how many evals the owner will buy at most (line 5.4: his number, never a guess)")
    m.add_argument("--fee-budget", type=float, metavar="USD", help="the owner's total fee budget in dollars (line 5.4: his number, never a guess)")
    pf = add("portfolio", "phase 5 for several proven ideas on one account: lines 5.2, 5.3, 5.6, 5.7 (open losses count)")
    pf.add_argument("names", nargs="+", metavar="name", help="two or more ideas that are each proven on history")
    pf.add_argument("--account", metavar="ID", help="the account in question: a rule file of the app's prop simulator, e.g. lucid-pro-50k@2026-09-27b")
    from . import evalcard                          # phases 5 and 6 are loaded when a command line is read, never with this module: a tape pass's workers import it
    e = sub.add_parser("eval-card", help="phase 6: the eval card -- lines 6.1-6.9 and the drawdown table of its own test history", allow_abbrev=False,
                       epilog=evalcard.FILLS, formatter_class=argparse.RawDescriptionHelpFormatter)
    e.add_argument("name", help="the idea's name")
    e.add_argument("--fills", metavar="-|FILE", help="the live trades of the eval so far, ONE JSON object: - = on stdin, else a file (THE FILLS FORMAT, below)")
    e.add_argument("--account", metavar="ID", help="the account the card stands on (default: the card's own, else the simulator result saved last)")
    bl = add("blocks", "everything an idea can be built from without writing code, and what version 1 refuses")
    bc = add("blockcode", "the same blocks as a browsable list, each with the code that implements it (the Lab's Toolkit view)")
    pp = add("pipe", "the strategy pipeline: pipeline cards in, each one taken through stages 0-7 by the runner (--root here = the PIPELINE's folder)")
    ps = pp.add_subparsers(dest="sub", required=True, metavar="{add,list,show,start,pause,resume,approve,refuse,book,rerun,pick,curve,executions}")
    pipes = {name: ps.add_parser(name, allow_abbrev=False, **({"help": text} if text else {})) for name, text in (     # no help = not listed (_loop)
        ("add", "check a pipeline card (lines P0.1-P0.4) and put it in the queue"), ("list", "one row an idea: status, stage reached, tries, why it stopped"),
        ("show", "one idea: its reason, its state, every stage card's first line"), ("start", "start the runner (detached); it works through the queue by itself"),
        ("pause", "the runner stops after the stage in hand"), ("resume", "the runner carries on"), ("approve", "the owner's yes: the idea goes in the book"),
        ("refuse", "the owner's no, with his reason"), ("book", "one row a book card"),
        ("rerun", "an idea that stopped starts again from stage 0 (its stage cards are kept in stages_old)"),
        ("pick", "the owner names the box stage 1 picks (one of the boxes at the floor), with his reason; --clear takes it away"),
        ("curve", "an idea's picked box as a person looks at it: its equity curve by day and its numbers (reads the stored trades, runs nothing)"),
        ("executions", "an idea's picked box as a finished run of the tester page, so Show-on-chart opens every entry and exit (written once)"),
        ("_loop", None))}      # _loop: the detached child of `pipe start`, the runner itself
    pipes["add"].add_argument("--spec", metavar="-|FILE", help="the pipeline card as JSON: - = on stdin, else a file")
    pipes["add"].add_argument("--inbox", action="store_true", help="the card goes before the queued ones")
    for name in ("show", "approve", "refuse", "rerun", "pick", "curve", "executions"):
        pipes[name].add_argument("name", help="the pipeline card's name")
    pipes["pick"].add_argument("cell", nargs="?", help="the box's id, e.g. k0p4_pts45-r2 (not with --clear)")
    pipes["pick"].add_argument("--clear", action="store_true", help="take the owner's pick away")
    pipes["refuse"].add_argument("--why", metavar="TEXT", help="the owner's reason (kept with the idea)")
    pipes["pick"].add_argument("--why", metavar="TEXT", help="the owner's reason for the box (kept with the idea)")
    pipes["_loop"].add_argument("--once", action="store_true", help="everything that can run now, then end")
    for x in pipes.values():
        x.add_argument("--root", metavar="DIR", help="the PIPELINE's folder (default HOMEBASE_PIPELINE_ROOT, else ~/.homebase/pipeline) -- not the app's idea folder: "
                                                     "the pipeline keeps its heat maps' ideas inside its own")
        x.add_argument("--json", action="store_true", help="print the result as one JSON object")
    for x in (lk, t):
        x.add_argument("--wait", type=float, metavar="S", help="answer within S seconds; past them the work goes on as a job")
        x.add_argument("--workers", type=int, help="worker processes (default: 8, or 4 while the desk trades)")
    for x in (lk, t, sr, m, pf, e, bl, bc, hm, q):
        x.add_argument("--root", metavar="DIR", help="the app's idea folder (default HOMEBASE_IDEAS_ROOT, else ~/.homebase/ideas)")
        x.add_argument("--json", action="store_true", help="print the result as one JSON object")
    for x in (b, p):
        x.add_argument("--workers", type=int, help="worker processes (default: 8, or 4 while the desk trades)")
        x.add_argument("--ledger", metavar="FILE", help="a smoke run's own ledger")
        x.add_argument("--days", help="a smoke run: named build days, d1,d2")
        x.add_argument("--cells", help="a smoke run: exit cells, e.g. atr3-r1,pts20-r0")
    for x in (b, c, p):
        x.add_argument("--out", metavar="DIR", help="the store folder (default runs_bp/)")
    for x in (k, b, c, s, j, p):
        x.add_argument("--root", metavar="DIR", help="the app's idea folder (default HOMEBASE_IDEAS_ROOT, else ~/.homebase/ideas)")
        x.add_argument("--json", action="store_true", help="print the result as one JSON object")
    return ap


def _job(kw: dict, a, command: str = "build", wait=None) -> dict:
    """A build (a freeze, a test) that was told how long to wait: a job (jobs.py), its answer inside the wait or `running`."""
    wait = a.wait if wait is None else wait
    d = JOBS.new(command, a.name, kw, a.root, wait)
    JOBS.start(d)
    return JOBS.wait(d.name, a.root, wait)


def _lock(a) -> dict:
    """`lock <name>`: the freeze. Its one tape pass (the worse-fills table of the build days) runs as a job, because the
    connector stops a command after 300 s: the command waits --wait seconds (freeze.LOCK_WAIT by itself) and then answers
    `running`; `lock <name>` again picks that job's wait back up. A freeze with nothing to run answers at once."""
    wait = FRZ.LOCK_WAIT if a.wait is None else a.wait
    job = JOBS.running(a.name, a.root)
    if job and JOBS.command(job, a.root) == "lock":
        return JOBS.wait(job, a.root, wait)
    kw = FRZ.start(a.name, a.root, workers=a.workers)       # every refusal that needs no run comes back at once, never as a job
    return _job(kw, a, "lock", wait) if kw.get("heavy") else FRZ.run(**kw)


def _test(a) -> dict:
    """`test <name> --confirm [--wait=S] [--second-look] [--early-look]`: every refusal, then the read is claimed in the
    one-read log, then the run -- in the foreground, or as a job (`job <id>` picks its wait back up: nothing is read again)."""
    kw = OOS.start(a.name, a.confirm, a.second_look, a.root, workers=a.workers, tester=a.tester, early_look=a.early_look)
    return OOS.run(**kw) if a.wait is None else _job(kw, a, "test")


def _build(a) -> dict:
    if a.stored:
        if a.name or a.spec_file:
            raise J.Refuse("build takes an idea's name or --stored <unit>, not both")
        return api.build_stored(a.stored)
    if not a.name:
        raise J.Refuse("build needs the idea's name (bp.py build <name> --reason=...), or --stored <unit> for a dry run on the old build days")
    run = dict(workers=a.workers, out=a.out, ledger=a.ledger, days=_list(a.days), cells=_list(a.cells))
    if not a.spec_file:                             # THE IDEA'S RECORD: its card says the home, the filter; its folder counts the rounds
        given = [f"--{k}" for k in ONE_TABLE if getattr(a, k) is not None]
        if given:
            raise J.Refuse(f"{', '.join(given)}: an option of the one-table build (--spec-file=PATH); an idea's record says its own home, filter and round")
        kw = REC.start(a.name, a.reason, a.root, tester=a.tester, **run)      # every refusal that needs no run -- then the reason is on disk
        return REC.run(**kw) if a.wait is None else _job(kw, a)
    try:
        spec = json.loads(Path(a.spec_file).read_text())
    except (OSError, ValueError) as e:
        raise J.Refuse(f"spec file {a.spec_file}: {e}") from None
    kw = dict(spec=spec, name=a.name, reason=a.reason or "", home=a.home, filt=a.filter, round_=1 if a.round is None else a.round, **run)
    if a.wait is None:
        return api.build(**kw)                      # in the foreground
    api.build(**kw, dry=True)                       # every refusal that needs no run comes back at once, never as a job
    return _job(kw, a)


def _card(a) -> dict:
    if not a.spec:
        raise J.Refuse(f"card needs the idea's spec, {{name, card, run}} as JSON: --spec=- (on stdin) or --spec=FILE (bp.py card {a.name} --spec=-)")
    where = "on stdin" if a.spec == "-" else a.spec
    try:
        raw = sys.stdin.read() if a.spec == "-" else Path(a.spec).read_text(encoding="utf-8")
        spec = json.loads(raw) if raw.strip() else None
    except (OSError, ValueError) as e:
        raise J.Refuse(f"the spec {where} {'is not there' if isinstance(e, OSError) else 'does not read as JSON'}: {e}") from None
    if spec is None:
        raise J.Refuse(f"no spec {where}: the idea's spec, {{name, card, run}} as JSON")
    return REC.card(a.name, spec, a.root)


def _fills(a):
    """`eval-card --fills=-|FILE`: the live fills, ONE JSON object {"fills": [...]} (evalcard.FILLS) -- None without the option."""
    if a.fills is None:
        return None
    where = "on stdin" if a.fills == "-" else a.fills
    try:
        raw = sys.stdin.read() if a.fills == "-" else Path(a.fills).read_text(encoding="utf-8")
        got = json.loads(raw) if raw.strip() else None
    except (OSError, ValueError) as e:
        raise J.Refuse(f"the fills {where} {'are not there' if isinstance(e, OSError) else 'do not read as JSON'}: {e}") from None
    if got is None:
        raise J.Refuse(f"no fills {where}: ONE JSON object {{\"fills\": [...]}} (the format: bp.py eval-card --help)")
    return got


def _pipe(a) -> dict:
    """`pipe <sub>`: the strategy pipeline's commands (pipe_runner.command). --root is the PIPELINE's folder here; `add` reads
    its card from --spec (- = stdin)."""
    from . import pipe_runner                       # loaded when a pipe command is read, never with this module
    card = None
    if a.sub == "add":
        if not a.spec:
            raise J.Refuse("pipe add needs the pipeline card as JSON: --spec=- (on stdin) or --spec=FILE (bp.py pipe add --spec=-)")
        where = "on stdin" if a.spec == "-" else a.spec
        try:
            raw = sys.stdin.read() if a.spec == "-" else Path(a.spec).read_text(encoding="utf-8")
            card = json.loads(raw) if raw.strip() else None
        except (OSError, ValueError) as e:
            raise J.Refuse(f"the card {where} {'is not there' if isinstance(e, OSError) else 'does not read as JSON'}: {e}") from None
        if card is None:
            raise J.Refuse(f"no card {where}: the pipeline card as JSON")
    if a.sub in ("curve", "executions"):               # the views (pipe_view): they read a store, run nothing
        from . import pipe_view
        return getattr(pipe_view, a.sub)(a.name, a.root)
    return pipe_runner.command(a.sub, getattr(a, "name", None), a.root, card=card, inbox=getattr(a, "inbox", False), why=getattr(a, "why", None),
                               once=getattr(a, "once", False), cell=getattr(a, "cell", None), clear=getattr(a, "clear", False))


def _said(r: dict) -> str:
    """A result for a person: its text -- and the next step, for the commands of an idea's record and of the pipeline."""
    cmd = r.get("command")
    return r["text"] + (f"\nNEXT: {r['next']}" if r.get("next") and (cmd in ("card", "status", "lock", "test", "seed-reads", "heatmap", "mc") or str(cmd).startswith("pipe ")
                                                                    or "idea" in r) else "")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) == 2 and argv[0] == "_job":        # the detached child of a job (jobs.start): no command of the toolkit's users
        return JOBS.work(argv[1])
    a = None
    try:
        a = _parser().parse_args(argv)
        if a.cmd == "build":
            r = _build(a)
        elif a.cmd == "card":
            r = _card(a)
        elif a.cmd == "status":
            r = REC.status(a.name, a.root)
        elif a.cmd == "job":
            r = JOBS.wait(a.id, a.root, a.wait)
        elif a.cmd == "pools":
            r = api.pools(_list(a.roots), _list(a.tf), a.workers, a.out, a.ledger, _list(a.days), _list(a.cells))
        elif a.cmd == "lock":
            r = _lock(a)
        elif a.cmd == "test":
            r = _test(a)
        elif a.cmd == "seed-reads":
            r = READS.seed(a.dry_run, a.root)
        elif a.cmd == "sim":
            from . import propodds
            r = propodds.sim(a.name, a.account, a.attempts, a.fee_budget, a.root)
        elif a.cmd == "portfolio":
            from . import propodds
            r = propodds.portfolio(a.names, a.account, a.root)
        elif a.cmd == "eval-card":
            from . import evalcard
            r = evalcard.card(a.name, _fills(a), a.root, a.account)
        elif a.cmd == "blocks":
            from . import blocklist
            r = blocklist.blocks()
        elif a.cmd == "blockcode":
            from . import blockcode
            r = blockcode.toolkit()
        elif a.cmd == "pipe":
            r = _pipe(a)
        elif a.cmd in ("heatmap", "mc"):
            from . import quick                      # the two views: they read, and run nothing
            r = quick.heatmap(a.name, a.place, a.round, a.root) if a.cmd == "heatmap" else quick.mc(a.name, a.on, a.root)
        else:
            r = api.code_check(a.name, a.store, a.trades, a.run_id, a.same_as, a.looked, a.cell, a.market, _list(a.sessions), a.window, a.max_per_day, a.root, a.out)
    except api.REFUSALS as e:
        cmd = (f"pipe {a.sub}" if a.cmd == "pipe" else a.cmd) if a else next((x for x in argv if not x.startswith("-")), None)
        why = f"{cmd} is not built yet: it is a later step of the toolkit plan ({e})" if a is None and cmd in NOT_BUILT else str(e)
        r = api.refused(cmd, why, getattr(a, "name", None) or getattr(a, "stored", None) if a else None)
    print(json.dumps(r) if "--json" in argv else _said(r))     # one object on one ASCII line: safe for any reader of stdout
    return JOBS.code(r)
