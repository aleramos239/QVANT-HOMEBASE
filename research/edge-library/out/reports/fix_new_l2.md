**new_l2 fix round: all five majors are resolved inside `l2ideas.py`; three minors are not closed (8-worker identity, the C2 donor pool, the cell cap).** Full engine suite: 1,295 passed, 2 skipped by design, 0 failed (2 workers; run after the last code edit). No menu run, no ledger row, no `runs/` store, nothing from 2024 or later read, nothing committed.

## Files (under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/l2ideas.py` — rewritten stage D; D1 / D5 trading rules untouched.
- `engine/tests/test_new_l2.py` — 132 tests.
- `engine/out/new_l2_smoke.log` — regenerated, counts only; script `engine/out/fix_new_l2/stage_d_smoke.py`.
- `engine/out/fix_new_l2/suite_2workers.log` — the full-suite run.
- `ENGINE.md` § 5 — one attributed paragraph pointing stage D to `l2ideas`.
- `progress.md` — one entry appended.

`l2sim.py`, `score.py`, `library.py`, `run_menus.py` and `families/__init__.py` were not edited.

## What was fixed
- **D2 / D4 on resting entries (major):** the filter is now judged at the trade. The simulator runs the base's own bracket; each fill is kept or skipped by the filter's verdict at the 1-minute decision that began the fill's minute (gate G1 on the base's trade list). `l2ideas.kept` removes skipped fills before anything is stored.
  - Smoke, 10 BUILD days: 552 kept of 2,776 resting fills, 0 against the filter at the fill minute, every kept trade is the base's own row.
  - Before: 40 % of f_book fills went into an opposing book, verdicts up to 178 minutes old.
  - donchian (market entry) keeps the engine's rule, read at its decision.
- **D3 exit (major):** now needs a flip. The exit is armed only once the 5-minute mean has not opposed the trade (at its entry or since), then 2 opposed usable minutes. On the smoke days no trade entered into an opposing book was closed within 2 closes of its fill.
- **Where it lives:** a mixin `l2ideas.StageD` in front of the base's registered class (`stage_class(base)`, importable by workers as `families.l2ideas.D_<base>`). The engine's options on the base class still have the old semantics, so stage D must use `l2ideas.run_variant` / `variant_table` / `run_member`, never `library.run_member(base, extra=...)`.
- **Labels (major):** placed in the notes and, in brackets, after the rationale sentence (a card prints only the rationale).
  - `bimb_follow_d1`: WEAK PRIOR + SECOND LOOK (BUILD + PICK).
  - `flow_exhaust`: WEAK PRIOR + ADJACENT TO A REFUTED PROGRAM.
  - D2 on orb, donchian, straddle and straddle_t 03:00 / 09:30 / 13:30: SECOND LOOK (the L2 screen's gate G1).
- **Seal (minor):** `run_variant` reads the base unit's own BUILD store and refuses unless a session passed the plateau. The variant's `run.json` carries `base_pass_sessions`; other sessions are refused. A PICK member run needs the variant's own BUILD plateau.
- **Other minors:**
  - `variants=` removed: a variant always runs the base's whole grid.
  - Variant meta now has `l2: True` and a both-sides note.
  - The DEAD list is gone: the 18:00 filters can now trade, from 18:05 / 18:09.
  - D1 / D5 design choices are written out in the docstring, with the tf 15 / 30 reasoning corrected.

## Tests and gates
- `test_new_l2.py`: 132 passed.
- Real-day oracles on the 10 smoke days, recomputed from raw prints and rows by stamp:
  - every verdict matches;
  - every filtered resting variant equals its base's trade list minus the refused fills;
  - every book exit is a flip.
- No look-ahead: the garbage-after-cut tests pass on the new logic.
- Nine scratch mutations of the stage D rules (verdict frozen at placement, stale verdict, peek, no flip, and others) were each caught.
- Smokes ok: D1 tf 5, D5 tf 1 / 5, 36 variants + 12 bases, 1-vs-2-worker parity, C2 runs.

## Decisions for the orchestrator
- **`weak: True` on D1 and D5 was my call.** It only raises the admission bar to t ≥ 3 on BUILD and changes no trade. EDGE_SPEC marks neither as weak; take it back in `l2ideas.FAMILIES` before admission if you disagree.
- **No "variant vs base" pass criterion is pre-registered.** A variant is a candidate like any other, one rule more complex than its base, so ties go to the base.

## Open risks
- **Worker identity at 8 is still unproven** (shown at 1 vs 2 only; I am limited to 2). Run agent: `L2_TEST_WORKERS=8 pytest tests/test_new_l2.py -k identical_trades` before the menus.
- **C2 null donors include 2024 sessions** (`score.C2Features`, engine-level). No PICK price or P&L is involved, but it is not strictly BUILD-only. Not fixed.
- **The entry filters keep few trades**, about a fifth of resting fills on the smoke days. The 100-trade bar will bind for straddle_t variants; `straddle_t_1800_thin` had 0 trades.
- **`x_book` still closes most trades** on the smoke days, now after a real flip. That is the rule as EDGE_SPEC states it.
- **Cap:** 38,592 of 40,000 cells are planned before any stage D unit (figure from the NEW_TIME author's progress note). Each stage D unit costs 3× its base's cells; running with `nulls=False` first is the cheaper order.
- **Stated limits of the resting filter:**
  - a fill with no decision at its minute start is skipped;
  - the pull / re-place latency at a minute start is not modelled, also not by the 250 ms stress;
  - `oco` / `both_sides` on a kept row are the base bracket's, which is conservative for Apex.
- `run_variant` still calls the private `run_menus._record`.
- **Disclosure:** while checking the D3 fix I printed book-exit counts and timings for the `x_book` variants to my console. No P&L, no stop-vs-target split; the smoke log holds none of it.