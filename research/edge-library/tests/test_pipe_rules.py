"""LOCK of the pipeline's numbers (blueprint/templates/pipeline.json, read by blueprint/pipe_rules.py) -- pipeline plan A, task 1.

1. need(*keys) walks the file; a key it does not have (or a note, '_...') is refused with R.RuleError.
2. random_bar(tries) = 1 - alpha / tries: the law's ladder of line 2.3 carried on past its fifth round; floor(root, part) = a
   part of the cost floor of line 2.2.
3. A number that pipeline.json and rules.json both carry is the same in both, or nothing loads: edited in the one file only,
   or in the other only, the load raises R.RuleError and names the number.
4. The law's numbers the pipeline changed (2026-10-07): 80 % of the reshuffled runs at the lock (3.7) and on the test (4.7),
   the best 1 % of days taken out on the test (4.6) and, new, at the lock (3.8).
Reads the templates only: no store, no tape, no simulation. Under a second.

  pytest tests/test_pipe_rules.py -q          python tests/test_pipe_rules.py     the same, one line per test
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import rules as R  # noqa: E402

FILE = P.FILE


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except R.RuleError as e:
        assert word in str(e), f"refused, but not for {word!r}: {e}"
        return str(e)
    raise AssertionError(f"not refused ({word})")


def teardown_function(_=None):
    P.FILE = FILE
    P._all.cache_clear()


# ================================================================ 1. need() walks the file

def test_need_walks_the_file_and_refuses_what_it_does_not_have():
    assert P.FILE == R.T / "pipeline.json" and "pipeline" not in R.NAMES       # the pipeline's own file: no template of the law
    assert P.need("raw", "low", "share") == 0.5 and P.need("raw", "low") == {"share": 0.5, "floor_part": 0.5, "trades": 300}
    assert P.need("raw", "strict") == {"share": 0.6, "floor_part": 1.0, "trades": 200}
    assert P.need("indicator") == {"share": 0.6, "floor_part": 1.0, "trades": 200, "other_markets": None}   # None: shown, asks nothing (the owner, 2026-10-08)
    assert P.need("card") == {"ways": [1, 3], "values": 3, "indicators": [0, 5], "bars": ["1", "5"], "markets": ["NQ", "ES", "GC"],
                              "sessions": ["asia", "london", "pre", "nyam", "mid", "pm", "eve"]}      # the evening session too (the owner, 2026-10-09)
    assert P.need("proof") == {"reshuffle": 0.75, "random_alpha": 0.05} and P.need("box", "best_days_share") == 0.01
    assert P.need("box") == {"best_days_share": 0.01, "fast_seconds": 5, "month_days": 21}         # ... and the book card's two numbers (stage 7)
    assert P.need("prop") == {"account": "lucid-pro-50k-no-dll@2026-09-27b", "days": 30, "eval": 0.5, "payout": 0.5,
                              "book_accounts": ["lucid-pro-50k-no-dll@2026-09-27b", "lucid-flex-50k@2026-09-27", "apex-legacy-300k@2026-09-28"]}
    assert P.need("portfolio") == {"eval": {"days": 5, "odds": 0.6}, "payout": {"days": 14, "odds": 0.75}, "fast_share": 0.5,       # the bar, and what the design says of a mix
                                   "one_side": ["apex-legacy-300k@2026-09-28"], "funded_only": ["apex-legacy-300k@2026-09-28"]}     # that no rule file carries (stage 8, 2026-10-09)
    assert P.need("portfolio", "payout", "odds") == 0.75
    assert P.need("test") == {"one_read_a_slot": False} and P.need("test", "one_read_a_slot") is False      # every pipeline idea gets its own read (the owner, 2026-10-08)
    assert P.need("mode") == "variant" and P.mode() == "variant"                                  # the owner, 2026-10-08: the hard rules are judged on ONE picked variant
    assert P.need("variant") == {"map_share": 0.5, "region_boxes": 25, "region_trades": 200, "pick_boxes": 1, "box_tries": 5, "floor_part": 1.0, "without_best_trades": 0.05, "months_won": 0.7, "best_month_share": 0.1, "losing_day_streak": 8}      # the loose check of the map, and the one box's numbers
    assert set(P.need()) == {"mode", "variant", "card", "raw", "indicator", "proof", "box", "test", "prop", "portfolio", "mix"}      # the whole file, its notes left out
    assert P.need("mix") == {"member_may_fail": ["P3.8", "P3.9", "P3.10", "P4.1", "3.4", "3.5", "3.6"]}      # the build-day mix's admission (bp.py pipe mix; the owner, 2026-10-10: a PROPOSAL)
    assert "raw.nope" in refused(lambda: P.need("raw", "nope"), "pipeline.json has no")
    refused(lambda: P.need("nope"), "nope")
    refused(lambda: P.need("raw", "low", "share", "deeper"), "raw.low.share.deeper")               # a number has nothing under it
    refused(lambda: P.need("card", "ways", 0), "card.ways.0")                                     # a list is a value, not a level
    refused(lambda: P.need("_about"), "_about")                                                   # a note for the reader is no number
    P.need("raw")["low"]["share"] = 0.99                                                          # what a caller does to its copy ...
    assert P.need("raw", "low", "share") == 0.5                                                   # ... is not done to the rules


def test_the_mode_is_map_or_variant_and_nothing_else():
    """pipeline.json "mode": "variant" (default, 2026-10-08) judges one picked box; "map" is the legacy whole-map behaviour. A file that
    says another word does not load, and a file without the key reads as "map" (the files written before the mode existed)."""
    p = json.loads(FILE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        P.FILE = Path(tmp) / "pipeline.json"
        for mode, expect in (("map", "map"), ("variant", "variant")):
            P.FILE.write_text(json.dumps({**p, "mode": mode}), encoding="utf-8")
            P._all.cache_clear()
            assert P.mode() == expect
        P.FILE.write_text(json.dumps({k: v for k, v in p.items() if k != "mode"}), encoding="utf-8")
        P._all.cache_clear()
        assert P.mode() == "map"
        P.FILE.write_text(json.dumps({**p, "mode": "both"}), encoding="utf-8")
        P._all.cache_clear()
        refused(lambda: P.mode(), "mode")
    teardown_function()
    assert P.mode() == "variant"


# ================================================================ 2. the random bar and the floor

def test_the_random_bar_is_the_laws_ladder_carried_on():
    assert [P.random_bar(k) for k in (1, 2, 5)] == [0.95, 0.975, 0.99]
    assert abs(P.random_bar(11) - 0.9954545454545455) < 1e-12 and P.random_bar(11) == 1 - 0.05 / 11
    assert P.random_bar(0) == P.random_bar(-3) == P.random_bar(1) == 0.95                       # no try yet is held to the first bar
    assert all(round(P.random_bar(int(k)) - v, 3) == 0 for k, v in R.need("2.3").items()) and len(R.need("2.3")) == 5      # 98.3 % = 98.33 % printed short
    assert all(P.random_bar(k + 1) > P.random_bar(k) for k in range(1, 40)) and P.random_bar(10 ** 6) < 1.0                # every try raises it; never 100 %


def test_the_floor_is_a_part_of_line_2_2():
    assert [P.floor(m, 1.0) for m in ("NQ", "ES", "GC")] == [70, 75, 140] == [P.floor(m, P.need("raw", "strict", "floor_part")) for m in ("NQ", "ES", "GC")]
    assert [P.floor(m, P.need("raw", "low", "floor_part")) for m in ("NQ", "ES", "GC")] == [35.0, 37.5, 70.0]
    refused(lambda: P.floor("CL", 1.0), "CL")                                                     # a market the law names no floor for


# ================================================================ 3. the two files never disagree

def _edited(path: tuple, value) -> dict:
    p = copy.deepcopy(json.loads(FILE.read_text(encoding="utf-8")))
    d = p
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value
    return p


def test_the_file_on_disk_agrees_with_the_law():
    assert P.check(json.loads(FILE.read_text(encoding="utf-8"))) == []
    assert P.need("raw", "strict", "share") == R.need("2.1") and P.need("raw", "strict", "trades") == R.need("2.4")
    assert P.need("proof", "reshuffle") == R.need("2.8") and P.need("box", "best_days_share") == R.need("3.8")["best_share"] == R.need("4.6")["best_share"]


def test_a_number_edited_in_pipeline_json_only_does_not_load():
    for path, value, word in ((("raw", "strict", "share"), 0.7, "raw.strict.share"), (("raw", "strict", "trades"), 150, "raw.strict.trades"),
                              (("proof", "reshuffle"), 0.8, "proof.reshuffle"), (("proof", "random_alpha"), 0.1, "proof.random_alpha"),
                              (("box", "best_days_share"), 0.02, "box.best_days_share")):
        bad = P.check(_edited(path, value))
        assert len(bad) == 1 and word in bad[0], f"{path} = {value!r}: {bad}"
    with tempfile.TemporaryDirectory() as tmp:                  # the loader itself: a copy with one number changed raises, loudly
        P.FILE = Path(tmp) / "pipeline.json"
        P.FILE.write_text(json.dumps(_edited(("raw", "strict", "share"), 0.7)), encoding="utf-8")
        P._all.cache_clear()
        why = refused(lambda: P.need("raw", "low", "share"), "do not agree")
        assert "raw.strict.share" in why and "rules.json 2.1" in why
        refused(lambda: P.random_bar(1), "do not agree")        # nothing answers, not only the number that differs
        refused(lambda: P.floor("NQ", 1.0), "do not agree")
        P.FILE.write_text(json.dumps(_edited(("raw", "low", "share"), 0.4)), encoding="utf-8")     # a number the law does not carry: the pipeline's own
        P._all.cache_clear()
        assert P.need("raw", "low", "share") == 0.4
    teardown_function()
    assert P.need("raw", "strict", "share") == 0.6


def test_a_number_edited_in_rules_json_only_does_not_load():
    t, keep = {n: copy.deepcopy(R.template(n)) for n in R.NAMES}, R.T
    try:
        with tempfile.TemporaryDirectory() as tmp:
            t["rules"]["2.4"]["need"] = 250                     # the law asks 250 trades; pipeline.json still says 200
            for n in R.NAMES:
                (Path(tmp) / f"{n}.json").write_text(json.dumps(t[n]), encoding="utf-8")
            R.T = Path(tmp)
            R._all.cache_clear()
            P._all.cache_clear()
            assert R.need("2.4") == 250
            why = refused(lambda: P.need("raw"), "do not agree")
            assert "raw.strict.trades" in why and "rules.json 2.4" in why
    finally:
        R.T = keep
        R._all.cache_clear()
        P._all.cache_clear()
    assert R.need("2.4") == 200 and P.need("raw", "strict", "trades") == 200


# ================================================================ 4. the law's numbers the pipeline changed

def test_the_laws_changed_numbers():
    assert R.need("3.7") == 0.8 == R.need("4.7") == R.template("montecarlo")["test"]["need"]      # 80 % of the reshuffled runs, at the lock and on the test
    assert R.rule("3.7")["op"] == R.rule("4.7")["op"] == ">=" and R.meets("3.7", 0.8) and not R.meets("3.7", 0.7999) and R.meets("4.7", 0.8)
    assert R.need("4.6") == {"best_share": 0.01, "above": 0} == R.need("3.8")                     # the best 1 % of days, on the test and at the lock
    assert set(R.rule("3.8")) - {"note"} == set(R.rule("4.6")) - {"note"} == {"text", "number", "need"}      # 3.8 is written like 4.6: no `op` of its own
    assert [k for k in R.lines() if k.startswith("3.")] == [f"3.{i}" for i in range(1, 9)]
    for k in ("3.7", "4.7"):
        assert "80 %" in R.rule(k)["number"] and "90" not in R.rule(k)["number"]
    for k in ("3.8", "4.6"):
        assert "best 1 % of days" in R.rule(k)["text"] and R.rule(k)["number"] == "above $0"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)
