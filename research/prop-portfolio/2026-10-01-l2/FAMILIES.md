
## O1 `open_dir` — `families/opendir.py` (registry: `open_dir_book`, `open_dir_flow`, `open_dir_both`)
Written 2026-10-02 00:05 ET, BEFORE the family was run on any data (pre-registration; nothing below changes after this line
is on disk). Source: SPEC "Families" O1 + "Stage A screen" O1. Tests: `tests/test_fam_open.py`.

**What it is.** At each session open, pick ONE side from the pre-open book and / or flow and rest ONE stop entry on that side.
Three screened variants = three registry names (one class each, `src` pinned by the class so that each loads only its own
columns): `open_dir_book` (`src=book`), `open_dir_flow` (`src=flow`), `open_dir_both` (`src=both`).
`open_dir_flow` is a **REVISIT of a REFUTED family**: the 9:30 delta-direction family (burned-data ledger
`NQ|1m|930_delta_direction`, refuted 2026-09-23: delta-selected side of the 9:30 straddle, 0 of 4 pre-registered cells). It is
labelled REVISIT in the registry notes and must be labelled so in every table that shows it. `open_dir_both` contains the same
flow signal as a confirmation and is labelled "contains the REVISIT signal".

**Defaults (= the SPEC's; the screen runs exactly these).** `src` book | flow | both · `off_atr` 0.25 · `stop_mode` atr ·
`stop_val` 3.0 · `tgt_r` 0.0 (no target) · `max_tr` 1 · `trail_atr` 0 · `exit_bars` 0 · `dir` both · `sess` all ·
`f_depth` / `f_trend` / `f_vwap` off. Family parameters (2): `src`, `off_atr`. Everything else below is a constant.
`SCREEN_TFS = ("30",)`: "ATR30" = the Template's Wilder ATR(14) on 30-minute bars since 00:00 ET (plain mean of the true
ranges while fewer than 15 bars exist, e.g. 6 bars at 03:00), i.e. the family is run at `tf = 30` only (run keys
`open_dir_<src>-tf30`). At any other tf the ATR would be ATR(tf): that is not the pre-registered config.

**Decision times (declared clock times, one decision per session, nothing is decided at any other moment).**
| session (R windows) | decision ("open") | unfilled entry cancelled | flat at |
|---|---|---|---|
| london 03:00–08:25 | 03:00:00 ET | 04:00:00 | 08:25 |
| nyam 09:30–11:00 | 09:30:00 ET | 10:30:00 | 11:00 |
| mid 11:00–13:30 | 11:05:00 ET (SPEC time: 5 min after the mid session starts) | 12:05:00 | 13:30 |
| pm 13:30–15:58 | 13:30:00 ET | 14:30:00 | 15:58 |

asia has no open in the SPEC: never traded. A CME half day ends at 13:15 ET (no pm decision; mid is flattened at 13:15).

**Trigger (exact).** Let T = the decision time. Rows are read ONLY through `ctx.feat_window`; at T the newest usable row is the
one stamped T − 1 min (book taken ~59 s into that minute, flow of [T − 60 s, T)).
* Freshness (all variants): the window must be exactly the consecutive minutes before T, i.e. `t_utc` of its first row
  = T − n·60 s and of its last row = T − 60 s (n = 5 book, 15 flow). A short or stale table = no signal.
* `book`: `m = mean(imb10)` over the 5 rows stamped T − 5 … T − 1 min (float64 mean of the float32 column).
  ALL 5 must be finite — any NaN (book_ok False: roll day −1 / 0 / +1, the masked evening hours of roll + 2, a crossed /
  one-sided book) = no signal, no fill-in. side = long if m > 0 (bids heavier), short if m < 0, none if m == 0.
* `flow`: `s = Σ f_delta` over the 15 rows stamped T − 15 … T − 1 min; a NaN row (a minute without a print) adds 0; at least
  8 of the 15 must be finite (the data layer's own "≥ 8 of 15" convention), else no signal.
  side = long if s > 0, short if s < 0, none if s == 0. Flow is our own tape: it does NOT depend on book_ok, so this variant
  trades roll days.
* `both`: both signals must exist and have the same sign; otherwise no trade.
* Also required at T (Template `can_enter`): flat, no working entry, 0 entries so far this session, ATR30 defined with ≥ 3
  completed 30-minute bars since 00:00, a last print exists. No signal at T = no trade in that session (no retry).

**Order (one side only).** One stop entry at `last print before T ± off_atr × ATR30` (long above, short below), snapped to the
tick; it goes live 85 ms after T (simulator law), fills at trigger + 1 tick slip (a gap costs the gap). Never a second leg,
never an OCO → `both_sides = False`. Unfilled at T + 60 min (a declared clock time, exact for all four opens) → cancelled; a
print stamped at or after T + 60 min cannot fill it. Entries are therefore possible only in [T, T + 60 min), which ends 83–265
minutes before each session end: an entry in the last 5 minutes of a session is impossible (the Template's own last-5-minute
cancel / `can_enter` guard stays on as well).

**Exits.** Protective stop 3.0 × ATR30 (the ATR at T) from the entry trigger, re-priced to the fill (same distance), 1 tick
slip. No target. No trail, no bar exit. Flat (market) at the session end. Max 1 trade per session, max 4 per day.

**Columns.** `open_dir_book`: `imb10`, `t_utc` · `open_dir_flow`: `f_delta`, `t_utc` · `open_dir_both`: `imb10`, `f_delta`,
`t_utc`. C2 shuffles `imb10` / `f_delta`; `t_utc` is a clock tag (the receiving session's own). No price anchor, no research
tier column. State: none beyond the Template's per-session state (`session_independent = True`).

**Apex 300K PA compliance.** One direction: YES (a single resting entry on one side; proven by the simulator's row stamps).
Stop ≤ 5 × target: **NO as pre-registered** — there is no target (`tgt_r` 0), so `stop_5x_target` FAILS at the Apex gate by
design; the family is screened for the Lucid / Apex-eval slots as is, and an Apex PA candidate would need a target
(`tgt_r` ≥ 0.2 by the 5:1 rule, ≥ 0.25 to leave margin for tick rounding) as a declared stage B parameter, never as a
changed default. MAE rule: scored offline (apex300), not a property of the entry. Simple enough to
trade by hand: one stop order at four fixed clock times.

## Walls: B4 `wall_bounce`, B5 `wall_break` — `families/walls.py`
Written 2026-10-02 00:05 ET, BEFORE either family was run on any data (pre-registration; nothing below changes after
the first run). Source: SPEC "Stage A screen" lines B4 / B5 + FEATURES.md "Walls". Where the SPEC left a detail open it
is decided here and marked **(decided)**.
**Amended 2026-10-02 01:00 ET — see "Walls — addendum" at the end of this section**: B4's order in the 1-tick case
(conformed to the SPEC line; the one bullet that changed is marked) + reading rules for C2, Stage E, the 1 s guard and
Apex. Before any screen run (no `runs/`, no `ledger.csv`); only smoke COUNTS had been seen, no P&L.

### Shared definitions
* **Decision** = a tf-bar close inside a session, only when `Template.can_enter` holds (flat, no working entry, fewer
  than `max_tr` entries this session, ≥ 3 tf bars since 00:00 ET, not in the last 5 minutes of the session). Features are
  read through `ctx.feat(name, back=k)` only, `k ≥ 0`.
* **Columns** (both families): `bid_px ask_px` (anchors), `bid_wall_dist bid_wall_sz bid_med_sz ask_wall_dist ask_wall_sz
  ask_med_sz` (features, shuffled by C2), `t_utc`, `book_ok` (fixed).
* **Row valid for a side** at `back=k`: `book_ok` is True and the side's anchor, `wall_dist`, `wall_sz`, `med_sz` are all
  finite and `med_sz > 0`. A roll / masked / NaN row is never valid: no signal, no forward fill.
* **Fresh / consecutive rows (decided)**: the newest usable row must be the minute that just ended
  (`t_utc(back=0) + 60 == decision time in s`) and row `back=k` must be exactly k minutes older
  (`t_utc(back=k) == t_utc(back=0) − 60k`). A gap in the table ⇒ no signal.
* **Wall on a side in a row** ⇔ the row is valid and `wall_sz ≥ m × med_sz` (the side's LARGEST level of the top-10
  near-book levels — "≤ 10 levels from best" is the column's own construction; the median includes the wall level).
  **Wall price** `W = bid_px − bid_wall_dist × tick` (bid) / `ask_px + ask_wall_dist × tick` (ask), tape coordinates.
* **Price** = `ctx.last_price` (the last print strictly before the decision), never a bar close or the anchor.
* **One order per decision (decided)**: if the bid-side and the ask-side condition both hold at the same decision, NO
  order is placed. So at most one entry order is ever working ⇒ `both_sides = False`.
* **Order life (decided)**: `ttl = 1` tf bar — an unfilled entry is cancelled at the next tf-bar close and the trigger
  is re-evaluated from scratch at that close (Template also cancels it 5 minutes before the session end).
* Common inputs = Template defaults (`dir both`, `tgt_r 2.0`, `trail_atr 0`, `exit_bars 0`, `max_tr 3`, `sess all`,
  filters off) except **`stop_mode = "struct"`** (the SPEC's stop for both families is a structure stop). ATR = Wilder
  ATR(14) on tf bars. Screen tfs `("1", "5")`. `session_independent = True` (no state of its own beyond the Template's).

### B4 `wall_bounce` (class `WallBounce`)
* Family inputs: `m = 5.0` (wall multiple; schema 1.5 … 20), `near = 2` (ticks; schema 1 … 10).
* **Trigger** at a decision, newest usable row (`back=0`) fresh, per side with `sd = +1` (bid wall → long) / `−1`
  (ask wall → short): the side shows a wall and `0 < sd × (last_price − W) ≤ near × tick` (price in front of the wall,
  within 2 ticks, the wall price not yet traded at / through).
* **Order** **(amended 01:00 ET, addendum 1; the 00:05 text placed NO order in the 1-tick case)**: a LIMIT entry at
  `W + sd × 1 tick` (1 tick in front of the wall), `ttl = 1`, in every case of the trigger. Last print 2 ticks in front →
  the limit is 1 tick on the passive side of the last print; last print 1 tick in front → the limit rests AT the last
  print's price (`WallBounce._lim` = `Template._lim` except that a limit AT the last print also rests; beyond the last
  print nothing is ever placed). It fills only on a 1-tick trade-through of the limit, i.e. on a print AT (or through)
  the wall price, at the limit price.
* **Stop**: struct = `W − sd × 4 ticks` ⇒ distance from the entry = max(5 ticks, 0.25 × ATR) (Template `_dist`, min 2
  ticks). **Target**: entry + `sd × tgt_r × stop distance` (`tgt_r 2.0`).
* Screen execution: `SCREEN_RUN = {"strict_limit": True}` (the stop is live on the fill print).
* Apex: one direction — yes (`both_sides = False`, single limit entry, never an OCO). Stop ≤ 5 × target — yes
  (stop = 0.5 × target from the fill; a limit fills at its own price).

### B5 `wall_break` (class `WallBreak`)
* Family inputs: `m = 5.0` (wall multiple; schema 1.5 … 20), `stand = 2` (consecutive snapshots; schema 2 … 10).
* **Trigger** at a decision, rows `back = 0 … stand` fresh and consecutive, per side with break direction `sd = −1` (bid
  wall broken → short) / `+1` (ask wall broken → long):
  1. *standing*: the side shows a wall in EVERY row `back = 1 … stand`, at the same wall price `W` (equal in ticks);
  2. *gone*: row `back=0` is valid for that side and does NOT show a wall at `W` (its largest level is at another price,
     or is no longer `≥ m × med_sz`). An invalid newest row is "unknown", not "gone": no signal;
  3. *traded through*: `sd × (last_price − W) > 0` (strictly beyond the wall price, ≥ 1 tick).
  At tf 5 only the three newest one-minute rows at the tf close are looked at **(decided)**: a wall that vanished
  earlier inside the bar is not a signal.
* **Order (decided)**: `Template._arm`, ONE leg — a STOP entry at `last_price + sd × 1 tick` (1 tick beyond the last
  print in the break direction; the last print is already beyond the wall, so a stop at "wall ± 1 tick" would be through
  the market and is not what `_arm` rests), `ttl = 1`.
* **Stop**: struct = `W − sd × 4 ticks` (the far side of the broken wall) ⇒ distance = max(|entry trigger − struct|,
  0.25 × ATR), kept from the fill. **Target**: `tgt_r 2.0` × that distance.
* Apex: one direction — yes (`both_sides = False`; the two sides cannot both break, and if they ever did no order is
  placed). Stop ≤ 5 × target — yes (stop = 0.5 × target; both brackets move with the fill).

### C2 null
`score.C2Features(FEATURES, seed)` shuffles the six wall columns (distance, size, median per side) and keeps `bid_px`,
`ask_px`, `t_utc`, `book_ok` as the receiving session's own: the null wall price is the donor's distance re-anchored on
the receiving session's best bid / ask.

### Tests
`tests/test_fam_walls.py` (synthetic tapes + features: trigger fires exactly when defined — the 1- and the 2-tick case of
B4 included —, an independent oracle on random days, NaN / masked / stale rows, last 5 minutes, one order at a time, the
tf-5 late close; look-ahead: tape AND rows replaced after a cut change nothing before it, and a mutant that reads one
row ahead fails that comparison), `tests/test_fam_walls_real.py` (the look-ahead verifier's test kept with the suite:
10 real in-sample days, one process, counts only — garbage after a cut, a one-minute leak in the table is caught, every
decision / order / bracket / fill re-derived from the raw tape and the raw feature cache) and `tests/test_families.py`
(the registry's 1-vs-8-worker identity for `wall_bounce-tf1|5`, `wall_break-tf1|5`).

### Walls — addendum 2026-10-02 01:00 ET (verifier findings; BEFORE any screen run, no P&L looked at)
No default, threshold or parameter changed (`m 5.0`, `near 2`, `stand 2`, 1 tick in front, 4 ticks beyond, floor 0.25 ATR,
struct stop, `tgt_r 2.0`, `max_tr 3`, tfs 1 and 5, `strict_limit` on B4). Items 2–7 are reading rules and labels, fixed
here before any screen result exists.

1. **B4 order in the 1-tick case — conformed to the SPEC line (a code change).** SPEC: "price within 2 ticks of it at
   the decision → limit entry 1 tick in front of the wall". As built at 00:05 an order rested only when the last print
   was EXACTLY 2 ticks in front: 1 tick in front, the limit equals the last print and `Template._lim` refuses a limit
   that is not strictly passive — a helper's rule dropped about half of the SPEC trigger (verifier, 10 smoke days, tf 1:
   12 of 21 triggers placed). Now both cases rest the limit (bullet "Order" above). `near = 1` is no longer a dead value.
   * Fill law unchanged: only a print at / through the wall price fills, at the limit price, no queue model, `strict_limit`.
   * 1-tick case, limit at / through the snapshot's opposite best (e.g. the wall is the best bid and the spread is one
     tick): live, that limit is marketable and fills at once at the same price. The simulator still fills it only if a
     later print inside the order's one tf bar trades at the wall price: the simulated trades are the subset of the live
     fills that went on to trade at the wall — same entry price, adverse selection kept. Pessimistic; no extra
     condition was added for it.
   * **NOT changed — open reading for the orchestrator, to settle BEFORE `screen.py run`, never after:** a last print AT
     the wall price (0 ticks) or through it is still no signal. That is the 00:05 definition ("the wall price not yet
     traded at / through") and FEATURES.md's own recipe (`0 < last − wall ≤ 2 ticks`); a limit 1 tick in front of the wall
     would then lie BEYOND the last print (marketable), which the simulator's limit law does not model. The verifier
     counted 4 such rows next to 21 triggers on the smoke days.
   * Smoke counts after the change (10 fixed days, no P&L): tf 1 17 trades (9 before), C2 null 11; tf 5 5 trades (3
     before), C2 null 0; `ok: true` (no dropped session, worker parity, no both-side session).
2. **C2 reading rule for B4 / B5.** The C2 null re-anchors the donor's wall distance on the receiving session's own bid /
   ask at every row. That destroys wall PERSISTENCE: under the null B5 almost never sees one wall price on two consecutive
   rows (verifier, smoke days, tf 1: 2 standing-and-gone events vs 30 real; 0 null trades vs 7), and
   `score.lift_vs_control` counts a control without trades as "never passes", so any real P(pass) > 0 would give
   lift > 0 vacuously. Rule, for every scored cell (family × tf × scored session(s)) of a wall family:
   * a C2 seed is INFORMATIVE only if its `ctrl_trades` ≥ 0.5 × the real run's trade count in the same session(s);
   * if any C2 seed of the cell is not informative, the cell's C2 lift is recorded as **UNINFORMATIVE = NOT PASSED**.
     Promotion needs lift > 0 against BOTH controls (SPEC), so that cell cannot be promoted whatever C1 says; the C2
     requirement is never dropped and never "passed by default";
   * the 0.5 is fixed now and is not tuned after results. B5 is expected to fail it at both tfs; B4 may at tf 5;
   * the only rescue is a persistence-preserving null, pre-registered BEFORE it is run and counted against the 400-run
     cap (orchestrator's decision; NOT built). Proposed design: translate the donor's wall-price PATH by ONE offset per
     decision — null wall price at `back=k` = receiver anchor(`back=0`) + (donor wall price(`back=k`) − donor
     anchor(`back=0`)) — so "standing at one price" and "gone" are the donor's and "traded through" is the receiver's
     last print. It needs the donor's anchors (or a per-row anchor-change column) inside `score.C2Features`, which today
     keeps the anchors as the receiver's own at every row: a `score.py` / `l2data.py` change, not a walls change.
3. **Stage E precondition (`book_ok` carries hindsight).** Both families read `book_ok`; two of its inputs look ahead:
   `ofb_mismatch` (a centred 61-minute median, about 32 minutes ahead, plus a whole-session median) and `roll_block`
   (masks the day BEFORE a roll). In-sample no wall decision is touched (verifier: all 1,159 mismatch rows outside the
   roll block are on roll + 2 evenings, 18:01–20:03 ET; 0 rows inside asia / london / nyam / mid / pm are removed by
   `ofb_mismatch` alone). Before any B4 / B5 holdout number is read, Stage E must assert the same on the holdout build
   (zero rows inside 00:00–16:00 ET masked by `ofb_mismatch` alone); if the assert fails, stop and decide first.
4. **The 1 s execution guard is mandatory for a B4 / B5 candidate.** The snapshot margin is about zero in the thin months
   (2023-11, 2024-12) and the wall families act on the newest snapshot alone, in asia and london too. Every shortlisted
   B4 / B5 cell (stage B onward) is reported with `latency_ms=1085` next to its screen line, and promotion is judged on
   the guarded line (lift > 0 against both controls must hold there as well). An edge that needs the first second is not
   deployable (FEATURES.md). The screen itself stays at the tester law.
5. **Decision time at tf 5 (clarification, nothing changed).** "A tf-bar close" is the Template's: when the last minute of
   a tf bucket has no print, the bucket is closed — and the family asked — at the end of the next minute that has one,
   off the 5-minute grid. The family reads the rows usable at THAT instant (freshness is checked against the actual
   decision time) and the last print before it, nothing later; unlike the flow families a late close is a valid wall
   decision (nothing is aggregated over the bar). Verifier: 0 of 6,559 tf-5 decisions on 10 real days were off-grid.
6. **B5 as built against the SPEC wording (nothing changed; made explicit).** (a) The stop entry rests 1 tick beyond the
   LAST PRINT, not beyond the wall, so B5 is a chase entry: on the smoke days 3 of 8 triggers had the last print ≥ 12
   ticks beyond the wall, stop distances 6–44 ticks. (b) The struct stop is `W ∓ 4 ticks` at the order; brackets move
   with the fill (the Template's rule for every stop entry), so after the 1-tick stop-entry slip the live stop sits at
   `W ∓ 3 ticks` whenever the 0.25 ATR floor does not bind. (c) Detection is one-shot on rows `back = 0 … stand`: a wall
   that vanished earlier inside a tf-5 bar, or one minute before the trade-through, is not a signal.
7. **Apex 300K PA label: NOT hand-executable as built → not an Apex 300K PA candidate.** One direction and stop ≤ 5 ×
   target hold (simulator stamps; stop = 0.5 × target). But a resting order placed 85 ms after a minute close from a
   one-second-old book snapshot, alive one bar, cannot be traded by hand, and Apex prohibits automation on PA accounts
   (SPEC, account-level rule 1). Any `apex300_pa` / `apex300_eval` number of B4 / B5 is for information only and carries
   this label; tf 5 does not change it.
8. Not run: the 1-vs-8-worker identity at 8 workers (house rule: ≤ 2 workers for a non-screen-runner; passed at 1 vs 2;
   neither class holds state of its own). The screen runner's default suite run covers it.
9. Provenance (the directory is untracked, so the 00:05 timing cannot be proven from the files): `families/walls.py`
   as amended = sha256 `6746591efd106572ef35dbd72448a636db32a1419bd7b36351156745406471a9`; the screen runner should find this hash before `screen.py run`. Suite at 01:02 ET
   (`L2_TEST_WORKERS=2`): 798 passed, 1 skipped.

## Book families B1 `bimb_follow`, B2 `bimb_fade`, B3 `thin_side` — `families/book.py`
Written 2026-10-02 00:05 ET, BEFORE the first run of any of them (smoke included). Frozen from here: a bug fix is reported as
a bug fix, nothing below is changed after a performance number exists. Tests: `tests/test_fam_book.py`.

### What the three share
| item | definition |
|---|---|
| base / common inputs | `l2sim.Template` with its defaults = the SPEC's common defaults: `stop_mode atr`, `stop_val 1.5`, `tgt_r 2.0`, `trail_atr 0`, `exit_bars 0`, `max_tr 3`, `dir both`, `sess all`, filters off. ATR = Wilder ATR(14) on tf bars since 00:00 ET. |
| screen tfs | `SCREEN_TFS = ("1", "5")`. At tf 5 the feature is still the newest ONE-minute row (the last minute of the bar); nothing is aggregated over the bar. |
| decision instants | only when the Template calls `fam_signal`: a tf-bar close that falls inside a session (first one = the first close after the session start), the strategy flat, no entry order working, fewer than `max_tr` entries in this session, at least 3 tf bars since 00:00 ET, and decision time earlier than session end − 5 minutes. (A tf bar whose last minute has no print is closed by the Template at the close of the next minute that has prints: the decision is taken then, on the row that is newest then.) |
| trigger kind | a LEVEL condition, evaluated afresh at every decision instant. No crossing / edge requirement, no cooldown: after a trade is closed the next decision instant at which the condition holds enters again (up to `max_tr` per session). |
| row used | the newest usable row at the decision = the minute that just ended. Two guards, both "no signal" when they fail: FRESH — `t_utc + 60 s` must equal the decision time (a stale row is never used); VALID — that row's `book_ok` must be True and the value(s) read finite. Roll days −1 / 0 / +1 and every other `book_ok = False` row therefore never signal. |
| access | `ctx.feat` / `ctx.feat_window` only, never a negative index; no state survives a session (`session_independent = True`), in fact no state at all: every decision is recomputed from the usable rows. |
| order | ONE market order at the decision (`Template._mkt`): filled on the first print at/after decision + 85 ms, + 1 tick slip. Stop = 1.5 × ATR from the signal bar's close, target = 2.0 × the stop distance; both are re-priced to the fill keeping their distances. Minimum stop distance 2 ticks (Template). No trailing stop, no bar exit; flat at the session end. |
| C2 null | shuffled: the book features (`imb10`, `imb3` / `bid10_rel15`, `ask10_rel15`). Fixed (the receiving session's own): `book_ok`, `t_utc`. |
| `both_sides` | **False** — never a resting entry, never two entry orders, one position at a time. |
| Apex 300K PA | one direction: YES (market entries only; proven by the simulator's `oco` / `both_sides` stamps). stop ≤ 5 × target: YES (from the fill: stop = d, target = 2 d → ratio 0.5). 30% MAE rule: a sizing question, checked by `score` / `apex300`. Manual-execution note: the signal needs a live z-score / depth-ratio read at each bar close — semi-manual at best; to be labelled so if it is ever picked. |

### B1 `bimb_follow` / B2 `bimb_fade`
* Columns: `imb10` (N = 10, default) or `imb3` (N = 3); `book_ok`, `t_utc`. `I = (ΣB − ΣA)/(ΣB + ΣA)` over the top N near-book levels (data layer).
* z-score at a decision whose newest row is stamped minute M, value `x`:
  `h` = the values of the rows stamped in the 60 minutes before M, i.e. `[M − 60 min, M − 1 min]` (the 60 rows before the newest
  one; a row outside that clock span is not counted), keeping only rows with `book_ok` True and a finite value;
  at least **30** values needed, else no signal; `z = (x − mean(h)) / std(h)` in float64, population std (ddof 0); `std(h)` must be > 0, else no signal.
  The current minute is NOT part of its own mean / std.
* Trigger: `|z| ≥ k`, `k = 2.0` (inclusive).
* Direction = the sign of z (the side that is heavier than its own trailing hour, not the sign of the raw imbalance):
  B1 follow: `z ≥ +k` → LONG, `z ≤ −k` → SHORT. B2 fade: `z ≥ +k` → SHORT, `z ≤ −k` → LONG.
* Family inputs (2): `k` = 2.0 (float, 0.5 … 6.0), `n_lv` = "10" (choice "10" | "3"). The 60-minute window and the 30-value minimum are constants, not inputs.
* Registered names (one per screened variant, families/README.md): `bimb_follow`, `bimb_fade` (class defaults, N = 10) and
  `bimb_follow_n3`, `bimb_fade_n3` (`{"n_lv": "3"}` — the SPEC's "Param 2: N ∈ {10 (default), 3}").

### B3 `thin_side`
* Columns: `bid10_rel15`, `ask10_rel15`; `book_ok`, `t_utc`. The data layer stores them as RATIO − 1 (top-10 depth of the side ÷ the
  median of its previous 15 one-minute snapshots, at least 8 valid, minus 1). The SPEC's thresholds are on the RATIO:
  `rb = 1 + bid10_rel15`, `ra = 1 + ask10_rel15`.
* Trigger: bid side thin = `rb ≤ 0.60` AND `ra ≥ 0.90`; ask side thin = `ra ≤ 0.60` AND `rb ≥ 0.90`. Both comparisons are
  inclusive with a 1e-6 tolerance on the ratio (the column is float32, a ratio of exactly 0.60 / 0.90 is attainable and counts as
  inside; same convention as `l2sim.depth_regime`). Both sides thin, or the other side below 0.90: no signal.
* Direction, "toward the thin side" = the way price moves into the side that lost its depth:
  bid side thin → SHORT; ask side thin → LONG.
* Family inputs (2): `thin` = 0.60 (float, 0.10 … 0.80), `hold` = 0.90 (float, 0.85 … 1.50).
* Registered name: `thin_side` (class defaults).

## Flow families F1 `delta_follow`, F2 `absorption`, F3 `cvd_div`, F4 `sweep_follow` — `families/flow.py`
Written 2026-10-02 00:07 ET, BEFORE any of the four was run on any data (smoke included). Pre-registration: nothing below
changes after this section is on disk; a bug fix is reported as a bug fix. Source: SPEC "Families" F1–F4 + "Stage A screen"
F1–F4 (binding) + FEATURES.md. Where the SPEC left a detail open it is decided here and marked **(decided)**.
Tests: `tests/test_fam_flow.py`. Registry names = the SPEC names, one screened config each (class defaults, `{}`).

### What the four share
| item | definition |
|---|---|
| base / common inputs | `l2sim.Template`, its defaults = the SPEC's common defaults: `stop_mode atr`, `stop_val 1.5`, `tgt_r 2.0`, `trail_atr 0`, `exit_bars 0`, `max_tr 3`, `dir both`, `sess all`, filters off. ATR = the Template's Wilder ATR(14) on tf bars since 00:00 ET (it includes the signal bar). |
| screen tfs | `SCREEN_TFS = ("1", "5")`. |
| decision instants | only when the Template calls `fam_signal`: a tf-bar close inside a session with the strategy flat, no entry order working, fewer than `max_tr` entries this session, ≥ 3 tf bars since 00:00 ET, and decision time earlier than session end − 5 minutes. |
| signal bar **(decided)** | the tf CLOCK bucket `[T − tf min, T)`, T = the decision time. A signal needs an ON-TIME close, all three: (i) T is a multiple of tf minutes (epoch = ET clock alignment, as the Template's bars); (ii) the last one-minute bar of the Template's closed tf bar ended exactly at T (the bar's last minute printed); (iii) the newest usable feature row is stamped T − 60 s (`t_utc + 60 == T` in seconds). A LATE close (the bar's last minute had no print, so the Template closes it at the next printed minute) or a stale / missing row = NO signal. At tf 1 every close is on time. |
| row guard | the newest usable row (the minute that just ended) must have `book_ok` True, else no signal: roll day −1 / 0 / +1, the masked evening hours of roll + 2 and every other `book_ok = False` row never signal **(decided: the conservative reading of "roll / NaN rows ⇒ no signal"; the flow columns themselves are valid on those rows and still enter the TRAILING statistics)**. A NaN flow value is never replaced by a forward fill. |
| tf-bar aggregation **(decided)** | a per-minute flow column is SUMMED over the one-minute rows stamped inside a tf clock bucket (bucket of a row = `(T − 1 s − t_utc) // (tf · 60 s)`, 0 = the signal bar). A NaN minute (no print) adds 0. A bucket without a single finite row is MISSING (not 0). At tf 1 a bucket is one row. |
| trailing window **(decided)** | "the trailing 60 tf bars" = the 60 clock buckets immediately BEFORE the signal bar (buckets 1 … 60; the signal bar is not part of its own percentile). Missing buckets are dropped; at least **30** valid buckets, else no signal. The window is clock-based, not session-based: it reaches back before the session start and into the same Globex evening (rows exist from 18:00 ET), never into the previous Globex session (the feature slice starts there). Percentile = `numpy.percentile(values, q)` (linear interpolation) on float64. 60 and 30 are constants, not inputs. |
| trigger kind | a condition on the bar that just closed, evaluated afresh at every decision instant; no cooldown (after a trade is closed the next qualifying bar enters again, up to `max_tr` per session). |
| access / state | `ctx.feat` / `ctx.feat_window` only, `back` / `n` ≥ 0. No state of its own: every decision is recomputed from the usable rows and the Template's bars (`session_independent = True`). |
| order | ONE market order at the decision (`Template._mkt`): first print at / after decision + 85 ms, 1 tick slip. Stop 1.5 × ATR from the signal bar's close, target 2.0 × the stop distance, both re-priced to the fill keeping their distances (minimum stop 2 ticks). No trail, no bar exit, flat at the session end. |
| C2 null | shuffled: the flow columns (`f_delta` / `f_sweep_buy_vol`, `f_sweep_sell_vol`). Fixed (the receiving session's own): `t_utc`, `book_ok`, and the Template's price bars (bar open / close / high / low, ATR). |
| `both_sides` | **False** for all four — never a resting entry, never two entry orders, one position at a time. |
| Apex 300K PA | one direction: YES (market entries only; proven by the simulator's `oco` / `both_sides` stamps). stop ≤ 5 × target: YES (from the fill: stop = d, target = 2 d → 0.5). MAE rule: sizing, scored offline. By hand: the signal needs a live percentile / cum-delta read at each bar close — semi-manual at best; to be labelled so if ever picked. |

### F1 `delta_follow` (class `DeltaFollow`)
* Columns: `f_delta` (tick-rule aggressor delta of the minute, own tape), `t_utc`, `book_ok`.
* `D` = Σ `f_delta` over the signal bar; `A = |D|`; `P` = the q-th percentile of `|D_j|` over the trailing window (j = 1 … 60).
* Trigger: the signal bar is valid, `A > 0` and `A ≥ P` (inclusive), AND the bar closes in the delta's direction:
  `C > O` when `D > 0`, `C < O` when `D < 0` (`O`, `C` = open / close of the Template's tf bar: first / last print of the
  bucket; `C == O` = no signal).
* Direction: follow — `D > 0` → LONG, `D < 0` → SHORT.
* Family input (1): `q` = 90.0 (float, 50 … 99.9).

### F2 `absorption` (class `Absorption`)
* Columns and `D`, `A`, `P` exactly as F1 (the same |delta| trigger, `q` = 90.0).
* Trigger: `A > 0`, `A ≥ P`, AND `|C − O| ≤ move_atr × ATR` (inclusive; ATR at this close).
* Direction: fade the aggressor — `D > 0` → SHORT, `D < 0` → LONG.
* Family inputs (2): `q` = 90.0 (float, 50 … 99.9), `move_atr` = 0.25 (float, 0.05 … 2.0).
* F1 and F2 are not exclusive: a top-decile bar that closes with its delta but moves ≤ 0.25 ATR triggers both (F1 follows, F2 fades).
* Ledger note: bar-level absorption at minute boundaries. ADJACENT to the refuted "NQ intraday absorption family"
  (burned-data ledger 2026-09-24: rolling-window / price-level absorption on the flow tape, OOS shot spent, refuted). Not the same
  trigger (no price level, no VWMA), but to be labelled "adjacent to a refuted program" wherever it is shown.

### F3 `cvd_div` (class `CvdDiv`)
* Columns: `f_delta`, `t_utc`, `book_ok`. `f_cum_delta` is NOT used (it runs from the 18:00 Globex open; FEATURES.md).
* Session = the Template session the decision is in (asia / london / nyam / mid / pm), start `S0`.
* Price side: `C` = the signal bar's close; `H_prev` / `L_prev` = the highest high / lowest low of the session's EARLIER tf bars
  (Template bars whose nominal close is inside the session; at least one must exist). New session high ⇔ `C > H_prev`; new
  session low ⇔ `C < L_prev` (strict) **(decided: the CLOSE must be beyond the prior session extreme, a wick is not enough)**.
* Session cum-delta **(decided)**: rows stamped in `[S0, T)`; there must be exactly one row per minute of that span (else no
  signal) and the newest row's `f_delta` must be finite. `cum_i` = running sum of `f_delta` (a NaN minute adds 0). The session
  path is `{0 at S0} ∪ {cum_i}` at one-minute resolution; `cvd` = its last value, `X_hi` = its maximum, `X_lo` = its minimum
  (running extremes over the whole session so far, the 0 start and the signal bar's own minutes included).
* Trigger: new session high AND `cvd < X_hi` (strict: cum-delta is below its session high) → SHORT (fade);
  new session low AND `cvd > X_lo` → LONG (fade).
* Warm-up **(decided)**: no signal before `S0 + warm_min` minutes, `warm_min` = 15 (R's default opening range, `orb.or_min`):
  a "session extreme" needs a session range first.
* Family input (1): `warm_min` = 15 (int, 0 … 120).

### F4 `sweep_follow` (class `SweepFollow`)
* Columns: `f_sweep_buy_vol`, `f_sweep_sell_vol` (contracts traded by aggressor orders that walked ≥ 2 price levels, by side;
  own tape), `t_utc`, `book_ok`. The Stage A line (percentile of bar sweep volume) is the binding definition; the earlier
  "≥ X contracts over ≥ 3 levels" wording of the family list is superseded by it (no threshold in contracts, FEATURES.md).
* `Vb`, `Vs` = Σ of the two columns over the signal bar (a row counts only when both are finite); **(decided)** sweep volume of a
  bar `V = Vb + Vs` (all sweep volume, both sides); `P` = the q-th percentile of `V_j` over the trailing window.
* Trigger: the signal bar is valid, `V > 0` and `V ≥ P` (inclusive).
* Direction **(decided)**: the sweep side = the side with the larger sweep volume in the bar: `Vb > Vs` → LONG, `Vs > Vb` → SHORT,
  `Vb == Vs` → no signal.
* Family input (1): `q` = 95.0 (float, 50 … 99.9).

### Tests
`tests/test_fam_flow.py` (synthetic tapes + features: each trigger fires exactly when defined, direction, percentile boundary,
never on a row that is not usable yet, NaN / `book_ok` False / stale rows, late close, last 5 minutes, one position at a time) and
`tests/test_families.py` (the registry's 1-vs-8-worker identity for `delta_follow`, `absorption`, `cvd_div`, `sweep_follow` at tf 1 and 5).

## Gates G1 / G2 / G3 on the approved picks — `gates.py` (NOT a Template family, not in the registry)
Written 2026-10-02 00:08 ET, BEFORE `gates.py` existed or was run on any trade list or feature row (smoke included). Frozen from
here: a bug fix is reported as a bug fix; no definition, default or threshold below changes after a performance number
exists. Source: SPEC "Families → Gates on approved strategies" + "Stage A screen" (gate line, B6 line) + the infra
note on B6. Where the SPEC left a detail open it is decided here and marked **(decided)**. Tests: `tests/test_fam_gates.py`.

**What a gate is.** A filter / sizer applied to an EXISTING in-sample tester trade list (1 NQ rows, every session of
the day, 2021-09-22 → 2024-12-31). A gate never creates, moves or re-prices a trade: it drops rows (G1, G2) or
repeats rows (G3 sizing). Order types, stops, targets, exits, the "no entry in the last 5 minutes" rule and the
`both_sides` property are the pick's own, untouched. The gate is run on the WHOLE list (sessions are split offline).

**The six picks (decided: the SPEC's "Baseline to beat" list = six trade lists under `trades/`).**
| pick id | trade list | tf | pick session | slot | entries | both_sides |
|---|---|---|---|---|---|---|
| `straddle-tf30_c10` | `R__hm2-straddle-tf30_c10` | 30 | nyam | Flex eval + Pro noDLL eval (override) | resting stop, OCO | True |
| `straddle-tf30_c9` | `R__hm2-straddle-tf30_c9` | 30 | nyam | Pro noDLL eval as named in the SPEC text (ties #10) | resting stop, OCO | True |
| `straddle-tf30_c32` | `R__hm2-straddle-tf30_c32` | 30 | pm | Flex funded | resting stop, OCO | True |
| `orb-tf5_c10` | `R__hm-orb-tf5_c10` | 5 | mid | Pro noDLL funded | resting stop, OCO | True |
| `donchian-tf15_c10` | `R__fp-donchian-tf15_c10` | 15 | pm | Pro DLL funded | market | False |
| `donchian-tf15_c1` | `R__fp-donchian-tf15_c1` | 15 | nyam | Apex 50K PA (and the 300K PA bar) | market | False |

**Decision instant and the row used (all gates).** One decision per trade, at its entry. Features are read ONLY through
a real `l2sim.Ctx` (`ctx.feat` / `ctx.feat_window`, the simulator's own guarded accessor) whose clock is set to
`entry_ms × 1e6 − 1 ns`: the rows visible are exactly those with `usable_at` STRICTLY before `entry_ms` (a row stamped
minute M is usable from M + 60 s). The slice is `l2sim.L2Features(cols)(trade date)` (18:01 ET the evening before →
end of the ET day; book columns already NaN where `book_ok` is False).
* **Fresh (decided)**: the newest usable row must be the minute that just ended: `0 ≤ clock − (t_utc + 60 s) < 60 s`.
  A stale / missing row = no signal.
* **No signal** (stale, NaN, roll day −1 / 0 / +1, masked evening hours, first sessions of a 20-day median, no row):
  never a fill-in, never 0. What "no signal" does is fixed per gate below **(decided)**: a veto gate (G1) does not veto,
  a permit gate (G2) does not permit, a sizing gate (G3) does not resize.
* Live equivalent: at every minute boundary while the pick's entry order works (or at the bar close that sends a market
  entry) the gate is evaluated on the row that just became usable; a vetoed order is pulled until a later minute permits it.
* `guard_ms` = 0 (default, the screen). A value > 0 moves the clock that much earlier (stage B robustness only: the 1 s
  execution guard of FEATURES.md; never a screen run).

**G1 `gate_imb_side` — skip if the book opposes the side.** Columns `imb10`, `t_utc`.
`m` = float64 mean of `imb10` over the 5 newest usable rows; ALL 5 finite and consecutive minutes
(`t_utc` newest − oldest = 240 s) and fresh, else no signal (same 5-minute mean as O1 `book`).
Opposes ⇔ `side × m < 0` (long and m < 0, short and m > 0). Opposed → the trade is SKIPPED. Not opposed, `m == 0`, or
no signal → the trade is KEPT (decided: the gate vetoes only on evidence; on masked days it is the ungated pick).

**G2 `gate_thin` — trade only in a thin book (B6).** Columns `depth10_rel20d`, `t_utc`.
`v` = the newest usable row, fresh. KEPT ⇔ `l2sim.depth_regime(v) == "thin"` (the ONE B6 definition shared with the
Template filter `f_depth`: the column is ratio − 1, thin ⇔ ratio ≤ 0.8 ⇔ column ≤ −0.2, 1e-6 inclusive). `mid`,
`thick` or no signal → SKIPPED (as `f_depth`: a missing value blocks the entry). "Thin day" = thin at the entry
(SPEC: "f_depth thin at entry"), judged per trade, not per calendar day.

**G3 `gate_size` — size ×0.5 / ×1 / ×1.5 by tercile of the side-aligned imbalance z.** Columns `imb10`, `t_utc`.
* `z` = B1's z-score at the entry: `x` = newest usable `imb10` (fresh, finite); `h` = the finite values among the 60
  rows before it that lie within the 60 clock minutes before it; ≥ 30 values and `std(h) > 0` (population std, float64),
  else no signal; `z = (x − mean(h)) / std(h)`.
* **(decided)** "|imb10 z| aligned with the side" = the signed alignment `a = side × z` (+ = the book leans WITH the
  trade more than in its own trailing hour). One ordered variable, three terciles.
* **(decided)** Terciles for a trade on session date D: the `a` values (finite only) of THIS list's own earlier trades
  in the SAME session of the day (asia / london / nyam / mid / pm by ET entry minute) whose date is one of the 250
  calendar sessions strictly before D (`score.in_sample_sessions()`; fewer at the start of the sample). At least 60
  values, else no signal. `q1`, `q2` = the 1/3 and 2/3 quantiles (numpy linear interpolation).
  `a > q2` → ×1.5 · `a < q1` → ×0.5 · otherwise (ties included) → ×1. No signal → ×1. No trade is ever skipped.
  Nothing from D itself or later enters the terciles (the list is processed date by date, one process).
* **[SCORING RECIPE WITHDRAWN 2026-10-02 01:15 ET, before any gate run: see "Gates — addendum", item 1. The half-unit rows
  stay the accounting rows; a G3 bundle is SCORED as a portfolio of its size tiers, never at half micros.]**
  **(decided) Bundle representation = HALF-UNIT ROWS.** R's loader normalises every row to 1 NQ, so a size cannot be
  carried in `qty`. A G3 bundle repeats each trade 1 / 2 / 3 times (×0.5 / ×1 / ×1.5; identical rows + `gate_mult`,
  `gate_unit`, `gate_units`). **Score a G3 bundle at HALF the pick's micros** (pick m40 → micros 20 → 20 / 40 / 60).
  Consequences the scorer must respect: (1) `walk.cap_ok` — at the approved m40 the ×1.5 tier is 60 micros and breaks
  the Lucid 40-micro cap; a compliant G3 cell needs micros ≤ cap / 3; (2) `max_day_tr` counts unit rows: only
  `max_day_tr = 0` cells are valid; (3) odd half-micros (pick m30 → 15) over-charge commission by ≤ $6 per ×1 / ×1.5
  trade (R's cost model per row); (4) C1 day-matched controls must be drawn for the de-duplicated list
  (`gate_unit == 1`), the permutation null below is the like-for-like control.

**Permutation null (the gates' C2; 2 seeds per gate, each counted as a control run).** The SAME gate function with
`features = score.C2Features(cols, seed)` (seed 1, 2): `imb10` / `depth10_rel20d` at (session, ET minute) replaced by
the value at the same ET minute of a seeded random other session (bijection over the in-sample calendar, donor ≥ 5
sessions away, NaN kept where the real row is NaN); `t_utc` stays the receiving session's own. G3's terciles are
rebuilt from the null's own `a` values. **(decided) Same number of trades:** the null's categories (G1 / G2: keep,
skip; G3: ×0.5, ×1, ×1.5) are then matched to the real gate's counts PER SESSION OF THE DAY by moving the minimum
number of seeded-random trades from over- to under-represented categories (`numpy.random.default_rng([20261001, seed,
crc32(real key)])`, trades in (entry_ms, row) order). The null ledger therefore has exactly the real gate's number of
rows in every session of the day; which trades they are carries no information about this session's book.
[Addendum item 2: the moved trades are drawn among the trades both the real gate and the null can judge.]

**Outputs / accounting.** `runs/gate_<pick>_<G>/` and `runs/gate_<pick>_<G>-perms<seed>/` (`trades.json` + `run.json`,
range 2021-09-22 → 2024-12-31, engine `gates-1`; the run.json carries the pick's approved cell, `score_micros`, counts
and the no-signal counts). One `gate` ledger row each through `screen.record_gate` (family `gate_G1|G2|G3`, tf = the
pick's, control `perm`, seed): 6 picks × 3 gates × (1 + 2) = 54 rows against the 400 cap, refused as a whole batch if
they would pass it. Idempotent by key. One process (G3 state crosses sessions), days in order; no worker pool.
[Addendum items 1, 4, 6: G3 layout = `half_units.json` + tier bundles; run.json carries `gate.cells` + `gate.counts`, there is no
`score_micros`; `python gates.py guard` = the 1 s execution-guard re-run, stage `gate_guard`, not counted.]
CLI: `python gates.py plan | status | run | smoke`. Screen tfs: none of its own (1-minute rows at the pick's entries).

**Defaults (the screen runs exactly these).** G1 window 5 rows · G2 thin = ratio ≤ 0.8 · G3 z window 60 min (≥ 30),
trailing 250 sessions, ≥ 60 values, multipliers 0.5 / 1 / 1.5 · null seeds 1, 2, donor gap 5 · `guard_ms` 0.

**Apex 300K PA compliance (inherited from the pick; a gate cannot repair it).**
| pick | one direction | stop ≤ 5 × target |
|---|---|---|
| straddle #10 / #9 / #32, orb #10 | NO as a trade list (OCO family: FAIL at the gate, gated or not) | yes (tgt_r 2.0 / 1.0 / 0.5 / 2.0) |
| donchian #10 (stop 30 pts, tgt_r 0.6) | YES (market entries only; basis `market_entries`, pass `both_sides=False`) | yes (stop = 1.67 × target) |
| donchian #1 (stop 10 pts, tgt_r 0.4) | YES (same) | yes (stop = 2.5 × target) |

G3 half-unit rows are same-side copies: they do not change the one-direction evidence. The 30% MAE rule is a sizing
question (apex300); remember the ×1.5 tier when sizing.

**Known approximations (state them next to every gate number).** (1) List gating only removes / repeats trades: live,
a skipped OCO leg leaves its sibling working and a skipped market entry frees a `max_tr` slot — trades the list does
not contain. A gate that survives the screen must be replayed through `l2sim` as a Template filter before any
promotion. (2) For resting entries the verdict is the one of the last minute boundary before the fill (≤ 60 s old).
(3) A G1-gated straddle works at most one leg whenever the book has a sign; that could make it one-direction live, but
only an `l2sim` replay can prove it (the list stays FAIL).

### Gates — addendum 2026-10-02 01:15 ET (verifier findings; BEFORE any gate run: no ledger row, no bundle, no gate P&L looked at)
Nothing changes in what a gate decides: signals, thresholds, windows, terciles, defaults, picks, null seeds and the donor rule
are as registered above. Checked: on the 10 smoke days the fixed `gates.py` gives the identical signal, verdict and gated list
for every trade of every pick as the first version. What changes is how a G3 result is SCORED, which trades the null's count
matching may move, and plumbing. The only numbers behind item 1 are the verifier's differences between an all-×1 G3 bundle and
the ungated pick (a representation test; no gate verdict was involved).

1. **G3 scoring recipe (bug, major).** "Score a G3 bundle at HALF the pick's micros" is WRONG and withdrawn, together with its
   consequences (1)–(4). R's day walk treats the 1 / 2 / 3 copies of a trade as separate overlapping trades: a `day_take` /
   `target_take` hit on copy 1 skips the other copies, `max_day_tr` counts copies, later copies are credited the earlier copies'
   final P&L. An all-×1 half-unit bundle therefore did NOT score like the ungated pick. The verdicts and the half-unit rows are
   unchanged and stay the ACCOUNTING rows (`half_units.json`; ledger `trades` / `net`). **A G3 bundle is scored as a PORTFOLIO
   OF ITS SIZE TIERS:** `runs/gate_<pick>_G3[-perms<seed>]/x0.5/`, `x1/`, `x1.5/` hold each source trade ONCE (an empty tier has
   no bundle); the scorer gets one member per tier at micros u / 2u / 3u, u = half the pick's micros (m40 → 20 / 40 / 60 ·
   m30 → 15 / 30 / 45 · the 300K bar m100 → 50 / 100 / 150). `gates.cell(pick, "G3", slot)` returns the member lists (`real`,
   `nulls`) and the keyword arguments; `gates.score_cell(pick, gate, slot, which)` and `gates.lift_cell(pick, gate, slot)` run them.
   The G3 directory has no `trades.json`: `score.py` cannot take the half-unit rows by accident.
   * Neutrality is a test on the real lists at all 8 cells (6 approved + straddle #9 + the 300K PA bar): an all-×1 G3 and a
     3-way tier split at equal micros score EXACTLY like the pick (every model, every metric, the walk statistics, the Apex
     compliance). So every cell is valid, `max_day_tr = 1` (straddle #9's only cell) included, and there is no commission
     rounding (tier micros are whole numbers).
   * Firm cap. The ×1.5 tier is over the Lucid 40-micro limit on ALL SIX Lucid cells (m40 → 60 micros at the two eval cells,
     straddle #9, Flex funded and Pro noDLL funded; m30 → 45 at Pro DLL funded); R's walk would clip it to 40 (×1.5 = ×1 at
     m40). `cell` reports `cap`, `cap_ok`, `unit_cap`; `score_cell` / `lift_cell` REFUSE an over-cap
     cell unless `over_cap=True` (reference only, labelled non-compliant). The compliant G3 cell is `unit=cell["unit_cap"]`
     (Lucid: 13 → 13 / 26 / 39 micros), as registered above ("micros ≤ cap / 3"); next to the bar (`base_kw`, the pick at its
     approved cell) `cell` gives `base_same_size_kw` (the pick at 2u micros = an all-×1 G3), the size-neutral reference.
     For an Apex PA the limit used is its HALF size (in force until the safety net): 50K 45 ≤ 50, 300K 150 ≤ 170, both inside.
   * Lift. `score.lift_vs_control` takes one source, not a member list. `gates.lift_cell`: G1 / G2 = `lift_vs_control(real,
     nulls, mode="direct")` itself; G3 = the same paired per-start difference on the tier portfolios (tested equal to
     `lift_vs_control` on single sources). The permutation null (same tier counts in every session of the day) is G3's
     like-for-like control. A C1 control for G3 needs the three tiers drawn separately (`score.daymatched` on each tier bundle,
     members at the tier's micros): not provided by `gates.py` — open for the analysis stage; until then a G3 result has no C1 lift
     and cannot be called promotable.
2. **Permutation null, count matching (bug, minor; the SPEC's "the same rule applied to another session's rows").** The trades
   moved to reach the real gate's counts were drawn among ALL trades of the surplus category, so the null could veto (G1), keep
   (G2) or resize (G3) trades the real gate cannot judge (masked book, roll day −1 / 0 / +1, no tercile yet). They are now drawn
   among the trades whose verdict has a BASIS in both the real gate and the null (G1 / G2: a signal; G3: a signal and a tercile
   population ≥ 60); a trade without basis moves only when no judged trade of that category and session is left
   (`counts.moved_without_basis`; 0 for every pick, gate and seed on the smoke days, where the first version moved 0–5). Still the
   minimum number of moves, the same seeds and RNG construction. The null is a CONTROL, never a tradable rule: it is matched to
   the real gate's full-sample counts and its donors may be later sessions (run.json `gate.control_only`).
3. **Snapshot-phase guard.** A gate builds its own `l2sim.Ctx`, so the guard of `l2sim.run` did not reach it. `gates.signals` now
   applies the same rule (`exec_guard_months`): trades of a month that FAILED the phase check (cache/phase_guard.json) are judged
   with the clock 1 s earlier, on top of `guard_ms` (`counts.exec_guard`); a holdout month without a persisted check raises
   `PhaseGuardMissing`. No effect in-sample (no month failed). `check_rows` / `signals` accept `allow_holdout=True`; the stage E
   runner (holdout calendar for G3's terciles, `C2Features(allow_holdout=True)`) is still to be written and must go through `signals`.
4. **The 1 s execution guard for gates (FEATURES.md: "an edge that needs the first second is not deployable").**
   (a) every real gate's run.json carries `counts.guard_check` = how many verdicts change with the clock 1 s earlier (a COUNT; no
   trade list, no P&L) and `counts.entry_timing` (fills 1–1000 ms after a minute boundary; market fills more than 60 s after their
   tf-bar boundary). Source lists: donchian #1 3,720 of 3,852 and #10 3,461 of 3,571 fills are under 1 s after the minute;
   straddle #10 / #9 307 of 3,273, ORB 337 of 3,272, straddle #32 98 of 3,137.
   (b) the robustness re-run exists: `python gates.py guard [--ms 1000]` → ledger stage `gate_guard`, keys
   `gate_<pick>_<G>-guard1000[-perms<seed>]`, the same picks / gates / seeds with the clock 1 s earlier. As `screen.py stress` it
   is NOT counted in the cap (no new config) and it is refused for a gate that has no `gate` row. A gate candidate is reported
   with its guard line next to its screen line; for the donchian picks the guard line is the deployable one.
5. **Cells.** `gates.slots(pick)` = the approved cells (`score.BASELINE` / `BASELINE_ALT`), then `apex300_pa` for donchian #1:
   the Apex 300K PA bar (m100, take 3000, lock 3000, Tmax, start `fresh`; checked against out/baseline_insample.json).
   `cell(pick, gate)` without a slot = the pick's approved cell.
6. **Bundles / ledger.** A bundle is built in a temporary directory, its ledger row is appended, then the bundle is moved in
   place: a refused row (cap) leaves nothing on disk, and a recorded key whose bundle is missing is rebuilt without a new row.
   run.json: `gate.cells` (the `cell` dicts per slot), `gate.counts`, `tiers` (G3). `score_micros` / `score_micros_factor` do not exist.
7. **Known approximations, continued.**
   (4) The gate clock is the FILL. A market entry that fills more than 60 s after its bar close is judged on a row that became
   usable after the order was sent (assuming the order goes out at the tf-bar close): 2 trades in each donchian list
   (2021-11-23, 2022-09-21; `entry_timing.market_over_60s_after_bar`). Every other market fill reads the decision's own row.
   (5) Whether a gate has a signal depends on `book_ok`, a HINDSIGHT data-quality mask of the data layer (session medians, a
   centred 61-minute contract-mismatch flag, the session's last tape minute; DATA.md). It is a mask, not a signal, but live it
   has to be rebuilt from a roll and holiday calendar, and roll-adjacent sessions are where the two can differ. `counts.no_signal`
   / `counts.basis` say how many trades it decides (no signal: G1 keeps, G2 skips, G3 ×1).
   (6) Straddle #10 and #9 have the same entries (3,273 rows, equal `entry_ms` and side; only the target differs), so their
   G1 / G2 / G3 verdicts are identical: 9 of the 54 runs repeat the other pick's selection on another exit. The SPEC names six
   picks, so both run; read them as ONE test of the entry rule.
Tests: `tests/test_fam_gates.py` (52; +18: tercile boundary and ties, null wiring through `run_all` / `_features`, verdict basis,
phase guard, G3 tiers, neutrality on the real lists, `lift_cell`, ledger-before-bundle, the guard stage, garbage-after-cut and a
one-minute look-ahead power test on the REAL feature table and the REAL C2 loader). 73 hand-made mutants of `gates.py`: all killed.

### Flow families — addendum 2026-10-02 00:19 ET (bug fix, before any screen run; no P&L had been looked at)
Found while testing, after the 10-day smoke (which prints counts only): on a CME equity half day the engine ends the day at
13:15 ET, but the Template's last-5-minutes rule only knows the mid session's own end (13:30), so an entry was possible between
13:10 and 13:15. The four flow families now apply "decision time earlier than session end − 5 minutes" to the clamped end as
well: **no signal at T ≥ 13:10 ET on a half day** (`_Flow.fam_day`; on a full day the cut is 16:05 ET, after every session).
Nothing else changed: no default, no threshold, no trigger definition. Test: `test_no_signal_in_the_last_five_minutes_of_a_half_day`.
Execution note (not a definition): the families read the `book_ok` flag, so `l2sim.needs_exec_guard` treats them as book readers —
in a month that fails the snapshot-phase check (none in-sample) their orders get the 1 s execution guard.
