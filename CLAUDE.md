# Homebase — rules for assistants working in this repo

## One pipeline (2026-10-18)

The strategy pipeline is ONE pipeline (`docs/superpowers/specs/2026-10-18-one-pipeline-two-tags-design.md`): it judges a strategy at one
contract after costs, with no prop simulator, and tags a pass Live or Live + Prop. The WR, PAYOUT and FUNDED pipelines and the group step
are retired and their code is removed. Never bring the payout pipeline back or write its lock file (`payout_enabled`): only the owner can
decide that.

## Strategy work follows the blueprint (house law, 2026-10-05)

**To run an idea, use the pipeline first** (skill `pipeline`; chat tools `pipeline_add / pipeline_status / pipeline_control / pipeline_decide /
pipeline_book`; Lab > Queue, Book, Guide). It runs the blueprint's phases by code, stops at the first fail, and keeps the book. The rest of
this section is the by-hand route and the law the pipeline is built on.

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
- Build days (2021-09-22 → 2025-06-30) stay the window for the idea card, the heat map, the proof and the lock.
- Judge the average of all variants, never the best cell.
- Use the connector's `blueprint_*` tools for every phase (blocks, card, build, code check, lock, test, sim, portfolio, eval card, status).
  They run `research/edge-library/bp.py` and save each idea in the app (`~/.homebase/ideas`, a Lab draft, a tester run, a Lab group).
  Never write one-off test code for a strategy.
- `research/edge-library/judge.py` still scores the old rules (v2). A v2 verdict is not a blueprint verdict.
- Talk to the owner in simple, minimal words: the answer first, a small table, no jargon.
