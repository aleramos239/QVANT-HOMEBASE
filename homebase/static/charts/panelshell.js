/* Homebase Charts — HBPanelShell: the chrome around the Order and DOM panels (2026-09-27 panels plan). Each
   panel is either DOCKED (stacked in the right dock column, #pdock) or FLOATING (dragged anywhere over the
   chart, kept inside the viewport, in #floatLayer). This file owns the header (title, dock/float toggle, ×),
   the drag/drop between the two states, the dock's reordering + splitter + width grip, and a floating panel's
   move + edge/corner resize. All the actual math (clamping, dock stacking, the drop-zone hit test, persisted-
   state parsing) is HBPanelLayout, pure and Node-tested; this file only wires the DOM to it.

   Content ownership: orderpanel.js and domui.js each own their own content and never see the chrome. mount()
   below hands each one a plain <div> to fill ONCE; that node is only ever reparented (dock <-> float, or into
   the dock's stack) after that, never rebuilt -- so an input's value and focus survive a layout change. The
   one exception the GOTCHAS call out (never rebuild while an input has focus) doesn't apply here because
   nothing here rebuilds; a reparent still blurs the input for a tick, so focus is explicitly restored right
   after the move. Browser only. */
(() => {
'use strict';
const L = window.HBPanelLayout;
const M = window.HBSpring;     // the feel pass (2026-09-28): momentum projection, rubber-band, the settle spring
const KEY = 'hb_charts_panels';
const TITLES = { order: 'Order', dom: 'DOM' };
const DRAG_OUT_PX = 24;     // a docked header must clear the dock by this much before it starts floating
const GRID_MIN_W = 240;     // the chart grid never gets crushed under this, however wide a side-by-side dock asks to be

let state = L.defaultState();
let defs = {};              // id -> { mount(container, page), setVisible(bool) }
let built = new Set();      // ids whose content has been mounted at least once
let els = {};                // id -> { root, head, title, toggleBtn, toggleIcon, closeBtn, body }
let dockEl = null, floatLayer = null;
let page = null;
let saveTimer = 0;
/* id -> {sx, sy} Spring pair settling a FLOATING panel into its release-time resting rect (wireHeaderDrag's
   `end`); id -> a cancel fn settling a FLIP transform after a dock/reorder relayout (animateDockFlip). A
   fresh pointerdown on a header that owns either stops it and reads its LIVE value as the new drag's start
   -- interruptible, no brick wall (apple-design skill, principle 3). */
let floatAnim = {};
let flipAnim = {};
function stopFloatAnim(id) {
  const a = floatAnim[id];
  if (!a) return null;
  a.sx.stop(); a.sy.stop();
  delete floatAnim[id];
  return { x: a.sx.value, y: a.sy.value };
}
function stopFlipAnim(id) {
  const cancel = flipAnim[id];
  if (cancel) { cancel(); delete flipAnim[id]; }
}
/* Settle a floating panel from its current on-screen (x, y) to `final` (the value already committed to
   `state`), carrying the drag's release velocity through the spring (apple-design: "always animate from the
   presentation value," "velocity handoff"). Skipped entirely under reduced motion -- an instant jump. */
function settleFloat(id, from, final, vx, vy) {
  stopFloatAnim(id);
  const e = els[id];
  if (!e) return;
  if (M.prefersReducedMotion() || (from.x === final.x && from.y === final.y)) {
    e.root.style.left = `${final.x}px`; e.root.style.top = `${final.y}px`;
    return;
  }
  const preset = M.pickPreset(vx, vy);
  const sx = new M.Spring(from.x, { ...preset, onUpdate: (v) => { e.root.style.left = `${v}px`; } });
  const sy = new M.Spring(from.y, { ...preset, onUpdate: (v) => { e.root.style.top = `${v}px`; } });
  floatAnim[id] = { sx, sy };
  sx.onSettle = () => { if (floatAnim[id] && floatAnim[id].sx === sx) delete floatAnim[id]; };
  sx.setTarget(final.x, { velocity: vx });
  sy.setTarget(final.y, { velocity: vy });
}
/* FLIP (First-Last-Invert-Play): `run()` reparents/relayouts synchronously (dock <-> float, or a reorder
   inside the dock all move a panel through a flex-computed slot whose pixel rect isn't known ahead of time),
   then plays the visual jump back in via a `transform` spring -- the one CSS property that's always free to
   animate regardless of what layout mode owns left/top/flex. `vx`/`vy` (px/s, the drag's release velocity)
   keep the same velocity-handoff continuity settleFloat gets; a plain reorder (no drag behind it) passes 0. */
function animateDockFlip(id, run, vx, vy) {
  stopFlipAnim(id);
  const e = els[id];
  const before = e ? e.root.getBoundingClientRect() : null;
  run();
  if (!e || !before || M.prefersReducedMotion()) return;
  const after = e.root.getBoundingClientRect();
  const dx = before.left - after.left, dy = before.top - after.top;
  if (!dx && !dy) return;
  const preset = M.pickPreset(vx, vy);
  const paint = () => { e.root.style.transform = `translate(${sx.value}px, ${sy.value}px)`; };
  const sx = new M.Spring(dx, { ...preset, onUpdate: paint });
  const sy = new M.Spring(dy, { ...preset, onUpdate: paint });
  const done = () => { if (Math.abs(sx.value) < 0.5 && Math.abs(sy.value) < 0.5) e.root.style.transform = ''; };
  sx.onSettle = done; sy.onSettle = done;
  flipAnim[id] = () => { sx.stop(); sy.stop(); e.root.style.transform = ''; };
  sx.setTarget(0, { velocity: -vx });
  sy.setTarget(0, { velocity: -vy });
}
/* Grips/splitters/resize handles: a live drag rubber-bands past its hard bound the same way (soft paint,
   `state`/the caller's own numbers stay hard-clamped throughout); at release, this plays the visible
   snap back onto the hard value with one short CSS transition instead of a JS spring. Unlike a dragged
   panel these are never grabbed again mid-animation, so the cheaper tool is the right one here (see the
   audit doc's design-decision note) -- `.pdock-snap-w`/`-h` (charts.css) sets the transition, removed again
   once it's done so a later PROGRAMMATIC resize (e.g. a window resize's onWindowResize) is never transitioned. */
function snapAxisCSS(el, prop, hardValue, unit) {
  if (!el) return;
  const u = unit == null ? 'px' : unit;   // '' for a unitless CSS number (flexGrow)
  if (M.prefersReducedMotion()) { el.style[prop] = `${hardValue}${u}`; return; }
  const cls = prop === 'flexGrow' ? 'pdock-snap-flex' : prop === 'height' ? 'pdock-snap-h' : 'pdock-snap-w';
  const cssProp = prop === 'flexGrow' ? 'flex-grow' : prop;
  el.classList.add(cls);
  el.style[prop] = `${hardValue}${u}`;
  const done = () => el.classList.remove(cls);
  el.addEventListener('transitionend', (e) => { if (e.propertyName === cssProp) done(); }, { once: true });
  setTimeout(done, 220);
}
/* The float-resize handles change left/top/width/height together on ONE element -- a separate snapAxisCSS
   call per property would each add+remove its own class independently and could cut another one's
   transition off early, so this is one call, one class, one timer for all four. */
function snapRectCSS(el, rect) {
  if (!el) return;
  if (M.prefersReducedMotion()) {
    el.style.left = `${rect.x}px`; el.style.top = `${rect.y}px`; el.style.width = `${rect.w}px`; el.style.height = `${rect.h}px`;
    return;
  }
  el.classList.add('pdock-snap-rect');
  el.style.left = `${rect.x}px`; el.style.top = `${rect.y}px`; el.style.width = `${rect.w}px`; el.style.height = `${rect.h}px`;
  const done = () => el.classList.remove('pdock-snap-rect');
  el.addEventListener('transitionend', done, { once: true });
  setTimeout(done, 220);
}

/* ---- persistence: try/catch at every access, same convention as orderpanel.js / panel.js ---- */
function load() {
  let raw = null;
  try { raw = localStorage.getItem(KEY); } catch (_) { raw = null; }
  return L.parsePersisted(raw, L.defaultState());
}
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (_) { /* storage off: this session only */ }
  }, 150);
}

function mk(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = window.HBIcons[name] || ''; return s; }

/* ---- ids currently docked+open, in dock order; the dock column only ever shows these ---- */
function dockedOpenIds() { return state.dockOrder.filter((id) => state.panels[id].open && state.panels[id].docked); }
function floatingOpenIds() { return L.IDS.filter((id) => state.panels[id].open && !state.panels[id].docked); }

/* ---- build each panel's chrome once; content is mounted into `.hbpanel-body` once, by the caller's def ---- */
function buildChrome(id) {
  const root = mk('div', 'hbpanel');
  root.id = `panel-${id}`;   // aria-controls target for #tbOrder / #tbDom (charts.html)
  root.dataset.panel = id;
  const head = mk('div', 'hbpanel-head');
  const title = mk('span', 'hbpanel-title', undefined);
  title.textContent = TITLES[id];
  const toggleBtn = mk('button', 'hbpanel-btn');
  toggleBtn.type = 'button';
  const toggleIcon = icon('extLink');
  toggleBtn.appendChild(toggleIcon);
  toggleBtn.onclick = (e) => { e.stopPropagation(); setDocked(id, !state.panels[id].docked); };
  const closeBtn = mk('button', 'hbpanel-btn');
  closeBtn.type = 'button';
  closeBtn.title = `Close ${TITLES[id]}`;
  closeBtn.setAttribute('aria-label', `Close ${TITLES[id]}`);
  closeBtn.appendChild(icon('x'));
  closeBtn.onclick = (e) => { e.stopPropagation(); setOpen(id, false); };
  head.append(title, mk('span', 'hbpanel-spacer'), toggleBtn, closeBtn);
  const body = mk('div', 'hbpanel-body');
  root.append(head, body);
  wireHeaderDrag(id, root, head);
  wireFloatResize(id, root);
  els[id] = { root, head, title, toggleBtn, toggleIcon, closeBtn, body };
  return els[id];
}
function ensureBuilt(id) {
  if (built.has(id)) return;
  built.add(id);
  buildChrome(id);
  const def = defs[id];
  if (def && def.mount) def.mount(els[id].body, page);
}

/* A DOM node is moved (dock <-> float, or reordered in the dock) with appendChild -- never destroyed. Moving a
   node whose descendant has focus blurs it; restore focus (and the caret) right after so a mid-type field in
   the Order panel survives a drag/dock switch untouched. */
function reparentPreservingFocus(node, parent, before) {
  const a = document.activeElement;
  const hadFocus = a && node.contains(a);
  let sel = null;
  if (hadFocus && typeof a.selectionStart === 'number') { try { sel = [a.selectionStart, a.selectionEnd]; } catch (_) { sel = null; } }
  if (before) parent.insertBefore(node, before); else parent.appendChild(node);
  if (hadFocus) {
    a.focus();
    if (sel) { try { a.setSelectionRange(sel[0], sel[1]); } catch (_) { /* not a text field after all */ } }
  }
}

/* ---- layout: dock column + floating layer, from `state` ---- */
/* The width budget for a side-by-side dock: the .main row's own width minus the drawing rail and the chart
   grid's minimum, so the grid never gets crushed to nothing however wide the two panels ask to be. */
function dockMaxTotalWidth() {
  const main = dockEl && (dockEl.closest('.main') || dockEl.parentElement);
  const mainW = main ? main.clientWidth : window.innerWidth;
  const rail = document.getElementById('rail');
  const railW = rail ? rail.offsetWidth : 0;
  return Math.max(L.DOCK_W_MIN * 2, mainW - railW - GRID_MIN_W);
}
function layoutDock() {
  const ids = dockedOpenIds();
  dockEl.replaceChildren();
  if (!ids.length) { dockEl.hidden = true; dockEl.classList.remove('side'); return; }
  dockEl.hidden = false;
  const isSide = state.dockOrientation === 'side' && ids.length === 2;
  dockEl.classList.toggle('side', isSide);
  const grip = mk('div', 'pdock-widthgrip');
  grip.setAttribute('role', 'separator');
  grip.setAttribute('aria-orientation', 'vertical');
  grip.setAttribute('aria-label', 'Resize the dock');
  grip.tabIndex = 0;

  if (isSide) {
    const widths = L.clampSideWidths(state.dockWidths, ids, dockMaxTotalWidth());
    ids.forEach((id) => { state.dockWidths[id] = widths[id]; });
    dockEl.style.width = `${L.sideTotalWidth(widths, ids)}px`;
    wireDockWidthGripSide(grip, ids);
    dockEl.appendChild(grip);
    ids.forEach((id, i) => {
      const e = els[id] || buildChrome(id);
      els[id] = e;
      e.root.classList.add('docked');
      e.root.classList.remove('floating');
      e.root.style.position = '';
      e.root.style.left = e.root.style.top = e.root.style.height = '';
      e.root.style.flexGrow = e.root.style.flexBasis = '';
      e.root.style.width = `${widths[id]}px`;
      e.toggleIcon.innerHTML = window.HBIcons.extLink;
      e.toggleBtn.title = `Float ${TITLES[id]}`;
      e.toggleBtn.setAttribute('aria-label', `Float ${TITLES[id]}`);
      reparentPreservingFocus(e.root, dockEl);
      if (i < ids.length - 1) {
        const split = mk('div', 'pdock-split-v');
        split.setAttribute('role', 'separator');
        split.setAttribute('aria-orientation', 'vertical');
        split.setAttribute('aria-label', `Resize ${TITLES[id]} / ${TITLES[ids[i + 1]]}`);
        wireDockSideSplitter(split, ids, i);
        dockEl.appendChild(split);
      }
    });
    return;
  }

  dockEl.style.width = `${state.dockWidth}px`;
  const heights = L.dockHeights(ids, state.dockHeights);
  for (const id of ids) if (Number.isFinite(heights[id])) state.dockHeights[id] = heights[id];
  wireDockWidthGrip(grip);
  dockEl.appendChild(grip);
  ids.forEach((id, i) => {
    const e = els[id] || buildChrome(id);
    els[id] = e;
    e.root.classList.add('docked');
    e.root.classList.remove('floating');
    e.root.style.position = '';
    e.root.style.left = e.root.style.top = e.root.style.width = e.root.style.height = '';
    e.root.style.flexGrow = String(Math.max(0.0001, heights[id] || 0));
    e.root.style.flexBasis = '0';
    e.toggleIcon.innerHTML = window.HBIcons.extLink;
    e.toggleBtn.title = `Float ${TITLES[id]}`;
    e.toggleBtn.setAttribute('aria-label', `Float ${TITLES[id]}`);
    reparentPreservingFocus(e.root, dockEl);
    if (i < ids.length - 1) {
      const split = mk('div', 'pdock-split');
      split.setAttribute('role', 'separator');
      split.setAttribute('aria-orientation', 'horizontal');
      split.setAttribute('aria-label', `Resize ${TITLES[id]} / ${TITLES[ids[i + 1]]}`);
      wireDockSplitter(split, ids, i);
      dockEl.appendChild(split);
    }
  });
}
function layoutFloats() {
  for (const id of floatingOpenIds()) {
    const e = els[id] || buildChrome(id);
    els[id] = e;
    const rect = L.clampFloatRect(state.panels[id], window.innerWidth, window.innerHeight);
    state.panels[id] = { ...state.panels[id], ...rect };
    e.root.classList.add('floating');
    e.root.classList.remove('docked');
    e.root.style.flexGrow = e.root.style.flexBasis = '';
    e.root.style.left = `${rect.x}px`;
    e.root.style.top = `${rect.y}px`;
    e.root.style.width = `${rect.w}px`;
    e.root.style.height = `${rect.h}px`;
    e.toggleIcon.innerHTML = window.HBIcons.panelRight;
    e.toggleBtn.title = `Dock ${TITLES[id]}`;
    e.toggleBtn.setAttribute('aria-label', `Dock ${TITLES[id]}`);
    if (e.root.parentElement !== floatLayer) reparentPreservingFocus(e.root, floatLayer);
  }
}
function detachClosed() {
  for (const id of L.IDS) {
    if (state.panels[id].open) continue;
    const e = els[id];
    if (e && e.root.parentElement) e.root.remove();
  }
}
function paintToolbar() {
  for (const id of L.IDS) {
    const btn = document.getElementById(id === 'order' ? 'tbOrder' : 'tbDom');
    if (!btn) continue;
    const on = state.panels[id].open;
    btn.setAttribute('aria-pressed', String(on));
    btn.classList.toggle('active', on);
  }
}
function relayout() {
  detachClosed();
  layoutDock();
  layoutFloats();
  paintToolbar();
  for (const id of L.IDS) { const d = defs[id]; if (d && d.setVisible) d.setVisible(state.panels[id].open); }
}

/* ---- open / close / dock / float ---- */
function setOpen(id, v) {
  v = !!v;
  if (state.panels[id].open === v) return;
  state.panels[id] = { ...state.panels[id], open: v };
  if (v) ensureBuilt(id);
  relayout();
  save();
}
function toggle(id) { setOpen(id, !state.panels[id].open); }
/* The header icon: dock <-> float in place. Floating a docked panel seeds its rect near the dock (so it does
   not jump across the screen); docking a floated one just drops it at the end of the stack. */
function setDocked(id, docked) {
  docked = !!docked;
  if (state.panels[id].docked === docked) return;
  if (!docked) {
    const dr = dockEl.getBoundingClientRect();
    const seed = { x: Math.max(0, dr.left - 40), y: dr.top + 40, w: state.panels[id].w, h: state.panels[id].h };
    state.panels[id] = { ...state.panels[id], docked, ...L.clampFloatRect(seed, window.innerWidth, window.innerHeight) };
  } else {
    state.panels[id] = { ...state.panels[id], docked };
    state.dockOrder = L.reorderList(state.dockOrder, id, state.dockOrder.length);
  }
  ensureBuilt(id);
  relayout();
  save();
}
function bringToFront(id) {
  const e = els[id];
  if (e && e.root.parentElement === floatLayer) floatLayer.appendChild(e.root);   // last child paints on top
}

/* ---- the dock's width grip (left edge) ---- */
function wireDockWidthGrip(grip) {
  let dragging = false, startX = 0, startW = 0;
  grip.addEventListener('pointerdown', (e) => {
    dragging = true; startX = e.clientX; startW = state.dockWidth;
    try { grip.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener('blur', end);
    e.preventDefault();
  });
  grip.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
    const raw = startW - (e.clientX - startX);
    state.dockWidth = L.clampDockWidth(raw);
    const over = raw - state.dockWidth;
    dockEl.style.width = `${over === 0 ? state.dockWidth : state.dockWidth + M.rubberband(over, L.DOCK_W_MAX)}px`;
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { grip.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.removeEventListener('blur', end);
    snapAxisCSS(dockEl, 'width', state.dockWidth);
    save();
  };
  grip.addEventListener('pointerup', end);
  grip.addEventListener('pointercancel', end);
  grip.addEventListener('lostpointercapture', end);
  grip.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); state.dockWidth = L.clampDockWidth(state.dockWidth + 16); dockEl.style.width = `${state.dockWidth}px`; save(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); state.dockWidth = L.clampDockWidth(state.dockWidth - 16); dockEl.style.width = `${state.dockWidth}px`; save(); }
  });
}
/* ---- the dock's width grip, side-by-side variant: grows/shrinks the leftmost panel (order[0], the one the
   grip sits against) and re-clamps the whole pair against the viewport budget. ---- */
function wireDockWidthGripSide(grip, ids) {
  let dragging = false, startX = 0, startWidths = null;
  const apply = (dx) => {
    // the grip is at the dock's LEFT edge: dragging it left (dx < 0) grows the dock, same sense as the stack grip
    const rawDelta = -dx;
    const raw = L.applyGripDragSide(startWidths, ids, rawDelta);
    const clamped = L.clampSideWidths(raw, ids, dockMaxTotalWidth());
    ids.forEach((id) => { state.dockWidths[id] = clamped[id]; });
    // rubber-band only the panel the grip actually owns (ids[0]) -- the other panel's width never moves
    // for this gesture (applyGripDragSide), so there's nothing of its own to soften.
    const id0 = ids[0];
    const rawW0 = startWidths[id0] + rawDelta;
    const over = rawW0 - clamped[id0];
    const drift = over === 0 ? 0 : M.rubberband(over, L.DOCK_W_MAX);
    dockEl.style.width = `${L.sideTotalWidth(clamped, ids) + drift}px`;
    ids.forEach((id) => { if (els[id]) els[id].root.style.width = `${clamped[id] + (id === id0 ? drift : 0)}px`; });
  };
  grip.addEventListener('pointerdown', (e) => {
    dragging = true; startX = e.clientX; startWidths = { ...state.dockWidths };
    try { grip.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener('blur', end);
    e.preventDefault();
  });
  grip.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
    apply(e.clientX - startX);
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { grip.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.removeEventListener('blur', end);
    snapAxisCSS(dockEl, 'width', L.sideTotalWidth(state.dockWidths, ids));
    for (const id of ids) if (els[id]) snapAxisCSS(els[id].root, 'width', state.dockWidths[id]);
    save();
  };
  grip.addEventListener('pointerup', end);
  grip.addEventListener('pointercancel', end);
  grip.addEventListener('lostpointercapture', end);
  grip.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); startWidths = { ...state.dockWidths }; apply(-16); save(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); startWidths = { ...state.dockWidths }; apply(16); save(); }
  });
}
/* ---- the vertical splitter between two side-by-side docked panels: absolute px, not a fraction of a fixed
   container (the dock's total width itself moves with the split), unlike the stacked splitter below. ---- */
function wireDockSideSplitter(split, ids, i) {
  let dragging = false, startX = 0, startWidths = null;
  const a = ids[i], b = ids[i + 1];
  split.addEventListener('pointerdown', (e) => {
    dragging = true; startX = e.clientX; startWidths = { ...state.dockWidths };
    try { split.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener('blur', end);
    e.preventDefault();
  });
  split.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
    // TOTAL delta from drag start (not accumulated frame-to-frame): the same "recompute from a snapshot"
    // shape as the header drag and the width grips above, and what lets the hard-vs-raw overshoot below be
    // computed directly instead of path-dependently.
    const dx = e.clientX - startX;
    const hard = L.applySideSplitDrag(startWidths, ids, i, dx);
    state.dockWidths = hard;
    const pairSum = (startWidths[a] || 0) + (startWidths[b] || 0);
    const rawA = (startWidths[a] || 0) + dx;
    const over = rawA - hard[a];
    const drift = over === 0 ? 0 : M.rubberband(over, Math.max(1, pairSum));   // a gains `drift`, b gives up the same -- their sum (the pair's total width) never moves
    if (els[a]) els[a].root.style.width = `${hard[a] + drift}px`;
    if (els[b]) els[b].root.style.width = `${hard[b] - drift}px`;
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { split.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.removeEventListener('blur', end);
    snapAxisCSS(els[a] && els[a].root, 'width', state.dockWidths[a]);
    snapAxisCSS(els[b] && els[b].root, 'width', state.dockWidths[b]);
    save();
  };
  split.addEventListener('pointerup', end);
  split.addEventListener('pointercancel', end);
  split.addEventListener('lostpointercapture', end);
}
/* ---- the horizontal splitter between two adjacent docked panels ---- */
function wireDockSplitter(split, ids, i) {
  let dragging = false, startY = 0, startHeights = null;
  const a = ids[i], b = ids[i + 1];
  split.addEventListener('pointerdown', (e) => {
    dragging = true; startY = e.clientY; startHeights = { ...state.dockHeights };
    try { split.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener('blur', end);
    e.preventDefault();
  });
  split.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
    const containerH = dockEl.getBoundingClientRect().height || 1;
    const totalDelta = L.pixelsToFraction(e.clientY - startY, containerH);   // TOTAL from drag start, see the side splitter's own note
    const hard = L.applySplitterDrag(ids, startHeights, i, totalDelta);
    state.dockHeights = hard;
    const pairSum = (startHeights[a] || 0) + (startHeights[b] || 0);
    const rawA = (startHeights[a] || 0) + totalDelta;
    const overPx = (rawA - hard[a]) * containerH;   // rubber-band in real px, then back to a height fraction
    const driftFrac = overPx === 0 ? 0 : M.rubberband(overPx, Math.max(1, pairSum * containerH)) / containerH;
    if (els[a]) els[a].root.style.flexGrow = String(Math.max(0.0001, hard[a] + driftFrac));
    if (els[b]) els[b].root.style.flexGrow = String(Math.max(0.0001, hard[b] - driftFrac));
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { split.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.removeEventListener('blur', end);
    snapAxisCSS(els[a] && els[a].root, 'flexGrow', Math.max(0.0001, state.dockHeights[a] || 0), '');
    snapAxisCSS(els[b] && els[b].root, 'flexGrow', Math.max(0.0001, state.dockHeights[b] || 0), '');
    save();
  };
  split.addEventListener('pointerup', end);
  split.addEventListener('pointercancel', end);
  split.addEventListener('lostpointercapture', end);
}

/* ---- the dock drop zone: the dock's own rect while it is showing, otherwise a thin strip at the right edge
   of the viewport (so dragging toward an empty/closed dock still shows where it will land) ---- */
function dockZoneRect() {
  if (!dockEl.hidden) { const r = dockEl.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }
  const w = 28; return { x: Math.max(0, window.innerWidth - w), y: 0, w, h: window.innerHeight };
}
/* ---- stack-vs-side drop zones: while one panel is being dragged and exactly one OTHER panel is already
   docked+open, the target for a drop is that other panel's own rect, split into top/bottom/left/right bands
   (HBPanelLayout.dockDropZone). With 0 or >=2 other docked panels there is nothing to arrange against, so the
   drop falls back to the plain "somewhere in the dock" behaviour (dockZoneRect + dockDropIndex). ---- */
function otherDockedId(id) {
  const ids = dockedOpenIds().filter((x) => x !== id);
  return ids.length === 1 ? ids[0] : null;
}
function targetPanelRect(id) {
  const e = id && els[id];
  if (!e || !e.root.isConnected) return null;
  const r = e.root.getBoundingClientRect();
  return { x: r.left, y: r.top, w: r.width, h: r.height };
}
function resolveDropZone(id, clientX, clientY) {
  if (dockEl.hidden) return { otherId: null, zone: null };
  const otherId = otherDockedId(id);
  const zone = otherId ? L.dockDropZone(clientX, clientY, targetPanelRect(otherId)) : null;
  return { otherId, zone };
}
let paintedZoneId = null;
function paintDropZone(targetId, zone) {
  if (paintedZoneId && paintedZoneId !== targetId && els[paintedZoneId]) {
    els[paintedZoneId].root.classList.remove('drop-top', 'drop-bottom', 'drop-left', 'drop-right');
  }
  const e = targetId && els[targetId];
  if (e) {
    e.root.classList.toggle('drop-top', zone === 'top');
    e.root.classList.toggle('drop-bottom', zone === 'bottom');
    e.root.classList.toggle('drop-left', zone === 'left');
    e.root.classList.toggle('drop-right', zone === 'right');
  }
  paintedZoneId = zone ? targetId : null;
}
function clearDropZone() { paintDropZone(null, null); }
/* Applies a resolved zone to the persisted arrangement: top/bottom -> stacked, above/below the target;
   left/right -> side by side, before/after it. Falls back to a plain index-based dock insert when there is no
   single other docked panel to arrange against (dropping the very first/only panel into the dock). */
function applyDockDrop(draggedId, otherId, zone, clientY) {
  state.panels[draggedId] = { ...state.panels[draggedId], docked: true };
  if (otherId && zone) {
    if (zone === 'left' || zone === 'right') {
      state.dockOrientation = 'side';
      state.dockOrder = zone === 'left' ? [draggedId, otherId] : [otherId, draggedId];
    } else {
      state.dockOrientation = 'stack';
      state.dockOrder = zone === 'top' ? [draggedId, otherId] : [otherId, draggedId];
    }
  } else {
    const targetIndex = dockDropIndex(clientY);
    state.dockOrder = L.reorderList(state.dockOrder, draggedId, targetIndex);
  }
}

/* ---- header drag: move a floating panel, drag a docked one out to float, drag a floating one onto the dock
   to dock it, or reorder within the dock. 2026-09-28 feel pass: 1:1 tracking during the drag is unchanged
   (it was already correct -- see the audit doc); release now projects the pointer's momentum (Apple's
   project()) forward before deciding dock-vs-float, so a flick toward the dock docks even if the raw
   release point fell a little short, and the panel's landing motion is a spring, not a snap. ---- */
function wireHeaderDrag(id, root, head) {
  let dragging = false, mode = null;   // mode: null (still docked) | 'float-move' | 'convert'
  let startX = 0, startY = 0, startRect = null, vtrack = null;
  head.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;   // the toggle / close buttons own their own click
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    // Interruptible: a header grabbed while its own release animation is still playing picks up from
    // there -- the LIVE on-screen value, not the (possibly stale) target -- instead of a brick-wall stop.
    stopFlipAnim(id);
    const live = stopFloatAnim(id);
    if (live) state.panels[id] = { ...state.panels[id], x: live.x, y: live.y };
    startRect = { x: state.panels[id].x, y: state.panels[id].y, w: state.panels[id].w, h: state.panels[id].h };
    mode = state.panels[id].docked ? null : 'float-move';
    vtrack = M.createVelocityTracker();
    M.pushSample(vtrack, e.clientX, e.clientY, e.timeStamp);
    bringToFront(id);
    try { head.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener('blur', end);
    e.preventDefault();
  });
  head.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
    M.pushSample(vtrack, e.clientX, e.clientY, e.timeStamp);
    const dx = e.clientX - startX, dy = e.clientY - startY;
    if (mode === null) {   // still docked: has it cleared the dock far enough to start floating?
      const { otherId, zone } = resolveDropZone(id, e.clientX, e.clientY);
      paintDropZone(otherId, zone);
      const dr = dockEl.getBoundingClientRect();
      if (e.clientX < dr.left - DRAG_OUT_PX || dockEl.hidden) {
        mode = 'convert';
        clearDropZone();
        const w = root.offsetWidth || state.panels[id].w, h = root.offsetHeight || state.panels[id].h;
        startRect = { x: e.clientX - 20, y: e.clientY - 12, w, h };
        state.panels[id] = { ...state.panels[id], docked: false, ...L.clampFloatRect(startRect, window.innerWidth, window.innerHeight) };
        ensureBuilt(id);
        relayoutForDrag(id);
      }
      return;
    }
    const { otherId, zone } = resolveDropZone(id, e.clientX, e.clientY);
    paintDropZone(otherId, zone);
    const inDock = zone || L.pointInRect(e.clientX, e.clientY, dockZoneRect());
    dockEl.classList.toggle('drop-target', !!inDock && !zone);   // whole-dock outline only when no specific zone
    const rect = mode === 'convert'
      ? { x: e.clientX - 20, y: e.clientY - 12, w: startRect.w, h: startRect.h }
      : { x: startRect.x + dx, y: startRect.y + dy, w: startRect.w, h: startRect.h };
    // `state` stays the authoritative HARD-clamped rect throughout (everything else in this file reads it
    // that way); only the painted position rubber-bands past a viewport edge while the pointer holds it
    // there -- released, settleFloat() springs the visible pixels back onto this same clamped value.
    const clamped = L.clampFloatRect(rect, window.innerWidth, window.innerHeight);
    state.panels[id] = { ...state.panels[id], ...clamped };
    const vw = window.innerWidth, vh = window.innerHeight;
    const softX = rect.x === clamped.x ? clamped.x : clamped.x + M.rubberband(rect.x - clamped.x, vw);
    const softY = rect.y === clamped.y ? clamped.y : clamped.y + M.rubberband(rect.y - clamped.y, vh);
    const e2 = els[id];
    e2.root.style.left = `${softX}px`; e2.root.style.top = `${softY}px`;
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { head.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.removeEventListener('blur', end);
    dockEl.classList.remove('drop-target');
    clearDropZone();
    const { vx, vy } = M.velocityOf(vtrack);
    // Momentum projection (apple-design skill, "animate to where the gesture is going"): the DOCK/FLOAT
    // decision -- and, when floating, the resting spot -- is judged at the projected landing point, not the
    // raw release point, so a fast flick toward the dock lands in it even released a little short.
    const projX = e.clientX + M.project(vx), projY = e.clientY + M.project(vy);
    const { otherId, zone } = resolveDropZone(id, projX, projY);
    const inDock = zone || L.pointInRect(projX, projY, dockZoneRect());
    if (mode && !state.panels[id].docked && inDock) {
      animateDockFlip(id, () => { applyDockDrop(id, otherId, zone, projY); relayout(); }, vx, vy);
    } else if (mode) {
      // stays floating: land AT the projected point (clamped on-screen), animated from the live pixel
      // position a moment ago -- never from `state`, which may already differ (rubber-band above). Note:
      // `parseFloat(...) || fallback` would wrongly fall back on a legitimate 0 (left edge); Number.isFinite
      // is the correct guard.
      const liveLeft = parseFloat(els[id].root.style.left), liveTop = parseFloat(els[id].root.style.top);
      const liveFrom = { x: Number.isFinite(liveLeft) ? liveLeft : state.panels[id].x, y: Number.isFinite(liveTop) ? liveTop : state.panels[id].y };
      const raw = mode === 'convert'
        ? { x: projX - 20, y: projY - 12, w: startRect.w, h: startRect.h }
        : { x: startRect.x + (projX - startX), y: startRect.y + (projY - startY), w: startRect.w, h: startRect.h };
      const final = L.clampFloatRect(raw, window.innerWidth, window.innerHeight);
      state.panels[id] = { ...state.panels[id], ...final };
      settleFloat(id, liveFrom, final, vx, vy);
    } else if (state.panels[id].docked) {
      // a plain press-release inside the dock, no float conversion: a zone against the other docked panel
      // switches stack<->side and/or reorders; otherwise treat it as a plain reorder gesture, so a small drag
      // up/down still reshuffles the stack without needing to leave it first
      if (otherId && zone) {
        animateDockFlip(id, () => { applyDockDrop(id, otherId, zone, projY); relayout(); }, vx, vy);
      } else {
        const targetIndex = dockDropIndex(projY);
        const cur = dockedOpenIds();
        if (cur.length > 1) { animateDockFlip(id, () => { state.dockOrder = L.reorderList(state.dockOrder, id, targetIndex); relayout(); }, vx, vy); }
      }
    }
    mode = null;
    save();
  };
  head.addEventListener('pointerup', end);
  head.addEventListener('pointercancel', end);
  head.addEventListener('lostpointercapture', end);
}
/* While converting mid-drag, the panel needs its floating geometry applied immediately (not the full
   relayout(), which would also rebuild the dock and could steal the pointer capture mid-gesture). */
function relayoutForDrag(id) {
  layoutFloats();
  layoutDock();
  paintToolbar();
}
/* Which slot in the dock a drop at this Y lands in, among the OTHER currently docked+open panels. */
function dockDropIndex(clientY) {
  const ids = dockedOpenIds();
  let idx = ids.length;
  for (let i = 0; i < ids.length; i++) {
    const e = els[ids[i]];
    if (!e) continue;
    const r = e.root.getBoundingClientRect();
    if (clientY < r.top + r.height / 2) { idx = i; break; }
  }
  return idx;
}

/* ---- a floating panel's edge/corner resize ---- */
function wireFloatResize(id, root) {
  const dirs = ['n', 's', 'e', 'w', 'se'];
  for (const dir of dirs) {
    const h = mk('div', `hbpanel-rz hbpanel-rz-${dir}`);
    root.appendChild(h);
    let dragging = false, startX = 0, startY = 0, startRect = null;
    h.addEventListener('pointerdown', (e) => {
      if (state.panels[id].docked) return;
      dragging = true; startX = e.clientX; startY = e.clientY;
      startRect = { x: state.panels[id].x, y: state.panels[id].y, w: state.panels[id].w, h: state.panels[id].h };
      try { h.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
      window.addEventListener('blur', end);
      e.preventDefault(); e.stopPropagation();
    });
    h.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      if (!e.buttons) { end(e); return; }   // the button was released without a pointerup/cancel reaching us
      const dx = e.clientX - startX, dy = e.clientY - startY;
      let { x, y, w, h: hh } = startRect;
      if (dir.includes('e')) w = startRect.w + dx;
      if (dir.includes('s')) hh = startRect.h + dy;
      if (dir.includes('w')) { w = startRect.w - dx; x = startRect.x + dx; }
      if (dir.includes('n')) { hh = startRect.h - dy; y = startRect.y + dy; }
      const clamped = L.clampFloatRect({ x, y, w, h: hh }, window.innerWidth, window.innerHeight);
      state.panels[id] = { ...state.panels[id], ...clamped };
      // rubber-band the SIZE past its min/max (the thing this gesture is actually asking for); a west/north
      // edge also moves x/y as a side-effect of the size, so it follows the soft size too, keeping the
      // OPPOSITE (anchored) edge exactly fixed rather than decoupling position from what's driving it.
      const vw = window.innerWidth, vh = window.innerHeight;
      const softW = w === clamped.w ? clamped.w : clamped.w + M.rubberband(w - clamped.w, vw);
      const softH = hh === clamped.h ? clamped.h : clamped.h + M.rubberband(hh - clamped.h, vh);
      const softX = dir.includes('w') ? clamped.x - (softW - clamped.w) : clamped.x;
      const softY = dir.includes('n') ? clamped.y - (softH - clamped.h) : clamped.y;
      const e2 = els[id];
      e2.root.style.left = `${softX}px`; e2.root.style.top = `${softY}px`;
      e2.root.style.width = `${softW}px`; e2.root.style.height = `${softH}px`;
    });
    const end = (e) => {
      if (!dragging) return;
      dragging = false;
      try { h.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
      window.removeEventListener('blur', end);
      snapRectCSS(els[id] && els[id].root, state.panels[id]);
      save();
    };
    h.addEventListener('pointerup', end);
    h.addEventListener('pointercancel', end);
    h.addEventListener('lostpointercapture', end);
  }
}

/* Any floating panel is re-clamped into the (possibly new) viewport on a window resize, so a browser shrink
   never leaves one stranded off-screen. */
function onWindowResize() {
  let floatChanged = false;
  for (const id of floatingOpenIds()) {
    const clamped = L.clampFloatRect(state.panels[id], window.innerWidth, window.innerHeight);
    if (clamped.x !== state.panels[id].x || clamped.y !== state.panels[id].y || clamped.w !== state.panels[id].w || clamped.h !== state.panels[id].h) {
      // a resize's own correction is authoritative -- never let a still-running settle spring or FLIP
      // (from a drag that released right before the window shrank) go on fighting it for the corrected rect
      // layoutFloats() is about to paint (coordinator review, 2026-09-28).
      stopFloatAnim(id);
      stopFlipAnim(id);
      state.panels[id] = { ...state.panels[id], ...clamped };
      floatChanged = true;
    }
  }
  // a side-by-side dock's two widths need re-clamping too: a browser shrink must never leave the pair wider
  // than the (now smaller) budget, crushing the chart grid.
  let dockChanged = false;
  if (state.dockOrientation === 'side' && dockEl && !dockEl.hidden) {
    const ids = dockedOpenIds();
    if (ids.length === 2) {
      const clampedW = L.clampSideWidths(state.dockWidths, ids, dockMaxTotalWidth());
      if (ids.some((id) => clampedW[id] !== state.dockWidths[id])) {
        ids.forEach((id) => { state.dockWidths[id] = clampedW[id]; });
        dockChanged = true;
      }
    }
  }
  if (floatChanged) layoutFloats();
  if (dockChanged) layoutDock();
  if (floatChanged || dockChanged) save();
}

/* ---- public API ---- */
function mount(pg, defsIn) {
  page = pg;
  defs = defsIn || {};
  dockEl = document.getElementById('pdock');
  floatLayer = document.getElementById('floatLayer');
  if (!dockEl || !floatLayer) return;
  state = load();
  // built once at mount regardless of open state (matches orderpanel.js's own "the form is built ONCE" rule,
  // and keeps #panel-order / #panel-dom real DOM ids from the start for #tbOrder/#tbDom's aria-controls)
  for (const id of L.IDS) ensureBuilt(id);
  relayout();
  window.addEventListener('resize', onWindowResize);
  const tbOrder = document.getElementById('tbOrder'), tbDom = document.getElementById('tbDom');
  if (tbOrder) tbOrder.onclick = () => toggle('order');
  if (tbDom) tbDom.onclick = () => toggle('dom');
}

window.HBPanelShell = { mount, toggle, setOpen, setDocked, isOpen: (id) => state.panels[id].open };
})();
