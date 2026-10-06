# Claude's Strategy Tester + desk-bridge tools (MCP)

`homebase/claude_mcp` is a stdio MCP server (hand-rolled JSON-RPC, Python stdlib only). It gives Claude
the Strategy Tester: list/read/write strategies, backtest, heat-map, walk-forward, Monte Carlo, prop-eval
re-scores, runs and trades, and **show on chart** (the open chart page loads the run and scrolls to it).
It also gives Claude a read of the live desk (`desk_status`, `desk_journal`, `desk_readiness`,
`data_coverage`, `services_health`) and two safe, non-trading operations (`account_reconnect`,
`account_remove`), plus a charts-service data export (`export_start`, `export_status`), and the eight
`blueprint_*` tools that run a strategy idea through the house blueprint, one per phase. **It has no
trading tool of any kind** — nothing here can place or cancel an order, flatten, kill, arm/disarm,
book/unbook an account, or touch a strategy or chart-trading switch (`homebase/claude_mcp/desk_client.py`'s
`ALLOWED_GET`/`ALLOWED_POST` is the whole allowlist; `tests/test_claude_mcp.py` pins it structurally).

## Register (once)

```sh
claude mcp add --scope user \
  -e PYTHONPATH=/Users/ramoscapital/ramos-quant-homebase \
  homebase -- /Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m homebase.claude_mcp
```

- **If `homebase` is already registered, no re-registration is needed after a code change** — the
  same command starts the same module, and the MCP server subprocess is spawned fresh each Claude Code
  session, so it picks up new tools the next time a session starts. Just restart the
  session (or run `/mcp` again).
- `PYTHONPATH` makes `homebase` importable whatever directory Claude Code starts in. The server imports
  nothing outside the stdlib, so any `python3` (3.9+) works in place of the venv's.
- Check it: `claude mcp list` should show `homebase ... ✓ Connected`. In a session, `/mcp` lists its 33 tools.
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
- DRAFT strategy files: `~/.homebase/strategies/<name>.py` (`HOMEBASE_DRAFTS_DIR` overrides). `set_group`
  writes `groups.json` in the same folder (which group the Lab lists a strategy under) and nothing else.
- `homebase/.state/tick_coverage.json` and `homebase/.state/data_watch.json` (the tick job's data watchdog: live feed
  late / thin / silent, refused merges, what is about to leave the broker), read directly off disk (never over
  HTTP) for `data_coverage`; `desk_readiness` adds the watchdog's one line to the desk's own checks.
- The blueprint toolkit, started as a child process by each `blueprint_*` tool (no service is asked):
  `research/edge-library/bp.py`, run with the research engine's Python (`$HOME/ONYX TRADING/.venv/bin/python`).
  `HOMEBASE_BP` and `HOMEBASE_BP_PYTHON` move them. The ideas it saves live in `~/.homebase/ideas/<name>/`
  (`HOMEBASE_IDEAS_ROOT` overrides), kept through `homebase/ideastore.py`. An idea folder that was moved
  writes no Lab draft and no group unless `HOMEBASE_DRAFTS_DIR` says where: it can never write the real Lab.

## What the tools need from the running services

All of the code below is in `main`. A tool only fails this way when a service is still running an older
version: restart that service (never 09:20–09:35 ET on weekdays).

- **The desk** (`com.ramosquant.homebase`, :8850) serves `GET /api/journal` and a `cooldown_s` field on
  `/api/status`'s accounts, which `desk_journal` and `desk_status` depend on. A desk older than that
  answers 404 / shows no cooldown.
- **`export_start` / `export_status`** use the chart service's `POST /api/export/start` and
  `GET /api/export/{id}` (`com.ramosquant.homebase-charts`, :8852). When those routes are missing the tools
  refuse and say the chart service needs a restart.
- **`data_coverage`** reads `homebase/.state/tick_coverage.json`, which the tick job writes
  (`python -m homebase.ticks --coverage` rewrites it). With no file it says so and returns cleanly (no error).
  The watchdog's part comes from `data_watch.json`, written at the end of every run of the tick job (a new
  process each hour: no service restart); a reading over 3 hours old is shown as "NOT CHECKED since".
- **Claude Code itself**: a running session keeps the tool list it started with: after a service restart or
  a code change, start a new session (or `/mcp` reconnect) to pick up new tools and new fields.

## The blueprint tools

`blueprint_card` (phase 0), `blueprint_code_check` (1), `blueprint_build` (2), `blueprint_lock` (3),
`blueprint_test` (4), `blueprint_sim` (5), `blueprint_eval_card` (6) and `blueprint_status` follow
`research/edge-library/BLUEPRINT.md`, section 2. Each runs one command of the toolkit
(`<python> bp.py <command> ... --root=<ideas folder> --json`) and returns its text and its pass/fail lines.

- **Nothing is judged in the connector.** The toolkit decides and refuses; exit code 2 comes back as
  "Refused (blueprint <command>): ..." (the tool's error), a toolkit that is not there as "not installed yet".
- **`blueprint_test` reads the test days ONCE.** It needs `confirm: true`; leave it on "ask".
- **Long commands** (`blueprint_build`, `blueprint_test`) return a job id after `wait_s` (default 120 s);
  the same tool called with that `job_id` keeps waiting.
- **Everything is saved in the app.** After each command the idea's `idea.json`, the record block on top of
  its Lab draft (`draft_<name>`: the card and the latest verdict; the code below it is never touched) and its
  Lab group (Ideas, Leads, Proven on history, Proven live, Shelved) are brought up to date. The group moves
  only when the status changes. A `groups.json` that does not read is reported in the tool's text and never
  fails the phase.
- No chart-service route is involved, so nothing needs a restart: a new session has the tools.

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

`show_on_chart`, `read_strategy` and `write_strategy` use `POST /api/tester/show`,
`GET /api/tester/strategies/{id}/source` and the DRAFT strategies in the catalog. A chart service started
before that code answers 404 / "not listed yet": restart `com.ramosquant.homebase-charts`. A chart page
opened before the restart needs a reload to pick up the `tester_show` handler.

The default range (`range: build`, the build days 2021-09-22 → 2025-06-30) is sent by name, and the chart
service owns its dates (`homebase/backtest/discipline.py`). A chart service started before the blueprint's
dates (connector 1.2.0) still runs 2021-01-01 → 2024-12-31 for it, and its result says "Research window
2021–2024": restart it. `test`, `all` and `custom` carry their own dates and are right either way.

## show_on_chart, on the page

It takes over only a chart with NO accounts ticked and no algo, that is not replaying and is not the selected
chart (the order panel and DOM follow the selection, which it never moves). It never changes interval or scroll
on a chart with accounts, and while any chart has accounts it loads the run into the Strategy Tester without
switching the bottom panel away from Positions/Orders. No eligible chart: nothing moves and the status bar says
why. Refused 09:20–09:35 ET on weekdays. A click in List of trades follows the same rule (the selected chart
allowed): a chart with accounts is never switched.

## Limits it inherits

- At most 2 backtests at once on this machine during desk hours (weekdays 08:00–16:15 ET) and 4 outside
  them (runs, heat-map cells and walk-forward cells together; `homebase/backtest/slots.py`). An override
  file, `~/.homebase/tester_slots.json`, can change the cap for a while and add no-start windows.
- Nothing starts 09:20–09:35 ET on weekdays: a single backtest asked for then is refused and the tool
  returns the refusal; a heat-map / walk-forward is accepted but its cells wait,
  and the tool reports them `paused for the 9:30 window`.

## The desk-bridge tools

- **Reads** — `desk_status`, `desk_journal`, `desk_readiness`, `data_coverage`, `services_health` — hit
  the desk's own `/api/status` / `/api/journal` (or read a local file for `data_coverage`) and are never
  refused; they format a compact summary, never a raw dump.
- **Operations** — `account_reconnect`, `account_remove`, `export_start`, `export_status` — are each
  refused 09:10–09:35 ET on weekdays, before any request goes out (`desk_tools.QUIET`; wider than the
  tester tools' 09:20–09:35). The desk also refuses an MCP `account_remove` in that window itself. `account_reconnect` and
  `account_remove` send `source: "mcp"` on the desk's existing `/api/accounts/reconnect` and
  `/api/accounts/remove` routes, which journal an extra `mcp_action` event alongside the
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
