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

/* An episode that has ended carries a t1 or an `end` other than "open". The history endpoint masks an episode that
   outlives the requested `to` as open (t1 null) as of that `to`, so a chunk fetched later can hold a staler, open copy
   of an episode a newer chunk already closed. */
const isClosed = (e) => e.t1 != null || (e.end != null && e.end !== 'open');

/* Does the incoming copy `n` replace the stored copy `o`? Only if it is at least as complete: never open over closed;
   closed over open; between two closed ones the larger t1; between two open ones the later copy (live updates). */
function moreComplete(n, o) {
  const nc = isClosed(n), oc = isClosed(o);
  if (nc !== oc) return nc;
  if (!nc) return true;
  const a = n.t1 == null ? -Infinity : n.t1, b = o.t1 == null ? -Infinity : o.t1;
  return a >= b;
}

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
    const ordered = clean.every((r, i) => i === 0 || r[0] >= clean[i - 1][0]);
    if (ordered && clean[0][0] >= last) {
      // in order, or repeating the newest t (the live tracker may re-emit a second): append, a repeated t replaces
      // the tail row (the later copy wins). No rebuild: this is the per-second hot path.
      for (const r of clean) {
        const n = this.rows.length;
        if (n && this.rows[n - 1][0] === r[0]) this.rows[n - 1] = r; else this.rows.push(r);
      }
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
      if (!e || typeof e.id !== 'string' || !Number.isFinite(e.t0)) continue;
      const old = this.eps.get(e.id);
      if (!old || moreComplete(e, old)) this.eps.set(e.id, e);
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
