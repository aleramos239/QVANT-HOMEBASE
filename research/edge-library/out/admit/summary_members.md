## 3. Admitted members (NQ only; both families are a SECOND look for the EXAM: their old favourites already saw 2025-26)
| member (default variant) | 2021* | 2022 | 2023 | 2024 | combined | trades | win | PF | max drawdown | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| orb_NQ_tf1_pre (`or_min5_atr1p5-r2`) | -$840 | $9,878 | $7,324 | $12,437 | $28,799 | 819 | 41 % | 1.32 | $3,300 | 1.89 |
| donchian_NQ_tf30_nyam (`n10_pct0p2-r2`) | $6,093 | $27,595 | -$4,700 | $16,974 | $45,962 | 647 | 38 % | 1.18 | $10,150 | 1.06 |

**orb_NQ_tf1_pre — ADMITTED.** Reason written first: the first minutes of a session set a range; a break of either side traps the other side and carries. In practice: range of 08:25-08:30 ET, stop orders on both sides (76 % of entries fall in the 08:30 minute = US data time), stop 1.5 x one-minute ATR (about 8 points), target 2 x the stop, about one trade a day (0.99), median hold 2 minutes. Complexity 3.
* Heat map: BUILD 72 % of 96 variants positive (median $16,118); 2024 64 % (median $5,254). Surviving set: 49 variants positive in both periods and under stress.
* Lift over matched random entries: +$26,479 on BUILD, +$17,612 in 2024; beats 100 % of 200 random draws in both. BUILD t 2.32 against a bar of 2.02.
* Stress (2 ticks + 250 ms): BUILD $16,362 -> $8,462; 2024 $12,437 -> $6,572. Half the profit goes: the average trade is only $35 (7 ticks).
* Worst open loss on one trade: $1,110 per contract = $112 per micro -> at most 17 micros inside $2,000 (43 at the 99th percentile). At about $1,000 risk a trade: $118,252 combined, Sharpe 1.51.
* Cautions: 145 trades (18 %) open and close within 2 seconds and earn $18,020 of the $28,799 (63 %): data-release spikes, where simulated fills are least trustworthy. 2021* is negative; shorts earn $22,352; the pre-market session cannot be run in the Strategy Tester.

**donchian_NQ_tf30_nyam — ADMITTED, FLAGGED (weak; the checker should confirm or demote it).** Reason written first: a close beyond the recent range traps the other side (trend continuation). In practice: at the 10:00 or 10:30 close of a 30-minute bar beyond the prior 10-bar channel, enter with it; stop 0.20 % of price (about 30 points), target 2 x; 0.78 trades a day. Complexity 3.
* Heat map: BUILD 95 % of 64 variants positive (median $28,875); 2024 90 % (median $11,147). Surviving set: 43 variants.
* FLAG 1: the BUILD central variant (`n10_pts20-r2`, t 2.19 against a bar of 2.02) loses $2,113 in 2024 under stress, so the default moved to the nearest surviving variant, whose own BUILD t is 1.65: below the bar. The library's own admission check on that variant says REJECT; it is admitted only by the rule this stage wrote down before any number was opened.
* FLAG 2: random entries with the same exits in the same session also made money (+$20,204 BUILD, +$10,998 in 2024). The signal adds $8,784 and $5,976 and beats only 86 % and 76 % of random draws: most of this profit is the NQ morning itself, not the breakout.
* FLAG 3: all the profit is from shorts (+$47,084; longs -$1,122) and 2023 lost $4,700.
* Stress: BUILD $28,988 -> $15,855; 2024 $16,974 -> $9,364. Worst open loss on one trade $890 per contract = $90 per micro -> at most 22 micros inside $2,000. At about $1,000 risk a trade: $67,408 combined, Sharpe 0.96.
