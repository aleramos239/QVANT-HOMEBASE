# LQvv5xgy_ik - "Exposing my Risk Management Protocol"
Channel: Fabervaale ENG | https://youtu.be/LQvv5xgy_ik | 34 min | written from auto-captions (some words garbled)
Gist: a talk on how the goal changes the risk plan: hedge fund, prop account, two trading contests, personal account. No entry or exit rule anywhere. The only part that touches our work is the prop section [8:08-13:48].
## 2. WHAT HE SAYS, BY ACCOUNT TYPE
### Hedge fund [0:30-8:08]
Aim is return per unit of risk, not raw return; many unrelated strategies; each model has a size limit (a scalp cannot hold billions). Medallion's early years used as the example. No rules.
### Prop account [8:08-13:48]
- An eval is a game against the firm's rules, not the market. Aim: low spread of outcomes, not high profit.
- Shape he recommends for the eval: win rate above 60-70%, moderate risk per trade, reward:risk about 1:1, down to 0.75:1, at most 1.5:1.
- He says "sniper" trades (10:1, one a week, low win rate) fail evals: longer losing runs, so the drawdown line is hit before the edge shows.
- After the eval (funded): push for the payout, then withdraw as much and as early as the rules allow. A prop firm is a bigger counterparty risk than a broker (his story: a $50K+ payout from a Canadian CFD prop got held for review).
- Consistency rules cap how hard the funded phase can be pushed.
### CME Group Equity Cup [13:48-17:24]
One account, short time, no testing. Kept drawdown tiny at first to free margin, then sized up. Claims 50-60 trades, +54.6%, max drawdown 0.42%, top ~0.6%. He says himself the result came with a lucky start and that the sizing would be unacceptable in a fund.
### World Trading Cup, 3 months [17:24-26:36]
Ranking is by final percent, so the plan is: month 1 run three small accounts (trend, mean-reversion, volatility breakout) with real costs to see which the market is paying; month 2 trade only the winner at moderate risk; last weeks maximum size, 300-400 trades. Most rivals go big too early and vanish. Claims on screen: monthly figures 68% / 89.5% / 158% cumulative with a 22% max drawdown; ~650 trades in the quarter. Automated models from his quant made money but too little after slippage to rank.
### Personal account [26:36-33:40]
0.25-0.5% risk per trade (caption says "1.25%", probably 0.25%); several brokers because of FTX-type failures; several models (discretionary, one algo = his first-30-minute breakout "IVB", options, long-term stock and bitcoin plans).
## 3. CLAIMED RESULTS
Contest figures above (stated, tables on screen). For the prop advice: two simulated outcome fans over 3 months [10:11] and a "path" summary slide [11:14]. No account statements, no pass-rate number, no trade list.
## 4. TESTABLE CONTENT
No strategy. Two checkable claims:
- C1 "High win rate with a small target passes evals more often than low win rate with a big target." Checkable on any idea we already built: read the eval odds of the same entry across the target columns of the standard table (0.5 / 0.75 / 1 x stop against 2 / 3 x stop / none). A study, not a strategy, and it must not be used to pick one cell (we judge the average of all cells).
- C2 "Run trend / mean-reversion / breakout side by side for a month and trade only the one that is winning." A switch between strategies based on last month's result. Our tools test one idea at a time; this is a portfolio rule.
## 5. FITS THE TESTER
NO for both. C1 needs no new entry rule, only the prop simulator read by target column; our drawdown counts open losses, which the high-win-rate shape (target smaller than stop) makes worse, so his advice may not carry to LucidPro. C2 needs a portfolio-level switch that does not exist.
## 6. REPEATS FROM THE 2026-10-03 BATCH
- "Trade the firm's rules, pay yourself early, firms can refuse payouts" = JJ Simon / Mathe Wieme account-game notes (aCOgfvL6lK8, 5yBAXjmaMl0).
- "High win rate, target smaller than stop for evals" = the shape of Matteo Conti's VWAP pullback (wm4A6qo0g3I: stop 80, target 40-50). JJ Simon said the opposite for evals (risk 1 to make 1.5-2).
- Lil Fish (XLMG6-SATRk) also said low-win-rate, big-winner variants fail consistency and daily-loss rules.
## 7. LOOK AT SCREEN
- [8:39]-[11:44] the prop "risk geometry" slides: the two outcome fans and their inputs (win rate, reward:risk, risk per trade, number of trades).
- [11:44] the phase chart (eval = low variance, funded = push for payout).
- [24:03]-[25:04] contest account reconstruction table.
## 8. RED FLAGS
All advice, no numbers for the prop part. Contest results are a high-variance format and he says so. A 3-month, one-seed simulation proves nothing either way. Mentions his platform, his research company and a planned fund.
## 9. VERDICT
SKIP for strategies. Worth one cheap read later: on a strategy that passes the lock, compare eval odds by target column on LucidPro 50K with open losses counted, to see whether "small target" or "big target" really passes more often under our rules.
