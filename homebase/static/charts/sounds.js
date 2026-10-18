/* Homebase Charts — HBSounds: trade sounds (the owner, 2026-10-18), optional and off until switched on in Settings >
   Sounds. Each event has its own sound (or Off) and one volume for all: an entry filled, a take profit filled, a stop
   filled, and the breakeven / trailing stop moving the stop. The sounds are made here with Web Audio (no files);
   the choice is kept in this browser (localStorage), every chart.

   Fills: every fill the desk or the PAPER book reports on a listed account, not a bot's (HBDeskClient.onAnyFill,
   HBPaperClient.onAnyFill). What it was is read from the order that filled, as last seen: a stop on the side that
   closes the position is the stop, a limit there the take profit, anything else an entry (a PAPER leg says its own
   role). Browser only. */
(() => {
'use strict';
const KEY = 'hb.sounds';
const SOUNDS = [['chime', 'Chime'], ['ding', 'Ding'], ['pop', 'Pop'], ['click', 'Click'], ['bell', 'Bell'], ['alert', 'Alert']];
const EVENTS = [['entry', 'Entry filled'], ['tp', 'Take profit filled'], ['sl', 'Stop filled'], ['moved', 'Breakeven / trailing moved the stop']];
const DEFAULTS = { on: false, volume: 0.6, events: { entry: 'pop', tp: 'chime', sl: 'alert', moved: 'click' } };

/* note lists: [frequency Hz, start s, length s, wave, end frequency?] */
const NOTES = {
  chime: [[880, 0, 0.22, 'sine'], [1318.5, 0.11, 0.35, 'sine']],
  ding: [[1568, 0, 0.5, 'sine']],
  pop: [[520, 0, 0.09, 'sine', 240]],
  click: [[2200, 0, 0.025, 'square']],
  bell: [[1046.5, 0, 0.7, 'triangle'], [2093, 0, 0.35, 'sine']],
  alert: [[740, 0, 0.11, 'triangle'], [740, 0.16, 0.11, 'triangle'], [554, 0.32, 0.2, 'triangle']],
};

let cfg = load();
function load() {
  try {
    const o = JSON.parse(localStorage.getItem(KEY) || 'null') || {};
    return { ...DEFAULTS, ...o, events: { ...DEFAULTS.events, ...(o.events || {}) } };
  } catch (_) { return { ...DEFAULTS, events: { ...DEFAULTS.events } }; }
}
function get() { return { ...cfg, events: { ...cfg.events } }; }
function set(patch) {
  cfg = { ...cfg, ...patch, events: { ...cfg.events, ...(patch.events || {}) } };
  cfg.volume = Math.min(1, Math.max(0, Number(cfg.volume) || 0));
  try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (_) { /* this session only */ }
}

let ctx = null;
function audio() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}
// a browser only lets a page make sound after the viewer has pressed something on it
document.addEventListener('pointerdown', () => audio(), { once: true, capture: true });

/* One sound, now, at `volume` (0..1). */
function play(name, volume = cfg.volume) {
  const notes = NOTES[name], a = notes && volume > 0 ? audio() : null;
  if (!a) return;
  const t0 = a.currentTime + 0.01;
  for (const [f, at, len, wave, f2] of notes) {
    const o = a.createOscillator(), g = a.createGain();
    o.type = wave;
    o.frequency.setValueAtTime(f, t0 + at);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, t0 + at + len);
    g.gain.setValueAtTime(0.0001, t0 + at);
    g.gain.exponentialRampToValueAtTime(0.35 * volume, t0 + at + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + at + len);
    o.connect(g).connect(a.destination);
    o.start(t0 + at);
    o.stop(t0 + at + len + 0.02);
  }
}
/* An event's sound, when sounds are on and that event has one. */
function event(kind) {
  const name = cfg.on ? cfg.events[kind] : null;
  if (name && name !== 'off') window.HBSounds.play(name);
}

/* ---- fills: what each order is, from the latest account views (desk + PAPER: HBDeskClient.state) ---- */
const kinds = new Map();   // "<account>:<order id>" -> 'entry' | 'tp' | 'sl'
const KINDS_MAX = 2000;
function noteOrders() {
  const T = window.HBTrade, st = window.HBDeskClient && window.HBDeskClient.state;
  if (!T || !st) return;
  for (const a of st.accounts || []) {
    for (const o of a.orders || []) {
      const p = (a.positions || []).find((x) => x.symbol === o.symbol && x.net);
      const closes = p && ((p.net > 0 && o.side === 'Sell') || (p.net < 0 && o.side === 'Buy'));
      const k = o.role === 'sl' || o.role === 'tp' ? o.role
        : closes && /stop/i.test(o.type) ? 'sl' : closes && /limit/i.test(o.type) ? 'tp' : 'entry';
      kinds.set(`${a.id}:${o.order_id}`, k);
    }
  }
  while (kinds.size > KINDS_MAX) kinds.delete(kinds.keys().next().value);
}
function onFill(account, fill) {
  if (!fill || fill.owner) return;   // a bot's own fills are the bot's business
  event(kinds.get(`${account}:${fill.order_id}`) || 'entry');
}

function mount() {
  const D = window.HBDeskClient, Pc = window.HBPaperClient;
  if (D) {
    D.on(() => noteOrders());
    if (D.onAnyFill) D.onAnyFill((d) => onFill(d.account, d.fill));
  }
  if (Pc && Pc.onAnyFill) Pc.onAnyFill((f) => onFill(f.account, f));
  noteOrders();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();

window.HBSounds = { SOUNDS, EVENTS, get, set, play, event };
})();
