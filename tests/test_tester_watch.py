"""What an idea did, as a person looks at it (chart service): its equity curve, its executions on the chart, and the Desk's
watch list of promoted Book strategies. The toolkit is stood in for at the mixin (no bp.py, no tape); the watch folder and HOME
are temp folders."""
import json

import pytest
from fastapi.testclient import TestClient

from homebase.charts import tester_api, watch
from homebase.claude_mcp import blueprint_tools, pipeline_tools
from homebase.claude_mcp.client import ToolError
from tests.test_tester_api import EVIL, app

DESK = {"origin": "http://localhost:8850"}
JSON = {"content-type": "application/json"}
CURVE = {"period": "test", "cell": "k0p3_pts30-r3", "idea": "nq_x_a1", "market": "NQ", "session": "mid", "bar": "1", "side": "long",
         "start": "2025-07-03", "end": "2026-09-21", "trades": 263, "days": 125, "net": 39183.0, "win_rate": 0.3422, "avg_trade": 148.98,
         "avg_win": 1601.83, "avg_loss": -606.83, "profit_factor": 1.373, "best_day": 5388.0, "worst_day": -1837.0, "max_drawdown": 11502.0,
         "curve": [["2025-07-03", -374.0, -374.0], ["2026-09-21", 3592.0, 39183.0]]}
BOOK = [{"name": "nq_x", "sub": "nq_x_a1", "family": "noise_band", "market": "NQ", "session": "mid", "bar": "1", "why": "Real buying keeps going.",
         "label": "helper", "hours": ["11:01", "13:24"], "prop": {}, "stages": {}}]


@pytest.fixture
def calls(monkeypatch):
    seen = {"curve": [], "exec": []}

    def curve(self, name):
        seen["curve"].append(name)
        if name == "nq_nopick":
            raise blueprint_tools.Refused("REFUSED: nq_nopick has no picked box yet")
        if name == "nq_down":
            raise ToolError("The blueprint toolkit is not installed.")
        return dict(CURVE)

    def executions(self, name):
        seen["exec"].append(name)
        return {"run_id": "20261009-000000-pipe_nq_x-abcd", "trades": 263, "of": 263, "start": "2025-07-03", "end": "2026-09-21",
                "period": "test", "cell": "k0p3_pts30-r3", "fresh": True}

    monkeypatch.setattr(pipeline_tools.PipelineMixin, "pipeline_curve", curve)
    monkeypatch.setattr(pipeline_tools.PipelineMixin, "pipeline_executions", executions)
    monkeypatch.setattr(pipeline_tools.PipelineMixin, "pipeline_state", lambda self: {"book": BOOK})
    return seen


@pytest.fixture
def c(tmp_path, monkeypatch, calls):
    monkeypatch.setenv("HOMEBASE_WATCH_ROOT", str(tmp_path / "watch"))
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: False)
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def test_curve_is_the_toolkits_and_is_kept_between_looks(c, calls):
    r = c.get("/api/tester/pipeline/curve/nq_x")
    assert r.status_code == 200 and r.json()["net"] == 39183.0 and r.json()["curve"][-1] == ["2026-09-21", 3592.0, 39183.0]
    c.get("/api/tester/pipeline/curve/nq_x")
    assert calls["curve"] == ["nq_x"]                                  # the second look read the kept answer
    assert c.get("/api/tester/pipeline/curve/Bad Name").status_code == 404
    no = c.get("/api/tester/pipeline/curve/nq_nopick")
    assert no.status_code == 409 and "no picked box yet" in no.json()["detail"]
    assert c.get("/api/tester/pipeline/curve/nq_down").status_code == 503


def test_executions_writes_the_run_once_and_asks_the_chart_pages(c, calls):
    r = c.post("/api/tester/pipeline/executions", json={"name": "nq_x"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "pages": 0, "run_id": "20261009-000000-pipe_nq_x-abcd", "trades": 263, "of": 263, "start": "2025-07-03",
                        "end": "2026-09-21", "period": "test", "cell": "k0p3_pts30-r3", "fresh": True}
    assert c.post("/api/tester/pipeline/executions", json={"name": "nq_x", "x": 1}).status_code == 400
    assert c.post("/api/tester/pipeline/executions", json={"name": "nq_x"}, headers=EVIL).status_code == 403
    assert calls["exec"] == ["nq_x"]


def test_executions_never_moves_a_chart_in_the_930_window(c, calls, monkeypatch):
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: True)
    r = c.post("/api/tester/pipeline/executions", json={"name": "nq_x"})
    assert r.status_code == 409 and "9:30 window" in r.json()["detail"] and calls["exec"] == []


def test_promote_puts_a_book_strategy_on_the_watch_list_and_remove_takes_it_off(c, tmp_path):
    assert c.get("/api/tester/watch").json() == {"strategies": []}
    r = c.post("/api/tester/watch/promote", json={"name": "nq_x"})
    assert r.status_code == 200 and r.json()["ok"] is True
    got = c.get("/api/tester/watch").json()["strategies"]
    assert len(got) == 1
    s = got[0]
    assert (s["name"], s["family"], s["market"], s["net"], s["trades"], s["watch_only"]) == ("nq_x", "noise_band", "NQ", 39183.0, 263, True)
    assert s["curve"] == CURVE["curve"] and s["promoted_utc"]
    assert json.loads((tmp_path / "watch" / "nq_x.json").read_text())["name"] == "nq_x"
    assert "stages" not in s                                           # a snapshot of the facts, not the whole card
    assert c.post("/api/tester/watch/remove", json={"name": "nq_x"}).json() == {"ok": True, "removed": True, "name": "nq_x"}
    assert c.get("/api/tester/watch").json() == {"strategies": []}
    assert c.post("/api/tester/watch/remove", json={"name": "nq_x"}).json()["removed"] is False      # already gone: not an error


def test_only_a_strategy_in_the_book_can_be_promoted(c):
    r = c.post("/api/tester/watch/promote", json={"name": "nq_other"})
    assert r.status_code == 409 and r.json()["ok"] is False and "not in the Book" in r.json()["detail"]
    assert c.get("/api/tester/watch").json() == {"strategies": []}
    assert c.post("/api/tester/watch/promote", json={"name": "Bad Name"}).status_code == 400
    assert c.post("/api/tester/watch/explode", json={"name": "nq_x"}).status_code == 404


def test_the_desk_page_reads_and_removes_cross_origin_and_nobody_else_does(c):
    c.post("/api/tester/watch/promote", json={"name": "nq_x"})
    r = c.get("/api/tester/watch", headers=DESK)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:8850"
    pre = c.options("/api/tester/watch/remove", headers={**DESK, "access-control-request-method": "POST"})
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == "http://localhost:8850"
    assert c.options("/api/tester/watch/remove", headers=EVIL).status_code == 403
    assert c.get("/api/tester/watch", headers=EVIL).status_code == 403
    assert c.post("/api/tester/watch/remove", json={"name": "nq_x"}, headers=EVIL).status_code == 403
    assert len(c.get("/api/tester/watch").json()["strategies"]) == 1                              # the stranger removed nothing
    gone = c.post("/api/tester/watch/remove", json={"name": "nq_x"}, headers=DESK)
    assert gone.status_code == 200 and gone.json()["removed"] is True and gone.headers["access-control-allow-origin"] == "http://localhost:8850"
    shown = c.post("/api/tester/watch/show", json={"name": "nq_x"}, headers=DESK)
    assert shown.status_code == 200 and shown.json()["run_id"].endswith("abcd")


def test_the_watch_store_keeps_whole_files_and_skips_what_does_not_read(tmp_path):
    at = tmp_path / "w"
    assert watch.listing(at) == [] and watch.get("nq_x", at) is None
    watch.put(watch.snapshot(BOOK[0], CURVE), at)
    (at / "broken.json").write_text("{not json")
    (at / "Other Name.json").write_text("{}")
    assert [s["name"] for s in watch.listing(at)] == ["nq_x"]
    assert not list(at.glob(".*.tmp"))
    with pytest.raises(ValueError):
        watch.put({"name": "../x"}, at)
    with pytest.raises(ValueError):
        watch.remove("../x", at)
