/* Homebase Charts — HBTapeUI: the Time & Sales panel's DOM (2026-10-21 tape plan). Its own floating/dockable
   panel like the DOM ladder (HBPanelShell owns the chrome; this file only fills the container it's handed and
   follows the SELECTED chart's root on its own, re-resolved every paint tick, domui.js's discipline). READ-ONLY.

   Prints reach the page as {"type":"tape", root, s, i0, rows, reset?} over the existing /ws socket (app.js's
   routing hands them to onMessage) -- but only once the page asked: {"op":"tape", root} is sent while the
   panel is open, for the selected chart's root, and {"op":"tape", root: null} when it closes, so a page
   without the panel open never receives the ~3k rows a second a busy open produces. The ring, the rebuilt
   orders, the filter and the clock are HBTape (pure, Node-tested); this file only paints them.

   Repaint discipline: every event only sets a dirty flag; one interval patches the DOM at most once every
   PAINT_MIN_MS (<= 10 fps). Only as many row elements as fit the list exist (newest first, no scroll-back in
   this version); they are built once per height and rewritten in place after that. Browser only. */
(() => {
'use strict';
const Tape = window.HBTape;
const Cat = window.HBCatalog;

const PAINT_MIN_MS = 100;   // <= 10 fps
const ROW_H = 18;           // px, matches .tape-row in tape.css
const MAX_ROWS = 200;

let page = null;
let container = null;
let ui = null;                     // built once
let visible = false;
let cur = { cell: null, root: null, tick: 0.25 };
let tape = Tape.empty();
let sent = null;                   // the root the server is streaming for us (null: nothing)
let mode = 'orders';               // 'orders' | 'raw'
let minSize = 0;
let side = 0;                      // 0 both · 1 buys · -1 sells
const rowEls = [];                 // newest first: {row, time, price, size, n, lv}
let dirty = false;

function mkEl(tag, cls, text) { return page.mk(tag, cls, text); }
function selectedCell() { const C = window.HBCharts; return C ? C.cells[C.selected] || null : null; }

/* ---- build (once) ---- */
function buildRowEl() {
  const row = mkEl('div', 'tape-row');
  const time = mkEl('span', 'tape-c tape-time');
  const price = mkEl('span', 'tape-c tape-price');
  const size = mkEl('span', 'tape-c tape-size');
  const n = mkEl('span', 'tape-c tape-n');
  const lv = mkEl('span', 'tape-c tape-lv');
  row.append(time, price, size, n, lv);
  return { row, time, price, size, n, lv };
}
function build() {
  ui = {};
  ui.wrap = mkEl('div', 'tape-wrap');

  ui.head = mkEl('div', 'tape-head');
  ui.seg = mkEl('div', 'seg');
  ui.modeBtns = {};
  for (const [m, label] of [['orders', 'Orders'], ['raw', 'Raw']]) {
    const b = mkEl('button', m === mode ? 'on' : '', label);
    b.type = 'button';
    b.onclick = () => { mode = m; for (const k in ui.modeBtns) ui.modeBtns[k].classList.toggle('on', k === m); dirty = true; };
    ui.modeBtns[m] = b;
    ui.seg.appendChild(b);
  }
  ui.min = mkEl('input', 'op-in tape-min');
  ui.min.type = 'number';
  ui.min.min = '0';
  ui.min.step = '1';
  ui.min.placeholder = 'min';
  ui.min.title = 'Minimum size';
  ui.min.setAttribute('aria-label', 'Minimum size');
  ui.min.oninput = () => { minSize = Math.max(0, Number(ui.min.value) || 0); dirty = true; };
  ui.side = mkEl('select', 'op-sel tape-side');
  ui.side.title = 'Side';
  ui.side.setAttribute('aria-label', 'Side');
  for (const [v, label] of [['0', 'Both'], ['1', 'Buys'], ['-1', 'Sells']]) ui.side.appendChild(new Option(label, v));
  ui.side.onchange = () => { side = Number(ui.side.value) || 0; dirty = true; };
  ui.head.append(ui.seg, mkEl('span', 'tape-spacer'), ui.min, ui.side);

  ui.cols = mkEl('div', 'tape-cols');
  ui.cols.append(mkEl('span', 'tape-c', 'Time'), mkEl('span', 'tape-c', 'Price'), mkEl('span', 'tape-c', 'Size'),
    mkEl('span', 'tape-c tape-n', 'Prints'), mkEl('span', 'tape-c tape-lv', 'Lvls'));

  ui.rows = mkEl('div', 'tape-rows');
  ui.rows.setAttribute('role', 'list');
  ui.rows.setAttribute('aria-label', 'Time and sales');
  if (window.ResizeObserver) new ResizeObserver(() => { dirty = true; }).observe(ui.rows);   // a resize changes how many rows fit

  ui.idle = mkEl('div', 'tape-idle');

  ui.wrap.append(ui.head, ui.cols, ui.rows, ui.idle);
  container.replaceChildren(ui.wrap);
}

/* ---- inputs: app.js's ws routing feeds onMessage / onOpen / onDisconnect; every one just marks dirty ---- */
function onMessage(m) {
  if (!m || m.root !== cur.root) return;   // a late message for the chart we just left
  tape = Tape.apply(tape, m);
  dirty = true;
}
/* The selected chart, every paint tick (cheap: it only updates what we track). */
function sync(cell) {
  const root = cell && cell.shown ? cell.shown.root : null;
  const tick = cell ? cell.tick : 0.25;
  if (root !== cur.root) { tape = Tape.empty(); dirty = true; }
  cur = { cell, root, tick };
}
/* What the server should be streaming: the selected root while the panel is open, nothing otherwise. Asked
   again whenever that changes; a send that fails (socket closed) is retried on the next tick. */
function subscribe() {
  const want = visible ? cur.root : null;
  if (want === sent) return;
  if (page.send({ op: 'tape', root: want })) sent = want;
}
function onOpen() { sent = null; subscribe(); }          // a new socket streams nothing until told: ask again
function onDisconnect() { sent = null; }                  // the ring stays; the hello after the reconnect resets it
function setVisible(v) {
  v = !!v;
  if (v === visible) return;
  visible = v;
  dirty = true;
  subscribe();
}

/* ---- paint ---- */
function showIdle(text) {
  ui.idle.textContent = text;
  ui.idle.hidden = false;
  ui.cols.hidden = true;
  ui.rows.hidden = true;
}
function showGrid() {
  ui.idle.hidden = true;
  ui.cols.hidden = false;
  ui.rows.hidden = false;
}
function paintRows(list, tick) {
  const fit = Math.min(MAX_ROWS, Math.max(1, Math.ceil(ui.rows.clientHeight / ROW_H)));
  if (rowEls.length !== fit) {
    rowEls.length = 0;
    for (let i = 0; i < fit; i++) rowEls.push(buildRowEl());
    ui.rows.replaceChildren(...rowEls.map((e) => e.row));
  }
  const raw = mode === 'raw';
  for (let i = 0; i < fit; i++) {
    const e = rowEls[i], o = list[list.length - 1 - i];   // newest first
    e.row.hidden = !o;
    if (!o) continue;
    e.row.classList.toggle('buy', o.side > 0);
    e.row.classList.toggle('sell', o.side < 0);
    e.time.textContent = Tape.fmtTime(o.t);
    e.price.textContent = Cat.fmtPrice(o.vwap, tick);
    e.size.textContent = Cat.fmtCompact(o.size);
    e.n.textContent = raw ? '' : String(o.n);
    e.lv.textContent = raw ? '' : String(Math.round((o.hi - o.lo) / tick) + 1);
  }
}
function paint() {
  const { cell, root, tick } = cur;
  if (!cell) return showIdle('No chart selected');
  if (!root) return showIdle('Loading the chart…');
  if (tape.root !== root) return showIdle(`Waiting for ${root} prints…`);
  showGrid();
  ui.wrap.classList.toggle('raw', mode === 'raw');
  const list = mode === 'raw' ? Tape.prints(tape.rows, tape.i0) : Tape.orders(tape.rows, tape.i0);
  paintRows(Tape.filter(list, minSize, null, side), tick);
}

function mount(el, pg) {
  container = el;
  page = pg;
  build();
  setInterval(() => {
    sync(selectedCell());
    subscribe();
    if (dirty) { dirty = false; if (visible) paint(); }
  }, PAINT_MIN_MS);
}

window.HBTapeUI = { mount, setVisible, onMessage, onOpen, onDisconnect };
})();
