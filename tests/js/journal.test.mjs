import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const J = require('../../homebase/static/charts/journal.js');
const rd = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');

/* A small document: elements with children, text, dataset, handlers -- enough to walk what journal.js builds. */
class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.className = ''; this.dataset = {}; this._text = ''; this.value = ''; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this._text = String(v); this.children = []; }
  appendChild(n) { this.children.push(n); return n; }
  append(...ns) { ns.forEach((n) => this.appendChild(n)); }
  replaceChildren(...ns) { this.children = []; this.append(...ns); }
  all(tag) { return this.children.flatMap((c) => [...(c.tagName === tag.toUpperCase() ? [c] : []), ...c.all(tag)]); }
}
const doc = { createElement: (t) => new El(t) };
const labelOf = (id) => ({ a1: 'Sim 1' }[id] || id);
const ms = (iso) => Date.parse(iso);

const trip = (o) => ({ id: 'a1|NQZ6|1', account: 'a1', symbol: 'NQZ6', owner: null, side: 'Buy', qty: 2, entry: 100, entry_ms: ms('2026-10-27T14:00:00Z'),
  exit: 103, exit_ms: ms('2026-10-27T14:05:00Z'), pnl: 120, stop: 98, r: 1.5, open: false, left: 0, source: 'fills', note: '', tags: [], ...o });

test('deskDay: the Desk day turns over at 18:00 ET', () => {
  assert.equal(J.deskDay(ms('2026-10-27T21:59:00Z')), '2026-10-27');   // 17:59 EDT
  assert.equal(J.deskDay(ms('2026-10-27T22:00:00Z')), '2026-10-28');   // 18:00 EDT
  assert.equal(J.deskDay(ms('2026-10-28T03:00:00Z')), '2026-10-28');   // 23:00 EDT
});

test('tripRow: side, dollars, R and an open trip in plain words', () => {
  const r = J.tripRow(trip({ pnl: -50, r: -0.5 }), labelOf);
  assert.deepEqual([r.who, r.side, r.qty, r.entry, r.exit, r.pnl, r.pnlTone, r.r, r.rTone], ['Sim 1', 'Long', 2, '100.00', '103.00', '−$50.00', 'down', '−0.50R', 'down']);
  const o = J.tripRow(trip({ open: true, exit: null, pnl: null, r: null, side: 'Sell', symbol: '', owner: 'bot1' }), labelOf);
  assert.deepEqual([o.exit, o.pnl, o.r, o.side, o.symbol], ['open', '—', '—', 'Short', 'bot1']);
});

test('csv: header, one line per trip, quotes and commas escaped, a note can never start a formula', () => {
  const out = J.csv('2026-10-27', [trip({ note: 'said "wait", went anyway', tags: ['fomo', 'A setup'] }), trip({ note: '=HYPERLINK("x")', open: true, exit: null, pnl: null, r: null })], labelOf);
  const lines = out.split('\r\n');
  assert.equal(lines[0], 'Date,Time (ET),Account,Symbol,Owner,Side,Qty,Entry,Exit,Gross $,R,Tags,Note');
  assert.match(lines[1], /^2026-10-27,[^,]+,Sim 1,NQZ6,,Long,2,100,103,120,1\.5,fomo \| A setup,"said ""wait"", went anyway"$/);
  assert.match(lines[2], /,Long,2,100,,,,,"'=HYPERLINK\(""x""\)"$/);
  assert.equal(lines[3], '');
  assert.equal(J.csv('2026-10-27', [], labelOf).split('\r\n').length, 3 - 1);   // header + the trailing break
});

test('tags: the day\'s tags once each, and a filter that keeps only that tag', () => {
  const ts = [trip({ id: 'x', tags: ['b', 'a'] }), trip({ id: 'y', tags: ['a'] }), trip({ id: 'z' })];
  assert.deepEqual(J.allTags(ts), ['a', 'b']);
  assert.deepEqual(J.withTag(ts, 'b').map((t) => t.id), ['x']);
  assert.equal(J.withTag(ts, '').length, 3);
  assert.deepEqual(J.splitTags(' a, b ,, a'), ['a', 'b', 'a']);
});

test('day: a table with one row per trip, a total, and the note and tags editable', () => {
  const body = new El('div'), saved = [];
  const h = { labelOf, onSave: (t, note, tags) => saved.push([t.id, note, tags]) };
  const ts = [trip({ id: 't1', note: 'late', tags: ['fomo'] }), trip({ id: 't2', pnl: -20, r: null, entry_ms: ms('2026-10-27T15:00:00Z') })];
  J.day(doc, body, { date: '2026-10-27', trips: ts, tag: '' }, h);
  const rows = body.all('tbody')[0].children;
  assert.equal(rows.length, 2);
  assert.equal(rows[0].dataset.key, 't1');
  assert.equal(body.all('tfoot')[0].textContent, '2 trips$100.00');
  const [tagIn, noteIn] = rows[0].all('input');
  assert.deepEqual([tagIn.value, noteIn.value], ['fomo', 'late']);
  tagIn.value = 'fomo, A setup'; noteIn.value = 'waited'; noteIn.onchange();
  assert.deepEqual(saved, [['t1', 'waited', ['fomo', 'A setup']]]);
});

test('day: loading, an error, an empty day and an empty tag filter each say so', () => {
  const body = new El('div'), h = { labelOf };
  const text = (v) => { J.day(doc, body, v, h); return body.textContent; };
  assert.equal(text({ date: '2026-10-27', trips: null }), 'Loading…');
  assert.match(text({ date: '2026-10-27', trips: null, error: 'Could not read the journal' }), /Could not read/);
  assert.equal(text({ date: '2026-10-27', trips: [] }), 'No trades on 2026-10-27');
  assert.equal(text({ date: '2026-10-27', trips: [trip()], tag: 'nope' }), 'No trips with that tag');
});

test('bar: the day picker always; the tag filter and CSV only for a picked day (CSV off with nothing to export)', () => {
  const h = { today: '2026-10-27', onDate() {}, onTag() {}, onCsv() {} };
  const live = J.bar(doc, { date: '', trips: null }, h);
  assert.equal(live.all('input').length, 1);
  assert.equal(live.all('button').length, 0);
  assert.equal(live.all('input')[0].max, '2026-10-27');
  const empty = J.bar(doc, { date: '2026-10-26', trips: [] }, h);
  assert.equal(empty.all('button')[0].disabled, true);
  const full = J.bar(doc, { date: '2026-10-26', trips: [trip({ tags: ['a'] })], tag: '' }, h);
  assert.equal(full.all('button')[0].disabled, false);
  assert.deepEqual(full.all('option').map((o) => o.value), ['', 'a']);
});

test('the Charts page loads journal.js before panel.js; the Lab page does not load it; the Fills tab keeps its live path', () => {
  const charts = rd('charts.html');
  assert.ok(charts.indexOf('charts/journal.js') > 0 && charts.indexOf('charts/journal.js') < charts.indexOf('charts/panel.js'));
  assert.doesNotMatch(rd('backtest.html'), /journal\.js/);
  const panel = rd('charts/panel.js');
  assert.match(panel, /No fills today/);
  assert.match(panel, /if \(!J\) \{ renderLiveFills\(target\); return; \}/);
  assert.doesNotMatch(rd('charts/journal.js'), /\/api\/desk\//, 'nothing here can reach the order routes');
});
