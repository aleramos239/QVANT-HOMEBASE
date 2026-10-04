"""Claude's Strategy Tester and desk-bridge tools: a stdio MCP server (JSON-RPC 2.0, stdlib only).

    python -m homebase.claude_mcp            (registered with `claude mcp add`, see deploy/claude-mcp.md)

It speaks to TWO loopback services (urllib): the chart service on http://127.0.0.1:8852, /api/tester/* and
/api/export/* only (HOMEBASE_CHARTS_URL may point it at another loopback port, e.g. a test server), and the
desk on http://127.0.0.1:8850, four exact routes only (desk_client.py: GET /api/status and /api/journal,
POST /api/accounts/reconnect and /api/accounts/remove). Besides that it reads/writes DRAFT strategy files
through homebase.draftstore (~/.homebase/strategies/<name>.py) and reads local state for data_coverage and
services_health (see desk_tools.py).

There are deliberately NO tools for orders, arming, killing, flattening, booking, chart trading,
market-data settings or paper accounts: tests/test_claude_mcp.py pins the tool names and that no /api
path outside the routes above ever appears in this package.

    protocol.py     the JSON-RPC loop: initialize, notifications/initialized, ping, tools/list, tools/call
    client.py       the chart service's HTTP client (Host/Origin/JSON headers its guards accept)
    tools.py        the tester tool schemas, handlers and the compact text they return
    desk_client.py  the desk's HTTP client (an exact route allowlist)
    desk_tools.py   the desk-bridge and export tools
"""
