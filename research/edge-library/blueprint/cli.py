"""cli.py -- the command line of bp.py (toolkit plan, section 4: one command per phase; the command line = the connector tool).

  bp.py build --stored <unit> [--json]     DRY RUN of lines 2.1-2.8 on the OLD build days for a unit whose stores are on disk
                                           (read-only). <unit> = an address (`ib-NQ-tf15-mid:mode=break`) or a uid of
                                           out/v2/build_units.csv, in quotes (`'orb-NQ-tf15|pre|'`, `E1-A-NQ`).
With --json a command prints exactly ONE JSON object on stdout, on one line (api.result; plan section 8), otherwise its `text`.
Exit: 0 = done (lines may still fail) · 2 = refused (the reason is printed; `ok` false) · 1 = crashed.
The other commands of the plan (card, code-check, build with rounds, lock, test, sim, eval-card, status, job) and the
options --wait and --root are not built yet.
"""
from __future__ import annotations

import argparse
import json
import sys

import judge as J

from . import api
from . import rules as R


class _Parser(argparse.ArgumentParser):
    """A bad command line is a refusal like any other: exit 2 and, with --json, the one JSON object."""

    def error(self, message):
        raise J.Refuse(f"{message} ({self.format_usage().strip()})")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = _Parser(prog="bp.py", description="The blueprint toolkit (BLUEPRINT.md section 2).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="phase 2: lines 2.1-2.8, each as pass or fail with its number")
    b.add_argument("--stored", metavar="UNIT", help="DRY RUN on the old build days (2021-09-22 .. 2023-12-31) for a unit whose stores are on disk")
    b.add_argument("--json", action="store_true", help="print the result as one JSON object")
    a = None
    try:
        a = ap.parse_args(argv)
        if not a.stored:
            raise J.Refuse("only the dry run on stored units is built so far (toolkit plan, step 2): bp.py build --stored <unit>")
        r = api.build_stored(a.stored)
    except (J.Refuse, R.RuleError) as e:
        r = api.refused(a.cmd if a else next((x for x in argv if not x.startswith("-")), None), str(e), a.stored if a else None)
    print(json.dumps(r) if "--json" in argv else r["text"])    # one object on one ASCII line: safe for any reader of stdout
    return 0 if r["ok"] else 2
