/* Homebase Charts — HBOrderPanel: TradingView's order panel (2026-09-27 order-panel plan, Task 3; split into
   its own floating/dockable panel by the 2026-09-27 panels plan — HBPanelShell owns the chrome: open/close,
   dock/float, drag, resize. This file only fills the container HBPanelShell hands it and never touches the
   page's layout itself). It follows the SELECTED chart: that chart's instrument, quote, tick and point value,
   and that chart's own trading accounts (2026-09-27 algo-per-chart plan, "Trading per chart"). On a chart
   whose Trading is off it is greyed out and cannot send.

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

const TYPES = [['Market', 'Market'], ['Limit', 'Limit'], ['Stop', 'Stop'], ['StopLimit', 'Stop Limit']];
const UNITS = [['usd', '$'], ['ticks', 'ticks'], ['price', 'price']];

let page = null;
let el = null;                          // the content container HBPanelShell hands us
let ui = null;                          // element references, built once
let visible = false;                    // HBPanelShell.setVisible: the panel is open (docked or floating)
let seen = { cell: null, root: null };  // the chart the form was last painted for
let formRoot = null;                    // the symbol the form's prices were typed for (reset when it changes)
let acctKey = null, logoRoot = null;
let prefQty = null;                     // the shared quantity (the chart's Buy/Sell box) the form last took
const st = {                            // the form, as typed (strings for fields)
  side: 'Buy', type: 'Market', price: '', trigger: '', limit: '', qty: '1', riskOn: false, risk: '',
  tp: { on: false, unit: 'ticks', value: '' }, sl: { on: false, unit: 'ticks', value: '' }, tif: 'Day',
  be: { on: false, unit: 'ticks', value: '' },   // auto-breakeven: the level that moves the stop to entry + 1 tick
  tr: { on: false, unit: 'ticks', value: '', after: 'fill' },
  p1: { on: false, unit: 'ticks', value: '', qty: '1' },   // partial take profit: `qty` contracts at TP1, the rest at the TP   // trailing stop: its distance; starts at the fill or after BE
  exitsOpen: true, extraOpen: false, lookOpen: false,
};
/* How the order's preview looks on the chart (the user, 2026-10-18: "let me play with it"); kept in this browser. */
const LOOK_KEY = 'hb.orderPreviewLook';
const LOOK0 = { on: true, style: 0, width: 1, shade: 12, labels: 'line' };
const look = (() => { try { return { ...LOOK0, ...JSON.parse(localStorage.getItem(LOOK_KEY) || 'null') }; } catch (_) { return { ...LOOK0 }; } })();
/* Where an order's breakeven / trailing stop runs (the owner, 2026-10-18): 'chart' (this page, while it is open) or
   'server' (the chart service's runner, exitrunner.py: with the page closed too). Kept in this browser. */
const RUN_KEY = 'hb.exitRunOn';
let runOn = (() => { try { return localStorage.getItem(RUN_KEY) === 'server' ? 'server' : 'chart'; } catch (_) { return 'chart'; } })();
function setRunOn(v) { runOn = v; try { localStorage.setItem(RUN_KEY, v); } catch (_) { /* this session only */ } paint(); }
function setLook(k, v) {
  look[k] = v;
  try { localStorage.setItem(LOOK_KEY, JSON.stringify(look)); } catch (_) { /* private window: this session only */ }
  paint();
  document.dispatchEvent(new Event('hb-order-look'));   // the desk's own order lines (tradelines.js) take the look too
}
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
const EXIT_NAMES = { tp: 'Take profit', p1: 'Partial take profit', sl: 'Stop loss', be: 'Breakeven', tr: 'Trailing stop' };
const BE_COLOR = '#E8A23A';
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
  // no quote (market shut): the chart's last close, so the exits still preview -- panelOrder refuses the send
  const bars = cell.bars || [], last = q && q.last != null ? q.last : bars.length ? bars[bars.length - 1].c : null;
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
  // a partial take profit leaves the TP the rest of the contracts: its $ is theirs
  const n1 = T.parseQty(st.p1.qty), rest = st.p1.on && Number.isInteger(n1) && n1 >= 1 && n1 < qd ? qd - n1 : null;
  const sl = triple('sl', slEntry, qd), tp = triple('tp', tpEntry, rest ?? qd);
  // the breakeven level sits on the profit side, as a TP does
  const be = st.be.on ? T.exitTriple({ unit: st.be.unit, value: exitVal('be'), side, entry: tpEntry, tick, pv, kind: 'tp', qty: qd }) : null;
  // the trail's distance: only its ticks (and $) count, so any entry will do when there is none yet
  const tr = st.tr.on ? T.exitTriple({ unit: st.tr.unit, value: exitVal('tr'), side, entry: tpEntry ?? 0, tick, pv, kind: 'sl', qty: qd }) : null;
  // a Stop Limit's worst-fill loss at its SL (from the limit), when the limit is not the trigger
  const worst = type === 'StopLimit' && sl && tpEntry != null && tpEntry !== slEntry && pv > 0
    ? T.riskTicks(tpEntry, sl.price, tick) * tick * pv * qd : null;
  // an exit typed as a price that sits on the wrong side has no triple: pass the price so panelOrder names the side
  const exitPx = (k, t) => (!st[k].on ? null : t ? t.price : st[k].unit === 'price' ? exitVal(k) : NaN);
  const lim = D().state && D().state.limits;
  const qtyMax = Math.min(T.PANEL_QTY_MAX, lim && lim.max_order_qty > 0 ? lim.max_order_qty : T.PANEL_QTY_MAX);
  const p1 = st.p1.on ? T.exitTriple({ unit: st.p1.unit, value: exitVal('p1'), side, entry: tpEntry, tick, pv, kind: 'tp', qty: n1 >= 1 ? n1 : 1 }) : null;
  const order = formError(type, qty, risk, sl, pv, qd, tick, be, tr) || p1Error(p1, n1, tp, qd) || T.panelOrder({ side, type, qty: st.riskOn ? null : qty, price, trigger,
    sl: exitPx('sl', sl), tp: exitPx('tp', tp), tif: st.tif, risk, quote: q, nowMs: now, tick, pv, qtyMax });
  return { root, tick, q, now, sl, tp, be, tr, p1, n1, rest, qty, order, worst, entry: tpEntry, slEntry };
}
/* What the user typed that can't be read, as {ok: false, error}; null when every shown field is readable. */
/* The partial take profit's own checks: it needs the TP, sits before it, and leaves at least one contract for it. */
function p1Error(p1, n1, tp, qd) {
  if (!st.p1.on) return null;
  const bad = (error) => ({ ok: false, error });
  if (!st.tp.on || !tp) return bad('The partial take profit needs the take profit on');
  if (!p1) return bad(blank(st.p1.value) ? 'Enter the partial take profit level' : 'Partial take profit: at least one tick on the profit side');
  if (qd < 2) return bad('A partial take profit needs at least 2 contracts');
  if (!(Number.isInteger(n1) && n1 >= 1 && n1 < qd)) return bad(`Contracts at the partial: 1 to ${qd - 1}`);
  if (p1.ticks >= tp.ticks) return bad('The partial take profit must come before the take profit');
  return null;
}
function formError(type, qty, risk, sl, pv, qd, tick, be, tr) {
  const bad = (error) => ({ ok: false, error });
  if (!st.riskOn && !Number.isFinite(qty)) return bad(blank(st.qty) ? 'Enter the quantity' : 'Quantity: whole contracts, digits only');
  if (st.riskOn && !blank(st.risk) && !Number.isFinite(risk)) return bad('USD risk: digits and one decimal point only');
  const shown = type === 'StopLimit' ? [['trigger', 'Trigger'], ['limit', 'Limit']] : type === 'Market' ? [] : [['price', 'Price']];
  for (const [k, name] of shown) if (!blank(st[k]) && !Number.isFinite(T.parseDecimal(st[k], true))) return bad(`${name}: digits and one decimal point only`);
  for (const k of ['tp', 'p1', 'sl', 'be', 'tr']) {
    if (st[k].on && !blank(st[k].value) && !Number.isFinite(exitVal(k))) return bad(`${EXIT_NAMES[k]}: digits and one decimal point only`);
  }
  if (st.sl.on && st.sl.unit === 'usd' && !sl && exitVal('sl') > 0 && pv > 0) {
    return bad(`Stop loss is under one tick (${T.money(tick * pv * qd)} a tick at this size)`);
  }
  if (st.tr.on && !tr) return bad(blank(st.tr.value) ? 'Enter the trailing distance, or turn it off' : 'Trailing stop: at least one tick');
  if (st.be.on && !be) return bad(blank(st.be.value) ? 'Enter the breakeven level, or turn it off' : 'Breakeven: at least one tick on the profit side');
  return null;
}

/* ---- build (once) ---- */
function build() {
  ui = {};
  const head = mk('div', 'op-head');
  ui.logo = mk('span', 'op-logo');
  ui.sym = mk('span', 'op-sym', '—');
  ui.name = mk('span', 'op-name');
  head.append(ui.logo, ui.sym, ui.name);

  ui.order = mk('div', 'op-order');
  ui.form = mk('div', 'op-form');

  const tiles = mk('div', 'op-tiles');
  ui.tile = {};
  for (const side of ['Sell', 'Buy']) {
    // 2026-09-28 (the user): a tile is just its side -- no bid / ask, no spread; it picks the side, Send sends
    const b = mk('button', `op-tile ${side === 'Buy' ? 'buy' : 'sell'}`);
    b.type = 'button';
    b.setAttribute('aria-pressed', 'false');
    b.append(mk('span', 'op-tlbl', side));
    b.onclick = () => { st.side = side; paint(); };
    ui.tile[side] = { b };
  }
  tiles.append(ui.tile.Sell.b, ui.tile.Buy.b);

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
  ui.qty.addEventListener('input', () => {
    st.qty = ui.qty.value;
    const n = T.parseQty(st.qty);
    if (Number.isInteger(n) && n >= 1) D().setPrefs({ qty: n });   // the chart's Buy/Sell box shows the same size
    paint();
  });
  ui.risk = mk('input', 'op-in');
  ui.risk.type = 'text'; ui.risk.inputMode = 'decimal'; ui.risk.autocomplete = 'off'; ui.risk.placeholder = 'USD';
  ui.risk.addEventListener('input', () => { st.risk = ui.risk.value; paint(); });
  ui.unitsLab = mk('span', 'op-lab', 'Units');
  urow.append(ui.unitsLab, ui.qty, ui.risk);
  const rrow = mk('div', 'op-swrow');
  ui.riskSw = sw('Size by dollar risk');
  ui.riskSw.onclick = () => setRisk(!st.riskOn);
  rrow.append(mk('span', 'op-sub', 'Size by dollar risk'), ui.riskSw);
  ui.qtyNote = mk('div', 'op-note');
  units.append(urow, ui.qtyNote, rrow);      // the note is the number's own unit ("contracts", "= 3 contracts"): right under it

  // Exits: TP and SL, each a switch, a value and its unit, with the other two alongside
  const exits = coll('Exits', 'exitsOpen');
  ui.exits = exits;
  ui.ex = {};
  for (const [k, label] of [['tp', 'Take profit'], ['p1', 'Partial take profit'], ['sl', 'Stop loss'], ['be', 'Breakeven'], ['tr', 'Trailing stop']]) {
    const box = mk('div', 'op-exit'), top = mk('div', 'op-swrow');
    const s = sw(label);
    s.onclick = () => { st[k].on = !st[k].on; paint(); };
    top.append(mk('span', 'op-exlab', label), s);
    const row = mk('div', 'op-exrow'), inp = mk('input', 'op-in'), sel = mk('select', 'op-sel');
    inp.type = 'text'; inp.inputMode = 'decimal'; inp.autocomplete = 'off';
    inp.setAttribute('aria-label', `${label} value`);
    inp.addEventListener('input', () => { st[k].value = inp.value; paint(); });
    sel.setAttribute('aria-label', `${label} unit`);
    for (const [u, text] of UNITS) {
      if (k === 'tr' && u === 'price') continue;   // a trail is a distance, never a price
      const o = mk('option', '', text); o.value = u; sel.appendChild(o);
    }
    sel.onchange = () => setUnit(k, sel.value);
    row.append(inp, sel);
    const sub = mk('div', 'op-note');
    box.append(top, row, sub);
    if (k === 'tp') {   // the TP as a multiple of the SL's distance, typed (the owner, 2026-10-18): "1 : 2.5"
      ui.rr = mk('label', 'op-field op-rr');
      ui.rrIn = mk('input', 'op-in');
      ui.rrIn.type = 'text'; ui.rrIn.inputMode = 'decimal'; ui.rrIn.autocomplete = 'off';
      ui.rrIn.setAttribute('aria-label', 'Reward to risk');
      ui.rrIn.addEventListener('input', () => { const n = T.parseDecimal(ui.rrIn.value, true); if (n > 0) setTpR(n); });
      ui.rr.append(mk('span', 'op-lab', 'Reward : risk  1 :'), ui.rrIn);
      box.append(ui.rr);
    }
    if (k === 'p1') {   // how many contracts close there
      ui.p1Row = mk('label', 'op-field');
      ui.p1Qty = mk('input', 'op-in');
      ui.p1Qty.type = 'text'; ui.p1Qty.inputMode = 'numeric'; ui.p1Qty.autocomplete = 'off';
      ui.p1Qty.setAttribute('aria-label', 'Contracts at the partial take profit');
      ui.p1Qty.addEventListener('input', () => { st.p1.qty = ui.p1Qty.value; paint(); });
      ui.p1Row.append(mk('span', 'op-lab', 'Contracts at TP1'), ui.p1Qty);
      box.append(ui.p1Row);
    }
    if (k === 'tr') {   // when it starts
      const at = mk('label', 'op-field');
      ui.trAfter = mk('select', 'op-sel');
      for (const [v, text] of [['fill', 'At the fill'], ['be', 'After breakeven']]) { const o = mk('option', '', text); o.value = v; ui.trAfter.appendChild(o); }
      ui.trAfter.onchange = () => { st.tr.after = ui.trAfter.value; paint(); };
      at.append(mk('span', 'op-lab', 'Starts'), ui.trAfter);
      ui.trAt = at;
      box.append(at);
    }
    if (k === 'be' || k === 'tr') {   // its armed breakevens / trails on this symbol, each with a Cancel
      ui.armed = ui.armed || {};
      ui.armed[k] = mk('div', 'op-armed');
      box.append(ui.armed[k]);
    }
    exits.body.appendChild(box);
    ui.ex[k] = { box, sw: s, inp, sel, sub, row };
  }

  // where the breakeven / trailing stop run
  ui.runRow = mk('label', 'op-field');
  ui.runOn = mk('select', 'op-sel');
  for (const [v, text] of [['chart', 'This chart'], ['server', 'The server']]) { const o = mk('option', '', text); o.value = v; ui.runOn.appendChild(o); }
  ui.runOn.onchange = () => setRunOn(ui.runOn.value);
  ui.runOn.title = 'This chart: while this page is open. The server: keeps working with the page or browser closed.';
  ui.runRow.append(mk('span', 'op-lab', 'BE + trail run on'), ui.runOn);
  exits.body.appendChild(ui.runRow);

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

  // Chart preview: how the entry / TP / SL preview looks (.op-look: never greyed, it works with Trading off too)
  const lk = coll('Chart preview', 'lookOpen');
  lk.box.classList.add('op-look');
  ui.look = lk;
  const lrow = mk('div', 'op-swrow');
  ui.lookSw = sw('Show on chart');
  ui.lookSw.onclick = () => setLook('on', !look.on);
  lrow.append(mk('span', 'op-sub', 'Show on chart'), ui.lookSw);
  const pick = (label, key, opts, num) => {
    const row = mk('label', 'op-field'), sel = mk('select', 'op-sel');
    for (const [v, text] of opts) { const o = mk('option', '', text); o.value = String(v); sel.appendChild(o); }
    sel.onchange = () => setLook(key, num ? Number(sel.value) : sel.value);
    row.append(mk('span', 'op-lab', label), sel);
    return { row, sel, key };
  };
  ui.lookSel = [
    pick('Line', 'style', [[0, 'Solid'], [2, 'Dashed'], [1, 'Dotted']], true),
    pick('Thickness', 'width', [[1, '1'], [2, '2'], [3, '3'], [4, '4']], true),
    pick('Labels', 'labels', [['line', 'On the line'], ['scale', 'On the price scale']], false),
  ];
  const srow = mk('label', 'op-field');
  ui.shade = mk('input');
  ui.shade.type = 'range'; ui.shade.min = '0'; ui.shade.max = '40'; ui.shade.step = '2';
  ui.shade.setAttribute('aria-label', 'Shading');
  ui.shade.oninput = () => setLook('shade', Number(ui.shade.value));
  srow.append(mk('span', 'op-lab', 'Shading'), ui.shade);
  lk.body.append(lrow, ...ui.lookSel.map((p) => p.row), srow);
  ui.form.append(tiles, types, fields, units, exits.box, extra.box, lk.box);

  // the chart's accounts (outside the greyed form: "Change" works on a chart with Trading off)
  const accts = mk('div', 'op-accts');
  const ahead = mk('div', 'op-ahead');
  ui.change = mk('button', 'op-link', 'Change');
  ui.change.type = 'button';
  ui.change.title = "This chart's accounts (its ⚙ → Trading)";
  // the Trade menu is gone: the accounts live in the chart's own Settings dialog, on its Trading tab
  ui.change.onclick = () => { const c = selectedCell(); if (c && page.chartSettings) page.chartSettings(c, 'trading'); };
  ahead.append(mk('span', 'op-lab', 'Accounts'), ui.change);
  ui.chips = mk('div', 'op-chips');
  ui.why = mk('div', 'op-why');
  accts.append(ahead, ui.chips, ui.why);

  const foot = mk('div', 'op-foot');
  // S1: the wrapper carries the LIVE ring (outside the button, so a disabled Send never dims it); the button its LIVE
  // tag ahead of the label text (paintLive). Neither changes the Send's size.
  ui.sendWrap = mk('div', 'op-sendwrap');
  ui.send = mk('button', 'op-send buy');
  ui.send.type = 'button';
  ui.sendLive = mk('span', 'tr-live', 'LIVE');
  ui.sendLive.hidden = true;
  ui.sendText = mk('span', 'op-send-t', 'Buy');
  ui.send.append(ui.sendLive, ' ', ui.sendText);   // a real space: read as "LIVE Buy …" (collapsed while the tag is hidden)
  T.wireSend(ui.send, send);
  ui.sendWrap.append(ui.send);
  ui.reason = mk('div', 'op-reason');
  ui.reason.setAttribute('role', 'status');
  foot.append(ui.sendWrap, ui.reason);

  ui.order.append(ui.form, accts, foot);

  el.replaceChildren(head, ui.order);
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
  if (ui.send.disabled) return;
  sendNow();
}
/* The chart's ENTRY tag clicked (the panel may be closed, so the Send button's state is not read): this chart's
   trading gate first, then the very same send -- placeOrder's confirm, gates and checks. */
function sendFromChart(cell) {
  if (cell !== selectedCell()) return;
  paint();
  const m = UI().effectiveMode(cell);
  if (m.mode !== 'on') { D().toast('err', m.reason); return; }
  sendNow();
}
function sendNow() {
  if (UI().busy()) return;
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
  // compute refused the order if BE / the trail is on without its value
  const beLevel = st.be.on && c.be ? c.be.price : null, trDist = st.tr.on && c.tr ? c.tr.ticks : null;
  const after = st.tr.after;
  const onSent = beLevel == null && trDist == null ? null : (b) => {
    const base = { root: c.root, side: o.side, accounts: b.accounts };
    if (runOn === 'server') {   // the BE first: the trail may wait for it by id
      const be = beLevel == null ? Promise.resolve(null) : serverArm({ ...base, kind: 'be', level: beLevel });
      if (trDist != null) be.then((x) => serverArm({ ...base, kind: 'trail', dist: trDist, be_id: after === 'be' && x ? x.id : null }));
      return;
    }
    const be = beLevel == null ? null : armBe({ ...base, kind: 'be', level: beLevel });
    if (trDist != null) armBe({ ...base, kind: 'trail', dist: trDist, best: null, beId: after === 'be' && be ? be.id : null });
  };
  const split = st.p1.on && c.p1 ? { qty: c.n1, tp: c.p1.price } : null;   // compute refused a partial that doesn't fit
  UI().placeOrder({ onSent, split, cell, root: c.root, side: o.side, type: o.type, price: o.price, trigger: o.trigger, qty: o.qty,
    tif: o.tif, exits: { sl: o.sl, tp: o.tp }, surface: 'panel' });
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
/* TP = n × the SL's ticks from the entry (whole ticks), in the TP's own unit; switched on if it was off. */
function setTpR(n) {
  const cell = selectedCell();
  if (!cell || !cell.shown) return;
  const sl = compute(cell).sl;
  if (!sl) { D().toast('err', 'Set a stop loss first'); return; }
  const unit = st.tp.unit;
  st.tp = { on: true, unit: 'ticks', value: String(Math.max(1, Math.round(sl.ticks * n))) };
  ui.ex.tp.inp.value = st.tp.value;
  if (unit !== 'ticks') setUnit('tp', unit); else paint();
}
function setRisk(on) {
  if (on && st.sl.unit === 'usd') setUnit('sl', 'ticks');   // the risk IS the stop's $: the SL is set in ticks or price
  st.riskOn = on;
  if (on && !st.sl.on) st.sl.on = true;
  paint();
}
/* The exits back to off (the retired SL/TP tick defaults are always 0: HBTrade.parsePrefs): at mount and on a
   symbol change. */
function resetExits() {
  const p = D().prefs;
  st.be = { on: false, unit: 'ticks', value: '' };
  st.tr = { on: false, unit: 'ticks', value: '', after: st.tr.after };
  st.p1 = { on: false, unit: 'ticks', value: '', qty: st.p1.qty };
  if (ui) for (const k of ['be', 'tr', 'p1']) { ui.ex[k].inp.value = ''; ui.ex[k].sel.value = 'ticks'; }
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
  const pq = D().prefs.qty;
  if (pq !== prefQty) {   // the chart's Buy/Sell box changed the size: the form follows (never while typing in it)
    prefQty = pq;
    if (!focused(ui.qty) && T.parseQty(st.qty) !== pq) st.qty = ui.qty.value = String(pq);
  }
  const cell = selectedCell(), root = cell && cell.shown ? cell.shown.root : null;
  if (cell !== seen.cell || root !== seen.root) {
    if (seen.cell && cell !== seen.cell) flashPending = true;   // shown once this chart's accounts paint (it may still be loading)
    seen = { cell, root };
  }
  if (root !== null && root !== formRoot) {   // another symbol: its prices and exits start over
    if (formRoot !== null) symbolChanged();
    formRoot = root;
  }
  if (!visible) {   // closed: the chart keeps the order's lines (they still drag, and the ENTRY tag still sends)
    flashPending = false;
    paintPreview(root ? cell : null, root ? compute(cell) : null);
    return;
  }

  // header: the badge (rebuilt only on a symbol change), the root and its name
  if (root !== logoRoot) { logoRoot = root; ui.logo.replaceChildren(...(root ? [window.HBCell.badgeEl(root, 20)] : [])); }
  if (!cell || !root) {
    ui.sym.textContent = cell ? (cell.cfg && cell.cfg.root) || '—' : '—';
    ui.name.textContent = '';
    el.classList.add('off');
    paintPreview(null, null);
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

  // Trading per chart: this chart's accounts ARE its switch, plus its mode (LIVE-arm aware)
  const t = UI().tradeOf(cell), m = UI().effectiveMode(cell);
  el.classList.toggle('off', !t.accounts.length);
  paintAccounts(t, m);
  if (flashPending) { flashPending = false; flashChips(); }   // another chart: its accounts are the ones an order goes to now (fix round 1)


  // the side tiles: which side the order is (no prices on them since 2026-09-28)
  for (const side of ['Sell', 'Buy']) {
    ui.tile[side].b.classList.toggle('on', st.side === side);
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
  for (const k of ['tp', 'p1', 'sl', 'be', 'tr']) {
    const e = ui.ex[k], x = st[k], tr = c[k];
    paintSwitch(e.sw, x.on);
    e.row.hidden = !x.on;
    e.sub.hidden = !x.on;
    e.inp.dataset.pick = x.unit === 'price' ? k : '';   // a price-unit exit also takes a click on the chart
    if (e.sel.value !== x.unit) e.sel.value = x.unit;
    const usdOpt = [...e.sel.options].find((o) => o.value === 'usd');
    if (usdOpt) usdOpt.disabled = k === 'sl' && st.riskOn;
    if (k === 'tp') {   // the box shows the ratio the exits make now (dragged or typed), unless it is being typed in
      ui.rr.hidden = !st.sl.on;
      ui.rrIn.disabled = !c.sl;
      ui.rrIn.placeholder = c.sl ? '' : 'set a stop loss';
      const now = c.sl && c.tp && c.sl.ticks > 0 ? String(Number((c.tp.ticks / c.sl.ticks).toFixed(2))) : '';
      if (!focused(ui.rrIn) && ui.rrIn.value !== now) ui.rrIn.value = now;
    }
    if (k === 'p1') {
      ui.p1Row.hidden = !x.on;
      if (!focused(ui.p1Qty) && ui.p1Qty.value !== x.qty) ui.p1Qty.value = x.qty;
    }
    if (k === 'tr') {
      ui.trAt.hidden = !x.on;
      if (ui.trAfter.value !== x.after) ui.trAfter.value = x.after;
      ui.trAfter.options[1].disabled = !st.be.on;   // "after breakeven" needs a breakeven
    }
    e.sub.textContent = !tr ? (blank(x.value) ? `Enter the ${EXIT_NAMES[k].toLowerCase()} level` : '—')
      : k === 'be' ? `At ${Cat.fmtPrice(tr.price, c.tick)} (${tr.ticks}t) the stop moves to entry + 1 tick`
      : k === 'p1' ? `${c.n1 >= 1 ? c.n1 : '?'} at ${Cat.fmtPrice(tr.price, c.tick)} (${tr.ticks}t${tr.usd == null ? '' : `, ${T.money(tr.usd)}`}); the rest at the take profit`
      : k === 'tr' ? `The stop follows the best price ${tr.ticks}t${tr.usd == null ? '' : ` (${T.money(tr.usd)})`} behind, in ${T.trailStep(tr.ticks)}t steps${x.after === 'be' && st.be.on ? ', once breakeven is reached' : ''}`
      : exitSub(x.unit, tr, c.tick, exitVal(k), k === 'sl' ? c.worst : null) + (k === 'tp' && c.rest != null ? ` · ${c.rest} contracts` : '');
  }

  paintPreview(cell, c);
  paintArmed(root);
  paintColl(ui.look);
  paintSwitch(ui.lookSw, look.on);
  for (const p of ui.lookSel) if (p.sel.value !== String(look[p.key])) p.sel.value = String(look[p.key]);
  if (ui.shade.value !== String(look.shade)) ui.shade.value = String(look.shade);

  ui.runRow.hidden = !st.be.on && !st.tr.on;
  if (ui.runOn.value !== runOn) ui.runOn.value = runOn;

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
  ui.sendText.textContent = T.sendLabel(st.side, qtyText, c.root, st.type);
  paintLive(UI().liveCue(cell, root));   // S1: from the send path's own account set, one-click on or off
  ui.send.classList.toggle('buy', st.side === 'Buy');
  ui.send.classList.toggle('sell', st.side === 'Sell');
  ui.send.classList.toggle('sending', !!T.sendingSide(UI().sending(), 'panel', null));   // fast-paper: pressed until it resolves
  ui.send.disabled = !!reason;
  ui.reason.textContent = m.mode !== 'on' ? '' : reason;   // the mode's reason already shows under the accounts
}
/* The order's preview (the user, 2026-10-18): on the selected chart, an ENTRY line and the TP / SL lines where each
   would sit if the order went now (a Market's follow the last trade), labelled "TP +$500 · 100t", with a green band
   from the entry to the TP and a red one to the SL. Its look (line, thickness, shading, where the labels go) is the panel's "Chart preview".
   It stays when the panel is closed; its "Show on chart" switch hides it. */
let pre = { series: null, lines: {}, zones: null, cell: null, hover: null };
function paintPreview(cell, c) {
  const series = cell && cell.P && look.on ? cell.candles : null;
  if (pre.series !== series) {   // another chart, or this one rebuilt its series: the old lines go with the old series
    try {
      for (const l of Object.values(pre.lines)) pre.series.removePriceLine(l);
      if (pre.zones) pre.series.detachPrimitive(pre.zones);
    } catch (_) { /* its chart is gone */ }
    if (pre.cell) { pre.cell.box.removeEventListener('pointermove', pre.hover); delete pre.cell.el.dataset.opGrab; delete pre.cell.el.dataset.opClick; }
    pre = { series, lines: {}, zones: null, cell: series ? cell : null, hover: null };
    if (series) {
      pre.zones = new window.HBTradeLines.Zones();
      series.attachPrimitive(pre.zones);
      pre.hover = (e) => {   // the hand over the ENTRY tag, ↕ over a line that drags
        const tag = onEntryTag(cell, e), grab = !tag && grabAt(cell, e);
        if (tag) cell.el.dataset.opClick = ''; else delete cell.el.dataset.opClick;
        if (grab) cell.el.dataset.opGrab = ''; else delete cell.el.dataset.opGrab;
      };
      cell.box.addEventListener('pointermove', pre.hover);
    }
  }
  if (!series) return;
  const P = cell.P, want = {};
  if (c.entry != null) {
    const n = c.order.ok ? c.order.qty : c.qty, size = Number.isInteger(n) && n >= 1 ? ` ${n} contract${n === 1 ? '' : 's'}` : '';
    // reward to risk; with a partial, the average reward of all the contracts (TP1's and the TP's)
    const reward = !c.tp ? null : c.p1 && c.rest != null ? (c.n1 * c.p1.ticks + c.rest * c.tp.ticks) / (c.n1 + c.rest) : c.tp.ticks;
    const rr = reward != null && c.sl && c.sl.ticks > 0 ? ` · 1:${(reward / c.sl.ticks).toFixed(1)}` : '';
    want.entry = { price: c.entry, color: st.side === 'Buy' ? P.accent : P.down, title: `ENTRY · ${st.side.toUpperCase()}${size}${rr}` };
  }
  for (const k of ['tp', 'sl']) {
    const t = c[k];
    if (!t) continue;
    const usd = t.usd == null ? null : (k === 'tp' ? '+' : '\u2212') + T.money(t.usd);   // the whole order's $ at that line
    const n = k === 'tp' && c.rest != null ? `${c.rest} ct` : null;   // with a partial, the contracts left for the TP
    want[k] = { price: t.price, color: k === 'tp' ? P.up : P.down, title: [k.toUpperCase() + (usd ? ` ${usd}` : ''), n, `${t.ticks}t`].filter(Boolean).join(' · ') };
  }
  if (c.p1) want.p1 = { price: c.p1.price, color: P.up, title: [`TP1${c.p1.usd == null ? '' : ` +${T.money(c.p1.usd)}`}`, `${c.n1} ct`, `${c.p1.ticks}t`].join(' · ') };
  if (c.be) want.be = { price: c.be.price, color: BE_COLOR, title: `BE · ${c.be.ticks}t → stop to entry+1` };
  for (const a of allArms()) if (a.root === c.root && a.kind !== 'trail') want[`armed:${a.id}`] = { price: a.level, color: BE_COLOR, title: 'BE ARMED · stop to entry+1' };
  for (const k of new Set([...Object.keys(want), ...Object.keys(pre.lines)])) {
    const w = want[k], line = pre.lines[k];
    if (!w) { if (line) { series.removePriceLine(line); delete pre.lines[k]; } continue; }
    // a Market's entry IS the last price: its own axis label would only push above the last price's
    const o = { price: w.price, color: w.color, title: look.labels === 'scale' ? w.title : '', lineWidth: look.width, lineStyle: look.style,
      axisLabelVisible: k !== 'entry' || st.type !== 'Market' };
    if (k.startsWith('armed:')) o.lineStyle = 0;   // a live order's breakeven: solid, whatever the preview's look
    if (line) line.applyOptions(o); else pre.lines[k] = series.createPriceLine(o);
  }
  const tags = look.labels === 'line' ? Object.entries(want).map(([key, w]) => ({ key, price: w.price, text: w.title, color: w.color, close: key === 'entry' })) : [];
  pre.zones.set(c.entry == null ? [] : ['tp', 'sl'].filter((k) => want[k]).map((k) => ({ from: c.entry, to: want[k].price, color: want[k].color })),
    tags, look.shade / 100);
}
/* ---- dragging the preview's lines on the chart (the user, 2026-10-18): the TP, the SL, and a resting order's
   entry. The chart's press goes here first (app.js onPick). Dragging only rewrites the form -- in the exit's own unit
   (ticks stay ticks) -- and never sends anything; an exit stops one tick short of its entry's wrong side.
   A click (no drag) on the ENTRY tag sends the order, as the panel's Send would; its × hides the preview, as the
   panel's "Show on chart" switch does (the user, 2026-10-18). A Market's entry can't move: dragging
   it away places an exit instead ('new') -- toward profit the TP, the other way the SL -- switched on if it was off. ---- */
const GRAB_PX = 6, CLICK_PX = 4;
function paneXY(cell, e) {
  const r = cell.chart.panes()[0].getHTMLElement().getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
function onEntryTag(cell, e) {
  const line = pre.lines.entry, hit = pre.zones && pre.zones.hits.find((h) => h.key === 'entry');
  if (pre.cell !== cell || !line || !hit || !cell.chart || cell.priceAtEvent(e) == null) return false;
  const { x, y } = paneXY(cell, e), ly = pre.series.priceToCoordinate(line.options().price);
  if (ly == null || Math.abs(y - ly) > 9 || x < hit.x || x > hit.x + hit.w) return false;
  return hit.xx != null && x >= hit.xx ? 'x' : 'tag';
}
function grabAt(cell, e) {
  if (pre.cell !== cell || !cell.chart || cell.priceAtEvent(e) == null) return null;
  const { y } = paneXY(cell, e);
  let best = null;
  for (const [k, line] of Object.entries(pre.lines)) {
    if (k.startsWith('armed:')) continue;   // an armed breakeven is the sent order's: cancelled from the panel, not dragged
    const ly = pre.series.priceToCoordinate(line.options().price), d = ly == null ? Infinity : Math.abs(ly - y);
    if (d <= GRAB_PX && (!best || d < best.d)) best = { k, d };
  }
  return best && (best.k === 'entry' && st.type === 'Market' ? 'new' : best.k);
}
function startPreviewDrag(cell, e) {
  const tag = onEntryTag(cell, e);
  if (tag === 'x') { setLook('on', false); return true; }
  let k = tag ? (st.type === 'Market' ? 'new' : 'entry') : grabAt(cell, e);
  if (!k) return false;
  const x0 = e.clientX, y0 = e.clientY;
  let moved = false;
  const move = (ev) => {
    if (!moved && Math.hypot(ev.clientX - x0, ev.clientY - y0) < CLICK_PX) return;
    moved = true;
    const p = cell.priceAtEvent(ev);
    if (p == null) return;
    if (k === 'new') {   // the first move off the entry decides which exit this drag places
      const entry = compute(cell).entry;
      if (entry == null || p === entry) return;
      k = (p > entry) === (st.side === 'Buy') ? 'tp' : 'sl';
      st[k].on = true;
    }
    dragTo(cell, k, p);
  };
  const stop = (ev) => {
    window.removeEventListener('pointermove', move, true);
    window.removeEventListener('pointerup', stop, true);
    window.removeEventListener('pointercancel', stop, true);
    window.removeEventListener('blur', stop);
    if (tag && !moved && ev && ev.type === 'pointerup') sendFromChart(cell);
  };
  window.addEventListener('pointermove', move, true);
  window.addEventListener('pointerup', stop, true);
  window.addEventListener('pointercancel', stop, true);
  window.addEventListener('blur', stop);
  return true;
}
function dragTo(cell, k, price) {
  if (k === 'entry') {
    const f = st.type === 'StopLimit' ? 'limit' : 'price';
    st[f] = fmtIn(price, cell.tick);
    needDefault[f] = false;
    ui.f[f].inp.value = st[f];
  } else {
    const c = compute(cell), from = k === 'sl' ? c.slEntry : c.entry;
    if (from == null) return;
    const above = (k !== 'sl') === (st.side === 'Buy');   // a long's TP / breakeven and a short's SL sit above the entry
    const p = above ? Math.max(price, from + cell.tick) : Math.min(price, from - cell.tick);
    const unit = st[k].unit;
    st[k].unit = 'price';
    st[k].value = ui.ex[k].inp.value = fmtIn(p, cell.tick);
    if (unit !== 'price') setUnit(k, unit);   // back to the typed unit, re-expressed (ticks / $)
  }
  paint();
}
/* ---- auto-breakeven (the owner, 2026-10-18): an order sent with Breakeven on arms {root, side, level, accounts}; once
   its position is open and the last trade reaches the level, the position's stop goes to entry + 1 tick (HBTrade.beStop:
   moved, or added; never loosened) with no confirm -- agreed to when the order was sent. HBTrade.beArmStep decides;
   each position line fires once. Kept in this browser: it works while a Charts page is open. ---- */
const BE_KEY = 'hb.beArms';
let arms = (() => { try { const a = JSON.parse(localStorage.getItem(BE_KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (_) { return []; } })();
function saveArms() { try { localStorage.setItem(BE_KEY, JSON.stringify(arms)); } catch (_) { /* this session only */ } }
function armBe(a) {
  const arm = { ...a, id: T.clientId(), at: Date.now(), seen: false, done: [], sentAt: 0 };
  arms.push(arm);
  saveArms();
  return arm;
}
function dropBe(id) { arms = arms.filter((a) => a.id !== id); saveArms(); paint(); }
function chartFor(root) {
  const C = window.HBCharts, sel = selectedCell();
  if (sel && sel.shown && sel.shown.root === root) return sel;
  return C ? C.cells.find((x) => x && x.shown && x.shown.root === root && x.chart) || null : null;
}
function watchBe() {
  if (!arms.length || UI().busy() || !D().state) return;
  for (const a of arms) {
    const cell = chartFor(a.root);
    if (!cell) continue;   // no chart of that symbol open: it waits
    const groups = T.linesFor(D().state, a.root, UI().editableIds(cell));
    const q = T.freshQuote(D().quotes[a.root], page.clockMs());
    const r = T.beArmStep(a, groups, q ? q.last : null, Date.now());
    if (r.drop) { dropBe(a.id); return; }
    if (r.seen && !a.seen) { a.seen = true; saveArms(); }
    if (!r.fire) continue;
    if (a.kind === 'trail') { if (trail(a, cell, groups, r.fire, q.last)) return; continue; }
    if (Date.now() - a.sentAt < 3000) return;   // the last move is still landing in the desk's state
    for (const g of r.fire.filter((x) => !a.done.includes(x.key))) {
      const s = T.beStop(g, groups, cell.tick);
      a.done.push(g.key);   // each position line once, whatever happens next
      a.sentAt = Date.now();
      saveArms();
      if (s.error) { D().toast('err', `Breakeven: ${s.error}`); continue; }
      if (s.action === 'none') continue;
      D().toast('ok', `Breakeven reached — stop to ${Cat.fmtPrice(s.price, cell.tick)}`);
      if (window.HBSounds) window.HBSounds.event('moved');
      if (s.action === 'move') UI().moveLine(cell, s.line, s.price, a.root, cell.tick, { noConfirm: true });
      else UI().addExit(cell, g, 'sl', s.price, a.root, cell.tick, { noConfirm: true });
      return;   // one send at a time (the in-flight lock); the next pass takes the next line
    }
    if (r.fire.every((x) => a.done.includes(x.key))) { dropBe(a.id); return; }
  }
}
/* One pass of an armed trailing stop: its best price since the fill, then the move trailStop calls for (one send;
   true when it sent). Its own errors are said once; it keeps trailing. */
function trail(a, cell, groups, pos, last) {
  const best = a.best == null ? last : a.side === 'Buy' ? Math.max(a.best, last) : Math.min(a.best, last);
  if (best !== a.best) { a.best = best; saveArms(); }
  if (a.beId && arms.some((x) => x.id === a.beId)) return false;   // "after breakeven": not yet
  if (Date.now() - a.sentAt < 2000) return false;                   // the last move is still landing
  for (const g of pos) {
    const s = T.trailStop(g, groups, a.best, a.dist, last, cell.tick);
    if (s.error) { if (!a.warned) { a.warned = true; saveArms(); D().toast('err', `Trailing stop: ${s.error}`); } continue; }
    if (s.action === 'none') continue;
    a.sentAt = Date.now();
    saveArms();
    if (window.HBSounds) window.HBSounds.event('moved');
    if (s.action === 'move') UI().moveLine(cell, s.line, s.price, a.root, cell.tick, { noConfirm: true });
    else UI().addExit(cell, g, 'sl', s.price, a.root, cell.tick, { noConfirm: true });
    return true;
  }
  return false;
}
/* ---- the server runner's arms (exitrunner.py): armed with the order, read back every 2 s, cancelled here ---- */
let serverArms = [];
async function serverCall(path, body) {
  const r = await fetch(`/api/exitrunner${path}`, body === undefined ? {} : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `the server answered ${r.status}`);
  return data;
}
function serverArm(body) {
  return serverCall('/arm', body).then((a) => { serverArms.push(a); paint(); return a; })
    .catch((e) => { D().toast('err', `Not armed on the server: ${e.message} — the order itself was sent`); return null; });
}
function pollServerArms() {
  serverCall('').then((d) => {
    const next = Array.isArray(d.arms) ? d.arms : [];
    // the server moved a stop since the last look (an arm's sent_at went up): its sound
    if (next.some((a) => { const was = serverArms.find((x) => x.id === a.id); return was && a.sent_at > was.sent_at; })
      && window.HBSounds) window.HBSounds.event('moved');
    serverArms = next;
  }).catch(() => { /* not available (replay): none */ });
}
function cancelArm(a) {
  if (!a.server) { dropBe(a.id); return; }
  serverCall('/cancel', { id: a.id }).then(() => { serverArms = serverArms.filter((x) => x.id !== a.id); paint(); })
    .catch((e) => D().toast('err', `Cancel failed: ${e.message}`));
}
/* Every arm this page knows: its own, and the server's (marked `server`, its fields read as the page's). */
function allArms() {
  return [...arms, ...serverArms.map((a) => ({ ...a, server: true, beId: a.be_id, error: a.error }))];
}
let armedKey = null;
function paintArmed(root) {
  const every = allArms(), mine = every.filter((a) => a.root === root);
  const key = JSON.stringify(mine.map((a) => [a.id, a.level, a.seen, a.best, a.error, every.some((x) => x.id === a.beId)]));
  if (key === armedKey) return;
  armedKey = key;
  const tick = (selectedCell() || {}).tick, px = (v) => Cat.fmtPrice(v, tick);
  for (const k of ['be', 'tr']) {
    const list = mine.filter((a) => (a.kind === 'trail') === (k === 'tr'));
    ui.armed[k].replaceChildren(...list.map((a) => {
      const row = mk('div', 'op-armrow'), x = mk('button', 'op-link', 'Cancel');
      x.type = 'button';
      x.onclick = () => cancelArm(a);
      const wait = !a.seen ? ' (waiting for the fill)' : a.beId && every.some((y) => y.id === a.beId) ? ' (waiting for breakeven)' : '';
      const where = a.server ? ' · server' : '';
      const text = (k === 'be' ? `Armed: ${a.side} at ${px(a.level)}${wait}`
        : `Trailing ${a.dist}t (${a.side})${a.best != null ? ` · best ${px(a.best)}` : ''}${wait}`) + where + (a.error ? ` — ${a.error}` : '');
      row.append(mk('span', '', text), x);
      return row;
    }));
    ui.armed[k].hidden = !list.length;
  }
}
/* S1: the red ring round Send and its LIVE tag while the selected chart's next order reaches a LIVE account (`ids`:
   HBTradeUI.liveCue, the send path's own set); none otherwise. */
function paintLive(ids) {
  const on = ids.length > 0, title = on ? T.liveCueTitle(ids, D().state) : '';
  ui.sendWrap.classList.toggle('live', on);
  ui.sendLive.hidden = !on;
  if (ui.sendWrap.title !== title) ui.sendWrap.title = title;
}
function paintIdle(text) {
  ui.send.disabled = true;
  ui.send.classList.remove('sending');
  ui.sendText.textContent = 'Buy';
  paintLive([]);   // no chart to send from: nothing can reach a LIVE account
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
      if (c.env) e.append(mk('span', 'env' + (c.live ? ' live' : c.paper ? ' paper' : ''), c.env));
      e.title = c.active ? `Orders from this panel go to ${c.id}` : `${c.id} — not trading from this chart right now`;
      return e;
    }) : [mk('span', 'op-none', 'No accounts on this chart')]));
  }
  ui.why.textContent = m.mode === 'on' ? '' : m.reason;
}

/* ---- the price pick: the chart calls this while a price field has focus (app.js onPick) ---- */
function activePick() {
  const a = document.activeElement;
  return visible && a && el.contains(a) && a.dataset && a.dataset.pick && !a.closest('[hidden]') ? a : null;
}
function wantsPick() { return !!activePick(); }
function pickPrice(price) {
  const inp = activePick(), cell = selectedCell();
  if (!inp || !cell || !cell.shown || !Number.isFinite(price)) return;
  const k = inp.dataset.pick, v = fmtIn(T.roundTick(price, cell.tick), cell.tick);
  inp.value = v;
  if (k in EXIT_NAMES) st[k].value = v;
  else { st[k] = v; needDefault[k] = false; }
  paint();
  setTimeout(() => { if (document.contains(inp)) inp.focus(); }, 0);   // keep picking: focus stays on the field
}

/* HBPanelShell calls this whenever the panel opens, closes, or switches dock/float (its content never changes
   size-driven behaviour, only whether it's worth painting at all). */
function setVisible(v) {
  visible = !!v;
  paint();
}
function setRoot() { paint(); }   // the selected chart (or its symbol) changed: the panel re-reads it

function mount(pg, container) {
  page = pg;
  el = container;
  if (!el) return;
  el.classList.add('opanel');
  st.qty = String(Math.min(T.PANEL_QTY_MAX, Math.max(1, D().prefs.qty)));
  build();
  ui.qty.value = st.qty;
  resetExits();
  D().on(() => { paint(); watchBe(); });   // desk / quote / prefs events: patch in place, never rebuild
  UI().onBusyChange(() => paint());
  UI().onTradeChange(() => paint());     // a chart's Trading switch / accounts, a LIVE arm
  setInterval(() => { paint(); watchBe(); }, 1000);
  pollServerArms();
  setInterval(pollServerArms, 2000);   // the server runner's arms: fired, dropped, their best price, their errors   // a quote going stale with no event; the lines follow the last trade even while closed
  paint();
}

window.HBOrderPanel = { mount, setRoot, pickPrice, wantsPick, setVisible, startPreviewDrag, look: () => look };
})();
