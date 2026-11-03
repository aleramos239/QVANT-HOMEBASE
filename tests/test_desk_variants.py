"""Variant sets (desk/variants.py, routes/variants.py): the Desk's store, its routes, and the suggestions. Nothing combines by itself."""
from __future__ import annotations

import json

import pytest

from homebase.desk import variants as v
from tests.labdesk_util import LAB
from tests.test_fake_desk_lab import desk  # noqa: F401  (the fixture)

NAMES = {"a_r1", "a_r2", "a_r15", "b_fast", "b_flex", "c"}
TEAMS = {"g1": {"name": "Apex", "members": ["c"]}}


def mk(tmp_path, members=("a_r1", "a_r2"), **kw):
    return v.apply(tmp_path, "create", {"members": list(members), **kw}, teams=TEAMS, names=NAMES)


def test_create_one_set_per_strategy_and_the_team_member_refused(tmp_path):
    d = mk(tmp_path)
    assert d["sets"] == [{"id": "v1", "name": "a", "members": ["a_r1", "a_r2"], "labels": {"a_r1": "1R", "a_r2": "2R"}}]
    assert v.set_of(tmp_path, "a_r2")["id"] == "v1" and v.set_of(tmp_path, "c") is None
    with pytest.raises(v.VariantError, match="already in the set a"):
        mk(tmp_path, ("a_r2", "a_r15"))
    with pytest.raises(v.VariantError, match=r"^It is in the team Apex\.$"):
        mk(tmp_path, ("b_fast", "c"))
    with pytest.raises(v.VariantError):
        mk(tmp_path, ("b_fast",))


def test_a_label_over_12_characters_is_refused(tmp_path):
    with pytest.raises(v.VariantError):
        mk(tmp_path, labels={"a_r1": "x" * 13})
    d = mk(tmp_path)
    d = v.apply(tmp_path, "label", {"id": "v1", "member": "a_r1", "label": "base"}, teams={}, names=NAMES)
    assert d["sets"][0]["labels"]["a_r1"] == "base"
    with pytest.raises(v.VariantError):
        v.apply(tmp_path, "label", {"id": "v1", "member": "a_r1", "label": "x" * 13}, teams={}, names=NAMES)


def test_split_removes_the_set_and_dismiss_is_remembered(tmp_path):
    mk(tmp_path)
    assert v.apply(tmp_path, "rename", {"id": "v1", "name": "A"}, teams={}, names=NAMES)["sets"][0]["name"] == "A"
    assert v.apply(tmp_path, "split", {"id": "v1"}, teams={}, names=NAMES)["sets"] == []
    d = v.apply(tmp_path, "dismiss", {"members": ["b_flex", "b_fast"]}, teams={}, names=NAMES)
    assert d["dismissed"] == [["b_fast", "b_flex"]] and v.load(tmp_path)["dismissed"] == d["dismissed"]


def test_an_archived_member_shrinks_the_set_and_under_two_dissolves(tmp_path):
    mk(tmp_path, ("a_r1", "a_r2", "a_r15"))
    d = v.load(tmp_path, NAMES - {"a_r15"})
    assert d["sets"][0]["members"] == ["a_r1", "a_r2"] and "a_r15" not in d["sets"][0]["labels"]
    assert json.loads((tmp_path / "variants.json").read_text())["sets"][0]["members"] == ["a_r1", "a_r2"]
    before = (tmp_path / "variants.json").stat().st_mtime_ns
    v.load(tmp_path, NAMES)                                  # nothing changed: the file is not written
    assert (tmp_path / "variants.json").stat().st_mtime_ns == before
    assert v.load(tmp_path, {"a_r1"})["sets"] == []


def test_suggest():
    n = ["nq_cb_r1", "nq_cb_r15", "nq_cb_r2", "gc_x"]
    kw = dict(in_team=set(), sets=[], dismissed=[])
    want = [{"stem": "nq_cb", "members": ["nq_cb_r1", "nq_cb_r15", "nq_cb_r2"],
             "labels": {"nq_cb_r1": "1R", "nq_cb_r15": "1.5R", "nq_cb_r2": "2R"}}]
    assert v.suggest(n, **kw) == want
    assert v.suggest(n, **{**kw, "dismissed": [["nq_cb_r1", "nq_cb_r15", "nq_cb_r2"]]}) == []
    assert [s["members"] for s in v.suggest(n, **{**kw, "in_team": {"nq_cb_r2"}})] == [["nq_cb_r1", "nq_cb_r15"]]
    assert v.suggest(["x_r15_fast", "x_r2_fast"], **kw)[0]["labels"] == {"x_r15_fast": "1.5R fast", "x_r2_fast": "2R fast"}


def test_status_carries_the_sets_and_suggestions(desk):
    assert desk.get("/api/status").json()["variants"] == {"sets": [], "suggest": []}
    (desk.d.root / "variants.json").write_text(json.dumps(
        {"sets": [{"id": "v1", "name": "x", "members": [LAB, "lab_gone"], "labels": {}}], "dismissed": [], "next": 2}))
    assert desk.get("/api/status").json()["variants"]["sets"] == []          # left under 2: dissolved
    r = desk.post("/api/variants/create", json={"members": [LAB]})
    assert r.status_code == 400 and desk.post("/api/variants/nope", json={}).status_code == 400
