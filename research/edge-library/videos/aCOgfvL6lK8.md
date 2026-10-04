## 1. SOURCE
Title: The Genius Who Outsmarted The Prop Firm Game, And Made $1.5M In Payouts. | Channel: Titans Of Tomorrow | 73 min
URL: https://youtu.be/aCOgfvL6lK8 | Guest: JJ Simon (quant-finance graduate, ex-poker player; trades Nasdaq futures only)
Gist: Prop firms as a volume game: buy many cheap evals, fixed-dollar stop and target on every account, fade the open/news move back toward the 9:29 price, aim for about 3x payouts on eval spend. He calls the edge "very small"; the money comes from the account maths and scale.
## 2. ACCOUNT GAME
- Firms that paid most: Topstep, Lucid, "TradiFi" (caption spelling; likely Tradeify). New firm = buy ONE account first, scale only after it pays.
- Today: about 10 firms, all 150K accounts, wants 5 funded per firm live at once (VAGUE: the "5" is not explained). Talks of running 30-40 accounts at once.
- Start: $5K bankroll, ~50 evals of 50K size at ~$100 each on two firms, became ~$17K in about a month (3.3-3.4x spend; his aim 3-4x). Next step was $10K over four firms (double firms, double spend), not bigger accounts. Treats accounts as a portfolio.
- His model: passes ~25-33% of evals, then ~25-33% of passes reach a payout. 33% x 33% = 1 eval in 9 pays out; 25% x 25% = 1 in 16. Example: $900 on 9 evals at $100 gives one $2,000 payout (2x) plus $2,000 left in the funded account.
- Payout size: aims for $5,000 each time: grow the funded account to a $10,000 balance, withdraw $5,000 (half), regrow, repeat. VAGUE: "balance" vs profit above start, and days per cycle. Biggest payout $45K; all others $5K or less.
- Scale target: spend about one third of payouts. For $100K/month profit: ~$50K eval spend, ~$150K payouts = ~30 payouts of $5K (about one a day). Return on spend: 2.7x weak, 3x normal, 4-6x good.
- Risk per trade: fixed dollars per account, set by that account's rules. Examples: risk $1,000 to make $2,000; risk $1,000 to make $1,500; risk $500 to make $2,000. Eval trades mostly 1:1.5 (some 1:2, 1:1); funded 1:1, 1:1.5, 1:4 and others. Eval logic: $3,000 target vs $2,000 max loss is 1:1.5, so he trades 1:1.5. NOT STATED: contracts, stop distance in points (only "a 15-point target on some accounts"), share of drawdown risked.
- Speed: claims he passes "like 10 evals in a day" by taking many small trades, ~20 trades a day (intro says 30+). VAGUE: wins needed per eval, how many evals are open at once.
- Copy trading: says he avoids it; each account gets its own entry. But he "layers in": when a funded account is in profit he adds evals in the same direction one after another, so it is staggered same-direction copying. Argues 10 accounts at $100 risk/$250 target pass far slower than one $1,000/$2,500 trade per account.
- Eval vs funded: different strategy and RR for each. Eval = maximise chance of hitting target before max loss. Funded = maximise chance of payout x payout size. Funded strategy details not given.
- After a pass: NOT STATED. After a payout: account stays open with ~$5K, regrow to $10K, withdraw again. Lost accounts are replaced by a new eval to keep ~30 running.
- Ruin maths: chance of zero payouts from N evals = (1-p)^N. 0.9^50 is under 1% (his 50-eval start). Wants ruin 5% or less, now 0.5%. Kelly (quarter or half when small) decides how many evals to afford. Pass-rate lookback: all evals; 20 is rough, 50+ is solid.
- Failures/denials: ~$300K of payouts denied over ~18 months; says live-account rules keep tightening; Topstep banned silver after it was exploited. Tracking: one Excel sheet for 16 months. Hedging across accounts: NOT DISCUSSED.
## 3. TESTABLE TRADING RULES (NQ, 1-minute, he calls them mechanical)
- Data: 1-min structure only, at most a 6-hour look-back for bias; a 30-60 minute direction bias. No chart patterns, no level 2, no order flow (tried on live earlier: "marginal").
- Fair price: the 09:29 ET price, or the latest consolidation after a breakout. Idea: news and open volume push price off fair value, then it retraces.
- Day plan (ET): 08:30 news: 1 trade continuing the news candle, then 3-4 fades back toward the pre-news price. 09:30: 1 continuation trade at the open (time is the trigger); wait for volume to fade and price to consolidate; then 3-4 reversion trades when price breaks structure back toward the open price (before 11:00). 11:00: one long trade held to ~14:00. 14:00, 18:00, 20:00 (Asia): repeat 1 continuation + 3-4 reversions.
- Reversion entry: a 1-min bar closes beyond the structure level that broke back toward the open. VAGUE: "consolidation", "structure", wait time, how continuation direction is chosen beyond "same as the first candle".
- Exit: fixed-dollar stop and target (RR 1:1 to 1:2), no structure-based stops, no partials, no runners. Break-even only ~5% of the time (before a new session open or news). No time stop. No win rate or per-rule results given.
## 4. CLAIMED RESULTS
- Over $1.5M payouts in under 18 months; ~$100K/month profit now (stuck near $75K for months before); $5K to $17K in a month early; biggest payout $45K; ~$300K denied; wins ~98% of days (pooled across many accounts; per-account pass is only ~30%).
- Evidence: none shown in the transcript (no statements, ledger or equity curve). Claims only; host did not ask for proof.
## 5. THINGS A FIRM WOULD BAN
- Nothing described is plainly against usual rules: own accounts, same-direction trades, no opposite positions, no account sharing, no bot mentioned. (I did not check any firm's current rulebook.)
- Check per firm: (a) 08:30 news-candle trades on funded accounts; (b) staggered same-direction entries on many accounts = copy trading in effect, which some firms limit or flag; (c) 18:00/20:00 trades and the 11:00-14:00 hold: overnight/flat-time rules matter (our flat-by-4pm rule would cut his 18:00 and 20:00 sessions); (d) 20-30 near-identical trades a day across accounts can read as abuse; he reports $300K denied.
## 6. TESTING-METHOD IDEAS
- Backtest as a prop challenge, not a live equity curve: count max-drawdown hits vs target hits per rule set; pick the firm whose rules suit the strategy's win rate and RR.
- Eval score = P(target before max loss); funded score = P(payout) x payout size. Chain: eval price / pass rate = cost to funded; x P(payout) x payout = return (example: $333 cost, $1,000 expected payout = 3x).
- Match RR to the eval's target:drawdown ratio (3,000:2,000 = 1:1.5). Fixed stop and target, no discretion, so every trade tests the same.
- Host idea (not JJ): "revolving door": 10 accounts, each traded one week apart on a 4-week cycle, switched off once paid; host's AI model showed a payout even from a losing curve. Unverified.
## 7. LOOK AT SCREEN
- [0:00]-[1:00] intro: check whether payout screenshots are shown. [53:23] host puts a loss-streak odds table on screen (not about the edge). No strategy chart is shown or explained in the audio.
## 8. RED FLAGS
- Payout claims unverified; promoter context: host sells an "Inner Circle" and reads prop-firm ads (Olap Prime, Alpha Capital, Alpha Futures).
- Edge is thin by his own words; no win rate, expectancy or backtest numbers. "98% winning days" is pooled across accounts and hides ~70% eval failure.
- His 25-33% pass rate is about what zero edge gives when target is ~2x drawdown (D/(T+D) = 33%; our figure for 3,000/2,000 is 40%). So it does not show edge. (our inference)
- "Prop firms are basically zero risk" is wrong: eval fees, ~70% fail, $300K denied, bans. His 3x needs ~$100 evals and firms that keep paying.
- Says he avoids copy trading yet stacks same-direction entries; outcomes are correlated, so "10 evals passed in a day" can be one lucky move.
- Last 10 minutes of captions have garbled numbers (e.g. "$450K allocation", "215 eval"); do not rely on them.
## 9. VERDICT
COPY the account maths (cost to funded, P(payout) x size, (1-p)^N ruin, ~3x spend target, fixed-dollar stop/target, no partials/BE/runners in eval). MAYBE test one rule on NQ ticks: fade the 09:30 move back to the 09:29 price after a 1-min structure break, before 11:00, fixed $ stop and target (needs exact definitions; check against our existing 09:30 tests). SKIP the 20-30 trades/day multi-account juggling and the 18:00/20:00 sessions.
