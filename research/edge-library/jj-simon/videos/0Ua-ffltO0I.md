# Video notes: 0Ua-ffltO0I - JJ Simon "How Prop Firms Actually Work (And How to Beat Them)"
https://www.youtube.com/watch?v=0Ua-ffltO0I | 9:29 | uploaded 2026-09-10 | captions read in full + motion-graphic frames (2026-11-02)
Edited explainer (sections + illustrative dashboards). No chart trading. Eval and funded are two different math tests.

## Summary
Firms earn only from eval fees and keep payouts below fees with rules: 50K label, $2,000 max loss, $3,000 target, 40-50 %
consistency; on funded: buffer, consistency, winning days, take only 50 %, one payout a week / every 5 winning days. Eval goal =
P(+$3,000 before -$2,000) within consistency; funded goal = average payouts over the account's life. Backtest as a prop: 50 evals
for pass rate, 30 funded for payout per funded. Pick the firm your strategy fits best; there is "no best prop firm". Track only
eval spend vs payouts.

## Numbers / rules
- Common 50K eval: +$3,000 before -$2,000, **50 % consistency (sometimes 40 %)**.
- Funded (typical, said): make another X, reach a **buffer**, meet consistency, meet winning-day rule, withdraw **50 % of profit**;
  "most firms let you get one payout every five winning days"; usually max one withdrawal a week.
- Illustrative dashboard (graphic, not real): sim balance $54,320, available to withdraw $1,860; max daily loss $2,000; profit buffer
  required $2,600; consistency 40 % (max per day); winning days 4 of 5. Another: profit this week $5,000, withdrawable now $2,000
  ("capped at $2,000 per 14 days"), next payout window 7 days.
- Backtest the prop: 50 evals -> pass rate; 30 funded -> total payouts / 30 = value per funded (e.g. $30k / 30 = $1,000).
  "Can I pass an eval for less than $1,000? Probably: $100 evals and you can probably pass 1 in 10."
- Firm comparison metrics: cost per funded = eval price / pass rate; cost per $ of funded drawdown = funded drawdown / cost per funded;
  expected payouts per funded (most important).
- Large sim balances: good on firms that allow multiple payouts; bad on firms that move you live quickly ("never realise the EV").
- He does NOT trade one fixed R:R everywhere: "a strategy that adapts as the market does" so each trade fits some firm.
- His result: $550k evals -> $1.8M payouts in 18 months, ~3.5x return "within a month" on a round.
- Track only: money spent on evals, money received as payouts. If balances rise but the bank doesn't, find the stage (eval -> funded -> payout) where EV drops.

## Not stated
Strategy, stop/target, risk per trade, win rate, trades/day, firm names, rotation method.
