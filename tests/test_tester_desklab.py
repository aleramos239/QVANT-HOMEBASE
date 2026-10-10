"""Promote to Desk, on the chart service: the store of promoted Lab strategies and its four routes. Text and files only --
no draft runs, no order goes anywhere. The runs are written by hand into the tester's runs folder, the drafts into the
conftest's temp drafts folder, the store into a temp folder through HOMEBASE_DESKLAB_ROOT."""
import datetime as dt
import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase import draftstore
from homebase.backtest import sandbox, slots
from homebase.charts import lab_templates, tester_api
from homebase.labrun import door, store
from tests.test_tester_api import EVIL, app

DESK = {"origin": "http://localhost:8850"}
CODE = lab_templates.BAR_BREAKOUT
RANGE = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}
SUMMARY = {"net_profit": 1234.5, "trades": 41, "win_rate": 48.8, "profit_factor": 1.31, "max_drawdown": -2100.0}
LAB = "That strategy is not in the Lab."
RUN_FIRST = "Run a backtest of this strategy first."
CHANGED = "The code changed since this backtest. Run it again, then promote."
CARRY = "It must not carry anything from one day to the next (set session_independent = True)."
NO_SANDBOX = "The sandbox is not working, so it cannot run."


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    monkeypatch.setattr(sandbox, "available", lambda: True)
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


@pytest.fixture
def make_run(tmp_path):
    """A run folder as the tester leaves it: request.json, status.json, run.json."""
    seq = iter(range(1, 100))

    def make(code=CODE, name="nq_bars", status="done", strategy=None, sha256=None, inputs=None):
        rid = f"20261009-12000{next(seq)}-draft_{name}-ab12"
        d = tmp_path / "state" / "tester" / "runs" / rid
        d.mkdir(parents=True)
        (d / "request.json").write_text(json.dumps({"strategy": strategy or f"draft_{name}", "id": rid,
                                                    "draft_sha256": sha256 or sha(code)}))
        (d / "status.json").write_text(json.dumps({"id": rid, "status": status}))
        if status == "done":
            (d / "run.json").write_text(json.dumps({"id": rid, "inputs": inputs or {"lookback": 8, "sl_pts": 20.0, "tp_pts": 40.0},
                                                    "qty": 2, "range": RANGE, "report": {"summary": {"all": SUMMARY}}}))
        return rid
    return make


def draft(drafts_dir, code=CODE, name="nq_bars"):
    (drafts_dir / f"{name}.py").write_text(code)


def promote(c, name="nq_bars", run_id="x", **kw):
    return c.post("/api/tester/desklab/promote", json={"name": name, "run_id": run_id}, **kw)


def sentence(r, status=None):
    assert r.json()["ok"] is False, r.text
    if status:
        assert r.status_code == status
    return r.json()["detail"]


def test_each_refusal_says_its_sentence_in_order(c, drafts_dir, make_run, monkeypatch):
    # 1 no such draft (even with the sandbox down and a run that would fail every later line)
    monkeypatch.setattr(sandbox, "available", lambda: False)
    assert sentence(promote(c, run_id="nope"), 404) == LAB
    draft(drafts_dir)
    # 2 the run is unknown / not finished / of another strategy
    assert sentence(promote(c, run_id="20261009-120000-draft_nq_bars-ab12"), 409) == RUN_FIRST
    assert sentence(promote(c, run_id=make_run(status="running"))) == RUN_FIRST
    assert sentence(promote(c, run_id=make_run(strategy="draft_other"))) == RUN_FIRST
    assert sentence(promote(c, run_id=make_run(strategy="nq930"))) == RUN_FIRST
    # 3 made from other code
    assert sentence(promote(c, run_id=make_run(code=CODE + "# older\n"))) == CHANGED
    good = make_run()
    # 4 the text cannot be read statically
    draft(drafts_dir, "x = 1\n", "nq_two")
    msg = sentence(promote(c, "nq_two", make_run("x = 1\n", "nq_two")))
    assert "exactly one class" in msg
    # 5 it carries from one day to the next (or does not say)
    for code in (CODE.replace("session_independent = True", "session_independent = False"),
                 CODE.replace("    session_independent = True\n", "")):
        draft(drafts_dir, code, "nq_carry")
        assert sentence(promote(c, "nq_carry", make_run(code, "nq_carry"))) == CARRY
    # 6 a market this service does not stream
    other = CODE.replace('root = "NQ"', 'root = "CL"')
    draft(drafts_dir, other, "cl_bars")
    assert sentence(promote(c, "cl_bars", make_run(other, "cl_bars"))) == "No live prices for CL here."
    # 7 the sandbox is last
    r = promote(c, run_id=good)
    assert sentence(r) == NO_SANDBOX
    assert c.get("/api/tester/desklab").json()["strategies"] == []              # nothing was written by any refusal


def test_a_good_promote_writes_the_record_and_the_page_reads_it_without_the_code(c, drafts_dir, make_run, tmp_path):
    code = CODE.replace("ctx.market(\"long\", sl=bar.c - sl, tp=bar.c + tp)", "ctx.market(\"long\")")
    draft(drafts_dir, code)
    rid = make_run(code)
    r = promote(c, run_id=rid, headers=DESK)
    assert r.status_code == 200 and r.json() == {"ok": True, "name": "nq_bars", "notes": door.read_source(code)}
    assert r.json()["notes"] == ["1 order can go out with no stop."]
    assert r.headers["access-control-allow-origin"] == "http://localhost:8850"
    rec = json.loads((tmp_path / "desklab" / "nq_bars.json").read_text())
    assert rec["source"] == code and rec["sha256"] == sha(code) and rec["id"] == "draft_nq_bars" and rec["enabled"] is False
    assert rec["params"] == {"lookback": 8, "sl_pts": 20.0, "tp_pts": 40.0} and rec["qty"] == 2 and rec["root"] == "NQ"
    assert rec["label"] == "Bar breakout" and rec["notes"] == r.json()["notes"] and rec["promoted_utc"]
    assert rec["run"] == {"id": rid, "range": RANGE, "net": 1234.5, "trades": 41, "win_rate": 48.8, "profit_factor": 1.31,
                          "max_drawdown": -2100.0}
    got = c.get("/api/tester/desklab", headers=DESK)
    assert got.status_code == 200 and got.headers["access-control-allow-origin"] == "http://localhost:8850"
    (s,) = got.json()["strategies"]
    assert "source" not in s and s["sha256"] == sha(code) and s["params"]["lookback"] == 8 and s["notes"] == rec["notes"]
    assert rec["session_window"] == s["session_window"] == ["09:30", "11:30"] and rec["bar_minutes"] == s["bar_minutes"] == 5
    assert s["today"] is None and s["days"] == [] and s["enabled"] is False     # on the Desk, switched off


def test_promoting_again_a_strategy_that_was_on_lands_off(c, drafts_dir, make_run):
    draft(drafts_dir)
    assert promote(c, run_id=make_run()).status_code == 200
    assert c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": True}).json()["enabled"] is True
    newer = CODE.replace("Bar breakout", "Bar breakout two")
    draft(drafts_dir, newer)
    assert promote(c, run_id=make_run(newer)).status_code == 200
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["label"] == "Bar breakout two" and s["enabled"] is False           # new code starts off


def test_promoting_again_replaces_the_record_and_keeps_the_history(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    assert promote(c, run_id=make_run()).status_code == 200
    store.put_day("nq_bars", {"date": "2026-09-25", "state": "done"}, tmp_path / "desklab")
    store.journal("nq_bars", {"n": 1}, tmp_path / "desklab")
    newer = CODE.replace("Bar breakout", "Bar breakout two")
    draft(drafts_dir, newer)
    assert promote(c, run_id=make_run(newer, inputs={"lookback": 3})).status_code == 200
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["sha256"] == sha(newer) and s["label"] == "Bar breakout two" and s["params"] == {"lookback": 3}
    assert [d["date"] for d in s["days"]] == ["2026-09-25"]
    assert (tmp_path / "desklab" / "nq_bars" / "journal.jsonl").is_file()


def test_the_list_shows_today_the_days_and_whether_the_runner_is_alive(c, drafts_dir, make_run, tmp_path):
    at = tmp_path / "desklab"
    assert c.get("/api/tester/desklab").json() == {"strategies": [], "runner": {"alive": False, "seen_utc": None, "prices": {}}}
    draft(drafts_dir)
    promote(c, run_id=make_run())
    today = slots.et_now().date().isoformat()                                  # conftest pins this to 2026-09-28
    for i in range(12):
        store.put_day("nq_bars", {"date": (dt.date(2026, 9, 28) - dt.timedelta(days=i)).isoformat(), "state": "done", "n": i}, at)
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert today == "2026-09-28" and s["today"]["n"] == 0
    assert [d["n"] for d in s["days"]] == list(range(10))                       # ten, newest first
    now = dt.datetime.now(dt.timezone.utc)
    store.put_runner({"pid": 7, "seen_utc": (now - dt.timedelta(seconds=5)).isoformat(timespec="seconds"), "source": "u",
                      "prices": {"NQ": {"age_s": 0.4, "late": False}}, "hosting": ["nq_bars"]}, at)
    run = c.get("/api/tester/desklab").json()["runner"]
    assert run["alive"] is True and run["prices"] == {"NQ": {"age_s": 0.4, "late": False}} and run["seen_utc"]
    store.put_runner({"pid": 7, "seen_utc": (now - dt.timedelta(seconds=60)).isoformat(timespec="seconds"), "prices": {}}, at)
    assert c.get("/api/tester/desklab").json()["runner"]["alive"] is False
    store.put_runner({"pid": 7, "seen_utc": "yesterday", "prices": {}}, at)
    assert c.get("/api/tester/desklab").json()["runner"]["alive"] is False


def test_remove_and_onoff(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    off = c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": False})
    assert off.status_code == 200 and off.json() == {"ok": True, "name": "nq_bars", "enabled": False}
    assert c.get("/api/tester/desklab").json()["strategies"][0]["enabled"] is False
    assert c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": True}).json()["enabled"] is True
    gone = c.post("/api/tester/desklab/onoff", json={"name": "nq_none", "on": True})
    assert gone.status_code == 404 and gone.json() == {"ok": False, "detail": "That strategy is not on the Desk."}
    store.put_day("nq_bars", {"date": "2026-09-25", "state": "done"}, tmp_path / "desklab")
    assert c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}).json() == {"ok": True, "removed": True, "name": "nq_bars"}
    assert c.get("/api/tester/desklab").json()["strategies"] == []
    assert (tmp_path / "desklab" / "nq_bars" / "days" / "2026-09-25.json").is_file()      # the history stays
    assert c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}).json()["removed"] is False


@pytest.mark.parametrize("what,body", [
    ("promote", {"name": "nq_bars"}), ("promote", {"name": "nq_bars", "run_id": "x", "z": 1}),
    ("promote", {"name": "Bad Name", "run_id": "x"}), ("promote", {"name": "nq_bars", "run_id": 5}),
    ("promote", {"name": 5, "run_id": "x"}), ("promote", []), ("promote", "nq_bars"),
    ("remove", {}), ("remove", {"name": "nq_bars", "on": True}), ("remove", {"name": "../x"}), ("remove", {"name": 5}),
    ("onoff", {"name": "nq_bars"}), ("onoff", {"name": "nq_bars", "on": "yes"}), ("onoff", {"name": "nq_bars", "on": 1}),
    ("onoff", {"name": "nq_bars", "on": None}), ("onoff", {"on": True}), ("onoff", {"name": "nq_bars", "on": True, "z": 1})])
def test_bodies_are_checked_strictly(c, what, body):
    r = c.post(f"/api/tester/desklab/{what}", json=body)
    assert r.status_code == 400 and r.json()["ok"] is False and r.json()["detail"]


def test_other_ways_in_are_refused(c):
    assert c.post("/api/tester/desklab/explode", json={"name": "nq_bars"}).status_code == 404
    assert c.post("/api/tester/desklab/remove", content="{not json", headers={"content-type": "application/json"}).status_code == 400
    assert c.post("/api/tester/desklab/remove", content='{"name":"nq_bars"}', headers={"content-type": "text/plain"}).status_code == 415


def test_the_desk_page_calls_cross_origin_and_nobody_else_does(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    assert c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": True}).json()["enabled"] is True
    for what in ("promote", "remove", "onoff"):
        pre = c.options(f"/api/tester/desklab/{what}", headers={**DESK, "access-control-request-method": "POST"})
        assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == "http://localhost:8850"
        assert c.options(f"/api/tester/desklab/{what}", headers=EVIL).status_code == 403
    assert c.options("/api/tester/desklab/explode", headers=DESK).status_code == 403
    assert c.get("/api/tester/desklab", headers=EVIL).status_code == 403
    assert c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}, headers=EVIL).status_code == 403
    assert c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": False}, headers=EVIL).status_code == 403
    assert promote(c, run_id="x", headers=EVIL).status_code == 403
    assert (tmp_path / "desklab" / "nq_bars.json").is_file()
    assert c.get("/api/tester/desklab").json()["strategies"][0]["enabled"] is True          # the stranger changed nothing
    gone = c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}, headers=DESK)
    assert gone.status_code == 200 and gone.headers["access-control-allow-origin"] == "http://localhost:8850"
    assert c.get("/api/tester/desklab", headers={"host": "evil.example"}).status_code == 403          # the Host allowlist


def test_only_markets_the_service_streams_can_be_promoted(tmp_path, drafts_dir, make_run, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    monkeypatch.setattr(sandbox, "available", lambda: True)
    a = FastAPI()
    a.include_router(tester_api.tester_router(lambda request: None, tmp_path / "ticks", tmp_path / "state2", live_roots=("ES",)))
    es = TestClient(a, base_url="http://localhost:8852")
    draft(drafts_dir)                                                           # NQ
    state2 = tmp_path / "state2" / "runs"
    rid = "20261009-120000-draft_nq_bars-ab12"
    (state2 / rid).mkdir(parents=True)
    (state2 / rid / "request.json").write_text(json.dumps({"strategy": "draft_nq_bars", "draft_sha256": sha(CODE)}))
    (state2 / rid / "status.json").write_text(json.dumps({"status": "done"}))
    (state2 / rid / "run.json").write_text(json.dumps({"inputs": {}, "qty": 1, "range": RANGE}))
    assert sentence(promote(es, run_id=rid), 409) == "No live prices for NQ here."


def test_the_store_is_the_env_folder_never_the_real_one(c, drafts_dir, make_run, tmp_path, monkeypatch):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    assert (tmp_path / "desklab" / "nq_bars.json").is_file()
    assert store.root() == tmp_path / "desklab"
    monkeypatch.delenv(store.ENV_ROOT)
    assert str(store.root()).endswith(".homebase/desklab") and store.root() != tmp_path / "desklab"


def test_promote_checks_the_markets_this_service_really_streams(tmp_path, monkeypatch, drafts_dir, make_run):
    """The chart service hands the router its own markets: one started without NQ has no live prices for an NQ strategy."""
    from homebase.charts.server import create_app
    from tests.backtest_util import D1, nq_archive
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    monkeypatch.setattr(sandbox, "available", lambda: True)
    es_only = create_app(roots=["ES"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1, start_et=dt.time(9, 30),
                         state=tmp_path / "state")
    c = TestClient(es_only, base_url="http://localhost:8852")
    draft(drafts_dir)
    assert sentence(promote(c, run_id=make_run()), 409) == "No live prices for NQ here."
    assert c.get("/api/tester/desklab").json()["strategies"] == []
