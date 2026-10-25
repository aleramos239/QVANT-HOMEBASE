# Skeptic audit: owner_fvg_oside_15_a1m3_nl_r1 (2026-10-20)

No new runs of any kind. Everything comes from stored arrays: the build `cells.npz`, `wf/test_cells.npz` and `wf/result.json`, the
Desk port's stored walk-forward trades, and the fvg_odir unseen `trades.json`.
Scripts: `skeptic_oside_r1.py` and `skeptic_extra.py` (outputs: `.json` files with the same names). The stitched walk-forward is rebuilt
exactly from these files (380 trades, $28,525; blind 99 trades, $6,574), with asserts.

## Verdict: DOUBTFUL. The edge is not proven, and the rule is not tradeable now.
The "blind" +$6,574 is worth about $0 as evidence. On its own it is weak (t 0.80, bootstrap p 0.21). It also came after 10-12 earlier
reads of the same months, and this leg was picked partly because those months were positive. Any edge it has lives in high-volatility
stretches, and it has been losing for the last 4 whole months.

## Numbers (1 NQ, after the engine's costs)
| check | result |
|---|---|
| WF stitched | 380 trades, +$28,525, $75 a trade, t 1.63 |
| of which build-day months (the rule was designed on them) | 281 trades, +$21,951 |
| of which blind months 2025-09 / 2026-01 / 2026-05 | -$1,252 (33) / +$4,172 (32) / +$3,654 (34) = +$6,574, t 0.80 |
| top 2 months (2025-01, 2025-05) | 57 % of the WF net |
| top 5 / top 10 days (of 209) | 52 % / 90 % of the WF net |
| WF without its best 5 % of trades (19) | **-$3,789** |
| blind without its best 5 trades | **-$956** |
| build r1 cell without its best 5 % | -$31,066 (of +$97,042) |
| +1 tick a side ($10 a trade) | WF +$24,725 ($65); blind +$5,584 ($56) |
| +2 ticks a side | WF +$20,925; blind +$4,594 |
| long / short, WF | +$5,977 (217, $28) / +$22,012 (162, $136) |
| long / short, build-day months of the WF | +$2,116 (156, $14) / +$19,835 (125, $159) |
| long / short, blind | +$3,861 (61) / +$2,177 (37) |
| long / short, whole build store | $57 / $61 a trade (even) |

### The blind result rests on the monthly pick
| blind month | the pick | 0.75R | 1R | 1.25R |
|---|---|---|---|---|
| 2025-09 | 1R | +$648 | -$1,252 | -$3,537 |
| 2026-01 | 1R | +$2,893 | +$4,172 | +$5,997 |
| 2026-05 | 0.75R | **+$3,654** | **-$1,406** | +$2,034 |
| 2026-09 (to 09-22) | stood aside | -$34 | +$1,581 | +$865 |

The fixed 1:1 rule on the same 4 months makes +$3,095 on 120 trades ($26). Picking 0.75R in May 2026 accounts for +$5,060 of the gap.

### Every test day 2025-07-01 .. 2026-09-22, fixed 1R (read by the walk-forward, so not blind)
469 trades, +$68,679, $146 a trade (0.15 R; build 0.07 R). Oct + Nov 2025 alone are 50 % of it.
**The last 4 whole months (2026-05 .. 08) lose: -$13,454 on 126 trades, PF 0.84.** The drawdown from 2026-05-18 to 09-09 is **-$20,368**.
The walk-forward's own pick for 2026-10 is to stand aside.
By build year: 2023 -$6.3k; 2025 H1 +$43.7k (45 % of the build net, $228 a trade).

## Stops and Apex (1 mini; the fresh-account open-loss limit is $2,250, i.e. about 112 pts)
| sample | median | p90 | p99 | max | share over 112 pts |
|---|---|---|---|---|---|
| build days, r1 | 30.5 pt ($610) | 56.5 ($1,130) | 99 | 516 pt ($10,325, 2025-04-07) | 0.5 % |
| WF stitched months | 35 | 64-66 | 92-108 | 110 | 0 % |
| all test days 2025-07+ (Desk twin) | 41.6 ($830) | 90.9 ($1,818) | 154 | 231 ($4,625) | **4.4 %** |
- 2.35 % of the 2025-07+ trades had an MAE above $2,250. apex300 allows MAE cuts on 2 % of trades, so 1 NQ is over the line.
- The WF drawdown was $8.6k and the recent fixed-rule drawdown $20.4k. The Apex 300K threshold is $7,500, so 1 NQ is too big for a
  300K PA. It needs micros or a per-trade risk cap.
- Frequency: 1.58-1.74 a day at 1:1. The hunt asked for 5-10 a day at 1:1.5.

## Looks: how often these months were read before tonight
Every read of 2025-07+ by the FVG family (local ET):
1. 10-19 19:30, fvg_odir_15_nl_new, the single unseen read (3 cells). **87 % of its trades are this leg's test-day trades**: same day,
   side and price (319 of 367).
2. 10-19 ~20:30, wf_fvg_odir, a 48-version block WF. FAILED.
3-5. 10-19 20:33-20:35, oside a1m3 one-a-day WFs (r075 / r1 / r15).
6-7. 10-19 21:52-21:53, oside a1m3 nl WFs (r075 / **r1 = this leg**), plus wf-each.
8-9. 10-19 22:05, Desk-port WFs (r075 / r1).
10-11. 10-20 00:43-00:44, nl_x2 WFs (r075 / r1).
12. 10-20 15:37, cl_fvg_oside_15_mid_r1_t2_gap0p1 (the family's best build version, middle-candle stop). **Blind: -$12,427 on 73.**

Amendment A says the family was "read 3 times". That counts groups of reads. The real number is 10 reads of fvg_oside and 12 counting
fvg_odir, across about 60 cell versions and about 40+ fvg_oside build sheets. The no-limit sheet was written at 21:14, after reads 1-5.
Gate 2 needs blind > 0, so this leg was also selected on the same blind numbers it now offers as proof.

Discount:
- With one look, t 0.80 is not significant (p 0.21).
- With about 4-10 effective looks, the chance of at least one result this good by luck is about 60-90 %.
- For the family-wise 5 % level it needs t ≈ 2.6. At $66 a trade that takes about 1,000 blind trades, against 99 on file.
- Estimate without the picker: $8-26 a trade (Desk / lane, fixed 1R). After +1 tick that is about -$2 to +$16.
- **Treat the +$6.6k as about $0 to +$1.6k (a 75-100 % haircut).**

## Why the Desk port "made only $2-33 per NQ" (WHAT_WORKS T2b #8)
It is not an engine gap. The Desk port takes the **same trades**:
- test days: 469 of 469 matched by entry time, median difference per trade $0, nets $66,999 vs $68,679;
- build days: 1,652 of 1,652 matched, $97,437 vs $97,042.

The gap has three causes:
1. The Desk WF has one cell, so it trades fixed 1:1 (or fixed 0.75) in every test month and never stands aside. The lane WF switches
   the target month by month and stood aside in 2026-09.
2. The Desk's last month runs to 09-30 (6 more trades, about -$1.8k NQ-eq). The lane stops at 09-22.
3. The Desk charges $1 a round turn on a micro, which is $10 NQ-eq against the lane's $4.

In NQ terms, Desk 1R blind = -$1,252 + $3,782 - $1,321 - $193 = +$1,016 on 126 trades ($8). The lane's fixed 1R on the same months
is $26. The lane WF with picks is $66.

**For trading by hand:** someone trading the rule as written (fixed 1:1) would have made about $8-26 a trade on the blind months,
about zero. The $66 needs the exact monthly target pick: every 4 months, take the middle passing cell of the last 3 months. That pick
turns May 2026 from -$1.4k into +$3.7k, and today it says stand aside.

## What I did not check
- No random control on the blind months alone (the WF did not store its test-day random pool).
- No queue-position or partial-fill model for the limit entry (the engine fills 1 tick through).
- No Apex simulator run.
