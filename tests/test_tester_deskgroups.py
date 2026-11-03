"""Teams on the chart service: a read-only view of the Desk's own team file (<state>/groups.json, engine_groups.py), its
routes and the combined results. Saved files only: nothing is run and nothing is booked. The runs are written by hand into the
tester's runs folder, the team file into a temp folder."""
import json

import pytest
from fastapi.testclient import TestClient

from homebase import paths
from homebase.charts import deskgroups, tester_api
from homebase.labrun import store
from tests.test_tester_api import EVIL, app

DESK = {"origin": "http://localhost:8850"}


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path / "state")
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def teams(tmp_path, groups: dict):
    """The Desk's team file, as engine_groups writes it: {id: {name, members, accounts, ...}}."""
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "groups.json").write_text(json.dumps(groups))


def test_load_reads_the_desks_team_file(tmp_path):
    assert deskgroups.load(tmp_path) == []
    (tmp_path / "groups.json").write_text("not json")
    assert deskgroups.load(tmp_path) == []
    (tmp_path / "groups.json").write_text("{}")
    assert deskgroups.load(tmp_path) == []
    (tmp_path / "groups.json").write_text(json.dumps({
        "g1": {"name": "Apex", "members": ["lab_nq_a", 5, "Bad!"], "accounts": ["a1"], "on": True, "mode": "cycle"},
        "g2": "junk", "g3": {"members": []}}))
    assert deskgroups.load(tmp_path) == [{"id": "g1", "name": "Apex", "members": ["lab_nq_a"]},
                                         {"id": "g3", "name": "g3", "members": []}]


def test_the_routes_answer_the_desk_page_only_and_list_the_desks_teams(c, tmp_path):
    assert c.get("/api/tester/deskgroups", headers=EVIL).status_code == 403
    assert c.get("/api/tester/deskgroups", headers=DESK).json() == {"groups": []}
    teams(tmp_path, {"g1": {"name": "Apex", "members": ["lab_nq_a"], "accounts": [], "on": False}})
    assert c.get("/api/tester/deskgroups", headers=DESK).json() == {"groups": [{"id": "g1", "name": "Apex", "members": ["lab_nq_a"]}]}


def test_dead_team_routes_are_gone(c):
    assert c.post("/api/tester/deskgroups/create", json={"name": "x"}, headers=DESK).status_code in (404, 405)
    assert c.options("/api/tester/deskgroups/create", headers=DESK).status_code in (404, 405)


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
    assert (s["rr"], s["rr_label"], s["sharpe"]) == (None, None, None), "rows without commission/seconds/bars: no RR or Sharpe, the rest stays"


def test_summarize_reads_rr_and_sharpe_off_the_report():
    # 2 wins of 1000 + 1 loss of 500 over three traded days: payoff 2.0, Sharpe = mean/sd of the day nets x sqrt(252), no padding
    rows = [{"date": f"2025-07-0{i}", "net": n, "entry_ms": i * 100, "exit_ms": i * 100 + 50, "commission": 4.0, "seconds": 60, "bars": 3,
             "side": "long", "qty": 1, "mfe_usd": 0.0, "mae_usd": 0.0}
            for i, n in ((1, 1000.0), (2, -500.0), (3, 1000.0))]
    s = deskgroups.summarize(rows)
    assert s["rr"] == 2.0 and s["rr_label"] == "1:2.00"
    mean, sd = 500.0, (((500) ** 2 + (1000) ** 2 + (500) ** 2) / 2) ** 0.5
    assert abs(s["sharpe"] - mean / sd * 252 ** 0.5) < 1e-6


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
    teams(tmp_path, {"g1": {"name": "Eval group", "members": ["lab_nq_a", "lab_nq_b", "lab_nq_c", "nq930"]},
                     "g2": {"name": "Empty", "members": []}})
    got = c.get("/api/tester/deskgroups/results", headers=DESK).json()["results"]
    g = got["g1"]
    assert (g["name"], g["walkforward"]) == ("Eval group", True)
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
    teams(tmp_path, {"g1": {"name": "Eval group", "members": ["lab_nq_a", "lab_nq_b"]}})
    g = c.get("/api/tester/deskgroups/results", headers=DESK).json()["results"]["g1"]
    a, b = g["members"]
    assert (a["state"], b["state"]) == ("done", "done") and g["left_out"] == []
    assert "through" not in a and "to" not in a
    assert (b["through"], b["to"]) == ("2026-08", "2026-09")
    assert g["in"]["unseen"] == ["lab_nq_a", "lab_nq_b"], "still counted: the page says the months differ"
    assert calls == []
