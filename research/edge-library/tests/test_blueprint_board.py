"""The idea board (the Lab's list of every saved idea): `bp.py status` gives each 3:1 idea a `wf` = {stage, box} that the page's
buttons read -- card (no card yet) | table (the in-sample table is next) | pick | test | done | used (the read stopped). Nothing is
run: what is on file is faked, the way the stage is read off it is the code under test."""
from __future__ import annotations

import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(W / "engine")]
from blueprint import api  # noqa: E402
from blueprint import hmwf as H  # noqa: E402
from blueprint import records as REC  # noqa: E402

IDEA = {"name": "nq_x", "status": "idea"}


def stage(monkeypatch, tmp_path, *, route=True, table=True, wf=None, last=None, card=True, status="idea"):
    d = tmp_path / "nq_x"
    d.mkdir(exist_ok=True)
    if card:
        (d / "spec.json").write_text("{}")
    IS = api.ideastore()
    monkeypatch.setattr(IS, "idea_dir", lambda name, root=None: d)
    monkeypatch.setattr(H, "route", lambda name, root=None: route)
    monkeypatch.setattr(api, "wf_on_file", lambda name: table)
    monkeypatch.setattr(REC, "_wf", lambda name, root=None: wf)
    monkeypatch.setattr(REC, "_last", lambda name, root: last)
    return REC._wf_stage("nq_x", {**IDEA, "status": status}, None)


def test_a_new_idea_waits_for_its_card_then_for_the_table(monkeypatch, tmp_path):
    assert stage(monkeypatch, tmp_path, table=False, card=False) == {"stage": "card"}
    assert stage(monkeypatch, tmp_path, table=False) == {"stage": "table"}


def test_a_table_waits_for_the_pick_then_the_test_months_then_is_done(monkeypatch, tmp_path):
    assert stage(monkeypatch, tmp_path, wf={"lock": None, "oos": None}) == {"stage": "pick", "box": None}
    assert stage(monkeypatch, tmp_path, wf={"lock": {"box": "k1_own1-r1"}, "oos": None}) == {"stage": "test", "box": "k1_own1-r1"}
    assert stage(monkeypatch, tmp_path, wf={"lock": {"box": "b"}, "oos": {"record": {}}}) == {"stage": "done", "box": "b"}
    assert stage(monkeypatch, tmp_path, wf={"lock": {"box": "b"}, "oos": {"state": H.USED}}) == {"stage": "used", "box": "b"}
    assert stage(monkeypatch, tmp_path, wf={"error": "the store is not readable"}) == {"stage": "error"}


def test_an_idea_off_the_3_to_1_route_has_no_stage(monkeypatch, tmp_path):
    assert stage(monkeypatch, tmp_path, route=False) == {}
    assert stage(monkeypatch, tmp_path, last=(1, [], None)) == {}      # built on the old split
    assert stage(monkeypatch, tmp_path, status="shelved") == {}
