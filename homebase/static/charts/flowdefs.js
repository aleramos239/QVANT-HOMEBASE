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
  { id: 'bkimb', group: 'Book (L2)', name: 'Book imbalance (over time)', pane: 'own',
    params: [{ key: 'levels', label: 'Book levels', type: 'choice', def: '10', choices: [['1', 'Top 1'], ['5', 'Top 5'], ['10', 'Top 10']] }],
    key: (p) => `bk:imb${p.levels}`, label: (p) => `Book imbalance ${p.levels}`,
    desc: 'Bid minus ask size over their sum in the top book levels, averaged per bar',
    lines: [line('main', 'Imbalance', BLUE, 1, 'solid', { type: 'hist', tag: false })], refs: [0.3, -0.3] },
  { id: 'bkdepth', group: 'Book (L2)', name: 'Book depth (bid vs ask)', pane: 'own', params: [], digits: 0,
    key: () => 'bk:depth', label: () => 'Book depth',
    desc: 'Total resting size in the top 10 book levels, bid and ask, averaged per bar',
    lines: [line('b10', 'Bid size', UP, 1, 'solid', { col: 'b10' }), line('a10', 'Ask size', DOWN, 1, 'solid', { col: 'a10' })] },
  { id: 'bkmicro', group: 'Book (L2)', name: 'Microprice', params: [],
    key: () => 'bk:micro', label: () => 'Microprice',
    desc: "Top-of-book price weighted by each side's size: it leans to the heavier side",
    lines: [line('main', 'Microprice', VIOLET, 1, 'solid', { tag: false })] },
  { id: 'bkquote', group: 'Book (L2)', name: 'Best bid / best ask', params: [],
    key: () => 'bk:quote', label: () => 'Best bid / ask',
    desc: 'The best bid and best ask prices, averaged per bar: the spread over time',
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
    words: (x, p) => { const lean = (p && p.lean) || 10, push = (p && p.push) || 25;
      return x == null ? '' : x >= push ? 'Buyers pushing' : x >= lean ? 'Buyers lean' : x <= -push ? 'Sellers pushing'
        : x <= -lean ? 'Sellers lean' : 'Even'; },
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
  { id: 'smt', group: 'Ranges & structure', name: 'SMT divergence (NQ vs ES)',
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
  { id: 'absorb', group: 'Book (L2)', name: 'Absorption', desc: 'Heavy volume traded into a resting level that held, marked by the side that held',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 4, max: 50, step: 0.5, def: 4 }, SECONDS,
      SIDE, { ...LABELS, def: false }, MSIZE] },
  { id: 'pulled', group: 'Book (L2)', name: 'Pulled liquidity', desc: 'A big resting order withdrawn as price came toward it',
    params: [{ key: 'multiple', label: 'Level at least (x median)', type: 'num', min: 3, max: 50, step: 0.5, def: 5 }, SECONDS_ENDED,
      { ...SIDE, choices: [['all', 'Both'], ['up', 'Bids pulled'], ['down', 'Offers pulled']] },
      { ...LABELS, def: false }, MSIZE] },
  { id: 'iceberg', group: 'Book (L2)', name: 'Icebergs', desc: 'A price hit again and again that keeps reloading: a hidden order',
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

/* Per-indicator colour rows and extra inputs for the Style / Inputs tabs, merged by catalog.js (OV_COLORS, params).
   colors: [{key, label, color (#RRGGBB, theme-independent only), alpha (10-100)}]; params: ordinary param defs.
   Every colour's default is what the renderer drew before, and every param's `def` is the value that was hard-coded. */
const settings = {
  footprint: {
    colors: [
      {"key": "buy", "label": "Buyers: imbalance numbers, stacked bracket, edge tick", "color": "#089981", "alpha": 100},
      {"key": "sell", "label": "Sellers: imbalance numbers, stacked bracket, edge tick", "color": "#F23645", "alpha": 100},
      {"key": "deltaPos", "label": "Positive delta (row delta mode, delta under the bar, dominant side +)", "color": "#089981", "alpha": 100},
      {"key": "deltaNeg", "label": "Negative delta", "color": "#F23645", "alpha": 100},
      {"key": "poc", "label": "Box round the busiest row", "color": "#F7A600", "alpha": 100},
    ],
    params: [
      {"key": "fontMax", "label": "Largest number size (px)", "type": "int", "min": 8, "max": 16, "step": 1, "def": 11},
      {"key": "fontMin", "label": "Smallest number size (px)", "type": "int", "min": 6, "max": 11, "step": 1, "def": 8},
      {"key": "barFill", "label": "Width of a bar's column (% of the bar spacing)", "type": "int", "min": 40, "max": 100, "step": 1, "def": 86},
      {"key": "minBarPx", "label": "Show numbers when a bar is at least this wide (px)", "type": "int", "min": 30, "max": 200, "step": 1, "def": 56},
      {"key": "minRowPx", "label": "Smallest row height when rows are set by hand (px)", "type": "int", "min": 6, "max": 30, "step": 1, "def": 9},
      {"key": "autoRowPx", "label": "Row height Auto aims for (px)", "type": "int", "min": 6, "max": 40, "step": 1, "def": 11},
      {"key": "pocWidth", "label": "POC box line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "stackWidth", "label": "Stacked-imbalance bracket width", "type": "int", "min": 1, "max": 6, "step": 1, "def": 2},
      {"key": "edgeWidth", "label": "Imbalance edge tick width when Numbers = None (px)", "type": "int", "min": 1, "max": 8, "step": 1, "def": 3},
      {"key": "hideCandles", "label": "Hide the candle bodies while the numbers show", "type": "bool", "def": true},
      {"key": "fontFamily", "label": "Number font", "type": "choice", "choices": [["mono", "Monospace"], ["sans", "Sans-serif"]], "def": "mono"},
    ],
  },
  bigprints: {
    colors: [
      {"key": "buy", "label": "Buyer markers and sweeps", "color": "#089981", "alpha": 100},
      {"key": "sell", "label": "Seller markers and sweeps", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "shape", "label": "Marker shape", "type": "choice", "choices": [["circle", "Circle"], ["square", "Square"], ["arrowUp", "Arrow up"], ["arrowDown", "Arrow down"]], "def": "circle"},
      {"key": "markerMin", "label": "Smallest marker size", "type": "num", "min": 0.5, "max": 3, "step": 0.1, "def": 0.6},
      {"key": "markerMax", "label": "Largest marker size", "type": "num", "min": 0.5, "max": 4, "step": 0.1, "def": 2.2},
      {"key": "fullAt", "label": "Biggest marker at this many times the minimum size", "type": "int", "min": 2, "max": 64, "step": 1, "def": 8},
      {"key": "sweepMin", "label": "Sweep minimum size (0 = same as Minimum size)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "sweepWidth", "label": "Sweep line width", "type": "int", "min": 1, "max": 6, "step": 1, "def": 2},
      {"key": "sweepArrow", "label": "Sweep arrow size", "type": "num", "min": 0.5, "max": 3, "step": 0.25, "def": 1},
      {"key": "sweepDash", "label": "Sweep line", "type": "choice", "choices": [["solid", "Solid"], ["dashed", "Dashed"], ["dotted", "Dotted"]], "def": "solid"},
    ],
  },
  bigtrades: {
    colors: [
      {"key": "buyOutline", "label": "Buyer bubble outline", "color": "#089981", "alpha": 100},
      {"key": "sellOutline", "label": "Seller bubble outline", "color": "#F23645", "alpha": 100},
      {"key": "buyFill", "label": "Buyer bubble fill", "color": "#089981", "alpha": 45},
      {"key": "sellFill", "label": "Seller bubble fill", "color": "#F23645", "alpha": 45},
    ],
    params: [
      {"key": "radiusMin", "label": "Smallest bubble radius (px)", "type": "int", "min": 1, "max": 20, "step": 1, "def": 3},
      {"key": "radiusMax", "label": "Largest bubble radius (px)", "type": "int", "min": 3, "max": 60, "step": 1, "def": 14},
      {"key": "fullSize", "label": "Size drawn as the biggest bubble when Maximum is 0 (0 = auto)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "lineWidth", "label": "Bubble outline width", "type": "int", "min": 0, "max": 4, "step": 1, "def": 1},
      {"key": "labels", "label": "Write the size inside big bubbles", "type": "bool", "def": true},
      {"key": "labelMinR", "label": "Write the size when the bubble radius is at least (px)", "type": "int", "min": 4, "max": 30, "step": 1, "def": 7},
      {"key": "fontSize", "label": "Size number font (px)", "type": "int", "min": 8, "max": 16, "step": 1, "def": 10},
      {"key": "front", "label": "Draw in front of the candles", "type": "bool", "def": false},
    ],
  },
  cstat: {
    colors: [
      {"key": "pos", "label": "Positive delta / Delta % / Max delta", "color": "#089981", "alpha": 100},
      {"key": "neg", "label": "Negative delta / Delta % / Min delta", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "showDelta", "label": "Row: Delta", "type": "bool", "def": true},
      {"key": "showVolume", "label": "Row: Volume", "type": "bool", "def": true},
      {"key": "showTrades", "label": "Row: Trades", "type": "bool", "def": true},
      {"key": "showDeltaPct", "label": "Row: Delta %", "type": "bool", "def": true},
      {"key": "showMaxDelta", "label": "Row: Max delta", "type": "bool", "def": true},
      {"key": "showMinDelta", "label": "Row: Min delta", "type": "bool", "def": true},
      {"key": "showSeconds", "label": "Row: Seconds", "type": "bool", "def": true},
      {"key": "rowH", "label": "Row height (px)", "type": "int", "min": 9, "max": 24, "step": 1, "def": 12},
      {"key": "labelW", "label": "Row-name column width (px)", "type": "int", "min": 30, "max": 120, "step": 1, "def": 58},
      {"key": "minBarPx", "label": "Show when a bar is at least this wide (px)", "type": "int", "min": 10, "max": 120, "step": 1, "def": 34},
      {"key": "fontSize", "label": "Font size (px)", "type": "int", "min": 8, "max": 14, "step": 1, "def": 10},
      {"key": "pctDecimals", "label": "Delta % decimals", "type": "int", "min": 0, "max": 3, "step": 1, "def": 1},
      {"key": "kFrom", "label": "Abbreviate as 12.3k from (absolute value)", "type": "int", "min": 1000, "max": 1000000, "step": 1000, "def": 10000},
      {"key": "place", "label": "Strip position", "type": "choice", "choices": [["bottom", "Bottom of the chart"], ["top", "Top of the chart"]], "def": "bottom"},
    ],
  },
  dturn: {
    colors: [
      {"key": "up", "label": "Up arrow (delta turned up)", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Down arrow (delta turned down)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "size", "label": "Arrow size", "type": "choice", "choices": [["0.7", "Small"], ["1", "Normal"], ["1.5", "Large"]], "def": "1"},
      {"key": "filled", "label": "Fill the arrow", "type": "bool", "def": true},
      {"key": "gap", "label": "Distance from the bar's low/high (px)", "type": "int", "min": 0, "max": 40, "step": 1, "def": 3},
      {"key": "lineWidth", "label": "Outline width (when not filled)", "type": "num", "min": 0.5, "max": 4, "step": 0.5, "def": 1.5},
      {"key": "run", "label": "Same-colour bars before the turn", "type": "int", "min": 1, "max": 5, "step": 1, "def": 2},
    ],
  },
  dstr: {
    colors: [
      {"key": "up", "label": "Up arrow", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Down arrow", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "size", "label": "Arrow size", "type": "choice", "choices": [["0.7", "Small"], ["1", "Normal"], ["1.5", "Large"]], "def": "1"},
      {"key": "filled", "label": "Fill the arrow", "type": "bool", "def": false},
      {"key": "gap", "label": "Distance from the bar's low/high (px)", "type": "int", "min": 0, "max": 60, "step": 1, "def": 17},
      {"key": "lineWidth", "label": "Outline width", "type": "num", "min": 0.5, "max": 4, "step": 0.5, "def": 1.5},
    ],
  },
  mwabs: {
    colors: [
      {"key": "up", "label": "Absorbed sellers (price turned up): line and dot", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Absorbed buyers (price turned down): line and dot", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "lineWidth", "label": "Line width", "type": "num", "min": 0.5, "max": 4, "step": 0.5, "def": 1.5},
      {"key": "tail", "label": "Line starts this far left of the bar (px)", "type": "int", "min": 0, "max": 30, "step": 1, "def": 6},
      {"key": "dot", "label": "Dot on the confirming bar", "type": "bool", "def": true},
      {"key": "dotR", "label": "Dot radius (px)", "type": "int", "min": 1, "max": 8, "step": 1, "def": 3},
      {"key": "dash", "label": "Line", "type": "choice", "choices": [["solid", "Solid"], ["dashed", "Dashed"], ["dotted", "Dotted"]], "def": "solid"},
      {"key": "ratio", "label": "Imbalance ratio (0 = the rule's own)", "type": "num", "min": 0, "max": 20, "step": 0.5, "def": 0},
      {"key": "zero", "label": "Other side traded nothing", "type": "choice", "choices": [["one", "Compare with 1"], ["skip", "No imbalance"]], "def": "one"},
      {"key": "edge", "label": "Bar's top and bottom row", "type": "choice", "choices": [["one", "Compare with 1"], ["skip", "No imbalance"]], "def": "one"},
      {"key": "minvol", "label": "Skip a pair when both sides are under (contracts)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "mindiff", "label": "Imbalance needs this many more contracts", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
    ],
  },
  stoprun: {
    colors: [
      {"key": "up", "label": "Run up through highs", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Run down through lows", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "lineWidth", "label": "Level line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "dash", "label": "Level line", "type": "choice", "choices": [["dashed", "Dashed"], ["solid", "Solid"], ["dotted", "Dotted"]], "def": "dashed"},
      {"key": "levelLine", "label": "Draw the swing level line", "type": "bool", "def": true},
      {"key": "show", "label": "Show", "type": "choice", "choices": [["all", "All"], ["held", "Closed beyond the level"], ["trap", "Pushed back (traps)"]], "def": "all"},
      {"key": "trapMark", "label": "Add a cross to a pushed-back run", "type": "bool", "def": true},
      {"key": "fontSize", "label": "Number font (px)", "type": "int", "min": 8, "max": 16, "step": 1, "def": 11},
      {"key": "arrowGap", "label": "Arrow distance from the level (px)", "type": "int", "min": 0, "max": 20, "step": 1, "def": 4},
      {"key": "sweepMin", "label": "Count a sweep from (contracts)", "type": "int", "min": 1, "max": 1000, "step": 1, "def": 1},
    ],
  },
  exhaust: {
    colors: [
      {"key": "up", "label": "Sellers spent (price turned up)", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Buyers spent (price turned down)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "capWidth", "label": "Cap line width", "type": "int", "min": 1, "max": 6, "step": 1, "def": 2},
      {"key": "capHalf", "label": "Cap extends past the bars by (px)", "type": "int", "min": 0, "max": 20, "step": 1, "def": 6},
      {"key": "arrow", "label": "Arrow", "type": "bool", "def": true},
      {"key": "fontSize", "label": "Label font (px)", "type": "int", "min": 8, "max": 16, "step": 1, "def": 11},
      {"key": "giveback", "label": "Last bar must close back past this share of the push bar (%)", "type": "int", "min": 10, "max": 100, "step": 5, "def": 50},
    ],
  },
  bigorders: {
    colors: [
      {"key": "bid", "label": "Bid orders (support)", "color": "#2962FF", "alpha": 100},
      {"key": "ask", "label": "Ask orders (resistance)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "endedOpacity", "label": "Ended orders opacity (%)", "type": "int", "min": 10, "max": 100, "step": 5, "def": 60},
      {"key": "caps", "label": "Mark how an ended order ended (square = traded, ring = pulled)", "type": "bool", "def": true},
      {"key": "liveLines", "label": "Show the standing (live) lines", "type": "bool", "def": true},
      {"key": "liveWidth", "label": "Live line thickness", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "liveDash", "label": "Live line style", "type": "choice", "choices": [["0", "Solid"], ["1", "Dotted"], ["2", "Dashed"]], "def": "0"},
      {"key": "labels", "label": "Size and price label on the live lines", "type": "bool", "def": true},
      {"key": "fade", "label": "Live line fades out over (seconds)", "type": "int", "min": 1, "max": 60, "step": 1, "def": 5},
      {"key": "maxLines", "label": "Most live lines per side", "type": "int", "min": 1, "max": 30, "step": 1, "def": 8},
      {"key": "minSize", "label": "Hide orders smaller than (contracts, 0 = no limit)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
    ],
  },
  imbalance: {
    colors: [
      {"key": "bid", "label": "Bid-heavy (bar and number)", "color": "#2962FF", "alpha": 100},
      {"key": "ask", "label": "Ask-heavy (bar and number)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "levels", "label": "Book levels", "type": "choice", "choices": [["1", "Top 1"], ["5", "Top 5"], ["10", "Top 10"]], "def": "10"},
      {"key": "bar", "label": "Show the bar", "type": "bool", "def": true},
      {"key": "number", "label": "Show the percentage", "type": "bool", "def": true},
    ],
  },
  absorb: {
    colors: [
      {"key": "up", "label": "Bid absorbed sellers (ring, A and number)", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Offer absorbed buyers (ring, A and number)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "minTraded", "label": "Traded into it at least (contracts, 0 = any)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "labelSize", "label": "Number size (px)", "type": "int", "min": 8, "max": 20, "step": 1, "def": 10},
    ],
  },
  pulled: {
    colors: [
      {"key": "bid", "label": "Bid pulled (cross and number)", "color": "#2962FF", "alpha": 100},
      {"key": "ask", "label": "Offer pulled (cross and number)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "minSize", "label": "Pulled size at least (contracts, 0 = any)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "labelSize", "label": "Number size (px)", "type": "int", "min": 8, "max": 20, "step": 1, "def": 10},
    ],
  },
  iceberg: {
    colors: [
      {"key": "up", "label": "Hidden buyer (line, diamond, text)", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Hidden seller (line, diamond, text)", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "reloads", "label": "Reloaded at least (times)", "type": "int", "min": 2, "max": 50, "step": 1, "def": 2},
      {"key": "endedOpacity", "label": "Ended iceberg opacity (%)", "type": "int", "min": 10, "max": 100, "step": 5, "def": 70},
      {"key": "width", "label": "Line thickness (px, before Marker size)", "type": "int", "min": 1, "max": 8, "step": 1, "def": 3},
      {"key": "labelSize", "label": "Text size (px)", "type": "int", "min": 8, "max": 20, "step": 1, "def": 10},
    ],
  },
  bkimb: {
    colors: [
      {"key": "up", "label": "Bid-heavy bars", "color": "#089981", "alpha": 50},
      {"key": "down", "label": "Ask-heavy bars", "color": "#F23645", "alpha": 50},
    ],
    params: [
      {"key": "digits", "label": "Decimals", "type": "int", "min": 0, "max": 6, "step": 1, "def": 2},
    ],
  },
  tspeed: {
    params: [
      {"key": "burstMult", "label": "Burst = this many times the recent median", "type": "num", "min": 1.5, "max": 10, "step": 0.5, "def": 3},
      {"key": "digits", "label": "Decimals", "type": "int", "min": 0, "max": 4, "step": 1, "def": 2},
    ],
  },
  pressure: {
    colors: [
      {"key": "even", "label": "Even (under the lean level)", "color": "#787B86", "alpha": 45},
      {"key": "leanUp", "label": "Buyers lean", "color": "#089981", "alpha": 50},
      {"key": "leanDown", "label": "Sellers lean", "color": "#F23645", "alpha": 50},
      {"key": "pushUp", "label": "Buyers pushing", "color": "#089981", "alpha": 100},
      {"key": "pushDown", "label": "Sellers pushing", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "lean", "label": "A lean from (|value|)", "type": "int", "min": 1, "max": 99, "step": 1, "def": 10},
      {"key": "push", "label": "A clear push from (|value|)", "type": "int", "min": 2, "max": 100, "step": 1, "def": 25},
      {"key": "digits", "label": "Decimals", "type": "int", "min": 0, "max": 4, "step": 1, "def": 2},
    ],
  },
  ddiv: {
    colors: [
      {"key": "bear", "label": "Bearish divergence (arrow above bar)", "color": "#F23645", "alpha": 100},
      {"key": "bull", "label": "Bullish divergence (arrow below bar)", "color": "#089981", "alpha": 100},
    ],
    params: [
      {"key": "size", "label": "Marker size", "type": "choice", "choices": [["0.7", "Small"], ["1", "Normal"], ["1.5", "Large"]], "def": "1"},
      {"key": "labels", "label": "Write the delta sign next to each marker", "type": "bool", "def": true},
      {"key": "side", "label": "Side", "type": "choice", "choices": [["all", "Both"], ["up", "Bullish only"], ["down", "Bearish only"]], "def": "all"},
    ],
  },
  levels: {
    params: [
      {"key": "showPdh", "label": "Prior day high", "type": "bool", "def": true},
      {"key": "showPdl", "label": "Prior day low", "type": "bool", "def": true},
      {"key": "showPdc", "label": "Prior day close", "type": "bool", "def": true},
      {"key": "showOnh", "label": "Overnight high", "type": "bool", "def": true},
      {"key": "showOnl", "label": "Overnight low", "type": "bool", "def": true},
      {"key": "showOpen", "label": "RTH open", "type": "bool", "def": true},
      {"key": "labels", "label": "Show labels", "type": "bool", "def": true},
      {"key": "width", "label": "Line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "dash", "label": "Line style", "type": "choice", "choices": [["solid", "Solid"], ["dotted", "Dotted"], ["dashed", "Dashed"]], "def": "dashed"},
    ],
  },
  npoc: {
    colors: [
      {"key": "line", "label": "Naked POC line", "color": "#F7A600", "alpha": 100},
    ],
    params: [
      {"key": "nakedOnly", "label": "Only untouched POCs", "type": "bool", "def": false},
      {"key": "lookback", "label": "Look back (bars)", "type": "int", "min": 50, "max": 2000, "step": 50, "def": 500},
      {"key": "width", "label": "Line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "dash", "label": "Line style", "type": "choice", "choices": [["solid", "Solid"], ["dotted", "Dotted"], ["dashed", "Dashed"]], "def": "dashed"},
    ],
  },
  tpo: {
    colors: [
      {"key": "single", "label": "Single prints", "color": "#F7A600", "alpha": 100},
      {"key": "poc", "label": "Point of control box", "color": "#F7A600", "alpha": 100},
    ],
    params: [
      {"key": "blocksOpacity", "label": "Blocks opacity %", "type": "int", "min": 10, "max": 100, "step": 5, "def": 45},
      {"key": "fontSize", "label": "Letter size", "type": "int", "min": 8, "max": 14, "step": 1, "def": 10},
      {"key": "showPoc", "label": "Mark point of control", "type": "bool", "def": true},
      {"key": "showVa", "label": "Shade value area", "type": "bool", "def": true},
      {"key": "markSingles", "label": "Highlight single prints", "type": "bool", "def": true},
    ],
  },
  pzone: {
    colors: [
      {"key": "up", "label": "Buyers' zone (support)", "color": "#22D3EE", "alpha": 100},
      {"key": "down", "label": "Sellers' zone (resistance)", "color": "#A855F7", "alpha": 100},
    ],
    params: [
      {"key": "opacity", "label": "Fill opacity (%)", "type": "int", "min": 0, "max": 100, "step": 5, "def": 20},
      {"key": "untouchedOnly", "label": "Only untouched zones", "type": "bool", "def": false},
    ],
  },
  profile: {
    colors: [
      {"key": "poc", "label": "Point of control", "color": "#F7A600", "alpha": 100},
      {"key": "priorPoc", "label": "Prior POC line", "color": "#F7A600", "alpha": 100},
    ],
    params: [
      {"key": "ghostOpacity", "label": "Prior profile opacity %", "type": "int", "min": 10, "max": 100, "step": 5, "def": 45},
      {"key": "lineWidth", "label": "Prior line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "labels", "label": "Show prior line labels", "type": "bool", "def": true},
      {"key": "fontSize", "label": "Label size", "type": "int", "min": 8, "max": 14, "step": 1, "def": 10},
      {"key": "highlightPoc", "label": "Highlight POC row", "type": "bool", "def": true},
    ],
  },
  sess: {
    params: [
      {"key": "lineWidth", "label": "Line width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "hiDash", "label": "High line style", "type": "choice", "choices": [["solid", "Solid"], ["dotted", "Dotted"], ["dashed", "Dashed"]], "def": "solid"},
      {"key": "loDash", "label": "Low line style", "type": "choice", "choices": [["solid", "Solid"], ["dotted", "Dotted"], ["dashed", "Dashed"]], "def": "dashed"},
      {"key": "showHigh", "label": "Show high lines", "type": "bool", "def": true},
      {"key": "showLow", "label": "Show low lines", "type": "bool", "def": true},
    ],
  },
  fvg: {
    params: [
      {"key": "border", "label": "Show border", "type": "bool", "def": true},
      {"key": "borderWidth", "label": "Border width", "type": "int", "min": 1, "max": 4, "step": 1, "def": 1},
      {"key": "extend", "label": "Extend open gaps to the right", "type": "bool", "def": false},
    ],
  },
  smt: {
    colors: [
      {"key": "up", "label": "Bullish divergence", "color": "#089981", "alpha": 100},
      {"key": "down", "label": "Bearish divergence", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "lineWidth", "label": "Line width", "type": "num", "min": 0.5, "max": 4, "step": 0.5, "def": 1.5},
      {"key": "showLine", "label": "Show divergence line", "type": "bool", "def": true},
      {"key": "dotRadius", "label": "End dot size", "type": "num", "min": 0, "max": 6, "step": 0.5, "def": 2.5},
      {"key": "size", "label": "Arrow size", "type": "choice", "choices": [["0.7", "Small"], ["1", "Normal"], ["1.5", "Large"]], "def": "1"},
      {"key": "fontSize", "label": "Label size", "type": "int", "min": 8, "max": 16, "step": 1, "def": 11},
    ],
  },
  events: {
    colors: [
      {"key": "high", "label": "High impact", "color": "#F23645", "alpha": 100},
      {"key": "medium", "label": "Medium impact", "color": "#FF9800", "alpha": 100},
      {"key": "low", "label": "Low impact", "color": "#F7C600", "alpha": 100},
      {"key": "holiday", "label": "Holiday / non-economic", "color": "#9598A1", "alpha": 100},
      {"key": "outline", "label": "Flag outline", "color": "#FFFFFF", "alpha": 100},
    ],
    params: [
      {"key": "flagSize", "label": "Flag size", "type": "int", "min": 6, "max": 20, "step": 1, "def": 10},
      {"key": "lineLow", "label": "Lines for low impact", "type": "bool", "def": false},
      {"key": "showFlags", "label": "Show flags", "type": "bool", "def": true},
    ],
  },
  headlines: {
    colors: [
      {"key": "headline", "label": "Headline dot", "color": "#787B86", "alpha": 100},
      {"key": "trump", "label": "Trump / Truth Social", "color": "#7E57C2", "alpha": 100},
      {"key": "breaking", "label": "Breaking flash", "color": "#F7A600", "alpha": 100},
      {"key": "burstUp", "label": "Burst up", "color": "#089981", "alpha": 100},
      {"key": "burstDown", "label": "Burst down", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "dotSize", "label": "Dot size", "type": "num", "min": 0.2, "max": 1.5, "step": 0.05, "def": 0.35},
      {"key": "boltSize", "label": "Burst marker size", "type": "num", "min": 0.3, "max": 2, "step": 0.1, "def": 0.6},
      {"key": "boltText", "label": "Show lightning symbol", "type": "bool", "def": true},
      {"key": "trumpHighlight", "label": "Colour Trump posts", "type": "bool", "def": true},
      {"key": "flash", "label": "Flash new headlines", "type": "bool", "def": true},
      {"key": "maxDots", "label": "Max headline dots", "type": "int", "min": 50, "max": 1000, "step": 50, "def": 300},
    ],
  },
  volume: {
    params: [
      {"key": "heightPct", "label": "Height (% of pane)", "type": "int", "min": 5, "max": 60, "step": 5, "def": 20},
      {"key": "colorBy", "label": "Colour bars by", "type": "choice", "choices": [["delta", "Delta"], ["candle", "Candle colour"]], "def": "delta"},
    ],
  },
  heatmap: {
    colors: [
      {"key": "buyFill", "label": "Buyer bubble fill", "color": "#089981", "alpha": 45},
      {"key": "sellFill", "label": "Seller bubble fill", "color": "#F23645", "alpha": 45},
      {"key": "buyOutline", "label": "Buyer bubble outline", "color": "#089981", "alpha": 100},
      {"key": "sellOutline", "label": "Seller bubble outline", "color": "#F23645", "alpha": 100},
    ],
    params: [
      {"key": "bubbleRadiusMin", "label": "Smallest bubble radius (px)", "type": "int", "min": 1, "max": 20, "step": 1, "def": 3},
      {"key": "bubbleRadiusMax", "label": "Largest bubble radius (px)", "type": "int", "min": 3, "max": 60, "step": 1, "def": 14},
      {"key": "bubbleFullSize", "label": "Size drawn as the biggest bubble when 'up to' is 0 (0 = auto)", "type": "int", "min": 0, "max": 100000, "step": 1, "def": 0},
      {"key": "bubbleLineWidth", "label": "Bubble outline width", "type": "int", "min": 0, "max": 4, "step": 1, "def": 1},
      {"key": "bubbleLabels", "label": "Write the size inside big bubbles", "type": "bool", "def": false},
      {"key": "bubbleFront", "label": "Draw in front of the candles", "type": "bool", "def": false},
      {"key": "opacity", "label": "Whole map opacity (%)", "type": "int", "min": 10, "max": 100, "step": 5, "def": 100},
      {"key": "fullAt", "label": "Strongest colour at (contracts, 0 = the biggest on screen)", "type": "int", "min": 0, "max": 100000, "step": 10, "def": 0},
      {"key": "cutoff", "label": "Hide cells weaker than (% of the colour scale)", "type": "int", "min": 0, "max": 95, "step": 1, "def": 0},
      {"key": "columnPx", "label": "Column width (pixels)", "type": "int", "min": 1, "max": 8, "step": 1, "def": 2},
    ],
  },
};

const api = { ta, catalog, settings, bookValue };
if (typeof window !== 'undefined') window.HBFlowDefs = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
