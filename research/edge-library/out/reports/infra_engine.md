**Engine-owner report — all 8 items done; every tester-match gate passes at 100 %, the suite is green, nothing was run beyond 10-day smokes.**

The earlier interrupted run had left nothing on disk, and the engine copy itself was broken (wrong path to the old pilot, missing `sim_validate.py`, no feature cache), so I repaired that first.

## Gates (trade identity only, in-sample bundles, nothing ≥ 2025 read)
`/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine/EDGE_VALIDATION.md` — re-run on the final code, ALL PASS:

| gate | what was replayed | result |
|---|---|---|
| NQ, new options off | 7 approved picks + 88 heat-map cells | 100 % identical, net diff $0 |
| ES | 3 ES-pilot screen runs + 104 heat-map cells | 100 % identical, same skipped days |
| Random control | 1 NQ run, 1 NQ heat-map (16 cells, fixed-point stops), 1 ES run | 100 % identical |
| Clock path | new straddle at 03:00 / 09:30 / 13:30 vs existing straddle, 4 exit cells each, NQ and ES | identical trade lists |

- **Test suite:** 888 tests, 886 passed, 2 skipped by design; 77 are new (`engine/tests/test_edge_*.py`). It was run with a 3-worker cap because other research jobs were using 8–12 cores; it has not been run at the default 8 workers since the last edits.
- **GC is flagged:** no GC tester run exists, so it cannot be matched to the tester. It rests on:
  - a GC tape built with the tester's own code being byte-identical to the tester's cached file;
  - tick/point unit tests;
  - an independent replay (`nfp_lib.py`) on 5 BUILD NFP days. One stop exit there differed by one tick, traced to `nfp_lib`'s exact float comparison missing a print at the stop.

## What was built
1. **Multi-root:** `l2sim.run(root="ES"|"GC")` replays the tester's own tape cache (ES $50/pt, tick 0.25; GC $100/pt, tick 0.10; $4 round turn). GC tapes for BUILD + PICK (747 sessions the tester never cached) were built into `engine/cache/tape/GC`. Level-2 features and options are refused outside NQ.
2. **Globex clock:** the evening (18:00–24:00) runs as its own segment of the next trade date, so no trade spans midnight or the 17:00–18:00 break. `l2ref.StraddleT` is family A's reference class, with its time-shuffle null (`shift_seed`).
   - Sessions `eve` and `pre` exist for every Template family and in the scoring session tagger.
   - `run_menus` runs each cell as three independent instances (the tester's five sessions / pre / eve), so the five stay exactly the tester-matched trades.
3. **Template additions, all default off:** `stop_mode="pct"`, `f_book`, `f_thin`, `x_book`. No book signal means no entry for the filters and no action for the exit. The book exit is a market order that respects placement latency, not an instant flatten.
4. **Menu:** `l2sim.menu(root)` gives the 32 exit cells exactly as amended; `families.unit_grid` multiplies them by the registered family variants.
5. **Controls:** `l2ref.Random` (tester-matched), the time-shuffle null, and `library.best_of_nulls` (also reachable as `score.best_of_nulls`).
6. **Periods:** BUILD / PICK / EXAM are defined once in `l2sim`; every loader raises on EXAM unless `allow_exam=True`; each run records its range and period; `score.make_calendar("build"|"pick")`.
7. **`library.py`:** ledger with hard caps (a grid of N cells counts N; a batch over a cap is refused whole), plateau, day/session-matched random draws, admission (fails closed on any missing input), member folders, and `run_member`, which refuses a PICK run unless the BUILD plateau passed.
8. **`run_menus.py`:** plan / status / run / nulls / smoke. Smoke prints counts only. Exercised only on 10 BUILD days in tests (NQ, ES, GC).
9. **`ENGINE.md`:** registry contract (5-tuple with mandatory `rationale` and `complexity`), clock API, menu, filters/exits, smoke without P&L.

## Open risks and decisions for the orchestrator
- **No library family is registered yet.** The 14 Level-2 screen families are still 4-tuples; authors must add the rationale/complexity field before `run_menus` will take them. `ledger.csv` does not exist yet (0 cells used).
- **"Most central cell" is my reading:** the positive cell whose net is closest to the unit's median, ties to the lowest variant/exit index. I fixed this before any run because several parameter axes are categorical; confirm or change it before the first menu.
- **Null cells and failed batches count against the 40,000 cap** (the L2 pilot's convention). With time-shuffle nulls, feature-shuffle nulls and three roots the cap will likely bind; un-counting nulls is a one-line change in `run_menus._record`.
- **18:00 and 00:00 fires** have no warm ATR and no print in their window. They use the closing ATR30 of the most recent ended evening and anchor on the previous close (18:00) or last evening print (00:00). There is no 18:00 trade on roll days.
- **Time-shuffle shifts are clamped to the segment:** 18:00 and 00:00 only shift later, 20:00 and 13:30 only earlier.
- **Evening, pre and the clock path cannot be validated in the tester;** their proof is internal. The 2 ticks + 250 ms stress matters most there.
- **`score.py` account scoring is still NQ-only.** ES/GC account-rule scoring needs a root-aware scorer at the stack stage.
- **Run cost is unmeasured at full scale;** three instances per cell makes each unit heavier than the old screen.
- **Housekeeping:** the L2 pilot's `screen_analyze.py` is `l2_screen_analyze.py` in this engine (name clash with the old pilot's module). Any script calling `l2sim.run` with workers needs an `if __name__ == "__main__":` guard — an unguarded scratch script of mine spawned workers recursively until I killed it; a guard against nested pools is now in `pool_usable`.

## Files (all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `ENGINE.md`
- `library.py`
- `run_menus.py`
- `progress.md` (one line appended)
- `engine/l2sim.py`
- `engine/l2ref.py`
- `engine/score.py`
- `engine/families/__init__.py`
- `engine/edge_validate.py`
- `engine/EDGE_VALIDATION.md`
- `engine/tests/test_edge_*.py` (seven files)

Nothing was written outside this directory, nothing committed, no tester jobs.