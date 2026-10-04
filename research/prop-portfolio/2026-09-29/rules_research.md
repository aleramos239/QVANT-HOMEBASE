# Prop-firm rules research (primary sources only), retrieved 2026-09-30

Sources: Lucid help centre (support.lucidtrading.com, read with defuddle; "mod" = page dateModified) and
Apex help centre (apextraderfunding.com; defuddle/WebFetch got HTTP 403, so pages were read in a normal
browser pane, no login/forms). Quotes are verbatim, <= 25 words.

## 1. LucidFlex 50K (evaluation and funded)
| Item | Finding | Source (mod) |
|---|---|---|
| Drawdown type | "LucidFlex evaluation and funded accounts use an End-of-Day Drawdown (EOD Drawdown) system to calculate the Max Loss Limit (MLL)." | /articles/12945815-lucidflex-drawdown (2026-08-26) |
| EOD trail rule | "At the end of each trading session, the system calculates the account's highest closing balance"; "The MLL increases as your balance grows, up to a defined point" | same |
| Breach wording | "If your account balance reached the MLL, your account will be breached." (says "balance"; open P&L / real-time NOT stated) | same |
| MLL numbers (50K) | MLL $2,000; Initial Trail Balance $52,100; Locked MLL Balance $50,100 (locks at start + $100 once exceeded; also locks on first payout request) | same |
| EOD update time | No explicit clock time on drawdown page. Session close/flatten: "All positions must be closed by 4:45 PM EST"; reopen 6:00 PM EST Sun-Thu. "Holding a position past this time does not result in a failed account" | /articles/11404729-allowed-trading-times (2026-08-26) |
| Eval targets | 50K: profit target $3,000; MLL $2,000; consistency 50%; max "4 mini or 40 micros" | /articles/12945790-lucidflex-evaluation-account (2026-08-31) |
| Daily loss limit | Eval: "Optional DLL available at checkout". Funded: "optional Daily Loss Limit, no consistency rule and no payout buffer." (DLL is a soft breach, see Pro) | evaluation page; /articles/12945795-lucidflex-funded-account (2026-08-15) |
| Eval consistency | "you must have Consistency Percentage of 50% or less to be eligible to upgrade" (largest day / total profit); small cushion built in "so that traders ... can pass in two days" ($1,560 biggest day on 50K at exactly target) | /articles/12945805-lucidflex-consistency-percentage (2026-08-26) |
| Min days (eval) | No minimum stated; "take as long as you need to pass". Consistency implies >= 2 days at target (cushion) | evaluation page |
| Max contracts | Eval: 4 minis / 40 micros from day 1 ("no scaling plan in the evaluation phase"). Funded: scaling by sim profit, updated at end of session: $0-999 = 2 minis; $1,000-1,999 = 3; $2,000+ = 4 | /articles/12945808-lucidflex-scaling-plan (2026-05-06) |
| Funded consistency | "There is no Consistency Percentage on LucidFlex funded accounts" | funded page |

## 2. LucidPro 50K
| Item | Finding | Source (mod) |
|---|---|---|
| Drawdown | Same EOD system as Flex: MLL $2,000, trail balance $52,100, locked at $50,100 | /articles/12890136-lucidpro-drawdown (2026-08-26) |
| DLL amount | Fixed DLL $1,200 (50K), eval and funded (until close above $52,100 trail balance) | /articles/12890122-lucidpro-daily-loss-limit (2026-07-26) |
| DLL behaviour | "All DLLs at Lucid Trading are considered soft breaches, meaning you do not lose your account for hitting DLL as long as the Max Loss Limit (MLL) has not been reached." At DLL: "restricted from placing additional trades until the next trading session" | same |
| DLL removable? | Yes, at purchase only: "Daily Loss Limit Off"; "these settings cannot be changed for an active account". Off = higher price | /articles/16226068-lucidpro-customization (2026-08-06) |
| DLL after trail | Once the account "closes above the Initial Trail Balance", fixed DLL is replaced by LucidScale DLL = highest EOD profit x 60% | DLL page |
| Eval | Target $3,000; MLL $2,000; max 4 minis / 40 micros; "Pass the evaluation in one trading day" (no min days, no eval consistency listed) | /articles/12890029-lucidpro-evaluation-account (2026-08-26) |
| Funded consistency | "must meet a Consistency Percentage of 40% to be eligible to request a payout" (35% for accounts bought/reset before 2025-11-28 3PM EST); resets each payout | /articles/12890109-lucidpro-consistency-percentage (2026-08-26) |
| Funded size | "No scaling plan, access to max contract size immediately" (4 minis on 50K) | /articles/12890069-lucidpro-funded-account (2026-08-26) |

## 3. Apex Trader Funding (apextraderfunding.com)
Product-name note: "Legacy" IS an Apex product label. Legacy = pre-3.0 accounts, with an INTRADAY live trailing threshold
("based on the highest live value during trades, not on closed trade values"). It is not an EOD account. The EOD accounts
are a separate newer family ("EOD Trailing Drawdown Accounts") with different numbers. Do not mix the two.

| Item | Legacy 50K (intraday trail) | EOD 50K (eval / PA) |
|---|---|---|
| Drawdown | $2,500; "trails ... behind the highest balance reached ($50,875) even though you closed at a lower amount"; PA stops trailing at start + $100 | Eval $2,000; PA $2,000 (EOD PA page). Threshold "calculated once per trading day at 4:59:59 PM ET"; "never moves downward" |
| Real-time enforced? | Yes (intraday peak incl. open P&L) | Yes: "Even though the threshold is calculated at end-of-day, it is enforced in real time." and "If at any moment ... the account balance touches or falls below the EOD Threshold, all open positions are automatically liquidated" |
| Includes unrealized? | Yes | PA page: "Your account balance, including unrealized PnL, may never touch or fall below the End-of-Day (EOD) Drawdown threshold." |
| Profit target | Not on the fetched legacy pages (UNCONFIRMED here; commonly $3,000) | $3,000 |
| Max contracts | 10 minis (PA starts at half = 5 until EOD balance > $52,600) | Eval 6; PA 4 (tiered 2/3/4 contracts by profit: $0-1,499 = 2, $1,500-2,999 = 3, $3,000+ = 4) |
| DLL | "No Daily Max Drawdown" in legacy eval rules | Eval DLL $1,000 fixed; PA DLL tiered $1,000 / $1,000 / $2,000 / $3,000 (profit tiers), "applies to total account equity, including both realized and unrealized" - liquidates and pauses, account stays alive |
| Eval consistency | None ("no consistency rules" in evals) | "Not Applied" |
| Min days | Eval: "minimum of seven trading days" (unless promo) | Eval: "No minimum trading days required, may pass in one trading day"; 30 calendar day access |
| PA payout | 8 trading days, 5 of them >= $50; 30% consistency rule ("no single trading day accounts for more than 30% of the total profit balance"), until 6th payout; safety net (DD + $100) first 3 payouts; min $500; max $2,000 on 50K for first five, none after; 100% of first $25K then 90% | 5 qualifying days each >= $250 net; "No single profitable trading day may account for 50% or more of total profit since your last approved payout"; safety net = DD + $100 for life of PA ($52,100 on 50K; min balance to request $52,600); min $500; caps $1,500/$1,500/$2,000/$2,500/$2,500/$3,000 for payouts 1-6; max 6 payouts; 100% split |
| Other PA rules (legacy) | 30% negative P&L (MAE) rule: open loss per trade <= 30% of start-of-day profit (30% of $2,500 = $750 for new accounts) | Not on the EOD PA page |
| Close time | All positions flat by 4:59 PM ET; trading day = 6:00 PM to 4:59 PM ET | same |
Dates: EOD drawdown/PA/payouts pages 2026-04-28; EOD evaluations 2026-06-05; DLL and scaling pages 2026-04-15/16; legacy eval rules 2026-07-22; legacy PA payout parameters 2026-07-22; legacy consistency 2026-04-15.
URLs: /help-center/eod-trailing-drawdown-accounts/{eod-drawdown-explained,eod-evaluations,eod-performance-accounts-pa,eod-payouts}/, /help-center/evaluation-accounts-ea/legacy-evaluation-rules/, /help-center/legacy-payouts/legacy-pa-payout-parameters/, /help-center/legacy-helpful-items/what-are-the-consistency-rules-for-legacy-pa-and-funded-accounts/, /help-center/additional-helpful-items/{daily-loss-limit-explained,scaling-levels-pa-explained}/.

## 4. Lucid funded-phase (Flex vs Pro, 50K)
| Item | LucidFlex funded | LucidPro funded |
|---|---|---|
| Payout eligibility | "at least the minimum required profit on 5 separate days" (50K: $150/day) plus positive net profit in the cycle; both reset after each payout | Min profit goal $500 (50K) + consistency <= 40% + profit above buffer |
| Consistency | None | 40% of cycle profit (35% on older accounts) |
| Buffer | "There is no buffer balance" | Buffer = initial MLL + $100 ($52,100 on 50K) |
| Min / max request | Min $500; max 50% of profit up to $2,000 on 50K, does not scale with payout number; 5 payouts, then moved live | Min $500; payout 1 max $2,000, payouts 2+ max $2,500 (50K); "No simulated payout caps" on funded page (conflicts with per-payout maxima) |
| Split | 90/10 | 90/10 |
| Scaling | Yes (2/3/4 minis at $0/$1k/$2k sim profit; end-of-session update; payouts can move you down a tier) | None |
| DLL | Optional at purchase | Optional at purchase; fixed $1,200, becomes 60% of peak EOD profit after trail balance |
Sources: /articles/12945796-lucidflex-payouts (2026-07-28), /articles/12890092-lucidpro-payouts (2026-08-06), /articles/13425130-new-live-structure (2026-09-23).
Live: after payouts, live accounts start $0 balance, EOD drawdown, no DLL, no consistency, MLL locks at $100 after profit = start drawdown.

## What this means for the EOD-vs-intraday breach model
- Apex EOD accounts: enforcement is INTRADAY against the EOD-set threshold, using balance including unrealized P&L. Only the trail
  (peak reference) is EOD; the breach test is real time. Model: threshold_t = max(EOD closes) - DD (never down; PA locks at start+$100);
  fail the moment intraday equity (mark-to-market, incl. open P&L) <= threshold_t. An EOD-close-only breach test is WRONG for Apex.
- Apex DLL: separate real-time rule on equity incl. open P&L; liquidates and pauses the day but does NOT fail the account.
- Apex Legacy: peak is intraday incl. open P&L (harder than EOD). Never use Legacy numbers ($2,500 DD, 10 minis, 30% consistency)
  for an EOD-account sim.
- Lucid Flex/Pro: trail is EOD (highest closing balance) like Apex. Breach is stated as "account balance reached the MLL" with no
  clock-time or open-P&L language; the only Lucid text on the intraday vs EOD distinction is LucidDaily ("Intraday drawdown brings your
  MLL up with your real-time P&L; EOD ... at the end of a session"). Conservative default: assume real-time liquidation when equity
  (incl. open P&L) touches the EOD-set MLL, the same as Apex. Treat "fail only on EOD close below MLL" as an unconfirmed optimistic variant.
- Lucid DLL is soft (lock out for the session, account alive). Model as day-stop, not failure; removable only at purchase (Pro/Flex).
- Position holding: Lucid auto-flattens at 4:45 PM ET without failing; Apex requires flat by 4:59 PM ET. Trail update times: Apex
  4:59:59 PM ET explicit; Lucid only "end of each trading session" (assume 4:45-5:00 PM ET, session-close balance).
- Funded phase in the sim: Flex payouts need 5 days >= $150 + positive cycle profit, no consistency/buffer, cap $2,000; Pro needs
  40% consistency + $500 goal + buffer. Apex EOD PA needs 5 days >= $250, 50% consistency, safety net, capped $1,500-$3,000.

## NOT confirmed from primary sources
1. Whether Lucid liquidates in real time on unrealized equity touching the MLL (help pages only say "balance"); no page found with
   explicit real-time or open-P&L wording. A search-engine summary claimed "Unrealized gains and losses do not affect the drawdown
   calculation" but the source page was not identified or read.
2. Exact clock time of Lucid's EOD MLL update (4:45 PM ET flatten is documented; the trail time itself is not).
3. LucidFlex/Pro eval minimum days: none stated (Pro: "one trading day"; Flex: two days via consistency cushion, not a stated rule).
4. Apex Legacy 50K profit target and contract count for the intraday-Legacy eval are not on the fetched legacy pages (only 7-day min,
   $2,500 DD, 10 minis for PA/full size); Legacy DLL not stated (only "No Daily Max Drawdown").
5. Whether the Apex "Legacy" 50K the requester means is the $2,500 intraday Legacy or an EOD account (Legacy is not EOD).
6. LucidPro funded page says "No simulated payout caps" while the payouts page lists per-request maximums; Pro caps taken from the payouts page.
7. Apex PA 50K EOD max contracts: PA table says 4, scaling starts at 2; the legacy 10-contract figure is a different product.
8. Apex defuddle/WebFetch access blocked (403); text read via browser pane, dates from article:modified_time meta tags.
