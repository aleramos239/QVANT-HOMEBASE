"""The Lab's fill-in form: answers in, a draft file out. Pure text (no draft runs in the chart service), plus the
behaviour gate: each generated strategy takes exactly the trade the contracts describe when the tester's own
run_session replays a small synthetic tape through it."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json

import pytest

from homebase import draftstore
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
    for k, key in (("distance", "distance"), ("lookback", "lookback"), ("trades", "trades")):
        assert got.get(key) == a.get(k)
    assert door.read_source(code) == []
    assert meta["doc"] == lab_forms.sentence(a)


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


def test_a_hand_edit_of_the_body_flips_intact_but_the_docstring_does_not():
    a = base("bar_breakout")
    code = lab_forms.build(a)
    assert lab_forms.read(code.replace("from __future__", "from __futurE__"))["intact"] is False
    assert lab_forms.read(code + "# a note\n") == {"answers": a, "intact": False}
    assert lab_forms.read(code.replace(f'"""{lab_forms.sentence(a)}"""', '"""Mine now.\n\nSecond line."""', 1)) \
        == {"answers": a, "intact": True}


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


def test_read_never_runs_the_text(tmp_path):
    marker = tmp_path / "ran"
    evil = lab_forms.build(base("at_time")) + f"\nopen({str(marker)!r}, 'w').write('x')\n"
    assert lab_forms.read(evil)["intact"] is False and not marker.exists()


def test_the_class_name_comes_from_the_draft_name_and_never_shadows_the_imports():
    assert "class MyOrb(Strategy):" in lab_forms.build(base("at_time", name="my_orb"))
    assert "class NqOrb15(Strategy):" in lab_forms.build(base("at_time", name="nq_orb_15"))
    assert "class InputDraft(Strategy):" in lab_forms.build(base("at_time", name="input"))
    draftstore.check_source(lab_forms.build(base("at_time", name="input")))


# ---------------------------------------------------------------- the sentence

def test_the_sentences_in_the_brief():
    a = base("open_straddle", market="NQ", time="09:30", distance=15.0, stop={"kind": "points", "value": 50.0},
             target={"kind": "rr", "value": 3.0}, side="both", out_by="15:55")
    assert lab_forms.sentence(a) == ("NQ: at 09:30 a buy stop 15 points above and a sell stop 15 points below. "
                                     "Stop 50 points, target 3 x the stop. One trade a day. Out by 15:55.")
    a = base("opening_range", market="ES", range_from="09:30", range_min=15, stop={"kind": "range"},
             target={"kind": "rr", "value": 2.0}, side="both", out_by="15:55")
    assert lab_forms.sentence(a) == ("ES: after the first 15 minutes from 09:30, a buy stop above the range and a "
                                     "sell stop below it. Stop at the other side of the range, target 2 x the stop. "
                                     "One trade a day. Out by 15:55.")
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
    refused(without(base("at_time"), "name"), "name", "name: 2-40 characters of a-z, 0-9 and '_', starting with a "
            "letter (e.g. nq_orb_15)")


@pytest.mark.parametrize("key,bad", [("market", "CL"), ("market", None), ("market", "nq"), ("rule", "orb"),
                                     ("rule", None), ("side", "up"), ("side", None)])
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
                                     (without(base("opening_range"), "target"), "target")])
def test_a_key_that_does_not_belong_or_is_missing_is_an_incomplete_form(a, field):
    if field == "target":
        refused(a, "target", TARGET)           # a missing target is the target's own sentence
    else:
        refused(a, field, INCOMPLETE)


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
    refused({**b, "out_by": "11:00", "bogus": 1}, "out_by", LAST)
    refused({**b, "bogus": 1}, "bogus", INCOMPLETE)


def _name_error(name) -> ValueError:
    try:
        draftstore.validate_name(name)
    except ValueError as e:
        return e
    raise AssertionError("valid name")
