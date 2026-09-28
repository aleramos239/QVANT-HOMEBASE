"""The export routes on the chart service: schema/meta/coverage, the start->poll->done->reveal
job lifecycle, and the Origin + Host write guards every POST here shares with the rest of the
service (paperbook.py, tester_api.py)."""
from __future__ import annotations

import datetime as dt
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.charts.export import export_router
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive

EVIL = {"origin": "https://evil.example"}
REBIND_HOST = {"host": "evil.example"}


def app(tmp_path, monkeypatch, roots=("NQ", "ES")):
    monkeypatch.setenv("HB_EXPORT_DIR", str(tmp_path / "downloads"))
    return create_app(roots=list(roots), base=tmp_path / "ticks", replay=D, speed=1,
                      start_et=dt.time(9, 30), state=tmp_path / "state", depth_base=tmp_path / "depth")


def client(tmp_path, monkeypatch, **kw):
    return TestClient(app(tmp_path, monkeypatch, **kw), base_url="http://localhost:8852")


def poll(c, jid, timeout=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = c.get(f"/api/export/{jid}").json()
        if st.get("status") in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("export never finished")


def test_schema_lists_roots_types_and_timeframes(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        got = c.get("/api/export/schema").json()
        assert "NQ" in got["roots"] and "6E" in got["roots"] and "BTC" in got["roots"]
        assert got["depth_roots"] == ["NQ", "ES"]
        assert "1s" in got["timeframes"] and "1D" in got["timeframes"]
        assert "level3" in got["types"]


def test_meta_reports_range_and_contracts(tmp_path, monkeypatch):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0, 2.0]))
    with client(tmp_path, monkeypatch) as c:
        got = c.get("/api/export/meta", params={"root": "NQ", "type": "candles"}).json()
        assert got["range"] == [D.isoformat(), D.isoformat()]
        assert got["contracts"] == ["NQZ6"]
        empty = c.get("/api/export/meta", params={"root": "ES", "type": "candles"}).json()
        assert empty == {"range": None, "contracts": []}


def test_meta_unknown_root_is_404(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        r = c.get("/api/export/meta", params={"root": "ZZ", "type": "candles"})
        assert r.status_code == 404


def test_coverage_reports_missing_sessions(tmp_path, monkeypatch):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0]))
    nxt = (D + dt.timedelta(days=1)).isoformat()
    with client(tmp_path, monkeypatch) as c:
        got = c.get("/api/export/coverage", params={"root": "NQ", "type": "ticks",
                                                     "start": D.isoformat(), "end": nxt}).json()
        assert got["sessions_total"] == 2
        assert got["missing"] == [nxt]


def test_start_requires_write_ok_origin_and_host(tmp_path, monkeypatch):
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0]))
    body = {"root": "NQ", "type": "ticks", "start": D.isoformat(), "end": D.isoformat()}
    with client(tmp_path, monkeypatch) as c:
        assert c.post("/api/export/start", json=body, headers=EVIL).status_code == 403
        assert c.post("/api/export/start", json=body, headers=REBIND_HOST).status_code == 403
        r = c.post("/api/export/start", json=body)
        assert r.status_code == 200 and "id" in r.json()


def test_start_validation_error_is_400(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        r = c.post("/api/export/start", json={"root": "XX", "type": "ticks",
                                              "start": D.isoformat(), "end": D.isoformat()})
        assert r.status_code == 400


def test_full_job_lifecycle_start_poll_done_and_reveal(tmp_path, monkeypatch):
    """A standalone app around just export_router -- not create_app's full service -- so the
    reveal command can be stubbed. The real one shells out to `open -R`, which would pop a
    Finder window on the developer's own desktop; never acceptable from an automated check. Only
    what `open -R` would have been CALLED WITH is under test here, not the real command."""
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [100.0, 100.25]))
    reveals = []
    a = FastAPI()
    a.include_router(export_router(lambda request: None, tmp_path / "ticks", tmp_path / "depth",
                                   tmp_path / "state", out_dir=tmp_path / "downloads",
                                   reveal_run=lambda *args, **kw: reveals.append(args)))
    with TestClient(a, base_url="http://localhost:8852") as c:
        r = c.post("/api/export/start", json={"root": "NQ", "type": "ticks",
                                              "start": D.isoformat(), "end": D.isoformat()})
        assert r.status_code == 200
        jid = r.json()["id"]
        st = poll(c, jid)
        assert st["status"] == "done" and st["rows"] == 2
        assert st["result"]["name"].startswith("NQ_ticks_")
        rr = c.post(f"/api/export/{jid}/reveal")
        assert rr.status_code == 200
        assert reveals and reveals[0][0] == ["open", "-R", st["result"]["path"]]


def test_cancel_and_status_of_an_unknown_job_are_404(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        assert c.get("/api/export/not-a-real-id").status_code == 404
        assert c.post("/api/export/not-a-real-id/cancel").status_code == 404
