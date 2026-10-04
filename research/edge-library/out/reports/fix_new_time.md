**new_time fix round: both majors are fixed and the cheap minors are documented and tested; no trade of any cell changes, and no menu was run (ledger 0 of 40,000 cells, no `runs/` store).**

## Files (all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/timed.py` — labels, docstring, two helpers (`resolved`, `entry_life_min`); the simulation code is untouched.
- `engine/tests/test_new_time.py` — 45 tests (was 31).
- `progress.md` — one entry appended (13:15 ET).

## Majors fixed
1. **SECOND LOOK label** on `straddle_t_0300`, `_0930` and `_1330`, in the notes and in the rationale.
   - With an ATR offset these are the old pilot's straddle-tf30 in london / nyam / pm. A new test pins it on the 10 smoke days, NQ and ES: trade for trade the ported `straddle` trades entered within 60 minutes.
   - The old 2025-26 holdout jobs ran `sess=all` on NQ and ES, so london was in the same bundles; I read job keys and inputs only, no results. GC was never run there, but the label sits on the whole entry.
   - The same three entries are marked DUPLICATE of the ported `straddle` tf 30 for the three ATR offsets: at most one of the two may become a member.
2. **`straddle_t_1105` is now WEAK** (t ≥ 3 on BUILD), like 00:00. EDGE_SPEC names no event for it; it is the old pilots' mid-session arm time. This was set before any number existed. Lifting it needs an event written into EDGE_SPEC before the menus run.

## Minors documented and tested
- **55-minute entries:** at 02:00 and 08:30 unfilled entries rest 55 minutes, not 60, because the Template cancels entries 5 minutes before the flat time. I kept the engine behaviour rather than override it, so the family stays trade-for-trade the engine straddle. A test now covers the boundary at all nine times.
- **Coverage rule:** a day with an empty clock hour loses all its day fires; the evening fires still run. Tested on GC 2023-11-24.
- **18:00 fire:** stale anchor and ATR, in effect "follow the reopen gap"; the stress test is the real gate. This is in the notes.
- **Time-shuffle null:** shifts are one-sided at 18:00 / 00:00 (0..+90) and 20:00 / 13:30 (−90..0). Tested.
- **Stored offsets:** `timed.resolved(root, inputs)` writes out the offset a stored run really used. Tested.
- **`vwap_ema_x`:** the card caveats (duplicate anchors outside mid / pm, session anchor restarting at 11:00 / 13:30, no EMA warm-up, thin slow-n cells) are in its notes.

## Test results
- `tests/test_new_time.py`: 45 passed at 2 workers.
- Full engine suite: exit 0 at 2 workers, 1,271 passed, 2 skipped by design.
- `python -m families`: 46 families, 32 edge-library, 0 errors.
- Counts-only smokes (10 BUILD days, 1 worker): all 32 `ok: true` — 27 straddle units on NQ / ES / GC, and `vwap_ema_x` on NQ tf 1 / 5 / 15, ES tf 5, GC tf 5.
- `run_menus.py plan`: unchanged, 279 units = 37,824 cells.

## Open for the orchestrator, before RUN
1. **20:00 in US winter.** The fire is one hour after the Tokyo open on 37 % of BUILD calendar days. I kept it as EDGE_SPEC lists it, at full strength, with the caveat in the notes. Marking it weak is one line in `WEAK_TIMES`; moving it to 19:00 in winter changes the definition. Either must happen now, not after results.
2. **Cards do not print notes.** `library.card` prints rationale, weak and penalty only. The SECOND-look labels of port1 / port2 / port3 therefore reach `run.json` but not `card.md`; my three entries also carry the label in the rationale. This needs a fix in `library.py`, which is not my file.
3. **`ENGINE.md` is stale on weak entries.** Its table still lists "straddle_t 00:00, vwap_ema_x"; 11:05 is now weak too.
4. **Cell cap.** All families plus the C1 pools come to 38,592 of 40,000 before any stage-D unit.
5. **Worker identity at 8 was not run.** I am limited to 2 workers; the RUN agent should confirm 1-vs-N identity at its real worker count on a short slice.

Nothing was written outside the edge-library directory, nothing committed, no tester jobs, EXAM not read.