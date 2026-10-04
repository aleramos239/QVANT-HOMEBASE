# Apex Trader Funding — LEGACY 300K Performance Account (PA): rules and model

First read 2026-10-01 (ET evening, ~19:50); re-checked and extended 2026-10-01 ~21:30–21:50 ET after two independent
verifications (`out/build_reports/verify_rules_0.md`, `verify_rules_1.md`). `defuddle` and WebFetch get HTTP 403 on
apextraderfunding.com, so every page was read in a normal browser pane (no login, no forms, no signup flow opened).
"mod" = the page's `article:modified_time`; every source below carries the date it was modified and the date it was read.
The wording is PARAPHRASED (no long verbatim copies); each value names the source page and section so it can be re-read.
Status: **CONFIRMED** = stated on an Apex page for the 300K or by an explicit formula; **CONFLICT** = Apex's own pages disagree;
**UNCONFIRMED** = pages are silent or ambiguous; **ASSUMED** = our modelling choice.
Model: `apex300.py` (`make_spec("apex300_pa")`), tests `tests/test_apex300.py`.

**The user's accounts (desk, 2026-10-01 21:42 ET, `progress.md`):** five 300K PAs (PAAPEX …0022–0026) at $300,000 each — the
`fresh` start state is the real one; `plus3000` / `plus7600` stay as sensitivities.

## A. Read this first — account-level rules that decide whether anything may run on these accounts

| # | Rule (Legacy PA) | Consequence for this project | Source |
|---|---|---|---|
| A1 | **Automation is prohibited** on PA and Live accounts: AI, bots, algorithms, fully automated systems, HFT, any hands-off / set-and-forget / walk-away trading. Penalty: closure of the PA and forfeiture of all balances. The general Prohibited Activities page (newer, all account types) is stricter still: no automation or algorithm usage at all, rewards are meant for human traders taking part actively, not for systems executing preprogrammed logic. Software may be submitted for approval (first read of [S3]: ATM stop/target management is encouraged). | The Homebase desk trading these five PAs unattended breaches this. **"A person supervises while the algo places the orders" is our inference, stated on NO Apex page: UNCONFIRMED and LIKELY NON-COMPLIANT** under [S17]. Clearly inside the rules: a rule set a person executes by hand (with ATM brackets where the platform allows). Anything else needs Apex's written approval first. **User decision before any deployment; nothing in this pilot changes it.** | [S3] "Automation in Trading", "Automation"; [S17] "No Automation or Algorithm Usage allowed" |
| A2 | **No hedging across accounts**: never long and short at the same time in the same account or in OTHER accounts, in any correlated market (indices, metals, …; minis or micros). This includes opposite positions **with other traders in the same household or other related parties**. Penalty: account closure. | The five PAs cannot run different strategies that may hold opposite NQ directions at the same time (nor NQ long vs ES short), and nobody in the household / no related party may be on the other side in their own Apex accounts. Either one strategy copied to all five (`five_accounts`), or a cross-account direction lock. `apex300.cross_account_conflicts()` counts violations in a plan (pass the household's accounts too). | [S8]; [S3] "Hedging and Correlated Instruments Rule"; [S17] "No Hedging of Any Kind" |
| A3 | PA must be traded by the account holder only: not by another person, system, automated bot, copy-trading service or mirroring software; trade copying WITH OTHER TRADERS is forbidden. **Copying your own trades across your own accounts is supported by Apex**: Tradovate "Group Trade" is switched on automatically for any Apex user with more than one active Tradovate account, with Apex's own setup guide. | Own-account copying: **CONFIRMED allowed** (Tradovate; results of any copier remain the trader's responsibility [S3]). **Constraint: the Tradovate group copier does not allow bracket / ATM orders** (NinjaTrader is needed for brackets) and does not work inside TradingView — so with five accounts in a Tradovate group the stop and the target cannot ride as a bracket: they must be separate orders or the copy must run through NinjaTrader. Size in a group = a multiple of the group total. | [S18]; [S3] "Copy or Trading Services …", "Automation in Trading"; [S17] "Account and Resource Sharing" |
| A4 | Contract-size consistency: same contracts / size / targets through a payout cycle; size may grow with the balance, never "big at the start, small later"; all-in at the start of a PA to get over the trailing drawdown is prohibited; Apex may require 8 days at uniform size before a payout. | Fixed micros per config (what the model does). The half → full switch after the safety net is allowed growth. Advisory flag `max_allowed_size_from_day1` when a config uses the whole half-size allowance. | [S3] "Contract Size Consistency"; [S4] |
| A5 | One-direction rule: one direction at a time, and no working orders on both sides of the market (no long + short brackets waiting for a breakout; no both-side orders around news). | Straddles / OCO entry brackets / both-side resting limits are NON-COMPLIANT (gate criterion `one_direction`, flag `OCO_both_side_orders`). `open_dir` (one side chosen) is fine. Fills cannot show resting orders, so every config must DECLARE `both_sides` (True / False). | [S7]; [S3] "Directional Bias and Consistency"; [S17] |
| A6 | 5:1 rule: the stop may not exceed 5× the profit target, on every trade; a stop is mandatory (mental stops allowed); the trailing threshold must not be used as the stop. | Gate criterion `stop_5x_target`: every trade row needs `sl` and `tp` with stop ≤ 5 × target; time / trail-only exits (no target) are non-compliant; a per-trade stop or a day stop ≥ 80% of $7,500 fails too. | [S6]; [S3] "Stop Losses and Risk Management"; [S17] |
| A7 | Up to 20 active PAs per household (Legacy + new combined). **Whether a Legacy account can still be bought: CONFLICT between Apex's own pages** — see section 2b. Cancelled Legacy accounts cannot be reinstated; Legacy accounts cannot be converted to the new types. | Five PAs are fine. A blown Legacy 300K PA is **probably replaceable at a price** (a new Legacy 300K evaluation: $797 / month list, then a $300 one-time PA fee, after passing a $20,000 target) — the earlier "irreplaceable" claim is WITHDRAWN. The offer is labelled limited-time and the checkout was not tested, so do not plan on it lasting. P(bust) still costs the cushion, the payout history (safety net / cap counters restart) and weeks of evaluation. | [S1] vs [S2], [S21], [S23] |

## 1. Values for the Legacy 300K PA

| Item | Value (300K) | Spec key (`apex300.py`) | Status | Source |
|---|---|---|---|---|
| Starting balance | $300,000 | `start_balance` | CONFIRMED | [S2] plan card "300K FULL" |
| Trailing threshold (max loss) | $7,500 below the peak; liquidation at $292,500 on a fresh account | `mll=7500` | CONFIRMED | [S2] (Trailing Threshold $7,500); [S9] table "300K Full Size 35 Minis – 7500" |
| Trailing type | INTRADAY: follows the highest LIVE (unrealised) balance during trades, not closed-trade values; enforced in real time | events on open equity (MAE / MFE), primary order `pess` | CONFIRMED (help centre) — but the account holder told Homebase "EOD trail" (`homebase/.../apex-legacy-300k@2026-09-28.json`); conflict, see section 6 | [S9] "Legacy Trailing Drawdown Example"; [S10]; [S3] "Legacy Trailing Drawdown Rule" |
| Where it stops trailing | When the peak unrealised balance reaches the safety net = start + drawdown + $100 = **$307,600**; the threshold then stays at start + $100 = **$300,100** for good | `lock_at=7600`, `lock_floor=100` | CONFIRMED (formula; examples are 50K / 150K) | [S10]; [S9] "FULL Accounts" |
| Max contracts | 35 minis (350 micros) | `cap=350` | CONFIRMED | [S2]; [S9] |
| Half-contract rule | Half of the maximum until the EOD balance passes start + drawdown + $100 = **$307,600**, then full size from the next full session; full size is kept even if the balance later drops below | `half=170` (17 minis), `unlock=7600`, `sticky_full=True` | CONFIRMED rule; **UNCONFIRMED** details: 17.5 minis → 17 or 18. **Default 170 micros (rounded down: the conservative reading — 175 would be a scaling violation if Apex counts 17)**; variant `half_175`. "Exceeds" (rule text) vs "reaches" (worked example): modelled as strictly above | [S5] (re-read 2026-10-01: no 300K example); [S16]; [S3] |
| Violation of the half rule | Close the excess at once; profits from it are removed and 8 more compliant days before the next payout; repeated = closure | not modelled (the model never exceeds the cap) | CONFIRMED | [S5]; [S4] |
| 30% negative P&L (MAE) rule | Open unrealised loss may not exceed 30% of the start-of-day PROFIT balance. New / low-profit accounts (profit below the trailing-drawdown amount): 30% of the trailing threshold = **$2,250**. After the threshold has stopped trailing: 30% of start-of-day profit (≥ $2,280). | `mae_pct=0.30`, `mae_min=2250`; limit = max(30% × profit, 2,250) | CONFIRMED formula (the $ examples on the pages are 50K: $750, and 150K: $2,400 at $8,000 profit) | [S11]; [S3] "30% Negative Profit and Loss Rule" |
| MAE at higher profit | 50% instead of 30% once the EOD profit balance is twice the safety net (**$15,200**), from the next full session (→ $7,600) | `mae_pct_hi=0.50`, `mae_hi_at=15200` | CONFIRMED formula | [S11] |
| MAE scope | Pages say both "per trade" and "combined open negative P&L" | per trade (one position at a time in every pre-registered family, so identical) | **UNCONFIRMED** | [S3]; [S4] |
| MAE enforcement | Not auto-liquidated. A brief overshoot corrected quickly is not penalised; first real violation = written warning; repeated / blatant = payout forfeiture, profit removal, closure | modelled as a FORCED CUT by us at the limit (−1 tick, commission), counted (`cuts`, `cut_share`); gate criterion `mae_rule`: cuts on > 2% of trades = NON-COMPLIANT (the config relies on the rule instead of its own stop) | CONFIRMED rule; cut = ASSUMED desk behaviour | [S3]; [S11] |
| 5:1 risk-reward | Stop ≤ 5 × profit target on every trade | gate criterion `stop_5x_target` (per trade from `sl` / `tp`; `inputs["tgt_r"] < 0.2` fails) | CONFIRMED | [S6] |
| One direction / hedging / both-side orders | see A2, A5 | gate criterion `one_direction`; `cross_account_conflicts` | CONFIRMED | [S7]; [S8]; [S17] |
| Daily loss limit | None | `dll=0` | CONFIRMED | [S2] (Daily Drawdown: None); [S9] |
| Min trading days per payout | 8 trading days since the start / the last request | `min_days=8`, `days_count="traded"` | CONFIRMED; what counts as a "trading day" (we count sessions with ≥ 1 trade; half-day holidays do not count at Apex) UNCONFIRMED | [S12] |
| Min profitable days | 5 of those days with profit ≥ $50 | `win_days=5`, `win_day=50` | CONFIRMED | [S12]; [S3] "Legacy Payout Evaluation Requirements" |
| Consistency rule | 30%: the highest-profit day since the last approved payout may not exceed 30% of the profit at the request (highest day ÷ 0.3 = minimum profit required). Applies to payouts 1–5 (gone from the 6th). | `cons=0.30`, `cons_until=5`, **`cons_base="cycle"`** | CONFIRMED rule; **UNCONFIRMED base**. Two readings: `cycle` = profit accumulated since the last approved payout (key-details bullet on [S3] / [S4] / [S13]) — **the conservative one, the SELECTION DEFAULT**; `balance` = current balance − starting balance (the worked example on [S12] and the others). **Both are always reported** (`cons_alt`, `*_cons_balance` columns). They coincide for the first payout of a fresh account; they differ afterwards and for a cushion that predates the cycle. | [S12] (re-read 2026-10-01); [S13]; [S3]; [S4] |
| Safety net for payouts | Drawdown + $100 = $7,600, first THREE approved payouts only. $500 may be requested at $307,600; every $1 above $500 needs $1 more balance (the balance after the payout stays ≥ $307,100) | `net_pay=7100`, `net_pays=3` | CONFIRMED (table: 300K minimum required balance $307,600; rule text) | [S12] table "Minimum Required Balances"; [S14] |
| Payouts 4+ | The safety net stops applying from the 4th payout — but the same page requires the minimum required balance ($307,600) to approve a payout and ties the $500 minimum payout to it, without limiting either to payouts 1–3. What must remain after payouts 4–5 is not stated. | **Default (conservative): `post_req_min=7600` (every request needs $307,600) and `post_net_min=7600` (the minimum required balance must REMAIN after payouts 4–5: cheque ≤ profit − 7,600, so a request needs $308,100).** Variants: `pay4_free` = R's optimistic reading (no minimum, $200 may remain); `pay4_req_only` (request needs $307,600, $200 may remain) | **UNCONFIRMED** | [S12] "Required Minimum Balance to Request a Payout", "Minimum and Maximum Payout Amounts"; [S14] |
| Min payout | $500 (any size) | `min_pay=500` | CONFIRMED | [S12] |
| Max payout, payouts 1–5 | **$3,500** per request | `pay_cap=3500`, `cap_pays=5` | CONFIRMED | [S12] table "Maximum Payouts (First Five Payouts)" |
| Max payout, 6th+ | No maximum, provided the minimum balance threshold remains in the account after the payout | uncapped; **default `post_cap_net=7600` ($307,600 remains — conservative)**; variant `pay4_free`: $200 | CONFIRMED (no cap); which "minimum balance" UNCONFIRMED | [S12] |
| Split | 100% of the first $25,000 paid per account, 90% after | `split_until=25000`, `split_full=1.0`, `split_after=0.9` | CONFIRMED | [S12] "Payout Split Percentage" |
| Max number of payouts | None stated for Legacy (new Intraday/EOD PAs: 6) | no stop | CONFIRMED by absence | [S12]; [S15] |
| After a request | Trading may continue; trade as if the money were already gone; the request is denied if the balance falls below the minimum | cheque deducted at the request EOD | CONFIRMED | [S12] |
| Session | Flat and orders cancelled by 16:59 ET; trading day 18:00 → 16:59 ET | not modelled (strategies end 15:58 ET) | CONFIRMED | [S9] |
| Commissions (round turn) | Tradovate: NQ **$3.10**, MNQ **$1.04**. Rithmic: NQ **$3.98**, MNQ **$1.02**. Deducted from the balance per trade (the Rithmic page states one schedule for evaluation and funded accounts). | `commission="apex"` = the dearer of the two per instrument (NQ $3.98, MNQ $1.04) because the platform of the five accounts is unknown; variants `comm_tradovate`, `comm_rithmic`; `commission="R"` = R's Lucid model ($4.00 / $1.00). Every 10 micros are costed as one NQ (R's convention); trading everything in MNQ costs more (10 × $1.04). | CONFIRMED schedule; platform UNCONFIRMED | [S19]; [S20] |

## 2. Legacy vs the accounts Apex sells now (do not mix)

| | LEGACY PA (the user's five 300K) | New Intraday-trailing PA (since 2026-03-01) | New EOD PA |
|---|---|---|---|
| Availability | Existing accounts keep the Legacy rules, no retroactive change, no conversion [S1]. New purchases: CONFLICT, see 2b | sold now; sizes 25K–150K (no 250K/300K) [S15] | sold now (R/rules_research.md) |
| Payout days | 8 trading days, 5 of them ≥ $50 | 5 qualifying days (50K: ≥ $200, 150K: ≥ $300) | 5 days ≥ $250 (50K) |
| Consistency | 30% (payouts 1–5) | 50% | 50% |
| Safety net | first 3 payouts only | for the life of the PA | for the life of the PA |
| Payout caps | $3,500 × 5 on 300K, then none; no payout count limit | per-payout ladder, max 6 payouts then the PA closes | ladder, max 6 |
| Split | 100% of first $25k, then 90% | 100% | 100% |
| Contract scaling (half size), MAE 30% rule, 5:1 rule | YES — [S16] states that its five trading rules apply to Legacy PAs only | NO: the home page advertises the new accounts with no MAE rule and no 5:1 rule [S23] | same |
| Both-side bracket orders, hedging, automation | prohibited ([S7], [S8], [S3]) | **also prohibited**: the general Prohibited Activities page applies to every account type [S17] | same |
| Daily loss limit | none | not read | tiered (R/rules_research.md) |
| Contracts | 35 minis, half until the safety net | — | 4 on 50K, tiered |

Never use new-account numbers (50% consistency, 5 days, lifetime safety net, 6-payout cap) for the user's accounts, and never use
Legacy numbers for a new account.

## 2b. Can a Legacy 300K still be bought? — CONFLICT between Apex pages; weight of evidence: YES, as a limited-time offer

| Evidence | Says | mod |
|---|---|---|
| [S1] Legacy Products Overview | Legacy evaluations are no longer available for purchase to anyone as of 2026-03-01; cancelled ones cannot be reinstated | 2026-07-21 |
| [S2] /legacy-products/ | Headed as a limited-time offer of Legacy accounts, available now; 6 tiers × 3 platforms (Tradovate, WealthCharts, Rithmic) with prices and signup links, incl. `…/signup/300k-tradovate-legacy`, `300k-rithmic-legacy`, `300k-wealthcharts-legacy` | 2026-08-25 (newest) |
| [S23] home page | Links "View Legacy Accounts" to [S2] | 2026-08-25 |
| [S21] How to Activate your Legacy PA | Speaks of Legacy accounts purchased on or after 2026-03-01 (one-time PA fee only for those) | 2026-07-22 |

Status: **CONFLICT, resolved in favour of "purchasable now (limited time)"** — three pages, two of them newer than [S1], sell or
presuppose new Legacy purchases; [S1] reads as not updated. **Not verified:** the signup / checkout flow was not opened (no forms),
so whether an order completes, and for how long the offer runs, is UNCONFIRMED.

**Legacy 300K EVALUATION — cost and rules** (`apex300.EVAL300`; the user asked for the best strategy for each eval too):

| Item | Value | Status | Source |
|---|---|---|---|
| Price | **$797 / month** list (recurring until cancelled or converted). The card also shows **$79.70 / month** with a coupon code (a 90%-off promotion; code and validity not shown) | CONFIRMED (card); coupon terms UNCONFIRMED | [S2] |
| PA activation after passing | One-time lifetime fee **$300** for the 300K (the only option for Legacy accounts bought on / after 2026-03-01). The [S2] plan card shows a one-time PA fee of $55.00 | **CONFLICT** ($300 vs $55; take $300 unless the checkout shows otherwise) | [S21]; [S2] |
| Reset | Available on Legacy evaluations, for a fee; a failed account is reset free at the monthly renewal | CONFIRMED; reset price not read | [S1]; [S22] |
| Profit goal | **$20,000** (balance must close at or above $320,000) | CONFIRMED | [S2]; [S9] |
| Trailing threshold | **$7,500**, intraday on the highest live balance. Tradovate: keeps trailing through the evaluation. Rithmic: stops trailing once the threshold reaches the profit target level | CONFIRMED | [S2]; [S9] |
| Contracts | **35 minis (350 micros)**, no scaling in the evaluation | CONFIRMED | [S2] |
| Daily drawdown | None | CONFIRMED | [S2]; [S9] |
| Minimum trading days | 7 (non-consecutive), unless a 1-day-pass promotion is active. The account holder told Homebase 1 day (`apex-legacy-300k@2026-09-28.json`, written for accounts bought earlier) | **UNCONFIRMED** which applies to a purchase today | [S9]; homebase rule file |
| Consistency rule in the evaluation | None stated (the page places consistency rules on PA / funded accounts) | CONFIRMED by absence | [S9] |
| Other | flat by 16:59 ET; profit goal is net of commissions; MAE / 5:1 / half-size rules are PA rules ([S16]), prohibited activities ([S17]: no both-side brackets, no hedging, no automation) apply to every account | CONFIRMED | [S9]; [S16]; [S17] |

Scoring (2026-10-02): `score.score_eval(trades, "apex300_eval", rules, micros=)` → P(pass ≤ 10 / 20 trading days) and bust on
the help-centre reading (`apex300.make_eval_spec` / `eval_sim`: the threshold trails the highest LIVE balance through R's
intraday event orders, 7 traded days, no lock, Apex commissions). The existing rule id `apex-legacy-300k@2026-09-28` (identical in
the repo and in `.worktrees/apex300k`) has the same target / threshold / contracts but says EOD trail, a lock at +$100 and
1 minimum day: it is reported next to the headline as the variant `holder_rule_file` (the looser reading: on equal costs the
headline never passes more and never busts less). evalcore's own `intraday` breach model tests the day's worst point against the EOD-trailed threshold, so
it cannot express a threshold that trails intraday highs: that is why this evaluation is not scored by `evalcore.race`.
Economics to weigh: one attempt costs $797 (or $79.70 with the coupon) per month + $300 on passing, for a target that is 2.67× the
trailing threshold ($20,000 vs $7,500).

## 3. Compared with the previous pilot (R/FUNDED_RULES.md, R/rules_research.md — Apex Legacy 50K PA)

Same rule family, scaled: 50K → 300K = drawdown 2,500 → 7,500; safety net 2,600 → 7,600; contracts 10 (half 5) → 35 (half 17);
MAE floor 750 → 2,250; MAE 50% tier at 5,200 → 15,200; payout cap 2,000 → 3,500; min balance to request 52,600 → 307,600.
Unchanged: 8 days / 5 days ≥ $50 / 30% consistency (payouts 1–5) / safety net first 3 payouts / min $500 / 100% of first $25k.

* R's ASSUMPTION "MAE limit = 30% × max(start-of-day profit, drawdown)" is **CONFIRMED** by [S11]; R's `sticky_full=True` is
  **CONFIRMED** by [S5].
* R's readings that this module no longer uses by default (they are the OPTIMISTIC side of unconfirmed rules): consistency on
  balance − start, payouts 4+ without a minimum balance ($200 may remain), exactly half the contracts, Lucid's commissions.
  `apex300.r_compat(firm)` restores all four; with it `apex300` is bit-identical to R's loop (tested), and it reproduces the first
  smoke table of this pilot exactly.
* NEW versus R: the automation ban (A1), cross-account / household hedging (A2), own-account copying and the group-copier
  bracket limit (A3), the size-consistency text (A4), the 20-PA household limit (A7), the two readings of the consistency base,
  the min-balance table, Apex's commission schedule, the Legacy evaluation's price.
* R/funded.py already implements the MAE rule for the 50K PA; `apex50_pa` here is the 50K PA under THIS module's loop and
  conservative readings (R's `apex` = `make_spec("apex50_pa", **r_compat("apex50_pa"))`).
* `homebase/backtest/propsim/rules/apex-legacy-300k@2026-09-28.json` (account holder's words) says EOD trail and carries LucidFlex
  payout placeholders: its funded block is NOT Apex's; use `apex300.py` for the PA.
* ROUTING: `score.py` sends every extended spec (`ext=True`: `apex300_pa`, `apex50_pa`) to `apex300.lifecycle` /
  `apex300.search` / `apex300.compliance`. Never pass an extended spec to R's `funded.lifecycle` / `funded.search`: R's loop
  silently ignores the start state, `trail="eod"`, the payouts-4+ options and the Apex commissions. Two 50K-scaled constants
  inside R do not fit the 300K either: `funded.apex_flags` (any day stop ≥ $2,000 flagged) and `funded.GRID` (100 micros, $1,000
  day take) — use `apex300.flags` / `apex300.GRID`.

## 4. What the numbers imply (arithmetic, not a result)

* MAE limit on a fresh account = $2,250 of OPEN loss per position. Max adverse move before a violation, NQ points =
  2,250 / (2 × micros): 10 micros 112.5 pts · 20: 56.3 · 30: 37.5 · 50: 22.5 · 75: 15.0 · 100: 11.25 · 170 (the half cap): 6.6.
  The MAE rule, not the 170-micro cap, is the binding size limit: stop distance (pts) × micros × $2 must stay below $2,250.
* First payout needs profit ≥ $7,600 and ≥ 8 trading days (in the minimum 8 days that is $950 per day), with the best day
  ≤ $2,280 (30% of 7,600) when requesting at exactly 7,600. A day_take above ~$2,250 only delays the first payout.
* Maximum per cycle on payouts 1–5: $3,500 per account per 8 trading days (needs profit ≥ $10,600 on payouts 1–3; ≥ $11,100 on payouts 4–5 under the default reading, where $7,600 must remain); five accounts = $17,500 per
  cycle. The 100% split covers the first $25,000 paid per account (the five capped payouts are $17,500 of it).
* Under the conservative consistency reading every cycle must EARN at least best-day ÷ 0.3 again before the next payout: a
  $1,000 best day needs $3,334 of new profit in the cycle.
* Threshold room: a fresh account can lose $7,500 from its PEAK equity (open profit counts). Once the peak has touched +$7,600
  the liquidation level is fixed at $300,100.
* **Five accounts copying one account are one bet at five times the size**: the $ scale by five, the probabilities do not move —
  P(at least one payout) = P(all five pay) and P(all five bust) = the single-account P(bust). No diversification
  (`apex300.five_accounts`). Diversifying across the five would need different strategies, which A2 only allows if they can
  never be on opposite sides at the same time.

## 5. Model (`apex300.py`) — what is simulated and what is not

* Inputs: trade list (R trades.json schema, per 1 NQ; `port_from_trades`, holdout-sealed by `date`, `entry_ms` AND `exit_ms`),
  sizing (`micros=` or `contracts=`), R day rules (`day_take`, `day_lock`, `day_stop`, `max_day_tr`, `after_loss/win`), payout
  policy T (500 | 1500 | 2500 | 'max' = $3,500 | None), start state (`fresh`, `plus3000`, `plus7600`, a number, or `Start(...)`,
  validated by `resolve_start`).
* Enforced: intraday trailing breach on open equity (R's event orders `pess` primary / `nat` / `opt`), lock at +7,600, half size
  (170 micros) until EOD profit > 7,600 (sticky), MAE forced cut + cut count, payout eligibility (8 traded days, 5 × $50, 30%
  consistency on the cycle profit, the minimum required balance for every request and left in the account from the 4th payout, cap,
  uncapped 6th+), split, Apex commissions.
* **Compliance gate** (`compliance`; identical in `evaluate_funded`, `search` and `score.py`). A config is compliant only when
  all three criteria are PROVEN; FAIL or UNCHECKED ⇒ `noncompliant=True`, and `compliant(rows)` drops the row:

  | Criterion | FAIL when | 'ok' needs |
  |---|---|---|
  | `one_direction` | `both_sides=True`; an OCO family (R's table: straddle, orb, lon_break, squeeze nr7 / inside, ib break); trade rows stamped `both_sides` / `oco`; a run with both-side sessions (`both_sides_sessions` of the l2sim result / bundle); opposite-side trades that overlap in time | PROOF from rows that cover the portfolio's trades (2026-10-02; a declaration alone is UNCHECKED): **`sim_rows`** = every row carries l2sim's stamp `both_sides: false` (the simulator saw no entry orders of opposite sides working at the same time in that session), or **`market_entries`** = unstamped rows (tester bundles) that are all market entries (`order_price` present and null) AND the caller declares `both_sides=False` |
  | `stop_5x_target` | a trade without `sl`; a row without `tp` (or a target on the wrong side); stop distance > 5 × target distance measured from the fill (NO tolerance: both simulators price the bracket from the fill; 5.02 : 1 fails); `inputs["tgt_r"] < 0.2`; a per-trade stop or a day stop ≥ 80% of $7,500 | rows covering the portfolio (at least as many rows as trades, with real per-row counts) that all carry a stop and a target within 5:1; with no rows at all: `inputs["tgt_r"]` GIVEN and ≥ 0.2 and a stop on every trade. A bare `{"n": 90}`, one clean row against 90 trades, or `inputs` without `tgt_r` ⇒ UNCHECKED |
  | `mae_rule` | MAE-rule cuts on > 2% of the executed trades | cut share ≤ 2% |

  The l2sim evidence: a trade row has `oco` (its entry was a leg of a two-sided OCO pair) and `both_sides` (stamped on every
  row of a session in which entry orders of opposite sides were working at the same time, with or without a fill); a
  position's own stop / target never counts. The same check (`one_direction` only) is applied to the evaluation.
* **Evaluation** (`make_eval_spec`, `eval_sim`, `eval_lifecycle`, `eval_metrics`; `score.score_eval(trades, "apex300_eval")`):
  section 2b's help-centre reading — $20,000 goal reached at a CLOSE, $7,500 threshold trailing the highest LIVE balance (open
  P&L included, R's event orders `pess` primary / `nat` / `opt`), no lock, 350 micros, 7 traded days, Apex commissions →
  P(pass ≤ 10 / 20 trading days), bust. `EVAL_VARIANTS`: `holder_rule_file` (the homebase rule file: EOD trail locking at
  +$100, 1 day, R's costs — on that reading `eval_sim` equals `evalcore.race` on the rule file attempt for attempt),
  `min_days_1`, `trail_eod`. Rule options: R's day rules, `target_take` (stop the day at the goal, R's law), `coast` (trade n
  micros once the goal is reached and days are missing; default off, the result always reports `coast1`).

* Start states: `fresh` = the user's five PAs today. `plus3000` = profit and peak at +3,000 (threshold at −4,500; pass
  `Start(3000, peak=...)` for a higher past peak); `plus7600` = threshold LOCKED at +100, half size until an EOD above 7,600.
  The payout clock, the consistency window and the payout count start at zero; the cushion counts as earned BEFORE the cycle
  (conservative under the `cycle` reading) unless `Start(cpnl=..., cd=..., cw=..., cmax=...)` says otherwise. Any approved payout
  implies a locked threshold. Impossible states (peak below the balance, balance under the threshold, …) raise.
* Metrics (R/funded.metrics): P(≥1 payout within 20 / 40 / 60 trading days), median days to first payout, E[first cheque]
  (gross, net), E[$ to the trader within 40 and 60 days], P(bust before first payout), P(bust), E[number of payouts within 40 / 60],
  MAE cut share — always under both consistency readings.
* `five_accounts(plan)`: the five PAs as copies of one account — E[$ total], P(at least one payout), P(all bust); with identical
  start states these are the single-account numbers (× 5 for the $); with different balances the joint is computed on the same
  trades.
* Rule-uncertainty variants (`VARIANTS`, `sensitivity`): `cons_balance`, `pay4_free`, `pay4_req_only`, `half_175`, `trail_eod`,
  `comm_tradovate`, `comm_rithmic`. Smoke run (R donchian-tf15 cell 10, NY AM, in-sample, 30 micros, request at $500; NOT a pick),
  E[$ in 40 days] per account, default (cycle) vs the balance reading: fresh $798 vs $1,208 · +3,000 $911 vs $2,085 · +7,600
  $1,033 vs $4,149. Only the consistency base and (slightly) `trail_eod` move the numbers; the commission schedule moves them by
  a few dollars.
* NOT modelled: the automation / copy / size-consistency / defined-system rules (qualitative), payout review discretion and
  processing time, half-day holidays, the 16:59 ET close, the news filter in the per-trade row check, data / PA fees, Apex's right
  to deny a payout.

## 6. To confirm with Apex support / the account dashboards (in order of impact)

1. A1: is ANY software-placed order acceptable on a Legacy PA (supervised or not)? Will Apex approve the desk software in writing?
2. Consistency base: 30% of (balance − start) or of the profit since the last approved payout?
3. Trailing type on these five accounts (the dashboard shows the threshold): intraday on unrealised peak (help centre) vs the
   account holder's "EOD trail".
4. Payouts 4+: is $307,600 still the minimum to request, and what must remain after the payout?
5. Half size = 17 or 18 minis; are 175 micros accepted?
6. Which platform are the five PAs on (Tradovate / Rithmic / WealthCharts) — commissions, and whether the group copier's
   no-bracket limit applies.
7. Legacy 300K evaluation: does the checkout complete, the coupon price and its terms, the PA fee ($300 vs $55), minimum days
   (7 vs a 1-day-pass promotion), the reset fee.

## Sources (apextraderfunding.com; mod = page modified, read = when we read it, ET)

* [S1] /help-center/legacy-products/legacy-products-overview/ (mod 2026-07-21; read 2026-10-01 19:5x and 21:3x)
* [S2] /legacy-products/ (mod 2026-08-25; plan cards and signup links; read 2026-10-01 19:5x and 21:3x)
* [S3] /help-center/performance-accounts-pa/legacy-performance-account-pa-compliance/ (mod 2026-04-15; read 2026-10-01 19:5x; automation / copy / scaling sections re-read 21:4x)
* [S4] /help-center/legacy-helpful-items/what-are-the-consistency-rules-for-legacy-pa-and-funded-accounts/ (mod 2026-04-15; read 2026-10-01 19:5x)
* [S5] /help-center/legacy-helpful-items/legacy-contract-scaling-rule/ (mod 2026-04-15; read 2026-10-01 19:5x and 21:4x)
* [S6] /help-center/legacy-helpful-items/legacy-5-1-risk-reward-ratio-rule/ (mod 2026-04-15; read 2026-10-01 19:5x and 21:4x)
* [S7] /help-center/legacy-helpful-items/one-direction-rule-directionally-biased-trading/ (mod 2026-04-15; read 2026-10-01 19:5x and 21:4x)
* [S8] /help-center/legacy-helpful-items/hedging-and-correlated-instruments-rule/ (mod 2026-04-15; read 2026-10-01 19:5x and 21:3x)
* [S9] /help-center/evaluation-accounts-ea/legacy-evaluation-rules/ (mod 2026-07-22; read 2026-10-01 19:5x and 21:3x)
* [S10] /help-center/legacy-products/legacy-trailing-drawdown-rule/ (mod 2026-07-22; read 2026-10-01 19:5x)
* [S11] /help-center/legacy-helpful-items/legacy-30-negative-p-l-rule-mae/ (mod 2026-04-15; read 2026-10-01 19:5x)
* [S12] /help-center/legacy-payouts/legacy-pa-payout-parameters/ (mod 2026-07-22; read 2026-10-01 19:5x and 21:3x)
* [S13] /help-center/legacy-helpful-items/legacy-30-consistency-rule-windfall/ (mod 2026-04-15; read 2026-10-01 19:5x)
* [S14] /help-center/legacy-payouts/legacy-safety-net-requirement-rule/ (mod 2026-07-22; read 2026-10-01 19:5x)
* [S15] /help-center/intraday-trailing-drawdown-accounts/intraday-trailing-drawdown-payouts/ (mod 2026-04-28; read 2026-10-01 19:5x)
* [S16] /help-center/performance-accounts-pa/legacy-performance-account-pa-trading-rules/ (mod 2026-07-31; the five rules that apply only to Legacy PAs; read 2026-10-01 19:5x and 21:4x)
* [S17] /help-center/getting-started/prohibited-activities/ (mod 2026-07-31; all account types; read 2026-10-01 21:3x)
* [S18] /help-center/tradovate/tradovate-group-copier/ (mod 2026-06-10; read 2026-10-01 21:3x)
* [S19] /help-center/tradovate/tradovate-commission-instruments/ (mod 2026-08-12; read 2026-10-01 21:3x)
* [S20] /help-center/rithmic/rithmic-commissions-instruments/ (mod 2026-07-22; read 2026-10-01 21:3x)
* [S21] /help-center/legacy-evaluation-accounts/how-to-activate-your-legacy-pa/ (mod 2026-07-22; read 2026-10-01 21:3x)
* [S22] /help-center/evaluation-accounts-ea/legacy-evaluation-subscription-billing/ (mod 2026-07-22; read 2026-10-01 21:3x)
* [S23] / (home page; mod 2026-08-25; read 2026-10-01 21:3x)
* Not read: the WealthCharts commission schedule, the signup / checkout pages, the User Agreement that [S3] and [S17] refer to.
* Secondary (search-engine summaries, not read as primary): Apex 4.0 launched 2026-03-01; 250K / 300K not sold in 4.0.
