/* Homebase Charts — the indicator settings dialog: TradingView's per-indicator Settings, with an "Inputs" tab
   (the catalog's params, as the old small dialog drew them) and a "Style" tab (one row per plotted line: an
   indicator with no Style tab -- catalog.js's styleLineKeys -- skips straight to a single Inputs pane, same as
   the params-only dialog this replaces). Every change previews live on the chart; Cancel/×/Esc/a backdrop
   click restore it; Ok keeps it. Follows settings-dialog.js's mount(box, host) shape:
     host: {cell, uid, closeMenu(), toggleMenu(anchor, cls, fill(menuEl)), placeMenu(), commit(changed), cancel(),
            onDefaultApplied(id, payload) -- optional, so the page's indicator-defaults cache (app.js) can be
            re-synced the instant "Apply default" is clicked, the same way the drawing toolbar's Template ▾
            re-syncs drawStyleDefaults}
   The bottom-left "Template ▾" wires the generic presets store (presets.js) exactly like the drawing tools'
   own Template ▾ (app.js's drawToolbarButtons/drawingSettingsDialog): kind `indicator:<id>`, a payload of
   {params, style}, "Reset to factory settings" as this dialog's own extra menu row (presets.js' menu() supports
   it generically; it is not one of the store's three built-in actions). */
(() => {
'use strict';
const C = window.HBCatalog;
const I = window.HBIcons;
const DASH = [['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']];
const WIDTHS = [1, 2, 3, 4].map((n) => [String(n), String(n)]);
const LINE_LABEL = { vwap: { main: 'VWAP', band1: 'Band 1', band2: 'Band 2', band3: 'Band 3' },
  ema: { main: 'EMA' }, sma: { main: 'SMA' }, vwma: { main: 'VWMA' },
  adx: { adx: 'ADX', pdi: '+DI', mdi: '-DI' }, cumdelta: { main: 'Cum delta' },
  volume: { up: 'Up bars', down: 'Down bars' }, delta: { up: 'Buying (up)', down: 'Selling (down)' } };
const SHAPE_NAMES = { line: 'Line', steps: 'Steps', curved: 'Curved' };

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
  const atOpen = { params: { ...inst.params }, style: inst.style ? JSON.parse(JSON.stringify(inst.style)) : null,
    opts: inst.opts ? JSON.parse(JSON.stringify(inst.opts)) : null };
  let vals = { ...inst.params };
  let opts = inst.opts ? JSON.parse(JSON.stringify(inst.opts)) : {};          // legend, refs, refColor (catalog.js clampOpts)
  const refDefs = C.refsOf(inst.id);
  const lineKeys = C.styleLineKeys(inst.id);
  let style = inst.style ? JSON.parse(JSON.stringify(inst.style))
    : lineKeys ? C.defaultStyle(inst.id, cell.cfg.indicators.filter((x) => x.uid !== uid)) : null;
  const TABS = [];
  if (d.params.length) TABS.push({ id: 'inputs', label: 'Inputs' });         // a style-only indicator (volume, cum delta) opens on Style
  TABS.push({ id: 'style', label: 'Style' });
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
      cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? current() : x)) });
    });
  }
  /* The instance as the dialog holds it now: clamped params, its style, and its options (none left = no `opts` key). */
  function current() {
    const patch = { ...inst, params: C.clampParams(inst.id, vals) };
    if (style) patch.style = style;
    const o = C.clampOpts(inst.id, opts);
    if (o) patch.opts = o; else delete patch.opts;
    return patch;
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
    if (TABS[tab].id === 'style') pane.append(...stylePane());
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
          const on = (vals[p.key] === undefined ? p.def : vals[p.key]) === v;      // an omitted default (the timeframe) reads as it
          const b = mk('button', on ? 'on' : '', text);
          b.type = 'button';
          b.setAttribute('role', 'radio');
          b.setAttribute('aria-checked', String(on));
          b.onclick = () => { vals[p.key] = v; draw(); preview(); };
          return b;
        }));
      };
      draw();
    } else if (p.type === 'boxes') {
      return boxesEditor(p);
    } else if (p.type === 'tf') {
      // the timeframe is typed: "15m", "1h", "90s", "4h", "1D" (a bare number is minutes); blank = the chart's own bars
      ctl = mk('input', 'sw-hex');
      ctl.type = 'text';
      ctl.placeholder = 'Chart (e.g. 15m, 1h, 4h)';
      ctl.maxLength = 10;
      ctl.spellcheck = false;
      ctl.value = vals[p.key] ? C.fmtTf(vals[p.key]) : '';
      ctl.setAttribute('aria-label', p.label);
      const err = mk('div', 'dlg-err');
      err.hidden = true;
      err.setAttribute('role', 'alert');
      const take = () => {
        const t = ctl.value.trim();
        if (t === '' || /^(chart|0)$/i.test(t)) { delete vals[p.key]; ctl.value = ''; err.hidden = true; preview(); return; }
        const sec = C.parseTf(t);
        if (sec) { vals[p.key] = String(sec); ctl.value = C.fmtTf(sec); err.hidden = true; preview(); return; }
        err.textContent = 'Type a length like 15m, 1h, 4h or 1D (up to a day)';
        err.hidden = false;
        ctl.value = vals[p.key] ? C.fmtTf(vals[p.key]) : '';
      };
      ctl.onblur = take;
      ctl.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; take(); } };
      ctl.id = id;
      lab.htmlFor = id;
      row.append(lab, ctl, err);
      return row;
    } else if (p.type === 'time') {
      // No destructive re-clamp per keystroke: a value only ever REPLACES vals[p.key] once it normalises (so
      // "9", "09:", "09:3" while still typing just wait, live-previewing the moment they resolve); left
      // incomplete/bad on blur or Enter, it shows an inline error (as the Style tab's hex field does) and the
      // field snaps back to the last valid value -- never the factory default.
      ctl = mk('input', 'sw-hex');
      ctl.type = 'text';
      ctl.placeholder = 'HH:MM';
      ctl.maxLength = 5;
      ctl.value = vals[p.key];
      ctl.setAttribute('aria-label', p.label);
      const err = mk('div', 'dlg-err');
      err.hidden = true;
      err.setAttribute('role', 'alert');
      ctl.oninput = () => {
        const norm = C.normalizeHHMM(ctl.value);
        if (!norm) return;   // still typing (or unparseable so far): leave vals/err alone, no preview yet
        vals[p.key] = norm;
        err.hidden = true;
        preview();
      };
      const settle = () => {
        const norm = C.normalizeHHMM(ctl.value);
        if (norm) { vals[p.key] = norm; ctl.value = norm; err.hidden = true; preview(); return; }
        err.textContent = 'Use HH:MM, e.g. 09:30';
        err.hidden = false;
        ctl.value = vals[p.key];   // back to the last valid value, never p.def
      };
      ctl.onblur = settle;
      ctl.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; settle(); } };   // S7
      ctl.id = id;
      lab.htmlFor = id;
      row.append(lab, ctl, err);
      return row;
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

  /* ---- Session range: a list of boxes, each a window you type (ET) with its own switch and colour ---- */
  function boxesEditor(p) {
    const wrap = mk('div', 'boxes');
    const list = () => (vals[p.key] = Array.isArray(vals[p.key]) ? vals[p.key] : C.clampParams(inst.id, {})[p.key]);
    const colorOf = (b, i) => b.color || C.SESS_BOX_COLORS[i % C.SESS_BOX_COLORS.length];
    const timeBox = (b, key, i, aria) => {
      const ctl = mk('input', 'sw-hex box-time');
      ctl.type = 'text'; ctl.maxLength = 5; ctl.placeholder = 'HH:MM'; ctl.value = b[key];
      ctl.setAttribute('aria-label', `Box ${i + 1} ${aria}`);
      const take = (settle) => {
        const norm = C.normalizeHHMM(ctl.value);
        if (norm) { b[key] = norm; if (settle) ctl.value = norm; ctl.classList.remove('bad'); preview(); } else if (settle) { ctl.value = b[key]; ctl.classList.remove('bad'); }
      };
      ctl.oninput = () => take(false);
      ctl.onblur = () => take(true);
      ctl.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (!e.repeat) take(true); } };
      return ctl;
    };
    const draw = () => {
      const boxes = list();
      wrap.replaceChildren();
      boxes.forEach((b, i) => {
        const row = mk('div', 'box-row'), on = mk('input');
        on.type = 'checkbox'; on.checked = b.on !== false;
        on.setAttribute('aria-label', `Box ${i + 1} on`);
        on.onchange = () => { b.on = on.checked; preview(); };
        const name = mk('input', 'sw-hex box-name');
        name.type = 'text'; name.maxLength = 14; name.placeholder = 'Name'; name.value = b.name || '';
        name.setAttribute('aria-label', `Box ${i + 1} name`);
        name.oninput = () => { b.name = name.value; preview(); };
        const sw = button('swatch'), dot = mk('i');
        dot.style.background = colorOf(b, i);
        sw.title = 'Box colour'; sw.setAttribute('aria-label', `Box ${i + 1} colour`);
        sw.append(dot);
        sw.onclick = () => host.toggleMenu(sw, 'menu-swatch', (m) => {
          const grid = mk('div', 'sw-grid');
          for (const hex of C.SESS_BOX_COLORS.concat(C.LINE_COLORS)) {
            const c = button('sw-cell');
            c.style.background = hex; c.title = hex; c.setAttribute('aria-label', hex);
            c.onclick = () => { b.color = hex; dot.style.background = hex; host.closeMenu(); preview(); };
            grid.append(c);
          }
          m.append(grid);
        });
        const del = button('btn btn-ghost box-del', '×');
        del.title = 'Remove this box'; del.setAttribute('aria-label', `Remove box ${i + 1}`);
        del.onclick = () => { boxes.splice(i, 1); draw(); preview(); };
        row.append(on, name, timeBox(b, 'from', i, 'from'), mk('span', 'box-to', 'to'), timeBox(b, 'to', i, 'to'), sw, del);
        wrap.append(row);
      });
      const foot = mk('div', 'box-foot');
      const add = button('btn btn-ghost', '+ Add box');
      add.disabled = boxes.length >= C.SESS_BOX_MAX;
      add.onclick = () => { boxes.push({ name: '', from: '09:30', to: '11:00', on: true }); draw(); preview(); };
      foot.append(add);
      // a named session you took out comes back in one click
      for (const d0 of C.SESS_BOX_DEFAULTS) {
        if (boxes.some((x) => x.from === d0.from && x.to === d0.to)) continue;
        const chip = button('btn btn-ghost', `${d0.name} ${d0.from}-${d0.to}`);
        chip.disabled = boxes.length >= C.SESS_BOX_MAX;
        chip.onclick = () => { boxes.push({ ...d0, on: true }); draw(); preview(); };
        foot.append(chip);
      }
      wrap.append(foot, mk('div', 'set-mini box-note', 'Times are New York time. A box may cross midnight (20:00 to 00:00).'));
    };
    draw();
    return wrap;
  }

  /* ---- Style tab: a row per plotted line (visible, colour, width, dash, and under it opacity, type, axis value),
     then the reference levels of a study that has them, then the legend ---- */
  function stylePane() {
    const rows = [];
    if (lineKeys) for (const k of lineKeys) rows.push(...styleRow(k));
    if (refDefs) rows.push(mk('div', 'set-cap', 'LEVELS'), ...refRows());
    rows.push(mk('div', 'set-cap', 'LEGEND'), legendRow());
    return rows;
  }
  function setOpt(key, v) {
    if (v === undefined) delete opts[key]; else opts[key] = v;
    preview();
  }
  function legendRow() {
    const row = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl'), cb = mk('input');
    cb.type = 'checkbox';
    cb.checked = opts.legend !== false;
    cb.onchange = () => setOpt('legend', cb.checked ? undefined : false);
    name.append(cb, mk('span', '', 'Show its values in the legend'));
    row.append(name, ctl);
    return row;
  }
  /* The dashed reference levels (RSI 70 / 30 ...): each one ticked on or off, its value typed, one colour for all. */
  function refRows() {
    const rows = [], now = () => (opts.refs || refDefs).slice();
    refDefs.forEach((r0, i) => {
      const row = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
      const cur = now()[i], cb = mk('input'), num = mk('input', 'set-num');
      cb.type = 'checkbox';
      cb.checked = cur !== null;
      num.type = 'number';
      num.step = 'any';
      num.value = String(cur === null ? r0 : cur);
      num.disabled = cur === null;
      num.setAttribute('aria-label', `Level ${i + 1} value`);
      const put = () => {
        const a = now();
        const n = Number(num.value);
        a[i] = !cb.checked ? null : Number.isFinite(n) && num.value !== '' ? n : r0;
        num.disabled = !cb.checked;
        setOpt('refs', a.every((v, j) => v === refDefs[j]) ? undefined : a);
      };
      cb.onchange = put;
      num.onchange = put;
      name.append(cb, mk('span', '', `Level ${i + 1}`));
      ctl.append(num);
      row.append(name, ctl);
      rows.push(row);
    });
    const crow = mk('div', 'set-row'), cname = mk('div', 'set-name', 'Colour'), cctl = mk('div', 'set-ctl');
    const sw = button('swatch'), dot = mk('i');
    dot.style.background = opts.refColor || '#787B86';
    sw.title = 'Level colour';
    sw.setAttribute('aria-label', 'Level colour');
    sw.append(dot);
    sw.onclick = () => host.toggleMenu(sw, 'menu-swatch', (m) => {
      const grid = mk('div', 'sw-grid');
      for (const hex of C.LINE_COLORS.concat(['#089981', '#F23645', '#787B86', '#9598A1', '#FFFFFF', '#000000'])) {
        const b = button('sw-cell');
        b.style.background = hex;
        b.title = hex;
        b.setAttribute('aria-label', hex);
        b.onclick = () => { dot.style.background = hex; setOpt('refColor', hex); };
        grid.append(b);
      }
      m.append(grid);
    });
    cctl.append(sw);
    crow.append(cname, cctl);
    rows.push(crow);
    return rows;
  }
  function styleRow(key) {
    const line = style[key], row = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
    const colorOnly = C.styleControls(inst.id) === 'color';        // volume / delta: a colour (and its opacity), no width or dash
    const cb = mk('input');
    cb.type = 'checkbox';
    cb.checked = line.visible !== false;
    cb.onchange = () => { line.visible = cb.checked; preview(); };
    const own = C.TA_BY_ID[inst.id] && C.TA_BY_ID[inst.id].lines.find((l) => l.part === key);
    name.append(cb, mk('span', '', (LINE_LABEL[inst.id] || {})[key] || (own && own.label) || key));
    // one row a line: colour (its opacity is in the colour's popover), width, style, and a "more" for the rest
    const sw = button('swatch'), i = mk('i');
    i.style.background = C.lineColor(line);
    sw.title = `${name.textContent} colour and opacity`;
    sw.setAttribute('aria-label', sw.title);
    sw.setAttribute('aria-haspopup', 'dialog');
    sw.append(i);
    sw.onclick = () => swatchMenu(sw, key, i);
    ctl.append(sw);
    if (!colorOnly) {
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
      ctl.append(width, dashSel);
    }
    const sub = mk('div', 'set-sub');
    sub.hidden = true;
    if (colorOnly) { row.append(name, ctl); return [row]; }
    const more = button('btn btn-ghost set-more');
    more.append(mk('span', 'icw'));
    more.firstChild.innerHTML = I.ellipsis || '…';
    more.title = 'More: line type, value on the axis';
    more.setAttribute('aria-label', `${name.textContent}: more`);
    more.setAttribute('aria-expanded', 'false');
    more.onclick = () => { sub.hidden = !sub.hidden; more.setAttribute('aria-expanded', String(!sub.hidden)); };
    ctl.append(more);
    const shape = mk('select', 'set-select');
    shape.setAttribute('aria-label', `${name.textContent} type`);
    for (const sh of C.SHAPES) { const o = mk('option', '', SHAPE_NAMES[sh]); o.value = sh; shape.append(o); }
    shape.value = line.shape || (own && own.step ? 'steps' : 'line');
    shape.onchange = () => { line.shape = shape.value; preview(); };
    const tag = mk('input');
    tag.type = 'checkbox';
    tag.checked = line.tag == null ? !(own && own.tag === false) : line.tag;
    tag.setAttribute('aria-label', `${name.textContent} value on the price axis`);
    tag.onchange = () => { line.tag = tag.checked; preview(); };
    const tl = mk('label', 'set-mini');
    tl.append(tag, document.createTextNode(' Value on the price axis'));
    sub.append(mk('span', 'set-mini', 'Type'), shape, tl);
    row.append(name, ctl);
    return [row, sub];
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
      const opRow = mk('div', 'sw-row'), op = mk('input'), pct = mk('span', 'sw-pct');
      op.type = 'range'; op.min = '10'; op.max = '100'; op.step = '5';
      op.setAttribute('aria-label', 'Opacity');
      const base = C.defaultStyle(inst.id, [])[key].alpha;       // volume and delta start half see-through; the rest solid
      op.oninput = () => {
        const a = Number(op.value);
        if (a >= 100 && base == null) delete style[key].alpha; else style[key].alpha = a;
        pct.textContent = `${a}%`;
        dot.style.background = C.lineColor(style[key]);
        preview();
      };
      opRow.append(mk('span', '', 'Opacity'), op, pct);
      const hexRow = mk('div', 'sw-row'), hex = mk('input', 'sw-hex');
      hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
      hex.setAttribute('aria-label', 'Hex colour');
      const takeHex = () => {
        const v = hex.value.trim();
        if (!/^#[0-9A-Fa-f]{6}$/.test(v)) { err.textContent = 'Use #RRGGBB'; err.hidden = false; return; }
        err.hidden = true;
        style[key].color = v; dot.style.background = v; sync(); preview();
      };
      hex.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; takeHex(); } };   // S7
      hex.onchange = takeHex;
      hexRow.append(hex);
      m.append(grid, opRow, hexRow, err);
      op.value = String(style[key].alpha == null ? 100 : style[key].alpha);
      pct.textContent = `${op.value}%`;
      function sync() {
        const cur = style[key].color;
        for (const [x, b] of picks) b.classList.toggle('on', x.toLowerCase() === cur.toLowerCase());
        if (document.activeElement !== hex) hex.value = cur;
      }
      sync();
      (m.querySelector('.sw-cell.on') || picks[0][1]).focus();
    });
  }

  /* Reset to factory settings: back to the catalog's own defaults, not atOpen (which is whatever the instance
     held when the dialog opened -- possibly already a saved/default preset). Params -> clampParams({}) fills
     every key with its catalog def; style -> a fresh defaultStyle (siblings excludes this instance, same as a
     brand-new instance's colour pick would if it were the only one on the chart). */
  function resetToFactory() {
    vals = C.clampParams(inst.id, {});
    opts = {};
    if (lineKeys) style = C.defaultStyle(inst.id, cell.cfg.indicators.filter((x) => x.uid !== uid));
    renderPane();
    preview();
  }

  const cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-primary', 'OK'), grow = mk('span', 'grow');
  const tpl = button('btn btn-ghost tpl-btn'), chev = mk('span', 'icw sm');
  chev.innerHTML = I.chevron;
  tpl.append(mk('span', '', 'Template'), chev);
  tpl.setAttribute('aria-haspopup', 'menu');
  tpl.onclick = () => window.HBPresets.menu(host, tpl, {
    kind: `indicator:${inst.id}`,
    current: () => ({ params: vals, style }),
    apply(payload, { isDefault }) {
      const clean = C.sanitizePreset(inst.id, payload);
      vals = clean.params;
      if (lineKeys) style = clean.style;
      renderPane();
      preview();
      if (isDefault && host.onDefaultApplied) host.onDefaultApplied(inst.id, clean);
    },
    extra: [{ label: 'Reset to factory settings', onclick: resetToFactory }],
  });
  cancel.onclick = () => host.cancel();
  ok.onclick = () => {
    flush();
    done = true;
    const patch = current();
    cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? patch : x)) });
    host.commit(JSON.stringify(patch.params) !== JSON.stringify(atOpen.params) || JSON.stringify(style) !== JSON.stringify(atOpen.style)
      || JSON.stringify(patch.opts || null) !== JSON.stringify(atOpen.opts));
  };
  foot.append(tpl, grow, cancel, ok);

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
      if (atOpen.opts) patch.opts = atOpen.opts; else delete patch.opts;
      cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? patch : x)) });
    },
  };
}

window.HBIndicatorSettings = { mount };
})();
