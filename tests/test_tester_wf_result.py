"""GET /walkforward/{wid}/result: encoded in the threadpool, byte for byte what FastAPI's own encoding gave (2026-10-26)."""
from __future__ import annotations

import json
import os

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from homebase.backtest import runner
from homebase.charts import tester_api
from homebase.charts.tester_routes import common, jobs

PAYLOAD = {"cells": [{"i": i, "params": {"stop": 1.5, "rr": 0.75}, "net": -12.5 * i, "name": "1:3 · ATR"} for i in range(3)],
           "lock": None, "nested": [[1, 2.0, None, True, "é"]], "big": 10 ** 20}


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    """Files count as settled at once here (the 2 s rule has its own test)."""
    monkeypatch.setattr(runner, "SETTLED_NS", 0)


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


def test_a_finished_result_is_served_from_its_bytes_until_one_of_its_files_changes(tmp_path):
    c, wfs = client(tmp_path)
    first = c.get("/api/tester/walkforward/w/result")
    again = c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 1                       # the second one never read or encoded it again
    assert again.content == first.content and sorted(again.headers.items()) == sorted(first.headers.items())
    (tmp_path / "lock.json").write_text('{"cell": 1}')          # the owner's pick: a file it is read from
    c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 2
    (tmp_path / "result.json").write_text(json.dumps({**PAYLOAD, "lock": {"cell": 1}}))
    assert c.get("/api/tester/walkforward/w/result").json()["lock"] == {"cell": 1} and wfs.calls == 3
    c.get("/api/tester/walkforward/w/result", params={"test_months": "1"})   # another key: read once more
    assert wfs.calls == 4


def test_a_test_month_read_under_way_and_a_refusal_are_never_kept(tmp_path):
    c, wfs = client(tmp_path)
    (tmp_path / "oos-claim.json").write_text("{}")             # claimed, no oos.json yet: its progress moves
    c.get("/api/tester/walkforward/w/result"), c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 2
    (tmp_path / "oos.json").write_text('{"state": "done"}')    # the read on file: kept from here on
    c.get("/api/tester/walkforward/w/result"), c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 3
    (tmp_path / "result.json").write_text(json.dumps({"not_done": True}))
    assert [c.get("/api/tester/walkforward/w/result").status_code for _ in range(2)] == [409, 409] and wfs.calls == 5


def test_a_result_written_in_the_last_2_seconds_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SETTLED_NS", 2_000_000_000)
    c, wfs = client(tmp_path)
    c.get("/api/tester/walkforward/w/result"), c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 2                       # a write just after could keep its stamp on a coarse clock: read again
    old = (tmp_path / "result.json").stat().st_mtime_ns - 3_000_000_000
    os.utime(tmp_path / "result.json", ns=(old, old))
    c.get("/api/tester/walkforward/w/result"), c.get("/api/tester/walkforward/w/result")
    assert wfs.calls == 3
