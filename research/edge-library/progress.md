# Edge library — progress (read me first on resume)
Spec: EDGE_SPEC.md (user rules, three periods, pre-registered menu, families + rationales). Engine copy: engine/.
- 2026-10-02 09:55 ET: workflow wf_6ce8bac5-db0 launched: infra (ES/GC, Globex clock, pct stops, nulls, library tooling) →
  ports of the 21 old families + straddle_t (18:00, 20:00, 00:00, 02:00, 03:00, 08:30, 09:30, 11:05, 13:30) + vwap_ema_x +
  L2 filter/exit ideas → verify → BUILD menus + nulls → plateau / PICK / stress / admission → cards in members/.
- Still running elsewhere: L2 screen analysis (wf_a10cf61f-56b), intraday re-rank of the old pilot (wf_149fdfe8-abe).
- 2026-10-02 10:10 ET: menu AMENDED by user (4 fixed-point stops, targets none/1:1/1:2/1:3 → 32 exit cells; grid cap 25,000). First workflow stopped before any run; relaunched.
- 2026-10-02 10:25 ET: user: re-run the pilot PROPERLY (7 fixes) → EDGE_SPEC 'PROPER RE-RUN' section: family-parameter variants from R tune axes, all screen tfs, eve/pre sessions for all families, 40,000-cell cap, NQ→ES→GC. Workflow relaunched.
- 2026-10-02 11:10 ET, ENGINE OWNER (infra) — read `ENGINE.md` first. Done: engine copy repaired (R / RE paths, missing modules, cache);
  multi-root NQ / ES / GC (`l2sim.run(root=)`; ES + GC replay the tester's tape cache, GC tapes for BUILD + PICK built into
  `engine/cache/tape/GC`, 824 sessions); periods BUILD / PICK / EXAM in `l2sim` (EXAM raises; `period=`; range + period in every bundle);
  Globex-day clock (evening = own segment of the next trade date; `eve` / `pre` sessions for every Template family; ATR30 carry;
  `l2ref.StraddleT` + time-shuffle null); Template: `stop_mode pct`, `f_book`, `x_book`, `f_thin`, `ctx.exit_market`; the 32-cell menu
  (`l2sim.menu`, `families.unit_grid`); registry 5-tuple with mandatory rationale + complexity; `l2ref.Random` (C1, tester-matched);
  `library.py` (ledger with hard caps, plateau, best_of_nulls, c1_draws, admission, member folders, run_member); `run_menus.py`
  (plan / run / nulls / smoke; nothing run beyond 10-day smokes). Gates: `engine/EDGE_VALIDATION.md` (NQ 7 picks + 88 cells, ES 3 runs
  + 104 cells, random control, clock path: all 100 % identical). NO library family is registered yet (family authors' job);
  ledger.csv is empty (0 cells used).
- 2026-10-02 12:10 ET, PORT3 author (vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev) — `engine/families/port3.py` registered (5-tuples: rationale, complexity,
  variants = first axis of the R heat-maps: band / zth {1.5, 2, 2.5, 3}, hold {1, 2, 3}, wick {0.6, 0.667, 0.75}, levels {both, pd, on}; tfs 1 / 5 / 15 / 30; NQ, ES, GC).
  Class bodies = R/families verbatim. Tester-match gate `engine/PORT3_VALIDATION.md` (`port3_validate.py`): NQ 20 screen runs + 9 heat-maps (308 cells),
  ES 20 runs + 6 heat-maps (168 cells): ALL 100 % identical, net diff $0. `engine/tests/test_port3.py` (50 tests: verbatim body, scripted triggers, tester month,
  independent first-signal oracle in all 7 sessions, garbage-after-cut, 1-vs-8 workers, smoke). 30 counts-only smokes ok (`engine/out/port3_smoke.log`).
  READ `engine/PORT3_NOTES.md` before judging a plateau: structural empty unit-sessions (vwap_* tf30 nyam / pre; sweep_rev levels=on in eve / asia), SECOND-LOOK flags
  (vwap_z tf5, ES vwap_flip), vwap_flip weak-prior decision left to the orchestrator. No menu was run; ledger untouched.
- 2026-10-02 12:10 ET, NEW_TIME author (straddle_t, vwap_ema_x) — `engine/families/timed.py` registered: `straddle_t_1800 / _2000 / _0000 (WEAK) / _0200 / _0300 / _0830 /
  _0930 / _1105 / _1330` (= `l2ref.StraddleT` + the 5 menu offsets by name `off` in {atr0p25, atr0p5, atr1, ptsA, ptsB}, resolved per root; cancel 60 min, flat = `clock_flat`,
  max_tr 1, tf 30, time-shuffle null) and `vwap_ema_x` (WEAK PRIOR; n {9, 21, 50} x anchor {session, rth}; tf 1 / 5 / 15; max_tr 3). `engine/tests/test_new_time.py`
  (31 tests: registry = pre-registration, synthetic-tape triggers, identity with the engine straddle on NQ / ES / GC, independent cross oracle, 1-vs-W workers,
  garbage-after-cut + a leak the check must catch, ET-all-year clock). Counts-only smokes ok: 27 straddle units + vwap_ema_x NQ tf 1 / 5 / 15, ES 5, GC 5.
  `run_menus.py plan`: 36 units = 14,688 cells incl. the time-shuffle nulls (12,960 straddle, 1,728 vwap_ema_x). No menu was run; ledger untouched.
  OPEN for the orchestrator: 11:05 has no event in EDGE_SPEC (not marked weak); vwap_ema_x anchors are identical outside mid / pm; thin unit-sessions (tf 15 pre / nyam).
- 2026-10-02 12:20 ET, PORT1 (families/port1.py): orb, straddle, donchian, squeeze, ib, lon_break, gap registered as edge-library families (rationale, complexity, screen tfs 1/5/15/30, variants = first axis of R/tune1|tune2 heat-maps; donchian carries the 2025-26 penalty). Tester-match gate `engine/port1_gate.py` -> `engine/PORT1_VALIDATION.md`: 28 NQ + 28 ES screen bundles and 300 NQ heat-map cells (every registered variant), all 100 % identical, net diff $0. Tests `engine/tests/test_port1.py` (48). Smokes (counts only) ok on NQ all tfs, ES / GC tf 5 + 30. 84 units, 7,680 cells; NO menu run. Open: cells that cannot trade by warm-up (e.g. donchian n 40 / 60 at tf 30) count as "not > 0" in the plateau; ib fade / gap fill ignore tgt_r (4 identical cells per stop); ib and gap variants are opposite hypotheses in one unit.
- 2026-10-02 12:20 ET, PORT GROUP 2 (`engine/families/port2.py`): ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2, first_bar_mom, tod_drift, mid_fade registered as edge-library families (class bodies AST-identical to R/families; rationale = the old docstring hypothesis; variants = first heat-map axis: tema_slope n 10/20/40, rsi2 th 5/10/15, first_bar_mom k 1/1.5/2, tod_drift off_min 0/15/30/60 x dir, the other four defaults only; tfs 1/5/15/30; roots NQ/ES/GC). Tester-match gate `engine/PORT2_VALIDATION.md` (`engine/port2_validate.py`): NQ 32 screen runs + 412 heat-map cells, ES 32 + 300, ALL 100 % identical (4.41 M trades, net diff 0). Tests `engine/tests/test_port2.py` (29). Smoke counts `engine/out/port2_smoke.jsonl` (48 smokes ok). No menu run, ledger untouched. Also fixed `tests/test_families.py::test_registry_loads_without_errors` (it checked the 4-tuple of a 5-tuple library family).
- 2026-10-02 12:30 ET, NEW_L2 author (EDGE_SPEC D) — `engine/families/l2ideas.py` (read its docstring: pre-registration + stage D recipe), `engine/tests/test_new_l2.py` (118 tests),
  counts-only smoke `engine/out/new_l2_smoke.log`. REGISTERED (NQ only, 5-tuples, C2 nulls run by run_menus): `bimb_follow_d1` (D1 = the L2 screen's bimb_follow class unchanged, tf 5,
  z {1.5, 2.0, 2.5}; the name has `_d1` because `bimb_follow` is the screen's own 4-tuple in book.py) and `flow_exhaust` (D5, tf 1 + 5, percentile {85, 90, 95}): 3 units x 96 cells
  (+ 192 C2 null cells each). STAGE D (D2 f_book / D3 x_book / D4 f_thin on orb, donchian, straddle, straddle_t_<HHMM>) is NOT in the registry (check_entry refuses an L2 option in an
  entry by design): `l2ideas.STAGE_D` (36 names, 2 DEAD: straddle_t_1800_fbook / _thin, no book row before the 18:00 reopen) + `variant_grid` (the base unit's grid, same cell ids,
  option on) + `variant_features` + `run_variant(name, tf, base_plateau=<pass True>)` -> runs/<name>-NQ-tf<tf>/ (+ -c2s1 / -c2s2) through run_menus' store + capped ledger; refused
  until the base passed the BUILD plateau. For one member cell: `library.run_member(base, ..., extra=l2ideas.option(name))`. KNOW: f_book / f_thin are read when the order is PLACED
  (a resting OCO pair is filtered leg by leg at its clock time -> usually ONE leg, no OCO); each stage D unit costs 3 x the base's cells (grid + 2 C2). No menu was run; ledger untouched.
- 2026-10-02 13:15 ET, NEW_TIME fix round after verify (`engine/families/timed.py`, `engine/tests/test_new_time.py`; LABELS, docs, two helpers and tests only: no
  trade of any cell changes; no menu was run before or after — ledger 0 cells, no runs/ store). (1) SECOND LOOK label on `straddle_t_0300 / _0930 / _1330` (notes AND
  rationale): with an ATR offset they are the old pilot's straddle-tf30 london / nyam / pm under a new name — pinned on the 10 smoke days, NQ + ES: trade for trade the ported
  `straddle` trades entered within 60 min; the old finalists' 2025-26 holdout jobs ran sess = all on NQ and ES (R / RE jobs.jsonl ho-straddle-tf30-*; GC never). The same
  three are a DUPLICATE of the ported `straddle` tf 30 for atr0p25 / atr0p5 / atr1: at most one of the two may be a member (dedupe at admission / stacking).
  (2) `straddle_t_1105` is now WEAK (t >= 3 on BUILD) like 00:00: EDGE_SPEC names no event for it (it is the old pilots' mid-session arm time). Decided before any number;
  lifting it needs an event written into EDGE_SPEC BEFORE the menus run. (3) Documented + tested: unfilled entries rest 55 min (not 60) at 02:00 and 08:30 (flat = at + 60,
  the Template cancels entries 5 min before flat; `timed.entry_life_min`); the coverage rule drops ALL day fires of a day with an empty clock hour (GC day after Thanksgiving,
  NQ / ES 2023-04-07, ...; evening fires still run); 18:00 = stale anchor / ATR, "follow the reopen gap", stress is the real gate; time-shuffle null shifts are one-sided at
  18:00 / 00:00 (0..+90) and 20:00 / 13:30 (-90..0); `timed.resolved(root, inputs)` writes out the offset a stored run really used (stored: off = <name>, off_mode 'menu',
  unused off_val); vwap_ema_x card caveats are in its notes. Tests: test_new_time.py 45 passed, full engine suite exit 0 (2 workers, 2 skips by design); 32 counts-only smokes ok; plan unchanged (36 units, 14,688 cells).
  OPEN for the orchestrator BEFORE RUN: (a) 20:00 ET is one hour after the Tokyo open on 37 % of BUILD calendar days (US winter): kept as EDGE_SPEC lists it, full strength —
  mark weak or move to 19:00 in winter only now, never after results; (b) `library.card` prints rationale / weak / penalty but NOT the notes: the SECOND-look labels of port1 /
  port2 / port3 reach run.json only (the three timed entries also carry it in the rationale); (c) ENGINE.md 1 still lists weak = "straddle_t 00:00, vwap_ema_x" (now also
  11:05); (d) all families = 38,592 of 40,000 cells before any stage-D unit; (e) RUN agent: confirm 1-vs-N worker identity at its real worker count on a short slice.
- 2026-10-02 14:10 ET, PORT GROUP 2 FIX (after verification; nothing run on the menu, ledger untouched) — READ `engine/PORT2_NOTES.md`: it lists the decisions the orchestrator owes BEFORE the BUILD run. Changed: `tod_drift` is now `weak: True` (no counterparty in its rationale: the old "control for pure clock effects"; t >= 3 on BUILD; one line to waive). `families/port2.py` now declares `SECOND_LOOK` (+ `second_look(name)`: tema_slope ES, ema_pullback, rsi2, first_bar_mom, tod_drift — from the old holdout job KEYS), `MIRROR_AXIS` (tod_drift `dir`), `can_trade(family, variant, tf, sess)` (cells with zero trades by construction) and the pre-declared `plateau_sets` / `tradable` splits. OPEN, orchestrator: tod_drift cannot pass the LITERAL plateau under its own hypothesis (long and short share one unit: ~50 % of cells at best) -> judge per direction, accept the foregone fail, or drop it (3,072 cells); penalty for the other second-look families is sealed to authors; library.card has no SECOND-look field. Class bodies untouched (trading-code hash 59b4af4d1e512352 = the hash of the code the first gate ran). Gate re-run CLEAN (`port2_validate.py --fresh`, 2 workers): 93 bundles, 776 runs + cells, 4,408,308 trades, ALL 100 % identical, ONE file hash on every row (the gate now aborts if a file changes under it) + every registered variant matched by a tester cell. `tests/test_port2.py` 39 tests incl. an INDEPENDENT first-signal oracle in all 7 sessions on NQ / ES / GC with atr / pts / pct stops (the paths no tester bundle covers) and tod_drift's 6-bar exit. 48 counts-only smokes re-run: same counts.
- 2026-10-02 14:55 ET, NEW_L2 author, VERIFY-ROUND FIXES (before any menu run; no ledger row, no runs/ store, no P&L seen) — `engine/families/l2ideas.py`
  (read its docstring), `engine/tests/test_new_l2.py` (132 tests), counts-only smoke `engine/out/new_l2_smoke.log` (script `engine/out/fix_new_l2/stage_d_smoke.py`),
  a pointer in ENGINE.md § 5. NOTHING of the D1 / D5 trading rules changed; `l2sim.py` / `score.py` / `library.py` / `run_menus.py` untouched.
  (1) STAGE D D2 / D4 ON A RESTING ENTRY (orb, straddle, straddle_t) now judged AT THE TRADE: the simulator runs the base's own bracket and every fill is kept or
  skipped by the filter's verdict at the 1-minute decision that began the fill's minute (= the L2 pilot's gate G1 on the base's trade list; `l2ideas.kept`). Before: read
  once at placement (40 % of f_book fills went into an opposing book, verdicts up to 178 min old, on a straddle it just picked a leg). Smoke, 10 days: 552 kept of 2,776
  resting fills, 0 against the filter at the fill minute, every kept trade is the base's own row. donchian (market entry) keeps the engine's rule (read at its decision).
  (2) D3 `x_book` NEEDS A FLIP: armed only once the 5-min mean has not opposed the trade (at its entry or since), then 2 opposed usable minutes. Before: any 2 opposed
  minutes (58 % of trades were entered already opposed and most were closed 2 minutes later).
  (3) Both live in a mixin `l2ideas.StageD` in front of the base's registered class (`l2ideas.stage_class(base)` = `families.l2ideas.D_<base>`): the engine's options on the
  BASE class are still the old semantics. Stage D = `l2ideas.run_variant(name, tf)` / `variant_table(name, tf, sess)` / `run_member(...)`; NEVER
  `library.run_member(base, ..., extra={"f_book": "on"})`.
  (4) SEAL: `run_variant` reads the base unit's own BUILD store and refuses unless a session passed the plateau (`base_sessions`); the variant's run.json carries
  `base_pass_sessions` and `variant_table` / `run_member` refuse any other session; a PICK member run needs the variant's OWN BUILD plateau of that session. `variants=`
  is gone: a variant always runs the base's WHOLE grid (3 x the base's cells with the two C2 nulls; `nulls=False` first is the cap-friendly order). Meta has `l2: True`.
  (5) LABELS (EDGE_SPEC rule 3), in the notes AND in brackets after the rationale (a card prints the rationale): `bimb_follow_d1` = WEAK PRIOR + SECOND LOOK (BUILD + PICK:
  the L2 screen ran and picked this exact cell with 2024 in view); `flow_exhaust` = WEAK PRIOR + ADJACENT TO A REFUTED PROGRAM; D2 on orb / donchian / straddle /
  straddle_t 03:00, 09:30, 13:30 = SECOND LOOK (the screen's gate G1). `weak: True` on D1 and D5 was MY call (it only raises the admission bar to t >= 3 on BUILD):
  ORCHESTRATOR, take it back in `l2ideas.FAMILIES` before admission if you disagree.
  (6) The DEAD list is gone (the 18:00 filters can trade from 18:05 / 18:09 on; on the smoke days 4 and 0 trades).
  Tests: test_new_l2.py 132 passed; full engine suite 1,295 passed, 2 skipped by design (2 workers). 9 scratch mutations of the stage D rules each caught.
  Smokes ok (D1 tf 5, D5 tf 1 / 5, 36 variants + 12 bases, 1- vs 2-worker parity, C2 runs). No menu run.
  OPEN: (a) RUN agent: `L2_TEST_WORKERS=8 pytest tests/test_new_l2.py -k identical_trades` before the menus (shown at 1 vs 2 only). (b) engine owner: the C2 null draws
  donors from all 825 in-sample sessions, 2024 included (score.C2Features) — no PICK price or P&L, but not "BUILD only". (c) the entry filters keep few trades (about a
  fifth of the resting fills on the smoke days): the 100-trade bar will bind for straddle_t variants; `straddle_t_1800_thin` had 0. (d) x_book still closes most trades
  on the smoke days (now after a real flip): the 5-min mean changes sign often — that is the rule as EDGE_SPEC states it. (e) cap: 38,592 of 40,000 cells are planned
  before any stage D unit (orb 96 / donchian 128 / straddle_t 160 cells per tf, x 3 with nulls). (f) limits of the resting filter are listed in the docstring (no
  decision at the fill's minute = skipped; the pull / re-place latency at a minute start is not modelled, also not by the stress; `oco` / `both_sides` on a kept row
  are the base bracket's = conservative for Apex). (g) no pass criterion "variant vs base" is pre-registered: a variant is a candidate like any other, one rule more
  complex than its base (ties go to the base).
- 2026-10-02 14:58 ET, RUN AGENT — PLAN, WRITTEN BEFORE ANY MENU RUN (ledger.csv does not exist, no runs/ store, no P&L seen). Registry: 32 library
  families, `families.ERRORS` empty; gate reports carry the hashes of the code on disk (l2sim 67d9d66a, l2ref 51f18fb1, port1 574e9c7b, port2 e78c6a29,
  port3 9b5667eb). Base plan = 279 units, 37,824 cells + 12 C1 pools x 64 = 38,592 of 40,000 -> 1,408 cells are left for stage D.
  ORDER (fixed now): NQ first = C1 pools tf 1/5/15/30 -> straddle_t 18:00, 20:00, 00:00, 02:00, 03:00, 08:30, 09:30, 11:05, 13:30 (+ time-shuffle, same pass)
  -> ported: orb, straddle, donchian, squeeze, ib, lon_break, gap, ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2, first_bar_mom, tod_drift,
  mid_fade, vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev (tf 1, 5, 15, 30 each) -> vwap_ema_x -> bimb_follow_d1, flow_exhaust (+ C2 s1, s2)
  -> STAGE D (NQ only) -> ES -> GC (same family order; the seven low-prior families run LAST within ES and GC).
  STAGE D RULE (mechanical, fixed now): the 36 names of `l2ideas.STAGE_D` (D2 fbook / D3 xbook / D4 thin on orb, straddle, donchian at tf 1/5/15/30 and on
  the nine straddle_t at tf 30). A (name, tf) is run only if `l2ideas.base_sessions(name, tf)` is not empty (the base unit passed the BUILD plateau in
  >= 1 session: `library.plateau`, the seal is in the code). Step 1 = the variant GRIDS alone (`nulls=False`, N cells each), in the order: bases
  straddle_t_1800 ... _1330, orb, straddle, donchian; tf 1, 5, 15, 30; options fbook, xbook, thin. Step 2 = the two C2 grid nulls (2 N) ONLY for a
  variant whose OWN BUILD plateau passes in >= 1 of its base-pass sessions (`l2ideas.variant_table` -> `library.plateau`), same order.
  D2 / D3 "on any member" for non-breakout families is NOT run as a menu (it would be > 100,000 cells): it is left to the Admit stage as member runs
  (`l2ideas.run_member`, counted as runs, cap 2,000).
  CAP RULE (fixed now): stage D may use 1,408 cells + what the cuts free. If stage D needs more than 1,408, ES / GC units are cut, GC before ES, in the
  order mid_fade, rsi2, tema_slope, ema_ribbon, supertrend, pinbar, gap (GC of all seven first, then ES of all seven), only as many as needed (128 / 384 /
  384 / 128 / 128 / 384 / 256 cells per root; 3,584 at most). If stage D still does not fit after all 14 cuts (budget 4,992), it runs in the order above
  until the next unit does not fit and the rest is listed as NOT RUN (cap) — nothing is dropped silently, nothing is chosen by a result.
  NOT DECIDED BY ME (left as registered = literal EDGE_SPEC): tod_drift / ib / gap are judged over all cells of the unit (PORT2_NOTES decision 1, option A);
  weak / penalty flags as registered; 20:00 kept at 20:00 all year.
- QUEUED (user 2026-10-02 ~13:50 ET, do NOT restart the running workflow): APEX LEGACY 300K PA-optimised build, after stage 1:
  (1) one-direction "close-confirm" variants of the two-sided families (straddle_t, orb, squeeze nr7/inside, ib break, lon_break):
  enter at market after a tf-bar CLOSES beyond the level, never two resting sides; every cell must have a target with stop <= 5x target;
  (2) Apex stack search on admitted one-direction members with apex300.py (fresh $300,000, conservative consistency, MAE $2,250 cut,
  half size 170 micros until +$7,600, intraday trail): objective E[$ to trader 40/60 d], P(payout), P(bust before 1st payout);
  five accounts = five copies, same direction; simple enough to place by hand (clock-time entries, <= 2 trades/day).
- 2026-10-03 08:55 ET: stage 1 workflow (wf_865c687c-462) finished infra + 5 family groups + verification; RUN died on a network outage after 77 BUILD + 13 null runs (old exit convention, never analysed → void). ORCHESTRATOR DECISIONS written to EDGE_SPEC (flat-by-4pm exits, mirror units, weak flags, nulls outside the cap, per-year reporting). Relaunched lean as wf_6e638dfd-361: prep → run (sonnet) → admit → check.
- 2026-10-03 10:10 ET, ENGINE OWNER — ORCHESTRATOR DECISIONS 2026-10-03 APPLIED, P&L-blind (no net / win rate of any run was printed or
  opened; the 90 old stores were moved unread). READ `ENGINE.md` § 0a FIRST (it lists every change); tests `engine/tests/test_edge_hold.py`
  (26) + `engine/tests/test_edge_decisions.py` (13); work files + logs in `out/engine_owner/`.
  (1) EXIT CONVENTION = Template input **`hold_to = "day"`** (not `hold`: vwap_flip owns that input name): stop / target / bar exit, else
  flat 15:58 ET of the trade date (13:13 on an equity half day; GC keeps 15:58), never at the session end; entries unchanged (session
  window, not in its last 5 min, nor in the 5 min before the day's flatten). Class default stays `"session"` = the tester's rule.
  `run_menus` runs EVERY unit and null with it: a Template cell = SEVEN single-session instances (asia, london, pre, nyam, mid, pm, eve;
  sessions a family never trades are left out), a time-fired cell = one; an evening entry is ONE segment 18:00 → 15:58 (may span 00:00,
  never 17:00). straddle_t: entry window and the 60-min cancel as before (55 min at 02:00 / 08:30), the filled side holds to 15:58.
  `library.run_member` / `l2ideas.run_member` run the member's one session with it. PROOF (counts only, 10 smoke days, all 32 families,
  NQ tf 1 / 5 / 30, ES tf 5 / 15 / 30, GC tf 5 / 30: `out/engine_owner/check_*.log`): old-rule single-session instances == the `sess=all`
  instance; under the new rule every entry is an old-rule entry and a trade the old rule closed by stop / target / bars is identical in
  every field — only the clock exits at a session end changed (stated exceptions: half-day last 5 minutes / 13:13 vs 13:15; an evening
  whose DAY has an empty clock hour is skipped).
  GATES re-run on the final code (l2sim 46119270, l2ref 51f18fb1 unchanged), all with the class default hold_to = session:
  `edge_validate.py` ALL GATES PASS; `port1_gate.py` PASS (56 screen bundles, 9 heat-maps); `port2_validate.py --fresh` ALL GATES PASS;
  `port3_validate.py` ALL GATES PASS (reports regenerated; the pre-change ones are in `out/engine_owner/*.pre-hold`). Full engine suite:
  1,334 passed, 2 skipped by design (3 workers, 10 min). VOID: `runs_void/` (90 stores, old ledger, old logs, README); `ledger.csv`
  reset (0 rows, new column `null_cells`); `runs/` is empty.
  (2)–(6) `families/__init__.py` overlay (no author module edited): WEAK += ema_ribbon, tema_slope, ema_pullback, supertrend (straddle_t
  00:00 / 11:05, tod_drift, vwap_ema_x were weak already; bimb_follow_d1 / flow_exhaust keep their author's weak flag); MIRROR = tod_drift
  dir, ib mode, gap mode → `library.plateau_units` judges one unit per axis value (36 of the 279 run units split); PENALTY = first_bar_mom
  (all sessions) + donchian in pm only (`families.penalty_for`); second-look / notes / mirror / penalty on the card (`library.member_meta`,
  `library.card`); 20:00 ET all-year note on straddle_t_2000. `library.plateau`: identical trade lists once, dead cells out, central cell,
  share verdicts 60 / 70 / 80 % overall / by stop type / per reward ratio. Ledger: null cells = kind `null`, column `null_cells`, NOT capped.
  (7) `library.metrics / per_year / sized / report_md / unit_report_md` (`python library.py report <key> --sess pm`): trades, net, win
  rate, PF, max drawdown, Sharpe (daily, annualised), avg trade, worst open loss per year (2021*, 2022, 2023; 2024 for PICK) then combined,
  at 1 contract and sized to about $1,000 risk in micros.
  PLAN (`run_menus.py plan`): 279 run units, **28,608 candidate cells** of 40,000 (11,392 left) + **9,984 null cells** (9,216 time-shuffle /
  C2 + 12 C1 pools × 64), uncapped. Smokes (10 days, counts only) ok: donchian NQ tf 5, straddle_t_1800 ES tf 30, ib GC tf 5
  (`out/engine_owner/smoke_*.json`).
  FOR THE RUN AGENT: (a) pass time ≈ 1.7–2.0 × the old one per Template unit (7 instances; `out/engine_owner/time_hold.py`), time-fired
  units unchanged → budget ~2 × the old BUILD estimate; (b) `out/run_agent/staged.py` still has BASE_PLAN = 38,592 / BUDGET 4,992 and the
  ES / GC cut list: with nulls uncapped the base plan is 28,608 and ALL 36 stage D grids (8,160 cells at most) fit without any cut —
  fix the constants before `driver.py all`; (c) old logs are gone from `out/` (moved to runs_void/), `runs/` is empty.
  FOR THE ADMIT STAGE: judge with `library.judge(u, sess)` (mirror units, dead / duplicate handling inside), build member dicts with
  `library.member_meta(family, sess, variant)`, stage D penalty via `families.penalty_for(base, sess)`.
  OPEN / DECIDED BY THE ENGINE OWNER BEFORE ANY VALID RUN (orchestrator may overrule before the run starts, never after): "dead" is read
  from entry counts (a variant with no trade in the session in any of its 32 exit cells), not from per-family predicates; GC flattens
  15:58 on equity half days; a held evening needs the day's coverage; `penalty` for donchian is pm-only and for first_bar_mom all sessions.
- 2026-10-03 10:30 ET, RUN AGENT (wf_6e638dfd-361, sonnet) — PLAN, WRITTEN BEFORE THE FIRST VALID RUN (ledger 0 rows, runs/ empty, no P&L seen).
  (1) Tests: full engine suite 1,334 passed + 2 skipped by design (3 workers, 20 min wall; log out/run_agent/pytest_full.log), 0 failures -> no family excluded;
  `L2_TEST_WORKERS=8 pytest tests/test_new_l2.py -k identical_trades` passed (8-worker identity of the D1 / D5 runs); `python -m families`: 32 library families, 0 errors.
  (2) Driver = out/run_agent/driver.py `all` (unchanged order: NQ C1 pools tf 1/5/15/30 -> straddle_t x 9 -> 20 ported families x tf 1/5/15/30 -> vwap_ema_x -> bimb_follow_d1 / flow_exhaust
  (+ C2) -> STAGE D (NQ) -> ES -> GC), `hold_to = day` inside run_menus, 8 workers, each unit one subprocess, idempotent (store + ledger row), log out/run_agent/driver.jsonl.
  (3) staged.py constants fixed (old copy: staged.py.pre-2026-10-03): BASE_PLAN 28,608 (candidate cells only), BUDGET = 40,000 - 28,608 = 11,392; the C2 null passes are uncapped
  (no budget test). CAP RULE: all 36 stage D grids (<= 8,160 cells) fit, so NO ES / GC cut is made (cuts.json stays absent; the driver's cut list is empty).
  STAGE D RULE unchanged: a (name, tf) runs only if the base unit passed `library.plateau` in >= 1 session (the seal in l2ideas.base_sessions); the C2 nulls only for a variant whose own plateau passes.
  (4) sanity.py now also totals null_cells. No selection and no P&L is read by any run-agent script; only plateau pass flags (stage D seal) and counts.
- SECOND-CHANCE LIST (user 2026-10-03: "retest any idea ... maybe we can save an old idea") — processed in the DEEPEN round, each a counted attempt:
  (1) the 14 L2 screen families re-read as trade-time filters / regime markers (they were judged once, as direction signals, at one default);
  (2) the flow-and-book AGREE marker at every strategy's trade time (not only 09:30) + its mirror (fade on disagree days);
  (3) NQ930 live settings (offset 5, stop 5, target 15) as its own heat map around those values in the tick engine (its only backtest is a TV 15 s export);
  (4) afternoon channel breakout and 9:30 opening momentum (failed on 2025-26) with the ADX-trend / RSI add-ons;
  (5) the old funded picks UNCAPPED (the daily take caps cut their edge);
  (6) removed desk algos NQ10AM and the NQ open long/short idea (the latter never fired live: date-gate bug) — fair first test in the engine;
  (7) earlier Onyx OFB research (FVG, London fade, resting-liquidity levels; July-Aug) — read the burned-data ledger first, revisit only what was shelved for data reasons.
- 2026-10-03 ~20:00 ET AUTOPILOT: user mandate recorded in EDGE_SPEC (AUTOPILOT MANDATE + DONE DEFINITION). On each workflow
  completion the orchestrator launches the next stage itself. Assumption: the five Apex 300K PAs are fresh at $300,000.
- 2026-10-03 21:10 ET, RUN AGENT interim — NQ BASE + STAGE D DONE (driver.py all, 8 workers; log out/run_agent/driver.jsonl, out/run_menus.log; no P&L read).
  NQ base: 4 C1 pools (tf 1/5/15/30) + 9 straddle_t (+9 time-shuffle nulls) + 20 ported x tf 1/5/15/30 + vwap_ema_x x3 + bimb_follow_d1 + flow_exhaust x2 (+ C2 s1 s2 each):
  96 build stores = 9,888 candidate cells, 19 null stores = 3,712 null cells, 0 failed units; wall 10:29 -> 18:09 ET (7 h 40 min).
  Sanity (counts only, out/run_agent/run_table.csv): sessions 573 of the calendar, 568 used (5 skipped for data gaps: 2021-12-01, 2022-06-21, 2022-08-05, 2022-09-06, 2023-04-07;
  the 18:00 / 20:00 straddle_t units also skip the 2022-10-11 evening), skipped_by_error 0 everywhere, both-sides evidence matches the declaration on every store, 0 trades outside a session,
  0 unrealistic winners; the only cells without a trade: donchian-NQ-tf30 (64 = n 40 / 60 cannot warm up at tf 30). Remark (counts): orb tf15 and tf30 hold the identical trade count (264,032).
  STAGE D (staged.py): 63 (name, tf) pairs; 45 variant grids run (base unit passed library.plateau in >= 1 session), 18 not run (base passed no session); 5,376 candidate cells
  (cap left 11,392 -> no ES / GC cut, cuts.json says freed 0); C2 nulls run for the 35 variants whose own BUILD plateau passed in >= 1 base-pass session (10 not run, 70 null passes).
  Ledger now: 15,104 candidate cells of 40,000 (24,896 left), 11,840 null cells (uncapped), 0 runs, 0 wfs. NEXT: ES base, then GC base (driver.py all continues).

## VIDEO IDEAS QUEUE (2026-10-03 night, from 11 user-sent videos; notes in videos/<id>.md; vault `video-batch-2026-10-03-takeaways`)
Candidates for NEW-IDEA ROUND 1 (each: rationale first, full menu, nulls, three periods — nothing here is verified):
  V1 vwap_trend_pullback NQ (wm4A6qo0g3I): VWAP from 09:30; 15-min trend = close>VWAP & VWAP rising & +0.1% last hour; enter first counter candle
     (5m and 15m trigger variants); window 10:30-15:30; flat 15:55; menu exits + his cell (stop 80 / tgt 40 long, 50 short); max 4/day, stop after 2 losses.
  V2 failed_second_push at prior value-area low/high, 09:30-11:00, day trend = value rising/falling; price-only first, then delta-flip trigger (footprint from ticks).
  V3 orb_0930_1000 long-only, close-confirm, exit 15:30 (also Apex 300K one-direction build) + side test: sign(prior close→10:00) vs 15:30→16:00.
  V4 vwap_stop_and_flip 1-min close vs 09:30-anchored VWAP (check overlap with vwap_ema cross; drop if gross/trade < costs).
  V5 fade_to_0929_price after the first open move (define exactly; compare with NQ930 tests).
  V6 volume_spike_breakout family; and TIME EXIT (hold N bars + hard stop) as a DEEPEN-toolbox exit.
  Low: anchored-VWAP first touch (18:00 / 09:30), stop 10 ticks, target 12.
Funded sizing sim to add at the stack stage: risk = 20% of live cushion vs flat $1,000.
- 2026-10-04 04:30 ET, RUN AGENT — BUILD COMPLETE (2021-09-22..2023-12-31, hold_to = day, 8 workers, wall 2026-10-03 10:29 -> 2026-10-04 04:27 ET = 18 h; no P&L read, no PICK / EXAM touched).
  Result (run_menus.py status): 279 / 279 run units done, 0 pending, 0 failed (no `*_error` ledger row); 439 stores in runs/ (324 build + 115 null, 654 MB).
  LEDGER: 33,984 candidate cells of 40,000 (6,016 left) = 28,608 base plan (NQ 9,728 + ES 9,440 + GC 9,440) + 5,376 stage D grids; 18,112 null cells run (uncapped:
  9,984 planned base nulls + 8,128 stage D C2); 0 runs, 0 walk-forwards used. NO CUT was needed (stage D 5,376 <= 11,392; out/run_agent/cuts.json says freed 0).
  Wall per root: NQ base 7 h 40 (14:29-18:09 UTC), stage D grids 2 h 19, stage D C2 nulls 4 h 40, ES 4 h 13, GC 3 h 05. Once a pass ran with 5 workers (auto_workers saw another busy python process); never above 8.
  STAGE D (rule unchanged): 63 (name, tf) pairs, 45 grids run, 18 not run because the base unit passed library.plateau in no session (straddle_t 2000 / 0000 / 0200 / 0930 / 1330 x3 options = 15, donchian tf1 x3 = 3);
  C2 nulls for the 35 variants whose own plateau passed in >= 1 base-pass session; 10 grids have no C2 (own plateau passed nowhere). Detail: out/run_agent/staged.json.
  SANITY (counts only; out/run_agent/run_table.csv, python out/run_agent/sanity.py): calendar 573 sessions (GC 572); used NQ 568 / ES 571 / GC 565 (NQ: 5 data-gap sessions 2021-12-01, 2022-06-21, 2022-08-05, 2022-09-06, 2023-04-07;
  the 18:00 / 20:00 straddle_t stores also lose the 2022-10-11 evening; ES / GC: their own gaps, listed in each run.json coverage); skipped_by_error = 0 in every store; the both-sides declaration matches the simulator's
  evidence in every store (no declared-False family with an opposite-side overlap); 0 trades outside a session; 0 unrealistic winners; every store period build, range 2021-09-22..2023-12-31.
  Cells without a trade: donchian n 40 / 60 at NQ tf 30 (64 cells per store: base, the three stage D options, their C2 nulls) and the same on ES / GC tf 30 base (can't warm up: by construction, `plateau` leaves them out as dead).
  Remarks (counts): orb tf 15 and tf 30 hold the identical trade count on NQ (264,032) - a possible duplicate unit pair for the Admit stage.
  FOR THE ADMIT STAGE: nothing was judged here. Read with library.judge(u, sess) / library.plateau_units / library.session_table on runs/<key>; stage D via l2ideas.variant_table; null bars via library.best_of_nulls / unit_null_replicates.
- 2026-10-04 04:33 ET, ADMISSION ANALYST — PLAN, WRITTEN BEFORE ANY BUILD NUMBER WAS OPENED (no table.csv / cells.npz read yet; members/ empty; nothing below may change after a number is seen).
  A. JUDGED UNIT = store x session x mirror value (`library.judge`; stage D: `l2ideas.variant_table`, base-pass sessions only). Binding plateau = `library.plateau` (median net > 0 and >= 60 % of judged cells > 0; dead cells out, identical trade lists once). A unit at exactly 60.0 % is flagged.
  B. BUILD PASSER (the ONLY units whose 2024 is read) = ALL of: (1) plateau pass; (2) the CENTRAL cell beats its matched control: Template family -> C1 (`library.c1_draws`, pool `c1-<root>-tf<tf>`, same exit cell, seeds 1 + 2 pooled, K 200: lift > 0 and nothing unmatched); time-fired -> time-shuffle null (net - mean of the same cell at shift seeds 1, 2 > 0); Level 2 -> also C2 (net - mean of the same cell at C2 seeds 1, 2 > 0); (3) central-cell t > the best-of-nulls bar of its batch (`library.best_of_nulls`, stat t, 95th pct of each null replicate's best cell). Batches: C1 per root (4 tf pools x 2 seeds x 7 sessions); time-shuffle per root (9 stores x 2 seeds; thin, flagged); C2 = all C2 stores of the NQ L2 families / of the stage D variants (seed x base-pass session). An L2 unit must clear its C1-or-shift bar AND its C2 bar. (4) WEAK: central-cell t >= 3. A unit failing (2)-(4) can never be admitted, so its PICK stays unread (kept clean for the DEEPEN round).
  C. PICK (2024): the passer's WHOLE menu, run for the passing session only (one instance per passing session, hold_to = day, the same instance run_menus used; a mirror unit: the passing value's variants) + the matched controls on 2024 (C1 pool of that root x tf x session; time-shuffle; C2 seeds 1, 2). Every read is logged in out/admit/pick_reads.csv. PICK verdict = `library.plateau` on the 2024 table.
  D. SURVIVING SET = cells with net > 0 on BUILD and on PICK whose net under 2 ticks + 250 ms is > 0 on BUILD and on PICK (stress is run only for cells positive in both). DEFAULT variant = the BUILD central cell if it is in the set, else the surviving cell whose BUILD net is closest to the BUILD median (card: "default moved").
  E. ADMIT = BUILD passer + PICK plateau pass + surviving set not empty + default variant: beats its controls on PICK, >= 100 trades (BUILD + PICK), worst per-trade open loss fits $2,000 at >= 1 micro. A PENALTY unit (first_bar_mom; donchian pm) that passes all numbers is NOT admitted by this stage: the spec also asks for "a reason why the 2025-26 failure was noise", which cannot be written without evidence -> near-miss "penalty: reason owed". Everything that passes the plateau but fails a later test -> out/near_misses.md with the failed test.
  F. SAME TRADES = ONE MEMBER: straddle_t 03:00 / 09:30 / 13:30 (ATR offsets) vs `straddle` tf 30 london / nyam / pm; orb tf 15 vs tf 30 where trade signatures are identical; a stage D variant vs its base. If both pass: lower complexity count, then family order. A stage D variant replaces its base only if it passes every test itself AND its paired difference vs the base is > 0 on BUILD and PICK and above the shuffled-book difference; else the base stands (ties go to the simpler).
  G. LEVEL 2 FILTER / EXIT VALUE (stage D, base-pass sessions): per cell d = net(variant) - net(base) on the identical calendar (a filter's d = minus the net of the trades it skipped); null d = net(C2 seed) - net(base). Reported: median d, share of cells d > 0, share of cells d > mean null d, paired t of the daily difference at the base's central cell (real and each null seed). "Added" = median d > 0, >= 60 % of cells d > 0 AND >= 60 % of cells above the shuffled-book d. Two null seeds only: stated.
  H. ACCOUNTING: PICK and stress passes re-run pre-registered cells that already count as candidates; they add no candidate -> ledger kind `null` with control `pick` / `stress` / `c1` (tracked, uncapped, reported apart from the 33,984 candidate cells). Orchestrator may re-book them; flagged in the summary.
  I. MULTIPLE TESTING: the plateau rule's own false-pass rate = share of NULL unit-sessions (C1 pool seed x session over the 32 exits; time-shuffle seed; C2 seed) that pass `library.plateau`; printed next to the count of judged units and passers, with the expected number of chance passes.
  J. Loss-day overlap of admitted members = share of member i's losing days that are losing days of member j (default variants; PICK and BUILD + PICK). No tuning, no cell chosen by its result outside these rules, EXAM untouched. Scripts + outputs: out/admit/.
- 2026-10-04 04:46 ET, ADMISSION ANALYST — DONE (plan of 04:33 ET followed; EXAM untouched; nothing tuned). READ `out/library_summary.md` (104 lines), `out/near_misses.md`, `members/*/card.md`.
  BUILD: 1,623 judged units (NQ 528 + 81 stage D, ES 507, GC 507) -> 213 pass the heat map (NQ 128, ES 26, GC 20, stage D 39) -> 5 BUILD passers (plateau + matched control + central t above the best-of-nulls bar [+ WEAK t >= 3]):
  orb-NQ-tf1|pre, donchian-NQ-tf30|nyam, donchian-NQ-tf30|pm (penalty), donchian-ES-tf30|pm (penalty), first_bar_mom-GC-tf5|pm (penalty). Bars (t): C1 NQ 2.02 / ES 1.30 / GC 1.24; time-shuffle NQ 2.62 / ES 2.00 / GC 1.64 (thin: 18); C2 2.65; stage D C2 3.61.
  PICK (2024) was opened ONLY for those 5 (whole menu, passing session only) + their C1 pools: `out/admit/pick_reads.csv` (19 rows). 2024 heat map: orb pre 64 % PASS, donchian nyam 90 % PASS, first_bar_mom GC pm 64 % PASS, donchian pm NQ 44 % fail, donchian pm ES 27 % fail.
  ADMITTED: `members/orb_NQ_tf1_pre` (clean: all library.admission tests pass; default `or_min5_atr1p5-r2`; surviving set 49 of 96) and `members/donchian_NQ_tf30_nyam` (FLAGGED: BUILD central cell fails the stressed 2024, default moved to `n10_pct0p2-r2` whose own BUILD t 1.65 < bar 2.02 -> library.admission on it says reject; admitted by plan rule D / E; beats only 86 % / 76 % of random draws; all profit from shorts; surviving set 43 of 64). REJECTED: `members/_rejected/first_bar_mom_GC_tf5_pm` (15 trades; penalty).
  LEVEL 2: no L2 family and no stage D variant is a BUILD passer; paired vs base the book filter / thin filter / book exit lowered the median variant by $11,683 / $10,445 / $8,835 and beat the shuffled book in 0 of 81 unit-sessions (`out/admit/stage_d_paired.csv`).
  NULL PASS RATES of the heat-map rule itself: NQ C1 6 of 56, NQ time-shuffle 5 of 18, ES / GC 0; both gates: 0 of 168 C1 null units (`out/admit/null_passrate.json`, `null_replicates.json`).
  LEDGER: candidate cells unchanged 33,984 of 40,000; +1,144 validation cells booked as kind null (stages null_pick 896, null_stress 248; stores in `runs_admit/`); 12 member runs of 2,000. orb tf 15 vs tf 30: 72 of 96 cells are identical trade lists on NQ, ES and GC (every fixed and percent stop).
  SCRIPTS (out/admit/): judge_build.py -> build_units.csv, build_plateaus.json, null_bars.json; run_admit.py (check = 10-day identity with the BUILD stores: 0 cells differ; run); judge_pick.py -> pick_judgement.json; admit_members.py -> admission.json + member folders (a re-run rewrites card.md WITHOUT the two hand-added appendices, kept in out/admit/card_appendix_*.md); finalize.py -> the two reports.
  OPEN for the checker / orchestrator: (1) confirm or demote donchian_NQ_tf30_nyam; (2) orb_NQ_tf1_pre: 63 % of its profit is made by trades that open and close within 2 s in the 08:30 data minute (fill realism), avg trade $35, stress halves it; (3) booking of the 1,144 PICK / stress cells; (4) 208 heat-map passers keep an unread 2024 for the DEEPEN round (closest: ib-NQ-tf5 mid break, t 1.99 vs 2.02, 100 % of variants positive).

- 2026-10-04 05:10 ET, ORCHESTRATOR — STAGE 1 CLOSED. Checker verdict applied: library = 1 member (orb_NQ_tf1_pre; thin: t 2.32 vs bar 2.02;
  63 % of profit from <= 2-second trades in the 08:30 minute; stress halves it; avg trade $35). donchian_NQ_tf30_nyam demoted (2024 read).
  No Level 2 filter / exit admitted (worse than the same strategy without it). Straddle clock times: none beats the random-minute bar.
  VWAP-EMA: no pass. 208 near-misses (205 with unread 2024) -> DEEPEN. Candidate cells booked: 34,808 of 40,000. NEXT: stage 2.

- 2026-10-04 05:20 ET, DEEPEN ANALYST — STAGE 2a DONE (EDGE_SPEC "STAGE 2a" followed; EXAM untouched; nothing tuned). READ `out/deepen_summary.md` (60 lines), `IDEAS.md`, `ideas/*/notes.md`.
  UNITS: 58 near-misses (fail == bar, not WEAK, no penalty, 2024 unread; NQ 48 / ES 7 / GC 3) x 8 sides = 464 side tables on stored BUILD trades. Labels use daily bars through the prior day (`out/deepen/test_labels.py` passes).
  PASS COUNTS of 464: (a) 307, (b) 295, (c) 306, (d) 23, (e) 38, all five 3. PLACEBO (same procedure on 58 random-entry units, 464 sides): (a) 402, (b) 53, (c) 205, (d) 2, (e) 23, all five 0.
  BUILD PASSERS: donchian-NQ-tf5|nyam vol_lo (quiet days; exact day split); rsi2-NQ-tf30|eve long and squeeze-NQ-tf30|pm long (stored split = approximate -> exact re-run with dir = long: rsi2 passes, squeeze fails).
  2024 OPENED for 2 sides only (`out/deepen/pick_reads.csv`): donchian vol_lo table PASSES (82 % positive) but its BUILD central variant loses $4,715 and the rule-moved default fails the bar and the random control -> NOT ADMITTED (same case as the stage-1 demotion); rsi2 long table FAILS (19 % positive).
  ADMITTED: none. Library = 1 member (orb_NQ_tf1_pre). Record of the donchian side: `members/_rejected/donchian_NQ_tf5_nyam_vol_lo/` (84-variant surviving set; only 17 beat random entries in both periods).
  OPEN FOR THE ORCHESTRATOR: (1) straddle_t_0830-NQ news_only passes (b)-(e) (t 3.59 vs 2.62) but has 71 BUILD trades; (a) was counted on BUILD alone (stricter than BUILD + 2024); 2024 NOT opened; same idea as the member. (2) test (e) for long / short is weak with the 2 seeds on disk (22 of 116 placebo sides pass it); used a 30-seed long-only pool for the one exact side. (3) "quiet day" recurs among the closest misses: a lead only.
  DEVIATIONS: news dates from `research/prop-portfolio/2026-09-29/news_days.csv` (the engine holds none; checked, all 3 types kept); first 28 / 20 sessions unlabelled (daily bars start 2021-09-22); roll-day gap not counted in ADX; moved default not admitted (checker precedent).
  MEMBER INFO (orb_NQ_tf1_pre default, BUILD + 2024): news days 102 trades $13,022 vs other days 717 trades $15,777 (2024: $856 vs $11,581); short $22,352 vs long $6,447.
  LEDGER: +608 candidate cells (192 exact BUILD re-runs, 224 PICK, 192 stress) -> 35,416 of 40,000 (ledger.csv itself shows 34,592: the 824 stage-1 cells were re-booked on paper only); +188 control cells; +8 member runs. Stores: `runs_deepen/`. Scripts: `out/deepen/` (labels.py, judge_sides.py, run_deepen.py, judge_exact_t4.py, judge_pick_sides.py, admit_sides.py, write_records.py).
  NOW SPENT ON 2024 (information only from here): donchian-NQ-tf5|nyam, rsi2-NQ-tf30|eve. IDEAS.md: 113 ideas, 1 admitted, 112 open, 0 shelved (no idea has used its 4 deepen rounds).

- 2026-10-04 05:24 ET, DEEPEN ANALYST — ORCHESTRATOR RULING APPLIED: 2024 opened for straddle_t_0830-NQ-tf30|pre news_only (test (a) counts BUILD + 2024). Read logged in `out/deepen/pick_reads.csv`.
  2024 table (news days): 63.8 % of 160 variants positive, median $1,448 -> passes at 60 % only. Central variant `offatr0p25_pct0p1-r2`: 71 + 31 = 102 trades; 2021* -$46 · 2022 $7,896 · 2023 $5,101 · 2024 -$1,129.
  Stress (2 ticks + 250 ms): BUILD $12,951 -> $11,476; 2024 -$1,129 -> -$2,349. Surviving set 86 of 160, without the central variant; no moved default (ruling).
  VERDICT: NOT ADMITTED -> `members/_rejected/straddle_t_0830_NQ_tf30_pre_news_only/`. Library = 1 member. Same idea as orb_NQ_tf1_pre. The random-minute control was not run on 2024 (menu only, as ruled).
  LEDGER: +354 candidate cells (160 on 2024, 194 stress) -> 35,770 of 40,000; +4 member runs. Updated: `out/deepen_summary.md` (sections 4-6, 8), `IDEAS.md`, `ideas/straddle_t_0830_NQ/notes.md`. Scripts: `out/deepen/judge_pick_0830.py`, `admit_0830.py`.

- 2026-10-04 05:55 ET, ORCHESTRATOR — STAGE 2a CLOSED: no new member (464 side tables; 3 passed BUILD; donchian NQ tf5 nyam quiet-days and
  rsi2 NQ tf30 eve long failed 2024; squeeze failed the exact re-run). Ruling: 2024 opened for straddle 08:30 NQ news-only (rule (a) counts
  BUILD + 2024) -> NOT admitted (central variant -$1,129 in 2024; table 63.8 %). Library = 1 member. Candidate cells 35,770.
  STAGE 2b LAUNCHED (workflow wf_894dcbcb-9fc): N1-N7 new families (EDGE_SPEC "STAGE 2b"), cap 50,000, code -> run -> admit -> check.
  No checker was run on stage 2a (nothing admitted). Weekly tokens 70 % at 05:20 ET.

- 2026-10-04 06:20 ET, ENGINE CODER (stage 2b, P&L-blind) — ROUND 1 FAMILIES BUILT in `engine/families/round1.py`: N1 vwap_trend_pull,
  N2 va_reclaim, N3 orb_confirm (MIRROR `dir`: long-only / short-only units), N4 late_mom, N5 open_fade, N6 vol_spike_break, N7
  straddle_tight_0830 / _0930 / _1000 = 9 registry entries, NQ / ES / GC, hold_to day. How each written rule is read: the module
  docstring + ENGINE.md § 13 (day limits = per session instance; N1 "first" = first candle of a pullback; N5 ATR = ATR30; N4 prior close = pdc).
  NEW in the engine: author cells (`info`: 201 cells, run + stored, left out of `library.plateau`), family-own exit cells (N7), `prepare`
  (N2 value-area cache `engine/cache/va70_<ROOT>.json`, built for BUILD), `run_menus.py plan | status | run --group round1`.
  PLAN: 63 run units, 7,068 candidate cells + 2,214 own null cells (N4 random direction, N7 random minutes); all 12 C1 pools exist.
  CAP 40,000 -> 50,000 (`library.CAPS`): 35,770 used (ledger.csv 34,946 + 824 booked on paper) + 7,068 = 42,838 -> fits, 7,162 left.
  TESTS: `tests/test_round1.py` 34 passed; full suite 1,389 passed, 2 skipped by design (old cap / mirror-set assertions updated in test_edge_library, test_edge_decisions).
  SMOKE NQ (+ ES, GC), 10 BUILD days, all 21 units each (counts only): every cell trades, 0 exits after the flatten, 0 entries outside the window /
  session, 0 overlaps, 0 errors, worker parity true (`out/engine_owner/round1_smoke_<ROOT>.log`). No BUILD store exists yet; no net / win rate / PF was opened.
  RUN: `nohup "~/ONYX TRADING/.venv/bin/python" run_menus.py run --group round1 --roots NQ,ES,GC --workers 8 >> out/run_agent/round1.log 2>&1 &` (restartable).
- 2026-10-04 08:16 ET, RUN AGENT - STAGE 2b ROUND1 BUILD COMPLETE (2021-09-22..2023-12-31, hold_to = day, 8 workers; PICK / EXAM untouched; no net / win rate / PF read).
  TESTS first: full engine suite 1,389 passed + 2 skipped, 0 failed (3 workers, ~9 min; out/run_agent/pytest_full_round1.log - the log shows dots only because addopts -q plus my -q = -qq hides the summary line; counted from the progress lines).
  RUN: `run_menus.py run --group round1 --roots NQ,ES,GC --workers 8` 06:36 -> 08:16 ET = 1 h 40 min wall (NQ 06:36-07:09, ES 07:12-07:43, GC 07:46-08:16); status 63 / 63 units done, 0 pending, 0 failed, 0 `*_error` rows; log out/run_agent/round1.log + out/run_menus.log.
  CELLS: 7,068 candidate cells (201 info-only author cells) in 63 build stores = per market vwap_trend_pull 4 units (NQ 387 / ES 384 / GC 384), va_reclaim 4 x 96 = 384, orb_confirm 3 units 594, late_mom 1 unit 288, open_fade 2 units 240, vol_spike_break 4 x 96 = 384, straddle_tight_0830 / _0930 / _1000 1 unit x 27 each. NULL: 12 own null stores = 2,214 null cells (late_mom 3 x 576, straddle 9 x 54); C1 pools: 12 already existed, 0 run.
  LEDGER (library.ledger_used): cells 42,014 of 50,000 in ledger.csv + 824 booked on paper = 42,838 -> 7,162 left (the hard check reads ledger.csv only, so it shows 7,986 left); wfs 0 used (the 24 "runs" are the earlier member rows, not this stage). Null cells run overall 21,658 (uncapped).
  SANITY (counts only; python out/run_agent/sanity_round1.py -> out/run_agent/run_table_round1.csv, same checks as sanity.py): 75 stores, period build, range 2021-09-22..2023-12-31 in all; sessions used NQ 568 of 573 / ES 571 of 573 / GC 565 of 572 (skips = data gaps); skipped_by_error 0; trades outside a session 0; unrealistic winners 0; both-sides declaration = evidence in every store; cells without a trade 0; 9,647,912 trades in all.
  NOTES (counts): straddle_tight_0930 fills in the last second before 09:30 sit in session 'pre' (so 'pre+nyam' on two markets) - judge it over 'all'; straddle_tight_0830 trades only in 'pre'; late_mom only in 'pm'; open_fade only in 'nyam'; vwap_trend_pull tf30 only in mid+pm; vol_spike_break tf30 only nyam+mid+pm. NEXT: the Admit analyst reads runs/<key> (library.judge / plateau); OPEN: the N2 value-area cache (engine/cache/va70_<ROOT>.json) holds the 573 BUILD dates only (prepare added 0); the coder says EXAM dates raise HoldoutSealed - whether PICK 2024 dates need an extension was not checked here (no PICK run).
- 2026-10-04 08:33 ET, ADMISSION ANALYST — STAGE 2b ROUND 1 JUDGED (scripts + tables: `out/admit_r1/`; summary `out/round1_summary.md`; odds `out/member_odds.md`). EXAM never read.
  BUILD: 258 units judged -> 43 pass the heat map (27 at 70 %, 19 at 80 %) -> 34 also beat the matched random control -> 4 also above the best-of-random bar.
  Bars: bar families = c1-<ROOT> as stage 1 (NQ 2.02, ES 1.30, GC 1.24); time-fired (N4, N7) = round 1's own random stores per market, written before any number was opened (8 replicates, THIN: NQ 0.84, ES 0.95, GC 0.63; pooled with stage 1's random-minute straddles: 2.56 / 1.88 / 1.63).
  2024 opened for the 4 (whole menu + control, passing session; `out/admit_r1/pick_reads.csv`; stores `runs_admit_r1/`):
    vwap_trend_pull NQ tf5 pm: table 61 % (passes), central `x0p1_pts30-r2` -$14,421 -> NOT admitted. vol_spike_break NQ tf30 pm: table 53 % (fails) -> NOT admitted.
    straddle_tight_0830 GC: table 70 %, central `offC_pts2-r1` -$1,180 -> NOT admitted. straddle_tight_0830 NQ: table 81 %, central `offB_pts5-r3` +$4,869 (244 trades), stress BUILD $8,954 -> $6,619, 2024 $4,869 -> $769.
  ADMITTED, FLAGGED: `members/straddle_tight_0830_NQ_tf30_pre/` (2021* $862 · 2022 $4,412 · 2023 $3,680 · 2024 $4,869; 793 trades; t 1.98 vs thin bar 0.84, fails the pooled bar 2.56 and the NQ random-entry bar 2.02; 19 of 27 variants survive; 39 micros inside $2,000). Same 08:30 idea as orb_NQ_tf1_pre (same side 80 % of shared days, daily correlation 0.41): ONE strategy for a stack. CHECKER: confirm or demote.
  Luck: 0 of 192 random units pass both BUILD gates; 4 of 258 real ones did, which a luck rate near 1.6 % would also give; 2024 removed 3.
  Information only: quiet-day heat map passes in 84 of 258 units vs 44 on active days (43 on all days); author cells: orb_confirm with the range stop NQ long 27 of 27 positive (best t 3.23), vwap author cell NQ 15-min afternoon 3 of 3 positive, open_fade target-at-ref 18 of 144.
  MEMBER ODDS alone (about $1,000 risk, open losses count; bar 60 % / 75 %): none at the bar. orb_NQ_tf1_pre eval P(pass <= 10 d) 26 / 32 / 31 / 34 % (Lucid Flex / Pro / Pro noDLL / Apex 50K), funded P(max payout <= 20 d) 23 / 25 / 24 / 11 %, Apex 300K PA 17 %; flagged member 21 / 21 / 21 / 32 % and 8 / 24 / 23 / 11 / 24 %.
  LEDGER: +440 candidate cells (246 on 2024, 194 stress) -> 43,278 of 50,000 (ledger.csv 42,454 + 824 on paper); +236 control cells; +4 member runs. IDEAS.md: 2 admitted (1 flagged), 138 open, 0 shelved; 27 new `ideas/` folders; rejected records in `members/_rejected/`.

- 2026-10-04 09:25 ET, ORCHESTRATOR — STAGE 2b CLOSED: round 1 (N1-N7, 258 units, 7,068 cells) admits NOTHING. Checker demoted
  straddle_tight_0830_NQ (fails the unchanged stage-1 bar 1.98 vs 2.56; profit needs a fill on the trigger print). Look-ahead audit
  of round1.py clean. Library = 1 member (orb_NQ_tf1_pre). Member odds alone: eval <= 10 d 26-34 %, funded max payout <= 20 d 11-25 %.
  LIVE FILLS (desk journal, read-only, 13 real stop-entry fills): NQ 09:30 adverse slip mean 0.6 pt, median 0.375, worst 1.75 (10 fills);
  gold NFP 10-02: 0.0; YM 4-5 pts. => real fills ~ engine base + ~1 tick; the 1 ms probe is far too harsh, the 2-tick stress is fair.
  STAGE 3 LAUNCHED (wf_38978cdb-3de): event-day straddles on stored trades with a full release calendar (EDGE_SPEC "STAGE 3").
  Candidate cells 43,278 of 50,000. Weekly tokens 71 %.

- 2026-10-04 09:25 ET, EVENT ANALYST — STAGE 3 (event straddles) DONE on stored trades. Summary: `out/events_summary.md`; scripts and results: `out/events/`.
  CALENDAR `engine/cache/events.csv` trusted, nothing dropped (no weekend date; 12 a year per monthly release, 52 claims, 8 Fed; jobs / CPI / Fed = the old file 40 / 40 / 27). Event sessions BUILD / 2024: A 227 / 96, B 159 / 68, C 97 / 46.
  BUILD, 15 units (tests a-e; bars NQ 2.56, GC 1.63, ES 2.00): 4 PASS — E1-A GC (223 trades, $10,598, t 4.55), E1-B NQ (157, $9,047, t 3.35), E1-B GC (156, $8,066, t 4.18), E3-C GC (97, $8,202, t 6.10). E1-A NQ fails only (e) (98.6 % < 99.67 %); every ES unit and every E2 (ATR straddle) unit fails the bar.
  2024 (whole menu + random-minute control; E1 = SECOND LOOK, E3-C GC first look): all four tables pass (81-100 % positive); BUILD central variants $5,496 / $2,383 / $2,448 / $4,166; stress 2 ticks + 250 ms BUILD / 2024: $6,358 / $4,126 · $8,637 / $173 · $4,746 / $1,128 · $6,972 / $3,396. library.admission: all pass, no moved default.
  ADMITTED, ALL FLAGGED (checker: confirm or demote): `straddle_tight_0830_GC_tf30_pre_evA` (2021* $902 · 2022 $4,660 · 2023 $5,036 · 2024 $5,496), `straddle_tight_0830_NQ_tf30_pre_evB` ($1,124 · $5,961 · $1,962 · $2,383; the demoted variant on tier-1 days; same idea as orb_NQ_tf1_pre), `straddle_tight_1000_GC_tf30_nyam_evC` ($552 · $2,418 · $5,232 · $4,166). E1-B GC = a subset of evA: on its card, no folder.
  FILL PROBE (entry 1 / 5 / 25 ms after the trigger print, never better than the stop; own replay matches the engine to the cent): gold 08:30 BUILD $10,598 -> -$1,382 / $1,278 / $1,758, 2024 $5,496 -> $426 / $596 / -$1,524; NQ evB $9,047 -> $4,977 / $5,122 / $3,237, 2024 $2,383 -> $1,173 / $473 / -$1,157; gold 10:00 $8,202 -> $1,652 / $1,852 / -$88, 2024 $4,166 -> -$1,004 / -$184 / -$1,424 = FILL-FRAGILE; orb_NQ_tf1_pre $16,362 -> $7,947 / $7,842 / $5,387, 2024 $12,437 -> $8,417 / $6,117 / $2,862 (not fragile). Most of the event members' profit is trades that open and close inside 2 seconds.
  INFORMATION: per-type tables in `out/events/per_type.csv` (gold 08:30: claims 118 trades $5,198, days without a release 339 trades -$6,556); Fed 14:00 on 19 BUILD days: NQ $2,248, ES $703, GC $2,038 (81 variants booked).
  ODDS alone (bar 60 % / 75 %): none near. Eval <= 10 d at about $1,000 risk, engine -> 5 ms fills: Lucid Flex gold 08:30 3 -> 1 %, NQ 7 -> 4 %, gold 10:00 0 %, orb 26 -> 20 %; Apex 50K 14 / 30 / 1 / 34 % -> 6 / 22 / 0 / 31 %. Funded max payout <= 20 d: event members 0-14 %, orb 11-25 %.
  LEDGER: +110 candidate cells (27 on 2024, 2 stress, 81 Fed information) -> 43,388 of 50,000; +54 control cells; +8 member runs. 2024 reads: `out/events/pick_reads.csv`. IDEAS.md: 3 ideas admitted holding 4 members (3 flagged), 140 open.

- 2026-10-04 09:45 ET, ORCHESTRATOR — STAGE 3 CLOSED (events, wf_38978cdb-3de). Calendar trusted (903 rows, 12 types, 40/40 spot checks).
  15 units judged; 4 pass BUILD; 3 members ADMITTED-FLAGGED (checker ok = true, nothing to demote under the written rules):
  straddle_tight_0830_GC evA ($16,094, 319 tr, SECOND LOOK), straddle_tight_0830_NQ evB ($11,430, 225 tr, SECOND LOOK, same idea as orb),
  straddle_tight_1000_GC evC ($12,368, 143 tr, first look on 2024, FILL-FRAGILE). All three live on the fill on the trigger print:
  checker says do not size / stack / count toward the goal before real release-day fills exist. Odds alone: nobody near 60 % / 75 %.
  Candidate cells 43,388 of 50,000. OPEN USER DECISION: second-tier ("B-list") admission for the 20 near-misses with unread 2024.

- 2026-10-04 10:15 ET, OCO PROBE (information only; no verdict changed; `out/oco_probe/OCO_PROBE.md`). New engine setting `Costs(oco_cancel_ms=)` in `engine/l2sim.py` (default 0 = the old trades, proven on all 4 members field by field; sha256/16 bc7394332573ff85): the other bracket leg works on N ms after the first fill; a trigger in the window = a DOUBLE FILL (second position, own stop / target, rows tagged `double_fill`).
  RESULT, central cells, 1 contract, 0 -> 25 / 50 / 100 / 250 ms: orb_NQ_tf1_pre BUILD $16,362 -> $16,673 / $16,673 / $17,255 / $17,255, 2024 $12,437 -> $12,098 / $12,098 / $12,505 / $13,042 (0-5 double fills); gold 08:30 evA $10,598 -> $10,598 / $10,754 / $10,910 / $11,066, 2024 $5,496 -> $5,496 / $5,652 / $5,398 / $5,554 (0-3);
  NQ 08:30 evB $9,047 -> $8,344 / $8,185 / $8,248 / $8,044, 2024 $2,383 -> $2,219 / $2,219 / $2,515 / $1,528 (1-7, up to 7.3 % of brackets); gold 10:00 evC $8,202 -> $8,202 / $7,968 / $7,968 / $7,968, 2024 $4,166 -> $4,166 / $4,166 / $3,992 / $4,304 (0-3). NO member turns negative. Worst single double fill -$918 (NQ evB 2023-01-12).
  Order gap: orb median 12 pts ($240; p10 7, p90 23.25), gold 1.2 pts ($120), NQ evB 10 pts ($200). Own tape recount = the engine's count in all 32 delay cells. Caveat: the late leg gets the same fill-on-the-trigger-print; the fill probe's risk stays the big one.
  TESTS: `tests/test_l2sim_oco_cancel.py` (4 new) + full suite 1,393 passed, 2 skipped (`out/oco_probe/pytest_full.log`). OPEN (engine owner): l2sim.py changed -> ENGINE.md 12 asks for `edge_validate.py`, `port2_validate.py`, `port3_validate.py` again (NOT re-run here; the suite warns about it). LEDGER: +40 `member` run rows (control `oco<ms>ms`; runs 36 -> 76 of 2,000), 0 candidate cells. 2024 reads: `out/oco_probe/pick_reads.csv` (24 rows, the already-read central cells only).

- 2026-10-04 11:20 ET, ORCHESTRATOR — USER RULINGS: (1) library first (no odds gating); (2) Lucid 5-second rule is an account-level
  share (> 50 % of profits from trades <= 5 s), NOT a gate: fast members are kept; (3) ADMISSION v2 = judge the average of all variants
  (EDGE_SPEC "ADMISSION v2"), the 20 near-misses go through it; (4) DEEPEN ROUND 2 with the user's toolbox (range stops, more ATR / RR,
  shorter 09:30 ranges for ib, momentum / volume / Level 2 filters). OCO probe: late cancel 25-250 ms = small effect (out/oco_probe/).
  Order: STAGE 4 (running, wf_b878e991-9b9) -> v2 re-judge of all stores + 2024 for the 20 -> DEEPEN ROUND 2. Cap -> 80,000.

- 2026-10-04 11:00 ET, ENGINE CODER — STAGE 4 ENGINE READY (P&L-blind, counts only; nothing run on BUILD yet). STEP 0: `edge_validate.py`, `port2_validate.py --fresh`, `port3_validate.py` ALL PASS on l2sim.py bc7394332573ff85 (the `oco_cancel_ms` edit).
  BUILT `engine/families/round2.py` (ENGINE.md § 14): W `straddle_wide_0830 / _1000` (bracket ± NQ 10 / 15 / 20 / 30, ES 2.5 / 4 / 5 / 8, GC 2 / 3 / 4 / 6; stop 0.5 / 1 / 1.5 × the offset = new stop_mode `offx`; target 1:1 / 1:2 / 1:3; armed 1 s before, cancel after 5 min; 36 cells) and D `event_dir_0830 / _1000` (anchor = last print before T; at T + x, x = 0.25 / 0.5 / 1 / 2 / 5 / 15 / 60 s, one market order in the direction of the move, no move = no trade, one trade a day; 7 × 32 = 224 cells). Every day is run; the release-day filter is the analyst's.
  ENGINE CHANGE (one line): `l2sim.et_ns` keeps a fraction of a second (needed for x = 0.25 / 0.5 s; whole-second times unchanged). The three gates were run AGAIN on the final file (sha256/16 72369e8b94b85172): ALL PASS. Full suite 1,420 passed, 2 skipped by design.
  NULLS: W = the same bracket at random minutes; D = the same entry with a coin-flip direction (same days, same instant); both `shift_seed` 1, 2 in the `-shift` store.
  PLAN `run_menus.py plan --group round2`: 12 run units, 1,560 candidate cells + 3,120 null cells; 43,388 + 1,560 = 44,948 of 50,000 → fits (5,052 left).
  TESTS `tests/test_round2.py` 23 passed (no look-ahead: prints after T + x rewritten → same decision; anchor strictly before T; order live only after T + x + 85 ms; one trade a day; 1 vs 8 workers). SMOKE 10 BUILD days, NQ and GC, all four families: ALL OK (0 errors, 0 entries outside the window, max 1 trade a day; `out/engine_owner/round2_smoke_*.log`).
  WATCH (print counts, `out/engine_owner/stage4/burst_timing.json`): on tier-1 08:30 days the tape's burst starts about 1.25 s after 08:30:00, so x = 0.25 / 0.5 s mostly decide before it; at 10:00 the burst is in the first 0.25 s. Nothing was changed for it.
  RUN: `cd W && nohup "~/ONYX TRADING/.venv/bin/python" run_menus.py run --group round2 --roots NQ,ES,GC --workers 8 >> out/run_agent/round2.log 2>&1 &` then `python run_menus.py status --group round2`.

- 2026-10-04 11:14 ET, RUN AGENT — STAGE 4 (round2) BUILD RUN DONE, P&L-blind. `run_menus.py run --group round2 --roots NQ,ES,GC --workers 8` (nohup, 14:59:50Z -> 15:13:30Z, ~13.7 min wall, no restart, no error row). BUILD 2021-09-22..2023-12-31 only; PICK and EXAM not run.
  UNITS: 12 run units = event_dir_0830 / event_dir_1000 (224 cells each x NQ, ES, GC = 1,344) + straddle_wide_0830 / _1000 (36 cells each x 3 = 216) = 1,560 candidate cells; 12 `-shift` null stores = 3,120 null cells (shift_seed 1, 2). 24 stores in runs/, 24 ledger rows. Trades 2,108,364 (cells + nulls).
  LEDGER: ledger.csv cells 42,564 -> 44,124 (+1,560); with the 824 booked on paper = 44,948 of 50,000 (5,052 left). Runs 76 of 2,000.
  SANITY (out/run_agent/sanity_round2.py -> run_table_round2.csv, counts only): skipped_by_error 0, trades outside a session 0, unrealistic_winners 0, both-sides declaration ok, cells without a trade 0 (GC straddle_wide_1000 6-point offset filled over the full BUILD). Sessions used / calendar: NQ 568/573, ES 571/573, GC 565/572 (skips = days with no usable tape, as in round 1).
  Next: v2 re-judge of all stores (library.plateau central variant), nothing P&L seen by the run agent.

- 2026-10-04 11:50 ET, ANALYST — STAGE 4 (event entries) JUDGED ON BUILD: **0 of 18 units pass; no member; 2024 NOT opened** (no 2024 run of these families exists; `out/entries/pick_reads.csv` = header only). No odds computed. Judged as briefed: tests (a)-(e) of STAGE 4 + the old 5-SECOND GATE; the v2 section (11:15 ET) was written while this ran and is NOT applied here.
  W (wide bracket): NQ 08:30 tables are 100 % positive (36 of 36) in groups A and B, but the central variants fail: W-B-NQ `offB_offx0p5-r2` 150 trades $9,535 t 3.23 (bar 2.56), subset 99.35 % < 99.72 %, and -$7,041 without winners under 5 s (73 % of gross profit is under 5 s); W-A-NQ `offD_offx0p5-r3` 132 trades $8,937 t 1.33, 76.8 %, passes the 5-second gate ($1,769). ES / GC and all 10:00 W units fail (d) and (e).
  D (market order in the direction of the move): 08:30 fails everywhere (5-22 % of 224 variants positive, median -$6,400 to -$7,700; NQ at 0.5-2 s loses $60-95 a trade and the random direction does better). 10:00: only D-C-GC passes the heat map (78 %), t 0.38; its random-direction control earns as much. Per-wait lead (information, no luck test): NQ 10:00 at 2-15 s, 66-84 % of exits positive and above the random direction.
  No unit fails ONLY the 5-second gate, so the verdict does not hang on it. For the v2 re-judge: `fast_profit_share` in out/entries/build_units.csv; tables to look at: W-A-NQ, W-B-NQ, W-B-ES, D-C-GC. W at 08:30 on NQ / GC = SECOND LOOK if 2024 is ever opened.
  Not run (written for admitted cards only): 1 / 5 / 25 ms fill probe, 100 ms late-cancel probe. Ledger: nothing new booked (0 runs, 0 variants); 44,124 (+824 on paper = 44,948) of 50,000.
  Records: out/entries_summary.md (58 lines) · ideas/event_entries_{NQ,ES,GC}/ · IDEAS.md (+3 lines OPEN, 143 open) · out/entries/ (judge4_build.py, write_records4.py, build_units.csv/.json, per_x.csv, per_type.csv, judge4_build.log).

- 2026-10-04 12:45 ET, ANALYST — ADMISSION v2 DONE (EDGE_SPEC "ADMISSION v2", parts A-C; the average of all variants; no odds). 1,916 units re-judged (stage 1: 1,623 · round 1: 258 · events: 15 · stage 4: 18 · the 2 stage-2a sides opened on 2024).
  BUILD: (1) 273 · (1)+(3) 250 · (1)+(2)+(3) 57 (NQ 39, ES 12, GC 6) -> 2024 opened for the 57 (45 menus new, 12 on disk; `out/v2/pick_reads.csv`): (4) 29 · (4)+(5) 19 · +(6) 14 · **14 saved = 7 ideas** (`out/v2_members.md`).
  MEMBERS (average variant, cards in members/): 08:30 burst idea = straddle_t_0830 NQ, straddle_tight_0830 NQ (all days, evA, evB), straddle_tight_0830 GC (evA, evB) · straddle_tight_1000 NQ evC · straddle_tight_1000 GC evC ·
  first_bar_mom midday (NQ 30-min, NQ 15-min, ES 15-min; PENALTY flag) · orb NQ 15-min pre-market · straddle_t_1800 NQ · tema_slope NQ 30-min evening (WEAK flag). Defaults = middle survivor by BUILD net.
  v1 member orb_NQ_tf1_pre FAILS v2 test (2) (table average $19,279 vs random $18,754, beats 54 %) -> members/_v1_only/. The 3 v1 event members stay (new defaults). _demoted / _rejected folders: v2_rejudge.md in each (straddle_tight_0830 NQ all days is now a member).
  PLACEBO: 1 of 168 random-entry tables passes all six (NQ 1-min evening). At 0.6 % about 11 of the 1,881 non-event units pass by luck; 8 did: the non-event members are NOT shown to be more than luck. Event members: two controls each, no placebo, burst-fill risk.
  NOT IN: ib midday break (passes BUILD, loses 2024), donchian (morning 93.5 % on (2); afternoon loses to random in 2024), vwap_trend_pull (2024 positive but below random entries), wide bracket (release days beat only 70-90 % of random day subsets), stage-4 market order.
  METHOD CALLS (out/v2_summary.md section 8): (2) = every control on disk must pass; C1 at table level = 200 coupled day-matched draws from the 2-seed pool (independent draws are about 5x too narrow); time-fired = 200 day-mixes of the 2 seeds (thin);
  (3) on BUILD = trades scaled to BUILD + 2024 >= 100; 60 % read as >= 60 %; penalty / WEAK kept as flags. OPEN: more random seeds (pool luck is not in the draws); a day-filter placebo; 1 / 5 / 25 ms fill probe of the new defaults.
  2024 SPENT by v2 for 43 failed units, incl. DEEPEN ROUND 2 names: ib midday (NQ 5 / 15 / 30, ES 30), vwap_trend_pull pm (NQ 1 / 5, ES 30), vol_spike_break pm (NQ, ES 30), orb_confirm pm long (NQ 5 / 15, ES 1 / 5), donchian pm.
  LEDGER: +5,162 candidate cells (3,601 on 2024 + 1,561 stress) -> 49,286 in ledger.csv, 50,110 with the 824 on paper, of 80,000; +2,786 control cells; +56 member runs (132 of 2,000). library.CAPS still says 50,000: run_v2.py passes caps=80,000 itself.
  RECORDS: out/v2_summary.md (66 lines) · out/v2_members.md · IDEAS.md (9 idea lines admitted, 137 open) · members/<14>/ · out/v2/ (v2.py = method; scripts; build_units.csv, pick_units.json, final.json, members.json, placebo.csv, closest.csv) · runs_v2/.

- 2026-10-04 12:40 ET, ORCHESTRATOR — APP WORK (outside the library, for the record): TradingView / Pine leftovers removed and merged
  (25dba038); speed group A (status / calendar caches, journal fill timings, side-by-side single backtests, drafts cache, chart
  timeframe resample, lean history) merged (fc822aef); exits branch B (accounts side by side, bound 4; one fewer position lookup) merged
  (ae1e829d) — the user rehearses it on paper Monday. Desk restarted 11:38, 12:32, 12:38 ET, each time back armed, same accounts,
  same bookings (only paper booked). 74 old worktrees removed. Repo renamed QVANT-HOMEBASE; research/ tracked on main.

- 2026-10-05 09:55 ET, ORCHESTRATOR — USER DIRECTIVE (binding): "when these are done I want you to pause, test these approved strats
  OOS and let me know which are real and which are overfit then pause until I say". => Let the three running jobs finish (judge tool,
  blocks + r3 spec files, 2025 open + 10-seed controls + 2025 menus). Then ONLY: score the saved strategies on 2025 (CHECK year; 2026
  stays sealed), report real vs overfit, and STOP. The AUTOPILOT MANDATE is suspended: do NOT run the r3 batch or any new round until
  the user says so. All desk algos are off (user, 2026-10-05 morning).
- 2026-10-05 10:00 ET, ORCHESTRATOR — USER: also run 2026 for the saved strategies that pass 2025 ("fully finish the OOS"). Rule written in
  EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES". Then report REAL / OVERFIT / NOT PROVEN and STOP until the user says.

- 2026-10-05 10:35 ET, ENGINE CODER — BLOCKS + IDEAS AS SETTINGS READY (WORKBENCH PLAN 2; P&L-blind, counts only; nothing run on BUILD beyond smokes; no existing engine file edited). Doc: ENGINE.md § 15.
  NEW: `engine/families/blocks.py` (mixin `Blocks` in front of any bar-based family: `WRAPPED` 27 families; range stop `stop_mode="rng"` x 0.25 / 0.5 / 1 of the idea's own range; menu `extended` = 32 standard cells + ATR x 1 / x 2 + targets 1.5 / 4 = 78 cells, 60 without a structure; filters volatility / momentum (RSI 14) / volume / news / book, two sides each; family `ib_n` = ib with a 5 / 15 / 30 / 60-minute range) · `run_idea.py` (plan | build | status | catalog | smoke) · `ideas/specs/r3_*.json` (6 ideas) · `engine/tests/test_blocks.py` (44) · `cache/minvol_<ROOT>.npz` (BUILD minute volume).
  TESTS: blocks 44 passed at 8 workers. Parity (blocks off = the original family, every trade field): 372 pairs per market on 10 BUILD days, 0 differ (NQ 5,064 / ES 4,750 / GC 3,977 trades compared; orb, donchian, first_bar_mom, vwap_trend_pull, vol_spike_break, ib_n(60) vs ib). No look-ahead: prints and book rows rewritten from each decision on change nothing before it (8 structures, every filter); 1 vs 8 workers identical. Smoke 14 spec x market x bar-size jobs: 0 dropped sessions, 0 hold violations (`out/blocks/`).
  FULL SUITE (l2sim.py sha256/16 50f67baa4337a160): 1,463 passed, 2 skipped, 4 FAILED — none in blocks: test_edge_periods + test_edge_roots (another agent's CHECK-2025 work in l2sim.py / 2025 tapes, edited 09:52 ET today), test_round1 / test_round2 plan tests (ledger 50,110 > library.CAPS 50,000 since v2). Log `out/blocks/suite_full.log`.
  r3 PLAN AS WRITTEN (`out/blocks/plan_r3.txt`): 522 units (54 base + 468 filter) = 131,022 candidate cells + 23,364 control cells; ledger 52,118 used of 80,000 -> DOES NOT FIT (103,140 over). About 53 h at 8 workers. Fits: base units only 13,554 cells (~6.6 h); or bar size 15 with filters on the standard menu 21,158 (~9.6 h). OWNER DECISION NEEDED before `build`.
  OPEN: judge.py does not read the new control stores `c1x-*` / `<name>__c1r-*` yet (an extended table fails its control with "no pool cell"); 12 workers need `l2sim.MAX_WORKERS` (hard 8) changed; `run_menus.py plan` now also lists ib_n (9 units, 1,152 cells, not to be run there).

- 2026-10-05 12:11 ET, OOS ANALYST — FULL OUT-OF-SAMPLE OF THE 15 SAVED STRATEGIES DONE: **REAL 0 · NOT PROVEN 8 · OVERFIT 7** (`out/oos_summary.md`, 73 lines). One read per unit per year, nothing tuned or re-run. **ALL WORK STOPS until the owner says.**
  2025 (`judge.py year <unit> --period check`, 4,000 draws, 10 seeds; average variant): CONFIRMED gold 08:30 evA +$2,009 / evB +$3,601, NQ 10:00 evC +$984, gold 10:00 evC +$2,226, first_bar_mom NQ 15-min +$2,176, and (information only) 18:00 bracket NQ +$8,152 · WEAK first_bar_mom ES 15-min +$1,373 (stress -$777), donchian NQ 30-min +$7,955 (lift -$960) · FAILED tight 08:30 NQ all days -$1,450 / evA -$2,806 / evB -$730, first_bar_mom NQ 30-min -$6,182, orb NQ 15-min -$9,371, tema_slope -$4,118, wide 08:30 NQ -$310.
  2026 (2026-01-01..2026-09-22, only the 5 members CONFIRMED on 2025; `out/exam2026/allowed.json` written first): gold 08:30 evA -$2,029 and evB -$896 FAILED (tests 4, 5, 6) · NQ 10:00 evC -$1,105 FAILED (4, 6) · gold 10:00 evC +$522 WEAK (beats random, -$661 under stress: fails 6 only) · first_bar_mom NQ 15-min +$6,269 WEAK (median variant -$62: fails 4 only; default +$50,281).
  SURPRISE: the judge also DEMOTES orb NQ 15-min (BUILD test (2): 79.4 % of random tables with 10 seeds, 96.8 % with 2); the RULING text counted it as a member. No effect: it is OVERFIT on 2025 anyway and was never near 2026. So 12 members under the rule in force, 3 demoted.
  STEP 0: library.CAPS cells 50,000 -> 80,000; the cap number updated in 4 test files (test_round1, test_round2 as asked + test_edge_decisions 1 line, test_edge_library 4 lines that pin the same cap). Engine suite 1,483 passed, 2 skipped. After the 2026 gold tapes: test_edge_roots' "no 2026 tape on disk" assert now allows only an allowed market up to allowed.json's end date (+ build_tapes still refuses 2026).
  CALENDAR (`out/exam2026/calendar_check.md`): NFP / CPI / FOMC 2025-26 = news_days.csv; 238 of 248 other rows re-read at official sources, all right; 5 rows ADDED (2026-09-30 GDP + PCE were missing; 10-01 CLAIMS + ISM_MFG; 10-02 NFP), none changed. No release type left out.
  2026 DATA: last complete session = 2026-09-22 for NQ and gold (end of the Massive backfill and of the NQ tape; later desk recordings have gaps). 181 gold tapes built (`out/exam2026/build_data.py`), nothing else. The engine dropped 2026-09-22 itself (hole 13:00-15:00) -> last day traded 09-21; NQ also lost 04-03 and 09-11. Used 179 (NQ) / 180 (GC) sessions.
  2026 STORES (12, `runs_exam2026/`, each in `out/exam2026/reads.csv`; allow_exam=True; identity check on 10 BUILD + 6 2025 days: 0 cells differ): menu + stress + 10-seed control for straddle_tight_0830 GC pre, straddle_tight_1000 NQ nyam, straddle_tight_1000 GC nyam, first_bar_mom NQ 15 mid (control = c1-NQ-tf15-mid). LEDGER +354 candidate cells -> 51,648 (52,472 with the 824 on paper) of 80,000; +1,130 control cells.
  judge.py: third period `exam` (same tests and code path as `check`), refused unless `--exam` AND the unit is on allowed.json; a DEMOTED unit never reaches it. New test `test_exam_is_sealed_without_the_flag_and_off_the_allowed_list` (judge, engine seal, runner seal). Lock: tests/test_judge.py green; the 15 2025 lines re-derived byte for byte after the change.
  JUDGEMENT CALLS: end date = last session of the unbroken complete run (not 10-01, the last day flagged complete among gappy desk days) · the EXAM key loads no carried evening ATR for 2026: shown on BUILD days to change no trade of these brackets (identity.log) · wide 08:30 NQ called OVERFIT (2025 average negative) although also DEMOTED · members/donchian_NQ_tf30_nyam/ holds card + surviving set only (no member run).
  RECORDS: 15 cards refreshed (`judge.py card <unit> --exam`) · IDEAS.md (10 status cells + header line) · JUDGE.md · out/events/CALENDAR.md · out/exam2026/ (oos.json, collect.py, write_summary.py, run_exam.py, make_jobs.py, jobs_exam.json, stores.csv, sanity.csv, score2025_*.log, score2026_*.log).

- 2026-10-05 ~13:30 ET, ORCHESTRATOR — FULL OUT-OF-SAMPLE DONE AND CHECKED (wf_b34428f0-ac4, checker ok): REAL 0 · NOT PROVEN 8 · OVERFIT 7
  of the 15 saved strategies (out/oos_summary.md). 2026 opened only for the 5 that passed 2025; all 5 failed 2026. Nearest miss: gold
  10:00 release bracket. Reported to the user. **STOPPED on the user's directive: nothing runs until the user says.** Ready, not run:
  judge.py, engine/families/blocks.py, ideas/specs/r3_*.json. Do not open engine/cache/daily_NQ_holdout.json (2026).
