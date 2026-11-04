# Video notes: KsfBGgX-CTM - JJ Simon "Why Wait 40 Years to Retire? (The Prop Firm Plan)"
https://www.youtube.com/watch?v=KsfBGgX-CTM | 7:30 | uploaded 2026-10-29 | captions read in full + slides and charts (2026-11-02)
Slides "How to Retire Through Prop Firm Income" + a quick NQ 1m evening chart run. Same trader and fair-price rule as RULEBOOK.md.

## Summary
A month plan: put $6,000 into 60 evals at $100, expect 1 in 3 to pass (20 funded), 1 in 3 funded to reach +$3,000, and each of those
to pay ~$2,700 over its life (break-even trader, winning-day firms, 90 % split) = ~$16-18k back. The only stated assumption is the
33 % pass rate. Eval and funded have different goals (pass rate vs payout EV). Don't copy trade. Strategy: 18:00 / 20:00 fair-price
continuation + reversions, "you can get through a lot of accounts with this strategy".

## Claims about himself
- $2M+ prop payouts: E8 Markets $306k, Topstep ~$300k, Lucid $68k, TradeFi(?) $180k (screens shown). Quant finance degree (U. of Washington), turned down a risk-management job.
- Started with $5,000 of evals; says $6,000 today "because prop firms got a little less profitable".

## The plan (slides, exact)
| Item | Number |
|---|---|
| Money in | $6,000 |
| Eval price | $100 (assumed) |
| Evals | 60 |
| Pass rate | 33 % (1 in 3) -> ~20 funded ("might get 25, might get 15") |
| Eval goal | +$3,000 before -$2,000 (50K-style account) |
| Funded traded | exactly the same as the eval (simplification; he says changing it is optimal) |
| Funded that reach +$3,000 | 33 % -> ~6.6 accounts |
| Cash per paying funded | $2,700 lifetime (after 90 % split) |
| Money out | ~$16,000-18,000 ("almost 3x"), "usually within a month" |
| Goal | $10,000 profit / month before other costs and taxes |
- Why 33 % on funded: same rules (+3k before -2k) traded the same way -> same 33 % as the eval.
- Why $2,700: firms with only winning-day rules, no buffer (he names Topstep, Lucid, Take Profit Trader(?), FundedNext). A break-even
  trader at a $3,000 balance drifts around $3,000; each win adds winning days; take half ($1,500), then half again ($750), ...
  down to ~0 = ~$3,000 x 90 % = $2,700.
- Slide "Different goals. Different math": eval = pass rate + cost per pass: $100 / (1 in 3) = $300 per funded.
  Funded = payout EV: 33 % x $2,700 = $900 expected cash per funded. $900 - $300 = **$600 per funded before other costs**.
  Pass chance and payout size pull against each other (higher payout chance -> smaller payouts).
- Scales down: $600 instead of $6,000 is "the same concept".
- Slide "A $50k account is not $50k": you can only lose the $2,000 drawdown; check target, payout cap, minimum days, consistency;
  choose stop, target and total risk across accounts BEFORE you enter.

## Account handling
- **Don't copy trade.** With $6,000 and 10 accounts copied you risk ~$1,000 at once instead of $100: wins and losses 10x, too much
  of the bankroll. (Implies one account per trade.)
- Risk per trade, stop, target: not stated here (sold in his mentorship: "statistically optimal sizing for all prop firms").
- Quit the job when trading pays the bills (~$10k/month) more than once; keep a reserve for a bad month; "simulate all of that".

## Strategy shown (NQ 1m, evening, by eye)
- 18:00 open = fair. One continuation, then reversions back to 18:00.
- No continuation when there is an unfilled gap the other way (slight bias to fill the gap: shorts back to the gap).
- 20:00 Asia open: continuation, then reversions back toward 18:00 (or toward the Asia open).
- One day: continuation, 3 reversion attempts at 18:00 (not good), then 5 trades in Asia. "You can get through a lot of accounts."
- New: entry can be on a **retracement** instead of the displacement candle, "for slightly better entries" (not defined further).
- Stop / target sizes: not stated in this video.

## Not stated
Win rate, trades a day, risk in $, stop/target points, firm-specific prices, daily stop.
