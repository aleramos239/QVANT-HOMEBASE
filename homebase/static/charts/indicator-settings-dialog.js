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
const VWAP_NEW_COLORS = ['#2962FF', '#FF6D00', '#00897B', '#E91E63', '#00BCD4'];
const VWAP_OWN = new Set(['anchor', 'customTime', 'more']);   // the VWAP's lines editor draws these
const VWAP_ANCHOR_NAMES = [['eth', 'Session (6 pm)'], ['rth', 'RTH (9:30 am)'], ['custom', 'Custom time'], ['week', 'Week'], ['month', 'Month']];
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
  const atOpen = { params: JSON.parse(JSON.stringify(inst.params)), style: inst.style ? JSON.parse(JSON.stringify(inst.style)) : null,
    opts: inst.opts ? JSON.parse(JSON.stringify(inst.opts)) : null };
  let vals = JSON.parse(JSON.stringify(inst.params));   // deep: a VWAP's extra lines are edited in place
  let opts = inst.opts ? JSON.parse(JSON.stringify(inst.opts)) : {};          // legend, refs, refColor (catalog.js clampOpts)
  const refDefs = C.refsOf(inst.id);
  const lineKeys = C.styleLineKeys(inst.id);
  let style = inst.style ? JSON.parse(JSON.stringify(inst.style))
    : lineKeys ? C.defaultStyle(inst.id, cell.cfg.indicators.filter((x) => x.uid !== uid)) : null;
  // a style saved before a colour row was added to this indicator lacks that key: it takes the default colour
  if (style && lineKeys) { const fresh = C.defaultStyle(inst.id, []); for (const k of lineKeys) if (!style[k]) style[k] = fresh[k]; }
  const TABS = [];
  const guide = window.HBGuide && window.HBGuide.get(inst.id);
  if (d.params.length) TABS.push({ id: 'inputs', label: 'Inputs' });         // a style-only indicator (volume, cum delta) opens on Style
  // a Style tab only when there is something to style: lines or colours, reference levels, or legend values (the order-flow overlays have none of the last)
  if (lineKeys || refDefs || C.hasLegend(inst.id)) TABS.push({ id: 'style', label: 'Style' });
  if (guide) TABS.push({ id: 'guide', label: 'How to read' });
  const first = TABS.findIndex((t) => t.id === host.tab);                   // the legend's "?" opens on the guide
  let tab = first < 0 ? 0 : first, done = false, raf = 0;

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
    else if (TABS[tab].id === 'guide') pane.append(guidePane());
    else {
      const rows = d.params.filter((p) => !(inst.id === 'vwap' && VWAP_OWN.has(p.key))).map(inputRow);
      if (inst.id === 'vwap') rows.unshift(vwapLinesEditor());   // its lines (anchor, time, colour) first; the bands follow
      pane.append(...rows);
    }
    pane.scrollTop = 0;
  }

  /* ---- VWAP: its lines, one row each: anchor, its time when custom, colour. The first line carries the bands. ---- */
  function vwapLinesEditor() {
    const wrap = mk('div', 'vlines');
    const more = () => (vals.more = Array.isArray(vals.more) ? vals.more : []);
    if (!style) style = C.defaultStyle('vwap', cell.cfg.indicators.filter((x) => x.uid !== uid));
    const palette = C.LINE_COLORS.concat(['#9C27B0', '#089981', '#F23645', '#787B86', '#FFFFFF', '#000000']);
    const colourOf = (i) => (i === 0 ? C.lineColor(style.main) : (more()[i - 1].color || VWAP_NEW_COLORS[(i - 1) % VWAP_NEW_COLORS.length]));
    const setColour = (i, hex) => {
      if (i === 0) { for (const k of ['main', 'band1', 'band2', 'band3']) if (style[k]) style[k].color = hex; } else more()[i - 1].color = hex;
    };
    const draw = () => {
      host.closeMenu();
      const items = [mk('label', 'vl-head', 'VWAP lines: each restarts at its own time every day')];
      for (let i = 0; i <= more().length; i++) {
        const obj = i === 0 ? vals : more()[i - 1];
        const item = mk('div', 'vl-item'), row = mk('div', 'vl-row'), err = mk('div', 'dlg-err');
        err.hidden = true; err.setAttribute('role', 'alert');
        if (i > 0) {
          const on = mk('input'); on.type = 'checkbox'; on.checked = obj.on !== false;
          on.setAttribute('aria-label', `Line ${i + 1} on`);
          on.onchange = () => { obj.on = on.checked; preview(); };
          row.append(on);
        } else row.append(mk('span', 'vl-first', '1'));
        const sel = mk('select', 'set-select vl-anchor');
        sel.setAttribute('aria-label', `Line ${i + 1} anchor`);
        for (const [v, text] of VWAP_ANCHOR_NAMES) { const o = mk('option', '', text); o.value = v; sel.append(o); }
        sel.value = obj.anchor || 'eth';
        sel.onchange = () => { obj.anchor = sel.value; if (!obj.customTime) obj.customTime = '09:30'; preview(); draw(); };
        row.append(sel);
        if ((obj.anchor || 'eth') === 'custom') {
          // No destructive re-clamp per keystroke: a value replaces the stored one only once it normalises; left
          // bad on blur or Enter, an inline error shows and the box snaps back to the last valid time.
          const tin = mk('input', 'sw-hex vl-time');
          tin.type = 'text'; tin.placeholder = 'HH:MM'; tin.maxLength = 5; tin.value = obj.customTime || '09:30';
          tin.setAttribute('aria-label', `Line ${i + 1} time (ET)`);
          tin.oninput = () => { const n = C.normalizeHHMM(tin.value); if (!n) return; obj.customTime = n; err.hidden = true; preview(); };
          const settle = () => {
            const n = C.normalizeHHMM(tin.value);
            if (n) { obj.customTime = n; tin.value = n; err.hidden = true; preview(); return; }
            err.textContent = 'Use HH:MM, e.g. 09:30'; err.hidden = false; tin.value = obj.customTime;
          };
          tin.onblur = settle;
          tin.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; settle(); } };
          row.append(tin);
        }
        if (i > 0) {   // the bands (set below, once) follow every line that has this on
          const bd = mk('input'); bd.type = 'checkbox'; bd.checked = obj.bands !== false;
          bd.setAttribute('aria-label', `Line ${i + 1} bands`); bd.title = `Line ${i + 1}: draw the bands around it`;
          bd.onchange = () => { if (bd.checked) delete obj.bands; else obj.bands = false; preview(); };
          const bl = mk('label', 'vl-bands'); bl.append(bd, mk('span', '', 'Bands'));
          row.append(bl);
        }
        const sw = button('swatch'), dot = mk('i');
        dot.style.background = colourOf(i);
        sw.title = `Line ${i + 1} colour` + (i === 0 ? ' (its bands follow)' : '');
        sw.setAttribute('aria-label', `Line ${i + 1} colour`);
        sw.append(dot);
        sw.onclick = () => host.toggleMenu(sw, 'menu-swatch', (m) => {
          const grid = mk('div', 'sw-grid');
          for (const hex of palette) {
            const c = button('sw-cell');
            c.style.background = hex; c.title = hex; c.setAttribute('aria-label', hex);
            c.onclick = () => { setColour(i, hex); dot.style.background = hex; host.closeMenu(); preview(); };
            grid.append(c);
          }
          m.append(grid);
        });
        row.append(sw);
        if (i > 0) {
          const rm = button('vl-rm', '×');
          rm.title = `Remove line ${i + 1}`; rm.setAttribute('aria-label', rm.title);
          rm.onclick = () => { more().splice(i - 1, 1); if (!more().length) delete vals.more; preview(); draw(); };
          row.append(rm);
        }
        item.append(row, err);
        items.push(item);
      }
      if (more().length < C.VWAP_MORE_MAX) {
        const add = button('btn btn-ghost vl-add', '+ Add line');
        add.title = 'A second VWAP line in this indicator, with its own anchor and colour';
        add.onclick = () => {
          const used = new Set([vals.anchor === 'custom' ? vals.customTime : vals.anchor, ...more().map((l) => (l.anchor === 'custom' ? l.customTime : l.anchor))]);
          const next = ['09:30', '18:00', '02:00', '16:00'].find((h) => !used.has(h)) || '09:30';
          more().push({ anchor: 'custom', customTime: next, on: true, color: VWAP_NEW_COLORS[more().length % VWAP_NEW_COLORS.length] });
          preview(); draw();
        };
        items.push(add);
      }
      wrap.replaceChildren(...items);
    };
    draw();
    return wrap;
  }

  /* ---- How to read: the plain-words guide (guide-*.js) and, when it has one, what this chart shows right now ---- */
  function guidePane() {
    const wrap = mk('div', 'guide');
    wrap.append(mk('p', 'guide-what', guide.what));
    const now = window.HBStatus && cell.statusFacts ? (() => { try { return window.HBStatus.of(inst, cell.statusFacts()); } catch (_) { return null; } })() : null;
    if (now) wrap.append(mk('p', 'guide-now ' + now.tone, `Right now: ${now.text}`));
    for (const [key, title] of [['see', 'What you see'], ['read', 'How to read it'], ['use', 'How to use it']]) {
      wrap.append(mk('h4', 'guide-h', title));
      const ul = mk('ul', 'guide-list');
      for (const t of guide[key]) ul.append(mk('li', '', t));
      wrap.append(ul);
    }
    if (guide.watch) wrap.append(mk('p', 'guide-watch', guide.watch));
    return wrap;
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
      ctl = mk('select', 'set-select ch-select');       // a dropdown, never a row of pills: long names fit the card
      ctl.id = id;
      lab.htmlFor = id;
      ctl.setAttribute('aria-label', p.label);
      for (const [v, text] of p.choices) { const o = mk('option', '', text); o.value = v; ctl.append(o); }
      ctl.value = vals[p.key] === undefined ? p.def : vals[p.key];       // an omitted default (the timeframe) reads as it
      ctl.onchange = () => {
        vals[p.key] = ctl.value;
        preview();
      };
    } else if (p.type === 'boxes') {
      return boxesEditor(p);
    } else if (p.type === 'pineinputs') {
      return pineInputs();
    } else if (p.type === 'pinescript') {
      // the server's script list, read when the dialog opens; the stored name stays in the list even if its file went away
      ctl = mk('select', 'set-select ch-select');
      ctl.id = id;
      lab.htmlFor = id;
      ctl.setAttribute('aria-label', p.label);
      const err = mk('div', 'dlg-err');
      err.hidden = true;
      err.setAttribute('role', 'alert');
      const fill = (list) => {
        const rows = [['', 'Choose a script']].concat(list.map((x) => [x.name, x.title ? `${x.name} - ${x.title}` : x.name]));
        if (vals[p.key] && !list.some((x) => x.name === vals[p.key])) rows.push([vals[p.key], vals[p.key]]);
        ctl.replaceChildren(...rows.map(([v, text]) => { const o = mk('option', '', text); o.value = v; return o; }));
        ctl.value = vals[p.key] || '';
      };
      const fail = (text) => { if (done) return; err.textContent = text; err.hidden = false; };
      fill([]);
      if (window.fetch) {
        window.fetch('/api/pine/scripts').then((r) => (r.ok ? r.json() : Promise.reject(new Error('list'))))
          .then((list) => { if (done) return; fill(Array.isArray(list) ? list : []); if (!list || !list.length) fail('No Pine scripts on the server yet'); })
          .catch(() => fail('Could not load the script list'));
      }
      ctl.onchange = () => { vals[p.key] = ctl.value; delete vals.inputs; preview(); };   // the old script's inputs mean nothing to the new one
      row.append(lab, ctl, err);
      return row;
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

  /* ---- Pine: the script's own inputs, one row each, from what its last run reported (the cell keeps the Worker). Stored under the first of
     the input's variable name, its title, its id (in_N) that no OTHER input answers to: the Worker reads a key by id, then variable name, then
     title, so a key that is another input's id, variable name or title would move both. Inputs can share a title or a variable name (one
     assigned expression), never a key; a save does not move to another input when the script gains one. The title is the one written in the
     script: an input with none (the runtime names it "untitled") is keyed by its id. An old save moves to the input's key when the block is
     drawn, whichever of its names held it (also when a script edit makes a name a key or no key). A value put back to the script's own default
     is dropped. The block is drawn again only when the inputs or the error change, so a number being typed keeps its focus while the
     script re-runs on each keystroke. ---- */
  function pineKeys(inputs) {   // input -> its key
    const hit = (x, k) => inputs.some((y) => y !== x && (y.id === k || y.varId === k || y.title === k));   // the Worker would give k to y too
    return new Map(inputs.map((x) => [x, [x.varId, x.title].find((k) => k && !hit(x, k)) || x.id]));
  }
  const pineHas = (o, k) => !!o && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k);
  function pineMigrate(inputs, keys) {   // each input takes the value the Worker read for it, from whichever of its names held one
    if (!vals.inputs || typeof vals.inputs !== 'object') return;
    const live = new Set(keys.values()), owned = new Set(inputs.flatMap((y) => [y.id, y.varId])), moves = [], gone = new Set();
    for (const x of inputs) {   // id, variable name, title: the order the Worker reads them; a title that is another input's id or variable name is that input's
      const k = keys.get(x), t = x.title || x.name, held = [x.id, x.varId, owned.has(t) ? null : t].filter((a) => a && pineHas(vals.inputs, a) && (a === k || !live.has(a)));
      if (held.length && held[0] !== k) moves.push([k, vals.inputs[held[0]]]);
      for (const a of held) if (a !== k) gone.add(a);
    }
    for (const a of gone) delete vals.inputs[a];   // only now: one name can be several inputs' (two of one title, one assigned expression)
    for (const [k, v] of moves) vals.inputs[k] = v;
  }
  function pineInputs() {
    const wrap = mk('div', 'pine-inputs');
    let seen;
    const draw = () => {
      const m = cell.pineMeta ? cell.pineMeta(uid) : null, keys = m ? pineKeys(m.inputs) : null, sig = JSON.stringify(m ? [m.error, m.inputs.map((x) => [keys.get(x), x.title, x.name, x.type])] : null);
      if (sig === seen) return;
      seen = sig;
      wrap.replaceChildren();
      if (!m) return;
      pineMigrate(m.inputs, keys);
      if (m.error) { const err = mk('div', 'dlg-err', m.error); err.setAttribute('role', 'alert'); wrap.append(err); }
      for (const x of m.inputs) if (x.title || x.name) wrap.append(pineInput(x, keys.get(x)));
    };
    cell.onPineMeta = () => { if (!done && TABS[tab].id === 'inputs') draw(); };
    draw();
    return wrap;
  }
  function pineInput(x, key) {
    const label = x.title || x.name, row = mk('div', 'field'), id = `is-${uid}-pine-${x.id}`, lab = mk('label', '', label);
    const cur = () => (pineHas(vals.inputs, key) ? vals.inputs[key] : x.defval);
    const put = (v) => {
      const o = vals.inputs && typeof vals.inputs === 'object' ? vals.inputs : (vals.inputs = {});
      if (v === x.defval) delete o[key]; else o[key] = v;
      if (!Object.keys(o).length) delete vals.inputs;
      preview();
    };
    let ctl;
    if (x.type === 'bool') {
      ctl = mk('input');
      ctl.type = 'checkbox';
      ctl.checked = !!cur();
      ctl.onchange = () => put(ctl.checked);
    } else if (Array.isArray(x.options) && x.options.length) {
      ctl = mk('select', 'set-select ch-select');
      for (const v of x.options) { const o = mk('option', '', String(v)); o.value = String(v); ctl.append(o); }
      ctl.value = String(cur());
      ctl.onchange = () => put(x.options.find((v) => String(v) === ctl.value));   // the option itself, a number stays a number
    } else if (x.type === 'int' || x.type === 'float' || x.type === 'price' || x.type === 'time') {   // price: a float; time: whole ms
      const whole = x.type === 'int' || x.type === 'time';
      ctl = mk('input', 'set-num');
      ctl.type = 'number';
      if (x.minval != null) ctl.min = String(x.minval);
      if (x.maxval != null) ctl.max = String(x.maxval);
      ctl.step = String(x.step || (whole ? 1 : 'any'));
      ctl.value = String(cur());
      ctl.oninput = () => { const n = Number(ctl.value); if (ctl.value !== '' && Number.isFinite(n)) put(whole ? Math.round(n) : n); };
    } else if (x.type === 'color') {
      ctl = mk('input');
      ctl.type = 'color';
      ctl.value = /^#[0-9a-f]{6}/i.test(String(cur())) ? String(cur()).slice(0, 7) : '#2962ff';
      ctl.oninput = () => put(ctl.value);
    } else {   // string, timeframe: typed as the script expects it
      ctl = mk('input', 'sw-hex');
      ctl.type = 'text';
      ctl.maxLength = 200;
      ctl.spellcheck = false;
      ctl.value = String(cur() == null ? '' : cur());
      ctl.oninput = () => put(ctl.value);
    }
    ctl.id = id;
    lab.htmlFor = id;
    ctl.setAttribute('aria-label', label);
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
    if (C.hasLegend(inst.id)) rows.push(mk('div', 'set-cap', 'LEGEND'), legendRow());   // the order-flow overlays have no legend values: the box would do nothing
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
    const colorOnly = C.styleControls(inst.id) === 'color' || C.isColorKey(inst.id, key);   // volume / delta and an overlay's colours: a colour (and its opacity), no width or dash
    const cb = mk('input');
    cb.type = 'checkbox';
    cb.checked = line.visible !== false;
    cb.onchange = () => { line.visible = cb.checked; preview(); };
    const own = C.TA_BY_ID[inst.id] && C.TA_BY_ID[inst.id].lines.find((l) => l.part === key);
    const cdef = C.colorDefs(inst.id).find((c) => c.key === key);
    if (!C.isColorKey(inst.id, key)) name.append(cb);   // an overlay's colour has no eye: it is one colour, always drawn
    name.append(mk('span', '', (LINE_LABEL[inst.id] || {})[key] || (cdef && cdef.label) || (own && own.label) || key));
    // a histogram coloured by the sign of each bar (cell.js point()): colour, width, line style and axis tag change nothing, only the eye does
    if (own && own.type === 'hist' && !own.fixed) { row.append(name); return [row]; }
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
    const f = document.activeElement;
    if (f && f !== ok && pane.contains(f) && f.blur) f.blur();      // a timeframe or time still being typed is taken first
    flush();
    done = true;
    cell.onPineMeta = null;
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
      cell.onPineMeta = null;
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
