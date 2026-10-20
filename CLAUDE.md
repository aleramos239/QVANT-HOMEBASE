# Homebase — rules for assistants working in this repo

## The server follows main by itself (owner, 2026-10-20)

The live Desk runs on the Chicago VPS. Every commit on this Mac's `main` reaches it by itself (`deploy/linux/vpssync.sh`, launchd
every 2 minutes): committed main only, never the working tree; it must import; it ships only when every account is flat and not
09:10-09:35 ET, and restarts only the services the change reaches. So: a change is on the server once it is COMMITTED to main --
commit every new file with the files that import it, and never commit half of someone else's work. Do not hand-copy files to the
server (push.sh, scp) unless the owner asks; check `./deploy/linux/vpssync.sh status` and `homebase/.state/vpssync.log`.

## The strategy pipeline is OFF (owner, 2026-10-20)

The pipeline, its Queue and its Book are switched off for now. Do not use it, start it, add to it or suggest it: no `pipeline_*` chat
tools (removed from the connector), no `bp.py pipe ...` (it refuses while `~/.homebase/pipeline/DISABLED` exists), no Lab Queue/Book
(hidden). Its launchd runner is parked in `~/Library/LaunchAgents/disabled/`, the nightly strategy-hunter task in
`~/.claude/scheduled-tasks-disabled/`, the `pipeline` skill in `~/.claude/skills-disabled/`. Only the owner turns it back on.
Agents still test strategies in Homebase, BY HAND: run each blueprint phase yourself with the `blueprint_*`, backtest, heatmap,
walkforward, montecarlo and prop_eval tools, read every result yourself (trades, per-year numbers, the walk-forward, the chart), and
report to the owner in plain words. Nothing is approved, booked or put on the Desk without the owner's word.
Never bring the payout pipeline back or write its lock file (`payout_enabled`).

## Strategy work follows the blueprint (house law, 2026-10-05)

Any request to build, test, backtest, optimize or judge a strategy or a strategy idea follows
`research/edge-library/BLUEPRINT.md`, section 2 (skill: `strategy-blueprint`). Read it before the first run.

- Phases, in order: idea card → code check → build → lock → the 3:1 walk-forward → before the eval → the eval.
- **Out-of-sample = the 3:1 walk-forward in BLOCKS over all data** (owner, 2026-10-18; spec
  `docs/superpowers/specs/2026-10-18-walkforward-3to1-design.md`): pick on 3 whole months, trade the next 1, then the next block
  (Jan-Mar pick → Apr trade, May-Jul pick → Aug trade, ...), stitch the traded months, 2021-09-22 → the last whole month. Every month
  is in-sample OR out-of-sample, never both. **Blocks are ALWAYS the default** -- Lab, Desk, pipeline, chat tools. ROLLING (pick on the
  last 3 months, trade the next 1, step a month) only when the owner picks it: the Lab's Range "3:1 rolling", or he tells Claude to use
  rolling (`walkforward(ratio="3:1", rolling=true)`) (the owner, 2026-10-18). The one test-days read
  (2025-07-01 on, once, for a locked strategy) is RETIRED, and so is "tune only on the build days". In the pipeline each window takes
  the pipeline's own pick (the middle passing box, never the best); the Desk card's "Unseen days" is this record, and the Desk only
  says when this month's pick differs: the owner changes the setting, nothing switches by itself.
- **Every route, no exceptions** (owner, 2026-10-19): the taught lane, by-hand engine runs and one-off checks too. "Check it OOS" /
  "test it out-of-sample" ALWAYS means the 3:1 block walk-forward, never a single read of the months after the build days. If a route
  has no walk-forward yet, say so and build it; never fall back to a single read. (2026-10-19 a single read was run on
  `owner_fvg_odir_15_nl_new` by mistake: those months are no longer blind for that rule.)
- Build days (2021-09-22 → 2025-06-30) stay the window for the idea card, the heat map, the proof and the lock.
- Judge the average of all variants, never the best cell.
- Use the connector's `blueprint_*` tools for every phase (blocks, card, build, code check, lock, test, sim, portfolio, eval card, status).
  They run `research/edge-library/bp.py` and save each idea in the app (`~/.homebase/ideas`, a Lab draft, a tester run, a Lab group).
  Never write one-off test code for a strategy.
- `research/edge-library/judge.py` still scores the old rules (v2). A v2 verdict is not a blueprint verdict.
- Talk to the owner in simple, minimal words: the answer first, a small table, no jargon.
