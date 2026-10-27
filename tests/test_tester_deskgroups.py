"""Desk groups on the chart service: the store (deskgroups.py), its routes and the combined results. Saved files only: nothing
is run and nothing is booked. The runs are written by hand into the tester's runs folder, the store into a temp folder."""
import io
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
    assert deskgroups.apply("create", {"name": "Again"})[-1]["id"] == "g3", "a deleted group's id is never given again"
    deskgroups.apply("delete", {"id": "g3"})
    assert deskgroups.apply("create", {"name": "Once more"})[-1]["id"] == "g4", "not even the last one deleted"
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


def test_a_groups_results_are_its_members_3to1_walkforwards_put_together(c, tmp_path, monkeypatch):
    """Owner 2026-10-25: the group's curve is the 3:1 -- in-sample, out-of-sample and both together, three lines, as each
    strategy's card. Each member's walk-forward (deskresults.wf_state) is read; one not done is left out and named."""
    import datetime as dt
    from homebase.store import draftstore
    from tests.test_tester_desklab import CODE, at_et, wf_result, write_wf
    seen = []

    def fake(trades, req):
        seen.append(len(trades))
        return {"rules": {"label": "LucidPro 50K"}, "headline": {"eval_pass_p": 0.4, "bust_p": 0.6, "median_days_to_pass": 5,
                                                              "funded_payout_p": 0.3, "funded_expected_cheque": 500.0}, "breach": {}}, False
    monkeypatch.setattr(tester_api, "_run_propsim", fake)
    at_et(monkeypatch, 2026, 10, 25, 12, 0)
    for n in ("nq_a", "nq_b", "nq_c"):                                  # the settings the walk-forward resolves (the code's own)
        store.put({**_record(n, f"20261001-100000-draft_{n}-aa"), "params": {"lookback": 6, "sl_pts": 20.0, "tp_pts": 40.0}})
    for n in ("nq_a", "nq_b"):                                           # nq_c: no walk-forward
        (draftstore.drafts_dir() / f"{n}.py").write_text(CODE.replace("nq_bars", n))
        rec = store.get(n)
        write_wf(tmp_path, rec, dt.date(2026, 10, 25), result=wf_result(), sha256=rec["sha256"])
    post(c, "create", {"name": "Eval group", "kind": "eval"})
    for sid in ("lab_nq_a", "lab_nq_b", "lab_nq_c", "nq930"):
        post(c, "move", {"strategy": sid, "group": "g1"})
    post(c, "create", {"name": "Empty"})
    got = c.get("/api/tester/deskgroups/results", headers=DESK).json()["results"]
    g = got["g1"]
    assert (g["name"], g["kind"], g["walkforward"]) == ("Eval group", "eval", True)
    assert [m["state"] for m in g["members"]] == ["done", "done", "changed"]     # nq_c has no Lab draft (S4: still said with the start off)
    assert g["members"][0]["unseen"]["net"] == 1234.5 and g["members"][0]["build"]["net"] == 4000.0 and g["members"][2]["unseen"] is None
    assert [x["strategy"] for x in g["left_out"]] == ["lab_nq_c", "nq930"]
    assert g["in"] == {k: ["lab_nq_a", "lab_nq_b"] for k in ("build", "unseen", "both")}
    assert (g["unseen"]["net"], g["unseen"]["trades"]) == (400.0, 4)              # 2 members x (300 - 100)
    assert g["unseen"]["curve"] == {"days": ["2022-04-04", "2022-04-05"], "vals": [600.0, 400.0]}
    assert (g["build"]["net"], g["build"]["trades"]) == (100.0, 2)                # 2 members x 50
    assert (g["both"]["net"], g["both"]["trades"]) == (500.0, 6)
    assert g["both"]["curve"] == {"days": ["2022-01-03", "2022-04-04", "2022-04-05"], "vals": [100.0, 700.0, 500.0]}
    assert g["prop"]["unseen"]["account"] == "LucidPro 50K"
    assert sorted(seen) == [2, 4, 6], "each side is scored once, as one account's trades"
    empty = got["g2"]
    assert empty["members"] == [] and empty["unseen"] is None and empty["both"] is None


def test_a_member_with_an_older_3to1_says_which_months_it_lacks(c, tmp_path, monkeypatch):
    """S4: nothing starts a 3:1 by itself, so a member may only have last month's. Its row carries through/to (the page says
    which months are missing and that the sum mixes months); a member up to date carries neither. Nothing is submitted."""
    import datetime as dt
    from homebase import draftstore
    from homebase.backtest.walkforward import WalkForwardManager
    from tests.test_tester_desklab import CODE, at_et, wf_result, write_wf
    calls = []
    monkeypatch.setattr(WalkForwardManager, "submit", lambda self, body: calls.append(body))
    monkeypatch.setattr(tester_api, "_run_propsim", lambda trades, req: ({"rules": {"label": "LucidPro 50K"}, "headline": {}, "breach": {}}, False))
    at_et(monkeypatch, 2026, 10, 25, 12, 0)                              # the last whole month is September
    for n, asked in (("nq_a", dt.date(2026, 10, 25)), ("nq_b", dt.date(2026, 9, 18))):      # nq_b's walk-forward ends in August
        store.put({**_record(n, f"20261001-100000-draft_{n}-aa"), "params": {"lookback": 6, "sl_pts": 20.0, "tp_pts": 40.0}})
        (draftstore.drafts_dir() / f"{n}.py").write_text(CODE.replace("nq_bars", n))
        rec = store.get(n)
        write_wf(tmp_path, rec, asked, result=wf_result(), sha256=rec["sha256"])
    post(c, "create", {"name": "Eval group", "kind": "eval"})
    for sid in ("lab_nq_a", "lab_nq_b"):
        post(c, "move", {"strategy": sid, "group": "g1"})
    g = c.get("/api/tester/deskgroups/results", headers=DESK).json()["results"]["g1"]
    a, b = g["members"]
    assert (a["state"], b["state"]) == ("done", "done") and g["left_out"] == []
    assert "through" not in a and "to" not in a
    assert (b["through"], b["to"]) == ("2026-08", "2026-09")
    assert g["in"]["unseen"] == ["lab_nq_a", "lab_nq_b"], "still counted: the page says the months differ"
    assert calls == []



class _Answer:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _desk(monkeypatch, answer):
    """The Desk the charts service asks to make a group's account cycle follow: `answer(path, body)` -> a status, or an
    exception to raise (no answer). -> the calls it got."""
    import urllib.error
    calls = []

    def urlopen(req, timeout=None):
        path, body = req.full_url.split(":8850", 1)[1], json.loads(req.data)
        calls.append((path, body))
        got = answer(path, body)
        if isinstance(got, Exception):
            raise got
        if got != 200:
            raise urllib.error.HTTPError(req.full_url, got, "x", {}, io.BytesIO(b'{"detail": "refused here"}'))
        return _Answer(got)
    monkeypatch.setattr(tester_api.urllib.request, "urlopen", urlopen)
    return calls


def test_a_group_change_makes_its_account_cycle_follow_first(c, monkeypatch):
    post(c, "create", {"name": "Apex"})
    post(c, "create", {"name": "Other"})
    post(c, "move", {"strategy": "lab_nq_b", "group": "g2"})
    calls = _desk(monkeypatch, lambda path, body: 200)
    assert post(c, "move", {"strategy": "lab_nq_a", "group": "g1"}).json()["ok"] is True
    assert calls == [("/api/groups/follow", {"id": "g1", "name": "Apex", "members": ["lab_nq_a"]})]
    calls.clear()
    post(c, "move", {"strategy": "lab_nq_b", "group": "g1"})                  # out of g2, into g1: both follow
    assert [b["id"] for _, b in calls] == ["g1", "g2"]
    calls.clear()
    post(c, "rename", {"id": "g1", "name": "Apex 300k"})
    assert calls == [("/api/groups/follow", {"id": "g1", "name": "Apex 300k", "members": ["lab_nq_a", "lab_nq_b"]})]
    calls.clear()
    assert post(c, "delete", {"id": "g1"}).json()["ok"] is True
    assert calls == [("/api/groups/delete", {"id": "g1"})]


def test_a_group_without_a_cycle_changes_freely(c, monkeypatch):
    _desk(monkeypatch, lambda path, body: 404)                              # the Desk: no cycle for this group
    post(c, "create", {"name": "Apex"})
    assert post(c, "move", {"strategy": "lab_nq_a", "group": "g1"}).json()["ok"] is True
    assert post(c, "delete", {"id": "g1"}).json()["ok"] is True


def test_no_answer_from_the_desk_changes_nothing(c, monkeypatch):
    post(c, "create", {"name": "Apex"})
    post(c, "move", {"strategy": "lab_nq_a", "group": "g1"})
    _desk(monkeypatch, lambda path, body: OSError("refused"))
    r = post(c, "delete", {"id": "g1"})
    assert r.json()["ok"] is False and "did not answer" in r.json()["detail"]
    assert [g["id"] for g in deskgroups.load()] == ["g1"], "the group stays: its cycle could not follow"
    r = post(c, "move", {"strategy": "lab_nq_a", "group": None})
    assert r.json()["ok"] is False and deskgroups.load()[0]["members"] == ["lab_nq_a"]
    _desk(monkeypatch, lambda path, body: 400)
    r = post(c, "move", {"strategy": "lab_nq_a", "group": None})
    assert r.json()["ok"] is False and "refused here" in r.json()["detail"]
