**Sim fixes done: the look-ahead hole is closed, the validation gate still passes at 100%, and the whole test suite passes (310 passed).**

## Major: look-ahead in `ctx.feat`
- **Guard:** `ctx.feat(name, back)` now raises `LookAheadError` for any negative, non-integer or bool `back`; `ctx.feat_window(name, n)` does the same for `n`, and `n=0` now returns an empty array (it used to return everything).
- **Never swallowed:** a `LookAheadError` aborts the run. It is not booked as a skipped session; the same holds for `HoldoutSealed`, `PermissionError` (the data layer's seal) and `MemoryError`.
- **Independent-clock test:** on nine in-sample days (either side of DST changes, a roll day, a half day, the last session), at every 1-minute bar close the newest visible flow row must equal the bar the engine built from the tape's own timestamps. One second before a minute ends, that minute's row must not be visible yet.
- **Power:** the same check goes red for constant shifts of ±1 s, ±60 s, −120 s and ±3600 s, and for a shift injected inside the adapter itself. It also runs through worker processes via a new `l2ref.ClockProbe`.
- **Verifier's own test:** `test_feat_guard_holes` now passes. Their `test_harness_catches_a_peeker[PeekFeat-True]` now fails by design, because the peek it relies on is refused.

## Minor items (all fixed)
- **Input validation:** `Strategy` now validates and coerces like the tester's `resolve_inputs`. Declare choices and ranges in `SCHEMA`; undeclared keys are typed by their default. `tf=15`, `n=20.7`, `stop_val=-3`, `dir='sideways'` and `max_tr=0` now raise; a parity test against the tester's own function is included.
- **`session_independent`:** defaults to `False` as in the tester; `Template`, the three reference families and the probes set it `True`. A raw strategy with cross-day state now gives identical trades at 1 and 4 workers (it is forced onto one process).
- **`Template.ROLLS`:** filled for direct `run_session` calls too, from the cached in-sample roll list. `run_session` also detects a roll day from the prior daily bar's contract.
- **Strategy exceptions:** the session is dropped (orders cancelled, trades discarded) and listed under `no_trade` as `strategy error: <Type>: <msg>`. The count is in `result["skipped_by_error"]` and in the bundle's coverage block, with a warning on stderr. `on_error="raise"` propagates for debugging.
- **Unrealistic winners:** `l2sim.unrealistic_winners(trades)` lists limit-entry trades with exit `tp` and MAE at or beyond the stop distance; the count is in `result["unrealistic_winners"]`.
- **`strict_limit=True`:** a limit entry whose fill print is already through its stop is stopped out on that print; nothing else changes.
- **Sensitivity options:** `run` / `run_many` and the CLI take `slip_ticks`, `latency_ms` and `strict_limit`, defaulting to the tester's values. `l2sim.STRESS` is 2 ticks / 250 ms, and any deviation is recorded in `meta["stress"]`. A differential test shows the stressed sim equals the tester's engine configured the same way.
- **Open risks documented:** `SIM_VALIDATION.md` now has an "Open risks" section covering the 1-tick slip against the spread, zero-latency cancels and flattens, the 85 ms sensitivity, and the limit-entry stop arming. The spread numbers were recomputed and match the verifier's. It also notes that `ctx.daily` / `datr()` are not gate-covered.

## Validation gate (re-run 21:46 ET, final code)
- **Gate:** PASS. straddle-tf30#10, orb-tf5#10 and donchian-tf15#10 are each 100% matched on all 20 fields, net diff $0.00, 0 sessions dropped by error.
- **Wider checks:** the four other baseline picks match 100%, all 88 grid cells are identical, and the tape is identical on 825 of 825 sessions.

The new stress table shows how much the approved picks depend on execution assumptions (full in-sample, net $):

| config | tester law, all sessions | 2 ticks + 250 ms, all sessions | tester law, pick session | 2 ticks + 250 ms, pick session |
|---|---|---|---|---|
| straddle-tf30#10 (nyam) | +141,158 | +115,698 | +95,315 | +87,475 |
| orb-tf5#10 (mid) | +16,152 | −17,043 | +62,610 | +52,215 |
| donchian-tf15#10 (pm) | −8,064 | −62,920 | +26,940 | +14,792 |

For donchian, 250 ms of latency alone costs about as much as a second tick of slip (−37,195 against −37,017 all sessions).

## Tests
- Whole suite: 310 passed in 152 s. The sim's own files account for 144 of those.
- Mutation checks, run from the scratchpad: switching off the guard, the error handler, `strict_limit`, input validation or the default roll list each turns the new tests red.
- An earlier full run had 2 failures in `test_score_loader.py` and `test_score_verify.py`; `apex300.py` and `score.py` were being edited by other agents at the time. The final run is clean.

## Things to know
- **Not fixed:** the `ctx.daily` lookback difference (the tester loads 400 days before the range start; the tape and daily cache start 2021-09-22). It cannot be matched without earlier tapes.
- **House rules:** nothing written outside the pilot directory and the scratchpad, nothing committed, no 2025+ row read, `progress.md` untouched.
- **Runaway processes:** one of my scratch mutation scripts briefly spawned extra processes at about 21:38 ET, outside any compute window. I killed it and confirmed none were left.
- **Not mine:** `homebase/static/index.html` shows as modified in git at 21:42 ET.

Files are in `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2`:
- `l2sim.py`
- `l2ref.py`
- `sim_validate.py`
- `SIM_VALIDATION.md`
- `out/sim_validation.json`
- `tests/test_l2sim_lookahead.py`
- `tests/test_l2sim_contract.py`
- `tests/test_l2sim_validation.py`