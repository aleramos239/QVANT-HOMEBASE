# Video notes: yW6c0K8uGvw - four paper-based strategy ideas
Title: "4 Institutional Scalping Strategies Market Makers Keep SECRET (Automate Prop Firm Trading)" | Channel: Chart Fanatics | https://youtu.be/yW6c0K8uGvw
Guest: Matteo Conte (ex-bank trader; says 400+ systems live at the bank, 25-100 now). Captions are auto: "VWOP/VWOF" = VWAP, "ENQ" = NQ.
Gist: how to turn research papers into simple rules (find the finding, then the reason, then entry/exit/size). Four ideas, none backtested on screen, none a scalp, nothing about market makers.
## 2. THE FOUR STRATEGIES
### S1 Opening-range breakout, long only (33:41-49:26). Source: 2018 "Market intraday momentum" paper
Why: overnight news and positioning pile up; the first 30 min (09:30-10:00 ET) shows the buy/sell imbalance, the market cannot absorb it at once, so it carries through the day. The paper itself says prior-close-to-10:00 return predicts the LAST 30 min; he did not trade that, he turned it into a breakout.
Market/time: US index (not named for S1). Range 09:30-10:00 ET. Bar size for "closes above": VAGUE. Entry cut-off time, one trade per day or more: VAGUE.
Entry: long when price closes above the range high. Short (close below range low) is optional; he prefers long-only because dips get bought (his experience).
Stop: range low. Target: 1:1 or 1:2 of risk (unclear if his pick or the paper's; caption unclear). Time exit 15:30 ET if neither hit. No other filters.
Sizing: 1 contract while developing; live = same dollar risk each trade, fewer contracts when the range is wide (volatility targeting).
Automation: encode in MultiCharts or Pine, one rule at a time (entry, then exit, then sizing).
### S2 VWAP stop-and-flip (49:26-58:59). Source: industry paper "VWAP, the holy grail of day trading systems"
Why: many institutions send VWAP-tracking execution algos that buy more where volume is; around a VWAP cross they add one-way flow and amplify the move. (Speculation, no evidence shown.)
Market/time: paper used QQQ on 1-minute bars; he says try NQ, ES, crude, stocks. VWAP anchored at the 09:30 open (strongly preferred; previous-day VWAP is an option). Trading window length: VAGUE ("find it in the backtest").
Entry: long when a 1-min bar closes above VWAP, short when it closes below. Exit: when price crosses back to VWAP. Reverse at the cross or go flat and wait: VAGUE.
Stop/target/filters: none stated beyond the VWAP cross. Sizing: 1 contract first, volatility-based later.
### S3 Post-earnings drift, stocks (59:03-79:08). Source: three papers (1968, 1989, 2006)
Why: prices do not absorb earnings news at once: thin analyst coverage in small/mid caps, and funds with liquidity limits spread buying over days or weeks. Mega-caps show no edge (2021 paper, per him).
Entry: price reaction up AND EPS above analyst estimate, buy next day's open. Exit: after 60 trading days (starting point). Stop: only an example, 5% below that day's open or pre-earnings close. Size: 1-2% of portfolio per stock, or scaled by surprise size. Universe of 20-30 small/mid caps; short side weaker (firms pre-announce bad news). Surprise/reaction thresholds: VAGUE.
### S4 Overnight hold (79:08-88:00). Source: 2008 "night and day" paper
Why: ~90% of equity-index gains arrive overnight. Two stories: overnight risk premium (he admits 90% is too big for that alone), or thin overnight liquidity causes overreaction that reverts in the day session (his preferred).
Entry: buy at 16:00 ET. Exit: 09:30 ET next day. No stop, target or filter. Sizing: bigger when volatility is low, smaller when high. Side idea "ORB during the overnight session": VAGUE, no rule given.
## 3. CLAIMED RESULTS
S1: no numbers. Only asserted: worked well over the past six years, long-only held up in 2022. No evidence shown.
S2: "something like 671% over 5 years" from the paper on QQQ; he says ignore headlines. No win rate, PF, drawdown, costs or trades per day. Not shown in transcript.
S3: none; only "60 years of research", drift lasts about 60 days. S4: "90% of returns overnight", same said for NQ 2015 to June 2026; no table in the audio.
Career claims (30M euro for the bank, 80% from "extremely simple" strategies, 15bn volume) cannot be checked; intro says dollars, later says euro per year.
## 4. AUTOMATION + PROP-FIRM TACTICS
Platform: his favourite is MultiCharts (EasyLanguage); Pine also fine; use an LLM to write the code, built step by step. No account counts, risk per trade, firm names or payout talk from the guest.
Only prop content is sponsor ads (Apex, NinjaTrader): Apex up to 20 accounts, 20K-150K sizes, no MAE or 5:1 rule, end-of-day or intraday trailing drawdown, "one day to pass". Ad claims; bot rules not mentioned.
Portfolio idea: run 3-4 uncorrelated systems (trend plus mean reversion), review monthly. Use Monte Carlo drawdown odds as a live alarm: pause if drawdown is a roughly 5%-odds event.
Sizing examples ($10,000 risk per trade; "$30,000" risk on 1 contract on a wide day) are not prop-sized and the second looks wrong or exaggerated.
## 5. DATA NEEDED
S1 price bars only (1-5 min) plus range/ATR for sizing. S2 1-min bars with volume (RTH VWAP); ticks are better. S3 stock prices, earnings dates, actual vs consensus EPS: we likely lack it. S4 price bars incl. the overnight session. None needs the order book or buy/sell volume.
## 6. TESTING-METHOD IDEAS
Split data about 80/20 in-sample/out-of-sample; tune only in-sample, freeze rules, run once on the unseen part. Start with the plainest version (time exit only), add a stop in-sample, then check out-of-sample.
Monte Carlo: reshuffle trade order (same end point, shows drawdown/streak range) and resample with replacement, 10-20k runs, to read P(drawdown > X). Run the same code on other markets as a sanity check. Add sizing last.
Weak spots: no cost model, no multiple-testing control, no walk-forward; "keep digging and you find gold" invites data mining. Our shuffled-null test is stricter.
## 7. LOOK AT SCREEN (inferred from his "here / up here" wording)
[38:57]-[40:05] ORB drawing: where stop and target sit vs entry; is 1R measured from entry or from the range edge; which bar closes.
[51:40]-[53:48] VWAP drawing: does the cross-back flip the position or just exit; the "losing trade" example.
[53:48] paper's result page (671%): costs, leverage, drawdown, trades per day are probably on screen. Other screens (PEAD diagram, overnight sketch) add little.
## 8. RED FLAGS
Title is clickbait: no scalping, no market-maker secrets, almost no prop content (ads). About half the runtime is pipeline talk and sponsor reads.
The ORB is his own translation: the paper tests first-30-min predicting the last 30 min, not a range breakout. "30 min is optimal" and "long-only beats beta" are stated, not shown.
VWAP reason is weak: VWAP algos follow a volume schedule, not a price cross. 671% is a paper headline with unknown costs; 1-min stop-and-flip trades often.
S3 holds 60 days and uses stocks; S4 holds past 16:00 and is mostly long-run equity drift (beta). Both clash with a 10-day eval and flat-by-close rules.
## 9. VERDICT
S1: worth a quick test as a variant in our ORB family: long-only vs both sides, close above 09:30-10:00 high, stop range low, 1R vs 2R, out 15:30, per year then combined vs shuffled null. Also test the paper's own finding: sign of (prior close to 10:00) vs 15:30-16:00 direction.
S2: maybe: close vs 09:30-anchored VWAP stop-and-flip on NQ 1-min. Count flips and net cost per trade first; likely overlaps our VWAP-EMA crossover; drop if gross edge per trade is below costs.
S3: skip (stocks, 60-day hold, needs EPS data). S4: skip (overnight hold, beta, overlaps time-of-day drift we tested; no rule for the overnight ORB).
