/* Homebase Charts — the app-wide Settings dialog (Task 4, 2026-09-27 accounts-paper-layouts-
   appsettings plan; MARKET DATA reworked in Fix round 1, ruling on ambiguous choice 2): a
   toolbar entry distinct from the chart's own gear (#tbSettings), opening a dialog structured so
   more app-wide settings can join later. Sections today:
     MARKET DATA — "Fill charts from": a radio per md login, the current one marked. Picking a
       radio only STAGES it -- it previews nothing and switches nothing. Apply (enabled only
       while the staged pick differs from the login actually in use) does the switch; the warning
       "Charts go blank for a few seconds while market data reconnects." sits right above it,
       always visible, so it is read before the click that matters, not after. While the switch
       runs Apply is disabled and reads "Applying…". On failure the error shows inline and the
       radio snaps back to whichever login is ACTUALLY in use (never the one that was staged).
     APPEARANCE — the existing light/dark toggle (app.js's toggleTheme), moved here; the toolbar
       button (#tbTheme) stays as a shortcut.
   Browser only: the model is server-side (GET/PUT /api/settings); the page (app.js) owns the
   dialog frame and hands it over as `host`:
     {getSettings(), putSettings(patch), status(), onStatus(fn) -> unsubscribe, isDark(),
      toggleTheme(), close()}
   -- this file only paints and reports clicks, exactly like settings-dialog.js's own contract.
   No native dialogs (alert/confirm/prompt): every message is inline. */
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
  let current = null;   // {md, accounts} from the server, once GET /api/settings answers
  let staged = null;    // the radio pick, NOT yet applied -- starts equal to current.md
  let busy = false;      // an Apply PUT in flight: Apply and the radios are disabled, never a
                        // second click queued
  let err = '';
  let done = false;

  const body = mk('div', 'dlg-fields'), foot = mk('div', 'dlg-foot');

  /* ---- MARKET DATA ---- */
  const mdCap = mk('div', 'set-cap', 'MARKET DATA');
  const mdIntro = mk('div', 'set-note', 'Fill charts from');
  const radios = new Map();   // "live" | "demo" -> {cb, acct: the account-id <span>}

  function mdRow(choice) {
    const row = mk('div', 'set-row'), name = mk('label', 'set-name'), cb = mk('input');
    cb.type = 'radio';
    cb.name = 'hb-md-login';
    cb.value = choice.value;
    cb.onchange = () => { staged = choice.value; err = ''; paintMd(); };
    const acct = mk('span', 'set-unit');
    name.append(cb, mk('span', '', choice.label), acct);
    radios.set(choice.value, { cb, acct });
    row.append(name);
    return row;
  }
  const mdRows = mk('div');
  mdRows.append(...MD_CHOICES.map(mdRow));
  const mdNote = mk('div', 'set-note', 'Only the live login carries Level 2 (depth, DOM ladder, heatmap).');
  const mdWarn = mk('div', 'set-why', 'Charts go blank for a few seconds while market data reconnects.');
  const mdErr = mk('div', 'set-why');
  mdErr.hidden = true;
  mdErr.setAttribute('role', 'alert');
  // what /api/status says about the feed itself (fix round 2, re-review M-f): a login that
  // connected as the other one, or the last switch that failed -- also one made in another tab
  // or before this dialog opened
  const mdState = mk('div', 'set-why');
  mdState.hidden = true;
  let feedStatus = host.status ? host.status() : null;
  const labelOf = (v) => (MD_CHOICES.find((c) => c.value === v) || { label: v }).label;
  const applyRow = mk('div', 'set-row'), apply = mk('button', 'btn btn-primary', 'Apply');
  apply.type = 'button';
  apply.onclick = doApply;
  applyRow.append(mk('span'), apply);   // .set-row's grid puts Apply in the right (auto) column

  function paintMd() {
    const activeMd = current ? current.md : null;
    for (const [v, { cb, acct }] of radios) {
      cb.checked = v === staged;
      cb.disabled = busy || !current;
      const label = current && current.accounts ? current.accounts[v] : null;
      acct.textContent = label ? `(${label})` : '';
    }
    mdErr.textContent = err;
    mdErr.hidden = !err;
    apply.disabled = busy || !current || staged === activeMd;
    apply.textContent = busy ? 'Applying…' : 'Apply';
    const s = feedStatus, notes = [];
    if (s && s.md_mismatch) notes.push(s.md_mismatch);
    if (s && s.switch_error && !err && !busy) {   // this dialog's own failure already shows above
      notes.push(`The last switch to ${labelOf(s.switch_error.to)} failed: ${s.switch_error.error}`);
    }
    mdState.textContent = notes.join(' ');
    mdState.hidden = !notes.length;
  }

  async function doApply() {
    if (busy || !current || staged === current.md) return;   // e.repeat on Enter/Space: ignored,
                                                              // Apply is already disabled by then
    const md = staged;
    busy = true;
    err = '';
    paintMd();
    const res = await host.putSettings({ md });
    if (done) return;   // the dialog closed while the PUT was in flight
    busy = false;
    if (res.ok) {
      current = res.settings;
      staged = current.md;
      err = '';
    } else {
      err = res.error || 'could not switch the market-data login';
      staged = current.md;   // snap back to whichever login is ACTUALLY in use, never the failed pick
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

  body.append(mdCap, mdIntro, mdRows, mdNote, mdErr, mdState, mdWarn, applyRow, apCap, apRow);
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
    staged = s.md;
    paintMd();
  });
  // reflects a switch that lands from elsewhere too (another tab, a reconnect after a failure) --
  // only while idle: a switch THIS dialog just started must not have its own staged pick undone
  // by the very status tick that is about to confirm it (doApply reconciles `current` itself)
  const offStatus = host.onStatus((s) => {
    if (s) feedStatus = s;
    if (busy || !current || !s || s.md == null || s.md === current.md) { paintMd(); return; }
    current = { ...current, md: s.md };
    staged = s.md;
    paintMd();
  });

  close.focus();
  return {
    stop() { done = true; offStatus(); },
  };
}

window.HBAppSettings = { mount };
})();
