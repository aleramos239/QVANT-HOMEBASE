/* Homebase Charts — HBNewsUI: the browser half of Task 4 (2026-09-27 plan) --
     - a live news store fed by GET /api/news (backfill) and the /ws "news"/"burst"/"burst_update" messages
       (app.js's connect() routes them here -- see the `type === 'news' || ...` branch);
     - the "News" bottom-panel tab (HBPanel.addTab): a live headline stream, newest first, with a source/tag
       filter chip bar, Trump posts highlighted, and a 3 s "breaking" flash on arrival;
     - a per-chart overlay (page.overlays, like HBTradeLines/HBTesterLayer) drawing headline ticks (every
       chart) and burst ⚡ markers (only on charts of the burst's own root) through cell.setExtraMarkers, with
       a hover tooltip built the same way tradelines.js's bot/paper markers are (crosshair-move + nearestTip).
   The pure logic (merge/dedupe, filters, the burst<->headline link, ET formatting, the marker records
   themselves) lives in news.js; this file only owns the DOM, the ws wiring and the chart primitives.
   Browser only. */
(() => {
'use strict';
const N = window.HBNews;
const T = window.HBTrade;    // diffRows: the same keyed list-patch helper panel.js's tables use

/* ---- the store: GET /api/news backfill + the three ws message types, one shared state for the panel and
   every chart's markers ---- */
const store = { items: [], bursts: [], filter: { sources: [], tags: [] }, loaded: false };
const subs = new Set();
function on(fn) { subs.add(fn); return () => subs.delete(fn); }
let queued = false;
function emit() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    for (const fn of [...subs]) { try { fn(); } catch (e) { console.error(e); } }
  });
}

async function loadInitial() {
  try {
    const r = await fetch('/api/news');
    if (!r.ok) return;
    const items = await r.json();
    if (Array.isArray(items)) { store.items = N.mergeItems(store.items, items); store.loaded = true; emit(); }
  } catch (_) { /* the panel just starts empty; the ws stream still fills it live */ }
}

/* A news item's flash ends on its own (news.js's isBreaking is a pure function of the clock, not a stored
   flag) -- this only makes sure something re-renders once it does, so the marker colour and the panel row
   actually flip back without needing a per-second poll of every chart. */
function scheduleUnflash(item) {
  const left = item.seen_ms + N.FLASH_MS - Date.now();
  if (left > 0) setTimeout(emit, left + 50);
}

function onMessage(m) {
  if (m.type === 'news') {
    const { type, ...item } = m;
    store.items = N.mergeItems(store.items, [item]);
    scheduleUnflash(item);
    emit();
    return;
  }
  if (m.type === 'burst' || m.type === 'burst_update') {
    const { type, ...burst } = m;
    store.bursts = N.mergeBursts(store.bursts, [burst]);
    emit();
  }
}

function toggleFilter(axis, value) {
  const set = new Set(store.filter[axis]);
  if (set.has(value)) set.delete(value); else set.add(value);
  store.filter = { ...store.filter, [axis]: [...set] };
  emit();
}

/* ---- jump-to-time (spec: "reusing the tester layer's jump/focusRange if available, otherwise
   scrollToTime") -- the selected chart only, never every chart. cell.reach()/cell.focusRange() are the same
   primitives testerlayer.js's jump() drives; scrollToTime is the plain fallback for a chart object that
   doesn't expose them (or has no bars loaded yet). */
function scrollToTime(cell, ms) {
  if (!cell || !cell.chart || !cell.bars || !cell.bars.length || !window.HBDrawings) return false;
  const i = window.HBDrawings.barIndexAt(cell.bars, ms);
  if (i < 0) return false;
  cell.chart.timeScale().setVisibleLogicalRange({ from: i - 30, to: i + 30 });
  return true;
}
let PAGE = null;
async function jumpTo(ms) {
  const cell = PAGE && PAGE.cur();
  if (!cell) return;
  if (typeof cell.reach === 'function' && typeof cell.focusRange === 'function') {
    const ok = await cell.reach(ms, () => {});
    if (ok) cell.focusRange(ms, ms);
    else scrollToTime(cell, ms);
    return;
  }
  scrollToTime(cell, ms);
}

/* ---- DOM helpers (every cell by textContent, like panel.js) ---- */
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function chip(text, pressed, onClick, cls) {
  const b = mk('button', `hb-news-chip${cls ? ` ${cls}` : ''}`, text);
  b.type = 'button';
  b.setAttribute('aria-pressed', String(!!pressed));
  b.onclick = onClick;
  return b;
}

/* ---- the panel tab ---- */
let barEl = null, listEl = null, emptyEl = null, showing = false;

function renderBar() {
  barEl.replaceChildren();
  for (const src of Object.keys(N.SOURCE_LABELS)) {
    barEl.appendChild(chip(N.sourceLabel(src), store.filter.sources.includes(src), () => toggleFilter('sources', src)));
  }
  const tags = N.availableTags(store.items);
  if (tags.length) {
    const sep = mk('span', 'hb-news-sep');
    barEl.appendChild(sep);
    for (const t of tags) barEl.appendChild(chip(t, store.filter.tags.includes(t), () => toggleFilter('tags', t), 'tag'));
  }
}

function buildRow(it) {
  const row = mk('div', 'hb-news-row');
  row.dataset.id = it.id;
  if (N.isTrump(it)) row.classList.add('trump');
  row.appendChild(mk('span', `hb-news-src ${it.source}`, N.sourceLabel(it.source)));
  row.appendChild(mk('span', 'hb-news-time', N.etTime(it.t_ms)));
  const title = mk('button', 'hb-news-title', it.title);
  title.type = 'button';
  title.title = it.title;
  title.onclick = () => jumpTo(it.t_ms);
  row.appendChild(title);
  if (it.tags && it.tags.length) {
    const tagsWrap = mk('span', 'hb-news-tags');
    for (const t of it.tags) tagsWrap.appendChild(mk('span', 'hb-news-tag', t));
    row.appendChild(tagsWrap);
  }
  if (N.isBreaking(it, Date.now())) {
    row.classList.add('breaking');
    const left = it.seen_ms + N.FLASH_MS - Date.now();
    if (left > 0) setTimeout(() => row.classList.remove('breaking'), left);
  }
  return row;
}

/* Keyed patch (panel.js's syncTable, for a plain list instead of a <table>): a news item never changes once
   published, so there is no update path -- only add/remove/reorder. */
function syncList(container, items) {
  const existing = new Map();
  for (const row of container.children) existing.set(row.dataset.id, row);
  const plan = T.diffRows([...existing.keys()], items, (it) => it.id);
  for (const k of plan.remove) { const row = existing.get(k); if (row) row.remove(); }
  let prev = null;
  for (const it of items) {
    let row = existing.get(it.id);
    if (!row) row = buildRow(it);
    container.insertBefore(row, prev ? prev.nextSibling : container.firstChild);
    prev = row;
  }
}

function patchPanel() {
  if (!listEl) return;
  renderBar();
  const filtered = N.filterItems(store.items, store.filter);
  if (!filtered.length) {
    listEl.replaceChildren();
    emptyEl.textContent = store.loaded ? 'No headlines yet' : 'Loading…';
    listEl.appendChild(emptyEl);
    return;
  }
  syncList(listEl, filtered);
}

function render(target) {
  if (target.querySelector(':scope > .hb-news')) { patchPanel(); return; }   // a re-render onto live DOM: patch, never rebuild
  const root = mk('div', 'hb-news');
  barEl = mk('div', 'hb-news-bar');
  listEl = mk('div', 'hb-news-list');
  emptyEl = mk('div', 'bp-empty');
  root.append(barEl, listEl);
  target.appendChild(root);
  patchPanel();
}
function onShow() { showing = true; patchPanel(); }
function onHide() { showing = false; }

/* ---- per-chart overlay: headline ticks (every chart) + burst markers (the burst's own root only) ---- */
class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.tips = [];               // [{ms, position, tip}], matched to the mouse by hoverTip (nearestTip)
    this.newsSig = null;
    this.burstSig = null;
    this.layer = mk('div', 'hb-news-layer');
    cell.el.appendChild(this.layer);
    this.tip = mk('div', 'ev-tip hb-news-tip');
    this.tip.hidden = true;
    this.layer.appendChild(this.tip);
    this.onMove = (p) => this.hoverTip(p);
    cell.chart.subscribeCrosshairMove(this.onMove);
    this.unsub = on(() => this.render());
    this.render();
  }

  onBars() { this.render(); }
  onSettings() { this.render(); }   // the chart's "News on chart" setting changed (cell.applySettings)

  /* The loaded-bar range this chart can actually place a marker in (tradelines.js's own convention for its
     bot/paper markers) -- not the visible viewport, but bounded well short of "every headline ever stored". */
  range() {
    const bars = this.cell.bars;
    if (!bars.length) return null;
    const barMs = this.cell.barMs();
    return { fromMs: bars[0].ms, toMs: barMs > 0 ? bars[bars.length - 1].ms + barMs : Infinity };
  }

  render() {
    if (this.dead || !this.cell.chart) return;
    const r = this.range();
    if (!r) {
      if (this.newsSig !== null) { this.newsSig = null; this.cell.setExtraMarkers('news', []); }
      if (this.burstSig !== null) { this.burstSig = null; this.cell.setExtraMarkers('bursts', []); }
      this.tips = [];
      return;
    }
    const filtered = N.filterItems(store.items, store.filter);
    const show = N.chartNews(this.cell.R && this.cell.R.newsOnChart, store.bursts, store.items);   // ⚙ → Events → News
    const hlist = show.headlines ? N.headlineMarkers(filtered, { fromMs: r.fromMs, toMs: r.toMs, nowMs: Date.now() }) : [];
    const root = (this.cell.shown || this.cell.cfg).root;
    const blist = N.burstMarkers(show.bursts, { root, fromMs: r.fromMs, toMs: r.toMs }, store.items);
    const hSig = JSON.stringify(hlist.map((m) => [m.id, m.color]));
    if (hSig !== this.newsSig) { this.newsSig = hSig; this.cell.setExtraMarkers('news', hlist.map(({ tip, ...m }) => m)); }
    const bSig = JSON.stringify(blist.map((m) => [m.id, m.color]));
    if (bSig !== this.burstSig) { this.burstSig = bSig; this.cell.setExtraMarkers('bursts', blist.map(({ tip, ...m }) => m)); }
    this.tips = [...hlist, ...blist].map((m) => ({ ms: m.ms, position: m.position, tip: m.tip }));
  }

  /* The tooltip of the headline/burst marker under the mouse (tradelines.js's own hoverTip, HBTrade.nearestTip
     within 10 px): aboveBar sits at the bar's high, belowBar at its low -- both markers here are anchored to
     the bar's own OHLC, never a stored price. */
  hoverTip(p) {
    const c = this.cell;
    if (this.dead || !c.chart || !p || !p.point || !this.tips.length || !c.bars.length) { this.tip.hidden = true; return; }
    const D = window.HBDrawings, ts = c.chart.timeScale(), pts = [];
    for (const m of this.tips) {
      const i = D.barIndexAt(c.bars, m.ms);
      if (i < 0) continue;
      const b = c.bars[i], x = ts.timeToCoordinate(b.tt);
      const y = c.candles.priceToCoordinate(m.position === 'belowBar' ? b.l : b.h);
      if (x == null || y == null) continue;
      pts.push({ x, y: m.position === 'belowBar' ? y + 12 : y - 12, tip: m.tip });
    }
    const text = T.nearestTip(pts, p.point.x, p.point.y, 10);
    if (!text) { this.tip.hidden = true; return; }
    this.tip.textContent = text;
    this.tip.hidden = false;
    const w = this.layer.clientWidth, tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(4, Math.min(w - tw - 4, p.point.x + 12))}px`;
    this.tip.style.top = `${Math.max(4, p.point.y - 30)}px`;
  }

  destroy() {
    this.dead = true;
    this.unsub();
    if (this.cell.chart) this.cell.chart.unsubscribeCrosshairMove(this.onMove);
    this.layer.remove();
    this.cell.setExtraMarkers('news', []);
    this.cell.setExtraMarkers('bursts', []);
  }
}

function mount(page) {
  PAGE = page;
  loadInitial();
  on(() => { if (showing) patchPanel(); });   // the tab's own live patch -- gated so a hidden tab does no work
  window.HBPanel.addTab({ id: 'news', label: 'News', render, onShow, onHide });
}

window.HBNewsUI = { mount, onMessage, overlay: (cell) => new Overlay(cell) };
})();
