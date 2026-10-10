"""LOCK of the pipeline card (blueprint/pipe_card.py) -- pipeline plan A, task 2: stage 0 of the strategy pipeline.

1. A WHOLE CARD passes lines P0.1-P0.4 and becomes its heat maps: one toolkit idea a way and a bar size (`<name>_<a|b|c><1|5>`),
   each a spec the toolkit's own card check (records.card_lines) takes -- home = the card's market, session and that bar, its
   neighbors = the other markets, no filter. A family without 1-minute bars gives its 5-minute heat map only.
2. NOTHING IS WRITTEN and no tape is read: check() answers from code and templates; the card it was handed stays as it was.
3. NO CARD AT ALL is refused outright (judge.Refuse): no object, a field a card does not have, a name the heat maps cannot
   carry, a source that is not one of the four.
4. EVERY LINE REFUSES WHAT IT HOLDS, as a failed row and no heat maps: P0.1 the reason and who loses · P0.2 the ways (count,
   family, main setting, 3 values, market, session, bars -- and whatever
   the toolkit refuses, in the toolkit's words) ·
   P0.3 the indicators (count, block and side, a why each, no block twice, a block only where it runs) · P0.4 the sides.
5. THE LIMITS ARE THE RULES FILE'S (templates/pipeline.json `card`), not the code's.
6. THE SIGNATURE says "the same idea": market, session, sides and the ways -- not the name, the reason, the source or the
   indicators, not the order of the ways, not whether a number was typed as text.
Reads code and templates only: no store, no tape, no run. A few seconds (the first card loads the engine's registry).

  pytest tests/test_pipe_card.py -q          python tests/test_pipe_card.py     the same, one line per test
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
import run_menus as RM  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
from blueprint import pipe_card as PC  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

FILE = P.FILE
CARD = {"name": "fvg_open", "why": "Late buyers chase the first gap after the open.", "loser": "Traders who fade the first move.",      # the plan's own example
        "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
        "ways": [{"family": "fvg", "main_setting": "min_gap", "values": ["0.1", "0.25", "0.5"], "fixed": {"mode": "touch"}, "limits": {}}],
        "indicators": [{"block": "trend", "side": "with", "why": "A gap with the trend has more room."}]}
WAY = CARD["ways"][0]
MID = {**WAY, "fixed": {"mode": "mid"}}                                                     # the same trigger entered at the middle of the gap
ORB = {"family": "orb", "main_setting": "or_min", "values": [5, 15, 30], "fixed": {}, "limits": {}}
IB_N = {"family": "ib_n", "main_setting": "ib_min", "values": ["5", "15", "30"], "fixed": {}, "limits": {}}      # ib_n has no 1-minute bars
LINES = ["P0.1", "P0.2", "P0.3", "P0.4"]
_KEEP: dict = {}


def setup_function(_=None):
    TI.setup_function()                             # the idea folder and the Lab drafts of the environment are temp folders


def teardown_function(_=None):
    TI.teardown_function()
    P.FILE = FILE
    P._all.cache_clear()
    if "families" in _KEEP:
        PC._families = _KEEP.pop("families")


def card(**more) -> dict:
    return {**copy.deepcopy(CARD), **more}


def ways(*w) -> dict:
    return card(ways=[copy.deepcopy(x) for x in w])


def way(**more) -> dict:
    return ways({**WAY, **more})


def fails(c: dict, line: str, *words: str) -> str:
    """The card fails exactly this line, with these words, and has no heat maps -> the row's text."""
    rows, subs = PC.check(c)
    assert [r["line"] for r in rows] == LINES and subs is None
    assert [r["line"] for r in rows if r["passed"] is not True] == [line], [r["text"] for r in rows]
    row = rows[LINES.index(line)]
    assert row["passed"] is False and row["text"].startswith(f"{line} FAIL "), row
    for w in words:
        assert w in row["text"], f"{w!r} is not in: {row['text']}"
    return row["text"]


def passes(c: dict) -> list:
    rows, subs = PC.check(c)
    assert [r["passed"] for r in rows] == [True] * 4 and subs, [r["text"] for r in rows]
    return subs


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except J.Refuse as e:
        assert word in str(e), f"refused, but not for {word!r}: {e}"
        return str(e)
    raise AssertionError(f"not refused ({word})")


def family(name: str, **more):
    """The block list says this of one family while the test runs (a family the engine does not have: one market, no small bars)."""
    real = _KEEP.setdefault("families", PC._families)
    PC._families = lambda: {**real(), name: {**real()[name], **more}}


# ================================================================ 1. a whole card and its heat maps

def test_a_whole_card_passes_its_four_lines_and_gives_two_heat_maps_a_way():
    rows, subs = PC.check(card())
    assert [r["line"] for r in rows] == LINES and all(set(r) >= {"line", "passed", "number", "need", "text"} for r in rows)
    assert [r["passed"] for r in rows] == [True] * 4 and all(r["text"].startswith(f"{r['line']} PASS ") for r in rows)
    assert rows[0]["need"] == {"sentences": 1, "words": 8} and rows[0]["number"] == 15
    assert rows[1]["number"] == 1 and rows[1]["need"] == {"ways": [1, 3], "values": 3, "bars": ["1", "5"], "markets": ["NQ", "ES", "GC"],
                                                          "sessions": ["asia", "london", "pre", "nyam", "mid", "pm", "eve"]}
    assert rows[2]["number"] == 1 and rows[2]["need"] == [0, 5] and "trend with" in rows[2]["text"]
    assert "fvg" in rows[1]["text"] and "min_gap" in rows[1]["text"] and "both sides" in rows[3]["text"]
    assert [(s["name"], s["way"], s["bar"]) for s in subs] == [("fvg_open_a1", 0, "1"), ("fvg_open_a5", 0, "5")]
    assert all(set(s) == {"name", "way", "bar", "spec"} for s in subs)
    assert subs[0]["spec"] == {"name": "fvg_open_a1", "version": 1,
                               "card": {"why": CARD["why"], "loser": CARD["loser"], "home": {"market": "NQ", "session": "nyam", "bar": "1"},
                                        "neighbors": ["ES", "GC"], "main_setting": "min_gap", "sides": "both",
                                        "sides_why": "both sides: the rule is symmetric", "loses_when": "not named on a pipeline card"},
                               "run": {"family": "fvg", "params": {"min_gap": [0.1, 0.25, 0.5]}, "fixed": {"mode": "touch"}, "filters": [],
                                       "exits": "standard", "limits": {}}}
    assert subs[1]["spec"]["card"]["home"] == {"market": "NQ", "session": "nyam", "bar": "5"} and subs[1]["spec"]["name"] == "fvg_open_a5"


def test_a_noise_band_card_passes_stage_0_with_one_side_a_held_anchor_and_a_cap():
    nb = {"family": "noise_band", "main_setting": "k", "values": ["0.2", "0.3", "0.4"], "fixed": {}, "limits": {}}
    c = card(name="noise_mid", session="mid", sides="long", sides_why="The index drifts up, and the vault break is long only.", ways=[nb],
             indicators=[{"block": "htf60", "side": "with", "why": "A break with the hourly trend has more room."}])
    subs = passes(c)
    assert [(x["name"], x["bar"]) for x in subs] == [("noise_mid_a1", "1"), ("noise_mid_a5", "5")] and subs[0]["spec"]["run"]["params"] == {"k": [0.2, 0.3, 0.4]}
    held = {**nb, "fixed": {"anchor": "globex"}, "limits": {"max_tr": 2}}                       # the anchor is ONE value an idea; max_tr is a limit
    passes({**c, "ways": [held]})
    passes({**c, "sides": "both", "sides_why": "The rule is symmetric.", "ways": [nb]})
    fails({**c, "ways": [{**nb, "main_setting": "anchor", "values": ["rth", "globex", "rth"]}]}, "P0.2")
    fails({**c, "ways": [{**nb, "fixed": {"anchor": "asia"}}]}, "P0.2")


def test_an_ifvg_card_passes_stage_0_with_a_held_age_one_side_and_a_cap():
    iv = {"family": "ifvg", "main_setting": "min_gap", "values": ["0.1", "0.25", "0.5"], "fixed": {}, "limits": {}}
    c = card(name="ifvg_open", why="Traders caught inside a gap that fails must get out.", loser="Traders who bought inside the gap.", ways=[iv],
             indicators=[{"block": "htf60", "side": "with", "why": "A failed gap with the hourly trend has more room."}])
    subs = passes(c)
    assert [(x["name"], x["bar"]) for x in subs] == [("ifvg_open_a1", "1"), ("ifvg_open_a5", "5")]
    assert subs[0]["spec"]["run"] == {"family": "ifvg", "params": {"min_gap": [0.1, 0.25, 0.5]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
    held = {**iv, "fixed": {"age": 20}, "limits": {"max_tr": 2}}                                 # the age is ONE value an idea; max_tr is a limit
    run = passes({**c, "ways": [held]})[0]["spec"]["run"]
    assert run["fixed"] == {"age": 20} and run["limits"] == {"max_tr": 2}
    passes({**c, "sides": "short", "sides_why": "The index falls faster than it rises, so the failed up gap is the cleaner one.", "ways": [iv]})
    passes({**c, "ways": [{**iv, "main_setting": "age", "values": [10, 30, 60]}]})                # the age can be the heat map's setting too
    fails({**c, "ways": [{**iv, "fixed": {"age": 3}}]}, "P0.2")                                   # under the family's own limit (5 .. 240)
    fails({**c, "ways": [{**iv, "fixed": {"mode": "go"}}]}, "P0.2")                               # fvg's setting, not this family's


def test_an_sfp_card_passes_stage_0_with_the_swing_size_as_its_setting():
    sf = {"family": "sfp", "main_setting": "swing", "values": ["15", "30", "60"], "fixed": {}, "limits": {}}
    c = card(name="sfp_open", why="Stops behind a small swing are taken and the move fails.", loser="Traders who chase the break of the swing.", ways=[sf],
             indicators=[])
    subs = passes(c)
    assert [(x["name"], x["bar"]) for x in subs] == [("sfp_open_a1", "1"), ("sfp_open_a5", "5")]
    assert subs[0]["spec"]["run"]["params"] == {"swing": ["15", "30", "60"]} and subs[0]["spec"]["card"]["main_setting"] == "swing"      # the engine names its choices in text
    passes({**c, "ways": [{**sf, "values": [15, 30, 60]}]})                                       # (a number typed as a number is the same choice)
    passes({**c, "ways": [{**sf, "limits": {"max_tr": 1}}]})
    passes({**c, "session": "london", "sides": "long", "sides_why": "London sweeps the Asian lows before the day's rise.", "ways": [sf]})
    fails({**c, "ways": [{**sf, "values": ["15", "30", "45"]}]}, "P0.2")                          # 45 is not a swing size
    fails({**c, "ways": [{**sf, "values": ["15", "30", "30"]}]}, "P0.2")


def test_a_pullback_card_passes_stage_0_with_the_level_as_its_setting_and_a_held_swing_size():
    pb = {"family": "pullback", "main_setting": "level", "values": ["0.5", "0.62", "0.79"], "fixed": {}, "limits": {}}
    c = card(name="pullback_open", why="A higher swing high shows buyers in control, and the first pullback is bought.",
             loser="Traders who chased the move late and are stopped out on the pullback.", ways=[pb], indicators=[])
    subs = passes(c)
    assert [(x["name"], x["bar"]) for x in subs] == [("pullback_open_a1", "1"), ("pullback_open_a5", "5")]
    assert subs[0]["spec"]["run"] == {"family": "pullback", "params": {"level": [0.5, 0.62, 0.79]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
    held = {**pb, "fixed": {"swing": "30"}, "limits": {"max_tr": 2}}                              # the swing size is ONE value an idea; max_tr is a limit
    run = passes({**c, "ways": [held]})[0]["spec"]["run"]
    assert run["fixed"] == {"swing": "30"} and run["limits"] == {"max_tr": 2}
    passes({**c, "ways": [{**pb, "main_setting": "swing", "values": ["15", "30", "60"], "fixed": {"level": 0.79}}]})      # the swing size can be the heat map's setting too
    passes({**c, "session": "london", "sides": "long", "sides_why": "The index drifts up, so only the up legs are bought.", "ways": [pb]})
    fails({**c, "ways": [{**pb, "values": ["0.5", "0.62", "0.95"]}]}, "P0.2")                     # beyond the family's own limit (0.25 .. 0.9)
    fails({**c, "ways": [{**pb, "fixed": {"swing": "45"}}]}, "P0.2")                              # 45 is not a swing size
    fails({**c, "ways": [{**pb, "fixed": {"swing": "leg"}}]}, "P0.2")                             # the owner's range definitions are filter blocks, not this family's


def test_every_heat_map_is_a_card_the_toolkit_takes():
    for s in passes(ways(WAY, MID, ORB)):
        rows, plan = REC.card_lines(REC._spec(REC._name(s["name"]), copy.deepcopy(s["spec"])))
        assert [r["passed"] for r in rows] == [True] * 7 and plan["home"]["table"] == f"NQ-tf{s['bar']}-nyam", [r["text"] for r in rows]
        assert [p["table"] for p in plan["neighbors"]] == [f"ES-tf{s['bar']}-nyam", f"GC-tf{s['bar']}-nyam"]
        assert plan["filters"] == [] and plan["variants"] == 3 * 48 and plan["not_here"] is None and plan["exits"] == "standard"
        assert [(x["market"], x["bar"]) for x in plan["stores"]] == [(m, s["bar"]) for m in ("NQ", "ES", "GC")]


def test_three_ways_give_six_heat_maps_named_by_way_and_bar():
    subs = passes(ways(WAY, MID, ORB))
    assert [s["name"] for s in subs] == [f"fvg_open_{x}" for x in ("a1", "a5", "b1", "b5", "c1", "c5")]
    assert [s["way"] for s in subs] == [0, 0, 1, 1, 2, 2] and [s["bar"] for s in subs] == ["1", "5"] * 3
    assert subs[2]["spec"]["run"]["fixed"] == {"mode": "mid"} and subs[4]["spec"]["run"]["family"] == "orb"
    assert subs[4]["spec"]["run"]["params"] == {"or_min": ["5", "15", "30"]} and subs[4]["spec"]["card"]["main_setting"] == "or_min"    # the engine names its choices in text


def test_a_family_without_one_minute_bars_gives_its_five_minute_heat_map_only():
    assert "1" not in RUN._blocks().WRAPPED["ib_n"].SCREEN_TFS
    subs = passes(ways(IB_N, WAY))
    assert [(s["name"], s["bar"]) for s in subs] == [("fvg_open_a5", "5"), ("fvg_open_b1", "1"), ("fvg_open_b5", "5")]


def test_the_neighbors_are_the_other_markets_and_the_other_bar_size_when_none_is_left():
    assert [s["spec"]["card"]["neighbors"] for s in passes(card(market="GC"))] == [["NQ", "ES"]] * 2
    assert [s["spec"]["card"]["neighbors"] for s in passes(card(market="ES"))] == [["NQ", "GC"]] * 2
    family("fvg", markets=["NQ", "ES"])
    assert [s["spec"]["card"]["neighbors"] for s in passes(card())] == [["ES"]] * 2
    family("fvg", markets=["NQ"])                                                           # no other market: the toolkit asks for one neighbor at least
    assert [s["spec"]["card"]["neighbors"] for s in passes(card())] == [["5-minute bars"], ["1-minute bars"]]
    family("fvg", markets=["NQ"], bars=["5", "15"])                                         # one market and one of the two bars: no neighbor is left
    fails(card(), "P0.2", "way a on 5-minute bars", "0.4 FAIL", "where else it should work")


def test_the_neighbors_of_a_heat_map_with_an_indicator_are_the_markets_the_indicator_runs_on_too():
    eng = RUN._blocks()
    assert PC.neighbors("NQ", "fvg", "5") == PC.neighbors("NQ", "fvg", "5", "trend") == ["ES", "GC"] == passes(card())[1]["spec"]["card"]["neighbors"]
    assert PC.neighbors("ES", "fvg", "1", "trend") == ["NQ", "GC"]                              # a block for every market: as without it
    assert "book" in eng.L2_BLOCKS and PC.neighbors("NQ", "fvg", "5", "book") == ["1-minute bars"]     # Level 2 is NQ alone: the other bar size
    assert PC.neighbors("NQ", "fvg", "1", "book") == ["5-minute bars"]
    assert eng.BLOCK_MARKETS["smt"] == ("NQ", "ES") and PC.neighbors("NQ", "fvg", "5", "smt") == ["ES"] and PC.neighbors("ES", "fvg", "5", "smt") == ["NQ"]
    nq = next(b for b, m in eng.BLOCK_MARKETS.items() if m == ("NQ",))                           # a block of NQ alone that is not Level 2
    assert PC.neighbors("NQ", "fvg", "5", nq) == ["1-minute bars"]
    for block, nbs in (("book", ["1-minute bars"]), ("smt", ["ES"])):                            # ... and the toolkit takes the card so written
        spec = copy.deepcopy(passes(card())[1]["spec"])
        spec["card"]["neighbors"], spec["run"]["filters"] = PC.neighbors("NQ", "fvg", "5", block), [{"block": block, "side": next(iter(eng.FILTERS[block]))}]
        assert spec["card"]["neighbors"] == nbs and REC.card_lines(spec)[1] is not None, REC.card_lines(spec)[0][1]["text"]
    spec["card"]["neighbors"] = ["ES", "GC"]                                                     # (the heat map's own neighbors: refused with smt on)
    assert REC.card_lines(spec)[1] is None
    family("fvg", bars=["5"])
    assert PC.neighbors("NQ", "fvg", "5", "book") == []                                          # no other bar size either: nothing to name


def test_a_one_sided_card_says_why_and_its_heat_maps_carry_it():
    subs = passes(card(sides="long", sides_why="Only buyers chase a gap up."))
    assert all((s["spec"]["card"]["sides"], s["spec"]["card"]["sides_why"]) == ("long", "Only buyers chase a gap up.") for s in subs)
    assert passes(card(sides_why="A gap is chased up and down."))[0]["spec"]["card"]["sides_why"] == "A gap is chased up and down."


def test_the_longest_name_still_names_its_heat_maps():
    name = "a" * 34
    subs = passes(ways(WAY, MID, ORB) | {"name": name})
    assert all(len(s["name"]) == 37 and REC._name(s["name"]) == s["name"] for s in subs) and len(subs) == 6
    assert len(f"{subs[0]['name']}_r5") == 40                                               # a later round's store still fits the app's 40 characters


# ================================================================ 2. nothing is written, nothing is read

def test_check_writes_nothing_reads_no_tape_and_leaves_the_card_as_it_was():
    with tempfile.TemporaryDirectory(prefix="pipe_card_") as d:
        keep = os.environ.get("HOMEBASE_PIPELINE_ROOT")
        os.environ["HOMEBASE_IDEAS_ROOT"] = os.environ["HOMEBASE_PIPELINE_ROOT"] = str(Path(d) / "root")       # (the idea folder is put back by the teardown)
        try:
            c = ways(WAY, ORB)
            was = json.dumps(c, sort_keys=True)
            with TI.no_engine():
                passes(c)
                fails(way(values=[1, 2]), "P0.2")
                PC.signature(c)
            assert json.dumps(c, sort_keys=True) == was and c["ways"][1]["values"] == [5, 15, 30]
            assert list(Path(d).iterdir()) == []
        finally:
            os.environ.pop("HOMEBASE_PIPELINE_ROOT", None) if keep is None else os.environ.__setitem__("HOMEBASE_PIPELINE_ROOT", keep)


# ================================================================ 3. no card at all: refused outright

def test_what_is_no_card_is_refused_outright():
    for bad in (None, "fvg_open", [CARD], 7):
        refused(lambda: PC.check(bad), "a JSON object")
    assert "['days', 'home']" in refused(lambda: PC.check(card(home={"bar": "5"}, days=["2026-01-05"])), "unknown fields")
    c = card()
    del c["name"]
    refused(lambda: PC.check(c), "name")
    for bad in ("Fvg_open", "f", "9lives", "fvg open", "a" * 35, 7, None):
        refused(lambda: PC.check(card(name=bad)), "starting with a letter")
    refused(lambda: PC.check(card(name="fvg_")), "'__'")                                  # fvg__a1: '__' marks a filter in a store's name
    refused(lambda: PC.check(card(name="c1_gap")), "c1")                                  # the control pools' prefix
    refused(lambda: PC.check(card(name="draft_gap")), "reserved")                         # the app's own rule for a name
    passes(card(name="fvg"))                                                              # fvg_a1 is no family's name
    passes(card(name="gap_r2"))                                                           # gap_r2_a1 does not end like a later round
    for bad in ("me", "", None, "Owner"):
        refused(lambda: PC.check(card(source=bad)), "owner, video, claude, wiki, paper, book, course")
    for good in ("owner", "video", "claude", "wiki", "paper", "book", "course"):
        passes(card(source=good))
    passes(card(source="paper", ref="Zarattini & Aziz 2023 (SSRN 4416622)"))               # ref: which one, optional
    for bad in ("", "   ", 7, "x" * 301):
        refused(lambda: PC.check(card(ref=bad)), "ref: one line")
    assert PC.signature(card(ref="a book")) == PC.signature(card())                        # where it came from is no part of the idea


# ================================================================ 4. each line refuses what it holds

def test_line_p0_1_the_reason_in_one_sentence_and_who_loses():
    fails(card(why=""), "P0.1", "why it should make money")
    fails(card(why=None), "P0.1", "why it should make money")
    fails(card(loser="  "), "P0.1", "who is on the losing side")
    fails(card(why="Late buyers chase the first gap. They pay up after the open."), "P0.1", "2 sentences (need 1)")
    fails(card(loser="Traders who fade. Also the late sellers."), "P0.1", "2 sentences (need 1)")
    r = fails(card(why="Late buyers chase gaps.", loser="The faders."), "P0.1", "6 words", "need 8")
    assert PC.check(card(why="Late buyers chase gaps.", loser="The faders."))[0][0]["number"] == 6 and "P0.1 FAIL" in r
    passes(card(why="Late buyers chase the gap.", loser="Traders who fade."))            # 8 words together: "or more"
    c = card()
    del c["loser"]
    fails(c, "P0.1", "who is on the losing side")


def test_line_p0_2_the_count_of_the_ways():
    fails(card(ways=[]), "P0.2", "0 ways", "1 to 3")
    fails(ways(WAY, MID, ORB, IB_N), "P0.2", "4 ways", "1 to 3")
    fails(card(ways={"a": WAY}), "P0.2", "0 ways")
    c = card()
    del c["ways"]
    fails(c, "P0.2", "0 ways")
    fails(ways(WAY, ORB, WAY), "P0.2", "way c is the same as way a")
    fails(ways(WAY, {**WAY, "values": [0.5, "0.10", 0.25]}), "P0.2", "way b is the same as way a")    # the same values, typed another way


def test_line_p0_2_a_way_names_a_family_its_main_setting_and_three_values():
    fails(card(ways=["fvg"]), "P0.2", "way a", "family, main_setting, values")
    fails(way(bars=["15"]), "P0.2", "way a", "['bars']")
    fails(way(family="fair_value"), "P0.2", "way a", "'fair_value'", "no entry trigger")
    fails(way(family="bimb_follow"), "P0.2", "way a", "no entry trigger")                 # a family of the registry that is not bar-based
    fails(way(main_setting="or_min"), "P0.2", "way a", "or_min", "no setting of fvg", "min_gap, mode, new_gap")
    fails(way(main_setting="tf"), "P0.2", "no setting of fvg")                            # the bar size is the pipeline's, not a setting
    fails(way(main_setting=None), "P0.2", "no setting of fvg")
    fails(way(values=["0.1", "0.25"]), "P0.2", "way a", "2 values", "need 3")
    fails(way(values=["0.1", "0.25", "0.5", "1"]), "P0.2", "4 values", "need 3")
    fails(way(values=["0.1", "0.25", "0.25"]), "P0.2", "3 values", "each once")
    fails(way(values=["0.1", 0.1, "0.5"]), "P0.2", "each once")                          # one number typed twice
    fails(way(values="0.1"), "P0.2", "0 values")
    fails(way(values=[0.1, [0.25], 0.5]), "P0.2", "text or a number")
    fails(way(fixed=["mode"]), "P0.2", "fixed and limits are objects")
    fails(way(limits="none"), "P0.2", "fixed and limits are objects")
    w = {k: v for k, v in WAY.items() if k not in ("fixed", "limits")}                    # fixed and limits may be left out
    assert passes(ways(w))[0]["spec"]["run"] == {"family": "fvg", "params": {"min_gap": [0.1, 0.25, 0.5]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}


def test_line_p0_2_the_family_runs_on_the_market_the_session_and_one_of_the_bars():
    fails(card(market="CL"), "P0.2", "market 'CL'", "NQ, ES, GC")
    fails(card(market="nq"), "P0.2", "market 'nq'")                                       # as the rules file writes it: the signature reads it
    fails(card(market=None), "P0.2", "market None")
    fails(card(session="lunch"), "P0.2", "session 'lunch'", "nyam")
    fails(card(session="morning"), "P0.2", "session 'morning'")
    assert "eve" in RM.DAY_PASSES and "eve" in P.need("card", "sessions")                  # the evening session is the pipeline's too (the owner, 2026-10-09)
    assert "evening (18:00-23:59 ET" in PC.check(card(session="eve"))[0][1]["text"] and PC.check(card(session="eve"))[1]
    for s in P.need("card", "sessions"):                                                    # each of the seven is read as a session: no row says it is not one
        assert s in RM.DAY_PASSES and not PC.check(card(session=s))[0][1]["text"].startswith("P0.2 FAIL session")
    fails(ways({"family": "lon_break", "main_setting": "min_rng_atr", "values": [0, 1, 2]}) | {"session": "mid"}, "P0.2", "way a", "lon_break", "midday", "nyam")
    family("fvg", markets=["ES", "GC"])
    fails(card(), "P0.2", "way a", "fvg does not run on NQ", "ES, GC")
    family("fvg", bars=["15", "30"])
    fails(card(), "P0.2", "way a", "1- or 5-minute bars", "15, 30")
    family("fvg", runs=False, why_not="its table is not built")
    fails(card(), "P0.2", "way a", "cannot run on the build days yet", "its table is not built")


def test_line_p0_2_carries_what_the_toolkit_refuses_in_the_toolkits_words():
    t = fails(way(fixed={"mode": "sideways"}), "P0.2", "way a on 1-minute bars", "0.2 FAIL the rule cannot be run as it is written")
    assert "sideways" in t or "mode" in t
    fails(way(values=["0.1", "0.25", "wide"]), "P0.2", "way a on 1-minute bars", "0.2 FAIL", "min_gap")
    fails(way(limits={"trail_atr": 2}), "P0.2", "0.2 FAIL limits.trail_atr is an exit of its own")
    fails(way(limits={"dir": "short"}) | {"sides": "long", "sides_why": "Only buyers chase."}, "P0.2", "0.6 FAIL the card says long, settings.limits.dir says short")
    fails(ways({"family": "gap", "main_setting": "mode", "values": ["fill", "go", "both"]}), "P0.2", "0.5 FAIL", "opposite ideas")
    fails(ways(WAY, {**ORB, "values": ["5", "15", "45"]}), "P0.2", "way b on 1-minute bars", "0.2 FAIL")


def test_line_p0_3_the_indicators():
    one = CARD["indicators"][0]
    six = [{"block": b, "side": "with", "why": "It has more room."} for b in ("trend", "vwap", "ema20", "ema50", "macd", "htf15")]
    assert PC.check(card(indicators=six[:5]))[0][2]["number"] == 5 and passes(card(indicators=six[:5]))
    fails(card(indicators=six), "P0.3", "6 indicators", "at most 5")
    fails(card(indicators="trend with"), "P0.3", "a list")
    fails(card(indicators=["trend_with"]), "P0.3", "indicator 1", "block, side, why")
    fails(card(indicators=[{**one, "bar": "5"}]), "P0.3", "indicator 1", "['bar']")
    fails(card(indicators=[one, {**one, "block": "trendy"}]), "P0.3", "indicator 2", "'trendy'", "no filter block")
    fails(card(indicators=[{**one, "side": "up"}]), "P0.3", "indicator 1", "trend has no side 'up'", "with | against")
    fails(card(indicators=[{"block": "trend", "side": "with"}]), "P0.3", "indicator 1", "trend with", "does not say why")
    fails(card(indicators=[{**one, "why": " "}]), "P0.3", "does not say why")
    fails(card(indicators=[one, {**one, "side": "against"}]), "P0.3", "indicator 2", "trend is named twice")
    book = {"block": "book", "side": "agree", "why": "The resting orders lean the same way."}
    assert "book" in RUN._blocks().L2_BLOCKS and passes(card(indicators=[one, book]))        # Level 2 on NQ
    fails(card(market="ES", indicators=[book]), "P0.3", "indicator 1", "Level 2", "NQ only", "ES")
    fails(card(market="GC", indicators=[one, book]), "P0.3", "indicator 2", "Level 2")
    smt = {"block": "smt", "side": "agree", "why": "Both indexes make the same low."}        # a block that compares NQ with ES
    assert passes(card(market="ES", indicators=[smt]))
    fails(card(market="GC", indicators=[smt]), "P0.3", "smt runs on NQ and ES only", "GC")
    assert PC.check(card(indicators=[]))[0][2]["number"] == 0 and "no indicator" in PC.check(card(indicators=[]))[0][2]["text"]
    c = card()
    del c["indicators"]                                                                       # none named = none tried
    assert len(passes(c)) == 2


def test_an_indicator_is_no_part_of_a_heat_map():
    a, b = passes(card()), passes(card(indicators=[]))
    assert a == b and all(s["spec"]["run"]["filters"] == [] for s in a)


def test_line_p0_4_the_sides():
    fails(card(sides="up"), "P0.4", "sides 'up'", "both, long or short")
    c = card()
    del c["sides"]
    fails(c, "P0.4", "both, long or short")
    fails(card(sides="short"), "P0.4", "short only", "does not say why")
    fails(card(sides="long", sides_why="  "), "P0.4", "does not say why")
    c = card()
    del c["sides_why"]                                                                        # both sides need no why
    passes(c)


def test_a_card_with_more_than_one_line_missing_says_each():
    rows, subs = PC.check(card(why="", sides="up", indicators=[{"block": "x"}], ways=[]))
    assert subs is None and [r["passed"] for r in rows] == [False] * 4 and [r["line"] for r in rows] == LINES
    rows, subs = PC.check(card(why="", ways=[{**WAY, "fixed": {"mode": "sideways"}}]))        # the toolkit is asked only when the card's own lines hold
    assert subs is None and [r["passed"] for r in rows] == [False, True, True, True]


# ================================================================ 5. the limits are the rules file's

def test_the_limits_are_read_from_the_rules_file():
    with tempfile.TemporaryDirectory(prefix="pipe_card_") as d:
        p = json.loads(FILE.read_text(encoding="utf-8"))
        p["card"] = {"ways": [2, 2], "values": 4, "indicators": [1, 1], "bars": ["5", "15"], "markets": ["ES", "GC"], "sessions": ["nyam", "eve"]}
        P.FILE = Path(d) / "pipeline.json"
        P.FILE.write_text(json.dumps(p), encoding="utf-8")
        P._all.cache_clear()
        four = {**WAY, "values": [0.1, 0.25, 0.5, 1]}
        good = card(market="ES", ways=[four, {**four, "fixed": {"mode": "mid"}}])
        subs = passes(good)
        assert [s["name"] for s in subs] == [f"fvg_open_{x}" for x in ("a5", "a15", "b5", "b15")]
        assert [s["spec"]["card"]["neighbors"] for s in subs] == [["GC"]] * 4 and subs[1]["spec"]["card"]["home"]["bar"] == "15"
        fails({**good, "ways": [four]}, "P0.2", "1 ways", "need 2")
        fails({**good, "ways": [WAY, MID]}, "P0.2", "3 values", "need 4")
        fails({**good, "market": "NQ"}, "P0.2", "market 'NQ'", "ES, GC")
        fails({**good, "session": "mid"}, "P0.2", "session 'mid'", "the midday session is not in this version", "one of nyam, eve")       # the file's sessions, not the code's
        fails({**good, "indicators": []}, "P0.3", "0 indicators", "need 1")
        fails({**good, "indicators": CARD["indicators"] * 2}, "P0.3", "2 indicators")


# ================================================================ 6. the signature: "the same idea"

def test_the_signature_is_the_idea_not_its_name_its_reason_or_its_indicators():
    s = PC.signature(card())
    assert isinstance(s, str) and len(s) == 40 and int(s, 16) >= 0 and s == PC.signature(card())
    assert s == PC.signature(card(name="another", why="Something else entirely is said here.", loser="Nobody.", source="video", indicators=[], sides_why="x"))
    assert s != PC.signature(way(values=["0.1", "0.25", "1"]))                               # another value list
    assert s == PC.signature(way(values=[0.5, 0.1, 0.25])) == PC.signature(way(values=["0.50", 0.25, "0.10"]))    # the order, and text or number
    assert s != PC.signature(card(market="ES")) and s != PC.signature(card(session="mid")) and s != PC.signature(card(sides="long", sides_why="x"))
    assert s != PC.signature(way(fixed={"mode": "mid"})) and s != PC.signature(way(limits={"max_tr": 1}))
    assert s != PC.signature(way(main_setting="mode")) and s != PC.signature(way(family="gap"))
    assert PC.signature(way(limits={"max_tr": 1})) == PC.signature(way(limits={"max_tr": "1"})) != PC.signature(way(limits={"max_tr": 2}))
    w = {k: v for k, v in WAY.items() if k != "limits"}
    assert s == PC.signature(ways(w))                                                         # limits left out = no limits
    assert PC.signature(ways(WAY, ORB)) == PC.signature(ways(ORB, WAY)) != s                  # the same ways in another order are the same card
    assert PC.signature(ways(ORB)) == PC.signature(ways({**ORB, "values": ["30", "5", "15"]}))
    two = {**WAY, "fixed": {"mode": "touch", "new_gap": "stop"}}
    assert PC.signature(ways(two)) == PC.signature(ways({**WAY, "fixed": {"new_gap": "stop", "mode": "touch"}})) != s


def test_the_family_of_a_card_is_its_first_ways():
    assert PC.family_of(card()) == "fvg" and PC.family_of(ways(ORB, WAY)) == "orb"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)
