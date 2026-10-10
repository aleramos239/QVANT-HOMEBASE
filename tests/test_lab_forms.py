"""The Lab's fill-in form: answers in, a draft file out. Pure text (no draft runs in the chart service), plus the
behaviour gate: each generated strategy takes exactly the trade the contracts describe when the tester's own
run_session replays a small synthetic tape through it."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import itertools
import json
import keyword
import sys
from array import array

import pytest

from homebase import draftstore, strategies
from homebase.backtest import drafthost, sandbox
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import Tape, et_ns
from homebase.charts import lab_forms, lab_templates
from homebase.labrun import door

RULES = ("open_straddle", "opening_range", "bar_breakout", "at_time")
SIDES = {"open_straddle": ("both", "long", "short"), "opening_range": ("both", "long", "short"),
         "bar_breakout": ("both", "long", "short"), "at_time": ("long", "short")}
STOPS = {"open_straddle": ({"kind": "points", "value": 50.0},), "bar_breakout": ({"kind": "points", "value": 20.0},),
         "at_time": ({"kind": "points", "value": 20.0},),
         "opening_range": ({"kind": "points", "value": 30.0}, {"kind": "range"})}
TARGETS = ({"kind": "points", "value": 150.0}, {"kind": "rr", "value": 3.0}, {"kind": "none"})


def base(rule: str, /, **over) -> dict:
    a = copy.deepcopy(lab_forms.schema()["defaults"][rule])
    a["name"] = "my_orb"
    a.update(over)
    return a


def every_answer():
    for rule in RULES:
        for side, stop, target in itertools.product(SIDES[rule], STOPS[rule], TARGETS):
            yield base(rule, side=side, stop=stop, target=target)


def ident(a: dict) -> str:
    return f"{a['rule']}-{a['side']}-{a['stop']['kind']}-{a['target']['kind']}"


EVERY = list(every_answer())


# ---------------------------------------------------------------- the schema

def test_schema_defaults_build_for_every_rule():
    s = lab_forms.schema()
    assert s["markets"] == ["NQ", "ES", "YM", "RTY", "GC", "SI"]
    assert [x[0] for x in s["sides"]] == ["both", "long", "short"]
    assert [r["id"] for r in s["rules"]] == list(RULES)
    for r in s["rules"]:
        assert r["label"] and r["words"]
        assert set(r["fields"]) <= set(s["fields"]) and "market" in r["fields"] and "out_by" in r["fields"]
        got = s["defaults"][r["id"]]
        assert got["market"] == "NQ" and got["rule"] == r["id"] and "name" not in got
        assert set(got) == set(r["fields"]) | {"rule"}
        assert lab_forms.build(got | {"name": "my_orb"})
    for f in s["fields"].values():
        assert f["label"] and f["words"] and f["type"] in ("time", "number", "int", "choice", "stop", "target")
        if f["type"] == "choice":
            assert f["choices"]


def test_schema_carries_what_the_page_needs_to_check_a_number():
    s = lab_forms.schema()
    assert s["ticks"] == {"NQ": 0.25, "ES": 0.25, "YM": 1.0, "RTY": 0.1, "GC": 0.1, "SI": 0.005}
    f = s["fields"]
    assert (f["lookback"]["min"], f["lookback"]["max"], f["lookback"]["step"]) == (2, 40, 1)
    assert (f["trades"]["min"], f["trades"]["max"], f["trades"]["step"]) == (1, 5, 1)
    assert f["distance"]["tick_multiple"] is True and f["distance"]["min_ticks"] == 1
    kinds = {k["id"]: k for k in f["stop"]["kinds"]}
    assert kinds["points"]["tick_multiple"] is True and kinds["points"]["min_ticks"] == 2
    assert "tick_multiple" not in kinds["range"]
    kinds = {k["id"]: k for k in f["target"]["kinds"]}
    assert kinds["points"]["tick_multiple"] is True and kinds["points"]["min_ticks"] == 1
    assert (kinds["rr"]["min"], kinds["rr"]["max"], kinds["rr"]["step"]) == (0.25, 20, 0.25)
    assert "tick_multiple" not in kinds["rr"] and kinds["none"] == {"id": "none", "label": "None"}
    for field in f.values():                       # every number the page draws says how to check it
        if field["type"] in ("int",):
            assert {"min", "max", "step"} <= set(field)
        if field["type"] == "number":
            assert field["tick_multiple"] is True and field["min_ticks"] >= 1


def test_schema_is_plain_json():
    s = lab_forms.schema()
    assert json.loads(json.dumps(s)) == s


# ---------------------------------------------------------------- what a form makes

@pytest.mark.parametrize("a", EVERY, ids=ident)
def test_every_combination_builds_a_valid_clean_draft(a):
    code = lab_forms.build(a)
    draftstore.check_source(code)
    meta = draftstore.static_meta(code)
    assert meta["root"] == a["market"] and meta["session_independent"] is True
    assert meta.get("bar_minutes", 0) == {"open_straddle": 0, "at_time": 0, "opening_range": 1,
                                          "bar_breakout": a.get("bar_min", 0)}[a["rule"]]
    got = {i["key"]: i["default"] for i in meta["inputs"]}
    if a["stop"]["kind"] == "points":
        assert got["sl_pts"] == a["stop"]["value"]
    else:
        assert "sl_pts" not in got
    t = a["target"]
    assert got.get("tp_pts") == (t["value"] if t["kind"] == "points" else None)
    assert got.get("rr") == (t["value"] if t["kind"] == "rr" else None)
    for key in ("distance", "lookback", "trades"):
        assert got.get(key) == a.get(key)
    assert door.read_source(code) == []
    assert meta["doc"] == lab_forms.sentence(a)


@pytest.mark.parametrize("market", lab_forms.MARKETS)
@pytest.mark.parametrize("rule", RULES)
def test_every_market_builds_with_its_own_root(market, rule):
    a = base(rule, market=market, stop={"kind": "points", "value": 5.0})
    code = lab_forms.build(a)
    draftstore.check_source(code)
    assert draftstore.static_meta(code)["root"] == market and lab_forms.sentence(a).startswith(market)


@pytest.mark.parametrize("a", EVERY, ids=ident)
def test_a_one_sided_file_has_no_code_for_the_other_side(a):
    code = lab_forms.build(a)
    for side, other in (("long", '"short"'), ("short", '"long"')):
        if a["side"] == side:
            assert other not in code.replace(f'"side": "{side}"', "")


@pytest.mark.parametrize("a", EVERY, ids=ident)
def test_no_generated_local_is_set_and_never_used(a):
    for fn in (n for n in ast.walk(ast.parse(lab_forms.build(a))) if isinstance(n, ast.FunctionDef)):
        names = [n for n in ast.walk(fn) if isinstance(n, ast.Name)]
        stored = {n.id for n in names if isinstance(n.ctx, ast.Store)}
        loaded = {n.id for n in names if isinstance(n.ctx, ast.Load)}
        assert stored <= loaded, (fn.name, stored - loaded)


@pytest.mark.parametrize("a", EVERY, ids=ident)
def test_a_form_file_reads_back_intact(a):
    assert lab_forms.read(lab_forms.build(a)) == {"answers": a, "intact": True}


def test_the_file_has_the_header_and_the_same_answers_give_the_same_bytes():
    a = base("open_straddle")
    code = lab_forms.build(a)
    assert code == lab_forms.build(copy.deepcopy(a))
    lines = code.splitlines()
    assert lines[0] == f'"""{lab_forms.sentence(a)}"""'
    assert lines[1] == ('# Made with the Lab\'s form. "Edit in the form" opens it again; a change made by hand '
                        'here is kept until then.')
    assert lines[2] == "# form: " + json.dumps(a, sort_keys=True)
    body = "\n".join(lines[4:]) + "\n"
    assert lines[3] == "# code: " + hashlib.sha256(body.encode()).hexdigest()
    assert lines[4] == "from __future__ import annotations"
    assert "class MyOrb(Strategy):" in code


def test_intact_means_the_form_would_write_this_exact_file():
    a = base("bar_breakout", side="long")
    code = lab_forms.build(a)
    assert lab_forms.read(code) == {"answers": a, "intact": True}
    assert lab_forms.read(code.replace("from __future__", "from __futurE__"))["intact"] is False
    assert lab_forms.read(code + "# a note\n") == {"answers": a, "intact": False}
    # the docstring above the header is part of the file too: a hand edit there still reads, but is not intact
    mine = code.replace(f'"""{lab_forms.sentence(a)}"""', '"""Mine now.\n\nSecond line."""', 1)
    assert lab_forms.read(mine) == {"answers": a, "intact": False}
    # so is the header: a hand-edited answers line is not what the form wrote for those answers
    other = code.replace('"side": "long"', '"side": "short"')
    assert lab_forms.read(other) == {"answers": {**a, "side": "short"}, "intact": False}
    assert lab_forms.read(code.replace("\n", "\r\n"))["intact"] is False
    # answers the form would refuse are not intact either (and reading them does not raise)
    bad = code.replace('"lookback": 6', '"lookback": 600')
    assert lab_forms.read(bad) == {"answers": {**a, "lookback": 600}, "intact": False}


def test_read_never_raises_on_hostile_text():
    code = lab_forms.build(base("at_time"))
    lines = code.split("\n")
    deep = "\n".join(("# form: " + "[" * 100000) if x.startswith("# form: ") else x for x in lines)
    assert lab_forms.read(deep) is None
    assert lab_forms.read(code + "\n# \ud800\n") == {"answers": base("at_time"), "intact": False}
    assert lab_forms.read(code.replace("# Made", "# \ud800 Made")) == {"answers": base("at_time"), "intact": False}
    assert lab_forms.read(code.encode()) is None and lab_forms.read(b"\xff\xfe") is None
    assert lab_forms.read(None) is None and lab_forms.read(5) is None
    big = lab_forms.read(code + "# x\n" * 1_000_000)
    assert big == {"answers": base("at_time"), "intact": False}
    assert lab_forms.read("x" * 5_000_000) is None
    huge_int = code.replace('"time": "09:30"', '"time": "09:30", "n": ' + "9" * 5000)
    assert lab_forms.read(huge_int) is None or lab_forms.read(huge_int)["intact"] is False


def test_read_gives_none_without_a_header_or_with_a_header_that_does_not_read():
    for t in lab_templates.templates():
        assert lab_forms.read(t["code"]) is None
    assert lab_forms.read("") is None
    code = lab_forms.build(base("at_time"))
    lines = code.splitlines()
    broken = "\n".join("# form: {not json" if n == 2 else x for n, x in enumerate(lines)) + "\n"
    assert lab_forms.read(broken) is None
    notdict = "\n".join("# form: [1, 2]" if n == 2 else x for n, x in enumerate(lines)) + "\n"
    assert lab_forms.read(notdict) is None
    nocode = "\n".join(x for x in lines if not x.startswith("# code:")) + "\n"
    assert lab_forms.read(nocode) is None


def test_read_gives_none_for_a_header_with_a_non_finite_number():
    code = lab_forms.build(base("at_time"))
    for bad in ("NaN", "Infinity", "-Infinity"):
        for header in ('{"name": %s, "x": 1}' % bad, '{"name": "x", "x": %s}' % bad,
                       '{"name": "x", "x": [1, {"y": %s}]}' % bad):
            text = "\n".join("# form: " + header if x.startswith("# form: ") else x for x in code.split("\n"))
            assert lab_forms.read(text) is None, (bad, header)


def test_read_never_runs_the_text(tmp_path):
    marker = tmp_path / "ran"
    evil = lab_forms.build(base("at_time")) + f"\nopen({str(marker)!r}, 'w').write('x')\n"
    assert lab_forms.read(evil)["intact"] is False and not marker.exists()


def test_the_class_name_comes_from_the_draft_name_and_never_shadows_the_imports():
    assert "class MyOrb(Strategy):" in lab_forms.build(base("at_time", name="my_orb"))
    assert "class NqOrb15(Strategy):" in lab_forms.build(base("at_time", name="nq_orb_15"))
    assert "class InputDraft(Strategy):" in lab_forms.build(base("at_time", name="input"))
    draftstore.check_source(lab_forms.build(base("at_time", name="input")))


def test_a_draft_named_like_a_python_keyword_or_constant_still_builds():
    names = [k.lower() for k in keyword.kwlist]
    ok = []
    for n in names:
        try:
            draftstore.validate_name(n)
        except ValueError:
            continue
        ok.append(n)
    assert {"true", "false", "none", "class", "return"} <= set(ok)
    for n in ok + ["nq_true", "exception", "int", "object"]:
        for rule in RULES:
            code = lab_forms.build(base(rule, name=n))
            draftstore.check_source(code)
            assert draftstore.static_meta(code)["class"].isidentifier()
            assert not keyword.iskeyword(draftstore.static_meta(code)["class"])


def test_build_checks_its_own_output_and_raises_a_plain_error_for_its_own_bug(monkeypatch):
    monkeypatch.setattr(lab_forms, "_class_name", lambda name: "True")
    with pytest.raises(RuntimeError) as e:
        lab_forms.build(base("at_time"))
    assert not isinstance(e.value, ValueError)


# ---------------------------------------------------------------- the sentence

def test_the_sentences_in_the_brief():
    a = base("open_straddle", market="NQ", time="09:30", distance=15.0, stop={"kind": "points", "value": 50.0},
             target={"kind": "rr", "value": 3.0}, side="both", out_by="15:55")
    assert lab_forms.sentence(a) == ("NQ: at 09:30 a buy stop 15 points above and a sell stop 15 points below. "
                                     "Stop 50 points, target 3 x the stop. One trade a day. "
                                     "Unfilled orders are cancelled at 11:00. Out by 15:55.")
    a = base("opening_range", market="ES", range_from="09:30", range_min=15, stop={"kind": "range"},
             target={"kind": "rr", "value": 2.0}, side="both", out_by="15:55")
    assert lab_forms.sentence(a) == ("ES: after the first 15 minutes from 09:30, a buy stop above the range and a "
                                     "sell stop below it. Stop at the other side of the range, target 2 x the stop. "
                                     "One trade a day. Unfilled orders are cancelled at 11:00. Out by 15:55.")
    a = base("open_straddle", side="long", last_entry="12:55", out_by="15:50")
    assert lab_forms.sentence(a).endswith("One trade a day. Unfilled orders are cancelled at 12:55. Out by 15:50.")
    a = base("bar_breakout", side="long", bar_min=5, lookback=6, trades=2, stop={"kind": "points", "value": 20.0},
             target={"kind": "points", "value": 40.0}, last_entry="11:00", out_by="11:30")
    assert lab_forms.sentence(a) == ("NQ, long only: buys when a 5-minute bar closes above the last 6 bars' high, "
                                     "from 09:30 to 11:00. Stop 20 points, target 40 points. Up to 2 trades a day. "
                                     "Out by 11:30.")
    a = base("at_time", market="GC", side="short", time="08:30", stop={"kind": "points", "value": 5.0},
             target={"kind": "none"}, out_by="09:55")
    assert lab_forms.sentence(a) == ("GC: sells at the market at 08:30. Stop 5 points, no target. "
                                     "One trade a day. Out by 09:55.")


def test_every_combination_has_one_plain_sentence():
    for a in EVERY:
        s = lab_forms.sentence(a)
        assert s.startswith(a["market"]) and s.endswith(f"Out by {a['out_by']}.") and "\n" not in s
        assert ("long only" in s) == (a["side"] == "long" and a["rule"] != "at_time")
        assert ("short only" in s) == (a["side"] == "short" and a["rule"] != "at_time")


# ---------------------------------------------------------------- the refusals

def refused(a, field: str, sentence: str):
    with pytest.raises(lab_forms.FormError) as e:
        lab_forms.build(a)
    assert (e.value.field, e.value.sentence) == (field, sentence) and str(e.value) == sentence
    with pytest.raises(lab_forms.FormError):
        lab_forms.sentence(a)


def without(a: dict, *keys) -> dict:
    return {k: v for k, v in a.items() if k not in keys}


PICK = "Pick one from the list."
STOP = "Every entry needs a stop."
TARGET = "Give a target, or pick None."
CLOCK = "A New York time, like 09:30."
INCOMPLETE = "The form is incomplete."
LAST = "It must be after the last entry, and 15:55 at the latest."


def test_a_name_that_is_not_a_draft_name_gets_the_draftstores_message():
    for bad in ("Bad Name", "x", "draft_x", "strategy", None, 7):
        try:
            draftstore.validate_name(bad)
        except ValueError as e:
            refused(base("at_time", name=bad), "name", str(e))
    refused(without(base("at_time"), "name"), "name", INCOMPLETE)         # a missing key is the form's, not the name's


@pytest.mark.parametrize("key,bad", [("market", "CL"), ("market", None), ("market", "nq"), ("market", []),
                                     ("rule", "orb"), ("rule", None), ("rule", {}), ("side", "up"), ("side", None),
                                     ("side", [])])
def test_market_rule_and_side_are_picked_from_their_lists(key, bad):
    refused(base("open_straddle", **{key: bad}), key, PICK)


def test_the_at_time_rule_takes_long_or_short_only():
    refused(base("at_time", side="both"), "side", "Pick long or short for this rule.")
    refused(base("at_time", side="x"), "side", PICK)


@pytest.mark.parametrize("stop", [None, {}, {"kind": "points"}, {"kind": "points", "value": 0},
                                  {"kind": "points", "value": -5.0}, {"kind": "points", "value": 0.25},
                                  {"kind": "points", "value": "50"}, {"kind": "points", "value": True},
                                  {"kind": "points", "value": float("nan")}, {"kind": "ticks", "value": 5.0},
                                  {"kind": "points", "value": 5.0, "extra": 1}, "50"])
def test_every_entry_needs_a_stop(stop):
    refused(base("open_straddle", stop=stop), "stop", STOP)


def test_a_huge_number_still_makes_a_readable_draft():
    code = lab_forms.build(base("open_straddle", distance=1e300, stop={"kind": "points", "value": 1e300}))
    draftstore.check_source(code)
    assert {i["key"]: i["default"] for i in draftstore.static_meta(code)["inputs"]}["sl_pts"] == 1e300


NASTY = [10 ** 400, -(10 ** 400), float("nan"), float("inf"), -float("inf"), "5", "", True, False, None, [], {}, [1],
         {"kind": "points"}, 1e308, -1e308, 1e-320, 0, -1, 10 ** 30, 2 ** 1024]


def nasty_fields():
    """(rule, how to put a bad value into the base answers) for every numeric and time field of every rule."""
    for rule in RULES:
        a = base(rule)
        for key, v in a.items():
            if key in ("stop", "target"):
                if v["kind"] in ("points", "rr"):
                    yield rule, key + ".value", lambda bad, a=a, key=key: {**a, key: {**a[key], "value": bad}}
                yield rule, key, lambda bad, a=a, key=key: {**a, key: bad}
                yield rule, key + ".kind", lambda bad, a=a, key=key: {**a, key: {**a[key], "kind": bad}}
            elif key not in ("name",):
                yield rule, key, lambda bad, a=a, key=key: {**a, key: bad}


@pytest.mark.parametrize("bad", NASTY, ids=repr)
def test_no_arithmetic_error_escapes_build_for_any_json_shaped_value(bad):
    n = 0
    for rule, field, put in nasty_fields():
        answers = put(bad)
        try:
            code = lab_forms.build(answers)
        except lab_forms.FormError as e:
            assert e.sentence and e.field
        else:
            draftstore.check_source(code)
            assert lab_forms.read(code)["intact"] is True
        try:
            lab_forms.sentence(answers)
        except lab_forms.FormError:
            pass
        n += 1
    assert n > 40


def test_a_number_too_big_for_a_float_gets_the_fields_own_sentence():
    refused(base("open_straddle", distance=10 ** 400), "distance", "The distance must be at least one tick.")
    refused(base("open_straddle", stop={"kind": "points", "value": 10 ** 400}), "stop", STOP)
    refused(base("open_straddle", target={"kind": "rr", "value": 10 ** 400}), "target", TARGET)
    refused(base("bar_breakout", lookback=10 ** 400), "lookback", "Between 2 and 40 bars.")
    refused(base("bar_breakout", trades=-(10 ** 400)), "trades", "Between 1 and 5.")
    refused(base("opening_range", range_min=10 ** 400), "range_min", PICK)
    refused(base("bar_breakout", bar_min=10 ** 400), "bar_min", PICK)


def test_a_time_is_ascii_digits_only():
    for bad in ("0\u0669:00", "\u06f0\u06f9:30", "09:3\u0660", "\uff10\uff19:30"):
        refused(base("at_time", time=bad), "time", CLOCK)
        refused(base("open_straddle", last_entry=bad), "last_entry", CLOCK)
        refused(base("at_time", out_by=bad), "out_by", CLOCK)
    refused(base("open_straddle", time="09:30", last_entry="0\u0669:00", out_by="15:55"), "last_entry", CLOCK)


TICK = "Use a multiple of the tick ({}).".format


@pytest.mark.parametrize("market,tick,bad,good", [("NQ", "0.25", 15.1, 15.25), ("ES", "0.25", 7.3, 7.5),
                                                   ("YM", "1", 7.5, 8.0), ("RTY", "0.1", 5.05, 5.1),
                                                   ("GC", "0.1", 5.05, 5.1), ("SI", "0.005", 0.012, 0.015)])
def test_distance_stop_and_target_points_are_whole_ticks_of_the_market(market, tick, bad, good):
    sentence = TICK(tick)
    refused(base("open_straddle", market=market, distance=bad), "distance", sentence)
    assert lab_forms.build(base("open_straddle", market=market, distance=good))
    refused(base("open_straddle", market=market, stop={"kind": "points", "value": bad + 5}), "stop", sentence)
    assert lab_forms.build(base("open_straddle", market=market, stop={"kind": "points", "value": good + 5}))
    refused(base("open_straddle", market=market, target={"kind": "points", "value": bad + 5}), "target", sentence)
    assert lab_forms.build(base("open_straddle", market=market, target={"kind": "points", "value": good + 5}))
    # a rr target is a ratio, not a price distance
    assert lab_forms.build(base("open_straddle", market=market, target={"kind": "rr", "value": 1.3}))


def test_the_tick_sentence_comes_after_the_fields_existing_checks():
    refused(base("open_straddle", stop={"kind": "points", "value": 0.3}), "stop", STOP)          # under 2 ticks first
    refused(base("open_straddle", distance=0.1), "distance", "The distance must be at least one tick.")
    refused(base("open_straddle", target={"kind": "points", "value": 0.1}), "target", TARGET)
    refused(base("open_straddle", market="YM", distance=15.5, stop={"kind": "points", "value": 30.5}),
            "stop", TICK("1"))                                      # the table's order: stop before distance


def test_the_stop_floor_is_two_ticks_of_the_market():
    for market, ok, low in (("NQ", 0.5, 0.25), ("ES", 0.5, 0.25), ("YM", 2.0, 1.0), ("RTY", 0.2, 0.1),
                            ("GC", 0.2, 0.1), ("SI", 0.01, 0.005)):
        assert lab_forms.build(base("open_straddle", market=market, stop={"kind": "points", "value": ok}))
        refused(base("open_straddle", market=market, stop={"kind": "points", "value": low}), "stop", STOP)


@pytest.mark.parametrize("rule", ["open_straddle", "bar_breakout", "at_time"])
def test_the_range_stop_only_works_with_the_opening_range(rule):
    refused(base(rule, stop={"kind": "range"}), "stop", "That stop only works with the opening range.")
    refused(base(rule, stop={"kind": "range", "value": 5.0}), "stop", "That stop only works with the opening range.")
    refused(base("opening_range", stop={"kind": "range", "value": 5.0}), "stop", STOP)


@pytest.mark.parametrize("target", [None, {}, {"kind": "points"}, {"kind": "points", "value": 0.1},
                                    {"kind": "points", "value": 0}, {"kind": "rr", "value": 0.2},
                                    {"kind": "rr", "value": 20.5}, {"kind": "rr", "value": "3"},
                                    {"kind": "none", "value": 1}, {"kind": "all"}, 5])
def test_a_target_is_given_or_none(target):
    refused(base("open_straddle", target=target), "target", TARGET)


def test_the_target_edges_are_allowed():
    for t in ({"kind": "points", "value": 0.25}, {"kind": "rr", "value": 0.25}, {"kind": "rr", "value": 20.0},
              {"kind": "rr", "value": 20}):
        assert lab_forms.build(base("open_straddle", target=t))


def test_distance_lookback_trades_and_the_two_lists():
    refused(base("open_straddle", distance=0.2), "distance", "The distance must be at least one tick.")
    refused(base("open_straddle", distance="15"), "distance", "The distance must be at least one tick.")
    assert lab_forms.build(base("open_straddle", distance=0.25))
    for bad in (1, 41, 6.5, "6", None, True, 0):
        refused(base("bar_breakout", lookback=bad), "lookback", "Between 2 and 40 bars.")
    for good in (2, 40, 6.0):
        assert lab_forms.read(lab_forms.build(base("bar_breakout", lookback=good)))["answers"]["lookback"] == int(good)
    for bad in (0, 6, 2.5, "1", None, False):
        refused(base("bar_breakout", trades=bad), "trades", "Between 1 and 5.")
    for bad in (10, 0, "15", None, True):
        refused(base("opening_range", range_min=bad), "range_min", PICK)
    for bad in (3, 30, "5", None):
        refused(base("bar_breakout", bar_min=bad), "bar_min", PICK)


@pytest.mark.parametrize("bad", ["9:30", "09:30:00", "24:00", "09:60", "00:04", "15:56", "16:00", "", "ten", 930, None])
@pytest.mark.parametrize("rule,key", [("open_straddle", "time"), ("opening_range", "range_from"),
                                      ("bar_breakout", "from"), ("at_time", "time"), ("open_straddle", "last_entry"),
                                      ("opening_range", "last_entry"), ("bar_breakout", "last_entry"),
                                      ("open_straddle", "out_by"), ("at_time", "out_by")])
def test_every_time_is_a_new_york_clock_time_from_0005_to_1555(rule, key, bad):
    refused(base(rule, **{key: bad}), key, CLOCK)


def test_the_time_edges_are_allowed():
    assert lab_forms.build(base("at_time", time="00:05", out_by="15:55"))
    assert lab_forms.build(base("at_time", time="15:50", out_by="15:55"))


def test_the_last_entry_must_come_after_the_start():
    refused(base("open_straddle", time="09:30", last_entry="09:30"), "last_entry", "It must be after the start.")
    refused(base("open_straddle", time="09:30", last_entry="09:29"), "last_entry", "It must be after the start.")
    refused(base("bar_breakout", **{"from": "10:00", "last_entry": "10:00"}), "last_entry",
            "It must be after the start.")
    # the opening range starts acting when its range is done: 09:30 + 15 minutes
    refused(base("opening_range", range_from="09:30", range_min=15, last_entry="09:45"), "last_entry",
            "It must be after the start.")
    refused(base("opening_range", range_from="09:30", range_min=15, last_entry="09:40"), "last_entry",
            "It must be after the start.")
    assert lab_forms.build(base("opening_range", range_from="09:30", range_min=15, last_entry="09:46"))


def test_out_by_must_come_after_the_last_entry_and_by_1555():
    refused(base("open_straddle", last_entry="11:00", out_by="11:00"), "out_by", LAST)
    refused(base("open_straddle", last_entry="11:00", out_by="10:59"), "out_by", LAST)
    refused(base("bar_breakout", last_entry="11:00", out_by="10:00"), "out_by", LAST)
    refused(base("at_time", time="09:30", out_by="09:30"), "out_by", LAST)
    refused(base("at_time", time="09:30", out_by="09:00"), "out_by", LAST)
    assert lab_forms.build(base("open_straddle", last_entry="11:00", out_by="11:01"))


@pytest.mark.parametrize("a,field", [(without(base("open_straddle"), "distance"), "distance"),
                                     (without(base("open_straddle"), "last_entry"), "last_entry"),
                                     (without(base("open_straddle"), "out_by"), "out_by"),
                                     (without(base("open_straddle"), "time"), "time"),
                                     (without(base("bar_breakout"), "trades"), "trades"),
                                     (without(base("opening_range"), "range_min"), "range_min"),
                                     (without(base("at_time"), "time"), "time"),
                                     ({**base("open_straddle"), "lookback": 6}, "lookback"),
                                     ({**base("at_time"), "last_entry": "11:00"}, "last_entry"),
                                     ({**base("opening_range"), "distance": 5.0}, "distance"),
                                     ({**base("open_straddle"), "bogus": 1}, "bogus"),
                                     ({**base("open_straddle"), 1: 2}, "1"),
                                     (without(base("opening_range"), "target"), "target"),
                                     (without(base("opening_range"), "stop"), "stop"),
                                     (without(base("opening_range"), "market"), "market"),
                                     (without(base("opening_range"), "side"), "side")])
def test_a_key_that_does_not_belong_or_is_missing_is_an_incomplete_form(a, field):
    refused(a, field, INCOMPLETE)


def test_a_key_problem_is_reported_before_any_value_is_looked_at():
    bad_values = {"name": "Bad Name", "market": "XX", "side": "up", "stop": None, "target": None, "distance": 0,
                  "time": "x", "last_entry": "x", "out_by": "x"}
    refused({**base("open_straddle"), **bad_values, "bogus": 1}, "bogus", INCOMPLETE)
    refused(without({**base("open_straddle"), **bad_values}, "last_entry"), "last_entry", INCOMPLETE)
    refused(without({**base("open_straddle"), **bad_values}, "name", "out_by"), "name", INCOMPLETE)   # table order
    refused({**base("at_time"), **{k: v for k, v in bad_values.items() if k in base("at_time")}, "lookback": 6},
            "lookback", INCOMPLETE)


def test_something_that_is_not_a_dict_is_an_incomplete_form():
    for bad in (None, [], "x", 3):
        with pytest.raises(lab_forms.FormError) as e:
            lab_forms.build(bad)
        assert e.value.sentence == INCOMPLETE


def test_the_first_failing_field_wins_in_the_tables_order():
    a = base("open_straddle")
    bad = {"name": "Bad Name", "market": "XX", "rule": "nope", "side": "up"}
    refused({**a, **bad}, "name", str(_name_error("Bad Name")))
    refused({**a, **without(bad, "name")}, "market", PICK)
    refused({**a, **without(bad, "name", "market")}, "rule", PICK)
    refused({**a, "side": "up", "stop": None}, "side", PICK)
    refused({**base("at_time"), "side": "both", "stop": None}, "side", "Pick long or short for this rule.")
    refused({**a, "stop": None, "target": None, "distance": 0}, "stop", STOP)
    refused({**a, "target": None, "distance": 0, "time": "x"}, "target", TARGET)
    refused({**a, "distance": 0, "time": "x"}, "distance", "The distance must be at least one tick.")
    b = base("bar_breakout")
    refused({**b, "lookback": 1, "trades": 9, "bar_min": 7}, "lookback", "Between 2 and 40 bars.")
    refused({**b, "trades": 9, "bar_min": 7, "last_entry": "x"}, "trades", "Between 1 and 5.")
    refused({**b, "bar_min": 7, "last_entry": "x"}, "bar_min", PICK)
    refused({**b, "last_entry": "x", "out_by": "x"}, "last_entry", CLOCK)
    refused({**b, "from": "x", "last_entry": "x", "out_by": "x"}, "from", CLOCK)
    refused({**b, "last_entry": "09:00", "out_by": "x"}, "out_by", CLOCK)
    refused({**b, "last_entry": "09:00", "out_by": "09:00"}, "last_entry", "It must be after the start.")
    refused({**b, "out_by": "11:00"}, "out_by", LAST)


def _name_error(name) -> ValueError:
    try:
        draftstore.validate_name(name)
    except ValueError as e:
        return e
    raise AssertionError("valid name")


# ---------------------------------------------------------------- the behaviour gate: the trade each rule takes
# The generated text is loaded the way the backtest child loads a draft (drafthost.register_source), here in the
# test process because the text is this generator's own output, and replayed through the tester's run_session.

D = dt.date(2024, 3, 5)


def tape(rows, root="NQ") -> Tape:
    """rows: [("HH:MM:SS[.mmm]", price), ...] in tape order."""
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(D, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, D, root + "H4", ts, px, array("i", [1] * len(ts)), {})


@pytest.fixture
def play():
    """play(answers, rows) -> (SessionResult, the strategy); the registered drafts are removed afterwards."""
    made = []

    def go(answers, rows, root=None, slip=1.0):
        name = answers["name"]
        cls = drafthost.register_source(name, lab_forms.build(answers))
        made.append(name)
        strategy = cls({})
        return run_session(strategy, tape(rows, root or answers["market"]), Costs(4.0, slip), qty=1), strategy

    yield go
    for name in made:
        strategies.REGISTRY.pop(draftstore.draft_id(name), None)
        sys.modules.pop(f"homebase_draft_{name}", None)


def at(hms: str) -> int:
    return et_ns(D, hms)


def straddle(**over):
    kw = dict(name="form_run", distance=15.0, stop={"kind": "points", "value": 10.0},
              target={"kind": "rr", "value": 3.0})
    return base("open_straddle", **(kw | over))


def test_straddle_both_sides_the_buy_fills_and_the_sell_is_cancelled(play):
    res, _ = play(straddle(), [("09:29:59", 100.0), ("09:31:00", 114.0), ("09:32:00", 115.0),
                               ("09:40:00", 146.0), ("10:00:00", 80.0)])
    t, = res.trades                                  # the sell stop at 85 never lives on: 80 at 10:00 trades nothing
    assert (t.side, t.order_price, t.entry_price) == ("long", 115.0, 115.25)
    assert (t.sl, t.tp) == (105.25, 145.25)          # 10 behind the fill, 3 x that ahead of it
    assert (t.exit_reason, t.exit_price, t.exit_ns) == ("tp", 145.25, at("09:40:00"))
    assert res.skip is None


def test_straddle_short_only_places_no_buy_stop(play):
    res, _ = play(straddle(side="short"), [("09:29:59", 100.0), ("09:31:00", 90.0), ("09:32:00", 84.5),
                                           ("09:40:00", 95.0), ("10:00:00", 130.0)])
    t, = res.trades                                  # 130 at 10:00 would fill a buy stop at 115
    assert (t.side, t.order_price, t.entry_price) == ("short", 85.0, 84.25)
    assert (t.sl, t.tp) == (94.25, 54.25)
    assert (t.exit_reason, t.exit_price) == ("sl", 95.25)


def test_straddle_long_only_places_no_sell_stop(play):
    res, _ = play(straddle(), [("09:29:59", 100.0)])      # (both sides, as a control: nothing triggers)
    assert res.trades == []
    res, _ = play(straddle(side="long"), [("09:29:59", 100.0), ("09:31:00", 70.0), ("09:32:00", 115.5),
                                          ("12:00:00", 116.0), ("15:56:00", 118.0)])
    t, = res.trades                                  # 70 at 09:31 would fill a sell stop at 85
    assert (t.side, t.entry_price, t.sl) == ("long", 115.75, 105.75)
    assert (t.exit_reason, t.exit_price, t.exit_ns) == ("time", 117.75, at("15:56:00"))


def test_straddle_rr_target_is_taken_from_a_gapped_fill(play):
    res, _ = play(straddle(), [("09:29:59", 100.0), ("09:31:00", 120.0), ("09:40:00", 151.0)])
    t, = res.trades
    assert t.order_price == 115.0 and t.entry_price == 120.25      # the gap is paid
    assert (t.sl, t.tp) == (110.25, 150.25)                         # stop 10 and target 30 from the FILL
    assert (t.exit_reason, t.exit_price) == ("tp", 150.25)


def test_straddle_points_target(play):
    res, _ = play(straddle(target={"kind": "points", "value": 20.0}),
                  [("09:29:59", 100.0), ("09:31:00", 115.0), ("09:40:00", 136.0)])
    t, = res.trades
    assert (t.entry_price, t.sl, t.tp) == (115.25, 105.25, 135.25)
    assert (t.exit_reason, t.exit_price) == ("tp", 135.25)


def test_straddle_without_a_target_leaves_at_out_by(play):
    a = straddle(target={"kind": "none"}, out_by="11:30")
    res, strategy = play(a, [("09:29:59", 100.0), ("09:32:00", 115.0), ("11:29:00", 130.0), ("11:31:00", 131.0)])
    t, = res.trades
    assert t.tp is None and t.sl == 105.25
    assert (t.exit_reason, t.exit_price, t.exit_ns) == ("time", 130.75, at("11:31:00"))
    assert strategy.session_window == ("09:25", "11:35")


def test_straddle_unfilled_stops_are_cancelled_at_the_last_entry(play):
    tape_rows = [("09:29:59", 100.0), ("10:59:00", 100.0), ("11:00:30", 120.0), ("11:30:00", 80.0)]
    res, _ = play(straddle(), tape_rows)
    assert res.trades == [] and res.skip is None
    res, _ = play(straddle(last_entry="12:00"), tape_rows)          # the control: with time left, the buy fills
    assert [t.side for t in res.trades] == ["long"]


def test_straddle_with_no_print_before_its_time_skips_the_day(play):
    res, _ = play(straddle(), [("09:31:00", 100.0), ("10:00:00", 130.0)])
    assert res.trades == [] and res.skip == "no print before 09:30"


def ranged(**over):
    return base("opening_range", name="form_run", **over)


RANGE_ROWS = [("09:29:59", 300.0), ("09:31:00", 102.0), ("09:35:00", 110.0), ("09:40:00", 98.0),
              ("09:44:59", 105.0)]                                  # the range is 98 to 110; 300 is before it


def test_opening_range_both_sides_stop_at_the_other_side_of_the_range(play):
    res, _ = play(ranged(), RANGE_ROWS + [("09:50:00", 111.0), ("10:00:00", 140.0), ("10:30:00", 90.0)])
    t, = res.trades                                  # 90 at 10:30 would fill the sell stop at 97.75
    assert (t.side, t.order_price, t.entry_price) == ("long", 110.25, 111.25)
    assert (t.sl, t.tp) == (98.0, 137.75)            # the range's low exactly (not moved by the 1.0 gap); 2 x that from the fill
    assert (t.exit_reason, t.exit_price) == ("tp", 137.75)


def test_opening_range_short_only(play):
    res, _ = play(ranged(side="short"), RANGE_ROWS + [("09:50:00", 97.0), ("10:00:00", 69.0), ("10:30:00", 130.0)])
    t, = res.trades                                  # 130 at 10:30 would fill a buy stop at 110.25
    assert (t.side, t.order_price, t.entry_price) == ("short", 97.75, 96.75)
    assert (t.sl, t.tp) == (110.0, 70.25)            # the range's high exactly
    assert (t.exit_reason, t.exit_price) == ("tp", 70.25)


def test_opening_range_long_only_and_points_stop(play):
    a = ranged(side="long", stop={"kind": "points", "value": 12.0}, target={"kind": "points", "value": 20.0})
    res, _ = play(a, RANGE_ROWS + [("09:44:59.500", 90.0), ("09:50:00", 111.0), ("10:00:00", 132.0)])
    t, = res.trades
    assert (t.entry_price, t.sl, t.tp) == (111.25, 99.25, 131.25)     # 12 behind the entry, 20 ahead; both follow the fill
    assert (t.exit_reason, t.exit_price) == ("tp", 131.25)


def test_opening_range_a_longer_range_and_a_later_start(play):
    a = ranged(range_from="10:00", range_min=30, last_entry="12:00")
    rows = [("09:35:00", 500.0), ("10:05:00", 100.0), ("10:20:00", 108.0), ("10:29:59", 104.0),
            ("10:50:00", 109.0), ("11:00:00", 140.0)]
    res, strategy = play(a, rows)
    t, = res.trades
    assert (t.order_price, t.entry_price, t.sl, t.tp) == (108.25, 109.25, 100.0, 127.75)
    assert strategy.session_window == ("09:55", "16:00") and strategy.bar_window == ("10:00", "10:30")


def test_the_range_stop_is_at_the_other_side_of_the_range_whatever_the_fill_gap(play):
    # NQ: a 5-point gap through the buy stop (110.25) fills at 115.50; the stop is still the range's low, 98.0
    res, _ = play(ranged(), RANGE_ROWS + [("09:50:00", 115.0), ("10:00:00", 200.0)])
    t, = res.trades
    assert (t.order_price, t.entry_price, t.sl) == (110.25, 115.25, 98.0)
    assert t.tp == 115.25 + 2.0 * (115.25 - 98.0)                  # rr 2 taken from the FILL and that stop
    # a points target is measured from the entry price (the stop price), 20 points, not from the gapped fill
    res, strategy = play(ranged(target={"kind": "points", "value": 20.0}),
                         RANGE_ROWS + [("09:50:00", 115.0), ("10:00:00", 200.0)])
    assert (res.trades[0].sl, res.trades[0].tp, res.trades[0].exit_price) == (98.0, 130.25, 130.25)
    assert "ctx.move_brackets_to_fill = False" in lab_forms.build(ranged())
    assert "ctx.move_brackets_to_fill = True" in lab_forms.build(ranged(stop={"kind": "points", "value": 10.0}))


def test_the_range_stop_is_exact_to_the_tick_on_silver_too(play):
    rows = [("09:29:59", 30.0), ("09:31:00", 30.0), ("09:40:00", 30.1), ("09:44:59", 30.05), ("09:50:00", 30.2),
            ("10:00:00", 31.0)]
    res, _ = play(ranged(market="SI"), rows)
    t, = res.trades
    assert t.order_price == pytest.approx(30.105) and t.entry_price == pytest.approx(30.205)
    assert t.sl == pytest.approx(30.0, abs=1e-9)                    # the low of the range, to the tick
    assert t.tp == pytest.approx(30.205 + 2 * 0.205, abs=1e-9)
    res, _ = play(ranged(market="SI", side="short"), [("09:29:59", 30.0), ("09:31:00", 30.0), ("09:40:00", 30.1),
                                                        ("09:44:59", 30.05), ("09:50:00", 29.9), ("10:00:00", 29.0)])
    assert res.trades[0].sl == pytest.approx(30.1, abs=1e-9)        # the high of the range


@pytest.mark.parametrize("market,px", [("NQ", 100.0), ("SI", 30.0)])
def test_a_flat_opening_range_takes_no_trade_with_the_range_stop(play, market, px):
    rows = [("09:29:59", px), ("09:31:00", px), ("09:44:59", px), ("09:50:00", px + 4 * (0.25 if market == "NQ" else 0.005)),
            ("10:00:00", px * 2)]
    res, _ = play(ranged(market=market), rows)
    assert res.trades == [] and res.skip == "the opening range is too small"
    for side in ("long", "short"):
        assert play(ranged(market=market, side=side), rows)[0].skip == "the opening range is too small"
    # the same flat range with a points stop trades: the guard is the range stop's own
    res, _ = play(ranged(market=market, stop={"kind": "points", "value": 5.0 if market == "NQ" else 0.05}), rows)
    assert res.skip is None


def test_a_one_tick_range_is_just_enough_for_the_range_stop(play):
    rows = [("09:29:59", 100.0), ("09:31:00", 100.0), ("09:44:59", 100.25), ("09:50:00", 101.0), ("10:00:00", 140.0)]
    res, _ = play(ranged(), rows)
    t, = res.trades                                  # entry 100.50, stop 100.00: two ticks apart
    assert (t.order_price, t.sl) == (100.5, 100.0) and res.skip is None


def test_opening_range_with_no_price_in_the_range_skips_the_day(play):
    res, _ = play(ranged(), [("09:29:59", 100.0), ("09:50:00", 130.0)])
    assert res.trades == [] and res.skip == "no prices in the opening range"


def test_opening_range_unfilled_stops_are_cancelled_at_the_last_entry(play):
    rows = RANGE_ROWS + [("10:59:00", 105.0), ("11:00:30", 120.0), ("11:30:00", 80.0)]
    res, _ = play(ranged(), rows)
    assert res.trades == []
    res, _ = play(ranged(last_entry="12:00"), rows)
    assert [t.side for t in res.trades] == ["long"]


def breakout(**over):
    kw = dict(name="form_run", bar_min=5, lookback=3, trades=2, side="long", last_entry="11:00",
              stop={"kind": "points", "value": 5.0}, target={"kind": "points", "value": 10.0})
    kw.update(over)
    return base("bar_breakout", **kw)


# 5-minute bars from 09:30, one print each: 100, 101, 100, then a close above the 3 bars' high, and so on
RISING = [("09:30:10", 100.0), ("09:35:10", 101.0), ("09:40:10", 100.0), ("09:45:10", 102.0),
          ("09:50:10", 102.5), ("09:55:10", 113.5), ("10:00:10", 114.0), ("10:05:10", 125.0),
          ("10:10:10", 140.0), ("10:15:10", 150.0)]


def test_bar_breakout_takes_two_trades_with_trades_2_and_never_a_third(play):
    res, _ = play(breakout(), RISING)
    first, second = res.trades                      # the bars closing at 10:10 and 10:15 also break out: no third
    assert (first.side, first.entry_ns, first.entry_price) == ("long", at("09:50:10"), 102.75)
    assert (first.sl, first.tp) == (97.75, 112.75)   # 5 and 10 from the 102 close, moved by the 0.75 fill gap
    assert (first.exit_reason, first.exit_price) == ("tp", 112.75)
    assert (second.entry_ns, second.entry_price) == (at("10:00:10"), 114.25)
    assert (second.sl, second.tp) == (109.25, 124.25)
    assert (second.exit_reason, second.exit_price) == ("tp", 124.25)
    res, _ = play(breakout(trades=3), RISING)
    assert len(res.trades) == 3                     # the limit is the only thing that stopped the third


def test_bar_breakout_one_trade_a_day_and_one_position_at_a_time(play):
    res, _ = play(breakout(trades=1), RISING)
    assert len(res.trades) == 1
    # a slow target: the bar that closes while the first trade is still open takes no second one
    res, _ = play(breakout(trades=3, target={"kind": "points", "value": 100.0}), RISING)
    assert len(res.trades) == 1 and res.trades[0].exit_reason in ("time", "eod")


def test_bar_breakout_sells_a_close_below_the_low_and_a_long_only_strategy_does_not(play):
    falling = [("09:30:10", 100.0), ("09:35:10", 101.0), ("09:40:10", 100.0), ("09:45:10", 98.0),
               ("09:50:10", 97.5), ("09:55:10", 87.0), ("10:00:10", 86.0)]
    res, _ = play(breakout(side="both", trades=1), falling)
    t, = res.trades
    assert (t.side, t.entry_price, t.sl, t.tp) == ("short", 97.25, 102.25, 87.25)
    assert (t.exit_reason, t.exit_price) == ("tp", 87.25)
    assert play(breakout(side="long"), falling)[0].trades == []
    assert play(breakout(side="short"), RISING)[0].trades == []


def test_bar_breakout_rr_target_is_worked_out_from_the_close(play):
    res, _ = play(breakout(side="long", target={"kind": "rr", "value": 2.0}), RISING)
    assert (res.trades[0].sl, res.trades[0].tp) == (97.75, 112.75)      # stop 5, target 2 x 5, both from the close


def test_bar_breakout_last_entry_is_inclusive_and_later_closes_do_nothing(play):
    res, _ = play(breakout(last_entry="09:50"), RISING)                 # the signal bar closes at 09:50
    assert [t.entry_ns for t in res.trades] == [at("09:50:10")]
    res, _ = play(breakout(last_entry="09:49"), RISING)
    assert res.trades == []


def test_bar_breakout_bars_that_began_before_the_start_time_do_not_count(play):
    rows = [("09:30:10", 100.0), ("09:35:10", 100.0), ("09:40:10", 101.0), ("09:45:10", 101.0)]
    res, _ = play(breakout(lookback=2, **{"from": "09:30"}), rows)
    assert len(res.trades) == 1                      # 09:30 and 09:35 count; the 09:40 bar breaks out
    res, _ = play(breakout(lookback=2, **{"from": "09:32"}), rows)
    assert res.trades == []                          # the 09:30 bar began before 09:32 and is not used


def timed(**over):
    kw = dict(name="form_run", side="long", time="09:30", stop={"kind": "points", "value": 5.0},
              target={"kind": "points", "value": 10.0})
    return base("at_time", **(kw | over))


def test_at_time_long_buys_at_the_market_with_stop_and_target_from_the_price(play):
    res, _ = play(timed(), [("09:29:59", 100.0), ("09:30:10", 100.5), ("10:00:00", 111.0)])
    t, = res.trades
    assert (t.side, t.order_price, t.entry_price, t.entry_ns) == ("long", None, 100.75, at("09:30:10"))
    assert (t.sl, t.tp) == (95.75, 110.75)
    assert (t.exit_reason, t.exit_price) == ("tp", 110.75)


def test_at_time_short_and_rr_target(play):
    res, _ = play(timed(side="short", target={"kind": "rr", "value": 2.0}),
                  [("09:29:59", 100.0), ("09:30:10", 99.5), ("10:00:00", 89.0)])
    t, = res.trades
    assert (t.side, t.entry_price, t.sl, t.tp) == ("short", 99.25, 104.25, 89.25)
    assert (t.exit_reason, t.exit_price) == ("tp", 89.25)


def test_at_time_with_no_print_before_its_time_skips_the_day(play):
    res, _ = play(timed(), [("09:30:10", 100.5), ("10:00:00", 111.0)])
    assert res.trades == [] and res.skip == "no print before 09:30"


def test_at_time_on_another_market_with_no_target_leaves_at_out_by(play):
    a = timed(market="GC", side="short", time="08:30", out_by="09:55", target={"kind": "none"})
    res, strategy = play(a, [("08:29:59", 2000.0), ("08:30:10", 1999.5), ("09:30:00", 1990.0),
                             ("09:56:00", 1989.0)])
    t, = res.trades
    assert t.entry_price == pytest.approx(1999.4) and t.sl == pytest.approx(2004.4) and t.tp is None
    assert (t.exit_reason, t.exit_price) == ("time", pytest.approx(1989.1))
    assert strategy.session_window == ("08:25", "10:00")


# ---------------------------------------------------------------- end to end in the real sandboxed backtest

@pytest.mark.skipif(not sandbox.available(), reason="the macOS sandbox is not available here")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")        # the web test client's own import notices
@pytest.mark.filterwarnings("ignore:Using `httpx`")
@pytest.mark.parametrize("rule", RULES)
def test_each_rule_backtests_in_the_sandbox(rule, tmp_path):
    from tests.test_lab_api import MARCH, OK, client, poll
    code = lab_forms.build(base(rule, name="form_sandbox"))
    with client(tmp_path) as c:
        assert c.put("/api/tester/drafts/form_sandbox", json={"code": code}, headers=OK).status_code == 200
        rid = c.post("/api/tester/run", json={"strategy": "draft_form_sandbox", "range": MARCH}, headers=OK).json()["id"]
        st = poll(c, rid)
        assert st["status"] == "done", st.get("error")
        assert c.get(f"/api/tester/run/{rid}/bundle").json()["run"]["strategy"]["id"] == "draft_form_sandbox"
