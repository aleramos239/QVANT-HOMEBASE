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


def base(rule: str, **over) -> dict:
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
