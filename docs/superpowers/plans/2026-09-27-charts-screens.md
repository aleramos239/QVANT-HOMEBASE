# Charts screens build: chart trading, live strategies, Strategy Tester panel, per-chart gear. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the page half of two finished backends on the homebase chart page:
- trading from the chart and the desk's live strategies on it (the desk's `/api/trade/*` behind the chart service's `/api/desk/*` proxy, and `{"type": "desk"}` / `{"type": "quote"}` messages on `/ws`);
- the Strategy Tester panel (`/api/tester/*`);
- a hover gear on each chart panel that opens that chart's Settings.

**Architecture:** The page stays plain scripts, as in the redesign. Each file is an IIFE exposing one `window.HB*`. There are two new **pure** modules, both Node-tested:
- `trade.js` (`HBTrade`): prefs, Limit/Stop inference, order bodies, the lines and their dollars, confirm texts, toasts, markers, the bots' badge/lines/markers and table rows;
- `tester.js` (`HBTester`): the run form, the holdout rule, the request body, progress, tiles, tables, trade marks and the jump interval.

There are six new browser modules:
- `deskclient.js` (`HBDeskClient`): the desk store, the actions sender and the toasts;
- `panel.js` (`HBPanel`): the shared, collapsible bottom panel and the four trading tabs;
- `tradeui.js` (`HBTradeUI`): the Trade menu, the confirm dialog, the actions and the chart-menu items;
- `tradelines.js` (`HBTradeLines`): a per-chart overlay with the Buy/Sell block, the lines, the chips, dragging, the execution markers and the bot overlay;
- `testerui.js` (`HBTesterUI`): the Strategy Tester tab;
- `testerlayer.js` (`HBTesterLayer`): the per-chart tester trades and the jump.

`cell.js` gains four generic hooks: overlays, extra markers, reach/focus and the gear. `app.js` gains a `page` object that the modules use for menus and dialogs.

On the Python side there is one piece: a **fake desk** (`tools/fake_desk.py`). The chart service can point its desk link at it **only in replay** (`--fake-desk PORT` with `--replay`).

**Tech Stack:**
- Python 3 / FastAPI / pytest / httpx;
- Lightweight Charts 5.2.1, vendored as `window.LightweightCharts`;
- Lucide icons (`lucide-static@1.48.0`), inlined;
- Node 26 (`node --test`).

**Specs** (the executor reads the "Page" sections of the first two, and the last two in full for look and conventions):
- `docs/superpowers/specs/2026-09-26-desk-on-chart-trading-design.md`, section "Page";
- `docs/superpowers/specs/2026-09-26-strategy-tester-design.md`, section "Page";
- `docs/superpowers/specs/2026-09-26-charts-tv-redesign-design.md`;
- `docs/superpowers/specs/2026-09-26-charts-tools-settings-design.md`.

## Global Constraints

- **Plain scripts:** each file is an IIFE exposing one `window.HB*` namespace. Pure halves load in Node (`module.exports`) with no browser globals at load time.
- **No native dialogs:** never `alert`, `confirm` or `prompt`. All text input is inline, and every message is set with `textContent`.
- **Icons:** Lucide only (`lucide-static@1.48.0`, inlined SVG in `icons.js`, with the ISC header list updated). Never TradingView's icons, logo or branding.
- **Design tokens** (redesign spec):
  - tokens: `--frame --panel --text --text-2 --border --grid --hover --pill --accent --accent-soft --up --down --down-soft --warn`;
  - light theme by default, dark supported;
  - font stack: `-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`;
  - menus and dialogs: radius 8, with the spec's shadows;
  - every control: a 2px `--accent` `:focus-visible` outline;
  - numbers: `font-variant-numeric: tabular-nums`.
- **RR** is written `1:X` (`RR 1:2`, `RR 1:1.5`). Every P&L shows **dollars**. **Sharpe** is shown in every tester summary.
- **Safety:**
  - Tests never touch a broker or the real desk (:8850), and never read or send `homebase/.state/desk.key`.
  - Browser checks run only against the **fake desk** on the dev replay.
  - **Never place real orders.**
  - Never write under `~/futures_ticks`.
- **Shell:** the user's hook blocks `rm -rf` and any command containing both the words "live" and "tradovate". Use `rm` on named files, or `git clean -n` first.
- **Commits:** a conventional message at the end of each task, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- **Cache-bust:** every page asset this build changes or adds loads with `?v=4` in `charts.html`. The rest keep `?v=3`.

## Execution notes (plan-level)

- **Base and where:**
  - This build starts from `main` **after** `feat/charts-build2` is merged into it. Precondition: `git -C /Users/ramoscapital/ramos-quant-homebase merge-base --is-ancestor feat/charts-build2 main` exits 0. If it does not, stop and tell the controller.
  - The controller creates the worktree:
    ```
    git -C /Users/ramoscapital/ramos-quant-homebase worktree add .worktrees/screens -b feat/charts-screens main
    ln -s /Users/ramoscapital/ramos-quant-homebase/.venv /Users/ramoscapital/ramos-quant-homebase/.worktrees/screens/.venv
    ```
    All work happens in `.worktrees/screens`.
  - Never modify, check out, stash or commit anything in `/Users/ramoscapital/ramos-quant-homebase` itself: that checkout runs the LIVE desk.
- **Python** is `.venv/bin/python`, a symlink to the live venv. Never `pip install` into it. Whole suite: `.venv/bin/python -m pytest -q`.
- **Node:** `node --test tests/js/*.test.mjs`. Node 26 needs file arguments; `tests/test_charts_js.py` runs them all inside pytest.
- **Syntax check** for the page scripts: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`.
- **No servers from Bash:** never `python -m homebase.charts`, uvicorn, `python -m tools.fake_desk`, `deploy/install.sh` or `launchctl`. The controller runs every server through the preview tool. After Task 2 the controller adds these two entries to `/Users/ramoscapital/ONYX TRADING/.claude/launch.json`:
  ```json
  {"name": "homebase-fake-desk", "runtimeExecutable": "/bin/sh", "runtimeArgs": ["-c", "cd /Users/ramoscapital/ramos-quant-homebase/.worktrees/screens && exec .venv/bin/python -m tools.fake_desk --port 8859"], "port": 8859, "autoPort": false},
  {"name": "homebase-charts-screens-replay", "runtimeExecutable": "/bin/sh", "runtimeArgs": ["-c", "cd /Users/ramoscapital/ramos-quant-homebase/.worktrees/screens && exec .venv/bin/python -m homebase.charts --replay 2026-09-22 --roots NQ,ES,YM --speed 20 --start 09:25 --port 8854 --fake-desk 8859"], "port": 8854, "autoPort": false}
  ```
  Start the fake desk first. Drive it with `curl -s -X POST http://127.0.0.1:8859/fake/... -H 'content-type: application/json' -d '{…}'`. Every browser check below says "(fake desk)".
- **Script order in `charts.html` once all tasks are done:**
  1. lightweight-charts, icons, catalog, primitives, drawings, position, settings, events, scrollback, cell, settings-dialog, chartmenu;
  2. **trade, deskclient, panel, tradeui, tradelines, tester, testerui, testerlayer**;
  3. app.
- **Lightweight Charts 5.2.1 facts used here** (checked in the vendored bundle):
  - Series markers accept `position: 'atPriceTop' | 'atPriceBottom' | 'atPriceMiddle'` together with `price`.
  - `createPriceLine({price, color, lineWidth, lineStyle, axisLabelVisible, title})` returns a line with `applyOptions`. `series.removePriceLine(line)` removes it.
  - A series primitive's `updateAllViews()` runs before every redraw of its pane, including autoscale, scroll, zoom and resize. Task 6 uses that as the reposition hook for the DOM chips.
  - LWC listens to mouse events on its own canvases. A pointer captured by a DOM element above the chart (`setPointerCapture`) never reaches LWC, so dragging a chip needs no `handleScroll` toggling.
  - `logicalToCoordinate` is right only for **integer** logicals. The drawings code's `timeToX` handles fractions; the tester primitive uses it.
- **The desk messages as they arrive on `/ws`** (main, `homebase/charts/desk.py`):
  - `{"type": "desk", "event": "state"|"account"|"bot"|"fill"|"result", "data": …}`;
  - `{"type": "desk", "down": "<reason>"}`;
  - `{"type": "quote", "root", "bid", "ask", "last", "ts_ms", "asof": "last_trade"}`.
  - These messages have no chart `id`: `app.js` routes them before its per-chart lookup.
- **Desk state** (`trading.py` `ChartDesk.snapshot`):
  ```
  {enabled, limits:{max_order_qty,max_position_qty},
   accounts:[{id,label,pinned,broker_account,env:"demo"|"live",connected,error,tradable,balance,realized_pnl,
              positions:[{contract_id,symbol,net,avg_price,root,point_value}],
              orders:[{order_id,symbol,side,type,qty,price,stop_price,status,owner}],
              fills:[{id,order_id,symbol,side,qty,price,time(ISO),owner}], strategies:[name]}],
   bot:{date, strategies:{<name>:{symbol,kind,enabled,shadow,offset_pts,sl_pts,tp_pts,book,
        timer:{stage,gate(true|false|null),adx,anchor}, day_status,
        accounts:{<id>:{status,qty,upper,lower,entry_side,entry_fill,entry_qty,sl,tp,exit_fill,exit_reason,pnl,note}}}}}}
  ```
  - Positions carry **no open P&L**; the page computes it from the quote's `last`.
  - Orders carry **no bracket link**; the page infers SL/TP (ruling S8).
  - Actions answer `{"results": {<account>: {ok, order_id, error[, refused]}}}`. A proxy or desk failure answers `{"detail": "..."}` with its HTTP status (403/413/415/503/504/502).
- **Tester API** (main, `homebase/charts/tester_api.py`):

  | Route | Answers |
  |---|---|
  | `GET /api/tester/strategies` | `[{id,name,root,session_window,bar_minutes,inputs:[{key,label,type:int\|float\|bool\|choice,default,min,max,step,choices}]}]` |
  | `GET /api/tester/prop-rules` | `[{id,name,version,confirmed}]` |
  | `POST /api/tester/run` | `{id}`, or 400 `{detail}` |
  | `GET /api/tester/run/{id}` | `{id,status:queued\|running\|done\|error\|cancelled,phase,done,total,error?}` |
  | `POST /api/tester/run/{id}/cancel` | |
  | `GET /api/tester/run/{id}/bundle` | `{run, trades, equity, plots, propsim}` |
  | `GET /api/tester/runs` | `[{id,strategy,created,status,range,holdout,trades,net_profit}]` |

  The bundle's parts:
  - `run` carries `strategy{id,name,root}`, `inputs`, `range{kind,start,end,label,holdout}`, `qty`, `commission`, `slippage_ticks`, `capital`, `holdout`, `holdout_reason`, `prop_rules`, `coverage{sessions,used,skipped,skipped_by_reason,no_trade,skipped_by_error,skipped_by_data}`, `engine`, `fill_law`, and `report{summary:{all,long,short},by_year,by_month,skipped_by_error,sharpe_basis}`.
  - `trades` rows are `{date,side:long|short,qty,entry_ms,entry_price,exit_ms,exit_price,exit_reason,order_price,sl,tp,gross,commission,net,mae_pts,mfe_pts,mae_usd,mfe_usd,bars,seconds}`.
  - `equity` is `{t_ms,equity,drawdown}`.
  - `plots` is `{plots:{name:[[t_ms,v]…]},hlines:[{name,price,date}]}`.
  - `propsim` is `{rules:{id,name,version,confirmed,label},caveat,headline:{eval_pass_p,eval_pass_ci:[lo,hi],bust_p,median_days_to_pass,funded_expected_cheque,…}}`, or it carries `error` / `skipped`.

## Plan-level rulings (ambiguities decided before execution)

- **S1 Base.** This build sits on main + build2. Any line number quoted from build2 may have moved, so tasks name functions, not lines.
- **S2 Fake desk only in replay.**
  - `python -m homebase.charts --fake-desk PORT` is an argparse error without `--replay`, and also when PORT is 8850 (the real desk).
  - `create_app(fake_desk_factory=…)` raises `ValueError` when `replay` is None.
  - The link reads the key from `homebase/.state/fake-desk.key`, **never** `desk.key`.
  - The fake desk binds 127.0.0.1 only and refuses ports 8850/8852/8853/8854.
  - The launchd plist runs no `--replay`, so production cannot reach this path.
  - In replay, quotes are noted **only** when a fake link exists, so the existing "replay never links to the desk" test stays true.
- **S3 Toasts come from the HTTP answer only.** SSE `result` events are ignored, so there are no double toasts. A `Filled 2 @ 30,910.25 · …047` toast comes from an SSE `fill` whose `order_id` this page placed. Bot fills and other tabs' fills get no toast.
- **S4 Confirm.** Every action goes through the confirm dialog unless one-click trading is on: order, modify (a drag), cancel, cancel-all, flatten, and × on a position or order. **Reverse always confirms.** The dialog's checkbox "Don't ask again (one-click trading)" switches one-click on.
- **S5 LIVE accounts.** Ticking a LIVE account in the Trade menu needs a second click within 3 s. The row reads "Tick LIVE — real orders. Click again". The confirm dialog shows LIVE badges in `--down`.
- **S6 Which accounts draw lines.**
  - Lines, the Buy/Sell block and execution markers use the **ticked** accounts.
  - The bottom panel's tables list **every** account.
  - The bot overlay uses every account booked to the bot.
- **S7 Modes.** `HBTrade.tradeMode` gives one of four modes:

  | Mode | Condition | What the page does |
  |---|---|---|
  | `down` | no desk state | Trade dot red; no block; no lines; the menu says why |
  | `off` | the desk's chart trading is off | lines read-only (no × or drag); the menu says "Chart trading is off on the desk" plus an "Open the desk" link |
  | `none` | no ticked account is tradable | lines read-only; no block |
  | `on` | trading possible | everything live |
- **S8 Brackets.** A working order is an **SL** when it is opposite to the account's position in that contract and its type contains "Stop". It is a **TP** when it is opposite and its type is Limit. Every other order is a plain order.
  - Orders with the same kind, side, type and price merge across accounts into one line, and positions with the same side and average price merge too. The label then reads `3 accts`. A drag modifies each order in the line; × cancels or flattens each account.
  - Orders with an `owner` (a bot's) are never drawn as order lines, since the bot overlay draws them, and they have no Cancel button in the table.
- **S9 Order type from a right-click:**

  | Side | Clicked price | Type |
  |---|---|---|
  | Buy | above the ask | **Stop** |
  | Buy | at or below the ask | **Limit** |
  | Sell | below the bid | **Stop** |
  | Sell | at or above the bid | **Limit** |

  With no quote, only Cancel all / Flatten / Reverse show. Brackets from the prefs' ticks (0 = off) use the order price as reference, and the **last trade** for Market orders, which is what the desk checks against.
- **S10 Quotes.** The block shows bid/ask "as of last trade" (tooltip). It is greyed when the quote is more than 30 s old against the page clock, which is the replay clock in a replay. The spread is shown in ticks.
- **S11 Drag** is by the chip only; TradingView also lets you drag the chip. Esc, `pointercancel` or window blur puts the line back. The confirm dialog shows `Move SL 3 30,885.00 → 30,880.00`. Cancelling the dialog puts the line back.
- **S12 Bot badge and lines.**
  - Names: `nq930` and `ym930` are "9:30 bot"; `nq10am` is "10am bot"; anything else keeps its key.
  - Badge: `9:30 bot · TREND ADX 23.4 · placed`. The status is `off` when the bot is disabled, `done +$876` when done (the sum of the accounts' pnl), and otherwise `day_status`, or the timer stage while the day is idle. Shadow bots get ` · shadow`.
  - Lines: `9:30 BUY STOP 10 @ 30,925.00` while placed; SL/TP while live. They are dashed `--warn` (entries), `--down` (SL) and `--up` (TP), read-only, and drawn with a bot icon.
  - Markers come from the account fills whose `owner` is the bot. The exit marker's text is the account's pnl.
- **S13 The Settings dialog gets no Trading tab.** Trading prefs are per viewer and live in the Trade menu.
- **S14 Per-chart gear.** It sits in the chart's axis corner (the square under the price axis, right of the time axis) and shows on panel hover or keyboard focus. A click selects that chart and opens its Settings. The chart menu's `Settings…` now opens the right-clicked chart explicitly.
- **S15 Bottom panel.**
  - One panel for everything, with tabs **Positions · Orders · Fills · Accounts · Strategy Tester**.
  - Collapsed, only its 34px tab bar shows. It opens to 260px by default and is resizable by its top edge (120px to 70vh).
  - Clicking the active tab collapses it; any tab opens it.
  - `{open, h, tab}` persists in `localStorage` `hb_panel`, inside try/catch.
- **S16 Holdout.** The page mirrors the server's rule so Run can say why before sending, but the server stays authoritative and its 400 `detail` is shown inline.
  - A range reaching 2025-01-01 or later needs the switch on and a reason (one line, at most 200 characters).
  - With the switch on but a range inside the research window, **no** `holdout` field is sent, so there is no spend.
  - Custom dates use `<input type="date">`.
- **S17 Prop rules** are a select at the bottom of the inputs dialog, because they are part of the run request. The default is `lucid-flex-50k@2026-08`. An unconfirmed set shows the amber badge `unconfirmed rules`.
- **S18 Recent runs.** A `Recent runs ▾` menu in the tester header lists `/api/tester/runs`. Loading a done run fills the form from its meta, so runs the assistant starts from scripts appear too.
- **S19 Run label.** With no run loaded, or a loaded one unchanged, the button reads `Run`. Once any form value differs from the loaded run, it reads `Update report`.
- **S20 Jumping to a tester trade.**
  - The chart service has no "history at a date" op, and this build does not add one. A jump uses the chart of the strategy's root: the selected one if it shows that root, else the first that does, else the selected chart switches root.
  - It loads older chunks through the existing scroll-back (`cell.reach`), showing progress and allowing cancel.
  - When the chart's interval cannot reach the trade under the 200,000-bar cap, the chart first switches to the finest of 5m / 15m / 1h / 4h / D that fits (`HBTester.reachSpec`), and a note says so.
  - Then it zooms to the trade and selects it.
  - A follow-up server op ("history ending at a date") would make 1m jumps possible. It is out of scope and is listed in the final report.
- **S21 Tester chart marks.**
  - Markers: an entry ▲ (long, `--accent`) or ▼ (short, `--down`) at the entry price; an exit ● at the exit price, `--up` or `--down` by net, with text `+$230`.
  - The selected trade gets short entry, SL and TP segments, plus a dashed connector from entry to exit, all drawn by a primitive.
  - Plots are overlay line series that never take part in autoscale. Hlines are segments over their session's bars.
  - `Hide trades` hides the markers, segments and plots.
- **S22 Markers.** Trading, bot and tester markers share the candle series' one markers plugin through `cell.setExtraMarkers(key, list)`. Each list is keyed by source and placed by `HBDrawings.placeMarkers`. The existing big-prints markers stay, capped at 600.
- **S23 Fill times** are ISO strings. The page parses them with `Date.parse`, and an unparseable fill is skipped.
- **S24 Toast placement:** top-right under the toolbar, so they never cover the bottom panel. At most 5 show; ok toasts last 5 s and errors 10 s; each has an × close.

## File map

| File | Status | Responsibility |
|---|---|---|
| `tools/__init__.py` | new | makes `tools` importable |
| `tools/fake_desk.py` | new | the fake desk: `/api/trade/*` shapes, SSE, and the `/fake/*` controls |
| `homebase/charts/__main__.py` | mod | `--fake-desk PORT`, only with `--replay` |
| `homebase/charts/server.py` | mod | `create_app(fake_desk_factory=…)`, replay only; replay quotes when linked |
| `tests/test_fake_desk.py` | new | the fake desk |
| `tests/test_charts_desk_server.py` | mod | the replay-only override |
| `homebase/static/charts/trade.js` | new | `HBTrade`, pure |
| `homebase/static/charts/tester.js` | new | `HBTester`, pure |
| `homebase/static/charts/drawings.js` | mod | `placeMarkers` (pure) |
| `homebase/static/charts/deskclient.js` | new | `HBDeskClient` |
| `homebase/static/charts/panel.js` | new | `HBPanel` and the trading tabs |
| `homebase/static/charts/tradeui.js` | new | `HBTradeUI` |
| `homebase/static/charts/tradelines.js` | new | `HBTradeLines` |
| `homebase/static/charts/testerui.js` | new | `HBTesterUI` |
| `homebase/static/charts/testerlayer.js` | new | `HBTesterLayer` |
| `homebase/static/charts/cell.js` | mod | gear, overlays, extra markers, `reach`, `focusRange`, `whenLoaded`, palette `warn` |
| `homebase/static/charts/app.js` | mod | `page` object, ws routing, gear host, Trade button, panel mount, overlays host |
| `homebase/static/charts.html`, `charts/charts.css`, `charts/icons.js` | mod | shell, styles, icons |
| `tests/js/trade.test.mjs`, `tests/js/tester.test.mjs` | new | Node tests |
| `tests/js/drawings.test.mjs` | mod | Node tests |

---

### Task 1: The per-chart gear

**Files:**
- Modify: `homebase/static/charts/cell.js` (constructor markup, `build()`, new `placeGear()`)
- Modify: `homebase/static/charts/app.js` (`hostFor`, `chartSettings`, `MENU_ACTS.settings`)
- Modify: `homebase/static/charts/charts.css`, `homebase/static/charts.html` (`cell.js`, `app.js` and `charts.css` go to `?v=4`)

**Interfaces:**
- Produces:
  - the host callback `onChartSettings(cell)`;
  - `chartSettings(cell = cur())` in app.js.

**Requirements:**
- A 22px Lucide `gear` (already `HBIcons.gear`) fills the corner square under the price axis. The square is the price axis width by the time axis height, at `right: 0; bottom: 0` of the panel.
- The gear is invisible (opacity 0) until the panel is hovered or the button has `:focus-visible`. Its colour is `--text-2`; on hover it becomes `--text` on `--hover`.
- Tooltip and `aria-label`: "Chart settings".
- A click selects that chart and opens **its** Settings dialog. The toolbar gear still opens the selected chart's.
- The chart menu's `Settings…` opens the right-clicked chart's dialog. That chart is already selected, and it is now passed explicitly.

- [ ] **Step 1: cell.js**
  - Add `<button class="cell-gear" type="button" title="Chart settings" aria-label="Chart settings"></button>` as the last child of the panel markup in the constructor.
  - Keep `this.gear`, fill it with `window.HBIcons.gear`, and wire it:
    ```js
    this.gear.addEventListener('click', (e) => { e.stopPropagation(); host.onChartSettings(this); });
    ```
  - Then add:

```js
  /* The gear sits in the chart's axis corner (TradingView's): as wide as the price axis, as tall as the time axis.
     Both are 0 before the first layout, so this runs again on every size change. */
  placeGear() {
    if (!this.chart) return;
    const w = this.chart.priceScale('right').width(), h = this.chart.timeScale().height();
    this.gear.hidden = !(w > 0 && h > 0);
    this.gear.style.width = `${w}px`;
    this.gear.style.height = `${h}px`;
  }
```

  - In `makeChart()`, after the chart exists: `this.chart.timeScale().subscribeSizeChange(() => this.placeGear());`.
  - At the end of `build()`: `requestAnimationFrame(() => this.placeGear());`.

- [ ] **Step 2: app.js**
  - In `hostFor`, add `onChartSettings(cell) { chartSettings(cell); },`.
  - Change `function chartSettings()` to `function chartSettings(c = cur())`. Its first lines become:
    ```js
    if (!c) return;
    select(cells.indexOf(c));
    ```
  - The rest of the function is unchanged; it already mounts with `cell: c`.
  - Change `MENU_ACTS.settings` to `(ctx) => chartSettings(ctx.cell)`.
  - The toolbar button becomes `$('#tbSettings').onclick = () => chartSettings();` so the click event is never passed as a cell.

- [ ] **Step 3: CSS**

```css
/* the per-chart gear, in the axis corner; shown on hover (TradingView) */
.cell-gear { position: absolute; right: 0; bottom: 0; z-index: 7; display: grid; place-items: center; opacity: 0;
  color: var(--text-2); background: var(--panel); border-radius: 0 0 6px 0; transition: opacity .12s; }
.cell-gear .ic { width: 16px; height: 16px; }
.panel:hover .cell-gear, .cell-gear:focus-visible { opacity: 1; }
.cell-gear:hover { color: var(--text); background: var(--hover); }
```

- [ ] **Step 4:** Syntax-check every page script; run `node --test tests/js/*.test.mjs` (green).

- [ ] **Step 5: Commit**
  ```
  feat(charts): a gear in each chart's axis corner opens that chart's Settings
  ```

**Controller browser check (replay :8854):**
- Hovering each of the four charts shows its gear.
- Clicking the gear on a non-selected chart selects it and opens Settings for it; a live preview changes only that chart.
- The toolbar gear and the right-click `Settings…` still work.
- The gear is reachable with Tab.
- The dark theme renders it correctly.
- There are zero console errors.

---

### Task 2: The fake desk and the replay-only `--fake-desk` override

**Files:**
- Create: `tools/__init__.py` (empty), `tools/fake_desk.py`
- Modify: `homebase/charts/__main__.py`, `homebase/charts/server.py` (`create_app`)
- Test: `tests/test_fake_desk.py` (new), `tests/test_charts_desk_server.py` (add three tests)

**Interfaces:**
- Produces:
  - `tools.fake_desk.FakeDesk`;
  - `create_fake_desk(key: str, desk: FakeDesk | None = None) -> FastAPI`;
  - `stream(desk, heartbeat_s=15.0)` (an async generator of SSE strings);
  - `main(argv) -> int`;
  - `create_app(..., fake_desk_factory=None)`;
  - the CLI flag `--fake-desk PORT`.
- Consumes: `homebase.trading.parse_order / parse_modify / parse_cancel / parse_symbol_action` (the desk's own parsers, so the fake desk gives the same 400s) and `homebase.contracts.point_value / round_to_tick`.

- [ ] **Step 1: Write the failing tests** in `tests/test_fake_desk.py`

```python
"""The fake desk used by the chart page's browser checks. It never reaches a broker."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from tools import fake_desk
from tools.fake_desk import FakeDesk, create_fake_desk, stream

KEY = "ab" * 32
H = {"x-homebase-key": KEY}
Q = {"NQ": {"bid": 30900.0, "ask": 30900.25, "last": 30900.25, "ts_ms": 1}}


def client(desk=None):
    return TestClient(create_fake_desk(KEY, desk or FakeDesk()))


def order(c, **kw):
    body = {"client_id": kw.pop("cid", "c1"), "accounts": kw.pop("accounts", ["sim041"]), "root": "NQ",
            "side": "Buy", "qty": 1, "type": "Market", "quotes": Q, **kw}
    return c.post("/api/trade/order", json=body, headers=H)


def acct(c, aid="sim041"):
    return next(a for a in c.get("/api/trade/state", headers=H).json()["accounts"] if a["id"] == aid)


def test_the_key_is_required_and_browsers_are_refused():
    c = client()
    assert c.get("/api/trade/state").status_code == 401
    assert c.get("/api/trade/state", headers={**H, "origin": "http://x"}).status_code == 403
    st = c.get("/api/trade/state", headers=H).json()
    assert st["enabled"] is True and st["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
    assert [a["env"] for a in st["accounts"]] == ["demo", "demo", "live"]


def test_a_market_buy_fills_at_the_ask_and_rests_its_bracket_as_an_oco_pair():
    c = client()
    r = order(c, qty=2, sl_price=30890.0, tp_price=30920.0).json()
    assert r["results"]["sim041"]["ok"] is True
    a = acct(c)
    assert a["positions"] == [{"contract_id": 1, "symbol": "NQZ6", "net": 2, "avg_price": 30900.25,
                               "root": "NQ", "point_value": 20.0}]
    kinds = sorted((o["type"], o["side"], o["price"] or o["stop_price"]) for o in a["orders"])
    assert kinds == [("Limit", "Sell", 30920.0), ("Stop", "Sell", 30890.0)]
    tp = next(o for o in a["orders"] if o["type"] == "Limit")
    assert c.post("/fake/fill", json={"account": "sim041", "order_id": tp["order_id"]}).status_code == 200
    a = acct(c)
    assert a["positions"] == [] and a["orders"] == []          # the stop went with it (OCO)
    assert a["realized_pnl"] == pytest.approx((30920.0 - 30900.25) * 2 * 20)


def test_limit_rests_moves_and_cancels():
    c = client()
    oid = order(c, type="Limit", price=30880.13).json()["results"]["sim041"]["order_id"]
    assert acct(c)["orders"][0]["price"] == 30880.25               # tick-rounded
    assert c.post("/api/trade/modify", json={"client_id": "m", "account": "sim041", "order_id": oid,
                                             "price": 30870.0}, headers=H).json()["results"]["sim041"]["ok"]
    assert acct(c)["orders"][0]["price"] == 30870.0
    c.post("/api/trade/cancel", json={"client_id": "x", "account": "sim041", "order_id": oid}, headers=H)
    assert acct(c)["orders"] == []


def test_refusals_carry_the_desks_sentences():
    c = client()
    assert order(c, qty=11).json()["results"]["sim041"]["error"] == "quantity must be 1-10"
    r = order(c, type="Stop", price=30890.0).json()["results"]["sim041"]
    assert r == {"ok": False, "order_id": None, "error": "a buy stop must be above the last price (30,900.25)",
                 "refused": True}
    c.post("/fake/refuse", json={"reason": "NQZ6 on SIM0000041 is locked 09:20-09:35 ET for the nq930 bot"})
    assert "locked" in order(c).json()["results"]["sim041"]["error"]
    c.post("/fake/refuse", json={"reason": None})
    c.post("/fake/enabled", json={"on": False})
    assert order(c).json()["results"]["sim041"]["error"] == \
        "chart trading is off — switch it on on the desk page"
    assert c.post("/api/trade/order", json={"client_id": "c"}, headers=H).status_code == 400   # the desk's parser


def test_flatten_and_reverse():
    c = client()
    order(c, qty=3)
    c.post("/api/trade/reverse", json={"client_id": "r", "accounts": ["sim041"], "root": "NQ", "quotes": Q},
           headers=H)
    assert acct(c)["positions"][0]["net"] == -3
    c.post("/api/trade/flatten", json={"client_id": "f", "accounts": ["sim041"], "root": "NQ", "quotes": Q},
           headers=H)
    assert acct(c)["positions"] == []


def test_bot_scenarios():
    c = client()
    b = c.post("/fake/bot", json={"scenario": "placed", "anchor": 30900.0}).json()
    s = b["strategies"]["nq930"]
    assert (s["day_status"], s["timer"]["gate"], s["accounts"]["sim041"]["upper"]) == ("placed", True, 30910.0)
    assert {o["owner"] for o in acct(c)["orders"]} == {"nq930"}
    s = c.post("/fake/bot", json={"scenario": "done", "anchor": 30900.0}).json()["strategies"]["nq930"]
    assert s["day_status"] == "done" and s["accounts"]["sim041"]["pnl"] == 296.0
    assert [f["owner"] for f in acct(c)["fills"]][-2:] == ["nq930", "nq930"]
    assert c.post("/fake/bot", json={"scenario": "nope"}).status_code == 400


def test_the_stream_sends_state_first_then_events_then_heartbeats():
    async def run():
        d = FakeDesk()
        g = stream(d, heartbeat_s=0.01)
        first = await g.__anext__()
        assert first.startswith("event: state\n")
        d.publish("bot", {"x": 1})
        assert (await g.__anext__()).startswith("event: bot\n")
        assert (await g.__anext__()).startswith("event: heartbeat\n")
        await g.aclose()
        assert not d.subs
    asyncio.run(run())


@pytest.mark.parametrize("port", ["8850", "8852", "8854"])
def test_the_cli_refuses_the_real_services_ports(port):
    with pytest.raises(SystemExit):
        fake_desk.main(["--port", port])
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_fake_desk.py -q`. Expect: FAIL (`No module named 'tools'`).

- [ ] **Step 3: Implement `tools/fake_desk.py`**

```python
"""A FAKE desk for browser checks of chart trading: never the real desk, never a broker.

    .venv/bin/python -m tools.fake_desk [--port 8859]

It speaks the desk's /api/trade/* (homebase/desk_api.py + trading.py):
  * the X-Homebase-Key header, with ITS OWN key, written fresh to homebase/.state/fake-desk.key
    (mode 0600) at start; the real desk.key is never read or written;
  * no Origin;
  * GET /state, and the SSE /stream: state first, then account / bot / fill / result, and a
    heartbeat every 15 s;
  * POST order / modify / cancel / cancel-symbol / flatten / reverse, answering
    {"results": {account: {ok, order_id, error[, refused]}}}.
Bodies go through the desk's own parsers (homebase.trading.parse_*), so a malformed body gets
the same 400. Everything lives in memory: nothing is journaled, and no broker code is imported.

Fills:
  * A Market order fills at once at the chart service's quote (body["quotes"][root]): the ask for
    a buy, the bid for a sell, else the last trade.
  * A Limit or Stop order rests until POST /fake/fill.
  * An entry's sl_price / tp_price become working Stop / Limit exits when it fills. The first
    exit to fill cancels the other (OCO).

Controls (no key; the process binds 127.0.0.1 only):
    POST /fake/enabled {"on": bool}                       chart trading on/off (a state event)
    POST /fake/refuse {"reason": "..." | null}            every action is refused with this sentence
    POST /fake/fill {"account", "order_id", "price"?}     fill a working order
    POST /fake/bot {"scenario": "idle|placed|live|done", "anchor": 30900.0}   the NQ 9:30 bot on sim041
    POST /fake/drop                                       end every SSE stream (the chart service reconnects)
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import itertools
import json
import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from homebase.contracts import point_value, round_to_tick
from homebase.paths import state_dir
from homebase.trading import parse_cancel, parse_modify, parse_order, parse_symbol_action

PORT = 8859
FORBIDDEN_PORTS = frozenset({8850, 8852, 8853, 8854})   # the real desk, the chart service, the replays
KEY_FILE = "fake-desk.key"
MAX_ORDER, MAX_POSITION = 10, 20
HEARTBEAT_S = 15.0
MONTH = "Z6"
ACCOUNTS = (("sim041", "SIM0000041", "demo"), ("sim047", "SIM0000047", "demo"),
            ("live099", "FAKELIVE099", "live"))
SCENARIOS = ("idle", "placed", "live", "done")
OFF = "chart trading is off — switch it on on the desk page"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class FakeDesk:
    def __init__(self):
        self.enabled = True
        self.refuse: str | None = None
        self.ids = itertools.count(1001)
        self.subs: set[asyncio.Queue] = set()
        self.acct = {aid: {"id": aid, "label": label, "env": env, "realized": 0.0, "pos": {},
                           "orders": {}, "legs": {}, "fills": []}
                     for aid, label, env in ACCOUNTS}
        self.bot: dict = {"date": None, "strategies": {}}
        self.set_bot("idle", 30900.0)

    # ---- views: the desk's own shapes (trading.ChartDesk.account_view / snapshot) ----
    def account_view(self, aid: str) -> dict:
        a = self.acct[aid]
        return {"id": aid, "label": a["label"], "pinned": a["label"], "broker_account": a["label"],
                "env": a["env"], "connected": True, "error": None, "tradable": True,
                "balance": 50_000.0 + a["realized"], "realized_pnl": a["realized"],
                "positions": [{"contract_id": 1, "symbol": sym, "net": p["net"], "avg_price": p["avg"],
                               "root": sym[:-len(MONTH)], "point_value": point_value(sym)}
                              for sym, p in sorted(a["pos"].items()) if p["net"]],
                "orders": [dict(o) for _, o in sorted(a["orders"].items())],
                "fills": list(a["fills"][-50:]),
                "strategies": ["nq930"] if aid == "sim041" else []}

    def snapshot(self) -> dict:
        return {"enabled": self.enabled,
                "limits": {"max_order_qty": MAX_ORDER, "max_position_qty": MAX_POSITION},
                "accounts": [self.account_view(aid) for aid in self.acct], "bot": self.bot}

    def publish(self, event: str, data) -> None:
        for q in list(self.subs):
            q.put_nowait((event, data))

    def changed(self, aid: str) -> None:
        self.publish("account", self.account_view(aid))

    # ---- book-keeping ----
    def fill(self, aid: str, symbol: str, side: str, qty: int, price: float, order_id: str,
             owner: str | None = None) -> None:
        a = self.acct[aid]
        p = a["pos"].setdefault(symbol, {"net": 0, "avg": None})
        s = 1 if side == "Buy" else -1
        net0, avg0 = p["net"], p["avg"]
        closing = min(qty, abs(net0)) if net0 and (net0 > 0) != (s > 0) else 0
        if closing:
            a["realized"] += (price - avg0) * (1 if net0 > 0 else -1) * closing * (point_value(symbol) or 0.0)
        net1 = net0 + s * qty
        if net1 == 0:
            avg1 = None
        elif closing == 0:
            avg1 = round(((avg0 or 0.0) * abs(net0) + price * qty) / abs(net1), 6)
        elif closing < abs(net0):
            avg1 = avg0
        else:
            avg1 = price                              # flipped: the rest opens at the fill price
        p.update(net=net1, avg=avg1)
        f = {"id": next(self.ids), "order_id": order_id, "symbol": symbol, "side": side, "qty": qty,
             "price": price, "time": now_iso(), "owner": owner}
        a["fills"].append(f)
        self.publish("fill", {"account": aid, "fill": f})

    def rest(self, aid, symbol, side, qty, typ, price, sl=None, tp=None, owner=None) -> str:
        oid = str(next(self.ids))
        price = round_to_tick(symbol, price)
        self.acct[aid]["orders"][oid] = {
            "order_id": oid, "symbol": symbol, "side": side, "type": typ, "qty": qty,
            "price": price if typ == "Limit" else None, "stop_price": price if typ == "Stop" else None,
            "status": "Working", "owner": owner}
        self.acct[aid]["legs"][oid] = {"sl": sl, "tp": tp}
        return oid

    def brackets(self, aid, symbol, side, qty, leg) -> None:
        out = "Sell" if side == "Buy" else "Buy"
        sl = self.rest(aid, symbol, out, qty, "Stop", leg["sl"]) if leg.get("sl") else None
        tp = self.rest(aid, symbol, out, qty, "Limit", leg["tp"]) if leg.get("tp") else None
        if sl and tp:
            legs = self.acct[aid]["legs"]
            legs[sl]["oco"], legs[tp]["oco"] = tp, sl

    def drop_order(self, aid: str, oid: str) -> dict:
        self.acct[aid]["legs"].pop(oid, None)
        return self.acct[aid]["orders"].pop(oid)

    def fill_order(self, aid: str, oid: str, price=None) -> None:
        a = self.acct[aid]
        leg = dict(a["legs"].get(oid) or {})
        o = self.drop_order(aid, oid)
        px = float(price) if price is not None else (o["price"] if o["type"] == "Limit" else o["stop_price"])
        self.fill(aid, o["symbol"], o["side"], o["qty"], px, oid)
        if leg.get("oco") in a["orders"]:
            self.drop_order(aid, leg["oco"])
        self.brackets(aid, o["symbol"], o["side"], o["qty"], leg)
        self.changed(aid)

    # ---- actions ----
    def gate(self, aid: str) -> str | None:
        if not self.enabled:
            return OFF
        if aid not in self.acct:
            return f"unknown account {aid!r}"
        return self.refuse

    @staticmethod
    def refused(reason: str) -> dict:
        return {"ok": False, "order_id": None, "error": reason, "refused": True}

    @staticmethod
    def ok(oid=None) -> dict:
        return {"ok": True, "order_id": oid, "error": None}

    def finish(self, action: str, cid: str, results: dict) -> dict:
        out = {"results": results}
        self.publish("result", {"client_id": cid, "action": action, **out})
        return out

    def order(self, body) -> dict:
        it = parse_order(body)
        symbol = it.root + MONTH
        q = (body.get("quotes") or {}).get(it.root) or {}
        last = q.get("last")
        res = {}
        for aid in it.accounts:
            why, px = self.gate(aid), None
            if why is None and not 1 <= it.qty <= MAX_ORDER:
                why = f"quantity must be 1-{MAX_ORDER}"
            if why is None and it.type == "Stop" and last is not None:
                if it.side == "Buy" and it.price <= last:
                    why = f"a buy stop must be above the last price ({last:,})"
                if it.side == "Sell" and it.price >= last:
                    why = f"a sell stop must be below the last price ({last:,})"
            if why is None and it.type == "Market":
                px = q.get("ask" if it.side == "Buy" else "bid") or last
                if px is None:
                    why = f"fake desk: no quote for {it.root} to fill a market order at"
            if why:
                res[aid] = self.refused(why)
                continue
            leg = {"sl": it.sl_price, "tp": it.tp_price}
            if it.type == "Market":
                oid = str(next(self.ids))
                self.fill(aid, symbol, it.side, it.qty, float(px), oid)
                self.brackets(aid, symbol, it.side, it.qty, leg)
            else:
                oid = self.rest(aid, symbol, it.side, it.qty, it.type, it.price, it.sl_price, it.tp_price)
            self.changed(aid)
            res[aid] = self.ok(oid)
        return self.finish("order", it.client_id, res)

    def modify(self, body) -> dict:
        cid, aid, oid, price = parse_modify(body)
        why = self.gate(aid)
        o = self.acct[aid]["orders"].get(oid) if why is None else None
        if why is None and o is None:
            why = f"order {oid} is not working on {self.acct[aid]['label']}"
        if why:
            return self.finish("modify", cid, {aid: self.refused(why)})
        o["price" if o["type"] == "Limit" else "stop_price"] = round_to_tick(o["symbol"], price)
        self.changed(aid)
        return self.finish("modify", cid, {aid: self.ok(oid)})

    def cancel(self, body) -> dict:
        cid, aid, oid = parse_cancel(body)
        why = self.gate(aid)
        if why is None and oid not in self.acct[aid]["orders"]:
            why = f"order {oid} is not working on {self.acct[aid]['label']}"
        if why:
            return self.finish("cancel", cid, {aid: self.refused(why)})
        self.drop_order(aid, oid)
        self.changed(aid)
        return self.finish("cancel", cid, {aid: self.ok(oid)})

    def _per_symbol(self, action: str, body, fn) -> dict:
        cid, accounts, root = parse_symbol_action(body)
        q = (body.get("quotes") or {}).get(root) or {}
        res = {}
        for aid in accounts:
            why = self.gate(aid)
            if why:
                res[aid] = self.refused(why)
                continue
            fn(aid, root + MONTH, q.get("last"))
            self.changed(aid)
            res[aid] = self.ok()
        return self.finish(action, cid, res)

    def _cancel_symbol(self, aid, symbol, last) -> None:
        for oid in [k for k, o in self.acct[aid]["orders"].items() if o["symbol"] == symbol and not o["owner"]]:
            self.drop_order(aid, oid)

    def _flatten(self, aid, symbol, last) -> int:
        self._cancel_symbol(aid, symbol, last)
        p = self.acct[aid]["pos"].get(symbol)
        net = p["net"] if p else 0
        if net:
            self.fill(aid, symbol, "Sell" if net > 0 else "Buy", abs(net), float(last or p["avg"]),
                      str(next(self.ids)))
        return net

    def _reverse(self, aid, symbol, last) -> None:
        net = self._flatten(aid, symbol, last)
        if net:
            px = float(last or self.acct[aid]["fills"][-1]["price"])
            self.fill(aid, symbol, "Buy" if net < 0 else "Sell", abs(net), px, str(next(self.ids)))

    def cancel_symbol(self, body) -> dict:
        return self._per_symbol("cancel-symbol", body, self._cancel_symbol)

    def flatten(self, body) -> dict:
        return self._per_symbol("flatten", body, self._flatten)

    def reverse(self, body) -> dict:
        return self._per_symbol("reverse", body, self._reverse)

    # ---- the NQ 9:30 bot on sim041 (bot view = trading.ChartDesk.bot_view) ----
    def set_bot(self, scenario: str, anchor: float) -> None:
        a = self.acct["sim041"]
        for oid in [k for k, o in a["orders"].items() if o["owner"] == "nq930"]:
            self.drop_order("sim041", oid)
        x = round_to_tick("NQZ6", anchor)
        up, dn = x + 10.0, x - 10.0
        st = {"status": "idle", "qty": 1, "upper": None, "lower": None, "entry_side": None,
              "entry_fill": None, "entry_qty": None, "sl": None, "tp": None, "exit_fill": None,
              "exit_reason": None, "pnl": None, "note": None}
        timer, day = {"stage": "idle", "gate": None, "adx": None, "anchor": None}, "idle"
        if scenario != "idle":
            timer = {"stage": "done", "gate": True, "adx": 23.4, "anchor": x}
            st.update(status="placed", upper=up, lower=dn)
            day = "placed"
        if scenario == "placed":
            self.rest("sim041", "NQZ6", "Buy", 1, "Stop", up, owner="nq930")
            self.rest("sim041", "NQZ6", "Sell", 1, "Stop", dn, owner="nq930")
        if scenario in ("live", "done"):
            st.update(status="live", entry_side="Buy", entry_fill=up, entry_qty=1, sl=up - 5, tp=up + 15)
            day = "live"
            self.fill("sim041", "NQZ6", "Buy", 1, up, str(next(self.ids)), owner="nq930")
        if scenario == "done":
            st.update(status="done", exit_fill=up + 15, exit_reason="tp", pnl=15 * 20 - 4.0)
            day = "done"
            self.fill("sim041", "NQZ6", "Sell", 1, up + 15, str(next(self.ids)), owner="nq930")
        self.bot = {"date": dt.date.today().isoformat(), "strategies": {"nq930": {
            "symbol": "NQ", "kind": "straddle", "enabled": True, "shadow": False,
            "offset_pts": 10.0, "sl_pts": 5.0, "tp_pts": 15.0, "book": {"sim041": 1},
            "timer": timer, "day_status": day, "accounts": {"sim041": st}}}}


async def stream(desk: FakeDesk, heartbeat_s: float = HEARTBEAT_S):
    q: asyncio.Queue = asyncio.Queue()
    desk.subs.add(q)
    try:
        yield sse("state", desk.snapshot())
        while True:
            try:
                event, data = await asyncio.wait_for(q.get(), heartbeat_s)
            except asyncio.TimeoutError:
                yield sse("heartbeat", {"ts": dt.datetime.now().timestamp()})
                continue
            if event is None:
                return
            yield sse(event, data)
    finally:
        desk.subs.discard(q)


def create_fake_desk(key: str, desk: FakeDesk | None = None) -> FastAPI:
    desk = desk or FakeDesk()
    app = FastAPI(title="fake desk (browser checks only)")
    app.state.desk = desk

    def check(request: Request) -> None:
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "browser requests are refused — trade through the chart service")
        if request.headers.get("x-homebase-key", "") != key:
            raise HTTPException(401, "bad or missing X-Homebase-Key")

    @app.get("/api/trade/state")
    async def trade_state(request: Request):
        check(request)
        return desk.snapshot()

    @app.get("/api/trade/stream")
    async def trade_stream(request: Request):
        check(request)
        return StreamingResponse(stream(desk), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    def route(fn):
        async def handler(request: Request):
            check(request)
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(400, "the body is not JSON") from None
            try:
                return fn(body)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        return handler

    for name, fn in (("order", desk.order), ("modify", desk.modify), ("cancel", desk.cancel),
                     ("cancel-symbol", desk.cancel_symbol), ("flatten", desk.flatten),
                     ("reverse", desk.reverse)):
        app.add_api_route(f"/api/trade/{name}", route(fn), methods=["POST"], name=f"trade_{name}")

    @app.post("/fake/enabled")
    async def fake_enabled(body: dict):
        desk.enabled = bool(body.get("on"))
        desk.publish("state", desk.snapshot())
        return {"enabled": desk.enabled}

    @app.post("/fake/refuse")
    async def fake_refuse(body: dict):
        desk.refuse = str(body["reason"]) if body.get("reason") else None
        return {"refuse": desk.refuse}

    @app.post("/fake/fill")
    async def fake_fill(body: dict):
        aid, oid = str(body.get("account")), str(body.get("order_id"))
        if oid not in desk.acct.get(aid, {}).get("orders", {}):
            raise HTTPException(404, "no such working order")
        desk.fill_order(aid, oid, body.get("price"))
        return {"ok": True}

    @app.post("/fake/bot")
    async def fake_bot(body: dict):
        if body.get("scenario") not in SCENARIOS:
            raise HTTPException(400, f"scenario: one of {', '.join(SCENARIOS)}")
        desk.set_bot(body["scenario"], float(body.get("anchor") or 30900.0))
        desk.publish("bot", desk.bot)
        desk.changed("sim041")
        return desk.bot

    @app.post("/fake/drop")
    async def fake_drop():
        n = len(desk.subs)
        for q in list(desk.subs):
            q.put_nowait((None, None))
        return {"dropped": n}

    return app


def write_key(path: Path) -> str:
    key = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    os.chmod(path, 0o600)
    return key


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.fake_desk")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)
    if a.port in FORBIDDEN_PORTS:
        ap.error(f"port {a.port} belongs to the real desk or the chart service")
    key = write_key(state_dir() / KEY_FILE)
    uvicorn.run(create_fake_desk(key), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_fake_desk.py -q`. Expect: 10 passed. The plan's code was checked against main's `homebase.contracts` and `homebase.trading` when the plan was written.

- [ ] **Step 5: Write the failing override tests** (append to `tests/test_charts_desk_server.py`)

```python
from homebase.charts import __main__ as charts_main


def test_the_fake_desk_link_is_refused_outside_replay(tmp_path):
    with pytest.raises(ValueError):
        live_app(tmp_path, fake_desk_factory=lambda fan: None)


@pytest.mark.parametrize("argv", [["--fake-desk", "8859"],                              # no --replay
                                  ["--replay", "2026-09-22", "--fake-desk", "8850"]])   # the real desk's port
def test_the_cli_refuses_a_fake_desk_without_replay_or_on_the_real_port(argv):
    with pytest.raises(SystemExit):
        charts_main.main(argv)


def test_replay_links_to_the_fake_desk_and_sends_it_quotes(tmp_path):
    posted = []

    async def sse_body():
        yield b'event: state\ndata: {"enabled": true, "accounts": [], "bot": {}}\n\n'
        await asyncio.Event().wait()

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, content=sse_body(), headers={"content-type": "text/event-stream"})
        posted.append(json.loads(req.content))
        return httpx.Response(200, json={"results": {}})

    kp = key_file(tmp_path)
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50, start_et=dt.time(9, 30),
                     state=tmp_path / "state", fake_desk_factory=lambda fan: DeskLink(
                         fan, key_path=kp, url="http://127.0.0.1:8859", transport=httpx.MockTransport(handler)))
    with TestClient(app, base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        assert next_of(ws, "quote", limit=2000)["root"] == "NQ"
        assert c.post("/api/desk/order", json={"client_id": "c"}).status_code == 200
    assert "NQ" in posted[-1]["quotes"]
```

Add `import datetime as dt` and `import pytest` at the top if they are missing. `archive` and `next_of` already come from `tests.test_charts_server`.

- [ ] **Step 6:** Run `.venv/bin/python -m pytest tests/test_charts_desk_server.py -q`. Expect: the three new tests FAIL.

- [ ] **Step 7: Implement**
  - `server.py` `create_app(..., desk_factory=None, fake_desk_factory=None)`:

```python
    if fake_desk_factory is not None and not replay:
        raise ValueError("fake_desk_factory is for replay only: a fake desk never runs beside the live feed")
    # the desk link: never in replay (a replayed price must never reach an order); a replay may link to the
    # FAKE desk only (browser checks, python -m homebase.charts --replay … --fake-desk PORT)
    if replay:
        link = fake_desk_factory(desk_fan.publish) if fake_desk_factory is not None else None
    else:
        link = desk_factory(desk_fan.publish) if desk_factory is not None else None
```

  - The replay feed callback: when a (fake) link exists, the replayed prints feed the quotes:

```python
    if replay:
        def on_replay(root: str, contract: str, rows: list[dict]) -> None:
            if link is not None:
                quotes.note(root, rows)
            hub.on_ticks(root, rows)

        feed = ReplayFeed(store, roots, replay, on_replay, speed=speed, start_et=start_et)
```

  - `__main__.py`:

```python
    ap.add_argument("--fake-desk", type=int, metavar="PORT",
                    help="replay only: link chart trading to the FAKE desk (python -m tools.fake_desk) on this port")
    a = ap.parse_args(argv)
    if a.fake_desk is not None and not a.replay:
        ap.error("--fake-desk needs --replay (a fake desk never runs beside the live feed)")
    if a.fake_desk == 8850:
        ap.error("--fake-desk must not be the real desk's port 8850")
    ...
    app = create_app(..., desk_factory=None if a.replay else (...unchanged...),
                     fake_desk_factory=(lambda fan: DeskLink(fan, key_path=state_dir() / "fake-desk.key",
                                                             url=f"http://127.0.0.1:{a.fake_desk}"))
                     if a.fake_desk is not None else None)
```

  - `desk.py`'s module docstring gains one line: "In replay the link may point at the fake desk (tools/fake_desk.py) only."

- [ ] **Step 8:** Run `.venv/bin/python -m pytest -q`. Expect: everything green, including `test_replay_never_links_to_the_desk`.

- [ ] **Step 9: Commit**
  ```
  feat(charts): a fake desk (tools/fake_desk.py) and --fake-desk PORT, replay only, for browser checks of chart trading
  ```

**Controller check:**
- Add the two launch entries; start `homebase-fake-desk`, then `homebase-charts-screens-replay`.
- In the page console: `new WebSocket(...)` is not needed; the page's `/ws` shows `{"type":"desk","event":"state"…}` and `{"type":"quote"…}` messages (read them with `read_network_requests` or a temporary `ws` listener).
- `curl -s http://127.0.0.1:8859/api/trade/state` answers 401. Only the key opens it.

---

### Task 3: `HBTrade`, the pure trading model, and `HBDrawings.placeMarkers`

**Files:**
- Create: `homebase/static/charts/trade.js`, `tests/js/trade.test.mjs`
- Modify: `homebase/static/charts/drawings.js` (add `placeMarkers` to the pure half and to `api`), `tests/js/drawings.test.mjs`

**Interfaces:**
- Produces:
  - `HBDrawings.placeMarkers(bars, list, barMs = 0) -> marker[]`, where each list item is `{ms, …lwcMarkerFields}` and each output is `{…fields, time: bar.tt}`, sorted.
  - `HBTrade` = `{ PREFS_KEY, QUOTE_STALE_MS, BOT_NAMES, parsePrefs, prefsText, short, rootOf, orderPrice, abbr, inferType, menuText, roundTick, bracket, orderBody, clientId, tradeMode, quoteView, usd, money, pnl, rrText, linesFor, linePnl, lineLabel, lineText, lineColor, withPrice, orderTitle, confirmOrder, actionTitle, resultToasts, fillText, fillMarkers, botName, botsFor, positionRows, orderRows, fillRows, accountRows, etTime }` (signatures in the code below).
- Consumes: `HBCatalog.fmtPrice / decimals`, `HBPosition.fmtUsd`.

- [ ] **Step 1: Write the failing tests** (`tests/js/trade.test.mjs`)

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const D = require('../../homebase/static/charts/drawings.js');
const M = '−';
const P = { up: '#089981', down: '#F23645', accent: '#2962FF', warn: '#F7A600' };

const acct = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const STATE = {
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [
    acct('sim041', 'SIM0000041', 'demo', {
      positions: [{ symbol: 'NQZ6', net: 2, avg_price: 30900, root: 'NQ', point_value: 20 }],
      orders: [
        { order_id: '11', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 2, price: null, stop_price: 30885, owner: null },
        { order_id: '12', symbol: 'NQZ6', side: 'Sell', type: 'Limit', qty: 2, price: 30930, stop_price: null, owner: null },
        { order_id: '13', symbol: 'NQZ6', side: 'Buy', type: 'Limit', qty: 1, price: 30880, stop_price: null, owner: null },
        { order_id: '14', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 30890, owner: 'nq930' }],
      fills: [{ id: 1, order_id: '9', symbol: 'NQZ6', side: 'Buy', qty: 2, price: 30900, time: '2026-09-22T13:31:12.000Z', owner: null },
        { id: 2, order_id: '8', symbol: 'NQZ6', side: 'Buy', qty: 1, price: 30910, time: '2026-09-22T13:30:01.000Z', owner: 'nq930' }],
      strategies: ['nq930'] }),
    acct('sim047', 'SIM0000047', 'demo', {
      positions: [{ symbol: 'NQZ6', net: 1, avg_price: 30900, root: 'NQ', point_value: 20 }],
      orders: [{ order_id: '21', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 30885, owner: null }] }),
    acct('live099', 'FAKELIVE099', 'live', {
      positions: [{ symbol: 'ESZ6', net: -1, avg_price: 6500, root: 'ES', point_value: 50 }] })],
  bot: { date: '2026-09-22', strategies: {
    nq930: { symbol: 'NQ', kind: 'straddle', enabled: true, shadow: false, book: { sim041: 1 },
      timer: { stage: 'done', gate: true, adx: 23.44, anchor: 30900 }, day_status: 'placed',
      accounts: { sim041: { status: 'placed', qty: 10, upper: 30910, lower: 30890, entry_side: null, sl: null, tp: null, pnl: null } } },
    nq10am: { symbol: 'NQ', kind: 'bars', enabled: true, shadow: true, book: {}, timer: null, day_status: 'idle', accounts: {} },
    ym930: { symbol: 'YM', kind: 'straddle', enabled: false, shadow: false, book: {}, timer: null, day_status: 'idle', accounts: {} } } },
};
const TICKED = { ticked: ['sim041', 'sim047'], oneClick: false, qty: 2, slTicks: 0, tpTicks: 0 };

test('prefs: defaults, clamps, de-duplicated ticks, garbage in -> defaults', () => {
  const dflt = { ticked: [], oneClick: false, qty: 1, slTicks: 0, tpTicks: 0 };
  assert.deepEqual(T.parsePrefs(null), dflt);
  assert.deepEqual(T.parsePrefs('garbage'), dflt);
  assert.deepEqual(T.parsePrefs('[1]'), dflt);
  assert.deepEqual(T.parsePrefs(JSON.stringify({ ticked: ['a', 'a', 5, ''], oneClick: true, qty: 3.6, slTicks: -2, tpTicks: '8' })),
    { ticked: ['a'], oneClick: true, qty: 4, slTicks: 0, tpTicks: 8 });
  assert.equal(T.prefsText({ qty: 0 }), JSON.stringify({ ticked: [], oneClick: false, qty: 1, slTicks: 0, tpTicks: 0 }));
});

test('names: short account, contract root', () => {
  assert.equal(T.short({ id: 'x', label: 'SIM0000047' }), '…047');
  assert.equal(T.short({ id: 'ab' }), 'ab');
  assert.deepEqual(['NQZ6', 'MNQH27', 'NQ', '6EZ6', 'ZN', 'ZNZ6', null].map(T.rootOf), ['NQ', 'MNQ', 'NQ', '6E', 'ZN', 'ZN', '']);
});

test('Limit or Stop from the clicked price (TradingView), and the menu text', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.25 };
  assert.equal(T.inferType('Buy', 30901, q), 'Stop');
  assert.equal(T.inferType('Buy', 30900.25, q), 'Limit');
  assert.equal(T.inferType('Sell', 30899.75, q), 'Stop');
  assert.equal(T.inferType('Sell', 30900, q), 'Limit');
  assert.equal(T.inferType('Buy', 30901, null), null);
  assert.equal(T.inferType('Buy', 30901, { last: 30902 }), 'Limit');   // no ask: the last trade
  assert.equal(T.menuText('Buy', 2, 30900, 'Limit', 0.25), 'Buy 2 @ 30,900.00 Limit');
});

test('brackets from ticks (0 = off) and the order body', () => {
  const p = { ...TICKED, slTicks: 20, tpTicks: 40 };
  assert.deepEqual(T.bracket('Buy', 30900, p, 0.25), { sl: 30895, tp: 30910 });
  assert.deepEqual(T.bracket('Sell', 30900, p, 0.25), { sl: 30905, tp: 30890 });
  assert.deepEqual(T.bracket('Buy', 30900, TICKED, 0.25), { sl: null, tp: null });
  assert.deepEqual(T.orderBody({ clientId: 'c1', accounts: ['a'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market', price: 1, sl: 2 }),
    { client_id: 'c1', accounts: ['a'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market', sl_price: 2 });
  assert.deepEqual(T.orderBody({ clientId: 'c1', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5 }),
    { client_id: 'c1', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5 });
  const a = T.clientId(), b = T.clientId();
  assert.notEqual(a, b);
  assert.ok(a.length >= 1 && a.length <= 64);
});

test('trade mode: down, off, none, on', () => {
  assert.deepEqual(T.tradeMode({ state: null, down: 'desk unreachable' }, TICKED), { mode: 'down', reason: 'desk unreachable', accounts: [] });
  assert.equal(T.tradeMode({ state: { ...STATE, enabled: false } }, TICKED).mode, 'off');
  assert.equal(T.tradeMode({ state: STATE }, { ...TICKED, ticked: [] }).reason, 'Tick an account in the Trade menu');
  const odd = { ...STATE, accounts: STATE.accounts.map((a) => ({ ...a, tradable: false })) };
  assert.equal(T.tradeMode({ state: odd }, TICKED).mode, 'none');
  assert.deepEqual(T.tradeMode({ state: STATE }, TICKED), { mode: 'on', reason: '', accounts: ['sim041', 'sim047'] });
});

test('quote view: prices, spread in ticks, stale after 30 s', () => {
  const q = { bid: 30900, ask: 30900.5, last: 30900.5, ts_ms: 1000 };
  assert.deepEqual(T.quoteView(q, 0.25, 2000), { bid: '30,900.00', ask: '30,900.50', spread: '2', stale: false, age: 1000 });
  assert.equal(T.quoteView(q, 0.25, 32000).stale, true);
  assert.deepEqual(T.quoteView(null, 0.25, 0), { bid: '—', ask: '—', spread: '', stale: true, age: null });
});

test('money: signed dollars with a true minus, RR 1:X', () => {
  assert.deepEqual([450, -1212.5, 0, null].map(T.usd), ['+$450', `${M}$1,212.50`, '$0', null]);
  assert.deepEqual([450, -3, null].map(T.money), ['$450', `${M}$3`, '—']);
  assert.equal(T.pnl(30900, 30910, 1, 2, 20), 400);
  assert.equal(T.pnl(30900, 30910, -1, 1, 20), -200);
  assert.equal(T.pnl(30900, 30910, 1, 1, null), null);
  assert.equal(T.rrText(15, 30), '1:2');
  assert.equal(T.rrText(20, 30), '1:1.5');
  assert.equal(T.rrText(0, 30), null);
});

test('lines: merged positions, SL/TP legs with dollars, plain orders, bots\' orders left out, ticked accounts only', () => {
  const lines = T.linesFor(STATE, 'NQ', TICKED);
  assert.deepEqual(lines.map((g) => g.kind), ['position', 'sl', 'tp', 'order']);
  assert.deepEqual(lines.map((g) => T.lineText(g, 30910)),
    ['LONG 3 · +$600 · 2 accts', `SL 3 · ${M}$900 · 2 accts`, 'TP 2 · +$1,200 · …041', 'BUY LMT 1 · …041']);
  assert.equal(T.lineText(lines[0], null), 'LONG 3 · 2 accts');
  assert.deepEqual(lines[1].legs.map((l) => [l.account, l.order_id]), [['sim041', '11'], ['sim047', '21']]);
  assert.deepEqual(lines.map((g) => T.lineColor(g, P)), [P.up, P.down, P.up, P.accent]);
  assert.equal(T.lineText(T.withPrice(lines[1], 30880), 30910), `SL 3 · ${M}$1,200 · 2 accts`);
  assert.deepEqual(T.linesFor(STATE, 'NQ', { ...TICKED, ticked: [] }), []);
  assert.deepEqual(T.linesFor(null, 'NQ', TICKED), []);
  assert.deepEqual(T.lineLabel(lines[3]), 'BUY LMT 1');
});

test('confirm: title, bracket dollars and RR, accounts, LIVE flag', () => {
  const b = T.orderBody({ clientId: 'c', accounts: ['sim041', 'sim047'], root: 'NQ', side: 'Buy', qty: 2, type: 'Limit', price: 30900, sl: 30885, tp: 30930 });
  assert.deepEqual(T.confirmOrder(b, STATE, null, 20, 0.25), {
    title: 'Buy 2 NQ Limit @ 30,900.00',
    accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo' }, { id: 'sim047', label: 'SIM0000047', env: 'demo' }],
    bracket: `SL 30,885.00 ${M}$600 · TP 30,930.00 +$1,200 · RR 1:2`, each: 'each of 2 accounts', live: false });
  const m = T.orderBody({ clientId: 'c', accounts: ['live099'], root: 'NQ', side: 'Sell', qty: 1, type: 'Market' });
  const c = T.confirmOrder(m, STATE, { last: 30910 }, 20, 0.25);
  assert.equal(c.title, 'Sell 1 NQ at market');
  assert.equal(c.live, true);
  assert.equal(c.bracket, '');
  const sl = T.linesFor(STATE, 'NQ', TICKED)[1];
  assert.equal(T.actionTitle('modify', { root: 'NQ', line: sl, from: 30885, to: 30880 }, 0.25), 'Move SL 3 30,885.00 → 30,880.00');
  assert.equal(T.actionTitle('cancel', { root: 'NQ', line: sl }, 0.25), 'Cancel SL 3 @ 30,885.00 · 2 accts');
  assert.equal(T.actionTitle('reverse', { root: 'NQ' }, 0.25), 'Reverse NQ');
  assert.equal(T.actionTitle('cancel-symbol', { root: 'NQ' }, 0.25), 'Cancel all NQ orders');
  assert.equal(T.actionTitle('flatten', { root: 'NQ', line: T.linesFor(STATE, 'NQ', TICKED)[0] }, 0.25), 'Flatten NQ · 2 accts');
});

test('toasts: one per account from the desk, the proxy detail otherwise; fills', () => {
  const data = { results: { sim041: { ok: true, order_id: '5', error: null },
    sim047: { ok: false, order_id: null, error: 'chart trading is off — switch it on on the desk page', refused: true } } };
  assert.deepEqual(T.resultToasts('order', 200, data, STATE), [
    { tone: 'ok', text: '…041 · order accepted' },
    { tone: 'err', text: '…047 · chart trading is off — switch it on on the desk page' }]);
  assert.deepEqual(T.resultToasts('flatten', 504, { detail: 'no answer from the desk in 20 s — check the Orders tab before trying again' }, STATE),
    [{ tone: 'err', text: 'no answer from the desk in 20 s — check the Orders tab before trying again' }]);
  assert.deepEqual(T.resultToasts('order', 0, null, STATE), [{ tone: 'err', text: 'desk error (HTTP 0)' }]);
  assert.equal(T.fillText({ account: 'sim041', fill: { side: 'Buy', qty: 2, price: 30910.25 } }, STATE, 0.25), 'Filled 2 @ 30,910.25 · …041');
});

test('execution markers: ticked accounts, manual fills only, at the fill price', () => {
  assert.deepEqual(T.fillMarkers(STATE, 'NQ', TICKED, P), [{ id: 'fsim041:1', ms: Date.parse('2026-09-22T13:31:12.000Z'), price: 30900,
    position: 'atPriceBottom', shape: 'arrowUp', color: P.accent, text: '' }]);
});

test('bots: badge, entry lines merged across accounts, markers from the bot\'s fills', () => {
  const [b, ten] = T.botsFor(STATE, 'NQ', 0.25, P);
  assert.deepEqual(b.badge, { text: '9:30 bot · TREND ADX 23.4 · placed', tone: 'live' });
  assert.deepEqual(b.lines.map((l) => l.text), ['9:30 BUY STOP 10 @ 30,910.00', '9:30 SELL STOP 10 @ 30,890.00']);
  assert.deepEqual(b.markers.map((m) => [m.shape, m.price, m.text]), [['arrowUp', 30910, '']]);
  assert.deepEqual(ten.badge, { text: '10am bot · idle · shadow', tone: 'idle' });
  assert.equal(T.botsFor(STATE, 'YM', 1, P)[0].badge.text, '9:30 bot · off');
  const done = structuredClone(STATE);
  Object.assign(done.bot.strategies.nq930, { day_status: 'done' });
  done.bot.strategies.nq930.accounts.sim041 = { status: 'done', qty: 1, entry_side: 'Buy', pnl: 876 };
  assert.equal(T.botsFor(done, 'NQ', 0.25, P)[0].badge.text, '9:30 bot · TREND ADX 23.4 · done +$876');
  assert.deepEqual(T.botsFor(done, 'NQ', 0.25, P)[0].lines, []);
});

test('table rows', () => {
  const q = { NQ: { last: 30910 } };
  assert.deepEqual(T.positionRows(STATE, q)[0], { account: 'sim041', who: 'SIM0000041', env: 'demo', symbol: 'NQZ6', root: 'NQ',
    side: 'Long', qty: 2, avg: '30,900.00', last: '30,910.00', pnl: '+$400', tone: 'up' });
  assert.equal(T.positionRows(STATE, {})[2].pnl, '—');
  const o = T.orderRows(STATE);
  assert.deepEqual(o.find((r) => r.order_id === '14'), { account: 'sim041', who: 'SIM0000041', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1,
    price: '30,890.00', status: '', owner: '9:30 bot', order_id: '14', cancellable: false });
  assert.deepEqual(T.fillRows(STATE).map((r) => r.time), ['09:31:12', '09:30:01']);
  const a = T.accountRows(STATE, q)[0];
  assert.deepEqual([a.who, a.env, a.balance, a.realized, a.open, a.strategies, a.status], ['SIM0000041', 'demo', '$50,000', '$0', '+$400', '9:30 bot', 'Ready']);
});

test('placeMarkers: on the bar holding the time, inside the loaded bars, sorted', () => {
  const bars = [0, 1, 2].map((i) => ({ ms: 60000 * (10 + i), tt: 100 + i }));
  const out = D.placeMarkers(bars, [{ id: 'b', ms: 60000 * 11 + 5, x: 1 }, { id: 'a', ms: 60000 * 10 }, { id: 'early', ms: 1 },
    { id: 'late', ms: 60000 * 13 }], 60000);
  assert.deepEqual(out, [{ id: 'a', time: 100 }, { id: 'b', x: 1, time: 101 }]);
  assert.equal(D.placeMarkers(bars, [{ id: 'late', ms: 60000 * 99 }], 0).length, 1);   // non-time bars: the last bar holds the rest
  assert.deepEqual(D.placeMarkers([], [{ ms: 1 }]), []);
});
```

- [ ] **Step 2:** Run `node --test tests/js/trade.test.mjs`. Expect: FAIL (cannot find `trade.js`).

- [ ] **Step 3: Implement `drawings.js` `placeMarkers`**. It goes in the pure half, after `barIndexAt`, and is added to `api`.

```js
/* Series markers for events at epoch ms ({ms, ...marker fields}): each lands on the bar that holds its time (the
   last bar starting at or before it), keeping its own price for atPrice* positions. Events before the first bar,
   or at/after the last bar's end (barMs; 0 = not a time bar, the last bar holds everything after it), are left
   out. Sorted by time, as Lightweight Charts wants. */
function placeMarkers(bars, list, barMs = 0) {
  const n = bars.length, out = [];
  if (!n) return out;
  const end = barMs > 0 ? bars[n - 1].ms + barMs : Infinity;
  for (const m of list || []) {
    if (!(m.ms >= bars[0].ms) || m.ms >= end) continue;
    const { ms, ...rest } = m;
    out.push({ ...rest, time: bars[barIndexAt(bars, ms)].tt });
  }
  return out.sort((a, b) => a.time - b.time);
}
```

- [ ] **Step 4: Implement `trade.js`**

```js
/* Homebase Charts — trading from the chart, the pure half:
     - the viewer's trade preferences;
     - what the page may do right now;
     - Limit or Stop for a clicked price;
     - order bodies and client ids;
     - the position / order / bracket lines with their labels and dollars;
     - the confirm dialog's texts and the toasts;
     - the execution markers;
     - the live strategies' badge / lines / markers;
     - the bottom panel's table rows.
   It reads the desk's state exactly as the desk's snapshot shapes it (homebase/trading.py
   ChartDesk.snapshot). No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const Pos = need('HBPosition', './position.js');

const MINUS = '−';
const PREFS_KEY = 'hb_trade_prefs';
const QTY_MAX = 10000;          // a sanity clamp only: the desk's limits decide
const QUOTE_STALE_MS = 30000;   // the desk's QUOTE_MAX_AGE_S: an older quote is shown greyed
const BOT_NAMES = { nq930: '9:30 bot', ym930: '9:30 bot', nq10am: '10am bot' };
const ET = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' });

const int = (v, lo, hi, dflt) => { const n = Math.round(Number(v)); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt; };
const accountsOf = (state) => (state && state.accounts) || [];

/* ---- preferences (per viewer: localStorage hb_trade_prefs) ---- */
function parsePrefs(text) {
  let o = null;
  try { o = JSON.parse(text); } catch (_) { o = null; }
  if (!o || typeof o !== 'object' || Array.isArray(o)) o = {};
  const ticked = Array.isArray(o.ticked)
    ? [...new Set(o.ticked.filter((x) => typeof x === 'string' && x.length >= 1 && x.length <= 64))].slice(0, 20) : [];
  return { ticked, oneClick: o.oneClick === true, qty: int(o.qty, 1, QTY_MAX, 1),
    slTicks: int(o.slTicks, 0, QTY_MAX, 0), tpTicks: int(o.tpTicks, 0, QTY_MAX, 0) };
}
const prefsText = (p) => JSON.stringify(parsePrefs(JSON.stringify(p)));

/* ---- names ---- */
/* "…047": the last 3 characters of an account's label (or id). */
function short(a) { const s = String((a && (a.label || a.id)) || ''); return s.length > 3 ? '…' + s.slice(-3) : s; }
/* NQZ6 -> NQ · MNQH27 -> MNQ · NQ -> NQ: a month code + 1-2 digit year stripped. */
function rootOf(symbol) {
  const s = String(symbol || '').toUpperCase(), m = /^([A-Z0-9]+?)[FGHJKMNQUVXZ]\d{1,2}$/.exec(s);
  return m ? m[1] : s;
}
function botName(key) { return BOT_NAMES[key] || key; }
function etTime(ms) { return Number.isFinite(ms) ? ET.format(new Date(ms)) : '—'; }
function px(v) { return v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }); }

/* ---- orders ---- */
/* A Limit's price, a Stop's (StopLimit's) trigger. */
function orderPrice(o) {
  if (/stop/i.test(String(o.type || ''))) return o.stop_price ?? o.price ?? null;
  return o.price ?? o.stop_price ?? null;
}
const ABBR = { Limit: 'LMT', Stop: 'STP', StopLimit: 'STP LMT', Market: 'MKT', TrailingStop: 'TRAIL' };
const abbr = (t) => ABBR[t] || String(t || '').toUpperCase();

/* TradingView's rule for a clicked price: a buy above the ask is a Stop, at or below it a Limit; a sell below the
   bid is a Stop, at or above it a Limit. No ask/bid: the last trade; no quote at all: null (no order items). */
function inferType(side, price, q) {
  if (!q || price == null) return null;
  if (side === 'Buy') { const a = q.ask ?? q.last; return a == null ? null : price > a ? 'Stop' : 'Limit'; }
  const b = q.bid ?? q.last;
  return b == null ? null : price < b ? 'Stop' : 'Limit';
}
function menuText(side, qty, price, type, tick) { return `${side} ${qty} @ ${Cat.fmtPrice(price, tick)} ${type}`; }
function roundTick(p, tick) { return tick > 0 ? Number((Math.round(p / tick) * tick).toFixed(Cat.decimals(tick))) : p; }

/* SL/TP from the tick defaults (0 = off) around ref: the order's price, or the last trade for a Market order. */
function bracket(side, ref, prefs, tick) {
  if (ref == null || !(tick > 0)) return { sl: null, tp: null };
  const s = side === 'Buy' ? 1 : -1;
  return { sl: prefs.slTicks > 0 ? roundTick(ref - s * prefs.slTicks * tick, tick) : null,
    tp: prefs.tpTicks > 0 ? roundTick(ref + s * prefs.tpTicks * tick, tick) : null };
}
function orderBody({ clientId, accounts, root, side, qty, type, price = null, sl = null, tp = null }) {
  const b = { client_id: clientId, accounts: [...accounts], root, side, qty, type };
  if (type !== 'Market') b.price = price;
  if (sl != null) b.sl_price = sl;
  if (tp != null) b.tp_price = tp;
  return b;
}
let seq = 0;
/* One per user action (the desk de-duplicates on it: a retry of the same action reuses it). */
function clientId(now = Date.now()) { seq = (seq + 1) % 1e6; return `c${now.toString(36)}-${seq.toString(36)}-${Math.random().toString(36).slice(2, 8)}`; }

/* ---- what the page may do (ruling S7) ---- */
function tradeMode(desk, prefs) {
  if (!desk || !desk.state) return { mode: 'down', reason: (desk && desk.down) || 'connecting to the desk', accounts: [] };
  const st = desk.state;
  if (!st.enabled) return { mode: 'off', reason: 'Chart trading is off on the desk', accounts: [] };
  const ticked = new Set(prefs.ticked);
  const accounts = accountsOf(st).filter((a) => ticked.has(a.id) && a.tradable).map((a) => a.id);
  if (!accounts.length) return { mode: 'none', reason: ticked.size ? 'No ticked account can trade right now' : 'Tick an account in the Trade menu', accounts };
  return { mode: 'on', reason: '', accounts };
}

/* The Buy/Sell block's texts: bid / ask (the last trade when one side is missing), the spread in ticks, stale when
   the quote's trade is over 30 s old against nowMs (the replay clock in a replay). */
function quoteView(q, tick, nowMs) {
  if (!q || (q.bid == null && q.ask == null && q.last == null)) return { bid: '—', ask: '—', spread: '', stale: true, age: null };
  const bid = q.bid ?? q.last, ask = q.ask ?? q.last, age = Number.isFinite(q.ts_ms) ? nowMs - q.ts_ms : null;
  const n = tick > 0 && q.bid != null && q.ask != null ? Math.round((q.ask - q.bid) / tick) : null;
  return { bid: Cat.fmtPrice(bid, tick), ask: Cat.fmtPrice(ask, tick), spread: n == null ? '' : String(n),
    stale: age == null || age > QUOTE_STALE_MS, age };
}

/* ---- money ---- */
const sign = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');
/* "+$450" · "−$1,212.50" · "$0"; null when unknown. */
function usd(v) { return v == null || !Number.isFinite(v) ? null : sign(Math.round(v * 100)) + Pos.fmtUsd(v); }
/* Unsigned unless negative: "$50,000" · "−$3"; "—" when unknown. */
function money(v) { return v == null || !Number.isFinite(v) ? '—' : (Math.round(v * 100) < 0 ? MINUS : '') + Pos.fmtUsd(v); }
/* qty contracts from `from` to `to`, s = 1 long / −1 short; null without a point value or a price. */
function pnl(from, to, s, qty, pv) { return pv == null || from == null || to == null ? null : (to - from) * s * qty * pv; }
function rrText(risk, reward) { return risk > 0 && reward > 0 ? `1:${Number((reward / risk).toFixed(2))}` : null; }

/* ---- lines (ruling S8) ---- */
/* Positions (merged by side + average price), SL/TP legs (an order opposite to the account's position in that
   contract: a stop type is SL, a limit is TP) and plain working orders, merged by kind + side + type + price, for
   the ticked accounts in `root`. A bot's own orders (owner set) are drawn by the bot overlay instead. */
function linesFor(state, root, prefs) {
  if (!state) return [];
  const ticked = new Set(prefs.ticked), groups = new Map();
  const add = (key, base, leg) => {
    let g = groups.get(key);
    if (!g) { g = { key, ...base, qty: 0, legs: [] }; groups.set(key, g); }
    g.qty += leg.qty;
    g.legs.push(leg);
  };
  for (const a of accountsOf(state)) {
    if (!ticked.has(a.id)) continue;
    const who = short(a), pos = (a.positions || []).filter((p) => p.root === root && p.net);
    for (const p of pos) {
      const s = p.net > 0 ? 1 : -1;
      add(`position|${s}|${p.avg_price}`, { kind: 'position', side: s > 0 ? 'Buy' : 'Sell', price: p.avg_price },
        { account: a.id, who, qty: Math.abs(p.net), avg: p.avg_price, s, pv: p.point_value ?? null, symbol: p.symbol });
    }
    for (const o of a.orders || []) {
      const at = orderPrice(o);
      if (o.owner || at == null || rootOf(o.symbol) !== root) continue;
      const p = pos.find((x) => x.symbol === o.symbol);
      const exit = !!p && ((p.net > 0 && o.side === 'Sell') || (p.net < 0 && o.side === 'Buy'));
      const kind = !exit ? 'order' : /stop/i.test(o.type) ? 'sl' : /limit/i.test(o.type) ? 'tp' : 'order';
      add(`${kind}|${o.side}|${o.type}|${at}`, { kind, side: o.side, type: o.type, price: at },
        { account: a.id, who, qty: Number(o.qty) || 0, order_id: String(o.order_id),
          avg: p ? p.avg_price : null, s: p ? (p.net > 0 ? 1 : -1) : 0, pv: p ? p.point_value ?? null : null });
    }
  }
  return [...groups.values()];
}
/* A position's open P&L at the last trade; an SL/TP's P&L if it fills at its price; null for plain orders or
   when a point value / price is unknown. */
function linePnl(g, last) {
  if (g.kind === 'order') return null;
  let sum = 0;
  for (const l of g.legs) {
    const v = pnl(l.avg, g.kind === 'position' ? last : g.price, l.s, l.qty, l.pv);
    if (v == null) return null;
    sum += v;
  }
  return sum;
}
function whoText(g) { const w = [...new Set(g.legs.map((l) => l.who))]; return w.length === 1 ? w[0] : `${w.length} accts`; }
function lineLabel(g) {
  if (g.kind === 'position') return `${g.side === 'Buy' ? 'LONG' : 'SHORT'} ${g.qty}`;
  if (g.kind === 'sl' || g.kind === 'tp') return `${g.kind.toUpperCase()} ${g.qty}`;
  return `${g.side.toUpperCase()} ${abbr(g.type)} ${g.qty}`;
}
function lineText(g, last) {
  if (g.kind === 'order') return `${lineLabel(g)} · ${whoText(g)}`;
  return [lineLabel(g), usd(linePnl(g, last)), whoText(g)].filter(Boolean).join(' · ');
}
function lineColor(g, P) {
  if (g.kind === 'position') return g.side === 'Buy' ? P.up : P.down;
  if (g.kind === 'sl') return P.down;
  if (g.kind === 'tp') return P.up;
  return g.side === 'Buy' ? P.accent : P.down;
}
const withPrice = (g, price) => ({ ...g, price });

/* ---- confirm dialog ---- */
function orderTitle(b, tick) {
  return `${b.side} ${b.qty} ${b.root} ${b.type === 'Market' ? 'at market' : `${b.type} @ ${Cat.fmtPrice(b.price, tick)}`}`;
}
function confirmOrder(b, state, quote, pv, tick) {
  const accts = accountsOf(state).filter((a) => b.accounts.includes(a.id));
  const ref = b.type === 'Market' ? (quote ? quote.last ?? null : null) : b.price, s = b.side === 'Buy' ? 1 : -1;
  const risk = b.sl_price != null ? pnl(ref, b.sl_price, s, b.qty, pv) : null;
  const reward = b.tp_price != null ? pnl(ref, b.tp_price, s, b.qty, pv) : null;
  const bits = [];
  if (b.sl_price != null) bits.push(`SL ${Cat.fmtPrice(b.sl_price, tick)}${risk != null ? ` ${usd(risk)}` : ''}`);
  if (b.tp_price != null) bits.push(`TP ${Cat.fmtPrice(b.tp_price, tick)}${reward != null ? ` ${usd(reward)}` : ''}`);
  const rr = ref != null && b.sl_price != null && b.tp_price != null ? rrText(Math.abs(ref - b.sl_price), Math.abs(b.tp_price - ref)) : null;
  if (rr) bits.push(`RR ${rr}`);
  return { title: orderTitle(b, tick), accounts: accts.map((a) => ({ id: a.id, label: a.label, env: a.env })),
    bracket: bits.join(' · '), each: accts.length > 1 ? `each of ${accts.length} accounts` : '', live: accts.some((a) => a.env === 'live') };
}
function actionTitle(kind, { root, line, from, to }, tick) {
  switch (kind) {
    case 'flatten': return line ? `Flatten ${root} · ${whoText(line)}` : `Flatten ${root}`;
    case 'cancel-symbol': return `Cancel all ${root} orders`;
    case 'reverse': return `Reverse ${root}`;
    case 'cancel': return `Cancel ${lineLabel(line)} @ ${Cat.fmtPrice(line.price, tick)} · ${whoText(line)}`;
    case 'modify': return `Move ${lineLabel(line)} ${Cat.fmtPrice(from, tick)} → ${Cat.fmtPrice(to, tick)}`;
    default: return kind;
  }
}

/* ---- toasts (ruling S3) ---- */
const VERB = { order: 'order accepted', modify: 'order moved', cancel: 'order cancelled', 'cancel-symbol': 'orders cancelled',
  flatten: 'flattened', reverse: 'reversed' };
function resultToasts(action, status, data, state) {
  const label = (id) => { const a = accountsOf(state).find((x) => x.id === id); return a ? short(a) : id; };
  if (!data || typeof data !== 'object' || !data.results) {
    const d = data && (data.detail ?? data.error);
    return [{ tone: 'err', text: typeof d === 'string' && d ? d : `desk error (HTTP ${status})` }];
  }
  return Object.entries(data.results).map(([id, r]) => (r && r.ok
    ? { tone: 'ok', text: `${label(id)} · ${VERB[action] || 'done'}` }
    : { tone: 'err', text: `${label(id)} · ${(r && r.error) || 'refused'}` }));
}
function fillText(ev, state, tick) {
  const f = ev.fill, a = accountsOf(state).find((x) => x.id === ev.account);
  return `Filled ${f.qty} @ ${Cat.fmtPrice(f.price, tick || 0.01)} · ${a ? short(a) : ev.account}`;
}

/* ---- markers ({ms, …} for HBDrawings.placeMarkers) ---- */
function fillMarkers(state, root, prefs, P) {
  const ticked = new Set(prefs.ticked), out = [];
  for (const a of accountsOf(state)) {
    if (!ticked.has(a.id)) continue;
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner || rootOf(f.symbol) !== root || !Number.isFinite(ms)) continue;
      const buy = f.side === 'Buy';
      out.push({ id: `f${a.id}:${f.id}`, ms, price: f.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
        shape: buy ? 'arrowUp' : 'arrowDown', color: buy ? P.accent : P.down, text: '' });
    }
  }
  return out;
}

/* ---- live strategies (ruling S12) ---- */
const fmt1 = (v) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(1));
function botStatus(s) {
  const t = s.timer || {}, accts = Object.values(s.accounts || {});
  let st;
  if (!s.enabled) st = 'off';
  else if (s.day_status === 'done') {
    const known = accts.filter((a) => a.pnl != null);
    st = known.length ? `done ${usd(known.reduce((x, a) => x + a.pnl, 0))}` : 'done';
  } else if (s.day_status && s.day_status !== 'idle') st = s.day_status;
  else st = t.stage || 'idle';
  return s.shadow ? `${st} · shadow` : st;
}
function botBadge(key, s) {
  const t = s.timer || {};
  const gate = t.gate === true ? `TREND ADX ${fmt1(t.adx)}` : t.gate === false ? `CHOP ADX ${fmt1(t.adx)}` : null;
  const tone = s.day_status === 'error' || t.stage === 'error' ? 'err'
    : ['placing', 'placed', 'live'].includes(s.day_status) ? 'live' : 'idle';
  return { text: [botName(key), s.enabled ? gate : null, botStatus(s)].filter(Boolean).join(' · '), tone };
}
function botLines(key, s, tick) {
  const pre = s.kind === 'straddle' ? '9:30' : botName(key), m = new Map();
  const put = (kind, price, label, qty) => {
    if (price == null) return;
    const id = `${kind}|${price}`, g = m.get(id) || { key: `bot|${key}|${id}`, kind, price, label, qty: 0 };
    g.qty += Number(qty) || 0;
    m.set(id, g);
  };
  for (const a of Object.values(s.accounts || {})) {
    if (a.status === 'placing' || a.status === 'placed') { put('entry', a.upper, 'BUY STOP', a.qty); put('entry', a.lower, 'SELL STOP', a.qty); }
    if (a.status === 'live') { put('sl', a.sl, 'SL', a.entry_qty ?? a.qty); put('tp', a.tp, 'TP', a.entry_qty ?? a.qty); }
  }
  return [...m.values()].map((g) => ({ ...g, text: `${pre} ${g.label} ${g.qty} @ ${Cat.fmtPrice(g.price, tick)}` }));
}
function botMarkers(key, s, state, P) {
  const out = [];
  for (const a of accountsOf(state)) {
    const st = (s.accounts || {})[a.id];
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner !== key || !Number.isFinite(ms)) continue;
      const entry = !st || !st.entry_side || f.side === st.entry_side, buy = f.side === 'Buy';
      out.push({ id: `b${a.id}:${f.id}`, ms, price: f.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
        shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: entry ? '' : (st && st.pnl != null ? usd(st.pnl) : '') });
    }
  }
  return out;
}
function botsFor(state, root, tick, P) {
  const strats = (state && state.bot && state.bot.strategies) || {};
  return Object.entries(strats).filter(([, s]) => rootOf(s.symbol) === root)
    .map(([key, s]) => ({ key, badge: botBadge(key, s), lines: s.enabled ? botLines(key, s, tick) : [], markers: botMarkers(key, s, state, P) }));
}

/* ---- the bottom panel's rows (every account: ruling S6) ---- */
function openPnl(p, quotes) { const q = quotes[p.root]; return pnl(p.avg_price, q ? q.last : null, p.net > 0 ? 1 : -1, Math.abs(p.net), p.point_value ?? null); }
const tone = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
function positionRows(state, quotes) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const p of a.positions || []) {
      if (!p.net) continue;
      const v = openPnl(p, quotes), q = quotes[p.root];
      out.push({ account: a.id, who: a.label, env: a.env, symbol: p.symbol, root: p.root, side: p.net > 0 ? 'Long' : 'Short',
        qty: Math.abs(p.net), avg: px(p.avg_price), last: px(q ? q.last : null), pnl: usd(v) ?? '—', tone: tone(v) });
    }
  }
  return out;
}
function orderRows(state) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const o of a.orders || []) {
      out.push({ account: a.id, who: a.label, symbol: o.symbol, side: o.side, type: o.type, qty: Number(o.qty) || 0,
        price: px(orderPrice(o)), status: o.status || '', owner: o.owner ? botName(o.owner) : '', order_id: String(o.order_id),
        cancellable: !o.owner });
    }
  }
  return out;
}
function fillRows(state) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      out.push({ ms, time: etTime(ms), who: a.label, symbol: f.symbol, side: f.side, qty: f.qty, price: px(f.price),
        owner: f.owner ? botName(f.owner) : '' });
    }
  }
  return out.sort((x, y) => (y.ms || 0) - (x.ms || 0));
}
function accountRows(state, quotes) {
  return accountsOf(state).map((a) => {
    const opens = (a.positions || []).filter((p) => p.net).map((p) => openPnl(p, quotes));
    const open = opens.some((v) => v == null) ? null : opens.reduce((x, v) => x + v, 0);
    return { id: a.id, who: a.label, env: a.env, connected: !!a.connected, broker: a.broker_account || '—',
      balance: money(a.balance), realized: money(a.realized_pnl), open: opens.length ? (usd(open) ?? '—') : '$0',
      openTone: tone(open), strategies: [...new Set((a.strategies || []).map(botName))].join(', '),
      status: a.tradable ? 'Ready' : (a.error || (a.connected ? 'Not tradable' : 'Disconnected')) };
  });
}

const api = { PREFS_KEY, QUOTE_STALE_MS, BOT_NAMES, parsePrefs, prefsText, short, rootOf, orderPrice, abbr, inferType, menuText,
  roundTick, bracket, orderBody, clientId, tradeMode, quoteView, usd, money, pnl, rrText, linesFor, linePnl, lineLabel,
  lineText, lineColor, withPrice, orderTitle, confirmOrder, actionTitle, resultToasts, fillText, fillMarkers, botName,
  botsFor, positionRows, orderRows, fillRows, accountRows, etTime };
if (typeof window !== 'undefined') window.HBTrade = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

Note: the test's `accountRows` expectation `a.open === '+$400'` holds because sim041's only position has a quote. `a.realized === '$0'` holds because `money(0)` is `'$0'`.

- [ ] **Step 5:** Run `node --test tests/js/*.test.mjs`. Expect: PASS. Fix any mismatch in the **code** unless the test contradicts a ruling above.

- [ ] **Step 6:** In `charts.html`, add `<script src="/static/charts/trade.js?v=4"></script>` after `chartmenu.js`, and bump `drawings.js` to `?v=4`.

- [ ] **Step 7: Commit**
  ```
  feat(charts): HBTrade — prefs, Limit/Stop inference, lines with dollars, confirm and toast texts, bot badge/lines/markers, table rows; HBDrawings.placeMarkers
  ```

---

### Task 4: The desk client, the bottom panel and the trading tabs

**Files:**
- Create: `homebase/static/charts/deskclient.js`, `homebase/static/charts/panel.js`
- Modify: `homebase/static/charts/app.js` (`page` object, ws routing, panel mount), `charts.html`, `charts.css`, `icons.js` (Lucide `chevron-up`, `external-link`)

**Interfaces:**
- Consumes: `HBTrade.*`.
- Produces:
  - `HBDeskClient`:
    - `{ get state(), get down(), quotes, get prefs() }`;
    - `setPrefs(patch)`, `on(fn) -> off`, `onMessage(m)`, `mode() -> HBTrade.tradeMode`;
    - `send(action, body) -> Promise<data>` (toasts included);
    - `toast(tone, text)`.
    - `on` listeners get a `Set` of reasons (`state|account|bot|fill|quote|prefs`), coalesced per animation frame.
  - `HBPanel`:
    - `mount(page)`;
    - `addTab({id, label, render(el), onShow?(), onHide?()})`;
    - `show(id)`, `refresh(id?)`, `isShowing(id) -> bool`.
  - `page` (app.js; every later task uses it):
    ```
    { mk, icon, $, cells(), cur(), select(cell), openDialog(title, cls) -> box, closeDialog(), setDialogClose(fn),
      openMenu(anchor, cls, opts) -> el, closeMenu(), placeMenu(), toggleMenu(anchor, fill), menuItem(text, sub, onPick, active),
      sbNote(text), clockMs(), deskUrl(), overlays: [] }
    ```
    `page.overlays` is an array of factories `(cell, page) -> {destroy(), onBars?()}`. Tasks 6 and 10 push theirs into it.

**Requirements:**
- `app.js` `ws.onmessage`: before the chart lookup, add:
  ```js
  if (m.type === 'desk' || m.type === 'quote') { window.HBDeskClient.onMessage(m); return; }
  ```
- `deskclient.js`:
  - the store and `onMessage`, as in the key code below;
  - `send` POSTs `/api/desk/{action}` with JSON, remembers ok `order_id`s, and turns the answer into toasts (`HBTrade.resultToasts`);
  - toasts go into `#toastRoot` (ruling S24).
- **Panel DOM** in `charts.html`, between `</div>` (end of `.main`) and `<footer>`:

```html
<section class="bpanel" id="bpanel" aria-label="Trading and Strategy Tester">
  <div class="bp-resize" id="bpResize" role="separator" aria-orientation="horizontal" aria-label="Resize the panel" tabindex="0"></div>
  <div class="bp-bar"><div class="bp-tabs" id="bpTabs" role="tablist"></div><span class="bp-spacer"></span>
    <button class="bp-toggle" id="bpToggle" type="button" aria-label="Open the panel" title="Open the panel"><span class="icw" data-icon="chevronUp"></span></button></div>
  <div class="bp-body" id="bpBody"></div>
</section>
<div class="toasts" id="toastRoot" aria-live="polite"></div>
```

- The tabs are **Positions · Orders · Fills · Accounts**, added by `panel.js`. The **Strategy Tester** tab is added in Task 9.
- Table columns:

  | Tab | Columns | Row action |
  |---|---|---|
  | Positions | Account (label + env badge) · Symbol · Side (Long in `--up`, Short in `--down`) · Qty · Avg price · Last · Open P&L (coloured by tone) | `Close` → `HBTradeUI.flattenAccount(account, root)` |
  | Orders | Account · Symbol · Side · Type · Qty · Price · Status · Owner | `Cancel`, only when `cancellable`, → `HBTradeUI.cancelOrder(account, order_id)` |
  | Fills | Time (ET) · Account · Symbol · Side · Qty · Price · Owner | — |
  | Accounts | Account · Env · Connected dot · Broker account · Balance · Realized P&L · Open P&L · Strategies · Status (red unless `Ready`) | — |

  The actions exist from Task 5. Until then the buttons call through `window.HBTradeUI && …` and do nothing when it is absent.
- Empty states read `No open positions`, `No working orders`, `No fills today` and `No accounts on the desk`. While down, every tab reads `Desk unreachable — <reason>` (textContent).
- A tab's content re-renders on desk changes only while it is showing: `HBDeskClient.on((why) => HBPanel.refresh())`.
- Panel behaviour follows ruling S15. Resizing: pointerdown on `.bp-resize` → `setPointerCapture` → height `= clamp(window.innerHeight - e.clientY - 30 /*status bar*/, 120, 0.7 * innerHeight)`. Arrow Up/Down on the focused separator changes it by 16px. The height is saved on release.

**Key code:** `deskclient.js`

```js
/* Homebase Charts — the desk as the page sees it:
     - the latest state and quotes from the chart service's /ws ({"type": "desk"} and
       {"type": "quote"} messages);
     - the viewer's trade preferences;
     - the actions sent to POST /api/desk/{action};
     - the toasts.
   Browser only; the logic lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const TOAST_MS = { ok: 5000, err: 10000 }, TOAST_MAX = 5;
const desk = { state: null, down: 'connecting to the desk', quotes: {}, prefs: loadPrefs() };
const subs = new Set();
const ours = new Set();   // order ids this page placed: their fills get a toast (ruling S3)
let queued = null;

function loadPrefs() { try { return T.parsePrefs(localStorage.getItem(T.PREFS_KEY)); } catch (_) { return T.parsePrefs(null); } }
function setPrefs(patch) {
  desk.prefs = T.parsePrefs(JSON.stringify({ ...desk.prefs, ...patch }));
  try { localStorage.setItem(T.PREFS_KEY, T.prefsText(desk.prefs)); } catch (_) { /* storage off: this session only */ }
  emit('prefs');
}
function on(fn) { subs.add(fn); return () => subs.delete(fn); }
/* Coalesced to one call per frame: a burst of account events redraws once. */
function emit(why) {
  if (queued) { queued.add(why); return; }
  queued = new Set([why]);
  requestAnimationFrame(() => {
    const w = queued;
    queued = null;
    for (const fn of [...subs]) { try { fn(w); } catch (e) { console.error(e); } }
  });
}

function onMessage(m) {
  if (m.type === 'quote') {
    desk.quotes[m.root] = { bid: m.bid, ask: m.ask, last: m.last, ts_ms: m.ts_ms };
    emit('quote');
    return;
  }
  if (m.down !== undefined) { desk.state = null; desk.down = m.down; emit('state'); return; }
  const d = m.data;
  if (m.event === 'state') { desk.state = d; desk.down = null; }
  else if (!desk.state) return;
  else if (m.event === 'account') {
    const list = desk.state.accounts || (desk.state.accounts = []), i = list.findIndex((a) => a.id === d.id);
    if (i >= 0) list[i] = d; else list.push(d);
  } else if (m.event === 'bot') desk.state.bot = d;
  else if (m.event === 'fill') {
    if (d && d.fill && ours.has(String(d.fill.order_id))) toast('ok', T.fillText(d, desk.state, tickFor(T.rootOf(d.fill.symbol))));
  } else return;   // result: this page's own answers come back on its POST (ruling S3)
  emit(m.event);
}
function tickFor(root) {
  const c = (window.HBCharts ? window.HBCharts.cells : []).find((x) => x.shown && x.shown.root === root);
  return c ? c.tick : 0;
}

async function send(action, body) {
  let status = 0, data = null;
  try {
    const r = await fetch(`/api/desk/${action}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    status = r.status;
    try { data = await r.json(); } catch (_) { data = null; }
  } catch (_) { data = { detail: 'chart service unreachable' }; }
  if (data && data.results) for (const r of Object.values(data.results)) if (r && r.ok && r.order_id) ours.add(String(r.order_id));
  for (const t of T.resultToasts(action, status, data, desk.state)) toast(t.tone, t.text);
  return data;
}

function toast(tone, text) {
  const root = document.getElementById('toastRoot');
  if (!root) return;
  const el = document.createElement('div'), msg = document.createElement('span'), x = document.createElement('button');
  el.className = `toast ${tone}`;
  el.setAttribute('role', tone === 'err' ? 'alert' : 'status');
  msg.textContent = text;
  x.type = 'button'; x.className = 'toast-x'; x.setAttribute('aria-label', 'Dismiss');
  x.innerHTML = window.HBIcons.x;   // our own static SVG string
  x.onclick = () => el.remove();
  el.append(msg, x);
  root.prepend(el);
  while (root.children.length > TOAST_MAX) root.lastChild.remove();
  setTimeout(() => el.remove(), TOAST_MS[tone] || 6000);
}

window.HBDeskClient = {
  get state() { return desk.state; }, get down() { return desk.down; }, quotes: desk.quotes,
  get prefs() { return desk.prefs; }, setPrefs, on, onMessage, send, toast,
  mode: () => T.tradeMode(desk, desk.prefs),
};
})();
```

**Key code:** the `page` object and its mount order in `app.js` `init()`, after `buildGrid()` is defined and before `connect()`:

```js
const page = {
  mk, icon, $, cells: () => cells, cur, select: (c) => select(cells.indexOf(c)),
  openDialog, closeDialog, setDialogClose(fn) { if (dlg) dlg.onClose = fn; },
  openMenu, closeMenu, placeMenu, toggleMenu, menuItem, sbNote, clockMs,
  deskUrl: () => `${location.protocol}//${location.hostname}:8850/`,
  overlays: [],
};
window.HBPanel.mount(page);                 // Task 4
```

`hostFor` gains `overlays(cell) { return page.overlays.map((f) => f(cell, page)); }`. Cell uses it from Task 6 on.

**CSS** (structure; the tokens are the redesign's):

```css
/* ---- bottom panel (collapsible, shared by trading and the Strategy Tester) ---- */
.bpanel { flex: none; position: relative; display: flex; flex-direction: column; margin: 0 4px 4px 56px;
  background: var(--panel); border-radius: 6px; height: 34px; }                    /* 56px = rail 52 + gap 4 */
.bpanel.open { height: var(--bp-h, 260px); }
.bp-resize { position: absolute; left: 0; right: 0; top: -4px; height: 8px; cursor: ns-resize; z-index: 2; }
.bpanel:not(.open) .bp-resize { display: none; }
.bp-bar { flex: none; height: 34px; display: flex; align-items: center; padding: 0 4px; border-bottom: 1px solid transparent; }
.bpanel.open .bp-bar { border-bottom-color: var(--border); }
.bp-tabs { display: flex; height: 100%; }
.bp-tab { height: 100%; padding: 0 12px; font-size: 13px; color: var(--text-2); border-bottom: 2px solid transparent; }
.bp-tab:hover { color: var(--text); }
.bp-tab[aria-selected="true"] { color: var(--text); border-bottom-color: var(--accent); }
.bp-spacer { flex: 1; }
.bp-toggle { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 4px; color: var(--text-2); }
.bp-toggle:hover { background: var(--hover); color: var(--text); }
.bpanel.open .bp-toggle .ic { transform: rotate(180deg); }
.bp-body { flex: 1; min-height: 0; overflow: auto; }
.bpanel:not(.open) .bp-body { display: none; }
.bp-empty { padding: 16px; color: var(--text-2); font-size: 13px; }
.bp-table { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
.bp-table th { position: sticky; top: 0; background: var(--panel); color: var(--text-2); font-weight: 400; text-align: left;
  height: 28px; padding: 0 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.bp-table td { height: 28px; padding: 0 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.bp-table td.num, .bp-table th.num { text-align: right; }
.bp-table tr:hover td { background: var(--hover); }
.bp-act { height: 22px; padding: 0 8px; border-radius: 4px; border: 1px solid var(--border); font-size: 12px; }
.bp-act:hover { background: var(--hover); }
.up { color: var(--up); } .down { color: var(--down); }
.env { padding: 0 5px; border-radius: 4px; font-size: 11px; line-height: 16px; background: var(--hover); color: var(--text-2); }
.env.live { background: var(--down-soft); color: var(--down); font-weight: 600; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--text-2); }
.dot.ok { background: var(--up); } .dot.bad { background: var(--down); } .dot.warn { background: var(--warn); }
/* ---- toasts (top-right under the toolbar: ruling S24) ---- */
.toasts { position: fixed; top: 46px; right: 12px; z-index: 90; display: flex; flex-direction: column; gap: 6px; width: min(380px, 90vw); }
.toast { display: flex; align-items: flex-start; gap: 8px; padding: 8px 8px 8px 12px; border-radius: 8px; background: var(--panel);
  box-shadow: var(--shadow-menu); border-left: 3px solid var(--up); font-size: 13px; }
.toast.err { border-left-color: var(--down); }
.toast span { flex: 1; overflow-wrap: anywhere; }
.toast-x { width: 20px; height: 20px; display: grid; place-items: center; border-radius: 4px; color: var(--text-2); }
.toast-x:hover { background: var(--hover); }
```

- [ ] **Step 1:** Add the icons: `chevronUp` (Lucide `chevron-up`) and `extLink` (Lucide `external-link`). Copy their inner elements exactly from `https://cdn.jsdelivr.net/npm/lucide-static@1.48.0/icons/<name>.svg` (`curl -s` prints the SVG; read it before pasting), and add both names to the header list.
- [ ] **Step 2:** Write `deskclient.js` (above) and `panel.js`. `panel.js` builds the shell per the requirements and the four tabs from `HBTrade.positionRows / orderRows / fillRows / accountRows(HBDeskClient.state, HBDeskClient.quotes)`, rendering each cell with `textContent`.
- [ ] **Step 3:** Change `app.js`: the `page` object, `HBPanel.mount(page)`, the ws routing and `hostFor.overlays`. Add the scripts to `charts.html` (`deskclient.js?v=4`, `panel.js?v=4`) plus the panel and toast DOM. Bump `app.js`, `charts.css` and `icons.js` to `?v=4`.
- [ ] **Step 4:** Syntax check; `node --test tests/js/*.test.mjs` green; `.venv/bin/python -m pytest -q` green.
- [ ] **Step 5: Commit**
  ```
  feat(charts): desk client (state + quotes over /ws, prefs, actions, toasts) and the bottom panel with Positions / Orders / Fills / Accounts
  ```

**Controller browser check (fake desk):**
- The panel is collapsed at start. Clicking Accounts opens it at 260px, listing 3 accounts with DEMO/DEMO/LIVE and "Ready". Clicking again collapses it.
- Drag-resize it; reload; the height, open state and tab persist.
- `curl -X POST :8859/fake/bot -d '{"scenario":"placed","anchor":<current NQ price>}'` → Orders shows two `9:30 bot` Stop orders with no Cancel button.
- Stop the fake desk → every tab reads `Desk unreachable — …`. Start it again → the tables return within 30 s.
- The charts resize when the panel opens (no overlap). Zero console errors.

---

### Task 5: The Trade menu, the confirm dialog, the actions, and the Buy/Sell items in the chart menu

**Files:**
- Create: `homebase/static/charts/tradeui.js`
- Modify: `charts.html` (the Trade button, `tradeui.js?v=4`), `app.js` (button wiring, `HBTradeUI.mount(page)`), `charts.css`

**Interfaces:**
- Consumes: `HBTrade`, `HBDeskClient`, `page`, `HBChartMenu.register`.
- Produces: `HBTradeUI`:
  - `mount(page)`;
  - `placeOrder({cell, root, side, type, price?, qty?})`;
  - `symbolAction(kind: 'flatten'|'cancel-symbol'|'reverse', root)`;
  - `flattenAccount(account, root)`, `cancelOrder(account, order_id)`;
  - `closeLine(line, root, tick)` (× on a line: flatten for a position, cancel for the rest);
  - `moveLine(line, price, root, tick, {onCancel})`;
  - `confirm({title, rows, note, live, action}) -> Promise<boolean>`.

**Requirements:**
- **Trade button** in the toolbar, right after `.tb-spacer`:

  ```html
  <button class="tb-btn" id="tbTrade" type="button" title="Trade" aria-haspopup="menu" aria-expanded="false"><span class="dot" id="tbTradeDot"></span><span class="tb-label">Trade</span><span class="icw sm" data-icon="chevron"></span></button><span class="tb-sep"></span>
  ```

  The dot is `ok` in mode on, `warn` in off/none, and `bad` in down. The button's `title` is the mode's reason.
- **The menu** (`toggleMenu(tbTrade, fill)`, class `menu-trade`, width 340) contains, top to bottom:
  1. A header `CHART TRADING` (`.menu-h`), then a status line:
     - mode down: `Desk unreachable — <reason>`;
     - mode off: `Chart trading is off on the desk` with a link `Open the desk` (Lucide external-link, `page.deskUrl()`, `target=_blank`, `rel=noopener`);
     - otherwise: `Max <max_order_qty> per order · <max_position_qty> per position`.
  2. One row per desk account: checkbox, label, `DEMO`/`LIVE` env badge, balance (`HBTrade.money`), and the connected dot.
     - An untradable account is disabled and shows `a.error || 'not tradable'` in `--text-2` under the label.
     - Ticking a LIVE account arms first (ruling S5).
     - Ticking calls `setPrefs({ticked})`.
  3. A divider, then:
     - `One-click trading`: a switch (`role="switch"`, `aria-checked`);
     - `Default quantity`: a number input from 1 to `max_order_qty`;
     - `Stop loss (ticks)` and `Take profit (ticks)`: number inputs from 0 to 10000, with a small `0 = off` note.
     - An input saves on `change` through `setPrefs`.
  - The menu re-fills on desk changes while open. The row that has focus keeps it.
- **Confirm dialog** (`page.openDialog(title, 'confirm')`, width 420):
  - one row per account: label + env badge (LIVE in `--down`);
  - the bracket line (`confirmOrder.bracket`), then `each` in `--text-2`;
  - a checkbox `Don't ask again (one-click trading)`;
  - the buttons `Cancel` (outlined) and the primary button, which is `Buy` (in `--accent`), `Sell` (in `--down`), or the action verb for other actions (`Flatten`, `Reverse`, `Cancel orders`, `Move`, `Cancel order`).
  - Enter confirms and Esc cancels (Esc through the app's `onKey`). The primary button has autofocus.
  - It resolves `true` or `false`; closing by ×, backdrop or Esc resolves `false`, through `page.setDialogClose`.
- **Actions:** each builds the body with a fresh `HBTrade.clientId()` and sends through `HBDeskClient.send`.

  | Action | Sends | Confirm skipped when |
  |---|---|---|
  | `placeOrder` | `accounts` = `mode().accounts`; brackets from `HBTrade.bracket(side, type === 'Market' ? quote.last : price, prefs, tick)`; the confirm uses `confirmOrder(body, state, quote, cell.pv, cell.tick)` | one-click is on |
  | `symbolAction` | `{client_id, accounts: mode().accounts, root}` | one-click is on — except **Reverse, which always confirms** |
  | `moveLine` | one `modify` per leg (`{client_id, account, order_id, price}`), sequentially | one-click is on |
  | `closeLine` / `cancelOrder` / `flattenAccount` | `cancel` per leg, or `flatten` with the line's accounts | one-click is on |

  If mode is not `on`, an action does nothing but toast the mode's reason.
- **Chart menu items:** in `mount`, register the `'trading'` section:

```js
  window.HBChartMenu.register('trading', (ctx) => {
    const D = window.HBDeskClient, T = window.HBTrade;
    if (D.mode().mode !== 'on') return [];
    const q = D.quotes[ctx.root], qty = D.prefs.qty, out = [];
    if (ctx.price != null) {
      for (const side of ['Buy', 'Sell']) {
        const type = T.inferType(side, ctx.price, q);
        if (type) out.push({ text: T.menuText(side, qty, ctx.price, type, ctx.tick),
          run: () => placeOrder({ cell: ctx.cell, root: ctx.root, side, type, price: ctx.price, qty }) });
      }
    }
    out.push({ text: `Cancel all orders (${ctx.root})`, run: () => symbolAction('cancel-symbol', ctx.root) },
      { text: `Flatten ${ctx.root}`, run: () => symbolAction('flatten', ctx.root) },
      { text: `Reverse ${ctx.root}`, run: () => symbolAction('reverse', ctx.root) });
    return out;
  });
```

**Key code:** the confirm (the dialog pattern `app.js` already uses):

```js
function confirm({ title, rows = [], note = '', each = '', live = false, action, tone = 'accent' }) {
  const D = window.HBDeskClient;
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => { if (done) return; done = true; resolve(ok); };
    const box = page.openDialog(title, 'confirm');
    page.setDialogClose(() => finish(false));            // ×, backdrop, Esc
    const body = page.mk('div', 'cf-body');
    for (const r of rows) {
      const row = page.mk('div', 'cf-acct');
      row.append(page.mk('span', '', r.label), page.mk('span', `env${r.env === 'live' ? ' live' : ''}`, r.env === 'live' ? 'LIVE' : 'DEMO'));
      body.append(row);
    }
    if (note) body.append(page.mk('div', 'cf-note', note));
    if (each) body.append(page.mk('div', 'cf-each', each));
    const one = page.mk('label', 'cf-one'), ck = page.mk('input');
    ck.type = 'checkbox';
    one.append(ck, page.mk('span', '', "Don't ask again (one-click trading)"));
    const foot = page.mk('div', 'dlg-foot'), no = page.mk('button', 'btn', 'Cancel'), yes = page.mk('button', `btn primary ${tone}`, action);
    no.type = yes.type = 'button';
    no.onclick = () => page.closeDialog();                 // onClose -> finish(false)
    yes.onclick = () => { if (ck.checked) D.setPrefs({ oneClick: true }); page.setDialogClose(null); page.closeDialog(); finish(true); };
    box.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target !== no && e.target.type !== 'checkbox') { e.preventDefault(); yes.click(); } });
    foot.append(no, yes);
    box.append(body, one, foot);
    if (live) box.classList.add('live');
    yes.focus();
  });
}
```

**CSS:** `.menu-trade` rows (a 32px account row as a grid: checkbox · label · env · balance · dot), a `.switch` (a 28×16 track, `--accent` when on), and the confirm dialog (`.cf-acct` rows at 28px, `.cf-note` 13px, `.cf-each` `--text-2` 12px, `.btn` outlined 32px radius 6, `.btn.primary.accent` on `--accent`, `.btn.primary.down` on `--down`, white text). All of it uses the tokens.

- [ ] **Step 1:** Write `tradeui.js` per the above. Wire `$('#tbTrade')` in `app.js`, call `HBTradeUI.mount(page)`, and update the dot on `HBDeskClient.on`.
- [ ] **Step 2:** Syntax check; Node and pytest green.
- [ ] **Step 3: Commit**
  ```
  feat(charts): Trade menu (accounts, DEMO/LIVE, one-click, qty, SL/TP ticks), confirm dialog with $ and RR 1:X, actions with toasts, Buy/Sell limit/stop + cancel/flatten/reverse in the chart menu
  ```

**Controller browser check (fake desk):**
- The Trade dot is amber with "Tick an account". Tick SIM…041 → the dot turns green.
- Ticking FAKELIVE099 asks for a second click.
- Right-click above the price → `Buy 1 @ … Stop` and `Sell 1 @ … Limit`; below the price → `Buy … Limit` and `Sell … Stop`.
- Pick Buy Limit → the confirm shows the account + DEMO, then Cancel; the dialog closes and nothing is sent (check the network).
- Confirm with SL 20 / TP 40 ticks set → the bracket line shows `RR 1:2` with dollars; confirm → toast `…041 · order accepted`; the Orders tab shows the Limit.
- `curl :8859/fake/refuse -d '{"reason":"test refusal"}'`, then an order → toast `…041 · test refusal`.
- Tick "Don't ask again" → the next order sends without the dialog.
- `/fake/enabled {"on":false}` → the dot turns amber, the menu shows "Chart trading is off on the desk" plus the Open the desk link, and the chart menu has no trading items.
- Reverse always confirms.
- Enter confirms; Esc cancels.

---

### Task 6: On the chart — the Buy/Sell block, the lines with drag and ×, and the execution markers

**Files:**
- Create: `homebase/static/charts/tradelines.js`
- Modify: `homebase/static/charts/cell.js`:
  - `palette()` gains `warn: '#F7A600'`;
  - `extMarkers` and `setExtraMarkers`, with `drawMarkers` merging them;
  - the overlays lifecycle.
- Modify: `app.js` (`page.overlays.push(HBTradeLines.overlay)`), `charts.html` (`tradelines.js?v=4`, `cell.js?v=4`), `charts.css`

**Interfaces:**
- Produces:
  - Cell:
    - `setExtraMarkers(key: string, list: {ms,…}[])`;
    - `this.ov` (the overlay instances);
    - overlays are created at the end of `build()` and destroyed in `teardown()` before `chart.remove()`;
    - `onBars()` is called at the end of `onUpdate` and `onOlder`.
  - `HBTradeLines.overlay(cell, page) -> {destroy, onBars}`.
- Consumes: `HBTrade`, `HBDeskClient`, `HBTradeUI.placeOrder / closeLine / moveLine`, `HBDrawings.placeMarkers / roundToTick`.

**Cell changes (key code):**

```js
  // constructor
  this.extMarkers = {};   // key -> [{ms, ...marker}] from overlays (trading, bots, the tester): HBDrawings.placeMarkers
  this.ov = [];           // this chart's overlays (page.overlays), rebuilt with the chart

  // build(), after the drawing controller:
  this.ov = this.host.overlays ? this.host.overlays(this) : [];

  // teardown(), first thing:
  for (const o of this.ov) { try { o.destroy(); } catch (e) { console.error(e); } }
  this.ov = [];

  // end of onUpdate() and of onOlder() (after its own redraws):
  for (const o of this.ov) if (o.onBars) o.onBars();

  setExtraMarkers(key, list) { this.extMarkers[key] = list || []; this.drawMarkers(); }

  drawMarkers() {
    if (!this.markers) return;
    const mins = this.visible('bigprints').map((x) => x.params.min), P = this.P, big = [];
    if (mins.length) {
      const min = Math.min(...mins);
      for (const b of this.bars) {
        for (const [, , size, side] of (b.big || [])) {
          if (size >= min) big.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
            color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
        }
      }
    }
    const extra = [];
    for (const k in this.extMarkers) extra.push(...this.extMarkers[k]);
    const placed = window.HBDrawings.placeMarkers(this.bars, extra, this.barMs());
    this.markers.setMarkers([...big.slice(-600), ...placed].sort((a, b) => a.time - b.time));
  }
```

**Overlay structure** (`tradelines.js`, one per chart, rebuilt with it):

- **DOM** (created in the constructor, removed in `destroy`):
  - `this.block`: the Buy/Sell block, appended to the cell's `.legend` (it becomes the legend's last child).
  - `this.layer = mk('div', 'tl-layer')`, appended to `cell.el` (the panel): absolute over the chart, `pointer-events: none`.
  - One chip per line inside it.
  - `this.badges = mk('span', 'lg-bots')`, appended to the legend title row. It is filled in Task 7.
- **Block:**

  ```html
  <div class="lg-trade" hidden>
    <button class="tr-sell" type="button"><span class="tr-px"></span><span class="tr-lbl">SELL</span></button>
    <div class="tr-mid"><input class="tr-qty" type="number" min="1" step="1" aria-label="Quantity"><span class="tr-spread"></span></div>
    <button class="tr-buy" type="button"><span class="tr-px"></span><span class="tr-lbl">BUY</span></button>
  </div>
  ```

  - It is shown only in mode `on`.
  - The prices and spread come from `HBTrade.quoteView(quotes[root], cell.tick, page.clockMs())`; `.stale` greys them.
  - `title`: `Bid / ask as of the last trade` (plus ` — no trade for 45 s` when stale).
  - The qty input mirrors `prefs.qty`; `change` calls `setPrefs({qty})`.
  - A click calls `HBTradeUI.placeOrder({cell, root, side, type: 'Market', qty: prefs.qty})`.
- **Lines** (`render()` runs on every `HBDeskClient` change and on `onBars`):
  - `const lines = HBTrade.linesFor(D.state, root, D.prefs)`, where `root = cell.shown.root`. The lines stay (read-only) in modes `off` and `none`; in mode `down` there are none.
  - Keep `this.items = Map(key -> {g, line, chip})`.
  - A new key gets `cell.candles.createPriceLine({price, color, lineWidth: 1, lineStyle: g.kind === 'position' ? 0 : 2, axisLabelVisible: true, title: ''})` plus a chip.
  - An existing key gets `applyOptions({price, color})`.
  - A stale key gets `removePriceLine` and its chip removed.
  - The key being dragged is skipped.
- **Chip:**

  ```html
  <div class="tl-chip" style="--c:<color>">
    <span class="tl-text">LONG 3 · +$600 · 2 accts</span>
    <button class="tl-x" aria-label="Close">×</button>
  </div>
  ```

  - `.tl-text` is the drag grip for `order`, `sl` and `tp` in mode `on`. Positions are not draggable.
  - `.tl-x` exists only in mode `on`; it calls `HBTradeUI.closeLine(g, root, cell.tick)`.
  - The text is `HBTrade.lineText(g, quotes[root]?.last)`.
- **Execution markers:** `cell.setExtraMarkers('fills', HBTrade.fillMarkers(D.state, root, D.prefs, cell.P))`. They are re-set only when the fills change (compare `JSON.stringify` of the ids).

**Key code:** the reposition hook and the drag (the subtle parts):

```js
/* A primitive that draws nothing: Lightweight Charts calls updateAllViews() before every redraw of the price
   pane (scroll, zoom, autoscale, resize), so the DOM chips follow their lines exactly. */
class Hook {
  constructor(fn) { this.fn = fn; this.raf = 0; }
  updateAllViews() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.fn(); }); }
  paneViews() { return []; }
  detached() { cancelAnimationFrame(this.raf); this.raf = 0; }
}

  // in the overlay:
  sync() {   // every chip at its line's y, right-aligned left of the price axis; hidden outside the price pane
    const c = this.cell;
    if (!c.chart) return;
    const paneH = c.chart.panes()[0].getHeight(), right = c.chart.priceScale('right').width() + 6;
    for (const it of this.items.values()) {
      const y = c.candles.priceToCoordinate(it.g.price);
      const off = y == null || y < 0 || y > paneH;
      it.chip.hidden = off;
      if (!off) { it.chip.style.right = `${right}px`; it.chip.style.transform = `translateY(${Math.round(y) - 11}px)`; }
    }
  }

  startDrag(e, key) {   // on .tl-text; the pointer is captured by the chip, so the chart never pans
    if (e.button !== 0 || this.dragging) return;
    e.preventDefault(); e.stopPropagation();
    const c = this.cell, it = this.items.get(key), grip = e.currentTarget, from = it.g.price;
    const top = c.box.getBoundingClientRect().top;
    let price = from;
    grip.setPointerCapture(e.pointerId);
    this.dragging = key;
    const move = (ev) => {
      const raw = c.candles.coordinateToPrice(ev.clientY - top);
      if (raw == null) return;
      price = window.HBDrawings.roundToTick(raw, c.tick);
      it.g = window.HBTrade.withPrice(it.g, price);
      it.line.applyOptions({ price });
      this.paint(it);            // the chip's text with the new SL/TP dollars
      this.sync();
    };
    const end = (commit) => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', lost);
      window.removeEventListener('keydown', esc, true);
      window.removeEventListener('blur', lost);
      this.dragging = null;
      if (commit && price !== from) {
        window.HBTradeUI.moveLine({ ...it.g, price: from }, price, c.shown.root, c.tick, { onCancel: () => this.render() });
      } else this.render();      // back to the desk's price
    };
    const up = () => end(true), lost = () => end(false);
    const esc = (ev) => { if (ev.key === 'Escape') { ev.stopPropagation(); ev.preventDefault(); end(false); } };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', lost);
    window.addEventListener('keydown', esc, true);
    window.addEventListener('blur', lost);
  }
```

In the constructor: `this.hook = new Hook(() => this.sync()); cell.candles.attachPrimitive(this.hook);`. `destroy()` does the following, in order:
1. unsubscribes from `HBDeskClient`;
2. calls `removePriceLine` for every line;
3. removes the DOM nodes;
4. calls `cell.candles.detachPrimitive(this.hook)`, when the chart still exists;
5. calls `cell.setExtraMarkers('fills', [])` and `cell.setExtraMarkers('bots', [])` **without** redrawing when `cell.chart` is null. `teardown` calls it before the removal, so a plain `delete cell.extMarkers.fills` is fine.

**CSS:**

```css
/* ---- chart trading on the chart ---- */
.lg-trade { display: inline-flex; align-items: stretch; gap: 4px; margin-top: 4px; pointer-events: auto; font-variant-numeric: tabular-nums; }
.tr-sell, .tr-buy { min-width: 76px; height: 38px; padding: 2px 8px; border-radius: 4px; color: #fff; display: flex; flex-direction: column;
  align-items: center; justify-content: center; line-height: 16px; }
.tr-sell { background: var(--down); } .tr-buy { background: var(--accent); }
.tr-sell:hover, .tr-buy:hover { filter: brightness(1.08); }
.tr-px { font-size: 13px; font-weight: 600; } .tr-lbl { font-size: 11px; letter-spacing: .04em; }
.lg-trade.stale .tr-px { opacity: .55; }
.tr-mid { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; }
.tr-qty { width: 48px; height: 22px; text-align: center; border: 1px solid var(--border); border-radius: 4px; background: var(--panel); font-size: 12px; }
.tr-spread { font-size: 11px; color: var(--text-2); }
.tl-layer { position: absolute; inset: 0; z-index: 4; pointer-events: none; overflow: hidden; }
.tl-chip { position: absolute; top: 0; display: inline-flex; height: 22px; border-radius: 4px; overflow: hidden; pointer-events: auto;
  font-size: 12px; font-variant-numeric: tabular-nums; box-shadow: 0 0 0 1px var(--c); background: var(--panel); }
.tl-text { padding: 0 8px; line-height: 22px; background: var(--c); color: #fff; white-space: nowrap; }
.tl-chip.drag .tl-text { cursor: ns-resize; }
.tl-x { width: 22px; color: var(--c); display: grid; place-items: center; }
.tl-x:hover { background: var(--hover); }
.tl-chip.bot .tl-text { background: var(--panel); color: var(--c); }
```

- [ ] **Step 1:** Make the cell changes and run `node --test tests/js/*.test.mjs`. The existing big-prints behaviour is unchanged; `placeMarkers` was tested in Task 3.
- [ ] **Step 2:** Write `tradelines.js`, then register it: `page.overlays.push(window.HBTradeLines.overlay)` before `buildGrid()` runs (move `buildGrid()` after the mounts if needed).
- [ ] **Step 3:** Syntax check; Node and pytest green.
- [ ] **Step 4: Commit**
  ```
  feat(charts): Buy/Sell block (bid/ask as of last trade), position / order / SL / TP lines with draggable chips and ×, execution markers; cell overlays + merged extra markers
  ```

**Controller browser check (fake desk; NQ 1m, SIM…041 + SIM…047 ticked):**
- The block shows bid/ask and spread under the legend, and greys after 30 s of no trade.
- BUY 2 (one-click on) → `LONG 4 · +$… · 2 accts` at the average, green; `▲` markers at the fill price; the P&L updates with the replay.
- A Limit with SL/TP ticks → after `/fake/fill` of the entry, `SL 2 · −$… · …041` and `TP …` chips appear.
- Drag the SL chip down → the dollars update while dragging; release → the confirm reads `Move SL …` (with one-click off). Cancel → it snaps back. Confirm → the line moves after the desk event.
- Esc during a drag reverts it.
- × on the SL → the cancel confirm → the line is gone.
- × on the position → the flatten confirm → the lines are gone and ▼ markers appear.
- In mode `off`, lines have no × and no drag.
- The chips track the lines through zoom, scroll and autoscale.
- The chart does not pan while dragging a chip.
- Switching the interval keeps the lines.
- Zero console errors.

---

### Task 7: Live strategies on the chart (legend badge, the bot's lines and markers)

**Files:**
- Modify: `homebase/static/charts/tradelines.js` (the bot part), `icons.js` (Lucide `bot`), `charts.css`, `charts.html` (`?v=4` stays)

**Interfaces:**
- Consumes: `HBTrade.botsFor(state, root, tick, P)` → `[{key, badge:{text,tone}, lines:[{key,kind:'entry'|'sl'|'tp',price,text}], markers}]`.

**Requirements** (ruling S12):
- Each bot gets a badge in the legend title row, `this.badges`: `<span class="bot-badge <tone>">` with the Lucide `bot` icon plus the text.
  - The tone colours are: `live` = `--accent` on `--accent-soft`; `err` = `--down` on `--down-soft`; `idle` = `--text-2` on `--hover`.
  - Tooltip: `The desk's <name> for <root> (view only)`.
- The bot lines go through the same `items` map as the trading lines, keyed `bot|…`:
  - `lineStyle` 2, colour `P.warn` / `P.down` / `P.up` by kind;
  - a chip `.tl-chip.bot` with the bot icon + text, no ×, not draggable.
- Markers: `cell.setExtraMarkers('bots', allBots.flatMap((b) => b.markers))`.
- Bots show in **every** mode that has a state, `off` and `none` included, because they are view-only. There is nothing in `down`.

- [ ] **Step 1:** Add the `bot` icon (copy from lucide-static@1.48.0 as in Task 4). Implement the bot part inside `render()`.
- [ ] **Step 2:** Syntax check; Node and pytest green.
- [ ] **Step 3: Commit**
  ```
  feat(charts): the desk's live strategies on their symbol's charts — legend badge (gate, ADX, status, P&L), entry / SL / TP lines, entry and exit markers
  ```

**Controller browser check (fake desk):**
- `/fake/bot {"scenario":"placed","anchor":<NQ price>}` → NQ charts show `9:30 bot · TREND ADX 23.4 · placed` and two dashed amber chips `9:30 BUY STOP 1 @ …` / `9:30 SELL STOP 1 @ …`, with no ×.
- `live` → the SL/TP chips and an amber ▲ marker.
- `done` → the badge reads `done +$296`, the exit marker's text is `+$296`, and the lines are gone.
- ES/YM charts show no NQ bot.
- Trading off → the badge is still shown.

---

### Task 8: `HBTester`, the pure Strategy Tester model

**Files:**
- Create: `homebase/static/charts/tester.js`, `tests/js/tester.test.mjs`
- Modify: `charts.html` (`tester.js?v=4`, after `tradelines.js`)

**Interfaces:**
- Produces: `HBTester` = `{ RANGES, HOLDOUT_START, DEFAULT_RULES, REASON_MAX, defaults, restore, fromRun, reachesHoldout, problems, body, key, runLabel, progress, pct, rate, num, dur, fmtEt, tiles, badges, propView, summaryRows, periodRows, sortTrades, tradeCells, tradeMarks, equitySeries, reachSpec }`.
- Consumes: `HBTrade.usd / money`, `HBCatalog.fmtPrice`.

- [ ] **Step 1: Write the failing tests** (`tests/js/tester.test.mjs`)

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const M = '−';
const STRAT = { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ', inputs: [
  { key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', default: 10, min: 0, max: 400, step: 0.25, choices: [] },
  { key: 'adx_gate', label: 'ADX(14) trend gate', type: 'bool', default: false, min: null, max: null, step: null, choices: [] },
  { key: 'mode', label: 'Mode', type: 'choice', default: 'a', min: null, max: null, step: null, choices: ['a', 'b'] },
  { key: 'n', label: 'Bars', type: 'int', default: 3, min: 1, max: 9, step: 1, choices: [] }] };
const COL = { net_profit: 12345.5, net_profit_pct: 24.691, gross_profit: 30000, gross_loss: -17654.5, commission_paid: 96,
  max_drawdown: -4210, max_drawdown_pct: -8.42, max_runup: 15000, profit_factor: 1.8765, trades: 24, wins: 13, losses: 11,
  win_rate: 54.17, avg_trade: 514.4, avg_win: 2307.69, avg_loss: -1604.95, rr: 1.4379, rr_label: '1:1.44', largest_win: 5000,
  largest_loss: -2500, avg_seconds_in_trade: 192, avg_bars_in_trade: 3.2, max_consec_losses: 4, sharpe: 1.234, sortino: 2.1,
  sharpe_traded_days: 3.3, t_stat: 2.346, expectancy: 514.4, days: 24 };
const RUN = { strategy: { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ' }, inputs: { offset_pts: 12, adx_gate: true, mode: 'b', n: 2 },
  range: { kind: 'custom', start: '2023-01-01', end: '2025-02-01', label: '2023-01-01 → 2025-02-01', holdout: true },
  qty: 2, commission: 4, slippage_ticks: 1, capital: 50000, holdout: true, holdout_reason: 'final check', prop_rules: 'lucid-flex-50k@2026-08',
  engine: 'x', fill_law: 'tick replay',
  coverage: { sessions: 520, used: 517, skipped: [{ date: '2023-03-01', reason: 'missing 13:00–15:00 ET' }], skipped_by_reason: {},
    no_trade: [], skipped_by_error: 2, skipped_by_data: 1 },
  report: { summary: { all: COL, long: COL, short: COL }, by_year: [], by_month: [], skipped_by_error: 2, sharpe_basis: 'weekday grid' } };

test('form defaults from the schema; restore keeps only valid values', () => {
  const f = X.defaults(STRAT);
  assert.deepEqual(f, { strategy: 'nq930', inputs: { offset_pts: 10, adx_gate: false, mode: 'a', n: 3 },
    range: { kind: 'research', start: '', end: '' }, qty: 1, commission: 4, slippage_ticks: 1,
    prop_rules: 'lucid-flex-50k@2026-08', holdout: { on: false, reason: '' } });
  const r = X.restore({ ...f, inputs: { offset_pts: 11, adx_gate: 'yes', ghost: 1, n: 2.5 }, qty: 3 }, STRAT);
  assert.deepEqual(r.inputs, { offset_pts: 11, adx_gate: false, mode: 'a', n: 3 });
  assert.equal(r.qty, 3);
  assert.equal(X.restore({ strategy: 'other' }, STRAT).strategy, 'nq930');
});

test('holdout: which ranges reach 2025, and the refusals the page shows before sending', () => {
  const f = X.defaults(STRAT);
  assert.equal(X.reachesHoldout({ kind: 'research' }), false);
  assert.equal(X.reachesHoldout({ kind: 'custom', start: '2023-01-01', end: '2024-12-31' }), false);
  assert.equal(X.reachesHoldout({ kind: 'custom', start: '2023-01-01', end: '2025-01-01' }), true);
  assert.equal(X.reachesHoldout({ kind: 'is_months', start: '', end: '2025-03-01' }), true);
  assert.equal(X.problems(f, STRAT), null);
  assert.equal(X.problems({ ...f, range: { kind: 'custom', start: '2023-01-01', end: '' } }, STRAT), 'A custom range needs a start and an end date');
  assert.equal(X.problems({ ...f, range: { kind: 'custom', start: '2024-01-01', end: '2023-01-01' } }, STRAT), 'The start date is after the end date');
  const hold = { ...f, range: { kind: 'custom', start: '2024-06-01', end: '2025-06-01' } };
  assert.equal(X.problems(hold, STRAT), 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: '  ' } }, STRAT), 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: 'a\nb' } }, STRAT), 'The holdout reason is one line of at most 200 characters');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: 'final check' } }, STRAT), null);
  assert.equal(X.problems({ ...f, inputs: { ...f.inputs, offset_pts: 401 } }, STRAT), 'Entry offset (pts): 0 to 400');
  assert.equal(X.problems({ ...f, inputs: { ...f.inputs, n: 2.5 } }, STRAT), 'Bars: a whole number');
  assert.equal(X.problems({ ...f, qty: 0 }, STRAT), 'Qty: 1 to 100');
});

test('the request body: holdout only when the range reaches it; key and run label', () => {
  const f = X.defaults(STRAT);
  assert.deepEqual(X.body({ ...f, holdout: { on: true, reason: 'x' } }), { strategy: 'nq930', inputs: f.inputs, range: { kind: 'research' },
    qty: 1, commission: 4, slippage_ticks: 1, prop_rules: 'lucid-flex-50k@2026-08' });
  const h = { ...f, range: { kind: 'custom', start: '2024-06-01', end: '2025-06-01' }, holdout: { on: true, reason: ' final check ' } };
  assert.deepEqual(X.body(h).holdout, { reason: 'final check' });
  assert.deepEqual(X.body(h).range, { kind: 'custom', start: '2024-06-01', end: '2025-06-01' });
  assert.deepEqual(X.body({ ...f, range: { kind: 'is_months', start: '', end: '2023-12-31' } }).range, { kind: 'is_months', end: '2023-12-31' });
  assert.equal(X.runLabel(f, null), 'Run');
  assert.equal(X.runLabel(f, X.key(f)), 'Run');
  assert.equal(X.runLabel({ ...f, qty: 2 }, X.key(f)), 'Update report');
});

test('a loaded run fills the form back', () => {
  const f = X.fromRun(RUN, STRAT);
  assert.deepEqual(f.inputs, { offset_pts: 12, adx_gate: true, mode: 'b', n: 2 });
  assert.deepEqual(f.range, { kind: 'custom', start: '2023-01-01', end: '2025-02-01' });
  assert.deepEqual(f.holdout, { on: true, reason: 'final check' });
  assert.equal(f.qty, 2);
});

test('progress text and fraction', () => {
  assert.deepEqual(X.progress({ status: 'queued' }), { text: 'Queued…', frac: null, final: false });
  assert.deepEqual(X.progress({ status: 'running', phase: 'building cache', done: 120, total: 1004 }),
    { text: 'Building the tick cache · 120 / 1,004 sessions', frac: 120 / 1004, final: false });
  assert.equal(X.progress({ status: 'running', phase: 'run', done: 5, total: 10 }).text, 'Running · 5 / 10 sessions');
  assert.equal(X.progress({ status: 'running', phase: 'prop sim', done: 10, total: 10 }).text, 'Prop sim…');
  assert.deepEqual(X.progress({ status: 'error', error: 'boom' }), { text: 'Failed: boom', frac: null, final: true });
  assert.equal(X.progress({ status: 'done' }).final, true);
});

test('Overview tiles, badges and the prop block', () => {
  assert.deepEqual(X.tiles(RUN).map((t) => [t.label, t.value, t.sub]), [
    ['Net P&L', '+$12,345.50', '+24.69%'], ['Max drawdown', `${M}$4,210`, `${M}8.42%`], ['Win rate', '54.2%', '13/24'],
    ['Profit factor', '1.88', ''], ['Sharpe', '1.23', 'weekday grid'], ['Avg trade', '+$514.40', ''], ['Avg win : loss', 'RR 1:1.44', ''],
    ['t-stat', '2.35', '']]);
  assert.deepEqual(X.badges(RUN).map((b) => [b.text, b.tone]), [['Tick replay', 'info'], ['517 of 520 sessions', 'warn'],
    ['2 strategy errors', 'err'], ['Includes holdout', 'err']]);
  const prop = { rules: { name: 'Apex 50K', confirmed: false, label: 'Apex 50K · unconfirmed rules' }, caveat: 'c',
    headline: { eval_pass_p: 0.4312, eval_pass_ci: [0.424, 0.438], bust_p: 0.31, median_days_to_pass: 17.5, funded_expected_cheque: 1648.2 } };
  assert.deepEqual(X.propView(prop).tiles.map((t) => [t.label, t.value, t.sub]), [['Eval pass', '43.1%', '95% CI 42.4–43.8%'],
    ['Bust', '31.0%', ''], ['Median days to pass', '18', ''], ['Funded: expected cheque', '$1,648.20', '']]);
  assert.equal(X.propView(prop).unconfirmed, true);
  assert.deepEqual(X.propView({ error: 'bad file', rules: { name: 'x', confirmed: true } }), { message: 'Prop eval failed: bad file', rules: { name: 'x', confirmed: true }, unconfirmed: false });
  assert.deepEqual(X.propView(null), { message: 'No prop-eval result in this run', rules: null, unconfirmed: false });
});

test('performance summary rows (All / Long / Short, dollars, RR 1:X, Sharpe)', () => {
  const rows = X.summaryRows(RUN.report.summary);
  assert.deepEqual(rows[0], { label: 'Net profit', all: '+$12,345.50 (+24.69%)', long: '+$12,345.50 (+24.69%)', short: '+$12,345.50 (+24.69%)' });
  const by = Object.fromEntries(rows.map((r) => [r.label, r.all]));
  assert.equal(by['Ratio avg win / avg loss'], 'RR 1:1.44');
  assert.equal(by['Sharpe ratio'], '1.23');
  assert.equal(by['Avg time in trade'], '3m 12s');
  assert.equal(by['Gross loss'], `${M}$17,654.50`);
  assert.equal(by['Commission paid'], '$96');
});

const TRADES = [
  { date: '2024-01-02', side: 'long', qty: 1, entry_ms: Date.parse('2024-01-02T14:30:01Z'), entry_price: 16900.25, exit_ms: Date.parse('2024-01-02T14:31:00Z'),
    exit_price: 16915.25, exit_reason: 'tp', sl: 16895.25, tp: 16915.25, net: 296, mae_usd: -40, mfe_usd: 300, seconds: 59 },
  { date: '2024-01-03', side: 'short', qty: 1, entry_ms: Date.parse('2024-01-03T14:30:02Z'), entry_price: 16800, exit_ms: Date.parse('2024-01-03T14:35:00Z'),
    exit_price: 16805, exit_reason: 'sl', sl: 16805, tp: 16785, net: -104, mae_usd: -100, mfe_usd: 20, seconds: 298 }];

test('trades: sort, cells, chart marks', () => {
  assert.deepEqual(X.sortTrades(TRADES, 'net', -1), [0, 1]);
  assert.deepEqual(X.sortTrades(TRADES, 'net', 1), [1, 0]);
  assert.deepEqual(X.sortTrades(TRADES, 'n', 1), [0, 1]);
  assert.deepEqual(X.tradeCells(TRADES[1], 1, 0.25), ['2', 'Short', '2024-01-03 09:30:02', '16,800.00', '2024-01-03 09:35:00', '16,805.00',
    'SL', '1', `${M}$104`, `${M}$100`, '+$20', '4m 58s']);
  const P = { accent: 'A', down: 'D', up: 'U' };
  assert.deepEqual(X.tradeMarks(TRADES, P)[3], { id: 'tx1', ms: TRADES[1].exit_ms, price: 16805, position: 'atPriceMiddle', shape: 'circle',
    color: 'D', text: `${M}$104`, size: 0.6 });
  assert.equal(X.tradeMarks(TRADES, P)[2].shape, 'arrowDown');
});

test('equity series: strictly increasing seconds', () => {
  assert.deepEqual(X.equitySeries({ t_ms: [1000, 1500, 5000], equity: [1, 2, 3], drawdown: [0, 0, -1] }), {
    equity: [{ time: 1, value: 1 }, { time: 2, value: 2 }, { time: 5, value: 3 }],
    drawdown: [{ time: 1, value: 0 }, { time: 2, value: 0 }, { time: 5, value: -1 }] });
});

test('reachSpec: keep the interval when the history fits under the cap, else the finest that does', () => {
  const now = Date.parse('2026-09-26T12:00:00Z');
  // sessions = ceil(days * 5/7) + 2; bars/session = ceil(82800 / seconds); fits when sessions * bars <= 180,000
  assert.equal(X.reachSpec('time:60', now - 20 * 86400000, now), 'time:60');                        // 17 x 1380 = 23,460
  assert.equal(X.reachSpec('time:60', Date.parse('2025-06-01T13:30:00Z'), now), 'time:300');       // 347 x 276 = 95,772
  assert.equal(X.reachSpec('time:60', Date.parse('2024-03-01T14:30:00Z'), now), 'time:900');       // 673 x 276 = 185,748 > cap; x 92 fits
  assert.equal(X.reachSpec('time:60', Date.parse('2021-10-01T14:30:00Z'), now), 'time:900');       // 1,303 x 92 = 119,876
  assert.equal(X.reachSpec('tick:1000', now - 86400000, now), 'time:300');
  assert.equal(X.reachSpec('time:3600', Date.parse('2021-10-01T14:30:00Z'), now), 'time:3600');
});
```

- [ ] **Step 2:** Run `node --test tests/js/tester.test.mjs`. Expect: FAIL.

- [ ] **Step 3: Implement `tester.js`**

```js
/* Homebase Charts — the Strategy Tester panel, the pure half:
     - the run form: defaults from a strategy's input schema, the range presets, the holdout rule
       the server enforces, the request body, Run vs Update report;
     - the progress text;
     - the report's tiles, tables, trade rows, badges and chart marks;
     - the interval a jump to an old trade can use.
   No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const Tr = need('HBTrade', './trade.js');

const MINUS = '−';
const HOLDOUT_START = '2025-01-01';
const DEFAULT_RULES = 'lucid-flex-50k@2026-08';
const REASON_MAX = 200;
const RANGES = [{ kind: 'research', label: 'Research window 2021–2024' },
  { kind: 'is_months', label: 'IS months only (Jan/Apr/Jul/Oct)' }, { kind: 'custom', label: 'Custom…' }];
const HOLDOUT_MSG = 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason';
const ISO = /^\d{4}-\d{2}-\d{2}$/;
const ET = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit',
  day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const COSTS = [['qty', 'Qty', 1, 100, true], ['commission', 'Commission', 0, 100, false], ['slippage_ticks', 'Slippage (ticks)', 0, 20, false]];

/* ---- formatting ---- */
const neg = (s, v) => (v < 0 ? MINUS + s : s);
function num(v, d = 2) { return v == null || !Number.isFinite(v) ? '—' : v >= 999 ? '∞' : neg(Math.abs(v).toFixed(d), v); }
function pct(v) { return v == null || !Number.isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v).toFixed(2) + '%'; }
function rate(v) { return v == null || !Number.isFinite(v) ? '—' : v.toFixed(1) + '%'; }
function dur(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  s = Math.round(s);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}
function fmtEt(ms) {
  if (!Number.isFinite(ms)) return '—';
  const p = Object.fromEntries(ET.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}
const int = (v) => (v == null ? '—' : Number(v).toLocaleString('en-US'));
const signed = (v) => Tr.usd(v) ?? '—';

/* ---- the form ---- */
function inputError(inp, v) {
  if (inp.type === 'bool') return typeof v === 'boolean' ? null : `${inp.label}: on or off`;
  if (inp.type === 'choice') return inp.choices.includes(v) ? null : `${inp.label}: one of ${inp.choices.join(', ')}`;
  if (typeof v !== 'number' || !Number.isFinite(v)) return `${inp.label}: a number`;
  if (inp.type === 'int' && !Number.isInteger(v)) return `${inp.label}: a whole number`;
  if ((inp.min != null && v < inp.min) || (inp.max != null && v > inp.max)) return `${inp.label}: ${inp.min} to ${inp.max}`;
  return null;
}
function defaults(s) {
  return { strategy: s.id, inputs: Object.fromEntries(s.inputs.map((i) => [i.key, i.default])),
    range: { kind: 'research', start: '', end: '' }, qty: 1, commission: 4, slippage_ticks: 1,
    prop_rules: DEFAULT_RULES, holdout: { on: false, reason: '' } };
}
/* A saved form for strategy s: its valid values over the defaults (anything unknown or invalid is dropped). */
function restore(saved, s) {
  const f = defaults(s);
  if (!saved || saved.strategy !== s.id) return f;
  for (const i of s.inputs) { const v = saved.inputs && saved.inputs[i.key]; if (v !== undefined && !inputError(i, v)) f.inputs[i.key] = v; }
  const r = saved.range || {};
  if (RANGES.some((x) => x.kind === r.kind)) f.range = { kind: r.kind, start: ISO.test(r.start) ? r.start : '', end: ISO.test(r.end) ? r.end : '' };
  for (const [k, , lo, hi, whole] of COSTS) { const v = saved[k]; if (typeof v === 'number' && v >= lo && v <= hi && (!whole || Number.isInteger(v))) f[k] = v; }
  if (typeof saved.prop_rules === 'string') f.prop_rules = saved.prop_rules;
  if (saved.holdout && typeof saved.holdout.reason === 'string') f.holdout = { on: !!saved.holdout.on, reason: saved.holdout.reason.slice(0, REASON_MAX) };
  return f;
}
function fromRun(run, s) {
  return restore({ strategy: run.strategy.id, inputs: run.inputs,
    range: { kind: run.range.kind, start: run.range.kind === 'research' ? '' : run.range.start, end: run.range.kind === 'research' ? '' : run.range.end },
    qty: run.qty, commission: run.commission, slippage_ticks: run.slippage_ticks, prop_rules: run.prop_rules,
    holdout: { on: !!run.holdout, reason: run.holdout_reason || '' } }, s);
}
function reachesHoldout(r) { return !!r && r.kind !== 'research' && (r.end || '2024-12-31') >= HOLDOUT_START; }
function problems(f, s) {
  for (const i of s.inputs) { const e = inputError(i, f.inputs[i.key]); if (e) return e; }
  for (const [k, label, lo, hi, whole] of COSTS) {
    const v = f[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return `${label}: ${lo} to ${hi}`;
  }
  const r = f.range;
  if (r.kind === 'custom' && !(ISO.test(r.start) && ISO.test(r.end))) return 'A custom range needs a start and an end date';
  if (r.kind !== 'research' && r.start && r.end && r.start > r.end) return 'The start date is after the end date';
  if (reachesHoldout(r)) {
    const why = (f.holdout.reason || '').trim();
    if (!f.holdout.on || !why) return HOLDOUT_MSG;
    if (why.includes('\n') || why.length > REASON_MAX) return `The holdout reason is one line of at most ${REASON_MAX} characters`;
  }
  return null;
}
function rangeBody(r) {
  if (r.kind === 'research') return { kind: 'research' };
  const b = { kind: r.kind };
  if (r.start) b.start = r.start;
  if (r.end) b.end = r.end;
  return b;
}
/* The POST /api/tester/run body. holdout only when the range reaches 2025 (ruling S16: no spend otherwise). */
function body(f) {
  const b = { strategy: f.strategy, inputs: { ...f.inputs }, range: rangeBody(f.range), qty: f.qty, commission: f.commission,
    slippage_ticks: f.slippage_ticks, prop_rules: f.prop_rules };
  if (reachesHoldout(f.range)) b.holdout = { reason: f.holdout.reason.trim() };
  return b;
}
const key = (f) => JSON.stringify(body(f));
function runLabel(f, loadedKey) { return loadedKey && key(f) !== loadedKey ? 'Update report' : 'Run'; }

function progress(st) {
  const s = st && st.status;
  if (s === 'queued') return { text: 'Queued…', frac: null, final: false };
  if (s === 'running') {
    const n = `${int(st.done)} / ${int(st.total)} sessions`, frac = st.total ? st.done / st.total : null;
    if (st.phase === 'building cache') return { text: `Building the tick cache · ${n}`, frac, final: false };
    if (st.phase === 'daily bars') return { text: 'Loading daily bars…', frac: null, final: false };
    if (st.phase === 'prop sim') return { text: 'Prop sim…', frac: 1, final: false };
    return { text: `Running · ${n}`, frac, final: false };
  }
  if (s === 'error') return { text: `Failed: ${st.error || 'unknown error'}`, frac: null, final: true };
  if (s === 'cancelled') return { text: 'Cancelled', frac: null, final: true };
  if (s === 'done') return { text: 'Done', frac: 1, final: true };
  return { text: '', frac: null, final: false };
}

/* ---- the report ---- */
const toneOf = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
function tiles(run) {
  const a = run.report.summary.all;
  return [
    { label: 'Net P&L', value: signed(a.net_profit), sub: pct(a.net_profit_pct), tone: toneOf(a.net_profit) },
    { label: 'Max drawdown', value: Tr.money(a.max_drawdown), sub: pct(a.max_drawdown_pct), tone: toneOf(a.max_drawdown) },
    { label: 'Win rate', value: rate(a.win_rate), sub: `${a.wins ?? 0}/${a.trades ?? 0}`, tone: '' },
    { label: 'Profit factor', value: num(a.profit_factor), sub: '', tone: '' },
    { label: 'Sharpe', value: num(a.sharpe), sub: 'weekday grid', tone: '', title: run.report.sharpe_basis },
    { label: 'Avg trade', value: signed(a.avg_trade), sub: '', tone: toneOf(a.avg_trade) },
    { label: 'Avg win : loss', value: a.rr_label && a.rr_label !== '—' ? `RR ${a.rr_label}` : '—', sub: '', tone: '' },
    { label: 't-stat', value: num(a.t_stat), sub: '', tone: '' }];
}
function badges(run) {
  const c = run.coverage || {}, out = [{ text: 'Tick replay', tone: 'info', title: 'Fills replay the tape: a stop entry pays the gap, a target needs 1-tick penetration' }];
  const skipped = (c.skipped || []).length, why = Object.entries(c.skipped_by_reason || {}).map(([k, n]) => `${n} × ${k}`).join('\n');
  out.push({ text: `${int(c.used)} of ${int(c.sessions)} sessions`, tone: skipped ? 'warn' : 'info', title: why || 'Every session in the range was used' });
  const errs = run.report.skipped_by_error || 0;
  if (errs) out.push({ text: `${errs} strategy error${errs === 1 ? '' : 's'}`, tone: 'err', title: 'Sessions the strategy crashed on (see Properties)' });
  if (run.holdout) out.push({ text: 'Includes holdout', tone: 'err', title: run.holdout_reason || '' });
  return out;
}
function propView(p) {
  const rules = p ? p.rules || null : null, unconfirmed = !!(rules && rules.confirmed === false);
  if (!p) return { message: 'No prop-eval result in this run', rules: null, unconfirmed: false };
  if (p.error) return { message: `Prop eval failed: ${p.error}`, rules, unconfirmed };
  if (p.skipped) return { message: p.skipped, rules, unconfirmed };
  const h = p.headline, ci = h.eval_pass_ci;
  return { rules, unconfirmed, caveat: p.caveat || '', tiles: [
    { label: 'Eval pass', value: rate(h.eval_pass_p * 100), sub: ci ? `95% CI ${(ci[0] * 100).toFixed(1)}–${(ci[1] * 100).toFixed(1)}%` : '' },
    { label: 'Bust', value: rate(h.bust_p * 100), sub: '' },
    { label: 'Median days to pass', value: h.median_days_to_pass == null ? '—' : String(Math.round(h.median_days_to_pass)), sub: '' },
    { label: 'Funded: expected cheque', value: Tr.money(h.funded_expected_cheque), sub: '' }] };
}
const SUMMARY = [
  ['Net profit', (c) => `${signed(c.net_profit)} (${pct(c.net_profit_pct)})`],
  ['Gross profit', (c) => Tr.money(c.gross_profit)], ['Gross loss', (c) => Tr.money(c.gross_loss)],
  ['Commission paid', (c) => Tr.money(c.commission_paid)],
  ['Max drawdown', (c) => `${Tr.money(c.max_drawdown)} (${pct(c.max_drawdown_pct)})`], ['Max run-up', (c) => Tr.money(c.max_runup)],
  ['Profit factor', (c) => num(c.profit_factor)], ['Total trades', (c) => int(c.trades)], ['Winning trades', (c) => int(c.wins)],
  ['Losing trades', (c) => int(c.losses)], ['Percent profitable', (c) => rate(c.win_rate)], ['Avg trade', (c) => signed(c.avg_trade)],
  ['Avg winning trade', (c) => signed(c.avg_win)], ['Avg losing trade', (c) => signed(c.avg_loss)],
  ['Ratio avg win / avg loss', (c) => (c.rr_label && c.rr_label !== '—' ? `RR ${c.rr_label}` : '—')],
  ['Largest winning trade', (c) => signed(c.largest_win)], ['Largest losing trade', (c) => signed(c.largest_loss)],
  ['Avg time in trade', (c) => dur(c.avg_seconds_in_trade)], ['Avg bars in trade', (c) => num(c.avg_bars_in_trade, 1)],
  ['Max consecutive losses', (c) => int(c.max_consec_losses)], ['Sharpe ratio', (c) => num(c.sharpe)], ['Sortino ratio', (c) => num(c.sortino)],
  ['Sharpe (traded days only)', (c) => num(c.sharpe_traded_days)], ['t-stat', (c) => num(c.t_stat)], ['Expectancy', (c) => signed(c.expectancy)],
  ['Trading days', (c) => int(c.days)]];
function summaryRows(s) { return SUMMARY.map(([label, f]) => ({ label, all: f(s.all), long: f(s.long), short: f(s.short) })); }
function periodRows(list) {
  return (list || []).map((p) => ({ period: p.period, trades: int(p.trades), net: signed(p.net), tone: toneOf(p.net), win: rate(p.win_rate),
    pf: num(p.profit_factor), dd: Tr.money(p.max_drawdown), sharpe: num(p.sharpe), avg: signed(p.avg_trade) }));
}

/* ---- the list of trades ---- */
const SORT = { n: (t, i) => i, side: (t) => t.side, entry: (t) => t.entry_ms, exit: (t) => t.exit_ms, reason: (t) => t.exit_reason,
  qty: (t) => t.qty, net: (t) => t.net, mae: (t) => t.mae_usd, mfe: (t) => t.mfe_usd, dur: (t) => t.seconds };
/* Trade indices sorted by column `k`, dir 1 ascending / −1 descending; ties keep the trade order. */
function sortTrades(trades, k, dir) {
  const f = SORT[k] || SORT.n;
  return trades.map((t, i) => i).sort((a, b) => {
    const x = f(trades[a], a), y = f(trades[b], b);
    return (x < y ? -1 : x > y ? 1 : 0) * dir || a - b;
  });
}
function tradeCells(t, i, tick) {
  return [String(i + 1), t.side === 'long' ? 'Long' : 'Short', fmtEt(t.entry_ms), Cat.fmtPrice(t.entry_price, tick), fmtEt(t.exit_ms),
    Cat.fmtPrice(t.exit_price, tick), String(t.exit_reason || '').toUpperCase(), String(t.qty), signed(t.net), signed(t.mae_usd),
    signed(t.mfe_usd), dur(t.seconds)];
}
/* Entry ▲/▼ at the entry price, exit ● at the exit price with the net $ (ruling S21); {ms,…} for placeMarkers. */
function tradeMarks(trades, P) {
  const out = [];
  trades.forEach((t, i) => {
    const long = t.side === 'long';
    out.push({ id: `te${i}`, ms: t.entry_ms, price: t.entry_price, position: long ? 'atPriceBottom' : 'atPriceTop',
      shape: long ? 'arrowUp' : 'arrowDown', color: long ? P.accent : P.down, text: '' });
    out.push({ id: `tx${i}`, ms: t.exit_ms, price: t.exit_price, position: 'atPriceMiddle', shape: 'circle',
      color: t.net >= 0 ? P.up : P.down, text: signed(t.net), size: 0.6 });
  });
  return out;
}
function equitySeries(eq) {
  const out = { equity: [], drawdown: [] };
  let last = -Infinity;
  (eq.t_ms || []).forEach((ms, i) => {
    let t = Math.floor(ms / 1000);
    if (t <= last) t = last + 1;
    last = t;
    out.equity.push({ time: t, value: eq.equity[i] });
    out.drawdown.push({ time: t, value: eq.drawdown[i] });
  });
  return out;
}

/* The interval a jump back to `ms` can use (ruling S20): the chart's own time interval when the sessions back to
   it fit under 90% of the client cap, else the finest of 5m, 15m, 1h, 4h, D that does. 23 h sessions, 5 per week. */
function reachSpec(spec, ms, nowMs, cap = 200000) {
  const sessions = Math.ceil(Math.max(1, (nowMs - ms) / 86400000) * 5 / 7) + 2;
  const fits = (sec) => sessions * Math.ceil(82800 / sec) <= cap * 0.9;
  const m = /^time:(\d+)$/.exec(spec), own = m ? Number(m[1]) : 0;
  if (own && fits(own)) return spec;
  for (const s of [300, 900, 3600, 14400, 86400]) if (s >= own && fits(s)) return `time:${s}`;
  return 'time:86400';
}

const api = { RANGES, HOLDOUT_START, DEFAULT_RULES, REASON_MAX, defaults, restore, fromRun, reachesHoldout, problems, body, key, runLabel,
  progress, pct, rate, num, dur, fmtEt, tiles, badges, propView, summaryRows, periodRows, sortTrades, tradeCells, tradeMarks,
  equitySeries, reachSpec };
if (typeof window !== 'undefined') window.HBTester = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4:** Run `node --test tests/js/*.test.mjs`. Expect: PASS.
- [ ] **Step 5: Commit**
  ```
  feat(charts): HBTester — run form from the schema, holdout rule mirrored, request body, progress, tiles / summary / trades / marks, equity series, jump interval
  ```

---

### Task 9: The Strategy Tester tab

**Files:**
- Create: `homebase/static/charts/testerui.js`
- Modify: `app.js` (`HBTesterUI.mount(page)`), `charts.html` (`testerui.js?v=4`), `charts.css`, `icons.js` (Lucide `play`, `square`, `history`)

**Interfaces:**
- Consumes: `HBTester`, `HBPanel.addTab`, `page`, `LightweightCharts`.
- Produces: `HBTesterUI`:
  - `mount(page)`;
  - `get bundle()` (the loaded `{run, trades, equity, plots, propsim}` or null);
  - `get selected()` (a trade index or null);
  - `get hidden()` (bool);
  - `on(fn) -> off` (fires on bundle, selection and hide changes);
  - `select(i)`.
  - Task 10 reads these.

**Requirements:**
- The tab is `HBPanel.addTab({id: 'tester', label: 'Strategy Tester', render, onShow, onHide})`.
- **Header row** (40px, one line, horizontally scrollable on narrow windows), left to right:
  1. the strategy `<select>` (`name` options, from `GET /api/tester/strategies`, loaded once);
  2. a gear (the inputs dialog);
  3. a range `<select>` (`HBTester.RANGES`); with Custom, two `<input type=date>` inline;
  4. `Qty`, `Commission $` and `Slippage (ticks)` as number inputs, 56px each;
  5. a `Holdout` switch; when on, an inline reason input (maxlength 200, placeholder `Why spend holdout data? (logged)`);
  6. the Run button (`HBTester.runLabel`, Lucide `play`);
  7. while running: a 120px progress bar + `progress().text` + a `Cancel` button (Lucide `square`);
  8. `Recent runs ▾` (Lucide `history`) at the far right;
  9. an inline error line (`--down`, textContent), holding the first `HBTester.problems(form, strategy)` or the server's 400 `detail`.
- **Inputs dialog** (`page.openDialog(strategy.name + ' · Inputs', 'settings-small')`):
  - one row per schema input: `int`/`float` → number (min/max/step); `bool` → checkbox; `choice` → select;
  - a `PROP EVAL` section with a rule-set select from `GET /api/tester/prop-rules`, where an unconfirmed set's option text ends in ` · unconfirmed rules`;
  - `Cancel` / `Ok`. Ok validates each input with the form rules and shows an inline error instead of saving.
- The form persists per viewer in `localStorage` `hb_tester` (`{strategy, forms: {id: form}}`, in try/catch) and is restored with `HBTester.restore`.
- **Run:**
  - if `problems` is set, show it and send nothing;
  - else `POST /api/tester/run` with `HBTester.body(form)`;
  - on a 400, show `detail` inline;
  - on `{id}`, poll `GET /api/tester/run/{id}` every 500 ms with a `setTimeout` chain, stopped by `final` and on unmount;
  - when done, `GET …/bundle` → the bundle is loaded, `loadedKey = HBTester.key(form)`, and the button reads Run;
  - Cancel → `POST …/cancel`.
- **Recent runs:** `GET /api/tester/runs` builds a menu. Each row reads `strategy · range label · net $ · n trades`, with a red `holdout` tag when set. A done run loads its bundle and fills the form with `HBTester.fromRun`. A non-done run shows its status text in the row, disabled.
- **Inner tabs** (32px, TradingView's order): `Overview · Performance summary · List of trades · Properties`.
  - **Overview:**
    - the badges row (`HBTester.badges`; tones `info` `--text-2`/`--hover`, `warn` `--warn`, `err` `--down`/`--down-soft`; `title` tooltips);
    - an 8-tile grid (`HBTester.tiles`, 2 rows of 4; value 18px/600 coloured by tone; label 12px `--text-2`; sub 12px);
    - the equity + drawdown mini chart (below);
    - a `Prop eval` block: the rules label with an amber `unconfirmed rules` badge when needed, 4 tiles or the message, and the caveat in 12px `--text-2`.
  - **Performance summary:** a `.bp-table` with the columns `· All · Long · Short` (`HBTester.summaryRows`), then `By year` and a `<details><summary>By month</summary>` table (`periodRows`).
  - **List of trades:** a `.bp-table` whose headers sort (click toggles ▲/▼; `sortTrades`) and whose cells come from `tradeCells(t, i, tick)`.
    - `tick` = the `tick` of any chart showing the strategy's root, else 0.25.
    - Clicking a row selects it (`--accent-soft` background) and calls `HBTesterLayer.jump(i)` (Task 10; guard with `window.HBTesterLayer &&`).
    - Rows render in chunks of 500, with a `Show more` row, so a 5,000-trade run stays fast.
  - **Properties:** key/value rows for:
    - strategy (name, id, root);
    - inputs (each `label = value`);
    - range label;
    - qty, commission $, slippage ticks, capital $;
    - prop rules;
    - sessions: `used / sessions`, with every skipped `date — reason` listed (collapsed `<details>` if over 10);
    - `no_trade` reasons;
    - engine, fill law;
    - holdout reason;
    - the run id and created/finished times.
- A `Hide trades` checkbox sits at the right of the inner tab bar and changes `hidden`.

**Key code:** the mini chart (Overview). It is rebuilt when a bundle loads and removed when the tab or bundle changes.

```js
function miniChart(el, equity, P) {
  const LW = window.LightweightCharts, s = window.HBTester.equitySeries(equity);
  const chart = LW.createChart(el, { autoSize: true, height: 180,
    layout: { background: { color: 'transparent' }, textColor: P.text2, fontSize: 11, attributionLogo: false,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif' },
    grid: { vertLines: { visible: false }, horzLines: { color: P.grid } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, handleScroll: false, handleScale: false });
  const eq = chart.addSeries(LW.AreaSeries, { lineColor: P.up, topColor: 'rgba(8,153,129,.28)', bottomColor: 'rgba(8,153,129,0)',
    lineWidth: 2, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false });
  eq.setData(s.equity);
  const dd = chart.addSeries(LW.AreaSeries, { lineColor: P.down, topColor: 'rgba(242,54,69,0)', bottomColor: 'rgba(242,54,69,.35)',
    lineWidth: 1, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false }, 1);
  dd.setData(s.drawdown);
  chart.panes()[1].setStretchFactor(0.35);
  chart.timeScale().fitContent();
  return chart;   // caller: chart.remove() before re-render
}
```

`P` is the current palette. Read it from any cell (`page.cur().P`), or compute the few colours from the theme the same way `cell.js` does.

- [ ] **Step 1:** Add the icons (`play`, `square`, `history`, copied from lucide-static@1.48.0). Write `testerui.js`.
- [ ] **Step 2:** Syntax check; Node and pytest green.
- [ ] **Step 3: Commit**
  ```
  feat(charts): Strategy Tester tab — strategy, inputs dialog from the schema, ranges, costs, holdout with reason, run / progress / cancel, recent runs, Overview (tiles, equity + drawdown, prop eval), Performance summary, List of trades, Properties
  ```

**Controller browser check (replay :8854; the tester runs read the local archive read-only; the first run may build its cache):**
- The Strategy Tester tab opens. `nq930` is selected, with defaults shown in the inputs dialog.
- Range `Custom` 2024-01-02 → 2024-01-31 → Run → progress → Overview shows 8 tiles (dollars, `RR 1:X`, Sharpe), the equity + drawdown chart, the badges `Tick replay` and `N of M sessions`, and Prop eval tiles.
- Change the qty → the button reads `Update report`.
- Custom end 2025-01-15 with Holdout off → an inline refusal, and nothing sent.
- Holdout on with a reason → the inline message clears and Run is enabled. **Do not click it** (see the note below).
- Performance summary shows All/Long/Short.
- List of trades sorts by Net.
- Properties lists the inputs and sessions.
- Recent runs lists the run and reloading it works.
- Dark theme.
- Zero console errors.

> Note for the controller: a holdout run appends a spend (the user's data rule). Browser checks never send a holdout run. Check the inline refusal with the switch off, and with the switch on check that Run is enabled **without clicking it**.

---

### Task 10: Tester trades on the chart, jumping to a trade, Hide trades, and the final sweep

**Files:**
- Create: `homebase/static/charts/testerlayer.js`
- Modify: `homebase/static/charts/cell.js` (`reach`, `reachStep`, `focusRange`, `whenLoaded`, and calls in `onOlder` / `onHistory` / `onError` / `teardown`), `app.js` (`page.overlays.push(HBTesterLayer.overlay)`), `charts.html` (`testerlayer.js?v=4`; final `?v=` audit), `charts.css`

**Interfaces:**
- Consumes: `HBTesterUI.bundle / selected / hidden / on / select`, `HBTester.tradeMarks / reachSpec`, `HBDrawings.placeMarkers / timeToX / barIndexAt`.
- Produces:
  - `HBTesterLayer.overlay(cell, page)`;
  - `HBTesterLayer.jump(i)`;
  - Cell: `reach(ms, onStep) -> Promise<bool>`, `focusRange(fromMs, toMs) -> bool`, `whenLoaded() -> Promise<bool>`.

**Cell key code:**

```js
  // constructor: this.reaching = null; this.loadWaiters = [];

  /* A history message landed: whoever waits for this chart's load (a jump that switched its root or interval). */
  // end of onHistory(): const w = this.loadWaiters; this.loadWaiters = []; w.forEach((f) => f(true));
  // onError() when nothing else is in flight: const w = this.loadWaiters; this.loadWaiters = []; w.forEach((f) => f(false));
  whenLoaded() { return new Promise((res) => this.loadWaiters.push(res)); }

  /* Load older history until the first bar starts at or before ms (a tester trade). It rides the scroll-back
     guard (one request at a time, the pauses after errors) and asks again every 700 ms until the answer lands.
     true once ms is on the chart; false when the archive or the 200,000-bar cap ends first, or a newer reach()
     or teardown() replaced it. */
  reach(ms, onStep) {
    if (this.reaching) this.reaching.resolve(false);
    return new Promise((resolve) => {
      const r = this.reaching = { ms, onStep, timer: 0,
        resolve: (ok) => { clearTimeout(r.timer); if (this.reaching === r) this.reaching = null; resolve(ok); } };
      this.reachStep();
    });
  }
  reachStep() {
    const r = this.reaching;
    if (!r) return;
    if (this.bars.length && this.bars[0].ms <= r.ms) { r.resolve(true); return; }
    if (this.back.done || this.capped) { r.resolve(false); return; }
    if (r.onStep && this.bars.length) r.onStep(this.bars[0].ms);
    this.askOlder({ from: 0, to: 0 });
    clearTimeout(r.timer);
    r.timer = setTimeout(() => this.reachStep(), 700);
  }
  // end of onOlder(): if (this.reaching) this.reachStep();
  // teardown() is not enough (a rebuild keeps the chart): destroy() does if (this.reaching) this.reaching.resolve(false);

  /* Zoom the time axis to [fromMs, toMs] with half its width of padding (at least 10 bars) each side. */
  focusRange(fromMs, toMs) {
    const D = window.HBDrawings, i = D.barIndexAt(this.bars, fromMs), j = Math.max(i, D.barIndexAt(this.bars, toMs));
    if (!this.chart || i < 0) return false;
    const pad = Math.max(10, Math.round((j - i) / 2));
    this.chart.timeScale().setVisibleLogicalRange({ from: i - pad, to: j + pad });
    return true;
  }
```

**The layer** (`testerlayer.js`): one overlay per chart. It is active when `HBTesterUI.bundle` exists, `cell.shown.root === bundle.run.strategy.root`, and trades are not hidden.
- **Markers:** `cell.setExtraMarkers('tester', active ? HBTester.tradeMarks(bundle.trades, cell.P) : [])`. They are recomputed only on bundle or hide changes, and on `onBars` only when `bars[0].ms` changed (older history came in).
- **Plots:** one `LineSeries` per `bundle.plots.plots[name]` on the price pane, with:
  ```
  {color: C.LINE_COLORS[k % 5], lineWidth: 1, lastValueVisible: false, priceLineVisible: false, autoscaleInfoProvider: () => null}
  ```
  The data maps each `[t_ms, v]` to `bars[barIndexAt(bars, t_ms)].tt`, drops points outside the bars, and keeps the last value per `tt`. The series are removed on destroy, hide and bundle change.
- **Primitive** (`TesterMarks`, attached to `cell.candles`; a `paneViews()` renderer using `useBitmapCoordinateSpace`, as `primitives.js` does):
  - for the **selected** trade, three short horizontal segments from x(entry) to x(exit):
    - entry price, `P.text2`, 1px;
    - SL, `P.down`, 1px dashed;
    - TP, `P.up`, 1px dashed;
  - a dashed connector from (x(entry), entry price) to (x(exit), exit price), in `P.up` when the trade's net is ≥ 0, else `P.down`;
  - for each `hlines` item, a 1px `P.text2` dotted segment across the bars whose `b.s === item.date`, with its name as a 11px label at the left end.
  - x uses `HBDrawings.timeToX(ms, {bars, isTime, barMs, coord: (i) => chart.timeScale().logicalToCoordinate(i)})` and y uses `cell.candles.priceToCoordinate`. A segment is skipped when either end is null.
- **`jump(i)`** (ruling S20):

```js
async function jump(i) {
  const U = window.HBTesterUI, b = U.bundle, t = b && b.trades[i];
  if (!t) return;
  U.select(i);
  const root = b.run.strategy.root, cells = page.cells(), rootOf = (c) => (c.shown || c.cfg).root;
  let cell = rootOf(page.cur()) === root ? page.cur() : cells.find((c) => rootOf(c) === root) || page.cur();
  page.select(cell);
  const spec = window.HBTester.reachSpec(cell.cfg.spec, t.entry_ms, page.clockMs());
  if (rootOf(cell) !== root || spec !== cell.cfg.spec) {
    const waiting = cell.whenLoaded();
    cell.update({ root, spec });
    if (spec !== cell.cfg.spec || !(await waiting)) return;
    if (spec !== cell.cfg.spec) page.sbNote(`Switched to ${spec.replace('time:', '')}s bars to reach ${t.date}`);
  }
  const day = t.date;
  const ok = await cell.reach(t.entry_ms, (firstMs) => page.sbNote(`Loading history back to ${day}… (at ${new Date(firstMs).toISOString().slice(0, 10)})`));
  if (!ok) { page.sbNote(`${day} is older than this chart's history can load`); return; }
  page.sbNote('');
  cell.focusRange(t.entry_ms, t.exit_ms);
}
```

Name the interval note the way the toolbar names intervals: use `HBCatalog`'s label for a spec if one exists (e.g. `5m`). The `${…}s bars` above is a fallback.

- [ ] **Step 1:** Make the cell changes, then write `testerlayer.js`. Register it with `page.overlays.push(window.HBTesterLayer.overlay)`.
- [ ] **Step 2: Final `?v=` audit.**
  - `git diff --name-only main -- homebase/static/` lists every changed or new asset; each must load with `?v=4` in `charts.html`, and nothing else may carry `?v=4`.
  - The script order matches the execution notes.
- [ ] **Step 3: Full verification.**
  - Syntax-check every page script.
  - `node --test tests/js/*.test.mjs` is green.
  - `.venv/bin/python -m pytest -q` is green.
  - `git grep -nE "\balert\(|\bconfirm\(|\bprompt\(" homebase/static/charts` finds no native dialog (`HBTradeUI.confirm` is ours; check that every hit is `HBTradeUI.confirm` or a method definition).
  - `git grep -n "desk.key" tools homebase/static` finds nothing.
- [ ] **Step 4: Commit**
  ```
  feat(charts): tester trades on the strategy's chart (entry/exit markers with $, selected trade's entry/SL/TP and connector, plots, hlines), jump to a trade through scroll-back with an interval that fits, Hide trades
  ```

**Controller browser check (replay :8854 + fake desk):**
- Load the January-2024 nq930 run from Task 9 → on an NQ chart, scroll back or let the jump load history.
- Click a trade in the list → the NQ chart switches to the interval `reachSpec` picks, shows `Loading history back to 2024-01-…` in the status bar, then zooms to the trade with its ▲/▼ entry, ● exit with `+$…`, and the entry/SL/TP segments and connector.
- Another row → the selection moves.
- `Hide trades` → everything tester-related disappears from the chart and comes back when unticked.
- An ES chart shows no nq930 trades.
- The trading lines and bot markers still show alongside, since the markers are merged.
- Reload → the tester form is restored, and Recent runs reloads the bundle.
- The full Task 5–7 flows still pass.
- Dark theme and a narrow window (the panel header scrolls, nothing overlaps).
- Zero console errors.
- Screenshots of: the Trade menu, the confirm dialog, the lines with chips, the bot badge, the tester Overview and a jumped trade.

---

## Self-review (done while writing)

- **Spec coverage:**

  | Spec item | Task |
  |---|---|
  | Toolbar Trade + account menu (ticks, DEMO/LIVE, one-click, default qty, SL/TP ticks, "off on the desk" + link, per-viewer persistence) | 5 |
  | Buy/Sell block ("as of last trade", qty, spread) | 6 |
  | Right-click Buy/Sell limit/stop + Cancel all / Flatten / Reverse through `HBChartMenu.register` | 5 |
  | Position / order / bracket lines, draggable, × | 6 |
  | Execution markers | 6 |
  | Confirm with RR 1:X and $ | 3 and 5 |
  | Toasts with refusal reasons | 3 and 4 |
  | Disabled / down state | 3, 5 and 6 |
  | Bottom panel Positions / Orders / Fills / Accounts | 4 |
  | Live strategies: badge, entry lines, SL/TP, markers | 3 and 7 |
  | Tester header: strategy, inputs dialog, ranges + custom, qty / commission / slippage, holdout + reason, Run / Update report, progress, cancel | 8 and 9 |
  | Tester Overview (tiles, equity/DD, badges, prop eval with unconfirmed label) | 9 |
  | Tester Performance summary | 9 |
  | Tester List of trades → jump | 9 and 10 |
  | Tester Properties | 9 |
  | Tester trades on the root's chart + Hide trades | 10 |
  | Per-chart gear | 1 |
  | Fake desk + replay-only override | 2 |
  | Cache-bust | every task, audited in 10 |

- **Known gap, reported:** a 1-minute jump into 2021–2024 cannot load under the client cap without a server "history at a date" op. S20 switches the interval instead, and the final report lists the follow-up.
- **Type consistency:** `linesFor` groups `{key, kind, side, type?, price, qty, legs[{account, who, qty, order_id?, avg, s, pv}]}` are what `lineText`, `actionTitle`, `closeLine` and `moveLine` use. `botsFor` gives `lines[{key, kind, price, text}]`. `placeMarkers` takes `{ms, …}` from `fillMarkers`, `botsFor().markers` and `tradeMarks`. The cell hooks `setExtraMarkers`, `reach`, `focusRange` and `whenLoaded` are defined in Tasks 6 and 10 before they are used.
