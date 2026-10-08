# Strategy pipeline — plan B: in the app

> One fresh subagent a task, review between tasks, TDD inside each.

**Goal:** the pipeline (plan A, built) is usable from any Claude chat connected to Homebase and from the Lab page:
add an idea, start / pause the queue, see where every idea stands and why it stopped, approve or refuse a finisher, read
the book, and a Guide page a beginner can follow.

**Spec:** `docs/superpowers/specs/2026-10-07-strategy-pipeline-design.md` sections 5 and 6.
**What exists:** `research/edge-library/blueprint/pipe_runner.py` (`command(sub, ...)`, `status`, `listing`, `show`, `booked`)
behind `bp.py pipe add | list | show | start | pause | resume | approve | refuse | book`, each with `--json` and
`--root=<pipeline root>` (env `HOMEBASE_PIPELINE_ROOT`, default `~/.homebase/pipeline`).

## Global constraints

- The app (everything under `homebase/`) runs on the repo's `.venv` (Python 3.14) and must NOT import research code:
  it talks to the pipeline only by running `bp.py pipe ... --json` with the toolkit's Python, exactly as
  `homebase/claude_mcp/blueprint_tools.py` does for the blueprint (`toolkit()`, `_bp`, `_answer`). Reuse those; do not
  write a second subprocess wrapper.
- No tool or route can skip a stage, change a gate number, or touch the desk. A chat can add cards, start / pause /
  resume the queue, approve / refuse an idea that is awaiting the owner, and read.
- Nothing is started from the page 09:20-09:35 ET on weekdays (the same `Slots().quiet()` check `blueprint_run` makes).
- Words on screen: simple and minimal, no jargon (the owner's standing rule). "Idea", "Queue", "Book", "Stopped",
  "Passed", "Approve". Never "sub-idea", "signature", "store", "stage card".
- Tests: `.venv/bin/python -m pytest -q tests/<file> -p no:cacheprovider` from the repo root; JS: `node --test tests/js/<file>`.
- Do not restart any service (the lead does it, gated on running tester jobs). Commit only your files, path-limited.

## Task B1: the chat tools and the API routes

**Files:** create `homebase/claude_mcp/pipeline_tools.py`, `tests/test_claude_mcp_pipeline.py`, `tests/test_tester_pipeline.py`;
modify `homebase/claude_mcp/tools.py` (the Toolbox inherits the new mixin; the tool list includes its SPECS),
`homebase/charts/tester_api.py` (routes), `deploy/claude-mcp.md` (the tool list), and wherever the connector's
instructions text names the blueprint tools (one sentence for the pipeline), plus the arsenal catalog if it lists chat
tools from SPECS and a test pins the count.

Tools (names and one-line purposes; schemas in the style of `blueprint_tools.SPECS`):
- `pipeline_add(card, inbox=false)` — put one idea card in the queue. The description carries the card's shape and
  limits in plain words (from the spec, section 2) and says: call `blueprint_blocks` first to see the entry rules and
  indicators that exist.
- `pipeline_status(name=None)` — the queue (one row an idea: status, stage reached, why it stopped), or one idea in
  full (its card, every stage's verdict and numbers).
- `pipeline_control(action)` — `start` | `pause` | `resume` the runner.
- `pipeline_decide(name, decision, why=None)` — `approve` | `refuse` an idea that is awaiting the owner; refuse needs a
  reason. The description says: only on the owner's word.
- `pipeline_book()` — the book: the finishers' cards.

Routes (prefix `/api/tester`):
- `GET /pipeline` -> `{"runner": {"running", "paused"}, "counts": {...}, "ideas": [state rows], "book": [cards], "stages": [{"n", "name", "words"}]}`
  (`stages` = the eight stages with one plain sentence each, for the Guide; kept in ONE place in the app).
- `GET /pipeline/idea/{name}` -> `{"card", "state", "stages": [{"n", "name", "passed", "result", "lines": [{"line","passed","text"}], "text"}]}`.
- `POST /pipeline/run` body `{"action": "add"|"start"|"pause"|"resume"|"approve"|"refuse", ...}` -> `{"ok", "text"}`;
  `write_ok`, JSON body check, quiet window, 400 on a bad shape, the toolkit's refusal as `ok: false` with its text.

## Task B2: the Lab pages

**Files:** `homebase/static/charts/lab.js`, `labcode.js`, `lab.css`, `homebase/static/backtest.html` (script versions),
`tests/js/labcode.test.mjs` (+ a new test file if cleaner).

Three more views beside Strategies / Blueprint / Arsenal, in the Lab's existing look and components:
- **Queue**: one row an idea — name, family, a status chip (Waiting / Running / Stopped / Problem / Passed / In the book /
  Refused), a 0-7 stage dots strip, and the one-line reason. Click a row: the idea's card and each stage with PASS / FAIL
  and its lines. Buttons: Start / Pause (one button that says what it will do), and on an idea that passed: Approve,
  Refuse (asks for the reason). A count line on top ("12 ideas: 3 waiting, 1 running, 8 stopped").
- **Book**: one card a strategy — name, label (Stands alone / Helper), market, time of day, the two 30-day odds for
  LucidPro, hours, winning months, biggest day share, fast-trade share; click for the full card.
- **Guide**: the six steps of the spec's section 6, each one sentence and one button that is disabled until its step
  is allowed (grey, with the reason as its title), then the ladder of the eight stages with a plain sentence each and
  how many ideas sit at each now. Step 1's button opens a small form for the card (name, why, who loses, market, time
  of day, entry rule from a list, its setting and three values, up to five indicators with a reason each, sides) that
  posts `action: "add"`; a refusal shows the toolkit's own words.
Refreshes every 5 s while the view is open (one GET), never while hidden. Pure helpers (row text, chip, dots, the
guide's step states) live in `labcode.js` with tests.

## Task B3: go live

The lead: full app test suite + JS, chart-service restart gated on running tester jobs (never 09:20-09:35 ET), a look
at the three pages in the browser, `bp.py pipe list` on the real root (creates `~/.homebase/pipeline`).
