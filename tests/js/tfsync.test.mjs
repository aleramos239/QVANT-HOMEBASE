import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* "Same interval on all charts" (2026-10-09, an option like the shared crosshair): the page's own three functions, lifted from
   app.js and run against stand-in charts. */
const SRC = readFileSync(new URL('../../homebase/static/charts/app.js', import.meta.url), 'utf8');
const lift = (name) => {
  const m = new RegExp(`^function ${name}\\(`, 'm').exec(SRC);
  assert.ok(m, `app.js defines ${name}`);
  return SRC.slice(m.index, SRC.indexOf('\n}\n', m.index) + 2);
};
function page(specs, { on = false, replay = [] } = {}) {
  const store = {};
  const cells = specs.map((spec, i) => ({ cfg: { spec }, replay: replay.includes(i) ? {} : null, asked: [],
    update(p) { this.asked.push(p.spec); if (!this.replay) this.cfg.spec = p.spec; } }));   // a replaying chart asks first, and changes nothing by itself
  const ctx = vm.createContext({ cells, localStorage: { setItem: (k, v) => { store[k] = v; } } });
  vm.runInContext(`let tfSync = ${on}, selected = 0; const TF_KEY = 'hb_tf_sync'; const cur = () => cells[selected];
    ${lift('followSpec')}
    ${lift('setSpec')}
    ${lift('setTfSync')}
    globalThis.api = { setSpec, setTfSync, select(i) { selected = i; }, get on() { return tfSync; } };`, ctx);
  return { cells, api: ctx.api, store };
}
const specs = (p) => p.cells.map((c) => c.cfg.spec);

test('off (the default): an interval change stays on its own chart', () => {
  const p = page(['time:60', 'time:300', 'time:900']);
  p.api.setSpec(p.cells[0], 'time:3600');
  assert.deepEqual(specs(p), ['time:3600', 'time:300', 'time:900']);
  assert.match(SRC, /let tfSync = \(\(\) => \{ try \{ return localStorage\.getItem\(TF_KEY\) === 'on'; \}/, 'off unless it was switched on');
});

test('on: every other chart takes the interval, and one already on it is not asked again', () => {
  const p = page(['time:60', 'time:300', 'time:900'], { on: true });
  p.api.setSpec(p.cells[1], 'time:900');
  assert.deepEqual(specs(p), ['time:900', 'time:900', 'time:900']);
  assert.deepEqual(p.cells[2].asked, [], 'the chart already on 15m was left alone');
  p.api.setSpec(p.cells[1], 'time:900');
  assert.deepEqual(p.cells.map((c) => c.asked.length), [1, 1, 0], 'the same interval again changes nothing');
});

test('on: a chart in Bar Replay is never changed by another chart, and its own change does not spread', () => {
  const p = page(['time:60', 'time:300', 'time:900'], { on: true, replay: [2] });
  p.api.setSpec(p.cells[0], 'time:3600');
  assert.deepEqual(specs(p), ['time:3600', 'time:3600', 'time:900'], 'the replaying chart keeps its interval');
  assert.deepEqual(p.cells[2].asked, []);
  p.api.setSpec(p.cells[2], 'time:60');                 // on the replaying chart itself: it asks "Leave replay?" (update), the others wait
  assert.deepEqual(p.cells[2].asked, ['time:60']);
  assert.deepEqual(specs(p).slice(0, 2), ['time:3600', 'time:3600']);
});

test('switching it on lines the others up with the selected chart, and the choice is remembered', () => {
  const p = page(['time:60', 'time:300', 'time:900']);
  p.api.select(1);
  p.api.setTfSync(true);
  assert.deepEqual(specs(p), ['time:300', 'time:300', 'time:300']);
  assert.equal(p.store.hb_tf_sync, 'on');
  p.api.setTfSync(false);
  assert.equal(p.store.hb_tf_sync, 'off');
  p.api.setSpec(p.cells[0], 'time:60');
  assert.deepEqual(specs(p), ['time:60', 'time:300', 'time:300'], 'off again: only its own chart');
});

test('the page changes an interval through setSpec only, and a custom one spreads once the server took it', () => {
  const direct = [...SRC.matchAll(/\.update\(\{ spec: s \}\)/g)].length;
  assert.equal(direct, 3, 'followSpec, setSpec, and the custom interval (which waits for the server)');
  assert.match(SRC, /b\.onclick = \(\) => setSpec\(cur\(\), s\);/, 'the toolbar buttons');
  assert.match(SRC, /closeMenu\(\); setSpec\(c, s\); \}, s === spec\);/, 'the interval menu');
  assert.match(SRC, /closeHotkeyBox\(\);\n    setSpec\(cell, s\);/, 'the typed interval');
  assert.match(SRC, /const s = customWait\.spec;\n    closeMenu\(\);\n    followSpec\(cell, s\);/, 'a custom interval: accepted first, then the others');
  assert.match(SRC, /option\('Same interval on all charts', tfSync, setTfSync\);/, 'the option sits in the layout menu beside the shared crosshair');
});
