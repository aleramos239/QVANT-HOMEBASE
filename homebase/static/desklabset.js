/* Homebase Desk -- the settings a Lab strategy declared adjustable, as READ-ONLY rows in the Setup panel (2026-10-10; read-only
   since the per-account settings, 2026-10-29: the owner edits size and the stops from each account row instead).

   The strategy names them (`desk_settings` in its code); the record carries their specs; /api/status's `lab.settings` hands them
   to the page and `lab.params` holds the values in force. They stay strategy-wide: this only shows them, as text. The write
   (`setLabSetting`, /api/lab-settings) is still the page's, for the Changes list's "Put back". */
(function (root) {
  "use strict";
  var D = root.document;

  function el(tag, cls, text) {
    var n = D.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function plain(v) { return v == null ? "" : String(v); }
  function specs(lab) {
    var s = lab && Array.isArray(lab.settings) ? lab.settings : [];
    return s.filter(function (x) { return x && typeof x.key === "string"; });
  }
  function valueOf(lab, s) {
    var p = lab && lab.params && typeof lab.params === "object" ? lab.params : {};
    return p[s.key] != null ? p[s.key] : s.default;
  }
  // A value as the row shows it: an on/off setting as On / Off, anything else as it is.
  function shown(s, raw) { return s.type === "bool" ? (raw === true || raw === "true" ? "On" : "Off") : plain(raw); }

  // The text rows for one strategy, in the order it declared them.
  function nodes(name, lab, ro) {
    return specs(lab).map(function (s) {
      var row = el("div", "hb-row");
      row.appendChild(el("span", "hb-row-k", plain(s.label || s.key)));
      row.appendChild(el("span", "hb-row-v", shown(s, valueOf(lab, s))));
      return row;
    });
  }
  // A short signature of what the rows show, so a panel repaints only when something it draws changed.
  function sig(lab) {
    return JSON.stringify([specs(lab).map(function (s) { return [s.key, valueOf(lab, s)]; }), !!(lab && lab.read_only)]);
  }

  root.DeskLabSet = { nodes: nodes, sig: sig, specs: specs };
})(typeof window !== "undefined" ? window : this);
