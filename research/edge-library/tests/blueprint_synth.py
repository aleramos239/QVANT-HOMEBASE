"""Hand-made reads and ideas for the tests of phases 5 and 6 (test_blueprint_propodds.py, test_blueprint_evalcard.py).
NOTHING HERE IS MARKET DATA: no tape is read and no engine run is made. Every trade is typed by a test, dated by hand on test
days (2025-07-01 on -- the days phase 5 reads), and written with the library's own store writer (library.write_unit) into a
temp folder, in the shape the real freeze and the real read leave things (freeze.py: lock.json; oos.py and runner.run_test:
test.json and the stores of the read), for an idea whose saved results say PROVEN ON HISTORY.

    no_engine()                          while it is open, every way into a tape or a calendar of the engine raises
    trade(day, micro_net, micro_mae)     a 1-contract trade row whose net at ONE MICRO is exactly `micro_net` dollars
    store(folder, key, cells, ...)       a store of the test days of hand-made cells {cell id: [trades]} -> its folder
    proven(IS, root, name, folder, ...)  an idea folder up to a passed out-of-sample test: its lock, its read, its stores
"""
from __future__ import annotations

import contextlib
import datetime as dt
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import rules as R  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402

COUNT = {2: 9, 4: 7}                                 # the law's lines of the build and of the test
SPAN = ("2025-07-01", "2025-08-29")                  # a short hand-made "test range": 44 weekdays, each a session day here
LOCK = "feedc0de00000001"                            # the hash of a hand-made lock
PERIOD = "bp_test"                                   # what a store of the test days says its period is (any name but the build's)
CARD = {"why": "A hand-made idea for the tests of phases 5 and 6.", "loser": "nobody: its trades are typed by hand",
        "home": {"market": "NQ", "session": "nyam", "bar": "15"}, "neighbors": ["midday"], "not_here": "the Asian session",
        "main_setting": "or_min", "sides": "both", "sides_why": "hand-made"}
RUN = {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}


@contextlib.contextmanager
def no_engine():
    """Phases 5 and 6 run nothing and open no tape: every way into the engine's data raises while the block runs."""
    names = ("run_many", "load_tape", "sessions", "load_daily", "build_tapes")
    keep = {n: getattr(S, n) for n in names}

    def stop(*a, **k):
        raise AssertionError("the engine was asked for data")

    for n in names:
        setattr(S, n, stop)
    try:
        yield
    finally:
        for n, f in keep.items():
            setattr(S, n, f)


def weekdays(start: str = SPAN[0], end: str = SPAN[1]) -> list:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return [(a + dt.timedelta(i)).isoformat() for i in range((b - a).days + 1) if (a + dt.timedelta(i)).weekday() < 5]


def ms(day: str, at: str) -> int:
    """A New York clock time of a day -> epoch milliseconds."""
    return int(dt.datetime.combine(dt.date.fromisoformat(day), dt.time.fromisoformat(at), tzinfo=S.ET).timestamp() * 1000)


def trade(day: str, micro_net: float, micro_mae: float = 0.0, at: str = "09:45", mins: float = 10, side: str = "long", reason: str = "tp") -> dict:
    """A trade row at 1 contract (the stores' unit) whose net at ONE micro is exactly `micro_net` and whose worst open point at
    one micro is `micro_mae` dollars -- the library's micro cost model read backwards: micro net = (net + the contract's
    commission) / 10 - the micro's commission."""
    div = R.template("sizes")["micros_per_contract"]
    a = ms(day, at)
    return {"date": day, "entry_ms": a, "exit_ms": a + int(mins * 60_000), "net": div * (micro_net + LB.MICRO_RT_USD) - LB.COMM_RT, "mae_usd": div * micro_mae,
            "side": side, "exit_reason": reason, "entry_price": 20000.0, "sl": 19980.0}


def store(folder, key: str, cells: dict, span=SPAN, calendar=None, name=None, lock=LOCK, **meta) -> Path:
    """A store of the test days of hand-made cells, {cell id: [trades]}, as runner.run_test writes one: its range and its
    period, the session days that were "replayed" (`calendar`; default: every weekday of the range) and the read it
    belongs to (the idea, its lock)."""
    cal = weekdays(*span) if calendar is None else list(calendar)
    grid = [{"id": cid, "variant": {"v": i}, "exit": {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}, "vi": i, "xi": 0} for i, cid in enumerate(cells)]
    res = [{"trades": sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])), "sessions": len(cal), "used": len(cal), "skipped": [], "no_trade": [], "elapsed_s": 0.0,
            "meta": {"inputs": {}, "engine": "hand-made", "root": "NQ", "range": {"start": span[0], "end": span[1], "holdout": True, "period": PERIOD}}}
           for rows in cells.values()]
    return LB.write_unit(key, {"family": "orb", "idea": name, "tf": "15", "sessions": ["nyam"], "sess_instance": "nyam", "period": PERIOD, "calendar": cal,
                               "read": {"name": name, "version": 1, "lock": lock}, **meta}, grid, res, Path(folder))


def lines(phase: int, fail=(), na=()) -> list:
    out = []
    for i in range(1, COUNT[phase] + 1):
        k = f"{phase}.{i}"
        passed = None if k in na else k not in fail
        out.append({"line": k, "passed": passed, "number": 1.0, "need": 0.5, "text": f"{k} {'n/a ' if passed is None else 'PASS' if passed else 'FAIL'} hand-made"})
    return out


def result(command: str, phase: int, name: str, **more) -> dict:
    """A command's result as the toolkit saves it (toolkit plan, section 8)."""
    return {"ok": True, "command": command, "name": name, "status": None, "phase": phase, "round": None, "lines": lines(phase, more.pop("fail", ()), more.pop("na", ())),
            "text": "", "next": f"after {command}", "job": None, "saved": [], "error": None, **more}


def proven(IS, root, name: str, folder=None, cells=None, worse=None, survivors=None, test_fail=(), span=SPAN, **odd) -> Path:
    """An idea folder as the toolkit leaves it after a PASSED out-of-sample test (cells = {variant: [its test-period trades]}):
      card.md, spec.json, rounds/1    the card and a build with every line passed
      lock.json                       the freeze: home, variants (the cells), survivors (default: all of them), test_range, hash
      <folder>/<name>-NQ-tf15-nyam-test, ...-test-worse     the two stores of the read (`worse`: the trades with worse fills;
                                      default: the same trades), written once a name
      test.json                       every 4.x line passed (test_fail = the ones that failed), the lock's hash, the stores
    cells None = a LEAD: built, never frozen, never tested. `odd` makes it wrong on purpose: stores=False (the test result
    names no store), written=False (the stores are not on disk), store_lock / store_span (the stores are another lock's, or
    of another range), test_lock (the test result is of another lock), locked (the lock's variant list)."""
    IS.create(name, root, exist_ok=True)
    IS.write_card(name, f"# {name} -- idea card (hand-made)\n", root)
    IS.write_spec(name, {"name": name, "version": 1, "card": CARD, "run": RUN}, root)
    d = IS.idea_dir(name, root)
    if not (d / "rounds" / "1" / "build.json").exists():
        IS.write_reason(name, 1, "hand-made", root)
        IS.write_build(name, 1, result("build", 2, name, na=("2.7",), round=1), root)
    if cells is None:
        return d
    key = f"{name}-NQ-tf15"
    keys = {"table": f"{key}-nyam-test", "worse": f"{key}-nyam-test-worse"}
    if odd.get("written", True) and not (Path(folder) / keys["table"] / "run.json").exists():
        for which, rows in (("table", cells), ("worse", worse or cells)):
            store(folder, keys[which], rows, odd.get("store_span", span), name=name, lock=odd.get("store_lock", LOCK))
    IS.write_lock(name, {"name": name, "version": 1, "round": 1, "store": name, "variants": list(odd.get("locked", cells)), "default": next(iter(cells)),
                         "survivors": list(cells if survivors is None else survivors), "test_range": {"NQ": {"start": span[0], "end": span[1]}},
                         "home": {**CARD["home"], "table": "NQ-tf15-nyam", "key": key, "folder": str(folder), "filter": None, "worse": f"{key}-nyam-worse"},
                         "hash": LOCK}, root)
    rows = [{"key": keys[which], "kind": kind, "root": "NQ", "tf": "15", "path": str(Path(folder) / keys[which]), "skipped": False, "ok": True}
            for which, kind in (("table", "unit"), ("worse", "worse"))]
    IS.write_test(name, result("test", 4, name, fail=test_fail, lock=odd.get("test_lock", LOCK), range={"start": span[0], "end": span[1]},
                               **({"stores": rows} if odd.get("stores", True) else {})), root)
    return d
