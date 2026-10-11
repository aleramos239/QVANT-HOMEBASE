# Rule sheet: Bruni's "low-effort" value-area break (video `nlLGlVJGrtw`, IQCapital, 103 min)

Written 2026-10-11, sheet `taught/bruni_va_break.json`, family `va_break` (`engine/families/vabreak.py`), tests `engine/tests/test_vabreak.py`.
Notes: `videos/nlLGlVJGrtw.md`. The owner said "add what we need, test on 5 and 15 minutes": run on the build days only, as taught, untuned.

## 1. Taught (time marks in the sheet)
| # | Part | The video says |
|---|---|---|
| T1 | Bars | 15-minute, "you don't switch time frame" (5 minutes is NOT his) |
| T2 | Day | developing session value area higher than the previous session's: a trending long market |
| T3 | Setup | price comes back into the previous session's value area (a touch is enough) |
| T4 | Break | a candle closes at least 6 NQ points above the previous session's value-area high |
| T5 | Engulf | it takes out the previous candle's high; its size does not matter |
| T6 | Low effort | volume under the 20 average, or falling vs the candle before; either |
| T7 | Entry / stop / target | at that close; stop at the candle's low; 1:2 (1:1 to 1:5 tried) |
| T8 | Continuation | same engulf + low effort, again and again, until the market structure high; none without the break trade |
| T9 | Invalid | price under the market structure low (the closest valid candle before the breakout) kills it |
| T10 | News | no trade with NFP / CPI at the trigger |
| T11 | Size | 0-5 setup score: half Kelly at 5, a quarter at 4, less below |

## 2. Pick (not in the video; yours to change)
| # | Gap | Pick |
|---|---|---|
| P1 | Which value area | the library's 70 % value area of the prior date's 09:30-16:00 prints (as `va_reclaim`) |
| P2 | "Developing value area higher" | the middle of today's developing 70 % area (1-minute closes weighted by volume, from 09:30) above the middle of yesterday's |
| P3 | "Comes back into the value area" | the bar that breaks must close under VAH + 6 on the bar before it (it breaks from under) |
| P4 | 20 average | EMA(20) of the tf-bar volumes of the day from 00:00 ET |
| P5 | Structure high | the RTH day high before the trigger bar; the target is cut to it when it is nearer |
| P6 | Structure low | the low of the nearest valid down candle (body > its longer wick) at or before the bar of that high; a bar under it, the trigger bar included, kills the setup |
| P7 | Cap | the video gives none: 10 a day, the structure high ends the leg; one position at a time |
| P8 | Window | 09:30 to 15:58 ET, entries from the second RTH bar to 5 minutes before the end |
| P9 | Buffer | 6 points as taught, never scaled to the bar size (at 5 minutes it is a larger part of the bar's ATR) |
| P10 | Side | long only (shown); the family trades the mirror through VAL, not run |

## 3. Would run (the taught lane, `bp.py taught`)
- NQ, 5 and 15-minute bars, one taught cell + 2 neighbours (target 1.5R / 2R / 2.5R), structure stop. Build days 2021-09-22 to 2025-06-30.
- Control: the pipeline's random entries at the same exits and passes (both sides, and long only). The random control does not know the structure cut or the structure kill.
- Reads: metrics per year then combined, prop odds on the PLAIN row (stress beside it), lines P3.2-P3.10, the lock's 3.3-3.8, reshuffled runs, random line.

## 4. Not run
News-day skip, the 0-5 score and size, the loss-streak rule, ATR percentile / regime age, the test days.
One note: the lane's generic text for a one-instance family says "entries 10:30-15:30"; this family's window is 09:30-15:58 (the lane note is conti's).
