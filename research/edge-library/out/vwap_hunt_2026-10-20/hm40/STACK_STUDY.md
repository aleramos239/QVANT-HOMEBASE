# The stack, in-sample: a day-by-day study (8 picked versions, NY sessions, 1 contract each)

Read from the in-sample stores only (runs_wf/<store>/is: 883 in-sample days, 2021-10-01 .. 2026-04-30; no test month). Script: stack_study.py. Every leg's trade count and net match stack.json. Nets are after the store's costs, 1 full NQ contract a leg, no extra tick.

## The legs

| # | Leg | Trades | Net | Avg | Win | Long share | Avg hold | Exit: target / stop / time-or-close |
|---|---|---|---|---|---|---|---|---|
| 1 | orbc long 5m (or_min60_own1p5-r2) | 975 | $243,305 | $250 | 60.0 % | 100.0 % | 210 min | 0.3 % / 4.7 % / 95.0 % |
| 2 | rvol break (m1p5_own1-r2) | 502 | $109,367 | $218 | 48.2 % | 34.5 % | 112 min | 20.3 % / 40.6 % / 39.0 % |
| 3 | displace (k1_own2-r2) | 1931 | $274,521 | $142 | 49.8 % | 48.9 % | 213 min | 4.8 % / 23.6 % / 71.7 % |
| 4 | donchian (n10_own1-r1p5) | 2049 | $481,924 | $235 | 53.8 % | 53.7 % | 183 min | 10.0 % / 17.6 % / 72.5 % |
| 5 | orb vwap pb (or_min15_pts60-r2) | 485 | $85,125 | $176 | 43.7 % | 50.5 % | 116 min | 25.2 % / 48.2 % / 26.6 % |
| 6 | win break 9:45 (r_end0945_own2-r1p5) | 757 | $190,122 | $251 | 56.0 % | 52.2 % | 316 min | 4.0 % / 14.1 % / 81.9 % |
| 7 | onr orb (adx_min10_own2-r2) | 356 | $147,211 | $414 | 59.8 % | 52.8 % | 240 min | 1.4 % / 11.2 % / 87.4 % |
| 8 | noise long 5m (k0p3_pts60-r2) | 902 | $91,877 | $102 | 46.9 % | 100.0 % | 125 min | 16.6 % / 44.5 % / 38.9 % |
| | **Stack** | **7957** | **$1,623,452** | **$204** | **52.3 %** | 61.9 % | 194 min | |

## (a) Trades a day

Average 9.01 a day, median 9, most 18 (on 2023-12-20).

| Trades that day | Days | Share of days | Net of those days | Avg day |
|---|---|---|---|---|
| 0 (data-gap days) | 7 | 0.8 % | $0 | $0 |
| 1-4 | 38 | 4.3 % | $2,411 | $63 |
| 5-10 | 552 | 62.5 % | $276,840 | $502 |
| >10 | 286 | 32.4 % | $1,344,201 | $4,700 |

Entries by hour (ET):

| Hour | Trades | Share | Net | Avg trade | Win |
|---|---|---|---|---|---|
| 09:00 | 1022 | 12.8 % | $423,297 | $414 | 51.9 % |
| 10:00 | 2474 | 31.1 % | $528,764 | $214 | 52.5 % |
| 11:00 | 1429 | 18.0 % | $339,699 | $238 | 53.7 % |
| 12:00 | 640 | 8.0 % | $66,405 | $104 | 48.1 % |
| 13:00 | 1059 | 13.3 % | $197,084 | $186 | 55.6 % |
| 14:00 | 815 | 10.2 % | $14,610 | $18 | 50.2 % |
| 15:00 | 518 | 6.5 % | $53,593 | $103 | 50.4 % |

## (b) Daily net (1 contract a leg)

On the 876 days with a trade: average $1,853, spread (sd) $13,661, 48.7 % of them positive.

| Percentile | 5 % | 10 % | 25 % | 50 % | 75 % | 90 % | 95 % |
|---|---|---|---|---|---|---|---|
| Day net | -$15,619 | -$12,054 | -$6,707 | -$436 | $8,624 | $19,412 | $26,708 |

| Risk number | Value |
|---|---|
| Max drawdown, daily closes | -$121,805 (2025-06-04 .. 2025-07-30) |
| Max drawdown, trade by trade (exit order) | -$123,859 |
| Longest losing streak (trading days in a row below 0) | 8 days |
| Longest losing streak (trades in a row below 0, entry order) | 23 trades |
| Longest time under a high (days) | 98 days |
| Worst day / best day | -$38,018 / $105,103 |
| The best 10 % of trading days (88) | $2,611,416 = 160.9 % of the net; the other 90 % -$987,964 |

The equity line joins the in-sample months only (each block's test month is left out), so drawdowns, streaks and 'days under a high' run across those gaps.

Worst 10 days:

| Date | Net | Trades | Legs that traded | Longs / shorts |
|---|---|---|---|---|
| 2025-03-07 | -$38,018 | 12 | 7 | 5 / 7 |
| 2025-03-06 | -$36,165 | 15 | 8 | 8 / 7 |
| 2025-03-11 | -$31,644 | 11 | 7 | 8 / 3 |
| 2024-08-06 | -$29,297 | 13 | 5 | 10 / 3 |
| 2023-06-14 | -$28,665 | 15 | 8 | 11 / 4 |
| 2022-11-08 | -$28,636 | 14 | 7 | 9 / 5 |
| 2024-08-23 | -$28,298 | 12 | 7 | 8 / 4 |
| 2022-03-08 | -$26,278 | 12 | 7 | 8 / 4 |
| 2022-10-26 | -$24,913 | 12 | 5 | 9 / 3 |
| 2022-03-16 | -$24,811 | 14 | 6 | 9 / 5 |

## (c) The owner's account rule: one position per account, 5 accounts

All trades in time order; a signal is skipped only when 5 positions are already open; a position frees its account at its exit.

| | Trades | Net | Avg trade | Win | Max drawdown (daily) |
|---|---|---|---|---|---|
| All signals | 7957 | $1,623,452 | $204 | 52.3 % | -$121,805 |
| Kept | 5830 | $1,318,950 | $226 | 51.7 % | -$103,649 |
| Skipped | 2127 (26.7 %) | $304,502 | $143 | 54.0 % | |

Net kept = 81.2 % of the full stack's net. Days on which 6+ positions would be open at once: 631 of 883 (71.5 %).

| Most positions open at once that day | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|---|
| Days | 7 | 2 | 1 | 28 | 81 | 133 | 631 |

Skipped by leg: orbc long 5m 414, rvol break 108, displace 349, donchian 648, orb vwap pb 107, win break 9:45 1, onr orb 47, noise long 5m 453.

## (d) How the legs move together

Daily net correlation (all 883 days, 0 on a leg's no-trade days): average pair +0.31, lowest +0.07, highest +0.67. With that average, the 8 legs act like about 2.6 independent bets (8 / (1 + 7 x average pair)).

| Leg | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | vs rest of stack |
|---|---|---|---|---|---|---|---|---|---|
| 1 orbc long 5m |  | +0.12 | +0.34 | +0.51 | +0.14 | +0.26 | +0.25 | +0.48 | +0.48 |
| 2 rvol break | +0.12 |  | +0.39 | +0.45 | +0.07 | +0.17 | +0.13 | +0.09 | +0.35 |
| 3 displace | +0.34 | +0.39 |  | +0.67 | +0.18 | +0.50 | +0.28 | +0.35 | +0.65 |
| 4 donchian | +0.51 | +0.45 | +0.67 |  | +0.24 | +0.55 | +0.42 | +0.39 | +0.79 |
| 5 orb vwap pb | +0.14 | +0.07 | +0.18 | +0.24 |  | +0.34 | +0.16 | +0.21 | +0.28 |
| 6 win break 9:45 | +0.26 | +0.17 | +0.50 | +0.55 | +0.34 |  | +0.35 | +0.32 | +0.57 |
| 7 onr orb | +0.25 | +0.13 | +0.28 | +0.42 | +0.16 | +0.35 |  | +0.21 | +0.41 |
| 8 noise long 5m | +0.48 | +0.09 | +0.35 | +0.39 | +0.21 | +0.32 | +0.21 |  | +0.47 |

Same direction at once (distinct legs holding the same side at the same moment, the trade itself counted):

| Legs on one side at once (at entry) | Trades | Share | Net | Avg trade | Win |
|---|---|---|---|---|---|
| 1 | 915 | 11.5 % | -$12,400 | -$14 | 46.0 % |
| 2 | 1547 | 19.4 % | $389,587 | $252 | 51.6 % |
| 3 | 1770 | 22.2 % | $487,485 | $275 | 52.7 % |
| 4+ | 3725 | 46.8 % | $758,780 | $204 | 54.0 % |

Days with 3+ legs on one side at some moment: 846 of 876 trading days (96.6 %); their net $1,684,468 (103.8 % of the total), avg day $1,991; the other trading days avg -$2,034. Most legs on one side at once: 8.
On days with 2+ legs trading (873), the day's majority side holds 81 % of its trades on average; all trades on one side on 29.2 % of those days.

## (e) By year and by month (in-sample months only)

| Year | Days | Trades | Trades/day | Net | Avg trade | Win | Days > 0 | Max drawdown (daily) |
|---|---|---|---|---|---|---|---|---|
| 2021 | 64 | 545 | 8.5 | $108,990 | $200 | 54.7 % | 54.0 % | -$46,772 |
| 2022 | 189 | 1683 | 8.9 | $459,443 | $273 | 54.5 % | 49.2 % | -$57,638 |
| 2023 | 189 | 1762 | 9.3 | $211,687 | $120 | 51.2 % | 47.9 % | -$59,606 |
| 2024 | 189 | 1736 | 9.2 | $289,901 | $167 | 50.5 % | 45.0 % | -$79,303 |
| 2025 | 189 | 1680 | 8.9 | $335,735 | $200 | 52.0 % | 49.7 % | -$121,805 |
| 2026 | 63 | 551 | 8.7 | $217,696 | $395 | 53.7 % | 53.2 % | -$55,988 |

Net per month, $k (blank = a test month, not used): 34 of 42 in-sample months positive; worst -$52,509, best $168,141.

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021 |  |  |  |  |  |  |  |  |  | +42.5 | -18.9 | +85.3 |
| 2022 |  | +41.2 | +32.7 | +112.2 |  | +17.7 | +130.4 | +30.0 |  | +71.4 | +12.1 | +11.8 |
| 2023 |  | +3.8 | +46.4 | +33.3 |  | +27.4 | -23.3 | +67.9 |  | +15.0 | +16.1 | +25.0 |
| 2024 |  | -34.1 | +14.2 | +77.6 |  | +18.7 | +55.4 | -11.3 |  | +66.9 | -2.1 | +104.7 |
| 2025 |  | +109.1 | +11.7 | +168.1 |  | -52.5 | -30.6 | -1.9 |  | +83.8 | +24.5 | +23.4 |
| 2026 |  | +62.9 | +102.6 | +52.2 |  |  |  |  |  |  |  |  |

| Calendar month (years pooled) | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Net $k |  | +183.0 | +207.5 | +443.4 |  | +11.2 | +131.9 | +84.8 |  | +279.6 | +31.7 | +250.2 |
| Months > 0 |  | 4/5 | 5/5 | 5/5 |  | 3/4 | 2/4 | 2/4 |  | 5/5 | 3/5 | 5/5 |

## (f) Long vs short

| Side | Trades | Net | Avg trade | Win | Share of the stack's net |
|---|---|---|---|---|---|
| Long | 4924 | $1,033,379 | $210 | 54.7 % | 63.7 % |
| Short | 3033 | $590,073 | $195 | 48.4 % | 36.3 % |

| Leg | Long trades | Long net | Long avg | Short trades | Short net | Short avg |
|---|---|---|---|---|---|---|
| 1 orbc long 5m | 975 | $243,305 | $250 | 0 | $0 | - |
| 2 rvol break | 173 | $29,253 | $169 | 329 | $80,114 | $244 |
| 3 displace | 945 | $182,095 | $193 | 986 | $92,426 | $94 |
| 4 donchian | 1101 | $258,876 | $235 | 948 | $223,048 | $235 |
| 5 orb vwap pb | 245 | $43,145 | $176 | 240 | $41,980 | $175 |
| 6 win break 9:45 | 395 | $103,350 | $262 | 362 | $86,772 | $240 |
| 7 onr orb | 188 | $81,478 | $433 | 168 | $65,733 | $391 |
| 8 noise long 5m | 902 | $91,877 | $102 | 0 | $0 | - |

## (g) What kind of day pays (NY 09:30-16:00 range and how far it went one way; hindsight, descriptive only)

867 trading days with a full NY session in the 5m cache. 'One-way' = |last 5m mid - first 5m mid| / the session range.

| Days, by | Third | Days | Avg range (pts) | Stack avg day | Share of these days' net | Days > 0 |
|---|---|---|---|---|---|---|
| session range | low | 289 | 156 | -$2,438 | -44.8 % | 28.7 % |
| session range | middle | 290 | 246 | $1,337 | 24.7 % | 53.1 % |
| session range | high | 288 | 442 | $6,558 | 120.2 % | 63.9 % |
| one-way | low | 289 | 232 | -$8,644 | -158.9 % | 4.5 % |
| one-way | middle | 289 | 273 | -$534 | -9.8 % | 46.0 % |
| one-way | high | 289 | 338 | $14,617 | 268.7 % | 95.2 % |

| Trades, by the NY session's eventual direction | Trades | Net | Avg trade |
|---|---|---|---|
| With it | 6113 | $5,145,358 | $842 |
| Against it | 1782 | -$3,573,528 | -$2,005 |

## Conclusions (hand-written from the tables above; in-sample only, the months the stack was picked on)

**What the stack is: mostly one bet -- that the NY session runs one way and closes far from its open, ridden to the close.**

| Sign | Number |
|---|---|
| Legs move together | average pair +0.31 -> about 2.6 independent bets, not 8; donchian vs the rest +0.79 |
| Same side at once | 69 % of trades enter while 3+ legs hold the same side; the day's majority side holds 81 % of the day's trades |
| Held to the close | average hold 194 min; 5 of 8 legs exit by time / the close on 72-95 % of trades |
| Trend days pay, chop days pay for them | days in the top third for 'one-way': avg +$14,617, 95 % positive; bottom third: avg -$8,644, 4.5 % positive |
| With vs against the day | trades on the side the session ended up going: +$842 avg; against it: -$2,005 avg (hindsight, not a rule) |
| Mornings | 62 % of trades enter 09:30-11:59 and make 80 % of the net; 14:00 entries average +$18 |
| Long tilt | 62 % of trades long (2 legs are long-only), 64 % of the net |

**Trades a day: the count goal is met.** 9.0 a day on average; 95 % of days have 5+ (62.5 % have 5-10, 32.4 % more than 10).
But the busy days are the trend days: days with more than 10 trades made $1.34M of the $1.62M (83 %).

**In-sample risk (1 full NQ a leg; divide by 10 for 1 MNQ a leg):**

| Risk | 1 NQ a leg | 1 MNQ a leg |
|---|---|---|
| Median trading day | -$436 | -$44 |
| Days positive | 48.7 % | 48.7 % |
| 1 day in 20 worse than | -$15,619 | -$1,562 |
| Worst day | -$38,018 | -$3,802 |
| Max drawdown | -$121,805 (Jun-Jul 2025) | -$12,181 |
| Longest losing run | 8 days; 98 days under a high | same |

- It is a right-tail book: the best 10 % of days (88) made 161 % of the net; the other 90 % of days lost $988k together.
  A run of quiet, two-way sessions is the normal way it loses (Jun-Aug 2025: -$85k in three in-sample months).
- Every in-sample year was positive (2023 weakest at $120 a trade) and 34 of 42 in-sample months; June-August are the weak months
  (7 of 12 positive: Jun 3/4, Jul 2/4, Aug 2/4).
- The owner's account rule (one position per account, 5 accounts) skips 27 % of signals (2,127; they average $143 against $226 kept)
  and keeps 81 % of the net ($1.32M); the drawdown falls to -$103,649. On 71 % of days 6+ positions would be open at once.
- Trades taken alone (no other leg on that side at entry): 915, -$14 a trade. The stack earns only when legs pile up on one side.

**Plain read:** the stack is not 8 diversified rules; it is about 2-3 bets on the same thing -- an NY morning break that keeps going
to the close -- sized 8 ways. On a trend day it makes a lot at once; on chop days most legs lose together. Its day-to-day swing
(sd $13,661 a day at 1 NQ a leg, $1,366 at 1 MNQ) is far bigger than 8 independent rules would give, which matters for any daily
loss limit. All of this is in-sample: CHECKPOINT_1 found that in-sample numbers in this hunt have not carried to test months.
