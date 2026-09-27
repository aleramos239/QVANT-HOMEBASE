/* Pure decision logic for the home-page algo manager.
 *
 * Display-only. Never touches whether a strategy trades — that is entirely
 * `cfg.enabled` + the book, both owned by the desk. This module only decides
 * which algo CARDS render on the home page.
 *
 * Safety rule: an algo that CAN trade (enabled AND booked on >=1 account) is
 * always visible and its hide preference is ignored. If the stored
 * preference is missing, unreadable, or not the expected shape, everything
 * is shown — the safe failure is seeing more, never less.
 *
 * UMD-ish export so this loads as a plain <script> on the desk page
 * (window.AlgoVisibility) and as a CommonJS module under `node --test`.
 */
(function (root, factory) {
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  }
  if (root) {
    root.AlgoVisibility = mod;
  }
})(typeof self !== "undefined" ? self : (typeof global !== "undefined" ? global : null), function () {
  "use strict";

  var STORAGE_KEY = "hb_hidden_algos";

  // Booked = at least one account row assigned in the book for this strategy.
  function isBooked(bookRows) {
    return Array.isArray(bookRows) && bookRows.length > 0;
  }

  // Live = can actually trade right now: enabled AND booked.
  function isLive(cfg, bookRows) {
    return !!(cfg && cfg.enabled) && isBooked(bookRows);
  }

  // Parse whatever came back from storage into a clean array of hidden
  // names. Anything unexpected collapses to [] (= show everything).
  function normalizeHidden(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.filter(function (n) { return typeof n === "string" && n.length > 0; });
  }

  // Read the stored hide-list. Missing key, JSON.parse failure, storage
  // blocked/unavailable (private window, cleared site data, etc.), or a
  // value that isn't an array of strings — all fail closed to "show all".
  function loadHidden(storage) {
    try {
      var s = storage || (typeof localStorage !== "undefined" ? localStorage : null);
      if (!s) return [];
      var raw = s.getItem(STORAGE_KEY);
      if (!raw) return [];
      return normalizeHidden(JSON.parse(raw));
    } catch (_e) {
      return [];
    }
  }

  function saveHidden(list, storage) {
    try {
      var s = storage || (typeof localStorage !== "undefined" ? localStorage : null);
      if (!s) return false;
      s.setItem(STORAGE_KEY, JSON.stringify(normalizeHidden(list)));
      return true;
    } catch (_e) {
      return false;
    }
  }

  // Given the desk's own status payload (strategies + book) and the raw
  // stored hide-list, decide what shows. `hiddenList` may be `undefined`,
  // corrupt JSON already parsed to garbage, or a clean array — this
  // function tolerates all of them via normalizeHidden.
  function computeVisibility(strategies, book, hiddenList) {
    strategies = strategies || {};
    book = book || {};
    var hidden = {};
    normalizeHidden(hiddenList).forEach(function (n) { hidden[n] = true; });

    var out = [];
    Object.keys(strategies).forEach(function (name) {
      var entry = strategies[name] || {};
      var cfg = entry.cfg || {};
      var bookRows = book[name];
      var live = isLive(cfg, bookRows);
      // A live algo can never be hidden, no matter what's stored.
      var wantsHidden = !live && !!hidden[name];
      out.push({
        name: name,
        symbol: cfg.symbol || "",
        enabled: !!cfg.enabled,
        booked: isBooked(bookRows),
        live: live,
        day_status: entry.day_status || "idle",
        hidden: wantsHidden,
        visible: !wantsHidden,
        // the checkbox is checked+disabled ("Live — disable it before
        // hiding") whenever the algo cannot be hidden right now
        locked: live,
      });
    });
    return out;
  }

  // Returns a new hidden-list with `name` added or removed. Refuses to add
  // a name that is currently live (belt-and-braces on top of
  // computeVisibility already ignoring it) — the UI should never call this
  // with hide=true for a live algo, but the function itself won't produce
  // an unsafe list either.
  function withHidden(hiddenList, name, hide, live) {
    var set = {};
    normalizeHidden(hiddenList).forEach(function (n) { set[n] = true; });
    if (hide && !live) {
      set[name] = true;
    } else {
      delete set[name];
    }
    return Object.keys(set);
  }

  return {
    STORAGE_KEY: STORAGE_KEY,
    isBooked: isBooked,
    isLive: isLive,
    normalizeHidden: normalizeHidden,
    loadHidden: loadHidden,
    saveHidden: saveHidden,
    computeVisibility: computeVisibility,
    withHidden: withHidden,
  };
});
