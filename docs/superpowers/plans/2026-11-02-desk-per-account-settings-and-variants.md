# Desk per-account settings, real NQ per account, variant sets: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A gear on every account row of a strategy's Set up card picks that account's contract (MNQ/NQ), size (contracts or $ risk) and most contracts; one strategy sends MNQ to some accounts and NQ to others; variants of one idea show as one strategy with one variant per account.

**Architecture:** A book row gains `contract`. The engine fixes the contract on the round when it opens (`DayState.symbol`) and every later step of that round (fills, exits, flatten, kill, carry, P&L, fees) reads the round's contract through one helper, `Engine._rcfg(st, cfg)`. Variant sets are a display + booking layer on the charts side (like `deskfamilies.py`); each variant keeps its own runner and record, and `/api/setup` books each variant on the accounts that picked it.

**Tech Stack:** Python 3 (FastAPI Desk + charts service, pytest), plain JS desk page (`homebase/static/desk/*.js`, `node --test tests/js`).

**Spec:** `docs/superpowers/specs/2026-11-02-desk-per-account-settings-and-variants-design.md` (read it first; this plan argues from it).

## Global Constraints

- Work only on branch `claude/desk-account-settings` in `.worktrees/desk-account-settings`. Never commit or merge to `main`: every commit on main ships to the live VPS (vpssync). Merge only on the owner's word.
- Never run anything against the VPS or the live ports (8850/8852). Check on the Practice Desk: `tools/fake_desk --lab` + `homebase.charts --replay`.
- Keep the current design (owner, 2026-10-27): same components and skin, no restyle.
- Every `homebase/static/desk/*.js` edit bumps its `?v=` in `homebase/static/index.html` AND its pin in `DESK_PINS` (`tests/test_desk_page.py:199`). Every `apple/*.css` edit bumps `apple/manifest.json` (pinned in `tests/test_desk_page.py`).
- Page words are plain and short ("NQ · $500 a trade · 1.5R", "MNQ ×3 · 1R").
- Default for a newly ticked account: contract MNQ (the strategy's default contract), contracts 1, Most 20 MNQ / 2 NQ (`acctsize.most_default`).
- Switching a row's contract: Contracts → 1, Most → that contract's default; $ risk stays as typed. Never carry a number across contracts.
- $ risk rounding stays `acctsize.row_size` (owner: "Keep 10% leeway"), with the ROW's contract's point value. Spec example: $500 risk, 40-point stop → NQ 0.6 → skipped; MNQ 6.25 → 6.
- A row without `contract` behaves exactly as today. A strategy is in a team OR a variant set, never both.
- Known red tests before you start: run `pytest -q -x tests` and `node --test tests/js` once on the untouched branch and write the failures into the PR notes; only those may stay red.
- No `rm -rf` (the safety hook blocks it). Never bare `git stash`.

## Review Focus

1. **A cap that converts to zero NQ.** A strategy whose default is MNQ with `max_qty` 5 gets an NQ row: 5 MNQ = 0.5 NQ. Expect the Save to refuse that row in words and the entry never to send 1 NQ. (Test in Task 4.)
2. **A restart in the middle of an NQ round.** The day file is written with `symbol: "NQ"`, the Desk restarts, the row is meanwhile changed to MNQ: the exit still goes out as NQ; an old day file with no `symbol` still loads. (Test in Task 2.)
3. **Fill symbols in other shapes.** A broker reports `"NQZ6"`, `"NQ"`, or Vest's own symbol for an NQ round on an MNQ-default strategy: the exit is booked; an `"MNQZ6"` fill is not booked against an NQ round. (Test in Task 3.)
4. **A set member booked behind the set's back.** `POST /api/book` on one variant of a set puts an account that another variant already has: refused with words, so one account is never on two variants. (Test in Task 9.)
5. **Setup Save with nothing touched.** Ticking one more account and saving must leave every other row's contract, size, $ risk and Most exactly as they were. (Test in Task 1.)

---

### Task 1: The book row's `contract`, and Setup Save keeps every row setting

**Files:**
- Modify: `homebase/desk/labcfg.py` (`book_row` at :527, beside `exec_symbol` at :246)
- Modify: `homebase/routes/setup.py` (`_rows` at :28-33, the solo body read in `register`)
- Test: `tests/test_labcfg_rows.py`, `tests/test_desk_setup.py`

**Interfaces:**
- Produces: `labcfg.book_row(r)` accepts optional `contract: str`; valid when `contract == rec root` or `contracts.exec_ok(root, contract)`. `book_row` has no record, so it only checks it is a known root (`contracts.spec_for(c).known`) and upper-case; the root check is `labcfg.row_ok(rec, row) -> str | None` (a sentence, or None).
- Produces: `labcfg.row_symbol(rec: dict, row: dict) -> str`: the row's `contract` when `row_ok`, else `exec_symbol(rec)`.
- Produces: solo `/api/setup` body gains optional `settings: {account: {contract?, size?, qty?, risk_usd?, most?}}`. `_rows(cur, accounts, hold, qty=None, settings=None) -> list`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_labcfg_rows.py
def test_a_row_may_name_its_contract_only_as_the_strategys_market_or_its_micro():
    nq = {"root": "NQ", "exec_root": "MNQ"}
    assert labcfg.book_row({"account": "a1", "qty": 1, "contract": "NQ"})["contract"] == "NQ"
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "NQ"}) is None
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "MNQ"}) is None
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "ES"})          # a sentence
    with pytest.raises(ValueError):
        labcfg.book_row({"account": "a1", "qty": 1, "contract": "XYZ"})
    assert labcfg.row_symbol(nq, {"account": "a1"}) == "MNQ"
    assert labcfg.row_symbol(nq, {"account": "a1", "contract": "NQ"}) == "NQ"
    assert labcfg.row_symbol(nq, {"account": "a1", "contract": "ES"}) == "MNQ"

# tests/test_desk_setup.py
def test_a_solo_save_keeps_every_rows_settings_and_takes_new_ones(desk):
    # a1 booked NQ $500 risk most 2; save ticks a2 in with no settings touched
    ...
    assert book["a1"] == {"account": "a1", "qty": 1, "size": "risk", "risk_usd": 500, "most": 2, "contract": "NQ"}
    assert book["a2"] == {"account": "a2", "qty": 1}
    # the same save with settings for a2
    assert book["a2"] == {"account": "a2", "qty": 3, "size": "contracts", "most": 20, "contract": "MNQ"}

def test_a_solo_save_with_a_contract_the_strategy_cannot_trade_writes_nothing(desk): ...
```

- [ ] **Step 2: Run them, expect FAIL** — `pytest tests/test_labcfg_rows.py tests/test_desk_setup.py -q` (no `row_ok` / settings dropped).
- [ ] **Step 3: Implement** `book_row` (+`contract`), `row_ok`, `row_symbol`, and `_rows(..., settings=None)`: each row = the cur row with its `size/risk_usd/most/contract/hold` kept, overlaid by `settings[a]` when given; `qty` from settings, else `qty`, else cur, else 1. A setting for an account that is not ticked is ignored. The solo save refuses whole (nothing written) when any row fails `row_ok`. The team path keeps its own size rules (team wins, as today) but also keeps `contract`. `LabDesk.set_book` (labdesk.py:765, behind `POST /api/book`) refuses a row that fails `row_ok` too, so no path writes a contract the strategy cannot trade (add that case to the test).
- [ ] **Step 4: Run them, expect PASS**, plus `pytest tests/test_desk_setup.py tests/test_labcfg_rows.py tests/test_acctsize.py -q`.
- [ ] **Step 5: Commit** `git commit -m "Desk: a book row may name its contract; Setup Save keeps each row's settings"`.

---

### Task 2: The round owns its contract: entry, restart, whole-market flat check

**Files:**
- Modify: `homebase/desk/daystate.py` (`DayState`: add `symbol: Optional[str] = None`)
- Modify: `homebase/desk/engine_lab.py` (`lab_enter` :1217, `_lab_enter_one` :1142, `_lab_position` :1045, `_lab_open_round` :1081)
- Modify: `homebase/desk/engine.py` (add `_rcfg`; `_place_one` :570 is called with the round's cfg)
- Modify: `homebase/desk/labdesk.py` (`_enter` :1638 passes the row contracts; :1653 call)
- Test: `tests/test_engine_lab.py`, `tests/test_micro_exec.py` (harness: `tests/labdesk_util.mkdesk/send/entry`, `placed()` in test_micro_exec)

**Interfaces:**
- Consumes: `labcfg.row_symbol(rec, row)` (Task 1).
- Produces: `DayState.symbol: Optional[str]` — the contract root the round's orders go to; None on old files = `cfg.symbol`.
- Produces: `Engine._rcfg(self, st: DayState, cfg: StrategyCfg) -> StrategyCfg` — `cfg` itself when `st.symbol` is None or equals `cfg.symbol`, else `dataclasses.replace(cfg, symbol=st.symbol, fee_rt=contracts.commission_rt(st.symbol))`. Every later task routes round handling through it.
- Produces: `Engine.lab_enter(name, legs, sizes, *, max_rounds, source="lab", contracts: dict | None = None)` — `contracts = {account: root}`; missing account = `cfg.symbol`.
- Produces: `Engine.lab_open_on(self, name: str, account: str) -> bool` — True while that account has a round of `name` that is placing/live/carried (used by Task 6 and Task 9).

- [ ] **Step 1: Write the failing tests**

```python
def test_one_signal_sends_mnq_to_one_account_and_nq_to_another(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"), rec_kw={"exec_root": "MNQ"})
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 3}, {"account": "a2", "qty": 1, "contract": "NQ"}]))
    out = send(d, entry(kind="market", price=None, ref=100.0, sl=95.0, tp=115.0))
    assert out["results"][0]["refused"] is None
    assert placed(d, "a1") == [("MNQ", "Buy", "Market", 3)]
    assert placed(d, "a2") == [("NQ", "Buy", "Market", 1)]
    assert d.engine.states[f"{LAB}@a2"].symbol == "NQ"

def test_an_open_nq_position_blocks_an_mnq_entry_on_that_account(tmp_path):
    # a1 booked MNQ; the fake adapter holds +1 NQ on a1 -> place_skipped "The account already holds NQ. Check it."

def test_a_round_keeps_its_contract_across_a_restart_and_a_row_change(tmp_path):
    # open an NQ round on a2, reload the engine from its day file, set a2's row to MNQ, then exit:
    # the exit/flatten request goes out as NQ; a day file written without "symbol" loads with symbol None

def test_rcfg_is_the_strategy_cfg_unless_the_round_trades_another_contract(): ...
```

- [ ] **Step 2: Run them, expect FAIL** — `pytest tests/test_engine_lab.py tests/test_micro_exec.py -q -k "contract or mnq or rcfg"`.
- [ ] **Step 3: Implement.**
  - `labdesk._enter` builds `contracts = {row["account"]: labcfg.row_symbol(rec, row) for row in booked}` and passes it to `lab_enter`; `lab_enter` hands each account's root to `_lab_enter_one(..., contract)` → `_lab_position(..., contract)` → `_lab_open_round(..., contract)`.
  - `_lab_open_round` sets `st.symbol = contract or cfg.symbol` before `_save()`, builds the pair's `OrderRequest`s and asks `hedge_refusal` with `self._rcfg(st, cfg)`, and returns that cfg so `_place_one` sends the round's contract. The `lab_round` journal line gains `symbol=st.symbol`.
  - `_lab_position` reads the WHOLE market on the account: `get_net_position` for `contracts.price_root(sym)` and, when it has one, `contracts.micro_of(...)`; any non-zero → `f"The account already holds {that}. Check it."`, any unreadable → `LAB_NO_POSITION_READ`.
- [ ] **Step 4: Run them, expect PASS**, then `pytest tests/test_engine_lab.py tests/test_micro_exec.py tests/test_order_bodies_lab.py tests/test_trading_lab.py -q`.
- [ ] **Step 5: Commit** `"Desk engine: a Lab round fixes its contract when it opens; the flat check reads the whole market"`.

---

### Task 3: Every later step of a round reads the round's contract (fills, exits, flatten, kill, carry, reconcile)

**Files:**
- Modify: `homebase/desk/engine.py` (`on_fill` :778, :856, :876; `_guard_placed` :1174; `reconcile_account` :1219)
- Modify: `homebase/desk/engine_lab.py` (`_lab_settle` :1336/:1376, `_lab_end_unfilled` :1442, `_lab_close_retry` :1613, `_lab_flatten_one` :1743/:1779, `_lab_carry_check` :743)
- Modify: `homebase/desk/engine_kill.py` (`_kill_state` :344/:362, `_kill_both_filled` :389, `_flatten_state` :447/:453)
- Read first: `homebase/broker/vest.py` — the symbol its fill events carry.
- Test: `tests/test_engine_lab.py`, `tests/test_fake_desk_lab.py`

**Interfaces:**
- Consumes: `Engine._rcfg` (Task 2).
- Produces: `contracts.same_contract(a: str, b: str) -> bool` — `root_of(a) == root_of(b)`; the ONLY fill-symbol test the engine uses for Lab rounds (replaces `cfg.symbol.upper() in ev.symbol.upper()` at :856 and :876).

- [ ] **Step 1: Write the failing tests**

```python
def test_same_contract_is_exact_never_a_substring():
    assert contracts.same_contract("NQ", "NQZ6") and contracts.same_contract("MNQ", "MNQZ6")
    assert not contracts.same_contract("MNQ", "NQZ6") and not contracts.same_contract("NQ", "MNQZ6")

def test_an_nq_exit_fill_on_an_mnq_default_strategy_is_booked(tmp_path):
    # MNQ-default strategy, a2 row NQ, entry filled; exit fill symbol "NQZ6" -> round done, exit_fill set, pnl in NQ dollars
    # an "MNQZ6" fill on the same account is NOT booked against that round

def test_flatten_kill_and_carry_of_an_nq_round_act_on_nq(tmp_path):
    # Kill -> the flatten request symbol is "NQ"; settle reads get_net_position("NQ"); an overnight NQ round is carried
    # and the next morning's exit goes out as NQ after the row was changed to MNQ

def test_a_vest_fill_of_an_nq_round_is_booked(tmp_path):
    # use the symbol shape read from broker/vest.py in Step 0
```

- [ ] **Step 2: Run them, expect FAIL** (the first fill test is spec trap 1: the round stays live today).
- [ ] **Step 3: Implement** `same_contract`, then at the top of each listed function, once the round's `st` is known: `cfg = self._rcfg(st, cfg)`. Do not change anything that runs before a round exists. `grep -n "cfg.symbol" homebase/desk/engine*.py` afterwards: every remaining use must be pre-round or non-Lab; list them in the commit message.
- [ ] **Step 4: Run them, expect PASS**, then `pytest tests/test_engine*.py tests/test_fake_desk_lab.py tests/test_micro_exec.py -q`.
- [ ] **Step 5: Commit** `"Desk engine: fills, exits, flatten, kill and carry follow the round's own contract; exact fill match"`.

---

### Task 4: Size each row in its own contract

**Files:**
- Modify: `homebase/desk/labdesk.py` (`_verdicts` :1285/:1297/:1323, `_most_default` :1598, `_group_size` :1576, `LabLimits.max_qty` uses :469/:726/:1295/:1341)
- Modify: `homebase/labrun/door.py` only if the per-row `lim` needs a new key (it should not: `point_value` and `max_qty` are passed per row)
- Modify: `homebase/routes/setup.py` (refuse a row whose converted cap is 0)
- Test: `tests/test_acctsize.py`, `tests/test_labdesk_b7*.py`, `tests/test_desk_setup.py`

**Interfaces:**
- Consumes: `labcfg.row_symbol` (Task 1).
- Produces: `labcfg.row_cap(rec: dict, row: dict, max_qty: int) -> int` — `max_qty` is in the strategy's default contract (as today); a row on another contract gets `int(max_qty * point_value(default) / point_value(row contract))`. Default-contract rows: unchanged. (This is how the spec's "one cap, same risk on every row" is built without changing any existing cap.)
- Produces: `LabDesk._most_default(name, symbol: str | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
def test_risk_rows_size_in_their_own_contract():               # the spec's example, keep 10% leeway
    # $500 risk, 40-point stop: NQ row -> skipped (ROW_NO_SIZE, Activity says why); MNQ row -> 6

def test_the_cap_converts_by_point_value():
    rec = {"root": "NQ", "exec_root": "MNQ"}
    assert labcfg.row_cap(rec, {"contract": "NQ"}, 20) == 2
    assert labcfg.row_cap(rec, {"contract": "NQ"}, 5) == 0
    assert labcfg.row_cap(rec, {}, 5) == 5
    assert labcfg.row_cap({"root": "NQ"}, {"contract": "MNQ"}, 2) == 20

def test_a_row_whose_cap_is_zero_is_refused_at_save_and_never_sends(desk): ...   # Review Focus 1
def test_the_door_counts_dollar_risk_in_the_rows_contract(tmp_path): ...         # NQ row: 5 pts x $20 x 1
def test_most_default_follows_the_rows_contract(): ...                           # 20 MNQ, 2 NQ
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** In `_verdicts`, per booked row: `sym = labcfg.row_symbol(rec, row)`, `lim_row = {**lim, "point_value": point_value(sym), "max_qty": labcfg.row_cap(rec, row, limits.max_qty)}`; `row_size(row, dists[i], point_value(sym), full, None, limits.max_risk_usd)`. `_group_size` (teams): keep it, sized with the row's contract the same way. Setup refuses a row with `row_cap == 0`: "..024: NQ is over this strategy's Most contracts (5 MNQ). Raise Limits first."
- [ ] **Step 4: Run, expect PASS**, then `pytest tests/test_acctsize.py tests/test_labdesk*.py tests/test_desk_setup.py tests/test_micro_exec.py -q`.
- [ ] **Step 5: Commit** `"Desk: each account row is sized, capped and risk-checked in its own contract"`.

---

### Task 5: P&L, fees and the Desk record per round contract

**Files:**
- Modify: `homebase/desk/engine.py` (`_gross_pnl` :1063), `homebase/desk/engine_dayrules.py` (`_fee`/`_net_pnl` :136-140, `_open_net` :221)
- Modify: `homebase/desk/bothistory.py` (`_pnl` :380 and the run builder that reads `lab_round`), `homebase/desk/trading.py` (`bot_history` :1509)
- Test: `tests/test_bothistory_lab.py`, `tests/test_engine_lab.py`

**Interfaces:**
- Consumes: `_rcfg`, the `lab_round` journal line's `symbol` (Task 2).
- Produces: `bothistory._pnl(entry, ex, qty, symbol, fee_rt=COMMISSION_RT)`; a run whose journal names a `symbol` is priced and charged in it (`commission_rt(symbol)`); a run without one is priced exactly as today.

- [ ] **Step 1: Failing tests:** an NQ round of an MNQ-default strategy, +10 points x1 → gross $200, fee `commission_rt("NQ")`, in the day's net, the day-rule open net, and the Desk record's run; an old journal run with no `symbol` → same number as before the change.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** through `self._rcfg(st, cfg)` in the engine functions; in bothistory read `symbol` off the run's `lab_round` record.
- [ ] **Step 4: Run, expect PASS**, then `pytest tests/test_bothistory*.py tests/test_engine*.py -q`.
- [ ] **Step 5: Commit** `"Desk: P&L, fees and the record count each round in its own contract"`.

---

### Task 6: Guards around the rows: no contract change mid-round, the old mini/micro switch, the backtest match; parity

**Files:**
- Modify: `homebase/routes/setup.py` (refuse), `homebase/desk/labdesk.py` (`set_identity` :590, snapshot :1885-1895)
- Modify: `homebase/static/desk/labdesk.js` (remove the "Switch to mini / micro" button at :206 and `switchLabInstrument`; keep Rename/Duplicate) + `?v=` + `DESK_PINS`
- Test: `tests/test_desk_setup.py`, `tests/test_labdesk_identity.py`, `tests/test_labrun_deskside.py`, `tests/test_desk_page.py`

**Interfaces:**
- Consumes: `Engine.lab_open_on(name, account)` (Task 2).
- Produces: the snapshot's `"cycle_sized"` is also True when any booked row has `size` or a `contract` other than the strategy default (deskside.py:325 then compares without size, as for the account cycle).

- [ ] **Step 1: Failing tests:**
  - Save that changes a2's contract while `lab_open_on(LAB, "a2")` → refused whole: "..a2 has an open trade on NQ; change it once it is flat." Changing size only is allowed (it applies to the next round).
  - `set_identity(name, {"instrument": ...})` → refused with "Pick the contract on each account (the gear)." when any row names a `contract`; otherwise as today.
  - snapshot of a strategy with an NQ row → `cycle_sized is True`; plain rows → unchanged.
  - the page no longer contains `switchLabInstrument`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**; then the engine parity check on a temp tree (recipe `~/Obsidian/Vault/50-Permanent/Findings/2026-10-21-engine-parity-temp-tree-recipe.md`): same trades before/after for 3 Desk strategies with plain rows. Then the full suite: `pytest -q tests` and `node --test tests/js` — only the known failures.
- [ ] **Step 5: Commit** `"Desk: no contract change mid-trade; the whole-strategy mini/micro switch leaves the page; the match reads any size"`. **Server part done: stop and report to the owner before the UI tasks.**

---

### Task 7: The gear sheet on the Set up card

**Files:**
- Modify: `homebase/static/desk/acctset.js` (cut to Contract / Size / Most / Variant; drop stop-after, profit/loss locks), `homebase/static/desk/labdesk.js` (`soloSetupHtml` :627, `soloEdit` :604, `soloBody`, `saveSolo`), `homebase/static/index.html` (`#acctSetOverlay` markup + `?v=`), `tests/test_desk_page.py` (pins)
- Modify (server, for the sheet's numbers): the strategy view gives `lab.contracts: ["MNQ","NQ"]` (default first) and `lab.most_default_by: {"MNQ": 20, "NQ": 2}`
- Test: `tests/js/acctset.test.mjs`, `tests/test_desk_page.py`

**Interfaces:**
- Consumes: the solo `/api/setup` `settings` body (Task 1).
- Produces (pure, `AcctSet`): `formOf(row, def)`, `rowFrom(form, prev)` (now with `contract`), `switchContract(form, to, mostBy) -> form` (qty 1, most = `mostBy[to]`, risk kept), `words(row, variant?) -> "NQ · $500 a trade · 1.5R" | "MNQ ×3 · 1R"`, `needsAsk(prev, next, live)` (also true for MNQ→NQ and Most up).

- [ ] **Step 1: Failing JS tests (`tests/js/acctset.test.mjs`):**

```js
assert.deepEqual(AcctSet.switchContract({contract:'MNQ', size:'contracts', qty:3, most:20}, 'NQ', {MNQ:20, NQ:2}),
                 {contract:'NQ', size:'contracts', qty:1, most:2});
assert.equal(AcctSet.switchContract({contract:'MNQ', size:'risk', risk_usd:500, most:20}, 'NQ', {MNQ:20, NQ:2}).risk_usd, 500);
assert.equal(AcctSet.words({contract:'NQ', size:'risk', risk_usd:500, qty:1}, '1.5R'), 'NQ · $500 a trade · 1.5R');
assert.equal(AcctSet.words({contract:'MNQ', qty:3}, '1R'), 'MNQ ×3 · 1R');
assert.equal(AcctSet.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, true), true);
assert.equal(AcctSet.needsAsk({contract:'NQ', qty:1}, {contract:'MNQ', qty:1}, true), false);
assert.equal(AcctSet.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, false), false);
```

- [ ] **Step 2: Run, expect FAIL** — `node --test tests/js/acctset.test.mjs`.
- [ ] **Step 3: Implement.** Each ticked account row in the solo card gets a gear button (same icon set as the sidebar) and its words; the gear opens the existing sheet (static markup, never rebuilt by `render()`); the sheet edits the card's draft (`SOLO_DRAFT[name].settings[account]`), not the server — the card's Save sends it. On a LIVE account, `needsAsk` changes go through `confirmDlg` at Save, listing old → new words. The global "Contracts per account" box and the line "For $ risk per trade, put it in a team." go. The status line lists each account's words ("Ready: ..24 NQ ×1, ..25 MNQ $500 a trade").
- [ ] **Step 4: Run, expect PASS** — `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: a gear per account on the Set up card: contract, size, most"`.

---

### Task 8: Variant sets: the store and its routes (charts side)

**Files:**
- Create: `homebase/charts/deskvariants.py` (pattern: `homebase/charts/deskfamilies.py`, same `GroupError`, `STRATEGY_RE`, file beside `deskfamilies.json`)
- Modify: `homebase/charts/tester_routes/desklab.py` (routes beside `/deskfamilies` at :704)
- Test: `tests/test_tester_deskvariants.py` (pattern: `tests/test_tester_deskfamilies.py`)

**Interfaces:**
- Produces: `deskvariants.load(at=None) -> list[dict]`, each `{"id": "v1", "name": str, "members": [strategy], "labels": {strategy: str}, "family": str | None}`; `deskvariants.apply(action, body, at=None) -> list[dict]`, `ACTIONS = ("create", "rename", "label", "split", "dismiss")`; `deskvariants.set_of(name, at=None) -> dict | None`; `deskvariants.dismissed(at=None) -> list[list[str]]`.
- Routes: `GET /api/tester/deskvariants` → `{"sets": [...], "dismissed": [...]}`; `POST /api/tester/deskvariants/<action>`.
- Rules: 2+ members; a strategy in at most one set; a member of a team (Desk group) is refused ("It is in the team X."); labels ≤ 12 chars; `split` deletes the set (bookings untouched); `dismiss` stores a sorted member list so it is never suggested again.

- [ ] **Step 1: Failing tests** for each rule above (create, one-set-per-strategy, team refusal, label length, split keeps nothing else changed, dismiss remembered).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** A set's members move to the set's family together (call `deskfamilies.apply("move", ...)` for each).
- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_tester_deskvariants.py tests/test_tester_deskfamilies.py -q`.
- [ ] **Step 5: Commit** `"Desk: variant sets (store and routes)"`.

---

### Task 9: `/api/setup` for a set: one variant per account

**Files:**
- Modify: `homebase/routes/setup.py`, `homebase/routes/book.py` (or wherever `POST /api/book` lives: `grep -rn '"/api/book"' homebase/routes`)
- Test: `tests/test_desk_setup.py`

**Interfaces:**
- Consumes: `deskvariants.set_of` (read through the charts service the way setup.py reads teams today), `Engine.lab_open_on` (Task 2), `_rows(..., settings)` (Task 1).
- Produces: `POST /api/setup` body `{"set": id, "accounts": [..], "pick": {account: strategy}, "settings": {account: {...}}, "turns": bool, "hold"?: bool, "on": bool}` → each member's book = the accounts that picked it, with their settings; `on` switches every member through `/api/strategy` (picked or not: unpicked ones run in shadow).

- [ ] **Step 1: Failing tests:**
  - a set Save books member A on a1, member B on a2 with their settings, turns ON every member, one `setup_saved` journal line.
  - an account with no pick, or a pick that is not a member → refused whole, nothing written.
  - moving a1 from A to B while `lab_open_on(A, "a1")` → refused: "..a1 has an open trade on 1R; change it once it is flat."
  - `POST /api/book` putting a2 on A while B has a2 → refused (Review Focus 4).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**, reusing the solo path per member (add new accounts first, then remove old, as setup does today).
- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_desk_setup.py tests/test_engine_groups*.py -q`.
- [ ] **Step 5: Commit** `"Desk: Set up a variant set in one save, one variant per account"`.

---

### Task 10: The set on the page: one sidebar row, its page, compare, split

**Files:**
- Modify: `homebase/static/desk/views.js` (sidebar), `homebase/static/desk/labdesk.js` (set page + Set up card with Variant in the gear), `homebase/static/desk/strategy.js` (member page says "In the set X → open", like a team member), `homebase/static/desk/popups.js` if the families compare view lives there; `index.html` `?v=` + `DESK_PINS`
- Test: `tests/js/` new `deskvariants.test.mjs`, `tests/test_desk_page.py`

**Interfaces:**
- Consumes: `GET /api/tester/deskvariants` (Task 8), set `/api/setup` (Task 9), `AcctSet.words(row, label)` (Task 7).
- Produces (pure, testable): `setDayPnl(set, accounts) -> number|null` — sum of the members' ACCOUNT P&L only, never shadow.

- [ ] **Step 1: Failing tests:** `setDayPnl` ignores shadow dollars; the sidebar shows one row for a set and no rows for its members; the gear on a set's account row offers the members' labels; one Trading switch.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** The set's page shows the Set up card (rows with Variant), each variant's shadow P&L / trades / match side by side (reuse the family compare view), and a "Split into separate strategies" button (confirm, then `deskvariants/split`).
- [ ] **Step 4: Run, expect PASS** — `node --test tests/js` and `pytest tests/test_desk_page.py -q`.
- [ ] **Step 5: Commit** `"Desk: a variant set is one strategy on the page"`.

---

### Task 11: The Desk suggests combines; the owner OKs

**Files:**
- Modify: `homebase/charts/deskvariants.py` (add `suggest`), its GET route answers `"suggest"` too
- Modify: `homebase/static/desk/views.js` (quiet line at the top of the strategy list + the Combine sheet), `?v=` + `DESK_PINS`
- Test: `tests/test_tester_deskvariants.py`, `tests/js/deskvariants.test.mjs`

**Interfaces:**
- Produces: `deskvariants.TAILS = ("_r075", "_r1", "_r15", "_r2", "_fast", "_flex", "_desk", "_apex300", "_s25", "_s60", "_g10", "_g25")` (the spec's list; a tail match is the name ending in one of them, optionally followed by more of them); `deskvariants.suggest(names: list[str], at=None) -> list[{"stem": str, "members": [str], "labels": {str: str}}]` — 2+ names per stem, skips names already in a set, in a team, or a dismissed group.
- Page: "3 strategies look like variants of {stem}: Combine?" → sheet with members + editable labels → Combine / Not these. If two members share an account, the sheet names it and Combine stays disabled until the owner unticks one (unbooking goes through the existing solo Save).

- [ ] **Step 1: Failing tests:** `suggest(["nq_cb_r1", "nq_cb_r15", "nq_cb_r2", "gc_x"])` → one group, stem `nq_cb`, labels `{"nq_cb_r1": "1R", "nq_cb_r15": "1.5R", "nq_cb_r2": "2R"}`; dismissed group not suggested again; a team member never suggested; JS: Combine disabled while two members share an account.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Combining never changes a booking.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `"Desk: suggests variants to combine; nothing combines without the owner"`.

---

### Task 12: Practice Desk walk-through and hand-off

**Files:** none new (screenshots go in the PR notes / to the owner).

- [ ] **Step 1:** `pytest -q tests` and `node --test tests/js`: only the known failures.
- [ ] **Step 2:** Practice Desk (`tools/fake_desk --lab` + `homebase.charts --replay`), never the live ports: (a) a solo strategy with ..A MNQ ×3 and ..B NQ $500 → one signal places MNQ ×3 and NQ ×n; (b) change ..B to MNQ during its trade → refused in words; after it exits → allowed; (c) LIVE account MNQ→NQ asks first; (d) combine three `_r*` strategies, pick a variant per account, Save, Trading ON → the right variant books each account, the others run in shadow; (e) split the set → three rows again, bookings unchanged.
- [ ] **Step 3:** Screenshots of the card, the gear sheet, a set's page and the suggestion line. Send them to the owner with a 5-line summary. Ask for his word before any merge to `main`.
