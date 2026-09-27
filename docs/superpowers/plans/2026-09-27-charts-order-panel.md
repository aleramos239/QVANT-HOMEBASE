# Charts order panel, instrument logos, Buy/Sell placement, Stop Limit + TIF. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three things:
- a TradingView-style order panel docked on the right of the chart page;
- a logo badge per instrument;
- the legend's Buy/Sell block moved to sit under the instrument name and above the indicator list.

Stop Limit orders and Time-in-force are added to the desk's chart-trading path.

**Architecture:**
- This runs on the same branch and worktree as the screens build (`feat/charts-screens`, `.worktrees/screens`). It runs after the screens Task 5/6 fix rounds and before screens Task 7.
- Page modules stay plain IIFEs, each exposing one `window.HB*`. Pure logic goes in `trade.js` (`HBTrade`, Node-tested). The new browser module is `orderpanel.js` (`HBOrderPanel`).
- The desk side changes only the chart-trading order path (`homebase/trading.py` ChartDesk, `homebase/broker/base.py` OrderRequest, and the Tradovate adapter + ws client). The fake desk mirrors it.

**Tech Stack:**
- Python 3 / FastAPI / pytest;
- Lightweight Charts 5.2.1;
- Lucide icons (`lucide-static@1.48.0`, inlined);
- Node 26 (`node --test tests/js/*.test.mjs`).

**Spec:** the design the user approved in chat on 2026-09-26, copied verbatim below. It is the binding authority.

> **1. Order panel on the right, like TradingView's**
> - **Opening it:** a new "Order" button next to Trade opens a side panel for the selected chart's instrument. It has two tabs, Order and DOM. DOM would hold the Level 2 price ladder we already planned, so for now it's an empty "coming next" tab.
> - **Prices:** Sell and Buy with the spread between them, updating live.
> - **Order type:** tabs for Market, Limit and Stop. For Limit and Stop you get a price box that fills from where you click on the chart.
> - **Size:** in contracts, with a switch to "USD risk". In USD risk mode you type the dollars you want to risk and it works out the contracts from your stop.
> - **Exits:** Take profit and Stop loss, each with an on/off switch. Each takes a value in $, ticks or price, and shows the other two alongside, like TV does.
> - **Accounts:** a row showing which accounts the order goes to, marked DEMO or LIVE.
> - **Send button:** one big button such as "Buy 1 NQZ6 MARKET". It's blue for buys and red for sells.
> - **Safety:** it goes through the same guarded send as the chart. That means the confirm dialog (unless one-click is on), the LIVE arm, the desk's 10/20 contract caps and the 9:30 bot lock.
> - Stop Limit and Time-in-force: the user said YES, so both are added to the desk in their own step (Task 2), and the order panel offers them. **The desk restart that makes them live needs the user's explicit OK at deploy time.**
>
> **2. A logo for each instrument:** a small round badge before the instrument name, in the legend and the symbol search. They are our own simple designs, not the exchanges' trademarked logos:
> - NQ "100", ES "500", YM "30", RTY "2K";
> - GC gold "Au", SI silver "Ag";
> - CL an oil drop, BTC "₿", and so on for the rest.
>
> **3. Moving the Buy/Sell buttons:** the legend order becomes instrument name and prices → Buy/Sell → indicator list. Folding the indicator list keeps Buy/Sell visible. The quantity box stays between the two buttons.

## Global Constraints

- Never place real orders. Tests never open broker (Tradovate) connections or use its tokens, and never write to `~/futures_ticks`.
- **No behaviour change for the 9:30 bot's orders.** Every existing `place_order` / `place_oso` / `OrderRequest` call made without the new fields must produce a byte-identical Tradovate body (pinned by a test).
- There are no native dialogs (`alert` / `prompt` / `confirm`); the viewer app blocks them. Use the page's `openDialog`.
- Every order-sending path goes through the tradeui guarded send:
  - the effective mode (LIVE-arm aware);
  - the confirm dialog unless one-click is on;
  - frozen preview → send (the bracket and prices sent equal the ones shown);
  - the shown∩fresh account resolution;
  - the in-flight lock.
- Lucide icons only, never TradingView's. There are no exchange or brand logos; badges are our own text/shape designs.
- Look like TradingView (light default, measured tokens in the redesign spec). Colours: Buy `rgb(41,98,255)`, Sell `rgb(242,54,69)`, matching the existing `.tr-buy` / `.tr-sell`.
- The asset cache-bust stays `?v=4` until the final sweep task of the screens plan. New script tags also carry `?v=4`.
- Browser storage (`localStorage`) is used only for per-viewer conveniences such as panel open/closed and width. Every access is wrapped in try/catch.

---

### Task 1: Instrument logos + Buy/Sell block under the name (UI)

**Files:**
- Modify: `homebase/static/charts/catalog.js`: `ROOT_BADGES` + `rootBadge(root)`, exported.
- Modify: `cell.js`, the legend markup:
  - a `.lg-logo` span before `.lg-name` in `.lg-title`;
  - a new `.lg-tradeslot` div between `.lg-ohlc` and `.lg-fold-wrap`.
- Modify: `tradelines.js`: append `this.block` into `.lg-tradeslot`, not at the legend's end.
- Modify: `app.js`: the symbol-search list rows show the badge.
- Modify: `icons.js`: Lucide `droplet`, `flame`, `bitcoin` if needed.
- Modify: `charts.css`.
- Test: `tests/js/catalog.test.mjs` (or the existing catalog test file).

**Interfaces:**
- Produces:
  - `HBCatalog.rootBadge(root) -> {text?: string, icon?: string, bg: string, fg: string}`;
  - `HBCatalog.badgeEl(root)`, which returns a `<span class="logo">` element (browser only; keep it in app.js/cell.js if catalog.js must stay DOM-free).
- The legend DOM order is `.lg-title` → `.lg-ohlc` → `.lg-tradeslot` → `.lg-fold-wrap` → `.lg-inds`.

**Badges:**

| Root | Badge | bg / fg |
|---|---|---|
| NQ | text "100" | `#0b1f4d` / `#fff` |
| ES | text "500" | `#b3261e` / `#fff` |
| YM | text "30" | `#1f3a93` / `#fff` |
| RTY | text "2K" | `#6a1b9a` / `#fff` |
| GC | text "Au" | `#c9a227` / `#1b1b1b` |
| SI | text "Ag" | `#9ea7ad` / `#1b1b1b` |
| HG | text "Cu" | `#b87333` / `#fff` |
| CL | icon `droplet` | `#1b1b1b` / `#fff` |
| NG | icon `flame` | `#1565c0` / `#fff` |
| ZN | text "10Y" | `#2e7d32` / `#fff` |
| BTC | text "₿" | `#f7931a` / `#fff` |

Any other root gets its first two letters on `#5d6b7a` / `#fff`. A micro root (an `M` prefix such as MNQ or MES) uses its parent's badge.

- [ ] Test first: `rootBadge` returns an entry for every `ROOT_NAMES` key, the fallback for `'ZZ'`, and the parent badge for `MNQ`, `MES` and `MGC`.
- [ ] Implement the badges as a 20 px circle (16 px in search rows), with 9–10 px bold text fitting the circle and `aria-hidden="true"`. The name keeps its accessible text.
- [ ] Legend: add the badge before the name. The trade block moves into `.lg-tradeslot`, and folding hides only `.lg-inds`. The Buy/Sell block stays visible when folded. Check this in the browser.
- [ ] Commit.

### Task 2: Stop Limit + Time-in-force on the desk's chart path (MONEY PATH)

**Files:**
- Modify: `homebase/broker/base.py`: `OrderRequest` gains `trigger_price: Optional[float] = None` and `time_in_force: str = "Day"`, **appended last** so positional callers are unchanged.
- Modify: `homebase/broker/tradovate_ws.py`: `place_oso` gains `entry_trigger_price=None`. For `entry_type == "StopLimit"` it sends `price=entry_price` (the limit) and `stopPrice=entry_trigger_price`. `place_order` already handles `stoplimit`.
- Modify: `homebase/broker/tradovate.py`:
  - `place_order` / `place_bracket` pass `time_in_force=req.time_in_force`. For StopLimit, `place_order` sends `price=req.price, stop_price=req.trigger_price` (never the SL), and `place_bracket` sends `entry_trigger_price=req.trigger_price`.
  - The order view carries both `price` (the limit) and `trigger` for StopLimit orders.
- Modify: `homebase/trading.py`:
  - `TYPES = ("Market", "Limit", "Stop", "StopLimit")`;
  - `TIFS = ("Day", "GTC")`;
  - `parse_order` reads `trigger_price` (required for StopLimit, refused otherwise) and `tif` (default "Day", must be in TIFS);
  - `OrderIntent` gets `trigger_price` and `tif`;
  - `check_prices` rules for StopLimit: the trigger is checked like a Stop against the last price. The limit must be on the fill-allowing side of the trigger (Buy: limit ≥ trigger; Sell: limit ≤ trigger) and within 100 ticks of it. The bracket ref is the limit price.
  - `_order_one` passes the trigger and tif through, and the journal records them;
  - `_modify` keeps refusing anything but Limit and Stop, with the message "Stop Limit orders can't be moved — cancel and place again".
- Modify: `tools/fake_desk.py`: accept StopLimit (trigger then limit; fill at the limit once the last price crosses the trigger and the limit is marketable) and tif (stored and shown; Day orders are dropped at the replay session end if simple, otherwise stored only).
- Modify: `homebase/static/charts/trade.js`: `orderBody` accepts `trigger` and `tif`; `confirmOrder` text shows "Buy 1 NQ Stop Limit @ 30,900.00 (trigger 30,895.00) · GTC".
- Test:
  - `tests/test_trading_*.py`: parse, check_prices and the journal;
  - a **byte-identical body test**: a Market/Limit/Stop `place_order`, and a Stop-entry `place_oso` with SL/TP, built with no new fields, equal the pre-change bodies (use the ws client with a fake `request` capturing the body; no network);
  - fake desk tests;
  - node tests for `orderBody` / `confirmOrder`.

**Interfaces:**
- Produces:
  - the desk order body `{..., type: "StopLimit", price: <limit>, trigger_price: <trigger>, tif: "Day"|"GTC"}`;
  - the desk state order rows for StopLimit carry `trigger`;
  - `HBTrade.orderBody({... trigger, tif})`.

- [ ] Test first for each rule above, then implement. Refusal messages are plain English.
- [ ] Run the full pytest and node suites. Commit.
- [ ] Report: list every file touched on the live desk path and paste the byte-identical test names.

### Task 3: The order panel (MONEY PATH)

**Files:**
- Create: `homebase/static/charts/orderpanel.js` (`HBOrderPanel`).
- Modify:
  - `charts.html`: an `Order` toolbar button `#tbOrder` right after `#tbTrade`, and `<aside class="opanel" id="opanel" hidden>` as the last child of `.main` after the grid; the script tag carries `?v=4`;
  - `app.js`: mount, and call the panel on selection change;
  - `tradeui.js`: `placeOrder` accepts explicit `exits: {sl, tp}` prices and `trigger` / `tif`, frozen for preview and send exactly like the M1 fix;
  - `trade.js`: pure helpers;
  - `icons.js`, `charts.css`.
- Test: `tests/js/trade.test.mjs` for the pure helpers.

**Interfaces:**
- Consumes: `HBDeskClient` (state, quotes, prefs, mode, on), `HBTradeUI.placeOrder` / `busy` / `onBusyChange` / `armedIds`, `HBCharts.selected` / `cells`, `HBCatalog.rootBadge`, and the page's `openDialog`.
- Produces: `HBOrderPanel.mount(page)`, `.toggle()`, `.setRoot(root)` and `.pickPrice(price)`. The last is called by the chart when the panel's price field is focused and the user clicks the chart.
- Pure helpers in `trade.js`:
  - `exitTriple({unit: 'usd'|'ticks'|'price', value, side, entry, tick, pv, kind: 'tp'|'sl'}) -> {usd, ticks, price}`: SL below entry for Buy, TP above; prices tick-rounded; ticks are whole and ≥ 1.
  - `qtyFromRisk(usd, slTicks, tick, pv) -> int`: floor, 0 when under one contract.
  - `panelOrder(state) -> {ok, error?, body-parts}`: validates the type/price/trigger side versus the quote, the SL/TP side, and qty 1–10.

**Behaviour (the spec above, made exact):**
- **Panel:** 320 px wide, resizable 280–420, docked on the right. Open state and width are kept in localStorage with try/catch. `#tbOrder` toggles it. The panel's header shows the badge, the front-month contract (from the desk state or quote if known, else the root), and ×.
- **Tabs:** Order | DOM. DOM shows a quiet "Level 2 ladder — coming next" placeholder.
- **Sell/Buy tiles:** bid/ask (falling back to last), with the spread in ticks between them. Clicking a tile picks the side. Stale quotes (>10 s) show dimmed.
- **Type tabs:** Market | Limit | Stop | Stop Limit.
  - Limit/Stop show a Price field. Stop Limit shows a Trigger field and a Limit field.
  - The fields default to the last price when first shown.
  - While a price field is focused, clicking the selected chart fills it (tick-rounded). Clicking does not place anything.
- **Units:** a qty field (1–10), plus a "USD risk" toggle. USD risk needs SL on: qty = `qtyFromRisk`, shown as "= N contracts". When it is 0 or SL is off, the send is disabled with the reason.
- **Exits:**
  - TP and SL each have a switch, a value field, and a unit dropdown ($ / ticks / price) showing the other two as secondary text. The "$" figure is for the whole order's qty.
  - Defaults come from `prefs.tpTicks` / `prefs.slTicks` (0 = off). Panel edits stay in the panel and don't change the Trade-menu defaults.
- **TIF:** a Day/GTC select under "Extra settings" (collapsible, like TV's).
- **Accounts row:** the effective accounts with DEMO/LIVE chips, and a "Change" link that opens the Trade menu. When the mode isn't "on", the reason is shown and the send is disabled.
- **Send button:** "Buy 1 NQZ6 MARKET" / "Sell 2 NQZ6 LIMIT", full width, in Buy blue or Sell red.
  - It is disabled while `HBTradeUI.busy()` or while `panelOrder` is not ok, and the reason shows under it.
  - Sending calls `HBTradeUI.placeOrder` with the explicit exits/trigger/tif. The confirm, one-click, the LIVE arm, the account resolution and the in-flight lock all apply unchanged.
- The panel never rebuilds its form on desk or quote events. It patches the price text and the accounts row in place (the lesson from Task 4/5 review item 4).
- Keyboard: Enter in a field does NOT send. Only a click, or Enter/Space on the focused send button without repeat, sends.

- [ ] Tests first for `exitTriple`, `qtyFromRisk` and `panelOrder`. Cover the sides for Buy/Sell × each type, a stale quote, and a USD risk under one contract.
- [ ] Implement the panel. Browser-check on the fake desk (:8859 + :8855), but do not start or stop servers; the controller does. Commit.
