# Algo per chart, Trading per chart, and both saved in layouts. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each chart can carry one assigned desk algo, showing its live run, its real past runs and a scoped Kill. Each chart also has its own Trading switch and its own account list. Saved layouts remember a chart's algo and accounts, and every Trading switch comes back OFF on load.

**Architecture:**
- The desk (`homebase/server.py`, `homebase/trading.py`, `homebase/engine.py`) gains two endpoints behind the existing `/api/trade/*` key guard:
  - a read-only bot history built from `.state/journal.jsonl`;
  - a per-strategy kill.
- The chart service proxies both. The fake desk mirrors both.
- The page moves from one global ticked-account list to a per-cell `trade` config (`{on, accounts}`) and a per-cell `algo`. Both are stored in the layout's cell entries.
- This plan **replaces screens-plan Task 7** ("bot on every chart of its root").
- **Order-panel Task 3 reads the selected cell's accounts and is disabled on a cell with Trading off.**

**Tech Stack:** Python 3 / FastAPI / pytest; plain-JS IIFEs; Lightweight Charts 5.2.1; Node 26 (`node --test tests/js/*.test.mjs`).

**Spec:** the design the user approved in chat on 2026-09-26 ("yes"), copied verbatim below. It is the binding authority.

> **Algo on a chart**
> - **Assigning:** each chart's gear gets an "Algo" setting that lists the desk's algos for that chart's instrument. Today that's just "NQ 9:30 Straddle · …047"; new ones appear as you add them. One algo per chart, or None.
> - **The live run:** a badge in the legend shows the algo's name, its state (idle, armed, placing, in trade, done) and today's P&L. Its two waiting entry orders, the fill, its stop-loss and target, and the exit are drawn as lines and markers. They're marked BOT and can't be dragged, so you can't move the bot's orders by accident.
> - **Past runs:** each real past day the bot ran on that account shows as entry and exit markers. Hovering one gives that day's result. Days it skipped show a small "skipped" flag with the reason.
> - **Kill:** a red Kill button on the badge. It asks first, then disarms that algo, cancels its orders and flattens its position, on that algo's accounts only. Today the desk only has a Kill for everything, so this is a new desk feature.
>
> **Trading per chart**
> - **The switch:** each chart gets its own Trading switch, off by default. Only charts with it on get the Buy/Sell buttons, draggable order lines, and Buy/Sell in the right-click menu.
> - **Accounts:** each trading chart picks its own accounts, shown as DEMO/LIVE chips on the chart. The Trade menu becomes where you set things up for the selected chart.
> - **The order panel** follows whichever chart is selected, and is greyed out on a chart with Trading off.
> - **Charts with Trading off** still show your positions and working orders as plain view-only lines, so you never lose sight of an open position.
>
> **Layouts:** a saved layout remembers each chart's algo and account list. Every Trading switch comes back off when you load a layout, so you switch it on yourself.

## Global Constraints

- Never place real orders. Tests never open broker (Tradovate) connections or use its tokens, and never write to `~/futures_ticks`. Do not restart or touch any running service or launchd job.
- The 9:30 bot's own order bodies and timing are unchanged. The per-strategy kill must not affect any other strategy or any account outside that strategy's book.
- The desk endpoints sit behind the existing `X-Homebase-Key` guard and netguard (Host allowlist, no Origin, JSON-only on writes). The chart service proxies them the same way it proxies `/api/trade/*` today.
- Nothing may reach an account the user did not choose for THAT chart. The LIVE arm, the confirm dialog (unless one-click), the frozen preview→send, the shown∩fresh account resolution and the in-flight lock all stay exactly as they are.
- Loading a layout (or a template) never turns Trading on. There are no native dialogs.
- Lucide icons only. Look like TradingView. The asset cache-bust stays `?v=4`.

---

### Task 1: Desk: bot history + per-strategy kill (MONEY PATH)

This task runs on `feat/desk-stoplimit` in `.worktrees/stoplimit`, after that branch's fix round, and ships with the same desk restart.

**Files:**
- Modify:
  - `homebase/trading.py` or a new `homebase/bothistory.py` (pure journal → runs);
  - `homebase/server.py` (routes under the `/api/trade/*` guard);
  - `homebase/engine.py` (a per-strategy "killed today" that the timer honours like the prestage skip);
  - `homebase/charts/desk.py` (proxy);
  - `tools/fake_desk.py` (mirror).
- Test: `tests/test_bothistory.py`, `tests/test_bot_kill.py`, plus the proxy and fake desk tests.

**Interfaces:**
- `GET /api/trade/bot-history?strategy=<name>&days=<1..400, default 120>` returns

  ```
  {strategy, symbol, runs: [{date, account, status: "traded"|"skipped"|"refused"|"no_fill"|"killed"|"error",
  reason?, legs: [{side, price, ts}], entry?: {side, price, ts}, exit?: {price, ts, kind: "tp"|"sl"|"flat"|"other"},
  pnl_usd?}]}
  ```

  - It is built from `.state/journal.jsonl` events: `placed`, `entry_fill`, `exit_fill`, `alert_refused`, `signal_refused`, `place_failed`, `both_filled_emergency`, the skip events, `kill_switch`, and the new `strategy_killed`.
  - The journal is read in a thread and cached by (size, mtime).
  - Malformed lines are skipped.
  - `pnl_usd` uses the contract's point value × qty, net of $4 per round trip per contract. If the fills can't be matched, `pnl_usd` is left out.
- `POST /api/trade/bot-kill {client_id, strategy}` does four things:
  - marks `strategy` killed for today, so the timer does not fire it and a staged fire is abandoned;
  - cancels that strategy's known working orders (its DayState legs);
  - flattens that strategy's contract on its booked accounts ONLY;
  - journals `strategy_killed` with results.

  It returns `{ok, results: {account: {...}}}`.
  - It does not disarm the desk globally and does not disable chart trading.
  - It is idempotent per `client_id`.
- The chart service exposes `GET /api/desk/bot-history` and `POST /api/desk/bot-kill`.

- [ ] Tests first. Cover the journal fixtures:
  - a traded day (TP and SL);
  - a skipped day;
  - refused;
  - no fill;
  - a malformed line;
  - two accounts on one day.

  For the kill, cover:
  - another strategy is untouched;
  - an account outside the book is untouched;
  - the timer won't fire after a kill (use a fake clock);
  - the client_id is deduplicated.

  Everything runs with fake adapters.
- [ ] Implement, run the full pytest and node suites, commit. The report lists every live-desk file touched.

### Task 2: Trading per chart (MONEY PATH)

**Files:**
- Modify:
  - `homebase/static/charts/trade.js`: pure helpers for the per-cell trade config;
  - `tradeui.js`: `effectiveMode` becomes per cell, and the Trade menu edits the selected cell;
  - `tradelines.js`: the block and draggable lines only when the cell's Trading is on; view-only lines otherwise;
  - `chartmenu.js` / `app.js`: Buy/Sell menu items only on trading cells; layout save and load of `trade`/`algo`;
  - `panel.js` if it reads the global ticked list;
  - `charts.css`.
- Test: `tests/js/trade.test.mjs`.

**Interfaces:**
- The cell config gains `trade: {on: boolean, accounts: string[]}` (default `{on:false, accounts:[]}`) and `algo: string|null`.
- `HBTrade.cellTrade(raw) -> {on, accounts}` sanitises the config: at most 20 ids, strings of 1–64 characters.
- `HBTrade.loadedTrade(raw) -> {on:false, accounts}` always forces `on` false. It is used by the layout and template loads.
- `HBTrade.tradeMode(desk, cellTrade)` replaces the global-prefs version. Its reasons:
  - `on:false` → mode `'off'`, reason "Trading is off on this chart";
  - no accounts → "Pick accounts for this chart in the Trade menu";
  - otherwise the existing rules.
- `prefs.ticked` is retired from order routing. Migration: on the first load, if a cell has no `trade` config and the old `prefs.ticked` is non-empty, the SELECTED cell gets `{on:false, accounts: prefs.ticked}`. Trading stays off, and other cells get nothing.
- Global prefs keep `oneClick`, `qty`, `slTicks` and `tpTicks`.

**Behaviour:**
- **Trade menu:** its header reads "Trading on this chart — NQ · chart 2" with a switch. Account rows are ticked per cell, with DEMO/LIVE chips. The LIVE arm is unchanged.
- **Trading cells:** the legend shows the account chips next to the Buy/Sell block, e.g. "…047 DEMO".
- **Trading OFF on a cell:**
  - no Buy/Sell block;
  - no chart-menu Buy/Sell/Cancel/Flatten/Reverse items;
  - the lines for ALL accounts' positions and working orders in that root are view-only: no drag, no ×;
  - the label reads "BUY LMT 2 · 2 accts · view only".
- **Trading ON:** the lines for the cell's accounts behave as now. Other accounts' lines stay view-only.
- **Every order-sending path takes its accounts from the cell it was started from:** the Buy/Sell block, a chart-menu item, a line drag or ×, and the order panel. The panel's per-account Close/Cancel buttons (bottom panel) act on the named account and keep their LIVE-arm check.
- **Layouts:** layout and template saves write `trade.accounts` and `algo`; loads go through `loadedTrade`. Changing a cell's symbol keeps its trade config but clears `algo` if the algo's symbol no longer matches.

- [ ] Tests first for `cellTrade`, `loadedTrade`, the per-cell `tradeMode` and the migration. Then implement, run the full suites, commit.

### Task 3: Algo on a chart (UI + one money action)

This replaces screens Task 7.

**Files:**
- Modify:
  - `homebase/static/charts/settings-dialog.js`: an "Algo" select on the chart's gear, listing `desk.bot.strategies` whose `symbol` matches the cell's root, shown as `"<botName> · …<last3 of each booked account>"`, plus "None";
  - `trade.js`: pure helpers for the bot badge state, lines, markers and past-run markers;
  - `tradelines.js`: the bot part;
  - `deskclient.js`: `botHistory(strategy)` fetches, cached for 60 s, refetched on a new day or when an `exit_fill` or skip event arrives;
  - `icons.js` (Lucide `bot`, `octagon-x`), `charts.css`.
- Test: `tests/js/trade.test.mjs`.

**Behaviour:**
- **Legend badge** (only when the cell has an `algo`): a bot icon, the name, a state pill and today's P&L. The state pill is one of idle / armed / placing / in trade / done / skipped / killed / shadow. The badge also has a red Kill button (Lucide `octagon-x`).
- **Kill:**
  - The confirm reads "Kill NQ 9:30 Straddle — cancel its orders and flatten its NQ position on …047. The desk stays armed for other strategies." Accounts are listed with DEMO/LIVE chips, and a LIVE account needs the LIVE arm.
  - It sends `bot-kill` through the guarded send (in-flight lock, one toast per account).
  - Kill is offered even when the cell's Trading is off: it is the emergency stop, not trading.
- **Today:**
  - the bot's working legs are dashed lines labelled "BOT BUY STP 10 @ …", with no drag and no ×;
  - its fill is a marker; SL/TP are lines labelled "BOT SL" / "BOT TP"; the exit is a marker.
- **Past runs:**
  - from `bot-history`, an entry marker (arrow up/down) and an exit marker (circle) per traded run;
  - the tooltip reads "2026-09-24 · …047 · Buy 10 @ 30,120.25 → TP 30,135.25 · +$2,960";
  - skipped/refused/no-fill days get a small grey flag at the session open, with the reason in the tooltip;
  - markers are merged through the existing extra-markers hook;
  - only runs inside the loaded history range are drawn.
- A cell without an `algo` shows no bot overlay at all, even for the bot's root.

- [ ] Tests first for the badge state mapping, the past-run → marker mapping (including skipped/refused and a missing P&L), and the name formatting. Then implement, browser-check on the fake desk (the controller runs the servers), commit.
