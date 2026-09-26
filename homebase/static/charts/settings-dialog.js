/* Homebase Charts — the chart Settings dialog (TradingView's Settings, for what applies to our charts): a
   column of tabs, rows of controls, the swatch popover and a footer. Every change previews live on the
   selected chart; Cancel, ×, Esc or a backdrop click put every chart back as it was when the dialog opened;
   Ok keeps the changes. Browser only: the model is HBSettings (settings.js); the page (app.js) owns the
   dialog frame and the menus and hands them over as `host`:
     {cell, cells(), toggleMenu(anchor, cls, fill(menuEl)), closeMenu(), placeMenu(), commit(changed), cancel()} */
(() => {
'use strict';
const S = window.HBSettings, I = window.HBIcons;
const LINE = [['solid', 'Solid'], ['dotted', 'Dotted'], ['dashed', 'Dashed']];
const PRECISION = [['', 'Default'], ...[0, 1, 2, 3, 4, 5, 6].map((n) => [String(n), n ? (10 ** -n).toFixed(n) : '1'])];
const FONT_SIZES = [10, 11, 12, 13, 14, 15, 16].map((n) => [String(n), String(n)]);
const asNumber = (v) => Number(v);
const asPrecision = (v) => (v === '' ? null : Number(v));

/* The tabs, in TradingView's order. A row: {label, check?: key (a checkbox before the label), colors?: [[key,
   what]] (a swatch each), select?: {key, choices: [[value, text]], parse?}, number?: {key, min, max, unit?}}.
   Task 7 inserts Status line and Scales and lines, and the hours-background row; Task 8 adds Events. */
const TABS = [
  { id: 'symbol', label: 'Symbol', icon: 'candles', sections: [
    ['CANDLES', [
      { label: 'Colour bars based on previous close', check: 'prevClose' },
      { label: 'Body', check: 'body', colors: [['bodyUp', 'up'], ['bodyDown', 'down']] },
      { label: 'Borders', check: 'borders', colors: [['borderUp', 'up'], ['borderDown', 'down']] },
      { label: 'Wick', check: 'wick', colors: [['wickUp', 'up'], ['wickDown', 'down']] },
    ]],
    ['DATA', [
      { label: 'Precision', select: { key: 'precision', choices: PRECISION, parse: asPrecision } },
      { label: 'Timezone', select: { key: 'timezone', choices: S.TIMEZONES.map(([k, text]) => [k, text]) } },
    ]],
  ] },
  { id: 'canvas', label: 'Canvas', icon: 'paintbrush', sections: [
    ['CHART BASIC STYLES', [
      { label: 'Background', colors: [['bg', '']] },
      { label: 'Vert grid lines', check: 'vertGrid', colors: [['vertGridColor', '']] },
      { label: 'Horz grid lines', check: 'horzGrid', colors: [['horzGridColor', '']] },
      { label: 'Crosshair', colors: [['crossColor', '']], select: { key: 'crossStyle', choices: LINE },
        number: { key: 'crossWidth', min: 1, max: 4 } },
      { label: 'Watermark', check: 'watermark', colors: [['watermarkColor', '']] },
    ]],
    ['SCALES', [
      { label: 'Text colour', colors: [['scaleText', '']] },
      { label: 'Text size', select: { key: 'scaleFont', choices: FONT_SIZES, parse: asNumber } },
      { label: 'Lines colour', colors: [['scaleLines', '']] },
    ]],
  ] },
];

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }

function mount(box, host) {
  const cell = host.cell;
  const atOpen = new Map(host.cells().map((c) => [c, c.settings()]));   // Cancel puts every chart back
  let work = S.normalize(cell.settings()), tab = 0, done = false, raf = 0;
  const swatches = new Map();   // colour key -> the <i> inside its swatch button

  const body = mk('div', 'set-body'), tabs = mk('div', 'set-tabs'), pane = mk('div', 'set-pane'), foot = mk('div', 'set-foot');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-orientation', 'vertical');
  pane.setAttribute('role', 'tabpanel');
  body.append(tabs, pane);
  box.append(body, foot);
  pane.addEventListener('scroll', () => host.closeMenu());   // a popover never floats away from its swatch

  /* Live preview on the selected chart, at most once a frame (a dragged opacity slider fires per pixel). */
  function preview() {
    if (raf || done) return;
    raf = requestAnimationFrame(() => { raf = 0; if (!done) cell.setSettings(S.overrides(work)); });
  }
  function flush() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }
  function set(key, v) { work = S.normalize({ ...work, [key]: v }); preview(); paint(); }
  /* What each colour field shows: its value, or the theme's colour while it follows the theme. */
  const shown = () => S.resolve(S.overrides(work), cell.P || {});
  function paint() { const r = shown(); for (const [k, i] of swatches) i.style.background = r[k] || ''; }

  function renderTabs() {
    const had = tabs.contains(document.activeElement);
    tabs.replaceChildren(...TABS.map((t, i) => {
      const b = button('set-tab' + (i === tab ? ' active' : '')), ic = mk('span', 'icw');
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(i === tab));
      ic.innerHTML = I[t.icon] || '';   // our own static SVG strings
      b.append(ic, mk('span', '', t.label));
      b.onclick = () => { if (tab !== i) { tab = i; renderTabs(); renderPane(); } };
      return b;
    }));
    if (had) tabs.querySelector('.active').focus();
  }

  function renderPane() {
    host.closeMenu();
    swatches.clear();
    pane.replaceChildren(...TABS[tab].sections.flatMap(([cap, rows]) => [mk('div', 'set-cap', cap), ...rows.map(row)]));
    pane.scrollTop = 0;
    paint();
  }

  function row(r) {
    const el = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
    if (r.check) {
      const cb = mk('input');
      cb.type = 'checkbox';
      cb.checked = !!work[r.check];
      cb.onchange = () => set(r.check, cb.checked);
      name.append(cb);
    }
    name.append(mk('span', '', r.label));
    for (const [key, what] of r.colors || []) {
      const b = button('swatch'), i = mk('i'), tip = `${r.label}${what ? ` ${what}` : ''} colour`;
      b.title = tip;
      b.setAttribute('aria-label', tip);
      b.setAttribute('aria-haspopup', 'dialog');
      b.append(i);
      swatches.set(key, i);
      b.onclick = () => swatchMenu(b, key);
      ctl.append(b);
    }
    if (r.select) {
      const { key, choices, parse } = r.select, s = mk('select', 'set-select');
      s.setAttribute('aria-label', r.label);
      for (const [v, text] of choices) { const o = mk('option', '', text); o.value = v; s.append(o); }
      s.value = work[key] == null ? '' : String(work[key]);
      s.onchange = () => set(key, parse ? parse(s.value) : s.value);
      ctl.append(s);
    }
    if (r.number) {
      const { key, min, max, unit } = r.number, n = mk('input', 'set-num');
      n.type = 'number'; n.min = String(min); n.max = String(max); n.step = '1';
      n.value = String(work[key]);
      n.setAttribute('aria-label', r.label);
      n.oninput = () => { if (n.value !== '') set(key, Number(n.value)); };
      n.onchange = () => { n.value = String(work[key]); };   // shows the clamped value
      ctl.append(n);
      if (unit) ctl.append(mk('span', 'set-unit', unit));
    }
    el.append(name, ctl);
    return el;
  }

  /* The swatch popover (menu styling): the palette, an opacity slider, a #RRGGBB field and "Default" (back to
     following the theme / the default). Picking a palette colour keeps the opacity. */
  function swatchMenu(anchor, key) {
    host.toggleMenu(anchor, 'menu-swatch', (m) => {
      const cur = () => shown()[key];
      const grid = mk('div', 'sw-grid'), err = mk('div', 'sw-err'), picks = [];
      err.hidden = true;
      err.setAttribute('role', 'alert');
      for (const hex of S.PALETTE.flat()) {
        const b = button('sw-cell');
        b.style.background = hex;
        b.title = hex;
        b.setAttribute('aria-label', hex);
        b.onclick = () => { set(key, S.withAlpha(hex, S.alphaOf(cur()))); sync(); };
        picks.push([hex, b]);
        grid.append(b);
      }
      const opRow = mk('div', 'sw-row'), op = mk('input'), pct = mk('span', 'sw-pct');
      op.type = 'range'; op.min = '0'; op.max = '100'; op.step = '1';
      op.setAttribute('aria-label', 'Opacity');
      op.oninput = () => { set(key, S.withAlpha(S.hexOf(cur()), Number(op.value) / 100)); sync(); };
      opRow.append(mk('span', '', 'Opacity'), op, pct);
      const hexRow = mk('div', 'sw-row'), hex = mk('input', 'sw-hex'), def = button('sw-default', 'Default');
      hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
      hex.setAttribute('aria-label', 'Hex colour');
      const takeHex = () => {
        const v = hex.value.trim();
        if (!/^#[0-9A-Fa-f]{6}$/.test(v)) { err.textContent = 'Use #RRGGBB'; err.hidden = false; return; }
        err.hidden = true;
        set(key, S.withAlpha(v, S.alphaOf(cur())));
        sync();
      };
      hex.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); takeHex(); } };
      hex.onchange = takeHex;
      def.onclick = () => { err.hidden = true; set(key, null); sync(); };
      hexRow.append(hex, def);
      m.append(grid, opRow, hexRow, err);
      function sync() {   // the popover shows the field's colour now
        const c = cur(), h = S.hexOf(c), a = Math.round(S.alphaOf(c) * 100);
        for (const [x, b] of picks) b.classList.toggle('on', x === h);
        op.value = String(a);
        pct.textContent = `${a}%`;
        if (document.activeElement !== hex) hex.value = h || '';
      }
      sync();
      (m.querySelector('.sw-cell.on') || picks[0][1]).focus();
    });
  }

  /* ---- footer ---- */
  const grow = mk('span', 'grow'), cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-solid', 'Ok');
  cancel.onclick = () => host.cancel();
  ok.onclick = () => {
    flush();
    cell.setSettings(S.overrides(work));
    done = true;
    host.commit(host.cells().some((c) => JSON.stringify(c.settings()) !== JSON.stringify(atOpen.get(c) || {})));
  };
  foot.append(grow, cancel, ok);

  renderTabs();
  renderPane();
  tabs.querySelector('.active').focus();

  return {
    /* Cancel, ×, Esc, a backdrop click: every chart back to its settings at open. After Ok: nothing. */
    revert() {
      if (done) return;
      done = true;
      flush();
      const now = host.cells();
      for (const [c, s] of atOpen) if (now.includes(c)) c.setSettings(s);
    },
  };
}

window.HBSettingsDialog = { mount, TABS };
})();
