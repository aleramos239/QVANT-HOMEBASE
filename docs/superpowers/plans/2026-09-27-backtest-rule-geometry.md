# Show a backtest's rules on the chart: entries, stops, targets and gates. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a backtest is loaded, the chart shows what the strategy actually decided that session — every level it placed, not only the fills. For the 9:30 straddle that means the anchor, BOTH entry offsets, and each leg's stop and target, with the leg that never filled clearly marked.

**Architecture:** The engine already carries this: `ctx.hline(name, price)` records a per-session level and `ctx.plot(name, t_ns, value)` records a series, both surfacing on the run bundle as `plots.hlines` / `plots`. `testerlayer.js` already draws every hline as a dotted grey segment across its session. The gap is at both ends: the strategies emit almost nothing (the straddle emits only `anchor`), and the page draws every level identically. So this plan is mostly **emit more, and draw it meaningfully** — no new transport.

**Tech Stack:** Python 3 / pytest; plain-JS IIFEs; Lightweight Charts 5.2.1 primitives; Node 26.

**Spec:** the user's request on 2026-09-27, verbatim:

> "when i run a backtest of a strategy, i want to be able to see the exectution, where the sl and tp was, and what ever indicator or rules was used, for example in the 9:30 straddle, i want to see both offset of where the long and short entry were"

## Global Constraints

- **No backtest number may move.** This adds recording and drawing only. A 2021-2024 report's trades, equity and stats must be byte-identical before and after, pinned by a test. Emitting an hline must never change order placement, fill logic or timing.
- The house fill law, the weekday-grid Sharpe and the machine-wide backtest caps are untouched.
- **Cost:** hlines are per session and a run can hold years. Keep the payload bounded (a fixed, small number of levels per session) and keep the existing rule that a level is drawn only while its session is on screen.
- Lucide icons only. No native dialogs. Leave the `?v=` tags; the controller bumps them at release.

---

### Task 1: Strategies record their geometry

**Files:** `homebase/strategies/straddle.py`, `nq10am.py`, `gc_nfpcpi.py`, `base.py` (docstring), and `homebase/backtest/engine.py` only if `hline` needs a `role`.

- [ ] **Extend the hline record with a `role`** so the page can style it without parsing names: `ctx.hline(name, price, role=...)` where role is one of `anchor`, `entry`, `sl`, `tp`, `level`. Default `level`, so existing callers are unchanged. The record becomes `{name, price, date, role}`.
- [ ] **`OpenStraddle` emits its full plan** at the fire time, for BOTH legs, whatever fills later:
  - `anchor` (role `anchor`) — already emitted, keep the name;
  - `Long entry +{off}` and `Short entry −{off}` (role `entry`) at each leg's trigger;
  - `Long SL` / `Long TP` and `Short SL` / `Short TP` (roles `sl` / `tp`) at each leg's bracket, as computed from the trigger.
  - The `{off}` in the label is the strategy's own offset, so the label reads "Long entry +5".
- [ ] **Mark what happened to each leg.** After the session resolves, record which side filled: emit `filled` on that side's entry hline and `cancelled` on the other. Simplest is a per-session `ctx.note(side, outcome)`; if that needs new plumbing, instead emit the unfilled leg's levels under a name suffixed " (not filled)" and let the page dim by that. Pick one and say which in the report.
- [ ] **Brackets move to the fill.** The desk re-prices SL/TP to the actual fill, and the straddle mirrors it. Emit BOTH: the planned bracket at the trigger, and the final bracket at the fill, so the difference is visible. Name them "Long SL (planned)" and "Long SL".
- [ ] **`nq10am`** emits its signal level, its stop (already there) and its target, plus its gate: when the top-quarter-close filter or an ADX gate decides, plot the gate's value as a series so the reason is on screen.
- [ ] **`gc_nfpcpi`** inherits the straddle's emission; confirm it appears and that the event-day tag is visible.
- [ ] Tests: the exact hline set for a straddle session at a known anchor, on both the filled and unfilled sides; roles set correctly; a byte-identical 2021-2024 report before and after; and a skipped session emitting no entry levels.

### Task 2: Draw the geometry so it reads at a glance

**Files:** `homebase/static/charts/testerlayer.js`, `charts.css`, and `testerui.js` for the toggle.

- [ ] **Style by role**, not by name: `anchor` is a solid thin neutral line; `entry` uses the side's colour (blue long, red short); `sl` is red; `tp` is green; `level` stays neutral. A "(planned)" or "(not filled)" level is drawn dimmed and more finely dashed than its live counterpart.
- [ ] **Label each line** at the right-hand end with its name and price, e.g. `Long entry +5 · 30,925.00`. Labels stack without overlapping when levels are close, and hide below a minimum bar width so a zoomed-out year is not a wall of text.
- [ ] **A "Rules" checkbox** beside "Hide trades" in the tester's sub-tab bar toggles the geometry independently of the trade markers. Its state persists per viewer in localStorage, in try/catch.
- [ ] **Series plots** (`bundle.plots`, e.g. an ADX gate) draw in the indicator pane below the chart, not over the candles, and only when Rules is on.
- [ ] **Hover** on any level shows its name, price and session date.
- [ ] Tests for the pure parts: role → style mapping, label layout and collision handling, and the visible-window bound.
