## 1. SOURCE
Title: My $1,300,000 Trading Strategy (Explained in 10 Minutes) | Channel: JJ Simon | 10 min | uploaded 2026-06-01
URL: https://youtu.be/UVKVSWKFlvo
Read: the full auto-captions (2026-10-09). Five NQ mornings of one week walked through.
Gist: the last price before 09:30 is "fair price". First ride the opening burst away from it, then trade back to it. Done at 11:00.
## 2. EVERY IDEA AND STRATEGY
1. Opening continuation [1:00-2:30, 5:00-5:40]: in the first 10-15 minutes go with the opening 1-minute candle(s). Stop 25 / target 38 pts; if the candle is over 25 pts, half size with 50 / 76. Always 1 : 1.5 because the eval is -2,000 / +3,000.
2. Reversion [2:30-3:30, 5:40-7:40]: after the burst, the first 1-minute "break of structure" back toward the pre-open price = entry, 25 / 38, re-enter on the next one after a loss. Often runs 100+ pts to the pre-open price.
3. News at 08:30 [3:50-4:50]: the same two trades around the pre-news price; move to breakeven before 09:30.
4. Holiday [8:00-8:50]: trade only if the 09:30 candle shows a volume burst; smaller target.
5. Stop at 11:00.
## 3. NEAREST PIPELINE FIT
- 1: `first_bar_mom` nyam (nq_first_bar on file). 2: `open_fade`, which is this rule (reference = the 09:29 close, to 11:00, max 3 trades): nq_open_fade and nq_open_fade_far on file. 3: nq_0830_straddle on file.
- The table has 25 pts x 1.5 nearly (20 / 30 pts x 1 or 2), not 25 / 38 exactly.
## 4. CLAIMED RESULTS
- $1.3 million from prop firms in 12 months (proof said to be in another video). One week shown: mostly winners, two losses.
## 8. VERDICT
- Nothing new to run: both trades are on file and both stopped at the raw heat map (nq_open_fade 12.5 % of boxes profitable).
