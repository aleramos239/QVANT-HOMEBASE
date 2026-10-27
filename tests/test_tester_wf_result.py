"""GET /walkforward/{wid}/result: encoded in the threadpool, byte for byte what FastAPI's own encoding gave (2026-10-26)."""
from __future__ import annotations

import json

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from homebase.charts import tester_api
from homebase.charts.tester_routes import common, jobs

PAYLOAD = {"cells": [{"i": i, "params": {"stop": 1.5, "rr": 0.75}, "net": -12.5 * i, "name": "1:3 · ATR"} for i in range(3)],
           "lock": None, "nested": [[1, 2.0, None, True, "é"]], "big": 10 ** 20}


class FakeWfs:
    def __init__(self, d):
        self.d, self.calls = d, 0

    def dir(self, wid):
        if wid != "w":
            raise KeyError(wid)
        return self.d

    def result(self, wid, n=None):
        self.calls += 1
        got = json.loads((self.d / "result.json").read_text())
        if got.get("not_done"):
            raise ValueError("walk-forward w is running, not done")
        return got


def client(tmp_path):
    (tmp_path / "result.json").write_text(json.dumps(PAYLOAD))
    wfs = FakeWfs(tmp_path)
    r = APIRouter(prefix="/api/tester")
    jobs.register(r, common.make_ctx(tester_api, lambda req: None, None, None, wfs, None, ()))

    @r.get("/old-way")                  # the route as it was: FastAPI encodes the dict itself
    def old_way():
        return wfs.result("w", None)

    app = FastAPI()
    app.include_router(r)
    return TestClient(app), wfs


def test_the_result_is_the_same_bytes_and_headers_as_fastapis_own_encoding(tmp_path):
    c, _ = client(tmp_path)
    new, old = c.get("/api/tester/walkforward/w/result"), c.get("/api/tester/old-way")
    assert new.status_code == old.status_code == 200
    assert new.content == old.content
    assert sorted(new.headers.items()) == sorted(old.headers.items())


def test_not_done_is_still_409_and_unknown_still_404(tmp_path):
    c, _ = client(tmp_path)
    (tmp_path / "result.json").write_text(json.dumps({"not_done": True}))
    assert c.get("/api/tester/walkforward/w/result").status_code == 409
    assert c.get("/api/tester/walkforward/nope/result").status_code == 404
    assert c.get("/api/tester/walkforward/w/result", params={"test_months": "4"}).status_code == 400
