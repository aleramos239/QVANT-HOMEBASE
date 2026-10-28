# Prompt: the chart page for manual trading, plus every tool and indicator

Paste everything below the line into a fresh Claude Code chat opened in `~/ramos-quant-homebase`.

---

Act like a senior trading-platform engineer who has built order entry for a futures desk and who trades by hand. Your job is the
Homebase **chart page** (port 8852, `homebase/charts/` + `homebase/static/charts/`). Make manual trading **faster, safer and easier**
for the owner, who trades NQ/ES/YM/RTY/GC/SI on prop accounts (Lucid, Apex) by eye. Then go through **every drawing tool and every
indicator**, one by one, and decide whether each should be kept, changed (more accurate, more adjustable, easier to read) or removed.
Add, remove or change features wherever it helps. Not in scope: the Lab, the Desk and strategies, except where the chart touches them.

## Read first

1. `CLAUDE.md` (house rules) and its memory index. Before each area run `~/.claude/vault-recall/recall "<topic>"`.
2. These vault notes in `~/Obsidian/Vault/30-Projects/Onyx-Trading/`:
   - `chart-tab-manual-trading-review-2026-10-23` (the last review: money risks, gaps, what was fixed)
   - `order-panel-chart-preview-and-auto-breakeven` (the order panel, BE, trailing, partial TP, the server exit runner)
   - `feedback-chart-ui-tradingview-look` (the look the owner wants: TradingView conventions, Apple chrome only where it doesn't touch the data)
   - `feedback-only-real-indicators` (his test for an indicator)
   - `indicator-cleanup-2026-10-22` (open owner decisions B1-B9)
   - `indicator-settings-adjustable-2026-10-22` (what was deferred)
   - `indicator-apps-tape-tv-orderflow-pine-2026-10-21`, `chart-service-restart-gate`, `swing-and-liquidity-definitions`
   - findings: `2026-10-14-chart-flatten-repeat-clicks-reverse-position`,
     `2026-10-19-server-and-mac-charts-fight-for-the-live-md-seat`, `2026-10-21-replay-mode-browser-check-recipe`,
     `2026-10-27-hidden-browser-pane-freezes-css-transitions`, `2026-10-27-mac-chart-md-feed-dropped-five-times-at-the-open-reason-not-logged`.
3. `.worktrees/MORNING-REPORT-2026-10-27.md`, section 3 "Charts". **Build on `claude/ux-redesign`** (it holds the clean-up and the chart
   redesign, not merged yet) and keep `claude/chart-md-login-and-close-log` in mind. Don't redo what they did.
4. The code: `trade.js` / `tradeui.js` / `tradepure.js` / `tradelines.js` / `orderpanel.js` / `position.js` (order entry), `dom.js` /
   `domui.js` (price ladder), `drawings.js` / `drawstyle.js` (tools), `catalog.js` / `flowdefs.js` /
   `indicator-settings-dialog.js` (indicators), `studies*.py` (indicator math), `exitrunner.py`, `homebase/trading.py`,
   `homebase/desk/dayrules.py`, and the prop rule files.

## Rules you must not break

- **The chart sends real orders to LIVE accounts.** Every change to order code is tested on PAPER first: replay mode, then a PAPER
  account after the 18:00 ET open. Never test on a live or funded account. Keep every fix from 10-14 and 10-23: Flatten reads,
  cancels and checks the broker's answer; Reverse carries a stop and reserves its close; Flatten has its own lock.
- A new order path asks before it can send on a LIVE account and names the account and machine. Nothing that sends is on by default.
  Anything that only cancels, flattens or tightens a stop never asks twice.
- **The indicators share their math with the strategy engine** (`studies_ta.py`, the engine's blocks). A math fix that changes a number
  a block reads can change a running Desk strategy. Any such fix: list the Desk strategies that read that block, run the engine-parity
  recipe, and change shared math only on the owner's word. Otherwise give the chart a new option and leave the default alone.
- **One chart holds the live market-data seat.** Don't add a second feed connection, and don't make the Mac and the server chart
  fight for the seat.
- Don't restart the chart service while a position is open or an exit is armed (`chart-service-restart-gate`). The server follows main
  (vpssync): work on branches and merge only on the owner's word, after 16:15 ET, with every account flat.
- The safety hook blocks any Bash command whose text contains the broker's order-call name. Put patches in a script file.
- The look: TradingView conventions. Data, prices, lines and numbers stay solid and instant. Glass and springs only on menus, dialogs
  and toasts. Lucide icons. Never TradingView's icons or brand. Tabular numbers. Reduced-motion fallbacks.

## Part 1: manual trading

Start with a table of every action a manual trade needs: entry, size, stop, target, move, partial, breakeven, trail, reverse, flatten,
cancel, switch account, switch symbol. For each one: clicks and keys today, the time it takes, and what can go wrong. Then fix the
slow and the risky ones. At minimum, look at:

**Speed**
- **Trading hotkeys**, each one off until set: buy/sell market, buy/sell at bid/ask, flatten this symbol, flatten all, cancel all,
  reverse, move stop to breakeven, size up/down, and a hold-to-confirm option. Today the keys only open the timeframe and symbol
  boxes, so trading keys must never fire while a text box has focus.
- **Click-to-trade on the price ladder** (`dom.js` is read-only today): click bid/ask to place a limit, drag an order to move it,
  right-click to cancel. Show working orders and the position on the ladder. One click to arm, then click to send, or a confirm,
  as the owner chooses.
- **Order templates**: named templates of a stop and targets in ticks, points, ATR or $, with partials, auto BE and trail, one per
  symbol, and one key or click to apply. The order panel already has risk in $, R:R, BE, BE+1, trailing and partial TP. Make them
  quick to reach rather than adding more.
- **Size per symbol and per account**, not one size box shared by every chart (`HBDeskClient.prefs.qty`). Show the size in contracts
  and in $ at risk next to the button.
- **Drag to change**: drag the stop or target line to move it, drag a position line to add a bracket, and show the $ and R live
  while dragging.
- **Account switching**: the "Trade on:" account stays clear, with one-click switching. Optionally copy to a group of accounts, using
  the existing trade copier (`tradecopier-copier-only-build`).

**Safety**
- A **prop pre-check** on every manual order, from the account's own rule file: daily loss limit, trailing max drawdown counting open
  losses (`lucid-drawdown-counts-open-losses`), max contracts, flat-by time, day lock, news blackout. Show the room left before the
  order ("$412 to the daily limit"). If an order would break a rule, block it or warn, as the owner chooses per rule. Show the room
  left at all times on the chart.
- **No naked entries by default**: offer a default stop for every entry, with a switch to turn it off.
- Show the open P&L and the day's P&L per account in $ and R. Make "Flatten all" impossible to miss and impossible to click by mistake.
- Restore after a reconnect: working orders, the position and armed exits redraw from the broker, never from page memory. Show a clear
  "feed down / orders unknown" state.

**After the trade**
- A **manual-trade journal**: every fill saved to disk (today the page keeps the last 50, in memory only), with the setup tag, screenshot
  or chart snapshot, R, MAE/MFE and notes. Trades marked on the chart. Day and week stats on traded days only (Sharpe rule). Export to CSV.
- Show a past day's manual trades on bar replay to review them.
- Sounds and alerts for fills, stop hits and price alerts, with volume and on/off per type.

## Part 2: drawing tools

Today: horizontal line, vertical line, long/short position, measure, note, alert, anchored VWAP, arrow, rectangle, channel, fib. For each
tool, test it by hand on a fake chart, then decide keep / fix / change / add. Check snapping to OHLC, magnet, lock, hide, clone, delete,
style presets, copy between charts and timeframes, saving with the layout, and right-click menus. Look at what a manual futures trader
uses daily that is missing: a ray / extended line, a price range with ticks / $ / %, a date range, a fib extension, a parallel channel,
a horizontal ray, text, alerts on any drawing, the session-level tools, and a long/short tool that turns into a real bracket order.

## Part 3: indicators, every single one

The catalog (~48 plus the TradingView tab and Pine): VWAP, session levels, prior day / week / month H/L, opening range, open at a time,
swing high/low, equal highs/lows, fair value gaps, range of the move, last-swing range, session range, noise band; order flow (delta,
cumulative delta, delta strength, delta turnaround, footprint, cluster statistics, big trades / prints / orders, absorption,
book imbalance, liquidity heatmap); volume, volume profile, TPO, prior value area, naked POCs, stacked profile zones, RVOL, VWMA;
SMA, EMA, TEMA, Bollinger, Keltner, Donchian, Supertrend, ATR, ADX, MACD, RSI, Stochastic, MFI, efficiency ratio; economic calendar,
headlines. Read the live list from `catalog.js` / `flowdefs.js` / `studies_tv*.py`. Don't trust this one.

For each indicator, one row:

| Indicator | What it shows (one plain sentence) | Anchored to something real? | Accurate? (checked against what) | Adjustable? (what's missing) | Easy to read? | Used by a Desk strategy? | Verdict: keep / fix / change / merge / remove |

- **Accuracy**: check each one against a reference: the TradingView-parity tests (`tvparity`), a hand calculation on 3 real days, and
  for order flow, the tick tape. Look for session-anchor errors (18:00 ET open vs RTH), roll days, holidays, partial bars, first bars of
  the session, repainting, and look-ahead (a mark drawn before its bar closed).
- **The owner's test** (`feedback-only-real-indicators`): it must be tied to something real (a true swing, a session level, a traded
  price, a book fact) and be explainable in one sentence. If it fails, offer removal first. Don't tune numbers to rescue it.
- **Adjustable**: every length, source, session, anchor, colour, width, label and visibility per timeframe in its settings dialog.
  Finish what 10-22 deferred: the Visibility tab, theme-aware colours, the heatmap palette, Pine plot overrides, MA type and source
  parity, the bigprints sweep settings.
- **Usable**: legend values, price-axis tags, sensible defaults, no overlapping clutter, fast on a 1-minute chart with a day of ticks.
- Removal means taking the instance off his layouts while the catalog entry stays, unless he says delete. "Unused on saved layouts" does
  not mean dead (finding `2026-10-22-unused-on-saved-layouts-is-not-dead`). Ask him about B1-B9 from the 10-22 cleanup again.
- New indicators only where a manual futures trader would use them and they pass his test (for example: overnight high/low, the initial
  balance, VWAP standard-deviation bands, a session delta per bar). Propose them, don't build them without his yes.

## How to work

1. **Review first, change nothing**: the Part 1 action table, the Part 2 tool list and the Part 3 indicator table, each with a ranked
   change list (money risk first, then speed, then looks). Show the owner. He picks.
2. One branch and worktree per package: order entry and ladder, prop pre-check, journal, drawing tools, indicator fixes. Two packages
   never touch the same files.
3. Each package: tests first, then code, then a headless-browser check on replay mode (`2026-10-21-replay-mode-browser-check-recipe`).
   Take two screenshots and check the state in JS, because the hidden pane freezes transitions. Then the full suite: JS `*.test.mjs`,
   Python charts, tvparity, the Desk page.
4. Order code is checked on PAPER, with real fills, after the 18:00 ET open, before it's called done. Say what was and wasn't tested
   with real fills.
5. Talk to the owner in plain short words: the answer first, a small table, no jargon.

## What to hand back

1. The manual-trade action table: before (clicks, time, risk) → after.
2. The drawing-tool list with each verdict and what changed.
3. The indicator table with each verdict, the accuracy check behind it, and which Desk strategies a math change would touch.
4. The code on branches, tested, each with a one-line merge plan and when it's safe to merge.
5. Hotkey and settings sheets: every new key and switch, its default, and where to change it.
6. What still needs the owner's decision, as a short numbered list he can answer by number.
