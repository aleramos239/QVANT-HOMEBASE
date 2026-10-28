# Prompt: one design system, a polished app

Paste everything below the line into a fresh Claude Code chat opened in `~/ramos-quant-homebase`.

---

Act like the head of design and the lead front-end engineer at a top trading-software company (think TradingView, Linear, Bloomberg's
new terminal, Apple's Stocks). Take Homebase from "works, built by many hands" to an app that looks and feels like it cost a million
dollars: **one consistent, minimal design** across every screen, easier to use, clearer to read. That covers type, colour, spacing,
tables, charts, text, explanations, layout, and what is shown where. Product behaviour stays the same: same data, same orders, same
checks. Only how it looks, reads and is organized changes.

The surfaces: the **Mac app** (`deploy/macapp/main_apple.swift`, Homebase.app) with **Desk** (`index.html` + `static/desk/*.js`),
**Charts** (`charts.html` + `static/charts/`) and **Lab** (`backtest.html` + `static/charts/lab*.js`), and the **server app**
(HomebaseVPS.app, Desk only). The skin lives in `homebase/static/apple/` (`manifest.json`, `system.css`, `symbols.css`, `desk|charts|lab`
css + js), loaded in the app and, through `apple/web.js`, in a browser too.

## Why it doesn't feel like one app today (measured on `claude/ux-redesign`)

| What | Count |
|---|---|
| Different hex colours in css/html/js | ~356 |
| CSS variables | ~483, under 3+ naming schemes (`--a-*`, `--hb-*`, `--font-*`, shadcn) |
| Font sizes | 45 |
| Corner radii | 30 |
| Style sheets layered on each other | `apple.css`, `apple/*.css`, `shadcn.css`, `hb.css`, `charts/charts.css`, `charts/apple-charts.css`, `charts/lab.css`, ... |

The goal is one small token set that every screen uses, and nothing hard-coded.

## Read first

1. `CLAUDE.md` and its memory index. Before each screen run `~/.claude/vault-recall/recall "<screen> design"`.
2. Vault notes (`~/Obsidian/Vault/30-Projects/Onyx-Trading/`):
   - `homebase-one-design-new-skin-everywhere`: how the skin loads; bump `manifest.json` version after any skin change; judge the look
     in the app, not a cached browser.
   - `feedback-chart-ui-tradingview-look`: the owner's taste. Charts follow TradingView conventions. Apple glass and springs only on
     chrome (menus, dialogs, toasts, floating panels), never on data.
   - The 10-09 silver-and-white decision: no cream or brown; accent graphite `#48484A` on light, silver `#D1D1D6` on dark. Orange
     means warning, red means armed/Kill/loss, green means profit, and the gold `Au` badge stays.
   - `homebase-app-ui-notes-hub`, and findings `2026-10-27-desk-page-script-lives-in-static-desk` (every `desk/*.js` edit bumps `?v=`
     and `DESK_PINS`) and `2026-10-27-hidden-browser-pane-freezes-css-transitions`.
3. `.worktrees/MORNING-REPORT-2026-10-27.md` §3-§6: the redesign's safety UI. Keep all of it:
   - the "This Mac" / "Server · Chicago" chip;
   - the "Chart trading ON · N live accounts" chip;
   - LIVE / DEMO / PAPER tags;
   - confirms that name the machine;
   - old → new before Save;
   - "Changes (7 days)" with Put back.

   You restyle these; you never remove or weaken them.
4. **Build on `claude/ux-redesign`.** Load the skills: `impeccable` first, then `design-taste-frontend`, `emil-design-eng`,
   `apple-design`, `dataviz` (for every chart and table), and `web-design-guidelines` for the audit.

## Rules you must not break

- **No behaviour change.** Same routes, same numbers, same orders, same confirms. If a better layout needs a behaviour change, propose
  it separately.
- **Safety stays loud.** LIVE, armed, Kill, chart trading ON, and the machine name stay the most visible things on any screen they're
  on. Minimal never means hiding risk.
- **Numbers are sacred**: tabular figures, right-aligned in tables, the same decimals for the same kind of value, $ with sign and
  thousands separator, red/green only for gain/loss (plus a +/− sign, so colour-blind reading works).
- Data surfaces (chart canvas, axes, price/position lines, DOM cells, legend values, table cells) stay solid, crisp and instant. Glass,
  blur and springs only on chrome. Respect `prefers-reduced-motion`, `prefers-reduced-transparency` and `prefers-contrast`.
- Light and dark both first-class. WCAG AA contrast on every text, including the silver-on-dark accent.
- Lucide icons only. No TradingView or other brand assets. Fonts: system first (`-apple-system` / SF Pro, SF Mono for numbers). A new
  font only if it clearly wins and ships locally, never from a CDN.
- The server follows main (vpssync). Work on branches. Merge only on the owner's word, after 16:15 ET, with every account flat. Skin
  and static files can go out without a restart; anything server-side follows the restart gate.

## Phase 0: audit (change nothing)

- **Screenshot every screen and state** in the Mac app (computer-use `app_screenshot` on `com.ramosquant.homebase.viewer`) and on a
  replay / fake desk in the browser, light and dark, at 1440 and 1024 wide. Include empty, loading, error, offline, "market closed",
  armed, chart trading ON, a long list, and a strategy with a very long name.
- **Inventory**: every colour, size, radius, shadow, spacing value, font and z-index in use, and which file sets it. Every button, input,
  toggle, tab, chip, badge, table, card, dialog, menu, toast and tooltip variant (expect several look-alikes of each).
- **Text**: every label, button text, empty state, error, confirm and tooltip. Mark jargon, inconsistent names for the same thing
  ("test months" / "unseen days" / "OOS"), shouting, and dev words ("payload", "id", "null", raw exceptions).
- **Where things are**: for each screen, what the owner looks at first, what he does most, and what's buried or misplaced.
- Hand back: a ranked list of the 30 worst problems, each with a screenshot, plus the inventory counts.

## Phase 1: the design system (one file, then everything uses it)

Write `homebase/static/apple/tokens.css` (or fold into `system.css`) as the **only** source of truth, with light and dark values:

| Token group | Target |
|---|---|
| Colour | ~12 neutrals (surface, raised, sunken, border, text 1/2/3), 1 accent, and the semantic colours: profit, loss, warning, live, demo, paper, info. Chart series colours from `dataviz`, checked for colour-blind safety |
| Type | 6-7 sizes on one scale (e.g. 11/12/13/15/17/22/28), 3 weights, line heights, SF Mono tabular for numbers, letter-spacing per size |
| Space | a 4-px scale (4/8/12/16/24/32/48) |
| Radius | 3 (small 4, medium 8, large 12) |
| Elevation | 3 shadows, plus glass for chrome |
| Motion | 2 durations, 1 spring, 1 ease, plus reduced-motion variants |
| Density | a compact mode for trading screens and a comfortable one for reading screens |

Then **components**, each with every state (default, hover, pressed, focus ring, disabled, loading, error) and a short usage line:
button (primary, secondary, quiet, danger, hold-to-confirm), input, number input with unit, select, toggle, segmented control, tabs,
chip/badge (LIVE/DEMO/PAPER, ON/OFF, machine), table, stat tile, card, dialog/confirm (old → new), menu, toast, tooltip, empty state,
skeleton loader, inline help ("?").

Map every old variable (`--a-*`, `--hb-*`, shadcn) to a token, then remove the old ones. Build a **living style page**
(`static/styleguide.html`) that shows every token and component in light and dark. Ship this phase alone first, with zero visual change
beyond rounding the near-duplicates. Prove it with before/after screenshots.

## Phase 2: screens, one at a time

For each screen: what's the one thing the owner needs to see in two seconds? Put it top-left and large. Put the most-used action
where the hand is. Everything else is one click away or gone.

- **Desk (Mac and server)**
  - The account strip: LIVE/DEMO/PAPER, P&L, room to the daily limit and drawdown, armed state.
  - Today: strategies with state, position, last signal and P&L.
  - Strategy card and settings, groups and the account cycle, Changes, the journal, accounts and logins, the setup wizard.
  - The server app must be unmistakably the server, yet look like the same product.
- **Charts**: toolbar, drawing rail, legend, order panel, position and order lines, price ladder, positions/orders/fills panel, settings,
  replay bar, indicator picker and settings dialog. TradingView-plain on the data, Apple polish on the chrome.
- **Lab**: the path idea → code check → in-sample table → pick → test months → verdict as one clear stepper. The in-sample table and
  heat map read at a glance (box numbers, diverging colour around $0, the picked box obvious). The verdict is the six lines in plain
  words with ✓/✗, then the result. Run lists, run detail, equity curves, per-year tables, Monte Carlo, the strategy list and drafts.
- **App shell**: tab bar, the machine chip, gear and Settings, the connection state, the command palette (Cmd-K: jump to any strategy,
  account, symbol, screen or setting), and keyboard shortcuts shown in menus and tooltips.

## Phase 3: charts and tables everywhere (not the trading chart)

Use `dataviz` for every equity curve, drawdown, P&L calendar, per-year bar, heat map, histogram and Monte Carlo fan. One chart style:
the same axes, gridlines, tooltips, crosshair, colours, number format, and empty and loading states. Draw drawdown under the equity
curve. Mark the in-sample/test-month boundary on every 3:1 curve. Tables follow one spec: sticky header, right-aligned numbers, zebra or
hairlines (pick one), sortable where useful, a totals row styled apart, compact density on trading screens, and no horizontal scroll at
1280 wide.

## Phase 4: words and explanations

- One **glossary**, one name per thing, used everywhere: in-sample, test months, box, pick, try, real/luck/fake, room to limit, armed,
  shadow, and so on. Retired names go.
- Plain, short, calm text (the owner's rule: the answer first, no jargon). Buttons are verbs ("Run the test months for #12"). Errors
  say what happened and what to do, never a raw exception. Empty states say what goes here and the one action to fill it.
- Inline help: a "?" next to every number or rule the owner might not read at a glance (Sharpe = traded days only, t-stat, the luck bar,
  drawdown counting open losses), as a short popover. Not a manual.
- Number and time formats: ET everywhere, labelled once. Dates written the same way everywhere. $, R, ticks and points always labelled.

## Phase 5: finish

- Accessibility: keyboard reach for everything, visible focus, labels on icon buttons, contrast AA, and hit targets of 28 px or more on
  the chart and 32 px or more elsewhere.
- Performance: no layout jank, skeletons instead of blank panels, and 60 fps on scroll and drag. Don't add heavy libraries.
- Dead CSS/JS removed once nothing references it, proven by a selector/reference search and screenshots.
- The app icon, the window title, the About box and the first-run screen: same quality bar.

## How to work

1. Phase 0 report first. The owner picks the direction: show 2 visual directions for the Desk "Today" screen as static mockups (same
   data, light and dark). He picks one. Then the system.
2. One branch and worktree per phase or screen group. Two never touch the same files. Bump `apple/manifest.json` version on every skin
   change. Bump `?v=` and `DESK_PINS` on every `desk/*.js` change.
3. Every change: before/after screenshots in the app, light and dark, then the JS (`*.test.mjs`), Python and Desk-page suites.
   Take two screenshots and check state in JS, because the hidden pane freezes transitions.
4. Talk to the owner in plain short words: the answer first, a small table, no jargon. Show, don't describe.

## What to hand back

1. The audit: the 30 worst problems with screenshots, and the inventory counts (before → after: colours, variables, font sizes, radii).
2. `tokens.css`, the component set and the live style page.
3. Every screen before → after, light and dark.
4. The glossary and the text changes (old → new).
5. The information map: for each screen, what's shown, in what order, and why.
6. Branches, tested, each with a one-line merge plan.
7. What still needs the owner's decision, numbered, so he can answer by number.
