# Order-flow indicators, Plan B (client) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The chart page draws what Plan A's server now knows: the order book's history (ended big orders, absorption, pulled liquidity, imbalance / depth / microprice over time) and the new tick fields (trade bubbles, sweeps, stacked imbalances, unfinished auctions, prior-session profile, delta divergence, tape speed).

**Architecture:** One page-side store (`HBBookStore`) holds the book samples and order-level episodes, fed by `/api/book/history` and the live `bookflow` ws message. Book series are computed in the page from it (`bk:` keys, never sent to the server); one overlay draws the order-level marks; the existing footprint / profile layers and the series-markers plugin take small extras. Every new module is Node-testable (IIFE with a `module.exports`, the pattern of `dom.js`).

**Tech Stack:** Plain JavaScript (no build step), Lightweight Charts 5.2.1, Node's built-in test runner (`node --test tests/js/*.test.mjs`).

**Spec:** `docs/superpowers/specs/2026-10-11-orderflow-indicators-design.md` (read §4.4-4.5 and §7). **Plan A** (`docs/superpowers/plans/2026-10-11-orderflow-plus-server.md`) must be done first: this plan asks for `flow`, `bookflow` and `/api/book/history`, and uses the `prev` profile and the `ddiv` / `tspeed` studies.

## Global Constraints

- Same worktree as Plan A (`feat/orderflow-plus`). The page files this plan touches (`catalog.js`, `cell.js`, `app.js`, `charts.html`, `backtest.html`) have **uncommitted edits from other sessions** in the main checkout (about 200 lines in `catalog.js`, 70 in `cell.js`, 300 in `app.js`; every `?v=` number). The hunks below are against `main`; before each task run `git diff main -- <file>` and apply by hand, anchored by the names in the hunks. Take the `?v=` numbers last, as the larger of this plan's and `main`'s.
- No new dependency, no build step, no new global beyond the five named here (`HBBookStore`, `HBFlowMath`, `HBFlowDefs`, `HBBookEvents`, `HBFlowLayer`).
- Never send a `bk:` key to the server. Never ask for `flow` unless an option wants it.
- A chart on a root with no recorded depth, an older service, a refused or paused history request, or a page with no book store (the Backtest tab) must show gaps, never an error or a zero.
- No strategy claim is made from any of these indicators; every verdict number is a first guess (Plan A: `bookflow.TUNING`).
- Commit trailer on each commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; no push unless the owner asks.
- The restart of the chart service is gated (Plan A, Task 6, Step 7); the page files load without one.

## Review Focus

- **No book behind the chart** (a root without recorded depth, a 404 / 503 from `/api/book/history`, the store not loaded): the series are gaps and the overlay backs off (2 s busy, 60 s paused, 30 s otherwise); no exception, no console error (tests in Tasks 1 and 4).
- **Saved layouts from before**: every new parameter has a default, so an old saved chart loads and a footprint now also shows stacked imbalances, unfinished auctions and the delta number (tests in Task 3; the owner can switch them off in the footprint's settings).
- **Tick / range / volume bars**: no fixed length, so a bar ends where the next one starts (test in Task 4).
- **A hidden indicator that wants `flow`** still counts, so showing it again is instant (test in Task 4).
- **Zoomed out**: the footprint extras draw only where the cells are readable; the profile's ghost only with the profile on (test in Task 5).
- **Bar Replay**: no book fetch and nothing past the replay cursor (Task 6, Step 2 of Task 7: the code is browser-only, so this is checked by eye).

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `homebase/static/charts/bookstore.js` | Create | `HBBookStore`: samples + episodes per root, history fetch, live apply |
| `homebase/static/charts/flowmath.js` | Create | `HBFlowMath`: stacked / unfinished / sizes, pure |
| `homebase/static/charts/flowdefs.js` | Create | the new catalog entries (`ta`, `catalog`, `bookValue`) |
| `homebase/static/charts/bookevents.js` | Create | `HBBookEvents`: ended big orders, absorption, pulled; drives `refreshBookSeries` |
| `homebase/static/charts/flowlayer.js` | Create | `HBFlowLayer`: heatmap trade bubbles, sweeps |
| `homebase/static/charts/catalog.js` | Modify | merge the definitions, new params, `bk:` filter, style keys |
| `homebase/static/charts/cell.js` | Modify | `flow` request, book series, study markers, layer extras |
| `homebase/static/charts/primitives.js` | Modify | footprint extras, profile ghost and lines |
| `homebase/static/charts/app.js`, `charts.html`, `backtest.html` | Modify | route `bookflow`, push overlays, script tags, `?v=` |
| `tests/js/bookstore`, `flowmath`, `flowdefs`, `bookevents`, `orderflow-cell`, `orderflow-primitives` `.test.mjs` | Create | new behaviour |
| `tests/js/catalog`, `cell-bardata`, `cell-window` `.test.mjs` | Modify | defaults, filter lists, `flow` in the messages |

---

### Task 1: `HBBookStore`, the page's book samples and order-level episodes

**Files:**
- Create: `homebase/static/charts/bookstore.js`, `tests/js/bookstore.test.mjs`

**Interfaces:**
- Consumes: the server's `GET /api/book/history?root=&from_ms=&to_ms=` answer `{tick, step, t0, t1, samples, episodes}` and the ws message `{"type": "bookflow", "root", "reset", "samples", "episodes"}` (Plan A, Tasks 4-6). A sample row is `[t_ms, bid10, ask10, imb1, imb5, imb10, micro, spread_ticks]`; an episode is `{id, s: "b"|"a", p, t0, t1, pk, r, tr, end, ab, d0}`.
- Produces (`window.HBBookStore`, also `module.exports`): `COL` (`{b10: 1, a10: 2, imb1: 3, imb5: 4, imb10: 5, micro: 6, spread: 7}`), `applyHistory(root, body)`, `applyLive(msg)`, `meanAt(root, a_ms, b_ms, colKey) -> number | null` (mean of that column over the samples with `a <= t < b`, nulls ignored), `episodes(root, from_ms, to_ms) -> ep[]` (overlapping, oldest first), `missing(root, from, to, now) -> [[from, to], ...]` (aligned 5 h chunks not yet covered), `retryAfter(status, detail) -> ms`, `onChange(fn(root, kind)) -> unsubscribe` (`kind` = `"history"` | `"live"`), `clear()`, `rowCount(root)`, and in a browser `ensure(root, from, to)` (fetches one missing chunk, backs off on a refusal: 2 s when `busy`, 60 s when paused, 30 s otherwise).

One place every book indicator reads from. Rows merge by `t` (the later copy wins), the store holds at most 400,000 rows a root (the oldest go first), episodes merge by `id`, and a fetched span is remembered so a window is asked for once.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/bookstore.test.mjs`:

```javascript
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/bookstore.js');
const T0 = 1_790_000_000_000;
const row = (i, imb = 0.1, micro = 100) => [T0 + i * 1000, 20, 30, imb, imb, imb, micro, 1];
beforeEach(() => S.clear());

test('meanAt averages a column over [a, b), ignoring nulls, null when empty', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 5000, samples: [row(0, 0.2), row(1, 0.4), row(2, 0.6, null), row(3, 0.8)], episodes: [] });
  assert.ok(Math.abs(S.meanAt('NQ', T0, T0 + 3000, 'imb10') - 0.4) < 1e-9);
  assert.equal(S.meanAt('NQ', T0, T0 + 4000, 'micro'), 100);
  assert.equal(S.meanAt('NQ', T0 + 9000, T0 + 12000, 'imb10'), null);
  assert.equal(S.meanAt('ES', T0, T0 + 4000, 'imb10'), null);
  assert.equal(S.meanAt('NQ', T0 + 3000, T0, 'imb10'), null);
});

test('rows merge by t: later copy wins, order kept, out-of-order batches fine', () => {
  S.applyLive({ root: 'NQ', samples: [row(5, 0.5), row(6, 0.6)] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 7000, samples: [row(0, 0.1), row(5, 0.9)], episodes: [] });
  assert.equal(S.rowCount('NQ'), 3);
  assert.equal(S.meanAt('NQ', T0 + 5000, T0 + 6000, 'imb10'), 0.9);
});

test('episodes upsert by id and overlap queries include open ones', () => {
  S.applyLive({ root: 'NQ', samples: [], episodes: [{ id: 'b1_1', s: 'b', p: 100, t0: T0, t1: null, pk: 20, r: 5, tr: 0, end: 'open', ab: null, d0: 1 }] });
  assert.equal(S.episodes('NQ', T0 + 10_000, T0 + 20_000).length, 1);
  S.applyLive({ root: 'NQ', samples: [], episodes: [{ id: 'b1_1', s: 'b', p: 100, t0: T0, t1: T0 + 5000, pk: 20, r: 5, tr: 30, end: 'traded', ab: null, d0: 1 }] });
  const e = S.episodes('NQ', T0 + 10_000, T0 + 20_000);
  assert.equal(e.length, 0);                                   // ended before the window
  assert.equal(S.episodes('NQ', T0, T0 + 20_000)[0].end, 'traded');
});

test('missing: aligned chunks not covered, clipped to now; covered ones are not asked again', () => {
  const C = S.CHUNK_MS, base = Math.floor(T0 / C) * C, now = base + C + 600_000;
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base, base + C], [base + C, now]]);
  S.applyHistory('NQ', { t0: base, t1: base + C, samples: [], episodes: [] });
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base + C, now]]);
});

test('change listeners fire once per applied message and can be removed', () => {
  let n = 0;
  const off = S.onChange(() => { n++; });
  S.applyLive({ root: 'NQ', samples: [row(0)] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 1000, samples: [], episodes: [] });
  off();
  S.applyLive({ root: 'NQ', samples: [row(1)] });
  assert.equal(n, 2);
});

test('junk input is dropped, never thrown', () => {
  S.applyLive(null); S.applyLive({}); S.applyHistory('NQ', null);
  S.applyLive({ root: 'NQ', samples: ['x', [NaN], null], episodes: [null, { id: 3 }] });
  assert.equal(S.rowCount('NQ'), 0);
});

test('onChange tells history from live', () => {
  const seen = [];
  const off = S.onChange((root, kind) => seen.push([root, kind]));
  S.applyHistory('NQ', { t0: T0, t1: T0 + 3000, samples: [row(0)], episodes: [] });
  S.applyLive({ root: 'NQ', samples: [row(5)], episodes: [] });
  off();
  S.applyLive({ root: 'NQ', samples: [row(6)], episodes: [] });
  assert.deepEqual(seen, [['NQ', 'history'], ['NQ', 'live']]);
});

test('retryAfter: busy clears in seconds, a paused window in a minute, anything else in half a minute', () => {
  assert.equal(S.retryAfter(503, 'busy — try again in a moment'), 2000);
  assert.equal(S.retryAfter(503, 'chart history is paused 09:20-09:35 ET'), 60_000);
  assert.equal(S.retryAfter(503, null), 60_000);
  assert.equal(S.retryAfter(404, 'unknown root'), 30_000);
  assert.equal(S.retryAfter(0, null), 30_000);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/bookstore.test.mjs`
Expected: FAIL (`Cannot find module '../../homebase/static/charts/bookstore.js'`).

- [ ] **Step 3: Implement**

Create `homebase/static/charts/bookstore.js`:

```javascript
/* Homebase Charts — HBBookStore: the Level 2 book's per-second samples and order-level episodes, per root.
   One store for every book indicator (big orders, absorption, pulled liquidity, imbalance, depth, microprice).
   Three sources, one shape:
     - GET /api/book/history?root&from_ms&to_ms  -> {tick, step, t0, t1, samples: [row, ...], episodes: [ep, ...]}
     - the ws message {"type":"bookflow", root, reset?, samples, episodes} (the server's live tracker)
   row = [t, bid10, ask10, imb1, imb5, imb10, micro, spread] (bookflow.py), ep = {id, s, p, t0, t1, pk, r, tr, end, ab, d0}.
   Pure data (top half, Node-tested) + a small fetch scheduler (bottom, browser only). */
(function () {
'use strict';

const COL = { b10: 1, a10: 2, imb1: 3, imb5: 4, imb10: 5, micro: 6, spread: 7 };
const CHUNK_MS = 5 * 3600 * 1000;      // history is asked in aligned 5 h chunks: 18,000 samples, always 1 s steps
const MAX_ROWS = 400_000;              // per root; the oldest go first
const GAP_OK_MS = 120_000;             // a chunk is "covered" when its covered span is within this of its end

class RootStore {
  constructor() {
    this.rows = [];                    // sorted by t, one per t
    this.eps = new Map();              // id -> episode
    this.cov = [];                     // merged [from, to) spans a request (or the live feed) answered
  }

  addRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return;
    const clean = rows.filter((r) => Array.isArray(r) && Number.isFinite(r[0]));
    if (!clean.length) return;
    const last = this.rows.length ? this.rows[this.rows.length - 1][0] : -Infinity;
    const sorted = clean.every((r, i) => i === 0 || r[0] > clean[i - 1][0]);
    if (sorted && clean[0][0] > last) {
      for (const r of clean) this.rows.push(r);
    } else {                           // out of order or overlapping: merge, the later copy of a t wins
      const m = new Map();
      for (const r of this.rows) m.set(r[0], r);
      for (const r of clean) m.set(r[0], r);
      this.rows = [...m.values()].sort((a, b) => a[0] - b[0]);
    }
    if (this.rows.length > MAX_ROWS) this.rows.splice(0, this.rows.length - MAX_ROWS);
  }

  addEpisodes(list) {
    for (const e of Array.isArray(list) ? list : []) {
      if (e && typeof e.id === 'string' && Number.isFinite(e.t0)) this.eps.set(e.id, e);
    }
  }

  cover(from, to) {
    if (!(to > from)) return;
    const spans = [...this.cov, [from, to]].sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const s of spans) {
      const l = out[out.length - 1];
      if (l && s[0] <= l[1] + 1000) l[1] = Math.max(l[1], s[1]); else out.push([s[0], s[1]]);
    }
    this.cov = out;
  }

  /* index of the first row with t >= x */
  lower(x) {
    let lo = 0, hi = this.rows.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (this.rows[m][0] < x) lo = m + 1; else hi = m; }
    return lo;
  }
}

const stores = new Map();
const listeners = new Set();
const of = (root) => { let s = stores.get(root); if (!s) { s = new RootStore(); stores.set(root, s); } return s; };
const changed = (root, kind) => { for (const f of listeners) { try { f(root, kind); } catch (_) { /* a listener never breaks the store */ } } };

/* The history answer: samples + episodes, and the span it covers. */
function applyHistory(root, body) {
  if (!body || typeof root !== 'string') return;
  const s = of(root);
  s.addRows(body.samples);
  s.addEpisodes(body.episodes);
  if (Number.isFinite(body.t0) && Number.isFinite(body.t1)) s.cover(body.t0, body.t1);
  changed(root, 'history');
}

/* A live ws message. reset: the server's snapshot (a new page, or a page that fell behind) replaces what the
   live feed gave; history-fetched rows stay (they are merged by t). */
function applyLive(m) {
  if (!m || typeof m.root !== 'string') return;
  const s = of(m.root);
  s.addRows(m.samples);
  s.addEpisodes(m.episodes);
  const t = (Array.isArray(m.samples) ? m.samples : []).filter((r) => Array.isArray(r) && Number.isFinite(r[0])).map((r) => r[0]);
  if (t.length) s.cover(Math.min(...t), Math.max(...t) + 1000);
  changed(m.root, 'live');
}

/* Mean of column `col` (a COL key) over the samples with a <= t < b; null when there is none. */
function meanAt(root, a, b, col) {
  const s = stores.get(root), c = COL[col];
  if (!s || !c || !(b > a)) return null;
  let sum = 0, n = 0;
  for (let i = s.lower(a); i < s.rows.length && s.rows[i][0] < b; i++) {
    const v = s.rows[i][c];
    if (typeof v === 'number' && Number.isFinite(v)) { sum += v; n++; }
  }
  return n ? sum / n : null;
}

/* Episodes overlapping [from, to), oldest first. */
function episodes(root, from, to) {
  const s = stores.get(root);
  if (!s) return [];
  const out = [];
  for (const e of s.eps.values()) if (e.t0 < to && (e.t1 == null || e.t1 >= from)) out.push(e);
  return out.sort((x, y) => x.t0 - y.t0);
}

/* The aligned chunks of [from, to) (to clipped to now) that are not covered, as [from, to) pairs. */
function missing(root, from, to, now) {
  const s = of(root), end = Math.min(to, now), out = [];
  if (!(end > from)) return out;
  for (let c = Math.floor(from / CHUNK_MS) * CHUNK_MS; c < end; c += CHUNK_MS) {
    const a = Math.max(c, from), b = Math.min(c + CHUNK_MS, end);
    const hit = s.cov.some((x) => x[0] <= a + GAP_OK_MS && x[1] >= b - GAP_OK_MS);
    if (!hit) out.push([c, Math.min(c + CHUNK_MS, now)]);
  }
  return out;
}

/* Milliseconds to leave a refused chunk alone: a busy answer clears in seconds, a paused window (09:20-09:35 ET, the
   tester's gate) is retried a minute on, anything else (a missing endpoint, a network error: status 0) half a minute. */
function retryAfter(status, detail) { return status === 503 ? (/^busy/.test(String(detail || '')) ? 2000 : 60_000) : 30_000; }

/* fn(root, kind): kind 'history' (a fetched window landed: redraw whole) or 'live' (a second or an episode: the newest
   bars only). Returns the unsubscribe. */
function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function clear() { stores.clear(); }
function rowCount(root) { const s = stores.get(root); return s ? s.rows.length : 0; }

const api = { COL, CHUNK_MS, applyHistory, applyLive, meanAt, episodes, missing, retryAfter, onChange, clear, rowCount };

/* ---------------------------------------------------------------- browser */
if (typeof window !== 'undefined') {
  const pending = new Set(), blocked = new Map();

  /* Ask for what [from, to) lacks, one chunk at a time per root; never while backing off. */
  api.ensure = async function ensure(root, from, to) {
    const now = Date.now();
    for (const [a, b] of missing(root, from, to, now)) {
      const key = `${root}|${a}`;
      if (pending.has(key) || (blocked.get(key) || 0) > now) continue;
      pending.add(key);
      try {
        const q = new URLSearchParams({ root, from_ms: String(a), to_ms: String(b) });
        const r = await fetch('/api/book/history?' + q);
        if (r.ok) { applyHistory(root, await r.json()); blocked.delete(key); }
        else {
          let detail = null;
          try { detail = (await r.json()).detail; } catch (_) { /* no JSON body */ }
          blocked.set(key, Date.now() + retryAfter(r.status, detail));
        }
      } catch (_) {
        blocked.set(key, Date.now() + retryAfter(0, null));
      } finally {
        pending.delete(key);
      }
      break;                           // one chunk per call: the caller asks again on the next change
    }
  };
  window.HBBookStore = api;
}
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/bookstore.test.mjs`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/bookstore.js tests/js/bookstore.test.mjs
git commit -m "feat(charts): HBBookStore - book samples and order-level episodes per root" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 2: `HBFlowMath`, the footprint extras and marker sizes as pure functions

**Files:**
- Create: `homebase/static/charts/flowmath.js`, `tests/js/flowmath.test.mjs`

**Interfaces:**
- Produces (`window.HBFlowMath`, also `module.exports`): `imbalances(fp, tick, ratio) -> {buy: Set, sell: Set}`, `stackedRuns(fp, tick, ratio, stack) -> [{side: "buy"|"sell", from, to, n}]` (runs of `stack` or more price rows **in a row** carrying one side's imbalance), `unfinished(fp) -> {high, low, hi, lo}` (the top / bottom row traded on **both** sides), `bubbleRadius(size, min, max, rMin = 3, rMax = 14) -> px`, `markerSize(size, min, scale) -> 0.6..2.2` (Lightweight Charts marker size; `0.6` when `scale` is off), `bubblesOf(bar, min) -> [{t, price, size, side}]` (from the bar's `bub`, `t` = the middle of that second), `sweepsOf(bar, min) -> [{t, from, to, size, side}]` (from `sw`). `fp` is the bar wire's `[[price, sellAtBid, buyAtAsk], ...]`.

The imbalance rule is the one the footprint already draws (buys at P against sells one tick below, sells at P against buys one tick above, at `ratio`:1).

- [ ] **Step 1: Write the failing tests**

Create `tests/js/flowmath.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = require('../../homebase/static/charts/flowmath.js');
const T = 0.25;

test('imbalances: buys against the sells one tick below, sells against the buys one tick above', () => {
  const r = M.imbalances([[100, 10, 1], [100.25, 2, 8], [100.5, 1, 9]], T, 3);
  assert.deepEqual([...r.buy], [402]);       // 9 buys vs 2 sells below; 8 vs 10 is not
  assert.deepEqual([...r.sell], []);
  assert.deepEqual([...M.imbalances([[100, 5, 5]], T, 0).buy], []);   // ratio 0 = off
});

test('stackedRuns: three in a row on one side make a run; a gap row or a short run does not', () => {
  const four = [[100, 1, 9], [100.25, 1, 9], [100.5, 1, 9], [100.75, 1, 9]];
  assert.deepEqual(M.stackedRuns(four, T, 3, 3), [{ side: 'buy', from: 100, to: 100.75, n: 4 }]);
  const two = [[100, 1, 9], [100.25, 1, 9]];
  assert.deepEqual(M.stackedRuns(two, T, 3, 3), []);
  const gap = [[100, 1, 9], [100.25, 1, 9], [100.75, 1, 9], [101, 1, 9]];   // 100.5 is missing: two runs of two
  assert.deepEqual(M.stackedRuns(gap, T, 3, 3), []);
  const sells = [[100, 9, 1], [100.25, 9, 1], [100.5, 9, 1], [100.75, 9, 1]];   // sells at P vs buys above: 9 vs 1 (the top row has none above)
  assert.deepEqual(M.stackedRuns(sells, T, 3, 3), [{ side: 'sell', from: 100, to: 100.75, n: 4 }]);
});

test('unfinished: both sides traded at the top / bottom row', () => {
  assert.deepEqual(M.unfinished([[100, 0, 5], [100.25, 3, 4], [100.5, 2, 2]]),
    { high: true, low: false, hi: 100.5, lo: 100 });
  assert.deepEqual(M.unfinished([[100, 3, 5], [100.5, 0, 7]]), { high: false, low: true, hi: 100.5, lo: 100 });
  assert.equal(M.unfinished([]).high, false);
});

test('bubbleRadius grows with the size and is clamped', () => {
  assert.equal(M.bubbleRadius(0, 10, 200), 0);
  assert.equal(M.bubbleRadius(10, 10, 200), 3);
  assert.equal(M.bubbleRadius(5000, 10, 200), 14);
  assert.ok(M.bubbleRadius(50, 10, 200) < M.bubbleRadius(100, 10, 200));
});

test('markerSize: off is 0.6; on grows with the size from the minimum and stops at 8x', () => {
  assert.equal(M.markerSize(100, 10, false), 0.6);
  assert.equal(M.markerSize(10, 10, true), 0.6);
  assert.equal(M.markerSize(80, 10, true), 2.2);
  assert.equal(M.markerSize(9999, 10, true), 2.2);
  assert.ok(M.markerSize(20, 10, true) > 0.6 && M.markerSize(20, 10, true) < M.markerSize(40, 10, true));
});

test('bubblesOf / sweepsOf: filtered by size, a bar without the fields gives none', () => {
  const bar = { bub: [[1000, 100, 4, 1], [1001, 100.25, 30, -1]], sw: [[5000, 100, 101, 12, 1], [6000, 100, 100.5, 3, -1]] };
  assert.deepEqual(M.bubblesOf(bar, 10), [{ t: 1_001_500, price: 100.25, size: 30, side: -1 }]);
  assert.equal(M.bubblesOf(bar, 3).length, 2);
  assert.deepEqual(M.sweepsOf(bar, 10), [{ t: 5000, from: 100, to: 101, size: 12, side: 1 }]);
  assert.deepEqual(M.bubblesOf({}, 1), []);
  assert.deepEqual(M.sweepsOf(null, 1), []);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/flowmath.test.mjs`
Expected: FAIL (`Cannot find module ... flowmath.js`).

- [ ] **Step 3: Implement**

Create `homebase/static/charts/flowmath.js`:

```javascript
/* Homebase Charts — HBFlowMath: the footprint's extra marks as pure functions of one bar's rows, so they are Node-tested.
   fp = [[price, sellAtBid, buyAtAsk], ...] (any order), tick = the market's tick size. Nothing here touches the DOM. */
(function () {
'use strict';

const key = (px, tick) => Math.round(px / tick);

/* Diagonal imbalances at `ratio`:1, the rule the Footprint layer already draws: buys at P against sells one tick
   below, sells at P against buys one tick above. Returns {buy: Set(key), sell: Set(key)}. ratio <= 0: none. */
function imbalances(fp, tick, ratio) {
  const buy = new Set(), sell = new Set();
  if (!(ratio > 0) || !Array.isArray(fp) || !fp.length) return { buy, sell };
  const at = new Map(fp.map((r) => [key(r[0], tick), r]));
  for (const [px, sv, bv] of fp) {
    const k = key(px, tick), below = at.get(k - 1), above = at.get(k + 1);
    if (bv > 0 && bv >= ratio * Math.max(below ? below[1] : 0, 1)) buy.add(k);
    if (sv > 0 && sv >= ratio * Math.max(above ? above[2] : 0, 1)) sell.add(k);
  }
  return { buy, sell };
}

/* Runs of `stack` or more price rows IN A ROW (no empty row between) that all carry the same side's imbalance:
   [{side: 'buy'|'sell', from: price, to: price, n}], from < to, ascending. */
function stackedRuns(fp, tick, ratio, stack) {
  const need = Math.max(2, Math.floor(stack) || 3), out = [];
  const { buy, sell } = imbalances(fp, tick, ratio);
  for (const [side, set] of [['buy', buy], ['sell', sell]]) {
    const ks = [...set].sort((a, b) => a - b);
    let s = 0;
    for (let i = 1; i <= ks.length; i++) {
      if (i < ks.length && ks[i] === ks[i - 1] + 1) continue;
      const n = i - s;
      if (n >= need) out.push({ side, from: ks[s] * tick, to: ks[i - 1] * tick, n });
      s = i;
    }
  }
  return out.sort((a, b) => a.from - b.from || (a.side < b.side ? -1 : 1));
}

/* Unfinished auction: the bar's top row traded on BOTH sides (the auction did not end with only one side left),
   and the same at the bottom row. A one-sided extreme is finished. {high: bool, low: bool, hi: price, lo: price}. */
function unfinished(fp) {
  if (!Array.isArray(fp) || !fp.length) return { high: false, low: false, hi: null, lo: null };
  let hi = fp[0], lo = fp[0];
  for (const r of fp) { if (r[0] > hi[0]) hi = r; if (r[0] < lo[0]) lo = r; }
  return { high: hi[1] > 0 && hi[2] > 0, low: lo[1] > 0 && lo[2] > 0, hi: hi[0], lo: lo[0] };
}

/* Bubble radius in px for `size` contracts: the area follows the size between `min` and `max` contracts. */
function bubbleRadius(size, min, max, rMin = 3, rMax = 14) {
  if (!(size > 0)) return 0;
  const lo = Math.max(1, min), hi = Math.max(lo + 1, max);
  const t = Math.min(1, Math.max(0, (size - lo) / (hi - lo)));
  return rMin + (rMax - rMin) * Math.sqrt(t);
}

/* A series marker's `size` (Lightweight Charts: 0.5 .. 3) for a print of `size` contracts when the chart scales big
   prints by size: 0.6 at `min`, 2.2 at 8 x `min` and beyond. Off (scale false): 0.6, as always. */
function markerSize(size, min, scale) {
  if (!scale || !(size > 0) || !(min > 0)) return 0.6;
  const t = Math.min(1, Math.max(0, Math.log2(size / min) / 3));
  return Math.round((0.6 + 1.6 * t) * 100) / 100;
}

/* Trade bubbles of one bar for the heatmap: rows [sec, price, size, side] with size >= min, as {t, price, size, side}
   (t = the middle of that second). A bar without `bub` (the chart did not ask for it) gives none. */
function bubblesOf(bar, min) {
  const out = [];
  for (const r of (bar && bar.bub) || []) {
    if (Array.isArray(r) && r[2] >= min) out.push({ t: r[0] * 1000 + 500, price: r[1], size: r[2], side: r[3] });
  }
  return out;
}

/* Sweeps of one bar: rows [ts_ms, from, to, size, side] with size >= min, as {t, from, to, size, side}. */
function sweepsOf(bar, min) {
  const out = [];
  for (const r of (bar && bar.sw) || []) {
    if (Array.isArray(r) && r[3] >= min) out.push({ t: r[0], from: r[1], to: r[2], size: r[3], side: r[4] });
  }
  return out;
}

const api = { imbalances, stackedRuns, unfinished, bubbleRadius, markerSize, bubblesOf, sweepsOf };
if (typeof window !== 'undefined') window.HBFlowMath = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/flowmath.test.mjs`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/flowmath.js tests/js/flowmath.test.mjs
git commit -m "feat(charts): HBFlowMath - stacked imbalances, unfinished auctions, bubble and marker sizes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 3: The catalog: `flowdefs.js`, new parameters, `bk:` keys never go to the server

**Files:**
- Create: `homebase/static/charts/flowdefs.js`, `tests/js/flowdefs.test.mjs`
- Modify: `homebase/static/charts/catalog.js`, `tests/js/catalog.test.mjs`

**Interfaces:**
- Consumes: nothing new (the catalog is data).
- Produces: `window.HBFlowDefs` = `{ta, catalog, bookValue}`. **`ta`** (merged at the end of `TA_DEFS`, so each has a `key(params)`, `label`, `lines`, `refs`, `pane` like the technical indicators): `bkimb` (key `bk:imb<1|5|10>`, own pane, param `levels`), `bkdepth` (`bk:depth`, own pane, lines `b10` / `a10`), `bkmicro` (`bk:micro`, price pane), `tspeed` (`tspeed:<n>`, own pane, lines `rate` / `hot` / `burst`; `rate` and `hot` are `fixed` histograms), `ddiv` (`ddiv:<n>`, no lines, a `marks(v, P)` function). **`catalog`** (merged after `heatmap`): `absorb` and `pulled`, no series, drawn by `HBBookEvents` (Task 6). A key starting `bk:` is computed in the page; `catalog.serverKeys` drops it. `bookValue(key, mean) -> number | {b10, a10} | null`.
- New parameters (all with defaults, so a saved layout loads unchanged): `footprint` `stack` (int 0-20, default 3, 0 = off), `unfinished` (bool, true), `deltaNum` (bool, true); `profile` `prior` (bool, true), `lines` (bool, false); `bigprints` `scale` (bool, true), `sweeps` (bool, false); `bigorders` `minSeconds` (int 1-600, 5), `history` (bool, true); `heatmap` `bubbles` (bool, false), `bubbleMin` (int 1-10,000, 10). `styleLineKeys` is `null` for a study with no lines (`ddiv`), so it gets no Style tab. Every `desc` stays within the Indicators dialog's 20-85 characters.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/flowdefs.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const D = require('../../homebase/static/charts/flowdefs.js');

test('every definition has the fields catalog.js reads', () => {
  for (const d of [...D.ta, ...D.catalog]) {
    assert.ok(d.id && d.group && d.name && Array.isArray(d.params) && d.desc, d.id);
  }
  for (const d of D.ta) {
    assert.equal(typeof d.key, 'function', d.id);
    assert.equal(typeof d.label, 'function', d.id);
    const p = Object.fromEntries(d.params.map((x) => [x.key, x.def]));
    assert.match(d.key(p), /^[a-z0-9:]+$/, d.id);
    assert.ok(Array.isArray(d.lines), d.id);
  }
  assert.equal(new Set([...D.ta, ...D.catalog].map((d) => d.id)).size, D.ta.length + D.catalog.length);
});

test('book series keys start with bk: and name a store column; server studies do not', () => {
  const byId = Object.fromEntries(D.ta.map((d) => [d.id, d]));
  assert.equal(byId.bkimb.key({ levels: '5' }), 'bk:imb5');
  assert.equal(byId.bkdepth.key({}), 'bk:depth');
  assert.deepEqual(byId.bkdepth.lines.map((l) => l.col), ['b10', 'a10']);
  assert.equal(byId.bkmicro.key({}), 'bk:micro');
  assert.equal(byId.tspeed.key({ length: 200 }), 'tspeed:200');
  assert.equal(byId.ddiv.key({ length: 5 }), 'ddiv:5');
});

test('ddiv marks: a divergence at the swing, nothing otherwise', () => {
  const m = D.ta.find((d) => d.id === 'ddiv').marks;
  assert.equal(m(null, {}), null);
  assert.equal(m({}, {}), null);
  assert.deepEqual(m({ dir: -1, ago: 5, px: 12 }, {}), { position: 'aboveBar', color: '#F23645', shape: 'arrowDown', text: 'Δ', size: 1, ago: 5 });
  assert.equal(m({ dir: 1, ago: 5, px: 4 }, {}).position, 'belowBar');
});

test('bookValue: a number for one column, an object for the depth pair, null while the store has nothing', () => {
  const mean = (m) => (col) => (col in m ? m[col] : null);
  assert.equal(D.bookValue('bk:imb5', mean({ imb5: 0.25 })), 0.25);
  assert.equal(D.bookValue('bk:micro', mean({})), null);
  assert.deepEqual(D.bookValue('bk:depth', mean({ b10: 10, a10: 30 })), { b10: 10, a10: 30 });
  assert.deepEqual(D.bookValue('bk:depth', mean({ b10: 10 })), { b10: 10, a10: null });
  assert.equal(D.bookValue('bk:depth', mean({})), null);
});

test('only the tape speed histograms keep a colour of their own', () => {
  const t = D.ta.find((d) => d.id === 'tspeed');
  assert.deepEqual(t.lines.map((l) => [l.part, !!l.fixed]), [['rate', true], ['hot', true], ['burst', false]]);
  assert.ok(D.ta.filter((d) => d.id !== 'tspeed').every((d) => d.lines.every((l) => !l.fixed)));
});
```

Update `tests/js/catalog.test.mjs` (the defaults of the five changed indicators, the filter lists and two new checks):

```diff
--- a/tests/js/catalog.test.mjs
+++ b/tests/js/catalog.test.mjs
@@ -14,7 +14,7 @@ test('a new chart gets volume, VWAP (ETH), session levels and a 3x footprint', (
     { id: 'volume', params: {}, visible: true },
     { id: 'vwap', params: VWAP_DEFAULT_PARAMS, visible: true },
     { id: 'levels', params: {}, visible: true },
-    { id: 'footprint', params: { imbalance: 3 }, visible: true }]);
+    { id: 'footprint', params: { imbalance: 3, stack: 3, unfinished: true, deltaNum: true }, visible: true }]);
 });
 
 test('every instance gets its own short uid', () => {
@@ -62,14 +62,17 @@ test('params are clamped to their range and type', () => {
   assert.deepEqual(C.clampParams('ema', { length: 20, source: 'bogus' }), { length: 20, source: 'close' });
   assert.deepEqual(C.clampParams('sma', { length: 20, source: 'ohlc4' }), { length: 20, source: 'ohlc4' });
   assert.deepEqual(C.clampParams('vwma', { length: 9 }), { length: 9 });   // no Source param for VWMA
-  assert.deepEqual(C.clampParams('footprint', { imbalance: 2.5 }), { imbalance: 2.5 });
-  assert.deepEqual(C.clampParams('footprint', { imbalance: -1 }), { imbalance: 0 });
-  assert.deepEqual(C.clampParams('bigprints', { min: 0 }), { min: 1 });
-  assert.deepEqual(C.clampParams('bigorders', {}), { multiple: 5 });
-  assert.deepEqual(C.clampParams('bigorders', { multiple: 0 }), { multiple: 1 });
-  assert.deepEqual(C.clampParams('bigorders', { multiple: 999 }), { multiple: 50 });
+  assert.deepEqual(C.clampParams('footprint', { imbalance: 2.5 }), { imbalance: 2.5, stack: 3, unfinished: true, deltaNum: true });
+  assert.deepEqual(C.clampParams('footprint', { imbalance: -1 }), { imbalance: 0, stack: 3, unfinished: true, deltaNum: true });
+  assert.deepEqual(C.clampParams('footprint', { stack: 99, unfinished: 'x' }), { imbalance: 3, stack: 20, unfinished: true, deltaNum: true });
+  assert.deepEqual(C.clampParams('bigprints', { min: 0 }), { min: 1, scale: true, sweeps: false });
+  assert.deepEqual(C.clampParams('bigorders', {}), { multiple: 5, minSeconds: 5, history: true });
+  assert.deepEqual(C.clampParams('bigorders', { multiple: 0 }), { multiple: 1, minSeconds: 5, history: true });
+  assert.deepEqual(C.clampParams('bigorders', { multiple: 999, minSeconds: 0, history: false }), { multiple: 50, minSeconds: 1, history: false });
+  assert.deepEqual(C.clampParams('heatmap', { bubbles: true, bubbleMin: 0 }), { bubbles: true, bubbleMin: 1 });
+  assert.deepEqual(C.clampParams('profile', {}), { prior: true, lines: false });
   assert.deepEqual(C.clampParams('imbalance', { junk: 1 }), {});
-  assert.deepEqual(C.clampParams('heatmap', { junk: 1 }), {});
+  assert.deepEqual(C.clampParams('heatmap', { junk: 1 }), { bubbles: false, bubbleMin: 10 });
   assert.deepEqual(C.clampParams('vwap', { anchor: 'xyz', customTime: 'nope' }), VWAP_DEFAULT_PARAMS);
   assert.deepEqual(C.clampParams('vwap', { anchor: 'rth', junk: 1 }), { ...VWAP_DEFAULT_PARAMS, anchor: 'rth' });
   // "9:30" is loose keyboard entry, not an error: it normalises to "09:30" like the other shorthands do
@@ -102,9 +105,9 @@ test('a Build-1 chart (st form) migrates field by field', () => {
     { id: 'delta', params: {}, visible: true },
     { id: 'cumdelta', params: {}, visible: true },
     { id: 'adx', params: { length: 14 }, visible: true },
-    { id: 'footprint', params: { imbalance: 4 }, visible: true },
-    { id: 'profile', params: {}, visible: true },
-    { id: 'bigprints', params: { min: 30 }, visible: true }]);
+    { id: 'footprint', params: { imbalance: 4, stack: 3, unfinished: true, deltaNum: true }, visible: true },
+    { id: 'profile', params: { prior: true, lines: false }, visible: true },
+    { id: 'bigprints', params: { min: 30, scale: true, sweeps: false }, visible: true }]);
 });
 
 test('an empty Build-1 st means the Build-1 defaults', () => {
@@ -391,8 +394,9 @@ test('market hours: Globex Sunday 18:00 to Friday 17:00 with a daily break; cryp
 
 test('dialog filtering by name and group', () => {
   assert.deepEqual(C.filter('', 'Moving averages').map((d) => d.id), ['ema', 'sma', 'vwma', 'tema']);
-  assert.deepEqual(C.filter('delta').map((d) => d.id), ['delta', 'cumdelta']);
-  assert.deepEqual(C.filter('ORDER').map((d) => d.id), ['footprint', 'profile', 'delta', 'cumdelta', 'bigprints', 'bigorders', 'imbalance', 'heatmap']);
+  assert.deepEqual(C.filter('delta').map((d) => d.id), ['delta', 'cumdelta', 'ddiv']);
+  assert.deepEqual(C.filter('ORDER').map((d) => d.id), ['footprint', 'profile', 'delta', 'cumdelta', 'bigprints', 'bigorders', 'imbalance', 'heatmap',
+    'absorb', 'pulled', 'bkimb', 'bkdepth', 'bkmicro', 'tspeed', 'ddiv']);
   assert.deepEqual(C.filter('heat').map((d) => [d.id, d.group]), [['heatmap', 'Order flow']]);
   assert.deepEqual(C.filter('zzz'), []);
   assert.equal(C.filter('').length, C.CATALOG.length);
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/flowdefs.test.mjs tests/js/catalog.test.mjs`
Expected: FAIL (`Cannot find module ... flowdefs.js`; catalog assertions on the new params).

- [ ] **Step 3: Implement**

Create `homebase/static/charts/flowdefs.js`:

```javascript
/* Homebase Charts — HBFlowDefs: the order-flow indicators' catalog entries, merged into catalog.js's TA_DEFS and
   CATALOG (so catalog.js, a shared file, takes one small hunk). Same shape as TA_DEFS (see catalog.js):
     - `ta`: indicators drawn as series. A key that starts with "bk:" is computed in the page from HBBookStore
       (never sent to the server; catalog.serverKeys drops it); any other key is a server study (studies_flow.py).
       A line's `col` names the book column it plots (bookstore.js COL); without one, the key after "bk:" is it.
     - `marks`: a server study drawn as chart markers: (v, P) -> a Lightweight Charts marker (plus `ago`: how many
       bars back the swing is) or null.
     - a histogram line with `fixed: true` keeps its own colour (a Style-tab colour) instead of green / red by sign.
   - `catalog`: indicators with no series of their own, drawn by an overlay (bookevents.js). */
(function () {
'use strict';
const UP = '#089981', DOWN = '#F23645', BLUE = '#2962FF', ORANGE = '#FF6D00', VIOLET = '#7E57C2', GREY = '#787B86';
const line = (part, label, color, width = 1, dash = 'solid', extra = {}) => ({ part, label, color, width, dash, ...extra });
const SECONDS = { key: 'minSeconds', label: 'Stood at least (seconds)', type: 'int', min: 1, max: 600, def: 5 };

const ta = [
  { id: 'bkimb', group: 'Order flow', name: 'Book imbalance (over time)', pane: 'own',
    params: [{ key: 'levels', label: 'Book levels', type: 'choice', def: '10', choices: [['1', 'Top 1'], ['5', 'Top 5'], ['10', 'Top 10']] }],
    key: (p) => `bk:imb${p.levels}`, label: (p) => `Book imbalance ${p.levels}`,
    desc: 'Bid minus ask size over their sum in the top book levels, averaged per bar',
    lines: [line('main', 'Imbalance', BLUE, 1, 'solid', { type: 'hist', tag: false })], refs: [0.3, -0.3] },
  { id: 'bkdepth', group: 'Order flow', name: 'Book depth (bid vs ask)', pane: 'own', params: [],
    key: () => 'bk:depth', label: () => 'Book depth',
    desc: 'Total resting size in the top 10 book levels, bid and ask, averaged per bar',
    lines: [line('b10', 'Bid size', UP, 1, 'solid', { col: 'b10' }), line('a10', 'Ask size', DOWN, 1, 'solid', { col: 'a10' })] },
  { id: 'bkmicro', group: 'Order flow', name: 'Microprice', params: [],
    key: () => 'bk:micro', label: () => 'Microprice',
    desc: "Top-of-book price weighted by each side's size: it leans to the heavier side",
    lines: [line('main', 'Microprice', VIOLET, 1, 'solid', { tag: false })] },
  { id: 'tspeed', group: 'Order flow', name: 'Tape speed', pane: 'own',
    params: [{ key: 'length', label: 'Bars for the burst line', type: 'int', min: 20, max: 2000, def: 200 }],
    key: (p) => `tspeed:${p.length}`, label: (p) => `Tape speed ${p.length}`,
    desc: 'Prints per second in each bar; above 3x the recent median is a burst',
    lines: [line('rate', 'Prints / s', GREY, 1, 'solid', { type: 'hist', tag: false, fixed: true }),
      line('hot', 'Burst', ORANGE, 1, 'solid', { type: 'hist', tag: false, fixed: true }),
      line('burst', 'Burst line', ORANGE, 1, 'dashed', { tag: false })] },
  { id: 'ddiv', group: 'Order flow', name: 'Delta divergence', params: [{ key: 'length', label: 'Bars each side', type: 'int', min: 1, max: 50, def: 5 }],
    key: (p) => `ddiv:${p.length}`, label: (p) => `Delta divergence ${p.length}`,
    desc: 'Swing high on a lower cumulative delta, or swing low on a higher one',
    lines: [],
    marks: (v, P) => (v && v.dir
      ? { position: v.dir < 0 ? 'aboveBar' : 'belowBar', color: v.dir < 0 ? (P.down || DOWN) : (P.up || UP),
        shape: v.dir < 0 ? 'arrowDown' : 'arrowUp', text: 'Δ', size: 1, ago: v.ago }
      : null) },
];

const catalog = [
  { id: 'absorb', group: 'Order flow', name: 'Absorption', desc: 'Heavy volume traded into a resting level that held, marked by the side that held',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 4, max: 50, step: 0.5, def: 4 }, SECONDS] },
  { id: 'pulled', group: 'Order flow', name: 'Pulled liquidity', desc: 'A big resting order withdrawn as price came toward it',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 2, max: 50, step: 0.5, def: 5 }, SECONDS] },
];

/* The value a "bk:" series shows for one bar: `mean(col)` = the mean of that book column over the bar's seconds (or
   null). A key with several lines gets an object by line part (the depth pane's bid / ask), the others a number. */
const BOOK_COLS = { 'bk:depth': ['b10', 'a10'] };
function bookValue(key, mean) {
  const cols = BOOK_COLS[key];
  if (!cols) return mean(String(key).replace(/^bk:/, ''));
  const out = {};
  let any = false;
  for (const c of cols) { const x = mean(c); out[c] = x; if (x != null) any = true; }
  return any ? out : null;
}

const api = { ta, catalog, bookValue };
if (typeof window !== 'undefined') window.HBFlowDefs = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

`homebase/static/charts/catalog.js` (five hunks; the file has other sessions' uncommitted edits: apply by hand, anchored by the names in the hunks):

```diff
--- a/homebase/static/charts/catalog.js
+++ b/homebase/static/charts/catalog.js
@@ -51,6 +51,10 @@ const BAND = (n, def) => [
    false (no price-axis tag). `refs` are the dashed reference lines of an own-pane study. Each is the same
    definition the strategy engine's blocks read (studies_ta.py). A def with `pane` can live in a pane of its own
    or on the price pane; one without is drawn on the price pane only. */
+/* The order-flow indicators' definitions (flowdefs.js, loaded before this file on the chart page): the book and
+   tick studies of 2026-10-11. Absent (a page that does not load it), none of them exist there. */
+const FLOW = (typeof window !== 'undefined' && window.HBFlowDefs)
+  || (typeof require === 'function' ? require('./flowdefs.js') : { ta: [], catalog: [] });
 const TA_UP = '#089981', TA_DOWN = '#F23645', TA_BLUE = '#2962FF', TA_ORANGE = '#FF6D00', TA_VIOLET = '#7E57C2', TA_GREY = '#787B86';
 const TA_LEN = (def, min = 2, max = 500) => ({ key: 'length', label: 'Length', type: 'int', min, max, def });
 const TA_LINE = (part, label, color, width = 1, dash = 'solid', extra = {}) => ({ part, label, color, width, dash, ...extra });
@@ -185,6 +189,7 @@ const TA_DEFS = [
       { key: 'need', label: 'Fewest days needed', type: 'int', min: 1, max: 60, def: 10 }],
     label: (p) => `RVOL ${p.days}`, desc: 'Bar volume over the median of the same time of day on earlier days; 2 is a spike',
     lines: [TA_LINE('main', 'RVOL', TA_VIOLET, 1, 'solid', { type: 'hist', tag: false })], refs: [1, 2] },
+  ...FLOW.ta,
 ];
 const TA_BY_ID = Object.fromEntries(TA_DEFS.map((d) => [d.id, d]));
 /* The number a generic line plots from the server's value `v` for one bar, or null (still warming up). */
@@ -212,18 +217,30 @@ const CATALOG = [
   { id: 'levels', group: 'Levels', name: 'Session levels', params: [],
     desc: 'Prior session high / low / close, overnight high / low and RTH open, as lines' },
   { id: 'footprint', group: 'Order flow', name: 'Footprint', desc: 'Sells at bid and buys at ask per price in each bar, shown when zoomed in', params: [
-    { key: 'imbalance', label: 'Imbalance ratio', type: 'num', min: 0, max: 20, step: 0.5, def: 3 }] },
-  { id: 'profile', group: 'Order flow', name: 'Volume profile', params: [],
-    desc: 'Volume traded at each price this session, its point of control and 70% value area' },
+    { key: 'imbalance', label: 'Imbalance ratio', type: 'num', min: 0, max: 20, step: 0.5, def: 3 },
+    { key: 'stack', label: 'Stacked imbalances: rows in a row (0 = off)', type: 'int', min: 0, max: 20, def: 3 },
+    { key: 'unfinished', label: 'Mark unfinished auctions', type: 'bool', def: true },
+    { key: 'deltaNum', label: 'Delta under each bar', type: 'bool', def: true }] },
+  { id: 'profile', group: 'Order flow', name: 'Volume profile', params: [
+    { key: 'prior', label: 'Show the prior session', type: 'bool', def: true },
+    { key: 'lines', label: 'Prior VAH / VAL / POC lines', type: 'bool', def: false }],
+    desc: 'Volume at each price this session, POC and value area; prior session as a ghost' },
   { id: 'delta', group: 'Order flow', name: 'Delta', params: [], pane: 'own', desc: 'Buy minus sell volume in each bar: which side was hitting the market harder' },
   { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [], pane: 'own',
     desc: "Running total of each bar's buy-minus-sell volume, reset every session" },
   { id: 'bigprints', group: 'Order flow', name: 'Big prints', desc: 'Single N+ contract trades: green = buyers lifted the offer, red = sellers hit the bid', params: [
-    { key: 'min', label: 'Minimum size', type: 'int', min: 1, max: 100000, def: 25 }] },
-  { id: 'bigorders', group: 'Order flow', name: 'Big orders', desc: "Resting book orders of N× the last minute's median size or more, drawn as lines", params: [
-    { key: 'multiple', label: 'Multiple', type: 'num', min: 1, max: 50, step: 0.5, def: 5 }] },
+    { key: 'min', label: 'Minimum size', type: 'int', min: 1, max: 100000, def: 25 },
+    { key: 'scale', label: 'Marker size follows the print size', type: 'bool', def: true },
+    { key: 'sweeps', label: 'Mark sweeps (one order walking several prices)', type: 'bool', def: false }] },
+  { id: 'bigorders', group: 'Order flow', name: 'Big orders', desc: 'Resting book orders N× the median size or more, as lines; ended ones stay', params: [
+    { key: 'multiple', label: 'Multiple', type: 'num', min: 1, max: 50, step: 0.5, def: 5 },
+    { key: 'minSeconds', label: 'Ended ones that stood at least (seconds)', type: 'int', min: 1, max: 600, def: 5 },
+    { key: 'history', label: 'Keep ended orders on the chart', type: 'bool', def: true }] },
   { id: 'imbalance', group: 'Order flow', name: 'Imbalance', params: [], desc: 'Bid vs ask size resting in the top 10 book levels, as a gauge in the legend' },
-  { id: 'heatmap', group: 'Order flow', name: 'Liquidity heatmap', params: [], desc: 'Resting book size at each price over time, drawn behind the candles' },
+  { id: 'heatmap', group: 'Order flow', name: 'Liquidity heatmap', desc: 'Resting book size at each price over time, behind the candles; optional trade bubbles', params: [
+    { key: 'bubbles', label: 'Trade bubbles', type: 'bool', def: false },
+    { key: 'bubbleMin', label: 'Bubble from (contracts in one second)', type: 'int', min: 1, max: 10000, def: 10 }] },
+  ...FLOW.catalog,
   ...TA_DEFS,
 ];
 const BY_ID = Object.fromEntries(CATALOG.map((d) => [d.id, d]));
@@ -348,7 +365,10 @@ const STYLE_LINES = { vwap: ['main', 'band1', 'band2', 'band3'], ema: ['main'],
   adx: ['adx', 'pdi', 'mdi'], cumdelta: ['main'] };
 // delta has no Style tab: it draws a per-bar up/down-coloured histogram, not a single line -- style-able
 // the same way would need its own up/down fields, not this one-colour-per-key shape (spec: "unless trivial").
-function styleLineKeys(id) { return STYLE_LINES[id] || (TA_BY_ID[id] ? TA_BY_ID[id].lines.map((l) => l.part) : null); }
+function styleLineKeys(id) {
+  const t = TA_BY_ID[id];
+  return STYLE_LINES[id] || (t && t.lines.length ? t.lines.map((l) => l.part) : null);   // a study drawn as markers only has no line style
+}
 
 const VWAP_DEFAULT = '#9C27B0';   // cell.js palette().vwap -- today's single-VWAP purple, kept as the first colour
 const UP_DEFAULT = '#089981', DOWN_DEFAULT = '#F23645';   // palette().up/.down -- theme-independent
@@ -451,7 +471,9 @@ function serverKey(inst) {
   }
 }
 
-function serverKeys(list) { return [...new Set((list || []).map(serverKey).filter(Boolean))]; }
+/* The studies the server computes for these instances. A "bk:" key is computed in the page from the book samples
+   (flowdefs.js): it is never asked of the server. */
+function serverKeys(list) { return [...new Set((list || []).map(serverKey).filter((k) => k && !k.startsWith('bk:')))]; }
 
 /* A saved chart config of any vintage as {root, spec, indicators}. The spec is
    normalised as the server answers it (a Build-1 "tick:0750" is "tick:750"). */
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/flowdefs.test.mjs tests/js/catalog.test.mjs`
Expected: PASS (5 + 80 tests).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/flowdefs.js homebase/static/charts/catalog.js tests/js/flowdefs.test.mjs tests/js/catalog.test.mjs
git commit -m "feat(charts): order-flow catalog entries and parameters; bk: keys stay in the page" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 4: `cell.js`: the `flow` request, the book series, study markers, extras to the layers

**Files:**
- Modify: `homebase/static/charts/cell.js`, `tests/js/cell-bardata.test.mjs`, `tests/js/cell-window.test.mjs`
- Create: `tests/js/orderflow-cell.test.mjs`

**Interfaces:**
- Consumes: Task 1 `HBBookStore.meanAt`, Task 2 `HBFlowMath.markerSize`, Task 3 `HBFlowDefs.bookValue` and the new catalog parameters, Plan A's `flow` wire flag.
- Produces on `Cell`: `has` and `need()` carry `flow` (true while a `heatmap` has `bubbles` or a `bigprints` has `sweeps`, hidden instances included); `sub` / `older` send `flow`; `bookSv(src, bar)` and `bookEnd(bar)`; `refreshBookSeries(all)` (called by Task 6's overlay: all bars after a fetched window, else the newest); `studyMarks()`; `priorNaked()`; `point()` computes a `bk:` series into `bar.sv` and a `fixed` histogram keeps its own colour; `drawMarkers()` scales a big print's marker by size when the indicator's `scale` is on; `syncFootprint()` / `syncProfile()` hand `{stack, unfinished, deltaNum}` / `{prior, lines, naked}` to the layers (Task 5).

A bar's book value is the mean of the 1 s samples inside it: a time bar `[ms, ms + barMs)`, a tick / range / volume bar up to the next bar's start (the last one: now). A bar the store holds nothing for is a gap, never a zero.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/orderflow-cell.test.mjs`:

```javascript
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The order-flow additions to cell.js, driven through Cell.prototype on a bare object (as cell-point.test.mjs does):
   the book series computed from HBBookStore ("bk:" keys), the markers of a study drawn as markers (ddiv), the
   Big-prints marker size, and the naked prior POC. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/flowdefs.js');
require('../../homebase/static/charts/flowmath.js');
require('../../homebase/static/charts/bookstore.js');
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const C = globalThis.HBCatalog, S = globalThis.HBBookStore;

const T0 = 1_790_000_000_000;
const row = (i, imb10, b10, a10, micro) => [T0 + i * 1000, b10, a10, 0, 0, imb10, micro, 1];
beforeEach(() => S.clear());

const stub = (more = {}) => Object.assign(Object.create(Cell.prototype), {
  P: { up: '#0f0', down: '#f00', upA: 'upA', downA: 'downA' }, shown: { root: 'NQ', spec: 'time:60' },
  cfg: { root: 'NQ', spec: 'time:60', indicators: [] }, bars: [], ...more });
const line = (id, part = 'main') => ({ gen: C.TA_BY_ID[id].lines.find((l) => l.part === part), src: C.serverKey({ id, params: C.clampParams(id, {}) }) });

test('a book series is the mean of the samples inside the bar, written into bar.sv for the legend', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 60000, samples: [row(0, 0.2, 10, 30, 100), row(1, 0.4, 20, 30, 102), row(61, 0.9, 0, 0, 0)], episodes: [] });
  const c = stub(), b = { tt: 7, ms: T0, sv: {} };
  const l = line('bkimb');
  assert.equal(l.src, 'bk:imb10');
  const p = c.point(l, b);
  assert.equal(p.time, 7);
  assert.ok(Math.abs(p.value - 0.3) < 1e-9);                     // the sample of the next minute is not in this bar
  assert.ok(Math.abs(b.sv['bk:imb10'] - 0.3) < 1e-9);            // what the legend and the crosshair read
  assert.equal(p.color, 'upA');                                  // a histogram coloured by sign
});

test('the depth pane has a bid and an ask line from one value object', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 60000, samples: [row(0, 0, 10, 30, 100), row(1, 0, 20, 50, 100)], episodes: [] });
  const c = stub(), b = { tt: 1, ms: T0, sv: {} };
  assert.equal(c.point(line('bkdepth', 'b10'), b).value, 15);
  assert.equal(c.point(line('bkdepth', 'a10'), b).value, 40);
  assert.deepEqual(b.sv['bk:depth'], { b10: 15, a10: 40 });
});

test('a bar the store holds nothing for is a gap, not a zero; a missing store or shown root is a gap too', () => {
  const c = stub(), b = { tt: 1, ms: T0, sv: {} };
  assert.deepEqual(c.point(line('bkimb'), b), { time: 1 });
  assert.deepEqual(stub({ shown: null }).point(line('bkimb'), { tt: 1, ms: T0, sv: {} }), { time: 1 });
  assert.deepEqual(c.point(line('bkimb'), { tt: 1, ms: T0 }), { time: 1 });     // no sv at all
});

test('a tick chart ends a bar where the next one starts, the last one now', () => {
  const c = stub({ cfg: { root: 'NQ', spec: 'tick:500', indicators: [] }, shown: { root: 'NQ', spec: 'tick:500' },
    bars: [{ ms: T0 }, { ms: T0 + 5000 }, { ms: T0 + 9000 }] });
  assert.equal(c.bookEnd(c.bars[0]), T0 + 5000);
  assert.equal(c.bookEnd(c.bars[1]), T0 + 9000);
  assert.ok(Math.abs(c.bookEnd(c.bars[2]) - Date.now()) < 1000);
});

test('a "fixed" histogram keeps its own colour (tape speed), the others take it from the sign', () => {
  const c = stub(), b = { tt: 1, sv: { 'tspeed:200': { rate: 12, burst: 30, hot: null } } };
  const src = 'tspeed:200';
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'rate'), src }, b), { time: 1, value: 12 });
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'hot'), src }, b), { time: 1 });
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'burst'), src }, b), { time: 1, value: 30 });
});

test('delta divergence: a marker on the swing bar, `ago` real bars before the confirming one, blanks not counted', () => {
  const bars = [0, 1, 2, 3, 4, 5].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[4].blank = true;                            // a known hole between the swing and the confirming bar
  bars[5].sv['ddiv:2'] = { dir: -1, ago: 2, px: 101 };
  const inst = { uid: 'u', id: 'ddiv', params: { length: 2 }, visible: true };
  const c = stub({ bars, cfg: { root: 'NQ', spec: 'time:60', indicators: [inst] } });
  assert.deepEqual(c.studyMarks(), [{ time: 102, position: 'aboveBar', color: '#f00', shape: 'arrowDown', text: 'Δ', size: 1 }]);
  inst.visible = false;
  assert.deepEqual(c.studyMarks(), []);
  bars[5].sv['ddiv:2'] = { dir: 1, ago: 2, px: 99 };
  inst.visible = true;
  assert.deepEqual(c.studyMarks().map((m) => [m.position, m.shape, m.color]), [['belowBar', 'arrowUp', '#0f0']]);
});

test('the prior POC is naked until the session trades back through it', () => {
  const bars = [{ s: 'A', l: 90, h: 100 }, { s: 'B', l: 101, h: 105 }, { s: 'B', l: 104, h: 108 }];
  const c = stub({ bars, profile: { poc: 100, prev: { poc: 100, rows: [[100, 5]] } } });
  assert.equal(c.priorNaked(), true);              // session B (the last) has not touched 100; session A's bar is not counted
  bars.push({ s: 'B', l: 99, h: 103 });
  assert.equal(c.priorNaked(), false);
  assert.equal(stub({ bars, profile: { poc: 1 } }).priorNaked(), false);          // no prior session
});

test('book keys never go to the server; the server studies do', () => {
  const list = [{ id: 'bkimb', params: { levels: '5' } }, { id: 'bkdepth', params: {} }, { id: 'bkmicro', params: {} },
    { id: 'tspeed', params: { length: 100 } }, { id: 'ddiv', params: { length: 3 } }, { id: 'rsi', params: { length: 14 } }];
  assert.deepEqual(C.serverKeys(list), ['tspeed:100', 'ddiv:3', 'rsi:14']);
  assert.equal(C.serverKey(list[0]), 'bk:imb5');
});

test('a page that does not load the book store (the Backtest tab) draws the book series as gaps and never throws', () => {
  const saved = globalThis.HBBookStore;
  try {
    delete globalThis.HBBookStore;
    const b = { tt: 1, ms: T0, sv: {} };
    assert.deepEqual(stub().point(line('bkimb'), b), { time: 1 });
    assert.deepEqual(b.sv, {});
  } finally { globalThis.HBBookStore = saved; }
});
```

Update `tests/js/cell-bardata.test.mjs` and `tests/js/cell-window.test.mjs` (every `sub` / `older` now says `flow`, one new test):

```diff
--- a/tests/js/cell-bardata.test.mjs
+++ b/tests/js/cell-bardata.test.mjs
@@ -21,7 +21,7 @@ function cell(indicators) {
   const c = Object.create(Cell.prototype);
   return Object.assign(c, { id: 'c1', cfg: { root: 'NQ', spec: 'time:60', indicators }, sent: [], drawn: 0, built: 0,
     host: { send: (m) => { c.sent.push(m); return true; }, changed() {}, onLoaded() {} },
-    inflight: [], has: { fp: false, big: false }, wantFp: false, replay: null, chart: null, shown: null, keys: new Set(),
+    inflight: [], has: { fp: false, big: false, flow: false }, wantFp: false, replay: null, chart: null, shown: null, keys: new Set(),
     bars: [], realT: new Map(), loadWaiters: [], noteOn: false, capped: false, reaching: null, R: { timezone: 'exchange' },
     back: { reset() {}, want: (r, ms) => ({ before: ms }), sent() {} },
     title() {}, message() {}, viewNow: () => null, restyle() { c.drawn++; }, build() { c.built++; c.chart = {}; } });
@@ -34,31 +34,31 @@ function loaded(indicators) {
   c.sent.length = 0;
   return c;
 }
-const subs = (c) => c.sent.filter((m) => m.op === 'sub').map((m) => ({ fp: m.fp, big: m.big }));
+const subs = (c) => c.sent.filter((m) => m.op === 'sub').map((m) => ({ fp: m.fp, big: m.big, flow: m.flow }));
 
 test('a chart asks for the footprint and the big prints only with an indicator that draws them', () => {
   const ask = (list) => { const c = cell(list); c.subscribe(); return subs(c); };
-  assert.deepEqual(ask([ind('volume'), ind('vwap'), ind('levels')]), [{ fp: false, big: false }]);
-  assert.deepEqual(ask([ind('volume'), ind('footprint')]), [{ fp: true, big: false }]);
-  assert.deepEqual(ask([ind('bigprints')]), [{ fp: false, big: true }]);
-  assert.deepEqual(ask([ind('footprint'), ind('bigprints')]), [{ fp: true, big: true }]);
+  assert.deepEqual(ask([ind('volume'), ind('vwap'), ind('levels')]), [{ fp: false, big: false, flow: false }]);
+  assert.deepEqual(ask([ind('volume'), ind('footprint')]), [{ fp: true, big: false, flow: false }]);
+  assert.deepEqual(ask([ind('bigprints')]), [{ fp: false, big: true, flow: false }]);
+  assert.deepEqual(ask([ind('footprint'), ind('bigprints')]), [{ fp: true, big: true, flow: false }]);
   // a hidden instance still counts: the legend's eye shows it again at once, with no reload (setVisible)
-  assert.deepEqual(ask([ind('footprint', { visible: false }), ind('bigprints', { visible: false })]), [{ fp: true, big: true }]);
+  assert.deepEqual(ask([ind('footprint', { visible: false }), ind('bigprints', { visible: false })]), [{ fp: true, big: true, flow: false }]);
 });
 
 test('Footprint switched on later: the chart reloads with the data, it is never drawn from bars that lack it', () => {
   const c = loaded([ind('volume')]);
-  assert.deepEqual(c.has, { fp: false, big: false });
+  assert.deepEqual(c.has, { fp: false, big: false, flow: false });
   c.update({ indicators: [ind('volume'), ind('footprint')] });
-  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
+  assert.deepEqual(subs(c), [{ fp: true, big: false, flow: false }]);
   assert.equal(c.drawn, 0);                        // not restyle(): the bars on screen have no footprint
   c.onHistory({ ...HIST });
-  assert.deepEqual(c.has, { fp: true, big: false });
+  assert.deepEqual(c.has, { fp: true, big: false, flow: false });
   c.update({ indicators: [ind('volume'), ind('footprint'), ind('bigprints')] });   // and Big prints after it
-  assert.deepEqual(subs(c), [{ fp: true, big: false }, { fp: true, big: true }]);
+  assert.deepEqual(subs(c), [{ fp: true, big: false, flow: false }, { fp: true, big: true, flow: false }]);
   assert.equal(c.drawn, 0);
   c.onHistory({ ...HIST });
-  assert.deepEqual(c.has, { fp: true, big: true });
+  assert.deepEqual(c.has, { fp: true, big: true, flow: false });
 });
 
 test('with the data already on the chart an indicator change is still drawn in place, with no reload', () => {
@@ -76,21 +76,21 @@ test('with the data already on the chart an indicator change is still drawn in p
 test('scroll-back asks for what the history on screen carries', () => {
   const c = loaded([ind('volume')]);
   c.askOlder({ from: 0, to: 1 });
-  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 60000, fp: false, big: false }]);
+  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 60000, fp: false, big: false, flow: false }]);
   const f = loaded([ind('footprint'), ind('bigprints')]);
   f.askOlder({ from: 0, to: 1 });
-  assert.deepEqual(f.sent, [{ op: 'older', id: 'c1', before: 60000, fp: true, big: true }]);
+  assert.deepEqual(f.sent, [{ op: 'older', id: 'c1', before: 60000, fp: true, big: true, flow: false }]);
 });
 
 test('the Level 2 ladder asks a chart for its footprint once, and the chart keeps asking for it afterwards', () => {
   const c = loaded([ind('volume')]);
   c.needFootprint();
   c.needFootprint();                               // the ladder calls at every paint
-  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
+  assert.deepEqual(subs(c), [{ fp: true, big: false, flow: false }]);
   c.onHistory({ ...HIST });
   assert.equal(c.has.fp, true);
   c.subscribe(true);                               // a later reload (a reset, a reconnect) still carries it
-  assert.deepEqual(subs(c), [{ fp: true, big: false }, { fp: true, big: false }]);
+  assert.deepEqual(subs(c), [{ fp: true, big: false, flow: false }, { fp: true, big: false, flow: false }]);
   const f = loaded([ind('footprint')]);            // already on the chart: nothing to load
   f.needFootprint();
   assert.deepEqual(f.sent, []);
@@ -108,15 +108,37 @@ test('a refused footprint reload is not sent again at the next paint', () => {
   assert.equal(subs(c).length, 1);
 });
 
-test('in a replay the ladder never sends a sub (it would end the replay); the replay history carries both', () => {
+test('in a replay the ladder never sends a sub (it would end the replay); the replay history carries all', () => {
   const c = loaded([ind('volume')]);
   c.replay = { date: '2026-09-24' };
   c.needFootprint();
   assert.deepEqual(c.sent, []);
   c.onHistory({ ...HIST, replay: true });          // no sub of ours in flight: the replay's own history
-  assert.deepEqual(c.has, { fp: true, big: true });
+  assert.deepEqual(c.has, { fp: true, big: true, flow: true });
   c.replay = null;                                 // a refused or finished replay: the ladder asks now
-  c.has = { fp: false, big: false };
+  c.has = { fp: false, big: false, flow: false };
   c.needFootprint();
-  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
+  assert.deepEqual(subs(c), [{ fp: true, big: false, flow: false }]);
+});
+
+test('trade bubbles and sweeps are asked for only while an option wants them; switching one on reloads', () => {
+  const ask = (list) => { const c = cell(list); c.subscribe(); return subs(c); };
+  const hm = (bubbles) => ind('heatmap', { params: { bubbles } });
+  const bp = (sweeps) => ind('bigprints', { params: { sweeps } });
+  assert.deepEqual(ask([hm(false), bp(false)]), [{ fp: false, big: true, flow: false }]);
+  assert.deepEqual(ask([hm(true)]), [{ fp: false, big: false, flow: true }]);
+  // a hidden instance still counts: the legend's eye shows its bubbles at once, with no reload (setVisible)
+  assert.deepEqual(ask([{ ...hm(true), visible: false }]), [{ fp: false, big: false, flow: true }]);
+  assert.deepEqual(ask([bp(true)]), [{ fp: false, big: true, flow: true }]);
+  const c = loaded([hm(false)]);
+  c.update({ indicators: [hm(true)] });
+  assert.deepEqual(subs(c), [{ fp: false, big: false, flow: true }]);
+  assert.equal(c.drawn, 0);                        // the bars on screen have no bubbles: reload, never draw from them
+  c.onHistory({ ...HIST });
+  assert.deepEqual(c.has, { fp: false, big: false, flow: true });
+  c.askOlder({ from: 0, to: 1 });
+  assert.equal(c.sent.find((m) => m.op === 'older').flow, true);
+  c.sent.length = 0;
+  c.update({ indicators: [hm(false)] });           // switched off again: the data is there, nothing to reload
+  assert.deepEqual(c.sent, []);
 });
```

```diff
--- a/tests/js/cell-window.test.mjs
+++ b/tests/js/cell-window.test.mjs
@@ -15,7 +15,7 @@ const P = Cell.prototype;
 
 function bare(over = {}) {
   const sent = [];
-  const c = { sent, id: 'c1', chart: {}, bars: [{ ms: 9e12 }], inflight: [], has: { fp: false, big: false }, windowAt: null, winReq: null,
+  const c = { sent, id: 'c1', chart: {}, bars: [{ ms: 9e12 }], inflight: [], has: { fp: false, big: false, flow: false }, windowAt: null, winReq: null,
     back: new globalThis.HBScrollBack.ScrollBack(), sessions: [], keys: new Set(), host: { send: (m) => { sent.push(m); return true; }, onLoaded() {} },
     slotted: (b) => b, append(b) { this.bars.push(b); }, build() { this.built = (this.built || 0) + 1; }, message(t) { this.msg = t; },
     showWindow: P.showWindow, onWindow: P.onWindow, onOlder: P.onOlder, onUpdate: P.onUpdate, ...over };
@@ -26,7 +26,7 @@ const ans = (before, over = {}) => ({ type: 'older', id: 'c1', before, bars: [{
 test('showWindow sends the older request for the end time and resolves true when it lands', async () => {
   const c = bare();
   const p = c.showWindow(5000);
-  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 5000, fp: false, big: false }]);
+  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 5000, fp: false, big: false, flow: false }]);
   c.onOlder(ans(5000));
   assert.equal(await p, true);
   assert.equal(c.windowAt, 5000);
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/orderflow-cell.test.mjs tests/js/cell-bardata.test.mjs tests/js/cell-window.test.mjs`
Expected: FAIL (`c.bookEnd is not a function`, `flow` missing from the messages).

- [ ] **Step 3: Implement**

`homebase/static/charts/cell.js` (eleven hunks; other sessions have uncommitted edits in this file: apply by hand, anchored by the method names):

```diff
--- a/homebase/static/charts/cell.js
+++ b/homebase/static/charts/cell.js
@@ -185,7 +185,7 @@ class Cell {
     this.replay = null;    // Bar Replay (2026-09-27 plan): null live, else {date, cursorMs, speed, playing, done}
                             // -- set by replayui.js, read by HBTradeUI.effectiveMode (a replaying chart never trades)
     this.today = []; this.todayKey = '[]';   // the session under way's thin hours, from the status message (setToday)
-    this.has = { fp: false, big: false };   // what the bars on screen carry beyond OHLCV: need() as their history was asked
+    this.has = { fp: false, big: false, flow: false };   // what the bars on screen carry beyond OHLCV: need() as their history was asked
     this.wantFp = false;   // the Level 2 ladder reads this chart's footprint (needFootprint)
     slot.className = 'panel';
     this.folded = false;   // the legend's collapse chevron: app.js syncs this to the persisted preference
@@ -483,7 +483,7 @@ class Cell {
   askOlder(r) {
     if (!this.chart || this.inflight.length || !this.bars.length || this.capped) return;
     const req = this.back.want(r, this.bars[0].ms);
-    if (req && this.host.send({ op: 'older', id: this.id, before: req.before, fp: this.has.fp, big: this.has.big })) this.back.sent(req);
+    if (req && this.host.send({ op: 'older', id: this.id, before: req.before, fp: this.has.fp, big: this.has.big, flow: this.has.flow })) this.back.sent(req);
   }
 
   /* Older sessions in front of the chart: the bars, their studies (and the repaired first bars) and session
@@ -549,7 +549,7 @@ class Cell {
         if (++w.tries > 40) { w.resolve(false); return; }
         // a sub in flight answers with its own history: this asks again once that has landed
         if (!this.chart || this.inflight.length || !this.bars.length) { w.timer = setTimeout(go, 300); return; }
-        if (!this.host.send({ op: 'older', id: this.id, before: endMs, fp: this.has.fp, big: this.has.big })) { w.resolve(false); return; }
+        if (!this.host.send({ op: 'older', id: this.id, before: endMs, fp: this.has.fp, big: this.has.big, flow: this.has.flow })) { w.resolve(false); return; }
         w.timer = setTimeout(go, 8000);       // no answer at all: ask once more (the guard above ends it)
       };
       w.go = go;
@@ -620,7 +620,9 @@ class Cell {
      chart without them asks for its history without -- it is most of the message. */
   need() {
     const on = (id) => this.cfg.indicators.some((x) => x.id === id);
-    return { fp: this.wantFp || on('footprint'), big: on('bigprints') };
+    const opt = (id, key) => this.cfg.indicators.some((x) => x.id === id && x.params && x.params[key]);
+    // flow: the sweeps and trade bubbles (the bar's `sw` / `bub`), a good part of the message: only while an option wants them
+    return { fp: this.wantFp || on('footprint'), big: on('bigprints'), flow: opt('heatmap', 'bubbles') || opt('bigprints', 'sweeps') };
   }
 
   /* The Level 2 ladder shows this chart (domui.js calls this at every paint): its Vol column sums the bars'
@@ -640,7 +642,7 @@ class Cell {
   subscribe(keepView = false) {
     const cfg = this.cfgNow(), view = keepView && this.chart ? this.viewNow() : null, has = this.need();
     if (!this.host.send({ op: 'sub', id: this.id, root: cfg.root, spec: cfg.spec, studies: C.serverKeys(cfg.indicators),
-      fp: has.fp, big: has.big })) return;
+      fp: has.fp, big: has.big, flow: has.flow })) return;
     this.inflight.push({ cfg, view, has });
     const s = this.shown;
     if (!s || s.root !== cfg.root || s.spec !== cfg.spec) this.message('Loading…');
@@ -674,7 +676,7 @@ class Cell {
     this.title();
     this.host.changed();
     const same = !!was && was.root === this.cfg.root && was.spec === this.cfg.spec && !(this.windowAt != null && ('spec' in patch || 'root' in patch)), need = this.need();
-    const loaded = (this.has.fp || !need.fp) && (this.has.big || !need.big);
+    const loaded = (this.has.fp || !need.fp) && (this.has.big || !need.big) && (this.has.flow || !need.flow);
     if (same && this.chart && !this.inflight.length && loaded && C.serverKeys(this.cfg.indicators).every((k) => this.keys.has(k))) {
       this.lastGood = this.cfgNow();
       this.restyle();
@@ -689,7 +691,7 @@ class Cell {
     const entry = this.inflight.shift();
     if (entry) this.lastGood = entry.cfg;
     if (this.inflight.length) return;
-    this.has = entry ? entry.has : { fp: true, big: true };   // no sub of ours: a replay's history, which carries both
+    this.has = entry ? entry.has : { fp: true, big: true, flow: true };   // no sub of ours: a replay's history, which carries all
     this.windowAt = null;
     if (this.winReq) this.winReq.resolve(false);   // a window asked for before this history is not the one wanted now
     this.back.reset();
@@ -959,7 +961,8 @@ class Cell {
             if (j === 0) this.colorOf[inst.uid] = sty.color;
             const tag = ln.tag !== false;   // its value on the price axis (a band or a histogram has none)
             const serie = ln.type === 'hist'
-              ? add(inst, k, ln.part, LW.HistogramSeries, { ...fmt, lastValueVisible: false, ...scale, visible: sty.visible !== false }, where)
+              ? add(inst, k, ln.part, LW.HistogramSeries, { ...fmt, lastValueVisible: false, ...(ln.fixed ? { color: sty.color } : {}),
+                ...scale, visible: sty.visible !== false }, where)
               : line(inst, k, ln.part, sty.color, sty.width, where,
                 { ...fmt, lastValueVisible: tag, ...scale, lineStyle: dash(sty.dash), visible: sty.visible !== false,
                   ...(ln.step ? { lineType: LW.LineType.WithSteps } : {}) });
@@ -1245,12 +1248,14 @@ class Cell {
     if (b.blank) return { time };
     if (l.src === '__vol') return { time, value: b.v, color: b.d >= 0 ? P.upA : P.downA };
     if (l.src === '__delta') return { time, value: b.d, color: b.d >= 0 ? P.upA : P.downA };
+    if (typeof l.src === 'string' && l.src.startsWith('bk:')) this.bookSv(l.src, b);   // the book's own series: into b.sv
     const v = b.sv ? b.sv[l.src] : null;
     if (v == null) return { time };
     if (l.gen) {   // a technical indicator: its definition says which number this line plots
       const x = C.lineValue(l.gen, v);
       if (x == null) return { time };
-      return l.gen.type === 'hist' ? { time, value: x, color: x >= 0 ? P.upA : P.downA } : { time, value: x };
+      if (l.gen.type !== 'hist') return { time, value: x };
+      return l.gen.fixed ? { time, value: x } : { time, value: x, color: x >= 0 ? P.upA : P.downA };
     }
     if (typeof v === 'number') return { time, value: v };
     if (l.src.startsWith('vwap')) {
@@ -1267,26 +1272,73 @@ class Cell {
 
   visible(id) { return this.cfg.indicators.filter((x) => x.id === id && x.visible !== false); }
 
+  /* A "bk:" series (flowdefs.js) is computed here, not by the server: the mean of the book's 1 s samples inside
+     the bar (HBBookStore), written into b.sv so the legend and the crosshair read it like any study. A bar past
+     what the store holds gives null (a gap, not a zero). */
+  bookSv(src, b) {
+    const S = window.HBBookStore, F = window.HBFlowDefs;
+    if (!S || !F || !this.shown || !b.sv) return null;
+    const from = b.ms, to = this.bookEnd(b), root = this.shown.root;
+    return (b.sv[src] = F.bookValue(src, (col) => S.meanAt(root, from, to, col)));
+  }
+  /* Where a bar ends, for the book's samples: a time bar's length, else the start of the next bar (the last one:
+     now). */
+  bookEnd(b) {
+    if (this.isTime()) return b.ms + this.barMs();
+    const i = C.barIndexAtMs(this.bars, b.ms, 0);
+    return i >= 0 && this.bars[i + 1] ? this.bars[i + 1].ms : Date.now();
+  }
+  /* The book changed (HBBookEvents' timer): every "bk:" series is set again after a fetched window landed, else
+     only the newest bar's point moves (the live samples). */
+  refreshBookSeries(all) {
+    if (!this.chart || !this.bars.length) return;
+    const last = this.bars[this.bars.length - 1];
+    for (const l of this.lines) {
+      if (typeof l.src !== 'string' || !l.src.startsWith('bk:')) continue;
+      if (all) l.s.setData(this.bars.map((b) => this.point(l, b))); else l.s.update(this.point(l, last));
+    }
+    this.legend(this.hover);
+  }
+
   /* Trading, bot and tester markers share this one series-markers plugin, keyed by source (ruling S22): each
      overlay hands its own list to setExtraMarkers, and every redraw merges them with the big-prints markers. */
   setExtraMarkers(key, list) { this.extMarkers[key] = list || []; this.drawMarkers(); }
 
   drawMarkers() {
     if (!this.markers) return;
-    const mins = this.visible('bigprints').map((x) => x.params.min), P = this.P, big = [];
+    const prints = this.visible('bigprints'), mins = prints.map((x) => x.params.min), P = this.P, big = [];
     if (mins.length) {
-      const min = Math.min(...mins);
+      const min = Math.min(...mins), scale = prints.some((x) => x.params.scale) && window.HBFlowMath;
       for (const b of this.bars) {
         for (const [, , size, side] of (b.big || [])) {
           if (size >= min) big.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
-            color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
+            color: side > 0 ? P.up : P.down, shape: 'circle', size: scale ? scale.markerSize(size, min, true) : 0.6, text: String(size) });
         }
       }
     }
     const extra = [];
     for (const k in this.extMarkers) extra.push(...this.extMarkers[k]);
     const placed = window.HBDrawings.placeMarkers(this.bars, extra, this.barMs());
-    this.markers.setMarkers([...big.slice(-600), ...placed].sort((a, b) => a.time - b.time));
+    this.markers.setMarkers([...big.slice(-600), ...this.studyMarks(), ...placed].sort((a, b) => a.time - b.time));
+  }
+
+  /* The markers of the studies that are drawn as markers (a catalog definition's `marks`: delta divergence). The
+     server emits one on the bar that CONFIRMS a swing, `ago` bars after it; it is placed on the swing's bar. */
+  studyMarks() {
+    const out = [];
+    for (const inst of this.cfg.indicators) {
+      const t = C.TA_BY_ID[inst.id];
+      if (!t || !t.marks || inst.visible === false) continue;
+      const k = C.serverKey(inst);
+      for (let i = 0; i < this.bars.length; i++) {
+        const v = this.bars[i].sv && this.bars[i].sv[k], m = v ? t.marks(v, this.P) : null;
+        if (!m) continue;
+        let j = i, left = m.ago || 0;
+        while (left > 0 && j > 0) { j--; if (!this.bars[j].blank) left--; }   // the swing bar: `ago` real bars back
+        if (!this.bars[j].blank) out.push({ time: this.bars[j].tt, position: m.position, color: m.color, shape: m.shape, text: m.text, size: m.size });
+      }
+    }
+    return out;
   }
 
   drawLevels() {
@@ -1339,11 +1391,26 @@ class Cell {
   syncFootprint() {
     if (!this.fp) return;
     const f = this.visible('footprint')[0];
-    this.fp.set(this.bars, !!f, f ? f.params.imbalance : 0, this.tick);
+    this.fp.set(this.bars, !!f, f ? f.params.imbalance : 0, this.tick,
+      f ? { stack: f.params.stack, unfinished: f.params.unfinished, deltaNum: f.params.deltaNum } : null);
+  }
+
+  syncProfile() {
+    if (!this.prof) return;
+    const f = this.visible('profile')[0];
+    this.prof.set(f ? this.profile : null, this.tick, f ? { prior: f.params.prior, lines: f.params.lines, naked: this.priorNaked() } : null);
+  }
+  /* The prior session's POC has not been traded since this session began (its line is dashed until it is). */
+  priorNaked() {
+    const q = this.profile && this.profile.prev, bars = this.bars;
+    if (!q || q.poc == null || !bars.length) return false;
+    const sess = bars[bars.length - 1].s;
+    for (let i = bars.length - 1; i >= 0 && bars[i].s === sess; i--) {
+      if (!bars[i].blank && bars[i].l <= q.poc && bars[i].h >= q.poc) return false;
+    }
+    return true;
   }
 
-  syncProfile() { if (this.prof) this.prof.set(this.visible('profile').length ? this.profile : null, this.tick); }
-
   destroy() {
     this.host.send({ op: 'unsub', id: this.id });
     clearTimeout(this.noteTimer);
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/orderflow-cell.test.mjs tests/js/cell-bardata.test.mjs tests/js/cell-window.test.mjs tests/js/cell-point.test.mjs tests/js/cell-holes.test.mjs tests/js/cell-destroy.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/cell.js tests/js/orderflow-cell.test.mjs tests/js/cell-bardata.test.mjs tests/js/cell-window.test.mjs
git commit -m "feat(charts): cell asks for flow only when wanted; book series, study markers, layer extras" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 5: The footprint extras and the profile's prior session, drawn

**Files:**
- Modify: `homebase/static/charts/primitives.js`
- Create: `tests/js/orderflow-primitives.test.mjs`

**Interfaces:**
- Consumes: Task 2's `HBFlowMath.stackedRuns` / `unfinished`, Task 4's `Footprint.set(bars, on, ratio, tick, ex)` and `Profile.set(p, tick, ex)` calls, the profile message's `prev` (Plan A Task 2: `{poc, vah, val, rows}` of the session before).
- Produces: `Footprint.extras(ctx, bar, x, w, rh)` (a 2 px bracket beside each stacked run: buyers right of the cell, sellers left; a small triangle at a high / low row where both sides traded; the bar's signed delta under it) and the `Profile` ghost (45% alpha, left of the current profile) and its VAH / VAL / POC lines (POC dashed while `naked`). Both draw only where they drew before: the footprint only while it is readable, the profile only with the indicator on.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/orderflow-primitives.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The footprint extras and the profile's prior session, drawn through a recording canvas context: which strokes
   and texts land where. The geometry (stack runs, unfinished auctions) is HBFlowMath's, tested in flowmath.test. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/flowmath.js');
require('../../homebase/static/charts/primitives.js');
const { Footprint, Profile } = globalThis.HBLayers;

const P = { up: 'UP', down: 'DOWN', text2: 'T2', poc: 'POC', va: 'VA', vaIn: 'VAIN', fpBg: 'BG', fpText: 'TX' };
const recorder = () => {
  const log = [], ctx = {};
  for (const m of ['beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'fillRect', 'strokeRect', 'closePath', 'fillText', 'setLineDash', 'arc']) {
    ctx[m] = (...a) => { log.push([m, ...a]); };
  }
  ctx.measureText = () => ({ width: 10 });
  for (const k of ['strokeStyle', 'fillStyle', 'lineWidth']) {
    Object.defineProperty(ctx, k, { set: (v) => { log.push([`set ${k}`, v]); }, get: () => undefined });
  }
  return { ctx, log };
};
const series = { priceToCoordinate: (px) => 1000 - px * 4 };          // a price row is 1 px per 0.25 -> 1 px/tick; y falls with price
const TICK = 0.25;
// buys at 100.25 .. 101.00 each >= 3x the sells one tick below -> a buy stack of 4 rows; both sides traded at the top row only
const FP = [[100.0, 1, 0], [100.25, 1, 4], [100.5, 1, 4], [100.75, 1, 4], [101.0, 1, 4], [101.25, 1, 1]];

function footprint(ex, ratio = 3) {
  const f = new Footprint(P);
  f.series = series; f.tick = TICK; f.ratio = ratio; f.ex = ex;
  return f;
}

test('a stack of buy imbalances gets a bracket on the ask side; a run too short gets none', () => {
  const { ctx, log } = recorder();
  footprint({ stack: 4 }).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  const strokes = log.filter((l) => l[0] === 'moveTo');
  assert.equal(strokes.length, 1);
  assert.equal(strokes[0][1], 200 + 20 + 3);                           // right of the cell: the ask side
  assert.ok(log.some((l) => l[0] === 'set strokeStyle' && l[1] === 'UP'));
  const two = recorder();
  footprint({ stack: 5 }).extras(two.ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(two.log.filter((l) => l[0] === 'moveTo').length, 0);
});

test('stacked imbalances need the imbalance ratio on; off draws nothing', () => {
  const { ctx, log } = recorder();
  footprint({ stack: 4 }, 0).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(log.filter((l) => l[0] === 'moveTo').length, 0);
});

test('unfinished auctions: a triangle on a high or low row where both sides traded, none on a one-sided extreme', () => {
  const { ctx, log } = recorder();
  footprint({ unfinished: true }).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(log.filter((l) => l[0] === 'fill').length, 1);          // the top row 101.25 traded both ways; 100.00 had no buyers
  const none = recorder();
  footprint({ unfinished: true }).extras(none.ctx, { fp: [[100, 5, 0], [101, 0, 5]], d: 0 }, 200, 40, 10);
  assert.equal(none.log.filter((l) => l[0] === 'fill').length, 0);
});

test('the delta number sits under the bar in the side colour', () => {
  const { ctx, log } = recorder();
  footprint({ deltaNum: true }).extras(ctx, { fp: FP, d: -12 }, 200, 40, 10);
  const t = log.find((l) => l[0] === 'fillText');
  assert.equal(t[1], '-12');
  assert.equal(t[2], 200);
  assert.ok(t[3] > series.priceToCoordinate(100.0));                   // below the lowest row
  assert.ok(log.some((l) => l[0] === 'set fillStyle' && l[1] === 'DOWN'));
});

test('no extras option: nothing is drawn', () => {
  const { ctx, log } = recorder();
  footprint({}).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.deepEqual(log, []);
});

test('the profile draws the prior session as a ghost and its lines, the POC dashed while it is naked', () => {
  const p = new Profile(P);
  p.series = series; p.tick = TICK;
  p.p = { poc: 100, vah: 101, val: 99, rows: [[100, 10], [101, 4]], prev: { poc: 98, vah: 99, val: 97, rows: [[98, 8], [99, 3]] } };
  const run = (ex) => {
    const { ctx, log } = recorder();
    p.ex = ex;
    p.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
    return log;
  };
  const rects = (log) => log.filter((l) => l[0] === 'fillRect');
  assert.equal(rects(run({})).length, 2);                              // the current profile only
  const ghost = run({ prior: true });
  assert.equal(rects(ghost).length, 4);
  assert.ok(rects(ghost)[2][1] < 1000 - 0.18 * 1000);                  // left of the current one
  const lines = run({ lines: true, naked: true });
  assert.equal(lines.filter((l) => l[0] === 'fillText').map((l) => l[1]).join(), 'pVAH,pVAL,pPOC');
  assert.ok(lines.some((l) => l[0] === 'setLineDash' && l[1].length === 2));    // the naked POC is dashed
  const touched = run({ lines: true, naked: false });
  assert.ok(!touched.some((l) => l[0] === 'setLineDash' && l[1].length === 2));
});

test('a profile with no prior session draws the current one and nothing else', () => {
  const p = new Profile(P);
  p.series = series; p.tick = TICK;
  p.p = { poc: 100, vah: 101, val: 99, rows: [[100, 10]] };
  p.ex = { prior: true, lines: true, naked: true };
  const { ctx, log } = recorder();
  p.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
  assert.equal(log.filter((l) => l[0] === 'fillRect').length, 1);
  assert.equal(log.filter((l) => l[0] === 'fillText').length, 0);
});

test('zoomed out (the footprint is not readable) the extras are not drawn either', () => {
  const f = footprint({ stack: 4, unfinished: true, deltaNum: true });
  f.on = true; f.bars = [{ fp: FP, d: 3, c: 100 }];
  f.chart = { timeScale: () => ({ logicalToCoordinate: (i) => i * 10 }) };     // 10 px a bar: below the 56 px the cells need
  let drew = false;
  f.draw({ useMediaCoordinateSpace: () => { drew = true; } });
  assert.equal(drew, false);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/orderflow-primitives.test.mjs`
Expected: FAIL (`footprint(...).extras is not a function`).

- [ ] **Step 3: Implement**

`homebase/static/charts/primitives.js`:

```diff
--- a/homebase/static/charts/primitives.js
+++ b/homebase/static/charts/primitives.js
@@ -27,15 +27,17 @@ class Layer {
 /* Per bar and price: "sells at bid | buys at ask", a volume bar behind, the
    bar's POC boxed, and diagonal imbalances coloured (buys at P vs sells one
    tick below; sells at P vs buys one tick above) at `ratio`:1. Drawn only
-   when zoomed in far enough to read. */
+   when zoomed in far enough to read. `ex` (2026-10-11): {stack, unfinished, deltaNum} -- a bracket beside runs of
+   `stack` or more stacked imbalances, a triangle where an auction at the bar's high / low did not finish, and
+   the bar's delta under it (HBFlowMath holds the rules). */
 class Footprint extends Layer {
   constructor(P) {
     super(P);
-    this.bars = []; this.ratio = 0; this.tick = 0.25; this.on = false;
+    this.bars = []; this.ratio = 0; this.tick = 0.25; this.on = false; this.ex = {};
     this.onReadableChange = null; this._readable = false;   // last value reported to the callback
     this._timer = null;   // pending setTimeout id for the not-yet-delivered flip, if any
   }
-  set(bars, on, ratio, tick) { this.bars = bars; this.on = on; this.ratio = ratio; this.tick = tick; this.redraw(); }
+  set(bars, on, ratio, tick, ex) { this.bars = bars; this.on = on; this.ratio = ratio; this.tick = tick; this.ex = ex || {}; this.redraw(); }
   readable() {
     if (!this.on || !this.chart || !this.series || !this.bars.length) return false;
     const last = this.bars[this.bars.length - 1];
@@ -88,16 +90,53 @@ class Footprint extends Layer {
           ctx.textAlign = 'left'; ctx.fillStyle = buyImb ? P.up : P.fpText; ctx.fillText(String(bv), x + 3, y);
           if (px === poc[0]) { ctx.strokeStyle = P.poc; ctx.lineWidth = 1; ctx.strokeRect(x - w / 2, y - rh / 2, w, rh - 1); }
         }
+        this.extras(ctx, b, x, w, rh);
       }
     });
   }
+  /* One bar's extras (see the class comment). Nothing here when an option is off or HBFlowMath did not load. */
+  extras(ctx, b, x, w, rh) {
+    const M = window.HBFlowMath, ex = this.ex, P = this.P, s = this.series;
+    if (!M || !ex || !b.fp.length) return;
+    if (ex.stack > 0 && this.ratio > 0) {
+      ctx.lineWidth = 2;
+      for (const r of M.stackedRuns(b.fp, this.tick, this.ratio, ex.stack)) {
+        const y0 = s.priceToCoordinate(r.to), y1 = s.priceToCoordinate(r.from);
+        if (y0 == null || y1 == null) continue;
+        const xx = r.side === 'buy' ? x + w / 2 + 3 : x - w / 2 - 3;     // buyers on the ask (right), sellers on the bid (left)
+        ctx.strokeStyle = r.side === 'buy' ? P.up : P.down;
+        ctx.beginPath(); ctx.moveTo(xx, y0 - rh / 2); ctx.lineTo(xx, y1 + rh / 2); ctx.stroke();
+      }
+    }
+    const u = M.unfinished(b.fp);
+    if (ex.unfinished) {
+      ctx.fillStyle = P.text2;
+      const mark = (px, dir) => {
+        const y = s.priceToCoordinate(px);
+        if (y == null) return;
+        const yy = y + dir * (rh / 2 + 5);
+        ctx.beginPath(); ctx.moveTo(x, yy + dir * 3); ctx.lineTo(x - 4, yy - dir * 3); ctx.lineTo(x + 4, yy - dir * 3); ctx.closePath(); ctx.fill();
+      };
+      if (u.high) mark(u.hi, -1);    // the triangle points at the top row
+      if (u.low) mark(u.lo, 1);      // ... and at the bottom row
+    }
+    if (ex.deltaNum && Number.isFinite(b.d) && window.HBCatalog) {
+      const y = s.priceToCoordinate(u.lo);
+      if (y == null) return;
+      ctx.textAlign = 'center';
+      ctx.fillStyle = b.d >= 0 ? P.up : P.down;
+      ctx.fillText(window.HBCatalog.fmtSigned(b.d), x, y + rh / 2 + (ex.unfinished && u.low ? 16 : 9));
+    }
+  }
 }
 
-/* Session volume profile on the right edge: POC highlighted, value area darker. */
+/* Session volume profile on the right edge: POC highlighted, value area darker. `ex` (2026-10-11): {prior, lines,
+   naked} -- the session before (p.prev, the same shape) as a faint ghost left of the current one, and its VAH / VAL /
+   POC as lines across the chart (the POC dashed while price has not traded back to it: `naked`). */
 class Profile extends Layer {
-  constructor(P) { super(P); this.p = null; this.tick = 0.25; }
+  constructor(P) { super(P); this.p = null; this.tick = 0.25; this.ex = {}; }
   z() { return 'bottom'; }
-  set(p, tick) { this.p = p; this.tick = tick; this.redraw(); }
+  set(p, tick, ex) { this.p = p; this.tick = tick; this.ex = ex || {}; this.redraw(); }
   draw(target) {
     const p = this.p; if (!p || !this.series || !p.rows || !p.rows.length) return;
     target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
@@ -108,6 +147,32 @@ class Profile extends Layer {
         ctx.fillStyle = px === p.poc ? this.P.poc : (px >= p.val && px <= p.vah ? this.P.vaIn : this.P.va);
         const w = W * v / maxV; ctx.fillRect(mediaSize.width - w, y - rh / 2, w, rh);
       }
+      const q = p.prev, ex = this.ex || {};
+      if (!q || !q.rows || !q.rows.length) return;
+      if (ex.prior) {                  // the prior session's ghost, left of the current profile
+        let mq = 1; for (const r of q.rows) if (r[1] > mq) mq = r[1];
+        const qh = Math.max(1, this.rowH(q.poc, this.tick) - 0.5);
+        ctx.globalAlpha = 0.45;
+        for (const [px, v] of q.rows) {
+          const y = this.series.priceToCoordinate(px); if (y == null) continue;
+          ctx.fillStyle = px === q.poc ? this.P.poc : this.P.va;
+          const w = W * v / mq; ctx.fillRect(mediaSize.width - W - 6 - w, y - qh / 2, w, qh);
+        }
+        ctx.globalAlpha = 1;
+      }
+      if (ex.lines) {                  // VAH / VAL / POC of the session before, across the whole pane
+        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
+        ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.lineWidth = 1;
+        for (const [px, name, color, dashed] of [[q.vah, 'pVAH', this.P.text2, false], [q.val, 'pVAL', this.P.text2, false],
+          [q.poc, 'pPOC', this.P.poc, !!ex.naked]]) {
+          const y = px == null ? null : this.series.priceToCoordinate(px); if (y == null) continue;
+          ctx.strokeStyle = color; ctx.fillStyle = color;
+          ctx.setLineDash(dashed ? [6, 4] : []);
+          ctx.beginPath(); ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(mediaSize.width, Math.round(y) + 0.5); ctx.stroke();
+          ctx.setLineDash([]);
+          ctx.fillText(name, 6, y - 2);
+        }
+      }
     });
   }
 }
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/orderflow-primitives.test.mjs`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/primitives.js tests/js/orderflow-primitives.test.mjs
git commit -m "feat(charts): footprint stacked imbalances / unfinished auctions / delta; profile prior session" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 6: The overlays (`HBBookEvents`, `HBFlowLayer`) and the page wiring

**Files:**
- Create: `homebase/static/charts/bookevents.js`, `homebase/static/charts/flowlayer.js`, `tests/js/bookevents.test.mjs`
- Modify: `homebase/static/charts/app.js`, `homebase/static/charts.html`, `homebase/static/backtest.html`

**Interfaces:**
- Consumes: Tasks 1-5; `HBLayers.Layer` (primitives.js), `HBLiquidity.logicalAt` (liquidity.js, loaded before these), `HBDrawings.xOfLogical`.
- Produces: `HBBookEvents.overlay(cell)` (a host overlay like `HBLiquidity.overlay`: `destroy()`, `onBars()`): ended big orders as a segment from where the level appeared to where it ended with a cap (traded = filled square, pulled = hollow circle, faded = none); an absorption marker (green triangle up = a bid absorbed sellers, red down = an offer absorbed buyers); a pulled-liquidity cross at `t1`; it asks the store for the visible span (`HBBookStore.ensure`), and every 250 ms calls `cell.refreshBookSeries`. Pure helpers `segments`, `absorptions`, `pulls` (Node-tested). `HBFlowLayer.overlay(cell)`: heatmap trade bubbles (bottom) from `bar.bub` and sweeps (top) from `bar.sw`. A big order still standing is the live line `l2layer.js` already draws, so only ended ones are drawn here (no doubled line). Bar Replay: nothing is fetched or drawn past the replay cursor.
- Wiring: `app.js` routes `{"type": "bookflow"}` to `HBBookStore.applyLive` (before the per-chart lookup: it has no chart id) and pushes both overlays after `HBLiquidity`; `charts.html` loads `flowdefs.js`, `flowmath.js`, `bookstore.js` before `catalog.js` and `bookevents.js`, `flowlayer.js` after `liquidity.js`; `backtest.html` loads `flowdefs.js` and `flowmath.js` (so a saved layout keeps its order-flow indicators and the footprint extras work there; it has no book store, so a book series is a gap there). The `?v=` numbers of the four changed files go up by one (take the larger of this and what `main` has at merge time).

- [ ] **Step 1: Write the failing tests**

Create `tests/js/bookevents.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const E = require('../../homebase/static/charts/bookevents.js');

const ep = (o) => ({ id: 'x', s: 'b', p: 100, t0: 0, t1: 20_000, pk: 300, r: 6, tr: 0, end: 'faded', ab: null, d0: 5, ...o });

test('segments: ratio and age filters; an open level runs to now', () => {
  const eps = [ep({ id: 'a' }), ep({ id: 'low', r: 3 }), ep({ id: 'short', t1: 2000 }), ep({ id: 'open', t1: null })];
  const s = E.segments(eps, { multiple: 5, minSeconds: 5, now: 60_000 });
  assert.deepEqual(s.map((x) => x.id), ['a', 'open']);
  assert.equal(s[1].t1, 60_000);
  assert.equal(s[1].open, true);
  assert.deepEqual(E.segments(eps, { multiple: 2, minSeconds: 1, now: 60_000 }).map((x) => x.id), ['a', 'low', 'short', 'open']);
});

test('segments: a malformed row is skipped, never throws', () => {
  assert.deepEqual(E.segments([null, {}, ep({ r: NaN })], { multiple: 5, minSeconds: 5 }), []);
  assert.deepEqual(E.segments(undefined), []);
});

test('absorptions: only flagged levels, the bid absorbing is "up"', () => {
  const eps = [ep({ id: 'b', ab: 12_000, r: 8, tr: 700 }), ep({ id: 'a', s: 'a', ab: 15_000, r: 8 }), ep({ id: 'none', ab: null, r: 9 }),
    ep({ id: 'early', ab: 1000, r: 9 })];
  const a = E.absorptions(eps, { multiple: 4, minSeconds: 5 });
  assert.deepEqual(a.map((x) => [x.id, x.side, x.t]), [['b', 'up', 12_000], ['a', 'down', 15_000]]);
});

test('pulls: only ended-as-pulled levels, at the end time', () => {
  const eps = [ep({ id: 'p', end: 'pulled', t1: 30_000 }), ep({ id: 't', end: 'traded' }), ep({ id: 'o', end: 'pulled', t1: null })];
  assert.deepEqual(E.pulls(eps, { multiple: 5, minSeconds: 5 }).map((x) => [x.id, x.t, x.side]), [['p', 30_000, 'b']]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/bookevents.test.mjs`
Expected: FAIL (`Cannot find module ... bookevents.js`).

- [ ] **Step 3: Implement**

Create `homebase/static/charts/bookevents.js`:

```javascript
/* Homebase Charts — HBBookEvents: the book's order-level history drawn on the price pane.
   Three indicators share one overlay and one source (HBBookStore's episodes):
     - "bigorders" (history on): each resting level that cleared `multiple` x the median and stood `minSeconds`, as
       a horizontal segment from where it appeared to where it ended, with a cap that says how it ended: traded =
       filled square, pulled = hollow circle, faded = none. A level still standing is the live line l2layer.js
       already draws (with its size label on the axis), so only ended ones are drawn here: they survive a reload;
     - "absorb": a marker where heavy volume traded into a level that held (the tracker's flag), by the side that
       absorbed (a bid absorbing sellers is green);
     - "pulled": a cross where a big resting order was withdrawn as price came toward it.
   The top half is pure and Node-tested; the overlay (bottom) is browser only, built per chart like every
   host.overlays() entry. Bar Replay: nothing past the replay cursor is drawn. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Store = need('HBBookStore', './bookstore.js');

const PAINT_MS = 250;

/* ---------------------------------------------------------------- pure */

/* Episodes -> the segments to draw. now: the right edge for a level still standing. An episode's `r` is its
   PEAK ratio against the trailing median, so `multiple` filters the same way the live gauge's threshold does. */
function segments(eps, { multiple = 5, minSeconds = 5, now = Infinity } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || !(e.r >= multiple)) continue;
    const t1 = e.t1 == null ? now : e.t1;
    if (!(t1 - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, side: e.s, price: e.p, t0: e.t0, t1, open: e.t1 == null, size: e.pk, end: e.end, traded: e.tr });
  }
  return out;
}

/* Absorption flags: [{id, t, price, side}] where side = 'up' (a bid absorbed sellers) or 'down' (an offer absorbed
   buyers). minSeconds: the level had stood at least this long when it was flagged. */
function absorptions(eps, { multiple = 4, minSeconds = 5 } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || e.ab == null || !(e.r >= multiple) || !(e.ab - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, t: e.ab, price: e.p, side: e.s === 'b' ? 'up' : 'down', traded: e.tr });
  }
  return out;
}

/* Pulled liquidity: [{id, t, price, side}] at the moment the order was withdrawn. side 'b' / 'a' = which side's. */
function pulls(eps, { multiple = 5, minSeconds = 5 } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || e.end !== 'pulled' || e.t1 == null || !(e.r >= multiple) || !(e.t1 - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, t: e.t1, price: e.p, side: e.s });
  }
  return out;
}

const api = { PAINT_MS, segments, absorptions, pulls };

/* ---------------------------------------------------------------- browser */

if (typeof window !== 'undefined' && window.HBLayers && window.HBLiquidity) {
  const { logicalAt } = window.HBLiquidity;

  class EventLayer extends window.HBLayers.Layer {
    constructor(P, ov) { super(P); this.ov = ov; }
    z() { return 'top'; }
    draw(target) { this.ov.draw(target); }
  }

  const inst = (cell, id) => (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;

  class Overlay {
    constructor(cell) {
      this.cell = cell;
      this.dead = false;
      this.dirty = true;
      this.root = cell.shown ? cell.shown.root : cell.cfg.root;
      this.layer = new EventLayer(cell.P || {}, this);
      if (cell.candles) cell.candles.attachPrimitive(this.layer);
      this.live = this.hist = false;     // what changed in the store since the last paint
      this.off = Store.onChange((root, kind) => {
        if (root !== this.root) return;
        this.dirty = true;
        if (kind === 'history') this.hist = true; else this.live = true;
      });
      this.onRange = () => { this.dirty = true; this.ask(); };
      if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
      this.timer = setInterval(() => {
        if (this.dead || !this.on()) return;
        if (this.hist || this.live) {          // the book series (cell.js point()): all bars after a fetch, else the newest
          if (this.cell.refreshBookSeries) this.cell.refreshBookSeries(this.hist);
          this.hist = this.live = false;
        }
        if (this.dirty) { this.dirty = false; this.layer.redraw(); }
      }, PAINT_MS);
      this.ask();
    }

    /* Anything of ours on the chart: the three marker indicators, or a series computed from the book (a key
       that starts with "bk:", flowdefs.js). */
    on() {
      const c = this.cell;
      if (this.dead || !c.chart || !c.bars || !c.bars.length) return false;
      if (inst(c, 'bigorders') || inst(c, 'absorb') || inst(c, 'pulled')) return true;
      return (c.cfg.indicators || []).some((x) => x.visible !== false && String(window.HBCatalog.serverKey(x) || '').startsWith('bk:'));
    }

    window() {
      const c = this.cell, bars = c.bars, ts = c.chart.timeScale(), vr = ts.getVisibleLogicalRange();
      if (!bars.length || !vr) return null;
      const barMs = c.isTime() ? c.barMs() : 0, last = bars[bars.length - 1].ms;
      const end = barMs ? last + barMs : last;
      const i0 = Math.max(0, Math.floor(vr.from)), i1 = Math.min(bars.length - 1, Math.ceil(vr.to));
      return { bars, barMs, end, from: bars[i0].ms, to: i1 >= bars.length - 1 ? end : bars[i1 + 1].ms };
    }

    /* Ask the store for the visible span (it fetches only what it does not hold, in aligned chunks). */
    ask() {
      if (!this.on() || this.cell.replay) return;
      const w = this.window();
      if (w) Store.ensure(this.root, w.from, Math.min(w.to, Date.now()));
    }

    draw(target) {
      if (!this.on()) return;
      this.root = this.cell.shown ? this.cell.shown.root : this.cell.cfg.root;
      const w = this.window();
      if (!w) return;
      const cell = this.cell, P = cell.P || {}, series = cell.candles, ts = cell.chart.timeScale();
      const replay = !!cell.replay, cursor = replay && Number.isFinite(cell.replay.cursorMs) ? cell.replay.cursorMs : null;
      const now = replay ? (cursor == null ? w.end : Math.min(cursor, w.end)) : Math.min(Date.now(), Math.max(w.end, w.bars[w.bars.length - 1].ms));
      const eps = Store.episodes(this.root, w.from - 3_600_000, Math.min(w.to, now)).filter((e) => e.t0 <= now);
      const xs = new Map();
      const X = (t) => {
        let x = xs.get(t);
        if (x === undefined) { x = window.HBDrawings.xOfLogical(logicalAt(w.bars, t, w.barMs, w.end), (i) => ts.logicalToCoordinate(i)); xs.set(t, x); }
        return x;
      };
      const big = inst(cell, 'bigorders'), ab = inst(cell, 'absorb'), pu = inst(cell, 'pulled');
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        if (big && big.params.history !== false) {
          const segs = segments(eps, { multiple: big.params.multiple, minSeconds: big.params.minSeconds, now });
          for (const s of segs) {
            if (s.open) continue;
            const x0 = X(s.t0), x1 = X(s.t1), y = series.priceToCoordinate(s.price);
            if (x0 == null || x1 == null || y == null || x1 < 0 || x0 > mediaSize.width) continue;
            const col = s.side === 'b' ? (P.accent || '#2962FF') : (P.down || '#F23645');
            ctx.strokeStyle = col; ctx.globalAlpha = s.open ? 0.9 : 0.6; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
            ctx.globalAlpha = 1;
            if (!s.open && s.end === 'traded') { ctx.fillStyle = col; ctx.fillRect(x1 - 2.5, y - 2.5, 5, 5); }
            else if (!s.open && s.end === 'pulled') { ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x1, y, 3.5, 0, Math.PI * 2); ctx.stroke(); }
          }
        }
        if (ab) {
          for (const a of absorptions(eps, { multiple: ab.params.multiple, minSeconds: ab.params.minSeconds })) {
            const x = X(a.t), y = series.priceToCoordinate(a.price);
            if (x == null || y == null || x < 0 || x > mediaSize.width) continue;
            ctx.fillStyle = a.side === 'up' ? (P.up || '#089981') : (P.down || '#F23645');
            ctx.beginPath();
            if (a.side === 'up') { ctx.moveTo(x, y - 7); ctx.lineTo(x - 5, y + 3); ctx.lineTo(x + 5, y + 3); }
            else { ctx.moveTo(x, y + 7); ctx.lineTo(x - 5, y - 3); ctx.lineTo(x + 5, y - 3); }
            ctx.closePath(); ctx.fill();
          }
        }
        if (pu) {
          ctx.lineWidth = 1.5;
          for (const p of pulls(eps, { multiple: pu.params.multiple, minSeconds: pu.params.minSeconds })) {
            const x = X(p.t), y = series.priceToCoordinate(p.price);
            if (x == null || y == null || x < 0 || x > mediaSize.width) continue;
            ctx.strokeStyle = p.side === 'b' ? (P.accent || '#2962FF') : (P.down || '#F23645');
            ctx.beginPath(); ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); ctx.stroke();
          }
        }
      });
    }

    onBars() { this.dirty = true; this.ask(); }

    destroy() {
      this.dead = true;
      clearInterval(this.timer);
      if (this.off) this.off();
      const cell = this.cell;
      try { if (cell.chart) cell.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
      try { if (cell.candles) cell.candles.detachPrimitive(this.layer); } catch (_) { /* series gone */ }
    }
  }

  api.overlay = (cell) => new Overlay(cell);
  window.HBBookEvents = api;
}
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

Create `homebase/static/charts/flowlayer.js`:

```javascript
/* Homebase Charts — HBFlowLayer: what the bars' tick fields add on the price pane, one overlay per chart:
     - heatmap trade bubbles (param `bubbles` of the "heatmap" indicator): executed trades of >= `bubbleMin`
       contracts per second, price and side, as circles sized by their size, behind the candles;
     - sweeps (param `sweeps` of "bigprints"): one aggressor walking several price levels inside one
       millisecond, as a vertical span from the first to the last price with a chevron on the side.
   Both read `bar.bub` / `bar.sw`, which the server sends on the bar wire's own `flow` flag, so cell.need()
   asks for them only while either option is on. Pure pieces live in flowmath.js (Node-tested). */
(function () {
'use strict';
if (typeof window === 'undefined' || !window.HBLayers || !window.HBLiquidity || !window.HBFlowMath) return;
const { logicalAt } = window.HBLiquidity, M = window.HBFlowMath;

const PAINT_MS = 250;
const inst = (cell, id) => (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;

class BubbleLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'bottom'; }
  draw(target) { this.ov.drawBubbles(target); }
}
class SweepLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'top'; }
  draw(target) { this.ov.drawSweeps(target); }
}

class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.dirty = true;
    const P = cell.P || {};
    this.bub = new BubbleLayer(P, this);
    this.swp = new SweepLayer(P, this);
    if (cell.candles) { cell.candles.attachPrimitive(this.bub); cell.candles.attachPrimitive(this.swp); }
    this.timer = setInterval(() => {
      if (this.dead || !this.dirty) return;
      this.dirty = false;
      this.bub.redraw(); this.swp.redraw();
    }, PAINT_MS);
    this.onRange = () => { this.dirty = true; };
    if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
  }

  /* The visible bars' index range and the mapping from a time to an x, or null when there is nothing to draw. */
  frame() {
    const c = this.cell;
    if (this.dead || !c.chart || !c.bars || !c.bars.length) return null;
    const ts = c.chart.timeScale(), vr = ts.getVisibleLogicalRange();
    if (!vr) return null;
    const bars = c.bars, barMs = c.isTime() ? c.barMs() : 0, last = bars[bars.length - 1].ms;
    const end = barMs ? last + barMs : last;
    const i0 = Math.max(0, Math.floor(vr.from) - 1), i1 = Math.min(bars.length - 1, Math.ceil(vr.to) + 1);
    const X = (t) => window.HBDrawings.xOfLogical(logicalAt(bars, t, barMs, end), (i) => ts.logicalToCoordinate(i));
    return { bars, i0, i1, X, series: c.candles, P: c.P || {} };
  }

  drawBubbles(target) {
    const h = inst(this.cell, 'heatmap');
    if (!h || !h.params.bubbles) return;
    const f = this.frame();
    if (!f) return;
    const min = h.params.bubbleMin, hi = Math.max(min * 20, 200);
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (let i = f.i0; i <= f.i1; i++) {
        for (const b of M.bubblesOf(f.bars[i], min)) {
          const x = f.X(b.t), y = f.series.priceToCoordinate(b.price);
          if (x == null || y == null || x < -20 || x > mediaSize.width + 20) continue;
          ctx.fillStyle = b.side > 0 ? 'rgba(8,153,129,.45)' : 'rgba(242,54,69,.45)';
          ctx.strokeStyle = b.side > 0 ? '#089981' : '#F23645';
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(x, y, M.bubbleRadius(b.size, min, hi), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
      }
    });
  }

  drawSweeps(target) {
    const bp = inst(this.cell, 'bigprints');
    if (!bp || !bp.params.sweeps) return;
    const f = this.frame();
    if (!f) return;
    const min = bp.params.min;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = 2;
      for (let i = f.i0; i <= f.i1; i++) {
        for (const s of M.sweepsOf(f.bars[i], min)) {
          const x = f.X(s.t), y0 = f.series.priceToCoordinate(s.from), y1 = f.series.priceToCoordinate(s.to);
          if (x == null || y0 == null || y1 == null || x < -10 || x > mediaSize.width + 10) continue;
          const col = s.side > 0 ? (f.P.up || '#089981') : (f.P.down || '#F23645');
          ctx.strokeStyle = col; ctx.fillStyle = col;
          ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
          const tip = s.side > 0 ? Math.min(y0, y1) : Math.max(y0, y1), d = s.side > 0 ? 6 : -6;   // buyers lift: up
          ctx.beginPath(); ctx.moveTo(x, tip - d); ctx.lineTo(x - 4, tip); ctx.lineTo(x + 4, tip); ctx.closePath(); ctx.fill();
        }
      }
    });
  }

  onBars() { this.dirty = true; }

  destroy() {
    this.dead = true;
    clearInterval(this.timer);
    const c = this.cell;
    try { if (c.chart) c.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
    for (const l of [this.bub, this.swp]) { try { if (c.candles) c.candles.detachPrimitive(l); } catch (_) { /* series gone */ } }
  }
}

window.HBFlowLayer = { overlay: (cell) => new Overlay(cell) };
})();
```

Wiring, `homebase/static/charts/app.js`:

```diff
--- a/homebase/static/charts/app.js
+++ b/homebase/static/charts/app.js
@@ -2331,6 +2331,7 @@ function connect() {
     if (m.type === 'paper') { window.HBPaperClient?.onMessage(m); return; }
     if (m.type === 'paperbook') { window.HBPaperClient?.onBook(m); window.HBDeskClient?.bookChanged(); return; }   // the PAPER account
     if (m.type === 'depth') { window.HBDomUI?.onDepth(m); window.HBL2Layer?.onDepth(m); window.HBLiquidity?.onDepth(m); return; }
+    if (m.type === 'bookflow') { window.HBBookStore?.applyLive(m); return; }   // the book's seconds + order levels (booklive.py)
     if (m.type === 'news' || m.type === 'burst' || m.type === 'burst_update') { window.HBNewsUI?.onMessage(m); return; }
     if (m.type === 'tester_show') { window.HBTesterUI?.show(m); return; }   // Claude's "show on chart" (POST /api/tester/show)
     const c = cells.find((x) => x.id === m.id);
@@ -2480,6 +2481,8 @@ async function init() {
   if (window.HBTesterLayer) page.overlays.push(window.HBTesterLayer.overlay);  // Task 10: the tester's trades, plots and jump on the root's chart
   if (window.HBL2Layer) page.overlays.push(window.HBL2Layer.overlay);      // charts-l2-news-ui Task 2: big-order lines + the imbalance gauge
   if (window.HBLiquidity) page.overlays.push(window.HBLiquidity.overlay);    // charts-l2-news-ui Task 3: the liquidity heatmap behind the candles
+  if (window.HBBookEvents) page.overlays.push(window.HBBookEvents.overlay);  // 2026-10-11: ended big orders, absorption, pulled liquidity, the book series
+  if (window.HBFlowLayer) page.overlays.push(window.HBFlowLayer.overlay);    // 2026-10-11: heatmap trade bubbles, big-print sweeps
   if (window.HBNewsUI) page.overlays.push(window.HBNewsUI.overlay);       // 2026-09-27 news-ui plan, Task 4: headline ticks + burst markers
   // M8 (tester review): HBTesterUI.mount registers the 'tester' tab via HBPanel.addTab, so it runs BEFORE
   // HBPanel.mount reads a saved {tab: 'tester'} -- otherwise a saved tester tab is not restored on reload.
```

`homebase/static/charts.html`:

```diff
--- a/homebase/static/charts.html
+++ b/homebase/static/charts.html
@@ -95,8 +95,11 @@
 <script src="/static/vendor/lightweight-charts-5.2.1.js?v=33"></script>
 <script src="/static/charts/icons.js?v=34"></script>
 <script src="/static/charts/spring.js?v=33"></script>
-<script src="/static/charts/catalog.js?v=35"></script>
-<script src="/static/charts/primitives.js?v=36"></script>
+<script src="/static/charts/flowdefs.js?v=1"></script>
+<script src="/static/charts/flowmath.js?v=1"></script>
+<script src="/static/charts/bookstore.js?v=1"></script>
+<script src="/static/charts/catalog.js?v=36"></script>
+<script src="/static/charts/primitives.js?v=37"></script>
 <script src="/static/charts/drawstyle.js?v=34"></script>
 <script src="/static/charts/drawings.js?v=34"></script>
 <script src="/static/charts/position.js?v=33"></script>
@@ -105,7 +108,7 @@
 <script src="/static/charts/events.js?v=33"></script>
 <script src="/static/charts/news.js?v=33"></script>
 <script src="/static/charts/scrollback.js?v=33"></script>
-<script src="/static/charts/cell.js?v=38"></script>
+<script src="/static/charts/cell.js?v=39"></script>
 <script src="/static/charts/settings-dialog.js?v=38"></script>
 <script src="/static/charts/indicator-settings-dialog.js?v=36"></script>
 <script src="/static/charts/chartmenu.js?v=33"></script>
@@ -124,12 +127,14 @@
      (backtest.html loads tester.js/testerui.js/testerlayer.js/replay.js/replayui.js) -->
 <script src="/static/charts/l2layer.js?v=33"></script>
 <script src="/static/charts/liquidity.js?v=33"></script>
+<script src="/static/charts/bookevents.js?v=1"></script>
+<script src="/static/charts/flowlayer.js?v=1"></script>
 <script src="/static/charts/orderpanel.js?v=33"></script>
 <script src="/static/charts/panellayout.js?v=33"></script>
 <script src="/static/charts/panelshell.js?v=33"></script>
 <script src="/static/charts/layouts.js?v=33"></script>
 <script src="/static/charts/presets.js?v=33"></script>
-<script src="/static/charts/app.js?v=38"></script>
+<script src="/static/charts/app.js?v=39"></script>
 <script src="/static/hb-glass.js?v=2"></script>
 </body>
 </html>
```

`homebase/static/backtest.html`:

```diff
--- a/homebase/static/backtest.html
+++ b/homebase/static/backtest.html
@@ -127,8 +127,10 @@
 <script src="/static/vendor/lightweight-charts-5.2.1.js?v=33"></script>
 <script src="/static/charts/icons.js?v=34"></script>
 <script src="/static/charts/spring.js?v=33"></script>
-<script src="/static/charts/catalog.js?v=35"></script>
-<script src="/static/charts/primitives.js?v=36"></script>
+<script src="/static/charts/flowdefs.js?v=1"></script>
+<script src="/static/charts/flowmath.js?v=1"></script>
+<script src="/static/charts/catalog.js?v=36"></script>
+<script src="/static/charts/primitives.js?v=37"></script>
 <script src="/static/charts/drawstyle.js?v=34"></script>
 <script src="/static/charts/drawings.js?v=34"></script>
 <script src="/static/charts/position.js?v=33"></script>
@@ -136,7 +138,7 @@
 <script src="/static/charts/dataexport.js?v=35"></script>
 <script src="/static/charts/events.js?v=33"></script>
 <script src="/static/charts/scrollback.js?v=33"></script>
-<script src="/static/charts/cell.js?v=38"></script>
+<script src="/static/charts/cell.js?v=39"></script>
 <script src="/static/charts/settings-dialog.js?v=38"></script>
 <script src="/static/charts/indicator-settings-dialog.js?v=36"></script>
 <script src="/static/charts/chartmenu.js?v=33"></script>
@@ -150,7 +152,7 @@
 <script src="/static/charts/panellayout.js?v=33"></script>
 <script src="/static/charts/layouts.js?v=33"></script>
 <script src="/static/charts/presets.js?v=33"></script>
-<script src="/static/charts/app.js?v=38"></script>
+<script src="/static/charts/app.js?v=39"></script>
 <script src="/static/charts/labcode.js?v=15"></script>
 <script src="/static/charts/lab.js?v=54"></script>
 <script src="/static/charts/labstep.js?v=1"></script>
```

- [ ] **Step 4: Run the whole JS suite and the Python wrapper**

Run: `node --test tests/js/*.test.mjs`
Expected: every test passes (this plan adds 40 tests in six new files and changes three existing files; the scratch copy's one failure was a test that needs the real repo's environment, not this work).

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_js.py`
Expected: PASS (it runs the same suite and checks no `*.test.*` file sits under `homebase/static`).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/bookevents.js homebase/static/charts/flowlayer.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/backtest.html tests/js/bookevents.test.mjs
git commit -m "feat(charts): book events + flow overlays, bookflow ws route, script tags" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Look at it on a recorded day, then hand over

**Files:** none (verification; the owner reviews the first-guess numbers).

- [ ] **Step 1: Run the worktree's page on a replay service (never the live 8852)**

From the worktree (Plan A and this plan both applied), in the background:
```bash
.venv/bin/python -m homebase.charts --replay 2026-10-08 --speed 20 --start 09:40 --port 8855
```
(`.venv` is the main checkout's: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python`.) A replay service serves the worktree's static files, replays the recorded ticks, and answers `/api/book/history` from the recorded depth files (the 09:20-09:35 ET pause is by wall clock, so check outside it). It has no live book, so the `bookflow` ws message is not exercised here: that is Step 3.

- [ ] **Step 2: Open `http://127.0.0.1:8855/` in the preview and check each item on NQ 1-minute bars, 2026-10-08**

| Item | Add this | You should see |
|---|---|---|
| 1 Big orders | Big orders (multiple 5) | ended levels stay as short horizontal segments with a square (traded) or a hollow circle (pulled); a reload keeps them |
| 2 Imbalance over time | Book imbalance (over time), levels 10 | a histogram pane, green above 0, red below; values move with the bars |
| 3 Heatmap bubbles | Liquidity heatmap, `Trade bubbles` on | circles, green buys / red sells, bigger = more contracts; turning it off removes them and the bar payload shrinks (Network tab: `history` message) |
| 4 Footprint extras | Footprint, zoomed in | a coloured bracket beside runs of 3+ stacked imbalances, small triangles at a high / low row, the bar delta under each bar |
| 5 Profile prior | Volume profile, `Show the prior session` on, `Prior VAH / VAL / POC lines` on | a faint ghost left of today's profile; lines labelled pVAH / pVAL / pPOC; the POC dashed until it is traded |
| 6 Big prints | Big prints, `Marker size follows the print size` on, `Mark sweeps` on | bigger prints = bigger dots; a vertical span with a chevron for a sweep |
| 7 Absorption | Absorption | a triangle where heavy volume traded into a level that held |
| 8 Pulled liquidity | Pulled liquidity | an x where a big order was withdrawn |
| 9 Depth + microprice | Book depth (bid vs ask), Microprice | a pane with a green bid line and a red ask line; a violet line hugging price |
| 10 Delta divergence | Delta divergence 5 | an arrow on a swing bar, appearing 5 bars after it, never moving |
| 11 Tape speed | Tape speed 200 | grey bars, orange where above the dashed burst line |

For each: toggling it off and on again leaves nothing behind; the gear opens its settings with the new fields; the browser console has no errors; a 5-minute and a 500-tick chart show the same series.

- [ ] **Step 3: After the Plan A merge and the gated restart, on the live service**

Open a live NQ chart with Big orders and Absorption: a standing level shows as the existing line, becomes a segment with a cap when it ends, and a reload keeps it; `/api/book/history` for the last hour returns samples (curl it: `curl -s 'http://127.0.0.1:8852/api/book/history?root=NQ&from_ms=<now-3600000>&to_ms=<now>' | head -c 300`). Check `desk_status` before and after the restart (restart gate).

- [ ] **Step 4: Tell the owner the numbers are first guesses**

List `bookflow.TUNING`, `OPEN_RATIO = 3`, `CLOSE_RATIO = 2`, the `minSeconds` defaults (5), the absorption multiple (4) and the pulled multiple (5), and ask which to change after a few real days. State plainly that these are chart-reading aids, not strategies: an idea that uses one goes through the pipeline.

---
