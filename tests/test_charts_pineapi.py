"""The Pine routes (homebase/charts/pineapi.py): the script list and text from a temp folder, names that
leave the folder refused, and the runtime file served only when it is the pinned build."""
from __future__ import annotations

import datetime as dt
import hashlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.charts import pineapi as P
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive

RSI = '//@version=6\nindicator("RSI twin", overlay=false)\nplot(ta.rsi(close, 14))\n'
STRAT = "//@version=5\nstrategy(title='Sniper', overlay=true)\nplot(close)\n"


def client(tmp_path, monkeypatch, scripts=None, runtime: bytes | None = None):
    monkeypatch.setenv(P.ENV, str(tmp_path))
    sd = tmp_path / "scripts"
    sd.mkdir(parents=True)
    for name, text in (scripts or {}).items():
        (sd / name).write_text(text)
    if runtime is not None:
        rp = P.runtime_path()
        rp.parent.mkdir(parents=True)
        rp.write_bytes(runtime)
    app = FastAPI()
    app.include_router(P.routes())
    return TestClient(app, base_url="http://localhost:8852")


def test_list_reads_version_kind_and_title_and_skips_other_files(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI, "my strat.pine": STRAT, "notes.txt": "x",
                                        "old.pine": "// no header\nplot(close)\n"}) as c:
        got = c.get("/api/pine/scripts").json()
    assert got == [{"name": "my strat.pine", "version": 5, "kind": "strategy", "title": "Sniper"},
                   {"name": "old.pine", "version": None, "kind": None, "title": None},
                   {"name": "rsi.pine", "version": 6, "kind": "indicator", "title": "RSI twin"}]


def test_list_is_empty_without_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv(P.ENV, str(tmp_path / "none"))
    assert P.list_scripts() == []


def test_study_counts_as_an_indicator():
    assert P.script_meta("a.pine", '//@version=4\nstudy("Old")\n')["kind"] == "indicator"


def test_read_returns_the_text(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI}) as c:
        r = c.get("/api/pine/scripts/rsi.pine")
    assert r.status_code == 200 and r.text == RSI
    assert r.headers["content-type"].startswith("text/plain")


def test_unknown_and_bad_names_are_404(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI}) as c:
        assert c.get("/api/pine/scripts/none.pine").status_code == 404
        assert c.get("/api/pine/scripts/rsi.py").status_code == 404
        assert c.get("/api/pine/scripts/..%2Frsi.pine").status_code == 404
        assert c.get("/api/pine/scripts/scripts%2Frsi.pine").status_code == 404


def test_a_name_that_resolves_outside_the_folder_is_refused(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI}) as c:
        (tmp_path / "secret.pine").write_text("outside")
        os.symlink(tmp_path / "secret.pine", tmp_path / "scripts" / "link.pine")
        assert c.get("/api/pine/scripts/link.pine").status_code == 404
        assert P.script_path("link.pine") is None
        assert P.script_path("../secret.pine") is None
        assert P.script_path("rsi.pine") == (tmp_path / "scripts" / "rsi.pine").resolve()


def test_runtime_404_when_missing_or_not_the_pinned_build(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        assert c.get("/api/pine/runtime.js").status_code == 404
    with client(tmp_path / "b", monkeypatch, runtime=b"var PineTS = 1;") as c:
        r = c.get("/api/pine/runtime.js")
    assert r.status_code == 404 and "pinned" in r.json()["detail"]


def test_runtime_served_when_the_hash_matches(tmp_path, monkeypatch):
    body = b"var PineTS = {};"
    monkeypatch.setattr(P, "RUNTIME_SHA256", hashlib.sha256(body).hexdigest())
    with client(tmp_path, monkeypatch, runtime=body) as c:
        r = c.get("/api/pine/runtime.js")
    assert r.status_code == 200 and r.content == body
    assert r.headers["content-type"].startswith("application/javascript")


def test_routes_refuse_a_foreign_host(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI}) as c:
        assert c.get("/api/pine/scripts", headers={"host": "evil.example"}).status_code == 403


@pytest.mark.skipif(not P.runtime_path().is_file(), reason="the Pine runtime is not installed on this machine")
def test_the_installed_runtime_is_the_pinned_build():
    assert hashlib.sha256(P.runtime_path().read_bytes()).hexdigest() == P.RUNTIME_SHA256


def test_the_chart_app_serves_the_pine_routes(tmp_path, monkeypatch):
    """create_app registers pineapi.routes(): the script list and text reach the page through the real app."""
    monkeypatch.setenv(P.ENV, str(tmp_path / "pine"))
    (tmp_path / "pine" / "scripts").mkdir(parents=True)
    (tmp_path / "pine" / "scripts" / "rsi.pine").write_text(RSI)
    body = b"var PineTS = {};"
    monkeypatch.setattr(P, "RUNTIME_SHA256", hashlib.sha256(body).hexdigest())
    P.runtime_path().parent.mkdir(parents=True)
    P.runtime_path().write_bytes(body)
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    app = create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        assert c.get("/api/pine/scripts").json() == [{"name": "rsi.pine", "version": 6, "kind": "indicator", "title": "RSI twin"}]
        assert c.get("/api/pine/scripts/rsi.pine").text == RSI
        assert c.get("/api/pine/runtime.js").content == body
