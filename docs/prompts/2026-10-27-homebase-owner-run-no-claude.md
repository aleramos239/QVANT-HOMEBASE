# Prompt: make Homebase fully usable by the owner, no Claude needed

Paste everything below the line into a fresh Claude Code chat opened in `~/ramos-quant-homebase`.

---

Act like a senior product engineer and software architect taking over a live trading app that works but still needs an AI
assistant behind it. Your job: make Homebase something the owner runs **alone, by clicking**, on all four surfaces: the
**Mac Desk**, the **Lab**, the **Charts**, and the **server (VPS) Desk** in Chicago. If the owner today has to ask Claude to do
something, or an agent does it with a script, the connector, `bp.py` or a hand edit, it needs a button, a form or a page.
Also clear out the dead weight and swap clumsy systems for simpler ones.

## Read first (in this order)

1. `CLAUDE.md` (house rules, binding) and the memory index it loads.
2. `.worktrees/MORNING-REPORT-2026-10-27.md` and `.worktrees/AUDIT-2026-10-27.md`. The clean-up (`claude/architecture-refactor`)
   and the redesign (`claude/ux-redesign`, which already holds the clean-up) are **built and tested but not merged**, plus
   `claude/ux-server-guards` on top. **Build on `claude/ux-redesign`. Do not start a third refactor.** Run
   `~/.claude/vault-recall/recall "<topic>"` before each area.
3. The surfaces: `homebase/desk_app/` + `homebase/static/desk/*.js` (Desk), `homebase/charts/` (Charts, Lab routes in
   `charts/tester_routes/`), `homebase/labrun/`, `homebase/labdesk.py`, `homebase/engine*.py`, `deploy/linux/` (server, vpssync).

## The goal, in the owner's words

- Everything usable without Claude: Desk, Lab, Charts, and the server Desk.
- **Lab → Desk runs the strategy exactly as tested**: same code, same settings, same box, same window, same exits, same sizing.
- On the Desk, change any strategy's **risk / size**, or **duplicate** it and change the **stop** or **RR**.
- **Send strategies from the Mac to the server** from the Mac app.
- Control the algos every way: duplicate, remove, delete, archive, restore, groups, and the rest (find what he forgot).
- Remove everything unused behind the scenes. Simplify anything that has an easier way.

## Rules you must not break

- **Trading behavior stays the same** unless this prompt asks for a change: the same orders, checks, fills and numbers. Every new
  control that adds risk on a LIVE account asks first and shows old → new. Lowering, tightening, OFF and unbooking never ask.
- **Nothing new lands ON.** Anything promoted, duplicated, imported or sent to the server lands OFF, unassigned.
- **The server never backtests** (`~/.homebase/no_backtests`). The server app stays Desk only. Every run, heat map, walk-forward
  and parity replay runs on the Mac, and its result is copied to the server.
- **The blueprint stays law** (`research/edge-library/BLUEPRINT.md` §2). In the app, the owner's own click is his word: the heat
  map runs only on his click, test months only on his click and only after his pick, one pick per table, every settings change
  counts as a try. No code picks a box. A duplicate with a new stop or RR is a **new try** of that idea: show this on the card and
  in its numbers. Never show a REAL verdict the six lines did not earn.
- **The pipeline stays off** and the payout pipeline stays gone: no buttons for them, never write `payout_enabled` or remove
  `pipeline/DISABLED`.
- **The server follows main** (`vpssync`). Work on branches. Merge to main only on the owner's word, after 16:15 ET or on a
  weekend, with every account flat. Every commit must import. Never hand-copy to the server.
- Sharpe = traded days only (`homebase/backtest/report.py` / `library.metrics`). Bars come from `barstore`. Never rebuild them.
- No new dependencies for things a few lines can do. Keep the existing layers from the refactor (`core/`, `data/`, `desk/`,
  `store/`, `desk_app/`, `charts/routes/`, `tester_routes/`).

## Phase 0: the "needs Claude" inventory (do this first, change nothing)

Build one table of every action the owner can do today, by surface, with how it is done now: **button / form / Claude chat /
connector tool / `bp.py` / script / hand edit of `~/.homebase` or `config.json` / terminal command**. Sources: every route
(Desk 56, Charts 133, Lab 65), every `mcp__homebase__*` tool, every `bp.py` command, every `deploy/` script, every file under
`~/.homebase` an agent has edited by hand (search the vault LOG and findings for "by hand", "copied", "edited"). Anything not
done by a button is a gap. Rank the gaps by how often the owner needs them. Show the owner the table before Phase 2.

## Phase 1: land what is already built

Rebase `claude/ux-redesign` (and the guards the owner wants) on main, re-run the full test suite and the parity checks the morning
report lists, and hand the owner a one-line merge plan. Merge only when he says so. Everything below builds on that tip.

## Phase 2: the features

Fill every gap from Phase 0. At minimum:

**Lab → Desk: exact parity**
- "Put on the Desk" saves a **frozen copy**: the strategy code, its settings and picked box, the market, bar, session/window, exits,
  sizing rule and cost model, with a code hash. The Desk runs that copy, never the Lab's live draft.
- The card shows "Same as tested ✓ (hash …)". If the Lab draft changes later, the Desk keeps the old copy and shows "New version in
  the Lab: Update?" with old → new.
- A **Parity check** button (Mac): replays the last N in-sample days on the Desk engine and in the tester, and lists any trade that
  differs (entry, exit, size, time). Use `engine/desk_parity` and the engine-parity recipe in the findings. Before the first ON on a
  LIVE account, ask if parity was never checked or failed.

**Desk strategy controls (Mac and server)**
- Edit: $ risk or contracts, daily loss/take, max trades, window times, accounts, mode (shadow / paper / demo / live). Every edit
  shows old → new and goes into "Changes (7 days)" with Put back.
- **Duplicate as a variant**: copy a strategy, change stop, target/RR, size, window. It lands OFF, named "X · stop 1.5 ATR · 2R",
  with its diff from the original. A "Test this variant" button runs it on the Mac on the 3:1 in-sample months; the card shows it as
  untested until then.
- Rename, notes, tags. Archive, restore, remove from the Desk, delete (only when OFF and flat; archive first; delete moves to a
  trash that empties after 30 days, never a hard delete from the page).
- Groups: create, rename, delete, move strategies in and out, account cycle, follow. One page, no hidden saves.
- Flatten this strategy, day-lock an account, book/unbook accounts, all as buttons.
- Export a strategy (one file: frozen copy + record) and import one (lands OFF).

**Mac → server**
- "Send to server" on any Desk card or Lab strategy: copies the frozen copy and its walk-forward record to the server Desk over the
  existing SSH link, lands OFF there, and never starts a backtest on the server. Also "Send all changed".
- Each card shows "On server: same / older / missing / server only". A server page in the Mac app shows what the server runs, the
  vpssync status (today `./deploy/linux/vpssync.sh status`), the last deploy, service health and the logs, with buttons for the
  things that are terminal commands today (status, restart one service when flat, reload launch files when flat).
- Strategy code (`homebase/strategies`) still ships by vpssync. Only drafts, settings and records go by "Send to server". Say which
  path each item takes, in the page.

**Lab without Claude**
- Make a strategy from the form builder (`/drafts/form`, the blocks) or edit its code, validate, code check (3 chart trades), run the
  in-sample months, heat map (click), pick, test months (click), the six lines and the verdict: every phase is a button. What the
  `blueprint_*` tools do, the Lab does too, saved in the same places (`~/.homebase/ideas`, drafts, runs, Lab groups).
- Compare two runs side by side. Export trades and results (CSV). Show any run on the chart with one click, its indicators drawn.
- Data: coverage per market and a "Fill missing days" button (the tick job), with progress.

**Charts**
- Every chart-trading setting, account choice and indicator setting is a control on the page (no config edits).

**Settings and help**
- One Settings page for everything an agent now edits in `config.json` or `~/.homebase` (tester slots, accounts, alerts, paths),
  each with its current value and a plain line on what it does. Not the pipeline or payout locks.
- A Help page: "How do I …" for every task in the Phase 0 table, one short step list each.

## Phase 3: dead weight

List, then delete only what the owner approves:
- Code nothing calls: run an import graph plus route-hit and JS-reference checks; old route names that only point elsewhere once
  nothing uses them; retired lanes (`blueprint_build/lock/test`, rolling, the old split, old pick scheme). Keep their saved
  results readable as history.
- Old files: `homebase/config.json.*` backups, stray SVG/JSON at the repo root, old `out/` folders, merged or abandoned branches and
  worktrees (list them with the last commit date; the hook blocks recursive force-deletes, so use `git worktree remove`).
- Duplicate systems that do the same job (two ways to promote, two archive paths, two group stores): keep one.
- The pipeline code stays parked, not deleted, unless the owner says so.
For each item: what it is, who used it, proof nothing calls it, and the test that still passes after it is gone.

## Phase 4: simpler systems

Wherever there is an easier way, propose it with before → after and how many lines it saves, and build it only after the owner
picks it. Look at least at: how a strategy's settings are stored (one file per strategy?), how the Mac and server Desk share state,
the `/api/desk/{action}` and `/desklab/{what}` grab-bag routes (one route per action?), and any page that saves on blur.

## How to work

- One branch and worktree per work package (Lab→Desk parity, Desk controls, Mac→server, Lab buttons, Settings+Help, dead weight).
  Two packages never touch the same files. Each package: tests first, then code, then a headless-browser check of the page on a fake
  desk (findings: replay-mode check recipe; the hidden pane freezes CSS transitions), then the full suite.
- Changed engine or order code: run the engine-parity recipe (same broker calls on the recorded runs) and say the result.
- Talk to the owner in plain short words: the answer first, a small table, no jargon.

## What to hand back

1. The Phase 0 table: every action, before (how) → after (which button).
2. The control map: one page per surface showing every control and what it does.
3. The folder structure after the work, and what moved where.
4. The code, on branches, tested, each with a one-line merge plan.
5. The dead-weight list: deleted / kept and why / waiting on the owner.
6. The simplifications done, with before → after.
7. What is still not possible without Claude, and why (it should be only things the house rules keep for the owner's words in a
   chat, if any).
