# Accounts per chart, a PAPER account, layout tabs, and app-wide Settings. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make **assigned accounts** the single thing that binds a chart to trading. An algo follows from its accounts. Add a PAPER account for forward testing and manual paper trading, replace the layout dropdown with TradingView-style layout tabs, and add an app-wide Settings dialog whose first setting picks the market-data account.

**Architecture:**
- A chart's `trade.accounts` becomes the whole story: non-empty means trade-ready, empty means view-only. The separate `trade.on` flag is retired.
- The `#tbTrade` toolbar menu is deleted; everything in it moves into the chart's gear → Trading tab, with the desk's own status moving to the bottom status bar.
- `PAPER` becomes a virtual account in the same list, served by a new `homebase/charts/paperbook.py` (manual paper positions and orders against live quotes, using the backtester's fill law). The existing algo forward-test runner (`paper.py`) is untouched.
- App settings live in `.state/charts/settings.json`, served by `/api/settings`.

**Tech Stack:** Python 3 / FastAPI / pytest; plain-JS IIFEs; Lightweight Charts 5.2.1; Node 26.

**Spec:** the design the user approved in chat on 2026-09-27 ("yes it matches"), plus their three answers. Verbatim intent:

> "im thinking its probably better to assign accounts instead of algos, unless its foward testing, lets add a paper account, for the fowardtesting … we just click the settings per tab and go to trading tab and in here there should be option to pick an algo and then i have to pick the accounts within it, and another section where theres accounts and i can just pick accounts, and if i assign an account thats in an algo, it shows the algo that i connected on the chart how it is, so we can remove the trading tab … also on the trading view top of the app, theres tabs for layouts, i like that lets add something like that"

Their answers: **an account IS the switch**; the PAPER account does **forward-test algos AND manual paper trading**; a layout tab is **one whole saved layout**. And on market data:

> "is that something thats automatic toward whichever account is connected … we should have a setting for the overall app … choosing which account it extracts and fills the chart with, becasue the live account is what has the level 2 data"

## Global Constraints

- **Assigning accounts is the only way a chart becomes trade-ready.** Every existing guard stays: the confirm dialog unless one-click, the two-step LIVE arm, the frozen preview→send, shown∩fresh account resolution, the in-flight lock, the replay guard, and the desk's own 10/20 caps and 09:20-09:35 bot lock.
- **A fresh chart has no accounts**, so it is view-only. **Changing a chart's instrument clears its accounts** (the existing safety ruling, now expressed as clearing rather than switching off).
- **Loading a layout restores DEMO and PAPER accounts but NEVER a LIVE account.** A live account must be re-ticked and re-armed in the session. A restored layout that dropped a live account says so once, plainly.
- **PAPER never reaches a broker.** No desk call, no order, on any paper path. A test asserts `paperbook.py` imports nothing from the broker, desk or trading modules, and that the page's paper path has no desk client reference.
- Market data is a **live trading feed**: switching its login drops and re-establishes the md socket. Never switch inside 09:20-09:35 ET on a weekday, and never while the desk's bot is placing.
- Lucide icons only. Look like TradingView, light default. No native dialogs. Bump every `charts.html` script tag one `?v=` in the final task, plus the desk's Charts link.

## Routing

| Task | Branch / worktree | Parallel? |
|---|---|---|
| 1 Accounts per chart (retire `trade.on`, redesign the Trading tab, delete the Trade menu) | `feat/chart-accounts` | — |
| 2 PAPER account (backend + wiring) | `feat/chart-accounts`, after Task 1 | — |
| 3 Layout tabs | `feat/layout-tabs` | yes |
| 4 App Settings + market-data account | `feat/app-settings` | yes |

---

### Task 1: Accounts per chart (MONEY PATH)

**Files:** `homebase/static/charts/trade.js`, `tradeui.js`, `tradelines.js`, `settings-dialog.js`, `app.js`, `charts.html` (delete `#tbTrade`), `charts.css`, `orderpanel.js` (its accounts row and "Change" link).

**The model:**
- A cell's config keeps `trade: { accounts: [...] }` and `algo`. **`trade.on` is gone**; `accounts.length > 0` replaces it everywhere.
- `HBTrade.tradeMode(desk, cellTrade)` reasons:
  - no accounts → mode `'off'`, reason "No accounts on this chart — pick one in the chart's ⚙ → Trading";
  - otherwise the existing rules (desk down, nothing tradable, LIVE unarmed).
- `loadedTrade(raw)` keeps DEMO and PAPER ids and drops every LIVE id. It returns `{accounts, droppedLive: [...]}` so the caller can say so once.
- Changing the instrument clears `accounts` (today it switches `on` off).

**Gear → Trading tab**, three sections in this order:
1. **ACCOUNTS** — one row per account: a checkbox, the label, an env chip (`LIVE` red, `DEMO` grey, `PAPER` amber), the balance, and, when that account is booked to an algo on this chart's instrument, a quiet "in NQ 9:30 Straddle". Ticking a LIVE row starts the existing two-step arm; it only ticks once armed. An account the desk does not list shows "?" and cannot be ticked (fail closed).
2. **ALGO** — the existing select, plus: picking an algo ticks its booked accounts for this instrument; ticking an account that belongs to an algo sets the select to that algo. Unticking the accounts leaves the algo selected, which is how you watch an algo without trading it. Clearing to None leaves the accounts alone.
3. **DEFAULTS (all charts)** — one-click trading, default quantity, stop-loss ticks, take-profit ticks, captioned "These apply to every chart."

**Deletions:** `#tbTrade` and its menu (`fillMenu`, `acctRow`, `numPref`, `updateTradeButton` and the dot). The desk's state moves to the bottom status bar as a dot plus text: "Desk: connected · chart trading on · max 10/order, 20/position", "Desk unreachable — …", or "Chart trading is off on the desk" with the existing link.

- [ ] Tests first: `tradeMode` with no accounts; `loadedTrade` dropping LIVE and reporting it; instrument change clearing accounts; the algo↔accounts two-way binding; an unlisted account failing closed. Then implement, browser-check on the fake desk, and commit.

### Task 2: The PAPER account (MONEY-ADJACENT)

**Files:** `homebase/charts/paperbook.py` (new), `homebase/charts/server.py` (routes and wiring), `homebase/static/charts/paperclient.js`, `trade.js`, `tradeui.js`, `tradelines.js`.

**Backend:**
- `PAPER` is a virtual account the page sees alongside the desk's: `{id: 'paper', label: 'PAPER', env: 'paper', tradable: true, balance: <its running equity>}`.
- `POST /api/paper/order|modify|cancel|flatten` mirror the desk's `/api/desk/*` request shapes so the page's send path is unchanged apart from where it points.
- Fills use the backtester's law against the live tick stream the service already has: a stop fills on touch and pays the gap plus slippage, a limit needs a 1-tick penetration, a market fills at the next print, $4 per round turn per contract, `tick_cmp` epsilon. Cite the `homebase/backtest/engine.py` lines in comments.
- State persists to `.state/charts/paper/book.jsonl` and survives a restart. `GET /api/paper/book` returns positions, working orders and fills so the page can draw them like any account's.
- It respects the same caps as the desk: 10 per order, 20 per position.

**Page:** PAPER appears in the ACCOUNTS list and behaves like any other account — Buy/Sell block, order panel, chart-menu items, draggable lines. Its lines and markers carry a PAPER tag and the paper colour. An algo assigned to PAPER forward-tests through the existing runner and keeps its current look.

- [ ] Tests first: each fill rule against a fixture tick stream; parity with `run_session` on the same prints; the caps; restart persistence; the no-broker-import assertion; and that a paper order never produces a desk call. Then implement and commit.

### Task 3: Layout tabs (parallel)

**Files:** `homebase/static/charts/layouts.js` (new, pure) and the tab bar in `app.js`, `charts.html` (delete `#tbLayout` and `#tbSave`), `charts.css`; `homebase/charts/server.py` for `DELETE /api/layouts/{name}` and a stored tab order.

- A tab strip under the toolbar. Each tab is a saved layout: its name, and a dot when it has unsaved changes. A `+` adds one from the current charts. Clicking switches, which saves the current layout first if it is named. Right-click gives Rename, Duplicate, Close. Middle-click closes. Drag reorders.
- The last open tab is remembered per viewer in localStorage, inside try/catch.
- Switching a tab goes through the same load path as today, so `loadedTrade` still drops LIVE accounts.
- [ ] Tests for the pure helpers: tab list ordering, the dirty flag, rename collisions, and closing the active tab. Then implement and commit.

### Task 4: App Settings, with the market-data account (parallel)

**Files:** `homebase/charts/settings_store.py` (new), `homebase/charts/server.py`, `homebase/charts/tickfeed.py` (re-login), `homebase/static/charts/appsettings.js` (new), `app.js`, `charts.html`, `charts.css`.

- A toolbar **Settings** entry (a distinct gear from the chart's) opens an app-wide dialog, structured so more settings can be added later. Sections for this task:
  - **MARKET DATA** — "Fill charts from": a radio per login, `Live 1552885` and `Apex …047`, with the current one marked. A note reads "Only the live login carries Level 2 (depth, DOM ladder, heatmap)." Changing it reconnects the market-data feed, which blanks charts for a few seconds.
  - **APPEARANCE** — the existing light/dark toggle, moved here (the toolbar button stays as a shortcut).
- `GET /api/settings` and `PUT /api/settings` persist to `.state/charts/settings.json`. The env var `HOMEBASE_CHARTS_MD` becomes the default when the file has no choice, so today's behaviour is unchanged until the user picks.
- **Applying the md change:** the feed closes its socket and reconnects under the chosen login. Depth re-subscribes on reconnect, which it already does. If the new login fails, it falls back to the previous one, keeps the old setting and reports the error in the dialog and in `/api/status`.
- **Refused** inside 09:20-09:35 ET on a weekday, or while the desk reports its bot placing: "Not while the 9:30 bot is working — try after 09:35."
- [ ] Tests: the store's round trip and its env-var default; the refusal windows; a failed re-login falling back and keeping the old setting; depth re-subscribing after the switch. Then implement and commit.
