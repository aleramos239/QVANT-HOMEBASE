/* Homebase Next — the Desk, as a macOS three-pane window: sidebar · content · inspector, under one toolbar.

   PRESENTATION ONLY. The page's own script still renders every row and owns every handler. This file:
     - switches off the two earlier design layers (apple.css, hb.css) so the system layer starts from the base page;
     - MOVES the page's own controls into the toolbar: the page switcher, the readiness bulb, the status pill, Arm /
       Disarm, the hold-to-Kill button and Settings are the same nodes with the same listeners they had;
     - gives the page's sidebar the glass pane, and adds an inspector that HOLDS nodes the page already renders
       (readiness, notices, the footer links; a strategy's figures, links and actions), re-collected after each of
       the page's repaints;
     - adds a "Setup" card to the strategy inspector, written from the same cfg the page prints as one line; a straddle with
     an RR (nq930) also gets a small RR field whose Set button calls the page's own setStratRr().
   It calls no endpoint itself, changes no handler and never stops an event. If anything here throws, the page is shown as
   the base page: the finally block always reveals it.                                                               */
(function () {
  'use strict';
  const A = window.HBApple;
  if (!A || document.documentElement.dataset.hbDesk) return;
  document.documentElement.dataset.hbDesk = '1';
  const D = document, H = D.documentElement, $ = (s, r) => (r || D).querySelector(s);
  const { el, sf } = A;

  try {
    A.disableSheets(['/static/apple.css', '/static/hb.css']);
    const side = $('#side'), main = $('.app-main'), frame = $('.frame');
    if (!side || !main || !frame) throw new Error('desk markup not found');

    /* ---- toolbar: the page's own controls, moved ---- */
    const tb = A.toolbar();
    const sw = $('#pgSw');
    if (sw) { sw.classList.add('hb-seg'); tb.center.append(sw); }
    const bulb = $('#bulb'), slot = $('.pill-slot'), clock = $('#clock'), arm = $('#armBtn'), kill = $('#killBtn'), settings = $('#settingsBtn');
    // status: the readiness shield, then the armed state over the desk's clock (a title-and-subtitle block, no glass)
    const stCol = el('div', { class: 'hb-st-col' });
    if (slot) stCol.append(slot);
    if (clock) stCol.append(clock);
    const status = el('div', { class: 'hb-status hb-desk-status' });
    if (bulb) status.append(bulb);
    status.append(stCol);
    tb.right.append(status);
    if (arm) { arm.classList.add('hb-tbtn', 'hb-text', 'hb-arm'); tb.right.append(arm); }
    if (kill) { kill.classList.add('hb-kill'); tb.right.append(kill); }
    if (settings) {
      settings.classList.add('hb-tbtn');
      settings.replaceChildren(sf('gear'));
      tb.insp.prepend(el('div', { class: 'hb-platter' }, settings));
    }
    const old = $('.inset-topbar');
    if (old) old.hidden = true;

    /* ---- panes ---- */
    side.classList.add('hb-side');
    const insp = el('aside', { class: 'hb-insp', id: 'hbInsp', 'aria-label': 'Inspector' });
    frame.append(insp);

    // Today / Activity: the desk's own status nodes, re-housed (the page keeps writing into them by id)
    const sum = el('button', { class: 'hb-row hb-ready-row', type: 'button', id: 'hbReadyRow', onclick: () => { if (typeof window.openChecks === 'function') window.openChecks(); } },
      el('i', { class: 'hb-ready-ico' }), el('span', { class: 'hb-row-k', id: 'hbReadyTxt', text: 'Checking…' }), sf('chevron-right', 'hb-chev'));
    const ready = $('#readyStrip'), foot = $('#todayFoot'), notices = $('#noticeStrip');
    const deskPage = el('div', { class: 'hb-ipage', id: 'hbInspDesk' },
      el('section', { class: 'hb-isec' }, el('div', { class: 'hb-isec-h', text: 'Readiness' }), el('div', { class: 'hb-box' }, sum, ready)),
      el('section', { class: 'hb-isec hb-isec-foot' }, el('div', { class: 'hb-isec-h', text: 'Desk' }), el('div', { class: 'hb-box' }, foot)),
      el('section', { class: 'hb-isec hb-isec-notices' }, el('div', { class: 'hb-isec-h', text: 'Notices' }), el('div', { class: 'hb-box' }, notices)));
    // a strategy: its setup (read-only but for a straddle's target RR), then the page's own figures, links and actions
    const setupBox = el('div', { class: 'hb-box', id: 'hbSetup' });
    const figsBox = el('div', { class: 'hb-box hb-figs-box', id: 'hbFigs' });
    const figsH = el('div', { class: 'hb-isec-h', text: 'Live results' });      // "Research results" for a watched strategy (it has no live trades)
    const linksBox = el('div', { class: 'hb-box hb-links-box', id: 'hbLinks' });
    const actsBox = el('div', { class: 'hb-acts', id: 'hbActs' });
    const stratPage = el('div', { class: 'hb-ipage', id: 'hbInspStrat' },
      el('section', { class: 'hb-isec' }, el('div', { class: 'hb-isec-h', text: 'Setup' }), setupBox),
      el('section', { class: 'hb-isec' }, figsH, figsBox),
      el('section', { class: 'hb-isec hb-isec-links' }, el('div', { class: 'hb-isec-h', text: 'More' }), linksBox),
      actsBox);
    insp.append(deskPage, stratPage);

    // a section title over the strategies list (the list itself is the page's, re-rendered in place)
    const list = $('#stratList');
    if (list) list.before(el('h2', { class: 'hb-sec-h', text: 'Strategies' }));
    const tl = $('#dayTl');
    if (tl) tl.before(el('h2', { class: 'hb-sec-h', text: 'Session' }));

    /* ---- after each repaint of the page: which view, the title, the inspector's borrowed nodes ---- */
    const vToday = $('#viewToday'), vStrat = $('#viewStrat'), vAct = $('#viewActivity');
    const status_ = () => { try { return ST; } catch (_) { return null; } };          // the page's own state (read only)
    const viewOf = () => (vStrat && !vStrat.hidden) ? 'strat' : (vAct && !vAct.hidden) ? 'activity' : 'today';
    const fmtN = (v) => (v == null || v === '' ? '—' : String(+v === Math.round(+v) ? Math.round(+v) : +v));
    const hm = (t) => { const m = /^(\d{1,2}):(\d\d)/.exec(String(t || '')); return m ? String(parseInt(m[1], 10)) + ':' + m[2] : ''; };
    const row = (k, v) => el('div', { class: 'hb-row' }, el('span', { class: 'hb-row-k', text: k }), el('span', { class: 'hb-row-v', text: v }));

    /* A WATCHED strategy (promoted from the Lab's Book; the page's WATCH list): what it is, read-only. It has no desk setup -- it places no orders. */
    const watched = () => { try { return VIEW && VIEW.k === 'watch' ? ((WATCH || []).find((w) => w && w.name === VIEW.name) || {}) : null; } catch (_) { return null; } };
    function setupWatch(w) {
      const sess = { asia: 'Asia', london: 'London', pre: 'Pre-market', nyam: 'NY morning', mid: 'Midday', pm: 'Afternoon', eve: 'Evening' };
      const rows = [row('Instrument', String(w.market || '—')), row('Time of day', sess[w.session] || String(w.session || '—')),
        row('Bars', w.bar ? fmtN(w.bar) + ' min' : '—'), row('Entry rule', String(w.family || '—')), row('Stop and target', String(w.cell || '—')),
        row('Tested on', w.start && w.end ? String(w.start) + ' to ' + String(w.end) : '—'), row('Orders', 'None: watch-only')];
      setupBox.replaceChildren(...rows);
    }

    function setup(name) {
      const st = status_(), s = st && st.strategies && st.strategies[name], c = s && s.cfg;
      if (!c) { setupBox.replaceChildren(); return; }
      const rows = [row('Instrument', String(c.symbol || '—'))];
      if (c.kind === 'bars') {
        rows.push(row('Bars', fmtN(c.bar_minutes) + ' min'));
        if (c.rule) rows.push(row('Rule', String(c.rule)));
      } else {
        rows.push(row('Entry offset', '±' + fmtN(c.offset_pts) + ' pts'));
        rows.push(row('Stop', fmtN(c.sl_pts) + ' pts'));
        rows.push(row('Target', c.rr > 0 ? '1:' + fmtN(c.rr) + ' · ' + fmtN(c.tp_pts) + ' pts' : fmtN(c.tp_pts) + ' pts'));
        if (c.self_fire && hm(c.fire_et)) rows.push(row('Fires', hm(c.fire_et) + ' ET'));
      }
      if (hm(c.cancel_et)) rows.push(row('Cancel unfilled', hm(c.cancel_et) + ' ET'));
      if (hm(c.flat_et)) rows.push(row('Flat', hm(c.flat_et) + ' ET'));
      if (Array.isArray(c.only_dates) && c.only_dates.length) rows.push(row('Only on', c.only_dates.slice(0, 2).join(', ') + (c.only_dates.length > 2 ? ' +' + (c.only_dates.length - 2) : '')));
      rows.push(row('Signal', c.kind === 'bars' ? 'Price-action rule' : c.self_fire ? 'Fires itself' : 'Nothing fires it'));
      if (c.shadow) rows.push(row('Mode', 'Shadow (journal only)'));
      const edit = c.kind !== 'bars' && c.rr > 0;
      const sig = JSON.stringify([name, edit, rows.map((r) => r.textContent)]);
      const had = (D.activeElement === rrCtl.input || D.activeElement === rrCtl.btn) ? D.activeElement : null;
      if (setupBox._sig !== sig) { setupBox._sig = sig; setupBox.replaceChildren(...rows, ...(edit ? [rrCtl.row, rrCtl.err] : [])); }
      if (had && had.isConnected && D.activeElement !== had) had.focus();      // a rebuild must not take the field from the owner
      if (rrCtl.name !== name) { rrCtl.name = name; rrCtl.dirty = false; rrCtl.err.hidden = true; }
      if (edit && !rrCtl.dirty && D.activeElement !== rrCtl.input) rrCtl.input.value = String(+c.rr);
    }
    // the RR field of a straddle with a target multiple: ONE node set for the whole page, so a repaint never wipes what is typed
    // (the rows' signature leaves it out). The write itself is the page's own setStratRr(), which says why a refusal came.
    const rrCtl = { name: '', dirty: false };
    rrCtl.input = el('input', { class: 'hb-field', type: 'number', step: '0.25', min: '0.25', max: '20', inputmode: 'decimal', 'aria-label': 'Target RR (1:x)', style: 'width:64px;text-align:right' });
    rrCtl.btn = el('button', { class: 'hb-btn', type: 'button', text: 'Set' });
    rrCtl.row = el('div', { class: 'hb-row' }, el('span', { class: 'hb-row-k', text: 'Target RR · 1:' }), rrCtl.input, rrCtl.btn);
    rrCtl.err = el('div', { class: 'hb-row hb-row-note', role: 'alert', hidden: true });
    async function setRr() {
      const name = rrCtl.name, v = parseFloat(rrCtl.input.value);
      if (!(v >= 0.25 && v <= 20)) { rrCtl.err.textContent = 'Enter a number from 0.25 to 20.'; rrCtl.err.hidden = false; return; }
      if (typeof window.setStratRr !== 'function') return;
      rrCtl.btn.disabled = true;
      try {
        const why = await window.setStratRr(name, v);
        if (rrCtl.name !== name) return;
        rrCtl.err.textContent = why || ''; rrCtl.err.hidden = !why;
        if (!why) rrCtl.dirty = false;
      } finally { rrCtl.btn.disabled = false; }
    }
    rrCtl.input.addEventListener('input', () => { rrCtl.dirty = true; rrCtl.err.hidden = true; });
    rrCtl.input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.repeat) setRr(); });
    rrCtl.btn.addEventListener('click', setRr);

    let syncing = false;
    function sync() {
      if (syncing) return;
      syncing = true;
      try {
        const v = viewOf();
        if (H.getAttribute('data-hb-view') !== v) H.setAttribute('data-hb-view', v);
        const st = status_();
        if (v === 'strat') {
          // the page just rebuilt #viewStrat: take this render's figures, links and actions into the inspector
          const figs = $(':scope > .figs', vStrat), links = $(':scope > .qlinks', vStrat), acts = $(':scope > .sd-actions', vStrat);
          // "No live trades yet." stands where the figures would be (the curve's own empty note stays in the content)
          const none = [...vStrat.children].find((n) => n.classList.contains('eq-empty') && /No live trades/.test(n.textContent)) || null;
          if (figs || none || links || acts) {
            figsBox.replaceChildren(...(figs ? [figs] : none ? [el('div', { class: 'hb-row hb-row-note', text: 'No live trades yet.' })] : []));
            if (none && !figs) none.remove();
            linksBox.replaceChildren(...(links ? [links] : []));
            actsBox.replaceChildren(...(acts ? [acts] : []));
          }
          const t = $('.sd-title', vStrat), sd = $('.sd-state b', vStrat);
          let name = '';
          try { name = (VIEW && VIEW.name) || ''; } catch (_) {}
          const w = watched();
          figsH.textContent = w ? 'Research results' : 'Live results';
          if (w) setupWatch(w); else setup(name);
          tb.title(t ? t.textContent : 'Strategy', sd ? sd.textContent : '');
        } else if (v === 'activity') {
          tb.title('Activity', 'Every alert, order and fill');
        } else {
          let date = '';
          if (st && st.et_now) {
            try { date = new Date(String(st.et_now).slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }); } catch (_) {}
          }
          tb.title('Today', date);
        }
        // readiness, in words (the bulb is the page's own verdict; the row opens the page's own System checks)
        if (bulb) {
          const lvl = bulb.classList.contains('bad') ? 'bad' : bulb.classList.contains('warn') ? 'warn' : bulb.classList.contains('ok') ? 'ok' : '';
          const txt = lvl === 'ok' ? 'Ready to trade' : lvl === 'warn' ? 'Needs attention' : lvl === 'bad' ? 'Not ready' : 'Checking…';
          if (sum.dataset.lvl !== lvl) sum.dataset.lvl = lvl;
          const t = $('#hbReadyTxt');
          if (t && t.textContent !== txt) t.textContent = txt;
        }
      } catch (_) { /* a repaint must never be broken by the skin */ }
      finally { syncing = false; }
    }
    const mo = new MutationObserver(sync);
    for (const n of [vToday, vStrat, vAct]) if (n) mo.observe(n, { attributes: true, attributeFilter: ['hidden'] });
    if (vStrat) mo.observe(vStrat, { childList: true });
    if (side) mo.observe(side, { childList: true });                  // the page repaints the sidebar on every refresh
    if (bulb) mo.observe(bulb, { attributes: true, attributeFilter: ['class'] });
    sync();

    /* ---- appearance: follow the window; the page's own toggle does the switch ---- */
    const themeBtn = $('#themeToggle');
    A.syncTheme(() => { if (themeBtn) themeBtn.click(); });
    if (themeBtn) themeBtn.hidden = true;
  } catch (e) {
    try { console.error('[hb-apple desk]', e); } catch (_) {}
    (window.__hbErrors = window.__hbErrors || []).push('desk skin: ' + (e && e.message));
  } finally {
    A.ready();
  }
})();
