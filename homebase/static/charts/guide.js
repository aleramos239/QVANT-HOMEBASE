/* Homebase Charts — HBGuide: what each indicator is, how to read it and how to use it, in plain words.
   The text lives in guide-*.js (one file per group of indicators); this file is the registry the pages read:
     HBGuide.add({ <indicator id>: { what, see, read, use, watch? } })   -- guide-*.js call it
     HBGuide.get(id)  -> that entry, or null
     HBGuide.ids()    -> every id with an entry
   An entry: `what` one sentence; `see` / `read` / `use` 1-5 short lines each (see: what is drawn; read: what a
   thing on the chart means; use: how a trader can use it); `watch` one optional line of caution. */
(function () {
'use strict';
const entries = Object.create(null);
const api = {
  add(map) { for (const id of Object.keys(map)) entries[id] = map[id]; },
  get(id) { return entries[id] || null; },
  ids() { return Object.keys(entries); },
};
if (typeof window !== 'undefined') window.HBGuide = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
