import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

/* 2026-09-28 three-tabs plan: the Backtest page must load no trading module and expose no trading
   global. Same technique replay.test.mjs's own "isolation" test uses (source text, not a live DOM --
   testerui.js/replayui.js assume a real document and can't be require()'d headless): read the
   published page and the shared-shell files, and grep for what must be absent / must be guarded. */

const html = readFileSync(new URL('../../homebase/static/backtest.html', import.meta.url), 'utf8');
const src = (f) => readFileSync(new URL(`../../homebase/static/charts/${f}`, import.meta.url), 'utf8');

const BANNED_MODULES = ['deskclient.js', 'paperclient.js', 'tradeui.js', 'tradelines.js', 'orderpanel.js',
  'dom.js', 'domui.js', 'panelshell.js', 'fillquality.js', 'newsui.js', 'news.js', 'l2layer.js', 'liquidity.js',
  'trade.js'];   // trade.js itself -- tradepure.js (its pure half) is fine and IS loaded

test('backtest.html loads none of the trading/desk modules', () => {
  for (const f of BANNED_MODULES) {
    // word-boundary match on the filename so "trade.js" doesn't false-positive on "tradepure.js" /
    // "tradelines.js" (both listed separately, both present/absent on their own terms)
    const re = new RegExp(`/${f.replace('.', '\\.')}(\\?|")`);
    assert.equal(re.test(html), false, `backtest.html loads ${f}`);
  }
});

test('backtest.html carries no Order/DOM toolbar buttons (nothing to wire without orderpanel.js/domui.js)', () => {
  assert.equal(html.includes('id="tbOrder"'), false);
  assert.equal(html.includes('id="tbDom"'), false);
});

test('backtest.html DOES load the Backtest-specific modules: tradepure, panel, tester (+ui/+layer), replay (+ui)', () => {
  for (const f of ['tradepure.js', 'panel.js', 'tester.js', 'testerui.js', 'testerlayer.js', 'replay.js', 'replayui.js']) {
    assert.ok(html.includes(`/${f}`), `backtest.html is missing ${f}`);
  }
});

test('window.HB_PAGE is set to backtest before any other script', () => {
  const flagAt = html.indexOf("window.HB_PAGE = 'backtest'");
  const firstScriptSrcAt = html.indexOf('<script src=');
  assert.ok(flagAt >= 0 && flagAt < firstScriptSrcAt);
});

/* ---- the shared chart shell (app.js/cell.js/replayui.js/settings-dialog.js) guards every call into
   a module that might not be loaded -- one file serves both charts.html and backtest.html. Each of
   these was a real, individually-verified call site (2026-09-28 three-tabs plan, Task 2); this test
   is the standing guarantee that a later edit can't silently drop one of the guards. */
test('app.js guards every call into HBTrade/HBTradeUI/HBDeskClient/HBPaperClient/HBOrderPanel/HBDomUI/HBTradeLines/HBPanelShell/HBReplayUI/HBTesterUI/HBTesterLayer/HBL2Layer/HBLiquidity/HBNewsUI', () => {
  const app = src('app.js');
  const mustContain = [
    'window.HBReplayUI?.guardSymbolChange', 'window.HBTradeUI?.setCellTrade(cell, off.trade)',
    'window.HBDeskClient?.toast(\'err\', T?.SYMBOL_CHANGE_ACCOUNTS_CLEARED)',
    'window.HBReplayUI?.cellDestroyed(c)', 'window.HBTradeUI?.gridRebuilt(cells)',
    'window.HBOrderPanel?.setRoot(panelRoot())', 'window.HBTradeUI?.paintDeskStatus()',
    'window.HBTradeUI?.setCellAlgo(cell, was.algo', 'window.HBDeskClient?.onMessage(m)',
    'window.HBPaperClient?.onMessage(m)', 'window.HBPaperClient?.onBook(m)', 'window.HBDeskClient?.bookChanged()',
    'window.HBDomUI?.onDepth(m)', 'window.HBL2Layer?.onDepth(m)', 'window.HBLiquidity?.onDepth(m)',
    'window.HBNewsUI?.onMessage(m)', 'window.HBTesterUI?.show(m)', 'window.HBReplayUI?.onBarUpdate(c, m)',
    'window.HBReplayUI?.onState(c, m)', 'window.HBReplayUI?.onError(c, m)', 'window.HBReplayUI?.onReconnect(cells)',
    'window.HBDomUI?.onDisconnect()', 'window.HBL2Layer?.onDisconnect()', 'window.HBLiquidity?.onDisconnect()',
    'if (window.HBTradeLines) page.overlays.push', 'if (window.HBReplayUI) page.overlays.push',
    'if (window.HBTesterLayer) page.overlays.push', 'if (window.HBNewsUI) page.overlays.push',
    'if (window.HBTesterUI) window.HBTesterUI.mount(page)', 'if (window.HBNewsUI) window.HBNewsUI.mount(page)',
    'if (window.HBTradeUI) window.HBTradeUI.mount(page)',
    'if (window.HBOrderPanel && window.HBDomUI && window.HBPanelShell)', 'if (window.HBReplayUI) window.HBReplayUI.mount(page)',
    'if (!window.HBTradeUI) return;', 'if (!window.HBDeskClient || !T) return;', 'const tradeCapabilities = window.HBTradeUI ?',
  ];
  for (const needle of mustContain) assert.ok(app.includes(needle), `app.js is missing guard: ${needle}`);
});

test('cell.js guards its one call into HBTrade.symbolChangeTrade', () => {
  assert.ok(src('cell.js').includes('window.HBTrade ? window.HBTrade.symbolChangeTrade(this.cfg, patch) : null'));
});

test('replayui.js falls back to HBTradePure and guards its two HBTradeUI calls', () => {
  const r = src('replayui.js');
  assert.equal((r.match(/window\.HBTrade \|\| window\.HBTradePure/g) || []).length >= 3, true,
    'readPrefs / placePractice / registerPracticeMenu / refreshPractice should all fall back to HBTradePure');
  assert.ok(r.includes('window.HBTradeUI?.replayEnded(cell, involuntary)'));
  assert.ok(r.includes("window.HBTradeUI?.replayEnded(cell, true)"));
  assert.ok(r.includes('window.HBTradeUI?.replayDestroyed(cell)'));
});

test('tester.js / testerui.js fall back to HBTradePure for money/usd when HBTrade is not loaded', () => {
  assert.ok(src('tester.js').includes("need('HBTrade', './trade.js') || need('HBTradePure', './tradepure.js')"));
  assert.ok(src('testerui.js').includes('window.HBTrade || window.HBTradePure'));
});

test('settings-dialog.js hides the Trading tab when the host offers no trade capabilities', () => {
  const sd = src('settings-dialog.js');
  assert.ok(sd.includes("host.accountRows ? TABS : TABS.filter((t) => t.id !== 'trading')"));
});

test('panel.js gives the Backtest tab its own bottom-panel storage key and default-open state', () => {
  const p = src('panel.js');
  assert.ok(p.includes("IS_BACKTEST ? 'hb_panel_backtest' : 'hb_panel'"));
  assert.ok(p.includes('isOpen = saved ? saved.open === true : IS_BACKTEST'));
});

/* Regression (caught only by the headless-browser check, not by node --test: panel.js's own
   module-top-level `Object.keys(T.BOT_NAMES)` and its five unconditional addTab() calls for
   Positions/Orders/Fills/Accounts/Fill quality threw / registered on the Backtest tab, since T
   (HBTrade) is never loaded there -- the crash aborted panel.js before it ever set window.HBPanel,
   which then made testerui.js's own mount() throw too ("Cannot read properties of undefined
   (reading 'addTab')"). Node's require()-based tests never caught this because trade.js's need()
   helper falls back to a real require() in Node, masking exactly the case a <script> tag can't. */
test('panel.js never dereferences T (HBTrade) unconditionally, and its five built-in trading tabs are gated on it', () => {
  const p = src('panel.js');
  assert.ok(p.includes('const BOT_KEYS = T ? Object.keys(T.BOT_NAMES) : [];'));
  assert.ok(p.includes("if (T) {\n  addTab({ id: 'positions'"));
});
