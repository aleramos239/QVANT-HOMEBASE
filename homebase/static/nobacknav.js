/* Homebase — no Backspace "go back". WebKit (the desktop viewer's WKWebView) still treats Backspace pressed
   outside a text field as history.back(): on the chart page that jumped to the desk (the Charts link opens in
   the same view), on the desk back to the charts. This guard cancels the keydown's default action for
   Backspace / Delete whenever the key is not aimed at something that edits text. It runs at the window's
   bubble phase, after every page handler, and never stops propagation -- so the chart's own Delete (remove a
   selected drawing) and every text field keep working exactly as before. Loaded by index.html and
   charts.html. */
(function () {
  'use strict';
  const NOT_TEXT = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file',
    'image', 'hidden']);
  /* True when Backspace / Delete would edit text in `el` (so its default action must stay). */
  function editsText(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    if (tag === 'TEXTAREA') return !el.readOnly && !el.disabled;
    if (tag === 'INPUT') return !NOT_TEXT.has(String(el.type || 'text').toLowerCase()) && !el.readOnly && !el.disabled;
    return false;
  }
  /* The guard: true when it cancelled the key (for tests). */
  function guard(e, doc) {
    if (!e || (e.key !== 'Backspace' && e.key !== 'Delete')) return false;
    const active = doc && doc.activeElement;
    if (editsText(e.target) || editsText(active)) return false;
    e.preventDefault();
    return true;
  }
  const api = { editsText, guard };
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    window.addEventListener('keydown', (e) => guard(e, document));
    window.HBNoBackNav = api;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
