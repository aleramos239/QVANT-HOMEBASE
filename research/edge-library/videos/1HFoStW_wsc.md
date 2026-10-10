## 1. SOURCE
Title: Ultimate VWAP Strategy for Day Trading (Institutional Grade) | Channel: The Secret Mindset | 21 min | uploaded 2025-11-22
URL: https://youtu.be/1HFoStW_wsc
Read: the full auto-captions (2026-10-09). Stocks in the examples.
Gist: a tour of VWAP uses; many claims, few rules.
## 2. EVERY IDEA AND STRATEGY
1. Three VWAPs [2:00-5:00, 15:00-17:00]: daily, weekly, monthly (also quarterly, yearly). All stacked one way with price beyond all three = trade only that way; the longer one wins a disagreement. Size down when far from the monthly line.
2. Slope [3:50-4:20]: flat = balance (fade), steep = trend.
3. VWAP from an event [5:20-7:20]: earnings, central-bank days.
4. Bands [7:30-9:30]: +/-2 = fade back to the VWAP; +/-3 = extreme; bands squeezing = a move is coming; price riding the +/-1 band = trend, do not fade.
5. Touch reading [9:40-11:20]: a long wick = defended; a break that snaps back within a few candles = a trap; more than three candles beyond = accepted.
6. By market type [11:20-13:30]: trend = pullbacks to a sloping VWAP; range = fade to it; thin volume and gap days = it stops working.
7. A checklist of five items [19:00-20:00].
## 3. NEAREST PIPELINE FIT
- 4: `vwap_band` (on file; nq_vwap_band_pm added 2026-10-09). 5: `vwap_flip` with hold 1 / 2 / 3 (nq_vwap_flip on file; added nq_vwap_flip_mid). 6: `vwap_trend_pull`, `vwap_z` (on file).
- No entry rule for: weekly / monthly / event VWAPs, band squeeze, the stack as a side switch.
## 4. CLAIMED RESULTS
- None. The "68 / 95 / 99.7 %" figures are the normal curve's, not measured on prices.
## 8. VERDICT
- A word list for VWAP. One thing would be new to build: the weekly VWAP as a level.
