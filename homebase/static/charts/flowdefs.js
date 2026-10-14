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
/* what every marker indicator can show or hide, and how big it draws */
const SIDE = { key: 'side', label: 'Side', type: 'choice', def: 'all',
  choices: [['all', 'Both'], ['up', 'Support (bids)'], ['down', 'Resistance (offers)']] };
const LABELS = { key: 'labels', label: 'Write the numbers next to each marker', type: 'bool', def: true };
const MSIZE = { key: 'size', label: 'Marker size', type: 'choice', def: '1', choices: [['0.7', 'Small'], ['1', 'Normal'], ['1.5', 'Large']] };
const SECONDS = { key: 'minSeconds', label: 'Stood at least (seconds)', type: 'int', min: 1, max: 600, def: 5 };
/* bookflow.py emits no level that ended before 3 s (min_episode_ms) and opens one only at 3x the median (OPEN_RATIO):
   a pulled level's setting below 3 changes nothing, so its lower bound is the floor. A saved value below clamps. */
const SECONDS_ENDED = { ...SECONDS, min: 3 };

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
  { id: 'bkquote', group: 'Order flow', name: 'Best bid / best ask', params: [],
    key: () => 'bk:quote', label: () => 'Best bid / ask',
    desc: 'The best bid and best ask price, averaged per bar: the spread over time',
    lines: [line('bid', 'Best bid', UP, 1, 'solid', { col: 'bid', tag: false }),
      line('ask', 'Best ask', DOWN, 1, 'solid', { col: 'ask', tag: false })] },
  { id: 'tspeed', group: 'Order flow', name: 'Tape speed', pane: 'own',
    params: [{ key: 'length', label: 'Bars for the burst line', type: 'int', min: 20, max: 2000, def: 200 }],
    key: (p) => `tspeed:${p.length}`, label: (p) => `Tape speed ${p.length}`,
    desc: 'Prints per second in each bar; above 3x the recent median is a burst',
    lines: [line('rate', 'Prints / s', GREY, 1, 'solid', { type: 'hist', tag: false, fixed: true }),
      line('hot', 'Burst', ORANGE, 1, 'solid', { type: 'hist', tag: false, fixed: true }),
      line('burst', 'Burst line', ORANGE, 1, 'dashed', { tag: false })] },
  { id: 'pressure', group: 'Order flow', name: 'Buy / sell pressure', pane: 'own',
    params: [{ key: 'length', label: 'Bars weighed together (newest counts most)', type: 'int', min: 1, max: 50, def: 5 }],
    key: (p) => `press:${p.length}`, label: (p) => `Buy/sell pressure ${p.length}`,
    desc: 'Which side pushes harder: volume, big prints, sweeps, orders; newest bars count most',
    /* `off`: a part line a NEW chart starts with hidden (the Style tab turns it on); the histogram is the blend of them */
    /* `bands`: |value| under the first is grey (even), under the second pale (a lean), over it solid (a clear push);
       `words`: what the legend says in front of the number */
    words: (x) => (x == null ? '' : x >= 25 ? 'Buyers pushing' : x >= 10 ? 'Buyers lean' : x <= -25 ? 'Sellers pushing'
      : x <= -10 ? 'Sellers lean' : 'Even'),
    lines: [line('p', 'Pressure', BLUE, 1, 'solid', { type: 'hist', tag: false, bands: [10, 25] }),
      line('tot', 'Session total', ORANGE, 2, 'solid', { tag: false }),
      line('vol', 'Volume', GREY, 1, 'dotted', { tag: false, off: true }),
      line('ord', 'Orders', '#00BCD4', 1, 'dotted', { tag: false, off: true }),
      line('big', 'Big prints', VIOLET, 1, 'dotted', { tag: false, off: true }),
      line('swp', 'Sweeps', UP, 1, 'dotted', { tag: false, off: true })], refs: [25, 10, -10, -25] },
  { id: 'ddiv', group: 'Order flow', name: 'Delta divergence', params: [{ key: 'length', label: 'Bars each side', type: 'int', min: 1, max: 50, def: 5 }],
    key: (p) => `ddiv:${p.length}`, label: (p) => `Delta divergence ${p.length}`,
    desc: 'Swing high on a lower cumulative delta, or swing low on a higher one',
    lines: [],
    marks: (v, P) => (v && v.dir
      ? { position: v.dir < 0 ? 'aboveBar' : 'belowBar', color: v.dir < 0 ? (P.down || DOWN) : (P.up || UP),
        shape: v.dir < 0 ? 'arrowDown' : 'arrowUp', text: 'Δ', size: 1, ago: v.ago }
      : null) },
  { id: 'smt', group: 'Structure', name: 'SMT divergence (NQ vs ES)',
    params: [{ key: 'window', label: 'Bars in the window', type: 'int', min: 1, max: 50, def: 6 },
      { key: 'reference', label: 'Bars it is compared with', type: 'int', min: 2, max: 500, def: 36 },
      { key: 'arrow', label: 'Show the arrow', type: 'bool', def: true },
      { key: 'labels', label: 'Write the words (SMT, and which market took the extreme)', type: 'bool', def: true }],
    key: (p) => `smt:${p.window}:${p.reference}`, label: (p) => `SMT ${p.window}/${p.reference}`,
    desc: 'NQ against ES, live: one makes a new high or low and the other does not',
    lines: [],
    marks: (v, P, p) => (v && v.dir && !(p && p.arrow === false)
      ? { position: v.dir < 0 ? 'aboveBar' : 'belowBar', color: v.dir < 0 ? (P.down || DOWN) : (P.up || UP),
        shape: v.dir < 0 ? 'arrowDown' : 'arrowUp', text: p && p.labels === false ? '' : 'SMT', size: 1, ago: v.ago }
      : null) },
];

const catalog = [
  { id: 'absorb', group: 'Order flow', name: 'Absorption', desc: 'Heavy volume traded into a resting level that held, marked by the side that held',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 4, max: 50, step: 0.5, def: 4 }, SECONDS,
      SIDE, { ...LABELS, def: false }, MSIZE] },
  { id: 'pulled', group: 'Order flow', name: 'Pulled liquidity', desc: 'A big resting order withdrawn as price came toward it',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 3, max: 50, step: 0.5, def: 5 }, SECONDS_ENDED,
      { ...SIDE, choices: [['all', 'Both'], ['up', 'Bids pulled'], ['down', 'Offers pulled']] },
      { ...LABELS, def: false }, MSIZE] },
  { id: 'iceberg', group: 'Order flow', name: 'Icebergs', desc: 'A price hit again and again that keeps reloading: a hidden order',
    params: [{ key: 'multiple', label: 'Traded at least (x the size it showed)', type: 'num', min: 3, max: 50, step: 0.5, def: 3 },
      { key: 'minTraded', label: 'And at least (contracts)', type: 'int', min: 1, max: 5000, def: 30 },
      { ...SIDE, choices: [['all', 'Both'], ['up', 'Bids (hidden buyer)'], ['down', 'Offers (hidden seller)']] }, LABELS, MSIZE] },
  { id: 'stoprun', group: 'Order flow', name: 'Stop runs', desc: 'A burst of aggressive trades through a recent swing high or low, where stops sit',
    params: [{ key: 'length', label: 'Swing = highest / lowest of the last (bars)', type: 'int', min: 3, max: 200, def: 50 },
      { key: 'minSize', label: 'Burst at least (contracts)', type: 'int', min: 1, max: 10000, def: 100 },
      { key: 'side', label: 'Direction', type: 'choice', def: 'all', choices: [['all', 'Both'], ['up', 'Up through highs'], ['down', 'Down through lows']] },
      LABELS, MSIZE] },
  { id: 'exhaust', group: 'Order flow', name: 'Exhaustion', desc: 'A big one-sided push to a new extreme that goes nowhere, then price gives it back',
    params: [{ key: 'length', label: 'Compared with the last (bars)', type: 'int', min: 3, max: 200, def: 20 },
      { key: 'multiple', label: 'Delta at least (x the average)', type: 'num', min: 1.5, max: 20, step: 0.5, def: 4 },
      { key: 'wait', label: 'No progress for (bars)', type: 'int', min: 1, max: 10, def: 3 },
      { key: 'side', label: 'Side', type: 'choice', def: 'all', choices: [['all', 'Both'], ['up', 'Buyers spent'], ['down', 'Sellers spent']] },
      { ...LABELS, label: 'Write "Ex" next to each mark' }, MSIZE] },
];

/* The value a "bk:" series shows for one bar: `mean(col)` = the mean of that book column over the bar's seconds (or
   null). A key with several lines gets an object by line part (the depth pane's bid / ask), the others a number. */
const BOOK_COLS = { 'bk:depth': ['b10', 'a10'], 'bk:quote': ['bid', 'ask'] };
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
