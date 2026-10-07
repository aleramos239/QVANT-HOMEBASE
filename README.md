# QVANT HOMEBASE

A futures trading desk. It runs a small set of approved strategies on its own
clock, sends bracketed orders to the broker, and writes every step to a journal.
Around the desk sit a chart service, a strategy tester, an MCP server for Claude,
two Mac viewer apps and a research folder.

It runs as launchd services on one Mac, from this folder
(`~/ramos-quant-homebase`). Every service listens on `127.0.0.1` only.

## How a trade happens

```
 DESK CLOCK (inside the server)        DESK SERVER  127.0.0.1:8850           BROKER
 timer.py       kind "straddle"        engine.py
 leveltimer.py  kind "levels"          · enabled? killed today?
   │                                   · already traded today?
   │ reads the last trade before       · inside the accept window?
   │ the fire time from the desk's     · any account booked?
   │ own market-data socket            · disarmed or shadow -> journal only
   │ (marketdata.py)                   · per booked account, together:
   │                                     buy stop + sell stop, each     ──▶  Tradovate (demo or live)
   └── two entry prices ──────────▶      with its stop and target            or a paper account
                                         attached broker-side (OSO)          (chart service, :8852)
                                       ◀── fills ───────────────────────
                                       · cancel the other entry
                                       · move stop / target to the fill
                                       · cancel_et: cancel unfilled entries
                                       · flat_et: flatten what is open
                                       · journal (homebase/.state/journal.jsonl)
```

- The app makes its own signals. There is no TradingView alert and no webhook
  (see "What is left of the old webhook design" below).
- The anchor price is the last trade of the strategy's own symbol that the desk
  received before the fire time. If the fire is late, or there was no fresh
  trade before it, the desk uses the latest trade instead and says so in the
  journal. If no fresh trade comes before the accept window closes, the day is
  missed and nothing is placed.
- Sizes, offsets, stops, targets and times come from `homebase/config.py`
  (`config.json` can override them). A straddle signal only carries the two
  entry prices, and the engine checks them against the config before any order
  exists. A levels signal also carries the day's stop distance, built from ATR.
- The book (`config.json`) says which accounts run which strategy and at what
  size. One signal goes to every booked account at the same moment.

### Signal sources in the code

| Source | Calls | Used for |
|---|---|---|
| `homebase/timer.py` (`SelfTimer`) | `engine.handle_alert(source="timer")` | kind `straddle` with `self_fire` |
| `homebase/leveltimer.py` (`LevelTimer`) | `engine.handle_levels` | kind `levels` |
| `homebase/feed.py` + `homebase/rules.py` | `engine.handle_signal` | kind `bars` (a rule on closed bars). No rule ships today: `RULES` is empty. |
| `POST /api/test-alert` | `engine.handle_alert(source="test")` | a dry-run test signal. Refused while armed. |
| Chart page (manual orders) | chart service `/api/desk/*` -> desk `/api/trade/*` (`homebase/trading.py`) | trading from the chart. Off by default. |

## Strategies

These ship in `config.py` defaults. All times are ET. Each trades at most once a day.

| Name | Market | Kind | What triggers it | Default |
|---|---|---|---|---|
| `nq930` | NQ | straddle | Every weekday at 09:30:00, if the daily TREND gate passes (ADX 14 on completed daily bars, read at 09:20). A chop day is skipped. | on |
| `gc_nfp` | GC | straddle | 08:29:59, only on the dates listed in `only_dates` (NFP days, added by hand). | off |
| `nq_nyam_flex` | NQ | levels | 09:30:00. Entries at the last print ± 0.25 × ATR(14) of 30-minute bars. | off |
| `nq_nyam_pro` | NQ | levels | Same entry as `nq_nyam_flex`, with a different take rule. | off |
| `nq_orb_pro` | NQ | levels | 11:05:00. Buy stop one tick above the 11:00–11:05 high, sell stop one tick below its low. | off |
| `nq_pm_flex` | NQ | levels | 13:30:00. Entries at the last print ± 1.0 × ATR(14) of 30-minute bars. | off |

- A **straddle** uses fixed distances from the config.
- A **levels** strategy builds new distances every day from ATR. Its stop is
  `sl_atr` × ATR from the trigger. Its take is a dollar rule (`day_take`,
  `target_take`) turned into points for each account.
- A strategy that is off, or has no booked account, places nothing. A booked
  strategy that will not trade today says why once (`inactive_today` in the
  journal and on the readiness line).

## Safety rules the code enforces

- **Armed flag.** `armed: false` is the default. Disarmed means dry run:
  signals are checked and journaled, nothing is placed. A strategy marked
  `shadow` is journaled only, even when armed.
- **Strategy switch.** Each strategy has its own `enabled` flag.
- **One trade a day.** A second signal for a strategy on the same day is
  refused. This holds across restarts (day state and journal are on disk).
- **Accept window.** A signal outside `accept_from_et`–`accept_until_et` is
  refused. `only_dates` limits an event strategy to its days.
- **Price check.** For a straddle the two entry prices must be exactly
  2 × `offset_pts` apart, or the signal is refused.
- **Brackets live at the broker.** Each entry carries its stop and target as
  one broker-side OSO order. If the app dies, the protection stays.
- **Both legs or none.** If one entry is rejected, the other is cancelled.
- **Sibling cancel.** When one entry fills, the app cancels the other at once.
  A clock check repeats the cancel if it did not stick.
- **Both filled.** If both entries fill, that account is flattened and its
  orders are cancelled.
- **Cancel time and flat time.** At `cancel_et` unfilled entries are cancelled.
  At `flat_et` any open position is flattened, with retries.
- **Manual positions are left alone.** Shortly before the fire, an account that
  already holds a position or a working order in the strategy's symbol is
  skipped for the day.
- **Kill switches.**
  - `POST /api/kill`: disarm, switch chart trading off, cancel and flatten
    every account.
  - Per-strategy kill (from the chart page): cancels that strategy's own
    orders, closes its own position, and blocks it for the rest of the day.
  - `POST /api/strategy-flatten`: flatten one strategy and switch it off.
- **Daily rules for levels strategies.** `day_take` and `day_lock` stop an
  account for the day. A real (non-paper) account sits out until the strategy's
  `ack_open_loss` is set.
- **Quiet window, 09:20–09:35 ET on weekdays.** No optional market-data
  requests, no new backtests, no adding accounts, and no desk writes from the
  MCP server.
- **Network guard.** The desk refuses any request whose `Host` is not loopback
  or listed in `allowed_hosts`. Writes also need a JSON body, and an allowed
  `Origin` when one is sent. `/api/trade/*` needs the desk key and a loopback
  host.
- **Login budget.** Logins per broker user are capped and backed off, so
  reconnects cannot use up the broker's request limit.
- **Chart trading.** Off by default. It has per-order and per-position size
  limits. It refuses orders in a strategy's symbol on an account where that
  strategy is working, and on its booked accounts 09:20–09:35 ET.

## Components

| Part | Where | What it is |
|---|---|---|
| Desk server | `homebase/server.py`, `homebase/engine.py` | The trading app. FastAPI on port 8850. Dashboard at `/`. |
| Timers | `homebase/timer.py`, `homebase/leveltimer.py` | Fire the strategies on the desk's clock. |
| Config | `homebase/config.py` | Strategy defaults, accounts, the book, the armed flag. |
| Broker layer | `homebase/broker/` | Tradovate adapter (REST + websocket, demo or live) and the paper adapter. |
| Daily rules, risk | `homebase/dayrules.py`, `homebase/levels.py`, `homebase/risk.py` | Take rules, sizing tiers, the day's levels, the drawdown meter. |
| Chart service | `homebase/charts/` | Live charts and the tick recorder. Its own process on port 8852. |
| Tick archive job | `homebase/ticks.py` | Keeps `~/futures_ticks` complete. |
| Strategy tester | `homebase/backtest/`, `homebase/strategies/` | Tick-replay backtests, heat maps, walk-forward, Monte Carlo, prop-eval scoring. |
| MCP server | `homebase/claude_mcp/` | Gives Claude the tester and a read of the desk. No trading tool. See `deploy/claude-mcp.md`. |
| Mac apps | `deploy/macapp/` | Viewer windows onto the pages. |
| Tools | `tools/` | `preopen_check.py` (read-only health check), `fake_desk.py` (a fake desk for browser checks). |
| Research records | `homebase/research/` | Equity curves shown on the desk page, and the scripts that build them. |
| Research | `research/` | Strategy research. See "Research" below. |
| Design history | `docs/superpowers/` | Old specs, plans and findings. `GOTCHAS.md` lists standing pitfalls. |

Not in git: `homebase/config.json` and `homebase/.state/` (credentials, tokens,
day state, journal).

### Accounts

- A broker account is one Tradovate account, demo or live, under a stored login.
  Many accounts can be on the desk at once.
- A paper account lives in the chart service (`homebase/charts/paperbook.py`).
  It needs no login. It fills orders against the live prints with the tester's
  fill rules. The desk drives it through `homebase/broker/paper.py`, so a
  strategy runs on paper through the same timer, engine and journal.

### Mac apps

Both apps are viewers. The trading runs in the launchd services. Closing a
window changes nothing.

- `deploy/macapp/build_app.sh` builds the classic viewer (tabs Desk / Charts /
  Backtest) as `~/Applications/Homebase.app`.
- `deploy/macapp/build_app_apple.sh` builds the newer viewer (tabs Desk /
  Charts / Lab). With no argument it builds `~/Applications/Homebase Next.app`.
  With `--as-homebase` it installs as `Homebase.app` and keeps the classic one
  as `Homebase Classic.app`.

## Run

```bash
cd ~/ramos-quant-homebase
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./deploy/install.sh            # install or refresh the launchd services
./deploy/install.sh remove     # unload them
```

`install.sh` stops and starts every service, the desk included. Do not run it
while a trade is open.

| launchd label | Runs | Port | Log (`homebase/.state/`) |
|---|---|---|---|
| `com.ramosquant.homebase` | `uvicorn homebase.server:app` | 8850 | `service.log` |
| `com.ramosquant.homebase-charts` | `python -m homebase.charts` | 8852 | `charts.log` |
| `com.ramosquant.homebase-ticks` | `python -m homebase.ticks` (hourly, at load, 17:20 and 05:30 local time) | – | `ticks.log` |
| `com.ramosquant.homebase-awake` | `caffeinate` (keeps the Mac awake on AC power) | – | – |

- Desk dashboard: `http://localhost:8850`. Charts: `http://localhost:8852`.
  Lab / Strategy Tester: `http://localhost:8852/backtest`.
- Restart the desk only: `launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase`
- The desk plist must include `--timeout-graceful-shutdown 5` (the template
  has it). Without it the chart service's open stream makes a desk restart
  hang until SIGKILL.
- Other devices: the desk accepts the host names in `allowed_hosts`
  (`config.json`). The chart service accepts loopback only.
- Pre-open check: `.venv/bin/python -m tools.preopen_check` (reads only).
- Morning review from the journal: `.venv/bin/python -m homebase.review`.

## Tests

```bash
.venv/bin/python -m pytest -q tests
node --test tests/js/*.test.mjs
```

- `tests/test_*.py`: Python tests for the engine, timers, broker layer, chart
  service, tester and MCP server.
- `tests/js/`: tests for the page JavaScript, run with Node's own test runner.
- `tests/conftest.py` makes any real broker call from a test fail, and points
  the tester's shared state at temp folders.
- `tests/test_release_rehearsal.py` plays whole trading days against a fake
  broker, clock and market data.

## Tick archive

`python -m homebase.ticks` keeps `~/futures_ticks` complete. Each run reads what the archive file and the chart
service's live recording of every recent session hold -- by the broker's tick id, one gap-free counter per contract --
and fetches from the broker's tick history only what is missing, then merges everything into the archive file (never
replaces; the live file is only read). The broker keeps ticks from 00:00 UTC of the previous day only, so a session's
first hours are gone at 20:00 ET on the session day: the pieces that leave first are fetched first. By day a run spends
at most 45 pages and never runs 09:20–09:35 ET; the live login only. A run with nothing to do says nothing.

- `homebase/.state/data_watch.json`: the data watchdog (`homebase/datawatch.py`), at the end of every run -- per
  market how late the live feed is, what share of the published tick ids the recording got in the last full hour,
  silence while the market is open; plus refused merges and what leaves the broker within 6 hours. One line in
  `ticks.log` while something is wrong. The chart strip and the connector (`data_coverage`, `desk_readiness`) read it.
- `homebase/.state/tick_coverage.json`: every root's last 30 sessions hour by hour -- holes and missing tick ids,
  each session classed whole / filling (the broker still has it: until when) / lost ("needs_massive") / vendor gap /
  not a hole, and what changed since the report before; one summary line in `ticks.log`. `--coverage` rewrites it.
  The charts draw these holes at their true width.
- `--rescan`: writes each recent file's hour-by-hour coverage into its manifest (`complete` there checks every hour).
- `--fill-from-massive --holes [--dry-run]`: the manual, one-shot Massive fill (`homebase/tickmassive.py`).

## Charts

`python -m homebase.charts` is the chart half of the terminal: multi-chart layouts on live ticks — time/tick/volume/range
bars, VWAP/EMA/SMA/VWMA/ADX, session levels, footprint, delta, cumulative delta, big prints, volume profile, Level 2
depth, an economic calendar and a news feed. Its OWN process: it holds no broker order connection and cannot slow the
trading app. Orders from the chart page go to the desk, which checks and places them. It records every live tick to
`~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`; past sessions come from the archive.

- Records live ticks for the app's six symbols (NQ ES YM RTY GC SI; the other nine were cut 2026-10-07 -- what the
  archive already holds of them stays on disk); `--roots` narrows it. The tick job merges this recording into the
  archive and fills what it missed.
- Settings > Data > **Refresh data** runs that tick job on demand (`homebase/charts/refresh.py`, `/api/refresh`): fetch
  what the broker still has, then fill the older holes from Massive when `MASSIVE_S3_KEY`/`MASSIVE_S3_SECRET` are in the
  service's environment (skipped, and said so, when they are not). One run at a time, never 09:20-09:35 ET.
- Records Level 2 depth for NQ and ES to `~/futures_depth` (`HOMEBASE_DEPTH_ROOTS` changes the list).
- BTC and MBT (CME crypto) trade 24/7: a session every day, 18:00 → 18:00 ET, weekends included -- in the chart
  service and the tick job alike. Never run `research/massive_ticks.py convert` over dates the desk recorded (from
  2026-09-23): it files Massive's CME trade dates (a Monday file holds the weekend's trades) and replaces an incomplete
  desk file whole. `python -m homebase.ticks --fill-from-massive` cuts each session to its own hours and merges.
- Replay any archived session (records nothing): `python -m homebase.charts --replay 2026-09-22 --roots NQ,ES,YM --speed 20 --port 8853`.
  A single chart can also replay a past session inside the live service (Bar Replay).
- Market-data login: `HOMEBASE_CHARTS_MD` is `demo` or `live`. The code default is `demo`; the shipped plist template
  sets `live`. The Settings dialog can switch it while running (saved in `homebase/.state/charts/settings.json`).
- Budget: one chart request per root per connection; gap refills ≤ 60/hour, never 09:20–09:35 ET.
- A symbol the md feed refuses (no realtimeId, an error answer, no answer in 15 s, no front contract) is isolated: the
  other symbols stay subscribed, the status bar shows it "unavailable" (the reason in the tooltip), and it is asked again
  after 10 min, then less often (never 09:20–09:35 ET), and on every reconnect. A socket that refuses every symbol is
  replaced, at most once per 10 min.
- Drawings (trend line, horizontal line, rectangle) are saved per symbol: `GET /api/drawings/{root}` returns a symbol's
  list, `PUT /api/drawings/{root}` replaces it (validated, ≤ 500 per symbol; writes from another site's page are
  refused). They live in `homebase/.state/charts/drawings.json`, beside the saved layouts (`layouts.json`). A page saves
  a symbol's whole list, so across open pages the last save wins: a page sees another page's edits only after a reload,
  and its next save overwrites them.
- Spec/plan: `docs/superpowers/specs/2026-09-25-live-charts-design.md`, `docs/superpowers/plans/2026-09-25-live-charts.md`;
  the TradingView-style page and drawing tools: `docs/superpowers/specs/2026-09-26-charts-tv-redesign-design.md`,
  `docs/superpowers/plans/2026-09-26-charts-tv-redesign.md`; Bitcoin (24/7): `docs/superpowers/specs/2026-09-26-charts-btc-24x7-design.md`,
  `docs/superpowers/plans/2026-09-26-charts-btc-24x7.md`.

## Strategy tester

The tester replays archived ticks through a strategy, one session at a time. Its API is served by the chart service
(`/api/tester/*`, `homebase/charts/tester_api.py`). The page is the Lab at `http://localhost:8852/backtest`.

- Data: `~/futures_ticks` (read only). A binary cache per session is built under `~/futures_derived/homebase_tape`.
- Fill rules (`homebase/backtest/engine.py`): a stop fills on touch, at the worse of its price and the print, plus
  slippage. A limit needs the price to trade one tick through it. A market order fills on the next print.
- A strategy is one class in `homebase/strategies/`. The desk strategies have tester twins that read the same
  config and the same level maths, so a backtest and a live fire use one definition.
- Each run is its own process. At most 2 backtests run at once during desk hours (weekdays 08:00–16:15 ET) and 4
  outside them. None starts 09:20–09:35 ET on weekdays.
- Heat maps (2 or 3 inputs, 60 cells by default), walk-forward (1 month to select, the next N months to test),
  Monte Carlo, and prop-eval scoring against the rule sets in `homebase/backtest/propsim/rules/`.
- The dates follow `research/edge-library/BLUEPRINT.md`, section 2. The default range is the build days,
  2021-09-22 to 2025-06-30. The test days start 2025-07-01: nothing refuses them, and a run that reads them is
  recorded in `homebase/.state/tester/spends.jsonl`.
- Draft strategies live in `~/.homebase/strategies/`. Listing or reading a draft never runs it. Its backtest runs
  inside the macOS sandbox (`homebase/backtest/draft.sb`). The desk never reads the drafts folder.
- Script run: `.venv/bin/python -m homebase.backtest.runner run --strategy nq930 ...`

## Research

Research lives in `research/`. It is offline work on stored data. The edge library's own rules forbid touching the
desk or placing orders.

- `research/edge-library/` — the edge library.
  - `EDGE_SPEC.md` — the rules every test follows.
  - `progress.md` — the log. Read it first when resuming.
  - `IDEAS.md` — every idea tested so far and its status.
  - `members/` — the saved strategies.
- `research/prop-portfolio/` — prop-firm pilots, one dated folder each (`2026-09-29` to `2026-10-02-*`).
- `research/nfp-2026-10-02/` — the work behind `gc_nfp`.
- `research/2026-10-01-nq-indicator-tests/` — a summary report of NQ indicator tests.

Derived price tapes (`research/**/*.tape`) and voided runs are not in git.

## What is left of the old webhook design

The first version took a 9:30 alert from a TradingView Pine script through a webhook. That path was removed on
2026-09-27. The routes `/hook`, `/api/tv-setup`, `/api/hook-url` and `/api/pine` no longer exist, nothing listens on
port 8851, and a test pins this (`tests/test_server.py`). The Pine sources and the desk page's "Pine script" button
are gone too: the strategies are the Python ones.

Leftovers you may still meet:

- `Engine.handle_alert` is still the entry point for straddles. The desk's own timer calls it. `POST /api/test-alert`
  calls it too, for a dry run only.
- `webhook_secret`, `hook_port` and `public_hook_url` are no longer fields in `config.py`. A `config.json` that still
  holds them loads the same, and the next save drops them.
- `pine_file` is still a field of a strategy in `config.py` (nq930's says `nq930.pine`, a file that no longer
  exists). Nothing reads it. It stays because a saved `config.json` carries it and the tester records it.
- The tunnel service is gone from the repo. `install.sh` unloads and deletes an old
  `com.ramosquant.homebase-tunnel` service if it finds one.
