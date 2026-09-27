# Strategy Tester: preset ranges, no holdout guard, selectable walk-forward ratios. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the 2025+ holdout guard from the Strategy Tester, replace the range control with a short list of presets, and let walk-forward run at a chosen IS:OOS ratio.

**Architecture:** The tester UI (`testerui.js` / `tester.js`) loses the holdout switch, its reason field and the blocking error. The server-side gate (`homebase/backtest/discipline.py`, and the tester API and grid/walk-forward callers) stops refusing ranges. The spend log keeps recording which runs touched 2025+, as a silent record only — it never blocks or prompts.

**Tech Stack:** Python 3 / FastAPI / pytest; plain-JS IIFEs; Node 26.

**Spec:** the user's instruction on 2026-09-27, verbatim:

> "remove all of it, i just want to have preset times to run, 2021-2024, 1:1,2,3 month IS and OS walkfoward ratio, and then OOS for each, and 2025-2026, and also 2022-2024"

This replaces the earlier rule that 2025+ needed the Holdout switch and a typed reason per use. The user was shown what the guard protected and chose to remove it.

**Reading of "and then OOS for each"** (state it in the UI so it is unambiguous): for each walk-forward ratio, the results table reports the selection (in-sample) result *and* the stitched out-of-sample result side by side, so the IS→OOS drop is visible per ratio. If the user meant something else, this is the line to change.

## Global Constraints

- **Nothing blocks a range any more.** No switch, no reason, no refusal, no 400 from the server on a date. Every preset and every custom range runs.
- **The spend log still writes.** `discipline`'s record of runs touching 2025-01-01 or later keeps appending (strategy, range, timestamp) so past results stay attributable. It is write-only: never read back to gate a run, and never surfaced as a prompt.
- **Numbers must not move.** A 2021-2024 run before and after this change must produce a byte-identical report. Pin it with a test.
- The house fill law, the weekday-grid Sharpe, and the machine-wide cap of 2 backtest processes with no starts 09:20-09:35 ET all stay exactly as they are.
- Lucide icons only. No native dialogs. Bump every `charts.html` script tag by one `?v=` in the last commit, and the desk's Charts link with it.

---

### Task 1: Remove the holdout guard

**Files:** `homebase/backtest/discipline.py`, `homebase/charts/tester_api.py`, `homebase/backtest/{runner,grid,walkforward}.py` (wherever the refusal or the `holdout` flag is threaded), `homebase/static/charts/tester.js` and `testerui.js`.

- [ ] Delete the holdout switch, the reason input, the amber banner, the "spends holdout" Run label and the blocking error text from the header. `X.problems()` no longer returns a holdout problem; `body()` no longer sends a `holdout` field.
- [ ] `discipline` stops refusing. Keep a `record(strategy, start, end)` that appends to the spend log when the range reaches 2025-01-01 or later, called from the same place the refusal used to be. Its return value is ignored by every caller.
- [ ] The grid and walk-forward paths stop forcing the research window: they run whatever range they are given.
- [ ] Remove `RESEARCH_ONLY_TABS` gating that exists only to disable the switch.
- [ ] Tests: a 2025-2026 range runs and returns a report; the spend log gains a line; a 2021-2024 range writes no line; the existing 2021-2024 golden report is byte-identical to before.

### Task 2: Preset ranges

**Files:** `homebase/static/charts/tester.js` (`RANGES`), `testerui.js` (`rangeGroup`).

- [ ] `RANGES` becomes exactly, in this order:
  - `2021-2024` → 2021-01-01 to 2024-12-31 (the default)
  - `2022-2024` → 2022-01-01 to 2024-12-31
  - `2025-2026` → 2025-01-01 to today
  - `All (2021-now)` → 2021-01-01 to today
  - `Custom` → the two date inputs, as now
- [ ] Picking a preset fills start/end and runs with no further input. The date inputs show only for Custom, and leaving Custom clears start/end (the existing I3 fix stays).
- [ ] The date inputs keep the focus fix from `fix/tester-date-focus`: they call `syncRunState()`, never `refreshHeader()`.
- [ ] Tests for the preset → (start, end) mapping, including that `2025-2026` and `All` end at today.

### Task 3: Walk-forward IS:OOS ratio

**Files:** `homebase/backtest/walkforward.py`, `homebase/charts/tester_api.py` (the scheme route), `tester.js`, `testerui.js`.

- [ ] The Walk-forward tab gains a **Ratio** select: `1:1`, `1:2`, `1:3` (months in-sample : months out-of-sample). `1:3` stays the default, matching today's behaviour.
- [ ] The scheme generalises: select on 1 month, test on the next N, stepping so the stitched out-of-sample covers each month exactly once (step by N, the existing no-overlap rule).
- [ ] The per-step table gains the selection month's own (in-sample) result beside its out-of-sample result, and the summary shows both stitched totals with the IS→OOS drop in $ and in Sharpe. Label the columns "In-sample (selection)" and "Out-of-sample".
- [ ] The ratio is part of the job's identity: switching it does not show a stale result.
- [ ] `GET /api/tester/walkforward-scheme` reports the step count for the chosen ratio and range; the UI reads it rather than assuming.
- [ ] Tests: stepping and non-overlap at each ratio; a range too short for one full window; the IS and OOS numbers for a step match single runs over those months.
