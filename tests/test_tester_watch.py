"""What an idea did, as a person looks at it (chart service): its equity curve and its executions on the chart. The toolkit is
stood in for at the mixin (no bp.py, no tape); HOME is a temp folder. (The Desk's watch-only list was removed 2026-10-10.)"""
import pytest
from fastapi.testclient import TestClient

from homebase.charts import tester_api
from homebase.claude_mcp import blueprint_tools, pipeline_tools
from homebase.claude_mcp.client import ToolError
from tests.test_tester_api import EVIL, app

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


