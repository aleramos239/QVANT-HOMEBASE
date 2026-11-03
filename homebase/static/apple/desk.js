/* Homebase Next — the Desk, as a macOS three-pane window: sidebar · content · inspector, under one toolbar.

   PRESENTATION ONLY. The page's own script still renders every row and owns every handler. This file:
     - switches off the two earlier design layers (apple.css, hb.css) so the system layer starts from the base page;
     - MOVES the page's own controls into the toolbar: the page switcher, the readiness bulb, the status pill, Arm /
       Disarm, the hold-to-Kill button and Settings are the same nodes with the same listeners they had;
     - gives the page's sidebar the glass pane, and adds an inspector that HOLDS nodes the page already renders
       (notices, the footer links; a strategy's figures, links and actions), re-collected after each of
       the page's repaints;
     - adds a "Setup" card to the strategy inspector, written from the same cfg the page prints as one line; a straddle with
     an RR (nq930) also gets a 5/10-point stop menu and a small RR field; both call the page's own setStratRr(). A Lab strategy
     on the Desk has no Setup here: the page's own Backtest and About blocks move in (its Set up card stays in the content).
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
    // readiness in words beside the shield ("Ready" / "2 things need a look"), filled by sync(); a click opens the same System checks
    const readyBtn = el('button', { class: 'hb-ready-word', type: 'button', text: 'Checking…', onclick: () => { if (typeof window.openChecks === 'function') window.openChecks(); } });
    // under it, chart trading when it is ON, armed or not (Disarm does not stop the chart page's orders); filled by sync(). Two
    // lengths: a narrow window shows the short one ("Chart ON · 5 live"), never without the count
    const ctLong = el('span', { class: 'hb-ct-long' }), ctShort = el('span', { class: 'hb-ct-short' });
    const ctChip = el('span', { class: 'hb-ct-chip', hidden: true, title: 'The chart page can place orders, even when Disarmed. Its switch is in Settings.' }, ctLong, ctShort);
    // one fixed-width column (desk.css), so a word or the chip coming or going never moves Arm or Kill
    const rdCol = el('div', { class: 'hb-rd-col' }, el('div', { class: 'hb-rd-top' }, bulb, readyBtn), ctChip);
    const status = el('div', { class: 'hb-status hb-desk-status' });
    status.append(rdCol, stCol);
    tb.right.append(status);
    if (arm) { arm.classList.add('hb-tbtn', 'hb-text', 'hb-arm'); tb.right.append(arm); }
    if (kill) { kill.classList.add('hb-kill'); tb.right.append(kill); }
    if (settings) {
      settings.classList.add('hb-tbtn');
      settings.replaceChildren(sf('gear'));
      tb.insp.prepend(el('div', { class: 'hb-platter' }, settings));
    }
    // which machine this window is, in the fixed corner by the gear (never clipped); filled by sync(), hidden while unknown. Two
    // lengths: a narrow window shows the short one ("Server")
    const mLong = el('span', { class: 'hb-m-long' }), mShort = el('span', { class: 'hb-m-short' });
    const machine = el('span', { class: 'hb-machine', hidden: true }, mLong, mShort);
    tb.insp.prepend(machine);
    const old = $('.inset-topbar');
    if (old) old.hidden = true;

    /* ---- panes ---- */
    side.classList.add('hb-side');
    const insp = el('aside', { class: 'hb-insp', id: 'hbInsp', 'aria-label': 'Inspector' });
    frame.append(insp);

    // Today / Activity: the desk's own status nodes, re-housed (the page keeps writing into them by id)
    const foot = $('#todayFoot'), notices = $('#noticeStrip');
    const noNotices = el('div', { class: 'mcap', id: 'hbNoNotices', text: 'No notices' });      // shown while the strip is empty
    const deskPage = el('div', { class: 'hb-ipage', id: 'hbInspDesk' },
      el('section', { class: 'hb-isec hb-isec-foot' }, el('div', { class: 'hb-isec-h', text: 'Desk' }), el('div', { class: 'hb-box' }, foot)),
      el('section', { class: 'hb-isec hb-isec-notices' }, el('div', { class: 'hb-isec-h', text: 'Notices' }), el('div', { class: 'hb-box' }, notices, noNotices)));
    // a strategy: its setup (read-only but for a straddle's target RR), then the page's own figures, links and actions
    const setupBox = el('div', { class: 'hb-box', id: 'hbSetup' });
    const figsBox = el('div', { class: 'hb-box hb-figs-box', id: 'hbFigs' });
    let figsSec = null;      // hidden when it has nothing: a Lab strategy's backtest is its 3:1 block below (owner 2026-10-18)
    const figsH = el('div', { class: 'hb-isec-h', text: 'Desk results' });      // "Backtest" for a Lab one
    // a Lab strategy's research (the page's own .labres blocks): its saved run (3:1 test months, or the old record), and the prop sim
    const unseenH = el('div', { class: 'hb-isec-h' }), unseenBox = el('div', { class: 'hb-box hb-figs-box', id: 'hbUnseen' });
    const propH = el('div', { class: 'hb-isec-h', text: 'Prop sim' }), propBox = el('div', { class: 'hb-box hb-figs-box', id: 'hbProp' });
    const unseenSec = el('section', { class: 'hb-isec' }, unseenH, unseenBox), propSec = el('section', { class: 'hb-isec' }, propH, propBox);
    unseenSec.hidden = propSec.hidden = true;
    const linksBox = el('div', { class: 'hb-box hb-links-box', id: 'hbLinks' });
    const actsBox = el('div', { class: 'hb-acts', id: 'hbActs' });
    const setupH = el('div', { class: 'hb-isec-h', text: 'Setup' });      // "About" for a Lab strategy on the Desk
    const stratPage = el('div', { class: 'hb-ipage', id: 'hbInspStrat' },
      el('section', { class: 'hb-isec' }, setupH, setupBox),
      figsSec = el('section', { class: 'hb-isec' }, figsH, figsBox),
      unseenSec, propSec,
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
    const stale_ = () => { try { return DESK_STALE === true; } catch (_) { return false; } };      // the page's: ST is the last-known state
    const staleWhy_ = () => { try { return String(STALE_WHY || ''); } catch (_) { return ''; } };      // and the page's reason why
    const archived = () => { try { return VIEW && VIEW.k === 'archive'; } catch (_) { return false; } };      // the Archive list: no strategy in the inspector
    const viewOf = () => (vStrat && !vStrat.hidden && !archived()) ? 'strat' : (vAct && !vAct.hidden) ? 'activity' : 'today';
    const fmtN = (v) => (v == null || v === '' ? '—' : String(+v === Math.round(+v) ? Math.round(+v) : +v));
    const hm = (t) => { const m = /^(\d{1,2}):(\d\d)/.exec(String(t || '')); const s = m ? String(parseInt(m[1], 10)) + ':' + m[2] : ''; return s && window.HBClock ? window.HBClock.text(s) : s; };
    const row = (k, v) => el('div', { class: 'hb-row' }, el('span', { class: 'hb-row-k', text: k }), el('span', { class: 'hb-row-v', text: v }));

    /* A LAB strategy (promoted from the Lab; the page's DESKLAB list, helpers in desklab.js): what it is, read-only. It runs in shadow -- it places no orders. */
    const labbed = () => { try { return VIEW && VIEW.k === 'lab' ? ((DESKLAB.strategies || []).find((w) => w && w.name === VIEW.name) || {}) : null; } catch (_) { return null; } };
    function setupLab(l) {
      const rows = l.name && window.DeskLab ? window.DeskLab.setupRows(l).map(([k, v]) => row(k, v)) : [];
      setupBox.replaceChildren(...rows);
    }

    /* A GROUP (the page's teams(), words in desklab.js): its kind, how many strategies, the account it is scored on, its account group. */
    const groupped = () => { try { return VIEW && VIEW.k === 'group' ? (teams().find((g) => g && g.id === VIEW.name) || null) : null; } catch (_) { return null; } };
    function setupGroup(g) {
      let res = null, cycle = null;
      try { res = DESKGRES[g.id] || null; } catch (_) {}
      try { cycle = (ST.groups || {})[g.id] || null; } catch (_) {}
      const rows = window.DeskLab ? window.DeskLab.groupSetupRows(g, res, cycle).map(([k, v]) => row(k, v)) : [];
      setupBox.replaceChildren(...rows);
    }

    /* A LAB strategy the Desk itself knows (desk id lab_<name>, kind "lab", a `lab` block in the status): the page renders its Backtest
       and About blocks; this moves them in (owner 2026-11-02: About and More on the right, no second Setup). */
    const deskLabbed = (name) => { const st = status_(), s = st && st.strategies && st.strategies[name]; return s && s.cfg && s.cfg.kind === 'lab' && s.lab ? s : null; };
    const takeSec = (sec, box) => {      // the page's .sec without its h2, into an inspector box; the old block stays when no new one came
      if (!sec) return;
      box._sig = null;      // never what setup() cached
      box.replaceChildren(...[...sec.children].filter((n) => n.tagName !== 'H2'));
      sec.remove();
    };

    function setup(name) {
      const st = status_(), s = st && st.strategies && st.strategies[name], c = s && s.cfg;
      if (!c) { setupBox.replaceChildren(); return; }
      const rows = [row('Instrument', String(c.symbol || '—'))];
      if (c.kind === 'bars') {
        rows.push(row('Bars', fmtN(c.bar_minutes) + ' min'));
        if (c.rule) rows.push(row('Rule', String(c.rule)));
      } else {
        rows.push(row('Entry offset', '±' + fmtN(c.offset_pts) + ' pts'));
        if (!(c.rr > 0)) rows.push(row('Stop', fmtN(c.sl_pts) + ' pts'));      // with an RR the stop is the menu below
        rows.push(row('Target', c.rr > 0 ? '1:' + fmtN(c.rr) + ' · ' + fmtN(c.tp_pts) + ' pts' : fmtN(c.tp_pts) + ' pts'));
        if (c.self_fire && hm(c.fire_et)) rows.push(row('Fires', hm(c.fire_et) + ' ET'));
      }
      if (hm(c.cancel_et)) rows.push(row('Cancel unfilled', hm(c.cancel_et) + ' ET'));
      if (hm(c.flat_et)) rows.push(row('Flat by', hm(c.flat_et) + ' ET'));
      if (Array.isArray(c.only_dates) && c.only_dates.length) rows.push(row('Only on', c.only_dates.slice(0, 2).join(', ') + (c.only_dates.length > 2 ? ' +' + (c.only_dates.length - 2) : '')));
      rows.push(row('Signal', c.kind === 'bars' ? 'Price-action rule' : c.self_fire ? 'Fires itself' : 'Nothing fires it'));
      if (c.shadow) rows.push(row('Mode', 'Shadow (journal only)'));
      const edit = c.kind !== 'bars' && c.rr > 0;
      const sig = JSON.stringify([name, edit, rows.map((r) => r.textContent)]);
      const had = [rrCtl.input, rrCtl.btn, rrCtl.sl, rrCtl.slBtn].includes(D.activeElement) ? D.activeElement : null;
      if (setupBox._sig !== sig) { setupBox._sig = sig; setupBox.replaceChildren(...rows, ...(edit ? [rrCtl.slRow, rrCtl.row, rrCtl.err] : [])); }
      if (had && had.isConnected && D.activeElement !== had) had.focus();      // a rebuild must not take the field from the owner
      if (rrCtl.name !== name) { rrCtl.name = name; rrCtl.dirty = false; rrCtl.err.hidden = true; rrCtl.slCur = null; }
      if (edit && !rrCtl.dirty && D.activeElement !== rrCtl.input) rrCtl.input.value = String(+c.rr);
      if (edit && !rrCtl.sl.disabled) rrCtl.follow(String(+c.sl_pts));      // the Desk's stop (one set elsewhere, not 5 or 10, shows as it is)
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
    // the stop: 5 or 10 points (owner 2026-10-18). A pick waits for its Set, which names the change ("Set 5 pt → 10 pt"); the RR
    // stays, the target follows (sl x rr)
    rrCtl.sl = el('select', { class: 'hb-field', 'aria-label': 'Stop (points)' },
      el('option', { value: '5', text: '5 pts' }), el('option', { value: '10', text: '10 pts' }));
    rrCtl.slBtn = el('button', { class: 'hb-btn', type: 'button', hidden: true });
    rrCtl.slRow = el('div', { class: 'hb-row' }, el('span', { class: 'hb-row-k', text: 'Stop' }), rrCtl.sl, rrCtl.slBtn);
    rrCtl.slCur = null;      // the Desk's stop as setup() last saw it (null: not seen yet for this strategy)
    const slShow = () => {      // the Set button, only while the pick differs from the Desk's stop
      const pick = rrCtl.sl.value, on = rrCtl.slCur != null && pick !== rrCtl.slCur;
      if (on) rrCtl.slBtn.textContent = 'Set ' + rrCtl.slCur + ' pts → ' + pick + ' pts';      // the menu's own unit word
      rrCtl.slBtn.hidden = !on;
    };
    // each repaint: a pick waiting for its Set stays; otherwise the menu follows the Desk
    rrCtl.follow = (cur) => {
      if (![...rrCtl.sl.options].some((o) => o.value === cur)) rrCtl.sl.append(el('option', { value: cur, text: cur + ' pts' }));
      const pending = rrCtl.slCur != null && rrCtl.sl.value !== rrCtl.slCur;
      rrCtl.slCur = cur;
      if (!pending) rrCtl.sl.value = cur;
      slShow();
    };
    rrCtl.sl.addEventListener('change', () => { rrCtl.err.hidden = true; slShow(); });
    rrCtl.slBtn.addEventListener('click', async () => {
      const name = rrCtl.name, v = parseFloat(rrCtl.sl.value);
      if (!(v > 0) || typeof window.setStratRr !== 'function') return;
      const kb = D.activeElement === rrCtl.slBtn;      // reached by keyboard: the focus goes back to the menu once the button hides
      rrCtl.sl.disabled = rrCtl.slBtn.disabled = true;
      try {
        const why = await window.setStratRr(name, null, v);
        if (rrCtl.name !== name) return;
        rrCtl.err.textContent = why || ''; rrCtl.err.hidden = !why;
        if (why) rrCtl.sl.value = rrCtl.slCur;      // a refused pick goes back to the Desk's stop
        else rrCtl.slCur = rrCtl.sl.value;      // saved: the Desk's stop now (the page's refresh confirms it)
      } finally {
        rrCtl.sl.disabled = rrCtl.slBtn.disabled = false; slShow();
        if (kb && rrCtl.slBtn.hidden && rrCtl.sl.isConnected) rrCtl.sl.focus();
      }
    });
    rrCtl.input.addEventListener('input', () => { rrCtl.dirty = true; rrCtl.err.hidden = true; });
    rrCtl.input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.repeat) setRr(); });
    rrCtl.btn.addEventListener('click', setRr);

    /* ---- toolbar words (plain functions of what the page already holds) ---- */
    // ONE machine value: the native shell's window.HB_MACHINE, else the desk's /api/status `machine`. Anything else: no chip,
    // never a guess from the address (the server's Desk can show as localhost through a tunnel). `short`: a narrow window's words
    const machineWord = (st, short) => { const m = window.HB_MACHINE ?? (st && st.machine); return m === 'mac' ? 'This Mac' : m === 'server' ? (short ? 'Server' : 'Server · Chicago') : ''; };
    // readiness as the page shows it: its own readinessShown(), the list openChecks() opens (bad or warn = needs a look). [level, words]
    // While the page's state is old (`stale`: its DESK_STALE) the last answer is not current, never a stale "Ready": "Desk not
    // answering", or "Updates paused" when only an open menu or size edit holds the page (`why`: its STALE_WHY says so).
    const readyWord = (st, stale, why) => {
      if (stale) return /^updates pause/.test(why || '') ? ['', 'Updates paused'] : ['bad', 'Desk not answering'];
      const r = st && typeof window.readinessShown === 'function' ? window.readinessShown(st.readiness, st) : null;
      if (!r || !Array.isArray(r.checks)) return ['', 'Checking…'];
      const probs = r.checks.filter((c) => c && (c.level === 'bad' || c.level === 'warn')), n = probs.length;
      if (!n) return ['ok', 'Ready'];
      return [probs.some((c) => c.level === 'bad') ? 'bad' : 'warn', n === 1 ? '1 thing needs a look' : n + ' things need a look'];
    };
    // chart trading as the desk has it (its chart_trading switch), whatever the Arm state; live = the accounts the page tags LIVE (env
    // "live"). `short`: the words a narrow window keeps -- the count stays
    const chartWords = (st, short) => {
      const ct = st && st.chart_trading;
      if (!ct || !ct.enabled) return '';
      const n = Object.values(st.accounts || {}).filter((a) => a && a.env === 'live').length;
      if (short) return 'Chart ON' + (n ? ' · ' + n + ' live' : '');
      return 'Chart trading ON' + (n ? ' · ' + n + ' live account' + (n === 1 ? '' : 's') : '');
    };
    // a strategy's research record, read only: a group's by its id, a Desk Lab strategy's by its Lab name, the rest by the view's name
    // (the keys the page's groupView / labResHtml read)
    const recordOf = (grp, dl, name) => { try { return (grp ? DESKGRES[grp.id] : DESKRES[dl ? dl.lab.name : name]) || null; } catch (_) { return null; } };
    // the research block's heading, by the record's own route flag (walkforward: the 3:1 blocks), never the retired route's words;
    // an old-route record with no run at all is no record: "Results" over the page's own note
    const isObj = (o) => !!o && typeof o === 'object';
    const researchWord = (rec, withInSample) => !isObj(rec) ? 'Results'
      : rec.walkforward === true ? (withInSample ? '3:1 in-sample · test months' : '3:1 test months')
      : isObj(rec.unseen) || isObj(rec.build) ? 'Old record (before 3:1)' : 'Results';
    // the words written: the machine chip, readiness (the toolbar's word and the inspector's row), chart trading. Their own try,
    // first in every sync(), so a view that throws never freezes them; the pill's own repaint runs only this (the page's renderMaster
    // runs even while an open menu holds the cards under FREEZE: the content and the inspector's views are left as they are)
    function words() {
      try {
        const st = status_();
        const mw = machineWord(st);
        if (mLong.textContent !== mw) {
          mLong.textContent = machine.title = mw; mShort.textContent = machineWord(st, true);
          machine.dataset.m = mw === 'This Mac' ? 'mac' : 'server'; machine.hidden = !mw;
        }
        // beside the shield: how many checks need a look (or that the state is old)
        const stale = stale_(), [wl, wt] = readyWord(st, stale, staleWhy_());
        if (readyBtn.dataset.lvl !== wl) readyBtn.dataset.lvl = wl;
        if (readyBtn.textContent !== wt) { readyBtn.textContent = wt; readyBtn.setAttribute('aria-label', 'Readiness: ' + wt); }
        noNotices.hidden = !notices.hidden;
        const cw = chartWords(st), cs = chartWords(st, true);
        if (ctLong.textContent !== cw) ctLong.textContent = cw;
        if (ctShort.textContent !== cs) ctShort.textContent = cs;
        if (ctChip.hidden !== !cw) ctChip.hidden = !cw;
      } catch (_) { /* a repaint must never be broken by the skin */ }
    }
    /* ---- end toolbar words ---- */

    /* ---- research: the page's .labres blocks (the unseen days; a group's prop sim) into the inspector ---- */
    function takeResearch(res, name, grp, dl) {
      if (res) {
        const u = $('.labres-unseen', res), p = $('.labres-prop', res);
        if (!u) unseenBox.replaceChildren();      // a group's one Full sample block has none: nothing stale from the last page
        if (u) { unseenH.textContent = u.classList.contains('full') ? u.dataset.h : researchWord(recordOf(grp, dl, name), !!$('.fh', u)); unseenBox.replaceChildren(u); }
        propH.textContent = p ? p.dataset.h || '' : '';
        propBox.replaceChildren(...(p ? [p] : []));      // a page with no prop sim keeps none from the page before
        unseenSec.dataset.for = res.dataset.for || '';
        res.remove();
      }
      unseenSec.hidden = propSec.hidden = !name || unseenSec.dataset.for !== name;
      if (!unseenBox.childElementCount) unseenSec.hidden = true;      // never one strategy's research under another
      if (!propBox.childElementCount) propSec.hidden = true;
    }
    /* ---- end research ---- */

    let syncing = false;
    function sync() {
      if (syncing) return;
      syncing = true;
      try {
        words();
        const v = viewOf();
        if (H.getAttribute('data-hb-view') !== v) H.setAttribute('data-hb-view', v);
        const st = status_();
        if (v === 'strat') {
          // the page just rebuilt #viewStrat: take this render's figures, links and actions into the inspector
          let name = '';
          try { name = (VIEW && VIEW.name) || ''; } catch (_) {}
          const l = labbed(), dl = deskLabbed(name);
          if (dl) { takeSec($(':scope > .sd-backtest', vStrat), figsBox); figsSec.hidden = !figsBox.childElementCount; }
          const figs = $(':scope > .figs', vStrat), links = $(':scope > .qlinks', vStrat), acts = $(':scope > .sd-actions', vStrat);
          // "No Desk trades yet." stands where the figures would be (the curve's own empty note stays in the content)
          const none = [...vStrat.children].find((n) => n.classList.contains('eq-empty') && /No Desk trades/.test(n.textContent)) || null;
          if (figs || none || links || acts) {
            if (!dl) {      // a Lab strategy on the Desk: its Backtest block, taken above
              figsBox.replaceChildren(...(figs ? [figs] : none ? [el('div', { class: 'hb-row hb-row-note', text: 'No Desk trades yet.' })] : []));
              figsSec.hidden = !figsBox.childElementCount;
            }
            if (none && !figs) none.remove();
            linksBox.replaceChildren(...(links ? [links] : []));
            actsBox.replaceChildren(...(acts ? [acts] : []));
          }
          const t = $('.sd-title', vStrat), sd = $('.sd-state b', vStrat);
          const grp = groupped();
          takeResearch($(':scope > .labres', vStrat), name, grp, dl);
          figsH.textContent = grp ? (figsBox.querySelector('[data-h="Full sample"]') ? 'Full sample' : 'Combined') : l || dl ? 'Backtest' : 'Desk results';
          setupH.textContent = dl && !grp ? 'About' : 'Setup';
          if (grp) setupGroup(grp); else if (l) setupLab(l); else if (dl) takeSec($(':scope > .sd-about', vStrat), setupBox); else setup(name);
          tb.title(t ? t.textContent : 'Strategy', sd ? sd.textContent : '');
        } else if (v === 'activity') {
          tb.title('Activity', 'Every alert, order and fill');
        } else if (archived()) {
          tb.title('Archive', 'Off the Desk and kept');
        } else {
          let date = '';
          if (st && st.et_now) {
            try { date = new Date(String(st.et_now).slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }); } catch (_) {}
          }
          tb.title('Today', date);
        }
      } catch (_) { /* a repaint must never be broken by the skin */ }
      finally { syncing = false; }
    }
    const mo = new MutationObserver(sync);
    for (const n of [vToday, vStrat, vAct]) if (n) mo.observe(n, { attributes: true, attributeFilter: ['hidden'] });
    if (vStrat) mo.observe(vStrat, { childList: true });
    if (side) mo.observe(side, { childList: true });                  // the page repaints the sidebar on every refresh
    if (bulb) mo.observe(bulb, { attributes: true, attributeFilter: ['class'] });
    mo.observe(notices, { attributes: true, attributeFilter: ['hidden'] });
    const pill = $('#statusPill');      // its class gains "stale" when the desk stops answering (the page's renderMaster)
    if (pill) new MutationObserver(words).observe(pill, { attributes: true, attributeFilter: ['class'] });
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
