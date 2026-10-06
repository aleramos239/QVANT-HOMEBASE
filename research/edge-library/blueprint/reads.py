"""reads.py -- WHO HAS USED THE TEST DAYS (2025-07-01 on). The out-of-sample test of BLUEPRINT.md phase 4 is ONE read: for an
idea, and for every close relative of it. The app keeps the one-read log (homebase/ideastore.py: test_reads.jsonl, one line a
read, written BEFORE the days are opened); this module answers what stands in the way of a read, and brings the reads that
were made before the blueprint into that log.

    old()                 the units whose 2025-07-01+ days were read BEFORE the blueprint, off the old read logs
    seed(dry_run, root)   `bp.py seed-reads [--dry-run]`: one line a unit in the one-read log; a unit that has a line is left
                          alone, so a second run adds nothing
    used(name, lock)      for a frozen idea: the read on file for the idea itself, and the reads of its SAME-IDEA RELATIVES

THE OLD READ LOGS (read-only; a row is a store that was run, logged before its pass, or a store a verdict rests on):
    out/judge/year_reads.csv     every store a `judge.py year` verdict rests on: unit, period (pick | check | exam), verdict
    out/check2025/reads.csv      the stores of the 2025 runner: the unit's table, period "check (2025)"
    out/exam2026/reads.csv       the stores of the 2026 runner: period "exam (2026-01-01..<end>)"
    out/v2/pick_reads.csv        the stores of the 2024 runners: every key ends -pick
WHICH ROW MEANS "this unit has had its 2025-07-01+ days read": a row whose PERIOD reaches a day on or after the first test
day (ranges.json). 2025 (check: the whole year, so Jul-Dec with it) and 2026 (exam) do; 2024 (pick) lies inside the build
days and does not. The unit is the judge's (its address, with its day filter: `straddle_tight_0830-GC-tf30-pre@A`): the
verdict that was read is that unit's. A table of the two runners that no verdict rests on is listed by its own address (its
days were replayed and its store is on disk); a row of a random-entry pool (`c1-...`) is no strategy and is left out.
IN THE LOG a unit stands under the name the judge gave it, in small letters (the app's rule for a name:
`straddle_tight_0830_gc_tf30_pre_eva`), version 0 (before the blueprint), lock `old:<its address>`, the range that was read,
state judged, and the old verdicts in words.

SAME IDEA (judge.py: "one strategy per stack"). Two units are the same idea when they share the entry trigger, the market and
the session, or when their default variants take the same side on 70 % or more of 30 or more shared trading days. The
relatives of a frozen idea are looked for among every unit with a read: the old saved strategies through judge.same_idea
itself (the idea's build store stands in for a store of runs/), blueprint ideas by the same two relations on their build days.
No test day is read here: the relations are read on build days, the logs are text.
"""
from __future__ import annotations

import csv
import json
import re
import zlib
from pathlib import Path

import judge as J
import library as LB

from . import W
from . import api
from . import rules as R

YEAR, CHECK, EXAM, PICK = (W / "out" / "judge" / "year_reads.csv", W / "out" / "check2025" / "reads.csv", W / "out" / "exam2026" / "reads.csv",
                           W / "out" / "v2" / "pick_reads.csv")
OLD_VERSION = 0                                     # a read made before the blueprint: an idea's versions start at 1
OLD = "old:"                                        # how the lock of such a line starts: old:<the unit's address>
TAG = re.compile(r"-(pick|check|exam)(?:-|$)")      # the period a store of the old runners belongs to, in its key
SPAN = re.compile(r"\((\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})\)")
YEARS = {"pick": "2024", "check": "2025", "exam": "2026"}


def _rows(path) -> list:
    try:
        with Path(path).open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _span(period: str, said: str = "") -> tuple:
    """(start, end) of a read: the judge's period, or the dates the row itself names (the 2026 runner wrote its end)."""
    m = SPAN.search(said or "")
    return (m[1], m[2]) if m else tuple(J.PERIODS[period]["range"])


def _reaches(span: tuple) -> bool:
    """Does a read of these dates hold a test day?"""
    return span[1] >= R.template("ranges")["test"]["start"]


def unit_of(addr: str) -> dict:
    """A unit's address (judge.ADDR: <family>-<ROOT>-tf<tf>-<session>[:<label>][@<day filter>]) -> what the same-idea check
    asks of it, and the name it has in the one-read log: the judge's own name for the unit, in small letters."""
    m = J.ADDR.match(addr.strip())
    if not m:
        raise J.Refuse(f"unit {addr!r}: expected <family>-<ROOT>-tf<tf>-<session>[:<axis>=<value>][@<day filter>]")
    label, filt = m["label"] or "", m["filt"]
    name = (f"{m['family']}_{m['root']}_tf{m['tf']}_{m['sess']}" + (f"_{label.replace('=', '')}" if label else "")
            + (f"_ev{filt}" if filt in J.EVENT_GROUPS else f"_{filt}" if filt else ""))
    name = re.sub(r"[^a-z0-9_]", "_", name.lower())
    if len(name) > 40:                              # the app's rule for a name: at most 40 characters (the address stays whole in the lock)
        name = f"{name[:31]}_{zlib.crc32(addr.strip().encode()):08x}"
    try:
        name = api.ideastore().validate_name(name)
    except ValueError as e:
        raise J.Refuse(f"unit {addr}: {e}") from None
    return {"unit": addr.strip(), "name": name, "family": m["family"], "market": m["root"], "bar": m["tf"], "session": m["sess"], "filter": filt}


def old(year=YEAR, check=CHECK, exam=EXAM, pick=PICK) -> dict:
    """THE UNITS WHOSE TEST DAYS WERE READ BEFORE THE BLUEPRINT (module docstring) -> {address: {unit, name, family, market,
    bar, session, filter, read {year: verdict | "run"}, range {start, end}, utc (the last of its reads), stores [...],
    verdict (in words), sources [the logs it stands in]}}, in the order the logs name them."""
    out: dict = {}

    def add(addr, period, span, utc, store, verdict, source):
        u = out.setdefault(addr, {**unit_of(addr), "read": {}, "range": {"start": span[0], "end": span[1]}, "utc": utc, "stores": [], "sources": []})
        u["read"][YEARS[period]] = verdict or u["read"].get(YEARS[period]) or "run"
        u["range"] = {"start": min(u["range"]["start"], span[0]), "end": max(u["range"]["end"], span[1])}
        u["utc"] = max(u["utc"], utc)
        u["stores"] += [store] if store and store not in u["stores"] else []
        u["sources"] += [source] if source not in u["sources"] else []

    spans = {m[1]: _span(m[1], r["period"]) for r in (*_rows(check), *_rows(exam)) for m in [re.match(r"(check|exam)\b", r.get("period") or "")] if m}
    for r in _rows(year):                           # a verdict of the judge: the unit as it was judged
        p = r.get("period")
        if p in YEARS and _reaches(spans.get(p) or _span(p)) and not (r.get("role") or "").startswith("BUILD"):
            add(r["unit"], p, spans.get(p) or _span(p), r["utc"], r["store"], r.get("verdict"), "out/judge/year_reads.csv")
    judged = {s for u in out.values() for s in u["stores"]}
    for path, rel in ((check, "out/check2025/reads.csv"), (exam, "out/exam2026/reads.csv")):       # a table that was run and no verdict rests on
        for r in _rows(path):
            m = re.match(r"(check|exam)\b", r.get("period") or "")
            if m and _reaches(_span(m[1], r["period"])) and r.get("kind") in ("base", "stress") and not r["unit"].startswith("c1-") and r["store"] not in judged:
                add(r["unit"], m[1], _span(m[1], r["period"]), r["utc"], r["store"], None, rel)
    for r in _rows(pick):                           # the 2024 runners: a key that names a later period would count; none does
        m = TAG.search(r.get("key") or "")
        if m and m[1] != "pick" and _reaches(_span(m[1])) and r.get("family") != "random":
            add(f"{r['family']}-{r['root']}-tf{r['tf']}-{r['sess']}", m[1], _span(m[1]), r["utc"], r["key"], None, "out/v2/pick_reads.csv")
    for u in out.values():
        u["verdict"] = (f"OLD READ {u['utc'][:10]}, before the blueprint: " + ", ".join(f"{y} {v}" for y, v in sorted(u["read"].items()))
                        + f" ({', '.join(u['sources'])})")
    return out


def seed(dry_run: bool = False, root=None, **logs) -> dict:
    """`bp.py seed-reads [--dry-run]`: THE ONE-READ LOG FILLED FROM THE OLD READ LOGS, once. Every unit of old() gets ONE line
    (ideastore.log_read: name, version 0, lock `old:<address>`, the range that was read, state judged, the old verdicts in
    words). A unit that has a line in the log already -- from an earlier run of this command, or because an idea of that
    name was tested -- is left alone: a second run adds nothing. --dry-run writes nothing and says what it would add.
    Beyond the agreed keys: dry_run, units (all of them, each with `on_file`), added | would_add (their names)."""
    IS = api.ideastore()
    units = list(old(**logs).values())
    have = {r.get("name") for r in IS.reads(root)}
    todo = [u for u in units if u["name"] not in have]
    if not dry_run:
        for u in todo:
            IS.log_read(u["name"], version=OLD_VERSION, lock=OLD + u["unit"], rng=u["range"], state="judged", verdict=u["verdict"], root=root)
    where = IS.ideas_root(root) / IS.READS_FILE
    rows = [{"name": u["name"], "unit": u["unit"], "range": u["range"], "read": u["read"], "verdict": u["verdict"], "on_file": u["name"] in have} for u in units]
    word = "would add" if dry_run else "added"
    text = [f"{'DRY RUN: nothing is written. ' if dry_run else ''}{len(units)} unit{'s' * (len(units) != 1)} had {'their' if len(units) != 1 else 'its'} test days "
            f"({R.template('ranges')['test']['start']} on) read before the blueprint; {len(units) - len(todo)} on file already, {word} {len(todo)} "
            f"({where})"]
    text += [f"  {'on file ' if x['on_file'] else word.upper():<9s} {x['name']:<38s} {x['unit']:<38s} {x['range']['start']} .. {x['range']['end']}  "
             + ", ".join(f"{y} {v}" for y, v in sorted(x["read"].items())) for x in rows]
    r = api.result("seed-reads", None, saved=[str(where)] if todo and not dry_run else [], dry_run=bool(dry_run), units=rows,
                   text="\n".join(text), next=("Run it without --dry-run to write the lines." if dry_run and todo else
                                              "Every old read is in the one-read log: a relative of these units is refused its test, or runs it as a SECOND LOOK."))
    r["would_add" if dry_run else "added"] = [u["name"] for u in todo]
    return r


# ================================================================ what stands in the way of a read

def _holders(root) -> dict:
    """Every unit with a read of the test days -> {name: {name, kind 'old' | 'idea', utc, verdict, state, family, market,
    session, (unit | lock)}}: the latest line of each name in the one-read log, and the units of the old read logs whether
    they were brought into the log or not (their reads were made either way)."""
    IS, out = api.ideastore(), {}
    for u in old().values():
        out[u["name"]] = {**{k: u[k] for k in ("name", "unit", "family", "market", "session", "utc", "verdict")}, "kind": "old", "state": "judged", "in_log": False}
    for r in IS.reads(root):
        name, lock = r.get("name"), r.get("lock")
        if not isinstance(name, str):
            continue
        h = {"name": name, "utc": r.get("utc"), "verdict": r.get("verdict"), "state": r.get("state"), "in_log": True}
        if isinstance(lock, str) and lock.startswith(OLD):
            try:
                h.update({k: v for k, v in unit_of(lock[len(OLD):]).items() if k in ("unit", "family", "market", "session")}, kind="old")
            except J.Refuse:
                h.update(kind="old", unit=lock[len(OLD):])
        else:
            h.update(kind="idea", lock=lock)
            try:
                frozen = json.loads((IS.idea_dir(name, root) / "lock.json").read_text(encoding="utf-8"))
                h.update(family=frozen["spec"]["run"]["family"], market=frozen["home"]["market"], session=frozen["home"]["session"], frozen=frozen)
            except (OSError, ValueError, KeyError, TypeError):
                pass                                # a read without its idea folder: it is found by its name only
        out[name] = {**out.get(name, {}), **h}
    return out


def _unit(lock: dict) -> dict:
    """The judge's unit of a frozen idea's home table, by hand (judge.unit reads runs/ only): what cellx and same_idea ask."""
    h = lock["home"]
    return {"name": lock["name"], "addr": h["unit"], "uid": h["uid"], "key": h["key"], "family": lock["spec"]["run"]["family"], "root": h["market"],
            "tf": str(h["bar"]), "sess": h["session"], "label": "", "filter": None, "group": None, "side": None, "placebo": 0}


def _sides(lock: dict) -> dict:
    """{trade date: the side of the default variant's first entry that day} on the idea's build days (judge._day_side)."""
    st = J.store({"dir": Path(lock["home"]["folder"]), "key": lock["home"]["key"]})
    return J._day_side(J.cellx(st, lock["default"], lock["home"]["session"]))


def same_members(lock: dict, members_dir=None) -> list:
    """judge.same_idea for a frozen blueprint idea against the old saved strategies (members/): the folders that are the
    same idea. The judge reads a unit's build store from runs/; the idea's own (in the blueprint's store folder) stands in
    for it, for this call only. Nothing of the test days is read: build and 2024 days."""
    u, folder = _unit(lock), (LB.MEMBERS if members_dir is None else Path(members_dir))
    if not folder.is_dir():                         # no saved strategy on this machine: nothing to be held against
        return []
    mine = J.store({"dir": Path(lock["home"]["folder"]), "key": u["key"]})
    keep = J.build_store
    J.build_store = lambda m: (mine, None) if m is u else keep(m)
    try:
        return J.same_idea(u, lock["default"], folder)
    finally:
        J.build_store = keep


def used(name: str, lock: dict, root=None, members_dir=None) -> dict:
    """WHAT STANDS IN THE WAY OF THE READ of a frozen idea -> {"own": the idea's own line in the one-read log | None,
    "relatives": [{name, kind, why, utc, verdict, state, unit}]} -- the units with a read of the test days that are the
    SAME IDEA (module docstring). An empty answer = the days are unseen for this idea.
    Refused (J.Refuse) when the question cannot be answered: a one-read log that does not read, or saved strategies the
    judge's check cannot be run against (a store of theirs that is gone). The test days are not opened on a guess."""
    IS = api.ideastore()
    try:
        own = IS.read_on_file(name, root=root)
        H = {k: v for k, v in _holders(root).items() if k != name}
    except IS.ReadLogUnreadable as e:
        raise J.Refuse(str(e)) from None
    fam, mk, ss = lock["spec"]["run"]["family"], lock["home"]["market"], lock["home"]["session"]
    why: dict = {}
    for k, h in H.items():
        if (h.get("family"), h.get("market"), h.get("session")) == (fam, mk, ss):
            why[k] = f"the same entry trigger, market and session ({fam}, {mk}, {J.SESS_PLAIN[ss].split(' (')[0]})"
    try:
        members = same_members(lock, members_dir)
    except (J.Refuse, OSError, KeyError, ValueError) as e:
        raise J.Refuse(f"the same-idea check against the saved strategies could not be run ({type(e).__name__}: {e}): whether the test days are unseen "
                       f"for {name} is not known, and they are not opened on a guess") from None
    for m in members:
        k = m.lower()
        if k in H:
            why.setdefault(k, f"the same idea by the judge's check, directly or through another saved strategy: the same trigger, market and session, or "
                              f"default variants that take the same side on {100 * J.SAME_SIDE:.0f} % or more of {J.SAME_DAYS} or more shared trading days")
    mine = None
    for k, h in H.items():
        if k in why or h.get("kind") != "idea" or not h.get("frozen"):
            continue
        try:
            mine = _sides(lock) if mine is None else mine
            theirs = _sides(h["frozen"])
        except (OSError, KeyError, ValueError, TypeError):
            continue
        shared = [d for d in mine if d in theirs]
        same = sum(mine[d] == theirs[d] for d in shared) / len(shared) if shared else 0.0
        if len(shared) >= J.SAME_DAYS and same >= J.SAME_SIDE:
            why[k] = f"its default variant takes the same side as this one's on {100 * same:.0f} % of {len(shared)} shared trading days"
    rel = [{"name": k, "kind": H[k].get("kind"), "why": w, "utc": H[k].get("utc"), "verdict": H[k].get("verdict"), "state": H[k].get("state"),
            "unit": H[k].get("unit"), "in_log": H[k].get("in_log")} for k, w in why.items()]
    return {"own": own, "relatives": rel}
