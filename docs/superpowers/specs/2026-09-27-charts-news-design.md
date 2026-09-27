# Charts — live news feed + burst detector + reaction log (backend, Part A)

Date: 2026-09-27 · Status: approved in chat.

**The request.** The user asked for "instant news posts, like financial juice … when trump would always post
something about war … it would pump or dump the market, or cause a burst, [so] we know when that happened
and from now on know when it happens". The design was presented and the user said "lets add … 2, 5" plus
the news feed. It was queued and is now started in parallel (the user asked why it wasn't running at the
same time).

**Probed 2026-09-26** (see the vault note `homebase-terminal-charts-build`, "Queue added"):
- FinancialJuice RSS (`https://www.financialjuice.com/feed.ashx?xy=rss`, 100 items / ~19 h) works;
- Trump's Truth Social posts, via `https://trumpstruth.org/feed`, work (truthsocial.com itself returns 403);
- ForexLive and MarketWatch are slower.

## Part A — backend in the chart service (this branch)

### `homebase/charts/news.py`
- **Sources:**
  - FinancialJuice RSS and trumpstruth RSS, each polled every **60 s** (never faster: be a polite client).
  - A browser User-Agent and a 10 s timeout.
  - A response cap of 2 MB.
  - The fetch function is injected, so tests never touch the network.
  - **No fetching in replay mode.**
- **Item:** `{id (stable hash of source+guid/link+title), source: "financialjuice"|"truth", t_ms (published),
  seen_ms (first time we saw it), title, url, tags: [...]}`.
  - Keep **both** timestamps: the gap between them measures the feed's delay.
  - Dedup by `id`.
- **Tagger** (pure): case-insensitive keyword groups, each producing a tag:
  - `war` (war, strike, missile, attack, military, troops, ceasefire, nuclear)
  - `tariff` (tariff, trade deal, duties, sanctions)
  - `fed` (fed, powell, fomc, rate cut, rate hike, interest rate)
  - `china`, `iran`, `russia`, `oil` (oil, opec, crude)
  - `trump` (every truth item, plus titles containing "trump")
  - `data` (cpi, nfp, payrolls, gdp, pce, jobless)
  - `breaking` (breaking, urgent, flash)
- **Storage:**
  - `.state/charts/news/<YYYY-MM-DD>.jsonl`, append-only, keyed by the `seen_ms` ET date;
  - retention 90 days;
  - `GET /api/news?from=<ms>&to=<ms>&tags=…&sources=…` returns items in range, newest first, capped at 500.
- **Live push:** a new item goes to every page as `{"type": "news", …item}` through the bounded per-connection
  outbox pattern (`desk.py` `Fanout`).

### `homebase/charts/bursts.py`: burst detector (pure core + a thin wiring)
- **Input:** the live ticks the chart service already receives, per root, for NQ, ES, YM, RTY, GC, CL, BTC.
  Configurable via env `HOMEBASE_BURST_ROOTS`.
- **Rule:**
  1. Compute the absolute move over a rolling **30 s** window: |last − first| in ticks.
  2. Compare it with the median 30 s move of the trailing **60 minutes** for that root.
  3. A burst fires when the move is ≥ **4× the median** AND ≥ **8 ticks**.
  4. Then enforce a refractory period of 120 s per root.
- **Burst record:** `{root, t_ms (window end), dir: up|down, move_ticks, ratio, from_px, to_px}`.
  - Pushed as `{"type": "burst", …}`.
  - Stored in `.state/charts/news/bursts-<date>.jsonl`.
- **Links:** each burst gets `near_news`, the items with `t_ms` or `seen_ms` within **±3 min**.

### Reaction log
- **What it records:** for every news item, the move of NQ, ES, GC, CL, BTC at +10 s, +1 min and +5 min after
  its `t_ms`. Moves are in points and ticks, measured from the last print at or before `t_ms`, using the
  chart service's live ticks.
- **When:** computed when the +5 min mark passes.
- **Storage:** `.state/charts/news/reactions-<date>.jsonl`, with fields
  `{id, source, title, tags, t_ms, seen_ms, delay_s, roots: {NQ: {m10s, m1m, m5m}, …}}`.
- **Missing data:** a root with no prints in the window gets `null`.
- **Reuse:** research reads this log later. There is no UI for it in Part A.

### Status and tests
- **`/api/status`:** `news: {ok, last_fetch: {source: {at, items, error}}, delay_p50_s}` plus `bursts: {roots, last}`.
- **pytest (fakes only; no network):**
  - RSS parsing (both formats, bad XML, dates);
  - dedup;
  - the tagger;
  - the 60 s floor and the 2 MB cap;
  - no fetch in replay;
  - the burst detector's rule edges (4×, 8 ticks, refractory, median warm-up needing 20 min of data);
  - news↔burst linking;
  - the reaction math at +10 s/+1 m/+5 m, including no-print → null;
  - storage and retention;
  - `/api/news` filters;
  - Host allowlist on the new routes (reuse `homebase/netguard.py`).

## Part B — page (after the screens build; its own plan)
- A news panel with a live headline stream, Trump posts highlighted, tag chips, and new "breaking" items
  flashing. A click jumps the chart to that time.
- Headline markers on the time axis, with the text on hover.
- ⚡ burst markers on charts, with the linked headlines in their tooltip.
