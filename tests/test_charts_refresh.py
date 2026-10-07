"""The Data tab's "Refresh data" button (homebase/charts/refresh.py): the broker step, then the Massive
step when its credentials are set, one run at a time, never in the 9:30 window, cancellable, and
honest about what failed. The processes are fakes -- the tick job itself is tested in test_ticks.py."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.charts import refresh as R

UTC = dt.timezone.utc
WED_NOON = dt.datetime(2026, 10, 7, 16, 0, tzinfo=UTC)         # 12:00 ET
WED_0930 = dt.datetime(2026, 10, 7, 13, 30, tzinfo=UTC)        # 09:30 ET: the quiet window


class FakeProc:
    def __init__(self, code=0, hold: threading.Event | None = None):
        self.code, self.hold, self.terminated = code, hold, False

    def wait(self):
        if self.hold is not None:
            self.hold.wait(5)
        return -15 if self.terminated else self.code

    def terminate(self):
        self.terminated = True
        if self.hold is not None:
            self.hold.set()


def manager(tmp_path, codes=(0, 0), env=None, clock=WED_NOON, holds=None, cov=None):
    calls = []
    queue = list(codes)

    def popen(argv, **kw):
        calls.append(argv)
        i = len(calls) - 1
        return FakeProc(queue[i], holds[i] if holds else None)

    m = R.RefreshManager(tmp_path / "state", python="py", cwd=tmp_path, clock=lambda: clock, popen=popen,
                         env={"MASSIVE_S3_KEY": "k", "MASSIVE_S3_SECRET": "s"} if env is None else env,
                         coverage_path=cov or tmp_path / "cov.json")
    return m, calls


def wait_final(m, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = m.status()
        if st["status"] in R.FINAL:
            return st
        time.sleep(0.01)
    raise AssertionError(f"never finished: {m.status()}")


def test_idle_before_any_click(tmp_path):
    m, _ = manager(tmp_path)
    assert m.status() == {"status": "idle"}


def test_a_click_runs_the_broker_step_then_the_massive_step(tmp_path):
    m, calls = manager(tmp_path)
    m.start()
    st = wait_final(m)
    assert st["status"] == "done"
    assert calls == [["py", "-m", "homebase.ticks"], ["py", "-m", "homebase.ticks", "--fill-from-massive", "--holes"]]
    assert [s["state"] for s in st["steps"]] == ["done", "done"]


def test_without_massive_credentials_that_step_is_skipped_and_says_why(tmp_path):
    m, calls = manager(tmp_path, env={"PATH": "/bin"})
    m.start()
    st = wait_final(m)
    assert st["status"] == "done" and len(calls) == 1
    assert st["steps"][1]["state"] == "skipped" and "credentials" in st["steps"][1]["note"]


def test_a_failed_step_stops_the_run_and_names_it(tmp_path):
    m, calls = manager(tmp_path, codes=(1, 0))
    m.start()
    st = wait_final(m)
    assert st["status"] == "error" and len(calls) == 1
    assert "Fetch missing ticks" in st["note"] and "exit 1" in st["note"]
    assert [s["state"] for s in st["steps"]] == ["error", "waiting"]


def test_only_one_refresh_at_a_time(tmp_path):
    hold = threading.Event()
    m, _ = manager(tmp_path, codes=(0,) * 4, holds=[hold, None, None, None])
    m.start()
    with pytest.raises(ValueError, match="already running"):
        m.start()
    hold.set()
    wait_final(m)
    m.start()                                  # and again once it is over
    wait_final(m)


def test_never_in_the_930_window(tmp_path):
    m, calls = manager(tmp_path, clock=WED_0930)
    with pytest.raises(ValueError, match="09:35"):
        m.start()
    assert calls == [] and m.status() == {"status": "idle"}


def test_cancel_ends_the_running_step_and_skips_the_rest(tmp_path):
    hold = threading.Event()
    m, calls = manager(tmp_path, holds=[hold, None])
    m.start()
    while not calls:
        time.sleep(0.01)
    m.cancel()
    st = wait_final(m)
    assert st["status"] == "cancelled" and len(calls) == 1
    assert st["steps"][0]["state"] == "cancelled" and st["steps"][1]["state"] == "waiting"


def test_the_finished_status_carries_the_coverage_summary(tmp_path):
    cov = tmp_path / "cov.json"
    cov.write_text(json.dumps({"generated_at_utc": "2026-10-07T16:01:00+00:00",
                               "summary": {"roots": 6, "sessions": 180, "complete": 170, "missing": 2}}))
    m, _ = manager(tmp_path, cov=cov)
    m.start()
    st = wait_final(m)
    assert st["coverage"]["sessions"] == 180 and st["coverage"]["missing"] == 2
    assert st["coverage"]["generated_at_utc"].startswith("2026-10-07")


def test_a_run_the_service_died_in_is_never_running_forever(tmp_path):
    d = tmp_path / "state" / "refresh"
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"status": "running", "step": "broker", "steps": []}))
    m, _ = manager(tmp_path)
    st = m.status()
    assert st["status"] == "error" and "interrupted" in st["note"]


def test_a_missing_binary_is_an_error_not_a_crash(tmp_path):
    def popen(argv, **kw):
        raise FileNotFoundError("py")
    m = R.RefreshManager(tmp_path / "state", python="py", cwd=tmp_path, clock=lambda: WED_NOON, popen=popen,
                         env={}, coverage_path=tmp_path / "cov.json")
    m.start()
    assert wait_final(m)["status"] == "error"


# ---------------------------------------------------------------------------- the routes
def client(tmp_path, **kw):
    app = FastAPI()
    app.include_router(R.refresh_router(lambda request: None, tmp_path / "state", python="py", cwd=tmp_path,
                                        clock=lambda: WED_NOON, popen=lambda argv, **k: FakeProc(),
                                        env={}, coverage_path=tmp_path / "cov.json", **kw))
    return TestClient(app, base_url="http://localhost:8852")


def test_routes_start_then_poll(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/refresh").json() == {"status": "idle"}
    assert c.post("/api/refresh").json()["status"] in ("running", "done")
    t0 = time.monotonic()
    while c.get("/api/refresh").json()["status"] == "running" and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    assert c.get("/api/refresh").json()["status"] == "done"


def test_a_second_start_is_409(tmp_path):
    hold = threading.Event()
    app = FastAPI()
    app.include_router(R.refresh_router(lambda request: None, tmp_path / "state", python="py", cwd=tmp_path,
                                        clock=lambda: WED_NOON, popen=lambda argv, **k: FakeProc(hold=hold),
                                        env={}, coverage_path=tmp_path / "cov.json"))
    c = TestClient(app, base_url="http://localhost:8852")
    assert c.post("/api/refresh").status_code == 200
    r = c.post("/api/refresh")
    assert r.status_code == 409 and "already running" in r.json()["detail"]
    hold.set()


def test_the_post_is_behind_the_write_guard(tmp_path):
    from fastapi import HTTPException

    def refuse(request):
        raise HTTPException(403, "writes from another site are refused")
    app = FastAPI()
    app.include_router(R.refresh_router(refuse, tmp_path / "state", python="py", cwd=tmp_path,
                                        clock=lambda: WED_NOON, popen=lambda argv, **k: FakeProc(),
                                        env={}, coverage_path=tmp_path / "cov.json"))
    c = TestClient(app, base_url="http://localhost:8852")
    assert c.post("/api/refresh").status_code == 403
    assert c.post("/api/refresh/cancel").status_code == 403
    assert c.get("/api/refresh").status_code == 200
