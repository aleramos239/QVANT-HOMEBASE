"""The Lab's draft routes on the chart service: list, validate, save, delete, templates, request review.
Text in, text out: no draft code runs in the chart service (the sandboxed backtest child is the only place)."""
from __future__ import annotations

import datetime as dt
import json
import sys
import time

from fastapi.testclient import TestClient

from homebase import draftstore
from homebase.charts import lab_templates, reviewpack
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

OK = {"origin": "http://localhost:8852"}
EVIL = {"origin": "https://evil.example"}
MARCH = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}


def client(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    return TestClient(app, base_url="http://localhost:8852")


def poll(c, rid, s=60.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/run/{rid}").json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_every_template_is_a_valid_draft():
    ts = lab_templates.templates()
    assert [t["id"] for t in ts] == ["straddle", "bar_breakout", "blank"]
    for t in ts:
        draftstore.check_source(t["code"])
        assert draftstore.static_meta(t["code"])["root"] == "NQ"


def test_the_straddle_starter_is_short_and_the_reference_carries_the_contract(tmp_path):
    assert lab_templates.STRADDLE.count("\n") < 50 and "class MyDraft(Strategy)" in lab_templates.STRADDLE
    ref = lab_templates.reference()
    assert "ctx.stop_entry" in ref and "on_bar" in ref and "MyDraft" not in ref
    with client(tmp_path) as c:
        assert c.get("/api/tester/drafts/reference").json()["text"] == ref


def test_the_template_route_serves_them(tmp_path):
    with client(tmp_path) as c:
        got = c.get("/api/tester/drafts/templates").json()
        assert [t["id"] for t in got] == ["straddle", "bar_breakout", "blank"]
        assert all(t["code"] and t["title"] for t in got)


def test_validate_reads_the_text_and_says_which_line(tmp_path):
    with client(tmp_path) as c:
        good = c.post("/api/tester/drafts/validate", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK).json()
        assert good["ok"] is True and good["meta"]["root"] == "NQ"
        assert [i["key"] for i in good["meta"]["inputs"]] == ["lookback", "sl_pts", "tp_pts"]
        bad = c.post("/api/tester/drafts/validate", json={"code": "class X(Strategy:\n  pass\n"}, headers=OK).json()
        assert bad["ok"] is False and bad["line"] == 1 and "SyntaxError" in bad["error"]
        noclass = c.post("/api/tester/drafts/validate", json={"code": "x = 1\n"}, headers=OK).json()
        assert noclass["ok"] is False and "exactly one class" in noclass["error"]
        assert c.post("/api/tester/drafts/validate", json={}, headers=OK).status_code == 400


def test_save_lists_reads_and_deletes_a_draft(tmp_path, drafts_dir):
    with client(tmp_path) as c:
        assert c.get("/api/tester/drafts").json() == []
        r = c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == "draft_nq_bars" and r.json()["meta"]["bar_minutes"] == 5
        assert (drafts_dir / "nq_bars.py").read_text() == lab_templates.BAR_BREAKOUT
        listed = c.get("/api/tester/drafts").json()
        assert [d["name"] for d in listed] == ["nq_bars"] and listed[0]["ok"] is True and listed[0]["bytes"] > 100
        # the catalog the tester already serves picks it up, and its source is readable
        assert "draft_nq_bars" in {s["id"] for s in c.get("/api/tester/strategies").json()}
        assert c.get("/api/tester/strategies/draft_nq_bars/source").json()["files"][0]["text"] == lab_templates.BAR_BREAKOUT
        assert c.delete("/api/tester/drafts/nq_bars", headers=OK).json() == {"deleted": True}
        assert c.delete("/api/tester/drafts/nq_bars", headers=OK).json() == {"deleted": False}
        assert c.get("/api/tester/drafts").json() == []
    assert not any(m.startswith("homebase_draft_") for m in sys.modules), "saving never imports a draft"


def test_a_draft_that_does_not_read_is_listed_with_its_error(tmp_path, drafts_dir):
    (drafts_dir / "broken.py").write_text("class A(Strategy):\n    root = 3 + 4\n")
    with client(tmp_path) as c:
        row = c.get("/api/tester/drafts").json()[0]
        assert row["name"] == "broken" and row["ok"] is False and row["error"]


def test_saving_refuses_bad_names_builtins_and_bad_code(tmp_path):
    with client(tmp_path) as c:
        for name in ("Bad-Name", "nq930", "draft_x", "json"):
            r = c.put(f"/api/tester/drafts/{name}", json={"code": lab_templates.BLANK}, headers=OK)
            assert r.status_code == 400, name
        r = c.put("/api/tester/drafts/okname", json={"code": "def ("}, headers=OK)
        assert r.status_code == 400 and "SyntaxError" in r.json()["detail"]
        assert c.put("/api/tester/drafts/okname", json={}, headers=OK).status_code == 400


def test_writes_keep_the_origin_host_and_json_guards(tmp_path):
    with client(tmp_path) as c:
        body = {"code": lab_templates.BLANK}
        assert c.put("/api/tester/drafts/guarded", json=body, headers=EVIL).status_code == 403
        assert c.put("/api/tester/drafts/guarded", json=body, headers={**OK, "host": "evil.example"}).status_code == 403
        assert c.delete("/api/tester/drafts/guarded", headers=EVIL).status_code == 403
        assert c.post("/api/tester/drafts/validate", json=body, headers=EVIL).status_code == 403
        assert c.put("/api/tester/drafts/guarded", content="code=x", headers={**OK, "content-type": "text/plain"}).status_code == 415
        assert c.get("/api/tester/drafts").json() == []


def test_a_saved_bar_draft_backtests_in_the_sandbox(tmp_path):
    with client(tmp_path) as c:
        c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        rid = c.post("/api/tester/run", json={"strategy": "draft_nq_bars", "range": MARCH}, headers=OK).json()["id"]
        st = poll(c, rid)
        assert st["status"] == "done", st.get("error")
        b = c.get(f"/api/tester/run/{rid}/bundle").json()
        assert b["run"]["strategy"]["id"] == "draft_nq_bars"


def test_request_review_writes_text_only_and_judges_the_run(tmp_path, monkeypatch):
    rdir = tmp_path / "reviews"
    monkeypatch.setenv(reviewpack.ENV, str(rdir))
    with client(tmp_path) as c:
        c.put("/api/tester/drafts/nq_bars", json={"code": lab_templates.BAR_BREAKOUT}, headers=OK)
        assert c.post("/api/tester/drafts/nope/review-request", json={}, headers=OK).status_code == 404
        r = c.post("/api/tester/drafts/nq_bars/review-request", json={"note": "worth a look"}, headers=OK)
        assert r.status_code == 200, r.text
        got = r.json()
        pack = json.loads((rdir / f"{got['id']}.json").read_text())
        assert pack["strategy"] == "draft_nq_bars" and pack["note"] == "worth a look" and pack["status"] == "requested"
        assert pack["code"] == lab_templates.BAR_BREAKOUT and len(pack["sha256"]) == 64
        assert {x["id"]: x["ok"] for x in pack["checks"]}["ran"] is False      # no backtest attached
        md = (rdir / f"{got['id']}.md").read_text()
        assert "Review request: draft_nq_bars" in md and "```python" in md and "For the reviewer" in md
        # with a finished run attached the pack carries its numbers
        rid = c.post("/api/tester/run", json={"strategy": "draft_nq_bars", "range": MARCH}, headers=OK).json()["id"]
        assert poll(c, rid)["status"] == "done"
        got2 = c.post("/api/tester/drafts/nq_bars/review-request", json={"run_id": rid}, headers=OK).json()
        pack2 = json.loads((rdir / f"{got2['id']}.json").read_text())
        assert pack2["backtest"]["all"] is not None and {x["id"] for x in pack2["checks"]} >= {"trades", "holdout", "costs"}
        assert c.post("/api/tester/drafts/nq_bars/review-request", json={"run_id": "nope"}, headers=OK).status_code == 404
    # nothing ran, nothing was promoted: the desk's strategy config is untouched by a review request
    assert not any("review" in m and m.startswith("homebase.server") for m in sys.modules)
