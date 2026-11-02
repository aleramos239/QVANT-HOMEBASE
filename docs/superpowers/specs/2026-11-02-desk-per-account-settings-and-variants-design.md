---
date: 2026-11-02
status: draft, waiting for the owner's OK
builds_on: f317c863 (Desk Set-up card), 6f057b86
---

# Desk: settings per account, real NQ per account, variants as one strategy

## Intent (the owner's words, 2026-11-02)

> "i want to be able to adjust settings per account, have a settings icon per account where i can pick the contracts per
> trade, mnq or nq, or the size of risk per trade which is default to mnq, then maybe if the strategy has different
> variants like rr or etc i can pick in between them, im also thinking of combing them so if theres multiple of a single
> strategy but different variants they become one"

Why: the owner runs one strategy idea on several prop accounts of different sizes (Apex 300K demos, a LIVE account,
paper). Each account wants its own size and contract, and often its own variant (1R vs 2R). Today that means
separate sidebar rows per variant, one size per strategy, one contract per strategy. The Desk Set-up card (f317c863)
made booking easy; this makes it fit each account.

Owner's answers in this conversation:

| Question | Answer |
|---|---|
| Must some accounts trade real NQ while others trade MNQ, for one strategy? | **Real NQ too** |
| One variant per account, or sometimes two at once? | **One per account** |
| Who decides which strategies combine? | **The Desk suggests, the owner OKs** |
| Build real NQ as a hidden NQ copy of the strategy, or change the order code? | **Change the order code** |

Earlier today the owner said "drop the per-account extras" (size per account, stop after a win, profit/loss locks) for
the Set-up card. This request brings back **size per account** (and adds contract and variant). Stop-after and the
profit/loss locks stay dropped.

## Goals

1. A gear icon on every account row of a strategy's Set up card. It opens one small sheet:
   - **Contract**: MNQ / NQ. Default MNQ.
   - **Size**: contracts per trade (a number) **or** $ risk per trade (a dollar amount). Default: contracts, 1.
   - **Most contracts**: a cap, in that row's own contract.
   - **Variant** (only on a combined strategy): one of its variants.
2. One strategy sends MNQ orders to some accounts and NQ orders to others, at the same moment, from the same signal.
3. Several strategies that are variants of one idea show as **one** strategy: one sidebar row, one ON/OFF, one
   Set up card. Each account picks exactly one variant.
4. The Desk spots likely variants by name and offers to combine them. Nothing combines without the owner's OK.

## Non-goals

- Stop after a win / profit, account profit/loss locks in a strategy panel (dropped by the owner today).
- Changing teams. The owner deleted all his teams today (data only); the team code (f317c863: team Set-up card, take
  turns, team $ risk) stays as it is. **My call:** a strategy is in a team OR a variant set, never both (the server
  refuses); inside a team, the team's size still wins over a row's, as today.
- Merging variants into one runner or one piece of strategy code. Each variant keeps its own runner and record.
- Contracts other than NQ/MNQ in this round (ES/MES, GC/MGC follow the same rule later; build it generic where free).
- Any change to how a strategy decides to trade (signals, stops, targets in points).

## Anti-goals (would make this a failure even if it works)

- **An order in the wrong contract or 10x the size.** 10 micros must never go out as 10 minis, and back.
- **A round that loses track of its position**: an NQ exit fill not booked, or an NQ position read as flat.
- **Changing a row mid-trade re-points an open or overnight trade** to another contract or variant.
- **Saving the Set up card wipes settings** (it does today: `routes/setup.py` `_rows` keeps only account/qty/hold).
- A combined strategy where one account ends up on two variants at once.
- New confusion on the page: the owner must always see, per account, contract + size + variant in plain words.

## Constraints

- Live money. Every commit on `main` ships to the VPS by itself (vpssync, only when all accounts are flat, not
  09:10-09:35). Build in a worktree off `main`; merge only on the owner's word.
- Check on the Practice Desk (`tools/fake_desk --lab` + `homebase.charts --replay`), never on the VPS or live ports.
- Keep the current design (owner, 2026-10-27): same components and skin, no restyle.
- Every `static/desk/*.js` edit bumps its `?v=` and `DESK_PINS`; `apple/*.css` edits bump `apple/manifest.json`
  (pin in `tests/test_desk_page.py`).
- Plain words on the page.

## Approaches considered

| | How | Trade-off | Picked |
|---|---|---|---|
| A. Change the order code | A book row carries its own contract; the engine orders, reads positions, books fills and counts P&L per row | One runner per variant; touches the money path in many places (map below) | **Yes (owner)** |
| B. Hidden NQ copy | When an account picks NQ, the Desk makes an NQ twin of that variant behind the scenes; the order code is untouched | Safest for the order path; one more runner per NQ variant; twins hidden in the UI | No (owner chose A) |
| C. One runner for all variants | Variants become a parameter of one strategy | Rewrites the runner and the record; breaks the tester parity | Dropped |

## The design

### 1. A book row's settings

`labcfg.book_row` (labcfg.py:527-563) already accepts and the engine already honours `size` ("contracts" | "risk"),
`risk_usd`, `most`, `hold` (`acctsize.row_size`, labdesk.py:1316-1324, 1605-1621). Add one field:

- `contract`: the row's exec contract root, `"MNQ"` or `"NQ"`, validated with the existing `contracts.exec_ok`
  against the strategy's root. Missing = the strategy's default (today's `exec_symbol(rec)`), so every existing row
  behaves exactly as now.

`routes/setup.py` `_rows` (lines 28-33) must carry `size`, `risk_usd`, `most`, `hold` and `contract` through instead of
dropping them; the Setup Save sends them. Rows written before keep working.

Defaults when the owner first ticks an account: contract MNQ, contracts 1, most = 20 for MNQ / 2 for NQ (the old
sheet's defaults).

**Switching a row's contract (my call):** Contracts goes back to 1 and Most to that contract's default (20 MNQ / 2 NQ);
$ risk stays as typed. Numbers are never carried over literally (3 MNQ must never become 3 NQ). The sheet shows the new
numbers before Save, on every account, not only LIVE ones.

**The row-contract check:** `exec_ok(root, exec_root)` rejects `NQ` for an `NQ` strategy, so a row's contract is valid
when it equals the root or passes `exec_ok`.

### 2. The order path follows the row (the money part)

Rule: **the contract is fixed on the round when it opens** (`x["symbol"]` in `_lab_open_round`, engine_lab.py:1087).
Every later step of that round reads the round's own contract, never `cfg.symbol`. A book edit therefore can never
re-point an open or overnight round.

Places that read the per-strategy contract and must read the row's (open) or the round's (later) contract instead:

| Step | Where |
|---|---|
| Size | `_verdicts` point value labdesk.py:1285/1297 -> `row_size` 1323; door risk check labrun/door.py:116; `_most_default` 1598-1602; `_group_size` 1576 (teams are gone; keep correct or remove) |
| Entry | `OrderRequest(symbol=cfg.symbol)` engine_lab.py:1110; flat-before-entry read `_lab_position` 1051 |
| Exit / flatten / kill | engine_lab.py `_lab_settle` 1336/1376, `_lab_end_unfilled` 1442, `_lab_close_retry` 1613, `_lab_flatten_one` 1743/1779; engine_kill.py `_kill_state` 344/362, `_kill_both_filled` 389, `_flatten_state` 447/453 |
| Hold overnight | `_lab_carry_check` engine_lab.py:743 |
| Fills / reconcile | engine.py `on_fill` 778, 856, 876; `_guard_placed` 1174; `reconcile_account` 1219 |
| P&L and fees | `_gross_pnl` engine.py:1067; `_open_net` engine_dayrules.py:221; `_fee`/`_net_pnl` engine_dayrules.py:136-140 use `cfg.fee_rt` -> use `contracts.commission_rt(round contract)` |
| Desk record | `bot_history(symbol=cfg.symbol)` trading.py:1514; `bothistory._pnl` bothistory.py:380 uses a fixed `COMMISSION_RT` and the strategy point value -> per trade contract |
| Limits | `LabLimits.max_qty` (labdesk.py:469, 726, 1295, 1341) is in the strategy's contract. **My call:** count it in micro-equivalents (1 NQ = 10 MNQ) so one cap means the same risk on every row |

Two known traps the builder must close first, each with a failing test before the fix:

- **Missed exit fills.** engine.py:856 matches with `cfg.symbol.upper() in ev.symbol.upper()`. With a strategy default
  of MNQ and an NQ row, `"MNQ" in "NQZ6"` is false: the exit is never booked and the round stays live. Match on the
  round's contract, exactly (root of the fill symbol == round contract), not by substring.
- **Wrong-contract net reads look flat.** `get_net_position(cfg.symbol)` on an NQ row reads the MNQ net (0): an entry
  goes on top of an open position, and settle/carry/flatten call the round clean while NQ is open. Read the round's
  (or, before the round, the row's) contract.

The flat-before-entry check reads the whole market on that account (NQ and MNQ), so another strategy's open position
still blocks a new entry as today. Vest keeps NQ and MNQ as one position in units: check its fill symbols before
matching fills by exact contract there.

Unchanged and fine (checked): hedge / same-market guards treat NQ and MNQ as one market (`_same_market` engine_lab.py:949,
`market_of` contracts.py:109), so MNQ on account A and NQ on B for one strategy is not a hedge. Ticks are identical.
Front-month roll is per symbol (`resolve_contract`).

### 3. The whole-strategy mini/micro switch

`_switch_plan` / `set_identity` (labdesk.py:534-581, 590+) rescales every row x10 or /10. With per-row contracts it
would fight the rows. **My call:** retire it from the page. The strategy's `exec_root` stays as the default contract
for new rows and for shadow. Existing rows keep their size; a row without `contract` is written with the current
default on its next save, so nothing silently changes.

### 4. Shadow, the backtest match, the runner

- Shadow (no account) keeps using the record's `exec_root or root` (host.py:623-646). No change.
- `DeskSide.symbol` (host.py:2249; deskside.py:151, 194) refuses snapshots whose `"symbol"` differs from the record's
  `exec_root`. Keep the snapshot's `"symbol"` (labdesk.py:1891) = the strategy default, so this lock keeps working;
  the per-row contract is the Desk's job.
- "Matched the backtest" in desk mode compares the lead account's qty (host.py:948, deskside.py:325-332). When the
  lead row's contract or size differs from the record's, compare without size (`any_size`), as the account cycle does.
- The runner child sends prices and qty, never a contract. No change there.

### 5. Variants as one strategy ("variant set")

- **What it is:** a named list of Lab strategies (the variants) plus a short label for each ("1R", "1.5R", "Fast").
  Stored beside the families (charts side, like `deskfamilies.py`), e.g. `variants: [{id, name, members, labels}]`.
  A strategy is in at most one set. Families stay folders (Shadow / Live trading); a set sits in one folder and its
  members move with it.
- **Sidebar:** one row for the set (its name, today's P&L of the accounts only; shadow dollars are never added to real
  ones). **My call.** The set's page shows shadow P&L per variant, separately. Expanding is not needed; the
  set's page shows the variants.
- **ON/OFF:** one switch for the set = every variant ON or OFF (each through the Desk's own `/api/strategy` path).
  Variants no account picked keep running in shadow, so their forward record keeps growing.
- **Set up card on the set's page:** the account rows; each row's gear adds **Variant**. Save writes each variant's
  book = the accounts that picked it, with their settings, in one server call (extend `/api/setup` to take a set).
  The server refuses as a whole if an account would be on two variants.
- **Changing an account's variant or contract while that account has an open round on the strategy:** refused with
  words ("..024 has an open trade on 1R; change it once it is flat"). **My call**: refusing is simpler and safer than
  queueing.
- **The set's page also shows** the variants side by side (forward shadow P&L, trades, match), reusing the existing
  family compare view.

### 6. The Desk suggests combines

- Strategies whose names share a stem and differ only in a variant-looking tail (e.g. `_r075`, `_r1`, `_r15`, `_r2`,
  `_fast`, `_flex`, `_desk`, `_apex300`, `_s25`/`_s60`, `_g10`/`_g25`) are grouped as a suggestion.
- **Where:** a quiet line at the top of the sidebar's strategy list: "3 strategies look like variants of NQ Candle
  Break: Combine?" -> a sheet listing the members and labels (editable) -> **Combine** / **Not these**. A "Not these"
  is remembered so it is not asked again. **My call** on the placement.
- A combine never changes any booking by itself: the set starts with the bookings its members already had; if two
  members share an account, the sheet says so and the owner picks which keeps it before Combine is allowed.
- Splitting a set back into separate strategies is one button on the set's page.

### 7. Page: the account gear sheet

Same components as the old per-account sheet (578aa750 `acctset.js`, still on disk and loaded), cut to:
Contract (MNQ / NQ) - Size (Contracts n / $ risk $x) - Most contracts - Variant (sets only). Each account row in the
Set up card shows its settings in words: "NQ - $500 a trade - 1.5R" or "MNQ x 3 - 1R".

- On a **LIVE** account, any change that can send more (NQ instead of MNQ, more contracts, more $ risk, higher cap)
  asks first, as the old sheet did (`AcctSet.needsAsk`).
- **$ risk rounding (owner, 2026-11-02: "Keep 10% leeway"):** unchanged from today's `acctsize.row_size`, now with
  the row's own contract's point value: the nearest whole contract, allowed up to 10% over the typed amount; a trade
  where even one contract would risk more than 10% over is skipped on that account and the Desk says so in Activity.
  Example, $500 risk with a 40-point stop: NQ = 0.6 contract -> skipped; MNQ = 6.25 -> 6.
- The status line under the card counts per account ("Ready: ..24 NQ x1 1R, ..25 MNQ $500 2R").

## Tests (where)

- Rows / sizing: `test_labcfg_rows.py`, `test_acctsize.py`, `test_labdesk_b7*.py`, `test_labdesk_round1.py`.
- Order path: `test_engine_lab.py`, `test_order_bodies_lab.py`, `test_trading_lab.py`, `test_fake_desk_lab.py`,
  `test_engine_groups*.py`, `test_micro_exec.py`, `test_labdesk_identity.py`.
- Record: `test_bothistory_lab.py`. Runner: `test_labrun_deskside.py`, `test_labrun_match.py`, `test_labrun_host.py`,
  `test_labrun_desk_e2e.py`. Setup: `test_desk_setup.py`. Page: `tests/js/*`, `tests/test_desk_page.py`.
- Must-have cases: one signal -> MNQ x n on A and NQ x m on B; NQ exit fill on an MNQ-default strategy is booked;
  open NQ position blocks a new entry on that row; flatten/kill/carry on an NQ row; editing a row's contract with a
  round open is refused; overnight NQ round still exits as NQ after the row changes to MNQ the next day; Setup Save
  keeps size/risk/most/contract; set Save refuses one account on two variants; P&L and fees per contract in the
  Desk record.

## Rollout

1. Server and order path first (rows, round contract, the two traps), behind no UI: every existing row has no
   `contract`, so behaviour is unchanged. Engine parity check on the temp tree (recipe
   `F/2026-10-21-engine-parity-temp-tree-recipe.md`).
2. Gear sheet + Setup Save keeps settings.
3. Variant sets + suggestions.
4. Practice Desk walk-through with screenshots; owner's word; merge; vpssync ships when flat.

## Left to the builder

- Exact storage shape of variant sets and where the suggestion stems list lives.
- Whether `_group_size` is removed or kept correct (teams are gone).
- Wording of refusals and the status line, in the house's plain style.
- Splitting each rollout step into commits.
