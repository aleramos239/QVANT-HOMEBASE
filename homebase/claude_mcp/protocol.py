"""MCP over stdio, by hand: newline-delimited JSON-RPC 2.0 on stdin/stdout (logs go to stderr).

Implemented: initialize, notifications/initialized (and any other notification: ignored), ping,
tools/list, tools/call. Anything else with an id answers -32601. A tool's own failure is a normal
result with isError: true (the MCP convention), so Claude reads the message.
"""
from __future__ import annotations

import json
import sys
import traceback

from . import tools
from .client import ToolError

SERVER_NAME = "homebase"
SERVER_VERSION = "1.6.0"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "Homebase Strategy Tester: backtest strategies on real tick data (tick replay, pessimistic fills), "
    "run parameter heat-maps and walk-forwards, Monte Carlo and prop-eval re-scores, write DRAFT strategies, "
    "and show any finished run on the user's chart page (show_on_chart; never 09:20-09:35 ET). Long jobs "
    "return their id after wait_s: call the same tool with that id to keep waiting, or cancel it. Strategy "
    "work follows research/edge-library/BLUEPRINT.md section 2 (skill: strategy-blueprint): read it before "
    "the first run. For a strategy idea use the blueprint_* tools (card, code check, build, lock, test, sim, "
    "eval card): they save everything in the app. "
    "Their order: blueprint_blocks (what an idea can be built from), blueprint_card, blueprint_code_check, "
    "blueprint_build, blueprint_lock, blueprint_test (once; early look needs the owner's yes), blueprint_sim "
    "(one strategy; blueprint_portfolio reads several proven ones on one account), "
    "blueprint_eval_card, with blueprint_status at any time and blueprint_heatmap and blueprint_mc as "
    "read-only views of what is saved; they file each idea under its Lab group themselves, so set_group is "
    "not needed for it. "
    "The strategy pipeline tests idea cards by itself, stage by stage: pipeline_add (one card; blueprint_blocks "
    "first), pipeline_control (start / pause / resume its runner), pipeline_status (the queue, or one idea in "
    "full), pipeline_book, and pipeline_decide (approve / refuse an idea that passed, only on the owner's word). "
    "The default range is the build days (2021-09-22 to "
    "2025-06-30), where all tuning happens. "
    "The test days (2025-07-01 on) are read once and only for a locked strategy, never for a quick look or "
    "\"all data\". At most 2 backtests "
    "run at once on this machine during desk hours (weekdays 08:00-16:15 ET) and 4 outside them, and none "
    "start 09:20-09:35 ET on weekdays: a refusal says so -- report it, do not retry in a loop.\n"
    "Desk bridge: desk_status / desk_journal / desk_readiness / data_coverage / services_health read the live "
    "trading desk; account_reconnect and account_remove are its only two safe write actions. No tool anywhere "
    "in this server can place or cancel an order, flatten, kill, arm/disarm, book/unbook an account or touch a "
    "strategy or chart-trading switch -- there is no trading tool, live or in the tester. Every desk write is "
    "refused 09:20-09:35 ET on weekdays, same as the tester's own jobs.")


def _log(msg: str) -> None:
    print(f"[homebase-mcp] {msg}", file=sys.stderr, flush=True)


class Server:
    def __init__(self, toolbox: tools.Toolbox | None = None):
        self.tools = toolbox or tools.Toolbox()

    def handle(self, msg) -> dict | None:
        """One parsed message -> the response dict, or None (a notification)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            rid = msg.get("id") if isinstance(msg, dict) else None
            return _error(rid, -32600, "invalid request")
        method, rid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        if "id" not in msg:
            return None                                  # a notification (initialized, cancelled, ...)
        try:
            if method == "initialize":
                want = params.get("protocolVersion") if isinstance(params, dict) else None
                return _ok(rid, {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                                 "capabilities": {"tools": {"listChanged": False}},
                                 "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                                 "instructions": INSTRUCTIONS})
            if method == "ping":
                return _ok(rid, {})
            if method == "tools/list":
                return _ok(rid, {"tools": self.tools.specs()})
            if method == "tools/call":
                if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                    return _error(rid, -32602, "tools/call needs {name, arguments}")
                name, args = params["name"], params.get("arguments") or {}
                if name not in self.tools.names():
                    return _error(rid, -32602, f"unknown tool {name!r}")
                if not isinstance(args, dict):
                    return _error(rid, -32602, "arguments: an object")
                try:
                    text = self.tools.call(name, args)
                    return _ok(rid, {"content": [{"type": "text", "text": text}], "isError": False})
                except (ToolError, ValueError) as e:
                    return _ok(rid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
            return _error(rid, -32601, f"method not found: {method}")
        except Exception as e:  # noqa: BLE001 -- the server never dies on one request
            _log(traceback.format_exc())
            return _error(rid, -32603, f"{type(e).__name__}: {e}")


def _ok(rid, result) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None, server: Server | None = None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    srv = server or Server()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = _error(None, -32700, "parse error")
        else:
            if isinstance(msg, list):           # a batch (older clients): answer each request in it
                outs = [o for o in (srv.handle(m) for m in msg) if o is not None]
                out = outs or None
            else:
                out = srv.handle(msg)
        if out is not None:
            stdout.write(json.dumps(out, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    _log(f"started (chart service {tools.describe_target()})")
    return serve()
