# New default heat map (40 cells) + every box through the 3:1 block walk-forward

Owner, 2026-10-20. Status: DRAFT, waiting for the owner's yes. Nothing is built before it.

## 1. Intent (the owner's words, made plain)

1. **One default heat map for every test, every session, every route, every chat and every agent**, built to favour win rate:
   no "no target" cell, no fixed-point or percent stops, small-to-middle targets.
2. **The 3:1 block walk-forward is THE in-sample / out-of-sample split, always, everywhere.** The old split (build days
   2021-09-22 .. 2025-06-30, then the test days 2025-07-01+ read once) stops being a default anywhere.
3. **Each box is run FIXED through every block** -- the same variant in every 3-month group; nothing is re-picked per block.
   Each box gets its own in-sample record (its 3-month groups stitched) and its own out-of-sample record (its 1-month test
   months stitched), and the results are shown block by block too.
4. **The owner picks the box himself** from the in-sample table. No code picks for him.

Why: the old route weeded ideas on four build years whose months the walk-forward later traded as "unseen" -- months were
read twice. Under this design every month is in-sample or out-of-sample, never both, and the picking happens on in-sample
numbers only.

## 2. Goals, non-goals, anti-goals

Goals
- The 40-cell table is the default heat map of every route listed in section 5.
- Every route's in/out-of-sample answer is the per-box fixed 3:1 block walk-forward.
- An in-sample table the owner can pick from, per box, with win rate up front.
- A new chat or agent that is told "heat map" or "test it" or "check it OOS" lands on both defaults without being told.

Non-goals
- No automatic pick, no pass/fail gate added by this project (the owner picks).
- No rewrite of the pipeline's stages: the pipeline is OFF (the owner disabled it 2026-10-20). See 4.6.
- No change to costs, fills, flat time 15:58, markets, bar sizes or families.
- Rolling (step 1 month) stays an option only when the owner asks, as today.

Anti-goals (a failure even if it runs)
- Any route that still defaults to the build days / one test-days read.
- A box whose settings change between blocks.
- Any out-of-sample month run, stored or shown before the owner says so (4.4).
- Old saved results silently re-labelled or broken.

## 3. The new default heat map ("hm40")

| | Values |
|---|---|
| Targets (R = x the stop distance) | 0.5, 0.75, 1, 1.5, 2 |
| ATR stops | 0.5, 1, 1.5, 2 x ATR(14) -- Wilder, 14 bars **of the idea's own bar size** |
| Own stops | 0.5, 1, 1.5, 2 x the strategy's own stop distance |

- 8 stops x 5 targets = **40 cells**; x the idea's 3 setting values = **120 boxes**.
- **Own stop** = the distance from the entry reference to the family's structure level (e.g. candle_sweep: the breakout
  candle's low for a long, high for a short) times the multiplier. Same rule `candle930` already uses
  (`engine/families/candle930.py:158,171`).
- **A family that passes no structure level** (27 of 59 today, e.g. straddle, vwap_z, ind_signal -- list from
  `blueprint/taught.py:228 passes_structure`) gets the **ATR stops only: 20 cells, 60 boxes**. Its own-stop cells are left
  out, never silently turned into ATR stops (today's `_dist` does that silently: it must not happen in hm40).
- Cell order: ATR stops first (0.5 → 2), then own stops (0.5 → 2), targets inner (0.5 → 2). Cell ids in the engine's
  existing style (`atr0p5-r0p5`, `struct1-r1p5`, ...).
- The old tables (standard 48, open 60, extended, own/own_low) stay in the code so old results still read; none is a
  default any more.

## 4. The walk-forward, per box

### 4.1 The months
- Data: 2021-09-22 → the last whole month of the market's complete sessions. Sep 2021 (partial) and the current month are
  outside every block.
- Blocks, not rolling: pick months = 3, test month = 1, the next block starts after the test month:
  Oct-Dec 2021 IS → Jan 2022 OOS, Feb-Apr IS → May OOS, Jun-Aug IS → Sep OOS, Oct-Dec IS → Jan OOS, ...
  Today (last whole month Sep 2026): 15 blocks, 45 in-sample months, 15 out-of-sample months. This is the layout
  `blueprint/pipe_wf.py months()/walk` and `homebase/backtest/walkforward.py` already produce; reuse it, do not re-derive.

### 4.2 Per box
Every box of the heat map is run once over all the data (each trade belongs to exactly one month). Then, per box:
- **In-sample record** = its trades in the 45 pick months, stitched.
- **Out-of-sample record** = its trades in the 15 test months, stitched.
- **Per block**: its 3-month in-sample numbers and its 1-month out-of-sample numbers, one row a block.
The box never changes between blocks. This generalises what the Lab already does for ONE cell
(`homebase/backtest/walkforward.py:294`, "one cell: nothing to choose": `stitched_is` + `stitched`) to every cell.

### 4.3 Numbers shown per record (both records, same columns)
Win rate · breakeven win rate of its realised reward:risk (1 / (1 + avg win / avg loss)) · win rate minus breakeven ·
trades · trades a week · average trade $ and R · net · profit factor · daily Sharpe · max drawdown ($ at 1 contract) ·
% of months positive · % of months with win rate ≥ 60 % · worst month's win rate · long / short net. All at 1 contract
after the house costs. Win rate is the first column; the table sorts by any column.

### 4.4 The owner's pick and the out-of-sample read (the owner, 2026-10-20: "run them when i say")
- Every box is run on the **45 in-sample months only**. The 15 out-of-sample months are **not run, not stored, not read**
  by anyone (Claude, agents, tools) until the owner says so.
- The owner picks a box (by number, in chat or in the Lab); the pick is saved (the lock, 4.7). The out-of-sample run of
  that box starts **only on the owner's word** ("run it"), never by itself after the pick.
- The read is logged (who, when, idea, box, code stamp), like `reads.py` today. A box whose out-of-sample is on file is
  shown, never run again.
- Out-of-sample of more than one box: only when the owner asks for those boxes by name.

### 4.5 Rolling
Unchanged as an opt-in: Lab Range "3:1 rolling" or the owner tells Claude. Per-box fixed, like the blocks.

### 4.6 The pipeline
It is OFF. This project does not rewrite its stages. Claude's call: while its stages still use the build days, the
pipeline refuses to start with a one-line reason ("the pipeline still runs on the old build-days split; move it to the
3:1 per-box walk-forward first"), so turning it back on cannot bring the old split back by accident. Moving the pipeline
onto this design is a later project, on the owner's word.

### 4.7 The other blueprint phases (Claude's call, after the builder check)
- Idea card: unchanged (it reads no data).
- Code check, proof against random entries, worse fills: run on the **45 in-sample months only**, shown per box as labels in
  the in-sample table. Nothing on the old build-days window (it holds 11 of the 15 test months).
- The owner's pick = the lock: the box, its settings and the code stamp are written BEFORE its out-of-sample months are
  read. `blueprint_sim`, the eval card and the Desk read the out-of-sample record of the locked box.
- Ideas whose months were already seen (tuned on the build days, or the test days read once in `reads.py`): the walk-forward
  runs, and its result carries a plain label "months already seen: <which>". Not refused.

### 4.8 The Lab (Claude's call)
- The Lab default heat map = the 40 exit cells. The strategy's own inputs are axes only when the owner adds them; the
  default cap rises to fit 40 x 3 values (120).
- Own-stop cells are offered when the strategy sets a stop of its own (controls stop "own"); otherwise the 20 ATR cells.
- ATR(14) of the strategy's own bar size applies to the hm40 cells only; old Lab runs and controls stay as they were.

## 5. Where the defaults must land (every route)

From the code map of 2026-10-20 (file:line references are today's):

**Research engine / blueprint**
- New table: alongside `engine/families/blocks.py exits()` as a new kind `hm40`, plus the own-stop multiplier in the
  stop distance. `engine/l2sim.py` and `families/blocks.py` are hashed into every store's code stamp
  (`blueprint/runner.py code()`): editing them marks every old store / lock "written by other code". Builder's call how
  to avoid that (the `orb830.py:259` pattern wraps `exits()` from outside).
- The build-range seal (`blueprint/runner.py:113-136 seal/guard`, `l2sim.py BP_BUILD/ALLOW_BP/ALLOW_BT`,
  `templates/ranges.json`) must let a hm40 walk-forward run read all days 2021-09-22 → last whole month. Old routes keep
  their seal.
- `blueprint_*` tools that build a heat map default to hm40 + the per-box walk-forward; `blueprint_test` (the one
  test-days read) and `oos.py` are no longer a default route (kept for old results; refused for new ideas unless the
  owner asks).
- Taught lane (`blueprint/taught.py`, `taught_wf.py`) and manual lane: default table hm40, OOS = the per-box walk-forward.

**Homebase (Lab / Desk / connector)**
- Lab heat map default (`homebase/backtest/controls.py`, `static/charts/tester.js CONTROLS`, `static/charts/lab.js
  HEAT_SUGGEST/EXIT_LAB`, `backtest/grid.py` cap 60): the 40 cells. The Lab needs an "own stop x multiplier" and ATR(14)
  of the strategy's bar size (today Lab ATR = 14 bars of 5 minutes).
- Lab Range default = 3:1 blocks (already the Lab's default since 10-18; `tester.js RANGES` still lists Build first --
  change). The Lab walk-forward with a heat map runs every cell fixed (4.2) and shows the in-sample table (4.3/4.4).
- Desk "Unseen days" card (`charts/deskresults.py`): already 1-cell 3:1 blocks; the built-in twins nq930 / gc_nfp still
  use the old single read: move them.
- Connector (`homebase/claude_mcp/tools.py heatmap, walkforward PRESETS`, `blueprint_tools.py`, `protocol.py` instructions
  text "default range is the build days ... test days read once"): defaults = hm40 + per-box 3:1 blocks; the text says so.

**Words every new chat / agent reads**
- `CLAUDE.md` (project): replace "Build days stay the window for the idea card, the heat map, the proof and the lock"
  with the new rule; add the hm40 default.
- `research/edge-library/BLUEPRINT.md` section 2.
- Skills: `~/.claude/skills/strategy-blueprint`, `test`, `tester`, and `skills-disabled/pipeline` (so it is right if
  re-enabled).
- Vault memory note + one line in the project MEMORY.md index; the old "Walk-forward 3:1 replaces unseen read" and
  "OOS = 3:1 block walk-forward" notes updated to point at this one.

## 6. Constraints
- House law: judge at 1 contract after costs; flat 15:58 ET; nothing tuned after the out-of-sample read.
- At most 2 backtests at once during desk hours (weekdays 08:00-16:15 ET), 4 outside.
- Old stores, locks and Desk results must stay readable and keep their old labels.
- The tests that lock the 48-cell table (`tests/test_blueprint_rules.py:141-162` and the others in the code map) keep
  locking the old table as an old table; new tests lock hm40 and the per-box walk-forward.
- Compute: 40 cells x 3 values x ~60 months vs today's 48 x 3 x 45 -- about the same per idea.

## 7. Open -- the owner's answers

None left (4.4 answered 2026-10-20).

## 8. Left to the builder
- Code layout, names, how the hashed-file problem is avoided, the store format for per-box records.
- Whether the own stop keeps today's 0.25 x ATR floor (Claude's call: keep it, as every structure stop has it).
- The random-entry control for own-stop cells (the control has no structure level): builder decides; it is shown, it
  asks nothing.
- Order of work: engine table → research walk-forward → Lab → connector → words.
