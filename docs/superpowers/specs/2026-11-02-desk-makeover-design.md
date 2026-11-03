# Desk makeover: one place per job, nothing silent

Date: 2026-11-02. Branch: `claude/desk-account-settings` (worktree `.worktrees/desk-account-settings`).
Audit it answers: `docs/superpowers/findings/2026-11-02-desk-audit.md` (main checkout, untracked; summary in the vault note
`30-Projects/Onyx-Trading/desk-audit-2026-11-02.md`).
Approved mockups (open in a browser; they link the Desk's own CSS through the brainstorm server, so read the markup if the
styles do not load): `2026-11-02-desk-makeover/strategy-page-and-sidebar.html`, `2026-11-02-desk-makeover/today-page.html`.
Absorbs: the UI half (Tasks 7-12) of `2026-11-02-desk-per-account-settings-and-variants-design.md` (server half, Tasks 1-6,
is done on this branch: 77f4b9bd..3cbe143b).

## 1. Intent

The owner, 2026-11-02: "fully inspect and analyze the desk, i want you to really clean it up and organize it, i dont want
duplicates, i dont want things that dont make sense or arent needed ... the controls on the app or per strategy or per
account, what shows, the way it shows, the panels and cards, the settings, everything i just want a really good make over,
upgrade, improvement, remove dead weight, easier to use and set up, impossible to get confused or mess up".

Earlier the same day: "i want to be able to adjust settings per account, have a settings icon per account where i can pick
the contracts per trade, mnq or nq, or the size of risk per trade which is default to mnq, then maybe if the strategy has
different variants like rr or etc i can pick in between them, im also thinking of combing them so if theres multiple of a
single strategy but different variants they become onw".

Why it matters: this Desk sends real orders. The audit found one job done in up to 6 places, words that mean two things,
and 8 ways a strategy can stop trading with nothing on screen saying so. Each of those is a way to lose money by mistake.

## 2. Goals, non-goals, anti-goals

Goals
- Every job has ONE place: set up a strategy (its Set up card), see if it can trade (its status line + Today's "Needs a
  look"), switch it (one ON/OFF path), size it (the gear on each account row), take it away (Archive or Delete).
- One word per thing (section 4.1), used everywhere on the Desk, in toasts, confirms and the journal's page text.
- Every reason a strategy cannot trade is said on screen, in words, where the owner is looking.
- Per-account settings and variant sets (the owner's request above) live inside this layout, not bolted on.
- Less: fewer pages, popups, buttons and files to keep in step.

Non-goals
- No restyle. Same skin, components, colours, fonts (owner 2026-10-27 "keep the current design", reaffirmed 2026-11-02
  "Keep the look"). New pieces reuse existing classes (`.sd`, `.sec`, `.feed-row`, `.seg`, `.switch`, `.mcap`, `.hb-field`).
- No change to how the engine decides a trade (gates, sizing math, door, timer). The server half of per-account settings
  is already built; this makeover changes what the page shows and which routes write.
- The Lab, Charts and Settings tabs are not part of it, except where a Desk word or link points into them.

Anti-goals (it fails even if it "works" when)
- A setting that trades is reachable from two places, or a state is said two ways on one row.
- A save quietly drops a field, or turns something off out of sight.
- Anything that used to be refused (owner check, LIVE ask, mid-trade contract change, hedge block) is no longer refused.
- The owner has to click a canvas page to answer a question (he answers in chat).

## 3. Constraints

- Every commit on `main` reaches the live VPS by itself (vpssync, when all accounts are flat and not 09:10-09:35 ET).
  Nothing merges to `main` without the owner's word. Work stays on this branch.
- Every `homebase/static/desk/*.js` edit bumps its `?v=` in `homebase/static/index.html` and `DESK_PINS`
  (`tests/test_desk_page.py`). Every `homebase/static/apple/*.css` edit bumps `homebase/static/apple/manifest.json`.
- Check on the Practice Desk (`tools/fake_desk --lab` + `homebase.charts --replay`), never on the live ports 8850/8852
  or the VPS. The VPS never backtests.
- Known failing tests at the branch start (only these may stay red): pytest 9 (alphatrader_wizard, charts_js,
  desk_app_names, labrun_restart x2, server_lab promoted, tester_api prop rules, tester_range_parity, topstepx_wizard);
  node 7 (charts-wp5, keyboardfocus, lab-charts-catchup, deskaddaccounts pins). Ledger:
  `.superpowers/sdd/2026-11-02-desk-per-account-settings-and-variants/`.
- Any account that is not paper asks before a change that can send more (bigger size, NQ instead of MNQ, a new
  account), as `saveSolo` does today (call 11). The 10%
  leeway on $ risk stays. A row without its own contract behaves exactly as today.

## 4. What the owner decided

Each item below was shown to the owner and answered. Quotes are his.

### 4.1 One word per thing ("Looks right", with the Today mockup)

| Word | Means | Replaces |
|---|---|---|
| Team | strategies + accounts that share one turn | group, account group, cycle, Desk group |
| Take turns | each trade goes to the next account | rotation, cycle, "one account a trade" |
| Shadow | ON with no account: writes down what it would do | practice, "Today, in shadow", "Shadow, forward" |
| Desk ON / OFF | the whole Desk may send orders | armed / disarmed |
| ON / OFF | one strategy's switch | enabled |
| LIVE | a real-money account, only that | live data login, LIVE popup wording |
| PROP | a prop-firm account (eval or funded PA) | DEMO on funded Apex accounts (my call, section 6) |
| Archive | off the Desk, history kept, can come back | Remove, Hide, Unassign, Remove from Desk |
| Delete | gone, history too | Delete history |
| Day stop | an account's day P&L target that flattens and stops it | Day take, profit lock, day lock |
| Lab | the backtest page | "backtest" page, Lab tab |

Variant: one of a set's strategies (section 4.5). Families are gone (4.6).

### 4.2 Sidebar ("Yes, drop them" + "Looks right")

Top to bottom: **Today** · **Trading** (ON with at least one account) · **Shadow** (ON, no account) · **Off · N** (folded
by default; **Archive · N** under it) · **Teams** ("None yet · add one" when empty) · **Accounts** · **Activity**.
- It sorts itself: a strategy moves section the moment its state changes. The owner never files anything.
- A variant set is ONE row. Its variants have no rows of their own.
- A row: the state icon (`.sd.live` bolt = Trading, `.sd.shadow` eye = Shadow, `.sd.off` = Off, `.sd.warn` when it has a
  "Needs a look" line), the name, today's $ (Shadow dims it: "would be").
- No variant-count tags on rows (they were cut off by the name); the page's sub-line says "3 variants".
- Account rows: name, tag (LIVE / PROP / DEMO / PAPER), today's $, "offline" when not connected.

### 4.3 Strategy page ("Looks right")

Top to bottom (see `strategy-page-and-sidebar.html`, markers 5-11):
1. Back, title, sub-line ("3 variants · 12:00 AM-4:00 PM ET · from the Lab"), the ON/OFF switch.
2. **Status line**, always: green "Ready · trades on 2 accounts · today +$412", or red with EVERY reason in words, each
   with its fix button where one exists (Reconnect, Turn on, Set limits, Open team).
3. **Set up card**, first on the page. One row per account: tick box, name, tag, its words ("FLEX · 1 NQ",
   "FAST · $500 risk · MNQ", "offline"), a gear. The gear opens an inline sheet under that row: **Variant** (sets only),
   **Contract** MNQ / NQ, **Size** Contracts / $ risk + its number, **Most contracts**. Under the rows: **Take turns**
   (only with 2+ accounts ticked), **Hold overnight**, one **Save** that says what changes. No account ticked: "it runs in
   shadow". A strategy in a team shows "In team X → open" instead of the card.
4. **Today**: per-account trade rows, refused lines, shadow lines, "Activity ›".
5. **Results**: one calendar with a Accounts / Shadow switch, and one line "Matched the backtest on 18 of 19 days ›"
   that opens the day list.
6. Right panel: **Backtest, per variant** (one row per variant; one row for a plain strategy), **About** (Signal,
   Window, Trades a day, Flat by, On the Desk since), **More**: Flatten & turn off, Open in the Lab, Rename, Archive,
   Delete.

Gone from the page (shown as gone in the approved mockup): the Setup summary, the strategy settings form
(Target / Risk / "Stop for the day", `labSetRows`), "Shadow, forward", the right panel's second Setup, Prop sim,
Remove from Desk, Duplicate.

### 4.4 Today page ("Looks right")

See `today-page.html`. Top to bottom:
1. Headline that counts right: "In session." + "2 strategies trading on 2 accounts · 6 in shadow · today +$412
   (Live +$310 · Demo +$102)". Trading and Shadow are counted apart, so "0 strategies on" next to 13 ON switches cannot
   happen again (`dayHeadline`, `homebase/static/desk/groups.js:450`).
2. **Needs a look · N**: one row per problem, ⚠ + words + its fix button. Empty: "Ready: nothing needs a look". This is
   the ONLY ready list on the Desk (4.8).
3. Session timeline (as today, `dayTimeline`).
4. Trading rows (with each account's words) and Shadow rows. Off strategies are not listed.
5. Right panel: **Desk** (Desk ON/OFF, "Accounts 2 of 3 connected ›", Today live, Today demo) and **Notices**
   ("No notices" when none). Readiness leaves the right panel.

### 4.5 Per-account settings and variant sets (earlier answers: "Real NQ too", "One per account", "Desk suggests, I OK")

- The gear (4.3 item 3) is the only place a strategy's size is set. It writes the book row's `contract`, `size`
  (`contracts` | `risk`, or Its own for a strategy that sizes itself: call 10), `qty`, `risk_usd`, `most` (server side
  done: `labcfg.row_ok/row_symbol/row_cap`, `book_row`).
  Defaults: MNQ, 1 contract, Most 20 MNQ / 2 NQ. Switching the contract resets qty to 1 and Most to that contract's
  default; $ risk is kept. A change that can send more on any account that is not paper asks first (call 11).
- A **variant set** is several Lab strategies (e.g. 1R / 1.5R / 2R of one idea) shown and set up as ONE strategy. Each
  account picks one variant in its gear ("One per account"). A strategy is in a team OR a set, never both.
- The Desk **suggests** combines from name tails (`_r075 _r1 _r15 _r2 _fast _flex _desk _apex300 _s25 _s60 _g10 _g25`)
  as one quiet line at the top of the Shadow/Trading list; the owner OKs ("Combine") or dismisses ("Not these", remembered).
  Nothing combines without him; combining never changes a booking.
- A set's page = the strategy page above with Variant in each gear and "Backtest, per variant" in the right panel.
  "Split into separate strategies" sits in More (bookings untouched).
- Full rules: per-account spec sections 2-7. This doc overrides only what section 6 below names.

### 4.6 Families go ("Yes, drop them")

The owner used families as "Shadow" / "Live trading" folders. The sorting sidebar does that job, and variant sets do the
variant fold. All family code goes (section 4.9). The data file is renamed, never deleted.

### 4.7 One ON/OFF path ("Remove them all")

A strategy with accounts is switched only through the Desk (`toggleStrat` → `/api/strategy`: owner check + cancel of
waiting entries). The chart-side `/api/tester/desklab/onoff` (`setDeskLab`, `homebase/static/desk/views.js:95`) stays
only for Shadow strategies the Desk does not hold. The server refuses it for a strategy that is booked on any account.

### 4.8 One readiness check ("Remove them all")

`compute_readiness` (`homebase/desk_app/readiness.py:77`) is the one source. Its checks (`{level, label, detail}`) gain
`strategy` (id, when about one), `account` (when about one) and `fix` (`reconnect` | `open` | `turn_on` | `limits` |
`team`). Today's "Needs a look" shows every non-ok check; each strategy's status line shows the checks with its id. The
other four places go: the System checks popup list (`renderChecks`/`openChecks`, `topbar.js`), the ready strip
(`#readyStrip`), the pre-open banner, and the ready part of Settings › Health. The toolbar's shield word stays
("Ready" / "3 need a look"); a click opens Today scrolled to "Needs a look".

New checks it must add (each was a silent trap in the audit, section 5):
- a new version, or limits removed, took the strategy off its accounts (it lands OFF and unbooked: say so, fix = Turn on);
- two strategies on the same market and account (one waits, or Hold overnight blocks the other);
- an open broker position, or one the Desk cannot read, blocks an entry;
- a window outside the Desk's 18:00-17:00 day: shadow only;
- the Lab switch file is missing (every Lab strategy disappears);
- a runner down or silent (today only on the strategy page);
- an account offline that a strategy is booked on (named with the strategy);
- the Desk is OFF (once, not per strategy);
- a team strategy with no account of its own in "one account each" mode.

### 4.9 Removals ("Remove them all")

| Goes | Where |
|---|---|
| Per-account Settings sheet panel and markup | `static/desk/acctset.js` panel (`openAcctSet` … `saveAcctSet`), `#acctSetOverlay` in `index.html`. KEEP the pure `AcctSet` helper (`formOf`, `rowFrom`, `words`, used by `desklab.js`, `strategy.js`, `activity.js`, `book.js`); it now backs the gear |
| "Show on home page" switches and Manage algos | `renderAlgoMgr`/`openAlgoMgr`/`toggleAlgoHidden` (`popups.js`), `HIDDEN_ALGOS`, `AlgoVisibility`; the Off section and Archive do this job |
| Families | `charts/deskfamilies.py`, its routes (`tester_routes/desklab.py:704-740`), `takeFamilies`/`loadDeskFamilies`/`familyPost`/`famVariant`/`familyView`/`deleteFamily` (`groups.js`), `archiveFamily`/`restoreFamily` (`labdesk.js`), `addFamily` + family columns in the team manager (`popups.js`), `famShort` in the sidebar. `deskfamilies.json` is renamed `deskfamilies.json.retired` once |
| Remove from Desk | `removeLabRow`/`removeLabStrat` (`labdesk.js`), `removeDeskLab` (`views.js:105`, already uncalled), the lab page's Remove button. Archive replaces it |
| Duplicate | `duplicateLabStrat` (`labdesk.js`) and its button |
| Team "Remove orphan" repair | `removeOrphanCycle` + the orphans block in `renderGroupMgr` (`popups.js`). A team becomes one record (section 6), so it cannot drift |
| Dead routes | `POST /api/groups` (`routes/groups.py:12`), `POST /api/accounts/add` (`routes/accounts.py:368`; keep `add-many`), `GET /api/diag-permissions` (`:598`), `POST /api/selftest-order` (`:626`), Desk group `kind` (`charts/deskgroups.py` `KINDS`, `_kind`) |
| Demo preview strategies | `static/desk/demo.js` (`?demo=1`), its `<script>` tag (`index.html:994`); `testFire`/`testFireWords` go with the built-in page below |
| Old Connect help text | `index.html:750` ("each strategy's page, under Accounts (+ Assign an account)") → points at the Set up card |
| Built-in (straddle) page | the non-lab part of `stratView` (`strategy.js:267`): RR fields, Test fire, its Take-turns switch, built-in archive/restore (`archivedBuiltins`, `archiveBuiltin`, `restoreBuiltin`, `removeBuiltin`, `openBuiltinInLab`). **Gate:** only after the owner confirms no built-in strategy is in the VPS config (section 8) |
| Strategy settings form | `labSetRows`/`labSetPick` (`strategy.js`), `setStratRr`/`setLabSetting` page callers (`popups.js`). Values stay as saved; About shows any value that differs from the Lab default, read-only |
| Setup summary | `setupHtml` (`strategy.js`); the status line + Set up card replace it |
| Prop sim in the right panel, second Setup in the right panel | `apple/desk.js` (`hbProp`, the inspector's Setup section) |
| "Shadow, forward" | `shadowStatsHtml` section (`labdesk.js:154`); the Results calendar's Shadow side replaces it |
| Account day stop outside the Accounts popup | the strategy-side and sheet copies; "Day stop" lives only in the Accounts popup (`dayTakeBox`/`setDayTake`, renamed) |

### 4.10 Fixed underneath (all were silent traps)

- Set up Save keeps each row's `size`/`risk_usd`/`stop_after`/`most`/`contract` (done on this branch, Task 1).
- Mid-trade contract change refused (done, Task 6).
- The traps in 4.8 become "Needs a look" lines.
- Team OFF also switches Take turns OFF for its strategies (my call, section 6).

## 5. Approaches

| | A: three steps | B: all at once |
|---|---|---|
| What | (1) removals + words, (2) sidebar + Today + one readiness, (3) strategy page + gear + sets; a merge after each | one branch, one practice walk-through, one merge |
| For | each step smaller to check; the owner sees progress live | no half-made page on the live Desk; one check of the whole; the gear is built once |
| Against | three ships, each with a mixed old/new page for days; step 3 rebuilds what step 1 touched | a bigger merge; nothing visible until the end |

The owner picked **B, "All at once"**. Dropped before asking: building the gear on today's page first and again in the
new layout (double work, and two different gears live for a while).

## 6. My calls (marked, for the owner to check while reading)

1. **PROP tag** for prop-firm accounts (eval and funded PA). Funded Apex PA accounts show DEMO today (their broker env is
   demo); PROP says what they are. LIVE stays only for real-money accounts. The rule for which accounts are PROP: an
   account whose name or connector marks a prop firm (`pa…`, Apex/Lucid/Topstep/Alpha/FundedNext connectors); the builder
   puts it in one function beside `isDemoAcct` and the server's equivalent.
2. **Team OFF clears Take turns** for its strategies (today it leaves rotation ON out of sight).
3. **The strategy settings form goes** (shown gone in the approved mockup). Changing a strategy's own Target / Risk /
   Stop-for-the-day = a new variant from the Lab. Current values are kept and shown read-only in About.
4. **Limits stay a gate**, but leave the page body: "Edit limits" sits in About, and a strategy that needs them shows red
   "Limits needed first" with a Set limits button. Owner: "Gear only" (section 8): a row's Most is its only cap. "Most contracts per
   account" stays in the limits dialog only while plain or team rows still read `max_qty`, worded for those rows.
5. **A team is one record**: the Desk's `groups.json` (`desk/engine_groups.py`) already holds name, members, accounts,
   mode, size and ON. The charts service stops keeping `deskgroups.json`: team edits go only through the Desk; the
   charts service reads members from the Desk's file (same machine, `paths.state_dir()`) for the team's backtest results
   and prop sims (`tester_routes/desklab.py:320, 794-811`). On first start, a `deskgroups.json` team with no Desk record
   is added OFF with no accounts, then the file is renamed `.retired`. The owner deleted all his teams on 2026-11-02, so
   this is near-empty on both machines.
6. **Variant sets live on the Desk too** (`<state>/variants.json`, beside `groups.json`), not charts side as the
   per-account plan Task 8 said: the Desk trades on them and `/api/setup` reads them, so one record, no cross-service read
   on a Save.
7. **Sidebar order inside a section**: by label, A-Z, so rows never jump around within a section.
8. **The toolbar shield word stays** and opens Today's "Needs a look" (no separate checks popup).
9. **Results**: the three calendars become one (per strategy, Accounts / Shadow). The per-account calendar stays in the
   Accounts popup; the LIVE popup's calendar goes (the strategy page and Accounts popup cover it).
10. **Strategies that size their own trades** (`lab.own_size: true`, e.g. every `nq_candle_break_*` with its own $ risk,
    both `nq_candle_sweep_*`): the gear's Size has a third choice, **Its own** ("its own $650 a trade"), first and the
    default for them, as the old sheet's `own` size did. A row is only rewritten when the owner changes that row: a Save
    never converts an existing plain `{account, qty}` row to Contracts / $ risk by itself.
11. **The ask stays on every account that is not paper** (LIVE, PROP and DEMO), exactly as `saveSolo` asks today
    (`isRealAcct`, `book.js:135-140`): funded PA accounts report env "demo", so a name rule is never trusted to skip an
    ask. PROP is a label only; a misread name changes a word, never a confirm.
12. **A set's variants are compared one at a time, never summed**: the Results Shadow side gets a variant picker (the
    set's variant labels as a `.seg`), and "Matched the backtest" follows the picked variant. The Accounts side shows real
    account dollars, whichever variant made them. The family compare view goes; nothing adds variants' shadow dollars.
13. **The open money-path gaps are fixed before the gear offers NQ** (per-account ledger, Task 3 parked minors): Vest's
    contract map is persisted (or its fills named by known order ids) so an NQ round's exit after an adapter restart is
    booked; NQ-round tests for `_kill_both_filled`, `_lab_end_unfilled`, `_lab_close_retry`, `reconcile_account`,
    `_guard_placed`. Until both land, the gear shows NQ disabled on Vest accounts.

## 7. Where it lives

Page (each edit bumps `?v=` + `DESK_PINS`):
- `static/desk/strategy.js`: `renderSide` (new sections), strategy page (status line, Set up card first, Today, Results),
  removal of `setupHtml`, `labSetRows`, built-in page.
- `static/desk/labdesk.js`: `labDeskView` (new order), `soloSetupHtml`/`soloEdit`/`soloBody`/`saveSolo` (gear rows,
  `settings` per account in the `/api/setup` body), set page, removals in 4.9.
- `static/desk/groups.js`: `dayHeadline`, `todayRow` (account words), Needs-a-look feed, team card words, families out.
- `static/desk/acctset.js`: pure `AcctSet` grows `switchContract`, `needsAsk`, `words(row, variant)` (per-account plan
  Task 7 interfaces); the panel goes.
- `static/desk/views.js`: `setDeskLab` only for Shadow; `toggleSide` keys for the new sections; suggestion line.
- `static/desk/topbar.js`, `static/desk/settings.js`, `static/desk/popups.js`: ready lists out, Day stop word, Manage
  algos out, team manager without families or orphans.
- `static/apple/desk.js`: right panel sections (Backtest per variant, About, More; Today: Desk, Notices).
- `static/desklab.js`: word changes in its text constants (`DeskLab.*`).
- `static/index.html`: removed markup (acctSet overlay, algo manager, demo script), help text, `?v=` bumps.

Server:
- `desk_app/readiness.py`: `strategy`/`account`/`fix` on checks; the new checks in 4.8.
- `routes/setup.py`: set Save (per-account plan Task 9 body: `set`, `accounts`, `pick`, `settings`, `turns`, `hold`, `on`).
- `desk/engine_groups.py`: team OFF clears rotation; becomes the only team record; new `variants.json` beside it (or a
  small `desk/variants.py`).
- `routes/strategies.py` or `charts/tester_routes/desklab.py`: chart-side onoff refuses a booked strategy.
- `routes/groups.py`, `routes/accounts.py`: dead routes out.
- `charts/deskgroups.py`, `charts/deskfamilies.py`, `charts/tester_routes/desklab.py`: families out, teams read from
  the Desk.

## 8. Before it ships

- **The owner, 2026-11-02, "Gear only":** the gear's Most contracts is the only cap on that account. The strategy's own
  Desk limit (`max_qty`) no longer caps a row that has its own Most; it binds only rows without one (plain rows, team
  rows). The Task 4 ruling stands, now with his word.
- **Built-in page gate.** A read of the VPS Desk config was refused by the permission check on 2026-11-02 (production
  read). Ask the owner either to OK one read-only look at the server's strategy config, or to confirm no built-in
  (straddle) strategy runs there. If one does, keep the built-in page and say so in the hand-off.
- Practice Desk walk-through with screenshots (section 9). Send them to the owner with a short summary.
- Final whole-branch review (the per-account ledger's final review has not run; it runs once over everything).
- Merge to `main` only on the owner's word. vpssync ships it when every account is flat and outside 09:10-09:35 ET.

## 9. Tests

- pytest: readiness checks (each new trap gives one line with `strategy`/`account`/`fix`); chart-side onoff refused for a
  booked strategy; set Save (per-account plan Task 9 cases); team OFF clears Take turns; team record migration from a
  leftover `deskgroups.json`; dead routes answer 404/405; families routes gone.
- node (`tests/js`): `AcctSet.switchContract/needsAsk/words` (per-account plan Task 7 asserts); sidebar sorting
  (Trading / Shadow / Off, a set = one row, A-Z inside); `dayHeadline` counts Trading and Shadow apart; status line shows
  every reason; suggestion grouping.
- `tests/test_desk_page.py`: pins, removed ids absent from `index.html`.
- Practice Desk walk-through: (a) solo strategy, ..A MNQ ×3 and ..B NQ $500, one signal places both; (b) change ..B to MNQ
  during an open NQ trade → refused in words; (c) combine 3 variants, pick one per account, Save, signal goes to each
  account's own variant; (d) take an account offline → red status line + "Needs a look" with Reconnect; (e) Desk OFF →
  one line; (f) Archive a strategy and bring it back; (g) Team OFF → its strategies' Take turns off; (h) Shadow strategy
  switched from the chart side, booked strategy refused there.

## 10. Left to the builder

- The plan: task order and size (the removals can go first inside the branch; one merge at the end either way).
- Exact copy of status-line and "Needs a look" sentences, within the words in 4.1.
- Whether the set store is a new `desk/variants.py` or part of `engine_groups.py`.
- How the charts service reads the Desk's team file (direct file read or a Desk route), as long as there is one record.
- Which plain / team rows still read the strategy-wide `max_qty` (decides whether that field stays in the dialog).
- Archive data for families/teams: rename, never delete.

## 11. Supersedes

- Per-account spec: "Families stay folders (Shadow / Live trading); a set sits in one folder" → families are gone.
  "Stored beside the families (charts side)" → sets live on the Desk (call 6).
- Per-account plan Tasks 7-12 → folded into the plan written from this doc.
- Plan `linked-churning-lake` ("Families stay as they are") → families go.
