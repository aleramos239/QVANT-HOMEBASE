/* Homebase Next — the Lab, as a macOS three-pane window: strategies · code and chart · backtest, under one toolbar.

   PRESENTATION ONLY. The page's own script (charts/lab.js) still renders every row and owns every handler. This file:
     - puts the page's own top bar AROUND the toolbar's main zone (it takes no box: display: contents), so the bar's
       delegated handlers (Run, More, the name field of an unsaved script) still see the controls that moved up;
     - MOVES the page's own controls into the toolbar: the page switcher (centre), the name field of an unsaved
       script (where the title is), the Code / Chart panel toggles (one platter), and the Run and More buttons the
       page repaints (the same nodes, dressed again after each repaint);
     - gives the page's library the sidebar pane and its backtest panel the inspector pane. There is ONE state, the
       page's: the window's sidebar / inspector buttons click the page's own Strategies / Results toggles, and a
       change the page makes itself is mirrored back to the window;
     - re-houses the trade stepper (the same node, with its listener) at the foot of the inspector;
     - writes the window title from what the page prints as the document's name and state, and repeats the page's
       own validation message at the top of the inspector while the script has a problem.
   It calls no endpoint, changes no handler and never stops an event. If anything here throws, the page is shown as
   the base page: the finally block always reveals it.                                                               */
(function () {
  'use strict';
  const A = window.HBApple;
  if (!A || document.documentElement.dataset.hbLab) return;
  document.documentElement.dataset.hbLab = '1';
  const D = document, H = D.documentElement, $ = (s, r) => (r || D).querySelector(s);
  const { el, sf } = A;

  try {
    const lab = $('#lab'), bar = $('.lab-bar'), lib = $('#labLib'), res = $('#labRes');
    if (!lab || !bar || !lib || !res) throw new Error('lab markup not found');

    /* ---- toolbar: the page's own controls, moved ---- */
    const tb = A.toolbar();
    const main = tb.left.parentNode;
    main.before(bar);                     // the page's bar now sits in the toolbar...
    bar.append(main);                     // ...around the main zone: a click on Run still bubbles through it
    for (const n of bar.querySelectorAll(':scope > .hb-bar-l, :scope > .hb-bar-r')) n.hidden = true;

    const sw = $('#pgSw');
    if (sw) { sw.classList.add('hb-seg'); tb.center.append(sw); }
    const doc = $('#labDoc');
    if (doc) tb.left.append(doc);         // only shown for an unsaved script: its name is a field

    // Code / Chart: the page's own toggles on one platter. Strategies / Results stay in the group (the page paints
    // their pressed state by that container) but are not shown: the window's own two buttons stand in for them.
    const panels = $('#labPanels');
    const SYMBOL = { code: 'code-tb', chart: 'candles-tb' };
    if (panels) {
      panels.classList.add('hb-platter');
      for (const b of panels.querySelectorAll('[data-panel]')) {
        const name = SYMBOL[b.dataset.panel];
        if (name) { b.classList.add('hb-tbtn'); b.replaceChildren(sf(name)); } else b.classList.add('hb-proxy');
      }
      tb.right.append(panels);
    }
    // Run and More: the page rewrites these two buttons on every repaint of its header
    const acts = $('#labActs');
    function dress() {
      const run = $('[data-act="run"]', acts), more = $('[data-act="more"]', acts);
      if (run && !run.classList.contains('hb-tbtn')) {
        run.classList.add('hb-tbtn', 'hb-text', 'hb-prominent');
        const svg = $('svg', run);
        if (svg) svg.replaceWith(sf('play-tb'));
      }
      if (more && !more.classList.contains('hb-tbtn')) { more.classList.add('hb-tbtn', 'hb-solo'); more.replaceChildren(sf('ellipsis-tb')); }
    }
    if (acts) {
      tb.right.append(acts);
      new MutationObserver(dress).observe(acts, { childList: true });
      dress();
    }

    /* ---- panes ---- */
    lib.classList.add('hb-side');
    res.classList.add('hb-insp');
    // what the page says is wrong with the script, also where the backtest would be (the text is the page's own)
    const checkTxt = el('span', { class: 'hb-row-k hb-selectable' });
    const check = el('section', { class: 'hb-isec hb-lab-check', id: 'hbLabCheck', hidden: true },
      el('div', { class: 'hb-isec-h', text: 'Validation' }), el('div', { class: 'hb-box' }, el('div', { class: 'hb-row' }, sf('warn'), checkTxt)));
    res.prepend(check);
    // the trade stepper: out of the chart, to the foot of the inspector (shown while the chart is)
    const nav = $('#labNav');
    if (nav) {
      res.append(el('section', { class: 'hb-isec hb-lab-trades', id: 'hbLabTrades' },
        el('div', { class: 'hb-isec-h', text: 'Trades on the chart' }), el('div', { class: 'hb-box' }, nav)));
    }

    /* ---- one state for the panes: the page's ---- */
    const PANEL = { sidebar: 'lib', inspector: 'res' }, OFF = { sidebar: 'hb-side-off', inspector: 'hb-insp-off' };
    const winOn = (n) => !H.classList.contains(OFF[n]);
    const pageOn = (n) => lab.dataset[PANEL[n]] !== '0';
    // the window changed (its button, or View > Show Sidebar): press the page's own toggle
    function fromWindow() {
      for (const n in PANEL) {
        if (winOn(n) === pageOn(n)) continue;
        const b = $('#labPanels [data-panel="' + PANEL[n] + '"]');
        if (b) b.click();
      }
    }
    // the page changed by itself (it hides the library the first time the chart opens on a small window)
    function fromPage() { for (const n in PANEL) if (winOn(n) !== pageOn(n)) A.toggle(n, pageOn(n)); }
    let linked = false;
    try { linked = !!new URLSearchParams(location.search).get('panels'); } catch (_) {}
    if (linked) fromPage(); else fromWindow();          // a ?panels= link is the page's word; otherwise the window's
    new MutationObserver(fromWindow).observe(H, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(fromPage).observe(lab, { attributes: true, attributeFilter: ['data-lib', 'data-res'] });

    /* ---- the window title: the open strategy and its state, as the page prints them ---- */
    const state = () => { try { return window.HBLab && window.HBLab.state; } catch (_) { return null; } };   // read only
    const titleEl = $('.hb-title', tb.left);
    function title() {
      try {
        const S = state(), b = S && S.cur && S.bufs ? S.bufs.get(S.cur) : null;
        const st = $('#edState'), txt = st ? st.textContent.trim() : '';
        const kind = b ? b.kind : $('#edName') ? 'new' : doc && doc.firstChild ? 'draft' : '';
        if (H.getAttribute('data-hb-doc') !== (kind || 'none')) H.setAttribute('data-hb-doc', kind || 'none');
        const err = !!(st && st.classList.contains('err'));
        if (tb.left.dataset.tone !== (err ? 'err' : '')) tb.left.dataset.tone = err ? 'err' : '';
        if (check.hidden !== !err) check.hidden = !err;
        if (err && checkTxt.textContent !== txt) checkTxt.textContent = txt;
        const tip = (st && st.getAttribute('title')) || '';             // the page's own tooltip ("Saved 2 min ago")
        if (titleEl && titleEl.title !== tip) titleEl.title = tip;
        if (!kind) return tb.title('Lab', '');
        const nameEl = $('.doc-name', doc);
        const name = b ? (b.kind === 'builtin' ? (b.meta && b.meta.name) || b.id : b.name) : nameEl ? nameEl.textContent.replace(/\.py$/, '') : '';
        let sub = txt;
        if (kind === 'builtin') sub = 'Built-in, read only';
        else if (kind === 'draft' && !err) sub = st && st.classList.contains('edited') ? 'Edited' : txt ? 'Draft · ' + txt : 'Draft';
        tb.title(name || 'Untitled', sub);
      } catch (_) { /* a repaint must never be broken by the skin */ }
    }
    if (doc) new MutationObserver(title).observe(doc, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['class', 'title'] });
    title();

    /* ---- appearance: follow the window; the page's own toggle does the switch ---- */
    const themeBtn = $('#tbTheme');
    A.syncTheme(() => { if (themeBtn) themeBtn.click(); });
  } catch (e) {
    try { console.error('[hb-apple lab]', e); } catch (_) {}
    (window.__hbErrors = window.__hbErrors || []).push('lab skin: ' + (e && e.message));
  } finally {
    A.ready();
  }
})();
