# Video notes: BLvsYJ4sqn8 - NQ evening "fair price" (18:00 and 20:00 sessions)
Title: "The ONE Setup That Made Me $400,000 in 90 Days (6 & 8PM Session, Step by Step)" | https://www.youtube.com/watch?v=BLvsYJ4sqn8 | 30:34 | captions: auto, read in full
Same trader as UVKVSWKFlvo. Claim: $400,000 of payouts in 90 days. Evidence: one month replayed by eye, he says it is too small and his real win rate is lower.
## Rule (NQ, 1-minute chart, 18:00 to 21:30 ET)
Fair price = the 18:00 open (the market is shut 17:00-18:00).
- 18:00: ONE trade with the opening candle, in the first 5 minutes (green buy, red sell). Skip it if it runs away from an unfilled gap or against the morning's direction.
  Then fade back to the 18:00 price when price is 30+ points away and a strong candle (body bigger than the last body, closes past its wick; better, a break of structure) points back.
- 20:00 (Asia open): same pair. If the 20:00 move goes toward 18:00, 18:00 stays fair ("best setup"); if it goes away, the 20:00 open becomes fair.
- 25 stop / 38 target, 1 to 1.5. Opening move not coming: breakeven. Flat before 20:00. Last fade 21:30 (then only with the trend).
- 15% of days never come back; some weeks do not move at all.
## Where it sits in the library (2026-10-10)
- Session `eve` exists. Continuation = `first_bar_mom` / `orb` on eve (`nq_orb_eve` stopped at stage 1: 10 of 144 boxes at $70).
- Fade to the 18:00 price: no entry rule for it (open_fade is nyam only); nearest is `vwap_z` / `vwap_band` on eve, whose VWAP starts at 18:00.
- NOT in the exit table: target = the fair price; the fair-price switch at 20:00.
