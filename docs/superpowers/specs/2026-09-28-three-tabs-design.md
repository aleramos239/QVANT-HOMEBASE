# Homebase — three tabs: Desk, Charts, Backtest

Date: 2026-09-28. Status: approved (account holder). The app becomes three tabs in the Mac
viewer: **Desk** (unchanged), **Charts** (live trading only, Tester and Bar Replay removed),
and a new **Backtest** tab (chart shell + Strategy Tester + Bar Replay/PracticeSim, no trading
code at all).

## 1. The window (`deploy/macapp/main.swift`)

- An `NSToolbar` segmented control (Desk · Charts · Backtest) in the title bar, plus a View
  menu with ⌘1/⌘2/⌘3, both driving the same `switchTab(_:)`.
- Three `WKWebView`s, one per tab, each built lazily the first time its tab is opened and kept
  alive after that (added to the same content view, `isHidden` toggled — never destroyed, so a
  heavy Backtest run keeps running while Charts is on screen). Each gets its own
  `WKProcessPool()` in its `WKWebViewConfiguration`, so each tab gets its own WebContent
  process where WebKit allows it — a stuck Backtest tab cannot stall the live chart's renderer.
- URLs, overridable via environment variables (falling back to the current defaults):
  `HOMEBASE_DESK_URL` → `http://localhost:8850`, `HOMEBASE_CHARTS_URL` → `http://localhost:8852/`,
  `HOMEBASE_BACKTEST_URL` → `http://localhost:8852/backtest`.
- **Link interception:** the navigation delegate reads the target URL's port and path on every
  top-level navigation. Port 8850 → Desk; port 8852 with a path starting `/backtest` → Backtest;
  port 8852 otherwise → Charts. If that resolves to a DIFFERENT tab than the one navigating, the
  delegate cancels the navigation and calls `switchTab` instead; if it resolves to the SAME tab,
  it allows the navigation through unchanged. This covers the desk's existing `#chartsLink` and
  the chart pages' existing `#tbDesk` link without any change to those pages. A plain browser
  never sees this delegate, so the same links stay plain links there.
- **Remembered tab:** `UserDefaults` key `HomebaseLastTab` (an Int, 0/1/2). On launch the
  remembered tab is created and shown first (not always Desk); the other two are created on
  first visit.
- **Retry-when-down:** per-tab, not global — each `WKWebView` gets its own delegate callbacks
  keyed by which webview failed, retrying only that tab's URL after 2s, exactly like today's
  single-webview retry.
- `build_app.sh` takes an optional first argument: the output `.app` path (defaults to
  `$HOME/Applications/Homebase.app` — unchanged for the real release build). A test build passes
  a scratch path so it never touches the installed app.

## 2. Charts tab — live only

Remove from `homebase/static/charts.html`: the `#tbReplay` toolbar button, and the script tags
for `tester.js`, `testerui.js`, `testerlayer.js`, `replay.js`, `replayui.js`. The bottom drawer
keeps Positions/Orders/Fills/Accounts/Fill quality/News (unchanged — those come from
`tradeui.js`/`fillquality.js`/`newsui.js`, none of which move). Buy/Sell, the order panel, DOM,
algos, Level 2, drawings, indicators and settings all stay exactly as they are.

**The catch:** `app.js` and `cell.js` are the shared chart shell — the SAME files load on both
Charts and Backtest — and today they call straight into `window.HBReplayUI` / `window.HBTesterUI`
/ `window.HBTrade` / `window.HBTradeUI` / `window.HBOrderPanel` / `window.HBTradeLines` /
`window.HBPanelShell` without checking they exist, in about a dozen places (layout load, grid
rebuild, chart selection, the settings-dialog host object, symbol-change, the mount sequence).
Since Charts stops loading `tester*.js`/`replay*.js`, and Backtest stops loading `trade.js` and
its trading siblings, both directions need the caller to check first. The fix is optional-
chaining / presence guards at each of those call sites — behaviour is unchanged when the module
IS loaded (every existing caller, on whichever page still has it), and the call becomes a safe
no-op when it is not (the corresponding UI/feature simply isn't there on that page). `trade.js`'s
own `replayGuard`/`replayHalt`/`replayConfirm` stay exactly as they are, unused but present, on
Charts (Bar Replay just never sets `cell.replay` there any more).

## 3. Backtest tab — new page, served by the charts service

New `homebase/static/backtest.html`, served at `GET /backtest` by `homebase/charts/server.py`
(same `FileResponse(..., headers={"cache-control": "no-cache"})` pattern as `/`). It is the same
chart shell as Charts — toolbar, drawing rail, indicators dialog, chart-layout picker, the
Settings dialog, the same look — **plus** the Strategy Tester as the bottom panel's main tab
(open and bigger by default), **plus** Bar Replay with PracticeSim.

**Scope decision (narrower than "everything Charts has except trading"):** Backtest loads
exactly the chart shell explicitly named above, the Tester, and Bar Replay. It does **not** load
News, the Level-2 ladder/liquidity heatmap overlays, or the DOM — those are live-market-
microstructure features tied to the desk's depth entitlement, not named in the brief's list of
what Backtest carries over, and cutting them keeps the isolation surface (next section) much
smaller and easier to verify exhaustively. If the account holder wants News or L2 visuals on
Backtest later, that is a small additive follow-up, not a revision of this cut.

**Modules loaded on `backtest.html`:** `nobacknav.js`, `vendor/lightweight-charts`, `icons.js`,
`spring.js`, `catalog.js`, `primitives.js`, `drawstyle.js`, `drawings.js`, `position.js`,
`settings.js`, `events.js`, `scrollback.js`, `cell.js`, `settings-dialog.js`,
`indicator-settings-dialog.js`, `chartmenu.js`, **`tradepure.js`** (new, see below), `panel.js`,
`tester.js`, `testerui.js`, `testerlayer.js`, `replay.js`, `replayui.js`, `panellayout.js`,
`layouts.js`, `presets.js`, `app.js`.

**Never loaded on `backtest.html`** (money paths): `deskclient.js`, `paperclient.js`, `dom.js`,
`domui.js`, `tradeui.js`, `tradelines.js`, `orderpanel.js`, `panelshell.js` (exists only to host
the Order/DOM floating panels — nothing to shell once those two are gone), `fillquality.js`,
`newsui.js`, `news.js`, `l2layer.js`, `liquidity.js`, and **`trade.js` itself** (see below).
`#tbOrder` / `#tbDom` toolbar buttons are not in `backtest.html`'s markup at all.

### 3a. The `trade.js` split (opus-reviewed)

`trade.js`'s own docstring calls it "the pure half" of trading, but it is not pure enough to
load on a page with no trading globals: its API includes order-body construction, live-account
gating and desk-state reads (`deskGate`, `armedMode`, `liveSendIds`…) — exactly "the parts that
can talk to the desk's order paths" the brief excludes. But three call sites elsewhere need
functions that genuinely ARE pure and have nothing to do with sending:

- `replayui.js` needs `PREFS_KEY` / `parsePrefs` (SL/TP prefs parsing) and `bracket` (SL/TP-tick
  math) for PracticeSim's own bracket sizing — the same prefs a real Buy/Sell block reads, by
  design (one SL/TP-ticks setting, not two).
- `tester.js` / `testerui.js` need `money` / `usd` (the `$1,234` / signed `+$12`/`−$12`
  formatters) for the report's tiles, tables and heat-map.

**Fix:** a new `homebase/static/charts/tradepure.js` (`window.HBTradePure`, Node-tested, no
browser globals at load time — same shape as `catalog.js`/`position.js`) holds exactly these five
names: `PREFS_KEY`, `parsePrefs`, `prefsText`, `bracket`, `money`, `usd` (`money`/`usd` need
`position.js`'s `fmtUsd`, already a standalone pure module). `trade.js` requires
`tradepure.js` internally and re-exports the same five names on `window.HBTrade` unchanged — so
`trade.js`'s public API and every existing Charts-page caller (`tradeui.js`, `tradelines.js`,
`orderpanel.js`) are untouched. `replayui.js`/`tester.js`/`testerui.js` change one line each:
`const Tr = window.HBTrade || window.HBTradePure;` (was `window.HBTrade` / a `require`d
`trade.js`) — on Charts this still resolves to `HBTrade` (unchanged behaviour); on Backtest,
`HBTrade` doesn't exist and it resolves to the new pure module instead.

`replayui.js` also has two direct calls into `window.HBTradeUI` (`replayEnded`/`replayDestroyed`)
that hand back control of the REAL Buy/Sell block once a replay session ends — meaningless when
there is no real Buy/Sell block. These become `window.HBTradeUI?.replayEnded(...)` /
`window.HBTradeUI?.replayDestroyed(...)` (no other change — on Charts, `HBTradeUI` doesn't load
Bar Replay any more at all per §2, but the guard costs nothing and is correct either way).

`cell.js` has one direct call, `window.HBTrade.symbolChangeTrade(this.cfg, patch)`, guarded to
`window.HBTrade ? window.HBTrade.symbolChangeTrade(this.cfg, patch) : null` — on a chart with no
trading concept, a symbol change never has a Trading switch to turn off.

`settings-dialog.js` already treats every trade-related host callback as optional
(`host.accountRows`, `host.tradeBits`, `host.applyTrade`, `host.algoChoices`, `host.restoreTrade`,
`host.onTradeChange` are all checked before use — this file was written expecting a host that
might not offer them). Two additions in that spirit: the 'trading' tab entry is filtered out of
the sidebar when `!host.accountRows`, and `app.js`'s `chartSettings()` only spreads the whole
`tradeBits`/`applyTrade`/`algoChoices`/`setAlgo`/`accountRows`/`createPaperAccount`/
`toggleAccount`/`armPending`/`tradeWhy`/`prefs`/`setPrefs`/`onTradeChange` bundle into the dialog
host object `if (window.HBTradeUI)` — one guard covers all eleven, instead of eleven.

`app.js`'s other trade-shaped call sites (`readLayout`, `buildGrid`, `select`, the `hostFor` cell
host, the mount sequence's overlay/panel wiring, `onRefused`, `onLoaded`) get the same treatment:
optional-chaining or an `if (window.HBTradeUI)`/`if (window.HBReplayUI)`/`if (window.HBTesterUI)`
around the specific line, with a same-shape fallback where a return value is consumed downstream
(e.g. `buildGrid`'s `hidden` list defaults to `[]`, so the toast that follows it never fires —
no separate guard needed there). `dropLiveAccounts()` and `migrateTickedOnce()`'s desk-state reads
already return early on a null desk state / missing `HBDeskClient`, so they need no change beyond
their existing call sites (already guarded at line ~2010, or trivially guarded at the one other
call site).

**Test:** `tests/js/backtest-isolation.test.mjs` reads `backtest.html`'s script tags and asserts
none of the banned filenames appear, then reads `app.js`/`cell.js`/`replayui.js` source text and
asserts every one of the identified unguarded call sites now carries a guard (same technique as
`replay.test.mjs`'s existing isolation test, which already greps replay/replayui source for
forbidden desk-sending calls) — plus a Node-`vm` smoke check that `tester.js`/`testerui.js`/
`replayui.js` load and run their pure functions with `window.HBTrade` absent and
`window.HBTradePure` present.

### 3b. Storage split

- **Chart layouts — separate namespace.** Today: server `GET/PUT/DELETE /api/layouts/{name}`,
  `GET/PUT /api/layout-order` (`homebase/charts/server.py`, backed by `<state>/charts/
  layouts.json` + `layout_order.json`), plus the per-viewer "what's on screen right now" cache in
  `localStorage['hb_charts_last']`. Backtest gets its own: routes `/api/bt/layouts/{name}` and
  `/api/bt/layout-order`, backed by `layouts_backtest.json` + `layout_order_backtest.json` in the
  same state dir (the route bodies are factored into one parametrized registration function
  called twice, not duplicated), and `localStorage['hb_backtest_last']`. `app.js` picks the base
  path and the storage key from one flag set by each HTML file before `app.js` loads:
  `window.HB_PAGE = 'backtest'` (absent/`'charts'` on Charts).
- **Drawings — shared per symbol.** Unchanged: `/api/drawings/{root}` already keys purely by
  instrument root, nothing page-specific to split. A trendline drawn on NQ in Backtest shows on
  NQ in Charts and back.
- **Settings, templates, presets, favourites — shared.** Unchanged: `/api/settings`,
  `/api/templates`, `/api/presets/{kind}`, and the favourites/theme/magnet localStorage keys
  (`hb_iv_favs`, `hb_theme`, `hb_charts_magnet`) are viewer-wide today and stay viewer-wide — both
  pages reuse the exact same keys/routes, so sharing is automatic and needs no new code.

### 3c. `show_on_chart` targets Backtest

`POST /api/tester/show` currently fans its message to every open `/ws` connection
(`fan_count` → `fan(msg)` → every `Conn` in `conns`). Pages now announce which page they are on
connect: `/ws?page=backtest` (Backtest) vs `/ws` (Charts, default `'charts'`) — one attribute,
`conn.page`, set once in the `/ws` handler. `fan_count` (the tester-router's `notify` callback,
used ONLY for tester progress/grid/show messages — verified: no other caller) filters to
`c.page == 'backtest'` before sending and counts only those, so `t_show_on_chart`'s "no chart
page is open" refusal is accurate again once Backtest, not Charts, is what must be open. The
general `fan()` used for paper/news/burst messages is untouched (Charts still gets those; the
client-side guards in §2/§3a make an unexpected message on either page a safe no-op regardless).

## 4. Phasing (one commit per task)

1. The Backtest page — `backtest.html`, `tradepure.js`, the `trade.js`/`replayui.js`/`cell.js`
   guards, the `/backtest` route, the layout-namespace split, `show_on_chart` retargeting, the
   isolation test. Usable in a browser on its own before touching Charts.
2. Remove the Tester/Replay entry points from `charts.html`/`app.js` (now that the guards from
   Task 1 make it safe to do so).
3. The Mac app tabs (`main.swift`, `build_app.sh`).

Before declaring done: merge `main` into `feat/three-tabs`; `feat/data-export` (a Data tab in
`settings-dialog.js`/`app.js`/`charts.html`/`charts.css`) may have landed on `main` by then —
resolve keeping both sets of changes (its Data tab is unrelated to the trading-tab guards above,
so it should be a clean merge; if `settings-dialog.js`'s `TABS` array conflicts, keep both the
new Data entry and the Trading-tab filter).

## What ships, what doesn't yet

This spec covers the code. It does not restart the charts service, does not bump any `?v=`, and
does not rebuild `~/Applications/Homebase.app` — release steps are the account holder's call
Reported separately at hand-off.
