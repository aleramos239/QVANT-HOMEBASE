# 100 strategy ideas from the papers (2026-10-26)

Owner ask: build on the papers sent 2026-10-24..26 (not copies), take each paper's underlying hypothesis, fixed TP / SL,
flat 16:00 ET, prefer high win rate and many trades. Nothing here is tested. Each section starts with the hypothesis and
the paper it came from; the ideas follow.

**Exits** (every idea, flat by 16:00 ET, one position at a time, entries on a bar close so no profit comes from <= 5 s holds):

| Code | Stop | Target | Why |
|---|---|---|---|
| E1 | 1 x ATR(14) of the idea's bar | 0.5 R | high win rate, the house default cell |
| E2 | just beyond the setup's own level (range edge, bar extreme) | 0.5 R | the stop sits where the idea is wrong |
| E3 | the setup's own level | a fixed level (VWAP, range middle), capped at 1 R | target is where the idea says price goes |

The hm40 heat map tests the full stop / target grid anyway; the code is the starting cell.
A 0.5 R target needs about a 67 % win rate just to break even, so a high win rate alone proves nothing. The edge has to beat that.
Lucid counts open losses: the stop in dollars must stay well inside the daily drawdown.

**Rules** = how many conditions the entry has (owner: fewer is better). **Freq** = a guess, not a count.
**Seen** = something close already exists in Homebase: a family in `engine/families/`, a line in `IDEAS.md`, or the
2026-10-25 list (`30-Projects/Onyx-Trading/ideas-100-untried-2026-10-25.md`, "10-25 #n").

---

## A. Range budget: a day only moves so far
*Wu et al. 2026 (LSTM true-range ORB): knowing today's true range in advance made ORB much better. Plain version: each day has a
normal range; where price is against that budget tells you whether a move has room left or is spent.* ADR = 14-day average daily range.

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 1 | Range-spent fade, NQ 5m | after the day's range reaches 100 % of ADR, the first 5m close back inside after a new day high / low: fade it | E2 | ~2/wk | 2 | |
| 2 | Range-left follow, NQ 5m | at 11:00, if less than 50 % of ADR is used, take the first break of the 09:30-11:00 range | E1 | ~3/wk | 2 | |
| 3 | Projected-edge fade | levels = 09:30 open +/- 0.5 x ADR; first touch: fade | E2 | ~3/wk | 1 | |
| 4 | Big-day follow-on | after a day with true range >= 1.5 x ATR(14 d), trade the 15m ORB break either way (volatility clusters) | E1 | ~1/wk | 2 | orb |
| 5 | Quiet-day fade | after a day with true range <= 0.7 x ATR(14 d), fade the first 15m ORB break (quiet persists) | E3 (OR middle) | ~1/wk | 2 | |
| 6 | Overnight-spent fade | if 18:00-09:30 already used 60 % of ADR, fade the first RTH push past the overnight high / low | E2 | ~2/wk | 2 | |
| 7 | Remaining-range target ORB | 15m ORB break; target = 25 % of ADR from entry, stop = OR middle | fixed | daily | 1 | orb |
| 8 | Fast-open trend day | if 09:30-10:00 used 40 % of ADR, buy (sell) the first 5m pullback to VWAP in that direction | E1 | ~2/wk | 2 | |
| 9 | Range-spent fade, GC | idea 1 on gold, 08:20-13:30 | E2 | ~2/wk | 2 | |
| 10 | Week-spent fade | from Wednesday, if the week's range >= the average weekly range, fade new week highs / lows | E2 | ~1/wk | 2 | |

## B. Retest anatomy: how a broken level gets retested says whether the break is real
*Pineda 2026 (QQQ ORB retest): most breaks retest the broken level; the time until the retest is the strongest link to the
outcome; a big run before the retest means a LOWER chance of continuation.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 11 | Fast retest go | 15m OR break, price comes back to the broken edge within 30 min: enter at the edge with the break | E2 (0.5 x OR beyond) | ~3/wk | 2 | |
| 12 | Slow retest fade | same, but the retest comes after 60 min: fade back into the range | E3 (OR middle) | ~2/wk | 2 | |
| 13 | Small-run retest go | the break ran less than 0.5 x OR before the retest: go with the break | E2 | ~2/wk | 2 | |
| 14 | Big-run retest fade | the break ran more than 1.5 x OR before the retest: fade toward the OR middle | E3 | ~1/wk | 2 | |
| 15 | PDH / PDL fast retest | break of the prior-day high (low), back to it within 30 min: go with the break | E2 | ~2/wk | 2 | 10-25 #26 is first touch, not retest |
| 16 | Overnight high / low fast retest | same on the 18:00-09:30 high / low | E2 | ~2/wk | 2 | |
| 17 | VWAP cross retest | 5m close crosses VWAP, comes back to touch it within 3 bars and closes on the new side: follow | E1 | daily | 2 | vwap_flip lost |
| 18 | Swing retest | break of a confirmed 50-bar swing, back to it within 6 bars: follow | E2 | ~2/wk | 2 | |
| 19 | GC first-hour fast retest | idea 11 on gold's 08:20-09:20 range | E2 | ~3/wk | 2 | |
| 20 | ES 30m OR fast retest | idea 11 on ES with a 30-minute range | E2 | ~3/wk | 2 | |

## C. Expansion-bar exhaustion: a huge bar has finished its move by the time it closes
*Mesfin 2026 (MNQ falsification): following big expansion bars lost with T = -11.5, the strongest number in the paper; the move is
used up inside the bar and the next bar gives some back. Same in their London result: a one-bar delay flipped the sign.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 21 | Expansion fade, NQ 5m RTH | bar range >= 2 x its 20-bar average: fade at the next open | E1 | 1-3/day | 1 | |
| 22 | Expansion fade, NQ 1m | bar range >= 3 x its 20-bar average: fade | E1 | 3+/day | 1 | |
| 23 | Expansion fade, NQ 15m | bar range >= 2 x its 20-bar average: fade | E1 | ~1/day | 1 | |
| 24 | Asia expansion fade | 20:00-02:00, 5m bar >= 1.5 x average: fade (the paper's own losing signal turned round, now with a stop and target) | E1 | 2+/day | 1 | |
| 25 | London expansion fade | same, 03:00-08:30 | E1 | 1-2/day | 1 | |
| 26 | Expansion away from VWAP | only expansion bars that close further from VWAP than they opened: fade | E1 | ~1/day | 2 | |
| 27 | Expansion into a level | expansion bar that reaches PDH / PDL or the overnight high / low: fade | E2 | ~2/wk | 2 | |
| 28 | Volume-climax fade | bar volume >= 3 x the 20-bar mean AND range >= 1.5 x average: fade | E1 | ~1/day | 2 | vol_spike_break was the follow side |
| 29 | Three-bar run fade | three 5m bars the same colour, each bigger than the last: fade | E1 | ~1/day | 1 | |
| 30 | Afternoon expansion fade | idea 21 only 13:00-15:30 | E1 | ~1/day | 2 | |
| 31 | Expansion fade, ES 5m | idea 21 on ES | E1 | 1-3/day | 1 | |
| 32 | Expansion fade, GC 5m | idea 21 on gold (gold wicks hard) | E1 | 1-3/day | 1 | |
| 33 | Expansion fade to the midpoint | target = the expansion bar's 50 % level, stop = half the bar beyond its extreme | E3 | 1-3/day | 1 | |
| 34 | Expansion then inside bar | expansion bar, then an inside bar: fade on the inside bar's break | E2 | ~1/day | 2 | |
| 35 | Opening-bar expansion fade | the 09:30 5m bar is an expansion bar: fade at 09:35 | E1 | ~2/wk | 1 | open_fade |

## D. Gap continuation with a fast open
*Mesfin 2026: the near-miss was gap continuation short with strong first-30-minute velocity (+16.5 points gross, T 1.46, 35 trades).
Also their VVG days: when the gap, the first move and the volume are all big, the day is different.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 36 | Gap-and-go short | gap down >= 0.3 x ATR(14 d) and 09:30-10:00 return <= -0.5 x ATR(14 d): short at 10:00 | E1 | ~1/wk | 2 | gap |
| 37 | Gap-and-go both sides | idea 36, mirrored for gap-up days | E1 | ~2/wk | 2 | gap |
| 38 | Small-gap half fill | gap < 0.3 x ATR(14 d): fade at 09:35, target = half the gap (high win rate) | fixed | ~3/wk | 1 | gap |
| 39 | Big gap holds | gap >= 1 x ATR(14 d) and the first 15m bar fills less than 25 % of it: go with the gap | E1 | ~1/wk | 2 | |
| 40 | Wild-open fade | gap, first 30 minutes and first-bar volume all in their top third: fade at 10:00 | E1 | ~1/mo | 3 | |
| 41 | Inside-range gap fade | the open is inside yesterday's range: fade the gap toward the prior close | E3 | ~3/wk | 1 | gap |
| 42 | Gold small-gap fade | GC 08:20 open vs the prior 13:30 close, small gaps: fade | E3 | ~3/wk | 1 | gap_GC |
| 43 | Overnight-middle magnet | after 10:00, price >= 1 x ATR from the middle of the overnight range: fade toward it | E3 | ~2/wk | 1 | |

## E. Noise band variants: inside the usual move it is noise, outside it someone big is pushing
*Delgado 2026 replication of Zarattini / Aziz / Barbon: it replicates, held up for 15 months after publication, then lost money for
a year. `noise.py` and `noise_eve.py` exist and were the best in-sample; these are new angles only.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 44 | Band-edge fade | price touches the band edge but does not close outside at the 30-minute check: fade toward the open | E3 | daily | 1 | noise |
| 45 | Failed band break | closes outside, then back inside within 2 checks: fade toward the open | E3 | ~3/wk | 2 | noise |
| 46 | Paper-exact VWAP | the band break with the replication's two details: typical-price VWAP and VWAP confirming at entry | E1 | daily | 2 | noise |
| 47 | Band plus range budget | take band breaks only while less than 70 % of ADR is used | E1 | ~4/wk | 2 | noise |
| 48 | Band, fixed 0.5 R target | the band break with a 0.5 R target instead of the VWAP trail (the high-win-rate version) | E1 | daily | 1 | noise |
| 49 | First check only | only the 10:00 check, one shot a day | E1 | ~3/wk | 1 | noise |
| 50 | Globex-open band | band built from the 18:00 open, traded 09:30-15:55 | E1 | daily | 1 | noise_eve |

## F. Institutional VWAP execution: big orders get worked toward VWAP
*Singh 2026 (VWAP execution survey) plus Gao et al. 2018: funds slice orders along the day's volume curve and are graded against
VWAP, so price is pulled back to VWAP, and late flow follows the day's trend.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 51 | VWAP stretch fade | 5m close >= 2 x ATR from VWAP: fade, target halfway back to VWAP | E3 | ~1/day | 1 | vwap_z, vwap_band |
| 52 | Late VWAP magnet | after 14:30, price >= 1.5 x ATR from VWAP: fade toward VWAP | E3 | ~2/wk | 2 | |
| 53 | Volume ahead of the curve | at 10:30, volume so far >= 1.5 x its 20-day same-time mean: trade the side of VWAP | E1 | ~1/wk | 2 | |
| 54 | Volume behind the curve | volume so far <= 0.7 x the same-time mean: it's a range day, so fade 15m OR breaks | E3 | ~1/wk | 2 | |
| 55 | Lunch VWAP revert | 11:30-13:30, a 1 x ATR move from VWAP: fade it (executors are quiet at lunch) | E3 | ~1/day | 2 | |
| 56 | Close-flow follow | 15:45: price on the same side of VWAP as the day's move: follow, flat 16:00 | E1 | daily | 2 | day_move, late_mom |
| 57 | Yesterday's closing VWAP | first touch of the prior session's final VWAP: fade | E2 | ~3/wk | 1 | |
| 58 | Weekly VWAP touch | first touch of the week-anchored VWAP: fade | E2 | ~3/wk | 1 | avwap |
| 59 | VWAP reclaim | below VWAP the whole first hour, then two 5m closes above it: long (and the mirror) | E1 | ~2/wk | 2 | |
| 60 | Globex VWAP in RTH | first RTH touch of the 18:00-anchored VWAP: fade | E2 | ~3/wk | 1 | |

## G. Exhaustion at known extremes
*Bhatti 2026 (ADX + VWAP, FX): at the prior session's high or low, stretched from VWAP, with the trend fading, the move is out of
fuel. `pd_vwap_adx` is built; these swap in other extremes or other fade signals.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 61 | PDH / PDL + RSI divergence | at the prior-day extreme, RSI(14) makes a lower high (higher low): fade | E2 | ~1/wk | 2 | pd_vwap_adx |
| 62 | Overnight extreme + VWAP stretch | at the overnight high / low and >= 1.5 x ATR from VWAP: fade | E2 | ~1/wk | 2 | |
| 63 | Prior-week extreme + stretch | at last week's high / low and stretched from VWAP: fade | E2 | ~2/mo | 2 | |
| 64 | New-high ADX turn | a new day high while ADX(14) is lower than on the bar before: fade | E2 | ~2/wk | 2 | vwapadx |
| 65 | Second-test fade | second test of the day high within 10 points, on lower bar volume: fade | E2 | ~2/wk | 2 | |

## H. Trend pullback with close-only stops
*Bhatti 2026 (gold EMA / VWAP) plus the two crossover papers: trends persist and win by keeping losses small; buy dips to the average in
the trend's direction; gold wicks, so judge stops on closes. `ema_vwap_pb` (gold) is built and `ema_pullback` was tried on the old route.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 66 | NQ 5m EMA20 rejection | price > EMA200, EMA50 > VWAP, a bar rejects the EMA20: long (and the mirror) | E1 | ~1/day | 3 | ema_pullback |
| 67 | Daily-trend VWAP dip | price above its 200-day mean: long only, the first pullback to VWAP after 10:00 | E1 | ~3/wk | 2 | |
| 68 | Daily EMA-directed ORB | daily 20 EMA > 50 EMA: long-only 15m ORB; below: short only | E1 | ~4/wk | 2 | orb |
| 69 | Close-only stop | any pullback idea, stopped only on a 5m close beyond EMA50, with a hard stop at 2 x ATR | close stop | n/a | +1 | |
| 70 | 1h-trend 5m dip | 1h EMA50 rising: 5m touch of EMA20 = long | E1 | ~1/day | 2 | |
| 71 | Gold 5m EMA21 dip | GC, 1h trend up: 5m rejection of EMA21 = long (and the mirror) | E1 | ~1/day | 2 | ema_vwap_pb |
| 72 | Trend inside-bar break | 15m inside bar, break in the EMA50 slope's direction | E2 | ~1/day | 2 | |
| 73 | Trend-day 38 % dip | a new day high after 10:30: buy a 38 % pullback of the day's range | E2 | ~2/wk | 2 | |
| 74 | Swing-low hold | uptrend, pullback to the latest 50-bar swing low that holds on the close: long | E2 | ~1/wk | 2 | |
| 75 | ES-led NQ dips | ES above its VWAP and EMA50: take only NQ pullback longs (and the mirror) | E1 | ~1/day | 2 | |

## I. Failed breaks: trapped breakout traders have to get out
*Mesfin 2026: ORB pullback entries were stopped out 81 % of the time, so breaks that come back usually fail. Pineda 2026: a big run
before the retest means low continuation. The 10-25 list has "fade the first break"; these wait for the close back inside.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 76 | Failed OR break | 15m OR break, then a 5m close back inside within 2 bars: fade toward the far side | E1 | ~3/wk | 2 | |
| 77 | Failed PDH / PDL break | same at the prior-day high / low | E2 | ~2/wk | 2 | sweep_rev, sfp |
| 78 | Failed overnight-extreme break | same at the overnight high / low | E2 | ~2/wk | 2 | |
| 79 | Failed swing break | a sweep of a 50-bar swing, closed back inside: fade | E2 | ~1/wk | 2 | sweep_rev, sfp, liq |
| 80 | Range-day edge fade | once both sides of the 30m OR have failed once, fade every OR-edge touch until 15:00 | E3 | 2+/day on those days | 2 | |
| 81 | Failed afternoon high | a new day high after 13:00 that closes back below within 2 bars: fade | E2 | ~2/wk | 2 | |
| 82 | Failed 08:30 move | the 08:30 bar breaks the pre-data range, and 09:30 opens back inside it: fade | E3 | ~1/wk | 2 | |
| 83 | Failed London break | London breaks the Asia range, NY opens back inside it: fade toward the Asia middle | E3 | ~1/wk | 2 | lon_break |

## J. Session handoff: a clean turn in one session carries into the next, but the first bar takes most of it
*Mesfin 2026 (London Signal B): a clean bearish-to-bullish turn in London paid, but only at once; one bar late lost.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 84 | London trend, NY dip | London (03:00-08:30) up >= 0.5 x ATR(14 d): buy the first 09:30-10:30 pullback to VWAP | E1 | ~2/wk | 2 | |
| 85 | London flip long | Asia closed down, London's first hour closed up: long at 04:00 | E1 | ~1/wk | 2 | |
| 86 | GC Asia break in London | gold, break of the 18:00-03:00 range after 03:00 | E1 | ~4/wk | 1 | 10-25 #22 is the fade |
| 87 | London-extreme fade in NY | first NY test of the London high / low: fade | E2 | ~3/wk | 1 | |
| 88 | Pre-market range break | the 08:30-09:30 range, first break after 09:30: follow | E1 | ~4/wk | 1 | |
| 89 | Euro-close VWAP flip | between 11:30 and 12:00, price changes side of VWAP: follow | E1 | ~2/wk | 2 | |
| 90 | Asia-open fade of RTH | at 20:00, fade the 09:30-16:00 move | E1 | daily | 1 | 10-25 #56 is the follow |

## K. Agreement and diversity: many fixed simple rules beat one tuned rule
*Feng et al. (iStratDE): many fixed, different strategies beat one adaptive one. Levine 2026: ORB did best in volatile markets.
Homebase 2026-10-02 (`bimb930`): agree-days + RSI direction passed 27-28 of 30 variants.*

| # | Idea | Entry | Exit | Freq | Rules | Seen |
|---|---|---|---|---|---|---|
| 91 | ORB + VWAP + open agree | 15m OR break only on the same side of VWAP and of the 09:30 open | E1 | ~3/wk | 3 | |
| 92 | NQ-ES agree | both break their 15m OR the same way within 10 min: trade NQ | E1 | ~3/wk | 2 | |
| 93 | NQ-ES divergence fade | NQ makes a new day high, ES does not: fade NQ | E2 | ~2/wk | 2 | |
| 94 | Index breadth | 3 of NQ / ES / YM / RTY above VWAP: NQ pullback longs only (and the mirror) | E1 | ~1/day | 2 | |
| 95 | Gold-silver agree | GC and SI both break their first-hour range the same way: trade GC | E1 | ~2/wk | 2 | |
| 96 | Volatility switch | daily ATR in its top third: follow OR breaks; bottom third: fade them | E1 / E3 | daily | 2 | |
| 97 | Two-clock agree | 5m and 15m bars close beyond VWAP on the same bar: follow | E1 | ~1/day | 2 | |
| 98 | Three-way vote at 10:00 | OR side, VWAP side and prior-close side all agree: trade at 10:00 | E1 | ~3/wk | 3 | |
| 99 | Fixed diverse stack | 4 low-correlation keepers from this list on one account at 1 micro each, never re-tuned | each own | daily | n/a | portfolio |
| 100 | Forecast-range ORB stop | 15m ORB with stop = 0.25 x YESTERDAY's true range instead of ATR (the LSTM paper's claim, using yesterday's true range as the forecast) | fixed | daily | 1 | orb |

---

## Where to start (my picks)

| Pick | Why |
|---|---|
| 21 / 31 / 32 Expansion fade | the strongest number in all the papers (T -11.5 the other way), one rule, fires several times a day, fits a 0.5 R target |
| 11 + 13 Fast / small-run retest | the paper's strongest link, new to Homebase, one clear level |
| 76 Failed OR break | the inverse of the 81 % stop-out finding, new to Homebase (the 10-25 list fades the first break, not the close back inside) |
| 44 / 48 Noise band edge fade, 0.5 R target | the noise band is our best in-sample family; these are the high-win-rate versions |
| 92 NQ-ES agree | agreement worked before (`bimb930`); two rules, two markets we have |
| 1 / 3 Range budget | the real idea behind the LSTM paper, with no model needed |

Each goes through the blueprint as usual: card (exits hm40), code check, then the owner's word for the heat map.
