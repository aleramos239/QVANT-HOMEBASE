/* Homebase Charts — HBStatus: why an indicator shows nothing (or how much it shows), in a few plain words, for the
   legend. The pure half (of) is Node-tested; the page gathers the facts (cell.js statusFacts) and draws the note.
     of(inst, facts) -> null (nothing to say) | { text, tone: 'info' | 'warn', act?: 'zoom' }
   facts: { bars, i0, i1 (the bars in view), readable (the footprint's numbers fit), book: { rows, covered, live },
            episodes (the book's order episodes in view), M (HBFlowMath), E (HBBookEvents' pure half) }. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);

const BOOK_IDS = new Set(['bigorders', 'absorb', 'pulled', 'iceberg', 'heatmap', 'bkimb', 'bkdepth', 'bkmicro', 'bkquote']);
const noun = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const info = (text) => ({ text, tone: 'info' });
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
  if (id === 'footprint') {
    if (!f.readable) return warn('Too small to read: zoom in', 'zoom');
    return visible(f).some((b) => b.fp && b.fp.length) ? null : warn('No trade detail for these bars');
  }
  if (BOOK_IDS.has(id) || id === 'imbalance') {
    const bk = f.book || {};
    if (id === 'imbalance') return bk.live ? null : warn('Waits for the live Level 2 book');
    if (!bk.rows && !bk.covered) return warn('Level 2 book is loading, or none was recorded for this time');
    if (!bk.covered) return warn('No Level 2 book was recorded for this time');
    const E = f.E, eps = f.episodes || [];
    const gap = bk.refused && !bk.full ? gapNote(bk.refused) : null;   // older history was refused: that is why it is missing
    if (gap && !E) return gap;
    if (gap && !['absorb', 'pulled', 'iceberg', 'bigorders'].includes(id)) return gap;
    if (id === 'absorb' && E) return countNote(E.absorptions(eps, { multiple: p.multiple, minSeconds: p.minSeconds }).length, 'Lower "Level at least"', gap);
    if (id === 'pulled' && E) return countNote(E.pulls(eps, { multiple: p.multiple, minSeconds: p.minSeconds }).length, 'Lower "Level at least"', gap);
    if (id === 'iceberg' && E) return countNote(E.icebergs(eps, { multiple: p.multiple, minTraded: p.minTraded }).length, 'Lower "Traded at least"', gap);
    if (id === 'bigorders' && E) return countNote(E.segments(eps, { multiple: p.multiple, minSeconds: p.minSeconds, now: Infinity }).length, 'Lower "Multiple"', gap);
    return null;
  }
  if (id === 'bigprints') {
    let n = 0;
    for (const b of visible(f)) for (const r of b.big || []) if (r[2] >= p.min) n++;
    return countNote(n, `Lower "Minimum size" (now ${p.min})`);
  }
  if (id === 'fvg' && f.M && f.M.fvgBoxes) {
    const key = `fvg:${p.min}:${p.length}`;
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
