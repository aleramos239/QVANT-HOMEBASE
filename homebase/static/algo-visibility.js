/* Pure decision logic for the home-page algo manager.
 *
 * Display-only. Never touches whether a strategy trades — that is entirely
 * `cfg.enabled` + the book, both owned by the desk. This module only decides
 * which algo CARDS render on the home page.
 *
 * Safety rule: an algo is un-hideable — its checkbox is checked and
 * disabled — whenever ANY of these hold (homebase/trading.py's bot_view /
 * state_view / engine.py are the source of truth for the field names):
 *   1. it can trade right now: cfg.enabled AND booked to >=1 account
 *      ("Live — disable it before hiding");
 *   2. it has activity TODAY: engine.day_status(strategy) is one of
 *      "placing" | "placed" | "live" | "error" — anything with working
 *      orders, an open position, or a fault ("Has orders or a position
 *      today"). This is the case that matters when the book has gone
 *      EMPTY mid-trade (e.g. a login the desk can't resolve an account
 *      under) — cfg.enabled && booked alone would say "not live" and let
 *      the user hide an algo that is still holding a real position.
 *   3. any of today's per-account runs is flagged `check_it`
 *      (engine.needs_check — a human must verify this position), or the
 *      strategy was `killed` today (engine.killed_today) and any run is
 *      still `placed`/`live` ("Needs a check — see the desk").
 *
 * If the stored preference is missing, unreadable, or not the expected
 * shape, everything is shown — the safe failure is seeing more, never less.
 *
 * Also home to the desk page's one confirm policy for every switch
 * (switchNeedsConfirm): the "Show on home page" switch never asks, because
 * hiding a card never changes what trades.
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

  // day_status values that mean "something is happening today" — see
  // Engine.day_status in homebase/engine.py: idle|placing|placed|live|done|error.
  // done and idle are excluded on purpose: done means today's run(s) are
  // flat and finished, idle means nothing has happened yet.
  var ACTIVITY_STATUSES = { placing: true, placed: true, live: true, error: true };

  var LOCK_REASON = {
    TRADABLE: "Live — disable it before hiding",
    ACTIVITY: "Has orders or a position today",
    CHECK: "Needs a check — see the desk",
  };

  // Booked = at least one account row assigned in the book for this strategy.
  function isBooked(bookRows) {
    return Array.isArray(bookRows) && bookRows.length > 0;
  }

  // Tradable = can actually place a NEW order right now: enabled AND booked.
  // Kept as its own function (used to be called isLive) because it answers
  // a narrower question than "can this be hidden" — see lockInfo() below.
  function isTradable(cfg, bookRows) {
    return !!(cfg && cfg.enabled) && isBooked(bookRows);
  }

  function hasActivityToday(dayStatus) {
    return !!ACTIVITY_STATUSES[dayStatus];
  }

  // accounts: the strategy's per-account day states for today, as returned
  // by /api/status (each carries `status` and, since the desk started
  // surfacing it, `check_it`). killed: engine.killed_today(strategy).
  function needsHumanCheck(accounts, killed) {
    var rows = Array.isArray(accounts) ? accounts : [];
    if (rows.some(function (a) { return a && a.check_it; })) return true;
    if (killed && rows.some(function (a) { return a && (a.status === "placed" || a.status === "live"); })) {
      return true;
    }
    return false;
  }

  // The single source of truth for "can this algo's card be hidden right
  // now". Returns {locked, reason} — reason is one of LOCK_REASON's values,
  // in priority order (tradable beats activity beats check), or null.
  function lockInfo(cfg, bookRows, dayStatus, accounts, killed) {
    if (isTradable(cfg, bookRows)) return { locked: true, reason: LOCK_REASON.TRADABLE };
    if (hasActivityToday(dayStatus)) return { locked: true, reason: LOCK_REASON.ACTIVITY };
    if (needsHumanCheck(accounts, killed)) return { locked: true, reason: LOCK_REASON.CHECK };
    return { locked: false, reason: null };
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
      var lock = lockInfo(cfg, bookRows, entry.day_status, entry.accounts, entry.killed);
      // A locked algo can never be hidden, no matter what's stored.
      var wantsHidden = !lock.locked && !!hidden[name];
      out.push({
        name: name,
        symbol: cfg.symbol || "",
        enabled: !!cfg.enabled,
        booked: isBooked(bookRows),
        day_status: entry.day_status || "idle",
        hidden: wantsHidden,
        visible: !wantsHidden,
        // the checkbox is checked+disabled whenever the algo cannot be
        // hidden right now, with a reason specific to why
        locked: lock.locked,
        lockReason: lock.reason,
      });
    });
    return out;
  }

  // The desk page's ONE confirm policy for every switch (2026-09-28, Apple-design audit
  // S6; the chart-trading switch's pattern): ask only when a flip turns ON something that
  // can place orders -- a strategy (unless SHADOW: it never places one), chart trading,
  // the desk's Arm. Never when it makes things safer (OFF, Disarm), and never for this
  // module's own "Show on home page" switch: hiding a card changes nothing that trades
  // (and a card that could trade is locked visible anyway). An unknown switch asks when
  // turned on -- fail toward asking.
  var SWITCH_CAN_TRADE = { strategy: true, chartTrading: true, desk: true, visibility: false };

  function switchNeedsConfirm(kind, turningOn, opts) {
    if (!turningOn) return false;
    if (kind === "strategy" && opts && opts.shadow) return false;
    return SWITCH_CAN_TRADE[kind] !== false;
  }

  // Returns a new hidden-list with `name` added or removed. Refuses to add
  // a name that is currently locked (belt-and-braces on top of
  // computeVisibility already ignoring it) — the UI should never call this
  // with hide=true for a locked algo, but the function itself won't produce
  // an unsafe list either.
  function withHidden(hiddenList, name, hide, locked) {
    var set = {};
    normalizeHidden(hiddenList).forEach(function (n) { set[n] = true; });
    if (hide && !locked) {
      set[name] = true;
    } else {
      delete set[name];
    }
    return Object.keys(set);
  }

  return {
    STORAGE_KEY: STORAGE_KEY,
    LOCK_REASON: LOCK_REASON,
    isBooked: isBooked,
    isTradable: isTradable,
    hasActivityToday: hasActivityToday,
    needsHumanCheck: needsHumanCheck,
    lockInfo: lockInfo,
    normalizeHidden: normalizeHidden,
    loadHidden: loadHidden,
    saveHidden: saveHidden,
    computeVisibility: computeVisibility,
    withHidden: withHidden,
    switchNeedsConfirm: switchNeedsConfirm,
  };
});
