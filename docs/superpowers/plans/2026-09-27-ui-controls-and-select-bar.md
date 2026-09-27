# A proper control system, and Bar Replay "Select bar". Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two things the user asked for after comparing the app with TradingView:
1. Every form control looks deliberate and consistent — today several are the browser's raw defaults sitting beside styled ones.
2. Bar Replay lets you click the exact bar on the chart to jump the cursor there, as TradingView's "Select bar" does.

**Architecture:**
- Task 1 is **mostly CSS**. Our controls are already built through `page.mk('input'|'select'|'button', …)`, so styling the element types and the handful of shared classes in `charts.css` upgrades the whole app without touching every call site. Only where native chrome cannot be styled — a `<select>`'s arrow, a number input's spinners — does markup change.
- Task 2 extends the existing replay overlay, which already has a "pick a start" click mode. The same picking mechanism becomes available *during* a replay, from a button on the control bar.

**Tech Stack:** plain-JS IIFEs; Lightweight Charts 5.2.1; Node 26; CSS custom properties already defined in `charts.css`.

**Spec:** the user on 2026-09-27:

> "i want to upgrade our UI, for example look at the difference between our buttons, our typable text boxes and the ones with trading view, also they bar replay lets them click the exact bar on the chart to go back to"

Their standing preference also applies: the chart UI must look like TradingView and never "AI-made" — one top toolbar, Lucide icons, never TradingView's own icons, light default.

## Global Constraints

- **Appearance only in Task 1.** No behaviour, no handler, no value semantics may change. Every existing test must pass untouched.
- **Both themes.** Every control is defined with the existing CSS tokens and checked in light and dark; never a hard-coded colour.
- **Accessibility does not regress:** visible focus rings on keyboard focus, hit targets at least 28 px tall, `disabled` visually distinct, and every existing `aria-*` left as is.
- Lucide icons only, copied exactly from lucide-static@1.48.0. No native dialogs.
- **Replay safety is untouched:** a chart in replay can never send a real order, and picking a bar is a read-only navigation action.
- Leave the `?v=` tags; the controller bumps them at release.

---

### Task 1: The control system (appearance)

**Files:** `homebase/static/charts/charts.css` overwhelmingly; `app.js` / `settings-dialog.js` / `testerui.js` / `orderpanel.js` only where markup must change for a wrapper or an icon.

**Before starting, invoke the UI skills** the user keeps for this work and follow them: `impeccable`, `design-taste-frontend`, `emil-design-eng`, `ui-ux-pro-max`. Compose them — structure, then anti-slop, then polish, then reference.

- [ ] **Audit first.** List every distinct control in the app and how it is currently styled: text inputs, number inputs, selects, date inputs, buttons (primary / secondary / ghost / icon), switches, checkboxes, radio groups, menu items, tabs, pills. Note which are raw browser defaults today. Put the table in the report. The known offenders are the Strategy Tester header's `input[type=date]` and `input[type=number]`, and every `<select class="set-select">`'s native arrow.
- [ ] **One set of rules**, on the element types plus the existing shared classes, so call sites need no change:
  - a single border, radius, height and inner padding shared by every text-like control;
  - a focus ring that reads clearly in both themes, on `:focus-visible` only;
  - hover, active, disabled and invalid states;
  - `<select>` gets its native arrow removed and a Lucide chevron placed by CSS, with padding for it;
  - `input[type=number]` loses its spinners in favour of our own, or loses them entirely where they add nothing;
  - buttons get primary / secondary / ghost / icon variants with consistent weight and spacing.
- [ ] **Numbers line up:** every numeric field and every table of prices or money uses tabular figures.
- [ ] **Apply and check** across the Settings dialog, the Strategy Tester header and its sub-tabs, the order panel, the bottom panel's tables, the toolbar and the menus. Nothing may shift layout enough to reflow a panel.
- [ ] Both themes checked, and a narrow window checked.

### Task 2: Bar Replay "Select bar"

**Files:** `homebase/static/charts/replayui.js`, `replay.js` (pure helpers), `icons.js`, `charts.css`.

- [ ] The replay control bar gains a **Select bar** button (Lucide `between-horizontal-start` or the closest fit), sitting left of the transport controls, matching TradingView's placement.
- [ ] Pressing it arms bar-picking on that replaying chart: the crosshair becomes a vertical marker that follows the mouse, the bar under it highlights, and the bar's ET date and time show beside the cursor. Clicking jumps the replay cursor to that bar; Esc or pressing the button again cancels.
- [ ] Jumping **backwards** rewinds the replay to that bar, so the chart redraws with everything after it hidden again. Jumping **forwards** fast-forwards to it. Both go through the existing `replay_ctl` `jump` op — check `homebase/charts/barreplay.py` for whether a backwards jump is supported and say so in the report if the backend needs a change.
- [ ] While picking is armed, the chart's other click behaviours are suppressed, exactly as the existing "pick a start" mode does, and the same safety holds: no order can be sent from a replaying chart.
- [ ] Practice trading, if a position is open when you jump backwards, is **reset** with a one-line note — a position cannot survive a rewind past its own entry. Say so in the UI.
- [ ] Tests for the pure parts: bar-at-x resolution, the cursor label's ET formatting, and the jump op built for a backwards and a forwards target.
