# wm4A6qo0g3I — Ex-Market Maker Shows the Exact VWAP Setup That Gets Traders Funded - Matteo Conti
Channel: IQCapital (prop-firm brand). URL: https://youtu.be/wm4A6qo0g3I
Gist: "Drift VWAP pullback" on NQ: when the day's VWAP shows a trend, enter the first pullback candle toward VWAP. High win rate, small reward vs risk, pitched as a way to pass evals.

## 2. TESTABLE RULES (best specified of the four)
- NQ. Trend state read on 15-min bars; entry at the next bar open by market order. VWAP anchored at the 09:30 ET cash open.
- LONG trend = all true: (1) close above VWAP; (2) VWAP higher than 15 min ago; (3) price up at least 0.1% over the last hour (4 bars of 15 min). SHORT = mirror (below VWAP, VWAP falling, price down at least 0.1%).
- No trades 09:30-10:30 ET; no new trades after 15:30 ET; flat everything at 15:55 ET.
- Trigger: long = first red candle (pullback) once trend is true; short = first green candle. Distance to VWAP does not matter.
- Exits: long stop 80 pts / target 40 pts; short stop 80 pts / target 50 pts. One position at a time, max 4 trades a day, stop for the day after 2 losses.
- Said to be tuned in sample: the 0.1% threshold and the 4-trade cap (the cap chosen to maximise eval pass chance).
- VAGUE: timeframe of the trigger candle (5m or 15m; he loads both, once says "50-minute", likely caption error); price used for VWAP and whether built from 15m or 5m bars; "first" candle after what (trend start or last exit); "2 losses" vs "2 losses in a row" (he says both); costs/slippage; bar order when stop and target sit in one bar; is the 1h change vs the close 4 bars ago.

## 3. CLAIMED RESULTS
- Intro teaser: "over 300%" across "more than 4,000 trades" in testing; the base for the percent is not given.
- Win rate 64% (intro) and about 65% (later); average win about $866, average loss about $1,300 (captions, one NQ). Our arithmetic: about +$85 to +$110 per trade, break-even near 60% wins. He admits average trade is small and it is "unlikely" to make money on a personal account.
- Developed on 2020/2021-2024; "out of sample" 2024 to 2 Aug 2026. Only an equity curve was shown; no separate out-of-sample numbers spoken.
- Monte Carlo of the trade list (20,000 runs, Python): one eval 49.8% pass, 3.4 days to pass on average; pass at least one in 2 / 3 / 4 attempts = 74.8% / 87.3% / 93.6%. We checked these equal 1-(1-0.498)^n, so attempts are treated as independent. Account size, profit target, drawdown rule and method are not spoken (screen only).
- "Used 6 months to pass many challenges" and a friend who blew 47 evals then passed: anecdotes, no proof.

## 4. PROP-FIRM TACTICS
- Choose a high-win, low-payoff strategy to maximise pass chance; accepts no value on own money. Size 1 NQ or 10 MNQ. 80-pt stop = $1,600 per NQ; two losses = $3,200 a day (our arithmetic; check vs the account drawdown).
- Buy several evals in a row (assumes $50 each, $200 for four). Funded/payout stage deferred to a "next interview". 49.8% single-eval pass is under our 60% bar.

## 5. TESTING-METHOD IDEAS
Code every rule and run all trades over the full history. Research on the first half only, freeze inputs, run unseen data; both curves rising. Few rules, few tuned inputs. Bootstrap the trade list for eval odds; use Monte Carlo drawdown percentiles (example: 5% chance of >$10k loss over 10 trades) as a live stop-the-strategy yardstick. Do not override the system live.

## 6. LOOK AT SCREEN
- [08:06] VWAP "from the 15-min chart shown on the 5-min": how and how often it updates.
- [14:18]-[15:20] green/red crosses marking trend true: on which bar close.
- [24:26]-[25:26] example trades: whether the trigger candle is 5m or 15m, and where entry sits.
- [26:27]-[28:28] equity curve since 2021 and the 4-trade day: no net, drawdown, or per-period numbers spoken.
- [31:30]-[33:33] Python sim screen: prop rules, size, target, drawdown type, sim method missing.

## 7. RED FLAGS
Brand sells challenges (ad at [20:23], $9 50K and $1 offers); "golden ticket" hype; 93.6% is a sales number built on independent attempts, ignoring fees, resets, and shared market regime; parameters tuned on the target metric; no costs mentioned; VWAP-algo story (90-95% of orders) is unsourced; host cheerleads.

## 8. VERDICT
Worth testing: these exact rules on our NQ 2021-2024 data only (per-year then combined), tick fills, 5m and 15m trigger variants, with costs. Expect a thin edge (about $100 a trade on his numbers) and an 80-pt stop that may clash with open-loss drawdown.
