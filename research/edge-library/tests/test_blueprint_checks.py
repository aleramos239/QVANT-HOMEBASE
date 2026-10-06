"""LOCK of the code check (blueprint/checks.py, `bp.py code-check`): the phase 1 lines of BLUEPRINT.md section 2 on a store or
on a plain trades file -- toolkit plan, step 7 (its code-check half).

(a) A CLEAN hand-made trade list passes 1.1-1.4. Each PLANTED bad trade is caught by its own line and by no other: an entry
    outside the stated window (1.1), an overnight hold, a late exit on a half day, two positions at once (1.2), one trade
    too many on a day (1.3), a winner far from its target, a stop-out that cost less than its stop (1.4). A stop that was
    gapped is LISTED and passes: the fill law makes those.
(b) 1.5 names the same 10 trades for the same list (the first 5 and 5 drawn with the fixed seed of rules.json) and is true
    only once the owner has looked; 1.6 holds an earlier trade list against the new one, field for field.
(c) The same through a STORE (the library's format): the stated sessions, the maximum per session and day and the stops and
    targets are read from the store itself; a stop that is not the stated points is caught.
(d) THE ENGINE'S OWN STORES on disk pass 1.1-1.4 (old build days and 2024, read-only), a family with its own target among
    them; the counts are those of run_menus.hold_checks.
(e) THE COMMAND as the connector writes it (`code-check <name> [--store=K | --trades=FILE] [--looked] --root=DIR --json`): the
    result is saved as the idea's check.json when the idea is on file (homebase.ideastore.write_check) and only printed
    when it is not; the owner's later `--looked` reads the same source again. And the seal: any day on or after 2025-07-01
    is refused, in a file, in a store's range, in a store's trades.
No simulation; hand-made files live in a temp folder, and so do the idea folder and the Lab drafts (HOMEBASE_IDEAS_ROOT,
HOMEBASE_DRAFTS_DIR): nothing touches ~/.homebase. Dollars appear only where line 1.4 names them (one trade at a time).

  pytest tests/test_blueprint_checks.py -q     (seconds)          python tests/test_blueprint_checks.py     one line per test
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import random
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import checks as CH  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import rules as R  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

PV, TICK, COMM = 20.0, 0.25, 4.0                              # NQ: dollars a point, the tick, the round-turn commission
DAYS = ["2022-03-15", "2022-03-16", "2022-03-17", "2022-03-18", "2022-03-21", "2022-03-22", "2022-03-23", "2022-03-24", "2022-11-25",
        "2024-05-14", "2025-06-27", "2025-06-30"]            # build days; 2022-11-25 is a half day; the last one ends the build
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")     # plan section 8
LINES = ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
STATED = dict(market="NQ", sessions=["nyam"], max_per_day=2)
HOME = Path.home() / ".homebase"
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="bp_checks_")}
_T["dir"] = Path(_T["keep"].name).resolve()
os.environ["HOMEBASE_IDEAS_ROOT"] = str(_T["dir"] / "ideas")           # never the real ~/.homebase: the idea folder of this module ...
os.environ["HOMEBASE_DRAFTS_DIR"] = str(_T["dir"] / "drafts")          # ... and its Lab drafts


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


BEFORE = {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies")}


def tmp() -> Path:
    return _T["dir"]


def ms(day: str, at: str) -> int:
    return S.et_ns(dt.date.fromisoformat(day), at) // 1_000_000


def tr(day: str, at: str = "09:35:00", held: int = 20, side: str = "long", how: str = "tp", stop: float = 10.0, tgt: float = 20.0, **over) -> dict:
    """One hand-made NQ trade in the engine's row format: a 10-point stop and a 20-point target by default. how = 'tp' (it
    ends at its target, at the limit price) | 'sl' (at its stop, one tick through the level, as the fill law has it) |
    'time' (closed by the clock 3 points in profit, between the two)."""
    sd, px = (1 if side == "long" else -1), 15000.0
    sl, tp = px - sd * stop, px + sd * tgt
    x = tp if how == "tp" else sl - sd * TICK if how == "sl" else px + sd * 3.0
    gross = sd * (x - px) * PV
    e = ms(day, at)
    return {"date": day, "side": side, "qty": 1, "entry_price": px, "exit_price": x, "exit_reason": how, "order_price": None, "sl": sl, "tp": tp,
            "gross": gross, "commission": COMM, "net": gross - COMM, "mae_usd": 0.0, "entry_ms": e, "exit_ms": e + held * 60_000, **over}


def clean() -> list:
    """12 trades on 12 build days, all entered in the New York morning: 4 end at the target, 6 at the stop, one is held to
    15:58 and one to 13:13 on a half day."""
    rows = [tr(d, side="long" if i % 2 else "short", how=("tp", "sl", "tp", "sl")[i % 4]) for i, d in enumerate(DAYS)]
    rows[4] = tr(DAYS[4], at="10:30:00", how="time", exit_ms=ms(DAYS[4], "15:58:02"))
    rows[8] = tr(DAYS[8], at="09:40:00", how="time", exit_ms=ms(DAYS[8], "13:13:01"))
    return rows


def saved(rows: list, name: str) -> Path:
    p = tmp() / f"{name}.json"
    p.write_text(json.dumps(rows))
    return p


def check(rows, name: str = "list", **kw) -> dict:
    """The code check of a hand-made list, saved as <name>.json and checked under that name."""
    return A.code_check(name, trades=saved(rows, name), **{**STATED, **kw})


def by(r: dict) -> dict:
    return {x["line"]: x for x in r["lines"]}


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert word in str(e), str(e)
        return str(e)
    raise AssertionError(f"not refused ({word})")


# ================================================================ (a) a clean list, and each planted bad trade

def test_a_clean_list_passes():
    r = check(clean(), looked=True)
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "saved", "error")] == [True, "code-check", "list", None, 1, None, None, [], None]
    assert [x["line"] for x in r["lines"]] == LINES and all(x["text"].startswith(x["line"] + " ") for x in r["lines"])
    assert [x["passed"] for x in r["lines"]] == [True, True, True, True, True, None] and r["passed"] is True and r["failed"] == [] and r["not_applicable"] == ["1.6"]
    b = by(r)
    assert b["1.1"]["text"] == "1.1 PASS every one of the 12 trades is entered inside the stated window (sessions nyam)" and (b["1.1"]["number"], b["1.1"]["need"]) == (0, 0)
    assert b["1.2"]["text"] == "1.2 PASS one position at a time and flat by 15:58 ET (13:13 on half days): no overlap and no late exit in 12 trades"
    assert (b["1.2"]["overlaps"], b["1.2"]["late"], b["1.2"]["need"]) == (0, 0, R.need("1.2"))
    assert b["1.3"]["text"] == "1.3 PASS never more than the stated maximum of 2 a day: the most is 1 (12 trades in 1 list)"
    assert (b["1.3"]["number"], b["1.3"]["need"]) == (1, 2)
    assert b["1.4"]["text"] == ("1.4 PASS 4 trades ended at the target and paid about it, 6 at the stop and cost about it (within 2 ticks = $10); "
                                "listed: 2 closed by the clock or another exit")
    assert (b["1.4"]["at_target"], b["1.4"]["at_stop"], b["1.4"]["gapped"], b["1.4"]["other"], b["1.4"]["number"], b["1.4"]["need"]) == (4, 6, 0, 2, 0, 0)
    assert b["1.4"]["tolerance_usd"] == R.rule("1.4")["also"]["within_ticks"] * TICK * PV == 10.0 and b["1.4"]["exceptions"] == []
    assert b["1.6"]["text"] == "1.6 n/a  no earlier trade list was given (after a change to the code: --same-as <the earlier store or file>)"
    assert r["source"] == {"kind": "trades", "where": str(tmp() / "list.json"), "market": "NQ", "lists": 1, "trades": 12}
    assert json.loads(json.dumps(r, default=lambda x: 1 / 0)) == json.loads(json.dumps(r))
    # the same list in any order of the file, as {"trades": [...]} and with the window as clock times
    rows = clean()
    random.Random(3).shuffle(rows)
    assert check(rows, "shuffled", looked=True)["lines"] == r["lines"]
    p = tmp() / "wrapped.json"
    p.write_text(json.dumps({"trades": clean()}))
    assert A.code_check("list", trades=p, looked=True, **STATED)["lines"] == r["lines"]
    w = check(clean(), looked=True, sessions=None, window="09:30-11:00")
    assert by(w)["1.1"]["text"] == "1.1 PASS every one of the 12 trades is entered inside the stated window (09:30-11:00 ET)" and w["passed"] is True
    # the counts are those of run_menus.hold_checks
    assert RM.hold_checks([{"trades": clean()}], "NQ") == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}


def test_each_planted_bad_trade_is_caught_by_its_own_line():
    def only(rows, line, word, **kw):
        r = check(clean() + rows, "planted", looked=True, **kw)
        x = by(r)[line]
        assert r["failed"] == [line] and r["passed"] is False and x["passed"] is False and word in x["text"], (line, r["failed"], x["text"])
        assert r["ok"] is True                              # a failed line is an answer, not a refusal
        return x

    # 1.1 an entry outside the stated window (12:15 is midday, the idea states the New York morning)
    x = only([tr("2022-03-25", at="12:15:00")], "1.1", "1 of the 13 trades is entered outside the stated window (sessions nyam)")
    assert x["number"] == 1 and x["exceptions"] == [{"list": "planted", "trade": 9, "date": "2022-03-25", "entry_et": "12:15:00", "what": "entered in session mid"}]
    x = only([tr("2022-03-25", at="15:58:30", exit_ms=ms("2022-03-25", "15:58:50"))], "1.1", "1 of the 13 trades is entered outside")
    assert x["exceptions"][0]["what"] == "entered outside every session"
    only([tr("2022-03-25", at="11:00:00")], "1.1", "09:30-11:00 ET", sessions=None, window="09:30-11:00")      # the window's end is not inside it
    # 1.2 an overnight hold; a late exit on a half day; two positions at once
    x = only([tr("2022-03-28", how="time", exit_ms=ms("2022-03-29", "10:00:00"))], "1.2", "1 late exit")
    assert (x["overlaps"], x["late"], x["number"]) == (0, 1, 1) and x["exceptions"][0]["what"] == "still open at 15:59 ET of its trade date (closed 2022-03-29 10:00:00 ET)"
    x = only([tr("2023-07-03", how="time", exit_ms=ms("2023-07-03", "13:14:05"))], "1.2", "1 late exit")
    assert x["exceptions"][0]["what"] == "still open at 13:14 ET of its trade date, a half day (closed 2023-07-03 13:14:05 ET)"
    assert check(clean() + [tr("2022-03-28", how="time", exit_ms=ms("2022-03-28", "13:14:05"))], "ok", looked=True)["passed"] is True      # not a half day
    assert check(clean() + [tr("2022-03-28", how="time", exit_ms=ms("2022-03-28", "15:58:59"))], "ok", looked=True)["passed"] is True      # inside the 15:58 minute
    only([tr("2022-03-28", how="time", exit_ms=ms("2022-03-28", "15:59:00"))], "1.2", "1 late exit")
    x = only([tr("2022-03-25", held=60), tr("2022-03-25", at="09:50:00", held=10)], "1.2", "1 overlap")
    assert (x["overlaps"], x["late"]) == (1, 0) and x["exceptions"][0]["what"] == "entered while trade 9 was still open" and x["exceptions"][0]["trade"] == 10
    assert check(clean() + [tr("2022-03-25", held=15), tr("2022-03-25", at="09:50:00", held=10)], "ok", looked=True)["passed"] is True     # one ends as the next begins
    bad = clean() + [tr("2022-03-28", how="time", exit_ms=ms("2022-03-29", "10:00:00")), tr("2022-03-25", held=60), tr("2022-03-25", at="09:50:00", held=10),
                     tr("2022-03-30", at="15:58:30", exit_ms=ms("2022-03-30", "15:58:50"))]       # 15:58 on: outside every session
    mine = by(check(bad, "all", looked=True))
    assert {"exit_after_day_flat": mine["1.2"]["late"], "overlap_in_session": mine["1.2"]["overlaps"], "entry_in_no_session": mine["1.1"]["number"]} == \
        RM.hold_checks([{"trades": bad}], "NQ") == {"exit_after_day_flat": 1, "overlap_in_session": 1, "entry_in_no_session": 1}
    # 1.3 one trade too many on a day
    three = [tr("2022-03-25", at=t, held=5) for t in ("09:35:00", "09:45:00", "09:55:00")]
    x = only(three, "1.3", "the most is 3 (need at most 2): 1 over")
    assert (x["number"], x["need"], x["exceptions"]) == (3, 2, [{"list": "planted", "date": "2022-03-25", "what": "3 trades"}])
    assert check(clean() + three, "ok", looked=True, max_per_day=3)["passed"] is True
    x = by(check([], "empty", looked=True))["1.3"]
    assert x["passed"] is False and x["text"] == "1.3 FAIL no trade at all: a rule that never trades is not what any idea implies"
    # 1.4 a winner far from its target; a stop-out that cost less than its stop; a gapped stop is listed and passes
    x = only([tr("2022-03-25", how="tp", net=196.0)], "1.4", "1 trade is off")
    assert x["exceptions"] == [{"list": "planted", "trade": 9, "date": "2022-03-25", "entry_et": "09:35:00", "ended": "tp", "net": 196.0, "stop_usd": 200.0,
                                "target_usd": 400.0, "what": "ended at its target and paid $196, not about the target of $400"}]
    x = only([tr("2022-03-25", how="tp", net=420.0)], "1.4", "1 trade is off")
    x = only([tr("2022-03-25", how="sl", net=-104.0)], "1.4", "1 trade is off")
    assert x["exceptions"][0]["what"] == "ended at its stop and cost $104, less than about the stop of $200"
    r = check(clean() + [tr("2022-03-25", how="sl", net=-(200.0 + 6 * TICK * PV + COMM))], "gap", looked=True)
    x = by(r)["1.4"]
    assert r["passed"] is True and (x["gapped"], x["at_stop"], x["number"]) == (1, 6, 0) and "1 stop gapped (the worst cost $34 more than its stop)" in x["text"]
    assert x["exceptions"][0]["what"] == "its stop was gapped: it cost $234 against a stop of $200"
    # many exceptions: the count is whole, the list is the worst SHOWN
    days = [d.isoformat() for d in (dt.date(2023, 1, 2) + dt.timedelta(n) for n in range(45)) if d.weekday() < 5][:30]
    x = by(check(clean() + [tr(d, how="sl", net=-(230.0 + 5 * i)) for i, d in enumerate(days)], "gaps", looked=True))["1.4"]
    assert (x["passed"], x["gapped"], x["exceptions_total"], len(x["exceptions"])) == (True, 30, 30, CH.SHOWN) and x["exceptions"][0]["net"] == -375.0
    for net in (-(200.0 + TICK * PV + COMM), -(200.0 + 2 * TICK * PV), -190.0, 390.0, 410.0):       # inside 2 ticks either way
        assert by(check(clean() + [tr("2022-03-25", how="sl" if net < 0 else "tp", net=net)], "ok", looked=True))["1.4"]["gapped"] == 0
    assert check(clean() + [tr("2022-03-25", how="tp", net=410.0)], "ok", looked=True)["passed"] is True
    two = {**tr("2022-03-25", how="sl"), "qty": 2, "net": -(400.0 + 2 * TICK * PV + 2 * COMM)}      # 2 contracts: the stop and "about" are twice as many dollars
    x = by(check(clean() + [two], "ok", looked=True))["1.4"]
    assert (x["passed"], x["at_stop"], x["gapped"]) == (True, 7, 0) and by(check(clean() + [{**two, "net": -430.0}], "ok", looked=True))["1.4"]["gapped"] == 1
    # without the exit reason the way a trade ended is read from what it paid; a winner beyond its target is still caught
    bare = [{k: v for k, v in t.items() if k != "exit_reason"} for t in clean()]
    x = by(check(bare, "bare", looked=True))["1.4"]
    assert (x["passed"], x["at_target"], x["at_stop"], x["other"]) == (True, 4, 6, 2)
    x = by(check(bare + [{k: v for k, v in tr("2022-03-25", net=900.0).items() if k != "exit_reason"}], "bare2", looked=True))["1.4"]
    assert x["passed"] is False and x["exceptions"][0]["what"] == "paid $900, more than about its target of $400"
    # what a list does not state cannot be read: the line does not apply, and the phase is not passed on it
    thin = [{k: t[k] for k in ("date", "side", "entry_ms", "exit_ms", "net")} for t in clean()]
    r = A.code_check("thin", trades=saved(thin, "thin"), market="NQ", looked=True)
    assert [x["passed"] for x in r["lines"]] == [None, True, None, None, True, None] and r["passed"] is False and r["not_applicable"] == ["1.1", "1.3", "1.4", "1.6"]
    assert "give --sessions or --window" in by(r)["1.1"]["text"] and "give --max-per-day" in by(r)["1.3"]["text"] and "no stop and target" in by(r)["1.4"]["text"]


# ================================================================ (b) 1.5 the ten trades for the chart, 1.6 the earlier list

def test_line_1_5_the_ten_trades_and_the_owner_looking():
    need = R.need("1.5")
    assert need == {"trades": 10, "first": 5, "random": 5} and isinstance(R.rule("1.5")["also"]["seed"], int)
    r, again = check(clean()), check(clean())
    x = by(r)["1.5"]
    picks = [t["trade"] for t in r["look"]]
    rest = sorted(np.random.default_rng(R.rule("1.5")["also"]["seed"]).choice(np.arange(6, 13), 5, replace=False).tolist())
    assert picks == [1, 2, 3, 4, 5] + rest and picks == [t["trade"] for t in again["look"]] and len(set(picks)) == 10
    assert x["passed"] is False and (x["number"], x["need"]) == (0, 10) and r["failed"] == ["1.5"] and r["passed"] is False
    assert x["text"] == ("1.5 FAIL the owner has not looked yet: look at these 10 trades on the chart (the first 5 and 5 at random), then run it again with "
                         "--looked: " + ", ".join(f"#{n}" for n in picks))
    assert r["look"][0] == {"trade": 1, "list": "list", "date": "2022-03-15", "entry_et": "09:35:00", "exit_et": "09:55:00", "side": "short", "session": "nyam", "ended": "tp"}
    assert [t["date"] for t in r["look"][:5]] == DAYS[:5] and all(set(t) == set(r["look"][0]) for t in r["look"])
    assert all(f"#{t['trade']:<3d} {t['date']} {t['entry_et']} -> {t['exit_et']} ET  {t['side']}" in r["text"] for t in r["look"])
    ok = by(check(clean(), looked=True))["1.5"]
    assert ok["passed"] is True and ok["number"] == 10
    assert ok["text"] == "1.5 PASS the owner looked at 10 trades on the chart (the first 5 and 5 at random): " + ", ".join(f"#{n}" for n in picks)
    rows = clean()                                          # the numbers follow the entry time, not the order of the file
    random.Random(5).shuffle(rows)
    assert check(rows, "shuffled")["look"] == [{**t, "list": "shuffled"} for t in r["look"]]
    assert [t["trade"] for t in check(clean()[:10], "ten")["look"]] == list(range(1, 11))
    few = by(check(clean()[:7], "few", looked=True))["1.5"]
    assert few["passed"] is False and "only 7 trades" in few["text"]


def test_line_1_6_the_earlier_trade_list_is_reproduced_exactly():
    a = saved(clean(), "earlier")
    r = check(clean(), "now", looked=True, same_as=a)
    x = by(r)["1.6"]
    assert x["passed"] is True and (x["number"], x["need"]) == (0, 0) and r["not_applicable"] == [] and r["passed"] is True
    assert x["text"] == "1.6 PASS the earlier trade list is reproduced exactly: 12 trades in 1 list (earlier.json)"
    rows = clean()
    rows[3]["net"] += 0.01                                  # one cent on one trade
    x = by(check(rows, "now", looked=True, same_as=a))["1.6"]
    assert x["passed"] is False and x["number"] == 1 and "1 of 1 list differs" in x["text"] and "trade 4" in x["text"] and "net" in x["text"]
    rows = clean()
    rows[6]["exit_ms"] += 1000
    assert "trade 7" in by(check(rows, "now", looked=True, same_as=a))["1.6"]["text"]
    x = by(check(clean()[:-1], "now", looked=True, same_as=a))["1.6"]
    assert x["passed"] is False and "12 trades earlier, 11 now" in x["text"]
    refused(lambda: check(clean(), "now", same_as=tmp() / "no_such_file.json"), "no_such_file.json")


# ================================================================ (c) the same through a store

EXITS = {"pts10-r2": {"stop_mode": "pts", "stop_val": 10.0, "tgt_r": 2.0}, "pts10-r0": {"stop_mode": "pts", "stop_val": 10.0, "tgt_r": 0.0}}


def no_target(rows: list) -> list:
    """The clean list as a cell without a target runs it: the stops and the clock only."""
    return [{**t, "tp": None} for t in rows if t["exit_reason"] != "tp"]


def store(key: str, cells: dict, end: str = "2025-06-30", sessions=("nyam",), max_tr: int = 2, folder: str = "stores") -> Path:
    """A store in the library's format (library.write_unit) from hand-made trade lists, one per cell."""
    grid = [{"id": cid, "vi": 0, "xi": i, "variant": {}, "exit": EXITS[cid]} for i, cid in enumerate(cells)]
    res = [{"trades": sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])), "sessions": 12, "used": 12, "skipped": [], "no_trade": [], "elapsed_s": 0.0,
            "skipped_by_error": 0, "meta": {"inputs": {"tf": "5", "sess": "+".join(sessions), "max_tr": max_tr, "hold_to": "day", **EXITS[cid]}, "engine": "hand-made",
                                            "root": "NQ", "range": {"start": "2021-09-22", "end": end, "holdout": True, "period": "bp_build"}}}
           for cid, rows in cells.items()]
    return LB.write_unit(key, {"family": "hand", "idea": "hand", "tf": "5", "sessions": list(sessions), "stage": "bp_build", "period": "bp_build",
                               "hold_to": "day"}, grid, res, tmp() / folder)


def test_a_store_is_read_with_what_it_states():
    p = store("hand-NQ-tf5", {"pts10-r2": clean(), "pts10-r0": no_target(clean())})
    r = A.code_check("hand", store=p, looked=True)
    b = by(r)
    assert [x["passed"] for x in r["lines"]] == [True, True, True, True, True, None] and r["passed"] is True and r["name"] == "hand"
    assert r["source"] == {"kind": "store", "where": str(p), "market": "NQ", "lists": 2, "trades": 20}      # 12, and the 8 of them without a target exit
    assert b["1.1"]["text"] == "1.1 PASS every one of the 20 trades is entered inside the stated window (sessions nyam)"
    assert b["1.3"]["text"] == "1.3 PASS never more than the stated maximum of 2 a session and day: the most is 1 (20 trades in 2 lists)"
    assert (b["1.4"]["at_target"], b["1.4"]["at_stop"], b["1.4"]["other"], b["1.4"]["gapped"]) == (4, 12, 4, 0)
    assert [t["list"] for t in r["look"]] == ["pts10-r2"] * 10 and r["look"][0]["trade"] == 1 and "of pts10-r2" in b["1.5"]["text"]
    assert [t["list"] for t in A.code_check("hand", store=p, cell="pts10-r0")["look"]] == ["pts10-r0"] * 8
    refused(lambda: A.code_check("hand", store=p, cell="no_such_cell"), "no_such_cell")
    assert A.code_check("hand", store=p, looked=True, sessions=["mid"])["failed"] == ["1.1"]      # what the caller states wins over the store
    # a store is named by its path, or by its KEY in the store folder (--store=K; the folder is runs_bp/ unless told)
    assert A.code_check("hand", store=str(p), looked=True)["lines"] == r["lines"]
    assert A.code_check("hand", store="hand-NQ-tf5", out=tmp() / "stores", looked=True)["lines"] == r["lines"]
    refused(lambda: A.code_check("hand", store="hand-NQ-tf5", looked=True), "hand-NQ-tf5")          # not in runs_bp/, not under the library

    def only(key, rows, line, word, **kw):
        q = A.code_check("hand", store=store(key, {"pts10-r2": clean() + rows, "pts10-r0": no_target(clean())}, **kw), looked=True)
        x = by(q)[line]
        assert q["failed"] == [line] and word in x["text"], (key, q["failed"], x["text"])
        return x

    x = only("p11", [tr("2022-03-25", at="12:15:00")], "1.1", "1 of the 21 trades is entered outside")
    assert x["exceptions"][0] == {"list": "pts10-r2", "trade": 9, "date": "2022-03-25", "entry_et": "12:15:00", "what": "entered in session mid"}
    only("p12a", [tr("2022-03-28", how="time", exit_ms=ms("2022-03-29", "10:00:00"))], "1.2", "1 late exit")
    only("p12b", [tr("2022-03-25", held=60), tr("2022-03-25", at="09:50:00", held=10)], "1.2", "1 overlap")
    x = only("p13", [tr("2022-03-25", at=t, held=5) for t in ("09:35:00", "09:45:00", "09:55:00")], "1.3", "the most is 3 (need at most 2): 1 over")
    assert x["exceptions"] == [{"list": "pts10-r2", "date": "2022-03-25", "session": "nyam", "what": "3 trades"}]
    only("p13b", [], "1.3", "the most is 1 (need at most 0)", max_tr=0)
    x = only("p14a", [tr("2022-03-25", how="tp", net=196.0)], "1.4", "1 trade is off")
    assert x["exceptions"][0]["what"] == "ended at its target and paid $196, not about the target of $400"
    x = only("p14b", [tr("2022-03-25", how="sl", stop=12.0)], "1.4", "1 trade is off")
    assert x["exceptions"][0]["what"] == "its stop is 12 points from the entry, not the stated 10"
    # in a store two trades of ONE session may not overlap; trades of two sessions of a cell are two instances and may
    two = [tr("2022-03-25", at="10:50:00", held=60), tr("2022-03-25", at="11:10:00", held=10)]
    q = A.code_check("hand", store=store("p12c", {"pts10-r2": clean() + two, "pts10-r0": no_target(clean())}, sessions=("nyam", "mid")), looked=True)
    assert q["passed"] is True and by(q)["1.2"]["overlaps"] == 0
    # a cell WITHOUT a target that holds target exits: the idea sets its own target; the store does not keep that price
    own = store("own", {"pts10-r2": clean(), "pts10-r0": no_target(clean()) + [tr("2022-03-25", how="tp", net=96.0, tgt=5.0)]})
    x = by(A.code_check("hand", store=own, looked=True))["1.4"]
    assert x["passed"] is True and (x["own_target"], x["at_target"], x["at_stop"]) == (5, 0, 12) and "5 target exits at the idea's own level, not held against a distance" in x["text"]
    # 1.6 between two stores: every field of every cell
    again = store("hand-NQ-tf5", {"pts10-r2": clean(), "pts10-r0": no_target(clean())}, folder="again")
    x = by(A.code_check("hand", store=again, looked=True, same_as=p))["1.6"]
    assert x["passed"] is True and x["text"] == "1.6 PASS the earlier trade list is reproduced exactly: 20 trades in 2 lists (stores/hand-NQ-tf5)"
    rows = clean()
    rows[2]["side"] = "long" if rows[2]["side"] == "short" else "short"
    x = by(A.code_check("hand", store=store("hand-NQ-tf5", {"pts10-r2": rows, "pts10-r0": no_target(clean())}, folder="changed"), looked=True, same_as=p))["1.6"]
    assert x["passed"] is False and "1 of 2 lists differs" in x["text"] and "pts10-r2" in x["text"] and "side" in x["text"]
    x = by(A.code_check("hand", store=store("hand-NQ-tf5", {"pts10-r2": clean()}, folder="short"), looked=True, same_as=p))["1.6"]
    assert x["passed"] is False and "pts10-r0 is missing" in x["text"]


# ================================================================ (d) the engine's own stores on disk

def test_the_engines_own_stores_pass():
    """Real trades of the engine, read-only: stores of the old build days (runs/) and of 2024 (runs_v2/), which the
    blueprint's build range holds. A family that sets its own target (ib fade, gap fill) and the random-entry pool are
    among them. Lines 1.1-1.4 must hold on every one; the counts equal run_menus.hold_checks' reading."""
    n = trades = 0
    for where in ("runs/orb-NQ-tf15", "runs/first_bar_mom-ES-tf15", "runs/ib-NQ-tf15", "runs/gap-GC-tf15", "runs/donchian-NQ-tf5", "runs/c1-GC-tf30",
                  "runs/vwap_band-ES-tf5", "runs_v2/orb-NQ-tf15-pre-pick"):
        if not (W / where / "run.json").exists():
            continue
        r = A.code_check("on_disk", store=where)             # as the library names it: <folder>/<key>
        b = by(r)
        assert [b[k]["passed"] for k in ("1.1", "1.2", "1.3", "1.4")] == [True] * 4, (where, [b[k]["text"] for k in ("1.1", "1.2", "1.3", "1.4")])
        assert b["1.1"]["number"] == b["1.2"]["number"] == b["1.4"]["number"] == 0 and r["source"]["kind"] == "store" and len(r["look"]) == 10
        n, trades = n + 1, trades + r["source"]["trades"]
    assert n >= 6 and trades > 500_000
    own = by(A.code_check("on_disk", store=W / "runs" / "ib-NQ-tf15"))["1.4"]
    assert own["own_target"] > 0 and own["at_stop"] > 0
    RESULTS["test_the_engines_own_stores_pass"] = (n, n, f"stores, {trades:,} trades")


# ================================================================ (e) the command, the idea's record, and the seal

def _run(argv: list) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(argv)
    return rc, out.getvalue()


def test_the_command():
    p, e = saved(clean(), "cmd"), saved(clean(), "cmd_earlier")
    argv = ["code-check", "cmd", f"--trades={p}", "--market=NQ", "--sessions=nyam", "--max-per-day=2"]      # the idea's name first; --opt=value
    last = [f"--root={tmp() / 'ideas'}", "--json"]          # the connector's shape: --root and --json come last
    r = A.code_check("cmd", trades=p, **STATED)
    rc, txt = _run(argv)
    lines = txt.rstrip("\n").split("\n")
    assert rc == 0 and txt.rstrip("\n") == r["text"] and lines[0] == f"CODE CHECK of cmd: 12 trades in 1 list, market NQ ({p})"
    assert lines[1:7] == [x["text"] for x in r["lines"]] and lines[7:17] == [ln for ln in lines if ln.startswith("  #")] and len(lines) == 18
    assert lines[17] == "RESULT: fails 1.5; not read: 1.6. Phase 1 is passed only when every line is true."
    rc, js = _run(argv + ["--looked", f"--same-as={e}", *last])
    d = json.loads(js)
    assert rc == 0 and js.count("\n") == 1 and js.isascii() and list(d)[:len(CONTRACT)] == list(CONTRACT) and d["name"] == "cmd" and d["passed"] is True
    assert d == json.loads(json.dumps(A.code_check("cmd", trades=p, looked=True, same_as=e, root=tmp() / "ideas", **STATED)))
    assert d["text"].split("\n")[-1] == "RESULT: every line is true. Phase 1 is passed." and d["next"].startswith("Phase 1 is passed")
    assert d["saved"] == [] and not (tmp() / "ideas").exists()                  # no idea of that name on file: printed, nothing saved
    rc, js = _run(["code-check", "cmd", f"--trades={p}", "--market=NQ", "--window=09:30-11:00", "--max-per-day=2", "--json"])
    assert rc == 0 and json.loads(js)["lines"][0]["passed"] is True
    n = 0
    for bad, word in ((["code-check"], "required"), (["code-check", "cmd"], "--store"), (["code-check", "cmd", f"--trades={p}"], "--market"),
                      (["code-check", "cmd", f"--trades={p}", "--market=CL"], "CL"), (argv + ["--store=x"], "one of"), (["code-check", "cmd", "--run-id=r1"], "--run-id"),
                      (argv[:4] + ["--sessions=lunch"], "lunch"), (argv[:4] + ["--window=9-11"], "HH:MM-HH:MM"), (argv[:4] + ["--window=11:00-09:30"], "HH:MM-HH:MM"),
                      (["code-check", "cmd", f"--trades={tmp() / 'nothing_here.json'}", "--market=NQ"], "nothing_here.json"), (argv + ["--max-per-day=0"], "max-per-day"),
                      (["code-check", "cmd", "--store=no_such_key"], "no_such_key"), (argv + ["--no-such-option"], "unrecognized")):
        rc, txt = _run(bad)
        assert rc == 2 and txt.startswith("REFUSED: ") and word in txt, (bad, txt)
        rc, js = _run(bad + last)
        d = json.loads(js)
        assert rc == 2 and list(d) == list(CONTRACT) and d["ok"] is False and word in d["error"] and (d["command"], d["phase"], d["lines"]) == ("code-check", 1, []), d
        n += 1
    RESULTS["test_the_command"] = (2 + n, 2 + n, "answers and refusals")


def test_the_result_is_saved_with_the_idea_when_the_idea_is_on_file():
    """The app keeps one folder per idea (homebase/ideastore.py). An idea that is on file gets the code check as its
    check.json; an idea that is not is only printed, and no folder is made for it."""
    IS, root = A.ideastore(), tmp() / "ideas_rec"
    p = saved(clean(), "cc_idea")
    r = A.code_check("cc_idea", trades=p, root=root, **STATED)                  # not on file: printed only
    assert r["saved"] == [] and not root.exists()
    IS.create("cc_idea", root)
    assert IS.read_idea("cc_idea", root)["phase"] == 0
    r = A.code_check("cc_idea", trades=p, root=root, **STATED)
    f = root / "cc_idea" / "check.json"
    assert r["saved"] == [str(f)] and json.loads(f.read_text()) == json.loads(json.dumps(r)) and r["failed"] == ["1.5"]
    idea = IS.read_idea("cc_idea", root)
    assert idea["phase"] == 1 and idea["status"] == "idea" and [x["line"] for x in idea["lines"]] == LINES and idea["next"] == r["next"]
    assert r["asked"] == {"trades": str(p), "market": "NQ", "sessions": ["nyam"], "max_per_day": 2}
    # the owner looked: `code-check <name> --looked` names no source again -- the one on file is read again, with what was stated
    rc, js = _run(["code-check", "cc_idea", "--looked", f"--root={root}", "--json"])
    d = json.loads(js)
    assert rc == 0 and d["passed"] is True and d["source"] == r["source"] and d["asked"] == r["asked"] and d["look"] == r["look"] and d["saved"] == [str(f)]
    assert json.loads(f.read_text()) == d and [x["passed"] for x in d["lines"]] == [True, True, True, True, True, None]
    assert [x["passed"] for x in IS.read_idea("cc_idea", root)["lines"]] == [True, True, True, True, True, None]
    # a new source replaces the one on file; the root may come from the environment
    s2 = store("cc-NQ-tf5", {"pts10-r2": clean(), "pts10-r0": no_target(clean())}, folder="cc_stores")
    keep = os.environ["HOMEBASE_IDEAS_ROOT"]
    try:
        os.environ["HOMEBASE_IDEAS_ROOT"] = str(root)
        d = A.code_check("cc_idea", store=s2)
    finally:
        os.environ["HOMEBASE_IDEAS_ROOT"] = keep
    assert d["saved"] == [str(f)] and d["asked"] == {"store": str(s2)} and json.loads(f.read_text())["source"]["kind"] == "store"
    assert A.code_check("cc_idea", looked=True, root=root)["source"] == d["source"]
    # an idea without a check on file and without a source: refused; a refusal is never saved
    IS.create("cc_other", root)
    refused(lambda: A.code_check("cc_other", looked=True, root=root), "--store")
    rc, txt = _run(["code-check", "cc_other", f"--trades={saved(clean() + [tr('2025-07-01')], 'cc_late')}", "--market=NQ", f"--root={root}"])
    assert rc == 2 and "2025-07-01" in txt and not (root / "cc_other" / "check.json").exists()
    assert sorted(x.name for x in root.iterdir()) == ["cc_idea", "cc_other"] and _listing(tmp() / "drafts") is None      # no Lab draft is written here


def test_no_day_on_or_after_2025_07_01():
    start = R.template("ranges")["test"]["start"]
    assert start == "2025-07-01"
    for i, late in enumerate((tr("2025-07-01"), tr("2026-03-10"), {**tr("2025-06-30"), "entry_ms": ms("2025-07-01", "09:35:00"), "exit_ms": ms("2025-07-01", "09:55:00")},
                              tr("2025-06-30", how="time", exit_ms=ms("2025-07-01", "09:40:00")), {k: v for k, v in tr("2025-07-02").items() if k != "date"})):
        word = refused(lambda: check(clean() + [late], f"late{i}"), "2025-07-01")
        assert "code check" in word and "$" not in word
        rc, txt = _run(["code-check", f"late{i}", f"--trades={tmp() / f'late{i}.json'}", "--market=NQ", "--sessions=nyam"])
        assert rc == 2 and txt.startswith("REFUSED: ") and "1.1" not in txt
    refused(lambda: check(clean(), "now", same_as=saved(clean() + [tr("2025-07-01")], "late_earlier")), "2025-07-01")      # the earlier list too
    assert check(clean() + [tr("2025-06-30", at="10:15:00")], "last_day", looked=True)["passed"] is True                 # the last build day is read
    # a store: its range is read BEFORE its trades; and its trades, whatever its range says
    keep, seen = LB.load_unit, []
    late = store("late-NQ-tf5", {"pts10-r2": clean()}, end="2025-12-31")
    lie = store("lie-NQ-tf5", {"pts10-r2": clean() + [tr("2025-07-01")]})
    try:
        LB.load_unit = lambda *a, **k: seen.append(a) or keep(*a, **k)
        refused(lambda: A.code_check("late", store=late), "2025-06-30")
        assert seen == []
        refused(lambda: A.code_check("lie", store=lie), "2025-07-01")
        refused(lambda: A.code_check("ok", store=store("ok-NQ-tf5", {"pts10-r2": clean()}), same_as=late), "2025-06-30")
    finally:
        LB.load_unit = keep
    for where in ("runs_check2025", "runs_exam2026"):       # the 2025 and 2026 stores on disk: refused by their range, never opened
        d = next((p.parent for p in sorted((W / where).glob("*/run.json"))), None)
        if d is not None:
            refused(lambda d=d: A.code_check("late", store=d), "2025-06-30")
    refused(lambda: A.code_check("none", store=tmp() / "stores" / "no_such_store"), "no_such_store")


def test_nothing_was_written_outside_the_temp_folder():
    assert _listing(HOME / "ideas") == BEFORE["ideas"] and _listing(HOME / "strategies") == BEFORE["drafts"], "a test wrote into ~/.homebase"
    assert _listing(tmp() / "ideas") is None                # the environment's idea folder was never needed either


RESULTS: dict = {}

if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
    sys.exit(rc)
