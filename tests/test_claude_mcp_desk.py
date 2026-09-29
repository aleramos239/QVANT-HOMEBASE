"""The desk-bridge MCP tools (homebase/claude_mcp/desk_tools.py, desk_client.py): each tool's
request shape and formatting against a fake desk (:8850) and a fake charts service (:8852), the
09:20-09:35 ET OPERATE refusal, the mcp_action journal tag, and data_coverage's local file read.
Route-level safety (no tool or route here can trade) is pinned in test_claude_mcp.py, which scans
this whole package; this file is about behavior, not that pin."""
from __future__ import annotations

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import pytest

from homebase.claude_mcp import tools
from homebase.claude_mcp.client import Client, ToolError
from homebase.claude_mcp.desk_client import DeskClient

ET = ZoneInfo("America/New_York")
IN_QUIET = dt.datetime(2026, 9, 29, 9, 27, tzinfo=ET)      # a Tuesday, inside 09:20-09:35 ET
OUTSIDE_QUIET = dt.datetime(2026, 9, 29, 10, 0, tzinfo=ET)


class Fake:
    """A fake HTTP service: canned answers per (method, path), every request recorded. Same shape
    as test_claude_mcp.py's Fake, duplicated here so this file stands alone against either the
    desk or the charts service (different route sets, same tiny server)."""

    def __init__(self):
        self.requests: list[dict] = []
        self.routes: dict = {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self, method):
                n = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                from urllib.parse import urlsplit
                path = urlsplit(self.path).path
                fake.requests.append({"method": method, "path": self.path, "route": path, "body": body,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                ans = fake.routes.get((method, path))
                if callable(ans):
                    ans = ans(body)
                status, payload = ans if isinstance(ans, tuple) else (200, ans)
                if ans is None:
                    status, payload = 404, {"detail": f"no route {path}"}
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self._serve("GET")

            def do_POST(self):
                self._serve("POST")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def last(self, method=None):
        rs = [r for r in self.requests if method is None or r["method"] == method]
        return rs[-1]

    def close(self):
        self.srv.shutdown()


STATUS = {
    "armed": True, "et_now": "2026-09-29T10:00:00-04:00",
    "accounts": {"sim041": {"connected": True, "account": "SIM41", "error": None, "cooldown_s": 0,
                            "open_position_count": 1, "working_orders": 2},
                "sim042": {"connected": False, "account": None, "error": "auth failed", "cooldown_s": 118.4,
                          "open_position_count": 0, "working_orders": 0}},
    "book": {"nq930": [{"account": "sim041"}]},
    "timer": {"strategies": {"nq930": {"stage": "gated", "late_reason": None, "wait_reason": None}}},
    "readiness": {"ready": False, "checks": [{"level": "bad", "label": "sim042", "detail": "not connected"},
                                             {"level": "ok", "label": "Power", "detail": "on power"}]},
}
JOURNAL = {"date": "2026-09-29", "count": 2,
          "events": [{"ts": 1, "et": "2026-09-29T09:00:00-04:00", "event": "broker_connected", "account": "sim041"},
                     {"ts": 2, "et": "2026-09-29T08:59:00-04:00", "event": "armed_toggled", "armed": True}]}


@pytest.fixture
def desk():
    f = Fake()
    f.routes.update({
        ("GET", "/api/status"): STATUS,
        ("GET", "/api/journal"): JOURNAL,
        ("POST", "/api/accounts/reconnect"): {"ok": True, "results": {"sim041": {"ok": True, "mode": "reconnect"}}},
        ("POST", "/api/accounts/remove"): {"ok": True, "removed": "sim042"},
    })
    yield f
    f.close()


@pytest.fixture
def charts():
    f = Fake()
    f.routes.update({("GET", "/api/tester/strategies"): []})
    yield f
    f.close()


def box(desk_fake, charts_fake=None, *, now=OUTSIDE_QUIET):
    b = tools.Toolbox(Client(charts_fake.url if charts_fake else "http://127.0.0.1:1"),
                      desk=DeskClient(desk_fake.url))
    b._now_et = lambda: now
    return b


# ---------------------------------------------------------------- reads

def test_desk_status_formats_accounts_book_and_timer(desk, charts):
    text = box(desk, charts).call("desk_status", {})
    assert "ARMED" in text and "sim041" in text and "SIM41" in text and "118.4s" in text
    assert "auth failed" in text and "nq930" in text and "gated" in text
    assert desk.last("GET")["route"] == "/api/status"


def test_desk_journal_passes_filters_and_formats_newest_first(desk, charts):
    text = box(desk, charts).call("desk_journal", {"date": "2026-09-29", "event": "broker_connected",
                                                    "account": "sim041", "limit": 10})
    req = desk.last("GET")
    assert req["route"] == "/api/journal"
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(req["path"]).query)
    assert q == {"date": ["2026-09-29"], "event": ["broker_connected"], "account": ["sim041"], "limit": ["10"]}
    assert "broker_connected" in text and "sim041" in text


def test_desk_readiness_formats_checks(desk, charts):
    text = box(desk, charts).call("desk_readiness", {})
    assert "NOT READY" in text and "sim042" in text and "not connected" in text and "Power" in text


def test_data_coverage_missing_report(desk, charts, monkeypatch, tmp_path):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    text = box(desk, charts).call("data_coverage", {})
    assert "No coverage report" in text


def test_data_coverage_reads_the_local_report(desk, charts, monkeypatch, tmp_path):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    report = {"generated_at_utc": "2026-09-29T00:00:00Z", "sessions_per_root": 30,
             "summary": {"complete": 1, "partial": 1, "hole_hours": 2.5, "live_only": 0, "missing": 1},
             "roots": {"NQ": [{"session": "2026-09-26", "status": "complete"},
                              {"session": "2026-09-25", "status": "partial", "hole_hours": 2.5, "missing_ids": 4},
                              {"session": "2026-09-24", "status": "missing"}]}}
    (tmp_path / "tick_coverage.json").write_text(json.dumps(report))
    text = box(desk, charts).call("data_coverage", {"root": "nq"})
    assert "2026-09-25" in text and "partial" in text and "2026-09-24" in text and "missing" in text
    assert "2.5" in text
    with pytest.raises(ToolError):
        (tmp_path / "tick_coverage.json").write_text("not json")
        box(desk, charts).call("data_coverage", {})


def test_services_health_reachability_pids_log_and_recorders(desk, charts, monkeypatch, tmp_path):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    (tmp_path / "ticks.log").write_text("line1\nline2\n")
    archive = tmp_path / "futures_ticks"
    year_dir = archive / "NQ" / str(OUTSIDE_QUIET.year)
    year_dir.mkdir(parents=True)
    (year_dir / "2026-09-26_NQZ6.csv.gz").write_bytes(b"x")

    class FakeProc:
        stdout = ("123\t0\tcom.ramosquant.homebase\n"
                 "-\t0\tcom.ramosquant.homebase-charts\n")

    b = box(desk, charts)
    b._tick_archive = archive
    b._launchctl = lambda args: FakeProc()
    text = b.call("services_health", {})
    assert "Desk (:8850): reachable" in text and "Charts (:8852): reachable" in text
    assert "desk=123" in text and "charts=not running" in text and "ticks=not running" in text
    assert "line1" in text and "line2" in text
    assert "NQ=" in text


def test_services_health_reports_an_unreachable_desk(desk, charts, monkeypatch, tmp_path):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    b = box(desk, charts)
    b._desk = DeskClient("http://127.0.0.1:1")     # nothing listens there
    b._launchctl = lambda args: type("P", (), {"stdout": ""})()
    text = b.call("services_health", {})
    assert "Desk (:8850): DOWN" in text


# ---------------------------------------------------------------- operate: quiet window + origin + source

def test_account_reconnect_sends_source_mcp_and_origin(desk, charts):
    b = box(desk, charts)
    text = b.call("account_reconnect", {"account": "sim041"})
    post = desk.last("POST")
    assert post["route"] == "/api/accounts/reconnect"
    assert post["body"] == {"source": "mcp", "account": "sim041"}
    assert post["headers"]["origin"] == desk.url and post["headers"]["content-type"] == "application/json"
    assert "sim041" in text and "ok" in text


def test_account_reconnect_all_when_no_account_given(desk, charts):
    box(desk, charts).call("account_reconnect", {})
    assert desk.last("POST")["body"] == {"source": "mcp"}


def test_account_remove_sends_source_mcp(desk, charts):
    text = box(desk, charts).call("account_remove", {"account": "sim042"})
    assert desk.last("POST")["body"] == {"account": "sim042", "source": "mcp"}
    assert "Removed sim042" in text


def test_account_remove_surfaces_a_refusal(desk, charts):
    desk.routes[("POST", "/api/accounts/remove")] = (409, {"detail": "account has an open position"})
    with pytest.raises(ToolError, match="open position"):
        box(desk, charts).call("account_remove", {"account": "sim041"})


def test_account_remove_description_matches_the_servers_actual_refusal_rules():
    """2026-09-29 review: the server refuses unless connected+seeded, flat (no position, no working
    order) and not placing/placed/live today -- the tool description must say so, not just "a
    position or a working order"."""
    from homebase.claude_mcp.desk_tools import SPECS
    desc = next(s["description"] for s in SPECS if s["name"] == "account_remove")
    for phrase in ("caches seeded", "no working order", "placing, placed or live",
                  "09:10-09:35"):
        assert phrase in desc, f"account_remove description missing {phrase!r}"


@pytest.mark.parametrize("tool,args", [
    ("account_reconnect", {}), ("account_remove", {"account": "sim041"}),
    ("export_start", {"root": "NQ", "type": "candles", "start": "2026-01-01", "end": "2026-01-02",
                      "timeframe": "1m"}),
    ("export_status", {"id": "20260101-000000-abcd1234"}),
])
def test_every_operate_tool_is_refused_in_the_930_window(desk, charts, tool, args):
    b = box(desk, charts, now=IN_QUIET)
    with pytest.raises(ToolError, match="09:20-09:35"):
        b.call(tool, args)
    assert not desk.requests and not charts.requests


def test_the_930_window_only_applies_on_weekdays_and_exact_minutes(desk, charts):
    saturday = dt.datetime(2026, 9, 26, 9, 27, tzinfo=ET)   # a Saturday at the same clock time
    b = box(desk, charts, now=saturday)
    b.call("account_reconnect", {})   # does not raise
    assert desk.requests


# ---------------------------------------------------------------- export

def test_export_start_and_status_request_shape(desk, charts):
    charts.routes[("POST", "/api/export/start")] = {"id": "20260101-000000-abcd1234"}
    charts.routes[("GET", "/api/export/20260101-000000-abcd1234")] = {
        "id": "20260101-000000-abcd1234", "status": "running", "phase": "reading",
        "sessions_done": 1, "sessions_total": 4, "rows": 1000}
    b = box(desk, charts)
    text = b.call("export_start", {"root": "NQ", "type": "candles", "start": "2026-01-01",
                                   "end": "2026-01-02", "timeframe": "1m"})
    assert charts.last("POST")["route"] == "/api/export/start"
    assert charts.last("POST")["body"] == {"root": "NQ", "type": "candles", "start": "2026-01-01",
                                           "end": "2026-01-02", "timeframe": "1m"}
    assert "20260101-000000-abcd1234" in text
    text = b.call("export_status", {"id": "20260101-000000-abcd1234"})
    assert "running" in text and "reading" in text and "1/4" in text


def test_export_start_guards_a_service_that_does_not_have_it_yet(desk, charts):
    # no ("POST", "/api/export/start") route registered -> the fake answers 404
    with pytest.raises(ToolError, match="feat/data-export"):
        box(desk, charts).call("export_start", {"root": "NQ", "type": "candles", "start": "2026-01-01",
                                                "end": "2026-01-02", "timeframe": "1m"})


# ---------------------------------------------------------------- the client's own allowlist

def test_desk_client_refuses_anything_off_its_exact_allowlist():
    c = DeskClient("http://127.0.0.1:1")
    with pytest.raises(ToolError):
        c.get("/api/accounts")            # close to allowed, but not exact
    with pytest.raises(ToolError):
        c.post("/api/status", {})         # a GET-only route, refused on POST
    with pytest.raises(ToolError):
        c.post("/api/kill", {})


def test_desk_client_env_must_stay_loopback(monkeypatch):
    monkeypatch.setenv("HOMEBASE_DESK_URL", "http://example.com:8850")
    with pytest.raises(ToolError):
        DeskClient()
