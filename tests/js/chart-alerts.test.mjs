import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/* 2026-10-27 alerts and sounds: the price alert follows Settings > Sounds; the red-folder warning, the bot-fill, headline
   and burst sounds are Off until chosen; one click mutes; the right-click menu sets an alert. Page code lifted and run on stand-ins. */
const rd = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
const APP = rd('charts/app.js');
const lift = (src, name) => {
  const m = new RegExp(`^(async )?function ${name}\\(`, 'm').exec(src);
  assert.ok(m, `defines ${name}`);
  return src.slice(m.index, src.indexOf('\n}\n', m.index) + 2);
};
const build = (name, params, scope) => new Function(...params, `${lift(APP, name)}\nreturn ${name};`)(...scope);

test('a price alert beeps through HBSounds (so Settings > Sounds rules it), never on a context of its own', () => {
  const heard = [], said = [], patched = [];
  class Boom { constructor() { throw new Error('a private AudioContext'); } }
  const win = { HBSounds: { event: (k) => heard.push(k) }, HBDeskClient: { toast: (t, x) => said.push([t, x]) }, AudioContext: Boom, webkitAudioContext: Boom };
  const fn = build('alertWentOff', ['window', 'patchDrawing', 'C', 'sbNote', 'Notification'],
    [win, (...a) => { patched.push(a); return true; }, { rootName: (r) => r }, (t) => said.push(['bar', t]), undefined]);
  fn({ cfg: { root: 'NQ' } }, { id: 'a', alert: { dir: 'up' }, points: [{ p: 100 }] }, 101);
  assert.deepEqual(heard, ['priceAlert']);
  assert.equal(patched.length, 1);
  assert.match(said[0][1], /NQ crossed 100/);
  win.HBSounds = undefined;   // a page with no sounds file (the Lab): still just the bar and the toast
  fn({ cfg: { root: 'NQ' } }, { id: 'a', alert: { dir: 'up' }, points: [{ p: 100 }] }, 101);
  assert.equal(said.length, 4);
});

test('the red-folder warning: a toast and a sound, only once its sound is not Off, never in a replay', () => {
  const toasts = [], heard = [], T = Date.now() + 4 * 60000;
  const cal = [{ t_ms: T, title: 'CPI m/m', country: 'USD', impact: 'High' }];
  const E = require('../../homebase/static/charts/events.js');
  let events = { redFolder: 'off' }, replay = null;
  const make = () => build('warnRedFolder', ['window', 'replayClock', 'calendar', 'redSaid'],
    [{ HBEvents: E, HBSounds: { get: () => ({ events }), event: (k) => heard.push(k) }, HBDeskClient: { toast: (t, x) => toasts.push([t, x]) } },
      replay, cal, new Set()]);
  make()();
  assert.deepEqual([toasts, heard], [[], []], 'Off by default');
  events = { redFolder: 'chime' };
  replay = { etMs: 1 };
  make()();
  assert.deepEqual([toasts, heard], [[], []], 'a replay is not the real clock');
  replay = null;
  const go = make();
  go(); go();
  assert.deepEqual(toasts, [['warn', 'Red folder in 4 min: CPI m/m']], 'once');
  assert.deepEqual(heard, ['redFolder']);
});

test('the right-click menu offers an alert at the price under the pointer, on a chart with drawings and a price', () => {
  const made = [];
  const fn = build('alertMenuItems', ['fmtPrice'], [(p, tick) => p.toFixed(2)]);
  const ctx = { price: 30878.25, tick: 0.25, cell: { dc: { addAlert: (p) => made.push(p) } } };
  const [it] = fn(ctx);
  assert.equal(it.text, 'Alert at 30878.25');
  it.run(ctx);
  assert.deepEqual(made, [30878.25]);
  assert.deepEqual(fn({ ...ctx, price: null }), []);
  assert.deepEqual(fn({ ...ctx, price: NaN }), []);
  assert.deepEqual(fn({ ...ctx, cell: {} }), []);
});

test('the mute button flips the same switch, shows it, and follows the settings dialog', () => {
  const attrs = {}, btn = { setAttribute: (k, v) => { attrs[k] = v; }, onclick: null, title: '' };
  let cfg = { on: false }, sub = null;
  const S = { get: () => cfg, set: (p) => { cfg = { ...cfg, ...p }; sub(cfg); }, onChange: (fn) => { sub = fn; } };
  build('wireSoundButton', ['$', 'window'], [() => btn, { HBSounds: S }])();
  assert.equal(attrs['aria-pressed'], 'false');
  btn.onclick();
  assert.deepEqual([cfg.on, attrs['aria-pressed']], [true, 'true']);
  S.set({ on: false });   // the settings dialog's own switch
  assert.equal(attrs['aria-pressed'], 'false');
  build('wireSoundButton', ['$', 'window'], [() => null, { HBSounds: S }])();   // the Lab has no button
  build('wireSoundButton', ['$', 'window'], [() => btn, {}])();                  // and no sounds file
});

function loadNews(sounds, filter) {
  const heard = [];
  const win = { HBNews: require('../../homebase/static/charts/news.js'), HBTrade: {}, HBSounds: { event: (k) => heard.push(k) },
    HBPanel: { addTab() {} } };
  const el = () => ({ className: '', textContent: '', hidden: false, dataset: {}, classList: { add() {} }, appendChild() {}, remove() {}, addEventListener() {} });
  const ctx = { window: win, document: { createElement: el }, requestAnimationFrame: (f) => f(), fetch: async () => ({ ok: false }),
    setTimeout: () => 0, Date, console };
  vm.runInNewContext(rd('charts/newsui.js'), ctx);
  win.HBNewsUI.mount({ cur: () => ({ shown: null, cfg: { root: 'NQ' } }), events: () => [] });
  return { U: win.HBNewsUI, heard };
}
const item = (id, seen, tags = []) => ({ type: 'news', id, t_ms: seen, seen_ms: seen, title: 't', source: 's', tags });

test('a new headline and a burst on the selected symbol sound; an old one, another symbol or a burst update do not', () => {
  const { U, heard } = loadNews();
  U.onMessage(item('a', Date.now()));
  U.onMessage(item('b', Date.now() - 60000));
  assert.deepEqual(heard, ['headline'], 'only one just seen');
  U.onMessage({ type: 'burst', root: 'NQ', t_ms: Date.now() });
  U.onMessage({ type: 'burst', root: 'ES', t_ms: Date.now() });
  U.onMessage({ type: 'burst_update', root: 'NQ', t_ms: Date.now() });
  assert.deepEqual(heard, ['headline', 'burst']);
});

test('the headline sound follows the News tab filter', () => {
  const { U, heard } = loadNews();
  U.toggleFilter('tags', 'red folder');
  U.onMessage(item('a', Date.now(), ['other']));
  U.onMessage(item('b', Date.now(), ['red folder']));
  assert.deepEqual(heard, ['headline']);
});

test('the Price alert tool tip says it only goes off while the page is open', () => {
  for (const f of ['charts.html', 'backtest.html']) {
    assert.match(rd(f), /data-tool="alert" title="Price alert \(goes off only while this page is open\)"/);
  }
});

test('the toolbar has the sound button (Charts), in the Apple skin\'s panels group too', () => {
  assert.match(rd('charts.html'), /id="tbSound"[^>]*aria-pressed="false"/);
  assert.match(rd('apple/charts.js'), /'tbOrder', 'tbDom', 'tbTape', 'tbSound'/);
});

test('an alert drawing\'s settings dialog does not open while the chart replays (it would save the replay\'s price or direction)', () => {
  const said = [], toasts = [];
  let opened = 0, orig = { id: 'a', type: 'hline', alert: { dir: 'up', fired: false }, points: [{ p: 100 }] };
  const fn = build('drawingSettingsDialog', ['drawings', 'sbNote', 'window', 'openDialog'],
    [{ list: () => [orig] }, (t) => said.push(t), { HBDeskClient: { toast: (k, t) => toasts.push(t) } }, () => { opened++; throw new Error('opened'); }]);
  fn({ cfg: { root: 'NQ' }, replay: {} }, { id: 'a' });
  assert.equal(opened, 0);
  assert.match(said[0], /cannot be set or moved while the chart replays/);
  assert.equal(toasts.length, 1);
  // live chart: it goes on to open; a plain line (no alert) in a replay is not an alert
  assert.throws(() => fn({ cfg: { root: 'NQ' } }, { id: 'a' }));
  orig = { ...orig, alert: undefined };
  assert.throws(() => fn({ cfg: { root: 'NQ' }, replay: {} }, { id: 'a' }));
});
