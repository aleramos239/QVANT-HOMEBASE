"""freeze.py -- THE FREEZE (BLUEPRINT.md phase 3; `bp.py lock <name>`; toolkit plan, step 8). "Before the test period is
touched": what the idea is gets saved, with one hash over all of it, and from here nothing changes.

    3.1  Saved: the rule, the variant list, the default variant (the middle survivor, never the best), the control and the costs
    3.2  From here nothing changes. A change is a new version: back to phase 2, and its earlier unseen read is marked as used
    3.3-3.8  the default variant ON ITS OWN on the build days: profit factor, net / worst drawdown, Sharpe, its drawdown at 1
         micro under the account's limit, Monte Carlo, its net without its best 1 % of days (lines.BOX on tables.box).
         One of them not met = refused: nothing is frozen
    SHOWN, never a pass line: the default variant's prop odds on the build days for the account of line 3.6 (propodds.look)

REFUSED unless, for the idea on file:
  * its LATEST build round has every line 2.1-2.9 in its result and none failed (null = the line does not apply) -- a round
    that was started and has no result, a smoke run, a round whose card was changed afterwards: refused
  * a CODE CHECK is on file for the round's home store with every line that is read true: 1.1-1.5 TRUE (1.5 = the owner
    looked at the 10 trades), 1.6 not failed -- and TRUE when the engine or the family code changed since the store was
    written (the earlier trade list reproduced by a fresh run: line 1.6)
THEN (start() refuses, run() works):
  1. THE WORSE-FILLS TABLE of the home table on the build days (runner.run_worse: the engine's STRESS, 2 ticks + 250 ms,
     + the 100 ms late cancel for a two-sided bracket). One tape pass; a table that is stored is never run again.
  2. THE DEFAULT VARIANT = the middle one, by build net, of the variants that make money on build AND on build with worse
     fills (plan section 6, decision 3; records.middle, the judge's tie rule). No such variant = refused: nothing to freeze.
     `default=<cell>` (a keyword of the CODE, never of bp.py or the chat tools, like `waive`): the pipeline's variant mode
     (pipeline.json "mode": "variant") has picked its box already, at the end of stage 1; that cell is the default instead of the
     middle survivor, and default_rule says so. It has to be a judged variant that makes money on build AND with worse fills:
     else refused (_choose).
  3. lock.json, written through the app's idea store (ideastore.write_lock):
       name, version, locked_utc, round, store
       spec          the card and the settings, as the frozen round ran them        plan   what a build of the card ran
       home          market, session, bar, table, the unit's store key and folder, its one filter, its uid
       variants      THE VARIANT LIST: the variants judged on build (dead and duplicate ones out), in table order
       default, survivors, default_rule
       box           lines 3.3-3.8 as they were read on the default variant (each line's number, need and words)
       prop          its prop odds on the build days as they were shown (propodds.look): a number on the card, no line reads it
       build         avg_trade: line 2.2's number of the frozen variants on the build days (line 4.8 holds the test against it)
       costs         normal (the engine's defaults) and worse (as run: with or without the late cancel)
       control       c1: the pool's store, its 10 seeds, 4,000 draws, the draw seeds (build as it was drawn, test as it WILL be)
       montecarlo    the runs and the fixed seed of lines 2.8 and 4.7
       code          sha256/16 of the engine and family files that make the trades (runner.code)
       stores        every build store the freeze rests on: its inputs fingerprint and the sha256/16 of its two files
       test_range    per market the card names: the first test day .. that market's last complete session on disk, FROZEN
       hash          sha256/16 over all of it
The status stays what the saved results say (a LEAD); the phase is 3. `lock` on an idea that is frozen changes nothing: it
shows the lock on file and says whether its hashes still match the files on disk (verify) -- what `test` will ask.

THE WORSE-FILLS PASS IS A TAPE PASS over 45 months. The connector stops a command that is not a job after 300 s, so the
command line waits LOCK_WAIT seconds by itself and then answers job.state = running (jobs.py); `bp.py lock <name>` again
picks that job's wait back up (cli.py).
TEST ONLY: BP_TEST_RUN (records.TEST_RUN) hands the pass its named build days, exit cells, store folder and ledger; with
`box: "said"` lines 3.3-3.8 are read and kept but do not refuse (the default of a 3-day table cannot pass on its own), and
`build_avg_trade` is kept as the build's average trade (a hand-made test table is held against it: line 4.8).
NOT A FREEZE: early() = the lock of the owner's EARLY LOOK at the test days (oos.py), for an idea that is not frozen: what is
there, marked early_look, with the build lines that failed. It is never the idea's lock.json, and the idea stays unfrozen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import flowtab
import judge as J

from . import api
from . import jobs as JOBS
from . import lines as L
from . import records as REC
from . import rules as R
from . import runner as RUN
from . import tables as T

LOCK_WAIT = 240.0                                   # seconds `lock` waits by itself for the worse-fills pass (the connector gives a command 300)
KEEP = ("hash",)                                    # what the hash is not taken over: itself
PLAIN = ("1.1", "1.2", "1.3", "1.4", "1.5")         # the lines of the code check that are read on every store: each must be TRUE


def digest(lock: dict) -> str:
    """ONE HASH OVER ALL OF IT: sha256/16 of the lock as canonical JSON (keys in order, no spaces), without its own hash."""
    doc = {k: v for k, v in lock.items() if k not in KEEP}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()[:16]


def sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def code(family) -> dict:
    """sha256/16 of the engine and family files as they are on disk NOW (runner.code, read again: nothing remembered)."""
    RUN._sha.cache_clear()
    return RUN.code(family)


def store_hash(folder, key: str) -> dict:
    """A store as a lock holds it: its folder, the fingerprint of its inputs, the sha256/16 of run.json and of cells.npz."""
    d = Path(folder) / key
    try:
        meta = json.loads((d / "run.json").read_text())
        return {"folder": str(Path(folder)), "inputs_hash": meta.get("inputs_hash"), "run": sha(d / "run.json"), "cells": sha(d / "cells.npz")}
    except (OSError, ValueError) as e:
        raise J.Refuse(f"store {Path(folder).name}/{key}: {e}") from None


def verify(lock: dict, spec=None) -> list:
    """WHAT NO LONGER MATCHES between a lock and the files on disk (an empty list = everything does): its own hash, the
    card and settings on file (`spec`: the idea's spec.json), the engine and family code, every build store it rests on."""
    bad = []
    if lock.get("hash") != digest(lock):
        bad.append(f"lock.json was changed after it was written (it says {lock.get('hash')}, its contents hash to {digest(lock)})")
    if spec is not None and {k: spec.get(k) for k in ("card", "run")} != {k: (lock.get("spec") or {}).get(k) for k in ("card", "run")}:
        bad.append("the card and settings on file (spec.json) are not the frozen ones")
    try:
        now = code(lock["spec"]["run"]["family"])
    except (KeyError, TypeError, OSError) as e:
        return bad + [f"the code of the frozen rule cannot be read ({e})"]
    bad += [f"{f} changed since the freeze ({h} -> {now.get(f) or 'gone'})" for f, h in (lock.get("code") or {}).items() if now.get(f) != h]
    for key, was in (lock.get("stores") or {}).items():
        try:
            got = store_hash(was["folder"], key)
        except J.Refuse as e:
            bad.append(f"store {key} cannot be read ({e})")
            continue
        if got != was:
            bad.append(f"store {Path(was['folder']).name}/{key} changed since the freeze ({', '.join(k for k in was if got.get(k) != was[k])})")
    return bad


def _l2_end():
    """The last session of the test days' Level 2 table (engine/btfeat.py), or a refusal that says it is not built."""
    import btfeat
    try:
        return btfeat.last_date()
    except FileNotFoundError as e:
        raise J.Refuse(str(e)) from None


def _reads(filt) -> dict:
    """What the filter of a rule (one, or a pair) reads, as `_range` takes it: flow (a delta block) / l2 (a Level 2 block)."""
    return {"flow": RUN._blocks().reads(filt, RUN._blocks().FLOW_BLOCKS), "l2": RUN._blocks().reads(filt, RUN._blocks().L2_BLOCKS)}


def _range(market: str, home: bool, flow: bool = False, l2: bool = False) -> dict:
    """The test range of a market as it is frozen (runner.test_range). The home's must be there: it is what the test reads.
    A neighbor's market without one is said in its place (no line of the test reads a neighbor). flow = the idea's filter is a
    delta block: the range ends where the flow file ends (flowtab.last_date): a later session has no flow row, so every entry of
    it would be blocked, and a test of those days would read an idea that was never run there. l2 = a Level 2 block: it ends
    where the test days' Level 2 table ends (btfeat.last_date: the vendor's depth history), for the same reason."""
    try:
        caps = ([flowtab.last_date(market)] if flow else []) + ([_l2_end()] if l2 else [])
        return RUN.test_range(market, min(caps) if caps else None)
    except J.Refuse as e:
        if home:
            raise
        return {"start": R.template("ranges")["test"]["start"], "end": None, "sessions": 0, "parts": [], "no_tape": 0, "stops": None, "none": str(e)}


def _folder(out) -> Path:
    return RUN.RUNS if out is None else Path(out)


def _where(folder: Path, key: str) -> str:
    return f"{folder.name}/{key}"


def _checked(d: Path, folder: Path, key: str, family: str) -> None:
    """Refused unless the idea's code check (check.json) stands for the home store `key` in `folder`: module docstring."""
    name, chk = d.name, REC._json(d / "check.json")
    home = f"bp.py code-check {name} --store={key}"
    if chk is None:
        raise J.Refuse(f"{name} has no code check on file: phase 1 comes before the freeze ({home}, look at the 10 trades it names, then again with --looked)")
    marks = {x.get("line"): x.get("passed") for x in chk.get("lines") or [] if isinstance(x, dict)}
    off = [k for k in PLAIN if marks.get(k) is not True] + (["1.6"] if marks.get("1.6") is False else [])
    if off or chk.get("ok") is False:
        why = "the owner has not looked at the 10 trades on the chart yet (line 1.5): run it again with --looked" if off == ["1.5"] else \
            f"line{'s' * (len(off) != 1)} {', '.join(off)} {'are' if len(off) != 1 else 'is'} not true"
        raise J.Refuse(f"the code check of {name} on file is not passed: {why} ({home})")
    src, asked, here = chk.get("source") or {}, chk.get("asked") or {}, (folder / key).resolve()
    same = lambda p: bool(p) and Path(str(p)).expanduser().resolve() == here  # noqa: E731
    fresh = same(asked.get("same_as")) and marks.get("1.6") is True            # a fresh run that reproduced the home store, trade for trade
    if not ((src.get("kind") == "store" and same(src.get("where"))) or fresh):
        raise J.Refuse(f"the code check of {name} on file is of {src.get('where') or 'a trades file'}, not of the home store of the round that is frozen "
                       f"({_where(folder, key)}): check that store ({home}, then --looked)")
    meta = json.loads((folder / key / "run.json").read_text())
    now = code(family)
    if meta.get("code") != now and marks.get("1.6") is not True:
        changed = [f for f in now if (meta.get("code") or {}).get(f) != now[f]]
        raise J.Refuse(f"{', '.join(changed)} changed since {_where(folder, key)} was written: after a change to the code the earlier trade list is reproduced "
                       f"exactly before anything counts (line 1.6: bp.py code-check {name} --store=<a fresh run> --same-as={key}, then --looked)")


def start(name, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, waive=(), default=None) -> dict:
    """EVERYTHING OF THE FREEZE THAT NEEDS NO RUN -> the arguments of run() (JSON: a job keeps them). An idea that is frozen
    already comes back as {"idea", "root", "frozen": True}: run() then only shows its lock. Refused here: module docstring,
    and what the runner refuses before a pass (the no-start window, the ledger's cap, another run in the store folder)."""
    test = REC._test_run(root)
    IS, d = api.ideastore(), REC._carded(name, root)
    if (d / "lock.json").exists():
        if REC._json(d / "lock.json") is None:
            raise J.Refuse(f"{d / 'lock.json'} does not read as a lock: nothing is frozen over it")
        return {"idea": name, "root": None if root is None else str(root), "frozen": True}
    job = JOBS.running(name, root)
    if job:
        raise J.Refuse(f"a job of {name} is still running ({job}): bp.py job {job} picks its wait back up")
    rounds = IS.rounds(name, root)
    if not rounds:
        raise J.Refuse(f"{name} has no build on file: the build comes before the freeze (bp.py build {name} --reason=\"why round 1 is run\")")
    n = rounds[-1]
    b, rspec = REC._json(d / "rounds" / str(n) / "build.json"), REC._json(d / "rounds" / str(n) / "spec.json")
    if b is None or rspec is None:
        raise J.Refuse(f"round {n} of {name} was started (its reason is on file) and has no result: the LATEST build round has to pass every line 2.1-2.9 "
                       "before the freeze")
    if b.get("ok") is False or b.get("dry_run") or (isinstance(b.get("job"), dict) and b["job"].get("state") != "done"):
        raise J.Refuse(f"round {n} of {name} is no build that counts (a smoke run, or one that did not finish)")
    marks = {x.get("line"): x.get("passed") for x in b.get("lines") or [] if isinstance(x, dict)}
    waived = [k for k in IS.LINES[2] if marks.get(k) is False and k in set(waive or ())]     # `waive`: a keyword of the code (the pipeline's, for 2.5), never of bp.py lock
    gone, failed = [k for k in IS.LINES[2] if k not in marks], [k for k in IS.LINES[2] if marks.get(k) is False and k not in waived]
    if gone or failed or (IS.status(name, root) != "lead" and not waived):
        raise J.Refuse(f"round {n} of {name} " + (f"fails {', '.join(failed)}" if failed else f"has no line {', '.join(gone)}" if gone else "is not a pass")
                       + ": every build line 2.1-2.9 has to pass before the freeze (null = it does not apply)")
    spec = REC._spec(name, REC._json(d / "spec.json"))
    if {k: spec[k] for k in ("card", "run")} != {k: rspec.get(k) for k in ("card", "run")}:
        raise J.Refuse(f"the card of {name} was changed after round {n}: what is on file is not the rule that passed the build -- build it (a new round) "
                       "or write the card of that round again")
    plan, store = rspec["plan"], rspec["store"]
    if plan.get("exits", "standard") != "standard":
        raise J.Refuse(f"{name}: its exits are the session-anchored table ({plan['exits']!r}), which can be built (phase 2) but not locked or tested yet: the worse-fills "
                       "pool, the freeze and the test days' tables are not wired to it -- the owner decides when it is (it is not done by hand)")
    days, cells = (days or test.get("days")), (cells or test.get("cells"))
    out, ledger, workers = out or test.get("out"), ledger or test.get("ledger"), workers or test.get("workers")
    days = None if days is None else RUN.seal(days)
    sp = RUN.checked(REC.engine(rspec, plan, store)[0])          # the home's market and bar size: the first store of the plan
    h, filt = plan["home"], REC.rule_filter(plan)
    key = T.bp_unit(sp, h["market"], h["bar"], h["session"], "", T.filter_of(sp, filt))["key"]
    folder = _folder(out)
    if not (folder / key / "run.json").exists():
        raise J.Refuse(f"the home store of round {n}, {_where(folder, key)}, is not on disk: there is nothing to freeze")
    _checked(d, folder, key, sp["family"])
    held = {RUN.S.cell_id(c["exit"]) for c in (REC._json(folder / key / "run.json") or {}).get("cells") or []}
    lack = [x for x in (RUN.S.cell_id(x) for x in R.exit_menu(h["market"])) if x not in held and (cells is None or x in set(cells))]
    if lack:                                        # (a store of the 32 old cells: built before the small targets joined the table)
        raise J.Refuse(f"the home store of round {n}, {_where(folder, key)}, does not hold the whole exit table of the law: {len(lack)} of its "
                       f"{len(R.exit_menu(h['market']))} exit cells are missing (first {lack[0]}; the small targets joined the table with BLUEPRINT.md version 1.1) "
                       f"-- build it again, the missing cells are run and joined to its stores: bp.py build {name} --reason=\"...\"")
    rows = RUN.run_worse(sp, key, h["session"], workers, out, ledger=ledger, days=days, cells=cells, block=block, dry=True)
    return {"idea": name, "root": None if root is None else str(root), "frozen": False, "round_": n, "heavy": not rows[0]["skipped"], "workers": workers,
            "out": None if out is None else str(out), "ledger": None if ledger is None else str(ledger), "days": days, "cells": cells, "block": block,
            "draws": test.get("draws"), "box": test.get("box"), "build_avg_trade": test.get("build_avg_trade"), **({"waived": waived} if waived else {}),
            **({"default": str(default)} if default else {})}


def _choose(rows: list, ids: list, worse: dict, pick, addr: str) -> tuple:
    """The default variant -> (cell | None, the survivors, default_rule). No `pick`: the middle survivor (records.middle) and the
    judge's tie rule, a cell of None when nothing survives (the caller refuses). `pick` = the pipeline's own choice (module docstring,
    step 2): it must be a judged variant AND a survivor, else J.Refuse; the survivors are those the middle would be taken from."""
    default, surv = REC.middle(rows, ids, worse)
    if pick is None:
        return default, surv, J.TIE_RULE
    if pick not in ids:
        raise J.Refuse(f"the box {pick} that the pipeline picked is no judged variant of {addr}: it cannot be the default variant")
    if pick not in surv:
        raise J.Refuse(f"the box {pick} that the pipeline picked is not a variant that makes money on build AND on build with worse fills (it needs both; "
                       f"{len(surv)} variant{'s' * (len(surv) != 1)} of {addr} do): it cannot be the default variant")
    return pick, surv, (f"picked by the pipeline, not by the toolkit: {pick}, the middle (by build net, never the best) of the boxes at the floor with enough trades in the "
                        f"map check of its stage 1; it makes money on build and with worse fills (the toolkit's own default, the middle survivor, would be {default})")


def run(idea, root=None, frozen=False, round_=None, heavy=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, draws=None,
        progress=None, box=None, build_avg_trade=None, waived=None, default=None) -> dict:
    """THE FREEZE ITSELF, with what start() returned: the worse-fills table of the home on the build days (when it is not
    stored), the default variant, lock.json (module docstring), the Lab's copies -> the result: lines 3.1 and 3.2, the
    lock's hash, the default and the test range. Beyond the agreed keys: lock (lock.json as it is on file), hash, default,
    survivors, variants, test_range, range (the home market's), stores, already (the idea was frozen before this call),
    matches + mismatches (do the lock's hashes still match the files on disk), notes, lab."""
    IS, name = api.ideastore(), idea
    d = IS.idea_dir(name, root)
    if frozen:
        lock = REC._json(d / "lock.json")
        if lock is None:
            raise J.Refuse(f"{d / 'lock.json'} does not read as a lock")
        return _result(name, root, lock, already=True, saved=[], stores=[])
    n = round_
    rspec = REC._json(d / "rounds" / str(n) / "spec.json")
    plan, store = rspec["plan"], rspec["store"]
    specs = [RUN.checked(e) for e in REC.engine(rspec, plan, store)]
    sp, h, filt, folder = specs[0], plan["home"], REC.rule_filter(plan), _folder(out)
    f = T.filter_of(sp, filt)
    u = T.bp_unit(sp, h["market"], h["bar"], h["session"], "", f)
    key, sess = u["key"], h["session"]
    worse = RUN.run_worse(sp, key, sess, workers, out, ledger=ledger, days=days, cells=cells, progress=progress, block=block)
    if not worse[0]["ok"]:
        raise J.Refuse(f"{worse[0]['key']}: sessions were dropped by a strategy error ({worse[0].get('error')}): no worse-fills table was written")
    st, _ = T._open(folder, key)
    wst, _ = T._open(folder, worse[0]["key"])
    T._labels(st, u)
    rows = J.table(st, u)
    ids = J.table_stats(rows)["ids"]
    if not ids:
        raise J.Refuse(f"{u['addr']}: no judged variant on the build days: there is nothing to freeze")
    gone = [c for c in ids if c not in wst["_idx"]]
    if gone:
        raise J.Refuse(f"the worse-fills table {_where(folder, worse[0]['key'])} lacks the variant {gone[0]}: it is not the home table's")
    wnet = {c: float(J.cellx(wst, c, sess, u)["net"].sum()) for c in ids}
    default, surv, rule = _choose(rows, ids, wnet, default, u["addr"])
    if default is None:
        raise J.Refuse(f"no variant of {u['addr']} makes money on build AND on build with worse fills ({RUN.worse_words(wst['meta']['worse'])}): there is "
                       "no default variant, so there is nothing to freeze (line 3.1)")
    said, box = box == "said", [fn(T.box(st, u, default, days)) for fn in L.BOX]      # lines 3.3-3.8: the default variant on its own
    if not said and not all(x["passed"] for x in box):          # (said: TEST ONLY, module docstring)
        raise J.Refuse(f"the default variant {default} of {u['addr']} does not meet every line read on it before the freeze -- "
                       + "; ".join(x["text"] for x in box if not x["passed"])
                       + " -- nothing is frozen: back to the build (a new round when one is left, it counts; otherwise the idea is shelved)")
    from . import propodds                          # (phase 5's module: loaded here, never with this one -- cli.py)
    prop = propodds.look(J.cellx(st, default, sess, u), T.build_days(u, days))       # shown, never a pass line
    pool, ctl, mc, costs = RUN.pool_key(h["market"], h["bar"]), R.template("control"), R.template("montecarlo"), R.template("costs")
    keys = [key, worse[0]["key"], pool] + ([T.bp_unit(sp, h["market"], h["bar"], sess)["key"]] if f else [])     # (with a filter: the plain table 2.7 was held against)
    markets = list(dict.fromkeys([h["market"], *(s["market"] for s in plan["stores"])]))
    lock = {"name": name, "version": rspec.get("version", 1), "locked_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "round": n,
            "store": store, "spec": {k: rspec[k] for k in ("name", "version", "card", "run") if k in rspec}, "plan": plan,
            "home": {**{k: h[k] for k in ("market", "session", "bar", "table")}, "unit": u["addr"], "uid": u["uid"], "key": key, "folder": str(folder),
                     "filter": filt, "worse": worse[0]["key"]},
            "variants": list(ids), "default": default, "survivors": list(surv), "default_rule": rule,
            "box": [{k: (None if isinstance(x[k], float) and x[k] in (float("inf"), float("-inf")) else x[k]) for k in ("line", "passed", "number", "need", "text")}
                    for x in box],
            "prop": prop,
            "build": {"avg_trade": T.avg_trade(st, u, ids) if build_avg_trade is None else float(build_avg_trade)},
            "costs": {"normal": costs["normal"], "worse": {**wst["meta"]["worse"], "two_sided": bool(wst["meta"].get("both_sides_declared"))}},
            "control": {"kind": ctl["kind"], "pool": pool, "seeds": list(range(1, ctl["seeds"] + 1)), "draws": int(draws or ctl["draws"]),
                        "draw_seed": {"build": J.seed_of(u["uid"], f"{RUN.PERIOD}-c1"), "test": J.seed_of(u["uid"], "test-c1")}},
            "montecarlo": {"runs": mc["runs"], "seed": mc["seed"]},
            "code": code(sp["family"]), "stores": {k: store_hash(folder, k) for k in keys},
            "test_range": {m: _range(m, m == h["market"], **_reads(filt)) for m in markets}}
    if waived:                                        # build lines that failed and were not asked (start(waive=): the pipeline's 2.5): written down, in the hash
        lock["waived"] = list(waived)
    lock = json.loads(json.dumps(lock))               # as it will read from disk (plain JSON: a number that is not is refused here)
    lock["hash"] = digest(lock)
    path = IS.write_lock(name, lock, root)
    IS.append_log(name, "locked", root, hash=lock["hash"], round=n, default=default)
    return _result(name, root, REC._json(path), already=False, saved=[w["path"] for w in worse if not w["skipped"]] + [str(path)], stores=worse)


def _result(name: str, root, lock: dict, already: bool, saved: list, stores: list) -> dict:
    """The answer of `lock`: lines 3.1 and 3.2, the hash, the default, the test range -- and, for an idea that was frozen
    before, whether the lock still matches the files on disk."""
    IS = api.ideastore()
    d = IS.idea_dir(name, root)
    h, w, c = lock["home"], lock["costs"]["worse"], lock["control"]
    rng = lock["test_range"][h["market"]]
    bad = verify(lock, REC._json(d / "spec.json"))
    nv, ns = len(lock["variants"]), len(lock["survivors"])
    who = "the 1 variant that makes money" if ns == 1 else f"the {ns} variants that make money"
    mine = lock["default_rule"] != J.TIE_RULE                    # the pipeline picked the default (freeze.run(default=))
    short = ("picked by the pipeline: the middle of the boxes at the floor with enough trades, by build net, never the best; it makes money on build and with worse fills"
             if mine else f"the middle of {who} on build and on build with worse fills; never the best")
    how = f"{short} ({ns} of {nv} variants make money on both)" if mine else f"the middle, by build net, of {who} on build and on build with worse fills ({ns} of {nv})"
    rows = [L._row("3.1", True, nv, None, f"saved: the rule ({lock['spec']['run']['family']}, home {REC._nice(h)}"
                   + (f", filter {h['filter'].replace('_', ' ', 1)}" if h["filter"] else "") + f"), the variant list ({nv} variants), the default variant "
                   f"{lock['default']} ({short}), the control "
                   f"({len(c['seeds'])} seeds, {c['draws']:,} draws, pool {c['pool']}) and the costs (worse fills: {RUN.worse_words(w)})", variants=nv, survivors=ns),
            L._row("3.2", True, None, None, f"from here nothing changes: lock {lock['hash']} of {lock['locked_utc']} holds version {lock['version']} -- a change "
                   "is a new version, back to the build, and its earlier read of the test days is marked as used"),
            *[L._row(x["line"], x["passed"], x["number"], x["need"], x["text"].split(" ", 2)[2]) for x in lock.get("box") or []]]
    lab, said, idea = REC._lab(name, root)
    notes = ([f"{h['market']}: {rng['no_tape']} of its {rng['sessions']} test sessions had no tape when the idea was frozen: the read builds what is missing "
              "from the archive before its pass"] if rng.get("no_tape") else [])
    for k, v in lock["stores"].items():             # a store of the freeze that other code wrote than the code that is frozen (the control pool: written once)
        wrote = (REC._json(Path(v["folder"]) / k / "run.json") or {}).get("code") or {}
        other = [f for f in wrote if lock["code"].get(f) not in (None, wrote[f])]
        if other:
            notes.append(f"{k} was written by an earlier {', '.join(other)} than the one frozen here: after a change to the code the earlier trade list is "
                         "reproduced exactly before a new run counts (line 1.6)")
    text = [f"FROZEN {'already' if already else 'now'}: {name} · lock {lock['hash']} · version {lock['version']} · round {lock['round']} · home {REC._nice(h)} · "
            f"store {Path(h['folder']).name}/{h['key']}", *[x["text"] for x in rows],
            f"DEFAULT VARIANT {lock['default']}: {how}",
            *([lock["prop"]["text"]] if lock.get("prop") else []),
            f"TEST RANGE {h['market']} {rng['start']} .. {rng['end']} ({rng['sessions']} sessions: "
            + ", ".join(f"{p['name']} {p['sessions']}" for p in rng["parts"]) + "), frozen: read ONCE, only by bp.py test",
            *[f"TEST RANGE {m} {r['start']} .. {r['end']} ({r['sessions']} sessions; a neighbor's market: the test reads the home table only)"
              for m, r in lock["test_range"].items() if m != h["market"] and r.get("end")],
            *([f"THE LOCK NO LONGER MATCHES THE FILES ON DISK: {'; '.join(bad)}"] if bad else [f"The lock matches the files on disk ({len(lock['stores'])} "
                                                                                             f"stores, {len(lock['code'])} code files)."] if already else []),
            *[f"NOTE: {x}." for x in notes], f"STATUS: {idea['status'].replace('_', ' ').upper()} · phase {idea['phase']}", *said]
    r = api.result("lock", name, status=idea["status"], phase=3, round=lock["round"], lines=rows, saved=saved, lock=lock, hash=lock["hash"], default=lock["default"],
                   survivors=ns, variants=nv, test_range=lock["test_range"], range={"market": h["market"], "start": rng["start"], "end": rng["end"]}, stores=stores,
                   already=already, matches=not bad, mismatches=bad, notes=notes, lab=lab, text="\n".join(text))
    r["next"] = REC._step(name, idea["status"], REC._last(name, root), root) if not bad else \
        "The lock no longer matches the files on disk: the test is refused until it does (put the files back; a change of the rule is a new version, back to the build)"
    return r


def lock(name, root=None, **kw) -> dict:
    """`bp.py lock <name>` in the foreground: start(), then run()."""
    return run(**start(name, root, **kw))


# ================================================================ the lock of an EARLY LOOK (oos.py: `bp.py test <name> --confirm --early-look`)

def early(name, root=None, out=None, draws=None) -> dict:
    """WHAT IS THERE, FROZEN AS IT IS, for the owner's early look at the test days (his decision of 2026-10-06: "warn, then
    run if I say yes") -> a lock in the shape of the freeze's, MARKED: early_look true, build_failed (the lines 2.x of its
    round that did not pass), code_check {missing, why: the freeze's own word when no code check stands for the home
    store}. For an idea that is NOT frozen; nothing is checked off and NOTHING IS RUN OR WRITTEN here (oos.start writes
    it beside the idea's files, just before the read is claimed -- never as the idea's lock.json: the idea stays unfrozen).
      the round          the latest one with a result (its card and settings as that round ran them)
      default, survivors the middle of the variants that made money on BUILD -- never the best; the worse-fills table of the
                         build days is the freeze's and is not run for a look -- or, when none made money, of all of them
      costs.worse        the worse fills the read itself runs (runner.worse_kw)      home.worse   None: no such build table
      test_range         the home market's, as the freeze reads it
    THE SAME IDEA, THE SAME EARLY LOOK: while nothing of it changed, the lock on file is the lock (its hash, its time), so a
    read that was claimed for it stays THE read. Refused: a frozen idea (its proper test is the one read); no build on
    file (run the build first); a round whose card was changed since; two filters; no home store; no judged variant."""
    IS, d, test = api.ideastore(), REC._carded(name, root), REC._test_run(root)
    if (d / "lock.json").exists():
        raise J.Refuse(f"{name} is frozen (lock.json): an early look is for an idea that is NOT frozen -- a frozen idea has its proper test, the one read "
                       f"(bp.py test {name} --confirm)")
    done = [n for n in IS.rounds(name, root) if (d / "rounds" / str(n) / "build.json").is_file()]
    if not done:
        raise J.Refuse(f"{name} has no build on file: there is nothing to look at early -- run the build first (bp.py build {name} --reason=\"why round 1 is run\")")
    n = done[-1]
    b, rspec = REC._json(d / "rounds" / str(n) / "build.json"), REC._json(d / "rounds" / str(n) / "spec.json")
    if b is None or rspec is None or b.get("ok") is False or b.get("dry_run"):
        raise J.Refuse(f"round {n} of {name} is no build that counts (its result or its settings do not read): there is nothing to look at early")
    spec = REC._spec(name, REC._json(d / "spec.json"))
    if {k: spec[k] for k in ("card", "run")} != {k: rspec.get(k) for k in ("card", "run")}:
        raise J.Refuse(f"the card of {name} was changed after round {n}: what is on file is not the rule its stores hold -- build it (a new round) or write "
                       "the card of that round again")
    plan, store = rspec["plan"], rspec["store"]
    sp = RUN.checked(REC.engine(rspec, plan, store)[0])
    h, filt, folder = plan["home"], REC.rule_filter(plan), _folder(out)
    f = T.filter_of(sp, filt)
    u = T.bp_unit(sp, h["market"], h["bar"], h["session"], "", f)
    key = u["key"]
    st, _ = T._open(folder, key)
    T._labels(st, u)
    rows = J.table(st, u)
    ids = J.table_stats(rows)["ids"]
    if not ids:
        raise J.Refuse(f"{u['addr']}: no judged variant on the build days: there is nothing to look at")
    default, surv = REC.middle(rows, ids)
    rule = "the middle of the variants that made money on BUILD (an early look runs no worse-fills table of the build days): " + J.TIE_RULE
    if default is None:
        by = {r["id"]: r for r in rows}
        order = sorted(ids, key=lambda c: (round(by[c]["net"], 2), by[c]["vi"], by[c]["xi"]))
        default, rule = order[(len(order) - 1) // 2], "no variant made money on build: the middle of ALL its variants, by build net and variant order"
    marks = {x.get("line"): x.get("passed") for x in b.get("lines") or [] if isinstance(x, dict)}
    try:
        _checked(d, folder, key, sp["family"])
        why = None
    except J.Refuse as e:
        why = str(e)
    two = bool(RUN._blocks().BASES[sp["family"]][2])
    from . import propodds                          # (phase 5's module: loaded here, never with this one -- cli.py)
    pool, ctl, mc, costs = RUN.pool_key(h["market"], h["bar"]), R.template("control"), R.template("montecarlo"), R.template("costs")
    keys = [key, pool] + ([T.bp_unit(sp, h["market"], h["bar"], h["session"])["key"]] if f else [])
    lock = {"name": name, "version": rspec.get("version", 1), "locked_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "round": n,
            "store": store, "spec": {k: rspec[k] for k in ("name", "version", "card", "run") if k in rspec}, "plan": plan,
            "home": {**{k: h[k] for k in ("market", "session", "bar", "table")}, "unit": u["addr"], "uid": u["uid"], "key": key, "folder": str(folder),
                     "filter": filt, "worse": None},
            "variants": list(ids), "default": default, "survivors": list(surv), "default_rule": rule,
            "box": [{k: (None if isinstance(x[k], float) and x[k] in (float("inf"), float("-inf")) else x[k]) for k in ("line", "passed", "number", "need", "text")}
                    for x in (fn(T.box(st, u, default, st["meta"].get("days") or None)) for fn in L.BOX)],      # read, never enforced: a look checks nothing off
            "prop": propodds.look(J.cellx(st, default, h["session"], u), T.build_days(u, st["meta"].get("days") or None)),      # shown, as at the freeze
            "build": {"avg_trade": T.avg_trade(st, u, ids) if test.get("build_avg_trade") is None else float(test["build_avg_trade"])},
            "costs": {"normal": costs["normal"], "worse": {**RUN.worse_kw(two), "two_sided": two}},
            "control": {"kind": ctl["kind"], "pool": pool, "seeds": list(range(1, ctl["seeds"] + 1)), "draws": int(draws or ctl["draws"]),
                        "draw_seed": {"build": J.seed_of(u["uid"], f"{RUN.PERIOD}-c1"), "test": J.seed_of(u["uid"], "test-c1")}},
            "montecarlo": {"runs": mc["runs"], "seed": mc["seed"]},
            "code": code(sp["family"]), "stores": {k: store_hash(folder, k) for k in keys},
            "test_range": {h["market"]: _range(h["market"], True, **_reads(filt))},
            api.EARLY_LOOK: True, "build_failed": [k for k in IS.LINES[2] if marks.get(k, False) not in (True, None)],      # failed, or not in the result at all
            "code_check": {"missing": why is not None, "why": why}}
    lock = json.loads(json.dumps(lock))               # as it will read from disk
    lock["hash"] = digest(lock)
    was = REC._json(d / api.EARLY_LOOK / "lock.json")
    same = lambda x: {k: v for k, v in x.items() if k not in ("locked_utc", "hash")}  # noqa: E731
    return was if was is not None and same(was) == same(lock) else lock
