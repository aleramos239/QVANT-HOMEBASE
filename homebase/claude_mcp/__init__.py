"""Claude's Strategy Tester tools: a stdio MCP server (JSON-RPC 2.0, stdlib only).

    python -m homebase.claude_mcp            (registered with `claude mcp add`, see deploy/claude-mcp.md)

It speaks to ONE service: the chart service's tester API on http://127.0.0.1:8852/api/tester/* (urllib;
HOMEBASE_CHARTS_URL may point it at another loopback port, e.g. a test server). Besides that it only
reads/writes DRAFT strategy files through homebase.draftstore (~/.homebase/strategies/<name>.py).

There are deliberately NO tools for orders, accounts, arming, killing, chart trading, market-data
settings or paper accounts: tests/test_claude_mcp.py pins that no tool name or /api path outside
/api/tester/ ever appears in this package.

    protocol.py   the JSON-RPC loop: initialize, notifications/initialized, ping, tools/list, tools/call
    client.py     the HTTP client (Host/Origin/JSON headers the chart service's guards accept)
    tools.py      the tool schemas, handlers and the compact text they return
"""
