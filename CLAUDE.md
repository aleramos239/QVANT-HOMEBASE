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

- Phases, in order: idea card → code check → build → lock → one out-of-sample test → before the eval → the eval.
- Build days: 2021-09-22 → 2025-06-30. All tuning happens here.
- Test days: 2025-07-01 → latest. One read, only for a locked strategy. Never for a quick look or "all data".
- Judge the average of all variants, never the best cell.
- Use the connector's `blueprint_*` tools for every phase (blocks, card, build, code check, lock, test, sim, portfolio, eval card, status).
  They run `research/edge-library/bp.py` and save each idea in the app (`~/.homebase/ideas`, a Lab draft, a tester run, a Lab group).
  Never write one-off test code for a strategy.
- `research/edge-library/judge.py` still scores the old rules (v2). A v2 verdict is not a blueprint verdict.
- Talk to the owner in simple, minimal words: the answer first, a small table, no jargon.
