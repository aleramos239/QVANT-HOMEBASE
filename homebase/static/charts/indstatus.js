/* Homebase Charts — HBStatus: why an indicator shows nothing (or how much it shows), in a few plain words, for the
   legend. The pure half (of) is Node-tested; the page gathers the facts (cell.js statusFacts) and draws the note.
     of(inst, facts) -> null (nothing to say) | { text, tone: 'info' | 'warn', act?: 'zoom', title? (the long form, for the hover) }
   facts: { bars, i0, i1 (the bars in view), readable (the footprint's numbers fit), book: { rows, covered, live },
            episodes (the book's order episodes in view), M (HBFlowMath), E (HBBookEvents' pure half),
            indicators (the chart's list, for "only the first draws"), barMs (0 off a time chart), spacing (px a bar),
            pine: { [uid]: { error, notes: [the script's warnings], running } } }. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);

const BOOK_IDS = new Set(['bigorders', 'absorb', 'pulled', 'iceberg', 'bkimb', 'bkdepth', 'bkmicro', 'bkquote']);
// the order-flow apps (2026-10-21) read a field that only bars loaded since then carry: [the field, what it holds in plain words]
const FIELD = { bigtrades: ['ag', 'order detail'], npoc: ['fp', 'trade detail'], mwabs: ['fp', 'trade detail'], pzone: ['fp', 'trade detail'], dstr: ['dmax', 'delta highs and lows'],
  stoprun: ['sw', 'sweep detail'] };
const noun = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const info = (text) => ({ text, tone: 'info' });
// the indicators that draw only their first instance on a chart (flowlayer.js inst(), catalog eventsView / newsMode)
const FIRST_ONLY = { fvg: 'gap', smt: 'SMT', events: 'calendar', headlines: 'news' };
// the burst detector's markets (bursts.py DEFAULT_ROOTS: the server's HOMEBASE_BURST_ROOTS can change it)
const BOLT_ROOTS = ['NQ', 'ES', 'YM', 'RTY', 'GC'];
const FIVE_MIN = 5 * 60000;
const warn = (text, act) => (act ? { text, tone: 'warn', act } : { text, tone: 'warn' });

function visible(f) {
  const out = [];
  for (let i = Math.max(0, f.i0); i <= Math.min(f.bars.length - 1, f.i1); i++) if (f.bars[i] && !f.bars[i].blank) out.push(f.bars[i]);
  return out;
}

function of(inst, f) {
  if (!inst || !f || !f.bars || !f.bars.length) return null;
  const id = inst.id, p = inst.params || {};
  if (inst.visible === false) return null;
  if (id === 'pine') return pineNote(f.pine && f.pine[inst.uid]);
  const first = FIRST_ONLY[id] && (f.indicators || []).find((x) => x.id === id && x.visible !== false);
  if (first && first.uid !== inst.uid) return warn(`Only the first ${FIRST_ONLY[id]} indicator on a chart draws`);
  const miss = FIELD[id];
  if (miss && !visible(f).some((b) => b[miss[0]] != null)) return warn(`No ${miss[1]} for these bars`);
  if (id === 'footprint') {
    if (!f.readable) return warn('Too small to read: zoom in', 'zoom');
    if (!visible(f).some((b) => b.fp && b.fp.length)) return warn('No trade detail for these bars');
    return p.text === 'trades' && !visible(f).some((b) => b.fpn != null) ? warn('No print counts for these bars') : null;
  }
  if (id === 'heatmap') return heatmapNote(p, f);
  if (id === 'headlines') return p.show !== 'all' && f.root && !BOLT_ROOTS.includes(f.root) ? warn(`No bolts on this market: they exist for ${BOLT_ROOTS.join(', ')}`) : null;
  if (id === 'cstat') {      // flowlayer.js drawStats hides under the same minBarPx (34) px a bar
    const min = p.minBarPx == null || !Number.isFinite(+p.minBarPx) ? 34 : +p.minBarPx;
    return f.spacing > 0 && f.spacing < min ? warn('Zoom in to see the stats') : null;
  }
  if (['orb', 'noise', 'topen'].includes(id) && f.barMs > FIVE_MIN) {
    const key = need('HBCatalog', './catalog.js').serverKey(inst);
    if (!visible(f).some((b) => b.sv && b.sv[key] != null)) return warn('Needs bars of 5 minutes or less (a bar must start within 5 minutes of the time)');
  }
  if (id === 'bigorders' && p.history === false) return null;   // only the live line: no book history is asked, so no ended-order count
  if (BOOK_IDS.has(id) || id === 'imbalance') {
    const bk = f.book || {};
    if (id === 'imbalance') return bk.live ? null : warn('Waits for the live Level 2 book');
    if (!bk.rows && !bk.covered) return warn('Level 2 book is loading, or none was recorded for this time');
    if (!bk.covered) return warn('No Level 2 book was recorded for this time');
    const E = f.E, eps = f.episodes || [];
    const gap = bk.refused && !bk.full ? gapNote(bk.refused) : null;   // older history was refused: that is why it is missing
    if (gap && !E) return gap;
    if (gap && !['absorb', 'pulled', 'iceberg', 'bigorders'].includes(id)) return gap;
    const side = (list) => list.filter((x) => E.sideOk(p.side, x.side)).length;   // the layer's own Side filter
    if (id === 'absorb' && E) return countNote(side(E.absorptions(eps, { multiple: p.multiple, minSeconds: p.minSeconds })), 'Lower "Level at least"', gap);
    if (id === 'pulled' && E) return countNote(side(E.pulls(eps, { multiple: p.multiple, minSeconds: p.minSeconds })), 'Lower "Level at least"', gap);
    if (id === 'iceberg' && E) return countNote(side(E.icebergs(eps, { multiple: p.multiple, minTraded: p.minTraded })), 'Lower "Traded at least"', gap);
    if (id === 'bigorders' && E) return countNote(E.segments(eps, { multiple: p.multiple, minSeconds: p.minSeconds, now: Infinity }).length, 'Lower "Multiple"', gap);
    return null;
  }
  if (id === 'bigprints') {
    let n = 0;
    for (const b of visible(f)) for (const r of b.big || []) if (r[2] >= p.min) n++;
    return countNote(n, `Lower "Minimum size" (now ${p.min})`);
  }
  if (id === 'bigtrades' && f.M) {
    let n = 0;
    for (const b of visible(f)) {
      for (const c of f.M.clusterOrders(f.M.ordersOf(b, 0, 0, p.side || 'all'), p.cluster || 'none', +p.thr || 100)) if (c.size >= p.min && (!p.max || c.size <= p.max)) n++;
    }
    return countNote(n, `Lower "Minimum size" (now ${p.min})`);
  }
  if (id === 'fvg' && f.M && f.M.fvgBoxes) {
    const key = need('HBCatalog', './catalog.js').serverKey(inst);      // the gap timeframe's key too ("fvg:0.25:14@300")
    const n = f.M.fvgBoxes(f.bars, key, f.i1).filter((b) => b.to >= f.i0).length;
    return n > 0 ? info(`${noun(n, 'gap', 'gaps')} in view`) : info('No open gap in view');
  }
  if (id === 'smt') {
    if (f.root && !['NQ', 'ES'].includes(f.root)) return warn('Reads NQ against ES: this market has no partner');
    if (f.time === false) return warn('Needs a time chart (minutes, hours)');
    const key = `smt:${p.window}:${p.reference}`;
    let n = 0;
    for (const b of visible(f)) if (b.sv && b.sv[key] && b.sv[key].dir) n++;
    return n > 0 ? info(`${noun(n, 'divergence', 'divergences')} in view`) : info('None in view');
  }
  if ((id === 'stoprun' || id === 'exhaust') && f.M) {
    const a = Math.max(0, f.i0), z = Math.min(f.bars.length - 1, f.i1);
    const n = id === 'stoprun' ? f.M.stopRuns(f.bars, a, z, p.length, p.minSize).length
      : f.M.exhaustions(f.bars, a, z, p.length, p.multiple, p.wait).length;
    return countNote(n, id === 'stoprun' ? 'Lower "Burst at least"' : 'Lower "Delta at least"');
  }
  return null;
}

/* The heatmap reads the depth history and the live buffer, not the book store: its only note is the zoom limit (past it nothing is asked or drawn). */
function heatmapNote(p, f) {
  if (p.map === false) return null;   // only its trade bubbles
  const L = need('HBLiquidity', './liquidity.js'), v = visible(f);
  if (!L || !v.length) return null;
  const span = v[v.length - 1].ms - v[0].ms + (f.barMs || 0);
  return span > L.MAX_VIEW_MS ? warn(`Zoomed out too far: the heatmap shows up to ${L.MAX_VIEW_MS / 3600000} hours`) : null;
}

/* A Pine script: why it did not run (the first line in the legend, all of it on hover), its warnings, or that it is running. */
function pineNote(s) {
  if (!s) return null;
  const short = (t) => { const one = String(t).split('\n')[0]; return one.length > 70 ? `${one.slice(0, 69)}…` : one; };
  if (s.error) return { text: short(s.error), tone: 'warn', title: String(s.error) };
  if (s.running) return info('Running…');
  const n = s.notes || [];
  if (!n.length) return null;
  return { text: n.length === 1 ? short(n[0]) : `${short(n[0])} (+${n.length - 1} more)`, tone: 'warn', title: n.join('\n') };
}

function countNote(n, hint, gap) {
  if (gap) return n > 0 ? info(`${noun(n, 'mark', 'marks')} in view. ${gap.text}`) : gap;   // the gap, not the setting, is the reason
  return n > 0 ? info(`${noun(n, 'mark', 'marks')} in view`) : warn(`None in view. ${hint}`);
}
/* Older Level 2 history was refused by the service: say so in plain words (a paused window, or just busy). */
function gapNote(r) {
  const d = String(r.detail || '');
  if (/^busy/.test(d)) return info('Loading older Level 2…');
  if (/paused/.test(d)) return warn(`Older Level 2 is ${d}: only the newest minutes show`);
  return warn('Older Level 2 could not load: only the newest minutes show');
}

const api = { of };
if (typeof window !== 'undefined') window.HBStatus = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
