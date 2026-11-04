# Video notes: sWJa8vRfPb8 - JJ Simon "Why I Can't Show You My Risk Management (It Would Kill Prop Firms)"
https://www.youtube.com/watch?v=sWJa8vRfPb8 | 19:52 | uploaded 2026-09-15 | captions read in full + Miro board frames incl. 3 full-res (2026-11-02)
Why he won't publish his sizing table, and how to build your own: objective per stage, value of an account state, a toy simulation.

## Summary
"Risk management" = stop, target and contract size together, chosen per account state. Combinations: ~25 firms x 3 plans x 3 sizes x
eval / funded (new, in drawdown, in profit, after payout) / live (new, in profit, in drawdown) = "1,800 at the minimum". His dashboard
simulates "millions" of stop/target pairs per firm, plan, balance and drawdown and prints the one with the most expected cash. He
won't post it (firms would change rules; people would copy one firm's numbers onto another, or the eval's onto the funded). He keeps
200-250 students max. Strategy is bias-based ("slight linear drift in the direction of my bias") so any moment can host a prop trade:
a very specific setup with a fitted target/stop (e.g. $832 / $516) won't fit any firm's rules.

## Objectives per stage (slide)
| Stage | Optimise |
|---|---|
| Live (own or firm live) | net trading return (adjust for drawdown, include fees) |
| Eval | P(reach target before losing the account); once profitable, optimise for TIME (speed) |
| Funded | expected cash withdrawn; nothing else (not profit, not survival) |
Track on every account: balance, distance to max loss, top balance (trailing), payout eligibility.

## Numbers / examples
- Cost of a funded account = eval price / pass rate: $100 at 25 % = **$400**. Value of a funded = expected future payouts (sunk fees
  are not charged on later losses). Example: 50 % chance of a $2,000 payout = $1,000 value -> $600 profit per funded
  (or 0.5 x (2000 - 400) - 0.5 x 400 = 600). Multiple payouts: 0.5 x 2k + 0.5 x 0.5 x 1k, etc.
- How to get the value: in replay, trade 50 funded accounts over a year; e.g. $50k payouts / 50 = $1,000 per funded.
- Slide 04 "Same $1,000 losing trade. Different account state" (funded, $2,000 room both):
  | State | Loss floor | Value now | After -$1,000 | Value drop |
  |---|---|---|---|---|
  | Fresh | -$2,000 | ~$410 | ~$205 | ~$205 |
  | +$2K profit | $0 | ~$1,002 | ~$501 | ~$501 |
  "Size for the state of the account. Then re-run the numbers when that state changes." (fixed-policy example, $500/$500 after the loss, 100 days)
- A funded account $2k in profit can be treated like a $2,000 live account (static setting) - its value is closer to cash.
- Slide 05 toy sim: 100 random +$50/-$50 step paths, 1:1 exits $500 stop / $500 target, no drift or costs, split into 10 eval
  attempts of max 10 trades, eval +$3,000 pass / -$2,000 fixed floor: 47 W / 53 L, P&L -$3,000; **0 passed, 2 failed, 8 still open**
  ("open does not mean failed": at $500 risk 10 trades rarely reach +6 net wins).
- Slide 06 "Change the target" (same paths, same $500 stop):
  | RR | Win rate | P&L | Pass | Fail | Open |
  |---|---|---|---|---|---|
  | 1:1 ($500) | 47 % | -$3,000 | 0 | 2 | 8 |
  | 1:1.5 ($750) | 43 % | +$3,750 | 1 | 2 | 7 |
  | 1:2 ($1,000) | 39 % | +$8,500 | 2 | 3 | 5 |
  Notes on slide: all three have zero expected profit in this fair model; sample too small to rank; a 1R winner can reverse before 2R.
- "Less risk with more edge increases pass rate; more risk with less edge increases pass rate" -> the optimal risk depends on your edge.
- Track: eval spend (most important), payouts in $ (second). Cost per funded = eval price / pass rate. Payout side = P(payout) x size.
  Pass rate, payout rate and payout size are all set by the risk management and pull against each other.
- Plans named: Tradeify (Instant, Growth, Select), Lucid (Daily?, Flex, Pro), Topstep (one plan).
- Simple route: pick ONE firm whose rules you like, find the optimal approach for it, trade only that one.
- "Copying someone else's number skips the context": don't copy the size he uses on stream.

## Not stated
His actual stops/targets/risk, win rate, trades a day, which firm he'd pick, cycling order.
