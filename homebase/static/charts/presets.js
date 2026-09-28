/* Homebase Charts — the generic /api/presets client + its Template ▾ menu (2026-09-27 draw-tools
   plan): the drawing tools' per-tool style presets today ("drawing:<tool>"), reusable by the
   indicator dialog later ("indicator:<tool>") without touching this file. Mirrors the chart
   Settings dialog's own Template ▾ (settings-dialog.js' templateMenu) almost exactly, parameterized
   by `kind` instead of being drawing-specific.

   Browser only (fetch, DOM) below the two pure helpers -- like settings-dialog.js, no
   module.exports fallback: this never ran, and never needs to run, outside the page. */
(() => {
'use strict';
const I = window.HBIcons;
const DEFAULT_NAME = '__default__';
const MAX_NAME = 40;

/* Why a preset name is refused ('' when fine) -- the same rule as check_preset_name in
   homebase/charts/presets.py: 1-40 characters, no / \ .. or control characters (it rides in the
   URL path), and not "." (the browser would resolve /api/presets/<kind>/. as a path step).
   __default__ is a name like any other here. */
function presetNameError(name) {
  if (typeof name !== 'string' || name.length < 1 || name.length > MAX_NAME) return `A name has 1 to ${MAX_NAME} characters`;
  if (name === '.' || /[/\\]|\.\.|[\u0000-\u001f\u007f]/.test(name)) return 'A name has no / \\ .. or control characters';
  return '';
}

/* {name: payload} -> [[name, payload]] sorted A-Z, __default__ left out: the menu shows the
   default through "Save as default" / "Apply default", never as a removable row. */
function sortedEntries(all) {
  return Object.keys(all && typeof all === 'object' ? all : {}).filter((n) => n !== DEFAULT_NAME)
    .sort((a, b) => a.localeCompare(b)).map((n) => [n, all[n]]);
}

function presetUrl(kind, name) {
  return '/api/presets/' + encodeURIComponent(kind) + (name == null ? '' : '/' + encodeURIComponent(name));
}

async function writePreset(method, kind, name, body, fetchFn) {
  const what = method === 'PUT' ? 'save' : 'delete';
  let r;
  try {
    r = await fetchFn(presetUrl(kind, name), method === 'PUT'
      ? { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : { method });
  } catch (_) { return `${what} failed: network error`; }
  if (r.ok) return '';
  let detail = '';
  try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
  return `${what} failed (${r.status})` + (detail ? ': ' + detail : '');
}

/* A kind's client, GET/PUT/DELETE /api/presets/<kind>[/<name>] -- the same {list, save, remove}
   shape app.js' own `templates` object has for /api/templates, so either can back a Template ▾
   menu. `fetchFn` defaults to the real fetch; tests inject a fake one. */
function client(kind, fetchFn = (...a) => fetch(...a)) {
  return {
    async list() { try { const r = await fetchFn(presetUrl(kind)); return r.ok ? await r.json() : null; } catch (_) { return null; } },
    save: (name, payload) => writePreset('PUT', kind, name, payload, fetchFn),
    remove: (name) => writePreset('DELETE', kind, name, undefined, fetchFn),
  };
}

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }
function menuBtn(text) {
  const b = button('menu-i');
  b.setAttribute('role', 'menuitem');
  b.append(mk('span', 'menu-t', text));
  return b;
}

/* The Template ▾ menu: Save as… (inline name, Enter saves), Save as default, Apply default, then
   the tool's saved presets (a click applies one; × deletes it after an inline "Delete?") -- the
   same shape and behaviour as the chart Settings dialog's own Template ▾.

   host: {toggleMenu(anchor, cls, fill), closeMenu(), placeMenu()} (the dialog-scoped shape every
   caller here already has -- settings-dialog.js' own `host`, or a page-level equivalent built the
   same way around openMenu/closeMenu/placeMenu).
   opts: {kind, current(): payload to save, apply(payload, { isDefault }): apply one to the working
   state (isDefault true for "Apply default" / a click on a row saved as the default, so the
   caller can tell a Template pick apart from picking the default back), extra: an optional list of
   {label, onclick()} rendered as plain menu rows after "Apply default" and before the saved-preset
   list (the indicator dialog's "Reset to factory settings" -- a plain-JS reset, nothing to do with
   the store, so it does not belong in this generic helper's own three actions)}. */
function menu(host, anchor, { kind, current, apply, extra }) {
  const store = client(kind);
  host.toggleMenu(anchor, 'menu-tpl', (m) => {
    const list = mk('div'), err = mk('div', 'menu-err');
    const saveAs = menuBtn('Save as…'), saveDefault = menuBtn('Save as default'), applyDefault = menuBtn('Apply default');
    const extraBtns = (extra || []).map(({ label, onclick }) => {
      const b = menuBtn(label);
      b.onclick = () => { host.closeMenu(); onclick(); };
      return b;
    });
    err.hidden = true;
    err.setAttribute('role', 'alert');
    m.append(saveAs, saveDefault, applyDefault, ...extraBtns, mk('div', 'menu-sep'), list, err);
    const fail = (text) => { err.textContent = text; err.hidden = false; host.placeMenu(); };
    applyDefault.onclick = async () => {
      const all = await store.list();
      if (!all) { fail('could not load the presets'); return; }
      host.closeMenu();
      if (DEFAULT_NAME in all) apply(all[DEFAULT_NAME], { isDefault: true });
    };
    saveDefault.onclick = async () => {
      const res = await store.save(DEFAULT_NAME, current());
      if (res) { fail(res); return; }
      host.closeMenu();
    };
    saveAs.onclick = () => {
      const rowEl = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), go = button('btn btn-primary', 'Save');
      input.type = 'text'; input.placeholder = 'Preset name'; input.maxLength = MAX_NAME; input.spellcheck = false;
      input.setAttribute('aria-label', 'Preset name');
      const save = async () => {
        const name = input.value.trim(), why = presetNameError(name);
        if (why) { fail(why); input.focus(); return; }
        if (name === DEFAULT_NAME) { fail(`"${DEFAULT_NAME}" is reserved -- use "Save as default"`); input.focus(); return; }
        const res = await store.save(name, current());
        if (res) { fail(res); return; }
        host.closeMenu();
      };
      go.onclick = save;
      input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; save(); } };   // S7: one PUT per press
      rowEl.append(input, go);
      saveAs.replaceWith(rowEl);
      input.focus();
    };
    list.append(mk('div', 'menu-empty', 'Loading…'));
    store.list().then((all) => {
      if (!m.isConnected) return;   // closed meanwhile
      if (!all) { list.replaceChildren(); fail('could not load the presets'); return; }
      const entries = sortedEntries(all);
      list.replaceChildren(...(entries.length ? entries.map(([name, payload]) => row(name, payload))
        : [mk('div', 'menu-empty', 'No saved presets')]));
      host.placeMenu();
    });
    function row(name, payload) {
      const r = mk('div', 'menu-row'), pick = menuBtn(name), del = button('menu-del');
      del.title = `Delete ${name}`;
      del.setAttribute('aria-label', `Delete ${name}`);
      del.innerHTML = I.x;   // our own static SVG string
      pick.onclick = () => { host.closeMenu(); apply(payload, { isDefault: false }); };
      del.onclick = () => {
        const ask = mk('div', 'menu-confirm'), yes = button('btn btn-danger', 'Delete'), no = button('btn btn-ghost', 'Cancel');
        ask.append(mk('span', '', `Delete “${name}”?`), yes, no);
        r.replaceWith(ask);
        no.focus();
        no.onclick = () => { ask.replaceWith(r); del.focus(); };
        yes.onclick = async () => {
          const res = await store.remove(name);
          if (res) { ask.replaceWith(r); fail(res); return; }
          ask.remove();
          if (!list.querySelector('.menu-row, .menu-confirm')) list.replaceChildren(mk('div', 'menu-empty', 'No saved presets'));
        };
      };
      r.append(pick, del);
      return r;
    }
  });
}

window.HBPresets = { DEFAULT_NAME, presetNameError, sortedEntries, client, menu };
})();
