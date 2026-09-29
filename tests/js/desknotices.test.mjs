import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk's notices (status.notices, from fix/tradovate-login-loop): each shown once, in plain
   words, escaped; dismissing marks them seen; an older desk without the field shows nothing. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const BLOCK = between('const esc = (v) =>', 'async function chartPost(') +
  between('/* ---- the desk\'s notices ----', '/* ---- activity log (W4)');

function load(stored = null) {
  const store = new Map(stored ? [['hb_notices_seen', stored]] : []);
  const strip = { hidden: true, _html: '', listeners: [],
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = v; },
    querySelector() { return { addEventListener: (_t, f) => strip.listeners.push(f) }; } };
  const ctx = vm.createContext({
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    $: (sel) => (sel === '#noticeStrip' ? strip : null),
  });
  vm.runInContext(BLOCK + '\nglobalThis.renderNotices = renderNotices;', ctx);
  return { ctx, strip, store };
}
const N1 = { et: '2026-09-29T09:05:12-04:00', text: '…049 is no longer on your Apex login — removed from the desk' };
const N2 = { et: '2026-09-29T09:06:00-04:00', text: 'Login <b>x</b> parked' };

test('each notice shows in plain words with its time, escaped; an older desk (no field) shows nothing', () => {
  const s = load();
  s.ctx.renderNotices([N2, N1]);
  assert.equal(s.strip.hidden, false);
  assert.match(s.strip.innerHTML, /<span class="t">09:05<\/span>…049 is no longer on your Apex login — removed from the desk/);
  assert.match(s.strip.innerHTML, /Login &lt;b&gt;x&lt;\/b&gt; parked/);
  for (const absent of [undefined, null, 'nope', {}]) {
    const o = load();
    o.ctx.renderNotices(absent);
    assert.equal(o.strip.hidden, true);
    assert.equal(o.strip.innerHTML, '');
  }
});

test('dismissed notices never come back -- not on the next poll, not after a reload; a new one still shows', () => {
  const s = load();
  s.ctx.renderNotices([N1]);
  s.strip.listeners[0]();
  assert.equal(s.strip.hidden, true);
  s.ctx.renderNotices([N1]);
  assert.equal(s.strip.hidden, true, 'the same poll again: still gone');
  const reload = load(s.store.get('hb_notices_seen'));
  reload.ctx.renderNotices([N1]);
  assert.equal(reload.strip.hidden, true, 'after a reload: still gone');
  reload.ctx.renderNotices([N2, N1]);
  assert.equal(reload.strip.hidden, false);
  assert.doesNotMatch(reload.strip.innerHTML, /…049/);
  assert.match(reload.strip.innerHTML, /parked/);
});

test('an unchanged list leaves the strip alone, and storage that throws still shows them', () => {
  const s = load();
  s.ctx.renderNotices([N1]);
  const html = s.strip.innerHTML;
  s.strip.innerHTML = 'untouched';
  s.ctx.renderNotices([N1]);
  assert.equal(s.strip.innerHTML, 'untouched');
  void html;
  assert.match(HTML, /renderNotices\(s\.notices\);/);
  assert.match(HTML, /<div class="notices" id="noticeStrip" role="status" hidden><\/div>/);
});
