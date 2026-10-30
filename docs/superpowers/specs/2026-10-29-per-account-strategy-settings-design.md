# Per-account strategy settings (owner, 2026-10-29)

## Why

The owner runs the same strategy on several accounts (evals, funded, paper) and wants each account to trade it its own way:
"for every single strategy i want to remove editing them from the panel and i only want to be able to edit it from the actual
account itself, that way i can adjust it per account, i want to be able to pick set risk or set contracts, also have more
options i can add like stop after win and more". What he wants to differ per account: "the risk per trade or contract size,
or maybe when to lock the account after a certain amount in profit or loss".

## Today (facts the design rests on)

- Every strategy on the live (VPS) Desk is a Lab strategy (`lab_<record>`); `config.json` has no built-in Desk strategy booked.
  So this covers **Lab strategies only**. Built-in Desk strategies are left as they are.
- A Lab strategy runs as ONE copy in the runner; its one entry goes to every booked account (`labrun/fanout.py`). The only
  per-account setting is the size `×N` in the sidecar book row `{account, qty}` (`<desklab>/<name>.desk.json`,
  `LabDesk.set_book` / `check_book`, `labdesk.py:699-734`).
- The side panel's editable rows ("Risk per trade ($)", "First entry", "Target (x the stop)", "Stop for the day once up ($)")
  are the record's `params`, edited through `POST /api/lab-settings` (`DeskLabSet.nodes`, `desklabset.js:48-118`). They go
  into the strategy's code: one value for all accounts.
- An account-cycle group with `risk_usd` already resizes every member's order at the Desk: `labdesk._group_size`
  (`labdesk.py:1522-1545`): n = round(risk / (stop distance x point value)), rounded down if more than 10 % over, capped by
  the strategy's `max_risk_usd`, fail closed when no contract fits.
- The account's own "Day take $" (`AccountCfg.day_lock`, `POST /api/account-day-lock`) locks the WHOLE account once the
  day's closed net (after fees) reaches it: no new entry on any strategy, resting entries cancelled, open positions keep
  their own stop/target (`engine_dayrules.py`, `DayBook.record_close`, `_lock_account`). Lab legs honour it through
  `account_locked` (`engine_lab.py:984`).

## What the owner decided

1. **The side panel stops editing.** "Risk per trade", "First entry", "Target", "Stop for the day once up" become read-only
   rows there (owner: "Read-only for now"). They stay strategy-wide; nothing deletes them.
2. **Each account row gets its own settings**, edited from that account (the strategy page's account row, `div.acct`):
   - **Size: set risk OR set contracts.** Contracts = today's `×N`. Risk = $ per trade, the Desk works out the contracts
     from that trade's stop.
   - **Stop after:** never / **a win** (the first winning trade of the day on that account ends this strategy's day there)
     / **in profit** (once this strategy's closed net for the day on that account is above $0, done for the day there).
3. **Profit lock and loss lock are for the WHOLE account** (owner: "The whole account"): once the account's day is up $X
   (the existing "Day take $") or down $Y (new), every strategy on that account stops for the day.

## The design

### Per strategy-on-account (book row)

Book rows grow from `{account, qty}` to `{account, qty, size, risk_usd, stop_after}`:

| Field | Values | Default (a row written before this) |
|---|---|---|
| `size` | `"contracts"` \| `"risk"` | `"contracts"` |
| `qty` | contracts when `size = contracts` (as today) | as stored |
| `risk_usd` | $ per trade when `size = risk`, > 0 | absent |
| `stop_after` | `"none"` \| `"win"` \| `"profit"` | `"none"` |
| `most` | most contracts on this account, or absent (box removed) | absent |

An old row reads exactly as today: **nothing trades differently until the owner changes a row.** A row with no `size`
field is "the strategy's own" (today: fixed `×N`, or for an `own_size` strategy its own size up to `×N`).

- **The account wins over the strategy's own size** (owner, 2026-10-29: "Yes, account wins"). Once a row is set to
  Contracts or Risk, that size is used on that account even for `own_size` strategies (the candle break / sweep family,
  overnight ORB) whose code sizes from `params.risk`: Contracts N = exactly N; Risk $X = the Desk's size from the stop.
- **Most contracts** (owner: "20 micros or 2 minis to start with ... i can set it higher", "be able to also remove or add
  the max contracts box"): a box on the row, added with a default of 20 micros (2 minis on a mini strategy), editable,
  removable. It caps both modes, and replaces the backtested `max_qty` cap for that row (so Contracts may go above the
  backtested size). It counts the order only, not other strategies' open contracts on the account (my call; the owner
  set aside firm scaling plans for now).
- **Backstop when the box is removed** (my call, safety): a Desk-wide hard cap of 10 minis' worth (100 micros) per
  order still applies, so a tiny stop can never send a huge order.

- **Risk sizing** reuses `_group_size`'s rule per account: n = round(risk_usd / (stop distance x point value)), rounded
  down when more than 10 % over; capped by the row's Most contracts (or the backstop) and the strategy's `max_risk_usd`
  when set. When not one contract fits
  or the stop cannot be measured, that account sits this trade out with a worded reason in the journal (fail closed);
  other accounts still trade.
- **Stop after** is checked per account before an entry (beside `max_rounds` in `engine_lab._lab_sits_out`), from that
  account's closed rounds of this strategy today: `win` = any closed round with net > 0; `profit` = sum of closed nets > 0.
  A round still open does not count. Only new entries stop; an open trade keeps its stop/target.
- **Own-rule sit-outs do not stop the strategy** (my call): an account that sits out for its own rule (stopped after a
  win / in profit, locked, no contract fits the stop, ceiling) does not count toward "two entries no account took"
  (`d["untaken"]`), the way slot-busy and group-hedge refusals are already excluded.

### Per account (whole account)

- **Profit lock** = the existing `AccountCfg.day_lock` ("Day take $"), unchanged.
- **Loss lock** (new) `AccountCfg.day_loss` ($, 0 = off): when a trade closes and the day's closed net (after fees) is at
  or below -day_loss, the account locks (owner: Desk trades only, like the profit lock; hand trades are not counted) for the day exactly like the profit lock (`DayBook.locked = "day_loss"`, no new
  entry anywhere, resting entries cancelled, open positions keep their own stop/target). Setting it at or above an
  already-reached loss locks at once (as `apply_day_lock` does for the profit lock). A lock is never lifted the same day.

### The account settings sheet (UI)

A **Settings** button on each account row of a strategy's page opens a small sheet in the current look (no restyle):

- **This strategy on this account:** Size (Contracts [N] / Risk [$]), Most contracts (+ add / remove), Stop after
  (Never / A win / In profit).
- **Whole account** (labelled so, shared by every strategy on it): Profit lock $, Loss lock $.
- Save writes the row through the existing book route (`POST /api/book` rows carry the new fields) and the account
  locks through `/api/account-day-lock` (+ the new loss value).

The `×N` on the row shows "×N" or "$X risk"; a small tag shows "stops after a win" / "in profit" when set.

## Safety (must hold)

- A row change is never applied to a trade already open: it takes effect from the next entry (today `×N` can be changed
  mid-trade too; nothing new is refused).
- Raising the size on a LIVE account asks first, as `editQty` does today. Switching a live row to risk sizing asks too.
- Every change is journalled (old and new values).
- Risk sizing can never send more than the row's Most contracts, or the 100-micro backstop when the box is removed.
- Loss lock and profit lock count CLOSED net only (as the existing lock does); an open loss is not counted.

## Not in this change

- Per-account first entry, target or any setting that changes the signal (would need one runner copy per account).
- Built-in Desk strategies (none booked on the live Desk).
- Automatic ceilings from firm rules and scaling plans (`scaling_micros` in the prop rule files) and a Firm rules picker
  (owner: "its okay for now"). Later.
- Account-cycle groups keep their own sizing: while a strategy's cycle with `risk_usd` is ON, the cycle's size wins over
  the row's (as today), and the sheet says so (my call). A cycle without `risk_usd` uses the row's size; a row's stop-after
  or lock takes that account out of the cycle's turn like a locked account (my call).

## Left to the builder

- Exact field names, the sheet's markup within the current look, and test layout.
- Where the per-account closed rounds for "stop after" are read from (`self._lab` rounds or the DayBook).
- Version bumps (`?v=`, `DESK_PINS`, Apple manifest) per the repo's rules.

## Done when

- Old book rows trade exactly as before (parity tests for sizing and entries).
- Unit tests: risk sizing per account (fits, rounds down, fails closed, capped), stop after win / profit, loss lock locks
  and cancels resting entries, refusals while a trade is open, old rows read as contracts.
- Checked on the Practice Desk: the sheet saves, the row shows the setting, the side panel rows are read-only.
- Committed on a branch; merged to main (= the VPS) only on the owner's word.
