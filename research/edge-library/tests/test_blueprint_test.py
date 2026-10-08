"""LOCK of THE ONE READ OF THE TEST DAYS (blueprint/oos.py, reads.py, tables.tested, lines.TEST, runner.run_test;
`bp.py test <name> --confirm [--wait=S] [--second-look]`, `bp.py seed-reads [--dry-run]`) -- toolkit plan, step 8;
BLUEPRINT.md phase 4.

(a) THE LINES 4.1-4.9 on hand-made trade tables, each with its edge cases: "above $0" is strict, the floor is "or more",
    95 % of the random tables is strict, the best 1 % of days are the average variant's, 80 % of the reshuffles is "or more".
(b) WHAT THE TEST REFUSES (exit 2; nothing run, no read used): not frozen; a lock that no longer matches the files on disk;
    --confirm missing; a job of the idea at work; stores of a read without its line in the log; --second-look without a
    used read.
(c) THE READ IS CLAIMED BEFORE THE RUN: the line is in the one-read log when the pass starts; a pass that fails (a refusal,
    a crash) leaves it there, no verdict is written, and a second `test` is refused.
(d) A WHOLE READ: every line 4.1-4.9 in test.json, the read judged with its verdict, PROVEN ON HISTORY or shelved in the
    app (idea.json, the Lab block, the Lab group), the default variant's test trades as a tester run. A fail is final.
(e) ONE READ FOR AN IDEA AND ITS RELATIVES: a read on file for a same-idea relative, or for one of the old saved strategies,
    refuses the test; --second-look is the only way past, and the verdict is then labelled SECOND LOOK everywhere.
(f) SEED-READS: which rows of the old read logs mean a read of the test days; one line a unit; a second run adds nothing;
    --dry-run writes nothing. On this machine's logs: the 15 saved strategies.
(g) THE READER'S SEAL (tables.tested): a store of another lock, of another range, without a locked variant, with a trade
    outside the range or with a thin pool is refused.
(h) THE RUNNER (runner.run_test): no claimed read = nothing is opened; the days are the frozen range's; the engine's test
    switch and no other. THE ONE REAL READ of this file replays, for an idea that is one of the old saved strategies (so:
    a second look), cells whose 2025-07-01+ stores are ALREADY on disk from the old 2025 / 2026 runs, on 4 days, and holds
    all three stores against them trade for trade. Counts only: no P&L of a test day is printed or asserted.
(i) THE COMMAND LINES as the connector writes them, and the app's own connector against this toolkit.

Everything else on the test days is HAND-MADE (tests/blueprint_frozen.py `fake_read` stands in for runner.run_test): no new
strategy result is produced on them. Temp folders only (--root, HOMEBASE_DRAFTS_DIR); the last test looks.
  pytest tests/test_blueprint_test.py -q        python tests/test_blueprint_test.py     one line per test (+ the connector's answers)
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_frozen as F  # noqa: E402

import judge as J  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import reads as READS  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402

NAME, KEY = "bpl_orb", "bpl_orb-NQ-tf15"
IS = F.IS
RESULTS: dict = {}
_T: dict = {}


def setup_function(_=None):
    F.env_on()


def teardown_function(_=None):
    F.env_off()


def reads(root) -> list:
    f = Path(root) / "test_reads.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def draft(name: str) -> list:
    return (F.DRAFTS / f"{name}.py").read_text(encoding="utf-8").splitlines()


def group(name: str):
    return F.read(F.DRAFTS / "groups.json")["members"].get(f"draft_{name}")


# ================================================================ (a) lines 4.1-4.9 on hand-made tables

def table(net, n=None, root: str = "NQ", split: int = None, **more) -> dict:
    """Table data by hand: net (variants x days); n = trades (default: 1 where a day has a net); the first `split` days are
    Jul-Dec 2025, the rest Jan-Sep 2026 (default: half and half)."""
    net = np.asarray(net, float)
    n = (net != 0).astype(float) if n is None else np.asarray(n, float)
    k = net.shape[1] // 2 if split is None else split
    first = np.arange(net.shape[1]) < k
    return {"root": root, "net": net, "n": n, "parts": [{"name": "Jul-Dec 2025", "days": first}, {"name": "Jan-Sep 2026", "days": ~first}], **more}


def ctl(p: float, seeds: int = 10, short: int = 0) -> dict:
    return {"pass": True, "p_beat": p, "replicates": 4000, "real_replicates": seeds, "short": short}


def test_the_test_has_seven_lines_in_the_laws_order():
    t = table([[100, 50, 30, 10]], controls={"c1": ctl(0.99)}, worse=[20.0])
    rows = [f(t) for f in L.TEST]
    assert [x["line"] for x in rows] == F.TEST_LINES == [k for k in R.lines() if k.startswith("4.")] and OOS.LINES is L.TEST
    assert all(set(x) >= {"line", "passed", "number", "need", "text"} and type(x["passed"]) is bool and x["text"].startswith(f"{x['line']} ") for x in rows)
    assert json.loads(json.dumps(rows)) == rows                                   # plain JSON: a result is saved and printed as it is


def test_line_4_1_both_parts_make_money_on_their_own():
    r = L.parts(table([[100, 20, 30, 40], [60, -40, 10, 10]]))                    # average variant: $70 in 2025, $45 in 2026
    assert r["passed"] is True and r["number"] == 45.0 and r["text"] == "4.1 PASS Jul-Dec 2025 $70 · Jan-Sep 2026 $45, average variant (need each above $0)"
    assert [(p["name"], p["avg"], p["days"]) for p in r["parts"]] == [("Jul-Dec 2025", 70.0, 2), ("Jan-Sep 2026", 45.0, 2)]
    r = L.parts(table([[500, 500, -10, 5]]))                                      # one good stretch does not hide a dead one
    assert r["passed"] is False and r["number"] == -5.0 and "Jan-Sep 2026 -$5" in r["text"]
    assert L.parts(table([[-1, 0, 500, 500]]))["passed"] is False                 # ... either way round
    r = L.parts(table([[50, -50, 10, 10]]))                                       # exactly $0 is not "above $0"
    assert r["passed"] is False and r["number"] == 0.0 and "Jul-Dec 2025 $0" in r["text"]
    assert L.parts(table([[100, -200, 5, 5], [100, 200, 5, 5]]))["passed"] is True      # the AVERAGE variant decides ($100 in 2025), not each variant
    r = L.parts(table([[100, 20, 0, 0]]))                                         # a part without a trade made no money
    assert r["passed"] is False and "Jan-Sep 2026 no trade" in r["text"]
    r = L.parts(table([[100, 20]], split=2))                                      # a part without a session day
    assert r["passed"] is False and "Jan-Sep 2026 no session day" in r["text"]
    r = L.parts({"root": "NQ", "net": np.ones((1, 2)), "n": np.ones((1, 2))})     # no parts to read
    assert r["passed"] is False and r["number"] is None and "no two parts" in r["text"]
    assert L.parts(table([[10, 20, 30, 40]], split=1))["parts"][1]["days"] == 3   # the parts are the caller's masks


def test_line_4_2_the_average_and_the_middle_variant_make_money():
    r = L.whole(table([[100, 20], [40, 0], [5, 5]]))                              # variants $120, $40, $10
    assert r["passed"] is True and (r["avg"], r["median"], r["number"], r["variants"]) == (170 / 3, 40.0, 40.0, 3)
    assert r["text"] == "4.2 PASS average variant $57, middle variant $40 (need both above $0)"
    r = L.whole(table([[1000, 0], [-1, 0], [-2, 0]]))                             # one lucky setting carries the average: the middle variant loses
    assert r["passed"] is False and r["number"] == -1.0 and "middle variant -$1" in r["text"]
    r = L.whole(table([[1, 0], [2, 0], [-1000, 0]]))                              # the middle variant is fine, the average is not
    assert r["passed"] is False and r["median"] == 1.0 and "average variant -$332" in r["text"]
    assert L.whole(table([[-10, 0], [20, 0]]))["passed"] is True                  # an even count: the median is the mean of the two middle ones ($5)
    r = L.whole(table([[-10, 0], [10, 0]]))                                       # ... and exactly $0 is not above $0
    assert r["passed"] is False and r["number"] == 0.0
    assert L.whole(table([[0.01, 0]]))["passed"] is True and L.whole(table(np.zeros((0, 2))))["passed"] is False


def test_line_4_3_the_average_trade_at_the_floor():
    r = L.floor_test(table([[100, 40], [70, 70]]))                                # 280 / 4 trades = exactly $70: "or more"
    assert r["line"] == "4.3" and r["passed"] is True and (r["number"], r["need"]) == (70.0, 70) and r["text"] == "4.3 PASS average trade $70 (need $70)"
    r = L.floor_test(table([[69.99, 69.99]]))
    assert r["passed"] is False and r["text"] == "4.3 FAIL average trade $69.99 (need $70)"
    assert L.floor_test(table([[100.0, 0.0]], [[2, 0]]))["number"] == 50.0        # net of all variants / THEIR TRADES
    assert L.floor_test(table([[139.0, 139.0]], root="GC"))["passed"] is False and L.floor_test(table([[140.0, 140.0]], root="GC"))["passed"] is True
    assert L.floor_test(table([[75.0, 75.0]], root="ES"))["passed"] is True and L.floor_test(table([[74.5, 74.5]], root="ES"))["passed"] is False
    r = L.floor_test(table([[0.0, 0.0]]))
    assert r["passed"] is False and r["number"] is None and "no trade" in r["text"]
    F.refused(lambda: L.floor_test(table([[100.0, 100.0]], root="CL")), "CL")     # a market the law names no floor for
    assert R.need("4.3") == R.need("2.2") and L.floor(table([[70.0, 70.0]]))["line"] == "2.2"      # the same floor as on build; 2.2 is still 2.2


def test_line_4_4_above_95_percent_of_the_random_tables():
    r = L.random_test({"controls": {"c1": ctl(0.95)}})                            # exactly 95 %: "above" is strict
    assert r["line"] == "4.4" and r["passed"] is False and (r["number"], r["need"]) == (0.95, 0.95) and "need above 95 %" in r["text"]
    r = L.random_test({"controls": {"c1": ctl(0.9503)}})
    assert r["passed"] is True and r["text"] == "4.4 PASS beats 95.03 % of 4,000 random tables (need above 95 %); 10 seeds" and "round" not in r
    assert L.random_test({"round": 5, "controls": {"c1": ctl(0.96)}})["passed"] is True       # a test has no round: the bar does not rise (round 5 on build: 99 %)
    assert L.beats_random({"round": 5, "controls": {"c1": ctl(0.96)}})["passed"] is False and L.beats_random({"controls": {"c1": ctl(0.96)}})["round"] == 1
    r = L.random_test({"controls": {"c1": ctl(0.99, short=3)}})                   # trades without a random match: not the same days
    assert r["passed"] is False and "3 trades had no random match" in r["text"]
    r = L.random_test({"controls": {"c1": ctl(0.999, seeds=2)}})                  # (a read always runs 10 seeds; fewer would be said)
    assert r["thin"] is True and "THIN" in r["text"]
    for missing in ({}, {"controls": {}}, {"controls": {"c1": {"pass": False, "why": "no pool"}}}):
        r = L.random_test(missing)
        assert r["passed"] is False and r["number"] is None and "no random tables" in r["text"]


def test_line_4_5_it_still_makes_money_with_worse_fills():
    t = table([[100, 100]], worse=[30.0, -10.0, 1.0], worse_fills="2 ticks + 250 ms + a 100 ms late cancel")
    r = L.worse_fills(t)                                                          # the average variant with worse fills: $7
    assert r["passed"] is True and (r["number"], r["need"], r["variants"]) == (7.0, 0, 3) and r["fills"] == R.need("4.5")
    assert r["text"] == "4.5 PASS average variant $7 with worse fills (2 ticks + 250 ms + a 100 ms late cancel; need above $0)"
    r = L.worse_fills({**t, "worse": [30.0, -30.0]})                              # exactly $0 is not above $0
    assert r["passed"] is False and r["number"] == 0.0
    assert L.worse_fills({**t, "worse": [-1.0, 500.0, -600.0]})["passed"] is False
    assert L.worse_fills({**t, "worse": np.array([0.01])})["passed"] is True
    for gone in (None, [], np.zeros(0)):                                          # the table was not run with worse fills: not met
        r = L.worse_fills({**t, "worse": gone})
        assert r["passed"] is False and r["number"] is None and "was not run with worse fills" in r["text"]
    assert "2 ticks + 250 ms;" in L.worse_fills(table([[1, 1]], worse=[1.0]))["text"]      # (a one-sided rule: no late cancel in the words)


def test_line_4_6_without_its_best_1_percent_of_days():
    """The days taken out = 1 % of the session days, rounded up, at least 1 (lines._best_count): 1 day on these short tables,
    4 of the 315 days of the real stretch (tests/test_blueprint_lines.py reads the count on long tables)."""
    r = L.best_days(table([[100, 50, 30, 10, -85, 0]]))                           # 6 days: the 1 best day made $100 of $105: $5 is left
    assert r["passed"] is True and (r["number"], r["need"], r["best"], r["total"], r["count"], r["days"]) == (5.0, 0, [100.0], 105.0, 1, 6)
    assert r["text"] == "4.6 PASS $5 without its best 1 % of days (1 of 6 session days; they made $100 of $105, average variant; need above $0)"
    r = L.best_days(table([[100, 50, 30, 10, -95, 0]]))
    assert r["passed"] is False and r["number"] == -5.0
    assert L.best_days(table([[100, 50, 30, 10, -90, 0]]))["passed"] is False     # exactly $0 is not above $0
    r = L.best_days(table([[300, 0, 0, 0], [-100, 40, 40, 40]]))                  # the AVERAGE variant's days: $100, $20, $20, $20 -> $60 left
    assert r["passed"] is True and r["best"] == [100.0] and r["number"] == 60.0
    assert L.best_days(table([[900]], split=1))["number"] == 0.0 and L.best_days(table([[900]], split=1))["passed"] is False      # 1 day: nothing left
    assert L.best_days(table([[900, -800]]))["passed"] is False
    r = L.best_days(table([[-5, -10, -20, -40]]))                                 # all days lose: the "best" one is the smallest loss
    assert r["passed"] is False and r["number"] == -70.0 and R.need("4.6") == {"best_share": 0.01, "above": 0}
    long = L.best_days(table([[10.0] * 315]))                                     # the real stretch: 1 % of 315 days = 3.15 -> 4 days out
    assert (long["count"], long["days"], long["number"]) == (4, 315, 3110.0) and "(4 of 315 session days;" in long["text"]


def test_line_4_7_monte_carlo_on_the_test_days():
    r = L.monte_test(table([[60, 10, 5, 20, 30, 15]]))                            # every day makes money: every reshuffled run does
    assert r["line"] == "4.7" and r["passed"] is True and (r["number"], r["need"], r["runs"]) == (1.0, 0.8, 1000)
    assert r["text"] == "4.7 PASS the average variant makes money in 100 % of 1,000 reshuffled runs (need 80 % or more)"
    r = L.monte_test(table([[400, -100, -100, -100, -100, 50]]))                  # a profit that hangs on one day: gone in many runs
    assert r["passed"] is False and 0.3 < r["number"] < 0.8
    assert L.monte_test(table([[-60, -10, -5, -20]]))["number"] == 0.0
    # whole days, the same days for every variant: two variants that cancel each other out day by day never make money
    assert L.monte_test(table([[100, -50, 30, 10], [-100, 50, -30, -10]]))["number"] == 0.0
    assert R.rule("4.7")["op"] == ">=" and R.meets("4.7", 0.8) and not R.meets("4.7", 0.7999)      # "80 % of the runs or more"


# ================================================================ (b) what the test refuses

def test_line_4_8_the_test_looks_like_the_build():
    # the test's average trade (4.3's reading) against HALF of the build's own: $300 on build -> $150 or more on the test days
    r = L.like_build(table([[150.0, 150.0], [150.0, 150.0]], build_avg_trade=300.0))
    assert r["line"] == "4.8" and r["passed"] is True and (r["number"], r["need"], r["build"]) == (150.0, 150.0, 300.0)       # "at least": half itself passes
    assert r["text"] == "4.8 PASS average trade $150 on the test days, $300 on build (need at least $150, half of the build's)"
    r = L.like_build(table([[149.0, 150.0], [150.0, 150.0]], build_avg_trade=300.0))
    assert r["passed"] is False and r["text"].startswith("4.8 FAIL average trade $149.75 on the test days, $300 on build")
    assert L.floor(table([[75.0, 75.0]]), "4.3")["passed"] is True and L.like_build(table([[75.0, 75.0]], build_avg_trade=300.0))["passed"] is False      # over the floor, a quarter of the build
    # nothing to hold it against = not met: no figure with the lock, a build that made none, a test without a trade
    assert L.like_build(table([[150.0, 150.0]]))["passed"] is False and "not on file" in L.like_build(table([[150.0, 150.0]]))["text"]
    assert L.like_build(table([[150.0, 150.0]], build_avg_trade=-20.0))["passed"] is False and L.like_build(table([[0.0, 0.0]], build_avg_trade=300.0))["passed"] is False
    assert R.rule("4.8")["op"] == ">=" and R.need("4.8") == 0.5


def test_line_4_9_the_default_variant_keeps_its_profit_factor():
    r = L.box_test(table([[10.0, 10.0]], box={"trades": [120.0, -100.0]}))        # $120 won, $100 lost: 1.2, "or more"
    assert r["line"] == "4.9" and r["passed"] is True and (r["number"], r["need"], r["trades"]) == (1.2, 1.2, 2)
    assert r["text"] == "4.9 PASS default variant: profit factor 1.20 over 2 trades (need 1.2 or more)"
    assert L.box_test(table([[10.0, 10.0]], box={"trades": [119.0, -100.0]}))["passed"] is False
    assert L.box_test(table([[10.0, 10.0]], box={"trades": [5.0, 7.0]}))["passed"] is True                 # no losing trade
    for none in (table([[10.0, 10.0]]), table([[10.0, 10.0]], box={"trades": []})):                         # no default variant handed over, or it did not trade
        assert L.box_test(none)["passed"] is False and "no trade" in L.box_test(none)["text"]


def test_what_the_test_refuses():
    root, n = F.fresh(NAME, "ref"), 0
    d, out = root / NAME, F.read_out("ref")

    def no(word: str, name: str = NAME, **kw) -> str:
        nonlocal n
        n += 1
        with F.reading("ref"), F.no_engine():
            why = F.refused(lambda: OOS.test(name, **{"confirm": True, **kw}, root=root), word)
        assert reads(root) == [] and not (d / "test.json").exists() and not out.exists(), word      # no read was used, nothing was written
        return why

    no("no card", "bpl_nobody")
    assert "bp.py lock bpl_orb" in no("not frozen")                               # a lead that is not frozen: the freeze comes first
    with F.tiny():
        lock = FRZ.lock(NAME, root)["lock"]
    # ---- the lock no longer matches the files on disk
    spec = F.read(d / "spec.json")
    (d / "spec.json").write_text(json.dumps({**spec, "run": {**spec["run"], "limits": {"max_tr": 1}}}))
    assert lock["hash"] in no("no longer matches the files on disk") and "spec.json" in no("card and settings on file")
    (d / "spec.json").write_text(json.dumps(spec))
    (d / "lock.json").write_text(json.dumps({**lock, "default": [c for c in lock["variants"] if c != lock["default"]][0]}))
    no("lock.json was changed after it was written")
    (d / "lock.json").write_text(json.dumps(lock))
    keep = RUN.code
    try:
        RUN.code = lambda family=None: {**keep(family), "l2sim.py": "0" * 16}
        no("l2sim.py changed since the freeze")
    finally:
        RUN.code = keep
    # ---- the owner has to have said so
    for confirm in (False, None, "yes", 1):
        assert "--confirm" in no("read ONCE", confirm=confirm)
    # ---- a job of the idea is at work
    jd = root / "_jobs" / "20260101T000000-abc123"
    jd.mkdir(parents=True)
    (jd / "job.json").write_text(json.dumps({"id": jd.name, "command": "test", "name": NAME, "state": "running", "pid": os.getpid(), "args": {}}))
    assert jd.name in no("still running")
    shutil.rmtree(root / "_jobs")
    # ---- a second look at nothing: it would be the first read
    no("FIRST read", second_look=True)
    # ---- stores of this lock's read are on disk and the log has no line: the days WERE read
    K = RUN.test_keys(KEY, NAME, "NQ", "15", "nyam")
    (out / K["table"]).mkdir(parents=True)
    (out / K["table"] / "run.json").write_text("{}")
    with F.reading("ref"), F.no_engine():
        assert K["table"] in F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "WERE read")
    shutil.rmtree(out)
    assert reads(root) == [] and not (d / "test.json").exists() and IS.status(NAME, root) == "lead" and IS.read_idea(NAME, root)["phase"] == 3
    RESULTS["test_what_the_test_refuses"] = (n + 1, n + 1, "refusals: nothing run, no read used")


# ================================================================ (c) the read is claimed before the run

def test_the_read_is_in_the_log_before_the_pass_and_stays_there_when_the_pass_fails():
    root, lock = F.frozen(NAME, "claim")
    d, seen = root / NAME, []
    rng = {"start": "2025-07-01", "end": lock["test_range"]["NQ"]["end"]}
    with F.reading("claim", seen=seen, fail=J.Refuse("planted: the pass fails")):
        why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "planted: the pass fails")
    # the line was on file when the pass started: claimed, for this lock and its frozen range -- and nothing else was
    line = seen[0]["line"]
    assert len(seen) == 1 and (line["state"], line["name"], line["version"], line["lock"], line["range"], line["verdict"]) == ("claimed", NAME, 1, lock["hash"], rng, None)
    assert seen[0]["test_json"] is False and not seen[0]["stores"] and "second_look" not in line
    # ... and it stays: no verdict, no status, a second test refused -- with or without --second-look
    assert "THE READ STAYS ON FILE" in why and line["utc"] in why and "refused from here on" in why
    assert reads(root) == [line] and not (d / "test.json").exists() and IS.status(NAME, root) == "lead" and IS.read_on_file(NAME, root=root) == line
    log = [json.loads(x) for x in (d / "log.jsonl").read_text().splitlines()]
    assert [x["event"] for x in log[-2:]] == ["test_claimed", "test_did_not_finish"] and "planted" in log[-1]["error"] and log[-2]["lock"] == lock["hash"]
    for kw in ({}, {"second_look": True}):
        with F.reading("claim"), F.no_engine():
            again = F.refused(lambda kw=kw: OOS.test(NAME, confirm=True, root=root, **kw), "already on file")
        assert "the run did not finish" in again and "read once" in again and reads(root) == [line]
    assert "on file" in REC.status(NAME, root)["next"]
    # a crash is no different: the claim was written first
    root2, lock2 = F.frozen(NAME, "crash")
    with F.reading("crash", fail=RuntimeError("planted: the machine went down")):
        try:
            OOS.test(NAME, confirm=True, root=root2)
            raise AssertionError("the crash was swallowed")
        except RuntimeError as e:
            assert "planted" in str(e)
    assert [(x["state"], x["lock"]) for x in reads(root2)] == [("claimed", lock2["hash"])] and not (root2 / NAME / "test.json").exists()
    with F.reading("crash"), F.no_engine():
        F.refused(lambda: OOS.test(NAME, confirm=True, root=root2), "already on file")
    # two claims at the same moment: the app's log lets one through (the claim is the last thing start() does)
    root3, lock3 = F.frozen(NAME, "race")
    with F.reading("race"), F.no_engine():
        IS.claim_read(NAME, version=1, lock=lock3["hash"], rng=rng, root=root3)
        F.refused(lambda: OOS.start(NAME, True, root=root3), "already on file")
    assert len(reads(root3)) == 1


# ================================================================ (d) a whole read

def _passed() -> tuple:
    if "pass" not in _T:
        root, lock = F.frozen(NAME, "pass")
        seen: list = []
        with F.reading("pass", seen=seen):
            r = OOS.test(NAME, confirm=True, root=root)
        _T["pass"] = (root, lock, r, seen)
    return _T["pass"]


def test_a_read_that_passes_is_proven_on_history_and_everything_is_saved():
    root, lock, r, seen = _passed()
    d, out, rng = root / NAME, F.read_out("pass"), {"start": "2025-07-01", "end": lock["test_range"]["NQ"]["end"]}
    assert list(r)[:len(F.CONTRACT)] == list(F.CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "error")] == [True, "test", NAME, "proven_on_history", 4, 1, None, None]
    assert (r["verdict"], r["passed"], r["failed"], r["second_look"], r["label"], r["dry_run"], r["lock"], r["range"]) == (
        "PROVEN ON HISTORY", True, [], False, None, False, lock["hash"], rng)
    # every line of the law, 4.1 to 4.9, read on the hand-made tables: each variant $150 a day on 8 days, $60 with worse fills, random entries -$5
    b = F.by(r)
    assert [x["line"] for x in r["lines"]] == F.TEST_LINES and all(x["passed"] is True and x["text"].startswith(x["line"] + " PASS ") for x in r["lines"])
    assert b["4.1"]["text"] == "4.1 PASS Jul-Dec 2025 $600 · Jan-Sep 2026 $600, average variant (need each above $0)"
    assert (b["4.2"]["avg"], b["4.2"]["median"], b["4.2"]["variants"]) == (1200.0, 1200.0, len(lock["variants"])) and b["4.3"]["number"] == 150.0
    c = b["4.4"]["controls"]["c1"]
    assert (b["4.4"]["number"], b["4.4"]["seeds"], c["replicates"], c["seeds"], c["short"]) == (1.0, 10, lock["control"]["draws"], list(range(1, 11)), 0)
    assert c["ctl_mean"] == -40.0 and list(c["stores"]) == [f"runs_test_pass/{RUN.test_keys(KEY, NAME, 'NQ', '15', 'nyam')['pool']}"]      # 8 random trades of -$5 a table
    assert b["4.5"]["number"] == 480.0 and "2 ticks + 250 ms + a 100 ms late cancel" in b["4.5"]["text"]
    assert b["4.6"]["number"] == 1050.0 and b["4.6"]["count"] == 1 and b["4.7"]["number"] == 1.0 and r["days"]["sessions"] == 8 and [p["sessions"] for p in r["days"]["parts"]] == [4, 4]
    # the read: claimed BEFORE the pass (what the pass saw), then judged with its verdict -- two lines, nothing rewritten
    assert (seen[0]["line"]["state"], seen[0]["test_json"]) == ("claimed", False)
    log = reads(root)
    assert [(x["state"], x["verdict"], x["lock"], x["range"]) for x in log] == [("claimed", None, lock["hash"], rng), ("judged", "PROVEN ON HISTORY", lock["hash"], rng)]
    assert log[0] == seen[0]["line"] and r["read"] == {"version": 1, "lock": lock["hash"], "utc": log[0]["utc"], "state": "judged", "verdict": "PROVEN ON HISTORY"}
    # test.json through the app's idea store, with EVERY line 4.x; the status is the app's reading of it
    saved = F.read(d / "test.json")
    assert [x["line"] for x in saved["lines"]] == F.TEST_LINES and saved["lines"] == json.loads(json.dumps(r["lines"])) and saved["verdict"] == "PROVEN ON HISTORY"
    assert (saved["ok"], saved["dry_run"], saved["job"], saved["next"], saved["default"]) == (True, False, None, r["next"], r["default"])
    got = IS.read_idea(NAME, root)
    assert (got["status"], got["phase"], got["group"], IS.status(NAME, root)) == ("proven_on_history", 4, "Proven on history", "proven_on_history")
    assert [x["line"] for x in got["lines"]] == F.TEST_LINES and got["next"] == r["next"] and group(NAME) == "Proven on history"
    head = draft(NAME)
    assert head[1] == f"# {NAME} · PROVEN ON HISTORY · phase 4 · round 1" and f"#   {b['4.7']['text']}" in head
    events = [json.loads(x) for x in (d / "log.jsonl").read_text().splitlines()]
    assert [x["event"] for x in events if x["event"].startswith("test")] == ["test_claimed", "tested"] and ("lead", "proven_on_history") in [(x.get("was"), x.get("now")) for x in events]
    assert sorted(str(Path(p).name) for p in r["saved"]) == sorted([*RUN.test_keys(KEY, NAME, "NQ", "15", "nyam").values(), "test.json", "test_reads.jsonl"])
    # the default variant's test trades as a finished run of the tester (the build's own path)
    dv = r["default"]
    assert dv["cell"] == lock["default"] and dv["trades"] == 8
    if F.APP_PYTHON.exists():
        assert dv["run_id"] and dv["note"] is None and dv["run_id"] in got["runs"], dv
        meta, trades = F.read(F.TESTER / "runs" / dv["run_id"] / "run.json"), json.loads((F.TESTER / "runs" / dv["run_id"] / "trades.json").read_text())
        assert (meta["strategy"]["id"], meta["strategy"]["root"], meta["imported"]["source"]) == ("draft_bpl_orb", "NQ", "research engine")
        assert "TEST" in meta["strategy"]["name"] and lock["default"] in meta["strategy"]["name"] and lock["hash"] in meta["imported"]["note"]
        assert len(trades) == 8 and (meta["range"]["start"], meta["range"]["end"], meta["coverage"]["sessions"]) == (F.TEST_DAYS[0], F.TEST_DAYS[-1], 8)
        assert f"tester run {dv['run_id']}" in r["text"]
    # the text: the read, the seven lines, the result, the status; the next step is the prop simulator
    text = r["text"].split("\n")
    assert text[0].startswith("TEST RUN on") or text[0].startswith("OUT-OF-SAMPLE TEST 2025-07-01")
    assert text[1].startswith(f"{NAME} · lock {lock['hash']} · version 1 · home NQ New York morning 15-minute bars · {len(lock['variants'])} locked variants")
    assert text[2:11] == [x["text"] for x in r["lines"]] and text[11] == "RESULT: PROVEN ON HISTORY: every line 4.1-4.9 is true -- approved for a real eval."
    assert text[12] == "STATUS: PROVEN ON HISTORY · phase 4" and "bp.py sim" in r["next"] and "\n" not in r["next"] and "SECOND LOOK" not in json.dumps(r)
    # the test days are read once: a second test is refused, whatever it says
    for kw in ({}, {"second_look": True}):
        with F.reading("pass"), F.no_engine():
            why = F.refused(lambda kw=kw: OOS.test(NAME, confirm=True, root=root, **kw), "already on file")
        assert "PROVEN ON HISTORY" in why and "read once" in why and len(reads(root)) == 2
    with F.tiny(), F.no_engine():                                                 # ... and the lock is still what it was
        assert FRZ.lock(NAME, root)["hash"] == lock["hash"]
    RESULTS["test_a_read_that_passes_is_proven_on_history_and_everything_is_saved"] = (7, 7, "lines saved; the read claimed, then judged")


def test_a_fail_is_final():
    root, lock = F.frozen(NAME, "fail")
    d = root / NAME
    with F.reading("fail", net=lambda cell, i, day: 150.0 if day < "2026" else -200.0, worse=lambda cell, i, day: -10.0):
        r = OOS.test(NAME, confirm=True, root=root)
    b = F.by(r)
    assert [x["line"] for x in r["lines"]] == F.TEST_LINES                        # EVERY line is in the result, pass or fail
    assert r["failed"] == [k for k, x in b.items() if x["passed"] is False] and {"4.1", "4.2", "4.5", "4.6"} <= set(r["failed"]) and b["4.4"]["passed"] is False
    assert (r["status"], r["verdict"], r["passed"], r["phase"]) == ("shelved", "NOT PROVEN", False, 4)
    assert "Jan-Sep 2026 -$800" in b["4.1"]["text"] and b["4.1"]["text"].startswith("4.1 FAIL ")
    # said in the output, in so many words; shelved in the app; the read is judged NOT PROVEN
    assert f"RESULT: NOT PROVEN: fails {', '.join(r['failed'])}. A FAIL IS FINAL: the idea is not re-tuned and re-tested on this period." in r["text"].split("\n")
    assert "a fail is final" in r["next"] and "SHELVED" in r["next"] and "STATUS: SHELVED · phase 4" in r["text"].split("\n")
    got = IS.read_idea(NAME, root)
    assert (got["status"], got["phase"], got["group"], group(NAME)) == ("shelved", 4, "Shelved", "Shelved") and draft(NAME)[1] == f"# {NAME} · SHELVED · phase 4 · round 1"
    assert [(x["state"], x["verdict"]) for x in reads(root)] == [("claimed", None), ("judged", "NOT PROVEN")]
    assert F.read(d / "test.json")["failed"] == r["failed"] and "NOT PROVEN" in REC.status(NAME, root)["next"] and "final" in REC.status(NAME, root)["next"]
    # ... and nothing gets it another read: not a second test, not a second look, not a new round, not a new card
    for kw in ({}, {"second_look": True}):
        with F.reading("fail"), F.no_engine():
            why = F.refused(lambda kw=kw: OOS.test(NAME, confirm=True, root=root, **kw), "already on file")
        assert "NOT PROVEN" in why and "a fail is final" in why
    with F.tiny(), F.no_engine():
        F.refused(lambda: REC.build(NAME, "tune it and try again", root=root), "frozen")
        F.refused(lambda: REC.card(NAME, F.idea(NAME, run={"limits": {"max_tr": 1}}), root), "frozen")
    assert len(reads(root)) == 2


def test_a_rule_with_a_filter_and_a_one_sided_card_are_frozen_and_read_as_they_were_built():
    # ---- a rule with ONE filter: the home table is the table with the filter on -- on build, at the freeze and on the test days
    name = "bpl_flt"
    F.lead(name, run={"filters": [{"block": "momentum", "side": "with"}]})
    root, lock = F.frozen(name, "flt")
    key, plain = "bpl_flt__momentum_with-NQ-tf15", "bpl_flt-NQ-tf15"
    assert (lock["home"]["key"], lock["home"]["filter"], lock["home"]["worse"]) == (key, "momentum_with", f"{key}-nyam-worse")
    assert list(lock["stores"]) == [key, f"{key}-nyam-worse", "c1-NQ-tf15", plain]          # ... and the plain table line 2.7 held it against is frozen with it
    assert F.read(F.OUT / f"{key}-nyam-worse" / "run.json")["filter"]["block"] == "momentum" and lock["spec"]["run"]["filters"] == [{"block": "momentum", "side": "with"}]
    with F.reading("flt"):
        r = OOS.test(name, confirm=True, root=root)
    K = RUN.test_keys(key, name, "NQ", "15", "nyam")
    assert K == {"table": f"{key}-nyam-test", "worse": f"{key}-nyam-test-worse", "pool": "bpl_flt__c1-NQ-tf15-nyam-test"}
    assert [s["key"] for s in r["stores"]] == [K["pool"], K["table"], K["worse"]] and r["unit"] == f"{key}-nyam" and r["status"] == "proven_on_history"
    assert F.read(F.read_out("flt") / K["table"] / "run.json")["read"]["lock"] == lock["hash"] and r["notes"] == []
    # ---- a card that trades ONE side: its side only, and the random tables (both sides) are said to be a tilted control
    name = "bpl_lng"
    F.lead(name, card={"sides": "long", "sides_why": "the index drifts up over the session"})
    root, lock = F.frozen(name, "lng")
    assert lock["plan"]["sides"] == "long" and F.read(F.OUT / "bpl_lng-NQ-tf15-nyam-worse" / "run.json")["limits"] == {"dir": "long"}
    with F.reading("lng"):
        r = OOS.test(name, confirm=True, root=root)
    assert len(r["notes"]) == 1 and "tilted control" in r["notes"][0] and f"NOTE: {r['notes'][0]}." in r["text"].split("\n") and F.read(root / name / "test.json")["notes"] == r["notes"]


# ================================================================ (e) one read for an idea and its relatives

def test_a_read_of_a_relative_stands_in_the_way_and_a_second_look_is_labelled_everywhere():
    """bpl_orb and bpl_two are the same entry trigger on the same market and session: one idea, two names."""
    root = F.fresh(NAME, "rel", "bpl_two")
    with F.tiny():
        a, b = FRZ.lock(NAME, root)["lock"], FRZ.lock("bpl_two", root)["lock"]
    with F.reading("rel"):
        first = OOS.test(NAME, confirm=True, root=root)
    assert first["status"] == "proven_on_history" and len(reads(root)) == 2
    # the relative's test days are not unseen: refused, and the relative and the reason are named
    with F.reading("rel"), F.no_engine():
        why = F.refused(lambda: OOS.test("bpl_two", confirm=True, root=root), "same-idea relative of bpl_two")
        use = READS.used("bpl_two", b, root)
    assert "the idea bpl_orb" in why and "the same entry trigger, market and session (orb, NQ, New York morning)" in why and "PROVEN ON HISTORY" in why
    assert "--second-look" in why and "SECOND LOOK everywhere" in why and len(reads(root)) == 2 and not (root / "bpl_two" / "test.json").exists()
    assert use["own"] is None and [(x["name"], x["kind"], x["state"]) for x in use["relatives"]] == [(NAME, "idea", "judged")]
    # the explicit second look goes through -- and says so EVERYWHERE
    with F.reading("rel", net=lambda cell, i, day: 90.0):
        r = OOS.test("bpl_two", confirm=True, second_look=True, root=root)
    assert (r["second_look"], r["label"], r["second_look_of"], r["verdict"], r["status"]) == (True, "SECOND LOOK", [NAME], "SECOND LOOK: PROVEN ON HISTORY", "proven_on_history")
    assert [x["line"] for x in r["lines"]] == F.TEST_LINES and all(x["text"].endswith(" [SECOND LOOK]") and x["second_look"] is True for x in r["lines"])
    text = r["text"].split("\n")
    assert text[0] == "SECOND LOOK: not a first read of the test days -- a read was on file for bpl_orb. It says less than a first read."
    assert "RESULT: SECOND LOOK: PROVEN ON HISTORY: every line 4.1-4.9 is true -- approved for a real eval." in text and "STATUS: PROVEN ON HISTORY (SECOND LOOK) · phase 4" in text
    assert r["next"].startswith("SECOND LOOK: ")
    log = [x for x in reads(root) if x["name"] == "bpl_two"]
    assert [(x["state"], x["verdict"]) for x in log] == [("claimed", None), ("judged", "SECOND LOOK: PROVEN ON HISTORY")] and log[0]["second_look"] is True
    saved = F.read(root / "bpl_two" / "test.json")
    assert (saved["second_look"], saved["label"], saved["verdict"]) == (True, "SECOND LOOK", "SECOND LOOK: PROVEN ON HISTORY")
    got = IS.read_idea("bpl_two", root)                                           # the app's own copies carry the label in every line and in the next step
    assert all(x["text"].endswith("[SECOND LOOK]") for x in got["lines"]) and got["next"].startswith("SECOND LOOK: ")
    assert sum("[SECOND LOOK]" in ln for ln in draft("bpl_two")) == 9 and any(ln.startswith("# NEXT: SECOND LOOK: ") for ln in draft("bpl_two"))
    if F.APP_PYTHON.exists() and r["default"]["run_id"]:
        meta = F.read(F.TESTER / "runs" / r["default"]["run_id"] / "run.json")
        assert "TEST (SECOND LOOK)" in meta["strategy"]["name"] and "SECOND LOOK" in meta["imported"]["note"]
    # a first read is never labelled as a second: the first idea's result says nothing of it
    assert "SECOND LOOK" not in json.dumps(first) and first["second_look"] is False
    RESULTS["test_a_read_of_a_relative_stands_in_the_way_and_a_second_look_is_labelled_everywhere"] = (7, 7, "lines labelled SECOND LOOK, + the text, the log, test.json, the Lab")


def test_an_old_saved_strategy_has_used_its_history():
    """bpl_pre is the opening range break on NQ in the pre-market: the saved strategy orb-NQ-tf15-pre, whose 2025 was read
    before the blueprint (out/judge/year_reads.csv). Its test days are not unseen -- whether the old reads were brought
    into the one-read log (seed-reads) or not."""
    if "orb-NQ-tf15-pre" not in READS.old():
        import pytest
        pytest.skip("the old read logs are not on this machine")
    name = "bpl_pre"
    F.lead(name, card={"home": {"market": "NQ", "session": "pre", "bar": "15"}, "neighbors": ["midday"]})
    root, lock = F.frozen(name, "old")
    for seeded in (False, True):
        if seeded:
            assert len(READS.seed(root=root)["added"]) == len(READS.old())
        with F.reading("old"), F.no_engine():
            why = F.refused(lambda: OOS.test(name, confirm=True, root=root), "one of the old saved strategies whose history is used")
            use = READS.used(name, lock, root)
        assert "the saved strategy orb-NQ-tf15-pre" in why and "OLD READ" in why and "2025 FAILED" in why and "--second-look" in why
        assert [(x["name"], x["kind"], x["unit"], x["in_log"]) for x in use["relatives"]] == [("orb_nq_tf15_pre", "old", "orb-NQ-tf15-pre", seeded)]
        assert not (root / name / "test.json").exists() and IS.read_on_file(name, root=root) is None
    n = len(reads(root))
    with F.reading("old"):                                                        # only as a second look
        r = OOS.test(name, confirm=True, second_look=True, root=root)
    assert (r["verdict"], r["second_look_of"]) == ("SECOND LOOK: PROVEN ON HISTORY", ["orb_nq_tf15_pre"]) and len(reads(root)) == n + 2
    assert "a read was on file for orb_nq_tf15_pre" in r["text"].split("\n")[0]
    # an idea that is NO relative of a saved strategy is not held up by them: bpl_orb trades another session
    root2, lock2 = F.frozen(NAME, "old2")
    READS.seed(root=root2)
    assert READS.used(NAME, lock2, root2) == {"own": None, "relatives": []}


def test_the_judges_same_idea_check_finds_a_relative_by_its_trades():
    """judge.same_idea is asked with the idea's own build store standing in for a store of runs/: what it answers (a member
    folder) is a relative when that member has a read. Here its answer is planted; the call itself runs once for real."""
    root, lock = F.frozen(NAME, "judge")
    assert READS.same_members(lock) == []                                         # the real call: 3 build days share no 30 days with any member
    keep = READS.same_members
    try:
        READS.same_members = lambda lock_, members_dir=None: ["first_bar_mom_NQ_tf15_mid", "not_a_member_with_a_read"]
        use = READS.used(NAME, lock, root)
        with F.reading("judge"), F.no_engine():
            why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "old saved strategies")
    finally:
        READS.same_members = keep
    assert [(x["name"], x["unit"]) for x in use["relatives"]] == [("first_bar_mom_nq_tf15_mid", "first_bar_mom-NQ-tf15-mid")] and "the judge's check" in use["relatives"][0]["why"]
    assert "first_bar_mom-NQ-tf15-mid" in why and "70 %" in why and reads(root) == []
    # the question has to be ANSWERED before the days are opened: a check that cannot be run, or a log that does not read, refuses the test
    try:
        READS.same_members = lambda lock_, members_dir=None: (_ for _ in ()).throw(OSError("planted: a member's store is gone"))
        with F.reading("judge"), F.no_engine():
            why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "could not be run")
    finally:
        READS.same_members = keep
    assert "planted" in why and "not opened on a guess" in why and reads(root) == []
    assert READS.same_members(lock, F.tmp() / "no_members_here") == []            # (a machine without saved strategies has none to be held against)
    (root / "test_reads.jsonl").write_text('{"name": "someone", "state": "judged"}\n{torn')
    with F.reading("judge"), F.no_engine():
        F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "does not read")
    (root / "test_reads.jsonl").unlink()
    u = READS._unit(lock)                                                         # the unit the judge is handed: the idea's home table
    assert (u["name"], u["key"], u["family"], u["root"], u["sess"], u["filter"]) == (NAME, KEY, "orb", "NQ", "nyam", None) and J.SAME_SIDE == 0.70 and J.SAME_DAYS == 30


def test_two_blueprint_ideas_are_one_idea_when_their_defaults_take_the_same_side():
    """The judge's second relation, between two ideas of the blueprint: another trigger or session, and still the same
    idea when the default variants take the same side on 70 % or more of 30 or more shared trading days (their build days)."""
    F.lead("bpl_pre", card={"home": {"market": "NQ", "session": "pre", "bar": "15"}, "neighbors": ["midday"]})
    root = F.fresh(NAME, "side", "bpl_pre")
    with F.tiny():
        a, b = FRZ.lock(NAME, root)["lock"], FRZ.lock("bpl_pre", root)["lock"]
    with F.reading("side"):
        assert OOS.test(NAME, confirm=True, root=root)["status"] == "proven_on_history"      # bpl_orb (the New York morning) has its read
    mine = READS._sides(b)                                                        # the real thing: {trade date: +1 | -1} of the default on its build days
    assert mine and set(mine.values()) <= {1, -1} and len(mine) <= len(F.DAYS) and all(isinstance(d, int) for d in mine)
    who = lambda: [x["name"] for x in READS.used("bpl_pre", b, root)["relatives"] if x["kind"] == "idea"]  # noqa: E731
    assert who() == []                                                            # another session, and 3 days are no 30: not the same idea
    keep = READS._sides
    try:
        for agree, shared, same in ((30, 40, True), (28, 40, True), (27, 40, False), (29, 29, False), (30, 30, True), (0, 40, False)):
            READS._sides = lambda lock, agree=agree, shared=shared: ({i: 1 for i in range(shared + 5)} if lock["name"] == "bpl_pre" else
                                                                     {i: (1 if i < agree else -1) for i in range(shared)})
            assert who() == ([NAME] if same else []), (agree, shared)
        READS._sides = lambda lock: {i: 1 for i in range(40)} if lock["name"] == "bpl_pre" else {i: (1 if i < 30 else -1) for i in range(40)}
        rel = [x for x in READS.used("bpl_pre", b, root)["relatives"] if x["name"] == NAME][0]
        assert rel["why"] == "its default variant takes the same side as this one's on 75 % of 40 shared trading days" and rel["state"] == "judged"
        with F.reading("side"), F.no_engine():
            why = F.refused(lambda: OOS.test("bpl_pre", confirm=True, root=root), "whose history is used")      # (an old saved strategy is its relative too: named first)
        assert "orb-NQ-tf15-pre" in why and "the idea bpl_orb (its default variant takes the same side" in why      # ... and every relative with a read is named
    finally:
        READS._sides = keep
    assert (J.SAME_SIDE, J.SAME_DAYS) == (0.70, 30) and a["hash"] != b["hash"]


# ================================================================ (f) seed-reads

HEAD = {"year": ["utc", "unit", "period", "role", "store", "seeds", "origin", "draws", "verdict"],
        "raw": ["utc", "unit", "store", "cells", "period", "kind", "seeds", "why"],
        "pick": ["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"]}


def _csv(path: Path, head: list, rows: list) -> Path:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(rows)
    return path


def test_which_rows_of_the_old_logs_mean_a_read_of_the_test_days():
    d = F.tmp() / "old_logs"
    d.mkdir(exist_ok=True)
    year = _csv(d / "year.csv", HEAD["year"], [
        ["2026-10-04T10:00:00+00:00", "aa-NQ-tf15-mid", "pick", "2024 menu", "runs_v2/aa-NQ-tf15-mid-pick", "", "new", 4000, "MEMBER"],       # 2024: inside the build days
        ["2026-10-05T10:00:00+00:00", "aa-NQ-tf15-mid", "check", "BUILD menu", "runs/aa-NQ-tf15", "", "new", 4000, "WEAK"],
        ["2026-10-05T10:00:00+00:00", "aa-NQ-tf15-mid", "check", "2025 menu", "runs_check2025/aa-NQ-tf15-mid-check", "", "new", 4000, "WEAK"],
        ["2026-10-05T11:00:00+00:00", "bb-GC-tf30-pre@A", "check", "2025 menu", "runs_check2025/bb-GC-tf30-pre-check", "", "new", 4000, "CONFIRMED"],
        ["2026-10-05T12:00:00+00:00", "bb-GC-tf30-pre@A", "exam", "2026 menu", "runs_exam2026/bb-GC-tf30-pre-exam", "", "new", 4000, "FAILED"],
        ["2026-10-04T09:00:00+00:00", "cc-ES-tf5-pm", "pick", "2024 menu", "runs_v2/cc-ES-tf5-pm-pick", "", "new", 4000, "fails 2024: 4"]])      # never read after 2024
    check = _csv(d / "check.csv", HEAD["raw"], [
        ["2026-10-05T09:00:00+00:00", "aa-NQ-tf15-mid", "runs_check2025/aa-NQ-tf15-mid-check", 96, "check (2025)", "base", "", "the menu"],
        ["2026-10-05T09:01:00+00:00", "bb-GC-tf30-pre", "runs_check2025/bb-GC-tf30-pre-check", 27, "check (2025)", "base", "", "all-days store of @A"],
        ["2026-10-05T09:02:00+00:00", "c1-NQ-tf15-mid", "runs_check2025/c1-NQ-tf15-mid-check", 64, "check (2025)", "control", "1-2", "a random pool: no strategy"],
        ["2026-10-05T09:03:00+00:00", "dd-NQ-tf30-eve", "runs_check2025/dd-NQ-tf30-eve-check", 96, "check (2025)", "base", "", "run, and no verdict rests on it"],
        ["2026-10-05T09:04:00+00:00", "dd-NQ-tf30-eve", "runs_check2025/dd-NQ-tf30-eve-check-shift", 96, "check (2025)", "control", "1-2", "its random-minute control"]])
    exam = _csv(d / "exam.csv", HEAD["raw"], [
        ["2026-10-05T12:00:00+00:00", "bb-GC-tf30-pre", "runs_exam2026/bb-GC-tf30-pre-exam", 27, "exam (2026-01-01..2026-09-22)", "base", "", "allowed @A"]])
    pick = _csv(d / "pick.csv", HEAD["pick"], [
        ["2026-10-04T09:00:00+00:00", "cc-ES-tf5-pm-pick", "cc", "ES", "5", "pm", "whole menu", 128, "2024"],
        ["2026-10-04T09:00:00+00:00", "runs_seeds/c1-ES-tf5-pm-pick-s3to10", "random", "ES", "5", "pm", "c1 control, seeds 3-10", 256, "2024"]])
    logs = dict(year=year, check=check, exam=exam, pick=pick)
    old = READS.old(**logs)
    # aa: its 2025 verdict · bb@A: 2025 and 2026 (the range the 2026 runner wrote) · dd: a table that was run on 2025 and never judged ·
    # cc (2024 only), the c1 pool and bb's all-days store (bb@A's verdict rests on it) are not units of their own
    assert list(old) == ["aa-NQ-tf15-mid", "bb-GC-tf30-pre@A", "dd-NQ-tf30-eve"]
    assert [(u["name"], u["read"], u["range"]) for u in old.values()] == [
        ("aa_nq_tf15_mid", {"2025": "WEAK"}, {"start": "2025-01-01", "end": "2025-12-31"}),
        ("bb_gc_tf30_pre_eva", {"2025": "CONFIRMED", "2026": "FAILED"}, {"start": "2025-01-01", "end": "2026-09-22"}),
        ("dd_nq_tf30_eve", {"2025": "run"}, {"start": "2025-01-01", "end": "2025-12-31"})]
    b = old["bb-GC-tf30-pre@A"]
    assert (b["family"], b["market"], b["bar"], b["session"], b["filter"], b["utc"]) == ("bb", "GC", "30", "pre", "A", "2026-10-05T12:00:00+00:00")
    assert b["verdict"] == "OLD READ 2026-10-05, before the blueprint: 2025 CONFIRMED, 2026 FAILED (out/judge/year_reads.csv)" and old["aa-NQ-tf15-mid"]["stores"] == ["runs_check2025/aa-NQ-tf15-mid-check"]
    assert all(IS.validate_name(u["name"]) == u["name"] for u in old.values()) and READS.old(year=d / "none.csv", check=d / "none.csv", exam=d / "none.csv", pick=d / "none.csv") == {}
    # ---- the command: --dry-run writes nothing and says what it would add; a run adds one line a unit; a second run adds nothing
    root = F.tmp() / "ideas" / "seed"
    dry = READS.seed(dry_run=True, root=root, **logs)
    assert list(dry)[:len(F.CONTRACT)] == list(F.CONTRACT) and (dry["command"], dry["dry_run"], dry["saved"]) == ("seed-reads", True, [])
    assert dry["would_add"] == ["aa_nq_tf15_mid", "bb_gc_tf30_pre_eva", "dd_nq_tf30_eve"] and "added" not in dry and not root.exists()
    assert dry["text"].split("\n")[0].startswith("DRY RUN: nothing is written. 3 units had their test days (2025-07-01 on) read before the blueprint; 0 on file already, would add 3")
    one = READS.seed(root=root, **logs)
    assert one["added"] == dry["would_add"] and one["saved"] == [str(root / "test_reads.jsonl")] and "would_add" not in one
    log = reads(root)
    assert [(x["name"], x["version"], x["lock"], x["range"], x["state"], x["verdict"]) for x in log] == [
        (u["name"], 0, "old:" + u["unit"], u["range"], "judged", u["verdict"]) for u in old.values()]
    before = (root / "test_reads.jsonl").read_bytes()
    two = READS.seed(root=root, **logs)
    assert two["added"] == [] and two["saved"] == [] and all(x["on_file"] for x in two["units"]) and (root / "test_reads.jsonl").read_bytes() == before
    assert READS.seed(dry_run=True, root=root, **logs)["would_add"] == [] and (root / "test_reads.jsonl").read_bytes() == before
    # a unit that is in the log already (an idea of that name was tested) is left alone; a new one is added, after the lines that are there
    IS.log_read("ee_nq_tf5_pm", version=1, lock="77aa", rng={"start": "2025-07-01", "end": "2026-09-22"}, state="judged", verdict="NOT PROVEN", root=root)
    _csv(year, HEAD["year"], [["2026-10-05T10:00:00+00:00", "ee-NQ-tf5-pm", "check", "2025 menu", "runs_check2025/ee-NQ-tf5-pm-check", "", "new", 4000, "FAILED"],
                              ["2026-10-05T10:00:00+00:00", "ff-NQ-tf5-pm", "check", "2025 menu", "runs_check2025/ff-NQ-tf5-pm-check", "", "new", 4000, "FAILED"]])
    three = READS.seed(root=root, **{**logs, "check": d / "none.csv", "exam": d / "none.csv"})
    assert three["added"] == ["ff_nq_tf5_pm"] and (root / "test_reads.jsonl").read_bytes().startswith(before) and len(reads(root)) == 5
    assert IS.read_on_file("ee_nq_tf5_pm", root=root)["verdict"] == "NOT PROVEN"


def test_seed_reads_on_this_machines_logs_the_fifteen_saved_strategies():
    old = READS.old()
    if not old:
        import pytest
        pytest.skip("the old read logs are not on this machine")
    members = sorted(p.name for p in LB.MEMBERS.iterdir() if p.is_dir() and not p.name.startswith("_"))
    assert len(old) == 15 and sorted(u["name"] for u in old.values()) == sorted(m.lower() for m in members)      # the 15 saved strategies, by the judge's own names
    assert sorted(u["unit"] for u in old.values() if "2026" in u["read"]) == sorted(json.loads(J.ALLOWED.read_text())["units"])      # ... 5 of them read on 2026 too
    assert all(u["range"]["start"] == "2025-01-01" and u["range"]["end"] in ("2025-12-31", "2026-09-22") and u["sources"] == ["out/judge/year_reads.csv"] for u in old.values())
    assert not [u for u in old.values() if u["unit"].startswith("c1-")] and all(len(u["name"]) <= 40 for u in old.values())
    # the command line, as a person and as the connector's JSON; a temp root, never the app's own folder
    root = F.tmp() / "ideas" / "seed_real"
    rc, js = F.run_cli(["seed-reads", "--dry-run", f"--root={root}", "--json"])
    d = json.loads(js)
    assert rc == 0 and (d["ok"], d["command"], d["name"], d["phase"], d["dry_run"]) == (True, "seed-reads", None, None, True) and len(d["would_add"]) == 15 and not root.exists()
    rc, txt = F.run_cli(["seed-reads", f"--root={root}"])
    assert rc == 0 and txt.count("\n  ADDED ") == 15 and "orb_nq_tf15_pre" in txt and len(reads(root)) == 15
    rc, js = F.run_cli(["seed-reads", f"--root={root}", "--json"])
    assert rc == 0 and json.loads(js)["added"] == [] and len(reads(root)) == 15
    assert all(IS.read_on_file(u["name"], version=0, lock="old:" + u["unit"], root=root)["state"] == "judged" for u in old.values())
    _T["seed"] = d["text"]
    RESULTS["test_seed_reads_on_this_machines_logs_the_fifteen_saved_strategies"] = (15, 15, "units: the saved strategies; a second run adds none")


# ================================================================ (g) the reader's seal

def test_the_reader_refuses_a_store_that_is_not_this_locks_read():
    root, lock, _, _ = _passed()
    out = F.read_out("pass")
    sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
    K = RUN.test_keys(KEY, NAME, "NQ", "15", "nyam")
    t = T.tested(sp, lock, out)                                                   # the stores of the read, as they are
    assert t["ids"] == lock["variants"] and t["net"].shape == (len(lock["variants"]), 8) and t["calendar"] == F.TEST_DAYS and t["worse_fills"] == "2 ticks + 250 ms + a 100 ms late cancel"
    assert [int(p["days"].sum()) for p in t["parts"]] == [4, 4] and float(t["net"].sum()) == 150.0 * 8 * len(lock["variants"]) and len(t["worse"]) == len(lock["variants"])
    with F.no_engine():                                                           # read-only, and no engine call
        assert T.tested(sp, lock, out)["controls"]["c1"]["p_beat"] == 1.0
        F.refused(lambda: T.tested(sp, {**lock, "hash": "0" * 16}, out), "read of another lock")
        short = {**lock, "test_range": {"NQ": {**lock["test_range"]["NQ"], "end": "2026-09-21"}}}
        F.refused(lambda: T.tested(sp, short, out), "not a store of the test days")
        F.refused(lambda: T.tested(sp, lock, F.tmp() / "runs_nowhere"), "has not written it")
        F.refused(lambda: T.tested(sp, {**lock, "variants": [*lock["variants"], "or_min5_pct0p2-r3"]}, out), "lacks the locked variant")
        F.refused(lambda: T.tested(sp, lock, F.OUT), "has not written it")       # the build's folder holds no store of a read
    for key, edit, word in ((K["table"], {"period": "bp_build"}, "not a store of the test days"), (K["worse"], {"calendar": None, "read": {"lock": "0" * 16}}, "another lock"),
                            (K["table"], {"calendar": []}, "which session days")):
        copy = F.tmp() / f"runs_seal_{word[:3]}"
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(out, copy)
        m = F.read(copy / key / "run.json")
        (copy / key / "run.json").write_text(json.dumps({**m, **edit}))
        J.reset()
        F.refused(lambda copy=copy: T.tested(sp, lock, copy), word)
    # a pool with fewer seeds than the lock froze; a trade dated outside the frozen range
    root2, lock2 = F.frozen(NAME, "thin")
    with F.reading("thin", seeds=[1, 2, 3]):
        why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root2), "3 of the 10 seeds")
    assert "THE READ STAYS ON FILE" in why and [x["state"] for x in reads(root2)] == ["claimed"]
    root3, lock3 = F.frozen(NAME, "late")
    with F.reading("late", days=[*F.TEST_DAYS[:-1], "2026-09-30"]):
        F.refused(lambda: OOS.test(NAME, confirm=True, root=root3), "outside 2025-07-01 .. ")
    J.reset()
    assert RUN.guard_test({"period": "x", "range": {"period": "x", "start": "2025-07-01", "end": "2026-09-22"}, "read": {"lock": "ab"}}, "a/b", "2025-07-01", "2026-09-22", "ab")
    for bad in ({"period": "bp_build", "range": {"period": "bp_build", "start": "2025-07-01", "end": "2026-09-22"}}, {"range": {"start": "2025-07-01", "end": "2026-09-22"}},
                {"period": "x", "range": {"period": "y", "start": "2025-07-01", "end": "2026-09-22"}}, {"period": "x", "range": {"period": "x", "start": "2021-09-22", "end": "2025-06-30"}}, {}):
        F.refused(lambda bad=bad: RUN.guard_test(bad, "a/b", "2025-07-01", "2026-09-22"), "not a store of the test days")


# ================================================================ (h) the runner of the one read

def test_the_runner_opens_nothing_without_a_claimed_read():
    """runner.run_test for an idea whose test days are UNSEEN (bpl_orb): every call here must stop before the engine."""
    root, lock = F.frozen(NAME, "runner")
    sp, out, end = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0]), F.tmp() / "runs_test_runner", lock["test_range"]["NQ"]["end"]
    rd, days, n = {"version": 1, "lock": lock["hash"]}, ["2025-08-20", "2026-03-18"], 0
    rng = {"start": "2025-07-01", "end": end}

    def go(**kw):
        a = {"name": NAME, "read": rd, "spec": sp, "key": KEY, "sess": "nyam", "variants": lock["variants"], "store": NAME, "end": end, "workers": 1, "out_dir": out,
             "ideas": root, "ledger": F.tmp() / "ledger_runner.csv", "days": days, **kw}
        return RUN.run_test(a.pop("name"), a.pop("read"), a.pop("spec"), a.pop("key"), a.pop("sess"), a.pop("variants"), a.pop("store"), a.pop("end"), a.pop("workers"),
                            a.pop("out_dir"), **a)

    def no(word: str, **kw) -> str:
        nonlocal n
        n += 1
        return F.refused(lambda: go(**kw), word)

    if not hasattr(S, "ALLOW_BT"):
        with F.tiny(), F.no_engine():
            no("no switch for the test days", dry=True)
        import pytest
        pytest.skip("the engine has no switch for the test days yet")
    with F.tiny(), F.no_engine():
        # ---- what a preflight says (dry: nothing is asked of the log, nothing is opened): the three stores of the read, to be run
        pre = go(dry=True)
        K = RUN.test_keys(KEY, NAME, "NQ", "15", "nyam")
        assert [(s["key"], s["kind"], s["stage"], s["skipped"], s["ok"]) for s in pre["stores"]] == [
            (K["pool"], "pool", "null_bp_test", False, None), (K["table"], "unit", "bp_test", False, None), (K["worse"], "worse", "bp_test_worse", False, None)]
        assert (pre["calendar"], pre["trades"]) == (None, {}) and [s["cells"] for s in pre["stores"]] == [480, len(lock["variants"]), len(lock["variants"])]
        assert K == {"table": "bpl_orb-NQ-tf15-nyam-test", "worse": "bpl_orb-NQ-tf15-nyam-test-worse", "pool": "bpl_orb__c1-NQ-tf15-nyam-test"} and RUN.TESTS == LB.W / "runs_bp_test"
        # ---- the dates are the frozen range's, and a read of named days is a test of the plumbing with its own folder and ledger
        for bad in (["2025-06-30"], ["2025-08-20", "2024-03-15"], ["2026-09-23"], ["2027-01-04"], []):
            no("reads 2025-07-01 .. ", days=bad, dry=True)
        no("reads 2025-07-01 .. ", end="2025-06-30", dry=True)
        no("its own store folder", out_dir=None, dry=True)
        no("its own store folder", ledger=None, dry=True)
        no("ISO dates", days=["soon"], dry=True)
        no("not a table of", key="bpl_other-NQ-tf15", dry=True)
        no("not a table of", sess="pm", dry=True)
        no("not a cell of the unit", variants=[*lock["variants"], "or_min5_nope-r9"], dry=True)
        no("no variant to run", variants=[], dry=True)
        for w in (0, 9):
            no("workers", workers=w, dry=True)
        # ---- THE CLAIM: without the read in the one-read log, claimed for THIS lock and not yet judged, nothing is opened
        assert "written to the log BEFORE the pass" in no("no claimed read")
        IS.claim_read(NAME, version=1, lock="0" * 16, rng=rng, root=root)        # a claim -- of another lock
        no("no claimed read")
    root2 = F.fresh(NAME, "runner2")
    with F.tiny(), F.no_engine():
        IS.claim_read(NAME, version=2, lock=lock["hash"], rng=rng, root=root2)   # ... of another version
        no("no claimed read", ideas=root2)
        root3 = F.fresh(NAME, "runner3")
        IS.claim_read(NAME, version=1, lock=lock["hash"], rng=rng, root=root3)   # ... or one that was judged: the read is over
        IS.log_read(NAME, version=1, lock=lock["hash"], rng=rng, state="judged", verdict="NOT PROVEN", root=root3)
        assert "a read that was judged is over" in no("no claimed read", ideas=root3)
    assert not out.exists() and not (F.tmp() / "ledger_runner.csv").exists()     # nothing was opened, nothing was written
    RESULTS["test_the_runner_opens_nothing_without_a_claimed_read"] = (n, n, "refusals of the runner, each before the engine")


OLD_STORES = {  # the stores of the old 2025 and 2026 runs that hold bpl_fbm's cells: (folder, key, the days of REAL_DAYS it covers)
    "table": [("runs_check2025", "first_bar_mom-NQ-tf15-mid-check", 0), ("runs_exam2026", "first_bar_mom-NQ-tf15-mid-exam", 1)],
    "worse": [("runs_check2025", "first_bar_mom-NQ-tf15-mid-check-stress", 0), ("runs_exam2026", "first_bar_mom-NQ-tf15-mid-exam-stress", 1)],
    "pool": [("runs_check2025", "c1-NQ-tf15-mid-check", 0), ("runs_seeds", "c1-NQ-tf15-mid-check-s3to10", 0), ("runs_exam2026", "c1-NQ-tf15-mid-exam", 1)]}


def _real_ok() -> None:
    import pytest
    if not hasattr(S, "ALLOW_BT"):
        pytest.skip("the engine has no switch for the test days yet")
    if S.compute_window_end() is not None:
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    if not all((LB.W / d / k / "run.json").exists() for v in OLD_STORES.values() for d, k, _ in v) or "first_bar_mom-NQ-tf15-mid" not in READS.old():
        pytest.skip("the stores of the old 2025 / 2026 runs are not on this machine")
    if not all(S.tape_path(d, "NQ").exists() for d in F.REAL_DAYS):
        pytest.skip("the tapes of the days are not on this machine")


def _same(out: Path, key: str, olds: list) -> tuple:
    """A store of the read against the old stores, trade for trade on their days -> (cells compared, stored trades, cells that differ)."""
    import datetime as dt
    mine, cells, n, diff = LB.load_unit(key, out), 0, 0, 0
    for d, k, part in olds:
        old = LB.load_unit(k, LB.W / d)
        ids, ords = {c["id"] for c in old["meta"]["cells"]}, [dt.date.fromisoformat(x).toordinal() for x in F.REAL_DAYS[2 * part:2 * part + 2]]
        for c in mine["meta"]["cells"]:
            if c["id"] in ids:
                a, b = LB.unit_cell(mine, c["id"]), LB.unit_cell(old, c["id"])
                ma, mb = np.isin(a["date"], ords), np.isin(b["date"], ords)
                x, y = (sorted(zip(v["entry_ms"][m].tolist(), np.round(v["net"][m], 2).tolist(), v["side"][m].tolist())) for v, m in ((a, ma), (b, mb)))
                cells, n, diff = cells + 1, n + len(y), diff + (x != y)
    return cells, n, diff


def test_the_one_real_read_replays_cells_that_are_already_on_disk():
    """bpl_fbm = first_bar_mom on NQ, 15-minute bars, midday: an OLD SAVED STRATEGY (2025 and 2026 were read for it before the
    blueprint). So the test is refused -- and as an explicit SECOND LOOK, on 4 named days, it replays nothing that is not on
    disk already: its variants, their worse fills and the 10 random-entry seeds are held against the old stores trade for
    trade. Counts only; no P&L of a test day is asserted or printed."""
    _real_ok()
    F.fbm()
    root, lock = F.frozen(F.FBM, "real")
    out, calls, keep = F.tmp() / "runs_test_real", [], (S.run_many, S.sessions)

    def ran(specs, *a, **k):
        calls.append({"fn": "run_many", "args": [str(x) for x in a], **{x: k.get(x) for x in ("period", "days", "allow_holdout", "allow_exam", "allow_check", "slip_ticks",
                                                                                              "latency_ms", "costs", "root")}, "specs": len(specs)})
        return keep[0](specs, *a, **k)

    def listed(*a, **k):
        calls.append({"fn": "sessions", "args": [str(x) for x in a], **k})
        return keep[1](*a, **k)

    assert set(lock["variants"]) <= {"k1_atr3-r1", "k1_pts20-r0", "k1p5_atr3-r1", "k1p5_pts20-r0", "k2_atr3-r1", "k2_pts20-r0"} and lock["costs"]["worse"]["two_sided"] is False
    with F.tiny(**F.settings(F.FBM), test_days=F.REAL_DAYS, test_out=str(out)):
        with F.no_engine():                                                      # refused first: its history is used
            why = F.refused(lambda: OOS.test(F.FBM, confirm=True, root=root), "one of the old saved strategies whose history is used")
        assert "first_bar_mom-NQ-tf15-mid" in why and reads(root) == [] and not out.exists()
        S.run_many, S.sessions = ran, listed
        try:
            r = OOS.test(F.FBM, confirm=True, second_look=True, root=root)
        finally:
            S.run_many, S.sessions = keep
    # ---- every engine call of the read: the TEST switch by its name, the frozen range named, the 4 named days, no other switch
    end = lock["test_range"]["NQ"]["end"]
    runs, lists = [c for c in calls if c["fn"] == "run_many"], [c for c in calls if c["fn"] == "sessions"]
    assert len(runs) == 2 and all(c["args"] == ["2025-07-01", end] and c["days"] == F.REAL_DAYS and c["allow_holdout"] == S.ALLOW_BT == "bp_test" and c["root"] == "NQ"
                                  and c["period"] is None and not c["allow_exam"] and not c["allow_check"] and c["costs"] is None for c in runs), runs
    assert [(c["slip_ticks"], c["latency_ms"], c["specs"]) for c in runs] == [(None, None, 480 + len(lock["variants"])), (2.0, 250, len(lock["variants"]))]
    assert {"fn": "sessions", "args": ["2025-07-01", end, "NQ"], "allow_holdout": "bp_test"} in lists                 # the session list of the frozen range
    assert not [c for c in calls if c.get("allow_exam") or c.get("allow_check") or c.get("allow_holdout") is True or "True" in c["args"]]      # never the EXAM key
    # ---- the three stores: of the frozen range, of this lock's read, of the days that were replayed -- and booked
    K = RUN.test_keys(lock["home"]["key"], F.FBM, "NQ", "15", "mid")
    for which, stage in (("pool", "null_bp_test"), ("table", "bp_test"), ("worse", "bp_test_worse")):
        m = F.read(out / K[which] / "run.json")
        assert (m["stage"], m["period"], m["range"], m["calendar"], m["days"]) == (stage, "bp_test", {"start": "2025-07-01", "end": end, "holdout": True, "period": "bp_test"},
                                                                                 F.REAL_DAYS, F.REAL_DAYS), which
        assert (m["read"]["name"], m["read"]["version"], m["read"]["lock"], m["sessions"]) == (F.FBM, 1, lock["hash"], ["mid"]) and m["read"]["claimed_utc"] == reads(root)[-2]["utc"]
        assert RUN.guard_test(m, K[which], "2025-07-01", end, lock["hash"]) is m
    led = [(x["stage"], x["key"], x["kind"], x["period"]) for x in LB.read_ledger(F.tmp() / "ledger_fbm.csv") if "test" in x["key"]]
    assert led == [("null_bp_test", K["pool"], "null", "bp_test"), ("bp_test", K["table"], "grid", "bp_test"), ("bp_test_worse", K["worse"], "grid", "bp_test")]
    assert F.read(out / K["worse"] / "run.json")["run_kw"] == {"slip_ticks": 2.0, "latency_ms": 250} and len(F.read(out / K["pool"] / "run.json")["cells"]) == 480
    # ---- TRADE FOR TRADE what the old 2025 and 2026 stores hold: nothing new was produced on the test days
    counts = {which: _same(out, K[which], olds) for which, olds in OLD_STORES.items()}
    for which, (cells, n, diff) in counts.items():
        assert cells > 0 and n > 0 and diff == 0, f"{which}: {diff} of {cells} cells differ from the old stores ({n} stored trades)"
    assert counts["table"][0] == counts["worse"][0] == 2 * len(lock["variants"]) and counts["pool"][0] == 640       # every cell of the read, on both parts
    # ---- the read went the whole way: claimed, run, judged; labelled a SECOND LOOK; every line in the result (their numbers are not looked at here)
    assert [x["line"] for x in r["lines"]] == F.TEST_LINES and all(type(x["passed"]) is bool and x["text"].endswith("[SECOND LOOK]") for x in r["lines"])
    assert r["verdict"].startswith("SECOND LOOK: ") and r["second_look"] is True and {"first_bar_mom_nq_tf15_mid", "first_bar_mom_nq_tf30_mid"} <= set(r["second_look_of"])
    assert [(x["state"], x.get("second_look")) for x in reads(root)] == [("claimed", True), ("judged", None)] and reads(root)[-1]["verdict"] == r["verdict"]
    assert r["days"]["sessions"] == 4 and [p["sessions"] for p in r["days"]["parts"]] == [2, 2] and r["days"]["named"] == F.REAL_DAYS and r["test_run"] is True
    assert r["status"] == IS.status(F.FBM, root) and F.read(root / F.FBM / "test.json")["verdict"] == r["verdict"]
    st = LB.load_unit(K["table"], out)
    assert r["default"]["trades"] == len(LB.unit_cell(st, lock["default"])["net"]) and (r["default"]["run_id"] or not F.APP_PYTHON.exists())
    with F.tiny(**F.settings(F.FBM), test_days=F.REAL_DAYS, test_out=str(out)), F.no_engine():      # ... and it was THE read: there is no other
        F.refused(lambda: OOS.test(F.FBM, confirm=True, second_look=True, root=root), "already on file")
    said = " · ".join(f"{which}: {cells} cells x stores, {n} stored trades, {diff} differ" for which, (cells, n, diff) in counts.items())
    print(f"real read of 4 days, cells already on disk ({said})", flush=True)
    RESULTS["test_the_one_real_read_replays_cells_that_are_already_on_disk"] = (sum(c for c, _, _ in counts.values()), sum(c for c, _, _ in counts.values()), said)


# ================================================================ (i) the command lines, and the app's connector

def test_the_command_line_of_the_test():
    root = F.fresh(NAME, "cmd")
    last = [f"--root={root}", "--json"]
    with F.reading("cmd"), F.no_engine():
        for argv, word in ((["test", NAME, "--confirm"], "not frozen"), (["test", "bpl_nobody", "--confirm"], "no card"), (["test", "--confirm"], "name"),
                           (["test", NAME, "--confirm", "--days=2025-07-01"], "unrecognized")):
            rc, js = F.run_cli([*argv, *last])
            d = json.loads(js)
            assert rc == 2 and list(d) == list(F.CONTRACT) and d["ok"] is False and word in d["error"] and (d["command"], d["phase"], d["lines"]) == ("test", 4, []), (argv, d)
    with F.tiny():
        FRZ.lock(NAME, root)
    with F.reading("cmd"):
        with F.no_engine():
            rc, js = F.run_cli(["test", NAME, *last])                            # --confirm is the owner's word: without it nothing happens
            d = json.loads(js)
            assert rc == 2 and "--confirm" in d["error"] and d["error"].startswith("the test days are read ONCE") and reads(root) == []
            rc, txt = F.run_cli(["test", NAME, f"--root={root}"])
            assert rc == 2 and txt.startswith("REFUSED: the test days are read ONCE")
        rc, txt = F.run_cli(["test", NAME, "--confirm", f"--root={root}"])       # a person: the read in words, the seven lines, the next step
        lines = txt.rstrip("\n").split("\n")
        assert rc == 0 and lines[0].startswith("OUT-OF-SAMPLE TEST 2025-07-01 .. ") and [ln[:8] for ln in lines[2:11]] == [f"{k} PASS" for k in F.TEST_LINES]
        assert "RESULT: PROVEN ON HISTORY" in txt and lines[-1].startswith("NEXT: Proven on history") and len(reads(root)) == 2
        with F.no_engine():
            rc, js = F.run_cli(["test", NAME, "--confirm", *last])               # the test days are read once: exit 2 from here on
            d = json.loads(js)
            assert rc == 2 and "already on file" in d["error"] and d["command"] == "test" and len(reads(root)) == 2
            rc, js = F.run_cli(["status", NAME, *last])
            s = json.loads(js)
            assert rc == 0 and (s["status"], s["phase"]) == ("proven_on_history", 4) and [x["line"] for x in s["lines"]] == F.TEST_LINES and "bp.py sim" in s["next"]
            lock = F.read(root / NAME / "lock.json")                             # the full record: the lock, the read and its verdict, the lines with their numbers
            assert s["record"]["lock"] == {k: lock[k] for k in ("hash", "version", "round", "locked_utc", "default", "test_range")}
            assert (s["record"]["read"]["state"], s["record"]["read"]["verdict"]) == ("judged", "PROVEN ON HISTORY") and s["lines"][2]["number"] == 150.0
            assert f"FROZEN · lock {lock['hash']}" in s["text"] and "TEST DAYS READ · judged" in s["text"] and "PROVEN ON HISTORY" in s["text"]


def test_the_read_as_a_job_through_the_front_door():
    """`test <name> --confirm --second-look --wait=S` as the toolkit runs it for the connector: the read is claimed by the
    command, the pass is a detached job, `job <id>` picks the wait back up and answers with the test's own result. The job
    is the REAL runner in its own process: so it is bpl_fbm on its 4 days again (cells that are on disk), into its own folder."""
    _real_ok()
    F.fbm()
    root, lock = F.frozen(F.FBM, "job")
    out, last = F.tmp() / "runs_test_job", [f"--root={root}", "--json"]
    with F.tiny(**F.settings(F.FBM), test_days=F.REAL_DAYS, test_out=str(out)):
        rc, js = F.run_cli(["test", F.FBM, "--confirm", "--wait=0", *last])      # refused at once, never as a job: nothing claimed
        d = json.loads(js)
        assert rc == 2 and d["job"] is None and "old saved strategies" in d["error"] and reads(root) == [] and not (root / "_jobs").exists()
        rc, js = F.run_cli(["test", F.FBM, "--confirm", "--second-look", "--wait=0", *last])
        d = json.loads(js)
        assert rc == 0 and (d["ok"], d["command"], d["name"], d["phase"], d["lines"]) == (True, "test", F.FBM, 4, []) and d["job"]["state"] in ("queued", "running")
        jid = d["job"]["id"]
        assert [(x["state"], x["lock"], x["second_look"]) for x in reads(root)] == [("claimed", lock["hash"], True)]      # claimed BEFORE the job started
        rc, js = F.run_cli(["test", F.FBM, "--confirm", "--second-look", *last])          # while it runs (and after): no second read
        e = json.loads(js)
        assert rc == 2 and ("still running" in e["error"] or "already on file" in e["error"])
        for _ in range(30):
            rc, js = F.run_cli(["job", jid, "--wait=20", *last])
            d = json.loads(js)
            if d["job"]["state"] not in ("queued", "running"):
                break
    assert rc == 0 and d["job"] == {"id": jid, "state": "done", "progress": d["job"]["progress"]} and d["ok"] and d["command"] == "test", d
    assert [x["line"] for x in d["lines"]] == F.TEST_LINES and d["verdict"].startswith("SECOND LOOK: ") and d["status"] == IS.status(F.FBM, root)
    assert [x["state"] for x in reads(root)] == ["claimed", "judged"] and F.read(root / F.FBM / "test.json")["verdict"] == d["verdict"]
    K = RUN.test_keys(lock["home"]["key"], F.FBM, "NQ", "15", "mid")
    counts = {which: _same(out, K[which], olds) for which, olds in OLD_STORES.items()}
    assert all(cells > 0 and n > 0 and diff == 0 for cells, n, diff in counts.values()), counts      # the job's stores too: what the old stores hold
    assert F.read(root / "_jobs" / jid / "job.json")["command"] == "test" and F.read(root / "_jobs" / jid / "result.json") == d


CONNECTOR = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from homebase.claude_mcp import blueprint_tools, tools
from homebase.claude_mcp.client import Client, ToolError
box = tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None)
out = []
for tool, args in json.loads(sys.argv[2]):
    try:
        out.append(box.call(tool, args))
    except ToolError as e:
        out.append("ToolError: " + str(e))
out.append(blueprint_tools._report(json.load(open(sys.argv[3]))))      # a finished read as the tool words it (its result object, from the toolkit)
print(json.dumps(out))
'''


def test_the_apps_connector_against_this_toolkit():
    """homebase/claude_mcp/blueprint_tools.py (the app's Python) starts THIS bp.py: blueprint_lock freezes the idea and
    answers with the hash, the default and the test range; blueprint_test without the owner's word is refused by the tool
    itself, and for an old saved strategy by the toolkit (the tool has no second look to offer). The idea folder, the Lab
    and the stores are temp folders; no test day is opened."""
    if not F.APP_PYTHON.exists():
        import pytest
        pytest.skip(f"the app's Python is not there: {F.APP_PYTHON}")
    if S.compute_window_end() is not None:
        import pytest
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    F.fbm()
    root, name = F.fresh(F.FBM, "app"), F.FBM
    done = F.tmp() / "a_finished_read.json"
    done.write_text(json.dumps(_passed()[2]))
    calls = [("blueprint_status", {"name": name}), ("blueprint_lock", {"name": name}), ("blueprint_lock", {"name": name}), ("blueprint_lock", {"name": "bpl_nobody"}),
             ("blueprint_test", {"name": name, "confirm": False}), ("blueprint_test", {"name": name, "confirm": True, "wait_s": 30}), ("blueprint_status", {"name": name})]
    env = {**os.environ, "HOMEBASE_IDEAS_ROOT": str(root), "HOMEBASE_DRAFTS_DIR": str(F.tmp() / "drafts_app"), "HOMEBASE_BP": str(F.W / "bp.py"),
           "HOMEBASE_BP_PYTHON": sys.executable,
           REC.TEST_RUN: json.dumps({**F.TINY, **F.settings(name), "test_days": F.REAL_DAYS, "test_out": str(F.tmp() / "runs_test_app")})}
    import subprocess
    q = subprocess.run([str(F.APP_PYTHON), "-B", "-c", CONNECTOR, str(S.REPO), json.dumps(calls), str(done)], capture_output=True, text=True, timeout=900, cwd=str(F.tmp()), env=env)
    assert q.returncode == 0, q.stderr[-2000:]
    before, lock, again, nobody, unconfirmed, refused, after, worded = json.loads(q.stdout)
    _T["blueprint_lock"], _T["blueprint_lock (again)"], _T["blueprint_test (an old saved strategy)"] = lock, again, refused
    _T["blueprint_test (a read that passed, as the tool words it)"] = worded
    saved = F.read(root / name / "lock.json")
    assert "before the freeze" in before or "freeze is next" in before
    head = lock.split("\n")
    assert head[0] == f"Blueprint lock · {name} · LEAD · phase 3 · round 1" and head[1].startswith(f"FROZEN now: {name} · lock {saved['hash']} · version 1 · round 1 · home NQ midday")
    assert lock.count("\n3.1 PASS ") == 1 and lock.count("\n3.2 PASS ") == 1 and f"DEFAULT VARIANT {saved['default']}" in lock and all(lock.count(f"\n3.{i} ") == 1 for i in range(3, 9))
    assert f"TEST RANGE NQ 2025-07-01 .. {saved['test_range']['NQ']['end']}" in lock and lock.count("Next: ") == 1 and "--confirm" in lock and "Saved: " in lock
    assert again.split("\n")[1].startswith(f"FROZEN already: {name} · lock {saved['hash']}") and "The lock matches the files on disk" in again and "Saved: " not in again
    assert nobody.startswith("ToolError: Refused (blueprint lock): ") and "no card" in nobody and "Nothing was run." in nobody
    assert unconfirmed.startswith("ToolError: confirm: must be true")             # the tool's own word: the toolkit is not even started
    assert refused.startswith("ToolError: Refused (blueprint test): ") and "old saved strategies whose history is used" in refused and "--second-look" in refused
    assert "Nothing was run." in refused and reads(root) == [] and not (root / name / "test.json").exists() and not (F.tmp() / "runs_test_app").exists()
    assert after.split("\n")[0] == f"Blueprint status · {name} · LEAD · phase 3 · round 1" and "FROZEN" in after
    assert worded.split("\n")[0] == "Blueprint test · bpl_orb · PROVEN ON HISTORY · phase 4 · round 1" and all(worded.count(f"\n4.{i} PASS ") == 1 for i in range(1, 10))
    assert "Lines: 9 passed · 0 FAILED" in worded and worded.count("Next: ") == 1 and "RESULT: PROVEN ON HISTORY" in worded


# ================================================================ nothing outside the temp folder

def test_nothing_was_written_outside_the_temp_folder():
    F.clean()
    assert not [k for k in (F._listing(RUN.TESTS) or []) if k.startswith("bpl_")], "a test wrote into runs_bp_test/"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
        except BaseException as e:                          # pytest.skip
            if type(e).__name__ != "Skipped":
                raise
            print(f"SKIP {name} ({e})", flush=True)
        finally:
            teardown_function()
    for what, text in ((k, v) for k, v in _T.items() if isinstance(v, str)):
        print(f"\n--- {what} ---\n{text}", flush=True)
    sys.exit(rc)
