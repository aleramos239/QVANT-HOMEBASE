# Video notes: dJdBnSBJlgQ - JJ Simon "I spent $550,000 on prop firm evaluations and learned this"
https://www.youtube.com/watch?v=dJdBnSBJlgQ | 35:44 | uploaded 2026-09-22 (recorded Sept 2026) | captions read in full + Miro board frames incl. 3 full-res (2026-11-02)
His totals, firm list, the "price the eval-to-payout process" slides, his Lucid order history, the account-state EV idea, risk of ruin.

## Summary
$550k of evals -> $1.931M of payouts after split in ~19 months (Feb 2025 -> Sep 2026). Mostly 150K accounts (avg eval ~$250),
~2,200 evals, ~116 a month across ~20 firms (~6 per firm per month), ~483 payouts at ~$4,000 average = about one payout per
eval on average ("more like 50 % chance of 2 payouts, 50 % of 0"). He now optimises $ per month, not ROI. Lessons: price the
eval-to-payout process (the eval = one big trade: risk the fee, win the funded account's value), size per account state, don't
copy trade, don't use tiny risk on many accounts, keep risk of ruin < 0.5 %. The strategy "was not the bottleneck": many entries
with a slight bias, stop and target fitted to the firm.

## Claims about himself
- Payouts by firm (pages shown): Topstep ~$300k, Lucid ~$140k, Tradeify $180k, FundedNext $177k, E8 $288k, My Funded Futures $87-92k,
  Alpha ~$80k, Hola Prime ~$60k, Funded Seat ~$46k (+ live accounts), Take Profit Trader ~$60-70k, Apex ~$60k.
- Month by month: Dec/Jan ~$200, Feb 2025 $17k (from $5k), then $40k, $46k, May $83k, 5th month six figures; "over $100k every month since".
- Spends ~$40-50k a month on evals for ~$130-150k payouts (~3x). "3x return is totally doable". His average ~3.5x.
- ~10-12 firms "sent me live" and he stopped trading them; active on ~10 now ("best 10 by EV per hour").
- Losses: one Apex funded account lost **$60k in one day** going for a "record payout" when $60k was ready to withdraw (tilt).
  Wrong instrument (NQ instead of MNQ, "max 15-20 MNQ") cost him "$50-100k" over time.

## Rules / numbers
- **Eval = one trade.** 50K eval, -$2,000 / +$3,000, fee $100, funded worth ~$1,000 (assumed) -> risk $100 to win $1,000 = "10x":
  profitable if more than 1 in 10 evals pass.
- Slide "I am pricing the eval-to-payout process": simulated account $4,500 risk / $9,000 target (a 150K plan); $250 fee -> $1,000 value
  (assumed expected cash of a funded account after passing, not cash at pass). Full loss allowance used = $250 fee at stake; half
  the allowance = $125 on a proportional basis. **EV = P(pass) x $1,000 - $250**; break-even pass rate 25 %.
- Example "100 attempts. Count all 100" (illustration, not his results): $250 fee, 30 % pass, 40 % of funded get a $4,000 payout ->
  30 funded, 12 paid, $48k payouts - $25k fees = **+$23k**. If only 6 paid instead of 12 you lose money.
- Sample sizes: at least 50 evals AND 50 funded accounts, and 100-200 trades, before trusting rates.
- Funded value depends on its state: near a payout (e.g. 54K balance, +$4k, $2k payout due soon) is worth more than the same
  balance far from a payout. Value = payout chance x payout size; he only counts cash that hits the bank.
- Account-state tree (made-up numbers on the board): from 50K, +-1K at 50/50 vs +2K at 33/66: compare
  P(win) x value(after win) + P(loss) x value(after loss); pick the target/stop with the higher number. His "risk management dashboard"
  does this for every account state (eval / funded / live, balance, drawdown, firm, plan type: Flex, Direct, Instant, Growth...)
  and prints the "statistically optimal" size. He trades by hand; the dashboard sizes.
- **Copy trading:** no new EV, more variance, and in prop it LOWERS EV: many accounts in profit at once -> more likely to be sent live
  (live accounts stop payouts). "Copying trades does not create independent outcomes."
- **One account at $2,000 risk beats 10 accounts at $200** (speed): at +-$200 you need 15 more wins than losses for +$3,000.
- "Count fit": don't force the same setup into every account; each account (balance, firm, payout rules) is worth a different amount.
- Daily goal on an account now: end the day in profit (said as his current aim; detail not stated).
- Risk of ruin: P(pass) 33 % x P(payout) 33 % ~ 10 % -> 90 % chance an eval pays nothing; with $1,000 (10 evals at $100): 0.9^10 = 35 %.
  Target < 0.5 % (he says $5k start gave him "sub 0.005"). Too high -> raise pass rate (fewer, better trades) and payout rate
  (**go for smaller payouts**: higher chance of reaching a smaller balance).
- Compounding plan: $5k -> $17k -> $51k -> $151k, 3.5x per cycle; cycles may now take ~2 months each ("profits have changed").
- Two equal-EV funded plans: 20 % chance of $10k vs 50 % chance of $4k (both $2k EV): with a small budget prefer the 50 % one.
- Start: one 50K account payout first (to prove firms pay), then he went to 150K accounts.
- "Choose your account before the risk": never a flat "$500 a trade"; risk depends on firm, stage and payout conditions.

## His Lucid order history (frames)
- Orders: **LucidMaxx 150K TDV/NT** and "LucidMaxx Reset 150K TDV/NT" at **$510** each (May 2026 resets at $425).
- Round that paid: 8 evals in August (8 x $510 ~ $4k) -> a ~$26k payout around Aug 19-20 (payout rows of $3,000 each visible).
- Before that: ~$10k of evals (April-July) for **$0** of payouts ("got to funded on max, got absolutely nothing").
- First Lucid run: ~$6k spent -> ~$105-120k (went live). Lucid overall: ~$20k spent, ~$105-150k back. Point: big variance per round.

## Strategy (as said here)
- "The most basic strategy": enter on a bias, assume a slight linear drift that way, take as many trades as possible (here, here, here).
- All take-profit and stop sizes are fitted to the prop firm, not the market.
- Risk per trade, stop/target points, win rate, trades/day: not stated in this video.
