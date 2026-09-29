# Claude's Strategy Tester + desk-bridge tools (MCP)

`homebase/claude_mcp` is a stdio MCP server (hand-rolled JSON-RPC, Python stdlib only). It gives Claude
the Strategy Tester: list/read/write strategies, backtest, heat-map, walk-forward, Monte Carlo, prop-eval
re-scores, runs and trades, and **show on chart** (the open chart page loads the run and scrolls to it).
It also gives Claude a read of the live desk (`desk_status`, `desk_journal`, `desk_readiness`,
`data_coverage`, `services_health`) and two safe, non-trading operations (`account_reconnect`,
`account_remove`), plus a charts-service data export (`export_start`, `export_status`). **It has no
trading tool of any kind** — nothing here can place or cancel an order, flatten, kill, arm/disarm,
book/unbook an account, or touch a strategy or chart-trading switch (`homebase/claude_mcp/desk_client.py`'s
`ALLOWED_GET`/`ALLOWED_POST` is the whole allowlist; `tests/test_claude_mcp.py` pins it structurally).

## Register (once, after this branch is merged; see restarts below)

```sh
claude mcp add --scope user \
  -e PYTHONPATH=/Users/ramoscapital/ramos-quant-homebase \
  homebase -- /Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m homebase.claude_mcp
```

- **If `homebase` is already registered from an earlier branch, no re-registration is needed** — the
  same command starts the same module, and the MCP server subprocess is spawned fresh each Claude Code
  session, so it picks up this branch's new tools the next time a session starts. Just restart the
  session (or run `/mcp` again) once this branch is merged.
- `PYTHONPATH` makes `homebase` importable whatever directory Claude Code starts in. The server imports
  nothing outside the stdlib, so any `python3` (3.9+) works in place of the venv's.
- Check it: `claude mcp list` should show `homebase ... ✓ Connected`. In a session, `/mcp` lists its 24 tools.
- Leave `write_strategy` on "ask" (do not allowlist it): it writes Python that a backtest will run. The
  sandbox below contains that code, but the user should still see what Claude writes before it runs.
  `account_remove` is worth leaving on "ask" too, even though it is refused while an account holds a
  position — removing the wrong account from the pool is still a real mistake to catch before it runs.
- Remove it: `claude mcp remove --scope user homebase`.

## What it talks to

- `http://127.0.0.1:8852/api/tester/*` and `/api/export/*` (the chart service). `HOMEBASE_CHARTS_URL` may
  point it at another **loopback** port (e.g. a replay instance: add
  `-e HOMEBASE_CHARTS_URL=http://127.0.0.1:8862`).
- `http://127.0.0.1:8850/api/status`, `/api/journal`, `/api/accounts/reconnect`, `/api/accounts/remove`
  only (the desk) — `homebase/claude_mcp/desk_client.py`'s exact allowlist, nothing else. `HOMEBASE_DESK_URL`
  overrides the loopback port the same way `HOMEBASE_CHARTS_URL` does for the chart service.
- DRAFT strategy files: `~/.homebase/strategies/<name>.py` (`HOMEBASE_DRAFTS_DIR` overrides).
- `homebase/.state/tick_coverage.json`, read directly off disk (never over HTTP) for `data_coverage`.

## Needs a restart to actually work

- **The desk** (`com.ramosquant.homebase`, :8850) must be restarted once this branch is merged: it adds
  `GET /api/journal` and a `cooldown_s` field on `/api/status`'s accounts, which `desk_status` and
  `desk_journal` depend on. Until then those two tools 404 / show no cooldown.
- **`export_start` / `export_status`** additionally need `feat/data-export` merged into the chart service
  (`POST /api/export/start`, `GET /api/export/{id}`) and the chart service (`com.ramosquant.homebase-charts`,
  :8852) restarted. Until then they refuse with "needs feat/data-export merged and the service restarted".
- **`data_coverage`** needs `fix/tick-archive-gaps` merged and at least one
  `python -m homebase.ticks --coverage` run to have written `homebase/.state/tick_coverage.json`. Until
  then it says so and returns cleanly (no error).
- **Claude Code itself**: a running session keeps the tool list it started with: after any of the above
  restarts, or after this branch first merges, start a new session (or `/mcp` reconnect) to pick up the new
  tools and the updated ones' new fields.

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

## The desk-bridge tools

- **Reads** — `desk_status`, `desk_journal`, `desk_readiness`, `data_coverage`, `services_health` — hit
  the desk's own `/api/status` / `/api/journal` (or read a local file for `data_coverage`) and are never
  refused; they format a compact summary, never a raw dump.
- **Operations** — `account_reconnect`, `account_remove`, `export_start`, `export_status` — are each
  refused 09:20–09:35 ET on weekdays, before any request goes out. `account_reconnect` and
  `account_remove` send `source: "mcp"` on the desk's existing `/api/accounts/reconnect` and
  `/api/accounts/remove` routes, which (this branch) journals an extra `mcp_action` event alongside the
  usual `manual_reconnect` / `account_removed` one — so the journal always shows whether a reconnect or a
  removal came from the dashboard or from Claude.
- **`account_remove`** is refused by the desk itself (409) while the account holds an open position or a
  working order — the tool surfaces that refusal as its error text, it does not re-check the position
  itself.
- **Nothing here can trade.** `homebase/claude_mcp/desk_client.py`'s `ALLOWED_GET` / `ALLOWED_POST` is a
  four-route allowlist (`/api/status`, `/api/journal`, `/api/accounts/reconnect`, `/api/accounts/remove`)
  enforced before any request is built — a fifth route, even a typo one character off, is refused locally.
  `export_start` / `export_status` reach only the chart service's `/api/export/*` prefix. No tool or route
  in this package can reach `/api/kill`, `/api/arm`, `/api/book`, `/api/strategy`, `/api/chart-trading`, an
  order or flatten route, or the chart service's own desk relay (`/api/desk/*`, which places orders) —
  `tests/test_claude_mcp.py::test_the_package_only_ever_reaches_known_safe_routes` asserts this by
  scanning the package's source, not just by review.
