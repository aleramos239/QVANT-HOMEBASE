# Desk Makeover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One place per job on the Desk (set up, see if it can trade, switch, size, take away), one word per thing, every
reason a strategy cannot trade said on screen, with the per-account gear and variant sets built into that layout.

**Architecture:** The server keeps one record per thing: teams only in the Desk's `groups.json`, variant sets in a new
Desk `variants.json`, readiness only in `compute_readiness` (its checks gain `strategy` / `account` / `fix`). The page is
rebuilt on those records: a self-sorting sidebar, Today with one "Needs a look" list, a strategy page led by a status line
and the Set up card with a gear per account. The engine's trade decisions do not change.

**Tech Stack:** Python 3 (FastAPI Desk `homebase/server.py` + charts service `homebase/charts`, pytest), plain JS desk
page (`homebase/static/desk/*.js`, `homebase/static/apple/desk.js`, `node --test tests/js`).

**Spec:** `docs/superpowers/specs/2026-11-02-desk-makeover-design.md` (approved by the owner 2026-11-02, "Approve it").
Read it first; section numbers below (4.3, call 10, ...) point into it. It absorbs the UI half (Tasks 7-12) of
`docs/superpowers/plans/2026-11-02-desk-per-account-settings-and-variants.md`, whose Tasks 1-6 are done on this branch
(77f4b9bd..3cbe143b).

## Global Constraints

- Branch `claude/desk-account-settings`, worktree `.worktrees/desk-account-settings`. Never commit or merge to `main`:
  every commit on main ships to the live VPS (vpssync). Merge only on the owner's word.
- Never touch the live ports 8850/8852 or the VPS. Check on the Practice Desk: `tools/fake_desk --lab` +
  `homebase.charts --replay`.
- No restyle (owner 2026-10-27, again 2026-11-02 "Keep the look"). New pieces reuse `.sd`, `.sec`, `.feed-row`, `.seg`,
  `.switch`, `.mcap`, `.hb-field`.
- Every `homebase/static/desk/*.js` edit bumps its `?v=` in `homebase/static/index.html` AND its `DESK_PINS` entry
  (version, sha16) in `tests/test_desk_page.py`. Every `homebase/static/apple/*.css` edit bumps
  `homebase/static/apple/manifest.json`. The failing pin test prints the new sha16.
- One word per thing, everywhere on the Desk (page text, toasts, confirms, journal page text):
  Team (not group / account group / cycle / Desk group) · Take turns (not rotation / cycle) · Shadow (not practice /
  "Shadow, forward") · Desk ON / OFF (not armed / disarmed) · ON / OFF (not enabled) · LIVE (real money only) ·
  PROP (prop-firm eval or funded PA) · Archive (not Remove / Hide / Unassign / Remove from Desk) · Delete ·
  Day stop (not Day take / profit lock / day lock) · Lab.
- Every account that is not paper asks before a change that can send more (bigger size, NQ instead of MNQ, Most up, a
  new account), exactly as `saveSolo` asks today (`isRealAcct`, `homebase/static/desk/book.js:136`). PROP is a label
  only; it never skips an ask.
- Gear defaults: MNQ (the strategy's default contract), 1 contract, Most 20 MNQ / 2 NQ (`acctsize.most_default`).
  Switching a row's contract: Contracts → 1, Most → that contract's default, $ risk kept. $ risk keeps the 10% leeway
  (`acctsize.row_size`).
- A Save rewrites only the rows the owner changed. A plain `{account, qty}` row (or an own-size strategy's row) is never
  turned into Contracts / $ risk by itself (call 10).
- Owner, "Gear only": a row's Most is its only cap; the strategy-wide `max_qty` binds only rows without their own Most.
- A strategy is in a team OR a variant set, never both.
- Data files are renamed `<name>.retired`, never deleted. No `rm -rf` (the safety hook blocks it). Never bare `git stash`.
- Known red before you start (only these may stay red): pytest 9 (alphatrader_wizard, charts_js, desk_app_names,
  labrun_restart x2, server_lab promoted, tester_api prop rules, tester_range_parity, topstepx_wizard); node 7
  (charts-wp5, keyboardfocus, lab-charts-catchup, deskaddaccounts pins).
- Python: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest`. `homebase/engine_groups.py`,
  `homebase/labcfg.py`, `homebase/labdesk.py` are shims: edit the `homebase/desk/` copies.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A Save with nothing touched.** Ticking one more account (solo or set) and saving leaves every other row's contract,
   size, $ risk, Most and `stop_after` exactly as they were, and an own-size strategy's plain rows stay plain.
   (Test in Task 6 for the set Save; test in Task 14 for the page's `soloBody`.)
2. **A stale page.** While `DESK_STALE` is true (the Desk does not answer), no status line or "Needs a look" says
   "Ready" in green; they say the state is the last known one. (Tests in Tasks 13 and 15.)
3. **A set member archived or deleted.** The set shrinks; under 2 members it dissolves; no booking changes.
   (Test in Task 5.)
4. **A leftover `deskgroups.json` team whose id the Desk already has.** The Desk's team is never overwritten.
   (Test in Task 3.)
5. **A non-NQ strategy.** A GC strategy's gear offers only MGC / GC with their own Most defaults, never MNQ / NQ.
   (Tests in Tasks 8 and 14.)

---

### Task 1: Money path before NQ: Vest's contract map survives a restart; NQ-round tests (call 13)

**Files:**
- Modify: `homebase/broker/vest.py` (`self._roots` :230, written :481, capped :486)
- Test: `tests/test_vest_adapter.py`, `tests/test_bot_kill.py`, `tests/test_engine_lab.py`, `tests/test_engine.py`, `tests/test_labdesk_wave_a.py`

**Interfaces:**
- Produces: Vest keeps `{order id | position id: root}` in `state_dir() / f"vest_roots_{account_id}.json"` (written with
  `core.jsonio.write_json`, loaded in `__init__`, same cap as memory). A missing or broken file loads as `{}`.
- Produces: nothing new for the engine; each NQ-round test below either passes as is or the function is fixed to read the
  round's contract through `Engine._rcfg(st, cfg)` (per-account Task 3).

- [ ] **Step 1: Write the failing tests**
  - `test_vest_roots_survive_an_adapter_restart` (tests/test_vest_adapter.py): an adapter records order `"o1"` placed on
    `"NQ"`; a new adapter for the same account (same `state_dir`, monkeypatched to `tmp_path`) has `_roots["o1"] == "NQ"`,
    and a fill frame for `"o1"` parsed through `parse_account_state(..., roots=adapter._roots)` books on `"NQ"`.
  - On an NQ round (row `contract: "NQ"`, strategy default MNQ), each of these sends or reads `"NQ"`, never `"MNQ"`:
    `test_kill_both_filled_flattens_an_nq_round_as_nq` (`_kill_both_filled`, desk/engine_kill.py:384; next to
    tests/test_bot_kill.py:500), `test_lab_end_unfilled_cancels_an_nq_round` (`_lab_end_unfilled`, engine_lab.py:1462;
    next to tests/test_engine_lab.py:3579), `test_lab_close_retry_closes_an_nq_round_as_nq` (`_lab_close_retry`,
    engine_lab.py:1630), `test_reconcile_account_reads_an_nq_round` (`reconcile_account`, engine.py:1202; next to
    tests/test_engine.py:300), `test_guard_placed_guards_an_nq_round` (`_guard_placed`, engine.py:1158; next to
    tests/test_labdesk_wave_a.py:90).
- [ ] **Step 2: Run, expect FAIL** (at least the Vest test): `pytest tests/test_vest_adapter.py tests/test_bot_kill.py tests/test_engine_lab.py tests/test_engine.py tests/test_labdesk_wave_a.py -q`
- [ ] **Step 3: Implement** the persisted map (pattern: `HeldBook(state_dir() / f"vest_held_{account_id}.json")`,
  vest.py:217); save after each write at :481. Fix any engine function whose NQ-round test failed.
- [ ] **Step 4: Run, expect PASS** (same command).
- [ ] **Step 5: Commit** `"Desk: Vest remembers each order's contract across a restart; NQ-round tests for kill, end, close, reconcile, guard"`.

Because this task lands first, the gear (Task 14) offers NQ on Vest accounts too; no "NQ disabled on Vest" state is built.

---

### Task 2: One readiness check: `strategy` / `account` / `fix`, and the nine traps (4.8)

**Files:**
- Modify: `homebase/desk_app/readiness.py` (`compute_readiness` :77), `homebase/desk/labdesk.py` (`_say_notes` :290,
  `set_book`, `set_enabled`), `homebase/desk/engine_lab.py` (`_lab_position` :1063, the `place_skipped` at :1085)
- Create: `tests/test_readiness_traps.py`
- Modify (exact-dict tests that gain keys): `tests/test_server_lab.py:544-575`, `tests/test_labdesk.py:1168-1305`, `tests/test_server.py:174-807`

**Interfaces:**
- Produces: a check is `{"level": "ok"|"info"|"warn"|"bad", "label": str, "detail": str}` plus, only when they apply,
  `"strategy": <desk id>`, `"account": <account id>`, `"fix": "reconnect"|"open"|"turn_on"|"limits"|"team"`.
  Fix meanings for the page: reconnect = Reconnect that account; open = open that strategy's page; turn_on = Turn on;
  limits = Set limits; team = Open team.
- Produces: `LabDesk.unbooked: dict[str, str]` (desk id → why), filled from `lab_unbooked` notes in `_say_notes`,
  cleared for a strategy when `set_book` gives it rows or `set_enabled(name, True)` succeeds. Memory only
  (shortcut: a Desk restart forgets it; persist it if the owner misses a line after a restart).
- Produces: `Engine.position_blocks: dict[tuple[str, str], tuple[str, str]]` ((strategy, account) → (desk day, reason)),
  set where `_lab_position` refuses, cleared when an entry for that pair is placed. Readiness reads only today's.
- Existing lines gain keys: OFF while booked → `strategy`, `fix: "turn_on"`; accounts stopped for today, inactive today,
  runner stopped for the day, booked after the session opened → `strategy`; split-team member with no account →
  `strategy`, `fix: "team"`; an account line → `account` (and `fix: "reconnect"` when it is offline).

- [ ] **Step 1: Write the failing tests** in `tests/test_readiness_traps.py` (build with `tests/labdesk_util.mkdesk`; a
  second Lab strategy via `store.put(rec(name="pp2"), root)` before `ld.refresh()`; follow the `compute_readiness` calls
  in tests/test_labdesk.py:1168-1305). One test each:
  - `test_taken_off_its_accounts_says_so_with_turn_on`: a `lab_unbooked` note for `lab_pp` → one check
    `level "warn"`, `strategy "lab_pp"`, `fix "turn_on"`, `detail` starting `"Taken off its accounts ("` and ending
    `"). It is OFF: set it up and turn it on to trade again."`; after `set_book` with a row it is gone.
  - `test_two_strategies_on_one_market_and_account_warn_each`: `lab_pp` and `lab_pp2`, both ON, both NQ, both on `a1` →
    two checks, `level "warn"`, `account "a1"`, `fix "open"`, `detail == "Shares NQ on ..a1 with pp2: one waits while the other holds a trade."` (and the mirror for pp2).
  - `test_a_position_block_is_bad_with_its_account`: `engine.position_blocks[("lab_pp","a1")] = (today, "The account already holds NQ. Check it.")`
    → `{"level": "bad", "label": "pp", "detail": "The account already holds NQ. Check it.", "strategy": "lab_pp", "account": "a1"}`; yesterday's entry → no line.
  - `test_a_window_outside_the_desk_day_says_shadow_only`: a record whose `labcfg.span(rec) is None`, ON →
    `level "info"`, `strategy`, `detail == labcfg.SAY_EVENING`.
  - `test_lab_switch_file_missing_with_booked_records_is_bad`: `lab.on is False` and a store record with a non-empty
    sidecar book (`labrun.store.booked`) → one check `{"level": "bad", "label": "Lab strategies", "detail": "The Lab switch file (lab_desk.on) is missing: no Lab strategy can trade."}`; with no booked record → no line.
  - `test_runner_down_is_one_bad_line`: `lab._runner()` → `{"alive": False, "age_s": 95}` and one Lab strategy ON with an
    account → exactly one check `{"level": "bad", "label": "Lab runner", "detail": "The Lab runner has not answered for 95 s: no Lab strategy can trade."}` (`age_s` None → "The Lab runner is not running: no Lab strategy can trade.").
  - `test_offline_account_names_each_booked_strategy_with_reconnect`: `a1` disconnected, `lab_pp` booked on it →
    `{"level": "bad", "label": "pp", "detail": "..a1 is offline.", "strategy": "lab_pp", "account": "a1", "fix": "reconnect"}`
    and no separate plain line for `a1`; an offline account with nothing booked keeps its line with `account` + `fix "reconnect"`.
  - `test_desk_off_is_one_line`: Desk OFF with 3 strategies ON → exactly one Mode line, no `strategy` key.
  - `test_limits_needed_first_says_so_with_set_limits`: a Lab strategy ON that `check_book` would refuse with
    `SET_LIMITS_FIRST` → `level "warn"` (spec call 4: red), `strategy`, `fix "limits"`, `detail == "Limits needed first: it runs in shadow until they are set."`
  - `test_split_team_member_without_account_has_fix_team`: the existing line, now with `strategy` and `fix "team"`.
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_readiness_traps.py -q`
- [ ] **Step 3: Implement** in `compute_readiness` (one helper per trap is fine; "same market" = the price root from
  `labcfg.row_symbol(rec, row)`'s root, among ON strategies with a book). Labels are the strategy's label (`name[4:]` for
  a `lab_` id without one). Update the exact-dict tests named under Files for the added keys only.
- [ ] **Step 4: Run, expect PASS:** `pytest tests/test_readiness_traps.py tests/test_server_lab.py tests/test_labdesk.py tests/test_server.py -q` (only the known red).
- [ ] **Step 5: Commit** `"Desk readiness: each line names its strategy, account and fix; nine silent traps now said"`.

Ruling for the page (Task 13): "Needs a look" lists `warn` and `bad`; `info` lines (today's "switched OFF: it will not
trade" and "no account: runs in shadow" at readiness.py:115/:123, the evening window) show only on that strategy's
status line, so a Desk with six Shadow strategies does not show six "needs a look" rows. The spec (4.8) says every
non-ok check; raise this with the owner in the hand-off.

---

### Task 3: Teams are one record (the Desk's), with the leftover file adopted, and Team OFF ends Take turns

**Files:**
- Modify: `homebase/desk/engine_groups.py` (`write_group` :257; add `adopt_teams`, `retire`, `new_team_id`),
  `homebase/routes/setup.py` (team path of `setup_save` :108; remove `group_follow` :159),
  `homebase/routes/groups.py` (remove `POST /api/groups`, keep `/api/groups/delete`), `homebase/server.py` (call the
  adoption once after the engine is made), `homebase/charts/deskgroups.py` (read-only),
  `homebase/charts/tester_routes/desklab.py` (remove `desk_post` if unused after, `cycle_follow`, `POST/OPTIONS /deskgroups/{what}`, `DESKGROUP_ACTIONS` :39), `homebase/charts/tester_api.py:241` (re-export)
- Test: `tests/test_desk_setup.py`, `tests/test_engine_groups.py`, `tests/test_tester_deskgroups.py` (rewritten for the
  read-only adapter), `tests/test_fake_desk_lab.py:1309-1318` (uses `/api/setup` instead of `POST /api/groups`)

**Interfaces:**
- Produces: `deskgroups.load(root: Path | None = None) -> list[dict]` = `[{"id", "name", "members"}]` read from
  `(root or paths.state_dir()) / "groups.json"` (the Desk's file; `{}`/unreadable → `[]`). `merged` and `summarize` stay.
  `KINDS`, `_kind`, `apply`, `preview`, the write lock and `deskgroups.json` handling go. `GET /deskgroups` and
  `/deskgroups/results` stay and read through `load()`.
  (Ruling: a direct file read, like the charts service's other `.state` reads; on the Practice Desk the team results
  panel reads the Mac's own `.state`, which only affects backtest results of practice teams.)
- Produces: `Engine.new_team_id() -> str`: the first `"g<n>"` (n from 1) not in `self.groups`.
- Produces: `/api/setup` team body accepts `"team": ""` → a new team with `new_team_id()`; the answer's `"team"` is the id.
- Produces: a team Save whose `members` include a strategy of another team takes it out of that team in the same Save:
  the other team's record is written, and the mover's book is written once, from the new team (never empty on the way).
- Produces: a team Save writes each member's Take turns = `on and mode == "cycle"` (Team OFF → Take turns OFF; ON in
  Take turns mode → back ON). A member that is in a variant set is refused: `"It is in the set {name}."` (409) — the set
  store arrives in Task 5; until then this check reads an empty list.
- Produces: `Engine.adopt_teams(path: Path) -> list[str]`: each team in that `deskgroups.json` whose id is not in
  `self.groups` is added through `group_checked` + `write_group` as `{name, members (Lab strategies the Desk holds),
  accounts: [], mode: "cycle", on: False}`; a clash or a `GroupError` leaves the Desk untouched; returns the added ids.
- Produces: `engine_groups.retire(path: Path) -> bool`: renames `path` to `path.name + ".retired"` when `path` exists and
  no `.retired` file exists yet; never deletes, never overwrites. `server.py` calls
  `engine.adopt_teams(p)` then `retire(p)` with `p = labrun.store.root().parent / "deskgroups.json"` once at start.

- [ ] **Step 1: Write the failing tests**
  - `test_leftover_team_is_adopted_off_with_no_accounts` and `test_adopted_file_is_renamed_retired_once` (a second
    start finds nothing to adopt and leaves the `.retired` file as is).
  - `test_a_leftover_team_id_clash_never_overwrites_the_desk_team` (Review Focus 4): Desk `g1` = `{name "Apex", accounts ["a1"], on True}`,
    file `g1` = `{name "Old", members [...]}` → Desk `g1` unchanged.
  - `test_team_off_switches_take_turns_off_for_its_strategies` and `test_team_on_in_take_turns_mode_switches_it_back_on` (`team(c, **kw)` in tests/test_desk_setup.py).
  - `test_a_new_team_gets_the_next_free_id` (`"team": ""` → `"g1"`, then `"g2"`).
  - `test_team_save_moves_a_member_from_another_team_in_one_book_write`: exactly one `book_updated` journal line for the mover.
  - `test_dead_team_routes_are_gone`: `POST /api/groups` and `POST /api/groups/follow` → 404/405;
    `POST /api/tester/desklab/deskgroups/create` → 404/405; `GET /api/tester/desklab/deskgroups` lists the Desk's teams.
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_desk_setup.py tests/test_engine_groups.py tests/test_tester_deskgroups.py -q`
- [ ] **Step 3: Implement** the signatures above. Keep `write_group`'s journal line; its own rotation switch-on for cycle
  members can stay, since the team Save's Take turns write runs after it.
- [ ] **Step 4: Run, expect PASS:** the same, plus `tests/test_fake_desk_lab.py tests/test_lab_groups.py tests/test_engine_groups_simultaneous.py -q`.
- [ ] **Step 5: Commit** `"Desk: a team is one record, kept by the Desk; a leftover charts team file is adopted then retired; Team OFF ends Take turns"`.

---

### Task 4: Families go (server and page)

**Files:**
- Delete (git rm): `homebase/charts/deskfamilies.py`, `tests/test_tester_deskfamilies.py`
- Modify: `homebase/charts/tester_routes/desklab.py` (GET `/deskfamilies` :705, OPTIONS :710, POST `/deskfamilies/{what}` :719, import :31),
  `homebase/server.py` (retire `deskfamilies.json` beside Task 3's retire), `tools/fake_desk.py:730-732`
- Modify (page): `homebase/static/desk/groups.js` (`DESKFAM` :63, `famOf` :66, `famOfStrat` :67, `famShort` :68,
  `archivedId` :69 if only families use it, `famArchived` :70, `takeFamilies` :71, `loadDeskFamilies` :79 and its call
  :25, `familyPost` :90, `famVariant` :104, `familyView` :117, `deleteFamily` :137), `labdesk.js` (`archiveFamily` :416,
  `restoreFamily` :441, `DESKFAM` 527/530, `familyView` :566, `famOf` :702, `VIEW.k === "family"` at 435/553/566/702),
  `popups.js` (`DESKFAM` :422, `familyPost` 432/445/450, `deleteFamily` :434, `addFamily` :477, family columns),
  `strategy.js` (`famShort` 15/20, `DESKFAM`/`famArchived` 25/27, `famBlocks` 27-32), `views.js` ("family" view at 18 and 161),
  `index.html` (`#familyNewName` + Add family 923-924, `?v=` bumps); `tests/test_desk_page.py` pins
- Test: `tests/js/desklabdesk.test.mjs:1824, :1843`, `tests/js/desklab.test.mjs:1408` (removed or rewritten), `tests/test_desk_page.py`

**Interfaces:**
- Consumes: `engine_groups.retire(path)` (Task 3), called for `labrun.store.root().parent / "deskfamilies.json"`.
- Produces: no `family` view kind; a saved `hb_view` of kind `"family"` falls back to Today.

- [ ] **Step 1: Write the failing tests:** `test_family_routes_are_gone` (GET and POST `/api/tester/desklab/deskfamilies*` → 404/405);
  `test_desk_page_has_no_families` in `tests/test_desk_page.py` (`familyNewName`, `loadDeskFamilies`, `familyView` absent from
  the page HTML); `test_families_file_is_retired_once`.
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_tester_desklab.py tests/test_desk_page.py -q`
- [ ] **Step 3: Implement:** remove the code listed; the sidebar keeps working with loose rows until Task 12 rebuilds it.
- [ ] **Step 4: Run, expect PASS:** `pytest tests/test_tester_desklab.py tests/test_desk_page.py -q` and `node --test tests/js` (known red only).
- [ ] **Step 5: Commit** `"Desk: families go; their file is renamed .retired"`.

---

### Task 5: Variant sets: the Desk's store, its routes, and the suggestions

**Files:**
- Create: `homebase/desk/variants.py`, `homebase/routes/variants.py`, `tests/test_desk_variants.py`
- Modify: `homebase/server.py` (register beside `routes.groups`, server.py:187), `tools/fake_desk.py` (register like
  `routes.groups` at :1364), `homebase/routes/status.py` (`"variants"` beside `"groups"` at :75), `tests/engine_trace.py:18`
  (add `variants.json` to the traced state files), `homebase/routes/setup.py` (Task 3's set check reads this store)

**Interfaces:**
- Produces (`homebase/desk/variants.py`, `root` = `engine._root`, the folder `GroupMixin._groups_path` puts
  `groups.json` in, engine_groups.py:68; the routes pass it):
  - `TAILS = ("_r075", "_r1", "_r15", "_r2", "_fast", "_flex", "_desk", "_apex300", "_s25", "_s60", "_g10", "_g25")`
  - `class VariantError(ValueError)` (words the page may show)
  - `load(root: Path, names: set[str] | None = None) -> dict` = `{"sets": [{"id": "v1", "name": str, "members": [str], "labels": {str: str}}], "dismissed": [[str]], "next": int}`.
    With `names`, members not in `names` are dropped and a set left under 2 members is removed; the file is written only
    when that changed (Review Focus 3).
  - `apply(root: Path, action: str, body: dict, *, teams: dict, names: set[str]) -> dict` (the new `load()`),
    `ACTIONS = ("create", "rename", "label", "split", "dismiss")`. Rules: 2+ members, each a Desk Lab strategy; a strategy
    in at most one set; a team member is refused `"It is in the team {name}."`; labels 1-12 chars; `split` removes the set
    (bookings untouched); `dismiss` stores the sorted member list. Written with `core.jsonio.write_json`.
  - `set_of(root: Path, name: str) -> dict | None`
  - `suggest(names: list[str], *, in_team: set[str], sets: list[dict], dismissed: list[list[str]]) -> list[dict]` =
    `[{"stem": str, "members": [str], "labels": {str: str}}]`: a name ending in one or more `TAILS` has stem = the name
    without them; 2+ names per stem; skips names in a set or a team and member lists already dismissed. Labels:
    `_r075` "0.75R", `_r1` "1R", `_r15` "1.5R", `_r2` "2R", any other tail its text without "_" ("fast"); several tails
    joined by a space ("1.5R fast").
- Produces (routes): `POST /api/variants/{action}` → `{"ok": True, "sets": [...]}` or 400 `{"detail": words}`; journal
  `variants_changed` (action, set id, members). `GET /api/status` gains `"variants": {"sets": [...], "suggest": [...]}`
  (set names are the stem without `lab_`).

- [ ] **Step 1: Write the failing tests** (`tests/test_desk_variants.py`):
  - create / one set per strategy / team member refused with `"It is in the team Apex."` / label of 13 chars refused /
    split leaves every book as it was / dismiss is remembered.
  - `test_an_archived_member_shrinks_the_set_and_under_two_dissolves` (Review Focus 3).
  - `suggest(["nq_cb_r1", "nq_cb_r15", "nq_cb_r2", "gc_x"], in_team=set(), sets=[], dismissed=[])` →
    `[{"stem": "nq_cb", "members": ["nq_cb_r1", "nq_cb_r15", "nq_cb_r2"], "labels": {"nq_cb_r1": "1R", "nq_cb_r15": "1.5R", "nq_cb_r2": "2R"}}]`;
    the same with `dismissed=[["nq_cb_r1", "nq_cb_r15", "nq_cb_r2"]]` → `[]`; with `in_team={"nq_cb_r2"}` → the other two only.
  - `test_status_carries_the_sets_and_suggestions` and `test_a_team_save_refuses_a_set_member` (tests/test_desk_setup.py).
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_desk_variants.py tests/test_desk_setup.py -q`
- [ ] **Step 3: Implement** the signatures above.
- [ ] **Step 4: Run, expect PASS:** the same plus `pytest tests/test_server.py tests/test_fake_desk_lab.py -q`.
- [ ] **Step 5: Commit** `"Desk: variant sets live on the Desk (store, routes, suggestions); nothing combines by itself"`.

---

### Task 6: `/api/setup` for a set (one variant per account), and `/api/book` keeps one variant per account

**Files:**
- Modify: `homebase/routes/setup.py`, `homebase/routes/strategies.py` (`set_book` :140)
- Test: `tests/test_desk_setup.py`

**Interfaces:**
- Consumes: `variants.set_of` (Task 5), `_rows(cur, accounts, hold, qty=None, settings=None)` (setup.py:32),
  `Engine.lab_open_on(name, account)` (engine_lab.py:905), `checked` / `write` in setup.py.
- Produces: `POST /api/setup` body `{"set": id, "accounts": [..], "pick": {account: strategy}, "settings": {account: {contract?, size?, qty?, risk_usd?, most?}}, "turns": bool, "hold"?: bool, "on": bool}`.
  Each member's book = the accounts that picked it (rows through `_rows` with `settings`); `turns` and `on` apply to every
  member (an unpicked member runs in shadow). One `setup_saved` journal line with `set`, `pick`, `on`.

- [ ] **Step 1: Write the failing tests:**
  - `test_set_save_books_each_variant_on_the_accounts_that_picked_it` (A on a1, B on a2, both ON, one `setup_saved`).
  - `test_set_save_refuses_an_unpicked_account_or_a_stranger_whole` (nothing written).
  - `test_set_save_refuses_moving_an_account_mid_trade`: `lab_open_on(A, "a1")` true, a1 moved to B → 409, detail
    `"..a1 has an open trade on 1R; change it once it is flat."`
  - `test_set_save_with_nothing_touched_keeps_every_row` (Review Focus 1): a2 gains a tick; a1's row
    `{contract: "NQ", size: "risk", risk_usd: 500, most: 2, stop_after: "win"}` comes back identical; a plain `{account, qty}` row stays plain.
  - `test_book_refuses_an_account_another_variant_has`: `POST /api/book` puts a2 on A while B has a2 → 409, detail
    `"..a2 is on 1.5R of the set nq_cb: one variant per account."`
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_desk_setup.py -q`
- [ ] **Step 3: Implement**, reusing the solo path per member (new accounts first, then removals, as `write` does).
- [ ] **Step 4: Run, expect PASS:** `pytest tests/test_desk_setup.py tests/test_engine_groups.py -q`
- [ ] **Step 5: Commit** `"Desk: Set up a variant set in one save, one variant per account"`.

---

### Task 7: One ON/OFF path, and the dead routes go (4.7, 4.9)

**Files:**
- Modify: `homebase/charts/tester_routes/desklab.py` (`desklab_onoff` :543, `desklab_write` :548),
  `homebase/routes/accounts.py` (remove `accounts_add` :368, `diag_permissions` :598, `selftest_order` :626)
- Test: `tests/test_tester_desklab.py` (:152, 202-206, 246-262, 270, 471), `tests/test_server.py:146,159,500,518`,
  `tests/test_topstepx_routes.py:182,323`, `tests/test_alphatrader_routes.py:204`, `tests/test_vest_routes.py:187`,
  `tests/test_claude_mcp.py:471`, `tests/test_netguard.py:124,198,276`, `tests/test_audit_chart_accounts.py`, `tests/test_selftest_fallback.py`

**Interfaces:**
- Produces: `POST /api/tester/desklab/onoff` for a strategy with `labrun.store.booked(name)` → 409
  `DESKLAB_TAKE_OFF` ("Take its accounts off on the Desk first."), checked under `store.write_lock()` like :411/:423.
- Produces: `POST /api/accounts/add`, `GET /api/diag-permissions`, `POST /api/selftest-order` → 404/405.
  `POST /api/accounts/add-many` stays. `activity.js:216,228` keep drawing old `selftest` journal lines.
- The page needs no change: `setDeskLab` (views.js:92) already toasts the refusal's `detail`
  ("Could not switch …: Take its accounts off on the Desk first.").

- [ ] **Step 1:** `grep -rn "selftest-order\|selftest_order\|accounts/add\"\|diag-permissions" homebase tools deploy` — if a
  non-test caller exists, keep that route and write why in the report.
- [ ] **Step 2: Write the failing tests:** `test_chart_switch_refuses_a_booked_strategy` (booked → 409, record unchanged;
  unbooked Shadow → switched as today); `test_dead_account_routes_are_gone`. Tests that used a removed route only as a
  vehicle (netguard, connectors) move to `add-many` or another live route; tests of the removed route itself go.
- [ ] **Step 3: Run, expect FAIL:** `pytest tests/test_tester_desklab.py tests/test_server.py -q`
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run, expect PASS:** every test file listed under Files.
- [ ] **Step 6: Commit** `"Desk: a booked strategy is switched only on the Desk; unused account routes go"`.

---

### Task 8: What the page needs to know: each strategy's contracts, and PROP accounts

**Files:**
- Modify: `homebase/desk/labdesk.py` (`status_view` :998-1030), `homebase/desk_app/brokers.py` (beside `is_vest_key` :42,
  `is_tsx_key` :52, `is_atr_key` :62), `homebase/routes/status.py` (account view :44-48)
- Test: `tests/test_labdesk.py`, `tests/test_desk_brokers_prop.py` (new), `tests/test_server.py`

**Interfaces:**
- Produces: `status_view(name)["contracts"] -> list[str]`, the strategy's default execution contract first, then the other
  size of the same market when one exists: NQ record (exec MNQ) → `["MNQ", "NQ"]`; GC (exec MGC) → `["MGC", "GC"]`; a
  market with no pair → `[root]`. `status_view(name)["most_default_by"] -> {contract: _most_default(name, contract)}`
  (`{"MNQ": 20, "NQ": 2}`).
- Produces: `brokers.is_prop(a: AccountCfg) -> bool` = not `a.paper` and (`a.prop` non-empty, or the keyring key is a
  TopstepX / AlphaTrader / Vest key, or the account name upper-cased starts with `"PA"` or contains `APEX`, `LUCID`,
  `TOPSTEP`, `FUNDEDNEXT`, `ALPHA`). The status account view gains `"prop": bool`.

- [ ] **Step 1: Write the failing tests:** `test_status_view_gives_contracts_and_their_most` (NQ and a GC record, Review
  Focus 5); `test_is_prop` (`PAAPEX3265980000023` demo → True; `1552885` live → False; `paper-6` → False; a TopstepX key → True);
  status carries `prop`.
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_labdesk.py tests/test_desk_brokers_prop.py tests/test_server.py -q`
- [ ] **Step 3: Implement** with `contracts` / `labcfg.exec_symbol` for the pair.
- [ ] **Step 4: Run, expect PASS** (same).
- [ ] **Step 5: Commit** `"Desk status: each strategy's contracts and their Most; prop-firm accounts marked"`.

---

### Task 9: Page removals (4.9) that need no new layout

**Files:**
- Modify: `homebase/static/desk/acctset.js` (keep the pure `AcctSet` :6-45; remove `ACCT_SET`, `ACCT_SAVING`,
  `acctSetRow` :49 … `saveAcctSet` :132), `index.html` (`#acctSetOverlay` 826-858, `#algoOverlay`, the `algo-visibility.js`
  tag :16, the old Connect help text :750 → "Tick it on a strategy's Set up card.", the `demo.js` tag :994, `?v=` bumps),
  `core.js` (`HIDDEN_ALGOS` :41, `closeAcctSet` :89), `popups.js` (`renderAlgoMgr` :377, `openAlgoMgr` :410,
  `toggleAlgoHidden` :518), `labdesk.js` (`removeLabRow`, `removeLabStrat`, `duplicateLabStrat` and their buttons),
  `views.js` (`removeDeskLab` :105), `homebase/static/desklab.js` (its `AlgoVisibility` uses), `demo.js` (`?demo=1` preview)
- Delete (git rm): `homebase/static/algo-visibility.js`, `tests/js/algo-visibility.test.mjs`, `homebase/static/desk/demo.js`
  after moving `testFire` / `testFireWords` into `strategy.js` beside the built-in page (they go with it in Task 17)
- Modify tests: `tests/test_charts_js.py:24-27`, `tests/js/deskswitches.test.mjs`, `tests/js/deskwords.test.mjs` (its
  `testFire` slice now reads strategy.js), `tests/js/deskbook.test.mjs:305-317`, `tests/js/desklabdesk.test.mjs:562`,
  `tests/js/deskpage.mjs` (no demo.js), `tests/test_desk_page.py` (`DESK_PINS`: drop `demo`, bump the rest)

**Interfaces:**
- Produces: the strategy list no longer hides anything by a stored list; a strategy is shown by its state (Task 12).

- [ ] **Step 1: Write the failing test:** `test_removed_pieces_are_gone` in `tests/test_desk_page.py`: the page HTML has none
  of `acctSetOverlay`, `algoOverlay`, `algo-visibility.js`, `desk/demo.js`, `duplicateLabStrat`, `removeLabStrat`,
  `HIDDEN_ALGOS`, "under Accounts (+ Assign an account)".
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_desk_page.py -q`
- [ ] **Step 3: Implement** the removals. The demo preview also owns `const DEMO` (core.js:14) and ~64 `DEMO` guards across
  desk/*.js: remove the constant and every guard, keeping the non-demo side of each (`DEMO_TAG` in book.js is a different
  thing and stays). The account Day stop fields in the removed sheet were its only copy outside the Accounts popup.
- [ ] **Step 4: Run, expect PASS:** `pytest tests/test_desk_page.py tests/test_charts_js.py -q` and `node --test tests/js` (known red only).
- [ ] **Step 5: Commit** `"Desk page: the settings panel, Manage algos, Remove from Desk, Duplicate and the demo preview go"`.

---

### Task 10: Words, the PROP tag and the pure `AcctSet` helpers

**Files:**
- Modify: `homebase/static/desk/acctset.js` (`AcctSet`), `book.js` (`acctTag` beside `isDemoAcct` :129, `DEMO_TAG` :8,
  `acctRow` :20-30), `activity.js` (:91, :455, :492), `strategy.js` (:333), `topbar.js` (pill words :162-173),
  `popups.js` (`dayTakeBox` :274 / `setDayTake` :281 words), every desk/*.js and `homebase/static/desklab.js` string that
  uses a replaced word (Global Constraints list), `index.html` (`?v=`), `tests/test_desk_page.py` pins
- Test: `tests/js/acctset.test.mjs`, `tests/js/deskwords.test.mjs`

**Interfaces:**
- Produces (pure): `AcctSet.words(row, variant?, most?) -> string`, parts joined `" · "`: variant first, then size
  (`"1 NQ"` / `"3 MNQ"` for contracts, `"$500 risk"` for $ risk, `"×3"` when the row names no contract), then the contract
  after a $ risk (`"$500 risk · MNQ"`), then `"most 20"` when `most`, then `tag(row)`. Ruling: the order follows the approved
  mockup ("FLEX · 1 NQ", "FAST · $500 risk · MNQ"), not the older plan's "NQ · $500 a trade · 1.5R". Callers that show a
  plain row pass `{...row, contract: row.contract || lab.contracts[0]}`.
- Produces (pure): `AcctSet.ownWords(usd) -> "its own $650 a trade"`.
- Produces (pure): `AcctSet.switchContract(form, to, mostBy) -> form` (qty 1, most `mostBy[to]`, $ risk kept).
- Produces (pure): `AcctSet.needsAsk(prev, next, real, contracts = [])` also true when
  `contracts.indexOf(next.contract || contracts[0]) > contracts.indexOf(prev.contract || contracts[0])` (the bigger
  contract is later in the strategy's `contracts`, Task 8: MNQ → NQ, MGC → GC) and when a contracts row's Most is raised
  or removed (today only a $ risk row checks Most).
- Callers of the old `words(r, most)` move to `words(r, undefined, most)` (activity.js:492, and any other
  `grep -n "AcctSet.words" homebase/static`).
- The limits dialog's "Most contracts per account" (index.html:806) reads "Most contracts, for accounts without their
  own Most" (owner, "Gear only").
- Produces: `acctTag(id) -> "PAPER" | "PROP" | "LIVE" | "DEMO"`: PAPER when env is paper, PROP when the status says
  `prop`, LIVE when env is live or the account is unknown, else DEMO. The ask still keys on `isRealAcct`, never on the tag.

- [ ] **Step 1: Write the failing tests** (`tests/js/acctset.test.mjs`; old `words` asserts are replaced):

```js
assert.deepEqual(AcctSet.switchContract({contract:'MNQ', size:'contracts', qty:3, most:20}, 'NQ', {MNQ:20, NQ:2}),
                 {contract:'NQ', size:'contracts', qty:1, most:2});
assert.equal(AcctSet.switchContract({contract:'MNQ', size:'risk', risk_usd:500, most:20}, 'NQ', {MNQ:20, NQ:2}).risk_usd, 500);
assert.equal(AcctSet.words({contract:'NQ', size:'contracts', qty:1}, 'FLEX'), 'FLEX · 1 NQ');
assert.equal(AcctSet.words({contract:'MNQ', size:'risk', risk_usd:500, qty:1}, 'FAST'), 'FAST · $500 risk · MNQ');
assert.equal(AcctSet.words({contract:'MNQ', qty:3}), '3 MNQ');
assert.equal(AcctSet.words({qty:3}), '×3');
assert.equal(AcctSet.words({contract:'MNQ', size:'contracts', qty:3, most:20}, undefined, true), '3 MNQ · most 20');
assert.equal(AcctSet.ownWords(650), 'its own $650 a trade');
const C = ['MNQ', 'NQ'];
assert.equal(AcctSet.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, true, C), true);
assert.equal(AcctSet.needsAsk({qty:1}, {contract:'NQ', qty:1}, true, C), true);
assert.equal(AcctSet.needsAsk({contract:'NQ', qty:1}, {contract:'MNQ', qty:1}, true, C), false);
assert.equal(AcctSet.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, false, C), false);
assert.equal(AcctSet.needsAsk({contract:'MNQ', size:'contracts', qty:1, most:20}, {contract:'MNQ', size:'contracts', qty:1, most:30}, true, C), true);
```

  and in `tests/js/deskwords.test.mjs`: `acctTag` for a paper, a prop (env demo), a live and an unknown account →
  `PAPER`, `PROP`, `LIVE`, `LIVE`; `test('the page uses one word per thing')`: the page HTML's visible strings contain none
  of "account group", "account cycle", "ARMED", "DISARMED", "Remove from Desk", "Day take", "practice" (case-insensitive,
  outside code comments and identifiers; the test strips comments and checks string literals and text nodes).
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/acctset.test.mjs tests/js/deskwords.test.mjs`
- [ ] **Step 3: Implement** the helpers, `acctTag`, the caller moves and the word sweep.
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: one word per thing; PROP tag; the gear's pure helpers"`.

---

### Task 11: Teams on the page come from the Desk

**Files:**
- Modify: `homebase/static/desk/popups.js` (`renderGroupMgr` :416 without kind, families or the orphans block :456;
  `removeOrphanCycle` :466 goes; `addGroup` :485; rename :493; `moveToGroup` :494/:510), `groups.js` (`kind` whitelist :13;
  delete :389; header comment :2), `labdesk.js` (`soloTeam` :574, :701), `activity.js` (:242, :355),
  `homebase/static/desklab.js` (kind at :445, :508), `index.html` `?v=`, pins
- Test: `tests/js/deskviews.test.mjs` (or the test file that covers the team manager today: `grep -ln renderGroupMgr tests/js`)

**Interfaces:**
- Consumes: `ST.groups` (`/api/status` `groups_view`: `{id: {name, members, accounts, ...}}`), `/api/setup` team body with
  `"team": ""` for a new team (Task 3), `POST /api/groups/delete`.
- Produces: `teams() -> [{id, name, members}]` from `ST.groups`, replacing every `DESKGROUPS.groups` read; `DESKGROUPS`
  and its charts load go. New / rename / move send the team's whole current body to `/api/setup`; delete posts
  `/api/groups/delete` to the Desk.

- [ ] **Step 1: Write the failing tests:** `addGroup("Apex")` posts `['/api/setup', {team: '', name: 'Apex', members: [], accounts: [], mode: 'cycle', on: false}]`;
  `moveToGroup('lab_pp', 'g2')` posts one `/api/setup` for `g2` with `lab_pp` added; the team manager has no "kind", no
  family column, no "Remove orphan".
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/<that file>`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk page: teams come from the Desk; new, rename, move and delete go through it"`.

---

### Task 12: The sidebar sorts itself (4.2)

**Files:**
- Modify: `homebase/static/desk/strategy.js` (`renderSide` :2-67, `labSideRow` :183), `views.js` (`toggleSide` :24,
  `SIDE_FOLD` :23), `labdesk.js` (the `renderSide` call in `render()` :704), `index.html` `?v=`, pins
- Create: `tests/js/deskmakeover.test.mjs` (pattern: slice the page HTML from `tests/js/deskpage.mjs` by section comments, run in `vm`)

**Interfaces:**
- Consumes: `DeskLab.inShadow(s, book)` (desklab.js:711), `ST.book`, `ST.strategies`, `ST.variants.sets` (Task 5),
  `readinessShown` checks (Task 2 keys), `acctTag` (Task 10).
- Produces (pure): `sideSections(names, st, sets) -> {trading: Row[], shadow: Row[], off: Row[]}`, `Row = {id, label, set?: id, warn: bool, pnl: number|null}`:
  Trading = ON with at least one account; Shadow = ON with none; Off = OFF. A set is ONE row (`id` = set id, `set` set);
  its state is the best of its members (trading > shadow > off); its members have no rows. A-Z by label inside a section.
  `warn` = a `warn`/`bad` check with that strategy (or any member). Shadow `pnl` is shown dimmed as "would be".
- Produces: sections Today · Trading · Shadow · Off · N (folded by default; Archive · N under it) · Teams ("None yet · add
  one" when empty) · Accounts (name, tag, today's $, "offline") · Activity. `SIDE_FOLD` keys `trading`, `shadow`, `off`,
  `teams`, `accts`, `act`; old keys (`strat`, `cyc`, `f:*`) are ignored.

- [ ] **Step 1: Write the failing tests** (`tests/js/deskmakeover.test.mjs`):
  - three strategies (ON+booked, ON no account, OFF) land in trading / shadow / off; names `zeta` and `Alpha` sort `Alpha`, `zeta`.
  - a set of `lab_a_r1` + `lab_a_r2` (one booked) → one trading row with `set: 'v1'`, no member rows.
  - a strategy with a `warn` check has `warn: true`.
  - Off is folded with no stored fold; Teams with no team shows "None yet · add one".
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/deskmakeover.test.mjs`
- [ ] **Step 3: Implement** `sideSections` and the new `renderSide` (`.sd.live` / `.sd.shadow` / `.sd.off` / `.sd.warn` icons as today).
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk sidebar: Trading, Shadow, Off sort themselves; a set is one row"`.

---

### Task 13: Today: a headline that counts right, one "Needs a look" list (4.4, 4.8)

**Files:**
- Modify: `homebase/static/desk/groups.js` (`dayHeadline` :450, `todayRow` :604, `todayFoot` :624), `labdesk.js`
  (Today inline :553-562, ready strip :672-690), `topbar.js` (`renderChecks` :254, `openChecks` / `closeChecks` :271-272,
  `readyWord` path; keep `readinessShown` :327 and acks :349-358; the pre-open banner goes and the rows
  `preopenChecks` :366 builds join "Needs a look" through `lookRows`), `popups.js`
  (`dismissReady` :139), `settings.js` (the ready part of `renderHealth` :358), `homebase/static/apple/desk.js` (Today
  inspector: Readiness section :72 goes; Desk :73 and Notices :74 stay, Notices empty → "No notices"), `index.html`
  (`#checksOverlay` :954, `#readyStrip`, new `#needsLook`, `?v=`), pins; `apple/desk.css` + `apple/manifest.json` only if CSS changes
- Test: `tests/js/deskmakeover.test.mjs`, `tests/test_desk_page.py`

**Interfaces:**
- Consumes: Task 2 check keys; `ST.variants`; `acctTag`.
- Produces (pure): `dayCounts(names, st) -> {trading: n, accounts: n, shadow: n}`; `dayHeadline(names)` line 2 =
  `"2 strategies trading on 2 accounts · 6 in shadow · today +$412 (Live +$310 · Demo +$102)"` (singulars "1 strategy",
  "1 account"; money part as `dayMoney()` gives it today).
- Produces (pure): `lookRows(checks, stale) -> [{text, fix, strategy?, account?}]` = the `warn` / `bad` checks after
  `readinessShown`, each `text` = `label + ": " + detail`. Header `"Needs a look · N"`; none → `"Ready: nothing needs a look"`;
  `stale` → one row `"The Desk is not answering: this is the last known state."` and never the green line (Review Focus 2).
- Produces: fix buttons: reconnect "Reconnect", open "Open", turn_on "Turn on", limits "Set limits", team "Open team".
- Produces: the toolbar shield word stays ("Ready" / "3 need a look"); its click = `setView('today')` then scroll `#needsLook` into view.

- [ ] **Step 1: Write the failing tests:** `dayHeadline` line 2 for 2 trading on 2 accounts + 6 shadow (exact string
  above); 1 and 1 → "1 strategy trading on 1 account · 0 in shadow · ..."; `lookRows` drops `ok` / `info`, keeps fix;
  `lookRows([], false)` → [] and the page says "Ready: nothing needs a look"; `lookRows([...], true)` never yields the
  green line; `tests/test_desk_page.py`: no `checksOverlay`, no `readyStrip`, has `needsLook`.
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/deskmakeover.test.mjs` and `pytest tests/test_desk_page.py -q`
- [ ] **Step 3: Implement.** Off strategies are not listed on Today; Trading rows show each account's `AcctSet.words`.
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py tests/test_apple_skin*.py -q`
  (use the existing apple test file names: `ls tests | grep -i apple`).
- [ ] **Step 5: Commit** `"Desk Today: counts Trading and Shadow apart; one Needs a look list; the other ready lists go"`.

---

### Task 14: The Set up card and its gear (4.3 item 3, 4.5)

**Files:**
- Modify: `homebase/static/desk/labdesk.js` (`SOLO_DRAFT` :573, `soloNow` :576, `soloBody` :580, `soloDiff` :586,
  `soloEdit` :595, `soloStatus` :604, `soloSetupHtml` :618, `saveSolo` :643), `index.html` `?v=`, pins
- Test: `tests/js/deskmakeover.test.mjs`, `tests/js/desklabset.test.mjs` (existing Set up card tests; update)

**Interfaces:**
- Consumes: `lab.contracts`, `lab.most_default_by`, `lab.own_size` (Task 8 / existing), `AcctSet.*` and `acctTag` (Task 10),
  solo `/api/setup` with `settings` (done), set `/api/setup` (Task 6, wired in Task 16).
- Produces: one row per account: tick, name, tag, words, gear. The gear opens an inline sheet under that row (not an
  overlay): Variant (sets only, Task 16), Contract (one `.seg` button per `lab.contracts`), Size (`Its own` first and
  default when `lab.own_size`, then Contracts / $ risk + its number), Most contracts. Under the rows: Take turns (only with
  2+ ticked), Hold overnight, Save listing what changes (`soloDiff` lines with `AcctSet.words(..., true)`). No account
  ticked: "No account ticked: it runs in shadow." A team member shows "In team {name} → open" instead of the card.
- Produces (pure): `soloBody(name)` sends `settings[account]` only for rows the owner changed in the gear.
- The sheet edits `SOLO_DRAFT[name].settings[account]`; a repaint never rebuilds a sheet being typed in (keep the
  draft-driven pattern `soloEdit` uses today). A non-paper account asks at Save through `confirmDlg` when `needsAsk`.

- [ ] **Step 1: Write the failing tests:**
  - `soloBody` with one more account ticked and no gear change → `settings` has no entry for untouched rows (Review Focus 1);
    an own-size strategy's plain row stays `{account, qty}`.
  - switching a1's gear to NQ → its draft is `{contract: 'NQ', size: 'contracts', qty: 1, most: 2}`; switching back keeps $ risk.
  - a GC strategy (`contracts: ['MGC','GC']`, `most_default_by: {MGC: 20, GC: 2}`) offers MGC and GC only (Review Focus 5).
  - Take turns hidden with one account ticked; "No account ticked: it runs in shadow." with none.
  - a DEMO / PROP / LIVE account going MNQ → NQ asks; a paper one does not.
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/deskmakeover.test.mjs tests/js/desklabset.test.mjs`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: the Set up card with a gear per account: contract, size, most"`.

---

### Task 15: The strategy page in the approved order (4.3)

**Files:**
- Modify: `homebase/static/desk/labdesk.js` (`labDeskView` :156-205: new order; Limits section :194 leaves the body;
  `shadowStatsHtml` :135 goes; calendar `stratCal` :81, `scalMode` :115), `strategy.js` (`stratView` :267 lab branch,
  `labView` :233, `setupHtml` :324 goes, `labSetRows` / `labSetPick` go, `labCurveHtml` :212, `labResHtml` :192),
  `popups.js` (`setStratRr` :193 / `setLabSetting` :209 page callers go), `homebase/static/apple/desk.js` (strategy
  inspector :87-92: Setup :88 and Prop sim :82 go; sections Backtest, About, More), `apple/desk.css` + `apple/manifest.json`
  if CSS changes, `index.html` `?v=`, pins
- Test: `tests/js/deskmakeover.test.mjs`, `tests/js/desklabdesk.test.mjs` (update the order asserts), `tests/test_desk_page.py`

**Interfaces:**
- Consumes: Task 2 checks, `lookRows` fix words (Task 13), the Set up card (Task 14).
- Produces (pure): `statusLine(id, checks, st, stale) -> {level: "ok"|"shadow"|"off"|"warn"|"bad"|"stale", text, reasons: [{text, fix}]}`.
  Reasons = every non-`ok` check with `strategy === id`, plus every `warn` / `bad` check with neither `strategy` nor
  `account` (Desk-wide: Desk OFF, feed, Lab runner; a Desk-wide `info` such as Power stays off strategy pages). Level =
  worst of `bad` / `warn` among them, else the strategy's state; `info` never turns it red. Texts: Trading ready `"Ready · trades on 2 accounts · today +$412"`; Shadow
  `"Shadow · no account · would be +$80 today"`; Off `"OFF"`; stale `"The Desk is not answering: last known state."` (Review Focus 2).
- Produces: page order: back, title, sub-line (`"3 variants · 12:00 AM-4:00 PM ET · from the Lab"`; plain: window +
  "from the Lab"), ON/OFF switch → status line → Set up card → Today ("Activity ›") → Results: one calendar with an
  Accounts / Shadow `.seg` (Accounts first when booked, else Shadow) and `"Matched the backtest on 18 of 19 days ›"`
  (opens the day list, `DeskLab.matchLine`) → right panel Backtest (one row per variant; one row for a plain strategy),
  About (Signal, Window, Trades a day, Flat by, On the Desk since, any setting that differs from the Lab default read-only,
  "Edit limits" → `openLabLimits`), More (Flatten & turn off, Open in the Lab, Rename, Archive, Delete).
- Gone: Setup summary, strategy settings form, "Shadow, forward", the right panel's second Setup, Prop sim, Remove from
  Desk, Duplicate.

- [ ] **Step 1: Write the failing tests:** `statusLine` for: ready trading (exact text above); an offline booked account →
  `bad` with reason `{text: "pp: ..a1 is offline.", fix: "reconnect"}`; Desk OFF line appears on every strategy; the
  `warn` limits line is red with fix `limits`; an `info` evening-window line keeps level `shadow` and lists the reason;
  `stale` → level `stale`, never `ok`.
  Order test: the lab page's section headings in order Set up, Today, Results; no "Shadow, forward", no "Prop sim".
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/deskmakeover.test.mjs tests/js/desklabdesk.test.mjs`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk strategy page: status line first, Set up card, Today, one Results calendar; About and More on the right"`.

---

### Task 16: Variant sets on the page (4.5, call 12)

**Files:**
- Modify: `homebase/static/desk/views.js` (suggestion line + Combine sheet), `labdesk.js` (set page: Variant in each gear,
  set `/api/setup` Save, Results variant picker, Split in More), `strategy.js` (member page: "In set {name} → open"),
  `homebase/static/apple/desk.js` (Backtest per variant), `index.html` `?v=`, pins
- Test: `tests/js/deskmakeover.test.mjs`

**Interfaces:**
- Consumes: `ST.variants` (Task 5), `POST /api/variants/{action}` (Task 5), set `/api/setup` (Task 6), `sideSections` (Task 12).
- Produces (pure): `setDayPnl(set, accounts) -> number | null`: the members' ACCOUNT P&L only, never shadow dollars.
- Produces: suggestion line at the top of the Trading / Shadow list:
  `"3 strategies look like variants of nq_cb: Combine?"` → sheet with members and editable labels → "Combine" /
  "Not these" (`dismiss`). Combine stays disabled while two members share an account, naming it
  (`"..a1 has both 1R and 2R: untick one first."`). Combining never changes a booking.
- Produces: set Save body as Task 6 (`pick` from each row's Variant). Results: the Shadow side gets the set's labels as a
  `.seg` picker; "Matched the backtest" follows the picked variant; nothing sums variants' shadow dollars.
  More: "Split into separate strategies" (confirm, then `split`).

- [ ] **Step 1: Write the failing tests:** `setDayPnl` ignores shadow; Combine disabled while two members share an account;
  the set's gear lists the members' labels; a set Save body carries `pick` for every ticked account; the Results picker
  shows one variant at a time.
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/deskmakeover.test.mjs`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: a variant set is one strategy on the page; the Desk suggests, the owner combines"`.

---

### Task 17: The built-in (straddle) page goes — GATED on the owner's word

Do not start this task until the owner either OKs one read-only look at the VPS strategy config (and it shows no built-in
strategy) or says no built-in strategy runs there. If one runs, skip this task and say so in the hand-off.
The LIVE popup (`openLive` / `renderLive`, spec call 9) is opened only from this page's "Desk calendar" button
(strategy.js:287), so it goes here with the page, and stays if the page stays.

**Files:**
- Modify: `homebase/static/desk/strategy.js` (`stratView` :267 non-lab branch: eqChart/loadEq/EQ, RR fields, `testFire`,
  `testFireWords`, its Take-turns switch `rotationHtml` B:59 caller, the "Desk calendar" link :287), `book.js` (Assign menu
  :1 if only the built-in page uses it), `views.js` (`hideInfo` / `removeBuiltin` :141/:148, `openBuiltinInLab` :134),
  `labdesk.js` (`archiveBuiltin` :483, `restoreBuiltin`, `archivedBuiltins`), `popups.js` (`openLive` :537, `renderLive`
  :555), `index.html` `?v=`, pins
- Test: `tests/js/deskwords.test.mjs` (testFire tests go), `tests/test_desk_page.py`

- [ ] **Step 1: Write the failing test:** the page HTML has no `testFire`, `openLive`, `archiveBuiltin`, `openBuiltinInLab`.
- [ ] **Step 2: Run, expect FAIL:** `pytest tests/test_desk_page.py -q`
- [ ] **Step 3: Implement** the removals.
- [ ] **Step 4: Run, expect PASS:** `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: the built-in strategy page goes (owner confirmed none runs)"`.

---

### Task 18: Whole check, Practice Desk walk-through, hand-off

**Files:** none new (screenshots go to the owner).

- [ ] **Step 1:** `pytest -q tests` and `node --test tests/js`: only the known red.
- [ ] **Step 2:** Practice Desk (`tools/fake_desk --lab` + `homebase.charts --replay`; never 8850/8852): (a) solo strategy,
  ..A MNQ ×3 and ..B NQ $500, one signal places both; (b) change ..B to MNQ during its open NQ trade → refused in words;
  (c) combine 3 variants, pick one per account, Save, a signal goes to each account's own variant; (d) take an account
  offline → red status line + "Needs a look" with Reconnect; (e) Desk OFF → one line; (f) Archive a strategy and bring it
  back; (g) Team OFF → its strategies' Take turns off; (h) a Shadow strategy switched from the chart side, a booked one
  refused there.
- [ ] **Step 3:** Screenshots of the sidebar, Today, a strategy page, the gear, a set's page and the suggestion line, sent
  to the owner with a short summary. Then the final whole-branch review (it also covers the per-account Tasks 1-6).
  Merge to `main` only on the owner's word.
