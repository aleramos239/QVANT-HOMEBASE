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
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {"offset_pts": 12}, "range": {"kind": "wf_is", "root": "NQ"},
                                         "qty": 2, "prop_rules": "lucid@1"}
    for want in (RID, "$187", "1.23", "50.0%", "2.70", "-$109", "By year", "pass 50.0%", "show_on_chart",
                 "Build · Sep 2021 – Jun 2025"):
        assert want in text, want
    assert "reads the test days" not in text
    said = {"owner_said": "run it on 2022-2024"}
    b.call("backtest", {"strategy": "nq930", "range": {"preset": "2022-2024"}, **said})
    assert fake.last("POST")["body"]["range"] == {"kind": "custom", "start": "2022-01-01", "end": "2024-12-31"}
    b.call("backtest", {"strategy": "nq930", "range": {"preset": "custom", "start": "2023-01-01", "end": "2023-06-30"}, **said})
    assert fake.last("POST")["body"]["range"] == {"kind": "custom", "start": "2023-01-01", "end": "2023-06-30"}
    with pytest.raises(ToolError):
        b.call("backtest", {"strategy": "nq930", "range": {"preset": "custom", "start": "2023-01-01"}, **said})
    with pytest.raises(ToolError):
        b.call("backtest", {"strategy": "nq930", "range": {"walkforward": 3}, **said})


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
    assert "default" not in preset and preset["enum"][:3] == ["build", "test", "all"]    # no range = the 3:1 in-sample months
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
        assert "2021-09-22" in t and "2025-06-30" in t and "2025-07-01" in t
    assert "once and only for a locked strategy, never for a quick look or \"all data\"" in text     # old ideas' route
    assert "once and only for a locked strategy" not in desc                                           # retired for runs
    assert "3:1 in-sample months" in desc and "ONLY when the owner says so" in desc and "owner_said" in desc
    assert ("walkforward (its old scheme \"pick\" only; a fixed one takes no range): the build days, 2021-09-22 -> 2025-06-30"
            in desc)                                                     # true for both tools (final review, 2026-10-21)
    listed = {t["name"]: t for t in rpc(srv, "tools/list")["result"]["tools"]}
    for name in ("backtest", "walkforward"):            # walkforward: its old scheme ("pick") only
        assert listed[name]["inputSchema"]["properties"]["range"]["description"] == desc
    assert "range" not in listed["heatmap"]["inputSchema"]["properties"]   # a heat map runs on the 3:1 in-sample months only


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
    b.call("heatmap", {"strategy": "nq930", "axes": axes, "max_cells": 10, "owner_said": "heat map it"})
    assert fake.last("POST")["path"] == "/api/tester/walkforward"          # a new heat map: the fixed 3:1 in-sample table
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "axes": axes, "max_cells": 10,
                                         "scheme": "fixed", "step_months": 4}
    text = b.call("heatmap", {"grid_id": GID})                              # an old heat map still reads
    assert "Best net: cell 1" in text and "Looks this strategy: 40" in text
    text = b.call("walkforward", {"strategy": "nq930", "axes": axes, "scheme": "pick", "ratio": 2, "metric": "sharpe",
                                  "min_trades": 3, "owner_said": "use the old 1:2 one"})
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "axes": axes, "range": {"kind": "research"},
                                         "scheme": "pick", "test_months": 2, "metric": "sharpe", "min_trades": 3}
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
    assert sorted(p.name for p in drafts_dir.iterdir()) == [".trash", "bad.py"]       # deleted = moved to the trash, not unlinked
    assert [p.name.split(".")[0] for p in (drafts_dir / ".trash").iterdir()] == ["nq_orb"]


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
                     "blueprint_eval_card", "blueprint_status", "blueprint_heatmap", "blueprint_mc",
                     "blueprint_wf", "blueprint_wf_pick", "blueprint_wf_oos", "desk_status",
                     "desk_journal", "desk_readiness", "data_coverage", "services_health", "account_reconnect",
                     "account_remove", "export_start", "export_status"]
    for n in names:
        if n == "pipeline_book":            # THE BOOK of the strategy pipeline: the strategies the owner approved, a read.
            continue                        # Nothing of an account is booked by it (the route-level pin below holds that)
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


# ---------------------------------------------------------------- hm40 + the fixed 3:1 block walk-forward (2026-10-20)

FWID = "20261020-120004-nq930-f1ed"
_REC = {"win_rate": 55.0, "breakeven": 50.0, "wr_minus_be": 5.0, "trades": 100, "per_week": 2.5, "avg_trade": 10.0,
        "avg_r": 0.1, "net": 1000.0, "pf": 1.2, "sharpe": 0.8, "max_dd": -500.0}
FIXED = {"scheme": "fixed", "step_months": 4, "rolling": False, "stitch": "blocks", "window": {"start": "2021-10", "end": "2025-08"},
         "blocks": [{"i": 0, "is": ["2021-10", "2021-11", "2021-12"]}], "n_cells": 2, "looks": 2, "lock": None,
         "cells": [{"i": 0, "params": {"ctl.stop": "atr:0.5", "ctl.target_rr": 0.5}, "is": _REC, "blocks": []},
                   {"i": 1, "params": {"ctl.stop": "atr:0.5", "ctl.target_rr": 1}, "is": {**_REC, "net": -200.0}, "blocks": []}]}


@pytest.fixture
def fixed(fake):
    fake.routes.update({
        ("POST", "/api/tester/walkforward"): {"id": FWID},
        ("GET", f"/api/tester/walkforward/{FWID}"): {"id": FWID, "status": "done", "walkforward": {"scheme": "fixed"}},
        ("GET", f"/api/tester/walkforward/{FWID}/result"): FIXED,
        ("POST", f"/api/tester/walkforward/{FWID}/pick"): lambda body: {"cell": body["cell"]},
        ("POST", f"/api/tester/walkforward/{FWID}/oos"): lambda body: {"state": "queued", "cell": body["cell"]},
    })
    return fake


def test_heatmap_tool_default_is_hm40(fixed):
    """A new heat map is the fixed 3:1 walk-forward's in-sample table: no axes = the server's hm40 boxes, no range."""
    text = box(fixed).call("heatmap", {"strategy": "nq930", "owner_said": "run the heat map"})
    req = fixed.last("POST")
    assert req["path"] == "/api/tester/walkforward"
    assert req["body"] == {"strategy": "nq930", "inputs": {}, "scheme": "fixed", "step_months": 4}
    assert "| #1 |" in text and "| #2 |" in text and "| #0 " not in text          # boxes 1-based, as the owner says them
    assert "Average of all 2 boxes" in text and "not the best box" in text
    spec = {s["name"]: s for s in tools.SPECS}["heatmap"]
    assert "hm40" in spec["description"] and "ONLY when the owner says so" in spec["description"]
    assert "range" not in spec["inputSchema"]["properties"] and "owner_said" in spec["inputSchema"]["properties"]


def test_fixed_text_says_when_the_strategy_declares_no_own_stop(fixed):
    """20 boxes because the strategy never set own_stop: the result says so in one line (final review, 2026-10-21)."""
    note = "this strategy declares no stop of its own (own_stop): 2 boxes"
    st = ("GET", f"/api/tester/walkforward/{FWID}")
    for own, says in ((False, True), (True, False), (None, False)):      # None: a job from before the flag was kept
        fixed.routes[st] = {"id": FWID, "status": "done", "walkforward": {"scheme": "fixed", **({} if own is None else {"own_stop": own})}}
        for tool in ("walkforward", "heatmap"):
            text = box(fixed).call(tool, {"walkforward_id": FWID} if tool == "walkforward" else {"grid_id": FWID})
            assert (note in text) is says, (own, tool)
    spec = {s["name"]: s for s in tools.SPECS}["write_strategy"]
    assert "set `own_stop = True` when the strategy passes its own sl (so the heat map gets the 4 own-stop rows)" in spec["description"]


def test_heatmap_tool_needs_owner_said(fixed):
    b = box(fixed)
    for said in ({}, {"owner_said": ""}, {"owner_said": "   "}):
        with pytest.raises(ToolError, match="owner_said"):
            b.call("heatmap", {"strategy": "nq930", **said})
    with pytest.raises(ToolError, match="3:1 in-sample months"):
        b.call("heatmap", {"strategy": "nq930", "owner_said": "run it", "range": {"preset": "all"}})
    assert not [r for r in fixed.requests if r["method"] == "POST"]
    assert "Heat-map" in b.call("heatmap", {"grid_id": GID})                         # reading an old one needs none


def test_walkforward_tool_default_fixed_blocks(fixed):
    b = box(fixed)
    with pytest.raises(ToolError, match="owner_said"):
        b.call("walkforward", {"strategy": "nq930"})
    text = b.call("walkforward", {"strategy": "nq930", "owner_said": "run the walk-forward"})
    assert fixed.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "scheme": "fixed", "step_months": 4}
    assert "| #1 |" in text and "pick=" in text
    b.call("walkforward", {"strategy": "nq930", "owner_said": "use rolling", "rolling": True})
    assert fixed.last("POST")["body"]["step_months"] == 1
    n = len(fixed.requests)
    for bad, says in (({"range": {"preset": "build"}}, "3:1 in-sample months"), ({"metric": "sharpe"}, 'scheme="pick"'),
                      ({"ratio": 2}, 'scheme="pick"'), ({"scheme": "best"}, 'scheme: "fixed" \\(the default\\) or "pick"')):
        with pytest.raises(ToolError, match=says):
            b.call("walkforward", {"strategy": "nq930", "owner_said": "run it", **bad})
    assert len(fixed.requests) == n
    spec = {s["name"]: s for s in tools.SPECS}["walkforward"]
    assert "ALWAYS the default" in spec["description"] and "ONLY when the owner says so" in spec["description"]
    assert spec["inputSchema"]["properties"]["scheme"]["default"] == "fixed"
    text = rpc(protocol.Server(b), "initialize", {"protocolVersion": "2025-06-18"})["result"]["instructions"]
    assert "The backtest, heatmap and walkforward tools follow the same law" in text
    assert "heatmap and walkforward run the 3:1 block walk-forward by default" in text
    assert "walkforward oos (the test months) ONLY when he says so (owner_said)" in text


def test_walkforward_oos_needs_owner_said(fixed):
    b = box(fixed)
    b.call("walkforward", {"walkforward_id": FWID, "pick": 3})                     # box #3 as he says it = cell 2
    assert fixed.last("POST")["path"] == f"/api/tester/walkforward/{FWID}/pick" and fixed.last("POST")["body"] == {"cell": 2}
    for bad in (0, -1, True, "3"):
        with pytest.raises(ToolError, match="pick"):
            b.call("walkforward", {"walkforward_id": FWID, "pick": bad})
    n = len(fixed.requests)
    for said in ({}, {"owner_said": ""}):
        with pytest.raises(ToolError, match="owner_said"):
            b.call("walkforward", {"walkforward_id": FWID, "oos": True, **said})
    assert len(fixed.requests) == n                                                 # refused before anything is asked
    fixed.routes[("GET", f"/api/tester/walkforward/{FWID}/result")] = {**FIXED, "lock": {"cell": 1}}
    text = b.call("walkforward", {"walkforward_id": FWID, "oos": True, "owner_said": " run the test months "})
    assert fixed.last("POST")["path"] == f"/api/tester/walkforward/{FWID}/oos"
    assert fixed.last("POST")["body"] == {"cell": 1, "owner_said": " run the test months "}   # his words, as said
    assert "Picked: #2" in text
    spec = {s["name"]: s for s in tools.SPECS}["walkforward"]["inputSchema"]["properties"]
    assert "ONLY when the owner says so in chat" in spec["oos"]["description"]
    assert "never on your own" in spec["oos"]["description"]


def test_walkforward_shows_a_finished_test_month_read(fixed):
    done = {"state": "done", "cell": 1, "record": {**_REC, "net": 321.0}, "owner_said": "run them",
            "blocks": [{"i": 0, "oos": "2022-01", "trades": 4, "win_rate": 50.0, "net": 321.0}]}
    fixed.routes[("GET", f"/api/tester/walkforward/{FWID}/result")] = {**FIXED, "lock": {"cell": 1, "params": {}}, "oos": done}
    text = box(fixed).call("walkforward", {"walkforward_id": FWID})
    assert "| #2 (picked) |" in text and "Test months of #2 (run once, on his words: 'run them')" in text
    assert "| 1 | 2022-01 | 4 | 50.0 | $321 |" in text
    assert not [r for r in fixed.requests if r["method"] == "POST"]               # reading it runs nothing


def test_backtest_default_is_the_3to1_in_sample_months_and_any_other_range_needs_owner_said(fake):
    b = box(fake)
    b.call("backtest", {"strategy": "nq930"})
    assert fake.last("POST")["body"]["range"] == {"kind": "wf_is", "root": "NQ"}
    n = len(fake.requests)
    for rng in ({"preset": "build"}, {"preset": "test"}, {"preset": "all"}, {"preset": "2025-2026"},
                {"preset": "custom", "start": "2023-01-01", "end": "2023-06-30"}):
        for said in ({}, {"owner_said": ""}, {"owner_said": "  "}):
            with pytest.raises(ToolError, match="owner_said"):
                b.call("backtest", {"strategy": "nq930", "range": rng, **said})
    assert len(fake.requests) == n                                                  # refused before anything is asked
    b.call("backtest", {"strategy": "nq930", "range": {"preset": "test"}, "owner_said": "run the test days"})
    assert fake.last("POST")["body"]["range"]["start"] == "2025-07-01"
    with pytest.raises(ToolError, match="no strategy"):
        b.call("backtest", {"strategy": "nope"})
    assert "owner_said" in {s["name"]: s for s in tools.SPECS}["backtest"]["inputSchema"]["properties"]


def test_heatmap_grid_id_of_a_walkforward_reads_the_walkforward(fixed):
    text = box(fixed).call("heatmap", {"grid_id": FWID})
    assert "| #1 |" in text and fixed.last()["path"] == f"/api/tester/walkforward/{FWID}/result"


def test_pick_and_oos_in_one_call_and_refusals_one_based(fixed):
    b = box(fixed)
    b.call("walkforward", {"walkforward_id": FWID, "pick": 2, "oos": True, "owner_said": "pick 2 and run it"})
    posts = [r for r in fixed.requests if r["method"] == "POST"]
    assert [(r["path"].rsplit("/", 1)[1], r["body"]) for r in posts] == [
        ("pick", {"cell": 1}), ("oos", {"cell": 1, "owner_said": "pick 2 and run it"})]
    fixed.routes[("POST", f"/api/tester/walkforward/{FWID}/pick")] = (
        409, {"detail": "cell 4 is picked already (2026-10-20, owner): the pick is locked"})
    with pytest.raises(ToolError, match=r"box #5 is picked already") as e:
        b.call("walkforward", {"walkforward_id": FWID, "pick": 1})
    assert "cell" not in str(e.value)
    fixed.routes[("POST", f"/api/tester/walkforward/{FWID}/pick")] = (409, {"detail": "cell: one of the table's cells, 0 to 39"})
    with pytest.raises(ToolError, match=r"#1 to #40"):
        b.call("walkforward", {"walkforward_id": FWID, "pick": 41})
    fixed.routes[("POST", f"/api/tester/walkforward/{FWID}/pick")] = lambda body: {"cell": body["cell"]}
    fixed.routes[("POST", f"/api/tester/walkforward/{FWID}/oos")] = (409, {"detail": "cell 2: the picked cell is 0: only it runs"})
    with pytest.raises(ToolError, match=r"box #3: the picked box is #1: only it runs"):
        b.call("walkforward", {"walkforward_id": FWID, "pick": 3, "oos": True, "owner_said": "run 3"})


def test_pick_or_oos_on_an_unfinished_walkforward_is_refused(fixed):
    fixed.routes[("GET", f"/api/tester/walkforward/{FWID}")] = {"id": FWID, "status": "running"}
    b = box(fixed)
    for args in ({"pick": 1}, {"oos": True, "owner_said": "run it"}):
        with pytest.raises(ToolError, match="still running"):
            b.call("walkforward", {"walkforward_id": FWID, "wait_s": 0, **args})
    assert not [r for r in fixed.requests if r["method"] == "POST"]


def test_an_old_scheme_start_needs_owner_said_too(fixed):
    with pytest.raises(ToolError, match="owner_said"):
        box(fixed).call("walkforward", {"strategy": "nq930", "scheme": "pick", "ratio": 2,
                                        "axes": [{"key": "sl_pts", "values": [4, 5]}, {"key": "tp_pts", "values": [10]}]})
    assert not [r for r in fixed.requests if r["method"] == "POST"]


# ---------------------------------------------------------------- the prop sim only when asked

def test_a_single_run_runs_the_prop_sim_only_when_prop_rules_is_given(fake):
    b = box(fake)
    b.call("backtest", {"strategy": "nq930"})
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "range": {"kind": "wf_is", "root": "NQ"},
                                         "propsim": False}
    b.call("backtest", {"strategy": "nq930", "prop_rules": "lucid@1"})
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "range": {"kind": "wf_is", "root": "NQ"},
                                         "prop_rules": "lucid@1"}


def test_a_chart_service_without_the_propsim_field_gets_the_run_without_it(fake):
    """An older runner.validate answers 400 'unknown field(s): propsim': post again without it, then leave it out."""
    fake.routes[("POST", "/api/tester/run")] = lambda body: (
        (400, {"detail": "unknown field(s): propsim"}) if "propsim" in body else {"id": RID})
    b = box(fake)
    assert RID in b.call("backtest", {"strategy": "nq930"})
    posts = [r["body"] for r in fake.requests if r["method"] == "POST"]
    assert [("propsim" in p) for p in posts] == [True, False]
    b.call("backtest", {"strategy": "nq930"})
    b.call("backtest", {"strategy": "nq930", "runs": [{}, {"inputs": {"offset_pts": 12}}]})
    posts = [r["body"] for r in fake.requests if r["method"] == "POST"]
    assert len(posts) == 5 and not any("propsim" in p for p in posts[1:])      # remembered: posted once each
    fake.routes[("POST", "/api/tester/run")] = (400, {"detail": "unknown field(s): nope"})
    with pytest.raises(ToolError, match="nope"):                               # any other refusal stands
        box(fake).call("backtest", {"strategy": "nq930"})
    assert len([r for r in fake.requests if r["method"] == "POST"]) == 6


# ---------------------------------------------------------------- several runs in one backtest call

BID = [f"20260927-12001{i}-nq930-b0{i}0" for i in range(3)]


def _batch_fake(fake, states):
    """POST /run hands out BID in turn; each run's status walks its list of states (the last one stays)."""
    posted = iter(BID)
    fake.routes[("POST", "/api/tester/run")] = lambda body: {"id": next(posted)}
    for rid, seq in zip(BID, states):
        seq = list(seq)
        fake.routes[("GET", f"/api/tester/run/{rid}")] = lambda body, rid=rid, seq=seq: {
            "id": rid, **(seq.pop(0) if len(seq) > 1 else seq[0])}
        fake.routes[("GET", f"/api/tester/run/{rid}/bundle")] = {**BUNDLE, "run": {**BUNDLE["run"], "id": rid}}


def test_backtest_runs_posts_every_run_first_then_one_table(fake):
    _batch_fake(fake, [[{"status": "running"}, {"status": "done"}], [{"status": "done"}],
                       [{"status": "error", "error": "strategy crashed"}]])
    text = box(fake).call("backtest", {"strategy": "nq930", "inputs": {"offset_pts": 10}, "costs": {"qty": 2},
                                       "runs": [{"inputs": {"offset_pts": 12}}, {"inputs": {"offset_pts": 14}, "label": "wide"},
                                                {}]})
    posts = [r for r in fake.requests if r["method"] == "POST"]
    assert [p["body"]["inputs"] for p in posts] == [{"offset_pts": 12}, {"offset_pts": 14}, {"offset_pts": 10}]
    for p in posts:      # the shared settings on every run, the prop sim off
        assert p["body"] == {"strategy": "nq930", "inputs": p["body"]["inputs"], "range": {"kind": "wf_is", "root": "NQ"},
                             "qty": 2, "propsim": False}
    paths = [r["path"] for r in fake.requests]
    assert max(i for i, r in enumerate(fake.requests) if r["method"] == "POST") < paths.index(f"/api/tester/run/{BID[0]}")
    assert paths.count("/api/tester/strategies") == 1                       # the catalog once, not once a run
    for want in (f"| offset_pts=12 | 2 | $187 | 50.0% | 2.70 | -$109 | 1.23 | {BID[0]} |", "| wide | 2 | $187 |",
                 "| #3 | error | — |", f"- #3: run {BID[2]} error: strategy crashed", "3 runs · 2 done · Build · Sep 2021",
                 "no prop sim", "Average of the 2 done: net $187 -- judge the average, not the best row.", "prop_eval"):
        assert want in text, want
    assert "run_ids=" not in text


def test_backtest_runs_with_prop_rules_still_posts_the_prop_sim_off(fake):
    _batch_fake(fake, [[{"status": "done"}]])
    box(fake).call("backtest", {"strategy": "nq930", "prop_rules": "lucid@1", "runs": [{}]})
    assert fake.last("POST")["body"] == {"strategy": "nq930", "inputs": {}, "range": {"kind": "wf_is", "root": "NQ"},
                                         "prop_rules": "lucid@1", "propsim": False}


def test_backtest_runs_returns_what_is_unfinished_and_run_ids_keeps_waiting(fake):
    _batch_fake(fake, [[{"status": "done"}], [{"status": "running", "done": 5, "total": 947}, {"status": "done"}]])
    b = box(fake)
    text = b.call("backtest", {"strategy": "nq930", "wait_s": 0,
                               "runs": [{"inputs": {"offset_pts": 12}}, {"inputs": {"offset_pts": 14}}]})
    assert f"| {BID[0]} |" in text and "| offset_pts=14 | running · 5/947 |" in text
    assert f"Still going: 1 of 2. Call backtest(run_ids=[{BID[0]!r}, {BID[1]!r}])" in text      # the whole batch, not the late rows
    again = b.call("backtest", {"run_ids": [BID[0], BID[1]]})
    assert f"| — | 2 | $187 | 50.0% | 2.70 | -$109 | 1.23 | {BID[1]} |" in again and "run_ids=" not in again
    assert "Average of the 2 done: net $187" in again
    assert len([r for r in fake.requests if r["method"] == "POST"]) == 2       # waiting posts nothing


def test_a_resumed_batch_names_its_rows_by_the_inputs_that_differ_and_averages_them_all(fake):
    _batch_fake(fake, [[{"status": "done"}], [{"status": "done"}], [{"status": "done"}]])
    for rid, off, net in zip(BID, (10, 12, 14), (100.0, 300.0, -1000.0)):
        run = {**BUNDLE["run"], "id": rid, "inputs": {**BUNDLE["run"]["inputs"], "offset_pts": off}}
        run["report"] = {**run["report"], "summary": {**run["report"]["summary"],
                                                        "all": {**run["report"]["summary"]["all"], "net_profit": net}}}
        fake.routes[("GET", f"/api/tester/run/{rid}/bundle")] = {**BUNDLE, "run": run}
    text = box(fake).call("backtest", {"run_ids": list(BID)})
    for off in (10, 12, 14):
        assert f"| offset_pts={off} |" in text
    assert "Average of the 3 done: net -$200" in text


def test_a_batch_label_is_one_table_cell(fake):
    _batch_fake(fake, [[{"status": "done"}]])
    text = box(fake).call("backtest", {"strategy": "nq930", "runs": [{"label": "wide | stop\nnew"}]})
    assert "| wide / stop new | 2 |" in text


def test_backtest_runs_keeps_the_single_run_rules_and_its_cap(fake):
    b = box(fake)
    one = [{"inputs": {"offset_pts": 12}}]
    n = len(fake.requests)
    for args, msg in (({"strategy": "nq930", "runs": one, "range": {"preset": "test"}}, "owner_said"),
                      ({"strategy": "nq930", "runs": one, "range": {"preset": "test"}, "owner_said": " "}, "owner_said"),
                      ({"strategy": "nq930", "runs": one * (tools.MAX_BATCH + 1)}, f"1 to {tools.MAX_BATCH}"),
                      ({"strategy": "nq930", "runs": []}, f"1 to {tools.MAX_BATCH}"),
                      ({"strategy": "nq930", "runs": [{"input": {}}]}, "runs #1"),
                      ({"strategy": "nq930", "runs": [{}, {"inputs": [1]}]}, "runs #2"),
                      ({"strategy": "nq930", "inputs": [1], "runs": one}, "inputs: an object"),
                      ({"strategy": "nq930", "runs": one, "run_id": RID}, "not both"),
                      ({"runs": one, "run_ids": [RID]}, "not both"),
                      ({"run_ids": [RID] * (tools.MAX_BATCH + 1)}, f"1 to {tools.MAX_BATCH}")):
        with pytest.raises(ToolError, match=msg):
            b.call("backtest", args)
    assert len(fake.requests) == n                                              # refused before anything is asked
    with pytest.raises(ToolError, match="no strategy 'nope'"):                  # one unknown strategy: nothing posted
        b.call("backtest", {"strategy": "nq930", "runs": [{}, {"strategy": "nope"}]})
    assert not [r for r in fake.requests if r["method"] == "POST"]
    said = {"range": {"preset": "test"}, "owner_said": "run the test days"}
    b.call("backtest", {"strategy": "nq930", "runs": one, **said})
    assert fake.last("POST")["body"]["range"]["start"] == "2025-07-01"
    fake.routes[("POST", "/api/tester/run")] = lambda body: (
        (400, {"detail": "inputs.offset_pts: must be within [0, 500]"}) if body["inputs"]["offset_pts"] > 500 else {"id": RID})
    text = b.call("backtest", {"strategy": "nq930", "runs": [{"inputs": {"offset_pts": 900}}, {"inputs": {"offset_pts": 12}}]})
    assert "- offset_pts=900: 400: inputs.offset_pts: must be within [0, 500]" in text
    assert "| offset_pts=900 | refused |" in text and "| offset_pts=12 | 2 | $187 |" in text and f"| {RID} |" in text


def test_backtest_runs_waits_once_for_all_on_the_tool_clock(fake):
    """One wait_s for the whole batch, not one a run: the fake clock moves 1 s a sleep."""
    now = [0.0]
    _batch_fake(fake, [[{"status": "running"}], [{"status": "running"}]])
    b = tools.Toolbox(Client(fake.url), sleep=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])
    text = b.call("backtest", {"strategy": "nq930", "wait_s": 5, "runs": [{}, {"inputs": {"offset_pts": 12}}]})
    assert now[0] == 5.0 and f"backtest(run_ids=[{BID[0]!r}, {BID[1]!r}])" in text
