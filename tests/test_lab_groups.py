"""The Lab's strategy groups: one small JSON file beside the drafts (<drafts dir>/groups.json), its routes on
the chart service, and the pin that grouping never edits, moves or deletes a strategy file."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase import draftstore
from homebase.backtest import drafthost
from homebase.charts import lab_templates
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

OK = {"origin": "http://localhost:8852"}
EVIL = {"origin": "https://evil.example"}
NONE = {"groups": [], "members": {}}


def client(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    return TestClient(app, base_url="http://localhost:8852")


def on_disk(drafts_dir):
    return json.loads((drafts_dir / "groups.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the file

def test_no_file_means_no_groups_and_reading_never_makes_one(drafts_dir):
    assert draftstore.read_groups() == NONE
    assert list(drafts_dir.iterdir()) == []


def test_filing_a_strategy_writes_one_json_file_and_never_touches_a_strategy_file(drafts_dir):
    p = draftstore.write("nq_orb", draftstore.DRAFT_TEMPLATE)
    before = (p.read_bytes(), p.stat().st_mtime_ns)
    st = draftstore.set_group("draft_nq_orb", "Opening range")
    assert st == {"groups": ["Opening range"], "members": {"draft_nq_orb": "Opening range"}}
    assert on_disk(drafts_dir) == st == draftstore.read_groups()
    draftstore.set_group("nq930", "Opening range")                       # a built-in files the same way, by its id
    draftstore.rename_group("Opening range", "ORB")
    draftstore.remove_group("ORB")
    assert sorted(x.name for x in drafts_dir.iterdir()) == ["groups.json", "nq_orb.py"]   # no temp file left behind
    assert (p.read_bytes(), p.stat().st_mtime_ns) == before
    assert [n for n, _ in draftstore.list_files()] == ["nq_orb"]         # groups.json is never listed as a draft
    assert [s["id"] for s in drafthost.catalog()] == ["draft_nq_orb"]


def test_a_strategy_has_one_group_and_can_leave_it(drafts_dir):
    draftstore.set_group("draft_a", "Gold")
    st = draftstore.set_group("draft_a", "Nasdaq")
    assert st == {"groups": ["Gold", "Nasdaq"], "members": {"draft_a": "Nasdaq"}}   # moved; Gold stays, empty
    for nothing in (None, ""):
        draftstore.set_group("draft_a", "Gold")
        assert draftstore.set_group("draft_a", nothing) == {"groups": ["Gold", "Nasdaq"], "members": {}}
    assert draftstore.set_group("draft_never_filed", None)["members"] == {}


def test_filing_under_a_group_that_exists_reuses_it_whatever_its_capitals(drafts_dir):
    draftstore.add_group("Gold")
    assert draftstore.set_group("gc_nfp", "  gold ") == {"groups": ["Gold"], "members": {"gc_nfp": "Gold"}}


def test_create_rename_and_delete(drafts_dir):
    assert draftstore.add_group("Gold") == {"groups": ["Gold"], "members": {}}
    draftstore.add_group("Nasdaq")
    draftstore.set_group("gc_nfp", "Gold")
    draftstore.set_group("nq930", "Nasdaq")
    with pytest.raises(ValueError, match="already"):
        draftstore.add_group("gold")
    with pytest.raises(ValueError, match="already"):
        draftstore.rename_group("Gold", "NASDAQ")
    with pytest.raises(ValueError, match="no group"):
        draftstore.rename_group("Silver", "Metals")
    with pytest.raises(ValueError, match="no group"):
        draftstore.remove_group("Silver")
    # a rename keeps the group's place and its strategies; changing only its capitals is a rename too
    assert draftstore.rename_group("Gold", "Metals") == {"groups": ["Metals", "Nasdaq"],
                                                         "members": {"gc_nfp": "Metals", "nq930": "Nasdaq"}}
    assert draftstore.rename_group("metals", "METALS")["groups"] == ["METALS", "Nasdaq"]
    # deleting a group puts its strategies back in no group
    assert draftstore.remove_group("METALS") == {"groups": ["Nasdaq"], "members": {"nq930": "Nasdaq"}}
    assert on_disk(drafts_dir) == {"groups": ["Nasdaq"], "members": {"nq930": "Nasdaq"}}


@pytest.mark.parametrize("bad", ["", "   ", "x" * 41, "Ungrouped", " ungrouped ", "a\x00b", None, 3, ["Gold"]])
def test_bad_group_names_are_refused_before_anything_is_written(bad, drafts_dir):
    with pytest.raises(ValueError):
        draftstore.validate_group(bad)
    with pytest.raises(ValueError):
        draftstore.add_group(bad)
    with pytest.raises(ValueError):
        draftstore.rename_group("Gold", bad)
    assert list(drafts_dir.iterdir()) == []


def test_a_group_name_is_one_line_with_single_spaces():
    assert draftstore.validate_group("  Opening \n  range ") == "Opening range"
    assert draftstore.validate_group("x" * 40) == "x" * 40
    assert draftstore.validate_group("Oro · 08:30 — NFP/CPI") == "Oro · 08:30 — NFP/CPI"


@pytest.mark.parametrize("bad", ["", "../x", "a b", "x" * 81, None, 7])
def test_only_a_strategy_id_can_be_filed(bad, drafts_dir):
    with pytest.raises(ValueError, match="strategy"):
        draftstore.set_group(bad, "Gold")
    assert list(drafts_dir.iterdir()) == []


@pytest.mark.parametrize("text", ["{not json", "[]", '"Gold"', '{"groups": "Gold"}', '{"groups": [3]}',
                                  '{"members": ["nq930"]}', '{"members": {"nq930": 3}}'])
def test_a_file_that_does_not_read_is_refused_and_never_written_over(text, drafts_dir):
    p = drafts_dir / "groups.json"
    p.write_text(text)
    with pytest.raises(ValueError, match="groups.json"):
        draftstore.read_groups()
    for edit in (lambda: draftstore.add_group("Gold"), lambda: draftstore.set_group("nq930", "Gold"),
                 lambda: draftstore.set_group("nq930", None), lambda: draftstore.remove_group("Gold")):
        with pytest.raises(ValueError, match="groups.json"):
            edit()
    assert p.read_text() == text


def test_a_file_written_by_hand_reads_when_it_only_names_members(drafts_dir):
    (drafts_dir / "groups.json").write_text('{"members": {"nq930": "Live", "gc_nfp": "Live"}}')
    assert draftstore.read_groups() == {"groups": ["Live"], "members": {"nq930": "Live", "gc_nfp": "Live"}}


def test_the_write_is_a_temp_file_then_a_replace(drafts_dir, monkeypatch):
    draftstore.set_group("nq930", "Gold")
    was = (drafts_dir / "groups.json").read_text()
    moves, real = [], os.replace

    def failing(src, dst):
        moves.append((os.fspath(src), os.fspath(dst)))
        assert json.loads(Path(src).read_text(encoding="utf-8"))["members"] == {"nq930": "Nasdaq"}   # complete first
        raise OSError("disk full")

    monkeypatch.setattr(draftstore.os, "replace", failing)
    with pytest.raises(OSError):
        draftstore.set_group("nq930", "Nasdaq")
    assert (drafts_dir / "groups.json").read_text() == was               # the old file is whole
    (src, dst), = moves
    assert dst == str(drafts_dir / "groups.json") and os.path.dirname(src) == str(drafts_dir) and src != dst
    monkeypatch.setattr(draftstore.os, "replace", real)
    assert draftstore.set_group("nq930", "Nasdaq")["members"] == {"nq930": "Nasdaq"}


# ---------------------------------------------------------------- the routes

def test_the_routes_create_file_rename_and_delete(tmp_path, drafts_dir):
    with client(tmp_path) as c:
        assert c.get("/api/tester/groups").json() == NONE
        c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        src = drafts_dir / "nq_bars.py"
        before = (src.read_bytes(), src.stat().st_mtime_ns)

        r = c.post("/api/tester/groups", json={"name": "Opening range"}, headers=OK)
        assert r.status_code == 200 and r.json() == {"groups": ["Opening range"], "members": {}}
        r = c.post("/api/tester/groups", json={"name": "opening range"}, headers=OK)
        assert r.status_code == 400 and "already" in r.json()["detail"]
        assert c.post("/api/tester/groups", json={"name": "Ungrouped"}, headers=OK).status_code == 400

        # a draft and a built-in file the same way; a group that is new is made by the move
        r = c.post("/api/tester/groups/move", json={"strategy": "draft_nq_bars", "group": "Opening range"}, headers=OK)
        assert r.status_code == 200 and r.json()["members"] == {"draft_nq_bars": "Opening range"}
        r = c.post("/api/tester/groups/move", json={"strategy": "nq930", "group": "Nasdaq"}, headers=OK)
        assert r.json() == {"groups": ["Opening range", "Nasdaq"],
                            "members": {"draft_nq_bars": "Opening range", "nq930": "Nasdaq"}}
        assert c.get("/api/tester/groups").json() == r.json() == on_disk(drafts_dir)
        r = c.post("/api/tester/groups/move", json={"strategy": "draft_nope", "group": "Nasdaq"}, headers=OK)
        assert r.status_code == 404 and "draft_nope" in r.json()["detail"]
        assert c.post("/api/tester/groups/move", json={"strategy": "nq930", "group": "x" * 41}, headers=OK).status_code == 400

        r = c.post("/api/tester/groups/rename", json={"name": "Opening range", "to": "ORB"}, headers=OK)
        assert r.json() == {"groups": ["ORB", "Nasdaq"], "members": {"draft_nq_bars": "ORB", "nq930": "Nasdaq"}}
        assert c.post("/api/tester/groups/rename", json={"name": "ORB", "to": "nasdaq"}, headers=OK).status_code == 400
        assert c.post("/api/tester/groups/rename", json={"name": "Silver", "to": "Metals"}, headers=OK).status_code == 400

        for nothing in (None, ""):                                     # back to Ungrouped
            c.post("/api/tester/groups/move", json={"strategy": "nq930", "group": "Nasdaq"}, headers=OK)
            r = c.post("/api/tester/groups/move", json={"strategy": "nq930", "group": nothing}, headers=OK)
            assert r.status_code == 200 and r.json()["members"] == {"draft_nq_bars": "ORB"}

        # deleting a group deletes no strategy: it is still listed, still runnable, its file untouched
        r = c.post("/api/tester/groups/delete", json={"name": "ORB"}, headers=OK)
        assert r.json() == {"groups": ["Nasdaq"], "members": {}}
        assert c.post("/api/tester/groups/delete", json={"name": "ORB"}, headers=OK).status_code == 400
        assert [d["name"] for d in c.get("/api/tester/drafts").json()] == ["nq_bars"]
        assert "draft_nq_bars" in {s["id"] for s in c.get("/api/tester/strategies").json()}
        assert (src.read_bytes(), src.stat().st_mtime_ns) == before
        assert sorted(x.name for x in drafts_dir.iterdir()) == ["groups.json", "nq_bars.py"]


def test_the_group_writes_keep_the_origin_host_json_and_shape_guards(tmp_path, drafts_dir):
    writes = [("/api/tester/groups", {"name": "Gold"}), ("/api/tester/groups/rename", {"name": "Gold", "to": "Oro"}),
              ("/api/tester/groups/delete", {"name": "Gold"}),
              ("/api/tester/groups/move", {"strategy": "nq930", "group": "Gold"})]
    with client(tmp_path) as c:
        for path, body in writes:
            assert c.post(path, json=body, headers=EVIL).status_code == 403, path
            assert c.post(path, json=body, headers={**OK, "host": "evil.example"}).status_code == 403, path
            r = c.post(path, content=json.dumps(body), headers={**OK, "content-type": "text/plain"})
            assert r.status_code in (415, 422), path
            assert c.post(path, json={**body, "extra": 1}, headers=OK).status_code == 400, path
            assert c.post(path, json=[body], headers=OK).status_code in (400, 422), path
        assert c.get("/api/tester/groups", headers={"host": "evil.example"}).status_code == 403
        assert c.get("/api/tester/groups").json() == NONE
    assert list(drafts_dir.iterdir()) == []


def test_a_groups_file_that_does_not_read_is_a_409_and_stays_as_it_is(tmp_path, drafts_dir):
    (drafts_dir / "groups.json").write_text("{not json")
    with client(tmp_path) as c:
        r = c.get("/api/tester/groups")
        assert r.status_code == 409 and "groups.json" in r.json()["detail"]
        r = c.post("/api/tester/groups/move", json={"strategy": "nq930", "group": "Gold"}, headers=OK)
        assert r.status_code == 409 and "groups.json" in r.json()["detail"]
        assert c.post("/api/tester/groups", json={"name": "Gold"}, headers=OK).status_code == 409
        assert c.get("/api/tester/drafts").status_code == 200           # the list itself still loads
    assert (drafts_dir / "groups.json").read_text() == "{not json"


def test_grouping_changes_neither_the_catalog_nor_the_drafts_listing(tmp_path, drafts_dir):
    (drafts_dir / "nq_bars.py").write_text(lab_templates.BAR_BREAKOUT)
    with client(tmp_path) as c:
        catalog, drafts = c.get("/api/tester/strategies").content, c.get("/api/tester/drafts").content
        c.post("/api/tester/groups/move", json={"strategy": "draft_nq_bars", "group": "Opening range"}, headers=OK)
        assert c.get("/api/tester/strategies").content == catalog
        assert c.get("/api/tester/drafts").content == drafts
