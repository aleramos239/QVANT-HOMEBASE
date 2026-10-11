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
