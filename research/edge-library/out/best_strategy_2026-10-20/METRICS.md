# Metrics of the three strategies, and why each was approved (2026-10-20)

All tables: NQ, 1 contract, after costs ($4 a round turn + 1 tick on every market or stop fill), engine tick replay, build days
2021-09-22 .. 2025-06-30 unless a line says "walk-forward". Made with the house metrics report (`strategy-metrics` skill,
`homebase/backtest/stats`) on each strategy's stored trades. Sharpe here is the house report's (daily P&L, trading days);
the lane's own Sharpe in the "why approved" lines uses all 948 session days, so it is a little lower.

## The out-of-sample for #2: the 3:1 block walk-forward (run 2026-10-20 15:31 ET, owner's word) -- FAILED

Pick on 3 months, trade the 4th, next block; 15 test months 2022-01 .. 2026-09; each month trades the walk's pick (the middle of the
target cells 0.75R / 1R / 1.25R that held the pick lines on the 3 months before; none held = the month stands aside).

| line | result | need | |
|---|---|---|---|
| P6.1 net on the test months | +$3,855 on 130 trades ($30 a trade) | above $0 | PASS |
| P6.2 beats random tables | 75.5 % | above 95 % | FAIL |
| P6.3 win rate vs realized reward:risk | 55.4 % at 0.84 R:R, breakeven 54.4 % | 57.4 % (+3) | FAIL |
| P6.4 trades | 130 | 200 | FAIL |

- 5 of the 15 test months stood aside, and the pick jumped between targets: 0.75R x4, 1R x4, 1.25R x2.
- Build-day test months: -$155 on 115 trades. Unseen test months (2025-07 on): +$4,010 on 15 trades (only 2026-05 traded;
  2025-09, 2026-01 and 2026-09 stood aside).
- **Verdict under the house law: NOT PROVEN.**

Each target cell alone on the same 15 test months (`taught wf-each`, no new days read):

| cell | traded every test month | of which unseen months (2025-07 on) |
|---|---|---|
| 0.75R | 188 trades, $64 a trade, PF 1.10 | 47 trades, +$812 |
| **1R (the sheet's own cell)** | **188 trades, $123 a trade, PF 1.17, DD $12.2k** | **47 trades, +$3,462 ($74 a trade)** |
| 1.25R | 188 trades, $34 a trade, PF 1.04 | 47 trades, -$4,703 |

So: the rule's own 1:1 cell held up on the test months; the walk's monthly pick and its stand-asides (a 0.6-a-day rule gives only
~40 trades in 3 months, too few for its lines) cut it to $30. That reading is not the house verdict; it says the failure is mostly
the walk's mechanics at this trade count, plus a weak 1.25R cell -- and 47 unseen trades are far too few to prove anything.

## The three side by side (build days)

| | 1 Open-side FVG | 2 10:00 displacement | 3 13:30 first bar |
|---|---|---|---|
| trades a day | 1.34 | 0.64 | 0.63 |
| avg trade | $108 | $171 | $93 |
| PF | 1.30 | 1.25 | 1.38 |
| win rate | 55.7 % | 55.6 % | 56.7 % |
| Sharpe (lane / house) | 2.07 / 2.19 | 1.25 / 1.57 | 1.64 / 2.06 |
| worst DD, open losses | $15.1k | $17.6k | $7.1k |
| net / worst DD | 9.1 | 5.9 | 7.8 |
| lane lines held | 10 of 10 | 10 of 10 | 10 of 10 |
| beats random (both sides) | 100 % | 100 % | 100 % |
| out-of-sample | not run: family's months already read | **3:1 walk-forward FAILED** | not run: parent's months already read |

## 1. Open-side FVG (`cl_fvg_oside_15_mid_r1_t2_gap0p1`)

**Per year, then combined** (1 NQ, after costs, build days):

| year | trades | net | win rate | avg trade | PF | payoff (avg win / avg loss) | Sharpe | max DD | longest losing run (trades / $) |
|---|---|---|---|---|---|---|---|---|---|
| 2021 (Sep-Dec) | 92 | $18,722 | 59.8 % | $204 | 1.78 | 1.20 | 4.81 | -$2,511 | 3 / -$2,313 |
| 2022 | 350 | $60,460 | 60.0 % | $173 | 1.43 | 0.96 | 3.11 | -$8,317 | 6 / -$6,352 |
| 2023 | 338 | -$1,092 | 50.6 % | -$3 | 0.99 | 0.97 | -0.08 | -$14,046 | 7 / -$5,278 |
| 2024 | 341 | $25,236 | 53.7 % | $74 | 1.21 | 1.04 | 1.51 | -$14,743 | 10 / -$8,345 |
| 2025 (Jan-Jun) | 147 | $33,952 | 59.2 % | $231 | 1.59 | 1.10 | 3.91 | -$6,485 | 5 / -$3,858 |
| **all** | 1268 | $137,278 | 55.7 % | $108 | 1.30 | 1.04 | 2.19 | -$14,743 | 10 / -$8,345 |

**Long / short / combined:**

| side | trades | net | win rate | avg trade | PF | avg win | avg loss | Sharpe | max DD |
|---|---|---|---|---|---|---|---|---|---|
| long | 671 | $66,911 | 56.2 % | $100 | 1.31 | $752 | -$737 | 2.03 | -$12,485 |
| short | 597 | $70,367 | 55.1 % | $118 | 1.30 | $932 | -$882 | 2.00 | -$15,923 |
| combined | 1268 | $137,278 | 55.7 % | $108 | 1.30 | $836 | -$806 | 2.19 | -$14,743 |

**More:** largest win $3,521 · largest loss -$3,744 · best winning run $10,627 · worst losing run -$8,345 (10 trades) · worst drawdown with open losses counted $15,127 · months won 78 % · trades a day 1.34

**Bootstrap** (10,000 resamples of the trades): average trade $108, 95 % range $56 to $161, chance the edge is $0 or less: 0.0 %. **Monthly win rate:** steady, lowest month 38.7 %, highest 73.5 %.

**Cost ladder** (1x = $9 a trade already in the net; the audit measured $6.4-8.5):

| friction | avg trade | net | PF | Sharpe |
|---|---|---|---|---|
| 0.5x | $113 | $142,984 | 1.32 | 2.28 |
| 1.0x | $108 | $137,278 | 1.30 | 2.19 |
| 2.0x | $99 | $125,866 | 1.27 | 2.01 |
| 4.0x | $81 | $103,042 | 1.22 | 1.64 |

**Why it was approved** (the lane's lines on the 1:1 cell, the pipeline's own functions):

- P3.2 PASS average trade $108 (need above $0)
- P3.3 PASS 1,268 trades (need 200)
- 3.3 PASS default variant: profit factor 1.30 over 1,268 trades (need 1.2 or more)
- 3.4 PASS default variant: net $137,278 / worst drawdown $15,127 = 9.08, open losses counted (need 3 or more)
- 3.5 PASS default variant: Sharpe 2.07 on 948 session days (need 1 or more)
- 3.6 PASS default variant: worst drawdown $1,513 at 1 micro, open losses counted (need under $2,000, the limit of LucidPro 50K)
- 3.7 PASS default variant: makes money in 100 % of 1,000 reshuffled runs (need 80 % or more)
- 3.8 PASS default variant: $102,179 without its best 1 % of days (10 of 948 session days; they made $35,099 of $137,278; need above $0)
- P4.1 PASS the box's average trade is above $0 in 100 % of 1,000 reshuffled runs (need 75 % or more)
- P4.2 PASS beats 100 % of the random-entry runs of the same box on try 1 (need above 95 % = 100 - 5 / 1 try)

## 2. 10:00 displacement (`cl_am_disp15_vwap_10to11`)

**Per year, then combined** (1 NQ, after costs, build days):

| year | trades | net | win rate | avg trade | PF | payoff (avg win / avg loss) | Sharpe | max DD | longest losing run (trades / $) |
|---|---|---|---|---|---|---|---|---|---|
| 2021 (Sep-Dec) | 48 | $11,178 | 58.3 % | $233 | 1.44 | 1.03 | 2.59 | -$10,057 | 5 / -$5,455 |
| 2022 | 158 | $32,588 | 56.3 % | $206 | 1.27 | 0.99 | 1.78 | -$13,402 | 4 / -$10,796 |
| 2023 | 163 | $9,208 | 51.5 % | $56 | 1.10 | 1.03 | 0.70 | -$14,180 | 7 / -$7,188 |
| 2024 | 165 | $47,470 | 61.2 % | $288 | 1.50 | 0.95 | 2.93 | -$13,190 | 4 / -$7,822 |
| 2025 (Jan-Jun) | 74 | $3,419 | 48.6 % | $46 | 1.04 | 1.10 | 0.27 | -$16,825 | 6 / -$11,246 |
| **all** | 608 | $103,863 | 55.6 % | $171 | 1.25 | 1.00 | 1.57 | -$16,825 | 7 / -$11,246 |

**Long / short / combined:**

| side | trades | net | win rate | avg trade | PF | avg win | avg loss | Sharpe | max DD |
|---|---|---|---|---|---|---|---|---|---|
| long | 293 | $47,843 | 54.3 % | $163 | 1.26 | $1,461 | -$1,376 | 1.56 | -$16,691 |
| short | 315 | $56,020 | 56.8 % | $178 | 1.24 | $1,595 | -$1,687 | 1.57 | -$21,463 |
| combined | 608 | $103,863 | 55.6 % | $171 | 1.25 | $1,532 | -$1,533 | 1.57 | -$16,825 |

**More:** largest win $11,421 · largest loss -$5,619 · best winning run $21,801 · worst losing run -$11,246 (7 trades) · worst drawdown with open losses counted $17,599 · months won 65 % · trades a day 0.64

**Bootstrap** (10,000 resamples of the trades): average trade $171, 95 % range $36 to $306, chance the edge is $0 or less: 0.7 %. **Monthly win rate:** steady, lowest month 25.0 %, highest 86.7 %.

**Cost ladder** (1x = $9 a trade already in the net; the audit measured $6.4-8.5):

| friction | avg trade | net | PF | Sharpe |
|---|---|---|---|---|
| 0.5x | $175 | $106,599 | 1.26 | 1.61 |
| 1.0x | $171 | $103,863 | 1.25 | 1.57 |
| 2.0x | $162 | $98,391 | 1.24 | 1.48 |
| 4.0x | $144 | $87,447 | 1.21 | 1.32 |

**Why it was approved** (the lane's lines on the 1:1 cell, the pipeline's own functions):

- P3.2 PASS average trade $171 (need above $0)
- P3.3 PASS 608 trades (need 200)
- 3.3 PASS default variant: profit factor 1.25 over 608 trades (need 1.2 or more)
- 3.4 PASS default variant: net $103,863 / worst drawdown $17,599 = 5.90, open losses counted (need 3 or more)
- 3.5 PASS default variant: Sharpe 1.25 on 948 session days (need 1 or more)
- 3.6 PASS default variant: worst drawdown $1,760 at 1 micro, open losses counted (need under $2,000, the limit of LucidPro 50K)
- 3.7 PASS default variant: makes money in 99.3 % of 1,000 reshuffled runs (need 80 % or more)
- 3.8 PASS default variant: $61,333 without its best 1 % of days (10 of 948 session days; they made $42,530 of $103,863; need above $0)
- P4.1 PASS the box's average trade is above $0 in 99.3 % of 1,000 reshuffled runs (need 75 % or more)
- P4.2 PASS beats 100 % of the random-entry runs of the same box on try 1 (need above 95 % = 100 - 5 / 1 try)

## 3. 13:30 first bar (`cl_pm_first_bar_cdl_ema_15`)

**Per year, then combined** (1 NQ, after costs, build days):

| year | trades | net | win rate | avg trade | PF | payoff (avg win / avg loss) | Sharpe | max DD | longest losing run (trades / $) |
|---|---|---|---|---|---|---|---|---|---|
| 2021 (Sep-Dec) | 44 | -$921 | 43.2 % | -$21 | 0.90 | 1.19 | -0.68 | -$2,410 | 3 / -$2,017 |
| 2022 | 160 | $17,815 | 57.5 % | $111 | 1.40 | 1.04 | 2.22 | -$6,620 | 5 / -$6,620 |
| 2023 | 167 | $16,417 | 59.3 % | $98 | 1.55 | 1.07 | 2.95 | -$2,838 | 5 / -$2,527 |
| 2024 | 161 | $7,576 | 54.7 % | $47 | 1.19 | 0.99 | 1.20 | -$5,902 | 6 / -$3,996 |
| 2025 (Jan-Jun) | 66 | $14,726 | 62.1 % | $223 | 1.66 | 1.01 | 3.13 | -$4,052 | 4 / -$3,799 |
| **all** | 598 | $55,613 | 56.7 % | $93 | 1.38 | 1.05 | 2.06 | -$6,620 | 6 / -$6,620 |

**Long / short / combined:**

| side | trades | net | win rate | avg trade | PF | avg win | avg loss | Sharpe | max DD |
|---|---|---|---|---|---|---|---|---|---|
| long | 330 | $28,795 | 57.6 % | $87 | 1.40 | $531 | -$515 | 2.07 | -$7,215 |
| short | 268 | $26,818 | 55.6 % | $100 | 1.36 | $677 | -$622 | 2.07 | -$6,655 |
| combined | 598 | $55,613 | 56.7 % | $93 | 1.38 | $595 | -$564 | 2.06 | -$6,620 |

**More:** largest win $3,646 · largest loss -$3,799 · best winning run $5,081 · worst losing run -$6,620 (6 trades) · worst drawdown with open losses counted $7,086 · months won 72 % · trades a day 0.63

**Bootstrap** (10,000 resamples of the trades): average trade $93, 95 % range $34 to $151, chance the edge is $0 or less: 0.1 %. **Monthly win rate:** steady, lowest month 28.6 %, highest 81.8 %.

**Cost ladder** (1x = $9 a trade already in the net; the audit measured $6.4-8.5):

| friction | avg trade | net | PF | Sharpe |
|---|---|---|---|---|
| 0.5x | $97 | $58,304 | 1.40 | 2.16 |
| 1.0x | $93 | $55,613 | 1.38 | 2.06 |
| 2.0x | $84 | $50,231 | 1.34 | 1.86 |
| 4.0x | $66 | $39,467 | 1.26 | 1.47 |

**Why it was approved** (the lane's lines on the 1:1 cell, the pipeline's own functions):

- P3.2 PASS average trade $93 (need above $0)
- P3.3 PASS 598 trades (need 200)
- 3.3 PASS default variant: profit factor 1.38 over 598 trades (need 1.2 or more)
- 3.4 PASS default variant: net $55,613 / worst drawdown $7,086 = 7.85, open losses counted (need 3 or more)
- 3.5 PASS default variant: Sharpe 1.64 on 948 session days (need 1 or more)
- 3.6 PASS default variant: worst drawdown $709 at 1 micro, open losses counted (need under $2,000, the limit of LucidPro 50K)
- 3.7 PASS default variant: makes money in 99.9 % of 1,000 reshuffled runs (need 80 % or more)
- 3.8 PASS default variant: $32,908 without its best 1 % of days (10 of 948 session days; they made $22,705 of $55,613; need above $0)
- P4.1 PASS the box's average trade is above $0 in 99.9 % of 1,000 reshuffled runs (need 75 % or more)
- P4.2 PASS beats 100 % of the random-entry runs of the same box on try 1 (need above 95 % = 100 - 5 / 1 try)

## Walk-forwards of #1 and #3 (owner's word, 2026-10-20; NOT blind: relatives' months were read before)
| | #1 Open-side FVG | #3 13:30 first bar |
|---|---|---|
| stitched test months | 286 trades, +$2,341, $8 a trade, PF 1.02 | 165 trades, +$16,475, $100 a trade, PF 1.39 |
| P6.1 net > 0 | pass | pass |
| P6.2 beats random 95 % | FAIL 68.6 % | pass 100 % |
| P6.3 win rate +3 over breakeven | FAIL 52.1 % vs 54.7 % | pass 58.2 % vs 53.0 % |
| P6.4 200 trades | pass 286 | FAIL 165 |
| build-day test months | +$14,768 (213) | +$18,259 (154) |
| unseen test months (2025-07 on) | -$12,427 (73) | -$1,784 (11) |
| 1R cell every test month, unseen part | -$11,035 (90 trades) | -$3,120 (50 trades) |
Verdict: both NOT PROVEN. Both lose on the months after June 2025.
