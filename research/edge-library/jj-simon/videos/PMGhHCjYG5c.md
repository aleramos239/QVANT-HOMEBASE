# Video notes: PMGhHCjYG5c - JJ Simon "How Quant Finance Made Me $1.6M Trading Prop Firms"
https://www.youtube.com/watch?v=PMGhHCjYG5c | 18:46 | uploaded 2026-08-20 | captions read in full + slide frames (2026-11-02)
Story + stats lessons (data mining, t-stat, losing streaks, ruin vs volatility), then one NQ 1m chart showing how he picks the account by points to fair.

## Summary
Four blow-ups ($50 Topstep eval at 14, ~$500, $5,000, then $60,000 in one day on a funded account grown from 50K to $110K) taught
him: the best of many backtests is luck; 30 trades say nothing (t ~ Sharpe x sqrt(years)); losing streaks are normal; and
**position sizing** matters more than the strategy: P(ruin) ~ exp(-2 x Sharpe x D / sigma), so cutting volatility is the overnight
fix. Prop "chips are not dollars": optimise for not hitting the max loss. He takes ~20 trades a day for 16 months (~7,000 trades).
Strategy: open = fair, revert to it; each trade goes to the account whose needs match the points available (1 contract x 25 pts,
2 x 20, 3 x 50...). Every stop is static (fixed points), never at a swing.

## Numbers he states
- $1.6M payouts (Aug 2026). Degree: computational finance and risk management, U. of Washington, graduated at 19 (May 2025).
- **~20 trades a day for 16+ months, >7,000 trades.** One-setup-a-day traders get ~252 a year.
- t-stat ~ Sharpe x sqrt(years) at Sharpe 1.0: 6 weeks 0.34, 6 months 0.71, 1 year 1.00, 4 years 2.00. "A losing month is not evidence either."
- Streaks, 50 % win rate, 100 trades: lose 4 in a row 97 %, 5 in a row 81 %, 6 in a row 55 %. He once lost **11 in a row**
  ("my R:R is high, so losses are supposed to outnumber wins" -> his win rate is below 50 %).
- Sizing example: $2,000 max loss, $500 risk a trade -> 4 losses = account gone; 97 % chance of 4 in a row over 100 trades ->
  "statistically guaranteed to blow this account. Your strategy is irrelevant to that sentence." (=> risk per trade must be well under 1/4 of the drawdown.)
- Slide: live account = maximise profit, chip = dollar; prop account = do not hit max loss, chip != dollar. "The account is not money.
  It is a claim on every payout you would have made later - worth $0 the second you breach." A +EV trade can still be the wrong trade.
- **P(ruin) ~ exp(-2 x Sharpe x D / sigma)** (Brownian motion, Sharpe 1, 10 % static drawdown): volatility 40 % -> 61 % fail,
  20 % -> 37 %, 10 % -> 14 %. Futures prop drawdowns are ~4 %, even tighter.
- **"Trailing drawdown is much worse. Don't buy the trailing-drawdown accounts; significantly less EV than end-of-day accounts."**
- His first news reversion lost; it's now his most profitable trade.

## Strategy / account assignment (chart)
- Fair = the session open (unless news changes fair value). Look for reversions to the open on displacement candles.
- Points available to fair decide the account: examples 28, 22, 22, 22, 50 points toward fair.
  "Maybe a specific account needs a 1 contract 25 point trade ... a different account needs 2 contracts 20 points ... another needs
  3 contracts 50 points." -> **match each signal to the account whose static target fits the room to fair.**
- On a live account you'd enter once and ride to target; on prop you split the move across accounts by what each account needs
  (payouts over the account's life, risk of being moved live, risk of ruin).
- Every stop is static (fixed), never above/below the previous high/low.
- He admits breaking his own rules to "get through all of my accounts" each day (impatience costs EV).

## Not stated
Exact stop/target points, $ risk per trade, win rate (only "below 50 %"), firm list, daily stop, rotation order.
