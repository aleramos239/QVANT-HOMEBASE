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
- Check it: `claude mcp list` should show `homebase ... ✓ Connected`. In a session, `/mcp` lists its 15 tools.
- Leave `write_strategy` on "ask" (do not allowlist it): it writes Python that a backtest will run. The
  sandbox below contains that code, but the user should still see what Claude writes before it runs.
- Remove it: `claude mcp remove --scope user homebase`.

## What it talks to

- `http://127.0.0.1:8852/api/tester/*` only (the chart service). `HOMEBASE_CHARTS_URL` may point it at
  another **loopback** port (e.g. a replay instance: add `-e HOMEBASE_CHARTS_URL=http://127.0.0.1:8862`).
- DRAFT strategy files: `~/.homebase/strategies/<name>.py` (`HOMEBASE_DRAFTS_DIR` overrides).

## Draft strategies: where their code runs

- **Listing, reading and validating a draft never runs it.** The catalog reads the file's text (Python `ast`):
  literal class attributes and a literal `return [Input(...), ...]`. A draft that cannot be read that way is
  listed with the reason, and `write_strategy` refuses it before writing.
- **Its backtest is the only place its code runs**, inside macOS `sandbox-exec` with
  `homebase/backtest/draft.sb` (deny by default): read the Python install, the venv, the repo code, the tick
  archive and the shared tape cache; write only its run dir and a private tmp dir (its own tape cache goes
  there); no network at all (not even 127.0.0.1 — never the desk on :8850 or the charts on :8852); no fork, no
  exec of anything but the interpreter; `homebase/.state`, `~/.homebase`, `~/.ssh`, `~/.zshrc` and the
  keychains unreadable; minimal environment. No working sandbox = draft backtests refused (fail closed).
- **Wall clock: 20 minutes** per draft run or heat-map cell (`sandbox.DRAFT_TIMEOUT_S`), then its whole process
  group is killed and the run reads "timed out". A draft runs in its own process group; cancel kills the group;
  the backtest slot is always released. The `cancel` tool stops any run, heat-map or walk-forward.
- The desk never reads the drafts dir, and a draft is never an algo choice.

## Needs the chart service to run this version

`POST /api/tester/show`, `GET /api/tester/strategies/{id}/source` and DRAFT strategies in the catalog are
new chart-service code: until `com.ramosquant.homebase-charts` is restarted on it, `show_on_chart`,
`read_strategy` and `write_strategy` answer 404 / "not listed yet" (the other tools work against the old
service). The chart page also needs a reload to pick up the new `tester_show` handler.

## show_on_chart, on the page

It takes over only a chart with NO accounts ticked and no algo, that is not replaying and is not the selected
chart (the order panel and DOM follow the selection, which it never moves). It never changes interval or scroll
on a chart with accounts, and while any chart has accounts it loads the run into the Strategy Tester without
switching the bottom panel away from Positions/Orders. No eligible chart: nothing moves and the status bar says
why. Refused 09:20–09:35 ET on weekdays. A click in List of trades follows the same rule (the selected chart
allowed): a chart with accounts is never switched.

## Limits it inherits

- At most 2 backtests at once on this machine (runs, heat-map cells and walk-forward cells together).
- Nothing starts 09:20–09:35 ET on weekdays: a single backtest asked for then is refused and the tool
  returns the refusal; a heat-map / walk-forward is accepted but its cells wait,
  and the tool reports them `paused for the 9:30 window`.
