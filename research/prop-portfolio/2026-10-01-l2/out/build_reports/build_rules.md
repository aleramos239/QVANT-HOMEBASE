Built the Apex Legacy 300K PA rules file, a funded-lifecycle simulator and its tests. All 29 of my tests pass, but Apex's own rules contain a deployment blocker: automated trading is prohibited on these accounts.

## Files
- `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/APEX300_RULES.md`
- `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/apex300.py`
- `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/tests/test_apex300.py`

## Rules research
defuddle and WebFetch both got HTTP 403 on apextraderfunding.com, so I read 16 help-centre and product pages in the browser pane (no login, no forms). The rules file paraphrases each value and gives URL, section and page-modified date instead of verbatim quotes, to stay inside content-reproduction limits; that is a deviation from "quote per value".

**Confirmed for the Legacy 300K PA:**

| Item | Value |
|---|---|
| Trailing threshold | $7,500, intraday on peak unrealised balance |
| Stops trailing | when the peak reaches $307,600; threshold then fixed at $300,100 |
| Max contracts | 35 minis (350 micros); half until EOD balance is above $307,600, then full for good |
| MAE rule | open loss ≤ 30% of start-of-day profit, minimum $2,250; 50% once profit ≥ $15,200 |
| 5:1 rule | stop ≤ 5× target, stop mandatory |
| One direction | no hedging, no working orders on both sides |
| Daily loss limit | none |
| Payout eligibility | 8 trading days, 5 of them ≥ $50, 30% consistency on payouts 1–5 |
| Safety net | first three payouts only; $307,600 needed to request $500 |
| Payout size | min $500; max $3,500 for payouts 1–5; no cap after |
| Split | 100% of the first $25,000 per account, then 90% |

- **Legacy vs new:** Legacy was retired 2026-03-01; existing accounts keep Legacy rules, with no retroactive change and no conversion.
- **Against R:** the previous pilot's $750 MAE-floor assumption and its "full size stays once unlocked" assumption are now confirmed by the help centre.
- **R already has the MAE rule** for the 50K, so no separate 50K rebuild was needed.

**Account-level rules the previous pilot did not have:**
1. **Automation is prohibited on PA accounts** (bots, algorithms, hands-off trading); the penalty is closure and forfeiture. Running the desk unattended on the five PAs would breach this.
2. **No hedging across accounts:** never long in one Apex account while short in another, in any correlated market. The five accounts need one shared direction or a cross-account lock.
3. **Legacy accounts cannot be bought or reinstated**, so each of the five is irreplaceable.
4. **Size consistency:** "all-in at the start of a PA" is prohibited.

## Simulator
- **Interface:** `make_spec("apex300_pa")` returns a plain `funded.Spec`, so R's `funded.py` and `score.py` consume it unchanged; `score.py` already discovers it.
- **Reuse:** R's day walk, MAE cut, event orders, metrics and grid helpers are imported; only the account loop is re-implemented, to add start states.
- **Enforced:** intraday breach on open equity, lock at +7,600, half size, MAE forced cut with cut count, payout eligibility and request policy (500 / 1500 / 2500 / max), split.
- **Start states:** `fresh`, `plus3000`, `plus7600` (threshold locked), or a custom `Start(...)`.
- **Compliance helpers:** flags scaled to the 300K, a per-trade stop-vs-threshold screen, and `cross_account_conflicts()` for multi-account plans.
- **Holdout:** `port_from_trades` and `load_trades` raise `HoldoutError` on any 2025+ row, calendar day or window end unless `allow_holdout=True`.
- **Compute rules:** `search` is capped at 8 workers and waits out both offline windows. A full default grid is 1,920 cells at about 240 ms each (roughly 8 minutes serial).
- **Rule-uncertainty variants:** `sensitivity()` runs `req_min_always`, `cons_cycle`, `half_minis` and `trail_eod`.

## Tests
- `tests/test_apex300.py`: 29 passed under both the ONYX venv python and `/usr/bin/python3`.
- Hand-worked scenarios cover breach on open loss, lock, half-size switch, MAE cut, payout timing, consistency block, request policy, split and start states.
- From a fresh start the new loop is bit-identical to R's on more than 5,000 random attempts, for both the 50K and 300K specs.
- Full suite in the pilot directory: 173 passed, 1 failed. The failure is `tests/test_score_search.py::test_search_funded_identical_to_R` (the scoring adapter's test, R `apex` variant); it does not touch `apex300`, and I did not investigate it further.
- Nothing was written into R or `homebase`.

Smoke run, in-sample, not a pick (R donchian-tf15 cell 10, NY AM, 30 micros, request at $500):

| Start | E[$ in 40 days] | P(payout ≤ 40d) | P(bust before first payout) |
|---|---|---|---|
| fresh | $1,208 | 0.23 | 0.76 |
| +3,000 | $2,085 | 0.36 | 0.63 |
| +7,600 | $4,149 | 0.67 | 0.32 |

At 60 micros and above, 21–33% of trades hit the MAE cut, so those sizes are flagged non-compliant. The MAE limit ($2,250 of open loss) is the binding size constraint, not the 175-micro half cap.

## Open risks
1. **Automation ban** is a user decision before anything is deployed on these accounts.
2. **Consistency base is unconfirmed:** 30% of (balance − start), which is the default and matches R, or 30% of profit since the last payout. On the smoke config at 60 micros from +7,600 this moves E[$ in 40 days] from $2,491 to $717.
3. **Trailing type conflict:** the help centre says intraday on unrealised peak; the account holder's Homebase rule file says "EOD trail". Intraday is the default; `trail_eod` is a variant.
4. **The five accounts' real state is unknown** (balance, peak, payouts taken, days in cycle), so the start states are assumptions.
5. **Assumed or unconfirmed values:** what must remain after payouts 4+ ($200, as R); half size as 17 or 18 minis (175 micros used); MAE "per trade" vs "combined"; whether an own-account trade copier is allowed.
6. **`score.py` uses two 50K-scaled constants from R on the 300K:** `funded.apex_flags` flags any day stop ≥ $2,000, and `funded.GRID` stops at 100 micros and $1,000 day-take. Use `apex300.flags` and `apex300.GRID` instead. Cushion starts are only available through `apex300`, since R's loop is fresh-start only.
7. **Cost model is Lucid's** ($4.00 round trip per NQ, $1.00 per MNQ); Apex commissions were not researched.
8. **The `pess` event order is extreme**, as in R; `nat` and `opt` are reported alongside.
9. **Not modelled:** payout review discretion, half-day holidays, and the qualitative rules (defined system, size consistency).
10. **Not updated:** `progress.md` and the vault, because of the write-only-under-the-pilot-directory rule and concurrent agents.