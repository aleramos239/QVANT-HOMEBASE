# Charts — Level 2 (depth of market): stream, record, and (later) DOM ladder + heatmap

Date: 2026-09-27 · Status: approved in chat. The user bought CME depth on the live Tradovate login and said
"i just got the level two data on the live account, add it". The features were described in chat just before.

**Verified 2026-09-27 (read-only probe on the live login):**
- `md/subscribeDOM` returns `mode: RealTime` for NQZ6, ESZ6 and BTCV6.
- Book size: NQ 30 bid / 19 offer levels, ES 30/30, BTC 8/10.
- BTC sent 23 updates in 6 s on a Saturday.

The chart service's market data already runs on the live login (`HOMEBASE_CHARTS_MD=live`, main be7f1c8).

## Part A (this branch, backend only — the page is being rebuilt on `feat/charts-screens`)

### `homebase/charts/depth.py` (new)
- **Book.** `Book(root)` keeps the latest bids and offers as lists of `[price, size]`, best first, up to 30
  levels each, plus the timestamp (ms) of the last update. It is fed by `md` events carrying `doms`:
  - match the event to a root by contractId (the tick feed's contract map);
  - replace the book with each snapshot (Tradovate sends full snapshots).
- **Subscriptions** use `md/subscribeDOM` / `md/unsubscribeDOM` on the chart service's EXISTING md socket
  (the tick feed's `ws`). There is no new login and no new socket.
  - **Who is subscribed:** the union of the roots shown on any page (demand from `/ws` clients) and
    `DEPTH_RECORD_ROOTS` (default `("NQ", "ES")`, env `HOMEBASE_DEPTH_ROOTS`).
  - **Changes:** subscribe on demand, and unsubscribe 60 s after the last viewer leaves unless the root is recorded.
  - **Reconnect:** re-subscribe everything when the md socket reconnects.
  - **Refusal:** a refused `subscribeDOM` is recorded as that root's `depth_error` (status) and retried every 10 min.
  - **Budget:** subscribeDOM is not a `getChart`, so it does not count against the 180/h chart budget; the
    tick feed's `count_request` is not called for it. The first real session must confirm there are no penalties.
- **Fan-out to pages:** `{"type": "depth", "root", "ts", "bids": [[p, s], …], "offers": [[p, s], …]}`.
  - At most **10 messages per second per root**, coalesced to the latest book.
  - Top **20 levels** each side on the wire.
  - Only to connections that have a chart on that root. Reuse the existing bounded per-connection outbox
    (the `Fanout` pattern from `desk.py`), so a slow page never blocks.
- **Status:** `/api/status` gains `depth: {root: {subscribed, levels, age_s, error}}`.
- **Replay:** no depth subscriptions. A replay page simply gets no `depth` messages.

### Recording (NQ, ES by default)
- **Where:** `~/futures_depth/<ROOT>/<YYYY>/<date>_<contract>.depth.jsonl.gz`.
  - Session date as the tick recorder uses it (18:00 ET roll; the 24/7 rule for crypto).
  - One gzip member per flush, like the tick recorder, so a crash loses at most one flush.
- **Content:** at most **4 snapshots/second** per root, and only when the top-10 book changed. Each line:
  `{"t": ms, "b": [[p, s] ×≤10], "a": [[p, s] ×≤10]}`.
- **Flushing and failures:**
  - flush every 30 s and on shutdown;
  - disk errors are reported in status and never crash the service;
  - the recorder never writes under `~/futures_ticks`.
- **Size estimate:** about 5–15 MB/day per root gzipped. `DEPTH_RECORD_ROOTS` is the knob.

### Tests (pytest, fakes only — no broker)
- **Book:** replace-on-snapshot, contractId → root, level caps.
- **Subscriptions:** subscribe/unsubscribe by demand, with the 60 s linger; re-subscribe after reconnect;
  a refusal becomes an error and is retried.
- **Fan-out:** the 10/s coalescing (injected clock) and root filtering.
- **Recorder:** the 4/s cap, change-only lines, the session-date file name, gzip members that survive a
  truncated tail, and no writes under `~/futures_ticks`.
- **Status and replay:** the `/api/status` depth block; replay makes no subscriptions.

## Part B (after `feat/charts-screens` merges; its own plan)
- **DOM ladder:** a toolbar `DOM` toggle opens a ladder column on the selected chart.
  - Price rows centred on the last trade: bid size (blue), price, ask size (red), and traded volume at the
    price for the session.
  - Best bid and ask are highlighted, and the user's working orders and position are marked.
  - The ladder recentres on demand.
- **Liquidity heatmap:** a chart indicator. A primitive draws the depth history as colour intensity by size
  behind the candles: a rolling live buffer of the last 2 h, plus the recorded files for past sessions.
- **Big-order lines:** a level with size ≥ 5× the median displayed size gets a labelled line
  ("500 @ 30,800"). Lines appear and fade.
- **Imbalance gauge:** a legend value, Σbids − Σoffers over the top 10 levels, as a percentage and a small bar.
- **Later:** click-to-trade on the ladder, through chart trading's guards.
