## 1. SOURCE
Title: The Only VWAP Strategy I Use Every Day (15 Years of Trading) | Channel: Trader Drysdale | 16 min | uploaded 2026-06-13
URL: https://youtu.be/Z2uJRbkb2pA
Read: the full auto-captions (2026-10-09).
Gist: on a range day, fade the edge of the session VWAP's one-standard-deviation band back to the VWAP. ES / NQ micros.
## 2. EVERY IDEA AND STRATEGY
1. The setup [4:00-5:40]: price is INSIDE the +/-1 band and rotating. It touches a band and rejects (a wick, a close back inside). Enter against the touch; stop a few points beyond the wick (8 pts on ES in his example); target the VWAP (10-16 ES pts) = 1 : 1 to 2 : 1.
2. When not [9:00-10:30]: price outside the band and holding there (a trend day); a touch without a rejection; the first 15 minutes; after two losses in a row.
3. More rules [6:40-9:00, 12:40-13:20]: one setup a day while learning; no trades 30 minutes around big news; risk 1-2 % a trade; close a trade that has not reached the VWAP in 60 minutes.
## 3. NEAREST PIPELINE FIT
- `vwap_band` with band about 1 (a close back inside the band after a close outside -> fade): NEW cards 2026-10-09 with band 0.75 / 1.0 / 1.25: nq_vwap_va_fade_nyam, nq_vwap_va_fade_mid, nq_vwap_va_fade_pm, es_vwap_va_fade_mid.
- Not in it: the target at the VWAP (the table's targets are multiples of the stop), the 60-minute time stop, the two-loss stop.
## 4. CLAIMED RESULTS
- "70-80 % reach the VWAP on a range day, 20-30 % on a trend day": stated, no data. Five journal examples, two of them losses.
## 8. VERDICT
- Clear enough to run and not yet tried at one band. Our wider fades (1.5-2.5) stopped at the raw heat map, so expectations are low.
