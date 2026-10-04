**Both majors and all listed minors are fixed in `apex300.py`, `APEX300_RULES.md` and `tests/test_apex300.py`; the whole suite passes (342 tests, 42 of them mine, also green under `/usr/bin/python3`).** An earlier full run had one failure in `test_score_loader`, because `score.py` was being edited by another agent mid-run; it passes in isolation and in the final run.

I did not edit `score.py`. Its owner picked up the new API while I worked and it already calls `apex300.compliance`, `search(..., strategy/inputs/both_sides/trades)`, `other_cons` and `r_compat`.

## MAJOR 1 — Legacy availability (re-read in the browser pane, no login, no forms)
- **Status: CONFLICT between Apex's own pages, weight of evidence "purchasable now, limited time".** The "irreplaceable" claim is withdrawn.
  - The Legacy overview page (modified 2026-07-21) still says sales ended 2026-03-01.
  - The Legacy products page (modified 2026-08-25) sells six tiers on three platforms with live signup links, including the 300K.
  - The home page links to it, and the PA activation page refers to Legacy accounts bought on or after 2026-03-01.
  - I did not open the signup or checkout flow, so whether an order completes is unverified.
- **Legacy 300K evaluation** (rules file section 2b, `apex300.EVAL300`):

| Item | Value |
|---|---|
| Price | $797/month list; the card also shows $79.70/month with a coupon code (terms not shown) |
| PA fee after passing | $300 one-time per the activation page; the plan card shows $55 (conflict) |
| Profit goal | $20,000 |
| Trailing threshold | $7,500, intraday on the live peak |
| Contracts | 35 minis, no scaling in the eval |
| Daily drawdown | none |
| Minimum trading days | 7 per the help centre; the Homebase rule file says 1 (unconfirmed which applies today) |

- The existing Homebase rule id `apex-legacy-300k@2026-09-28` has the right target, threshold and contracts, but says EOD trail and 1 day.

## MAJOR 2 — compliance gate
- **One function, `compliance()`, is now the gate for `evaluate_funded`, `search` and `five_accounts`.** It reports each criterion as ok, FAIL or UNCHECKED, and anything not ok means `noncompliant=True`.
  - **One direction:** fails on `both_sides=True`, an OCO family from R's table, rows stamped `both_sides`/`oco`, or opposite-side trades that overlap in time. It passes only when the caller declares `both_sides=False`.
  - **Stop ≤ 5× target:** checked per trade from the rows' `sl`/`tp`; a missing stop or target fails. A 6-tick tolerance covers one tick of entry slippage. Without rows it falls back to `inputs["tgt_r"]`, otherwise UNCHECKED. A day stop or per-trade stop at 80% or more of $7,500 also fails.
  - **MAE rule:** fails when cuts exceed 2% of executed trades.
- `compliant(rows)` keeps only rows where all three are proven.
- The verifier's case (straddle, `tgt_r` 0.1, $7,000 day stop) is now non-compliant in both entry points with identical flags; this is tested.
- **Fail-closed consequence:** a caller that does not pass `both_sides=False` and either rows or `inputs` gets no compliant rows.
- **Gap that needs the sim owner:** l2sim rows carry no record of working orders. A family that uses `ctx.oco` or rests orders on both sides must be declared `both_sides=True` by its runner, or l2sim should stamp the rows.

## Minors
- **Half size:** default 170 micros; 175 is the variant `half_175`. The grid tops out at 170.
- **Consistency base:** "profit since last payout" is the selection default. The other reading is always reported (`cons_alt`, `*_cons_balance` columns in search).
- **Payouts 4+:** by default every request needs $307,600 and $307,600 must remain after the payout. Variants `pay4_free` (R's optimistic reading) and `pay4_req_only`.
- **Commissions:** Apex publishes Tradovate NQ $3.10 / MNQ $1.04 and Rithmic $3.98 / $1.02 per round turn. The default takes the dearer per instrument because the accounts' platform is unknown. Lucid specs keep R's costs (tested).
- **`r_compat(firm)`** restores R's readings; with it the loop is bit-identical to R and reproduces the builder's smoke table exactly.
- **Automation wording:** "supervised algo" is now labelled unconfirmed and likely non-compliant, citing the stricter Prohibited Activities page.
- **Copy trading:** copying your own accounts is confirmed allowed via the Tradovate group copier. That copier does not allow bracket/ATM orders, so stops and targets cannot ride as a bracket there.
- **Hedging:** the household / related-party clause is added.
- **Holdout seal:** now also by `entry_ms` and `exit_ms`. Non-ISO dates and files without a `trades` list raise, and a Port that already holds holdout data is refused.
- **Other code fixes:** side spellings are normalised (unknown raises); start states are validated (any approved payout implies a locked threshold); short windows, unknown starts and unknown overrides give clear errors.
- **Docs:** the routing docstring is fixed and every source carries modified and read dates.

## `five_accounts(plan)`
It returns E[$ total], P(at least one payout) and P(all bust), under both consistency readings, plus the compliance verdict. With identical start states it is the single-account lifecycle: dollars ×5, probabilities unchanged. The output note says so plainly: copying gives no diversification. Different balances per account are supported and computed jointly on the same trades.

## In-sample smoke (not a pick)
Donchian-tf15 cell 10, NY AM, 30 micros, request at $500; E[$ in 40 days] per account:

| Start | Default (since last payout) | Balance reading |
|---|---|---|
| fresh | $798 | $1,208 |
| +3,000 | $911 | $2,085 |
| +7,600 | $1,033 | $4,149 |

From a fresh start, five copies give E[$ total] $3,991, P(any payout ≤ 40 days) 0.23 and P(all bust) 0.86. Per `progress.md`, the desk shows the five accounts at $300,000, so fresh is the real state.

## Open
- The automation ban is still a user decision before any deployment.
- Still unconfirmed: consistency base, trailing type (help centre intraday vs account holder's "EOD"), 17 vs 18 minis, payouts 4+ remainder, the accounts' platform.
- Not read: WealthCharts commissions, the checkout, the User Agreement, the eval reset fee.
- `apex300_pa` and `apex50_pa` numbers scored before this change are stale, because the defaults changed.
- I did not touch `progress.md` or the vault.

Files are in `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2`:
- `apex300.py`
- `APEX300_RULES.md`
- `tests/test_apex300.py`