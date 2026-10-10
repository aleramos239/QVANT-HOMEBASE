/* Homebase Desk -- the settings a Lab strategy declared adjustable, as controls in the Setup panel (2026-10-10).

   The strategy names them (`desk_settings` in its code); the record carries their specs; /api/status's `lab.settings` hands them
   to the page and `lab.params` holds the values in force. This builds ONE persistent set of rows per strategy (a repaint of the
   page never wipes what is being typed, like the RR field) and writes through the page's own setLabSetting(), which says why
   a refusal came. A change takes effect from the strategy's next session; the Desk refuses it while the session runs. */
(function (root) {
  "use strict";
  var D = root.document;
  var KEPT = {};                       // desk id -> {sig, rows: [nodes], fields: {key: field}, err}

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
  // What the control holds as the text the backend takes: a choice as it is, a number as typed.
  function wire(s, raw) {
    if (s.type === "choice") return String(raw);
    if (s.type === "bool") return raw === true || raw === "true";
    var n = parseFloat(raw);
    return isFinite(n) ? n : NaN;
  }

  function build(name, lab, ro) {
    var kept = { sig: JSON.stringify(specs(lab)), rows: [], fields: {}, err: null, ro: false };
    specs(lab).forEach(function (s) {
      var f = { spec: s, dirty: false };
      var row = el("div", "hb-row");
      row.appendChild(el("span", "hb-row-k", plain(s.label || s.key)));
      var input;
      if (s.type === "choice") {
        input = el("select", "hb-field");
        (s.choices || []).forEach(function (c) { var o = el("option", "", plain(c)); o.value = plain(c); input.appendChild(o); });
      } else {
        input = el("input", "hb-field");
        input.type = "number";
        if (s.min != null) input.min = String(s.min);
        if (s.max != null) input.max = String(s.max);
        if (s.step != null) input.step = String(s.step);
        input.setAttribute("inputmode", "decimal");
        input.style.width = "72px";
        input.style.textAlign = "right";
      }
      input.setAttribute("aria-label", plain(s.label || s.key));
      var btn = el("button", "hb-btn", "Set");
      btn.type = "button";
      f.input = input; f.btn = btn;
      function mark() { f.dirty = true; kept.err.hidden = true; }
      input.addEventListener("input", mark);
      input.addEventListener("change", mark);
      async function save() {
        var v = wire(s, input.value);
        if (v !== v) { kept.err.textContent = plain(s.label || s.key) + ": a number."; kept.err.hidden = false; return; }
        if (typeof root.setLabSetting !== "function") return;
        btn.disabled = true;
        try {
          var why = await root.setLabSetting(kept.name, s.key, v);
          kept.err.textContent = why || ""; kept.err.hidden = !why;
          if (!why) f.dirty = false;
        } finally { btn.disabled = !!kept.ro; }
      }
      input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.repeat) save(); });
      btn.addEventListener("click", save);
      row.appendChild(input);
      row.appendChild(btn);
      kept.rows.push(row);
      kept.fields[s.key] = f;
    });
    kept.err = el("div", "hb-row hb-row-note");
    kept.err.setAttribute("role", "alert");
    kept.err.hidden = true;
    kept.rows.push(kept.err);
    kept.name = name;
    return kept;
  }

  // The rows for one strategy, the same nodes on every call (values follow the Desk's unless being typed).
  function nodes(name, lab, ro) {
    if (!specs(lab).length) { delete KEPT[name]; return []; }
    var k = KEPT[name];
    if (!k || k.sig !== JSON.stringify(specs(lab))) k = KEPT[name] = build(name, lab, ro);
    k.ro = !!ro;
    Object.keys(k.fields).forEach(function (key) {
      var f = k.fields[key], v = valueOf(lab, f.spec);
      f.input.disabled = !!ro; f.btn.disabled = !!ro;
      if (!f.dirty && D.activeElement !== f.input) f.input.value = plain(v);
    });
    return k.rows;
  }
  // A short signature of what the controls show, so a panel repaints only when something it draws changed.
  function sig(lab) {
    return JSON.stringify([specs(lab).map(function (s) { return [s.key, valueOf(lab, s)]; }), !!(lab && lab.read_only)]);
  }

  root.DeskLabSet = { nodes: nodes, sig: sig, specs: specs };
})(typeof window !== "undefined" ? window : this);
