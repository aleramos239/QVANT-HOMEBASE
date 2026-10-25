# Video notes: 0uAQUHEB_L8 - JJ Simon "How To Make $30,000/Month Trading Prop Firms EASILY"
https://www.youtube.com/watch?v=0uAQUHEB_L8 | 23:12 | captions read in full + slides and charts (2026-10-19)
Three parts: the math, the account stack, the strategy (3 NQ 1m New York days, Aug 12-14 2026). Same fair-price rule (see jj-simon-fair-price-rulebook.md).

## Part 0: the math (slide)
- At 1.5R break-even is exactly 40% (2.5p - 1 = 0). A 50% win rate would be +0.25R a trade and $5,000 -> ~$857,000 in a year: "don't be unrealistic".
- Speed > win rate:
| | 5% edge, 1 trade a day | 1% edge, 10 trades a day |
|---|---|---|
| Win rate | 45% | 41% |
| Pass probability | 58.4% | 32.1% |
| Days to resolve | ~200 | ~34 |
| Cost per funded account | $171 | $311 |
  About double the cost but ~6x faster -> he prefers many trades a day.
- Backtest AS a prop account: start $50k, lose $2k (trailing) = account gone, count how often you reach $53k first; respect consistency and minimum-winning-day rules. That gives your pass rate. Then payout rate. Then payouts > expenses.

## Part 1: account stack ($20k -> ~$50k in a month)
1. $20k = 200 evals at ~$100.
2. 33% pass -> 66 funded.
3. Same 33% reach +$3k on funded -> 22 accounts at $3k = $66k sim money.
4. Payout rule (Topstep, Lucid, etc.): 5 winning days of $150, then take half.
5. Cycle 1: 22 x $1,500 = $33,000. Cycle 2: 22 x $750 = $16,500. Cycle 3: 22 x $375 = $8,250. Total $57,750 -> after the 90% split ~$52k. Net ~+$30k a month; $8,250 still in the accounts.
- Why it works even break-even: a break-even trader's funded balance drifts back to where it is; up days add winning days, down days don't remove them. So a funded account at $3k is worth ~$3k.
- Reduce risk as funded balance grows: same EV, less variance (risking the whole $1,500 as a coin flip gives the same $16.5k on average, just riskier).
- Time: 22 trading days; 3 cycles x 5 winning days = 15 days; so pass the eval in ~7 days or less (2-4 days is better).
- Max 5 funded accounts per firm -> 5-8 firms; 200 evals / 8 firms = 25 a firm a month, ~6 a week; ~10 evals a day.
- Same EV with $2k (2k -> 6k): fewer accounts, same percentage.
- Sticky note: "Don't put every account at risk at the same time." "Beat the prop firm, not the market."

## Part 2: the strategy (said here)
- Works for every session: New York 09:30, 08:30 news, 14:00, Asia (20:00), London, 18:00.
- Always 1.5R. Standard stop 25 / target 38. Opening candle > 25 pts -> size down (same 1.5R, e.g. 50 / 75 with fewer contracts).
- One continuation of the session open, then many reversions toward the bias. 10-20 entries a day.
- Continuation needs a break of structure: a choppy open with no break = no continuation until the first break (Aug 14).
- Add another continuation at the next candle close while it runs.
- Layer when it goes your way with the trend.
- Room is too small for 25 / 38 (quiet day): keep 1.5R but shrink it: 12.5 stop / 19 target when there are ~19 pts to fair. Any 1.5R works (12.5/19, 25/38, 50/75).
- Realistic win rate ~41%. Losing streaks are normal (5 in a row, then 8 wins).
- Few accounts: take only the stronger setups (more confluence). Many accounts: take every biased signal.

## Every example (NQ 1m)
| Day | What happened |
|---|---|
| Fri Aug 14 2026, 09:30 | First 3 candles choppy, no break of structure -> no continuation until the first break; continuation short W. Displacement up -> reversion longs, several entries (one L). Too close, wait for another move down; displacement entry, break-of-structure entry, more displacements; streak "2 W, 4 L, 3 W, 2 L". Box: stop 25 / target 38 ($750 / $1,380). |
| Thu Aug 13 2026, 09:30 (bad session) | Consolidation, continuation on the opening candle after a break -> barely L. Reversion displacements: 5 L in a row. Then trend turned his way: break, displacement, break, break (1 L), displacements -> 8 W. Day: 8 W vs 7 L at 1.5R = very good. |
| Wed Aug 12 2026, 08:30 news + 09:30 | Fair = pre-news price. Open continuation W, another at the candle close W. Then price stayed near fair all day: 25 / 38 impossible, so 12.5 / 19 trades on displacements / breaks whenever ~19 pts away. A 50 / 75 box drawn too (74.75 / 49.25). |
