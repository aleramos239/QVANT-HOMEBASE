## 1. SOURCE
Title: Everything You Need to Know About ORB and How I Use It - Webinar | Channel: Max Options Trading | 57 min | uploaded 2025-10-22
URL: https://youtu.be/SunW-hRFGzY
Read: the full auto-captions (2026-10-09). A sponsored summit talk (Apex, a charting platform).
Gist: his base method: the first 15-minute candle of the session, its high, low and middle; wait for a 15-minute close outside, then enter on 1-2 minute bars.
## 2. EVERY IDEA AND STRATEGY
1. The range [9:00-13:30]: high and low of the 09:30-09:45 candle, wicks included, plus the middle line. No pre-market bias at all.
2. The break [22:00-27:30]: a 15-minute close outside the range, then on the 1-2 minute chart a continuation bar ("print through") with lower highs behind it = entry. Stop at the range edge (14 pts in his example) or behind the last swing (30 pts).
3. Other opens [28:00-30:30]: the same range at 18:00 ET (Globex open), the Asia open 20:00-21:00 ET and London 03:00 ET; also gold and single stocks.
4. Failed break [31:00-33:30]: a break that fails and closes back inside is traded to the middle line and the other edge.
5. Chop [20:30-22:30]: inside a range buy the bottom, sell the top.
6. Size by the trade [15:30-18:30]: bigger when the stop is small against the room to the target, smaller when it is not. Size, risk and emotion are one dial.
7. One good trade and log off; no daily profit target.
## 3. NEAREST PIPELINE FIT
- 2: `orb_confirm` or_min 15 / 30 / 60 (NQ and ES cards on file; added gc_or_long, gc_or_short on 2026-10-09).
- 3: `orb` at other session starts: nq_orb_london, nq_orb_asia on file (asia here = 00:00 ET, not Tokyo's open); added nq_orb_eve (18:00 ET).
- 4, 5: `ib_n` fade (nq_ib_fade_nyam, nq_ib_fade_mid on file; added nq_ib_fade_pm, es_ib_fade_mid).
- No entry rule for: the middle line, sizing by the trade, a 20:00 ET range.
## 4. CLAIMED RESULTS
- "Almost half a million" across 20+ funded accounts in 12 trading days; the host says he checked $375,000. Win rates 82-92 % on screen. Five hand-picked chart days.
## 8. VERDICT
- Already the most-tested idea here: orb_confirm near misses nq_or_mid_long and nq_pm_follow_long stopped at the proof. New from this video: the evening open and gold.
