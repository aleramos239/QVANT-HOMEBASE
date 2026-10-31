# 100 ideas for the 6pm-12am ET (Asia) window (2026-10-29) -- untested

NQ, 5m unless stated, entries 18:00-23:00, flat 23:55, hm40 exits, 3:1 in-sample only. Nothing here was run.

Why this list looks the way it does: this window is the most mined one on file (about 90 ideas / 8,000 boxes in the 2026-10-25 /goal, none approved;
FVG, EMA/VWAP pullback, hourly candles, candle sweep/break + flow gates, window ORBs, gap follow, noise band, drift, time-of-day scans all dead).
Multi-trade 5m rules lose to the $12 round trip. The only things that stayed alive: huge displacement (k >= 2.5, rare), the 18:00 candle follow
(flat), the SMA50 up-trend gate (t ~1.6, 2025-26 bull beta). So these ideas use different information (the Asia clocks, the RTH day just ended,
other markets, the calendar) and aim at 0-2 trades a night. (~) = close to something already tried. (d) = needs other-market data or a dates list, not checked.

## A. Asia market clocks (Tokyo 19:00, Hong Kong/Shanghai 21:30, Tokyo lunch 22:30-23:30)
1. 19:00 Tokyo open: follow the first 5m candle's colour at 19:05
2. 19:00 opening range 15 min: follow the first break
3. 19:00 opening range 15 min: fade the first break
4. 19:00 candle sweeps the 18:00-19:00 high/low and closes back inside: fade
5. 21:30 Hong Kong/Shanghai open: follow the first 5m candle
6. 21:30 opening range 15 min: follow the first break
7. 21:30 opening range 15 min: fade the first break
8. 21:30 candle >= 2.5x the evening's average 5m range: follow it (the displacement idea at the China open)
9. Tokyo lunch lull 22:30-23:30: fade the break of the 21:30-22:30 range
10. 20:00: follow the break of the 19:00-20:00 range
11. Sunday night only: follow the 18:00 candle
12. Sunday night only: weekend gap >= 0.3 ATR, fade to the Friday close
13. Monday-Thursday nights only: follow the 18:00 candle (Sunday left out)
14. Sunday night: always long 18:00 -> 23:55

## B. The RTH day that just ended (one trade a night)
15. RTH closed in its top 10 %: long 18:00 -> 23:55
16. RTH closed in its bottom 10 %: short 18:00 -> 23:55
17. Same two, faded
18. Last RTH hour (15:00-16:00) up >= 0.5 ATR: long the evening
19. Last RTH hour down >= 0.5 ATR: short the evening
20. Same two, faded
21. Quiet RTH (range < 0.6 of its 10-day mean): follow the break of the 18:00-19:00 range
22. Wide RTH (range >= 1.5x its 10-day mean): fade the evening's first 30-minute move
23. RTH made a new 20-day high: long the evening
24. RTH made a new 20-day low: buy the bounce
25. RTH was an inside day: follow the evening break of its high/low
26. Evening returns to the 16:00 RTH close after moving >= 0.5 ATR away: limit bounce
27. First touch of the RTH high/low in the evening: continue
28. First touch of the RTH high/low in the evening: fade
29. First touch of the RTH final VWAP: bounce
30. Gap day (RTH opened outside the prior range and closed there): follow in the evening

## C. The 18:00 anchor
31. Limit at the 18:00 open after price moved >= 0.5 ATR away
32. VWAP anchored at 18:00: first cross, follow
33. After 30 min above both the 18:00 open and its VWAP: long (below both: short)
34. 18:00-18:30 range: first break
35. 18:00 15m candle range: first break
36. 17:00->18:00 gap and the 18:00 candle disagree: trade the candle
37. 18:00 candle >= 1 ATR: fade at its close, target its open
38. 18:00 candle >= 1 ATR: limit at its 50 % in its direction
39. First 5m close back across the 18:00 open after 19:00
40. 18:00-19:00 range swept in 19:00-20:00 and reclaimed: fade the sweep

## D. Candles and limits (the siblings of the 15m FVG limit and the candle break)
41. 15m FVG limit on the 18:00-open side, stop = middle candle's far end (the RTH rule; the 5m FVG touch lost 115/120)
42. 15m FVG limit, gaps >= 1 ATR only
43. 1h FVG limit
44. Previous 15m candle break on the 18:00-open side, stop = its other end
45. Same, only after a candle whose range < 0.5 of the average
46. Outside 15m bar: follow
47. Failed 15m candle break: fade
48. Pin bar (15m) at an evening high/low: trade the other way
49. Order block: limit at the open of the last opposite candle before a >= 2.5 ATR displacement
50. Three same-colour 15m candles: fade
51. Three same-colour 15m candles: follow
52. Doji at an evening extreme: break of either side

## E. The three things that stayed alive, tweaked
53. Evening noise band k 0.3 (on the VPS shadow): first signal of the night only
54. Same, long only in an up-trend (RTH close > SMA50), short only in a down-trend
55. Same on 15m bars
56. Huge displacement follow (k >= 3): first of the night only
57. Huge displacement k >= 3: limit at 50 % of the candle instead of market
58. Huge displacement k >= 3 on 1m bars
59. 18:00 candle follow with a 60-minute time stop instead of 23:55
60. 18:00 candle follow only when its body >= 0.5 ATR

## F. Other markets as the signal (d)
61. Yen (6J) candle >= 2x its average range: NQ goes the opposite way on the next candle
62. Yen quiet (< 0.5 of average range) in the first hour: take NQ's 18:00-19:00 range break
63. ES breaks its 18:00-19:00 high/low before NQ does: NQ follows
64. YM, ES and RTY all agree with NQ's 18:00 candle: follow; disagree: no trade
65. 10-year (ZN) first-hour move sets NQ's side (both signs tested)
66. Gold up >= 1 ATR in the first 90 min: short NQ
67. Crude (CL) first-hour move sets NQ's side
68. Euro (6E) first-hour move sets NQ's side
69. Aussie dollar (6A) up in the first hour: long NQ
70. ES and NQ opened with different gaps at 18:00: trade the bigger gap's side

## G. Levels
71. 100-point level touched: bounce, stop 15 pts
72. 50-point level broken: limit retest
73. Round-number break held by a 5m close beyond it: follow
74. First new evening-session high after 20:00: continue
75. First new evening-session low after 20:00: continue
76. New evening high at 22:00 or later fails (closes back inside): fade
77. Double top/bottom within 3 pts (two failed tries): trade the failure
78. Triple tap at a level: trade the break
79. Prior-day POC / VAH / VAL first touch in the evening
80. Weekly open touched in the evening (Sunday-Monday)
81. Hour-open retest at 19, 20, 21, 22, 23: limit at the hour open after a >= 0.5 ATR move away
82. Close outside the 2-sigma VWAP band (from 18:00): fade to VWAP (~ Bollinger fades lost)

## H. Compression and expansion
83. Evening range < 0.4 ATR by 20:30: follow the break of the 18:00-20:30 range
84. Narrowest 30m bar of the evening so far: break of it
85. Inside 30m bar: break of it
86. First 5m bar >= 3x the evening's average range: follow (~)
87. Volume spike (>= 3x the 20-bar average): fade at its close
88. Quiet volume (below the 20th percentile of the hour): fade to VWAP
89. Large print (>= 25 lots) against the move: fade it (~ big-print follow lost)
90. Tonight's first-hour range >= last night's: follow the break of it

## I. Calendar and events (d)
91. Bank of Japan decision night: fade the announcement candle
92. Australian data (19:30): follow the first 5m candle
93. China data (21:30): follow the first 5m candle
94. Mega-cap earnings after the close (NVDA, AAPL, MSFT, AMZN, GOOG, META, TSLA): follow the 18:00 gap on report nights
95. FOMC day: follow the 14:00 move into the evening
96. Last trading day of the month: long 18:00 -> 23:55
97. First trading day of the month, evening: long
98. Night before a US holiday: long
99. Quarterly-expiry Thursday evening: fade the first hour
100. Night before CPI / NFP / FOMC: fade the evening's first 30-minute move

Cheapest to build with what exists (no new data, one trade a night): 1, 2, 5, 6, 11, 13, 15-20, 31, 32, 53, 54, 56, 59.
