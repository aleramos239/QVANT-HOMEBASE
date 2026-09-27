/* Homebase Charts — the app-wide Settings dialog (Task 4, 2026-09-27 accounts-paper-layouts-
   appsettings plan): a toolbar entry distinct from the chart's own gear (#tbSettings), opening a
   dialog structured so more app-wide settings can join later. Sections today:
     MARKET DATA — "Fill charts from": a radio per md login, the current one marked, applied the
       moment it's picked (no Ok/Cancel -- like the theme toggle it previews nothing, it just
       switches). A failed switch (the 09:20-09:35 ET / bot-placing refusal, or a failed re-login)
       shows inline and leaves the radios on whichever login is actually live.
     APPEARANCE — the existing light/dark toggle (app.js's toggleTheme), moved here; the toolbar
       button (#tbTheme) stays as a shortcut.
   Browser only: the model is server-side (GET/PUT /api/settings); the page (app.js) owns the
   dialog frame and hands it over as `host`:
     {getSettings(), putSettings(patch), status(), onStatus(fn) -> unsubscribe, isDark(),
      toggleTheme(), close()}
   -- this file only paints and reports clicks, exactly like settings-dialog.js's own contract. */
(() => {
'use strict';

const MD_CHOICES = [
  { value: 'live', label: 'Live' },
  { value: 'demo', label: 'Apex (demo)' },
];

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function mount(box, host) {
  let current = null;   // {md} from the server, once GET /api/settings answers
  let busy = false;      // a PUT in flight: the radios refuse a second pick, never queue one
  let err = '';
  let done = false;

  const body = mk('div', 'dlg-fields'), foot = mk('div', 'dlg-foot');

  /* ---- MARKET DATA ---- */
  const mdCap = mk('div', 'set-cap', 'MARKET DATA');
  const mdIntro = mk('div', 'set-note', 'Fill charts from');
  const radios = new Map();   // "live" | "demo" -> the <input type=radio>

  function mdRow(choice) {
    const row = mk('div', 'set-row'), name = mk('label', 'set-name'), cb = mk('input');
    cb.type = 'radio';
    cb.name = 'hb-md-login';
    cb.value = choice.value;
    cb.onchange = () => pick(choice.value);
    name.append(cb, mk('span', '', choice.label));
    radios.set(choice.value, cb);
    row.append(name);
    return row;
  }
  const mdRows = mk('div');
  mdRows.append(...MD_CHOICES.map(mdRow));
  const mdNote = mk('div', 'set-note', 'Only the live login carries Level 2 (depth, DOM ladder, heatmap).');
  const mdErr = mk('div', 'set-why');
  mdErr.hidden = true;
  mdErr.setAttribute('role', 'alert');

  function paintMd() {
    const activeMd = current ? current.md : null;
    for (const [v, cb] of radios) {
      cb.checked = v === activeMd;
      cb.disabled = busy || !current;
    }
    mdErr.textContent = err;
    mdErr.hidden = !err;
  }

  async function pick(md) {
    if (busy || !current || md === current.md) { paintMd(); return; }
    busy = true;
    err = '';
    paintMd();
    const res = await host.putSettings({ md });
    if (done) return;   // the dialog closed while the PUT was in flight
    busy = false;
    if (res.ok) {
      current = res.settings;
      err = '';
    } else {
      err = res.error || 'could not switch the market-data login';
    }
    paintMd();
  }

  /* ---- APPEARANCE ---- */
  const apCap = mk('div', 'set-cap', 'APPEARANCE');
  const apRow = mk('div', 'set-row'), apName = mk('label', 'set-name', 'Dark theme');
  const apCtl = mk('div', 'set-ctl'), apSwitch = mk('button', 'switch');
  apSwitch.type = 'button';
  apSwitch.setAttribute('role', 'switch');
  apSwitch.setAttribute('aria-label', 'Dark theme');
  apSwitch.onclick = () => { host.toggleTheme(); paintAppearance(); };
  apCtl.append(apSwitch);
  apRow.append(apName, apCtl);
  function paintAppearance() {
    const dark = host.isDark();
    apSwitch.classList.toggle('on', dark);
    apSwitch.setAttribute('aria-checked', String(dark));
  }

  body.append(mdCap, mdIntro, mdRows, mdNote, mdErr, apCap, apRow);
  const close = mk('button', 'btn btn-ghost', 'Close');
  close.type = 'button';
  close.onclick = () => host.close();
  foot.append(close);
  box.append(body, foot);

  paintMd();
  paintAppearance();
  host.getSettings().then((s) => {
    if (done || !s) return;
    current = s;
    paintMd();
  });
  // reflects a switch that lands from elsewhere too (another tab, a reconnect after a failure)
  const offStatus = host.onStatus((s) => {
    if (!current || !s || s.md == null || s.md === current.md) return;
    current = { ...current, md: s.md };
    paintMd();
  });

  close.focus();
  return {
    stop() { done = true; offStatus(); },
  };
}

window.HBAppSettings = { mount };
})();
