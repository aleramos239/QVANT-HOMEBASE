/* Homebase Next — the shared shell (Desk, Charts, Lab). Injected by the Mac app at document end, before the tab's own
   skin script. It builds NOTHING that sends: it makes the window's toolbar, the sidebar / inspector toggles and the
   appearance sync, and gives each page's skin a few helpers. A page's own controls are MOVED into the toolbar (the same
   nodes, with the handlers they already carry), never re-created.

   window.HBApple:
     el(tag, attrs, ...children)   make an element
     sf(name)                      an SF Symbol (symbols.css) as <i class="sf sf-NAME">
     disableSheets(patterns)       switch off earlier design layers by href substring
     toolbar()                     build the toolbar once; returns {lead, left, center, right, insp, title(b, s)}
     toggle(name)                  'sidebar' | 'inspector': flip, remember, return the new state
     command(name)                 a View-menu command from the app ('sidebar' | 'inspector')
     syncTheme(fn)                 follow the window's appearance; fn(wantDark) flips the page's own theme
     ready()                       the page has its shape: show it                                                   */
(function () {
  'use strict';
  if (window.HBApple) return;
  const D = document, H = D.documentElement;
  const TAB = (window.HB_NATIVE && window.HB_NATIVE.tab) || H.getAttribute('data-hb-tab') || 'desk';
  const KEY = 'hbx_' + TAB + '_';

  function el(tag, attrs, ...children) {
    const e = D.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k === 'html') e.innerHTML = v;
      else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c != null && c !== false) e.append(c);
    return e;
  }
  const sf = (name, cls) => el('i', { class: 'sf sf-' + name + (cls ? ' ' + cls : ''), 'aria-hidden': 'true' });

  function disableSheets(patterns) {
    for (const l of D.querySelectorAll('link[rel~="stylesheet"]')) {
      const href = l.getAttribute('href') || '';
      if (patterns.some((p) => href.indexOf(p) >= 0)) l.disabled = true;
    }
  }

  const get = (k, d) => { try { const v = localStorage.getItem(KEY + k); return v == null ? d : v; } catch (_) { return d; } };
  const set = (k, v) => { try { localStorage.setItem(KEY + k, v); } catch (_) {} };

  /* ---- sidebar / inspector: a class on <html>, remembered per tab ---- */
  const PANES = { sidebar: { cls: 'hb-side-off', btn: null, on: 'Hide Sidebar', off: 'Show Sidebar' },
                  inspector: { cls: 'hb-insp-off', btn: null, on: 'Hide Inspector', off: 'Show Inspector' } };
  function paint(name) {
    const p = PANES[name], shown = !H.classList.contains(p.cls);
    if (p.btn) { p.btn.title = shown ? p.on : p.off; p.btn.setAttribute('aria-label', p.btn.title); p.btn.setAttribute('aria-expanded', String(shown)); }
  }
  function toggle(name, want) {
    const p = PANES[name]; if (!p) return false;
    const shown = want == null ? H.classList.contains(p.cls) : !!want;      // currently off -> show
    H.classList.toggle(p.cls, !shown);
    set(name, shown ? '1' : '0');
    paint(name);
    window.dispatchEvent(new Event('resize'));          // a chart sizes itself to its container
    setTimeout(() => window.dispatchEvent(new Event('resize')), 340);
    return shown;
  }
  // narrow windows start with the inspector closed (a pane has to give, as in a native split view)
  function restore(name, dflt) {
    const saved = get(name, null);
    const shown = saved == null ? dflt : saved === '1';
    H.classList.toggle(PANES[name].cls, !shown);
  }

  /* ---- the toolbar ---- */
  let TB = null;
  function toolbar(opts) {
    if (TB) return TB;
    opts = opts || {};
    const side = el('button', { class: 'hb-tbtn hb-bare', type: 'button', id: 'hbSideBtn', onclick: () => toggle('sidebar') }, sf('sidebar-left'));
    const insp = el('button', { class: 'hb-tbtn hb-solo', type: 'button', id: 'hbInspBtn', onclick: () => toggle('inspector') }, sf('sidebar-right'));
    PANES.sidebar.btn = side; PANES.inspector.btn = insp;
    const titleB = el('b'), titleS = el('span');
    const lead = el('div', { class: 'hb-tb-lead hb-drag' }, opts.sidebar === false ? null : side);
    const left = el('div', { class: 'hb-tb-l' }, el('div', { class: 'hb-title' }, titleB, titleS));
    const center = el('div', { class: 'hb-tb-c' });
    const right = el('div', { class: 'hb-tb-r' });
    const main = el('div', { class: 'hb-tb-main hb-drag' }, left, center, right);
    const inspZone = el('div', { class: 'hb-tb-insp hb-drag' }, opts.inspector === false ? null : insp);
    const bar = el('header', { class: 'hb-tb', id: 'hbTb', role: 'toolbar', 'aria-label': 'Window toolbar' }, lead, main, inspZone);
    D.body.prepend(el('div', { class: 'hb-tb-scrim', 'aria-hidden': 'true' }), bar);
    restore('sidebar', true);
    restore('inspector', window.innerWidth >= 1180);
    paint('sidebar'); paint('inspector');
    TB = { bar, lead, left, center, right, insp: inspZone, sideBtn: side, inspBtn: insp,
           title(b, s) { if (titleB.textContent !== b) titleB.textContent = b; if (titleS.textContent !== (s || '')) titleS.textContent = s || ''; } };
    return TB;
  }

  function command(name) { if (PANES[name]) toggle(name); }

  /* ---- appearance: the page follows the window (View > Appearance in the app) ---- */
  function syncTheme(flip) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const run = () => {
      const want = mq.matches, have = H.getAttribute('data-theme') === 'dark';
      if (want !== have) { try { flip(want); } catch (_) {} }
      if ((H.getAttribute('data-theme') === 'dark') !== want) H.setAttribute('data-theme', want ? 'dark' : 'light');
    };
    run();
    if (mq.addEventListener) mq.addEventListener('change', run); else if (mq.addListener) mq.addListener(run);
  }

  /* ---- page links: the app switches tabs itself; in a plain browser a link is just a link ---- */
  function ready() { H.classList.add('hb-ready'); }

  window.HBApple = { el, sf, disableSheets, toolbar, toggle, command, syncTheme, ready, tab: TAB, get, set };
})();
