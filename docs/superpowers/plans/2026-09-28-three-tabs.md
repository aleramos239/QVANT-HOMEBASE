# Three tabs: Desk / Charts / Backtest. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-28-three-tabs-design.md` (approved). Read it first —
it has the exact guard list, the `trade.js` split rationale, and the storage-namespace split.

**Tech stack:** plain-JS IIFEs, Node 26 (`node --test tests/js/*.test.mjs`); FastAPI
(`.venv/bin/python -m pytest -q`); Swift/Cocoa/WebKit for the Mac viewer (`swiftc`, no other
toolchain).

## Global constraints

- No trading module (`deskclient.js`, `paperclient.js`, `tradeui.js`, `tradelines.js`,
  `orderpanel.js`, `dom.js`, `domui.js`, `trade.js`) loads on `backtest.html`; verified by an
  automated test, not by eye.
- Every `app.js`/`cell.js`/`replayui.js` call site that reaches into a module which now might not
  be loaded gets a presence guard, not a rewrite of the surrounding function — minimise the diff
  in these shared, previously-reviewed files (GOTCHAS: "money paths fail closed").
- Browser checks run headless against the worktree's own dev servers
  (`tools.fake_desk --port 8880`, `homebase.charts --replay ... --port 8881 --fake-desk 8880`),
  never the live desk (:8850) or live charts (:8852), and never through the app's own Browser
  pane.
- Lucide icons only. No native dialogs. Asset changes need a `?v=` bump — bump it once, at the
  end of Task 2, not per file.
- Tests never open broker connections or write `~/futures_ticks` / `~/futures_depth`.

---

### Task 1: `tradepure.js` — extract the genuinely pure helpers

**Files:** create `homebase/static/charts/tradepure.js`; modify `homebase/static/charts/trade.js`
(require it internally, keep re-exporting the same five names unchanged); create
`tests/js/tradepure.test.mjs`.

- [ ] Move `PREFS_KEY`, `parsePrefs`, `prefsText`, `bracket` (+ its private `roundTick` helper),
      `money`, `usd` (+ their private `sign`/`MINUS`) into `tradepure.js`, `window.HBTradePure`,
      requiring `HBCatalog` (for `bracket`'s tick rounding) and `HBPosition` (for `fmtUsd`)
      exactly like `trade.js` does today. No behaviour change — same inputs, same outputs.
- [ ] `trade.js`: `const TP = need('HBTradePure', './tradepure.js');` near its other `need(...)`
      calls; delete the moved implementations; its `api` object still exports
      `{ PREFS_KEY: TP.PREFS_KEY, parsePrefs: TP.parsePrefs, prefsText: TP.prefsText,
      bracket: TP.bracket, money: TP.money, usd: TP.usd, ...everything else unchanged }`.
- [ ] `tests/js/tradepure.test.mjs`: port the existing `parsePrefs`/`bracket`/`money`/`usd` cases
      out of `tests/js/trade.test.mjs` (keep the originals there too — `trade.js` must still pass
      them through its own re-exports; this is a regression check that the delegation is
      transparent, not a move of the test file).
- [ ] `node --test tests/js/trade.test.mjs tests/js/tradepure.test.mjs` green.
- [ ] Commit: `refactor(charts): extract trade.js's pure prefs/bracket/money helpers into tradepure.js`.

### Task 2: guard the shared chart-shell's trade/tester/replay call sites

**Files:** modify `homebase/static/charts/app.js`, `cell.js`, `replayui.js`,
`settings-dialog.js`.

- [ ] `app.js`: apply every guard listed in spec §3a — `readLayout` (fallback `{accounts:[]}`/
      `null`/`[]` when `T` is absent), `dropLiveAccounts`/`deskStrategies` (already safe, verify
      only), `applyTemplateTrade`/`restoreTemplateTrade`/`migrateTickedOnce` (unreachable once
      the settings-dialog bundle and the `if (window.HBDeskClient)` call site are guarded —
      verify, don't restructure), `hostFor`'s `onReplayGuard`/`onSymbolChange`, `buildGrid`
      (`window.HBReplayUI?.cellDestroyed`, `hidden = T ? T.hiddenCellsLoaded(...) : []`,
      `window.HBTradeUI?.gridRebuilt`), `select`/`onLoaded` (`window.HBOrderPanel?.setRoot`,
      `window.HBTradeUI?.paintDeskStatus`), `onRefused` (`window.HBTradeUI?.setCellAlgo`), the
      `chartSettings()` dialog-host bundle (one `...(window.HBTradeUI ? {...} : {})` spread), the
      mount sequence (`HBTradeLines`/`HBReplayUI`/`HBTesterLayer`/`HBTesterUI`/`HBTradeUI`
      overlay pushes and `.mount()` calls each behind `if (window.HB____)`, `HBPanelShell.mount`
      behind `if (window.HBOrderPanel && window.HBDomUI && window.HBPanelShell)`,
      `migrateTickedOnce()`'s call site behind `if (window.HBDeskClient)`).
- [ ] `cell.js`: `window.HBTrade ? window.HBTrade.symbolChangeTrade(this.cfg, patch) : null`.
- [ ] `replayui.js`: `const Tr = window.HBTrade || window.HBTradePure;` wherever it currently
      reads `window.HBTrade` for `parsePrefs`/`bracket`; `window.HBTradeUI?.replayEnded(...)` /
      `window.HBTradeUI?.replayDestroyed(...)` at its two call sites.
- [ ] `tester.js`/`testerui.js`: same `window.HBTrade || window.HBTradePure` swap for their `Tr`.
- [ ] `settings-dialog.js`: filter the `'trading'` tab out of the sidebar when
      `!host.accountRows` (the three `TABS` usages inside `mount()` read a local `tabs` instead).
- [ ] Run the FULL existing Charts test suite (`node --test tests/js/*.test.mjs`) — this task
      touches widely-depended-on files; nothing besides the guarded lines should change
      behaviour, so no existing test should need editing. If one does, that is a signal to
      re-check the guard, not the test.
- [ ] Commit: `refactor(charts): guard app.js/cell.js/replayui.js's trade+tester+replay calls so each module works when the others aren't loaded`.

### Task 3: `backtest.html` + the `/backtest` route + layout-namespace split

**Files:** create `homebase/static/backtest.html`; modify `homebase/charts/server.py`
(the `/backtest` route, the parametrized layout-route registration called twice, `Conn.page`,
`fan_count` filtering); modify `homebase/static/charts/app.js` (the `HB_PAGE`-driven layout
base-path + localStorage-key switch — one `LAYOUTS_BASE`/`LAST_KEY` near the top, per spec §3b).

- [ ] `backtest.html`: copy `charts.html`, drop `#tbReplay`... no — keep `#tbReplay` (Backtest
      HAS Bar Replay) but drop `#tbOrder`/`#tbDom`; set `<title>Backtest · Homebase</title>`;
      `<script>window.HB_PAGE = 'backtest';</script>` before the other scripts; the script-tag
      list exactly as spec §3 "Modules loaded on backtest.html" (note: NOT
      `deskclient.js`/`paperclient.js`/`dom.js`/`domui.js`/`tradeui.js`/`tradelines.js`/
      `orderpanel.js`/`panelshell.js`/`fillquality.js`/`newsui.js`/`news.js`/`l2layer.js`/
      `liquidity.js`/`trade.js`); the same `?v=` as `charts.html` currently carries (bumped once
      at the end of Task 2, per Global Constraints — use that same number here).
- [ ] `server.py`: `@app.get("/backtest")` returns `FileResponse(STATIC / "backtest.html",
      headers={"cache-control": "no-cache"})`, same as `/`.
- [ ] `server.py`: factor the six `/api/layouts*`/`/api/layout-order` handlers into one function
      taking `(path_for_layouts, path_for_order)`, register it once for `/api/layouts*` with the
      existing paths and once for `/api/bt/layouts*` with new `layouts_backtest.json` /
      `layout_order_backtest.json` in the same state dir.
- [ ] `server.py`: `/ws` reads `page = sock.query_params.get("page", "charts")`, stored as
      `conn.page` on the `Conn`; `fan_count` sends only to `c.page == "backtest"` conns and
      counts only those.
- [ ] `app.js`: `const LAYOUTS_BASE = window.HB_PAGE === 'backtest' ? '/api/bt' : '/api';` used at
      all 6 layout fetch call sites (`/api/layouts...` → `` `${LAYOUTS_BASE}/layouts...` ``);
      `const LAST_KEY = window.HB_PAGE === 'backtest' ? 'hb_backtest_last' : 'hb_charts_last';`
      used at the 2 `localStorage` call sites for the on-screen layout cache. `hb_iv_favs`,
      `hb_theme`, `hb_charts_magnet` stay literal (shared, per spec §3b).
- [ ] `backtest.html`'s WS connect passes `?page=backtest` (Charts' own connect call is
      unchanged, defaulting server-side to `"charts"`).
- [ ] `tests/js/backtest-isolation.test.mjs` per spec §3a: script-tag ban list, guard-presence
      check on the identified call sites, and the `vm`-sandbox smoke run of
      `tester.js`/`testerui.js`/`replayui.js` with `window.HBTrade` undefined.
- [ ] `tests/test_charts_layouts.py` (new, or extend the existing layouts test file if one
      exists — check `tests/` first): the `/api/bt/layouts*` routes round-trip independently of
      `/api/layouts*` (writing one namespace never touches the other's file on disk).
- [ ] `tests/test_claude_mcp.py` / a charts-server test: `show_on_chart` posts a `tester_show`
      that reaches a `page=backtest` conn and not a plain (`charts`) conn; `fan_count`'s returned
      count matches only backtest conns.
- [ ] `node --test tests/js/*.test.mjs` and `.venv/bin/python -m pytest -q` both green.
- [ ] Commit: `feat(charts): the Backtest page — chart shell + Strategy Tester + Bar Replay, no trading modules, its own layout namespace`.

### Task 4: remove the Tester/Replay entry points from `charts.html`

**Files:** modify `homebase/static/charts.html` only (Task 2 already made `app.js` safe for
their absence).

- [ ] Delete `#tbReplay` from the toolbar markup.
- [ ] Delete the `tester.js`/`testerui.js`/`testerlayer.js`/`replay.js`/`replayui.js` script
      tags.
- [ ] Bump `?v=` on every remaining script tag in BOTH `charts.html` and `backtest.html` (one
      shared number — this is the `?v=` bump Global Constraints deferred from Task 3).
- [ ] `node --test tests/js/*.test.mjs` green (in particular: nothing in the surviving Charts
      test suite references the removed tabs/buttons as still-present).
- [ ] Headless-Chrome check against the worktree's own dev servers (`fake_desk` on 8880,
      `homebase.charts --replay ... --port 8881 --fake-desk 8880`): Charts loads, no console
      error, no Strategy Tester tab, no Replay button; Backtest loads, Strategy Tester open by
      default and bigger, Replay button present, no Order/DOM buttons, no trading globals
      (`window.HBTrade`, `window.HBTradeUI`, `window.HBDeskClient`, `window.HBOrderPanel`,
      `window.HBDomUI` all `undefined` — check from the console). Screenshot both.
- [ ] Commit: `feat(charts): Charts is live-only — Strategy Tester and Bar Replay moved to Backtest`.

### Task 5: the Mac app tabs

**Files:** modify `deploy/macapp/main.swift`, `deploy/macapp/build_app.sh`.

- [ ] `build_app.sh`: accept `$1` as the output `.app` path, default
      `$HOME/Applications/Homebase.app`.
- [ ] `main.swift` per spec §1: the `NSToolbar` segmented switcher + ⌘1/⌘2/⌘3 menu items; three
      lazily-created `WKWebView`s (own `WKProcessPool` each) shown/hidden on the same content
      view; env-overridable URLs; per-tab retry-on-fail; `UserDefaults["HomebaseLastTab"]`
      remembered and restored; the port/path-based link-interception in the navigation delegate.
- [ ] Test build: `deploy/macapp/build_app.sh /tmp/.../HomebaseTabsTest.app` (scratch path, never
      `~/Applications`) — `swiftc` succeeds, the bundle is produced. Do not launch it (Global
      Constraints: never launch a built binary that could reach a live service; this one points
      at :8850/:8852 by default, so it must not run automatically — launching for a look is the
      account holder's own step).
- [ ] Commit: `feat(macapp): Desk/Charts/Backtest tab switcher, per-tab WKWebView + process pool, port-based link interception`.

### Task 6: merge `main`, final checks

- [ ] `git fetch`/`git log main` — check whether `feat/data-export` landed on `main` since this
      branch started.
- [ ] `git merge main` into `feat/three-tabs`. Expected touch points if `feat/data-export`
      landed: `settings-dialog.js`'s `TABS` array (its new Data tab entry vs this branch's
      Trading-tab filter — keep both), `app.js`, `charts.html`, `charts.css` (its Data tab wiring
      vs this branch's guard/script-tag changes — keep both; `backtest.html` did not exist before
      this branch, so it needs the Data tab reviewed for whether it belongs there too — money-
      adjacent? if not, add its script tag/markup to `backtest.html` in the same merge commit;
      if it touches desk/paper data, treat it like the other excluded modules instead).
- [ ] Re-run both test suites after the merge.
- [ ] Do not bump `?v=` again, restart any service, run `deploy/install.sh`, or rebuild into
      `~/Applications` — report what the release step still needs instead (see hand-off report).
