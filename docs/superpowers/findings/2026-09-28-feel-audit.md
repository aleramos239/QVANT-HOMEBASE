---
title: Feel-pass audit — Homebase charts page
date: 2026-09-28
---

Scope: `homebase/static/charts.html` + `homebase/static/charts/*.js` + `charts.css`. The desk page
(`index.html`) is a separate stylesheet/design system (`shadcn.css`) and is not touched by this pass — the
brief's own build steps (spring module, panel physics, glass tokens "already in charts.css") are all
charts-page-scoped. Out of scope by the brief's own exclusion list, confirmed by reading their code: the
chart canvas/axes, `.tl-chip`/`.tl-text` (order/position line chips, tradelines.js — precise price drags,
not chrome), `.dom-row`/`.dom-*` (the DOM ladder, dom.js/domui.js), `.lg-ohlc`/`.lg-vals`/`.l2-imb*` (legend
values). These stay exactly as they are.

## Input-path latency

- No debounce or artificial timer sits on any button/menu/toolbar input path. The `setTimeout` calls in
  `app.js:1500,1636,1661,1665,1814`, `panelshell.js:38`, `drawings.js:295`, `newsui.js:46,145`,
  `testerui.js:882,892,1668,1672,2037,2041` are all legitimate (arm-to-confirm windows, localStorage-write
  debounce, backend job polling, reconnect backoff) — none delay visual feedback. No ~300ms tap-delay risk:
  this is a desktop WKWebView app, not a touch surface.
- Feedback is release-triggered, not press-triggered, almost everywhere. Only `.btn` (charts.css:1024-1034)
  and the fast-paper send buttons (`.tr-sell/.tr-buy/.op-send:active`, charts.css:750) get a pointerdown-time
  (`:active`) response. Every other interactive surface — `.tb-btn`/`.tb-pill` (toolbar), `.rail-btn`
  (drawing rail), `.tab-btn` (layout tabs), `.menu-i`/`.menu-row`/`.menu-star`/`.ib` (menu rows, icon
  buttons), `.dtb-btn`/`.dtb-swatch` (draw toolbar), `.hb-news-chip`/`.rp-chip`/`.tst-badge`/`.set-tab`/
  `.bp-tab`/`.tst-tab`/`.seg button`/`.grid-pick` (chips/segmented controls/tabs), `.lg-row` (legend rows),
  `.cell-gear`, `.hbpanel-btn` — has only `:hover`, no press state. Build target 2.3.
- `.op-chead` (Exits / Extra settings collapse in the order panel) only transitions its chevron
  (charts.css:724); the body show/hide itself is an instant `[hidden]`-style cut, no animation. Noted, not
  addressed — below the brief's cutline (not a listed surface) and a height transition on a variable-content
  block is its own can of worms; left alone.

## 1:1 drags — grab-offset correctness

- `panelshell.js` `wireHeaderDrag` (float move, line 460-490), `wireDockWidthGrip` (258), `wireDockWidthGripSide`
  (289), `wireDockSideSplitter` (327), `wireDockSplitter` (355), `wireFloatResize` (546) are all delta-based
  (`startRect.x + (e.clientX - startX)`), never snap-to-pointer — the grab offset is already correct
  everywhere in this file. All nine gestures already handle the `pointercancel`/`lostpointercapture`/
  `!e.buttons` (buttons-lost) cases per GOTCHAS. Nothing here was broken; the gap is momentum, not tracking.
- `drawings.js` (trend/hline/rect point drags, `on.move` machinery ~L440-470) and `tradelines.js`
  (`startDrag`/`startExitDrag`, price-chip vertical drag ~L577-680) map the pointer straight to a chart price
  via `coordinateToPrice`, not a pixel delta — a different, correct pattern for a value-setting drag. Left
  untouched: these are precision, money-adjacent drags (chip price = an actual stop/target), explicitly
  excluded from the "add physics" list, and TradingView's own such drags are similarly snap-exact, not
  springy.

## Hard stops that should rubber-band

- `panellayout.js` `clampFloatRect` (24), `clampDockWidth` (17), `clampSideWidths` (141),
  `applySplitterDrag` (84), `applySideSplitDrag` (165) are all `Math.min(hi, Math.max(lo, v))` — a dragged
  panel, grip or splitter stops dead the instant it reaches a bound. Build target: soften with
  `HBSpring.rubberband()` live during the drag in `panelshell.js`, still landing on the exact hard-clamped
  value at release (the pure clamp math in `panellayout.js` is unit-tested and correct — kept as the
  ground truth, not touched).
- The floating panel never animates between docked and floating layout: `relayout()` (panelshell.js:217)
  reparents synchronously — CSS `left/top/width/height` are set (or cleared, for a dock reparent) in the same
  tick with no transition. A drag release today decides dock-vs-float from the raw release point only
  (`resolveDropZone`/`pointInRect` at lines 498-499) — a fast flick toward the dock that releases just short
  of it currently floats instead of docking. Build target 2.2.

## Enter/exit paths and transform-origins

- Every popup surface is instant-insert / instant-remove, no transition, no `@starting-style`, no
  `transform-origin` set anywhere in `charts.css` (`grep transform-origin` = 0 hits) or any `charts/*.js`
  file. Confirmed by reading the code, not just CSS: `openMenu`/`closeMenu` (app.js:308,337) and
  `openDialog`/`closeDialog` (app.js:949,972) are the single chokepoint for essentially every menu and dialog
  in the app (symbol/interval/grid/tab/context/indicator/magnet/swatch menus, Settings, Indicators, the
  confirm dialog, the Delete-layout/Leave-replay confirms, drawing-style dialogs) — `replayui.js`,
  `tradeui.js`, `testerui.js` all call through the same `page.openMenu`/`page.openDialog`. One fix at the
  root fixes all of them.
- `closeHotkeyBox` (app.js:463), toast() (deskclient.js:131-148), `closeDrawToolbar` (app.js:1193, inserted
  via `syncDrawToolbar` app.js:1280-1286), and the Bar Replay control bar (`Overlay.build`/`destroy`,
  replayui.js:717-718/981-992) follow the identical instant-insert/instant-remove pattern independently.
- No exit path exists at all today for any of the above (`el.remove()` is always synchronous) — so "enter
  and exit along the same path" is currently "enter and exit are both instant," which is trivially symmetric
  but not what the brief wants. Build target 2.5: a shared `HBSpring.materialize`/`dematerialize` pair
  (`data-motion` attribute + CSS transition, not a JS spring — see reasoning in the build report) wired into
  all six chokepoints above.
- Dialogs open centered (`.backdrop { display:grid; place-items:center }`) — correctly exempt from
  trigger-anchoring per Emil Kowalski's "modals stay centered" rule; menus/popovers should anchor to their
  trigger once `transform-origin` exists. `placeMenu()` (app.js:318) already computes the anchor rect right
  before showing the menu — the natural place to also set `transform-origin`.
- One nesting hazard for the coming glass pass: swatch/template popovers opened with `{ root: box }`
  (app.js:1057, 1440 — indicator-settings and Settings dialogs' own `toggleMenu` hosts) render as DOM
  descendants of `.dialog`, so a translucent `.menu` there would sit directly on a translucent `.dialog` —
  the "never stack light glass on light glass" rule. Handle with a `.dialog .menu` CSS override (solid, no
  blur), not a JS special case.

## Reduced-motion / reduced-transparency / contrast

- `prefers-reduced-motion` is already handled in three places: `.tr-sell/.tr-buy/.op-send.sending::after`'s
  "sending" stripe (charts.css:757-759), `.tst-eval-spin` (894), and `.btn:active` (1034). Good existing
  pattern to extend, not a green field.
- `prefers-reduced-transparency` and `prefers-contrast`: zero hits anywhere in `charts.css` or `shadcn.css` —
  expected, since there is no translucency yet to react to. Build target 2.6, alongside the new glass rules
  themselves (add both together so glass never ships without its accessibility fallback).

## Typography

- `font-variant-numeric: tabular-nums` is already broad and deliberate (2026-09-26/27 passes) — present on
  every price/qty/P&L surface checked: `.lg-ohlc`, `.lg-vals`, `.l2-imb`, `.lg-trade`/`.tr-px`, `.dom-rows`,
  `.op-tiles`, `.tst-tile-v`, `.bp-table`, `.cf-note`, `.set-acct-bal`, `.lg-paper-stats`, the whole
  `:where(...)` control block (charts.css:986-1007), `.statusbar`. No gaps found in a full read of the file.
- Zero size-specific letter-spacing tuning: every `letter-spacing` in the file (`.menu-h` .06em uppercase,
  `.set-cap` .04em uppercase, `.hbpanel-title` .03em uppercase, `.bb-pill.warn` .02em, `.tab-btn`/`.replay-pill`
  etc.) is on small uppercase labels, which already want *positive* tracking and already have it. What is
  missing is the *large*-text side of the rule: `.dlg-head` (20px/600), `.op-tpx`/`.tr-px` (15px/600),
  `.tst-tile-v` (18px/600), `.lg-title` (16px) carry the default `letter-spacing: normal` with no negative
  tracking at all. Build target 2.7 — a small, deliberately subtle correction (Apple's own guidance: tighten
  large text slightly, body stays at 0 — these aren't display-scale numbers, so the correction is a fraction
  of what a hero headline would get).
- No custom easing curves exist anywhere (`grep cubic-bezier charts.css` = 0 hits before this pass); every
  transition uses the bare `ease`/`ease-out`/`ease-linear` keyword. Emil Kowalski's guidance (loaded skill):
  the built-in curves are "too weak" for anything meant to read as physical. Build target: add
  `--ease-spring-out`/`--ease-spring-in` cubic-bezier tokens to the existing `:root` token block.

## Design decision carried into the build (recorded here so it's visible before the diff)

Two different "spring" treatments are used on purpose, not inconsistently:
- **Real analytic springs (`spring.js`'s `Spring`, rAF-driven, velocity-carrying)** — only for the floating
  Order/DOM panel drag (2.2), because it is the one gesture-driven, re-graspable-mid-flight interaction in
  this file (apple-design's interruptibility principle is specifically about things a user can grab again
  while they're still moving).
- **CSS transitions on a strong cubic-bezier ("spring-shaped") curve** — for every click-triggered surface
  (menus, dialogs, toasts, the draw toolbar, the replay bar). These are never dragged and never re-triggered
  mid-gesture, so Emil Kowalski's explicit guidance applies verbatim: "use CSS transitions over keyframes for
  interruptible UI... transitions retarget smoothly," at a fraction of the cost of a rAF loop per popup.
  Critically damped by default (no bounce) everywhere in this category, matching "bouncy only where a gesture
  carried momentum."
