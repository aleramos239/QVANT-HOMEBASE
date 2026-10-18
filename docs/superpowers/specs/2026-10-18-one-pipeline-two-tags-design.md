# One pipeline, two tags (design, 2026-10-18)

The owner, 2026-10-18, after the full audit of 2026-10-17: the four pipelines (Live, WR, Payout, Funded) become ONE pipeline
that judges a strategy by its own size-free numbers at one contract, and tags each pass **Live** or **Live + Prop**. The prop
simulator (eval odds, payout odds, 40 % bar, account rule files) leaves the pipeline: how a strategy is sized and risked for an
eval or a funded account is a later step on the Desk, not a pipeline gate.

## Why

- The pipeline's 202 ideas gave 1 honest pass. The 40 % eval-odds gate stopped 76 % of them and measures size, not edge.
- The prop odds depend on contract size and on which account rule file is loaded; the owner wants the pipeline to say whether a
  strategy has an edge at all, in numbers that do not move with size.
- Four modes is where the random gate got lost (a label in prop mode until 2026-10-17). One set of rules is easier to keep honest.
- The owner's goal is net profit across all accounts, not the survival of any one account: "if one account gets blown that's fine
  as long as overall we are profitable." So drawdown is a price tag and a sizing question, not a stop.

## Goals

1. One pipeline, one queue, one book. The switch is Off / On.
2. Three stops, all at one contract after costs, judged on the picked box:
   - **Profitable**: average trade above $0 with at least 200 trades on the build days (today's P3.2 and P3.3), and the box's own
     net above $0 on the unseen days (today's stage-6 box read).
   - **Beats random**: the locked map beats 95 % of the random-entry tables on the unseen days (line 4.4, the ladder of tries as
     today). Unchanged.
   - **Win rate over breakeven for its realized R:R, plus 3 points.** Realized R:R = average winning trade / average losing trade
     (absolute, after costs). Breakeven win rate = 1 / (1 + realized R:R). The box's win rate must be at or above breakeven + 0.03.
     Judged on the build days when the box is picked (so the boxes the pick is made among already hold it) and again on the unseen
     days at stage 6.
3. Shown numbers (labels, never stops), on the book card, each read on the build days and on the unseen days:
   win rate · realized R:R · breakeven win rate · average trade in R (average trade / average losing trade) · net per contract ·
   net per year per contract · Sharpe (daily session P&L including $0 days, mean / std, times sqrt 252) · months positive
   (share of months with a trade that end above $0; exists as `winning_months`) · biggest day's share of the net (exists) ·
   worst drawdown in R (today's `worst_drawdown`, open losses counted, / average losing trade) · monthly win rate (lowest and
   median month, months with 3+ trades).
4. The tag, written on the book card at stage 7 off the unseen-days numbers:
   - **Live**: the three stops hold.
   - **Live + Prop**: the three stops hold AND Sharpe is at or above the prop Sharpe bar AND months positive is at or above 60 %.
   The Lab's Book shows the tag on the card; `pipeline_book` and `bp.py pipe book` print it.
5. Everything stays in `templates/pipeline.json` as numbers: the +3 cushion, the 200 trades, the 60 % months, the Sharpe bar.

## Non-goals

- No prop simulator in the pipeline: no eval odds, no payout odds, no account rule files, no fees line, no "stands alone / helper"
  label, no 75 % funded table, no payout set build. That code (pipe_prop, pipe_funded, pay_build) is not called by the pipeline
  any more. Deleting it is a separate clean-up, after this lands.
- **The group step goes (the owner, 2026-10-18: "remove it").** `bp.py pipe mix` and `bp.py pipe portfolio` (pipe_mix.py,
  pipe_portfolio.py, the runner's portfolio call, the MCP tools and Lab buttons that reach them, the `mix` and `portfolio` blocks of
  `pipeline.json`, their tests) are removed in this change. Judging a group comes back on the Desk, with sizing.
- No change to the blueprint law (`rules.json`, lines 1.x to 5.x) or to `gates.mode "law"`: the law mode stays as it is for the
  by-hand route.
- No sizing step. "How we modify the risk or strategy to trade an eval or a funded account" comes after, on the Desk.
- No change to what a card is, how stages 0-5 run the engine, or how the unseen days are read once (the 2026-10-17 repeat-read stop
  stays).

## Anti-goals

- A strategy must never pass on a win rate alone. The win-rate rule only ever adds to "profitable + beats random".
- No number typed in code. If the builder finds one, it goes in `pipeline.json`.
- The payout lock (`payout_enabled`) is never written by this change or by Claude. Retiring the Payout choice removes the choice; it
  does not enable anything.

## What changes, by file (the owner's decisions; how is the builder's)

- `blueprint/pipe_rules.py`: `PROFILES` keeps `live` only; `GATES` = ("law", "edge"); "edge" replaces "prop" as the shipped
  default. `winlane` and `funded` keys are read as before but the shipped file has them off. `prop_gates()` becomes `edge_gates()`.
  The WR settings page's write (`set_settings`) is refused for every profile (there is no WR profile).
- `blueprint/templates/pipeline.json`: `gates.mode "edge"`, a new `edge` block: `{"wr_cushion": 0.03, "min_trades": 200,
  "prop": {"sharpe": <bar>, "months_positive": 0.6}}`. The `prop`, `portfolio.eval/payout` and `mix` blocks go (or are left as
  notes). `pipeline_wr.json`, `pipeline_payout.json`, `pipeline_funded.json` are deleted.
- `blueprint/pipe_switch.py`: `CHOICES` = ("off", "live"); `LOCKED` empty; the bar's buttons are Off and On.
- `blueprint/pipe_gates.py`: one new pure row, **P3.15 win rate vs realized R:R** (win rate, breakeven, cushion, realized R:R in the
  text), from a box's trade nets; it is a stop in edge mode. Rows P3.11 / P3.12 (the WR lane) are not printed in edge mode.
- `blueprint/pipe_stages.py`: in edge mode `_holding` asks P3.2, P3.3 and P3.15 and nothing about eval odds; the pick's order
  (`_outward`, `_pick`) ranks by average trade instead of prop odds and still takes the MIDDLE box, never the best; stage 5's P5.9
  prop row and stage 6's prop block are not read; `_facts` adds the shown numbers of goal 3; stage 7 writes `tag` ("live" |
  "live+prop") and the numbers on the book card. Stage 6 reads P3.15 on the unseen trades next to the box net and line 4.4.
- `blueprint/oos.py` (or wherever stage 6's `only=("box", "4.4")` is honoured): the unseen read also returns the box's trade
  nets so stage 6 can judge P3.15 and compute the shown numbers.
- `blueprint/cli.py`, `homebase/claude_mcp/pipeline_tools.py`, `homebase/static/charts/lab.js`: `pipe mode` offers off | live;
  `pipe profile` and the WR settings page go; the Payout page and `pipe payout` go from the Lab menu and the CLI; the Book card
  shows the tag and the shown numbers. `pipeline_control` offers off | live.
- Tests: `tests/test_pipe_prop_gates.py`, `test_pipe_profiles.py`, `test_pipe_switch.py`, `test_pipe_winlane.py`,
  `test_pipe_funded.py`, `test_pipe_gates.py`, `test_pipe_stages.py`, `test_pipe_rules.py` updated to the one mode; a new test
  for P3.15 (win rate exactly at breakeven + cushion passes, one point under fails; a box with no losing trade: realized R:R
  undefined, the row passes with the text saying so) and for the tag (both ways).
- Existing ideas on disk: their stage cards were judged under prop mode. They are left as they are; `bp.py pipe rerun <name>`
  re-judges one. The audit's 4 candidates stopped by engine-file changes are rerun once this lands (a follow-up, the owner's word).

## Constraints

- House law: judge the average of the variants, never the best cell. Stage 1's loose map check stays exactly as prop mode runs it
  today: half the boxes profitable (`variant.map_share` 0.5) and at least one box above $0 with 200 trades (the `gates.variant`
  overlay `{region_boxes: 1, pick_boxes: 1, floor_part: 0.0}` moves to the `edge` block unchanged). The stops above are the picked
  box's. The pick stays the middle box.
- The unseen days are read once per idea family; no change.
- At most 2 backtests at once in desk hours. No change.
- `bp.py pipe payout enable` is never run and the lock file is never written.

## Calls I made (the owner can overturn any)

- The +3 cushion and P3.15 are asked on the build days AND the unseen days. The owner said "+3 everywhere"; asking it on both
  reads is my reading.
- The pick's order without prop odds: by average trade, middle box first. The owner only said the prop sim leaves. This applies in mode "law" too (the only change to law mode): the prop odds code is out of the pick.
- The new row is **P3.15** (P3.13 is the WR lane's target row, P3.14 the funded row; both stay on old cards and are not printed in
  edge mode).
- A stale profile word in `~/.homebase/pipeline_profile` (for example "funded") reads as live; it does not raise.
- The prop Sharpe bar ships at **1.0** (annualized, daily). The owner did not name a number; it is a `pipeline.json` number.
- Months positive counts months with at least one trade, as `winning_months` does today.
- "law" mode is kept untouched rather than deleted, so the by-hand blueprint route still has its full ladder.
- Retiring WR / Payout / Funded = removing the choices and their files now, deleting their code later.

## Left to the builder

- Where exactly P3.15 is computed for the unseen days (stage 6 after `oos.test`, or inside the read), as long as it is one function
  on trade nets used by both reads.
- The Book card's layout for the tag and the shown numbers.
- The test fixtures' shape.

## Addendum, 2026-10-18 later: stage 6 is a 3:1 walk-forward (the owner)

The owner: "the 3 month is the new build days and the 1 month is the new unseen days, it should still be 75% in and 25% out of
sample"; keep the early stages (0-5 on the build days, they weed out weak ideas) and replace the final test. Decisions taken in
the walk-forward session are in `docs/superpowers/specs/2026-10-18-walkforward-3to1-design.md`, section 3.

- **Data.** Stage 6 still runs the one read of the test days (oos.test) so every box of the locked table has its trades on
  2025-07-01 .. latest. With the build store (every box, 2021-09-22 .. 2025-06-30) that is every box on every day: no new engine
  switch. The read's own lines (box, 4.4, 4.1-4.9) become labels.
- **Months.** The calendar's months; the first month is dropped when it starts after its 7th day (2021-09). Step k picks on months
  k..k+2 and trades month k+3; every month from the 4th on is tested once.
- **The pick per window** = the pipeline's own: the boxes whose window trades hold P3.2 (average trade above $0), P3.3 (at least
  `walkforward.window_trades`, 15 -- Claude's call: the 200-trade rule scaled to 3 of 45 months) and P3.15; the middle of them by
  average trade (`_outward`). No box holds: the month stands aside ($0, no trade).
- **Stops on the stitched record** (rows P6.1-P6.4): net above $0; win rate at or above the realized-R:R breakeven + 3 points;
  beats 95 % of random tables (each month's pick's exit cell, drawn from that month's pool -- the build pool before 2025-07, the
  read's own pool after -- with the lock's draw seed and draws, summed over months); and at least `variant.region_trades` (200)
  trades in all.
- **Book card.** `numbers.unseen` = the stitched record; `walkforward` = {picks by month, months stood aside, `next`: the pick on
  the last 3 whole months = the box to trade this month}. The tag reads the stitched record.
