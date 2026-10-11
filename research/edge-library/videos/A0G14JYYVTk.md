# A0G14JYYVTk - "A Hedge Fund Manager Just CRACKED Prop Trading (Live On Chart)" - Matteo Conti
Channel: IQCapital (the prop firm's own channel; ads for its $9 challenge at the end) | https://www.youtube.com/watch?v=A0G14JYYVTk | 1 h 22 | uploaded 2026-10-06 | written from auto-captions (some numbers are garbled; marked)
Gist: Conti (ex-market maker, runs a quant fund) gives THREE rule sets built for passing prop challenges: high win rate, reward smaller than risk, flat before the close. All NQ, coded in MultiCharts, developed on data from 2018, "out of sample" from 2023. He says each alone passes about 40% of challenges, the three together pass faster and more often (about 5 trading days, about 5 micros each), and the three have under 0.25 correlation. Follow-up to the "golden ticket" VWAP pullback video (wm4A6qo0g3I).
## 1. VAULT BREAK [about 6:00-13:00] - NQ, 30-minute bars, LONG ONLY
Reason: markets drift up; a clean push out of the "noise area" plus the day's VWAP shows real buying. He credits academic work (first paper "1987"; the same noise-area idea as Zarattini / Aziz / Barbon and Maroy).
Rule (times are Central; add 1 hour for New York):
1. At 00:00 CT (01:00 ET) record the session open. Noise-up level = open + 30% x the 15-session average of the daily ATR. Fixed for the day (30% was picked in sample as a trade-off between frequency and edge).
2. Entry only 10:00-14:30 CT (11:00-15:30 ET): a bar closes above the noise-up level AND above the session VWAP (VWAP counted from 00:00 CT). Next bar open. Up to 3 trades a session; after a target or stop, the next qualifying close opens another.
3. Exit: target $800, stop $1,500 (1 NQ), else out at 14:30 CT. The target / stop are in dollars, not points.
Shown [about 49:00-52:00]: average trade about $112, "67% winners" (the profit-factor figure is garbled in the captions); equity rising, "new highs" recently. No trade count or period total given.
## 2. VWAP PULLBACK + ADX GATE [22:40-36:00] - NQ, 1-minute bars, LONG ONLY
Reason: institutional VWAP algos trade around the VWAP, so a pullback to it in an up day gets bought.
Rule:
1. Opening range = 08:30-09:00 CT (09:30-10:00 ET). A bar closes above its high = the setup is armed.
2. Price touches the session VWAP, then a 1-minute bar closes back above it.
3. ADX (period not said, standard 14) above 20 and NOT rising versus the bar before. If everything else is true and ADX is rising, wait until it stops rising (or crosses 20, then stops rising).
4. Long at the next bar open. Target = highest high of the last 5 bars; stop = lowest low of the last 20 bars; else flat at 15:55 CT (caption, said twice as "3:55 Central" = 16:55 New York: most likely right, since his session ends 16:00 CT = 17:00 ET, so this is 5 minutes before the close; NOT 15:55 New York). Limit order target, market stop.
Shown: average trade about $121, lower frequency than strategy 1, similar win rate (captions garbled).
## 3. OVERNIGHT-BIAS OPENING RANGE BREAKOUT [36:00-48:00; chart 1:03:30-1:06:30] - NQ, 15-minute bars, LONG AND SHORT
Reason: the overnight session has price discovery; where the cash open lands inside that range says which side has the push.
Rule:
1. Overnight range = 23:00 CT to 08:30 CT (00:00-09:30 ET). At the 08:30 CT open: top third of the range = long bias only; bottom third = short bias only; middle third = no trade that day.
   At the chart [1:04:32] he says the range starts at midnight CT (01:00 ET), and [1:05:10-1:06:00] that the entry waits until after 9:00 or 9:30 CT: neither is on the whiteboard. Rule sheet 7 in `taught/RULE_SHEETS_2026-10-10.md` asks the owner.
2. Opening range = the first 15-minute bar (08:30-08:45 CT). A close beyond it in the bias direction with ADX above 20 (rising or not) = entry at the next bar open. One trade a day. A break the other way first does not cancel it.
3. Stop = 30% x the 15-session average daily ATR (the same level as strategy 1, about 90-100 NQ points lately, so about $1,800-2,000 for 1 NQ). Target = 3 x the stop. Else out at 14:30 CT; most trades end on that clock.
Shown: out of sample since 2023, about 53% winners, profit factor about 1.4, short side about 50% winners with 1.6; about $200,000 net on 1 NQ over the whole sample (period not said), $88,000 of it from 53 outlier trades; trades rarely, so alone it would let many challenges time out. He says it suits FUNDED accounts, the other two the evaluation.
## 4. PORTFOLIO AND RULES OF THUMB [30:00-45:00, 53:00-1:15:00]
- Three low-correlation strategies together raise the pass rate; each alone about 40%.
- Size: about 5 micros each; average time to pass about 5 trading days (his claim, rules of his own prop firm, not Lucid).
- BENCH RULE: run a Monte Carlo of the strategy's drawdown; when the live drawdown is past the 75th percentile, stop it; bring it back only after a new equity high. Two failed challenges in a row = investigate. "Losing streaks cluster."
- Execute by code, never by hand; the rule sets have too many moving parts.
## 5. DATA NEEDED
NQ 1-, 15- and 30-minute bars with volume (session VWAP from 00:00 CT = 01:00 ET), daily ATR, ADX. All on disk.
## 6. FITS THE TESTER
| Strategy | Fits | What is missing |
|---|---|---|
| 1 Vault break | NO as said, PARTLY with one new entry rule | A `noise_band` entry: a close above (session open + k x 15-day mean daily range) and above VWAP, session from 01:00 ET, entries 11:00-15:30 ET. The standard table has no $800 / $1,500 exits (NQ fixed stops stop at 45 points = $900; his $1,500 = 75 points). The owner has allowed wide NQ stops outside the table once (2026-10-07 straddle) |
| 2 VWAP + ADX | NO | An entry rule (armed by the opening-range break, VWAP touch and re-close, ADX gate) AND a structure exit (5-bar high / 20-bar low), which the toolkit lacks. `adx strong` is 25 and ignores "not rising" |
| 3 Overnight bias ORB | PARTLY | `orb_confirm` (or_min 15, both sides, one trade a day) plus a day filter `onr_third` = the 09:30 open in the top / middle / bottom third of the 00:00-09:30 ET range (long only on top, short only on bottom, none in the middle). Stop 0.3 x daily ATR is not in the table (the table has 1.5 and 3 x the bars' own ATR14, and fixed points) |
Repeats: strategy 1 = the noise-boundary momentum of Zarattini / Aziz / Barbon and Maroy (2025), already on the "to build" list as `noise_band`; strategy 2 = the 2026-10-03 batch VWAP drift pullback (wm4A6qo0g3I) with an ADX gate; the "high win rate, small target" shape was already noted from Conti. Two independent sources now point at the noise-area entry.
## 7. CAUTIONS
- Sponsored by his prop firm; the $9 challenge is advertised at the end. The pass rates are for IQ Capital's rules, not LucidPro's.
- Parameters (30%, 3 trades, $800 / $1,500, ADX 20, times) were picked in sample from 2018; the "out of sample" is 2023 on, and strategy 1 / 2 results are shown only as equity pictures and one average trade.
- Our own run today: `nq_vwap_pullback` (the earlier VWAP pullback) and every opening-range idea failed at stage 1 with $3 to $38 an average trade. These three differ by the filters (noise level, overnight third, ADX), which is what to test.
## 8. ON-SCREEN NUMBERS (read from the frames 2026-10-10; MultiCharts reports, 1 NQ, costs not shown)
| | 1 Vault break | 2 VWAP + ADX | 3 Overnight-bias ORB |
|---|---|---|---|
| Seen at | 57:38 | 1:01:28 | 1:13:35, 1:15:55 |
| Bars | 30 min | 1 min | 15 min |
| Report period | 2022-01-21 to 2026-09-24 | 2022-01-06 to 2026-09-24 | 2022-01-24 to 2026-09-24 |
| Trades (long / short) | 1,151 / 0 | 576 / 0 | 236 / 198 |
| Winners | 67.68 % | 67.71 % | 53.69 % (long 56.78, short 50.00) |
| Average trade | $112.48 | $144.77 | $455.92 (long $453, short $459) |
| Average win / loss | $740 / $1,205 | $658 / $936 | $2,210 / $1,577 |
| Win size : loss size | 0.61 | 0.70 | 1.40 (this is the "1.4" he says, not the profit factor) |
| Biggest win / loss | $800 / $1,500 | $5,550 / $5,570 | $8,715 / $5,415 |
| Net | about $129,000 (trades x average; not shown) | about $83,000 (same) | $197,870 shown |
| Profit factor | not shown | not shown | 1.62 |
| Worst drawdown | not shown | not shown | $19,510 |
| Outlier trades | 0 | 79 trades, $3,360 | 53 trades, $88,605 (45 % of the net) |
| Losers in a row, worst | 6 ($7,965) | 5 ($8,250) | 6 ($11,850) |
| Trades a year | about 245 | about 122 | about 93 |
- All three reports START IN JANUARY 2022. He says "developed from 2018, out of sample from 2023", so about one year of each report is build data by his own words.
- Strategy 3 is in the market 3.56 % of the time; Sharpe 0.46 on the report.
- Strategy 1 equity curve [56:46] runs from $100,000 to above $200,000 with a flat stretch from late 2023 to late 2024.
## 9. WHAT WE DID WITH IT (state 2026-10-10)
- Strategy 1 -> family `noise_band` (built). 18 ideas run. ONE is in the book: `nq_noise_gx_mid_long` (NQ, 1-minute bars, midday, long): 263 trades, average trade $149, profit factor 1.37, net $39,183, worst drawdown $11,816. The others stop: afternoon and morning versions fail on the unseen days or without their best 5 % of trades; shorts, ES and gold fail the first heat map.
- Strategy 2 -> AS TAUGHT 2026-10-11 (family `vwap_adx`, sheet `taught/conti_vwap_adx.json`, build days): 442 trades, 74.2 % winners, average trade -$4, profit factor 0.98; 2 of 11 lines. Fails. From his chart [59:35]: the VWAP starts at 09:30 New York; target and stop are fixed at the entry.
- Strategy 1 -> AS TAUGHT 2026-10-11 (family `vault_break`, sheet `taught/conti_vault_break.json`, build days): 766 trades, 66.8 % winners, average trade $85, profit factor 1.21, average win $717 / loss $1,190 (his $740 / $1,205); 11 of 11 lines; eval odds 35 % in 30 days.
- Strategy 3 -> AS TAUGHT 2026-10-10 (family `onr_orb`, two sheets): 380 / 358 trades, average trade $409 / $484, profit factor 1.54 / 1.76; on the Desk as "NQ OVERNIGHT ORB (micro)", OFF.
