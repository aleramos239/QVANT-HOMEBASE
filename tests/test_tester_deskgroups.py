"""Desk groups on the chart service: the store (deskgroups.py), its routes and the combined results. Saved files only: nothing
is run and nothing is booked. The runs are written by hand into the tester's runs folder, the store into a temp folder."""
import json

import pytest
from fastapi.testclient import TestClient

from homebase.charts import deskgroups, tester_api
from homebase.labrun import store
from tests.test_tester_api import EVIL, app

DESK = {"origin": "http://localhost:8850"}


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def post(c, what, body, **kw):
    return c.post(f"/api/tester/deskgroups/{what}", json=body, headers=DESK, **kw)


def test_the_store_creates_renames_moves_and_deletes_with_one_group_per_strategy(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    assert deskgroups.load() == []
    a = deskgroups.apply("create", {"name": "  Eval   group ", "kind": "eval"})
    assert a == [{"id": "g1", "name": "Eval group", "kind": "eval", "members": []}]
    deskgroups.apply("create", {"name": "Funded", "kind": "funded"})
    deskgroups.apply("move", {"strategy": "lab_nq_a", "group": "g1"})
    deskgroups.apply("move", {"strategy": "nq930", "group": "g1"})
    g = deskgroups.apply("move", {"strategy": "lab_nq_a", "group": "g2"})
    assert [(x["id"], x["members"]) for x in g] == [("g1", ["nq930"]), ("g2", ["lab_nq_a"])], "one group at most: moving takes it out of the first"
    g = deskgroups.apply("move", {"strategy": "lab_nq_a", "group": None})
    assert [x["members"] for x in g] == [["nq930"], []]
    deskgroups.apply("rename", {"id": "g2", "name": "Funded group"})
    deskgroups.apply("kind", {"id": "g2", "kind": "together"})
    assert [(x["name"], x["kind"]) for x in deskgroups.load()] == [("Eval group", "eval"), ("Funded group", "together")]
    g = deskgroups.apply("delete", {"id": "g1"})
    assert [x["id"] for x in g] == ["g2"]
    assert deskgroups.apply("create", {"name": "Again"})[-1]["id"] == "g1", "a free id is reused"
    assert deskgroups.path() == tmp_path / "deskgroups.json", "beside the records' folder, never inside it (it lists *.json)"
    assert store.listing() == []


@pytest.mark.parametrize("action,body,said", [
    ("create", {"name": ""}, "1 to 40 characters"),
    ("create", {"name": "x" * 41}, "1 to 40 characters"),
    ("create", {"name": "Fine", "kind": "live"}, "eval, a funded account"),
    ("create", {"name": "EVAL group"}, "with that name already"),
    ("rename", {"id": "gone", "name": "x"}, "not there any more"),
    ("rename", {"id": "g1", "name": "eval group"}, None),            # its own name in another case is fine
    ("move", {"strategy": "Bad Name", "group": "g1"}, "not a strategy"),
    ("move", {"strategy": "nq930", "group": "gone"}, "not there any more"),
    ("delete", {"id": "gone"}, "not there any more"),
    ("nope", {}, "unknown"),
])
def test_the_store_refuses_in_words_and_writes_nothing(tmp_path, monkeypatch, action, body, said):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    deskgroups.apply("create", {"name": "Eval group", "kind": "eval"})
    before = deskgroups.path().read_text()
    if said is None:
        assert deskgroups.apply(action, body)[0]["name"] == "eval group"
        return
    with pytest.raises(deskgroups.GroupError, match=said):
        deskgroups.apply(action, body)
    assert deskgroups.path().read_text() == before


def test_the_store_caps_the_number_of_groups_and_survives_a_bad_file(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    for i in range(deskgroups.MAX_GROUPS):
        deskgroups.apply("create", {"name": f"G {i}"})
    with pytest.raises(deskgroups.GroupError, match="12 groups"):
        deskgroups.apply("create", {"name": "One more"})
    deskgroups.path().write_text("not json")
    assert deskgroups.load() == []
    deskgroups.path().write_text(json.dumps({"groups": [{"id": "g1", "name": "A", "kind": "weird", "members": ["ok_1", "Bad!", 5, "ok_1"]},
                                                        "junk", {"id": "g1", "name": "dup"}]}))
    assert deskgroups.load() == [{"id": "g1", "name": "A", "kind": "together", "members": ["ok_1"]}]


def test_the_routes_answer_the_desk_page_only_and_say_a_refusal_in_words(c):
    assert c.get("/api/tester/deskgroups", headers=EVIL).status_code == 403
    assert c.get("/api/tester/deskgroups", headers=DESK).json() == {"groups": []}
    assert c.options("/api/tester/deskgroups/create", headers={"origin": "http://evil.example"}).status_code == 403
    pre = c.options("/api/tester/deskgroups/create", headers=DESK)
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == DESK["origin"]
    assert post(c, "create", {"name": "Eval", "kind": "eval"}, ).json()["groups"][0]["id"] == "g1"
    assert c.post("/api/tester/deskgroups/create", json={"name": "x"}, headers=EVIL).status_code == 403
    r = post(c, "create", {"name": "eval"})
    assert r.status_code == 409 and r.json() == {"ok": False, "detail": "There is a group with that name already."}
    assert post(c, "move", {"strategy": "lab_nq_a", "group": "g1"}).json()["groups"][0]["members"] == ["lab_nq_a"]
    assert post(c, "wat", {}).status_code in (404, 403)
    assert c.get("/api/tester/deskgroups", headers=DESK).json()["groups"][0]["members"] == ["lab_nq_a"]


def test_summarize_and_merged(tmp_path):
    a = [{"date": "2025-07-01", "net": 1000.0, "entry_ms": 1, "exit_ms": 10}, {"date": "2025-07-02", "net": -400.0, "entry_ms": 20, "exit_ms": 30}]
    b = [{"date": "2025-07-01", "net": -200.0, "entry_ms": 2, "exit_ms": 5}, {"date": "2025-07-03", "net": 600.0, "entry_ms": 40, "exit_ms": 50},
         {"date": "x", "net": "bad"}]
    ledger, owners = deskgroups.merged([("A", a), ("B", b)])
    assert owners == ["B", "A", "A", "B"] and [t["net"] for t in ledger] == [-200.0, 1000.0, -400.0, 600.0]
    s = deskgroups.summarize(ledger, owners)
    assert (s["net"], s["trades"], s["win_rate"], s["days"]) == (1000.0, 4, 50.0, 3)
    assert s["profit_factor"] == round(1600 / 600, 3) and s["max_drawdown"] == -400.0 and s["worst_day"] == -400.0 and s["best_day"] == 800.0
    assert s["together_days"] == 1, "2025-07-01 had both members"
    assert s["curve"] == {"days": ["2025-07-01", "2025-07-02", "2025-07-03"], "vals": [800.0, 400.0, 1000.0]}
    assert deskgroups.summarize([]) is None
    assert deskgroups.summarize(ledger)["together_days"] is None


def _record(name, build_id):
    return {"name": name, "id": f"draft_{name}", "label": name.upper(), "root": "NQ", "source": "", "sha256": f"sha-{name}",
            "params": {}, "qty": 1, "run": {"id": build_id, "net": 500.0, "trades": 2, "win_rate": 50.0, "profit_factor": 1.5,
                                            "max_drawdown": -100.0},
            "notes": [], "enabled": False, "promoted_utc": "2026-10-11T12:00:00+00:00", "commission": 4.0, "slippage_ticks": 1.0,
            "session_window": ["09:25", "16:00"], "bar_minutes": 1}


def _run(tmp_path, rid, name, trades, holdout):
    d = tmp_path / "state" / "tester" / "runs" / rid
    d.mkdir(parents=True)
    rng = ({"kind": "custom", "start": "2025-07-01", "end": "2026-10-11", "holdout": True} if holdout
           else {"kind": "research", "start": "2021-09-22", "end": "2025-06-30", "holdout": False})
    (d / "request.json").write_text(json.dumps({"strategy": f"draft_{name}", "draft_sha256": f"sha-{name}", "inputs": {}, "qty": 1, "range": rng}))
    (d / "status.json").write_text(json.dumps({"id": rid, "status": "done"}))
    net = sum(t["net"] for t in trades)
    (d / "run.json").write_text(json.dumps({"id": rid, "range": rng, "inputs": {}, "qty": 1, "report": {"summary": {"all": {
        "net_profit": net, "trades": len(trades), "win_rate": 50.0, "profit_factor": 1.2, "max_drawdown": -300.0}}}}))
    (d / "trades.json").write_text(json.dumps(trades))


def test_a_groups_results_put_its_members_saved_runs_together(c, tmp_path, monkeypatch):
    seen = []

    def fake(trades, req):
        seen.append([t["net"] for t in trades])
        return {"rules": {"label": "LucidPro 50K"}, "headline": {"eval_pass_p": 0.4, "bust_p": 0.6, "median_days_to_pass": 5,
                                                              "funded_payout_p": 0.3, "funded_expected_cheque": 500.0}, "breach": {}}, False
    monkeypatch.setattr(tester_api, "_run_propsim", fake)
    for n in ("nq_a", "nq_b", "nq_c"):
        store.put(_record(n, f"20261001-100000-draft_{n}-aa"))
    _run(tmp_path, "20261001-100000-draft_nq_a-aa", "nq_a", [{"date": "2024-01-02", "net": 300.0, "entry_ms": 1, "exit_ms": 2}], False)
    _run(tmp_path, "20261001-100000-draft_nq_b-aa", "nq_b", [{"date": "2024-01-02", "net": -100.0, "entry_ms": 3, "exit_ms": 4}], False)
    _run(tmp_path, "20261011-110000-draft_nq_a-bb", "nq_a", [{"date": "2025-07-01", "net": 1000.0, "entry_ms": 10, "exit_ms": 20},
                                                             {"date": "2025-07-02", "net": -300.0, "entry_ms": 30, "exit_ms": 40}], True)
    _run(tmp_path, "20261011-110001-draft_nq_b-bb", "nq_b", [{"date": "2025-07-01", "net": -200.0, "entry_ms": 12, "exit_ms": 18}], True)
    post(c, "create", {"name": "Eval group", "kind": "eval"})
    for sid in ("lab_nq_a", "lab_nq_b", "lab_nq_c", "nq930"):          # nq_c has no unseen run, nq930 is built in
        post(c, "move", {"strategy": sid, "group": "g1"})
    post(c, "create", {"name": "Empty"})
    got = c.get("/api/tester/deskgroups/results", headers=DESK).json()["results"]
    g = got["g1"]
    assert (g["name"], g["kind"]) == ("Eval group", "eval")
    assert [m["strategy"] for m in g["members"]] == ["lab_nq_a", "lab_nq_b", "lab_nq_c"]
    assert [m["state"] for m in g["members"]] == ["done", "done", "none"]
    assert g["members"][0]["unseen"]["net"] == 700.0 and g["members"][2]["unseen"] is None
    assert [x["strategy"] for x in g["left_out"]] == ["lab_nq_c", "nq930"]
    assert g["in"] == {"build": ["lab_nq_a", "lab_nq_b", "lab_nq_c"][:2], "unseen": ["lab_nq_a", "lab_nq_b"]}
    u = g["unseen"]
    assert (u["net"], u["trades"], u["together_days"]) == (500.0, 3, 1)
    assert u["curve"] == {"days": ["2025-07-01", "2025-07-02"], "vals": [800.0, 500.0]}
    assert g["build"]["net"] == 200.0 and g["build"]["trades"] == 2
    assert g["prop"]["unseen"]["account"] == "LucidPro 50K" and g["prop"]["unseen"]["eval_pass_p"] == 0.4
    assert sorted(map(sorted, seen)) == [[-300.0, -200.0, 1000.0], [-100.0, 300.0]], "each side is scored once, as one account's trades"
    empty = got["g2"]
    assert empty["members"] == [] and empty["unseen"] is None and empty["build"] is None and empty["prop"] == {"build": None, "unseen": None}
    assert c.get("/api/tester/deskgroups/results", headers=EVIL).status_code == 403
