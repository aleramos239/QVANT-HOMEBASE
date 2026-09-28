/* Homebase Charts — the indicator settings dialog: TradingView's per-indicator Settings, with an "Inputs" tab
   (the catalog's params, as the old small dialog drew them) and a "Style" tab (one row per plotted line: an
   indicator with no Style tab -- catalog.js's styleLineKeys -- skips straight to a single Inputs pane, same as
   the params-only dialog this replaces). Every change previews live on the chart; Cancel/×/Esc/a backdrop
   click restore it; Ok keeps it. Follows settings-dialog.js's mount(box, host) shape:
     host: {cell, uid, closeMenu(), toggleMenu(anchor, cls, fill(menuEl)), placeMenu(), commit(changed), cancel()}
   A bottom-left "Template ▾" spot is left for a parallel branch's generic presets store -- not built here. */
(() => {
'use strict';
const C = window.HBCatalog;
const DASH = [['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']];
const WIDTHS = [1, 2, 3, 4].map((n) => [String(n), String(n)]);
const LINE_LABEL = { vwap: { main: 'VWAP', band1: 'Band 1', band2: 'Band 2', band3: 'Band 3' },
  ema: { main: 'EMA' }, sma: { main: 'SMA' }, vwma: { main: 'VWMA' },
  adx: { adx: 'ADX', pdi: '+DI', mdi: '-DI' }, cumdelta: { main: 'Cum delta' } };

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }

function mount(box, host) {
  const { cell, uid } = host;
  const inst = cell.cfg.indicators.find((x) => x.uid === uid), d = inst && C.def(inst.id);
  if (!inst || !d) return { revert() {} };
  const atOpen = { params: { ...inst.params }, style: inst.style ? JSON.parse(JSON.stringify(inst.style)) : null };
  let vals = { ...inst.params };
  const lineKeys = C.styleLineKeys(inst.id);
  let style = inst.style ? JSON.parse(JSON.stringify(inst.style))
    : lineKeys ? C.defaultStyle(inst.id, cell.cfg.indicators.filter((x) => x.uid !== uid)) : null;
  const TABS = [{ id: 'inputs', label: 'Inputs' }];
  if (lineKeys) TABS.push({ id: 'style', label: 'Style' });
  let tab = 0, done = false, raf = 0;

  const body = mk('div', 'set-body'), tabsEl = mk('div', 'set-tabs'), pane = mk('div', 'set-pane'), foot = mk('div', 'set-foot');
  tabsEl.setAttribute('role', 'tablist');
  pane.setAttribute('role', 'tabpanel');
  tabsEl.hidden = TABS.length < 2;   // an Inputs-only indicator (e.g. footprint): no point showing a lone tab
  body.append(tabsEl, pane);
  box.append(body, foot);
  pane.addEventListener('scroll', () => host.closeMenu());

  function preview() {
    if (raf || done) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (done) return;
      const params = C.clampParams(inst.id, vals);
      const patch = { ...inst, params };
      if (style) patch.style = style;
      cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? patch : x)) });
    });
  }
  function flush() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

  function renderTabs() {
    tabsEl.replaceChildren(...TABS.map((t, i) => {
      const b = button('set-tab' + (i === tab ? ' active' : ''), t.label);
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(i === tab));
      b.onclick = () => { if (tab !== i) { tab = i; renderTabs(); renderPane(); } };
      return b;
    }));
  }

  function renderPane() {
    host.closeMenu();
    pane.replaceChildren();
    if (TABS[tab].id === 'style') pane.append(...lineKeys.map(styleRow));
    else pane.append(...d.params.map(inputRow));
    pane.scrollTop = 0;
  }

  /* ---- Inputs tab: one row per catalog param (bool / choice / time / number) ---- */
  function inputRow(p) {
    const row = mk('div', 'field'), id = `is-${uid}-${p.key}`, lab = mk('label', '', p.label);
    let ctl;
    if (p.type === 'bool') {
      ctl = mk('input');
      ctl.type = 'checkbox';
      ctl.checked = !!vals[p.key];
      ctl.onchange = () => { vals[p.key] = ctl.checked; preview(); };
    } else if (p.type === 'choice') {
      ctl = mk('div', 'seg');
      ctl.setAttribute('role', 'radiogroup');
      ctl.setAttribute('aria-label', p.label);
      const draw = () => {
        ctl.replaceChildren(...p.choices.map(([v, text]) => {
          const b = mk('button', vals[p.key] === v ? 'on' : '', text);
          b.type = 'button';
          b.setAttribute('role', 'radio');
          b.setAttribute('aria-checked', String(vals[p.key] === v));
          b.onclick = () => { vals[p.key] = v; draw(); preview(); };
          return b;
        }));
      };
      draw();
    } else if (p.type === 'time') {
      ctl = mk('input', 'sw-hex');
      ctl.type = 'text';
      ctl.placeholder = 'HH:MM';
      ctl.maxLength = 5;
      ctl.value = vals[p.key];
      ctl.setAttribute('aria-label', p.label);
      ctl.oninput = () => { vals[p.key] = ctl.value; preview(); };
      ctl.onblur = () => { ctl.value = vals[p.key] = C.clampParams(inst.id, vals)[p.key]; };   // snaps to HH:MM or the default
    } else {
      ctl = mk('input', 'set-num');
      ctl.type = 'number';
      ctl.min = String(p.min); ctl.max = String(p.max); ctl.step = String(p.step || 1);
      ctl.value = String(vals[p.key]);
      ctl.setAttribute('aria-label', p.label);
      ctl.oninput = () => { if (ctl.value !== '') { vals[p.key] = ctl.value; preview(); } };
      ctl.onchange = () => { ctl.value = String(C.clampParams(inst.id, vals)[p.key]); };   // shows the clamped value
    }
    ctl.id = id;
    lab.htmlFor = id;
    row.append(lab, ctl);
    return row;
  }

  /* ---- Style tab: one row per plotted line -- visible, colour swatch, width, dash ---- */
  function styleRow(key) {
    const line = style[key], row = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
    const cb = mk('input');
    cb.type = 'checkbox';
    cb.checked = line.visible !== false;
    cb.onchange = () => { line.visible = cb.checked; preview(); };
    name.append(cb, mk('span', '', (LINE_LABEL[inst.id] || {})[key] || key));
    const sw = button('swatch'), i = mk('i');
    i.style.background = line.color;
    sw.title = `${name.textContent} colour`;
    sw.setAttribute('aria-label', sw.title);
    sw.setAttribute('aria-haspopup', 'dialog');
    sw.append(i);
    sw.onclick = () => swatchMenu(sw, key, i);
    const width = mk('select', 'set-select');
    width.setAttribute('aria-label', `${name.textContent} width`);
    for (const [v, text] of WIDTHS) { const o = mk('option', '', text); o.value = v; width.append(o); }
    width.value = String(line.width);
    width.onchange = () => { line.width = Number(width.value); preview(); };
    const dashSel = mk('select', 'set-select');
    dashSel.setAttribute('aria-label', `${name.textContent} line style`);
    for (const [v, text] of DASH) { const o = mk('option', '', text); o.value = v; dashSel.append(o); }
    dashSel.value = line.dash;
    dashSel.onchange = () => { line.dash = dashSel.value; preview(); };
    ctl.append(sw, width, dashSel);
    row.append(name, ctl);
    return row;
  }

  /* A small colour-only popover (no opacity/theme-default: an indicator line is always a plain hex). */
  function swatchMenu(anchor, key, dot) {
    host.toggleMenu(anchor, 'menu-swatch', (m) => {
      const grid = mk('div', 'sw-grid'), err = mk('div', 'sw-err'), picks = [];
      err.hidden = true;
      for (const hex of C.LINE_COLORS.concat(['#089981', '#F23645', '#787B86', '#9598A1', '#FFFFFF', '#000000'])) {
        const b = button('sw-cell');
        b.style.background = hex;
        b.title = hex;
        b.setAttribute('aria-label', hex);
        b.onclick = () => { style[key].color = hex; dot.style.background = hex; sync(); preview(); };
        picks.push([hex, b]);
        grid.append(b);
      }
      const hexRow = mk('div', 'sw-row'), hex = mk('input', 'sw-hex');
      hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
      hex.setAttribute('aria-label', 'Hex colour');
      const takeHex = () => {
        const v = hex.value.trim();
        if (!/^#[0-9A-Fa-f]{6}$/.test(v)) { err.textContent = 'Use #RRGGBB'; err.hidden = false; return; }
        err.hidden = true;
        style[key].color = v; dot.style.background = v; sync(); preview();
      };
      hex.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); takeHex(); } };
      hex.onchange = takeHex;
      hexRow.append(hex);
      m.append(grid, hexRow, err);
      function sync() {
        const cur = style[key].color;
        for (const [x, b] of picks) b.classList.toggle('on', x.toLowerCase() === cur.toLowerCase());
        if (document.activeElement !== hex) hex.value = cur;
      }
      sync();
      (m.querySelector('.sw-cell.on') || picks[0][1]).focus();
    });
  }

  const cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-primary', 'OK'), grow = mk('span', 'grow');
  // Task 5: a parallel branch is building a generic presets store (/api/presets/<kind>, presets.js) for a
  // Template ▾ menu here -- deliberately not built in this change.
  const tplSpot = mk('span', 'ind-tpl-spot', 'Template ▾');
  tplSpot.title = 'Reserved for the presets store (/api/presets/<kind>, presets.js) -- not built in this change';
  cancel.onclick = () => host.cancel();
  ok.onclick = () => {
    flush();
    done = true;
    const params = C.clampParams(inst.id, vals);
    const patch = { ...inst, params };
    if (style) patch.style = style;
    cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? patch : x)) });
    host.commit(JSON.stringify(params) !== JSON.stringify(atOpen.params) || JSON.stringify(style) !== JSON.stringify(atOpen.style));
  };
  foot.append(tplSpot, grow, cancel, ok);

  renderTabs();
  renderPane();

  return {
    revert() {
      if (done) return;
      done = true;
      flush();
      const now = cell.cfg.indicators.some((x) => x.uid === uid);
      if (!now) return;   // removed meanwhile (e.g. the legend's × while the dialog was open)
      const patch = { ...inst, params: atOpen.params };
      if (atOpen.style) patch.style = atOpen.style; else delete patch.style;
      cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? patch : x)) });
    },
  };
}

window.HBIndicatorSettings = { mount };
})();
