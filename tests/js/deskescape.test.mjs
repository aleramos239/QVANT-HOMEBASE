import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page (homebase/static/index.html, :8850) puts the broker's own words on screen -- an
   account's name, a connection error, a readiness check's detail. Review 2026-09-28: every one is
   escaped, and every inline handler that carries a broker account id passes it as a JS string
   literal (jsArg) -- esc() alone is not enough inside onclick="...", because the browser decodes
   &#39; back to a quote before the JavaScript runs. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const HOSTILE_ID = "x');alert(1);('";
const HOSTILE_TEXT = '<img src=x onerror=alert(1)>';

// run an inline handler the way a browser does: decode the attribute value, then evaluate it
const decode = (v) => v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
function runHandler(attr, names) {
  const calls = [], alerts = [];
  const stubs = names.map((n) => (...a) => calls.push([n, ...a]));
  new Function(...names, 'alert', 'event', decode(attr))(...stubs, (x) => alerts.push(x), {});
  return { calls, alerts };
}

function acctRowCtx(accounts) {
  const ctx = vm.createContext({ ST: { accounts }, usd: (v) => '$' + v });
  vm.runInContext(ESC + between('/* ---- account row (rendered inside strategy cards) ---- */', '/* ---- the book (assignments) ---- */') +
    '\nglobalThis.acctRow = acctRow; globalThis.jsArg = jsArg;', ctx);
  return ctx;
}

test('jsArg: any string becomes one JS string literal that survives the HTML attribute', () => {
  const ctx = acctRowCtx({});
  for (const v of [HOSTILE_ID, 'a"b', 'c\\d', '</div><script>', 'plain-048']) {
    const attr = `f(${ctx.jsArg(v)})`;
    assert.doesNotMatch(attr, /["']/, 'no raw quote reaches the attribute');
    const { calls, alerts } = runHandler(attr, ['f']);
    assert.deepEqual(calls, [['f', v]]);
    assert.deepEqual(alerts, []);
  }
});

test('an account row escapes the broker\'s name and error, and its buttons pass the id as data', () => {
  const ctx = acctRowCtx({ [HOSTILE_ID]: { label: HOSTILE_TEXT, env: 'live', connected: false,
    error: '<b>token</b> expired', account: HOSTILE_ID, balance: 1, realized_pnl: 0 } });
  const html = ctx.acctRow(HOSTILE_ID, { qty: 3, strategy: 'nq930' });
  assert.doesNotMatch(html, /<img|<b>token/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /&lt;b&gt;token&lt;\/b&gt; expired/);
  const handlers = [...html.matchAll(/onclick="([^"]*)"/g)].map((m) => m[1]);
  assert.equal(handlers.length, 3, 'size edit, Calendar, Unassign');
  for (const h of handlers) {
    const { calls, alerts } = runHandler(h, ['editQty', 'openCal', 'removeAsg']);
    assert.equal(calls.length, 1, h);
    assert.ok(calls[0].includes(HOSTILE_ID), `the exact id reaches ${calls[0][0]}`);
    assert.deepEqual(alerts, [], 'nothing else runs');
  }
});

test('System checks escape a check\'s label and detail', () => {
  const els = { checksList: { innerHTML: '' }, bulbBig: {}, checksTitle: {} };
  const ctx = vm.createContext({
    ST: { readiness: { ready: false, checks: [{ level: 'bad', label: HOSTILE_TEXT, detail: '<script>x</script>' }] } },
    $: (sel) => els[sel.replace(/^#/, '')], readinessShown: (r) => r,
    bulbLevel: () => 'bad', CHK_COLOR: { bad: 'var(--neg)', info: 'var(--muted-foreground)' },
  });
  vm.runInContext(ESC + between('function renderChecks()', 'function openChecks()') + '\nglobalThis.renderChecks = renderChecks;', ctx);
  ctx.renderChecks();
  assert.doesNotMatch(els.checksList.innerHTML, /<img|<script>/);
  assert.match(els.checksList.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(els.checksList.innerHTML, /&lt;script&gt;x&lt;\/script&gt;/);
});

test('the Not-ready strip, the + Assign menu, the accounts dialog and the connect wizard escape too', () => {
  assert.match(HTML, /<b>\$\{esc\(c\.label\)\}<\/b> \$\{esc\(String\(c\.detail\)\.slice\(0, 70\)\)\}/);
  assert.match(HTML, /onclick="pickAsg\('\$\{name\}',\$\{jsArg\(id\)\},\$\{c\.qty\}\)">\s*\$\{esc\(accts\[id\]\.label \|\| id\)\}/);
  assert.match(HTML, /onclick="reconnectAcct\(\$\{jsArg\(id\)\}\)"/);
  assert.match(HTML, /onclick="removeAcct\(\$\{jsArg\(id\)\}\)"/);
  assert.match(HTML, /WIZ\.pick=\$\{jsArg\(a\.name\)\};renderAcctList\(\)/);
  assert.match(HTML, /<span class="t">\$\{esc\(a\.name\)\}<\/span>/);
  // (strategy names -- toggleAlgoHidden('${a.name}') -- are the desk's own config, not broker text)
  assert.doesNotMatch(HTML, /'\$\{id\}'|WIZ\.pick='\$\{a\.name\}'|'\$\{a\.account/, 'no broker id is quoted raw into an inline handler');
});

test('the Accounts dialog builds each row with replacer functions: $-patterns in a broker id stay literal', () => {
  const ID = "ev\"il'<b>$`$&$$\\u0022</b>";
  const block = between('function openAccts() {', 'function closeAccts()');
  assert.match(block, /\.replace\('<span class="spacer"><\/span>',\s*\(\) => `/);
  assert.match(block, /\.replace\("<\/div>", \(\) => `/);
  const els = { acctCount: { textContent: '' }, acctList2: { innerHTML: '' } };
  const ctx = vm.createContext({
    ST: { accounts: { [ID]: { label: 'L', env: 'live', connected: true, account: ID, balance: 1, realized_pnl: 0 } },
          book: { nq930: [{ account: ID, qty: 3 }] } },
    $: (sel) => els[sel.replace(/^#/, '')], usd: (v) => '$' + v,
    renderPaper() {}, loadPaper() {}, showOverlay() {},
  });
  vm.runInContext(ESC + between('/* ---- account row (rendered inside strategy cards) ---- */', '/* ---- the book (assignments) ---- */') +
    block + '\nglobalThis.openAccts = openAccts;', ctx);
  ctx.openAccts();
  const html = els.acctList2.innerHTML;
  assert.equal((html.match(/<div class="acct"/g) || []).length, 1, 'one row, not spliced into itself');
  const handlers = [...html.matchAll(/onclick="([^"]*)"/g)].map((m) => m[1]).filter((h) => /reconnectAcct|removeAcct/.test(h));
  assert.equal(handlers.length, 2);
  for (const h of handlers) {
    const { calls } = runHandler(h, ['reconnectAcct', 'removeAcct']);
    assert.deepEqual(calls[0].slice(1), [ID], 'the exact id, $-patterns and all');
  }
});
