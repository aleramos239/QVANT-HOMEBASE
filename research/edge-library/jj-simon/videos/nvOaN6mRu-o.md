# Video notes: nvOaN6mRu-o - JJ Simon "How Poker Math Made Me $100K/Month Trading Prop Firms"
https://www.youtube.com/watch?v=nvOaN6mRu-o | 24:49 | uploaded 2026-09-29 | captions read in full + Miro whiteboard frames (2026-11-02)
Theory video: poker ideas (EV, pot odds, variance, GTO, multi-tabling, bankroll) mapped to prop evals. No chart trading.

## Summary
Price the decision (the eval), not the trade: EV = P(payout) x payout - fee. Break-even payout rate = fee / payout. Expect long
losing streaks even with positive EV; check whether your payout rate has fallen into the bottom 5 % of luck. A prop rule set is a
complete-information game, so there is one best way to trade it: model each account state (what the account is worth after a win
or a loss) and pick the trade size that maximises P(win) x value(after win) + P(loss) x value(after loss); if you can't, at least
simulate several firms and use the one your strategy fits best. Unlike poker multi-tabling, on a prop firm he prefers MORE risk on
ONE account over tiny risk on many (a $200 risk needs ~15 more wins than losses to reach +$3,000). Bankroll: risk of ruin < 0.5 %.

## Numbers he states
- EV example: 30 % chance of a $300 payout, $50 eval -> 0.3 x 300 - 50 = **+$40** per eval (he later calls it "+90 %"; the
  board says 90 = 0.3 x 300). Break-even payout rate = 50 / 300 = 1 in 6.
- Fee should include activation fees and resets; also fees and slippage in simulations.
- Streak: 70 % no-payout, 10 evals in a row all fail = 0.7^10 = 2.8 %. If the chance of your actual run falls below ~1 %, be wary;
  below 0.5 % assume "something's gone wrong" (strategy or execution, not luck).
- Payout-rate noise: expect 30 %, 20 attempts can land anywhere ~19-41 % (95 % band, his example).
- Validate with **200+ trades** (5 trades is nothing). He says he knows his win rate at 0.5R, 1R, 2R, 3R from "over a year of
  actual trading and eight years of back testing".
- Break-even win rate formula: stop / (stop + target). 1:1 = 50 %, 1:2 = 33 %.
- Firm choice example: one account "20 % consistency", another "100 % consistency but $2K payout cap" vs "$5K payout cap": the same
  strategy performs very differently; simulate and pick the better one.
- Account-state model (board): from A0, a win goes to state A1 (+$800 or +$1,000), a loss to A2 (-$800 / -$1,000).
  Example values: account worth $700 after +$800, $900 after +$1,000. Choose the size with the best P(w) x value(win) + P(l) x value(loss).
  Bigger target = lower P(win) and bigger loss; that's the trade-off. Board: "Optimize the rules. Validate the market edge."
- Multi-tabling slide ("Multi-table the process. Measure the correlation."; "Copying trades does not diversify market risk"):
  poker: $200 risk as 10 x $20 tables beats 1 x $200 (60 % double-or-nothing: losing all 10 = 0.4^10 ~ 0.01 %).
  **Prop: he picks 1 account x bigger risk over 10 accounts x $200**, because the eval is +$3,000 / -$2,000: at $200 a trade you need
  to win 15 more than you lose, "it's going to take you forever". Same total risk, more on one account, to get there faster.
- Bankroll slide ("Bankroll management buys survival"):
  - Cash budget: $1,000 / $50 total cost per attempt = **20 attempts**. Include every fee; don't budget from the advertised account size.
  - Account room: $2,000 remaining loss room / $100 risk = **20R to the limit** ("distance to failure, not 20 safe losses";
    trailing rules reduce the room).
  - "Cap spending per firm and across the portfolio." Risk of ruin target **< 0.5 %**.
- Kelly criterion: he points to it for bankroll-optimal sizing (exact use not stated).
- Tracks every attempt like a poker session: buy-in (fee), cash-out (payout), dates, duration, ROI, game type -> for trading: instrument, R:R, win rate, firm, plan.

## Not stated
His actual risk per trade, stop/target in points, win rate, trades a day, firm list, cycling order, daily stop.
