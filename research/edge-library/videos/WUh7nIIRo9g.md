# WUh7nIIRo9g — Stop Guessing Your Daily Bias. Measure It.
Channel: MatFinOg (Matteo Conti, ex-market-maker). URL: https://youtu.be/WUh7nIIRo9g
Gist: sweep "buy at hour H, sell one hour later" over all 24 hours to find hour-of-day drift, then re-check on data not used to pick the hours. His own demo fails out of sample.

## 2. TESTABLE RULES
- Measurement tool, not a strategy: S&P 500 futures (contract not named; dollar scale looks like 1 ES), 60-min bars, full 24h session, Central time. Long 1 contract at the open of the bar after hour H, exit at the open one bar later. No stop, no target. Repeat for H = 0..23.
- Hour map on ALL data (2018 to Sep 2026): long 22:00-06:00 CT mostly positive; long at 09:00 CT lost about $30k (so short bias 10:00-11:00 ET); 14:00 and 21:00 CT also negative.
- Selection rule: keep hours whose average trade is above about $5-6 (before costs), prefer clusters of neighbouring hours, short only the single worst hour.
- "Time rotation" demo, all data: long 00:00-03:00 CT, short 14:00-15:00 CT. Second pass, in sample 2018-2024: long 22:00-01:00 CT, short 09:00-10:00 CT.
- VAGUE: bar time-stamp convention (he says "bar that closes at..." and mixes it up); contract size/type; whether $5-6 is dollars per trade; costs and slippage (he shows results "before cost").
- VAGUE: which hours the $75k run used (captions say long 00-03 plus a short at 14, then talk of long/short at 9).
- Stop/target grid ($0-10,000, step 500, 441 combos) was "for illustration only"; best profit factor at stop 4,500 / target 2,000.

## 3. CLAIMED RESULTS
- All-data rotation run: net $75,000; 49.22% winners; profit factor unclear (caption "of one"); average trade "1672" (likely $16.72, about 4,400 trades by our arithmetic; unclear). Before costs.
- Best stop/target profit factor "108" (likely 1.08). Adding stop 1,000 / target 5,000 lowered profit.
- Out of sample (2025 to now): "looked good in sample, weak out of sample". Equity curves shown on screen; no numbers spoken. Evidence is his own failed test, not a working edge.

## 4. PROP-FIRM TACTICS
None.

## 5. TESTING-METHOD IDEAS
- Sweep all hours with one input, one trade per day per hour; rank by average trade; look for clusters.
- Pick hours on the first period only (he used 2018-2024), freeze, then run the unseen period. Real = both curves rise with similar average trade and % winners.
- Same sweep works for day of week, month, and other markets. Optimising stop/target on the same data is overfitting.

## 6. LOOK AT SCREEN
- [04:05]-[05:07] 24-row hour table: only midnight ($13,650), 1am (~$21k), 9am (-$30k) are spoken; full table missing.
- [08:13] equity curve and long-only/short-only split of the rotation run: no per-side numbers spoken.
- [11:18] in-sample hour table (2018-2024): which hours cleared the $6 bar is only partly spoken.
- [13:18] out-of-sample curve: size of the failure is not stated.

## 7. RED FLAGS
No course pitch in this transcript. Admits step one is look-ahead. $5-6 average trade is far under ES slippage (one tick = $12.50); no cost model shown. Credential talk (market maker, 30M euro).

## 8. VERDICT
Skip as a new edge (we already did time-of-day drift; his own out-of-sample fails). Optional cheap check: does his worst-long hour (10:00-11:00 ET) also show negative drift in our 2021-2024 table.
