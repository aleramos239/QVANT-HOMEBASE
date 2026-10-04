# PORT2_NOTES — ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2, first_bar_mom, tod_drift, mid_fade (families/port2.py)

For the orchestrator, the Run agent and the Admit / exam stages. Written 2026-10-02, BEFORE any menu run (ledger empty, no
`runs/` store). Nothing here is a result: structure, counts and clock times only. No P&L was read to write it.

## Decisions the orchestrator owes BEFORE the BUILD run (they cannot be taken after a number exists)

1. **tod_drift cannot pass the plateau as EDGE_SPEC is written — decide how it is judged, or drop it.**
   EDGE_SPEC "PROPER RE-RUN" 4 makes `off_min × dir` its variants (8) and judges the plateau "over ALL (parameter × exit)
   cells of a unit": 256 cells per unit-session, half of them long, half short, entering on the SAME prints (tested). Under
   the family's own hypothesis (a drift in one direction) the other direction's 128 cells lose, so about 50 % of the cells
   can be > 0 at best, against the 60 % bar. A literal pass needs BOTH directions to make money at the same clock time,
   which is a volatility effect of tight stops, not the stated drift. Cells that cannot trade lower the ceiling further
   (table below). The registry follows EDGE_SPEC literally; nothing was changed. Options, all prepared, none switched on:
   * **A — literal (the default if nothing is decided):** `library.plateau(session_table)` over all 256 cells. Expect a fail by
     construction. Cost: 12 units × 256 = 3,072 cells of the 40,000 (NQ alone 1,024; ES / GC are cut by EDGE_SPEC's own
     rule once NQ fails, if the cap binds).
   * **B — per direction (pre-declared alternative):** `port2.plateau_sets("tod_drift", session_table)` →
     `{"long": 128 rows, "short": 128 rows}`, each judged by `library.plateau` on its own. Two looks per unit-session instead
     of one: say so next to the result. Optionally `port2.tradable(...)` first, to judge only the cells that can trade.
   * **C — drop tod_drift** (it is the old pilot's "control for pure clock effects") and save the 3,072 cells.
   The same trap, already reported by port group 1: `ib` (fade / break) and `gap` (fill / go). One rule for all three is best.

2. **tod_drift is now registered `weak: True`** (WEAK RATIONALE → admission needs t ≥ 3 on BUILD). Reason: its rationale names
   no counterparty, no flow and no reason to persist — `R/families/tod_drift.py`: "control for pure clock effects";
   `R/SPEC.md` 17: "Tests pure time-of-day drift". EDGE_SPEC user rule 2 rejects an effect without a reason and marks the
   analogous `straddle_t` 00:00 ("NO event behind it") WEAK. This only makes admission stricter. To waive it: delete the
   one line `"weak": True,` in `families/port2.py` before the run (the gate stays valid: its code hash does not change)
   and the matching pin in `tests/test_port2.py` (`lib["weak"] is (name == "tod_drift")`).

3. **Penalty for the other second-look families — sealed to me.** EDGE_SPEC C gives a penalty to families "whose in-sample
   favourites FAILED on 2025-26" and names donchian pm and first_bar_mom nyam. The old job lists also hold holdout jobs
   for ema_pullback, rsi2, tod_drift and (ES) tema_slope. Whether those favourites failed is in bundles I may not open.
   Only `first_bar_mom` carries the penalty. If any of the others failed, add `"penalty": "<text>"` to its entry before the run.

4. **Rationales of ema_ribbon, tema_slope, ema_pullback, supertrend restate the trigger** (no counterparty named). They are
   the hypothesis sentences of the old docstrings (written 2026-09-29 21:07 ET, before the old screen's first job at 21:38 ET),
   as EDGE_SPEC C asks ("Rationale per family as in R/SPEC.md"), and of the same kind as EDGE_SPEC's own examples
   ("donchian = trend continuation"). Left `weak` unset. Accept, or add `"weak": True` before the run.

5. **tod_drift is run as the tester draft ran it, not as a time-fired family of EDGE_SPEC A.** Every screen tf (1 / 5 / 15 / 30);
   its ATR stop is the Wilder ATR(14) of its own tf bars -- the bar-family rule ("Wilder ATR14 on the family's tf"), which is
   EDGE_SPEC's ATR30 only at tf 30; no `shift_seed` input, so `run_menus` gives it the C1 random-entry control (day- and
   session-matched) instead of the time-shuffle null. This is the verbatim port and is what the tester-match gate proves.
   Know also that its four tfs share the SAME entry prints (session start + off_min):
   the tf only changes the ATR stop size, the warm-up and the 6-bar hold (6 / 30 / 90 / 180 minutes), so its four tf units
   are four strongly correlated looks, not four independent ones. Confirm, or drop the family (decision 1 C).

6. **For the engine owner:** (a) `library.card` / `spec.json` have no field for the SECOND-look label: the Admit stage must put
   `port2.second_look(family)` on the card and in the exam report (same for `port1` / `port3` / `timed`). (b) I did not
   touch `tests/test_families.py`; the previous author's stricter `test_registry_loads_without_errors` is still in place
   and still wants the engine owner's confirmation.

## What is registered
| family | variants (first axis of its R heat-map) | cells per unit | complexity | flags |
|---|---|---|---|---|
| ema_ribbon | defaults only (first axis `max_tr`) | 32 | 4 | |
| tema_slope | `n` 10 / 20 / 40 | 96 | 2 | SECOND LOOK (ES tf 5) |
| ema_pullback | defaults only (first axis `max_tr`) | 32 | 4 | SECOND LOOK (NQ tf 1 / 5; ES tf 5) |
| supertrend | defaults only (first axis `max_tr`) | 32 | 3 | |
| rsi2 | `th` 5 / 10 / 15 | 96 | 3 | SECOND LOOK (NQ tf 1 / 5; ES tf 5) |
| first_bar_mom | `k` 1.0 / 1.5 / 2.0 | 96 | 3 | PENALTY (EDGE_SPEC C); SECOND LOOK (NQ tf 15; ES tf 30) |
| tod_drift | `off_min` 0 / 15 / 30 / 60 × `dir` long / short | 256 | 5 | **WEAK**; SECOND LOOK (NQ tf 5 / 15 / 30; ES tf 5 / 15); mirror axis `dir` |
| mid_fade | defaults only (no heat-map exists) | 32 | 3 | mid only |

Every family: tf 1 / 5 / 15 / 30 × NQ, ES, GC = 12 units; 96 units, 8,064 cells for the group (`run_menus.py plan`), no null
cells of its own (C1 pools are shared per root × tf). Market entries only, no Level-2 feature. Class bodies =
`R/families/<fam>.py` verbatim (tested by syntax tree).

Complexity = trigger rules + every number the family itself fixes or exposes. Not counted, for every family alike: what the
Template gives all families (tf, session, the menu, its ATR(14) of the tf bars, its daily ATR(14), its session clock).

## Cells that cannot trade, by construction (`port2.can_trade(family, variant, tf, session)`; tested against counts)
The plateau counts a cell without a trade as "not > 0". These follow from the families' own rules (unchanged from R):
indicators restart at 00:00 ET (18:00 for `eve`), an entry needs WARM tf bars since the restart and lies before the last
5 minutes of its session.

| family | never a trade (every variant) |
|---|---|
| first_bar_mom | `eve` and `asia`, every tf (the session's first bar is the first bar since the restart: no ATR before it) |
| mid_fade | every session but `mid` |
| ema_pullback (WARM 20) | tf 15 `asia`; tf 30 `eve`, `asia`, `london`, `pre` (first possible entry 10:00 ET) |
| ema_ribbon, supertrend (WARM 10), tema_slope (WARM 8) | tf 30 `asia` |
| rsi2 | none |

tod_drift, `off_min` values that can trade (both directions alike) → share of the 256 cells that can trade at all:

| session | tf 1 | tf 5 | tf 15 | tf 30 |
|---|---|---|---|---|
| eve, asia | 15 / 30 / 60 → 75 % | 15 / 30 / 60 → 75 % | 60 only → 25 % | none → 0 % |
| pre | 0 / 15 / 30 → 75 % | 75 % | 75 % | 75 % |
| london, nyam, mid, pm | all four → 100 % | 100 % | 100 % | 100 % |

Under option A the mirror halves each of these shares. Under option B (per direction, all 128 cells of a direction) the
ceilings are the shares above: tf 15 `eve` / `asia` (25 %) and tf 30 `eve` / `asia` (0 %) still cannot reach 60 %.

## Semantics inherited from the old code (know them when reading a table)
* **tod_drift keeps `exit_bars` 6**: its menu cells with target "none" end after 6 tf bars (or the stop / session end), not at
  the session end. The hold time therefore scales with the tf (6 min … 3 h).
* **supertrend** starts every restart (00:00; 18:00 in `eve`) with direction up: the first signal after a restart is a short.
* **`struct` stops are not in the menu**: ema_pullback, supertrend and first_bar_mom pass a structure level, but the menu's
  stop modes (atr / pts / pct) never use it.
* **mid_fade** is sparse: at most one trade a day (289 per tf on NQ, 238 on ES over 2021-09 → 2024-12; counts from the gate).
  The ≥ 100-trade rule (BUILD + PICK) is close.
* `pre` starts 08:25, not a tf 15 / 30 boundary: the "first bar of pre" (first_bar_mom) is the clock bar that closes first
  inside the session (08:15–08:30 / 08:00–08:30), mostly pre-session data.

## Execution-realism flags for admission
* **first_bar_mom in `pre` at tf 5 / 15 / 30 enters by market order at 08:30:00.085 ET — on the US data release** — filled at the
  next print + 1 tick (tf 1 enters at 08:26). No look-ahead, but the base fill is kind on data days: for any `pre` member of
  any bar-close family that signals at the 08:30 close, the 2 ticks + 250 ms stress result is the decisive number.
* `eve` / `asia`: overnight spreads are wider than the 1-tick slip (ENGINE.md 11.2): the stress test is the gate there too.
* **GC**: no GC tester bundle exists for any family (ENGINE.md 11.1). Flag every GC member. The independent oracle below
  covers GC, but it is not the tester.
* `rsi2` and `tema_slope` at tf 1 trade thousands of times a year at 1 contract: costs dominate; nothing to decide, just expect it.

## Proof
* `PORT2_VALIDATION.md` (`python port2_validate.py --fresh`): every in-sample tester bundle of the eight families, NQ and ES
  (64 screen runs + 712 heat-map cells), trade for trade. Every row carries the same file hashes (read before each pass,
  checked after it; a change aborts the gate). The report also lists, per registered variant, the tester runs / cells that
  matched it.
* `tests/test_port2.py`:
  * registry = pre-registration (variants = first heat-map axis, tfs = old screen, inputs = tester drafts, complexity pinned,
    WEAK flag, SECOND_LOOK = the old holdout job keys);
  * class bodies = R syntax tree; the code hash ignores metadata and catches a one-token trigger change;
  * tester match on 10 BUILD days (NQ, ES) and every NQ heat-map cell on 5 days; the gate report belongs to the code on disk;
  * **independent oracle** (plain Python / numpy straight from the prints, no Template) of every family's first signal in
    all seven sessions on NQ, ES and GC, 10 BUILD days each: side, entry print, fill, stop and target for atr, pts and pct
    stops — the paths no tester bundle covers. Two deliberately broken families and a deliberately wrong oracle are caught;
  * `can_trade` against trade counts; tod_drift long / short twins enter on the same prints; the plateau split;
  * no look-ahead (garbage after a cut) for all eight + a peeking family that is caught; 1-vs-W-worker identity; smokes.
* `out/port2_smoke.jsonl`: counts-only smokes on 10 BUILD days (NQ tf 1 / 5 / 15 / 30, ES tf 5, GC tf 5).
