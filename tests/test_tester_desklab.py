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
from homebase.charts import deskresults, lab_templates, tester_api
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
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)     # a promote starts no run here unless a test says so
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
                                                    "qty": 2, "range": RANGE, "commission": 2.5, "slippage_ticks": 0.0,
                                                    "report": {"summary": {"all": SUMMARY}}}))
        return rid
    return make


def draft(drafts_dir, code=CODE, name="nq_bars"):
    (drafts_dir / f"{name}.py").write_text(code)


def promote(c, name="nq_bars", run_id="x", **kw):
    return c.post("/api/tester/desklab/promote", json={"name": name, "run_id": run_id}, **kw)


def mark(name="nq_bars"):
    """What a day file of this record's promotion carries."""
    r = store.get(name)
    return {"sha256": r["sha256"], "promoted_utc": r["promoted_utc"]}


def a_day(date, **kw):
    return {"date": date, "state": "done", "why": None, "orders": [], "trades": [], "net": 0.0, "match": None,
            "updated_utc": "x", **kw}


def at_et(monkeypatch, *ymdhm):
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(*ymdhm, tzinfo=slots.ET))


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
    assert (rec["commission"], rec["slippage_ticks"]) == (2.5, 0.0)             # D1: the costs that backtest ran with
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
    assert s["days"] == []                                                      # B1: another promotion's day is not this one's
    assert (tmp_path / "desklab" / "nq_bars" / "days" / "2026-09-25.json").is_file()     # ... and it is still kept
    assert (tmp_path / "desklab" / "nq_bars" / "journal.jsonl").is_file()


def test_the_list_shows_today_the_days_and_whether_the_runner_is_alive(c, drafts_dir, make_run, tmp_path):
    at = tmp_path / "desklab"
    assert c.get("/api/tester/desklab").json() == {"strategies": [], "archived": [], "builtins": [], "runner": {"alive": False, "seen_utc": None, "prices": {}}}
    draft(drafts_dir)
    promote(c, run_id=make_run())
    today = slots.et_now().date().isoformat()                                  # conftest pins this to 2026-09-28
    for i in range(12):
        store.put_day("nq_bars", {"date": (dt.date(2026, 9, 28) - dt.timedelta(days=i)).isoformat(), "state": "done", "n": i,
                                  **mark()}, at)
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert today == "2026-09-28" and s["today"]["n"] == 0
    assert [d["date"] for d in s["days"]] == [(dt.date(2026, 9, 28) - dt.timedelta(days=i)).isoformat() for i in range(10)]
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


# ---------------------------------------------------------------- B1: a day belongs to ONE promotion
def test_a_day_another_promotion_wrote_is_never_shown_as_this_ones(c):
    """The whole-branch review's script (old_day_under_new_code.py): the runner's finished day of the OLD code, then
    "Promote again" with other code in the evening. The page must not read the old day as the new code's."""
    today = slots.et_now().date().isoformat()
    old = {"sha256": "a" * 64, "promoted_utc": "2026-10-08T13:00:00+00:00"}
    new = {"sha256": "b" * 64, "promoted_utc": "2026-10-09T23:00:00+00:00"}
    store.put_day("nq_x", a_day(today, **old, net=811.0, match={"ok": True, "text": "Matched the backtest: 1 of 1 trade."},
                                orders=[{"t": "10:10:00", "text": "Sell at market, stop 21,520.00", "refused": None}]))
    store.put({"name": "nq_x", "id": "draft_nq_x", "label": "nq_x", "root": "NQ", "source": "# other code", **new,
               "params": {}, "qty": 1, "run": {}, "notes": [], "enabled": True})
    (row,) = c.get("/api/tester/desklab").json()["strategies"]
    assert row["sha256"] == "b" * 64 and row["today"] is None and row["days"] == []
    store.put_day("nq_x", a_day(today, **new, state="waiting"))                 # the new code's own day
    (row,) = c.get("/api/tester/desklab").json()["strategies"]
    assert row["today"]["state"] == "waiting" and [d["date"] for d in row["days"]] == [today]


def test_promote_again_shows_no_days_until_the_new_code_has_run(c, drafts_dir, make_run):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    for date in ("2026-09-25", "2026-09-28"):
        store.put_day("nq_bars", a_day(date, **mark()))
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"]["date"] == "2026-09-28" and [d["date"] for d in s["days"]] == ["2026-09-28", "2026-09-25"]
    newer = CODE.replace("Bar breakout", "Bar breakout two")
    draft(drafts_dir, newer)
    promote(c, run_id=make_run(newer))
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"] is None and s["days"] == []
    store.put_day("nq_bars", a_day("2026-09-28", **mark(), state="running"))    # the runner hosts the new code
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"]["state"] == "running" and [d["date"] for d in s["days"]] == ["2026-09-28"]


def test_the_same_code_promoted_again_does_not_show_the_days_of_the_promotion_before(c, drafts_dir, make_run):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    was = store.put({**store.get("nq_bars"), "promoted_utc": "2026-09-20T12:00:00+00:00"})    # (promoted a week ago)
    store.put_day("nq_bars", a_day("2026-09-28", sha256=was["sha256"], promoted_utc=was["promoted_utc"]))
    assert c.get("/api/tester/desklab").json()["strategies"][0]["today"]["date"] == "2026-09-28"
    promote(c, run_id=make_run())                                               # the same code, promoted again now
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["sha256"] == was["sha256"] and s["today"] is None and s["days"] == []


def test_remove_then_promote_does_not_show_the_old_days(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    was = store.put({**store.get("nq_bars"), "promoted_utc": "2026-09-20T12:00:00+00:00"})
    store.put_day("nq_bars", a_day("2026-09-28", sha256=was["sha256"], promoted_utc=was["promoted_utc"]))
    assert c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}).json()["removed"] is True
    promote(c, run_id=make_run())
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"] is None and s["days"] == []
    assert (tmp_path / "desklab" / "nq_bars" / "days" / "2026-09-28.json").is_file()     # the history stays on disk


def test_a_day_file_with_no_promoted_utc_is_shown_by_its_code_alone(c, drafts_dir, make_run):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    store.put_day("nq_bars", a_day("2026-09-28", sha256=mark()["sha256"]))
    store.put_day("nq_bars", a_day("2026-09-25", sha256="f" * 64))
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"]["date"] == "2026-09-28" and [d["date"] for d in s["days"]] == ["2026-09-28"]


# ---------------------------------------------------------------- B2: today is the day the RUNNER is on
@pytest.mark.parametrize("when, today", [
    ((2026, 10, 8, 17, 30), "2026-10-08"),       # Thursday 17:30 ET: still Thursday's session
    ((2026, 10, 8, 18, 30), "2026-10-09"),       # after the 18:00 roll: Friday's
    ((2026, 10, 8, 23, 59), "2026-10-09"),
    ((2026, 10, 9, 0, 1), "2026-10-09"),         # midnight changes nothing
    ((2026, 10, 10, 12, 0), None),               # Saturday noon: no session
    ((2026, 10, 11, 17, 59), None),              # Sunday before the open
    ((2026, 10, 11, 19, 0), "2026-10-12"),       # Sunday 19:00 ET: Monday's
])
def test_today_is_the_session_day_the_runner_is_on_not_the_wall_clock_date(c, drafts_dir, make_run, monkeypatch, when, today):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    for date in ("2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12"):
        store.put_day("nq_bars", a_day(date, **mark()))
    at_et(monkeypatch, *when)
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert (s["today"] or {}).get("date") == today


# ---------------------------------------------------------------- D7: the ten past days are short
def test_the_past_days_carry_only_what_the_page_reads_and_today_stays_whole(c, drafts_dir, make_run):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    full = a_day("2026-09-28", **mark(), net=811.0, why=None, rebuilt=True,
                 match={"ok": True, "text": "Matched the backtest: 1 of 1 trade."},
                 orders=[{"t": "10:10:00", "text": "Sell at market, stop 21,520.00", "refused": None}],
                 trades=[{"side": "short", "qty": 1, "entry_t": "10:10:00", "entry_px": 21500.0, "exit_t": "10:23:51",
                          "exit_px": 21459.25, "reason": "tp", "net": 811.0}])
    store.put_day("nq_bars", full)
    store.put_day("nq_bars", a_day("2026-09-25", **mark(), state="stopped", why="Too slow: no answer in 1 s."))
    (s,) = c.get("/api/tester/desklab").json()["strategies"]
    assert s["today"] == full                                                   # today: every row
    assert s["days"] == [
        {"date": "2026-09-28", "state": "done", "why": None, "net": 811.0, "rebuilt": True,
         "match": {"ok": True, "text": "Matched the backtest: 1 of 1 trade."}},
        {"date": "2026-09-25", "state": "stopped", "why": "Too slow: no answer in 1 s.", "net": 0.0, "rebuilt": False,
         "match": None}]


# ---- Step B (B1): while accounts are assigned on the Desk (the desk's sidecar holds book rows), the Lab page can neither
# ---- promote the strategy again nor remove it. The desk writes the sidecar; this service only reads it.
TAKE_OFF = "Take its accounts off on the Desk first."


def sidecar(name="nq_bars", book=({"account": "main", "qty": 1},)):
    r = store.get(name)
    store.put_desk(name, {"mark": store.mark_of(r) if r else [None, None], "limits": None, "book": list(book), "written_utc": "x"})


def test_promote_again_is_refused_while_accounts_are_assigned_on_the_desk(c, drafts_dir, make_run):
    draft(drafts_dir)
    assert promote(c, run_id=make_run()).status_code == 200
    first = store.get("nq_bars")
    sidecar()
    newer = CODE.replace("Bar breakout", "Bar breakout two")
    draft(drafts_dir, newer)
    r = promote(c, run_id=make_run(newer))
    assert sentence(r, 409) == TAKE_OFF
    assert store.get("nq_bars") == first                                        # the record on the Desk is untouched
    sidecar(book=())                                                            # the accounts were taken off
    assert promote(c, run_id=make_run(newer)).status_code == 200
    assert store.get("nq_bars")["label"] == "Bar breakout two" and store.get("nq_bars")["enabled"] is False
    assert store.get_desk("nq_bars")["written_utc"] == "x"                      # the sidecar is the desk's: never written here


def test_the_other_promote_refusals_still_come_first(c, drafts_dir, make_run):
    draft(drafts_dir)
    assert promote(c, run_id=make_run()).status_code == 200
    sidecar()
    assert sentence(promote(c, run_id=make_run(code=CODE + "# older\n"))) == CHANGED     # its own sentence, not the Desk's


def test_a_first_promote_with_a_sidecar_left_from_before_and_no_accounts_goes_through(c, drafts_dir, make_run):
    draft(drafts_dir)
    store.put_desk("nq_bars", {"mark": ["old", "old"], "limits": {"max_qty": 1}, "book": [], "written_utc": "x"})
    assert promote(c, run_id=make_run()).status_code == 200


def test_remove_is_refused_while_accounts_are_assigned_on_the_desk(c, drafts_dir, make_run):
    draft(drafts_dir)
    promote(c, run_id=make_run())
    sidecar()
    r = c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}, headers=DESK)
    assert sentence(r, 409) == TAKE_OFF and r.headers["access-control-allow-origin"] == "http://localhost:8850"
    assert store.get("nq_bars") is not None
    assert c.post("/api/tester/desklab/onoff", json={"name": "nq_bars", "on": True}).json()["enabled"] is True   # the switch still works
    sidecar(book=())
    assert c.post("/api/tester/desklab/remove", json={"name": "nq_bars"}).json() == {"ok": True, "removed": True, "name": "nq_bars"}
    assert store.get("nq_bars") is None and store.get_desk("nq_bars") is not None    # the sidecar is the desk's to remove


def test_promote_checks_the_sidecar_and_writes_the_record_under_one_lock(c, drafts_dir, make_run, monkeypatch):
    """The desk may book an account at the same instant: the check and the write are one step for it."""
    draft(drafts_dir)
    seen = []
    real_booked, real_put = store.booked, store.put

    def held():
        try:                                                                    # from another thread: is the lock held?
            import threading
            out = []

            def probe():
                try:
                    with store.write_lock(wait_s=0.0):
                        out.append(False)
                except TimeoutError:
                    out.append(True)
            t = threading.Thread(target=probe)
            t.start()
            t.join(5)
            return out[0]
        except Exception:  # noqa: BLE001
            return None
    monkeypatch.setattr(store, "booked", lambda *a, **k: (seen.append(("booked", held())), real_booked(*a, **k))[1])
    monkeypatch.setattr(store, "put", lambda *a, **k: (seen.append(("put", held())), real_put(*a, **k))[1])
    assert promote(c, run_id=make_run()).status_code == 200
    assert seen == [("booked", True), ("put", True)]


def test_open_in_the_lab_is_asked_by_the_desk_and_taken_once_by_the_lab_page(c, drafts_dir):
    """The Mac app drops a link's #fragment when it switches tab, so the Desk leaves its ask and the Lab page takes it."""
    draft(drafts_dir)
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # nothing asked
    gone = c.post("/api/tester/desklab/open", json={"name": "nq_none"}, headers=DESK)
    assert gone.status_code == 404 and gone.json() == {"ok": False, "detail": LAB}
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # a refusal asks nothing
    ok = c.post("/api/tester/desklab/open", json={"name": "nq_bars"}, headers=DESK)
    assert ok.status_code == 200 and ok.json() == {"ok": True, "name": "nq_bars"}
    assert c.get("/api/tester/lab-open").json() == {"name": "nq_bars"}
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # taken once
    bad = c.post("/api/tester/desklab/open", json={"name": "nq_bars", "x": 1}, headers=DESK)
    assert bad.status_code == 400
    evil = c.post("/api/tester/desklab/open", json={"name": "nq_bars"}, headers=EVIL)
    assert evil.status_code == 403


def test_the_list_names_the_built_ins_the_desk_runs(c, monkeypatch):
    """The Lab's "On the Desk" group holds the Desk's built-ins too: the list says which ones the Desk runs."""
    assert c.get("/api/tester/desklab").json()["builtins"] == []
    monkeypatch.setattr(tester_api, "desk_strategy_ids", lambda: ["gc_nfp", "nq930"])
    assert c.get("/api/tester/desklab").json()["builtins"] == ["gc_nfp", "nq930"]


# ---- the research the Desk's panel shows: the saved run on the unseen days and the prop sim (GET /api/tester/desklab/results) ----
UNSEEN = {"kind": "custom", "start": "2025-07-01", "end": "2026-10-11", "label": "Test", "holdout": True}
HEAD = {"eval_pass_p": 0.41, "bust_p": 0.59, "median_days_to_pass": 14, "funded_payout_p": 0.3, "funded_expected_cheque": 602.3}


def lab_results(c):
    """The promoted strategies' answers: the Desk's own straddles (deskresults.BUILTIN_TWINS) are answered beside them."""
    got = c.get("/api/tester/desklab/results", headers=DESK).json()["results"]
    return {k: v for k, v in got.items() if k not in deskresults.BUILTIN_TWINS}


def write_run(tmp_path, rid, name="nq_bars", code=CODE, rng=UNSEEN, inputs=None, qty=2, status="done", net=900.0):
    d = tmp_path / "state" / "tester" / "runs" / rid
    d.mkdir(parents=True)
    inputs = inputs or {"lookback": 8, "sl_pts": 20.0, "tp_pts": 40.0}
    (d / "request.json").write_text(json.dumps({"strategy": f"draft_{name}", "id": rid, "draft_sha256": sha(code),
                                                "inputs": inputs, "qty": qty, "range": rng}))
    (d / "status.json").write_text(json.dumps({"id": rid, "status": status}))
    (d / "trades.json").write_text("[]")
    if status == "done":
        (d / "run.json").write_text(json.dumps({"id": rid, "inputs": inputs, "qty": qty, "range": rng,
                                                "report": {"summary": {"all": {**SUMMARY, "net_profit": net, "rr": 2.81, "rr_label": "1:2.81",
                                                                                 "sharpe": 0.43}}}}))
    return rid






def test_a_setting_the_record_leaves_out_is_the_codes_default_when_a_run_is_matched(tmp_path, monkeypatch):
    """A record may carry fewer settings than its code has (the Desk's Setup panel adds one when it is changed): a run that
    resolved the rest to the code's defaults is still the same copy; one that changed a default is not."""
    from homebase.charts import deskresults
    rec = {"name": "nq_bars", "id": "draft_nq_bars", "source": CODE, "sha256": sha(CODE), "qty": 2, "params": {"lookback": 8}}
    full = deskresults.resolved_params(rec)
    assert full["lookback"] == 8 and set(full) == {"lookback", "sl_pts", "tp_pts"}, "the code's own defaults fill the rest"
    runs = tmp_path / "runs"
    write_run(tmp_path.joinpath("x"), "20261011-140000-draft_nq_bars-cc01", inputs=dict(full))
    write_run(tmp_path.joinpath("x"), "20261011-140001-draft_nq_bars-cc02", inputs={**full, "sl_pts": full["sl_pts"] + 5})
    runs = tmp_path / "x" / "state" / "tester" / "runs"
    got = deskresults.unseen_run(runs, rec)
    assert got and got["id"] == "20261011-140000-draft_nq_bars-cc01"






# ---- the unseen days are the 3:1 walk-forward (owner, 2026-10-18): the stitched out-of-sample months of a rolling search over the
# settings the Desk may change, and its pick for this month when it differs from what runs ----
CODE_SET = CODE.replace("    session_independent = True\n", "    session_independent = True\n    desk_settings = (\"sl_pts\", \"tp_pts\")\n")


def write_wf(tmp_path, rec, today, status="done", result=None, sha256=None):
    """A walk-forward job folder as the tester leaves it, built from the Desk's own request (deskresults.wf_request)."""
    from homebase.backtest import walkforward
    g = walkforward.validate_wf(deskresults.wf_request(rec, today))
    cells = g.pop("cells")
    gid = f"{today:%Y%m%d}-120000-{rec['id']}-{len(list((tmp_path / 'state' / 'tester' / 'walkforward').glob('*'))):04x}"
    d = tmp_path / "state" / "tester" / "walkforward" / gid
    (d / "cells" / "00").mkdir(parents=True)
    (d / "cells" / "00" / "request.json").write_text(json.dumps({**cells[0]["req"], **({"draft_sha256": sha256} if sha256 else {})}))
    (d / "grid.json").write_text(json.dumps({"id": gid, **g, "status": status, "total": len(cells), "done": len(cells),
                                             "cells": [{"i": c["i"], "params": c["params"], "status": status} for c in cells]}))
    if result is not None:
        (d / "result.json").write_text(json.dumps(result))
    return gid


def wf_result(pick):
    t = [{"date": "2022-01-03", "net": 300.0, "entry_ms": 1, "exit_ms": 2}, {"date": "2022-01-04", "net": -100.0, "entry_ms": 3, "exit_ms": 4}]
    return {"scheme": {"ratio": "3:1"}, "next": {"for": "2026-10", "params": pick},
            "stitched": {"stats": {**SUMMARY, "sharpe": 0.5}, "months": ["2022-01", "2026-09"], "trades": t}}


def test_a_strategy_with_no_settings_to_search_says_so(c, tmp_path, drafts_dir, make_run, monkeypatch):
    monkeypatch.setattr(tester_api, "_run_propsim", lambda trades, req: ({"rules": {"label": "LucidFlex 50K"}, "headline": HEAD, "breach": {}}, False))
    assert c.get("/api/tester/desklab/results", headers=EVIL).status_code == 403
    draft(drafts_dir)
    build = make_run()
    (tmp_path / "state" / "tester" / "runs" / build / "trades.json").write_text("[]")
    assert promote(c, run_id=build, headers=DESK).json()["ok"] is True
    got = c.get("/api/tester/desklab/results", headers=DESK)
    assert got.headers["access-control-allow-origin"] == DESK["origin"]
    assert lab_results(c) == {"nq_bars": {
        "unseen": None, "unseen_state": "unfit", "curve": None, "walkforward": True, "pick": None,
        "why": "No walk-forward: it needs 2 or 3 settings the Desk can change, and this strategy has 0.",
        "prop": {"build": {"account": "LucidFlex 50K", **HEAD}, "unseen": None}}}


def test_the_search_is_each_setting_at_its_value_and_25_percent_either_side():
    rec = {"params": {"a": 20.0, "b": 3, "c": "x"}, "source": "", "settings": [
        {"key": "a", "type": "float", "min": 0.5, "max": 1000.0, "step": 0.25},
        {"key": "b", "type": "int", "min": 3, "max": 10, "step": 1},
        {"key": "c", "type": "choice", "choices": ["x", "y"]}, {"key": "d", "type": "bool"}]}
    assert deskresults.wf_axes(rec) == [{"key": "a", "values": [15.0, 20.0, 25.0]}, {"key": "b", "values": [3, 4]},
                                        {"key": "c", "values": ["x", "y"]}], "below its min is left out; 3 settings at most"
    assert deskresults.wf_end(dt.date(2026, 10, 18)) == "2026-09-30" and deskresults.wf_end(dt.date(2026, 1, 1)) == "2025-12-31"


def test_the_card_shows_the_stitched_record_its_prop_sim_and_this_months_pick(c, tmp_path, drafts_dir, make_run, monkeypatch):
    scored = []

    def fake(trades, req):
        scored.append(len(trades))
        return {"rules": {"label": "LucidFlex 50K"}, "headline": HEAD, "breach": {}}, False
    monkeypatch.setattr(tester_api, "_run_propsim", fake)
    at_et(monkeypatch, 2026, 10, 18, 12, 0)
    draft(drafts_dir, CODE_SET)
    build = make_run(CODE_SET)
    (tmp_path / "state" / "tester" / "runs" / build / "trades.json").write_text("[]")
    assert promote(c, run_id=build, headers=DESK).json()["ok"] is True
    rec, today = store.get("nq_bars"), dt.date(2026, 10, 18)
    assert lab_results(c)["nq_bars"]["unseen_state"] == "none"
    write_wf(tmp_path, rec, today, result=wf_result({"sl_pts": 20.0, "tp_pts": 40.0}), sha256="other code")   # not this copy
    write_wf(tmp_path, rec, dt.date(2026, 9, 18), result=wf_result({"sl_pts": 20.0, "tp_pts": 40.0}))        # last month's window
    assert lab_results(c)["nq_bars"]["unseen_state"] == "none"
    gid = write_wf(tmp_path, rec, today, result=wf_result({"sl_pts": 25.0, "tp_pts": 40.0}))
    r = lab_results(c)["nq_bars"]
    assert r["unseen"] == {"id": gid, "range": {"start": "2022-01-01", "end": "2026-09-30"}, "walkforward": "3:1",
                           "net": 1234.5, "trades": 41, "win_rate": 48.8, "profit_factor": 1.31, "max_drawdown": -2100.0,
                           "rr": 3.0, "rr_label": None, "sharpe": 0.5}
    assert r["curve"] == {"days": ["2022-01-03", "2022-01-04"], "vals": [300.0, 200.0]}
    assert r["pick"] == {"for": "2026-10", "pick": {"sl_pts": 25.0, "tp_pts": 40.0}, "running": {"sl_pts": 20.0, "tp_pts": 40.0}}
    assert r["prop"]["unseen"] == {"account": "LucidFlex 50K", **HEAD} and 2 in scored
    # the pick agrees with what runs: no notice
    write_wf(tmp_path, rec, today, result=wf_result({"sl_pts": 20.0, "tp_pts": 40.0}))
    assert lab_results(c)["nq_bars"]["pick"] is None


def test_a_promote_starts_the_walkforward_once_and_a_failed_one_is_not_started_again(c, tmp_path, drafts_dir, make_run, monkeypatch):
    from homebase.backtest.walkforward import WalkForwardManager
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", True)
    at_et(monkeypatch, 2026, 10, 12, 12, 0)
    calls, refuse = [], []

    def fake_submit(self, body):
        if refuse:
            raise ValueError("Backtests do not start 09:20-09:35 ET.")
        calls.append(body)
        write_wf(tmp_path, store.get("nq_bars"), dt.date(2026, 10, 12), status="queued")
        return "x"
    monkeypatch.setattr(WalkForwardManager, "submit", fake_submit)
    draft(drafts_dir, CODE_SET)
    refuse.append(1)
    assert promote(c, run_id=make_run(CODE_SET), headers=DESK).json()["ok"] is True and calls == []
    assert lab_results(c)["nq_bars"]["unseen_state"] == "none"
    refuse.clear()
    got = lab_results(c)["nq_bars"]
    assert got["unseen_state"] == "pending" and got["unseen"] is None and len(calls) == 1
    assert calls[0] == {"strategy": "draft_nq_bars", "inputs": {"lookback": 8},
                        "axes": [{"key": "sl_pts", "values": [15.0, 20.0, 25.0]}, {"key": "tp_pts", "values": [30.0, 40.0, 50.0]}],
                        "range": {"kind": "custom", "start": "2021-09-22", "end": "2026-09-30"}, "qty": 2,
                        "commission": 2.5, "slippage_ticks": 0.0, "select_months": 3, "test_months": 1}
    for _ in range(2):
        assert lab_results(c)["nq_bars"]["unseen_state"] == "pending"
    assert len(calls) == 1
    gdir = next((tmp_path / "state" / "tester" / "walkforward").glob("*-draft_nq_bars-*"))
    g = json.loads((gdir / "grid.json").read_text())
    (gdir / "grid.json").write_text(json.dumps({**g, "status": "error"}))
    for _ in range(2):
        assert lab_results(c)["nq_bars"]["unseen_state"] == "failed"
    assert promote(c, run_id=make_run(CODE_SET), headers=DESK).json()["ok"] is True and len(calls) == 1
    # the Lab's code changed since the promote: a run of it would never match, so none starts
    (gdir / "grid.json").unlink()
    draft(drafts_dir, CODE_SET + "# newer\n")
    assert lab_results(c)["nq_bars"]["unseen_state"] == "changed" and len(calls) == 1


def test_the_curve_of_an_unseen_run_is_its_running_total_by_day_after_costs(tmp_path):
    from homebase.charts import deskresults
    runs = tmp_path / "runs"
    (runs / "r1").mkdir(parents=True)
    trades = [{"date": "2025-07-03", "net": -500.0}, {"date": "2025-07-01", "net": 1000.0}, {"date": "2025-07-01", "net": -250.5},
              {"date": "2025-07-08", "net": 3000.0}, {"date": "bad", "net": "x"}, "junk"]
    (runs / "r1" / "trades.json").write_text(json.dumps({"trades": trades}))
    assert deskresults.curve_of(runs, "r1") == {"days": ["2025-07-01", "2025-07-03", "2025-07-08"], "vals": [749.5, 249.5, 3249.5]}
    (runs / "r1" / "trades.json").write_text(json.dumps(trades[:2]))
    assert deskresults.curve_of(runs, "r1") == {"days": ["2025-07-01", "2025-07-03"], "vals": [1000.0, 500.0]}
    (runs / "r1" / "trades.json").write_text(json.dumps(trades[:1]))
    assert deskresults.curve_of(runs, "r1") is None, "one trading day is not a curve"
    assert deskresults.curve_of(runs, "gone") is None
    (runs / "r1" / "trades.json").write_text("not json")
    assert deskresults.curve_of(runs, "r1") is None




def test_the_desks_show_on_chart_carries_a_run_the_lab_page_takes_once_with_the_strategy(c, drafts_dir):
    draft(drafts_dir)
    ok = c.post("/api/tester/desklab/open", json={"name": "nq_bars", "run": "20261011-nq_bars-1"}, headers=DESK)
    assert ok.status_code == 200 and ok.json() == {"ok": True, "name": "nq_bars"}
    assert c.get("/api/tester/lab-open").json() == {"name": "nq_bars", "run": "20261011-nq_bars-1"}
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # taken once
    for bad in ({"name": "nq_bars", "run": "../etc"}, {"name": "nq_bars", "run": 7}, {"name": "nq_bars", "run": "a", "x": 1}):
        assert c.post("/api/tester/desklab/open", json=bad, headers=DESK).status_code == 400
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # a refusal asks nothing


# ---- the Desk's own straddles (nq930, gc_nfp): their tester twin's saved runs, read by hand, shown under the Desk id ----
BUILD = {"kind": "research", "start": "2021-09-22", "end": "2025-06-30", "label": "Build", "holdout": False}


def write_twin_run(tmp_path, rid, rec, rng=UNSEEN, inputs=None, qty=None, status="done", net=900.0):
    d = tmp_path / "state" / "tester" / "runs" / rid
    d.mkdir(parents=True)
    inputs = rec["params"] if inputs is None else inputs
    qty = rec["qty"] if qty is None else qty
    (d / "request.json").write_text(json.dumps({"strategy": rec["id"], "id": rid, "inputs": inputs, "qty": qty, "range": rng}))
    (d / "status.json").write_text(json.dumps({"id": rid, "status": status}))
    (d / "trades.json").write_text("[]")
    if status == "done":
        (d / "run.json").write_text(json.dumps({"id": rid, "inputs": inputs, "qty": qty, "range": rng,
                                                "report": {"summary": {"all": {**SUMMARY, "net_profit": net, "rr": 2.81, "rr_label": "1:2.81",
                                                                                 "sharpe": 0.43}}}}))
    return rid


def test_the_desks_straddles_are_answered_from_their_twins_saved_runs_and_nothing_is_started(c, tmp_path, monkeypatch):
    monkeypatch.setattr(tester_api, "_run_propsim",
                        lambda trades, req: ({"rules": {"label": "LucidFlex 50K"}, "headline": HEAD, "breach": {}}, False))
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", True)        # even with the automatic read on, a built-in's is never started
    started = []
    monkeypatch.setattr(tester_api.RunManager, "submit", lambda self, req: started.append(req), raising=False)
    assert deskresults.BUILTIN_TWINS == {"nq930": "nq930", "gc_nfp": "gc_nfpcpi"}
    got = c.get("/api/tester/desklab/results", headers=DESK).json()["results"]
    for desk_id, twin in deskresults.BUILTIN_TWINS.items():
        assert got[desk_id] == {"unseen": None, "unseen_state": "none", "manual": True, "twin": twin, "curve": None,
                                "prop": {"build": None, "unseen": None}}
    assert started == []
    # a saved run of the twin at the Desk's size and setting is its unseen result, and its build run feeds the prop sim's Build column
    rec = deskresults.builtin_rec("nq930")
    assert rec["id"] == "nq930" and rec["qty"] >= 1 and set(rec["params"]) >= {"offset_pts", "sl_pts", "tp_pts"}
    unseen = write_twin_run(tmp_path, "20261011-190000-nq930-aa01", rec)
    build = write_twin_run(tmp_path, "20261011-190001-nq930-aa02", rec, rng=BUILD)
    write_twin_run(tmp_path, "20261011-190002-nq930-aa03", rec, qty=rec["qty"] + 1)          # another size: not the Desk's
    write_twin_run(tmp_path, "20261011-190003-nq930-aa04", rec, inputs={**rec["params"], "sl_pts": rec["params"]["sl_pts"] + 1})
    res = c.get("/api/tester/desklab/results", headers=DESK).json()["results"]["nq930"]
    assert res["unseen"]["id"] == unseen and res["unseen"]["net"] == 900.0 and res["unseen_state"] == "done"
    assert res["prop"] == {"build": {"account": "LucidFlex 50K", **HEAD}, "unseen": {"account": "LucidFlex 50K", **HEAD}}
    assert deskresults.build_run_id(tmp_path / "state" / "tester" / "runs", rec) == build
    assert started == []


def test_open_in_the_lab_takes_a_built_in_twin_by_its_flag_and_only_the_known_ones(c, drafts_dir):
    ok = c.post("/api/tester/desklab/open", json={"name": "gc_nfpcpi", "builtin": True}, headers=DESK)
    assert ok.status_code == 200 and ok.json() == {"ok": True, "name": "gc_nfpcpi"}
    assert c.get("/api/tester/lab-open").json() == {"name": "gc_nfpcpi", "builtin": True}
    assert c.get("/api/tester/lab-open").json() == {"name": None}                        # taken once
    withrun = c.post("/api/tester/desklab/open", json={"name": "nq930", "builtin": True, "run": "20261011-nq930-1"}, headers=DESK)
    assert withrun.status_code == 200
    assert c.get("/api/tester/lab-open").json() == {"name": "nq930", "run": "20261011-nq930-1", "builtin": True}
    # a built-in that is not a Desk straddle's twin, and a flag that is not true, ask nothing
    assert c.post("/api/tester/desklab/open", json={"name": "gc_nfp", "builtin": True}, headers=DESK).status_code == 404
    assert c.post("/api/tester/desklab/open", json={"name": "nq930", "builtin": False}, headers=DESK).status_code == 400
    assert c.get("/api/tester/lab-open").json() == {"name": None}


def _edit_request(tmp_path, rid, **extra):
    p = next((tmp_path / "state" / "tester" / "runs").glob(f"{rid}")) / "request.json"
    req = json.loads(p.read_text())
    req.update(extra)
    p.write_text(json.dumps(req))


def test_a_run_with_trade_rules_is_not_promoted_the_desk_does_not_apply_them(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    rid = make_run()
    _edit_request(tmp_path, rid, controls={"max_trades": 2, "stop_mode": "fixed", "stop_pts": 12.0})
    r = promote(c, run_id=rid)
    assert r.status_code == 409 and "Trade rules (max_trades, stop_mode, stop_pts)" in r.json()["detail"]
    assert store.get("nq_bars") is None
    assert promote(c, run_id=make_run()).status_code == 200          # the same code with no rules goes through


def test_an_instant_entry_run_is_not_promoted_when_the_code_enters_print_by_print(c, drafts_dir, make_run, tmp_path):
    scanning = CODE + "\n    def scan(self, tape, lo, hi, t0, t1):\n        return []\n"
    draft(drafts_dir, scanning)
    rid = make_run(scanning)
    _edit_request(tmp_path, rid, inputs={"trigger": "instant"})
    r = promote(c, run_id=rid)
    assert r.status_code == 409 and "Entry is set to instant" in r.json()["detail"]
    rid2 = make_run(scanning)
    _edit_request(tmp_path, rid2, inputs={"trigger": "bar_close"})
    assert promote(c, run_id=rid2).status_code == 200


def test_archive_and_restore(c, drafts_dir, make_run, tmp_path):
    """Archive (the owner, 2026-10-18): a copy is kept, the record comes off, the Lab draft goes under "Archive"; Restore puts
    it back switched off and the draft back in its group. The history never moves."""
    draft(drafts_dir)
    promote(c, run_id=make_run())
    draftstore.set_group("draft_nq_bars", "Ideas")
    store.put_day("nq_bars", {"date": "2026-09-25", "state": "done"}, tmp_path / "desklab")
    post = lambda what, name="nq_bars": c.post(f"/api/tester/desklab/{what}", json={"name": name})
    assert post("archive").json() == {"ok": True, "name": "nq_bars"}
    early = post("filed")                                       # the Desk has not taken it off: not archived
    assert early.status_code == 409 and early.json()["detail"] == "It is still on the Desk, so it was not archived."
    assert c.get("/api/tester/desklab").json()["archived"] == []
    assert post("remove").json()["removed"] is True             # step 2 (the Desk's own Remove on the real page)
    assert post("filed").json() == {"ok": True, "name": "nq_bars"}
    got = c.get("/api/tester/desklab").json()
    assert got["strategies"] == [] and [w["name"] for w in got["archived"]] == ["nq_bars"]
    assert got["archived"][0]["run"]["net"] == SUMMARY["net_profit"]
    assert draftstore.read_groups()["members"]["draft_nq_bars"] == "Archive"
    assert post("filed").json()["ok"] is True                    # again: the group it had before is kept, not "Archive"
    assert (tmp_path / "desklab" / "nq_bars" / "days" / "2026-09-25.json").is_file()
    assert post("restore").json() == {"ok": True, "name": "nq_bars"}
    back = c.get("/api/tester/desklab").json()
    assert back["archived"] == [] and back["strategies"][0]["name"] == "nq_bars" and back["strategies"][0]["enabled"] is False
    assert "archived_utc" not in store.get("nq_bars") and "group_was" not in store.get("nq_bars")
    assert draftstore.read_groups()["members"]["draft_nq_bars"] == "Ideas"
    assert post("restore").status_code == 409                   # it is on the Desk now
    assert post("archive", "nq_none").status_code == 404


def test_restore_refused_while_a_namesake_is_on_the_desk(c, drafts_dir, make_run, tmp_path):
    draft(drafts_dir)
    rid = make_run()
    promote(c, run_id=rid)
    c.post("/api/tester/desklab/archive", json={"name": "nq_bars"})
    c.post("/api/tester/desklab/remove", json={"name": "nq_bars"})
    c.post("/api/tester/desklab/filed", json={"name": "nq_bars"})
    assert draftstore.read_groups()["members"].get("draft_nq_bars") == "Archive"
    promote(c, run_id=rid)                                      # promoted again from the Lab meanwhile
    assert c.get("/api/tester/desklab").json()["archived"] == []
    r = c.post("/api/tester/desklab/restore", json={"name": "nq_bars"})
    assert r.status_code == 409 and r.json()["detail"] == "A strategy of that name is on the Desk."


def test_a_builtin_is_archived_and_restored(c, monkeypatch):
    """nq930 / gc_nfp stay in the Desk's config: Archive notes them (the page switched them off and hides them) and files the tester
    twin under the Lab's "Archive" group; Restore takes the note off and the twin back to its group. Only the Desk's own ids."""
    monkeypatch.setattr(tester_api, "desk_strategy_ids", lambda: ["gc_nfp", "nq930"])
    draftstore.set_group("gc_nfpcpi", "Ideas")
    post = lambda what, name: c.post(f"/api/tester/desklab/{what}", json={"name": name})
    assert post("archive_builtin", "gc_nfp").json() == {"ok": True, "name": "gc_nfp"}
    assert post("archive_builtin", "gc_nfp").json()["ok"] is True                # twice: the group it had is kept
    (row,) = c.get("/api/tester/desklab").json()["archived"]
    assert row["name"] == "gc_nfp" and row["builtin"] is True
    assert draftstore.read_groups()["members"]["gc_nfpcpi"] == "Archive"
    assert post("archive_builtin", "nq_bars").status_code == 404                # not one of the Desk's own
    assert post("restore_builtin", "gc_nfp").json() == {"ok": True, "name": "gc_nfp"}
    assert c.get("/api/tester/desklab").json()["archived"] == []
    assert draftstore.read_groups()["members"]["gc_nfpcpi"] == "Ideas"
    assert post("restore_builtin", "gc_nfp").status_code == 404
