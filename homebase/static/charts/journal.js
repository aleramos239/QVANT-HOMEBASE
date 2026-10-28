/* Homebase Charts — the journal half of the Fills tab: a Desk day's round trips (GET /api/journal/day), a note and tags on
   each (PUT /api/journal/note), and a CSV of what is on screen. The route reads the desk's journal and the chart service's own
   fill log; nothing here can place, change or cancel an order. The pure parts (rows, CSV) have no DOM and are Node-tested; render()
   takes the document, so a test can hand it a small shim. panel.js owns the tab; this file owns what is inside it. */
(function () {
'use strict';
const ET = typeof Intl !== 'undefined' ? new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour12: false,
  hour: '2-digit', minute: '2-digit', second: '2-digit' }) : null;
const ETD = typeof Intl !== 'undefined' ? new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric',
  month: '2-digit', day: '2-digit', hour: '2-digit', hour12: false }) : null;

function etTime(ms) {
  if (!Number.isFinite(ms)) return '—';
  const t = ET.format(new Date(ms));
  return typeof HBClock !== 'undefined' ? HBClock.text(t) : t;   // the app's one clock format
}
/* The Desk day (it starts at 18:00 ET, like the engine's) of an instant, as YYYY-MM-DD. */
function deskDay(ms) {
  const p = Object.fromEntries(ETD.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  const d = new Date(Date.UTC(+p.year, +p.month - 1, +p.day + (+p.hour % 24 >= 18 ? 1 : 0)));
  return d.toISOString().slice(0, 10);
}
const px = (v) => (v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }));
const usd = (v) => (v == null || !Number.isFinite(v) ? '—' : (v < 0 ? '−$' : '$') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const rText = (r) => (r == null || !Number.isFinite(r) ? '—' : (r < 0 ? '−' : '') + Math.abs(r).toFixed(2) + 'R');
const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'down');

/* One trip as the table shows it. labelOf maps an account id to its name. */
function tripRow(t, labelOf) {
  return { key: t.id, time: etTime(t.entry_ms), who: labelOf(t.account), symbol: t.symbol || t.owner || '', side: t.side === 'Buy' ? 'Long' : 'Short',
    qty: t.qty, entry: px(t.entry), exit: t.open ? 'open' : px(t.exit), pnl: usd(t.pnl), pnlTone: tone(t.pnl), r: rText(t.r), rTone: tone(t.r),
    tags: (t.tags || []).join(', '), note: t.note || '', id: t.id };
}

/* A cell that starts with = + - @ is a formula to a spreadsheet: a note must not become one. */
function cell(v) {
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const CSV_HEAD = ['Date', 'Time (ET)', 'Account', 'Symbol', 'Owner', 'Side', 'Qty', 'Entry', 'Exit', 'Gross $', 'R', 'Tags', 'Note'];
function csv(date, trips, labelOf) {
  const rows = trips.map((t) => [date, etTime(t.entry_ms), labelOf(t.account), t.symbol || '', t.owner || '', t.side === 'Buy' ? 'Long' : 'Short',
    t.qty, t.entry, t.open ? '' : t.exit, t.pnl == null ? '' : t.pnl, t.r == null ? '' : t.r, (t.tags || []).join(' | '), t.note || '']);
  return [CSV_HEAD, ...rows].map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
}

/* The trips that carry `tag` ('' = all). */
const withTag = (trips, tag) => (tag ? trips.filter((t) => (t.tags || []).includes(tag)) : trips);
const allTags = (trips) => [...new Set(trips.flatMap((t) => t.tags || []))].sort();

/* ---- the page's side ---- */
async function load(date) {
  const r = await fetch(`/api/journal/day?date=${encodeURIComponent(date)}`);
  if (!r.ok) throw new Error(`the journal answered ${r.status}`);
  const d = await r.json();
  if (!d || !Array.isArray(d.trips)) throw new Error('the journal answered something unreadable');
  return d.trips;
}
async function saveNote(id, note, tags) {
  const r = await fetch('/api/journal/note', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, note, tags }) });
  if (!r.ok) throw new Error(`the note was not saved (${r.status})`);
}
const splitTags = (s) => String(s || '').split(',').map((x) => x.trim()).filter(Boolean);

/* ---- the DOM: all of it through `doc` ---- */
function mk(doc, tag, cls, text) {
  const e = doc.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function td(doc, tr, text, cls) { const c = mk(doc, 'td', cls, text == null ? '' : String(text)); tr.appendChild(c); return c; }

/* The bar above the tab: the day picker (empty = today's live fills), the tag filter and the CSV button. */
function bar(doc, v, h) {
  const b = mk(doc, 'div', 'bp-fq-bar bp-jbar'), lab = mk(doc, 'span', null, 'Day');
  const inp = mk(doc, 'input', 'bp-fq-select');
  inp.type = 'date'; inp.value = v.date || ''; inp.max = h.today;
  inp.title = 'Pick a day for its round trips; clear it for today\'s live fills';
  inp.onchange = () => h.onDate(inp.value);
  b.append(lab, inp);
  if (v.date) {
    const tags = allTags(v.trips || []);
    if (tags.length) {
      const sel = mk(doc, 'select', 'bp-fq-select');
      for (const t of ['', ...tags]) { const o = mk(doc, 'option', null, t || 'All tags'); o.value = t; sel.appendChild(o); }
      sel.value = v.tag || '';
      sel.onchange = () => h.onTag(sel.value);
      b.appendChild(sel);
    }
    const x = mk(doc, 'button', 'bp-act', 'Export CSV');
    x.type = 'button'; x.disabled = !(v.trips || []).length;
    x.onclick = () => h.onCsv();
    b.appendChild(x);
  }
  return b;
}

const HEAD = [['Time (ET)'], ['Account'], ['Symbol'], ['Side'], ['Qty', 'num'], ['Entry', 'num'], ['Exit', 'num'], ['Gross $', 'num'], ['R', 'num'],
  ['Tags'], ['Note']];
/* A picked day: v = {date, trips, tag, error}; trips null while loading. Rebuilt whole by its caller, never on a desk event. */
function day(doc, body, v, h) {
  body.replaceChildren();
  body.dataset.day = v.date;
  if (v.error) { body.appendChild(mk(doc, 'div', 'bp-empty', v.error)); return; }
  if (!v.trips) { body.appendChild(mk(doc, 'div', 'bp-empty', 'Loading…')); return; }
  const trips = withTag(v.trips, v.tag);
  if (!trips.length) { body.appendChild(mk(doc, 'div', 'bp-empty', v.trips.length ? 'No trips with that tag' : `No trades on ${v.date}`)); return; }
  const table = mk(doc, 'table', 'bp-table bp-jr'), thead = mk(doc, 'thead'), htr = mk(doc, 'tr'), tbody = mk(doc, 'tbody');
  for (const [t, c] of HEAD) htr.appendChild(mk(doc, 'th', c, t));
  thead.appendChild(htr);
  for (const t of trips) {
    const r = tripRow(t, h.labelOf), tr = mk(doc, 'tr');
    tr.dataset.key = r.key;
    td(doc, tr, r.time); td(doc, tr, r.who); td(doc, tr, r.symbol); td(doc, tr, r.side, r.side === 'Long' ? 'up' : 'down');
    td(doc, tr, r.qty, 'num'); td(doc, tr, r.entry, 'num'); td(doc, tr, r.exit, 'num');
    td(doc, tr, r.pnl, 'num ' + r.pnlTone); td(doc, tr, r.r, 'num ' + r.rTone);
    const tagIn = mk(doc, 'input', 'bp-fq-select'), noteIn = mk(doc, 'input', 'bp-fq-select');
    tagIn.value = r.tags; tagIn.placeholder = 'tags, comma'; tagIn.maxLength = 120;
    noteIn.value = r.note; noteIn.placeholder = 'note'; noteIn.maxLength = 2000;
    const save = () => h.onSave(t, noteIn.value, splitTags(tagIn.value));
    tagIn.onchange = save; noteIn.onchange = save;
    const c1 = mk(doc, 'td'), c2 = mk(doc, 'td');
    c1.appendChild(tagIn); c2.appendChild(noteIn);
    tr.append(c1, c2);
    tbody.appendChild(tr);
  }
  const net = trips.reduce((s, t) => s + (t.pnl == null ? 0 : t.pnl), 0), tfoot = mk(doc, 'tfoot'), ftr = mk(doc, 'tr');
  td(doc, ftr, `${trips.length} trip${trips.length === 1 ? '' : 's'}`);
  for (let i = 1; i < 7; i++) td(doc, ftr, '');
  td(doc, ftr, usd(net), 'num ' + tone(net));
  for (let i = 8; i < HEAD.length; i++) td(doc, ftr, '');
  tfoot.appendChild(ftr);
  table.append(thead, tbody, tfoot);
  body.appendChild(table);
}

const api = { deskDay, tripRow, csv, withTag, allTags, splitTags, load, saveNote, bar, day };
if (typeof window !== 'undefined') window.HBJournal = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
