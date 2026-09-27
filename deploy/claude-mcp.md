# Claude's Strategy Tester tools (MCP)

`homebase/claude_mcp` is a stdio MCP server (hand-rolled JSON-RPC, Python stdlib only). It gives Claude
the Strategy Tester: list/read/write strategies, backtest, heat-map, walk-forward, Monte Carlo, prop-eval
re-scores, runs and trades, and **show on chart** (the open chart page loads the run and scrolls to it).
It has no trading tools of any kind.

## Register (once, after this branch is merged and the chart service restarted)

```sh
claude mcp add --scope user \
  -e PYTHONPATH=/Users/ramoscapital/ramos-quant-homebase \
  homebase -- /Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m homebase.claude_mcp
```

- `PYTHONPATH` makes `homebase` importable whatever directory Claude Code starts in. The server imports
  nothing outside the stdlib, so any `python3` (3.9+) works in place of the venv's.
- Check it: `claude mcp list` should show `homebase ... ✓ Connected`. In a session, `/mcp` lists its 14 tools.
- Remove it: `claude mcp remove --scope user homebase`.

## What it talks to

- `http://127.0.0.1:8852/api/tester/*` only (the chart service). `HOMEBASE_CHARTS_URL` may point it at
  another **loopback** port (e.g. a replay instance: add `-e HOMEBASE_CHARTS_URL=http://127.0.0.1:8862`).
- DRAFT strategy files: `~/.homebase/strategies/<name>.py` (`HOMEBASE_DRAFTS_DIR` overrides). The chart
  service only ever loads a draft in a child process; the desk never reads that directory.

## Needs the chart service to run this version

`POST /api/tester/show`, `GET /api/tester/strategies/{id}/source` and DRAFT strategies in the catalog are
new chart-service code: until `com.ramosquant.homebase-charts` is restarted on it, `show_on_chart`,
`read_strategy` and `write_strategy` answer 404 / "not listed yet" (the other tools work against the old
service). The chart page also needs a reload to pick up the new `tester_show` handler.

## Limits it inherits

- At most 2 backtests at once on this machine (runs, heat-map cells and walk-forward cells together).
- Nothing starts 09:20–09:35 ET on weekdays: a single backtest (and any DRAFT validation) asked for then
  is refused and the tool returns the refusal; a heat-map / walk-forward is accepted but its cells wait,
  and the tool reports them `paused for the 9:30 window`.
