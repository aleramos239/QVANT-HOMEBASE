"""LOCK of `bp.py blocks` (blueprint/blocklist.py): the one list of what a chat can reuse without writing code.

(a) IT IS THE ENGINE'S AND THE TEMPLATES': every bar-based family of the registry with its own settings (the class's schema),
    its markets and bar sizes and the sessions it trades in; every filter block with its two sides; the limits; the
    standard exit table; the sessions; the bar sizes; the markets with their cost floors; the random tables, the Monte
    Carlo and the size steps -- read where the toolkit reads them, each with one line of plain words.
(b) WHAT VERSION 1 REFUSES IS WHAT IT REFUSES: every entry of the list is put to the toolkit here (the card's own lines, the
    runner's own check), and each is refused.
(c) THE COMMAND: a plain list for a person, the same as JSON (`blocks`), `--root` taken as the connector sends it.
Reads engine CODE and the templates only: no store, no tape, no run. A few seconds.

  pytest tests/test_blueprint_blocklist.py -q          python tests/test_blueprint_blocklist.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
from blueprint import blocklist as BL  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402
import run_menus as RM  # noqa: E402

CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")      # plan section 8
CARD = {"why": "The first minutes of the New York morning set a range, and a break of it traps the traders who leaned on it.",
        "loser": "traders who faded the opening range", "home": {"market": "NQ", "session": "nyam", "bar": "15"}, "neighbors": ["midday"],
        "not_here": "the Asian session", "main_setting": "or_min", "sides": "both", "sides_why": "a range can break either way", "loses_when": "a week without a clear direction"}
SETTINGS = {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
B = BL.blocks()["blocks"]


def failing(card=None, run=None) -> list:
    """The lines of the idea card that fail for a card changed like this (records.card_lines: the card command's own)."""
    rows, plan = REC.card_lines({"name": "bl_probe", "version": 1, "card": {**CARD, **(card or {})}, "run": {**SETTINGS, **(run or {})}})
    assert (plan is None) == any(x["passed"] is False for x in rows)
    return [x["line"] for x in rows if x["passed"] is False]


def test_the_plain_card_passes_so_a_refusal_below_is_the_change():
    assert failing() == []


def test_the_families_are_the_engines_bar_based_ones_with_their_own_settings():
    fam, blocks = RM.registry(), RUN._blocks()
    F = {f["name"]: f for f in B["families"]}
    assert list(F) == sorted(blocks.WRAPPED) and len(F) == 29
    assert [n for n, f in F.items() if not f["runs"]] == ["va_reclaim"] and "old build days" in F["va_reclaim"]["why_not"]
    for name, f in F.items():
        cls, lib = blocks.WRAPPED[name], fam.library(name)
        assert f["does"] and f["does"][0] != " " and not f["does"].startswith(("C ", "N", "B ", "blocks ")), (name, f["does"])     # the trigger, without the registry's label
        assert f["why"] == lib["rationale"] and f["markets"] == list(lib["roots"]) and f["bars"] == list(cls.SCREEN_TFS) and f["bracket"] is bool(blocks.BASES[name][2])
        assert f["sessions"] == [s for s in RM.DAY_PASSES if cls({**lib["variants"][0], "tf": cls.SCREEN_TFS[0], "sess": s}).sessions()] and f["sessions"]
        sc, d = cls.schema(), cls.defaults()
        for x in f["settings"]:
            assert x["name"] in sc and x["default"] == d[x["name"]] and x["values"] and x["name"] not in S.Template.DEFAULTS and x["name"] != "auth", (name, x)
        assert f["tried"] == lib["variants"] and (f["mirror"] is None or f["mirror"] in d)
        if f["runs"]:
            assert RUN.checked({"name": "bl_probe", "reason": CARD["why"], "family": name, "markets": [f["markets"][0]], "bar_sizes": [f["bars"][0]],
                                "sessions": [f["sessions"][0]], "params": {}, "exits": "standard"})["family"] == name, "what the list says runs is taken by the runner"
    assert [x["name"] for x in F["orb"]["settings"]] == ["or_min"] and F["orb"]["settings"][0]["values"] == "5 | 15 | 30" and F["orb"]["bracket"] is True
    assert F["donchian"]["settings"] == [{"name": "n", "default": 20, "values": "a whole number 2 .. 200"}]
    assert F["donchian"]["tried"] == [{"n": 10}, {"n": 20}, {"n": 40}, {"n": 60}]
    assert F["ib"]["sessions"] == ["nyam", "mid", "pm"] and F["ib"]["mirror"] == "mode" and F["gap"]["sessions"] == ["nyam"]
    assert {x["name"]: x["values"] for x in F["rsi2"]["settings"]} == {"th": "a number 1 .. 40", "trend_f": "true | false"}
    assert sorted(B["other_families"]) == sorted(set(fam.REGISTRY) - set(blocks.WRAPPED)) and len(B["other_families"]) == 33


def test_the_filters_the_limits_and_the_exit_table():
    blocks = RUN._blocks()
    assert [(f["block"], f["side"]) for f in B["filters"]] == [(b, s) for b, sides in blocks.FILTERS.items() for s in sides] and len(B["filters"]) == 87
    assert all(f["words"] == blocks.PLAIN[(f["block"], f["side"])] for f in B["filters"])
    assert all(f["runs"] and f["why_not"] is None for f in B["filters"])
    l2 = [f for f in B["filters"] if f["block"] in blocks.L2_BLOCKS]                                   # Level 2: NQ only, built but not yet locked or tested
    assert l2 and all(f["markets"] == ["NQ"] and not f["tested"] for f in l2) and all(f["markets"] == list(blocks.BLOCK_MARKETS.get(f["block"], ("NQ", "ES", "GC"))) and f["tested"] for f in B["filters"] if f not in l2)
    assert {f["block"] for f in l2} == {"book", "depth", "ahead", "wall", "stack"}
    assert {x["name"]: x["runs"] for x in B["limits"]} == {"max_tr": True, "dir": True, "exit_bars": False, "trail_atr": False} == {
        k: k not in REC.OWN_EXITS for k in ("max_tr", "dir", "exit_bars", "trail_atr")}
    import run_idea as RI
    assert set(RI.LIMIT_KEYS) == {x["name"] for x in B["limits"]}
    ex, m = B["exits"], R.template("exit_menu")
    assert (ex["cells"], ex["stops"], ex["targets_r"], ex["flat_et"], ex["flat_et_half_day"]) == (48, m["stops"], [0.0, 0.5, 0.75, 1.0, 2.0, 3.0], "15:58", "13:13")
    for root in ("NQ", "ES", "GC"):
        assert ex["by_market"][root] == [S.cell_id(c) for c in R.exit_menu(root)] and ex["by_market"][root][:32] == [S.cell_id(c) for c in S.menu(root)] and len(ex["by_market"][root]) == 48


def test_the_sessions_bars_markets_and_the_numbers_of_the_templates():
    assert [(s["name"], s["words"]) for s in B["sessions"]] == [(s, J.SESS_PLAIN[s]) for s in RM.DAY_PASSES]
    assert [s["name"] for s in B["sessions"] if not s["runs"]] == ["eve"] and B["bars"] == list(RM.registry().TFS) == ["1", "5", "15", "30"]
    c = R.template("costs")
    assert B["markets"] == [{"market": k, "floor": R.need("2.2", k), "point_value": c["contract"][k]["point_value"], "tick": c["contract"][k]["tick"]}
                            for k in ("NQ", "ES", "GC")]
    assert [m["floor"] for m in B["markets"]] == [70, 75, 140]
    mc, ctl, sz = R.template("montecarlo"), R.template("control"), R.template("sizes")
    assert B["montecarlo"] == {"runs": mc["runs"], "seed": mc["seed"], "draw": "whole days, with replacement, the same days for every variant",
                               "build": {"line": "2.8", "need": 0.75}, "test": {"line": "4.7", "need": 0.9},
                               "eval_card": {"percentiles": [50, 75, 90, 95, 99], "after_trades": [10, 20, 30, 40]}}
    assert B["random_tables"] == {"seeds": ctl["seeds"], "draws": ctl["draws"]} == {"seeds": 10, "draws": 4000}
    assert B["sizes"] == {"unit": "micros", "steps": sz["steps"], "stage_a": sz["stage_a"]} and B["ranges"]["build"] == {"start": "2021-09-22", "end": "2025-06-30"}
    assert B["ranges"]["test"]["start"] == "2025-07-01"
    assert [a["id"] for a in B["accounts"]] == [x["id"] for x in PO.app().list_rules()] and all(set(a) == {"id", "name", "confirmed"} for a in B["accounts"])


def test_what_version_1_refuses_is_what_the_toolkit_refuses():
    what = {x["what"]: x for x in B["refused"]}
    assert all(x["why"] for x in B["refused"]) and len(what) == len(B["refused"]) >= 9
    said = " | ".join(what)
    for word in ('home "all"', "evening session", "two filters", "trail_atr", "exit_bars", "Level 2", "va_reclaim", "more than one", "extended"):
        assert word in said, word
    # ... each put to the toolkit: the card's own lines, the runner's own check, the build's own refusal
    assert failing(card={"home": {"market": "all", "session": "nyam", "bar": "15"}}) == ["0.3"] == failing(card={"home": {"market": "NQ", "session": "all", "bar": "all"}})
    assert failing(card={"home": {"market": "NQ", "session": "eve", "bar": "15"}}) == ["0.3"] and failing(card={"neighbors": ["the evening session"]}) == ["0.4"]
    for own in ("trail_atr", "exit_bars"):
        assert failing(run={"limits": {own: 2}}) == ["0.2"]
    book = {"filters": [{"block": "book", "side": "agree"}]}
    assert failing(run=book) == [] and failing(run={"exits": "extended"}) == ["0.2"]           # Level 2 is allowed on a card whose places are all NQ ...
    assert failing(card={"neighbors": ["ES"]}, run=book) == ["0.2"] and failing(card={"not_here": "GC"}, run=book) == ["0.2"]       # ... and nowhere else
    assert failing(card={"neighbors": ["ES"]}, run={"filters": [{"block": "delta", "side": "with"}]}) == []             # a delta block runs on every market
    import inspect
    from blueprint import freeze as FZ
    assert "can be built but not locked or tested" in inspect.getsource(FZ.start) and "cannot be tested yet" in inspect.getsource(RUN.run_test)
    try:
        RUN.checked({"name": "bl_probe", "reason": CARD["why"], "family": "orb", "markets": ["NQ", "ES"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {},
                     "exits": "standard", "filters": [{"block": "wall", "side": "clear"}]})
        raise AssertionError("a Level 2 filter on ES was taken")
    except J.Refuse as e:
        assert "NQ only" in str(e)
    assert failing(run={"params": {"or_min": ["5", "15", "30"], "max_tr": [1, 2, 3]}}) == ["0.5"]
    assert failing(card={"main_setting": "mode", "not_here": "the afternoon"}, run={"family": "ib", "params": {"mode": ["break", "fade", "x"]}}) == ["0.5"]      # opposite ideas
    assert failing(run={"filters": [{"block": "news", "side": "no"}, {"block": "momentum", "side": "with"}, {"block": "volume", "side": "high"}]}) == ["0.2"]
    two = {"filters": [{"block": "news", "side": "no"}, {"block": "momentum", "side": "with"}]}
    assert failing(run=two) == [], "a card may NAME two filters (line 0.2) ..."
    assert "one filter" in what[next(k for k in what if "two filters" in k)]["why"]                 # ... a build runs one: records.start refuses the two together
    import inspect
    assert "version 1 reads a rule with one filter at most" in inspect.getsource(REC.start)
    try:
        RUN.checked({"name": "bl_probe", "reason": CARD["why"], "family": "va_reclaim", "markets": ["NQ"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {},
                     "exits": "standard"})
        raise AssertionError("va_reclaim was taken")
    except J.Refuse as e:
        assert "cannot run on the build range" in str(e)
    assert failing(run={"family": "straddle_t_0830", "params": {}}, card={"main_setting": ""}) == ["0.2", "0.5"], "a family that is not bar-based is no entry trigger"


def _run(argv: list) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(argv)
    return rc, out.getvalue()


def test_the_command():
    rc, out = _run(["blocks", "--root=/nowhere/at/all", "--json"])
    r = json.loads(out)
    assert rc == 0 and out.count("\n") == 1 and tuple(r)[:len(CONTRACT)] == CONTRACT
    assert (r["ok"], r["command"], r["name"], r["lines"], r["saved"]) == (True, "blocks", None, [], [])
    assert r["blocks"] == json.loads(json.dumps(B)) and r["counts"] == {"families": 28, "families_not_yet": 1, "filters": 87, "filters_not_yet": 0, "refused": len(B["refused"])}
    rc, text = _run(["blocks"])
    lines = text.splitlines()
    assert rc == 0 and text == r["text"] + "\n" and "bp.py card" in r["next"]
    for head in ("ENTRY TRIGGERS", "FILTERS", "LIMITS", "EXITS", "SESSIONS", "BAR SIZES", "MARKETS", "RANDOM TABLES", "MONTE CARLO", "SIZE STEPS", "ACCOUNTS",
                 "WHAT VERSION 1 REFUSES"):
        assert sum(ln.startswith(head) for ln in lines) == 1, head
    for f in B["families"]:
        assert sum(ln.split()[:1] == [f["name"]] for ln in lines) == 1, f["name"]            # one line a family
    assert sum(ln.strip().startswith(("volatility ", "momentum ", "volume ", "news ", "book ")) for ln in lines) == 12
    assert all(any(x["what"] in ln for ln in lines) for x in B["refused"]) and max(len(ln) for ln in lines) < 330, max(lines, key=len)
    assert sum(ln.strip().startswith("settings: ") for ln in lines) == len(B["families"])
    assert sum(ln.split()[:1] == [a["id"]] for a in B["accounts"] for ln in lines) == len(B["accounts"])
    assert "NOT YET" in next(ln for ln in lines if ln.split()[:1] == ["va_reclaim"]) and "$70" in text and "15:58" in text
    assert not Path("/nowhere").exists()


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
    print("\n" + BL.blocks()["text"])
    sys.exit(rc)
