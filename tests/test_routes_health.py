"""GET /api/health, /api/logs/{name}, /api/preopen-check: the Settings card "Health". Fake state files; read-only."""
from __future__ import annotations

import datetime as dt
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.routes import health

NOW = dt.datetime(2026, 10, 27, 21, 30, tzinfo=dt.timezone.utc)
WATCH = {"at_utc": "2026-10-27T21:16:56+00:00", "late": ["GC"], "thin": [], "silent": ["SI"], "refused": [{"root": "NQ", "session": "2026-10-26", "why": "x"}],
         "markets": {"NQ": {"open": True}, "ES": {"open": False}, "GC": {"open": True, "late_s": 300}, "SI": {"open": True, "silent_s": 600}},
         "leaving": [{}, {}], "level": "warn", "line": "data: GC is 5 min late"}
COVER = {"generated_at_utc": "2026-10-27T17:17:00+00:00", "sessions_per_root": 30,
         "summary": {"classes": {"whole": 2, "filling": 1, "lost": 1}, "filling": {"hole_hours": 22.0, "until_utc": "2026-10-28T00:00:00+00:00"}, "lost": {"hole_hours": 70.0}},
         "roots": {"NQ": [{"class": "whole"}, {"class": "filling"}], "ES": [{"class": "whole"}, {"class": "lost"}]}}


def client(state):
    app = FastAPI()
    health.register(app, state_dir=lambda: state)
    return TestClient(app)


def test_mask_hides_secret_values_and_keeps_words():
    m = health.mask
    assert m("[tradovate] a1: token renewed at 17:10:54 ET (normal)") == "[tradovate] a1: token renewed at 17:10:54 ET (normal)"
    assert m("GET /x?token=abc123&a=1") == "GET /x?token=***&a=1"
    assert m('{"password": "hunter2", "ok": 1}') == '{"password": "***", "ok": 1}'
    assert m("authorization: Bearer abc.def-ghi") == "authorization: ***"
    assert "eyJhbGciOi" not in m("t eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig_nat-ure end")
    assert "A" * 40 not in m("key " + "A" * 40 + " x")
    assert m("lab_nq_noise_band_eve_k03_stop2atr_t15_x") == "lab_nq_noise_band_eve_k03_stop2atr_t15_x"
    assert m("access_token=abc refresh_token: 'zz'") == "access_token=*** refresh_token: '***'"


def test_log_tail_is_whitelisted_capped_and_masked(tmp_path):
    (tmp_path / "service.log").write_text("\n".join(f"line {i} token=sekret{i}" for i in range(1000)) + "\n")
    (tmp_path / "secret.log").write_text("no\n")
    c = client(tmp_path)
    d = c.get("/api/logs/service?lines=5").json()
    assert d["available"] and d["lines"] == [f"line {i} token=***" for i in range(995, 1000)]
    assert len(c.get("/api/logs/service?lines=99999").json()["lines"]) == health.LINES_MAX
    assert c.get("/api/logs/secret").status_code == 404                    # not on the list: never read
    assert c.get("/api/logs/..%2Fconfig").status_code == 404
    assert c.get("/api/logs/charts").json() == {"available": False, "name": "charts", "reason": "No such log on this machine"}


def test_log_tail_reads_only_the_end_of_a_big_file(tmp_path):
    (tmp_path / "ticks.log").write_text("first\n" + "x" * 200 + "\n" * 1 + (("ab " * 33).strip() + "\n") * (health.TAIL_BYTES // 100 + 50))
    d = client(tmp_path).get("/api/logs/ticks?lines=500").json()
    assert "first" not in d["lines"] and all(len(x) == 98 for x in d["lines"]) and d["size"] > health.TAIL_BYTES


def test_health_reads_watch_and_coverage_for_every_market(tmp_path):
    (tmp_path / "data_watch.json").write_text(json.dumps(WATCH))
    (tmp_path / "tick_coverage.json").write_text(json.dumps(COVER))
    (tmp_path / "ticks.log").write_text("a\n")
    h = health.read(tmp_path, NOW)
    w = h["watch"]
    assert w["available"] and not w["stale"] and w["line"] == "GC is 5 min late" and w["refused"] == 1 and w["leaving"] == 2
    assert {m["root"]: m["state"] for m in w["markets"]} == {"NQ": "fine", "ES": "closed", "GC": "late", "SI": "silent"}
    assert [m["root"] for m in w["markets"] if m["state"] == "late"] and w["markets"][2]["minutes"] == 5
    cv = h["coverage"]
    assert cv["available"] and cv["classes"] == {"whole": 2, "filling": 1, "lost": 1} and cv["lost_hours"] == 70.0
    assert cv["roots"] == {"NQ": {"whole": 1, "filling": 1}, "ES": {"whole": 1, "lost": 1}}
    assert [x["name"] for x in h["logs"]] == ["ticks"] and h["logs"][0]["size"] == 2


def test_health_says_so_when_the_data_is_not_on_this_machine(tmp_path):
    h = health.read(tmp_path, NOW)
    assert h["watch"] == {"available": False, "reason": "No data check on this machine"}
    assert h["coverage"] == {"available": False, "reason": "No tick coverage report on this machine"}
    assert h["logs"] == []
    (tmp_path / "data_watch.json").write_text("{not json")
    assert health.read(tmp_path, NOW)["watch"]["available"] is False


def test_an_old_watch_reading_is_stale_not_current(tmp_path):
    (tmp_path / "data_watch.json").write_text(json.dumps(WATCH))
    assert health.read(tmp_path, NOW + dt.timedelta(hours=4))["watch"]["stale"] is True


def test_preopen_runs_once_a_window_drops_the_banners_own_rows_and_maps_levels(tmp_path, monkeypatch):
    calls = []
    rows = [("OK", "desk readiness", "ready"), ("WARN", "ticks NQ", "thin candles"), ("FAIL", "clock", "off"), ("OK", "power", "plugged in")]
    monkeypatch.setattr(health, "run_preopen", lambda: calls.append(1) or rows)
    c = client(tmp_path)
    assert c.get("/api/preopen-check").json() == {"available": True, "at": None, "age_s": None, "checks": []}   # a plain read never runs it
    d = c.get("/api/preopen-check?run=1").json()
    assert calls == [1] and d["available"] and d["worst"] == "bad"
    assert d["checks"] == [{"level": "warn", "label": "ticks NQ", "detail": "thin candles"}, {"level": "bad", "label": "clock", "detail": "off"},
                           {"level": "ok", "label": "power", "detail": "plugged in"}]
    c.get("/api/preopen-check?run=1")
    assert calls == [1]                                                   # asked again at once: the cached answer
    assert c.get("/api/preopen-check").json()["checks"] == d["checks"]


def test_preopen_off_the_mac_is_a_plain_note(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "run_preopen", lambda: None)
    d = client(tmp_path).get("/api/preopen-check?run=1").json()
    assert d["available"] is False and "Mac" in d["reason"]


def test_preopen_one_failed_run_is_a_note_not_an_error(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("lsof gone")
    monkeypatch.setattr(health, "run_preopen", boom)
    d = client(tmp_path).get("/api/preopen-check?run=1").json()
    assert d["available"] is True and d["checks"] == [{"level": "warn", "label": "Pre-open check", "detail": "could not run: RuntimeError: lsof gone"}]
