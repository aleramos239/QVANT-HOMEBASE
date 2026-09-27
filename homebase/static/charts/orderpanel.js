/* Homebase Charts — HBOrderPanel: TradingView's order panel, docked on the right of the chart page
   (2026-09-27 order-panel plan, Task 3). It follows the SELECTED chart: that chart's instrument, quote, tick and
   point value, and that chart's own trading accounts (2026-09-27 algo-per-chart plan, "Trading per chart"). On a
   chart whose Trading is off it is greyed out and cannot send.

   Money path:
     - the send resolves the chart at CLICK time (HBCharts.cells[HBCharts.selected]) -- never a chart reference
       kept from a paint -- and refuses when that is not the chart the form was last painted for;
     - it validates with HBTrade.panelOrder against the latest quote, then hands the explicit prices (entry,
       trigger, SL, TP, TIF) to HBTradeUI.placeOrder, which owns everything else: the chart's gate (its mode, LIVE
       arms, still on the page, still on that symbol) at click and again at send, the confirm dialog (unless
       one-click), the frozen preview -> send, the shown ∩ fresh accounts, the in-flight lock, the no-quote
       refusals. This file never calls HBDeskClient.send;
     - Enter in a field never sends. Only a pointer click on the send button, or Enter / Space on it (not a held
       key), does.
   The form is built ONCE (mount). Desk, quote, selection and busy events only patch texts, classes and disabled
   states in place; the accounts row is rebuilt only when its chips change; an input's value is never rewritten
   while it has focus. Browser only; the logic lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const Cat = window.HBCatalog;
const D = () => window.HBDeskClient;
const UI = () => window.HBTradeUI;

const KEY = 'hb_charts_opanel';        // {open, w}: per viewer, a convenience only
const W_MIN = 280, W_MAX = 420, W_DEF = 320;
const TYPES = [['Market', 'Market'], ['Limit', 'Limit'], ['Stop', 'Stop'], ['StopLimit', 'Stop Limit']];
const UNITS = [['usd', '$'], ['ticks', 'ticks'], ['price', 'price']];
const STALE_MS = 10000;                // the tiles dim when the quote's last trade is older than this

let page = null;
let el = null;                          // the <aside>
let ui = null;                          // element references, built once
let open = false, width = W_DEF, tab = 'order';
let seen = { cell: null, root: null };  // the chart the form was last painted for
let formRoot = null;                    // the symbol the form's prices were typed for (reset when it changes)
let acctKey = null, logoRoot = null;
const st = {                            // the form, as typed (strings for fields)
  side: 'Buy', type: 'Market', price: '', trigger: '', limit: '', qty: '1', riskOn: false, risk: '',
  tp: { on: false, unit: 'ticks', value: '' }, sl: { on: false, unit: 'ticks', value: '' }, tif: 'Day',
  exitsOpen: true, extraOpen: false,
};
const needDefault = { price: true, trigger: true, limit: true };   // fill from the last price when next shown

/* ---- small helpers ---- */
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = window.HBIcons[name] || ''; return s; }   // our own static SVG strings
function fmtIn(v, tick) { return Number.isFinite(v) ? v.toFixed(Cat.decimals(tick)) : ''; }
function selectedCell() { const C = window.HBCharts; return C ? C.cells[C.selected] || null : null; }
function focused(input) { return document.activeElement === input; }
function load() {
  try { const v = JSON.parse(localStorage.getItem(KEY) || 'null'); return v && typeof v === 'object' ? v : null; } catch (_) { return null; }
}
function save() { try { localStorage.setItem(KEY, JSON.stringify({ open, w: width })); } catch (_) { /* storage off: this session only */ } }
function sw(label) {
  const b = mk('button', 'switch');
  b.type = 'button';
  b.setAttribute('role', 'switch');
  b.setAttribute('aria-checked', 'false');
  b.setAttribute('aria-label', label);
  return b;
}
function paintSwitch(b, on) { b.classList.toggle('on', on); b.setAttribute('aria-checked', String(on)); }
function field(label, key) {
  const row = mk('label', 'op-field'), inp = mk('input', 'op-in');
  inp.type = 'text'; inp.inputMode = 'decimal'; inp.autocomplete = 'off'; inp.spellcheck = false;
  inp.dataset.pick = key;   // focused, a click on the selected chart fills it
  row.append(mk('span', 'op-lab', label), inp);
  return { row, inp };
}

/* ---- the form's numbers for one chart: the exits' triples, the size, and panelOrder's verdict ----
   Typed numbers are read strictly (fix round 1): qty digits only, $ and prices plain decimals -- anything else
   (commas, hex, exponents) is refused with its reason, never guessed at. */
const EXIT_NAMES = { tp: 'Take profit', sl: 'Stop loss' };
const blank = (v) => String(v == null ? '' : v).trim() === '';
function exitVal(k) { return st[k].unit === 'price' ? T.parseDecimal(st[k].value, true) : T.parseUsd(st[k].value); }
function compute(cell) {
  const root = cell.shown.root, tick = cell.tick, pv = cell.pv ?? null;
  const q = D().quotes[root] || null, now = page.clockMs();
  const { side, type } = st;
  const px = (v) => T.parseDecimal(v, true);
  const price = type === 'Limit' || type === 'Stop' ? px(st.price) : type === 'StopLimit' ? px(st.limit) : null;
  const trigger = type === 'StopLimit' ? px(st.trigger) : null;
  const rt = (v) => (Number.isFinite(v) ? T.roundTick(v, tick) : null);
  const last = q && q.last != null ? q.last : null;
  const slEntry = type === 'Market' ? last : type === 'StopLimit' ? rt(trigger) : rt(price);
  const tpEntry = type === 'Market' ? last : rt(price);   // a Stop Limit's LIMIT: its TP's entry and its worst fill
  const triple = (k, entry, qty) => (st[k].on ? T.exitTriple({ unit: st[k].unit, value: exitVal(k), side, entry, tick, pv, kind: k, qty }) : null);
  const risk = st.riskOn ? T.parseUsd(st.risk) : null;
  let qty;
  if (st.riskOn) {
    // sized from the worst fill, as panelOrder and the confirm's "risk (worst fill)" (fix round 1): a Stop Limit's
    // SL distance runs from its LIMIT
    const one = triple('sl', slEntry, 1);
    qty = one ? T.qtyFromRisk(risk, T.riskTicks(tpEntry, one.price, tick), tick, pv) : 0;
  } else qty = T.parseQty(st.qty);
  const qd = Number.isInteger(qty) && qty >= 1 ? qty : 1;   // the $ figures: the whole order's
  const sl = triple('sl', slEntry, qd), tp = triple('tp', tpEntry, qd);
  // a Stop Limit's worst-fill loss at its SL (from the limit), when the limit is not the trigger
  const worst = type === 'StopLimit' && sl && tpEntry != null && tpEntry !== slEntry && pv > 0
    ? T.riskTicks(tpEntry, sl.price, tick) * tick * pv * qd : null;
  // an exit typed as a price that sits on the wrong side has no triple: pass the price so panelOrder names the side
  const exitPx = (k, t) => (!st[k].on ? null : t ? t.price : st[k].unit === 'price' ? exitVal(k) : NaN);
  const lim = D().state && D().state.limits;
  const qtyMax = Math.min(T.PANEL_QTY_MAX, lim && lim.max_order_qty > 0 ? lim.max_order_qty : T.PANEL_QTY_MAX);
  const order = formError(type, qty, risk, sl, pv, qd, tick) || T.panelOrder({ side, type, qty: st.riskOn ? null : qty, price, trigger,
    sl: exitPx('sl', sl), tp: exitPx('tp', tp), tif: st.tif, risk, quote: q, nowMs: now, tick, pv, qtyMax });
  return { root, tick, q, now, sl, tp, qty, order, worst };
}
/* What the user typed that can't be read, as {ok: false, error}; null when every shown field is readable. */
function formError(type, qty, risk, sl, pv, qd, tick) {
  const bad = (error) => ({ ok: false, error });
  if (!st.riskOn && !Number.isFinite(qty)) return bad(blank(st.qty) ? 'Enter the quantity' : 'Quantity: whole contracts, digits only');
  if (st.riskOn && !blank(st.risk) && !Number.isFinite(risk)) return bad('USD risk: digits and one decimal point only');
  const shown = type === 'StopLimit' ? [['trigger', 'Trigger'], ['limit', 'Limit']] : type === 'Market' ? [] : [['price', 'Price']];
  for (const [k, name] of shown) if (!blank(st[k]) && !Number.isFinite(T.parseDecimal(st[k], true))) return bad(`${name}: digits and one decimal point only`);
  for (const k of ['tp', 'sl']) {
    if (st[k].on && !blank(st[k].value) && !Number.isFinite(exitVal(k))) return bad(`${EXIT_NAMES[k]}: digits and one decimal point only`);
  }
  if (st.sl.on && st.sl.unit === 'usd' && !sl && exitVal('sl') > 0 && pv > 0) {
    return bad(`Stop loss is under one tick (${T.money(tick * pv * qd)} a tick at this size)`);
  }
  return null;
}

/* ---- build (once) ---- */
function build() {
  ui = {};
  const head = mk('div', 'op-head');
  ui.logo = mk('span', 'op-logo');
  ui.sym = mk('span', 'op-sym', '—');
  ui.name = mk('span', 'op-name');
  ui.close = mk('button', 'op-x');
  ui.close.type = 'button'; ui.close.title = 'Close'; ui.close.setAttribute('aria-label', 'Close the order panel');
  ui.close.appendChild(icon('x'));
  ui.close.onclick = () => setOpen(false);
  head.append(ui.logo, ui.sym, ui.name, mk('span', 'op-spacer'), ui.close);

  const tabs = mk('div', 'op-tabs');
  tabs.setAttribute('role', 'tablist');
  ui.tabs = {};
  for (const [id, text] of [['order', 'Order'], ['dom', 'DOM']]) {
    const b = mk('button', 'op-tab', text);
    b.type = 'button'; b.setAttribute('role', 'tab');
    b.onclick = () => { tab = id; paint(); };
    ui.tabs[id] = b;
    tabs.appendChild(b);
  }

  // ---- the Order tab ----
  ui.order = mk('div', 'op-order');
  ui.order.setAttribute('role', 'tabpanel');
  ui.form = mk('div', 'op-form');

  const tiles = mk('div', 'op-tiles');
  ui.tile = {};
  for (const side of ['Sell', 'Buy']) {
    const b = mk('button', `op-tile ${side === 'Buy' ? 'buy' : 'sell'}`);
    b.type = 'button';
    b.setAttribute('aria-pressed', 'false');
    const px = mk('span', 'op-tpx', '—');
    b.append(px, mk('span', 'op-tlbl', side));
    b.onclick = () => { st.side = side; paint(); };
    ui.tile[side] = { b, px };
  }
  ui.spread = mk('span', 'op-spread');
  tiles.append(ui.tile.Sell.b, ui.spread, ui.tile.Buy.b);

  const types = mk('div', 'op-types');
  types.setAttribute('role', 'tablist');
  types.setAttribute('aria-label', 'Order type');
  ui.types = {};
  for (const [id, text] of TYPES) {
    const b = mk('button', 'op-type', text);
    b.type = 'button'; b.setAttribute('role', 'tab');
    b.onclick = () => setType(id);
    ui.types[id] = b;
    types.appendChild(b);
  }

  const fields = mk('div', 'op-fields');
  ui.f = { price: field('Price', 'price'), trigger: field('Trigger', 'trigger'), limit: field('Limit', 'limit') };
  for (const [k, f] of Object.entries(ui.f)) {
    f.inp.addEventListener('input', () => { st[k] = f.inp.value; needDefault[k] = false; paint(); });
    fields.appendChild(f.row);
  }

  // Units: contracts, or a USD risk sized from the stop loss
  const units = mk('div', 'op-units');
  const urow = mk('label', 'op-field');
  ui.qty = mk('input', 'op-in');
  ui.qty.type = 'text'; ui.qty.inputMode = 'numeric'; ui.qty.autocomplete = 'off';
  ui.qty.addEventListener('input', () => { st.qty = ui.qty.value; paint(); });
  ui.risk = mk('input', 'op-in');
  ui.risk.type = 'text'; ui.risk.inputMode = 'decimal'; ui.risk.autocomplete = 'off'; ui.risk.placeholder = 'USD';
  ui.risk.addEventListener('input', () => { st.risk = ui.risk.value; paint(); });
  ui.unitsLab = mk('span', 'op-lab', 'Units');
  urow.append(ui.unitsLab, ui.qty, ui.risk);
  const rrow = mk('div', 'op-swrow');
  ui.riskSw = sw('USD risk');
  ui.riskSw.onclick = () => setRisk(!st.riskOn);
  rrow.append(mk('span', 'op-sub', 'USD risk'), ui.riskSw);
  ui.qtyNote = mk('div', 'op-note');
  units.append(urow, rrow, ui.qtyNote);

  // Exits: TP and SL, each a switch, a value and its unit, with the other two alongside
  const exits = coll('Exits', 'exitsOpen');
  ui.exits = exits;
  ui.ex = {};
  for (const [k, label] of [['tp', 'Take profit'], ['sl', 'Stop loss']]) {
    const box = mk('div', 'op-exit'), top = mk('div', 'op-swrow');
    const s = sw(label);
    s.onclick = () => { st[k].on = !st[k].on; paint(); };
    top.append(mk('span', 'op-exlab', label), s);
    const row = mk('div', 'op-exrow'), inp = mk('input', 'op-in'), sel = mk('select', 'op-sel');
    inp.type = 'text'; inp.inputMode = 'decimal'; inp.autocomplete = 'off';
    inp.setAttribute('aria-label', `${label} value`);
    inp.addEventListener('input', () => { st[k].value = inp.value; paint(); });
    sel.setAttribute('aria-label', `${label} unit`);
    for (const [u, text] of UNITS) { const o = mk('option', '', text); o.value = u; sel.appendChild(o); }
    sel.onchange = () => setUnit(k, sel.value);
    row.append(inp, sel);
    const sub = mk('div', 'op-note');
    box.append(top, row, sub);
    exits.body.appendChild(box);
    ui.ex[k] = { box, sw: s, inp, sel, sub, row };
  }

  // Extra settings: time in force for a resting order
  const extra = coll('Extra settings', 'extraOpen');
  ui.extra = extra;
  const tifRow = mk('label', 'op-field');
  ui.tif = mk('select', 'op-sel');
  for (const t of ['Day', 'GTC']) { const o = mk('option', '', t); o.value = t; ui.tif.appendChild(o); }
  ui.tif.onchange = () => { st.tif = ui.tif.value; paint(); };
  tifRow.append(mk('span', 'op-lab', 'Time in force'), ui.tif);
  ui.tifRow = tifRow;
  ui.tifNote = mk('div', 'op-note');
  extra.body.append(tifRow, ui.tifNote);

  ui.form.append(tiles, types, fields, units, exits.box, extra.box);

  // the chart's accounts (outside the greyed form: "Change" works on a chart with Trading off)
  const accts = mk('div', 'op-accts');
  const ahead = mk('div', 'op-ahead');
  ui.change = mk('button', 'op-link', 'Change');
  ui.change.type = 'button';
  ui.change.title = "This chart's trading and accounts (the Trade menu)";
  ui.change.onclick = () => { const b = document.getElementById('tbTrade'); if (b) b.click(); };
  ahead.append(mk('span', 'op-lab', 'Accounts'), ui.change);
  ui.chips = mk('div', 'op-chips');
  ui.why = mk('div', 'op-why');
  accts.append(ahead, ui.chips, ui.why);

  const foot = mk('div', 'op-foot');
  ui.send = mk('button', 'op-send buy', 'Buy');
  ui.send.type = 'button';
  T.wireSend(ui.send, send);
  ui.reason = mk('div', 'op-reason');
  ui.reason.setAttribute('role', 'status');
  foot.append(ui.send, ui.reason);

  ui.order.append(ui.form, accts, foot);

  // ---- the DOM tab (the Level 2 ladder comes next) ----
  ui.dom = mk('div', 'op-dom', 'Level 2 ladder — coming next');
  ui.dom.setAttribute('role', 'tabpanel');

  ui.grip = mk('div', 'op-resize');
  ui.grip.setAttribute('role', 'separator');
  ui.grip.setAttribute('aria-orientation', 'vertical');
  ui.grip.setAttribute('aria-label', 'Resize the order panel');
  ui.grip.tabIndex = 0;
  wireResize(ui.grip);

  el.replaceChildren(ui.grip, head, tabs, ui.order, ui.dom);
}

/* A collapsible section (TradingView's "Exits", "Extra settings"): its header toggles st[key]. */
function coll(title, key) {
  const box = mk('div', 'op-coll'), h = mk('button', 'op-chead'), body = mk('div', 'op-cbody');
  h.type = 'button';
  h.append(mk('span', '', title), icon('chevron'));
  h.onclick = () => { st[key] = !st[key]; paint(); };
  box.append(h, body);
  return { box, head: h, body, key };
}

/* ---- the send: a pointer click, or Enter / Space on the focused button -- never a held key (HBTrade.wireSend,
   shared with the chart's Buy/Sell block) ---- */
function send() {
  if (UI().busy() || ui.send.disabled) return;
  const cell = selectedCell();   // resolved NOW, at the click -- never a chart kept from a paint
  if (!cell || !cell.shown) { D().toast('err', 'No chart selected — nothing sent'); return; }
  if (cell !== seen.cell || cell.shown.root !== seen.root) {
    paint();
    D().toast('err', 'The selected chart changed — review the order');
    return;
  }
  const c = compute(cell);
  if (!c.order.ok) { paint(); D().toast('err', c.order.error); return; }
  const o = c.order;
  UI().placeOrder({ cell, root: c.root, side: o.side, type: o.type, price: o.price, trigger: o.trigger, qty: o.qty,
    tif: o.tif, exits: { sl: o.sl, tp: o.tp } });
}

/* ---- form changes that write an input (never while it has focus) ---- */
function setType(type) {
  st.type = type;
  if (type === 'Limit' || type === 'Stop') { if (!st.price) needDefault.price = true; }
  if (type === 'StopLimit') { if (!st.trigger) needDefault.trigger = true; if (!st.limit) needDefault.limit = true; }
  paint();
}
/* A unit change keeps the same exit: the value is re-expressed in the new unit. */
function setUnit(k, unit) {
  const cell = selectedCell(), e = ui.ex[k];
  if (!cell || !cell.shown) { st[k].unit = unit; paint(); return; }
  const c = compute(cell), t = c[k];
  st[k].unit = unit;
  st[k].value = !t ? '' : unit === 'usd' ? (t.usd == null ? '' : String(t.usd)) : unit === 'ticks' ? String(t.ticks) : fmtIn(t.price, c.tick);
  e.inp.value = st[k].value;
  paint();
}
function setRisk(on) {
  if (on && st.sl.unit === 'usd') setUnit('sl', 'ticks');   // the risk IS the stop's $: the SL is set in ticks or price
  st.riskOn = on;
  if (on && !st.sl.on) st.sl.on = true;
  paint();
}
/* The exits back to the Trade menu's tick defaults (0 = off): at mount and on a symbol change. */
function resetExits() {
  const p = D().prefs;
  for (const [k, n] of [['tp', p.tpTicks], ['sl', p.slTicks]]) {
    st[k] = { on: n > 0, unit: 'ticks', value: n > 0 ? String(n) : '' };
    if (ui) { ui.ex[k].inp.value = st[k].value; ui.ex[k].sel.value = 'ticks'; }
  }
}
function symbolChanged() {
  st.price = st.trigger = st.limit = '';
  needDefault.price = needDefault.trigger = needDefault.limit = true;
  for (const k of ['price', 'trigger', 'limit']) ui.f[k].inp.value = '';
  resetExits();
}

/* ---- paint: texts, classes and disabled states in place ---- */
function paint() {
  if (!ui) return;
  el.hidden = !open;
  el.style.width = `${width}px`;
  const tb = document.getElementById('tbOrder');
  if (tb) { tb.setAttribute('aria-pressed', String(open)); tb.classList.toggle('active', open); }
  const cell = selectedCell(), root = cell && cell.shown ? cell.shown.root : null;
  if (cell !== seen.cell || root !== seen.root) {
    if (seen.cell && cell !== seen.cell) flashPending = true;   // shown once this chart's accounts paint (it may still be loading)
    seen = { cell, root };
  }
  if (root !== null && root !== formRoot) {   // another symbol: its prices and exits start over
    if (formRoot !== null) symbolChanged();
    formRoot = root;
  }
  if (!open) { flashPending = false; return; }
  for (const [id, b] of Object.entries(ui.tabs)) { b.setAttribute('aria-selected', String(tab === id)); b.classList.toggle('on', tab === id); }
  ui.order.hidden = tab !== 'order';
  ui.dom.hidden = tab !== 'dom';

  // header: the badge (rebuilt only on a symbol change), the root and its name
  if (root !== logoRoot) { logoRoot = root; ui.logo.replaceChildren(...(root ? [window.HBCell.badgeEl(root, 20)] : [])); }
  if (!cell || !root) {
    ui.sym.textContent = cell ? (cell.cfg && cell.cfg.root) || '—' : '—';
    ui.name.textContent = '';
    el.classList.add('off');
    paintIdle(cell ? 'Loading the chart…' : 'No chart selected');
    return;
  }
  // prices: default a newly shown price field to the last trade (tick-rounded) -- before compute reads them
  const q0 = D().quotes[root], last = q0 && q0.last != null ? q0.last : null;
  const shownF = { price: st.type === 'Limit' || st.type === 'Stop', trigger: st.type === 'StopLimit', limit: st.type === 'StopLimit' };
  for (const k of Object.keys(ui.f)) {
    ui.f[k].row.hidden = !shownF[k];
    if (shownF[k] && needDefault[k] && last != null && !focused(ui.f[k].inp)) {
      st[k] = fmtIn(T.roundTick(last, cell.tick), cell.tick);
      ui.f[k].inp.value = st[k];
      needDefault[k] = false;
    }
  }

  const c = compute(cell);
  ui.sym.textContent = root;   // the root the order body carries; the desk picks the contract (fix round 1)
  ui.name.textContent = Cat.rootName(root) || '';

  // Trading per chart: this chart's switch, accounts and mode (LIVE-arm aware)
  const t = UI().tradeOf(cell), m = UI().effectiveMode(cell);
  el.classList.toggle('off', !t.on);
  paintAccounts(t, m);
  if (flashPending) { flashPending = false; flashChips(); }   // another chart: its accounts are the ones an order goes to now (fix round 1)


  // tiles: bid / ask (the last trade when a side is missing), the spread in ticks, dim when stale
  const view = T.quoteView(c.q, c.tick, c.now), stale = !T.freshQuote(c.q, c.now, STALE_MS);
  ui.tile.Sell.px.textContent = view.bid;
  ui.tile.Buy.px.textContent = view.ask;
  ui.spread.textContent = view.spread;
  ui.spread.title = view.spread ? `Spread: ${view.spread} tick${view.spread === '1' ? '' : 's'}` : '';
  for (const side of ['Sell', 'Buy']) {
    ui.tile[side].b.classList.toggle('on', st.side === side);
    ui.tile[side].b.classList.toggle('stale', stale);
    ui.tile[side].b.setAttribute('aria-pressed', String(st.side === side));
  }
  for (const [id, b] of Object.entries(ui.types)) { b.classList.toggle('on', st.type === id); b.setAttribute('aria-selected', String(st.type === id)); }

  // units
  ui.qty.hidden = st.riskOn;
  ui.risk.hidden = !st.riskOn;
  ui.unitsLab.textContent = st.riskOn ? 'Risk ($)' : 'Units';
  if (ui.qty.value === '' && !focused(ui.qty) && st.qty) ui.qty.value = st.qty;
  paintSwitch(ui.riskSw, st.riskOn);
  ui.qtyNote.textContent = !st.riskOn ? 'contracts'
    : !(T.parseUsd(st.risk) > 0) ? 'Enter the dollars to risk'
    : c.qty >= 1 ? `= ${c.qty} contract${c.qty === 1 ? '' : 's'}` : !st.sl.on ? 'Turn on a stop loss to size from risk' : 'under one contract at this stop';
  ui.qtyNote.classList.toggle('warn', st.riskOn && !(c.qty >= 1));

  // exits
  paintColl(ui.exits);
  for (const k of ['tp', 'sl']) {
    const e = ui.ex[k], x = st[k], tr = c[k];
    paintSwitch(e.sw, x.on);
    e.row.hidden = !x.on;
    e.sub.hidden = !x.on;
    e.inp.dataset.pick = x.unit === 'price' ? k : '';   // a price-unit exit also takes a click on the chart
    if (e.sel.value !== x.unit) e.sel.value = x.unit;
    const usdOpt = [...e.sel.options].find((o) => o.value === 'usd');
    if (usdOpt) usdOpt.disabled = k === 'sl' && st.riskOn;
    e.sub.textContent = !tr ? (blank(x.value) ? `Enter the ${k === 'tp' ? 'take profit' : 'stop loss'}` : '—')
      : exitSub(x.unit, tr, c.tick, exitVal(k), k === 'sl' ? c.worst : null);
  }

  // extra settings: time in force for a resting order only (a Market order is Day)
  paintColl(ui.extra);
  ui.tifRow.hidden = st.type === 'Market';
  if (ui.tif.value !== st.tif) ui.tif.value = st.tif;
  ui.tifNote.textContent = st.type === 'Market' ? 'Market orders are Day only' : st.tif === 'GTC' ? T.GTC_WARN : '';
  ui.tifNote.classList.toggle('warn', st.type !== 'Market' && st.tif === 'GTC');

  // the send button
  const busy = UI().busy();
  const reason = m.mode !== 'on' ? m.reason : !c.order.ok ? c.order.error : busy ? 'Sending…' : '';
  const qtyText = c.order.ok ? c.order.qty : c.qty;
  ui.send.textContent = T.sendLabel(st.side, qtyText, c.root, st.type);
  ui.send.classList.toggle('buy', st.side === 'Buy');
  ui.send.classList.toggle('sell', st.side === 'Sell');
  ui.send.disabled = !!reason;
  ui.reason.textContent = m.mode !== 'on' ? '' : reason;   // the mode's reason already shows under the accounts
}
function paintIdle(text) {
  ui.send.disabled = true;
  ui.send.textContent = 'Buy';
  ui.reason.textContent = text;
  ui.chips.replaceChildren();
  acctKey = null;
  ui.why.textContent = '';
}
function paintColl(cl) {
  const on = !!st[cl.key];
  cl.box.classList.toggle('open', on);
  cl.body.hidden = !on;
  cl.head.setAttribute('aria-expanded', String(on));
}
/* The exit's other two units; a $ exit whose whole ticks come to other dollars than typed shows the real ones first
   ("= $31.25"); a Stop Limit's SL adds its worst-fill loss (from the limit). */
function exitSub(unit, t, tick, typed, worst) {
  const usd = t.usd == null ? null : T.money(t.usd), ticks = `${t.ticks} tick${t.ticks === 1 ? '' : 's'}`, px = Cat.fmtPrice(t.price, tick);
  let parts;
  if (unit === 'usd') parts = [t.usd != null && Math.abs(t.usd - typed) > 0.004 ? `= ${usd}` : null, ticks, px];
  else if (unit === 'ticks') parts = [usd, px];
  else parts = [ticks, usd];
  if (worst != null) parts.push(`worst fill ${T.money(worst)}`);
  return parts.filter(Boolean).join(' · ');
}
let flashTimer = 0, flashPending = false;
function flashChips() {
  ui.chips.classList.remove('flash');
  void ui.chips.offsetWidth;   // restart the highlight
  ui.chips.classList.add('flash');
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => ui.chips.classList.remove('flash'), 600);
}
/* The chart's accounts as "…047 DEMO" chips (dimmed when an order would not go there right now), rebuilt only
   when they change, and the reason the chart can't trade. */
function paintAccounts(t, m) {
  const chips = T.accountChips(D().state, t.accounts, m.mode === 'on' ? m.accounts : []);
  const key = JSON.stringify(chips);
  if (key !== acctKey) {
    acctKey = key;
    ui.chips.replaceChildren(...(chips.length ? chips.map((c) => {
      const e = mk('span', 'tr-acct' + (c.active ? '' : ' off'), c.who);
      if (c.env) e.append(mk('span', 'env' + (c.live ? ' live' : ''), c.env));
      e.title = c.active ? `Orders from this panel go to ${c.id}` : `${c.id} — not trading from this chart right now`;
      return e;
    }) : [mk('span', 'op-none', 'No accounts on this chart')]));
  }
  ui.why.textContent = m.mode === 'on' ? '' : m.reason;
}

/* ---- the price pick: the chart calls this while a price field has focus (app.js onPick) ---- */
function activePick() {
  const a = document.activeElement;
  return open && tab === 'order' && a && el.contains(a) && a.dataset && a.dataset.pick && !a.closest('[hidden]') ? a : null;
}
function wantsPick() { return !!activePick(); }
function pickPrice(price) {
  const inp = activePick(), cell = selectedCell();
  if (!inp || !cell || !cell.shown || !Number.isFinite(price)) return;
  const k = inp.dataset.pick, v = fmtIn(T.roundTick(price, cell.tick), cell.tick);
  inp.value = v;
  if (k === 'tp' || k === 'sl') st[k].value = v;
  else { st[k] = v; needDefault[k] = false; }
  paint();
  setTimeout(() => { if (document.contains(inp)) inp.focus(); }, 0);   // keep picking: focus stays on the field
}

/* ---- open / width ---- */
function setOpen(v) {
  open = !!v;
  save();
  paint();
}
function toggle() { setOpen(!open); }
function setRoot() { paint(); }   // the selected chart (or its symbol) changed: the panel re-reads it
function wireResize(g) {
  let drag = false;
  const apply = (w) => { width = Math.min(W_MAX, Math.max(W_MIN, Math.round(w))); el.style.width = `${width}px`; };
  g.addEventListener('pointerdown', (e) => {
    drag = true;
    try { g.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    e.preventDefault();
  });
  g.addEventListener('pointermove', (e) => { if (drag) apply(el.getBoundingClientRect().right - e.clientX); });
  const end = (e) => {
    if (!drag) return;
    drag = false;
    try { g.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    save();
  };
  g.addEventListener('pointerup', end);
  g.addEventListener('pointercancel', end);
  g.addEventListener('lostpointercapture', end);
  g.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); apply(width + 16); save(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); apply(width - 16); save(); }
  });
}

function mount(pg) {
  page = pg;
  el = document.getElementById('opanel');
  if (!el) return;
  const saved = load();
  width = saved && Number.isFinite(saved.w) ? Math.min(W_MAX, Math.max(W_MIN, saved.w)) : W_DEF;
  open = !!(saved && saved.open === true);
  st.qty = String(Math.min(T.PANEL_QTY_MAX, Math.max(1, D().prefs.qty)));
  build();
  ui.qty.value = st.qty;
  resetExits();
  const tb = document.getElementById('tbOrder');
  if (tb) tb.onclick = toggle;
  D().on(() => paint());                 // desk / quote / prefs events: patch in place, never rebuild
  UI().onBusyChange(() => paint());
  UI().onTradeChange(() => paint());     // a chart's Trading switch / accounts, a LIVE arm
  setInterval(() => { if (open) paint(); }, 1000);   // a quote going stale with no event
  paint();
}

window.HBOrderPanel = { mount, toggle, setRoot, pickPrice, wantsPick };
})();
