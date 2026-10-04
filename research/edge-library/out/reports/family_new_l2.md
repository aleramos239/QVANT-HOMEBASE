**new_l2 group report — D1 and D5 are registered as library candidates and smoke clean; the three Level-2 options are wired as stage D variants, but outside the registry, because the registry refuses them by design.** Full suite: 1,257 passed, 2 skipped, 0 failed (run at 2 workers, not 8). No menu was run and no ledger or `runs/` exists.

## Files (all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/l2ideas.py` — new; its docstring is the pre-registration and the stage D recipe.
- `engine/tests/test_new_l2.py` — new, 118 tests.
- `engine/out/new_l2_smoke.log` — counts-only smoke output.
- `progress.md` — one entry appended.

Nothing else was edited, nothing committed, no tester jobs, nothing from 2024 or later read.

## What was built
- **D1 `bimb_follow_d1`** (NQ, tf 5): the L2 screen's `bimb_follow` class unchanged, z variants {1.5, 2.0, 2.5}, complexity 3. The name carries `_d1` because `bimb_follow` is already taken by the screen's own entry in `book.py`.
- **D5 `flow_exhaust`** (NQ, tf 1 and 5): percentile variants {85, 90, 95}, complexity 5. It fades a bar that makes a new session high or low on a top-percentile delta in that direction but closes in the opposite half of its range.
- Both carry the EDGE_SPEC rationale word for word and get C2 nulls from `run_menus`. That is 3 units × 96 cells, plus 192 null cells each.
- **Stage D** (D2 `f_book`, D3 `x_book`, D4 `f_thin`): `l2ideas.STAGE_D` lists 36 variants on `orb`, `donchian`, `straddle` and the nine `straddle_t_<HHMM>`.
  - `variant_grid` returns the base unit's own grid with the engine's option switched on, same cell ids.
  - `run_variant(name, tf, base_plateau=...)` writes `runs/<name>-NQ-tf<tf>/` plus two C2 stores through `run_menus`' store and capped ledger. It refuses to run until handed a base plateau with `pass: True`.
  - For a single member cell: `library.run_member(base, ..., extra=l2ideas.option(name))`.

## Deviation from the task text
The task asked for the options as registry variants. `families.check_entry` refuses any L2 option in a registry entry or variant, and `run_menus` plans every registered family as a base unit. I kept them out of `FAMILIES` rather than work around that guard. The Run stage calls `run_variant` instead of `run_menus.py run --family`.

## Tests
- `test_new_l2.py`: 118 passed on its own (about 2.5 min).
- Smokes (10 BUILD days, 1 worker, counts only): D1 tf5, D5 tf1 and tf5 all `ok: true` — no dropped session, evening and pre-open sessions trade, 1-vs-2-worker parity holds, C2 runs.
- **Definition checks:** D1 and D5 signals match an independent oracle at every decision, on synthetic days and on the 10 real BUILD days (D5 recomputed from the raw tape and raw table by row stamp).
- **No look-ahead:** with every print and feature row after a cut replaced by garbage, nothing earlier changes. Run synthetically and on real days with cuts at 10:15:23, 09:30:23 and 20:00:07 ET.
- **Options on the breakout families:** every entry verdict (6,714) and every book exit matches a by-stamp oracle on the real days. A variant runs on the same sessions as its base, and option-off equals the base.
- **Worker identity:** same trades at 1 and N workers for D1, D5 and the stage D variants. I ran N = 2 (the limit for non-run agents); the test defaults to 8 and has not been run at 8.
- **Mutation checks** (scratch only): a one-row peek in the book mean, in D5's delta and in D1's z-score, a wrong exit count, a wrong thin threshold and three D5 rule changes were each caught by at least one test. The real-day garbage test alone does not catch a D5 peek; the oracle and the synthetic garbage test do.

## Open risks and decisions for the orchestrator
- **D5 details I decided before any run:**
  - tf 1 and 5 only, because 60 trailing bars do not fit the feature slice at tf 15 or 30;
  - a wick counts as the new extreme;
  - no extra warm-up beyond one earlier session bar;
  - the flow families' `book_ok` guard is inherited, so D5 does not trade on roll day ±1.
- **Filters are read when the order is placed, not at the fill.** On orb and the straddles each leg of the resting pair is checked at its clock time, so `f_book` nearly always leaves one leg and no OCO. That changes the strategy's shape, not just its trade count.
- **Two variants can never trade:** `straddle_t_1800_fbook` and `_thin`, because no book row exists before the 18:00 reopen. They are listed as `DEAD` and refused.
- **`f_thin` trades rarely** on the smoke days (some straddle times on 1 day of 10), so the 100-trade admission bar may bind.
- **Cap:** each stage D unit costs three times its base's cells (grid plus two C2 nulls). The full table cannot fit under 40,000; `variants=` restricts a run to the member's variant.
- **`run_variant` calls `run_menus._pass`,** a private function. A change there breaks it; the tests would show it.
- **Exam caveat:** a variant's pass loads book columns, so a month that fails the snapshot-phase check adds 1 s of latency to the variant but not to its base store. No BUILD or PICK month failed.
- **D1 has no half-day cut** (unchanged from the screen): on a half day it can enter between 13:10 and 13:15 and be flattened at 13:15.
- **Disclosure:** while checking that the book-exit test was not vacuous I printed pooled exit-reason counts (book / stop / target / time) for the `x_book` variants on the 10 smoke days. No P&L was looked at and no definition changed afterwards; the only later change was the `DEAD` list, which came from zero trade counts.