"""The Claude MCP server (homebase.claude_mcp): the JSON-RPC protocol, each tool's request shape against a
fake chart service, draft writes, and the pins that no tool -- tester or desk-bridge alike -- can trade,
arm, kill, flatten or book. The desk-bridge tools themselves (desk_status, account_reconnect, ...) are
tested in test_claude_mcp_desk.py against a fake desk; this file's pins cover the whole package."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from homebase import draftstore
from homebase.claude_mcp import protocol, tools
from homebase.claude_mcp.client import Client, ToolError

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "homebase" / "claude_mcp"
RID = "20260927-120000-nq930-abcd"
GID = "20260927-120001-nq930-beef"
WID = "20260927-120002-nq930-cafe"
TRADES = [{"date": "2024-03-05", "side": "long", "qty": 1, "entry_ms": 1709649001000, "entry_price": 110.25,
           "exit_ms": 1709649003000, "exit_price": 125.25, "exit_reason": "tp", "net": 296.0, "mae_usd": 0.0,
           "mfe_usd": 310.0, "seconds": 2.0},
          {"date": "2024-03-06", "side": "short", "qty": 1, "entry_ms": 1709735401000, "entry_price": 99.0,
           "exit_ms": 1709735461000, "exit_price": 104.0, "exit_reason": "sl", "net": -109.0, "mae_usd": 105.0,
           "mfe_usd": 20.0, "seconds": 60.0}]
COL = {"trades": 2, "net_profit": 187.0, "sharpe": 1.23, "win_rate": 50.0, "profit_factor": 2.7,
       "max_drawdown": -109.0, "avg_trade": 93.5, "t_stat": 0.6}
BUNDLE = {"run": {"id": RID, "strategy": {"id": "nq930", "name": "NQ 9:30 Straddle", "root": "NQ"},
                  "inputs": {"offset_pts": 10.0}, "range": {"label": "Build · Sep 2021 – Jun 2025"}, "qty": 1,
                  "commission": 4.0, "slippage_ticks": 1.0, "capital": 50000.0, "engine": "x", "fill_law": "tick replay",
                  "coverage": {"sessions": 3, "used": 2, "skipped_by_reason": {"no tape": 1}, "no_trade": []},
                  "report": {"summary": {"all": COL, "long": COL, "short": COL},
                             "by_year": [{"period": "2024", "trades": 2, "net": 187.0, "win_rate": 50.0,
                                          "profit_factor": 2.7, "max_drawdown": -109.0, "sharpe": 1.2}],
                             "skipped_by_error": 0}},
          "trades": TRADES, "equity": {}, "plots": {},
          "propsim": {"rules": {"label": "LucidFlex 50K"}, "headline": {"eval_pass_p": 0.5, "eval_pass_ci": [0.4, 0.6],
                                                                        "bust_p": 0.3, "timeout_p": 0.2,
                                                                        "median_days_to_pass": 9,
                                                                        "funded_payout_p": 0.4,
                                                                        "funded_expected_cheque": 1500}}}
CATALOG = [{"id": "nq930", "name": "NQ 9:30 Straddle", "root": "NQ",
            "inputs": [{"key": "offset_pts", "type": "float", "default": 10.0, "min": 0, "max": 500}]}]


class Fake:
    """A fake chart service: canned answers per (method, path), every request recorded."""

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
                fake.requests.append({"method": method, "path": self.path, "body": body,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                ans = fake.routes.get((method, self.path))
                if callable(ans):
                    ans = ans(body)
                status, payload = ans if isinstance(ans, tuple) else (200, ans)
                if ans is None:
                    status, payload = 404, {"detail": f"no route {self.path}"}
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


@pytest.fixture
def fake():
    f = Fake()
    f.routes.update({
        ("GET", "/api/tester/strategies"): CATALOG,
        ("GET", "/api/tester/strategies/nq930/source"): {"id": "nq930", "files": [{"path": "homebase/strategies/nq930.py",
                                                                                   "text": "class NQ930: ..."}]},
        ("POST", "/api/tester/run"): {"id": RID},
        ("GET", f"/api/tester/run/{RID}"): {"id": RID, "status": "done"},
        ("GET", f"/api/tester/run/{RID}/bundle"): BUNDLE,
        ("GET", f"/api/tester/grid/{GID}/cell/1/bundle"): BUNDLE,
        ("POST", "/api/tester/grid"): {"id": GID},
        ("GET", f"/api/tester/grid/{GID}"): {"id": GID, "strategy": "nq930", "status": "done", "done": 2, "total": 2,
                                             "looks": 40, "axes": [{"key": "sl_pts"}, {"key": "tp_pts"}],
                                             "cells": [{"i": 0, "params": {"sl_pts": 4, "tp_pts": 10}, "status": "done",
                                                        "summary": {**COL, "net_profit": 50.0}},
                                                       {"i": 1, "params": {"sl_pts": 5, "tp_pts": 10}, "status": "done",
                                                        "summary": COL}]},
        ("POST", "/api/tester/walkforward"): {"id": WID},
        ("GET", f"/api/tester/walkforward/{WID}"): {"id": WID, "status": "done"},
        ("GET", f"/api/tester/walkforward/{WID}/result"): {
            "scheme": {"ratio": "1:3", "metric_label": "Net $", "min_trades": 5}, "n_cells": 4, "n_steps": 2,
            "looks": 8, "window": {"start": "2021-01", "end": "2021-06"},
            "stitched": {"stats": COL, "n_months": 3, "per_month": {"net_profit": 62.3}, "uncovered": []},
            "stitched_is": {"stats": COL, "n_months": 1, "per_month": {"net_profit": 187.0}},
            "drop": {"net_profit_per_month": -124.7, "pct": -66.7, "sharpe": -0.5},
            "stability": {"changes": 1}, "steps": [{"k": 0, "select": "2021-01", "test": ["2021-02", "2021-04"],
                                                    "params": {"sl_pts": 4}, "is": COL, "oos": COL, "stitched": True}]},
        ("POST", "/api/tester/montecarlo"): {"paths": 500, "mode": "shuffle", "unit": "day", "n_trades": 2,
                                             "n_days": 2, "seed": 7, "drawdown": {"p5": -50, "p95": -300},
                                             "final_net": {"p50": 187}, "losing_streak": {"p50": 1}, "floor": 2000,
                                             "p_ruin": 0.01, "p_prop_pass": 0.4, "prop_rules": {"label": "LucidFlex 50K"},
                                             "actual": {"max_dd": -109, "worse_than_pct": 40.0}},
        ("POST", "/api/tester/propsim"): BUNDLE["propsim"],
        ("GET", "/api/tester/prop-rules"): [{"id": "lucid@1", "name": "LucidFlex 50K", "version": "1", "confirmed": True}],
        ("GET", "/api/tester/runs"): [{"id": RID, "strategy": "nq930", "status": "done", "range": {"label": "R"},
                                       "trades": 2, "net_profit": 187.0}],
        ("GET", "/api/tester/grids"): [{"id": GID, "strategy": "nq930", "status": "done", "done": 2, "total": 2,
                                        "axes": ["sl_pts", "tp_pts"]}],
        ("POST", "/api/tester/show"): lambda body: {"ok": True, "pages": 1, **body},
    })
    yield f
    f.srv.shutdown()


def box(fake):
    return tools.Toolbox(Client(fake.url), sleep=lambda s: None)


def rpc(srv, method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    return srv.handle(msg)


# ---------------------------------------------------------------- the protocol

def test_initialize_list_ping_and_errors():
    srv = protocol.Server(tools.Toolbox(Client("http://127.0.0.1:1")))
    init = rpc(srv, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "t", "version": "0"}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["capabilities"] == {"tools": {"listChanged": False}}
    assert init["serverInfo"]["name"] == "homebase"
    assert rpc(srv, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == protocol.PROTOCOLS[0]
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc(srv, "ping")["result"] == {}
    listed = rpc(srv, "tools/list")["result"]["tools"]
    assert [t["name"] for t in listed] == tools.Toolbox().names()
    for t in listed:
        assert t["description"] and t["inputSchema"]["type"] == "object"
        json.dumps(t)
    assert rpc(srv, "nope")["error"]["code"] == -32601
    assert rpc(srv, "tools/call", {"name": "place_order", "arguments": {}})["error"]["code"] == -32602
    assert srv.handle({"id": 3})["error"]["code"] == -32600
    bad_args = rpc(srv, "tools/call", {"name": "trades", "arguments": {"run_id": RID, "bogus": 1}})["result"]
    assert bad_args["isError"] and "bogus" in bad_args["content"][0]["text"]


def test_serve_speaks_newline_delimited_json():
    srv = protocol.Server(tools.Toolbox(Client("http://127.0.0.1:1")))
    inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n\nnot json\n'
                      '{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    out = io.StringIO()
    protocol.serve(inp, out, srv)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines == [{"jsonrpc": "2.0", "id": 1, "result": {}},
                     {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}]


def test_the_module_runs_over_stdio_against_a_fake_service(fake):
    """python -m homebase.claude_mcp end to end: initialize, tools/list, one tools/call hitting the fake."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_strategies", "arguments": {}}}]
    p = subprocess.run([sys.executable, "-m", "homebase.claude_mcp"], cwd=REPO, capture_output=True, text=True,
                       input="".join(json.dumps(m) + "\n" for m in msgs), timeout=60,
                       env={**os.environ, "HOMEBASE_CHARTS_URL": fake.url})
    out = [json.loads(x) for x in p.stdout.splitlines()]
    assert [o["id"] for o in out] == [1, 2, 3]
    call = out[2]["result"]
    assert call["isError"] is False and "nq930" in call["content"][0]["text"] and "offset_pts" in call["content"][0]["text"]
    assert fake.last()["path"] == "/api/tester/strategies"


def test_a_tool_error_is_a_result_with_isError(fake):
    fake.routes[("POST", "/api/tester/run")] = (400, {"detail": "paused for the 9:30 window: no backtest starts "
                                                                "09:20–09:35 ET on weekdays"})
    srv = protocol.Server(box(fake))
    res = rpc(srv, "tools/call", {"name": "backtest", "arguments": {"strategy": "nq930"}})["result"]
    assert res["isError"] is True and "09:20–09:35" in res["content"][0]["text"]


# ---------------------------------------------------------------- request shapes

def test_every_request_carries_loopback_origin_and_json(fake):
    b = box(fake)
    b.call("backtest", {"strategy": "nq930"})
    post = fake.last("POST")
    assert post["headers"]["origin"] == fake.url and post["headers"]["content-type"] == "application/json"
    assert post["headers"]["host"] == fake.url.removeprefix("http://")


def test_backtest_request_shape_and_summary(fake):
    b = box(fake)
    text = b.call("backtest", {"strategy": "nq930", "inputs": {"offset_pts": 12}, "costs": {"qty": 2},
                               "prop_rules": "lucid@1"})
    assert fake.requests[0]["body"] == {"strategy": "nq930", "inputs": {"offset_pts": 12}, "range": {"kind": "research"},
                                        "qty": 2, "prop_rules": "lucid@1"}
    for want in (RID, "$187", "1.23", "50.0%", "2.70", "-$109", "By year", "pass 50.0%", "show_on_chart",
                 "Build · Sep 2021 – Jun 2025"):
        assert want in text, want
    assert "reads the test days" not in text
    b.call("backtest", {"strategy": "nq930", "range": {"preset": "2022-2024"}})
    assert fake.last("POST")["body"]["range"] == {"kind": "custom", "start": "2022-01-01", "end": "2024-12-31"}
    b.call("backtest", {"strategy": "nq930", "range": {"preset": "custom", "start": "2023-01-01", "end": "2023-06-30"}})
    assert fake.last("POST")["body"]["range"] == {"kind": "custom", "start": "2023-01-01", "end": "2023-06-30"}
    with pytest.raises(ToolError):
        b.call("backtest", {"strategy": "nq930", "range": {"preset": "custom", "start": "2023-01-01"}})
    with pytest.raises(ToolError):
        b.call("backtest", {"strategy": "nq930", "range": {"walkforward": 3}})


def test_range_presets_match_the_page():
    """build (the default) and test are the blueprint's days, and the three copies of their dates agree:
    the server's rules (backtest/discipline.py), this connector, the page's range pill (tester.js)."""
    from homebase.backtest import discipline
    assert tools.range_body(None) == tools.range_body({}) == tools.range_body({"preset": "build"}) == {"kind": "research"}
    assert tools.range_body({"preset": "test"}, today="2026-10-06") == {"kind": "custom", "start": "2025-07-01",
                                                                        "end": "2026-10-06"}
    assert tools.range_body({"preset": "all"}, today="2026-09-27") == {"kind": "custom", "start": "2021-01-01",
                                                                       "end": "2026-09-27"}
    build, test = tools.PRESETS["build"], tools.PRESETS["test"]
    assert build == (discipline.RESEARCH_START.isoformat(), discipline.RESEARCH_END.isoformat())
    assert test == (discipline.HOLDOUT_START.isoformat(), None)
    js = (REPO / "homebase" / "static" / "charts" / "tester.js").read_text()
    page = {i: (s, e or None) for i, s, e in re.findall(
        r"\{ id: '(\w+)', label: '[^']*', start: '([\d-]+)', end: (?:'([\d-]+)'|null) \}", js)}
    assert page == {"research": build, "test": test, "all": tools.PRESETS["all"]}


def test_the_old_preset_names_still_run_as_their_own_dates():
    """A call written before the blueprint's dates (2026-10-06) keeps working. The old names are plain date
    windows: 2021-2024 is no longer the default, so it no longer rides on {kind: research}."""
    assert tools.range_body({"preset": "2021-2024"}) == {"kind": "custom", "start": "2021-01-01", "end": "2024-12-31"}
    assert tools.range_body({"preset": "2022-2024"}) == {"kind": "custom", "start": "2022-01-01", "end": "2024-12-31"}
    assert tools.range_body({"preset": "2025-2026"}, today="2026-09-27") == {"kind": "custom", "start": "2025-01-01",
                                                                             "end": "2026-09-27"}
    preset = tools._RANGE["properties"]["preset"]
    assert preset["default"] == "build" and preset["enum"][:3] == ["build", "test", "all"]
    assert {"2021-2024", "2022-2024", "2025-2026", "custom"} <= set(preset["enum"])
    with pytest.raises(ToolError, match="range.preset"):
        tools.range_body({"preset": "research"})


def test_every_chat_reads_the_blueprints_dates():
    """The connector's instructions and the range description carry the house law to every chat."""
    srv = protocol.Server(tools.Toolbox(Client("http://127.0.0.1:1")))
    text = rpc(srv, "initialize", {"protocolVersion": "2025-06-18"})["result"]["instructions"]
    desc = tools._RANGE["description"]
    for t in (text, desc):
        assert "research/edge-library/BLUEPRINT.md section 2" in t and "research window" not in t
        assert "build days" in t and "2021-09-22" in t and "2025-06-30" in t
        assert "test days" in t and "2025-07-01" in t
        assert "once and only for a locked strategy, never for a quick look or \"all data\"" in t
    listed = {t["name"]: t for t in rpc(srv, "tools/list")["result"]["tools"]}
    for name in ("backtest", "heatmap", "walkforward"):
        assert listed[name]["inputSchema"]["properties"]["range"]["description"] == desc


def test_a_run_that_read_the_test_days_says_so():
    late = {**BUNDLE, "run": {**BUNDLE["run"], "holdout": True, "range": {"label": "Test · Jul 2025 → 2026-10-06"}}}
    head = tools.bundle_summary(late, {"run_id": RID}).splitlines()[0]
    assert head.endswith("Test · Jul 2025 → 2026-10-06 · reads the test days")


def test_a_long_run_returns_its_id_when_the_wait_runs_out(fake):
    fake.routes[("GET", f"/api/tester/run/{RID}")] = {"id": RID, "status": "queued", "paused": "paused for the 9:30 window"}
    text = box(fake).call("backtest", {"strategy": "nq930", "wait_s": 0})
    assert "still going" in text and RID in text and "paused for the 9:30 window" in text


def test_heatmap_walkforward_mc_prop_and_lists(fake):
    b = box(fake)
    axes = [{"key": "sl_pts", "values": [4, 5]}, {"key": "tp_pts", "values": [10]}]
    text = b.call("heatmap", {"strategy": "nq930", "axes": axes, "max_cells": 10})
    assert fake.last("POST")["path"] == "/api/tester/grid"
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "axes": axes, "range": {"kind": "research"},
                                         "max_cells": 10}
    assert "Best net: cell 1" in text and "Looks this strategy: 40" in text
    text = b.call("walkforward", {"strategy": "nq930", "axes": axes, "ratio": 2, "metric": "sharpe", "min_trades": 3})
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "axes": axes, "range": {"kind": "research"},
                                         "test_months": 2, "metric": "sharpe", "min_trades": 3}
    assert "stitched OOS" in text and "Drop IS->OOS" in text
    text = b.call("montecarlo", {"run_id": RID, "paths": 500})
    assert fake.last("POST")["body"] == {"run_id": RID, "paths": 500} and "P(prop pass" in text
    b.call("montecarlo", {"grid_id": GID, "cell": 1, "mode": "bootstrap"})
    assert fake.last("POST")["body"] == {"grid_id": GID, "cell": 1, "mode": "bootstrap"}
    with pytest.raises(ToolError):
        b.call("montecarlo", {"run_id": RID, "grid_id": GID, "cell": 1})
    text = b.call("prop_eval", {"run_id": RID, "prop_rules": "lucid@1"})
    assert fake.last("POST")["body"] == {"run_id": RID, "prop_rules": "lucid@1"} and "pass 50.0%" in text
    assert "lucid@1" in b.call("list_prop_rules", {})
    assert RID in b.call("list_runs", {})
    assert GID in b.call("list_runs", {"kind": "heatmaps"}) and fake.last()["path"] == "/api/tester/grids"


def test_get_run_and_trades(fake):
    b = box(fake)
    assert "NQ 9:30 Straddle" in b.call("get_run", {"run_id": RID})
    assert "Heat-map cell" in b.call("get_run", {"grid_id": GID, "cell": 1})
    text = b.call("trades", {"run_id": RID, "sort": "net", "limit": 1})
    rows = [ln for ln in text.splitlines() if ln.startswith("| 1 ")]
    assert rows and "-$109" in rows[0] and "More: trades" in text      # worst first keeps the ORIGINAL index (#1)
    assert "09:30:01" in b.call("trades", {"run_id": RID})             # ET wall clock


def test_show_on_chart_request_shape(fake):
    b = box(fake)
    text = b.call("show_on_chart", {"run_id": RID, "focus": {"trade_index": 1}})
    assert fake.last("POST") ["path"] == "/api/tester/show"
    assert fake.last("POST")["body"] == {"run_id": RID, "focus": {"trade_index": 1}} and "1 open chart page" in text
    b.call("show_on_chart", {"grid_id": GID, "cell": 1})
    assert fake.last("POST")["body"] == {"grid_id": GID, "cell": 1}
    fake.routes[("POST", "/api/tester/show")] = {"ok": True, "pages": 0}
    assert "No chart page is open" in b.call("show_on_chart", {"run_id": RID})


def test_cancel_uses_the_tester_cancel_routes_only(fake):
    b = box(fake)
    for kind, arg in (("run", "run_id"), ("grid", "grid_id"), ("walkforward", "walkforward_id")):
        fake.routes[("POST", f"/api/tester/{kind}/X1/cancel")] = {"status": "cancelled"}
        assert "cancelled" in b.call("cancel", {arg: "X1"})
        assert fake.last("POST")["path"] == f"/api/tester/{kind}/X1/cancel"
    with pytest.raises(ToolError):
        b.call("cancel", {})
    with pytest.raises(ToolError):
        b.call("cancel", {"run_id": "a", "grid_id": "b"})


def test_read_strategy_includes_source_and_the_template(fake):
    text = box(fake).call("read_strategy", {"strategy": "nq930"})
    assert "class NQ930" in text and "DRAFT TEMPLATE" in text and "ctx.stop_entry" in text
    with pytest.raises(ToolError):
        box(fake).call("read_strategy", {"strategy": "nope"})


def test_write_strategy_and_delete_draft(fake, drafts_dir):
    b = box(fake)
    fake.routes[("GET", "/api/tester/strategies")] = CATALOG + [
        {"id": "draft_nq_orb", "name": "My draft", "root": "NQ", "draft": True, "session_independent": True,
         "inputs": [{"key": "offset_pts", "default": 10.0}]}]
    text = b.call("write_strategy", {"name": "nq_orb", "code": draftstore.DRAFT_TEMPLATE})
    assert (drafts_dir / "nq_orb.py").read_text() == draftstore.DRAFT_TEMPLATE
    assert "Listed as draft_nq_orb" in text
    fake.routes[("GET", "/api/tester/strategies")] = CATALOG + [
        {"id": "draft_bad", "name": "bad", "draft": True, "error": "ModuleNotFoundError: No module named 'x'"}]
    with pytest.raises(ToolError, match="cannot read it: ModuleNotFoundError"):
        b.call("write_strategy", {"name": "bad", "code": draftstore.DRAFT_TEMPLATE})
    with pytest.raises(ToolError, match="literal"):          # refused before anything is written
        b.call("write_strategy", {"name": "dyn", "code": draftstore.DRAFT_TEMPLATE.replace('root = "NQ"', 'root = "N" + "Q"')})
    with pytest.raises(ToolError, match="module name"):
        b.call("write_strategy", {"name": "json", "code": draftstore.DRAFT_TEMPLATE})
    with pytest.raises(ToolError, match="built-in"):
        b.call("write_strategy", {"name": "nq930", "code": "x = 1\n"})
    with pytest.raises(ToolError, match="SyntaxError"):
        b.call("write_strategy", {"name": "oops", "code": "def f(:\n"})
    assert "Deleted" in b.call("delete_draft", {"name": "nq_orb"}) and not (drafts_dir / "nq_orb.py").exists()
    assert sorted(p.name for p in drafts_dir.iterdir()) == ["bad.py"]


def test_set_group_files_a_strategy_and_list_strategies_shows_each_group(fake, drafts_dir):
    b = box(fake)
    fake.routes[("GET", "/api/tester/strategies")] = CATALOG + [
        {"id": "draft_nq_orb", "name": "My draft", "root": "NQ", "draft": True, "inputs": []}]
    assert "group" not in b.call("list_strategies", {}).lower()          # nothing filed: the listing is as it was
    text = b.call("set_group", {"strategy": "draft_nq_orb", "group": "Opening range"})
    assert "draft_nq_orb" in text and '"Opening range"' in text
    b.call("set_group", {"strategy": "nq930", "group": "opening range"})  # the group that exists, whatever its capitals
    assert json.loads((drafts_dir / "groups.json").read_text()) == {
        "groups": ["Opening range"], "members": {"draft_nq_orb": "Opening range", "nq930": "Opening range"}}
    listed = b.call("list_strategies", {})
    line = {ln.split(":")[0]: ln for ln in listed.splitlines() if ln.startswith("- ")}
    assert line["- nq930"].endswith('· group "Opening range"') and "DRAFT" not in line["- nq930"]
    assert line["- draft_nq_orb"].endswith('· DRAFT · group "Opening range"')
    assert listed.splitlines()[-1] == "Groups: Opening range (2)"
    for nothing in ({"group": ""}, {}):                                   # out of its group; the group stays, empty
        b.call("set_group", {"strategy": "nq930", "group": "Opening range"})
        assert "ungrouped" in b.call("set_group", {"strategy": "nq930", **nothing})
    b.call("set_group", {"strategy": "draft_nq_orb"})
    listed = b.call("list_strategies", {})
    assert '· group "' not in listed and listed.splitlines()[-1] == "Groups: Opening range (0)"
    with pytest.raises(ToolError, match="no strategy 'nope'"):
        b.call("set_group", {"strategy": "nope", "group": "Gold"})
    with pytest.raises(ToolError, match="Ungrouped"):
        b.call("set_group", {"strategy": "nq930", "group": "Ungrouped"})
    assert {r["method"] for r in fake.requests} == {"GET"}                # it writes the one file itself, no route
    assert sorted(p.name for p in drafts_dir.iterdir()) == ["groups.json"]
    # a file that does not read: the listing still answers and says so; nothing writes over it
    (drafts_dir / "groups.json").write_text("{not json")
    listed = b.call("list_strategies", {})
    assert "- nq930" in listed and "groups.json" in listed.splitlines()[-1]
    with pytest.raises(ToolError, match="groups.json"):
        b.call("set_group", {"strategy": "nq930", "group": "Gold"})
    assert (drafts_dir / "groups.json").read_text() == "{not json"


def test_the_client_refuses_anything_but_loopback_and_tester_routes(monkeypatch):
    monkeypatch.setenv("HOMEBASE_CHARTS_URL", "http://example.com:8852")
    with pytest.raises(ToolError):
        Client()
    with pytest.raises(ToolError):
        Client("http://127.0.0.1:1").get("/api/orders")


# ---------------------------------------------------------------- no trading, ever

# "desk" and "account" are no longer forbidden IN A TOOL NAME: the desk-bridge tools read the desk
# and its accounts by design (desk_status, account_reconnect, account_remove). What stays forbidden
# is anything that places, arms, kills, flattens or books -- see the route-level pin below, which is
# the real enforcement (DeskClient's exact allowlist, never a tool name spelling).
FORBIDDEN_TOOL_WORDS = ("order", "trade_", "place", "arm", "kill", "flatten", "book", "paper",
                        "position", "broker", "live", "setting", "market_data", "algo", "bot")


def test_no_tool_can_trade():
    names = tools.Toolbox().names()
    assert names == ["list_strategies", "read_strategy", "backtest", "heatmap", "walkforward", "montecarlo",
                     "prop_eval", "list_prop_rules", "list_runs", "get_run", "trades", "show_on_chart",
                     "cancel", "write_strategy", "delete_draft", "set_group", "blueprint_blocks", "blueprint_card",
                     "blueprint_code_check", "blueprint_build", "blueprint_lock", "blueprint_test", "blueprint_sim", "blueprint_portfolio",
                     "blueprint_eval_card", "blueprint_status", "blueprint_heatmap", "blueprint_mc", "desk_status",
                     "desk_journal", "desk_readiness", "data_coverage", "services_health", "account_reconnect",
                     "account_remove", "export_start", "export_status"]
    for n in names:
        assert not any(w in n for w in FORBIDDEN_TOOL_WORDS), n


# The desk-bridge tools (homebase/claude_mcp/desk_client.py, desk_tools.py) legitimately say "desk",
# "8850" and "/api/accounts/..." now -- the pin moves from "never mention the desk" to "never reach a
# route that trades". FORBIDDEN_ROUTES is the spec's own list; ALLOWED_DESK_ROUTES is DeskClient's
# entire allowlist (checked against the live constants, not just this copy of it).
FORBIDDEN_ROUTES = ("/api/order", "/api/kill", "/api/arm", "/api/book", "/api/strategy",
                    "/api/chart-trading", "/api/flatten", "/api/desk/", "/api/paper", "/api/settings",
                    "/api/bot", "/api/md", "/api/accounts/add")


def test_the_package_only_ever_reaches_known_safe_routes():
    """Every /api/... path string anywhere in the package must be a tester route, an export route,
    or one of DeskClient's four exact desk routes -- and none of the routes the spec calls out
    (order/kill/arm/book/strategy/chart-trading/flatten, or the charts service's desk relay that
    places orders) may appear at all, by name or by tool."""
    from homebase.claude_mcp import desk_client
    src = {p.name: p.read_text() for p in MCP_DIR.glob("*.py")}
    assert src
    assert desk_client.ALLOWED_GET == frozenset({"/api/status", "/api/journal"})
    assert desk_client.ALLOWED_POST == frozenset({"/api/accounts/reconnect", "/api/accounts/remove"})
    allowed_desk = desk_client.ALLOWED_GET | desk_client.ALLOWED_POST
    for name, text in src.items():
        for bad in FORBIDDEN_ROUTES:
            assert bad not in text, (name, bad)
        for path in re.findall(r"/api/[\w/{}.-]*", text):
            ok = path.startswith("/api/tester/") or path.startswith("/api/export/") or path in allowed_desk
            assert ok, (name, path)
    imports = set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", "\n".join(src.values()), re.M))
    homebase_imports = {i for i in imports if i.startswith(("homebase", ".."))}
    assert homebase_imports <= {"..", "homebase.claude_mcp"}, homebase_imports     # draftstore, paths via `..`
    assert "from .. import draftstore" in src["tools.py"]
    assert "from .. import paths" in src["desk_tools.py"]


CWID = "20260927-120003-nq930-c0de"
_SHARED = {"stats": COL, "per_month": {"net_profit": 50.0}, "legs": {"n": 4, "pct_profitable": 50.0},
           "span": ["2021-02", "2021-04"]}


def test_walkforward_on_a_compare_job_returns_the_side_by_side_summary_or_one_scheme(fake):
    fake.routes.update({
        ("GET", f"/api/tester/walkforward/{CWID}"): {"id": CWID, "status": "done",
                                                     "walkforward": {"compare": True, "test_months": None}},
        ("GET", f"/api/tester/walkforward/{CWID}/compare"): {
            "compare": True, "scheme": {"metric_label": "Net $", "min_trades": 5},
            "window": {"start": "2021-01", "end": "2021-06"}, "looks": 30,
            "looks_basis": {"cells": 2, "select_months": 5, "choice_penalty": 3},
            "shared_months": {"n": 3, "span": ["2021-02", "2021-04"]},
            "phase_check": {"warning": "the start month moves these more than the ratio does"},
            "note": "picking the best ratio is itself a selection",
            "schemes": [{"ratio": f"1:{n}", "test_months": n, "stats": COL, "span": ["2021-02", "2021-06"],
                         "per_month": {"net_profit": 37.4}, "legs": {"n": 5 // n, "pct_profitable": 40.0},
                         "phase_spread": {"net_profit": {"min": -10.0, "max": 90.0, "mean": 40.0}},
                         "shared": _SHARED} for n in (1, 2, 3)]},
        ("GET", f"/api/tester/walkforward/{CWID}/result?test_months=2"):
            fake.routes[("GET", f"/api/tester/walkforward/{WID}/result")],
    })
    b = box(fake)
    text = b.call("walkforward", {"walkforward_id": CWID})
    assert fake.last()["path"] == f"/api/tester/walkforward/{CWID}/compare"
    assert "Shared months (2021-02–2021-04, 3 months" in text and "Full spans" in text
    assert "| 1:1 |" in text and "| 1:3 |" in text and "30 looks (2 cells x 5 selection months x 3" in text
    assert "Phase check: the start month moves these more than the ratio does." in text
    assert "-$10..$90 (mean $40)" in text and "picking the best ratio is itself a selection" in text
    assert "stitched_is" not in text and "Drop IS->OOS" not in text
    text = b.call("walkforward", {"walkforward_id": CWID, "test_months": 2})
    assert fake.last()["path"] == f"/api/tester/walkforward/{CWID}/result?test_months=2"
    assert "stitched OOS" in text
    with pytest.raises(ToolError):
        b.call("walkforward", {"walkforward_id": CWID, "test_months": 4})
    # an ordinary job: no test_months -> /result, exactly as before
    b.call("walkforward", {"walkforward_id": WID})
    assert fake.last()["path"] == f"/api/tester/walkforward/{WID}/result"
