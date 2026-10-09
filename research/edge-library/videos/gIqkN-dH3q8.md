## 1. SOURCE
Title: Independent Quant Trader Robert Carver Reveals His Portfolio | Channel: Odds on Open | 2 min 40 s | uploaded 2025-08-05
URL: https://youtu.be/gIqkN-dH3q8 | Guest: Robert Carver
Read: the full auto-captions (2026-10-09). The clip is one answer: a list of the rule names he runs. No settings, no weights, no results.
Gist: He names his suite of trading rules in alphabetical order. All are slow (days to years), run across many markets at once, and held overnight.
## 2. ACCOUNT GAME
- Nothing. Not a prop-firm video.
## 3. TESTABLE TRADING RULES
His rules, and whether the pipeline can run them (NQ / ES / GC, same day, 1- or 5-minute bars):
- Acceleration ("a trend on a trend": momentum growing = long, a fall that slows = long). No entry rule. Nearest: the `macd with` indicator (histogram with the trade and not weakening).
- Asset trend (trend of the whole asset class, long or short every market in it). Does not fit: many markets, multi-day.
- Breakout (where price sits in its range; near an extreme = go with it). Nearest: `donchian`. Already read: 8 channel cards on 2026-10-08, all stopped at stage 1.
- Carry (slope of the futures curve). Does not fit: needs the curve, multi-day.
- Momentum (moving-average crossover on price). Nearest: `ema_ribbon` (EMA 8 / 21 / slow line up). Added 2026-10-09: nq_ema_stack_mid_long, nq_ema_stack_mid_short.
- Slow mean reversion (short the market that beat its peer for years). Does not fit: years, pairs.
- Normalized momentum (momentum on a risk-adjusted price series). No block.
- Relative carry, relative momentum (long / short inside an asset class). Do not fit: many markets.
- Skew (buy what fell sharply; a paid risk premium; absolute and relative). Nearest: `rsi2` long, already read (nq_rsi2_pm_long, stopped at stage 1).
- He says fast mean reversion does not survive trading costs for him; only the slow kind does.
## 4. CLAIMED RESULTS
- None given.
## 5. THINGS A FIRM WOULD BAN
- Everything here holds overnight for days or longer: not usable on a day-trading prop account as he runs it.
## 6. TESTING-METHOD IDEAS
- Many rules on many markets, each small, rather than one tuned strategy. Rules come in pairs (plain and relative).
- Risk-adjust the price series before measuring momentum.
## 7. LOOK AT SCREEN
- Nothing: he only talks.
## 8. PIPELINE VERDICT (2026-10-09, build days)
- nq_ema_stack_mid_long: stopped at stage 3. 5-minute map passed stage 1 (64.58 % of boxes profitable, 27 at the floor); the picked box slow89_pts30-r0 ($106 a trade, 347 trades) fails P3.7 (-$28,945 without its best 5 % of trades), P3.8 (25 of 46 months won), P3.9 (best month 16.98 %), P3.10 (10 losing days in a row). The 1-minute map failed (31.94 %).
- nq_ema_stack_mid_short: stopped at stage 1. 27.78 % (1-minute) and 32.64 % (5-minute) of boxes profitable.
## 9. CAVEAT
- His own book (Advanced Futures Trading Strategies) reports no intraday trend rule that pays on hourly data. The two cards are a bent version of his momentum rule, not his rule.
