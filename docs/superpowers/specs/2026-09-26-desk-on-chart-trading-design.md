# Desk on the chart — live strategies, positions & orders, and trading from the chart

Date: 2026-09-26 · Status: **APPROVED** by the user in chat ("YES, to both"), including the recommended prestage skip below.

User asks:
- "i want to be able to connect accounts and trade and execute on them on the charts"
- "i also want to be able to see the live strategeis executing on there"

The user's choices (chat, "yes" to the recommended options):
- **Accounts:** the user ticks one or more; an order goes to each ticked account at once.
- **Confirmation:** a confirm step, with a one-click switch.
- **Bot account:** tradable, but locked 09:20–09:35 ET.
- **The chart asks the desk; only the desk talks to Tradovate.**

The assistant never places orders. The first real order is the user's.

## Why this shape

The desk (`homebase/server.py`, :8850) is the only process holding broker sessions. It fires the 9:30 bot at
09:30:00.000 from one asyncio loop. The chart service (:8852) is a separate process on purpose: chart load
can never delay the fire. Trading from the chart keeps that split:

```
page ──(same-origin HTTP + existing /ws)──► chart service ──(localhost, desk key)──► desk ──► Tradovate
page ◄──────────── desk events fanned out ◄── chart service ◄──(SSE, desk key)────── desk
```

## What was found in the desk (2026-09-26 code map) and what it forces

- **Brackets:** `TradovateAdapter.place_order` / `place_bracket` use native OSO (broker-side OCO). A
  bracket entry is one broker call: entry + stop + target.
- **Only fills are streamed today** (`observe_fills`). Order, position and cash-balance pushes from the
  user-sync websocket update private dicts only, and positions are fetched on every `get_metrics()` call.
  → The adapter gains an entity listener plus caches for `position` and `cashBalance`, so the chart gets
  live updates **without** extra broker requests.
- **`flatten_all` / `cancel_all` are account-wide.** → Chart trading needs a **symbol-scoped**
  `flatten_symbol` / `cancel_symbol`.
- **Bot conflicts:**
  - The bot matches fills by order id, but falls back to **symbol+side** when a push has no id. It reads
    an opposite-side fill while `live` as its exit. A manual fill in the bot's symbol on the bot's account
    while the bot is `placing|placed|live` can therefore corrupt the bot's state.
  - Its 12:55/15:55 flatten nets the **whole** position in its symbol.
  - → Manual orders in a strategy's symbol on an account booked to that strategy are **refused 09:20–09:35
    ET and while that strategy's day state on the account is `placing`, `placed` or `live`**. This is the
    user's lock, plus the second condition the code requires.
- **No auth on desk routes** (network isolation only; `/hook` has a secret). → New trading routes require a
  **desk key header**, which browsers cannot send cross-origin without a preflight the desk never grants.
  They also refuse any request carrying an `Origin` header.
- **Silent account fallback:** a pinned account missing from the login is connected to another account
  (…044/…045 → …047, seen 2026-09-26). → Fixed first: a missing pin raises and
  the entry shows disconnected with the reason. Trading refuses any account whose resolved broker account
  differs from its pin.
- **Max qty:** none enforced. **Risk meter:** `risk.py` exists but is unwired. → New limits (below); the
  risk meter is out of scope.

## Desk side (`homebase/`)

- **`broker/tradovate.py`:**
  - `_resolve_account` raises when a pinned account is not on the login.
  - `add_listener(cb)`: called with `(entity_type, entity)` for `order`, `orderVersion`, `position`, `fill`
    and `cashBalance` pushes, after the adapter's own ingest.
  - `position` / `cashBalance` caches, seeded at connect/reconnect with `position_list` /
    `cash_balance_list`.
  - `flatten_symbol(symbol)`: market order for −net in that contract, then cancel only that contract's
    working orders.
  - `cancel_symbol(symbol)`.
  - `modify_order` is used for drags (it exists).
- **`trading.py` (new) — `ChartDesk`:**
  - keeps per-account live views from the listener (positions with avg price and open P&L, working orders
    incl. bracket legs, recent fills, balance, realized P&L);
  - enforces the guards;
  - places, modifies and cancels through the adapters; places concurrently across ticked accounts
    (`asyncio.gather`), one result per account;
  - journals every action: `manual_order`, `manual_modify`, `manual_cancel`, `manual_flatten`,
    `manual_reverse`, `manual_refused` (with the reason).
- **`desk_api.py` (new) router, mounted at `/api/trade`:**
  - **Every route** requires `X-Homebase-Key`, the hex secret in `homebase/.state/desk.key`. The desk
    creates the file at startup if missing (32 random bytes, mode 0600). Any request with an `Origin`
    header is refused (403).
  - `GET /api/trade/state`: a full cached snapshot, no broker calls:
    - `enabled`, `limits`;
    - `accounts[]`: id, label, broker account, env demo/live, connected, error, balance, realized P&L,
      positions, working orders, strategies booked;
    - `bot{}`: timer stage, gate TREND/CHOP + ADX, anchor, and each booked strategy's day states:
      status, upper/lower, SL/TP, fills, P&L.
  - `GET /api/trade/stream` (SSE): `state` on connect, then `account` / `bot` / `fill` / `result` events;
    a heartbeat every 15 s.
  - `POST /api/trade/order`:
    `{client_id, accounts:[id], root, side: Buy|Sell, qty, type: Market|Limit|Stop, price?, sl_price?, tp_price?}`
    → `{results: {id: {ok, order_id|null, error|null}}}`.
  - `POST /api/trade/modify` `{client_id, account, order_id, price}`.
  - `POST /api/trade/cancel` `{client_id, account, order_id}`.
  - `POST /api/trade/cancel-symbol` `{client_id, accounts, root}`.
  - `POST /api/trade/flatten` `{client_id, accounts, root}`.
  - `POST /api/trade/reverse` `{client_id, accounts, root}`: flatten, then market the opposite side for the
    previous |net| (two journaled steps).
- **Guards** (desk-side and authoritative; each refusal carries a sentence the page shows as-is):
  1. Chart trading is **enabled** on the desk: config `chart_trading.enabled`, default **false**, with a
     switch on the desk page. The desk's **Kill** also switches it off.
  2. The account exists, is connected, and resolved to **its own** pinned broker account.
  3. **Quantity:**
     - `1 ≤ qty ≤ chart_trading.max_order_qty` (default 10);
     - the resulting |net| in that contract ≤ `chart_trading.max_position_qty` (default 20);
     - both are editable on the desk page.
  4. **Bot lock:** if the account is booked to a strategy whose symbol is this root, refuse 09:20–09:35 ET
     on weekdays, and while that strategy's day state on the account is `placing|placed|live`. Other roots
     on that account are unaffected.
  5. At most 5 actions per second per account (a double-click guard).
  6. Price sanity: Limit/Stop prices are tick-rounded server-side; a Stop Buy below the market or a Stop
     Sell above it is refused ("a buy stop must be above the last price").
- **Prestage skip** (user-approved): at 09:28:30, if a booked account holds a non-zero position in the bot's
  symbol, the bot **skips that account for the day**: journal `timer_skipped` with `reason: manual_position`
  (account, net) and the readiness strip red for that account. Other booked accounts fire as usual. Without
  the skip the bot would net against the manual contracts at its 12:55/15:55 flatten and could misattribute
  fills.

## Chart service side (`homebase/charts/`)

- **`desk.py` (new):**
  - Reads the desk key, holds one SSE connection to `http://127.0.0.1:8850/api/trade/stream`, and
    reconnects with backoff 1 s → 30 s.
  - Keeps the latest state and fans it out to page clients over the existing `/ws` as `{"t": "desk", ...}`
    messages.
  - When the desk is unreachable: `{"t": "desk", "down": "<reason>"}`, and the page disables trading.
- **Proxy:** `POST /api/desk/{order|modify|cancel|cancel-symbol|flatten|reverse}` → the desk's
  `/api/trade/*` with the key. It runs after the chart service's own `browser_write_ok` Origin check;
  bodies are passed through, with a size limit of 4 KB.
- **Live bid/ask for the Buy/Sell buttons:** `md/subscribeQuote` for the roots shown on any chart, on the
  chart service's md socket. It is budget-neutral if quote subscriptions don't count against the 180/h
  chart budget — **verify during implementation**. Fallback: the last trade's bid/ask (already on every
  tick), labelled "as of last trade".

## Page (`homebase/static/charts/`)

**Toolbar**
- A **Trade** button (right side, like TradingView's) opens the account menu:
  - each desk account shows a checkbox, label, `DEMO` / `LIVE` badge (LIVE in `--down`), balance, and
    connected dot;
  - a "one-click trading" switch;
  - the default quantity;
  - SL/TP defaults in ticks (off by default).
- When chart trading is disabled on the desk, the menu says so, with a link to the desk page.
- The ticked set persists per viewer (localStorage, try/catch).

**On each chart whose root is tradable** (≥ 1 account ticked):
- **Buy/Sell block** under the legend (TradingView layout): red `SELL` box with the bid, the spread in
  ticks, and blue `BUY` box with the ask; the quantity sits between them.
  - A click sends a Market order to the ticked accounts, after the confirm dialog unless one-click is on.
- **Right-click on the price pane:** a context menu with:
  - `Buy 2 @ 30,900.00 Limit` / `Sell 2 @ … Stop`: Limit or Stop is inferred from the clicked price versus
    the ask/bid, as TradingView does;
  - `Cancel all orders (NQ)`;
  - `Flatten NQ`;
  - `Reverse NQ`.
- **Lines** (native price lines + a primitive for labels and ×):
  - **Positions:** a line at the average price, green (long) or red (short). Its label reads
    `LONG 3 · +$450 · …047` (one per account; accounts at the same average price are merged, e.g.
    `3 accts`). A × flattens that account/root.
  - **Working orders:** a line at the price: `BUY LMT 2 · …047`. Drag it to modify; × cancels it.
  - **Brackets:** `SL` / `TP` lines, draggable, showing `−$300` / `+$600` for their distance from the
    average price.
  - **Executions:** small ▲/▼ at the fill's bar and price.
- **Confirm dialog:** account list with env badges, side, qty, type, price, SL/TP with $ risk/reward (RR as
  1:X), and a "Don't ask again (one-click trading)" checkbox. Enter confirms; Esc cancels.
- **Refusals and results:** a toast per account with the desk's reason or "Filled 2 @ 30,910.25".

**Bottom panel** (collapsible, 260px default, shared later with the Strategy Tester): tabs **Positions**,
**Orders**, **Fills** and **Accounts** (TradingView's Account Manager). Tables use tabular numbers, and each
row has its action (close, cancel).

**Live strategies:** on every chart of a booked strategy's symbol:
- **Legend badge:** `9:30 bot · TREND ADX 23.4 · placed` (or CHOP / off / done +$876).
- **Entry levels:** after 09:30:00, the bot's upper and lower stop entries as dashed lines
  (`9:30 BUY STOP 10 @ 30,925.00`); after the fill, its SL/TP lines. These are view-only, since the bot
  owns them.
- **Markers:** entry/exit markers with the realized P&L.
- **Data:** the badge and lines come from the desk's `bot` state, so they are exactly what the desk is
  doing.

## Testing

- **Desk (pytest, FakeAdapter; no real broker):**
  - each guard: disabled, borrowed account, qty limits, bot lock windows incl. DST and `placing|placed|live`,
    rate limit, stop-price side;
  - key/Origin checks;
  - snapshot and SSE event order;
  - `flatten_symbol` / `cancel_symbol` / reverse;
  - `_resolve_account` raising;
  - the listener caches;
  - the prestage warning.
- **Chart service:** the SSE client (reconnect, fan-out), the proxy (Origin check, key forwarded, size
  limit), and quote-subscription budget accounting.
- **Page:**
  - Node tests: order-type inference, line labels, P&L and $ math, and the account-menu state.
  - Browser checks against a **fake desk** test server that speaks the same API, never the real desk.
- **Deploy:**
  - Deploying needs a **desk restart** (the live trading service). This happens only with the user's
    explicit OK, outside market hours, after the suite is green. Chart trading stays disabled until the
    user switches it on.
  - The first real order is placed by the user.

## Out of scope (for now)

- Level 2 / DOM ladder: the user must buy depth first.
- Wiring the trailing-drawdown risk meter.
- Trading any symbol not shown on a chart.
- Options.
- Alerts.
- Sending a Long/Short drawing as an order.
