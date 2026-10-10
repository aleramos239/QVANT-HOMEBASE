# ENGINE.md — what a family author (and the Run / Admit agents) needs from the edge-library engine

`W = ~/ramos-quant-homebase/research/edge-library/` · engine `W/engine/` · python `"~/ONYX TRADING/.venv/bin/python"`.
Contract of the project: `W/EDGE_SPEC.md`. Proof that the engine equals the tester: `W/engine/EDGE_VALIDATION.md`
(NQ 7 picks + 88 heat-map cells, ES 3 runs + 104 cells, the random control, the clock path: all 100 % identical).
The fill law, the event model and its open risks: `prop-portfolio/2026-10-01-l2/SIM_VALIDATION.md` (unchanged here).
Level-2 feature columns: `prop-portfolio/2026-10-01-l2/FEATURES.md`.

| file | what |
|---|---|
| `engine/l2sim.py` | the offline tick sim (port of the tester's engine), `Template`, periods, roots, the Globex clock, the menu |
| `engine/l2ref.py` | reference families: `Straddle`, `Orb`, `Donchian` (tester-matched), `Random` (C1 control), `StraddleT` (family A, clock path + its time-shuffle null) |
| `engine/families/` | the registry: ONE module per family group, written by its author |
| `engine/score.py` | the old pilot's scoring, NQ only (eval / funded, intraday breach model, C2 feature shuffle); knows `eve` / `pre` and the period calendars |
| `library.py` | ledger with the HARD caps, unit stores, `plateau`, `best_of_nulls`, `c1_draws`, `admission`, member folders, `run_member` |
| `run_menus.py` | BUILD menus: one tape pass per unit over every menu cell + its nulls; `smoke` |
| `engine/edge_validate.py` | the tester-match gates (re-run after ANY engine change) |
| `engine/families/fvg.py` | the `fvg` entry trigger (fair value gap: touch / mid / go entry, min_gap x ATR), 2026-10-06 |
| `engine/flowtab.py` | per-minute tick order flow (volume, delta, sweeps, biggest order) for the DELTA filter blocks, NQ / ES / GC |
| `engine/levels.py`, `engine/families/liq.py` | the liquidity levels and the `liq` trigger (sweep / break), the `level` and `swept` filters, 2026-10-06 |
| `engine/families/noise.py` | the `noise_band` entry trigger (a close beyond open +/- k x daily ATR(14) and the anchored VWAP; anchor rth or globex), 2026-10-08. It joins `blocks.WRAPPED` itself (`join_blocks()`), so `families/blocks.py` and every earlier store's code hash stay as they were |
| `engine/families/ifvg.py` | the `ifvg` entry trigger (inversion fair value gap: fvg's gap, open for `age` bars; a bar that closes through the whole gap against it -> market against the gap; min_gap x ATR), 2026-10-09. Joins `blocks.WRAPPED` itself, as noise.py |
| `engine/families/sfp.py` | the `sfp` entry trigger (swing failure: a swing high / low of the day's own 15 / 30 / 60-minute bars, known one swing bar late; a bar that trades beyond it and closes back -> market against it), 2026-10-09. Joins `blocks.WRAPPED` itself, as noise.py |
| `engine/tests/test_blocks_batch1.py` | the price-and-trend filter blocks (ema, vwma, avwap, channel, adx, rvol, rsi) against independent calculations |
| `engine/bpfeat.py` | the Level-2 feature table of the blueprint build range (2025 first half) and its loader with the build seal |

## 0a. ORCHESTRATOR DECISIONS 2026-10-03 in the engine (applied P&L-blind by the engine owner; read this first)
EDGE_SPEC's last section binds every stage. What it changed here (tests: `tests/test_edge_hold.py`, `tests/test_edge_decisions.py`):

1. **Exit convention "flat by 4pm" = Template input `hold_to = "day"`** (the name is `hold_to` because vwap_flip owns an input
   `hold`). A trade runs to its stop / target / close-based exit or is flattened at **15:58 ET of its trade date** (**13:13**
   on an equity half day: `l2sim.day_flat(d, root)`; GC keeps 15:58), never at the session end. Entries are unchanged: inside
   the session window only, never in its last 5 minutes (nor in the last 5 minutes before the day's flatten time), resting
   entries cancelled at session end − 5 min, one position at a time — no second entry while a trade of the instance is open.
   * `hold_to = "session"` stays the **class default** = the tester's rule; every tester-match gate runs with it and is
     unchanged (`edge_validate.py` re-run: ALL GATES PASS).
   * `hold_to = "day"` takes **ONE session per instance** (`sess = "all"` raises). `run_menus.cell_specs` therefore runs a
     Template cell as **seven independent instances** (`DAY_PASSES` = asia, london, pre, nyam, mid, pm, eve; a session the
     family never trades is left out), a time-fired family as one. Proven on the 10 smoke days for all 32 families (NQ tf 1 /
     5 / 30, ES tf 5 / 15, GC tf 30; `out/engine_owner/check_hold.py` → `out/engine_owner/check_*.log`, counts only): (A) under
     the OLD rule the five single-session instances together equal the `sess="all"` instance trade for trade; (B) under the
     new rule EVERY entry (date, side, time, price) is an entry of the old rule and vice versa, and a trade the old rule
     closed by its stop / target / bar exit is identical in every field. So a `hold_to="day"` run is the tester-matched
     trade list with ONE change: the exits the old rule forced by the clock at a session end are held to the stop / target /
     15:58. Stated exceptions, all from the rule itself: on an equity half day the old rule still entered in the 5 minutes
     before 13:13 and could hit a stop / target between 13:13 and the 13:15 close (now a 13:13 flatten); an evening entry
     of a trade date whose DAY has an empty clock hour is not taken (the held evening skips that date).
   * **Evening entries** (sess `eve`, straddle_t 18:00 / 20:00) run as ONE segment from 18:00 of the evening before to the
     day's flatten time (`eve_window = ("18:00", "16:10")`, `l2sim.eve_runs_on`): indicators restart at 18:00 only, the trade
     may span 00:00, never 17:00. Such a trade date needs its evening AND its day window without an empty clock hour, else
     the evening instance skips it (listed in `eve_skipped`).
   * straddle_t: the entry window is still `[at, clock_flat(at))`, unfilled legs still cancel after 60 min (55 at 02:00 /
     08:30, as before); only the flatten moved to 15:58. The time-shuffle null draws the same minutes as before.
   * `l2sim.EARLY_STOP`: once an instance's session is over and it is flat with nothing working, the day's replay stops
     (identical trades with it off: tested). `run_menus.py smoke` now also counts `exit_after_day_flat`,
     `overlap_in_session`, `entry_in_no_session` (all must be 0).
   * `library.run_member` / `l2ideas.run_member` run the member's ONE session with `hold_to = "day"`.
   * The 77 BUILD + 13 null stores of 2026-10-02 (old convention, never analysed) are VOID: `runs_void/` (+ the old ledger
     and logs). `ledger.csv` was reset.
2. **Judged units** (`library.plateau_units` / `judge`): a MIRROR family — tod_drift `dir`, ib `mode`, gap `mode`
   (`families.MIRROR`) — is one plateau unit per value of its axis; the store stays one per family × root × tf.
   `library.plateau` judges the JUDGED cells: structurally DEAD cells are left out (`session_table` marks a variant that has
   no trade in the session in ANY of its 32 exit cells: an entry count, never P&L) and cells with IDENTICAL trade lists
   (`trade_sig`) count once.
3. **Central cell** = the positive judged cell whose net is closest to the unit's median; ties → lowest (variant, exit) index.
4. **Flags** are laid over the registry in ONE place, `families/__init__.py` (`WEAK_FAMILIES`, `MIRROR`, `PENALTY_SESS`,
   `CARD_NOTES`; no author module was edited): WEAK = straddle_t 00:00 + 11:05, tod_drift, vwap_ema_x, ema_ribbon, tema_slope,
   ema_pullback, supertrend (+ the L2 author's own bimb_follow_d1, flow_exhaust). PENALTY = first_bar_mom (every session)
   and donchian in **pm only** (`families.penalty_for(name, sess)`). `LIBRARY[name]` now also has `mirror`, `penalty_sess`,
   `second_look`, `notes`. `library.member_meta(family, sess, variant)` hands the Admit stage every card field.
5. 20:00 ET stays 20:00 ET all year: on the card through the notes of `straddle_t_2000`.
6. **Null / control cells are not capped**: ledger kind `null`, column `null_cells`, `library.ledger_nulls()`. The 40,000 cap
   counts candidate grids only (`run_menus.py plan` prints both: 28,608 candidate cells, 9,984 null cells).
7. **Reporting** (`library.metrics`, `per_year`, `sized`, `report_md`, `shares_md`, `unit_report_md` = `python library.py
   report <key> --sess pm`, `card`; results: the Admit stage only): trades, net, win rate, PF, max
   drawdown, Sharpe (daily, annualised), avg trade, worst open loss — per year (2021*, 2022, 2023; 2024 for PICK), then
   combined; the plateau's share of cells > 0 overall / by stop type (fixed, ATR, percent) / per reward ratio with the verdict
   at 60 / 70 / 80 %; the same trades sized to about $1,000 of risk per trade in micros.

Where a paragraph below still says "flat at the session end", "three instances" or "null cells count", this section wins.

## 0. Rules that bind you
* Work on **BUILD only** (2021-09-22 → 2023-12-31). `l2sim.BUILD / PICK / EXAM_START` are the one definition.
  `l2sim.run(..., period="build")`. **EXAM (≥ 2025-01-01) is sealed**: `load_tape`, `sessions`, `run`, `build_tapes`,
  `L2Features`, `score.*` raise `HoldoutSealed` / `HoldoutError` unless `allow_exam=True` (the orchestrator's exam stage only).
  **PICK (2024)** is read only by the Admit stage: `library.run_member(..., "pick")` raises `PickSealed` unless it is handed
  the candidate's BUILD plateau with `pass: True`. A ported family's tester-match gate may replay the old in-sample bundles
  (to 2024-12-31) for **trade identity only**.
* The menu, the times, the variants and the rationales are **pre-registered** in EDGE_SPEC. Nothing is added or changed
  after a performance number has been seen. Smoke tests print **trade counts only**.
* ≤ 8 worker processes for this project machine-wide (`EDGE_MAX_WORKERS=<n>` lowers the cap of a process); no heavy job
  09:18–09:36 ET on weekdays (l2sim waits by itself). Authors: ≤ 10 days, 1–2 workers.
* A script that calls `l2sim.run` with workers > 1 **must** have `if __name__ == "__main__":` (spawned workers re-import it).
* Never edit `l2sim.py`, `l2ref.py`, `score.py`, `library.py`, `run_menus.py`, `families/__init__.py` or another author's module.

## 1. The registry contract (`engine/families/<your_module>.py`)
```python
FAMILIES = {      # name -> (StrategyClass, default_inputs, both_sides, notes, LIBRARY dict)
    "donchian": (Donchian, {}, False, "C: close beyond the prior n-bar channel -> market with it; struct stop = other side",
                 {"rationale": "Trend continuation: a close beyond the recent range traps the other side, whose stops feed the move.",
                  "complexity": 3,                                   # rules + free parameters of the family (an int >= 1)
                  "variants": [{"n": 10}, {"n": 20}, {"n": 40}, {"n": 60}],     # EDGE_SPEC "PROPER RE-RUN" 4: the FIRST axis of
                  "ported": "donchian",                              #   the family's heat-map in R/tune1.jsonl / tune2.jsonl
                  # "roots": ("NQ", "ES", "GC"),  "weak": True,  "penalty": "in-sample favourite (pm) FAILED on 2025-26"
                  }),
}
```
| field | rule |
|---|---|
| name | lower-case letters, digits, `_`. Becomes the unit key `<name>-<ROOT>-tf<tf>`. |
| StrategyClass | subclass of `l2sim.Template`, **defined in your module** (workers import it by name). Class attributes: `SCREEN_TFS` (the tfs the family supports, e.g. `("1", "5", "15", "30")`), `FEATURES` (every column read through `ctx.feat`; **`()` for a family without Level-2 features**), `DEFAULTS` + `SCHEMA` (every family input declared). |
| default_inputs | overrides of the class `DEFAULTS` (`{}` = the defaults). Never `tf`, never a `sess` other than `all`, never `f_depth` / `f_book` / `x_book` / `f_thin` (stage D only). |
| both_sides | `True` if entry orders of opposite sides can be working at once (`_arm` with two legs = OCO). The simulator stamps the evidence on every row; a wrong declaration fails the smoke. |
| notes | the EDGE_SPEC id + one line (trigger). |
| **`rationale`** | **mandatory**: ONE sentence written before any test — who is on the other side / what flow it rides / why it persists. |
| **`complexity`** | **mandatory**: int ≥ 1 = rules + free parameters. Ties go to the simpler member. |
| `variants` | list of input-override dicts = the family-parameter variants (default `[{}]` = defaults only; families whose first axis is `max_tr` or that have no grid: defaults only). A variant may not set `tf`, `sess`, the exit inputs (`stop_mode`, `stop_val`, `tgt_r`: the menu owns them) or an L2 option. 2-D variants (tod_drift `off_min` × `dir`) are just more dicts. |
| `roots` | default `("NQ", "ES", "GC")` for `FEATURES = ()`, `("NQ",)` with features (Level 2 is NQ only: anything else is refused). |
| `weak` | `True` = WEAK RATIONALE / WEAK PRIOR: admission then needs t ≥ 3 on BUILD. The orchestrator's list (§ 0a 4) is laid over the entries by `families.load()`. |
| `ported` | the R family it ports: it then needs a **tester-match gate** (§ 8). |
| `penalty` | text for a family whose favourite failed on 2025-26: admission then also needs the PICK plateau. Applies to first_bar_mom in every session and to donchian in pm only (`families.penalty_for(name, sess)`). |

`python -m families` (in `engine/`) prints the registry, the LIBRARY line of each library family and **every contract
error**. A module that fails to import or an entry that breaks the contract is not registered (`families.ERRORS`), and
`run_menus` refuses to run while that dict is not empty. A 4-tuple (the L2 pilot's 14 screen entries) stays registered
but is **not** a library family until it carries the 5th field.

## 2. Writing a family on `l2sim.Template`
The Template is the port of `R/template.py` (the tester drafts `pp_<fam>`): 1-minute bars aggregated into tf bars on ET
clock multiples; indicators (Wilder ATR14 `self.atr`, EMAs `self.E[span]` for `SPANS`, `self.O/H/L/C/V`, `self.nb`) run
over every tf bar since the last restart; session objects (`self.vw()` session VWAP, `self.vwr()` anchored VWAP, `self.sn`,
`self.n_ent`, `self.onh/onl`, `self.rng(a, b)`, `self.mo(a)`, `self.mc(a, b)`, `self.pdh/pdl/pdc`, `self.datr()`) as in R.
Hooks: `fam_day(ctx)`, `fam_session(ctx, s)`, `fam_update(ctx)` (every tf close), `fam_signal(ctx)` (tf close inside a
session, flat, entries left, not in the last 5 minutes), `fam_times()` + `fam_time(ctx, sec)`, `fam_filter(ids)`,
`sess_on(s)`, `fam_sessions()`. Entries: `self._mkt(ctx, side, struct=, tp_px=)`, `self._arm(ctx, legs, ttl=, lp=)` (stop
entries; two legs = OCO), `self._lim(...)`. Exits: the menu's stop / target, `trail_atr`, `exit_bars`, `ctx.flatten(reason)`.
**A port copies the R family's `class Fam` body verbatim** (`SESS`, `_hms`, `_sec` are module globals of `l2sim`; read the
session table through `self.S[...]` if you define your own windows). Tested inputs must stay those of the tester draft.

### Sessions (`sess` input; split offline by entry time with `l2sim.session_of`)
| key | ET window | notes |
|---|---|---|
| asia | 00:00–03:00 | unchanged |
| london | 03:00–08:25 | unchanged |
| **pre** | 08:25–09:30 | NEW. Overnight range `onh/onl` = 00:00–08:25. |
| nyam / mid / pm | 09:30–11:00 / 11:00–13:30 / 13:30–15:58 | unchanged |
| **eve** | 18:00–23:59 | NEW. The evening **before** the trade date; the trade's `date` is the NEXT trade date (Sunday evening → Monday). Every indicator and session object **restarts at 18:00** (and again at 00:00, exactly as the tester's day). No overnight range, prior-day levels = the day that ended at 17:00. |

`sess="all"` = the tester's five (bit-identical to the tester). Every Template family gets `eve` and `pre` without any
code: **`run_menus` runs each menu cell as three independent instances — `sess="all"`, `"pre"`, `"eve"` — in the same tape
pass and merges their trades**, so the five sessions of a library run are exactly the tester-matched family and the two new
sessions cannot change one of their trades. (`sess="globex"` = all seven in ONE instance also exists; a family that carries
state across a session boundary can then differ from the tester at the first bars after 09:30, so the menus do not use it.)
The evening is its own engine segment (replayed before the day window): no trade spans 00:00 or the 17:00–18:00 break. In
the evening `fam_time(ctx, sec)` gets **negative** seconds (18:00 = −21600; `sec` is always relative to 00:00 ET of the
trade date) and `ctx.segment == "eve"`. A family restricted to some sessions keeps doing it through `fam_filter` (e.g.
`ib`: NY only → its `pre` and `eve` instances simply never trade).

## 3. The clock-time API (time-fired families; family A `straddle_t`)
```python
import l2ref, l2sim as S
class StraddleT(l2ref.StraddleT):           # subclass in YOUR module, register it; inputs: at, flat, cancel_min, off_mode, off_val
    pass
```
* `S.LISTED_TIMES` = 18:00, 20:00, 00:00, 02:00, 03:00, 08:30, 09:30, 11:05, 13:30. `S.clock_sec("18:00") == -21600`
  (17:00–18:00 raises), `S.clock_session(t)` → eve / asia / london / pre / nyam / mid / pm, `S.clock_flat(t)` = EDGE_SPEC's
  "flat at the next listed time or the session end, whichever is first" (18:00→20:00, 20:00→23:59, 00:00→02:00, 02:00→03:00,
  03:00→08:25, 08:30→09:30, 09:30→11:00, 11:05→13:30, 13:30→15:58).
* A time-fired family defines its own window with `fam_sessions()` → `{"t": (start_s, end_s)}` and `fam_filter` → `["t"]`;
  a window in the evening is run in the evening segment, a window that ends after 16:10 extends the day window to 17:00.
  A window may not span 00:00. `sess` is unused; the trade is tagged offline by its entry time.
* **ATR30** = the Template's ATR at tf 30 (`SCREEN_TFS = ("30",)`). `ATR_CARRY = True`: until 3 half-hour bars exist since
  the last restart (i.e. for a fire at 18:00 or 00:00) the ATR is `ctx.atr_carry` = **the closing ATR30 of the most recent
  evening that has ended** (18:00 → the previous trade date's evening, 00:00 → the evening just ended; cache
  `engine/cache/eve_atr30_<ROOT>.json`, prints before the decision only). 20:00, 02:00 and later use the running value,
  exactly as the tester's straddle.
* **Anchor price**: `ctx.last_price` (last print inside the window) → at 00:00 `ctx.prev_price` (the last evening print) →
  at 18:00 `self.pdc` (the previous trade date's last print; the orders go live at 18:00:00.085 and a gapped reopen fills at
  the gap). On a contract-roll day there is no 18:00 trade. Pass it on: `self._arm(ctx, legs, lp=lp)`.
* `begin_day(d)` (optional method): the runner calls it before it reads `times()` for the day (a day-dependent schedule).
* **Time-shuffle null**: any family with an int input `shift_seed` is treated as time-fired by `run_menus`: the same grid
  is run again with `shift_seed` 1 and 2 = the same straddle at a seeded uniformly random minute within ±90 min of `at`
  (kept inside its segment: evening 18:00–23:59, day 00:00–15:58; one draw per trade date, the same for every cell).
* Proof (tests/test_edge_clock.py, EDGE_VALIDATION "CLOCK"): `StraddleT` at 03:00 / 09:30 / 13:30 = `l2ref.Straddle`
  london / nyam / pm trade for trade over 2021-09-22 → 2024-12-31 on NQ and ES.

## 4. The menu (pre-registered; `l2sim.menu*`)
* `S.menu(root)` → the **32 exit cells** `{"stop_mode", "stop_val", "tgt_r"}`: stops ATR × {1.5, 3} · points NQ {10, 20,
  30, 45} / ES {2.5, 5, 8, 12} / GC {2, 3, 5, 7} · percent {0.10, 0.20} (`stop_mode="pct"`: stop_val % of the entry reference
  price) × targets `tgt_r` {0 = none, 1, 2, 3}. `S.menu_offsets(root)` → the 5 straddle offsets (`off_mode`, `off_val`).
* `families.unit_grid(name, root, tf)` → every registered variant × the 32 cells (`S.menu_grid`), ids like `n20_atr1p5-r2`.
  A grid of N cells counts N cells against the 40,000 cap. The plateau is judged over ALL of a unit's cells, per session.
* Position size is not a variant: every run is 1 contract.

## 5. Level-2 filters / exit on the Template (NQ only; stage D: only on base units that passed the BUILD plateau)
| input | rule | no signal (NaN / `book_ok` False / stale row) | columns to load |
|---|---|---|---|
| `f_book="on"` (D2) | an entry is allowed only if the 5-minute mean `imb10` does not oppose its side (long: mean ≥ 0) | **no entry** | `imb10`, `t_utc` |
| `f_thin="on"` (D4) | an entry is allowed only if the break-side depth is thin: `ask10_rel15` (long) / `bid10_rel15` (short) ratio ≤ 0.8 (column ≤ −0.2) | **no entry** | `bid10_rel15`, `ask10_rel15`, `t_utc` |
| `x_book="on"` (D3) | at every 1-minute close with a position open: mean opposed at 2 consecutive **usable** minutes → `ctx.exit_market("book")` | **nothing happens**; such a minute neither counts nor resets | `imb10`, `t_utc` |
| `f_depth` | B6 thin / thick book (as before) | no entry | `depth10_rel20d` |

The 5-minute mean = the L2 pilot's gate G1 signal (`S.book_mean5`: 5 consecutive finite rows, the newest one the minute that
just ended). `ctx.exit_market(reason)` is a MARKET order that respects the placement latency (and the 1 s execution guard, and
the stress), unlike `ctx.flatten`. `l2sim.run` refuses these options without `features=L2Features([... the columns ...])`
(`families.features_for(name, S.template_feature_needs(params))` builds it) and on any root but NQ.
`library.run_member(..., extra={"f_book": "on"})` runs a member cell with an option.

**STAGE D does NOT run these options on the base class** (note added by the NEW_L2 author in the verify round, 2026-10-02;
nothing in `l2sim.py` was changed). On a resting entry (orb, straddle, straddle_t) the engine reads `f_book` / `f_thin` once,
when the bracket is placed, and `x_book` needs no flip: that is not EDGE_SPEC D2 / D3 / D4. Stage D goes through
`engine/families/l2ideas.py` (read its docstring): `l2ideas.stage_class(base)` = a mixin in front of the base's registered
class — a market entry keeps the engine's rule; a resting bracket is the base's own and each fill is kept or skipped by the
filter's verdict at the 1-minute decision that began the fill's minute (`l2ideas.kept`); the book exit is armed only once the
book has not opposed the trade. Run it with `l2ideas.run_variant(name, tf)` (sealed by the base's own BUILD store, session
by session), read it with `l2ideas.variant_table(name, tf, sess)`, run a member cell with `l2ideas.run_member(...)` — never
`library.run_member(base, ..., extra={...})` for a stage D member.

## 6. Roots
`l2sim.run(..., root="ES" | "GC")`: ES $50 / pt, tick 0.25; GC $100 / pt, tick 0.10; $4.00 round turn, 1 tick slip
(the tester's table, as the ES pilot). ES / GC replay the tester's own tape cache `~/futures_derived/homebase_tape/<ROOT>/`;
sessions the tester never cached are built with the tester's own code into `engine/cache/tape/<ROOT>/`
(`python engine/l2sim.py tapes GC`; done for GC BUILD + PICK: 824 sessions). Session list = the archive manifests (as the
tester). Half days clamp equity-index roots only. No features and no L2 option outside NQ. The menu's fixed-point sizes
differ per root; ATR and percent cells are unit-free. `score.py` (account rules) is NQ only — see open risks.

## 7. Smoke test — bugs only, never P&L
```
cd W/engine && "~/ONYX TRADING/.venv/bin/python" -m families                      # registered? contract errors?
cd W        && "~/ONYX TRADING/.venv/bin/python" run_menus.py smoke <family> --root NQ --tf 5 --days 10 --workers 1
cd W/engine && "~/ONYX TRADING/.venv/bin/python" -m pytest tests/test_families.py -k <family>
```
`run_menus.py smoke` runs the family's whole menu grid on ≤ 10 fixed BUILD days (early sample, a roll day and roll + 1, two
half days, an FOMC day, plain days), ≤ 2 workers, writes nothing, counts nothing against the caps and prints **counts only**:
sessions, dropped sessions and the first error, trades in total / per cell (min, max) / per session / per side / per stop
mode, cells without a trade, market vs resting entries, the both-side evidence against your declaration, 1- vs 2-worker
parity, the nulls' trade counts (time-shuffle, C2). `ok: true` = no dropped session, the declaration matches, parity holds,
the nulls run. Zero trades everywhere = a bug or a trigger that never fires; never look at a P&L to decide which.

## 8. Tester-match gate of a PORTED family
A port must reproduce its old tester bundles before its BUILD menu runs: same (date, side, entry time, entry price, exit
price, exit reason) on ≥ 99 % of the trades, net within 0.5 %. Use `sim_validate.compare(sim_trades, ref_trades)` and
`sim_validate.load_bundle("grid_id#cell")` / `edge_validate.load_run(run_id)` (they refuse a bundle whose range reaches 2025
and drop every row outside the in-sample window before anything reads it); the run ids are in `R/jobs.jsonl` (stage
`screen`, key `screen-<fam>-tf<tf>`) and `RE/jobs.jsonl` for ES. Assert identity; never print the bundle's P&L. Never
touch a `holdout` stage bundle. `tests/test_edge_roots.py` and `tests/test_edge_controls.py` are the pattern.

## 9. Controls and the nulls bar
* **C1** random entries: `l2ref.Random` (the port of `R/families/random.py`; tester-matched) with the same exit cell, pooled
  over seeds 1 and 2 (`run_menus.py nulls` → `c1-<ROOT>-tf<tf>`, p_entry 0.5, all seven sessions). `library.c1_draws(member,
  pool)` = K day- and session-matched random ledgers → `lift` (member net − mean), `p_beat`, `fallback_share`, `short`.
  For a clock-time family the timing-matched control is the **time-shuffle null** (§ 3).
* **C2** feature shuffle (L2 families): `score.C2Features(cols, seed=1 | 2)`; `run_menus` runs both seeds for an L2 unit.
* `library.best_of_nulls(batch)` = the 95th percentile, over the batch's null replicates (one seed × one unit-session over
  the menu), of each replicate's BEST cell; statistic `t` (per-trade net: unit-free). `library.unit_null_replicates(store)`
  builds the replicates of a null store. Fewer than 20 replicates is flagged `thin`.

## 10. Library tooling (`library.py`)
* **Ledger `W/ledger.csv`, HARD caps**: runs ≤ 2,000 · grid cells ≤ 40,000 · walk-forwards ≤ 40. `ledger_add(stage, key,
  "grid", cells=N)` counts N cells; a row / batch past a cap raises `CapExceeded` and appends nothing (`ledger_check` before
  a batch). **Null cells and failed batches count too** (the L2 pilot's convention). `python library.py ledger`.
* **Plateau** `plateau(table)`: pass ⇔ median net over ALL cells > 0 and ≥ 60 % of the cells > 0 (a cell without a trade
  is not > 0). Member = the positive cell whose net is closest to the unit's median (central in outcome — never the best
  cell; several parameter axes are categorical, so a grid position has no centre); ties → the lowest (variant, exit) index.
* **Admission** `admission(member)` (fail closed; a missing input fails): net > 0 on BUILD and on PICK · BUILD plateau (and
  PICK plateau for a `penalty` family) · beats C1 in both (lift > 0, nothing unmatched) · beats C2 in both (L2, both seeds)
  · BUILD t above the batch's best-of-nulls bar · stressed net (2 ticks + 250 ms) > 0 in both, reported next to the base ·
  ≥ 100 trades (BUILD + PICK) · the worst per-trade open loss fits $2,000 at ≥ 1 micro · rationale + complexity · a WEAK
  member needs t ≥ 3 on BUILD. `write=True` → `members/<name>/{spec.json, trades_build.json, trades_pick.json, daily.csv,
  card.md}`; a rejected candidate → `members/_rejected/<name>/{spec.json, card.md}`.
  `daily.csv`: date, period, net, worst_open_loss (USD ≥ 0: how far the day's P&L, open losses included, was below its
  start at the worst point), minutes_in_market; one row per session of the calendar (0 rows for no-trade days).
* `run_member(family, root, tf, variant, exit_cell, period, sess=, stress=, c2_seed=, extra=, build_plateau=)` = one full
  run of a member cell (1 run in the ledger), on the same instance the menu used for its session (`all` / `pre` / `eve`),
  keeping only that session's trades: the Admit stage's PICK / stress / C2 runs.
* `run_menus.py plan | status | run --family f [--roots NQ,ES,GC] [--tf ..] | nulls | smoke`: stores under `runs/<key>/`
  (`run.json` with the range and period, `cells.npz` = every trade of every cell, `table.csv` = cell × session), one ledger
  row per store, idempotent. A pass that dropped a session writes no store (`<stage>_error` row; fix the family).
  `library.load_unit(key)`, `unit_cell(u, id)`, `session_table(u, "pm")` → `plateau(...)`.

## 11. Known conventions and open risks (read before trusting a number)
1. **GC has no tester bundle**: validated by construction (tester tape code byte-identical, same engine, arithmetic tests,
   independent `nfp_lib` replay on 5 NFP days). Flag it on every GC member.
2. **Evening / pre sessions and the clock path cannot be run in the tester.** Their proof is internal (§ 3). Overnight
   spreads are wider than the 1-tick slip (SIM_VALIDATION open risk 1): the stress test is the hard gate for eve / asia.
3. **18:00 fires** anchor on the previous close and use the previous evening's ATR30; they do not exist on roll days.
4. A skipped evening (a clock hour without a print between 18:00 and 24:00) is listed in `eve_skipped`; the day still runs.
5. `score.py` (eval / funded account rules) is hard-wired to NQ ($20 / pt, R's pilot context). ES / GC account scoring needs
   R's pilot selector (`PP_PILOT=es`) in a separate process, or a root-aware scorer: a later stage.
6. (CLOSED 2026-10-03) Null cells no longer count against the 40,000 cap: ledger kind `null` / column `null_cells` (§ 0a 6).
7. `x_book` checks at 1-minute closes that have a print; a minute without a print is not a decision.
8. The per-trade `t` statistic treats trades as independent (same-day trades are not): the nulls bar uses the same
   statistic, so the comparison is fair, but an absolute t ≥ 3 is weaker than it sounds for 3-trades-per-session families.

9. **hold_to = "day" has no tester equivalent** (the tester flattens at the session end): its proof is internal — the
   entries are the tester-matched ones (§ 0a 1), the exits are the same engine orders held longer. Overnight holds cross
   the thin hours: the 2 ticks + 250 ms stress stays the hard gate, and `worst_open_loss` (daily.csv, the metric set) now
   carries the whole hold.
10. **"Structurally dead" is read from entry counts** (a variant without a trade in a session in any exit cell over BUILD),
    not from a per-family predicate: a variant that could trade by its rules but never fired in 2.3 years is also left out
    (port2's `can_trade` lists the by-construction cases; the two agree on them). Decided before any valid run.
11. A held evening trade date is skipped when the DAY has an empty clock hour (e.g. NQ / ES 2023-04-07): slightly fewer
    evening sessions than under the old convention.
12. Compute: seven instances per cell instead of three; with EARLY_STOP roughly 1.5–2 × the old pass time (measure on the
    first units and budget the BUILD run accordingly).

## 12. Tests and gates
STATE 2026-10-03 10:10 ET (after the ORCHESTRATOR DECISIONS): full suite `EDGE_MAX_WORKERS=3 L2_TEST_WORKERS=3 python -m pytest` →
1,334 passed, 2 skipped by design (~10 min); `edge_validate.py`, `port1_gate.py`, `port2_validate.py --fresh`, `port3_validate.py`
all re-run on the final `l2sim.py` (sha256/16 461192700c259bfd): ALL PASS. The lines below are the 2026-10-02 state.
* `cd W/engine && EDGE_MAX_WORKERS=3 L2_TEST_WORKERS=3 "~/ONYX TRADING/.venv/bin/python" -m pytest` → 888 tests: 886 passed, 2
  skipped by design (F3 has no percentile case; the L2 pilot's screen bundles are not copied here). 77 of them are the
  edge-library tests `tests/test_edge_*.py` (periods, roots, clock, template, controls, library, run_menus). ~6 min.
* `"~/ONYX TRADING/.venv/bin/python" edge_validate.py --workers 4` → `EDGE_VALIDATION.md`: ALL GATES PASS (~5 min).
  Re-run both after ANY change to `l2sim.py` / `l2ref.py`.

## 13. STAGE 2b — NEW-IDEA ROUND 1 (`engine/families/round1.py`): how it is declared and run
Written from EDGE_SPEC "STAGE 2b" before any result (engine coder, P&L-blind). Nine registry entries = the seven families:
`vwap_trend_pull` (N1, tf 1/5/15/30, nyam / mid / pm), `va_reclaim` (N2, tf 1/5/15/30, all seven sessions), `orb_confirm` (N3,
tf 1/5/15, nyam / mid / pm, MIRROR axis `dir`: long-only and short-only are separate judged units), `late_mom` (N4, time-fired,
tf 30), `open_fade` (N5, tf 1/5, nyam), `vol_spike_break` (N6, tf 1/5/15/30, all seven), `straddle_tight_0830 / _0930 / _1000`
(N7, time-fired, one entry per clock time as `straddle_t`). Roots NQ / ES / GC, `hold_to = day`, 1 contract.
* **How each written rule is read** is fixed in the module docstring (read it before judging a number). The main ones: a
  "day" limit (max trades, one trade a day, stop after 2 losing trades) = ONE session instance (a member trades one session);
  "next bar open" = a market order at the signal bar's close; N1 "first candle against the trend" = the first down bar after
  a bar that was not down (mirror for short), with the state read on that bar; N2 value area = 70 % of the previous trade
  date's 09:30–16:00 volume by price in 1-tick rows (none on a contract-roll day); N4 prior close = the Template's `pdc` (the
  previous trade date's last print); N5 ATR = the engine's ATR30, the stretch is disarmed when price trades back to ref.
* **New hooks** (classmethods of a family class, read by `families.unit_grid` / `run_menus`; old families are untouched):
  `unit_exits(root)` = the family's OWN exit cells instead of the 32 menu cells (N7: 3 stops × 3 targets, points scaled per
  root); `author_cells(root, tf)` = INFORMATION-ONLY cells, one per variant each, appended after the menu cells with
  `'info': True` — they are run and stored (`run.json` cells carry `info`), they count as candidate cells in the ledger, and
  `library.session_table` / `judged_rows` / `plateau` leave them out (`plateau()['info']` = how many; `cells_all` excludes
  them; never the central cell). N1: 3 cells on NQ tf 15 (stop 80 pts, target 40 long / 50 short); N3: 6 per unit (stop at
  the other side of the range, flat 15:30); N5: 24 per unit (target = ref with each of the 8 menu stops);
  `prepare(root, workers)` = a one-off cache built in the main process before a unit's pass (N2: `cache/va70_<ROOT>.json`,
  BUILD dates only; a worker that misses a date computes it from the previous day's tape with the same function; a 2025+
  date raises `HoldoutSealed`).
* **Nulls.** Bar-based families (N1, N2, N3, N5, N6): the C1 pool `c1-<ROOT>-tf<tf>` (day- and session-matched random
  entries with the same exit cell, `library.c1_draws`) — all 12 pools already exist; `run --group` runs a missing one.
  N4: `shift_seed` 1, 2 = the SAME 15:30 trade on the same days with a seeded coin-flip direction (store `late_mom-<ROOT>-
  tf30-shift`; the engine's input name is kept so `is_time_fired` / `unit_null_replicates` work unchanged). N7: `shift_seed`
  = the same bracket at a random minute within ± 90 min (as `straddle_t`); its own exit cells have no C1 pool.
* **Plan** (`python run_menus.py plan --group round1`): 63 run units, 7,068 candidate cells (201 author cells among them) +
  2,214 own null cells; candidate cap raised 40,000 → 50,000 (`library.CAPS`); used 35,770 (ledger.csv 34,946 + 824 booked
  on paper, `run_menus.PAPER_CELLS`) + 7,068 = 42,838 → fits, 7,162 left.
* **Run** (restartable: a stored key is skipped; ≤ 8 workers; waits out 09:18–09:36 ET by itself):
  `cd W && nohup "~/ONYX TRADING/.venv/bin/python" run_menus.py run --group round1 --roots NQ,ES,GC --workers 8 >> out/run_agent/round1.log 2>&1 &`
  then `python run_menus.py status --group round1` (pending keys). One family: `run --family va_reclaim --roots NQ`.
* **Judge.** `straddle_tight_0930`: a fill in the last second before 09:30 is tagged `pre` — judge it over session `all`.
  Structurally dead unit-sessions (entry counts, not P&L): N1 tf 30 in nyam (the VWAP slope needs 4 closes after 09:30);
  N6 needs 21 bars since the restart (tf 30 from 10:30, tf 15 from 05:15; evening tf 15 only from 23:15, tf 30 never).
* **Tests / smoke.** `tests/test_round1.py` (34 tests: entry logic on synthetic bars, garbage-after-a-cut no-look-ahead for
  all seven, next-bar entries, value area from yesterday's RTH prints only, limits, 1 vs 8 workers, stores with author
  cells). Smoke, counts only: `python out/engine_owner/round1_smoke.py NQ` → `out/engine_owner/round1_smoke_NQ.log`
  (`run_menus.smoke` now also counts `entry_outside_hours` from the module's `ENTRY_WINDOWS`).

## 14. STAGE 4 — EVENT ENTRY VARIANTS (`engine/families/round2.py`): how it is declared and run
Written from EDGE_SPEC "STAGE 4" before any result (engine coder, P&L-blind). Four registry entries, all time-fired (tf 30,
ONE instance per cell, `hold_to = day`, NQ / ES / GC, 1 contract). They run on EVERY BUILD day; the release-day filter
(groups A / B / C of the STAGE 3 calendar) is laid on the stored trades by the analyst.
* **W `straddle_wide_0830` / `_1000`** = round1's `straddle_tight` with the wider written offsets: OCO stop entries at the last
  print ± `off` (A / B / C / D: NQ 10 / 15 / 20 / 30, ES 2.5 / 4 / 5 / 8, GC 2 / 3 / 4 / 6 points), placed 1 s before the clock
  time, unfilled legs cancelled 5 min after it was placed, entries until 09:30 / 11:00. Own exits (`unit_exits`): **new
  `stop_mode = "offx"`** (this class only) = stop distance from the fill = `stop_val` {0.5, 1, 1.5} × the cell's offset;
  target 1:1 / 1:2 / 1:3. 4 × 9 = 36 cells, ids like `offA_offx0p5-r1`. `library.plateau` shows them as stop group `offx`.
* **D `event_dir_0830` / `_1000`**: anchor = the last print STRICTLY BEFORE the release time T (`ctx.last_price` at the T
  event). Decision at T + `x` (`x` = 0.25 / 0.5 / 1 / 2 / 5 / 15 / 60 s): the last print stamped AT OR BEFORE T + x vs the
  anchor → ONE market order that way (`_mkt`, live after the order delay: 85 ms, stress 250 ms; fills at the first print
  from then on + slippage); no move (or no print since T) = no trade; one decision and one trade a day. Stop reference =
  the decision print; ATR stops = ATR30. Exits = the 32 menu cells: 7 × 32 = 224 cells, ids like `x0p25_atr1p5-r2`.
  `both_sides` False (one direction, no resting order).
* **Engine change (one line): `l2sim.et_ns` keeps a fraction of a second** (`'HH:MM:SS.ffffff'`; it was cut off before).
  A whole-second time gives the value it always gave. `EventDir` writes its decision time always with the fraction and
  takes that event in its own `on_time`, so the Template's whole-second clock never sees it. Gates on the final file
  (l2sim.py sha256/16 72369e8b94b85172): `edge_validate.py`, `port2_validate.py --fresh`, `port3_validate.py` ALL PASS
  (logs `out/engine_owner/stage4/*_final.log`); the same three also passed on the file as it stood after the `oco_cancel_ms`
  edit (bc7394332573ff85). Full suite 1,420 passed, 2 skipped by design.
* **Nulls** (`shift_seed` 1, 2, the unit's `-shift` store, same tape pass): W = the same bracket at a seeded random minute
  within ± 90 min (as `straddle_tight`); D = the SAME entry at the same instant on the same days with a seeded coin-flip
  direction per (seed, date, clock time) — the same flip for every `x` and exit cell (as `late_mom`). No C1 pool is needed.
* **Plan** (`python run_menus.py plan --group round2`, saved in `out/engine_owner/stage4/plan_round2.txt`): 12 run units,
  1,560 candidate cells (D 6 × 224, W 6 × 36) + 3,120 own null cells; cap 43,388 used + 1,560 = 44,948 of 50,000 → fits,
  5,052 left. The 18 JUDGED units = {W, D} × {A, B, C} × 3 markets are day filters on these 12 stores.
* **Run** (restartable: a stored key is skipped; ≤ 8 workers; waits out 09:18–09:36 ET by itself):
  `cd W && nohup "~/ONYX TRADING/.venv/bin/python" run_menus.py run --group round2 --roots NQ,ES,GC --workers 8 >> out/run_agent/round2.log 2>&1 &`
  then `python run_menus.py status --group round2`.
* **Tests / smoke.** `tests/test_round2.py` (23 tests: registry, grids and plan; `et_ns` fraction; D direction, anchor
  strictly before T, prints at / 1 ns after T + x, order live only after T + x + delay, one trade a day, ES / GC ticks, the
  null; garbage after the decision instant changes no decision — synthetic and 3 real days; W bracket, cancel, null,
  no look-ahead; 1 vs 8 workers on NQ and GC). Smoke, counts only: `python out/engine_owner/round2_smoke.py NQ|GC` →
  `out/engine_owner/round2_smoke_<ROOT>.log`: ALL OK on both (0 errors, 0 entries outside the window, max 1 trade a day,
  worker parity; GC uses 9 of the 10 smoke days).
* **Read before judging (print counts only, `out/engine_owner/stage4/burst_timing.json`).** On the 159 tier-1 08:30 days of
  BUILD the tape's burst comes about 1.25 s AFTER 08:30:00 (median start of the busiest 250 ms; it lies in the first
  0.5 s on only 13–17 % of days; median 2 prints in the first 0.25 s, none at all on 14–25 % of days). So at 08:30
  `x` = 0.25 / 0.5 s mostly decide BEFORE the burst (or do not trade). At 10:00 the burst is in the first 0.25 s on 63–75 %
  of days. Nothing was changed for it: the written X stay as written.

## 15. BLOCKS AND IDEA SPECS (`engine/families/blocks.py`, `run_idea.py`): an idea = settings, not new code
Written 2026-10-05 (engine coder, P&L-blind; EDGE_SPEC "WORKBENCH PLAN" 2). Nothing in `l2sim.py`, `library.py`, `run_menus.py`
or another family module was changed. Full definitions: the docstring of `blocks.py`; tests: `tests/test_blocks.py` (44).
* **How it works.** `blocks.Blocks` is a mixin put IN FRONT of a family class: `blocks.WRAPPED[name]` = `B_<name>(Blocks, <the
  registered class>)` for every bar-based library family without Level-2 features (27; time-fired families are left out). It
  overrides two Template methods only: `allowed(side)` (the filters) and `_dist` (the range stop). All blocks default off, and then
  a wrapped family is trade for trade the original (proved on 10 BUILD days x 3 markets x 6 families). A block is read **when the
  family places its order**: the signal bar's close for a market entry, the placement instant for a resting bracket (orb / ib_n:
  the range end) — never at a later fill; a direction filter on a two-sided bracket keeps the leg it allows. A filter with no
  signal blocks the entry on BOTH sides.
* **Exit blocks.** `stop_mode = "rng"`: stop = `stop_val` x the height of the family's own structure (`blocks.HEIGHTS`: orb /
  orb_confirm opening range, ib / ib_n range, lon_break London range, donchian n-bar channel, vol_spike_break 20-bar channel,
  first_bar_mom signal bar); floor 2 ticks; no structure yet = no entry; a family without one refuses the mode. More ATR stops and
  targets are menu cells only: `blocks.menu_extended(root)` = the 32 standard cells (same order and ids) + stops ATR x 1 / x 2 and
  range x 0.25 / 0.5 / 1, targets + 1.5 and 4 → 78 cells (60 without a structure). `library.plateau` shows the stop group as `rng`.
* **Filter blocks** (`blocks.FILTERS`: block → side → input). `volatility` high / low (`f_dvol`): the prior day's range above / not
  above the median of the 20 daily ranges ending with it (= out/deepen/labels.py T2). `momentum` with / against (`f_rsi`): Wilder
  RSI(14) of the closed tf bars since the restart, > 50 for a long with it. `volume` high / low (`f_cvol`): the volume from
  the session's anchor (asia 00:00, london 03:00, pre 08:25, nyam / mid / pm 09:30, eve 18:00: `blocks.VOL_ANCHOR`) to the decision
  vs the median of the same clock window over the 20 prior trade dates (`cache/minvol_<ROOT>.npz`, built by
  `blocks.build_minvol(root, period)`; a worker that misses a date reads that date's tape). `news` yes / no (`f_news`): the trade
  date has a row at 08:30 or 10:00 ET in `cache/events.csv`. `book` agree / disagree (NQ): agree = the Template's own `f_book="on"`,
  disagree = `f_bookopp="on"` (the same `l2sim.book_mean5`, opposed). Dead by warm-up (entry counts): RSI needs 15 closes since
  00:00 / 18:00 (tf 30: from 07:30, never in asia / eve; tf 15: from 03:45, eve from 21:45).
* **`ib_n`** (registered by `blocks.py`; group `blocks`): `port1.Ib` with `ib_min` 5 / 15 / 30 / 60 minutes from 09:30 (60 = ib, trade
  for trade), tf 5 / 15 / 30, NY sessions.
* **An idea** = `ideas/specs/<name>.json`: name, reason (required, plain words), family, markets, bar_sizes, sessions, params (main
  values; every combination = a variant), fixed, filters (each = one separate filter unit), exits `standard` | `extended`,
  optional filter_exits, limits (max_tr, dir, exit_bars, trail_atr). `run_idea.py plan | build | status | catalog | smoke <spec>`
  (its docstring has the format). Units: `<name>-<ROOT>-tf<tf>` and `<name>__<block>_<side>-<ROOT>-tf<tf>` in `runs/` (run.json
  `family` = the entry family, `idea`, `filter`), stage `build`, hold_to = day, one instance per session of the spec. `judge.py`
  addresses a unit as `<key>-<session>`; `run_idea.py catalog '<pattern>' --out f.csv` → `judge.py table --stage f.csv`.
* **Controls** (stage `null`): the C1 pool `c1-<ROOT>-tf<tf>` (standard cells); `c1x-<ROOT>-tf<tf>` = the same random entries for the
  extended cells without a structure (ids `s<seed>_<exit id>`); `<name>__c1r-<ROOT>-tf<tf>` = random entries carrying the idea's own
  structure height (`blocks.CONTROLS`, ids `s<seed>_<structure inputs>_<exit id>`); a book unit also `<key>-c2s1 / -c2s2` (shuffled
  book). **judge.py does not read `c1x` / `c1r` yet**: until it does, an extended table fails its control with "no pool cell".
* **Cap**: `run_idea.CAPS` = 80,000 candidate cells, handed to the ledger calls (library.CAPS still says 50,000); a spec whose
  pending cells do not fit is refused as a whole. ≤ 8 workers (`l2sim.MAX_WORKERS`); two builds of different specs can run side by side.
* **Adding a block**: one input in `Blocks.DEFAULTS / SCHEMA`, one check in `Blocks.allowed`, one `FILTERS` entry, and its three
  tests (does what it says; garbage after the decision changes nothing; 1 vs 8 workers). A new structure = one `HEIGHTS` entry.
* **Open**: filters are not read at the FILL of a resting bracket; `f_bookopp` without a feature table trades nothing (silently,
  as `f_book`); a period other than BUILD needs `build_minvol(root, period)` first or reads the tapes on the fly.
