# Video notes: 2BtwoTCxcbc - JJ Simon "Why your trading strategy doesn't matter on prop firms"
https://www.youtube.com/watch?v=2BtwoTCxcbc | 12:03 | captions read in full + every slide (2026-10-19)
No chart trading. Slides on prop-firm math: sizing, copy trading, edge vs speed. Same trader as the fair-price rulebook.

## His own numbers about his strategy
- Win rate 41% at 1.5R (stop 1, target 1.5), about 10 trades a day.
- Break-even at 1.5R = 40%. After commissions, spread and slippage his 41% is "about 40%": break-even on a live account, maybe a loser.
- He says the edge comes from the prop sizing, not the strategy.
- Spends ~$40k a month on evals, gets back ~$140k on average. $1.8M payouts, $550k spent, ~$1.3M profit, 3.5x.
- He will NOT share his exact risk management (sells it in his mentorship).

## Slides (exact numbers)
Act 1, zero edge: 40% win, 1.5R, 0.000R per trade. On a $50k prop account at $100 an attempt.
"The product is calibrated": to cover a $100 fee you need a $2,000 payout 5% of the time; a coin flipper at normal sizing gets 5.1%. Fee, target, trailing floor and payout threshold are tuned so a coin flipper at the size people naturally pick walks away with nothing.

Six points of win rate (1.5R, sized right):
| Win rate | Edge per trade | Get paid | Per year |
|---|---|---|---|
| 38% | -0.050R | 6.6% | $2,031 |
| 40% | 0.000R | 8.9% | $4,678 |
| 42% | +0.050R | 10.5% | $6,443 |
| 44% | +0.100R | 13.2% | $9,120 |
| 46% | +0.150R | 15.6% | $11,473 |
(Even 38%, a loser, shows money: that is his sizing claim.)

What sizing is worth (zero edge, 40%):
| | Payout chance | Money |
|---|---|---|
| Needed to cover the fee | 5.0% | 0 |
| Sized the obvious way (same R on eval and funded) | 5.1% | $11 a year |
| Sized correctly | 9.3% (8.9-9.3 by firm) | +$85 an attempt ($185 back per $100), $5,169 a year |

Ten accounts, one year (zero edge, sized right):
| | Average year | Bad year (1 in 10) | Chance of a losing year |
|---|---|---|---|
| Same trades copied to all ten | $43,498 | -$8,000 | 16.5% |
| Traded independently | $44,452 | +$27,100 | ~0% |
"Copying one sequence across ten accounts is not ten accounts. It is one account, ten times bigger." Same EV, no diversification.

Edge is realised in time (45% win, +0.125R per trade):
| Risk per trade | Per attempt | Days per attempt | Per year |
|---|---|---|---|
| 0.30% | +$787 | 204 | $965 |
| 0.65% | +$411 | 48 | $2,150 |
| 1.00% | +$214 | 18 | $2,933 |
| 1.50% | +$205 | 10 | $5,100 |
| 3.00% | +$178 | 4.5 | $9,833 |
Risk less = more EV per attempt; risk more = 10x more per year (one account at a time).

Three inputs, one answer: your EDGE (measured, not guessed, net of costs, 500+ trades), your FREQUENCY (trades a day at the same quality), your FEES (what an attempt costs, how many you run). Those decide sizing; not entries, indicators or setup. Change one and the answer moves.

## Rules for sizing (his)
- 1.5R is "statistically optimal" for the prop environment (his claim).
- Size each stage for its own goal: eval = chance of +$3,000 before -$2,000; funded = EV (payout chance x payout size). Also different: funded near a payout, after a payout, live. Different firm = different R. Different balance = different R.
- Don't copy-trade the same entries on every account; trade accounts independently (same EV, far less variance).
- With a real edge: higher risk = faster payouts, more per year; lower risk = more EV per attempt but slow.
- More trades and more accounts = more money, if each trade keeps the same edge.

## What this means for us
- By his own numbers the strategy is ~40% at 1.5R net = break-even (realized-R:R break-even 40%). Our pipeline needs win rate >= break-even + 3 (43% at 1.5R): his own figures would NOT pass it, and would not get the Live tag (he says it's break-even live).
- His whole claim is that prop sizing turns break-even into profit. That is a prop-sim question (pass odds and EV per attempt by stage), not a strategy question. We retired the prop simulator on 2026-10-18 (one pipeline); testing his claim would need the owner's call.
