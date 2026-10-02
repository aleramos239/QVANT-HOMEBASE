/* Homebase Next — Charts, as a macOS window: one toolbar · a controls row · the chart panes · an inspector · a status bar.

   PRESENTATION ONLY. The page's own scripts still build every pane, menu, dialog and panel and own every handler.
   This file:
     - MOVES the page's own controls into the window toolbar: the page switcher (centre), the Order and DOM panel
       toggles (one platter, trailing) and the chart-settings gear (its own platter, in the inspector zone). They are
       the same nodes with the listeners they already had;
     - keeps the page's own chart toolbar as the controls row under the toolbar (symbol, intervals, more intervals,
       Indicators, layout) and moves the layout tab strip (its tabs and its "+") to that row's trailing end;
     - gives the page's panel dock (#pdock: Order ticket, DOM) the inspector material and tells the window how wide
       it is, so the content and the toolbar's inspector zone follow it (the page still sizes, splits and closes it).
       The app's View > Inspector command is passed on as a click on the page's own Order / DOM toggles;
     - marks which panes sit under the floating drawing rail, so their header steps clear of it, and shows each
       pane's name as symbol + detail (a span beside the page's own name node, which stays in the tree);
     - writes the title's subtitle from the selected pane's own header text.
   It calls no endpoint, changes no handler and never stops an event. If anything here throws, the page is shown as
   the base page: the finally block always reveals it.                                                               */
(function () {
  'use strict';
  const A = window.HBApple;
  if (!A || document.documentElement.dataset.hbCharts) return;
  document.documentElement.dataset.hbCharts = '1';
  const D = document, H = D.documentElement, $ = (s, r) => (r || D).querySelector(s);
  const { el, sf } = A;

  try {
    const ctl = $('body > header.toolbar'), main = $('body > .main'), grid = $('#grid');
    if (!ctl || !main || !grid) throw new Error('charts markup not found');
    const rail = $('#rail'), dock = $('#pdock'), oldBar = $('body > .hb-bar');

    /* ---- toolbar: the page's own controls, moved ---- */
    const tb = A.toolbar({ sidebar: false, inspector: false });
    tb.title('Charts', '');
    const sw = $('#pgSw');
    if (sw) { sw.classList.add('hb-seg'); tb.center.append(sw); }
    // Order / DOM: text toggles on one platter (the page keeps their aria-pressed; the grey pill shows it)
    const panels = el('div', { class: 'hb-platter hb-c-panels', role: 'group', 'aria-label': 'Panels' });
    for (const id of ['tbOrder', 'tbDom']) {
      const b = D.getElementById(id);
      if (b) { b.classList.add('hb-tbtn', 'hb-text'); panels.append(b); }
    }
    if (panels.children.length) tb.right.append(panels);
    // chart settings: the gear, on its own platter over the inspector
    const gear = $('#tbSettings');
    if (gear) {
      gear.classList.add('hb-tbtn');
      gear.replaceChildren(sf('gear'));
      tb.insp.append(el('div', { class: 'hb-platter' }, gear));
    }

    /* ---- the controls row: the page's chart toolbar, plus the layout tabs at its trailing end ---- */
    const strip = $('#tabStrip');
    if (strip) ctl.append(strip);
    if (oldBar) oldBar.hidden = true;

    /* ---- the inspector: the page's own dock ---- */
    // html.hb-insp-off always says what the dock says. When only the class moved (the app's View > Inspector command
    // flipped it), the command is passed on as a click on the page's own panel toggles; then the dock is read again.
    let dockW = 0, was = null, acting = false;
    const isOpen = () => !!dock && !dock.hidden;
    function command(show) {
      if (show) {
        const b = [D.getElementById('tbOrder'), D.getElementById('tbDom')].find((x) => x && x.getAttribute('aria-pressed') !== 'true');
        if (b) b.click();
      } else {
        for (const p of dock.querySelectorAll('.hbpanel.docked')) {
          const b = p.id && $('#hbTb [aria-controls="' + p.id + '"]');
          if (b && b.getAttribute('aria-pressed') === 'true') b.click();
        }
      }
    }
    function syncDock() {
      let open = isOpen();
      if (H.classList.contains('hb-insp-off') === open) {
        if (was === open && !acting && dock) {
          acting = true;
          try { command(!open); } catch (_) { /* the page's toggle is the page's business */ }
          acting = false;
          open = isOpen();
        }
        H.classList.toggle('hb-insp-off', !open);
      }
      was = open;
      if (open) {
        const w = Math.max(270, Math.round(dock.getBoundingClientRect().width));
        if (w !== dockW) { dockW = w; H.style.setProperty('--a-insp-w', w + 'px'); }
      }
      fit();
    }
    // the page switcher is centred on the window; when a wide inspector leaves no room for that, it takes its place in the row
    function fit() {
      const W = window.innerWidth, zone = isOpen() ? dockW : tb.insp.offsetWidth;
      const need = W / 2 + (sw ? sw.offsetWidth / 2 : 0) + 12, room = W - zone - 8 - panels.offsetWidth;
      const tight = need > room;
      if (H.classList.contains('hb-c-tight') !== tight) H.classList.toggle('hb-c-tight', tight);
    }
    window.addEventListener('resize', fit);
    if (dock) {
      dock.classList.add('hb-insp');
      new MutationObserver(syncDock).observe(dock, { attributes: true, attributeFilter: ['hidden', 'style', 'class'] });
      if (typeof ResizeObserver !== 'undefined') new ResizeObserver(syncDock).observe(dock);
    }
    // View > Inspector in the app flips the class; here the dock itself is the truth
    new MutationObserver(syncDock).observe(H, { attributes: true, attributeFilter: ['class'] });
    syncDock();

    /* ---- panes: the header steps clear of the rail; the subtitle is the selected pane's own name ---- */
    // one repaint per frame; the timer is the fallback for a window that is not being drawn (no frames arrive then)
    let raf = 0, tmr = 0;
    const queue = () => { if (raf || tmr) return; raf = requestAnimationFrame(paint); tmr = setTimeout(paint, 160); };
    // a pane's name is one string ("NQ · E-mini Nasdaq-100 · 1m"): shown as the symbol (13 semibold) and its detail (11),
    // in a span of the skin's own beside the page's node, which stays in the tree for the page and for assistive tech
    const nameMo = new MutationObserver(queue), watched = new WeakSet();
    function header(p) {
      const nm = $('.lg-name', p);
      if (!nm) return;
      if (!watched.has(nm)) { watched.add(nm); nameMo.observe(nm, { childList: true, characterData: true, subtree: true }); }
      const t = (nm.textContent || '').trim(), i = t.indexOf(' \u00b7 ');
      const sym = i > 0 ? t.slice(0, i) : t, det = i > 0 ? t.slice(i + 3) : '';
      let h = nm.nextElementSibling;
      if (!h || !h.classList.contains('hb-lg-name')) { h = el('span', { class: 'hb-lg-name', 'aria-hidden': 'true' }, el('b'), el('span')); nm.after(h); }
      if (h.firstChild.textContent !== sym) h.firstChild.textContent = sym;
      if (h.lastChild.textContent !== det) h.lastChild.textContent = det;
    }
    function paint() {
      if (raf) cancelAnimationFrame(raf);
      if (tmr) clearTimeout(tmr);
      raf = tmr = 0;
      try {
        const rr = rail ? rail.getBoundingClientRect() : null;
        for (const p of grid.children) {
          if (rr) {
            const r = p.getBoundingClientRect();
            const under = rr.width > 0 && r.left < rr.right && r.right > rr.left && r.top < rr.bottom && r.bottom > rr.top;
            if (p.classList.contains('hb-under-rail') !== under) p.classList.toggle('hb-under-rail', under);
          }
          header(p);
        }
        const name = $('.panel.selected .lg-name', grid) || $('.panel .lg-name', grid);
        tb.title('Charts', name ? name.textContent.trim() : '');
      } catch (_) { /* a repaint must never be broken by the skin */ }
    }
    const mo = new MutationObserver(queue);
    mo.observe(grid, { childList: true, attributes: true, attributeFilter: ['style', 'data-count'] });
    const favs = $('#tbFavs'), symText = $('#tbSymbolText');
    if (favs) mo.observe(favs, { childList: true });                       // the page repaints it on every selection / interval change
    if (symText) mo.observe(symText, { childList: true, characterData: true, subtree: true });
    if (typeof ResizeObserver !== 'undefined') { const ro = new ResizeObserver(queue); ro.observe(grid); if (rail) ro.observe(rail); }
    window.addEventListener('resize', queue);
    queue();
    setTimeout(queue, 600);                                                 // the first panes arrive after the page's own fetch

    /* ---- the earlier "lens" glass is not this window's material: its class comes off the two nodes that had it ---- */
    const unlens = () => { for (const n of D.querySelectorAll('#pgSw.hb-lens, #tbFavs.hb-lens')) n.classList.remove('hb-lens', 'hb-lens-on'); };
    unlens(); setTimeout(unlens, 0); setTimeout(unlens, 400); window.addEventListener('load', unlens);

    /* ---- appearance: follow the window; the page's own toggle does the switch (it restyles every chart) ---- */
    const themeBtn = $('#tbTheme');
    A.syncTheme(() => { if (themeBtn) themeBtn.click(); });
  } catch (e) {
    try { console.error('[hb-apple charts]', e); } catch (_) {}
    (window.__hbErrors = window.__hbErrors || []).push('charts skin: ' + (e && e.message));
  } finally {
    A.ready();
  }
})();
