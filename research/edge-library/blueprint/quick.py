"""quick.py -- TWO READ-ONLY VIEWS of an idea that has a build on file, made to be read in a chat (the owner's
`/test <name> heatmap` and `/test <name> mc`):

    heatmap(name, place, round_)   `bp.py heatmap <name> [--place=home|1|2|..|not_here] [--round=N]`
        THE HEAT MAP of ONE table of a build round (the latest with a result, or round N): one row per value of the idea's
        main setting, one column per exit cell of the standard table (8 stops x the 4 targets inside each), each cell =
        that variant's net on the build days. Under it what line 2.1 reads -- how many variants make money, the average
        variant --, the middle variant (the median), and the best and the worst cell AS INFORMATION: the law judges the
        average of all variants, never the best cell. Then the same in one line for every other place the card names.
        A place = home | 1, 2, .. (a neighbor, in the card's order) | not_here (the place it should NOT work).
    mc(name, on)                   `bp.py mc <name> [--on=build|test]`
        THE MONTE CARLO of the home table: the law's own line -- 2.8 on the build days of the latest round, 4.7 on a
        test THAT IS ON FILE -- and then the same 1,000 reshuffled runs as two small tables, for the average variant
        (what the law judges) and the default variant (the middle survivor): the final net and the worst drawdown of a
        run at the percentiles of montecarlo.json `view`, and the share of runs that end above $0.

BOTH READ, AND NOTHING ELSE. They read the idea's record (a round's settings and result; the lock and the test result) and
the stores those name, through the seals of every other reader: tables._open (the build days and nothing later),
runner.guard_test (the frozen range, this lock's read). No tape pass, no round is counted, nothing is written -- not
idea.json either: the status in the answer is read off the saved results (ideastore.status).
THE NUMBERS ARE THE LAW'S. Makes money = above $0 (rules.json 2.1: lines._heat); the variants that count = the judged ones
(library.judged_rows: one that cannot trade there, or that has the trades of another, is shown and not counted); the middle
variant = the median (plan section 6, decision 3). The runs are mc.py's of the fixed seed -- so the line's number here IS
the number the build or the test saved --, a run's drawdown is the eval card's (evalcard.falls) on mc.histories.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI

from . import api
from . import lines as L
from . import mc as MC
from . import records as REC
from . import rules as R
from . import runner as RUN
from . import tables as T

HOME, NOT_HERE = "home", "not_here"
ON = ("build", "test")
DRAW = "whole days, with replacement, the same days for every variant"
NO_TARGET = "no target"                             # target 0 R: the trade runs to its stop or to the flat time


def _k(v: float, mark: bool = True) -> str:
    """Dollars in thousands, as a chat reads them: +$45.0k makes money, -$3.2k loses; a size (a drawdown) has no mark."""
    sign = "" if not mark else "+" if L._profitable(v) else "-" if v < 0 else ""
    return f"{sign}${abs(v) / 1000:,.1f}k"


def _idea(name, root) -> Path:
    """The idea's folder, or refused: the app has no idea of that name."""
    IS = api.ideastore()
    try:
        d = IS.idea_dir(name, root)
    except ValueError as e:
        raise J.Refuse(str(e)) from None
    if not d.is_dir():
        raise J.Refuse(f"no idea {name} in {IS.ideas_root(root)}")
    return d


def _days(named, sessions, start=None, end=None) -> dict:
    """The days a view read: the build range, or the named days of a store that was run on a few."""
    rg = R.template("ranges")["build"]
    return {"start": named[0] if named else start or rg["start"], "end": named[-1] if named else end or rg["end"], "sessions": sessions, "named": named}


def _when(d: dict) -> str:
    return (f"{len(d['named'])} named build days" if d["named"] else "build days") + f" {d['start']} .. {d['end']}"


def built(name, root=None, round_=None) -> dict:
    """THE BUILD ROUND a view reads -> {dir, round, build (its result, as saved), plan, store, family, filter, folder}: the
    latest round with a result, or the one named; its stores are where its own result says. Refused: no such idea; NO
    BUILD YET (run the build first); a round without a result."""
    IS, d = api.ideastore(), _idea(name, root)
    done = [n for n in IS.rounds(name, root) if REC._json(d / "rounds" / str(n) / "build.json")]
    if not done:
        raise J.Refuse(f"{name} has no build on file yet: run the build first (bp.py build {name} --reason=\"why round 1 is run\") -- this reads the "
                       "stores a build wrote, and runs nothing")
    if round_ is not None and round_ not in done:
        raise J.Refuse(f"round {round_} of {name} has no result on file (rounds with one: {', '.join(str(n) for n in done)})")
    n = done[-1] if round_ is None else round_
    b, rspec = REC._json(d / "rounds" / str(n) / "build.json"), REC._json(d / "rounds" / str(n) / "spec.json") or {}
    plan = rspec.get("plan")
    if not (isinstance(plan, dict) and rspec.get("store") and isinstance(rspec.get("run"), dict)):
        raise J.Refuse(f"round {n} of {name} has no settings on file (rounds/{n}/spec.json: its store, its plan): its tables cannot be found")
    at = next((s.get("path") for s in b.get("stores") or [] if isinstance(s, dict) and s.get("key") == b.get("home_store")), None)
    return {"dir": d, "round": n, "build": b, "plan": plan, "store": rspec["store"], "family": rspec["run"].get("family"),
            "filter": tuple(plan["filters"][0].split("_", 1)) if plan.get("filters") else None, "folder": Path(at).parent if at else RUN.RUNS}


# ================================================================ the heat map

def places(plan: dict) -> dict:
    """{its name on the command line: the place}: home · 1, 2, .. = the card's neighbors, in the card's order · not_here."""
    return {HOME: plan["home"], **{str(i): p for i, p in enumerate(plan["neighbors"], 1)}, NOT_HERE: plan["not_here"]}


def _table(B: dict, p: dict) -> tuple:
    """One table of the round by its place -> (the store, its rows in the place's session, where it is). tables._open is
    the seal: a store that is not inside the build days is refused, not read."""
    st, where = T._open(B["folder"], RI.unit_key({"name": B["store"]}, p["market"], p["bar"], B["filter"]))
    rows = LB.plateau_units(st, p["session"]).get("")
    if rows is None:
        raise J.Refuse(f"store {where} is judged per value of a mirror axis: no view reads such a table")
    return st, rows, where


def summary(rows: list) -> dict:
    """ONE TABLE IN A FEW NUMBERS -- what line 2.1 reads, and the two ends: its judged variants (the judge's: one that
    cannot trade there and one with the trades of another are out), how many make money (above $0: rules.json 2.1) and
    their share, the net of the average and of the middle variant (the median), the best and the worst cell. The best
    cell is INFORMATION: the law judges the average of all variants, never the best."""
    ts, by = J.table_stats(rows), {r["id"]: float(r["net"]) for r in rows}
    out = {"variants": ts["cells"], "profitable": 0, "share": None, "avg": None, "median": None, "best": None, "worst": None, "dead": ts["dead"], "duplicates": ts["dup"]}
    if ts["cells"]:
        ids, v = ts["ids"], np.array([by[c] for c in ts["ids"]])
        share, avg, _ = L._heat(v)
        hi, lo = int(v.argmax()), int(v.argmin())
        out.update(profitable=int(L._profitable(v).sum()), share=float(share), avg=float(avg), median=float(np.median(v)),
                   best={"cell": ids[hi], "net": float(v[hi])}, worst={"cell": ids[lo], "net": float(v[lo])})
    return out


def grid(st: dict, rows: list, setting: str) -> dict:
    """THE GRID of one table -> {setting, rows (the values of the main setting), cols (the exit cells the store holds, in
    the menu's order: stops outer, targets inner), stops, targets (of each column), net (rows x cols: that variant's net
    in dollars; null = it cannot trade there), cells (their ids)}."""
    cell = {c["id"]: c for c in st["meta"]["cells"]}
    rows = [r for r in rows if not r.get("info")]
    var, ex = {r["vi"]: cell[r["id"]]["variant"] for r in rows}, {r["xi"]: cell[r["id"]]["exit"] for r in rows}      # (by variant index, by exit index)
    vis, xis = sorted(var), sorted(ex)
    net, ids = [[None] * len(xis) for _ in vis], [[None] * len(xis) for _ in vis]
    for r in rows:
        i, j = vis.index(r["vi"]), xis.index(r["xi"])
        net[i][j], ids[i][j] = (None if r.get("dead") else float(r["net"])), r["id"]
    return {"setting": setting, "rows": [var[v].get(setting, S.cell_id(var[v])) for v in vis], "cols": [S.cell_id(ex[x]) for x in xis],
            "stops": [f"{ex[x]['stop_mode']} {float(ex[x]['stop_val']):g}" for x in xis],
            "targets": [f"{float(ex[x]['tgt_r']):g}R" if ex[x].get("tgt_r") else NO_TARGET for x in xis], "net": net, "cells": ids}


def _grid_text(g: dict, dead: set, twins: set) -> list:
    """The grid as a chat shows it: one line per value and stop, the targets across; a cell in $ thousands with its mark
    (+ makes money, - loses), `.` = it cannot trade here, `=` = the trades of another variant (counted once)."""
    stops = list(dict.fromkeys(g["stops"]))
    tgts = sorted(set(g["targets"]), key=lambda t: 0.0 if t == NO_TARGET else float(t[:-1]))
    at = {(s, t): j for j, (s, t) in enumerate(zip(g["stops"], g["targets"]))}
    w = max(len(str(x)) for x in [g["setting"], *g["rows"]])

    def cell(i: int, j) -> str:
        v = None if j is None else g["net"][i][j]
        return ("" if j is None else "." if v is None or g["cells"][i][j] in dead else "=" if g["cells"][i][j] in twins else
                ("+" if L._profitable(v) else "-" if v < 0 else "") + f"{abs(v) / 1000:.1f}")

    out = [f"{g['setting']:<{w}}  {'stop':<8}" + "".join(f"{t:>10}" for t in tgts)]
    for i, v in enumerate(g["rows"]):
        out += [f"{(str(v) if k == 0 else ''):<{w}}  {s:<8}" + "".join(f"{cell(i, at.get((s, t))):>10}" for t in tgts) for k, s in enumerate(stops)]
    return [x.rstrip() for x in out]


def _said(s: dict) -> str:
    """A table in one line."""
    return ("no variant traded there" if not s["variants"] else
            f"{s['profitable']} of {s['variants']} variants make money ({L._pc(s['share'])}) · average {_k(s['avg'])} · middle {_k(s['median'])} · "
            f"best {_k(s['best']['net'])} · worst {_k(s['worst']['net'])}")


def heatmap(name, place=None, round_=None, root=None) -> dict:
    """`bp.py heatmap <name> [--place=home|1|2|..|not_here] [--round=N]` (module docstring). Runs nothing, counts no round,
    writes nothing. Beyond the agreed keys: place, grid {setting, rows, cols, stops, targets, net, cells}, summary (the
    table shown: place, said, table, store + summary()), places (every place of the card, the same), not_judged {dead,
    duplicates: the cells that are shown and not counted}, days; `lines` = line 2.1 of that round as the build saved it,
    for the home table. Refused: built()'s refusals, a place the card does not have, a store that is not there."""
    B = built(name, root, round_)
    P = places(B["plan"])
    which = HOME if place is None else str(place).strip().lower().replace("-", "_")
    if which not in P:
        raise J.Refuse(f"place {str(place)!r}: {', '.join(list(P)[:-1])} or {NOT_HERE} (home · a neighbor by its number, in the card's order: "
                       + ", ".join(f"{k} = {p['said']}" for k, p in P.items() if k not in (HOME, NOT_HERE)) + " · the place it should NOT work)")
    sums, shown = [], None
    for k, p in P.items():
        try:
            st, rows, where = _table(B, p)
        except J.Refuse:
            if k == which:
                raise
            sums.append({"place": k, "said": p["said"], "table": p["table"], "store": None, **summary([])})      # (a place whose store is gone: said, not hidden)
            continue
        sums.append({"place": k, "said": p["said"], "table": p["table"], "store": where, **summary(rows)})
        if k == which:
            shown = (st, rows)
    st, rows = shown
    s, p, n = next(x for x in sums if x["place"] == which), P[which], B["round"]
    g, judged = grid(st, rows, B["plan"]["main_setting"]), set(J.table_stats(rows)["ids"])
    dead = [r["id"] for r in rows if r.get("dead") and not r.get("info")]
    twins = [r["id"] for r in rows if not r.get("dead") and not r.get("info") and r["id"] not in judged]
    named = st["meta"].get("days") or None
    days = _days(named, len(named) if named else (B["build"].get("days") or {}).get("sessions"))
    line = next((x for x in B["build"].get("lines") or [] if isinstance(x, dict) and x.get("line") == "2.1"), None) if which == HOME else None
    what = "HOME" if which == HOME else f"NOT HERE \"{p['said']}\"" if which == NOT_HERE else f"NEIGHBOR {which} \"{p['said']}\""
    off = " · ".join(x for x in (f"{len(dead)} variant{'s' * (len(dead) != 1)} that cannot trade here (.)" if dead else "",
                                 f"{len(twins)} with the trades of another variant (=)" if twins else "") if x)
    text = [f"HEAT MAP of {name} · round {n} · {what} {REC._nice(p)} ({p['table']}) · {_when(days)}",
            f"Each cell: that variant's net on those days in $ thousands, after costs, 1 contract (+ makes money, - loses). Rows: {g['setting']} x stop; across: the target.",
            *_grid_text(g, set(dead), set(twins)),
            *([f"MAKE MONEY: {s['profitable']} of {s['variants']} variants ({L._pc(s['share'])}) · average variant {_k(s['avg'])} · middle variant {_k(s['median'])}",
               f"BEST CELL {s['best']['cell']} {_k(s['best']['net'])} · WORST CELL {s['worst']['cell']} {_k(s['worst']['net'])} -- information only: the law judges "
               "the average of all variants, never the best cell"] if s["variants"] else ["NO VARIANT TRADED HERE on those days."]),
            *([f"NOT COUNTED: {off}"] if off else []),
            *([f"{line.get('text')}   <- line 2.1 of round {n}, as the build saved it"] if line else []),
            "THE OTHER PLACES of the card (--place=<its name> shows the grid of one):",
            *[f"  {x['place']:<9} {REC._nice(P[HOME]) if x['place'] == HOME else x['said']} ({x['table']}): " + ("its store is not on disk" if x["store"] is None else _said(x))
              + (" (the card says it should NOT work here; no line reads it)" if x["place"] == NOT_HERE else "") for x in sums if x["place"] != which]]
    IS = api.ideastore()
    status = IS.status(name, root)
    return api.result("heatmap", name, status=status, round=n, lines=[line] if line else [], place=which, grid=g, summary=s, places=sums,
                      not_judged={"dead": dead, "duplicates": twins}, days=days, text="\n".join(text), next=REC._step(name, status, REC._last(name, root), root))


# ================================================================ the Monte Carlo

def tables(t: dict, default=None, above=0) -> list:
    """THE RESHUFFLED RUNS AS TABLES, for the average variant and -- when the table has it -- the default variant.
    t = table data (lines.py: net and n per variant and session day, ids). -> [{variant 'average' | 'default', cell,
    percentiles, net [...], drawdown [...], above_zero, runs}]: a run's FINAL NET is mc.reshuffle's (the runs of lines
    2.8 and 4.7: the fixed seed, the same days for every variant), its WORST DRAWDOWN the largest fall of its P&L from
    its highest point so far, the start counting as a point (the eval card's: evalcard.falls, on mc.histories); both at
    the percentiles of montecarlo.json `view`, linear between ranks; above_zero = the share of runs that end above
    `above` dollars."""
    from . import evalcard as EC                    # (it loads the prop simulator's module: only when a table is asked for)
    net, pct = np.asarray(t["net"], np.float64), R.template("montecarlo")["view"]["percentiles"]
    tot, _ = MC.reshuffle(net, t["n"])
    who = [("average", None, net.mean(0), tot.mean(0))]
    if default in t["ids"]:
        i = t["ids"].index(default)
        who.append(("default", default, net[i], tot[i]))
    out = []
    for (variant, cell, _, final), path in zip(who, MC.histories(np.array([x[2] for x in who]))):
        worst = EC.falls(path)[1][:, -1]
        out.append({"variant": variant, "cell": cell, "percentiles": list(pct), "net": [float(v) for v in np.percentile(final, pct)],
                    "drawdown": [float(v) for v in np.percentile(worst, pct)], "above_zero": float((final > above).mean()), "runs": int(len(final))})
    return out


def _built(name, root) -> tuple:
    """THE HOME TABLE OF THE LATEST BUILD ROUND as the lines read it (tables._data: its judged variants on the session days
    of the build range, or on the named days its store was run on) -> (the round, the table, the days)."""
    B = built(name, root)
    h = B["plan"]["home"]
    u = T.bp_unit({"name": B["store"], "family": B["family"]}, h["market"], h["bar"], h["session"], "", B["filter"])
    st, where = T._open(B["folder"], u["key"])
    T._labels(st, u)
    ts = J.table_stats(J.table(st, u))
    if not ts["cells"]:
        raise J.Refuse(f"{u['addr']}: no judged variant on the build days")
    named = st["meta"].get("days") or None
    cal = named or [d.isoformat() for d in S.sessions(*S.period(RUN.PERIOD), h["market"], allow_holdout=RUN.PERIOD)]
    return B, T._data(st, u, ts, LB._ordinals(cal), where), _days(named, len(cal))


def _tested(name, root) -> tuple:
    """THE TABLE OF THE TEST THAT IS ON FILE -> (the lock, the table, the days): the locked variants on the session days
    the read replayed, from the store the test result names. Nothing is run. Refused: no test on file -- or one that does
    not count (refused, a dry run, still running) --, a result of another lock, a store that is not this lock's read
    (runner.guard_test: the frozen range, this lock) or that lacks a locked variant."""
    d = _idea(name, root)
    lock, test = REC._json(d / "lock.json"), REC._json(d / "test.json")
    job = (test or {}).get("job")
    if not (lock and test and test.get("ok") is not False and not test.get("dry_run") and isinstance(test.get("lines"), list)
            and not (isinstance(job, dict) and job.get("state") != "done")):
        raise J.Refuse(f"{name} has no out-of-sample test on file: --on=test reads the test that was run (bp.py test {name} --confirm, for a frozen idea) and "
                       "runs nothing" + (" -- its early look is no test (bp.py status shows its lines)" if (d / api.EARLY_LOOK / "test.json").is_file() else ""))
    if test.get("lock") != lock.get("hash"):
        raise J.Refuse(f"{name}: the test result on file is of lock {test.get('lock') or '?'}, the lock on file is {lock.get('hash')}: its Monte Carlo is read "
                       "on the read of ITS lock")
    try:
        h, rng, ids = lock["home"], lock["test_range"][lock["home"]["market"]], [str(v) for v in lock["variants"]]
        at = next(Path(s["path"]) for s in test["stores"] if s["kind"] in ("unit", "filter"))
        span = (str(rng["start"]), str(rng["end"]))
    except (KeyError, TypeError, StopIteration):
        raise J.Refuse(f"{name}: its lock and its test result do not say where the trades of the test are (lock.json: home, variants, test_range; "
                       "test.json: stores)") from None
    meta, where = REC._json(at / "run.json"), f"{at.parent.name}/{at.name}"
    if meta is None or not (at / "cells.npz").exists():
        raise J.Refuse(f"{name}: no store {at} (run.json and cells.npz): the trades of its test are not there")
    RUN.guard_test(meta, where, *span, lock["hash"])
    st, cal = J.store({"dir": at.parent, "key": at.name}), meta.get("calendar")
    gone = [v for v in ids if v not in st["_idx"]]
    if gone or not cal:
        raise J.Refuse(f"{name}: store {where} " + (f"lacks the locked variant {gone[0]}" if gone else "does not say which session days were replayed") + ": it is not read")
    u = T.bp_unit({"name": lock.get("store"), "family": ((lock.get("spec") or {}).get("run") or {}).get("family")}, h["market"], str(h["bar"]), h["session"])
    return lock, T._data(st, u, {"ids": ids, "dead": 0, "dup": 0}, LB._ordinals(cal), where), _days(None, len(cal), *span)


def mc(name, on=None, root=None) -> dict:
    """`bp.py mc <name> [--on=build|test]` (module docstring). Runs nothing, writes nothing. on = build (default): the
    home table of the latest build round, line 2.8 -- the share of the reshuffled runs in which lines 2.1 and 2.2 both
    hold; test: the locked variants of the test that is on file, line 4.7 -- the share in which the average variant makes
    money. Beyond the agreed keys: on, default (the default variant's cell), days, table {store, variants}, montecarlo
    {runs, seed, draw, percentiles}, tables (tables()), lock (on a test). `lines` = the one line, with ITS OWN number.
    Refused: no such idea; no build yet (run the build first); --on=test without a test on file."""
    on = ON[0] if on is None else str(on).strip().lower()
    if on not in ON:
        raise J.Refuse(f"--on {on!r}: build or test (the build days of the latest round · the out-of-sample test that is on file)")
    IS, m = api.ideastore(), R.template("montecarlo")
    if on == "build":
        B, t, days = _built(name, root)
        dv = B["build"].get("default") or {}
        row, n, default, home, above = L.monte(t), B["round"], dv.get("cell"), B["plan"]["home"], R.rule("2.1")["also"]["profitable_above"]
        head = f"round {n} · {_when(days)}"
        why = f"the middle of the {dv.get('survivors')} variant{'s' * (dv.get('survivors') != 1)} that made money on build; never the best"
    else:
        lock, t, days = _tested(name, root)
        row, n, default, home, above = L.monte_test(t), lock.get("round"), lock.get("default"), lock["home"], R.rule("4.7")["also"]["above"]
        head, why = f"the out-of-sample test {days['start']} .. {days['end']} (lock {lock['hash']})", "the lock's default variant"
    tb, pct = tables(t, default, above), m["view"]["percentiles"]
    nums = lambda vals, mark: "".join(f"{_k(v, mark):>10}" for v in vals)  # noqa: E731
    text = [f"MONTE CARLO of {name} · {head} · home {REC._nice(home)} · {len(t['ids'])} variants · {days['sessions']:,} session days",
            f"{m['runs']:,} reshuffled runs: whole days drawn with replacement, the same days for every variant, fixed seed {m['seed']}.",
            row["text"], f"{'':<18}" + "".join(f"{str(p) + 'th':>10}" for p in pct) + "   percentile of the runs"]
    for x in tb:
        text += ["AVERAGE VARIANT (what the law judges)" if x["variant"] == "average" else f"DEFAULT VARIANT {x['cell']} ({why})",
                 f"  {'final net':<16}" + nums(x["net"], True), f"  {'worst drawdown':<16}" + nums(x["drawdown"], False),
                 f"  ends above $0 in {L._pc(x['above_zero'])} of the runs"]
    if len(tb) < 2:
        text.append("DEFAULT VARIANT: none to show" + (f" ({default} is not one of the table's variants)" if default else " (no variant made money on build)"))
    text.append(f"HOW TO READ IT: {pct[0]}th = {pct[0]} runs in 100 end below it, {pct[-1]}th = {100 - pct[-1]} in 100 end above it; a drawdown is a run's largest fall "
                f"from its highest point, so its {pct[-1]}th is the deep end. $ thousands after costs, 1 contract.")
    status = IS.status(name, root)
    return api.result("mc", name, status=status, phase=api.PHASE["mc"] if on == "build" else api.PHASE["test"], round=n, lines=[row], on=on, default=default, days=days,
                      table={"store": t["store"], "variants": len(t["ids"])}, montecarlo={"runs": m["runs"], "seed": m["seed"], "draw": DRAW, "percentiles": list(pct)},
                      tables=tb, text="\n".join(text), next=REC._step(name, status, REC._last(name, root), root), **({"lock": lock["hash"]} if on == "test" else {}))
