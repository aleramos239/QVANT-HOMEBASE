"""cli.py -- the command line of bp.py (toolkit plan, section 4: one command per phase; the command line = the connector tool).
The connector (homebase/claude_mcp/blueprint_tools.py) writes every command as
    <python> bp.py <command> <the idea's name> --opt=value ... --root=<ideas root> --json
in this folder; the card comes on stdin (`--spec=-`), nothing else does. A person may leave --root and --json out.

  bp.py card <name> --spec=- | --spec=FILE                                PHASE 0: lines 0.1-0.6 off the card ({"name", "card",
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
  build, pools: [--workers=N] (default 8, or 4 while the desk trades)
A SMOKE RUN (build, pools): --days=d1,d2 --cells=x,y --out=DIR --ledger=FILE = named build days and a few exit cells, into
its own store folder and ledger; never a verdict (`dry_run` true), never saved as a round, never runs_bp/ or ledger.csv.
With --json a command prints exactly ONE JSON object on stdout, on one line (api.result; plan section 8), otherwise its `text`
(and, for the commands of an idea's record, the next step); what a run is doing goes to stderr. Exit: 0 = done (lines may
still fail) · 2 = refused (the reason is printed; `ok` false) · 1 = crashed. --wait=S (build): past S seconds the answer is
job.state = running and the work goes on (jobs.py); no --wait = the command works in the foreground. --root (or
HOMEBASE_IDEAS_ROOT) = the app's idea folder, where the jobs are kept too.
Not built yet: lock, test, sim, eval-card; a tester run as the code check's source (--run-id).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import judge as J

from . import api
from . import jobs as JOBS
from . import records as REC

NOT_BUILT = ("lock", "test", "sim", "eval-card")                         # the connector's other commands: a later step of the plan
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
    k = add("card", "phase 0: the idea card, lines 0.1-0.6")
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


def _job(kw: dict, a) -> dict:
    """A build that was told how long to wait: a job (jobs.py), its answer inside the wait or `running`."""
    d = JOBS.new("build", a.name, kw, a.root, a.wait)
    JOBS.start(d)
    return JOBS.wait(d.name, a.root, a.wait)


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


def _said(r: dict) -> str:
    """A result for a person: its text -- and the next step, for the commands of an idea's record."""
    return r["text"] + (f"\nNEXT: {r['next']}" if r.get("next") and (r.get("command") in ("card", "status") or "idea" in r) else "")


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
        else:
            r = api.code_check(a.name, a.store, a.trades, a.run_id, a.same_as, a.looked, a.cell, a.market, _list(a.sessions), a.window, a.max_per_day, a.root, a.out)
    except api.REFUSALS as e:
        cmd = a.cmd if a else next((x for x in argv if not x.startswith("-")), None)
        why = f"{cmd} is not built yet: it is a later step of the toolkit plan ({e})" if a is None and cmd in NOT_BUILT else str(e)
        r = api.refused(cmd, why, getattr(a, "name", None) or getattr(a, "stored", None) if a else None)
    print(json.dumps(r) if "--json" in argv else _said(r))     # one object on one ASCII line: safe for any reader of stdout
    return JOBS.code(r)
