import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* linkwatch.js (D11, 2026-10-27): a toast and an optional repeating alarm when the chart service, the Desk link or the
   prices stop. The state machine alone, under fakes: nothing is sent, nothing is heard. */
function load({ position = false } = {}) {
  const log = [], timers = new Map();
  let n = 0, pos = position;
  const win = {};
  vm.runInNewContext(readFileSync(new URL('../../homebase/static/charts/linkwatch.js', import.meta.url), 'utf8'),
    { window: win, document: { readyState: 'complete', addEventListener() {} } });
  const w = win.HBLinkWatch.make({
    toast: (tone, text) => { const el = { id: ++n }; log.push(['toast', tone, text]); return el; },
    dismiss: (el) => log.push(['dismiss', el.id]),
    sound: (kind) => log.push(['sound', kind]),
    positionOpen: () => pos,
    every: (fn, ms) => { const id = ++n; timers.set(id, { fn, ms }); return id; },
    cancel: (id) => timers.delete(id),
  });
  return { w, log, timers, setPos: (v) => { pos = v; }, tick: () => [...timers.values()].forEach((t) => t.fn()) };
}
const sounds = (log) => log.filter((x) => x[0] === 'sound').map((x) => x[1]);

test('the chart service drops: one toast, an alarm now and again every 15 s, all stopped when it is back', () => {
  const { w, log, timers, tick } = load();
  w.service(false); w.service(false);   // the socket retries every 2 s: still one toast
  assert.equal(log.filter((x) => x[0] === 'toast').length, 1);
  assert.equal(log[0][1], 'warn', 'stays until dismissed');
  assert.deepEqual(sounds(log), ['link']);
  assert.equal([...timers.values()][0].ms, 15000);
  tick();
  assert.deepEqual(sounds(log), ['link', 'link']);
  w.service(true);
  assert.equal(timers.size, 0, 'no alarm once back');
  assert.deepEqual(log.slice(-2).map((x) => x[0]), ['dismiss', 'toast']);
  assert.deepEqual(log.at(-1).slice(1), ['ok', 'The chart service is back.']);
});

test('the Desk link: nothing before it was ever up on this page; after that a drop alarms, stronger with a position open', () => {
  const a = load();
  a.w.desk('connecting to the desk'); a.w.desk('no link to the desk');
  assert.deepEqual(a.log, [], 'a page that never saw the Desk up says nothing');
  a.w.desk(null);
  a.setPos(true);                                    // the position was open when it dropped
  a.w.desk('no link to the desk');
  assert.deepEqual(sounds(a.log), ['linkpos']);
  assert.match(a.log.find((x) => x[0] === 'toast' && x[1] === 'warn')[2], /Desk.*no link to the desk.*position/s);
  a.w.desk(null);
  assert.equal(a.timers.size, 0);
  const b = load();
  b.w.desk(null); b.w.desk('no link to the desk');
  assert.deepEqual(sounds(b.log), ['link'], 'flat: the plain alarm');
  assert.doesNotMatch(b.log.find((x) => x[1] === 'warn')[2], /position/);
});

test('prices: stale markets alarm, an empty list is back; the alarm runs while any one problem is open', () => {
  const { w, log, timers } = load();
  w.feed([]);
  assert.deepEqual(log, [], 'fresh prices say nothing');
  w.feed(['NQ', 'ES']);
  assert.match(log[0][2], /NQ, ES/);
  w.service(false);                                  // a second problem joins the first alarm
  assert.equal(timers.size, 1, 'one alarm, not two');
  w.feed([]);
  assert.equal(timers.size, 1, 'the service is still down');
  w.service(true);
  assert.equal(timers.size, 0);
});

test('a position that opened after the first drop makes the next drop of the same episode strong', () => {
  const { w, log, setPos } = load();
  w.service(false);
  setPos(true);
  w.feed(['NQ']);
  assert.deepEqual(sounds(log), ['link', 'linkpos']);
});

test('the page wires it: app.js tells the client and the watch about the socket and the prices; charts.html loads it after the desk client', () => {
  const rd = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
  const APP = rd('charts/app.js'), HTML = rd('charts.html');
  assert.match(APP, /ws\.onopen = \(\) => \{\n    statusAt = Date\.now\(\);\n    window\.HBDeskClient\?\.socket\(true\); window\.HBLinkWatch\?\.service\?\.\(true\);/);
  assert.match(APP, /ws\.onclose = \(\) => \{\n    window\.HBDeskClient\?\.socket\(false\); window\.HBLinkWatch\?\.service\?\.\(false\);/);
  assert.match(APP, /if \(s\.mode === 'live'\) window\.HBLinkWatch\?\.feed\?\.\(\(f\.stale \|\| \[\]\)\.filter\(\(r\) => cells\.some\(\(c\) => c\.cfg && c\.cfg\.root === r\)\)\);/);
  assert.ok(HTML.indexOf('/charts/deskclient.js') < HTML.indexOf('/charts/linkwatch.js') && HTML.indexOf('/charts/sounds.js') < HTML.indexOf('/charts/linkwatch.js'));
  assert.doesNotMatch(rd('backtest.html'), /linkwatch/);
});

test('it never sends: no fetch, no send, no desk action in the file', () => {
  const src = readFileSync(new URL('../../homebase/static/charts/linkwatch.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src.replace(/\/\*[\s\S]*?\*\//g, ''), /fetch\(|\.send\(|XMLHttp|WebSocket/);
});
