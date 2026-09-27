# Level 2 screens and the news panel on the chart page (Part B of the depth and news specs). Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The page half of two live backends:
- Level 2 (`homebase/charts/depth.py`): the DOM ladder, big-order lines, the imbalance gauge and the liquidity heatmap;
- the news feed plus burst detector (`homebase/charts/news.py`, `bursts.py`): the news panel, headline markers and ⚡ burst markers.

**Architecture:**
- Plain-JS IIFEs exposing `window.HB*`, with pure logic Node-tested.
- Depth reaches a page as `{"type":"depth", root, ts, bids, offers}` over `/ws`, once a chart shows that root: the top WIRE_LEVELS levels, ≤ 1 message per WIRE_MIN_S. A null ts means the book is gone.
- News arrives as `GET /api/news` plus the `/ws` messages `news`, `burst` and `burst_update`.
- The one backend addition is a read-only `GET /api/depth/history` over the recorded `~/futures_depth` files, used by the heatmap.

**Tech Stack:** Python 3 / FastAPI / pytest; Lightweight Charts 5.2.1 primitives; Node 26.

**Specs:**
- `docs/superpowers/specs/2026-09-27-charts-depth-design.md` §Part B.
- `docs/superpowers/specs/2026-09-27-charts-news-design.md` §Part B.
- The user approved building both on 2026-09-27 ("yes").

## Global Constraints

- **Read-only.** Nothing in this plan places, modifies or cancels orders. Click-to-trade on the ladder is out of scope ("Later" in the spec).
- **No new market-data requests.** Depth comes only from the existing subscriptions. The heatmap history reads recorded files; it never calls getChart and never writes to `~/futures_depth` or `~/futures_ticks`.
- **The chart service stays responsive.** File reads and gzip decoding run in a worker thread, with a bounded response size (≤ 2 MB, down-sampled). Nothing new runs heavy on the event loop.
- **All new routes sit behind the Host guard** (the `/api/*` middleware). Writes are JSON-only.
- **The page never rebuilds a panel or ladder on every message.** Patch in place, keyed rows, and at most 10 fps on the ladder.
- Lucide icons only. Look like TradingView (light default). No native dialogs. Every script tag carries `?v=7`. Bump from the live `?v=6` once, in the last task, and the desk's Charts link from `?v=4` to `?v=5`.

## Routing

| Task | Branch / worktree |
|---|---|
| 1 DOM ladder | `feat/charts-l2` / `.worktrees/l2` |
| 2 Big-order lines + imbalance gauge | `feat/charts-l2` |
| 3 Liquidity heatmap + depth history route | `feat/charts-l2` |
| 4 News panel + headline markers + ⚡ burst markers | `feat/charts-news-ui` / `.worktrees/newsui` (parallel) |

---

### Task 1: DOM ladder (read-only)

**Files:** a new `homebase/static/charts/dom.js` (pure: book → rows, recentre, session volume at price) and `domui.js` (the ladder DOM). The order panel's DOM tab (`orderpanel.js`) hosts the ladder, and a toolbar `DOM` button (Lucide `list-ordered`) opens the order panel on its DOM tab. Plus `charts.css`, `charts.html` and `icons.js`.

**Behaviour:**
- **Layout:** the ladder follows the SELECTED chart's root. It has price rows centred on the last trade, with the columns: bid size (blue) | price | ask size (red) | session volume at price.
  - Volume at price comes from the cell's loaded ticks/bars if they are available, otherwise it is blank.
  - Best bid/ask rows are highlighted.
  - The rows are the tick grid covering ±20 levels.
- **Markers:** the user's working orders on that root (from HBDeskClient state: the price and a qty chip) and the position's average price.
- **Recentre:** a button (and the Ctrl+Space shortcut only while the ladder has focus). Auto-recentre happens only when the last trade leaves the visible rows.
- **No book or stale book:** "No Level 2 for <root>" (roots without depth), or "Book stale" when ts is null.
- **Updates:** patch in place with keyed rows, at ≤ 10 fps.

**Tests (Node):** book → rows, including gaps in the book and a tick grid with epsilon; recentring; volume-at-price aggregation.

### Task 2: Big-order lines + imbalance gauge

**Files:** `dom.js` (pure: `bigLevels(book, history)` and `imbalance(book)`), plus two catalog entries under "Order flow" in `catalog.js`: `bigorders` (param: multiple, default 5) and `imbalance`. Also a per-cell overlay (`l2layer.js`) that draws price lines and the legend value, and `charts.css`.

**Behaviour:**
- **Big-order lines:**
  - A level whose displayed size is ≥ multiple × the median displayed size over the last 60 s of books for that root gets a labelled horizontal line, e.g. "500 @ 30,800".
  - Lines fade out over 5 s after the level falls below the threshold or disappears.
  - At most 8 lines per side.
- **Imbalance:** the legend shows Σ bid sizes − Σ ask sizes over the top 10 levels, as a percentage of the total, with a small bar (blue for bid-heavy, red for ask-heavy).
- **Scope:** both are per chart, on when the indicator is added, and show nothing when there is no depth.

**Tests:** the median window; the threshold; fade timing (injected clock); the cap; imbalance maths including empty sides.

### Task 3: Liquidity heatmap + depth history route

**Backend:**
- `GET /api/depth/history?root=NQ&from_ms=&to_ms=&cols=` reads the recorded `~/futures_depth/<ROOT>/<YYYY>/<date>_<contract>.depth.jsonl.gz` files for that range, in a worker thread.
- It returns a down-sampled grid: `{t0, dt_ms, tick, prices:[lo, hi], cells:[[t_idx, price_idx, size], ...]}`, with max 2 MB and at most `cols` (≤ 600) time columns. It handles a torn gzip tail gracefully.
- **Tests:** synthetic recorded files; a torn tail; the size cap; range clipping; a root with no files.

**Page:**
- A catalog indicator `heatmap` under "Order flow".
- A primitive drawn behind the candles: colour intensity by size, with a log scale, normalised per visible window.
- Data sources: a rolling live buffer of the last 2 h from depth messages (in memory, bounded), plus `/api/depth/history` for older visible ranges. It fetches on scroll-back and is cached per range.

**Tests (Node):** the grid → cell mapping; normalisation; the live buffer bound.

### Task 4: News panel + headline markers + ⚡ burst markers (parallel worktree)

**Files:** `homebase/static/charts/news.js` (pure) and `newsui.js` (panel + markers), plus a bottom-panel tab "News" (panel.js `addTab`), `charts.css` and `charts.html`.

**Behaviour:**
- **Panel:** a live headline stream, newest first.
  - Items show the source chip (FinancialJuice / Truth Social) and time (ET).
  - Trump posts are highlighted.
  - Tag chips come from the backend's `tags`.
  - A new item flashes for 3 s as "breaking".
  - A filter chip bar selects sources and tags.
- **Clicking a headline** jumps the selected chart to that time, reusing the tester layer's `jump`/`focusRange` if available, otherwise `scrollToTime`.
- **Headline markers:** small ticks on the time axis of each chart at the headline times, with the text on hover. They are merged through the extra-markers hook and capped per visible range.
- **Burst markers:** a ⚡ marker on charts of the burst's root at the burst time. The tooltip shows the ratio and the linked headlines (from `burst`/`burst_update` messages and `/api/news` links).
- **Updates:** the panel never rebuilds on quotes; it patches in place. Items are capped at 500 in memory.

**Tests (Node):** news merge/dedupe by id, filters, the burst ↔ headline link mapping, ET formatting.
