# Per-account strategy settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each account a Lab strategy is booked on gets its own size (contracts or $ risk), Most contracts box and "stop after" rule; each account gets a loss lock beside its profit lock; the side panel's strategy-wide rows become read-only.

**Architecture:** Book rows (sidecar `<desklab>/<name>.desk.json`, mirrored in `cfg.book`) grow optional fields. One pure sizing function (`homebase/desk/acctsize.py`) turns a row + an entry's stop into contracts; `LabDesk._verdicts` / `_takers` use it. "Stop after" is one more per-account check in `engine_lab._lab_sits_out`. The loss lock is one more `DayRules` / `DayBook` lock beside `day_lock`. The UI is a small sheet (`static/desk/acctset.js`) opened from the account row.

**Tech Stack:** Python 3 (FastAPI, dataclasses, pytest), plain browser JS (node --test).

**Spec:** `docs/superpowers/specs/2026-10-29-per-account-strategy-settings-design.md`

## Global Constraints

- A row with no `size` field trades EXACTLY as today (legacy path untouched: `_sized`, `max_qty` cap, own_size `min`).
- Row fields: `size` `"contracts"|"risk"`; `qty` whole 1..10^6; `risk_usd` finite > 0 and <= 100000, required iff `size == "risk"`; `stop_after` `"none"|"win"|"profit"` (stored only when not "none"); `most` whole 1..1000, absent = box removed.
- Most contracts default: 20 when the strategy's orders go to a micro, 2 when they go to a mini (UI fills it in when the box is added).
- Backstop when `most` is absent: 10 minis' worth per order = `max(1, int(10 * point_value(root) / point_value(exec_symbol)))` (100 micros / 10 minis).
- Risk sizing: n = round(risk_usd / (dist x pv)); if n x dist x pv > risk_usd x OVER_MOST (1.10) then n = floor(risk_usd / (dist x pv)); capped by `max_risk_usd` when set; a pair uses its wider stop; n < 1 or stop not measurable -> that account sits out with `ROW_NO_SIZE`.
- An ON account-cycle group with `risk_usd` keeps its own size (it already overrides `sizes` in `_enter`).
- Stop after `win` = any closed round today on that account with net > 0; `profit` = sum of closed nets today > 0. Open rounds do not count. Only new entries stop.
- Loss lock `AccountCfg.day_loss` ($, 0 = off): locks when the day's closed net <= -day_loss after a Desk trade closes; set at or past an already-reached loss locks at once; never lifted the same day. Lock reason string `"day_loss"`.
- Sentences (exact): `ROW_NO_SIZE = "No contract fits this account's risk for this stop."`, `LAB_DONE_WIN = "Done for today on this account: a trade won."`, `LAB_DONE_PROFIT = "Done for today on this account: it is in profit."`, `ROW_OVER_MOST = "Size is over this account's Most contracts."`.
- Raising size on a LIVE account, or switching a LIVE row to risk, asks first (`confirmDlg`, as `editQty`).
- Every row change journalled with old and new (`book_updated` already carries `assignments`; add `previous`).
- Keep the current design: no restyle; the sheet uses existing classes (`agroup`, `feed-row`, `btn btn-outline btn-sm`, `qty-input`, `switch`).
- Every `static/desk/*.js` edit bumps its `?v=` in `homebase/static/index.html` and its `DESK_PINS` entry `(v, sha256[:16])` in `tests/test_desk_page.py`; an `apple/desk.css` / `apple/desk.js` edit bumps `apple/manifest.json` and its assert.
- Branch `claude/per-account-settings` only. Never merge to main (= the VPS) without the owner's word.
- Tests: `.venv/bin/python -m pytest <file> -q` (repo root `.venv` at `~/ramos-quant-homebase/.venv`), `node --test tests/js/<file>.test.mjs`.

## Review Focus

1. An old sidecar row `{account, qty}` on an own_size strategy -> still sends `min(qty, order's qty)`, still refused above `max_qty` (parity test in Task 2).
2. A page that saves a row through `pickAsg` / `editQty` / `removeAsg` must not strip the other rows' new fields (JS test in Task 5).
3. A risk row whose stop is tiny -> clamped to `most` (or the backstop), never more (Task 2 test).
4. An account with only a loss lock set must still let Lab strategies trade (`LAB_TAKE_RULE` keys on `day_take`/`target_take` only) (Task 4 test).
5. Accounts that sit out for their own rule do not count toward the "two entries no account took" stop (Task 3 test).

---

### Task 1: Book rows carry the new fields

**Files:**
- Modify: `homebase/desk/labcfg.py` (`_shaped` ~507, `_norm` ~521, `commit` ~820)
- Modify: `homebase/desk/labdesk.py` (`check_book` ~699-734, `set_book` ~734-746)
- Modify: `homebase/routes/strategies.py` (`/api/book` 116-142)
- Test: `tests/test_labcfg_rows.py` (new), add to the existing labdesk book tests file (`tests/test_labdesk*.py` that covers `check_book`)

**Interfaces:**
- Produces: `labcfg.book_row(r: dict) -> dict` — validated, shaped row; raises `ValueError(sentence)` on a bad row. Output keys in order: `account, qty`, then `size, risk_usd, stop_after, most` only when set (`stop_after` dropped when "none"; `risk_usd` only with size "risk").
- Produces: `labdesk.ROW_OVER_MOST` (sentence above).

- [ ] **Step 1: Write the failing tests**

```python
def test_old_row_reads_as_today():
    assert labcfg.book_row({"account": "A", "qty": 2}) == {"account": "A", "qty": 2}

def test_new_fields_kept_and_defaults_dropped():
    r = {"account": "A", "qty": 1, "size": "risk", "risk_usd": 500, "stop_after": "win", "most": 20}
    assert labcfg.book_row(r) == r
    assert labcfg.book_row({"account": "A", "qty": 3, "size": "contracts", "stop_after": "none"}) == \
        {"account": "A", "qty": 3, "size": "contracts"}

@pytest.mark.parametrize("bad", [
    {"account": "A", "qty": 1, "size": "risk"},                       # no risk_usd
    {"account": "A", "qty": 1, "size": "risk", "risk_usd": float("nan")},
    {"account": "A", "qty": 1, "size": "lots"},
    {"account": "A", "qty": 1, "stop_after": "loss"},
    {"account": "A", "qty": 1, "most": 0},
    {"account": "A", "qty": 1, "most": True},
])
def test_bad_rows_raise(bad):
    with pytest.raises(ValueError):
        labcfg.book_row(bad)

def test_shaped_skips_bad_rows_and_norm_keeps_fields():
    rows = [{"account": "A", "qty": 1, "size": "risk", "risk_usd": 400}, {"account": "B", "qty": 1, "size": "x"}]
    assert labcfg._shaped(rows) == [rows[0]]
    assert labcfg._norm(["m"], None, rows[:1])["book"] == rows[:1]
```

Plus in the labdesk book tests: `check_book` refuses `{"size": "contracts", "qty": 25, "most": 20}` with `ROW_OVER_MOST`; accepts `{"size": "contracts", "qty": 5}` when `limits.max_qty` is 2 (a set row is not held to the backtested cap); still refuses a legacy `{"qty": 5}` above `max_qty`. `set_book` round-trips the new fields into the sidecar and `cfg.book`. `/api/book` returns 400 with the sentence for a bad row and journals `book_updated` with `previous`.

- [ ] **Step 2: Run to see them fail** — `.venv/bin/python -m pytest tests/test_labcfg_rows.py -q` → FAIL (`book_row` not defined).
- [ ] **Step 3: Implement** `book_row`; use it in `_shaped` (catch `ValueError`, skip the row, keep one row an account), `_norm` and `commit` (replace the `{account, qty}` literals). `check_book`: the `max_qty` refusal only for rows without `size`; `ROW_OVER_MOST` when `size == "contracts"` and `qty > most`. `set_book`: commit `[labcfg.book_row(r) for r in rows] + others`. Route: build rows with `labcfg.book_row` (ValueError -> 400 with its words; keep the unknown-account 404/400 and `qty > 0` filter), journal `previous=` the old rows.
- [ ] **Step 4: Run** the new file and `tests/test_labcfg*.py tests/test_labdesk*.py tests/test_bookflow.py` → PASS.
- [ ] **Step 5: Commit** `git commit -m "desk: book rows carry size, risk, stop-after and most contracts (per-account settings 1)"`

### Task 2: Per-account sizing

**Files:**
- Create: `homebase/desk/acctsize.py`
- Modify: `homebase/desk/labdesk.py` (`_verdicts` 1249-1306, `_takers` 1548-1556, event flow 1453-1484)
- Test: `tests/test_acctsize.py` (new), the labdesk event tests (`tests/test_labdesk*.py` that drive `_verdicts`/events)

**Interfaces:**
- Consumes: rows from Task 1.
- Produces: `acctsize.ROW_NO_SIZE`, `acctsize.BACKSTOP_MINIS = 10`, `acctsize.OVER_MOST = 1.10` (import labdesk's existing `OVER_MOST` instead if it lives there; one constant only),
  `acctsize.row_size(row: dict, dists: list[float], pv: float, full_pv: float, own_qty: int | None, cap_usd: float) -> tuple[int | None, str | None]`,
  `acctsize.most_default(pv: float, full_pv: float) -> int`.
- Produces: `LabDesk._takers(unit, per, booked, want=None, row_sizes: dict | None = None)`; `row_sizes[account]` replaces that account's size.
- Produces: `status_view(name)["most_default"]` (int) for the UI.

- [ ] **Step 1: Write the failing tests**

```python
MNQ, NQ = 2.0, 20.0
def test_legacy_row_is_untouched():
    assert row_size({"account": "A", "qty": 3}, [10], MNQ, NQ, None, 0) == (3, None)
    assert row_size({"account": "A", "qty": 3}, [10], MNQ, NQ, 2, 0) == (2, None)   # own_size: min
def test_contracts_wins_over_own_size():
    assert row_size({"account": "A", "qty": 4, "size": "contracts"}, [10], MNQ, NQ, 1, 0) == (4, None)
def test_risk_rounds_and_rounds_down_when_over_10_pct():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [25], MNQ, NQ, None, 0) == (10, None)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 1000}, [83], NQ, NQ, None, 0) == (None, ROW_NO_SIZE)  # 1 NQ = $1,660
def test_pair_uses_wider_stop():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [10, 25], MNQ, NQ, None, 0)[0] == 10
def test_most_and_backstop_cap():
    r = {"account": "A", "qty": 1, "size": "risk", "risk_usd": 5000}
    assert row_size(dict(r, most=20), [1], MNQ, NQ, None, 0) == (20, None)
    assert row_size(r, [0.25], MNQ, NQ, None, 0) == (100, None)          # backstop: 10 minis = 100 micros
    assert row_size(r, [0.25], NQ, NQ, None, 0) == (10, None)
def test_cap_usd_and_unmeasurable_stop():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [25], MNQ, NQ, None, 300) == (6, None)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [0], MNQ, NQ, None, 0) == (None, ROW_NO_SIZE)
def test_most_default():
    assert most_default(MNQ, NQ) == 20 and most_default(NQ, NQ) == 2
```

Labdesk event tests: two accounts booked, A `{"qty": 1, "size": "risk", "risk_usd": 500}`, B legacy `{"qty": 2}`, an NQ-micro strategy entry with a 25-pt stop → `engine.lab_enter` receives `sizes == {"A": 10, "B": 2}`. A risk row with a 0-pt stop → A refused `ROW_NO_SIZE`, B still sent. An ON cycle group with `risk_usd` → its size for every account (row ignored). Legacy parity: the existing own_size and `max_qty` tests pass unchanged.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** `row_size` / `most_default` (rule in Global Constraints; `contracts` and `risk` both clamp to `most` else the backstop). In `_verdicts`: per row, per entry, `q_i = row_size(row, [dist_i], pv, full, own_qty_i, limits.max_risk_usd)`; pass `q_i or 1` to `door.check_event`, set `why = ROW_NO_SIZE` when `q_i` is None; the `q > limits.max_qty` check only for rows without `size`. Distances via `door._entry_price(it, {"last_price": last})` as `_group_size` does. Add `LabDesk._row_sizes(name, ev, unit, booked, last) -> dict[str, int]` (rows with `size` only; the unit's distances together) and pass it to `_takers` at the four call sites. Add `"most_default"` to `status_view`.
- [ ] **Step 4: Run** `tests/test_acctsize.py tests/test_labdesk*.py tests/test_labrun_door.py tests/test_engine_groups*.py` → PASS.
- [ ] **Step 5: Commit** `"desk: size per account -- contracts or risk, most contracts, backstop (per-account settings 2)"`

### Task 3: Stop after a win / in profit

**Files:**
- Modify: `homebase/desk/engine_lab.py` (`_lab_sits_out` 977-1010, constants ~57)
- Modify: `homebase/desk/labdesk.py` (`_enter` untaken rule ~1609)
- Test: `tests/test_engine_lab.py`, the labdesk event tests

**Interfaces:**
- Consumes: `stop_after` on the row from Task 1; `ROW_NO_SIZE` from Task 2.
- Produces: `engine_lab.LAB_DONE_WIN`, `engine_lab.LAB_DONE_PROFIT`; `labdesk.OWN_RULE` = `(door.SLOT_BUSY, GROUP_HEDGE, ROW_NO_SIZE, LAB_ACCOUNT_STOPPED, LAB_DONE_WIN, LAB_DONE_PROFIT)`.

- [ ] **Step 1: Write the failing tests** — `test_stop_after_win_sits_out_after_a_winner`: row `stop_after: "win"`, one closed round today net +$40 → `_lab_sits_out(...) == LAB_DONE_WIN`; with net −$40 → None. `test_stop_after_profit_sums_closed_nets`: closed +$40 and −$60 → None; +$40, −$20 → `LAB_DONE_PROFIT`. `test_open_round_not_counted`: a live round with pnl None → not counted. `test_other_account_unaffected`: account B (no rule) → None. Labdesk: two entries both refused on their only account with `LAB_DONE_WIN` → `d["untaken"] == 0` and the strategy is not stopped.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement**: in `_lab_sits_out`, after the daily-limit check, read the account's row from `assignments(self.cfg, name)`; closed rounds = this strategy's `day_states` on that account with `status not in ("placing", "placed", "live")` and `pnl is not None`; nets via `self._net_pnl(s, cfg, s.pnl)`. In `_enter`, replace the inline `(door.SLOT_BUSY, GROUP_HEDGE)` with `OWN_RULE`. (Cycles: the turn already asks `_lab_sits_out`, so a done account is skipped; add one cycle test confirming the turn moves on.)
- [ ] **Step 4: Run** `tests/test_engine_lab.py tests/test_labdesk*.py tests/test_engine_groups*.py` → PASS.
- [ ] **Step 5: Commit** `"desk: stop after a win or in profit, per account (per-account settings 3)"`

### Task 4: Loss lock for the whole account

**Files:**
- Modify: `homebase/config.py` (`AccountCfg` ~96, save ~285), `homebase/desk/dayrules.py` (`DayRules`, `merge_rules`, `LOCK_*`, `DayBook.record_close`), `homebase/desk/engine_dayrules.py` (`rules_for`, `day_view`, `apply_day_lock`), `homebase/routes/control.py` (`/api/account-day-lock`)
- Test: `tests/test_risk_dayrules.py`, the route test that covers `/api/account-day-lock`

**Interfaces:**
- Produces: `AccountCfg.day_loss: float = 0.0`; `DayRules.day_loss: float = 0.0` (4th field, default keeps every existing constructor call valid); `dayrules.LOCK_LOSS = "day_loss"`; `day_view()["day_loss"]`; route body `{account, day_lock?, day_loss?}` (at least one).

- [ ] **Step 1: Write the failing tests** — `record_close(-300, DayRules(day_loss=250))` → `"day_loss"` and `locked == "day_loss"`; −200 → None; a later +500 close does not unlock. `merge_rules` keeps the lowest positive `day_loss`. `apply_day_lock` with closed net −300 and day_loss newly set to 250 → locks now. An account with only `day_loss` → a Lab entry is not refused `LAB_TAKE_RULE`. Route: `{account, day_loss: 250}` saves, journals `account_day_lock_set` with `day_loss` and `previous`; `{account}` alone → 400; `day_loss: -1` → 400. Config round-trip keeps `day_loss`, omits it at 0.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement**: `record_close` checks the loss after the take/lock (`elif rules.day_loss and self.closed_net <= -rules.day_loss + 1e-9`). `rules_for` appends `DayRules(0.0, own, False, own_loss)` when either is set. Leave `DayRules.any` as it is unless every caller reads it as "a lock exists" (read callers first; the `LAB_TAKE_RULE` test pins behaviour). The page's lock words (`dayState` in `popups.js`) say "Loss lock hit" for `"day_loss"` — done in Task 5.
- [ ] **Step 4: Run** `tests/test_risk_dayrules.py` + the control route test + `tests/test_engine_lab.py` → PASS.
- [ ] **Step 5: Commit** `"desk: whole-account loss lock (per-account settings 4)"`

### Task 5: The account settings sheet; side panel read-only

**Files:**
- Create: `homebase/static/desk/acctset.js`, `tests/js/acctset.test.mjs`
- Modify: `homebase/static/desk/book.js` (`acctRow` 9-31, `pickAsg`, `editQty`, `removeAsg`), `homebase/static/desk/desklabset.js` (`DeskLabSet.nodes` 48-118), `homebase/static/desk/popups.js` (`dayState` words for `day_loss`), `homebase/static/apple/desk.js` (`setupDeskLab` ~335, only if it renders its own inputs), `homebase/static/index.html` (script tag + `?v=`), `tests/test_desk_page.py` (DESK_PINS, manifest assert), `tests/js/deskbook.test.mjs`, `tests/js/desklabset.test.mjs`

**Interfaces:**
- Consumes: row fields (Task 1), `status.lab.most_default` (Task 2), `/api/account-day-lock` with `day_loss` and `account.day.day_loss` (Task 4).
- Produces (pure, testable): `AcctSet.label(row) -> string` ("×N" or "$X risk"), `AcctSet.tag(row) -> string` ("stops after a win" / "stops in profit" / ""), `AcctSet.rowFrom(form, prevRow) -> row` (drops `most` when removed, `stop_after` when "none"), `AcctSet.needsAsk(prev, next, live) -> bool` (live and (bigger contracts, bigger risk, or switched to risk)), `AcctSet.withRow(book, row) -> book` (replaces one account's row, keeps every other row's fields), `openAcctSet(strategy, account)`.

- [ ] **Step 1: Write the failing JS tests** — `label({qty: 3}) === "×3"`, `label({qty: 1, size: "risk", risk_usd: 500}) === "$500 risk"`; `tag({stop_after: "win"}) === "stops after a win"`; `rowFrom` with Most removed has no `most`; `needsAsk` true for a live switch to risk and a live raise, false for a lower size or a non-live account; `withRow` keeps another row's `risk_usd`. `deskbook.test.mjs`: `editQty` / `pickAsg` / `removeAsg` keep other rows' new fields; a Lab row with `size` opens the sheet on click instead of the inline qty box. `desklabset.test.mjs`: the four setting rows render as text, no `input`, and no `setLabSetting` call.
- [ ] **Step 2: Run** `node --test tests/js/acctset.test.mjs tests/js/deskbook.test.mjs tests/js/desklabset.test.mjs` → FAIL.
- [ ] **Step 3: Implement** the sheet in the current look: section "This strategy on this account" (Size: Contracts [N] / Risk [$]; Most contracts with "+ Add" / "Remove", added at `most_default`; Stop after: Never / A win / In profit; note "The account cycle sizes this strategy while it is on" when an ON cycle with `risk_usd` holds it) and section "Whole account — every strategy on it" (Profit lock $, Loss lock $). Save: `needsAsk` → `confirmDlg` with `liveBookingNote`; POST `/api/book` with `withRow`; then POST `/api/account-day-lock` only with the values that changed. `acctRow`: a "Settings" button (`btn btn-outline btn-sm`) for Lab strategies beside Calendar; the ×N span shows `label(row)` + `tag(row)`. Side panel rows read-only. Bump every touched script's `?v=` and DESK_PINS; manifest if apple files change.
- [ ] **Step 4: Run** the JS tests above plus `.venv/bin/python -m pytest tests/test_desk_page.py -q` → PASS.
- [ ] **Step 5: Commit** `"desk: account settings sheet; side panel settings read-only (per-account settings 5)"`

### Task 6: Practice Desk check and full run

**Files:** none new (fix in the owning task's files if something fails).

- [ ] **Step 1:** Full suites: `.venv/bin/python -m pytest -q -x` and `node --test tests/js/*.test.mjs` → all PASS.
- [ ] **Step 2:** Start the Practice Desk (`tools/fake_desk.py` through `.claude/launch.json`; it has no day-lock route — note it, check the lock fields by unit test only). In the browser: open a Lab strategy, click Settings on an account row, set Risk $500 + Most 20 + Stop after a win, save; the row shows "$500 risk · stops after a win"; reload keeps it; remove Most → saved without it; the side panel rows show as text. Screenshot for the owner.
- [ ] **Step 3:** Ask the owner before merging to main (main ships to the VPS).
