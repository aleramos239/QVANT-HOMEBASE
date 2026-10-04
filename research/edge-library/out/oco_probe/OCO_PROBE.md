# OCO cancel delay probe (2026-10-04) — information only, no verdict changed

Question: the engine cancels the other side of a bracket the instant one side fills. Live the cancel takes time, so both sides can fill. Does that turn the members into losers? **Answer on BUILD and 2024: no. It is rare and small.**
Method: new engine setting `oco_cancel_ms`. The other entry stays working that many ms after the first fill. If it triggers in that window it fills by the normal stop rule and opens a second position with its own stop and target (a "double fill").
Dollars are for 1 contract. "pairs" = net of both legs of the double fills. "(chg)" = total net minus the 0 ms total. Share = double fills / brackets that filled.

| member (central cell) | delay ms | BUILD entries | double fills (share) | pairs | total net (chg) | 2024 entries | double fills (share) | pairs | total net (chg) |
|---|---|---|---|---|---|---|---|---|---|
| orb_NQ_tf1_pre | 0 | 567 | 0 | 0 | 16,362 | 252 | 0 | 0 | 12,437 |
| | 25 | 568 | 1 (0.2 %) | +137 | 16,673 (+311) | 253 | 1 (0.4 %) | -13 | 12,098 (-339) |
| | 50 | 568 | 1 (0.2 %) | +137 | 16,673 (+311) | 253 | 1 (0.4 %) | -13 | 12,098 (-339) |
| | 100 | 570 | 3 (0.5 %) | +786 | 17,255 (+893) | 255 | 3 (1.2 %) | -319 | 12,505 (+68) |
| | 250 | 570 | 3 (0.5 %) | +786 | 17,255 (+893) | 257 | 5 (2.0 %) | +330 | 13,042 (+605) |
| straddle_tight_0830_GC evA | 0 | 223 | 0 | 0 | 10,598 | 96 | 0 | 0 | 5,496 |
| | 25 | 223 | 0 | 0 | 10,598 (0) | 96 | 0 | 0 | 5,496 (0) |
| | 50 | 224 | 1 (0.4 %) | -18 | 10,754 (+156) | 97 | 1 (1.0 %) | +312 | 5,652 (+156) |
| | 100 | 225 | 2 (0.9 %) | -36 | 10,910 (+312) | 98 | 2 (2.1 %) | -186 | 5,398 (-98) |
| | 250 | 226 | 3 (1.4 %) | -84 | 11,066 (+468) | 99 | 3 (3.1 %) | -204 | 5,554 (+58) |
| straddle_tight_0830_NQ evB | 0 | 157 | 0 | 0 | 9,047 | 68 | 0 | 0 | 2,383 |
| | 25 | 159 | 2 (1.3 %) | -1,516 | 8,344 (-703) | 69 | 1 (1.5 %) | +132 | 2,219 (-164) |
| | 50 | 160 | 3 (1.9 %) | -1,809 | 8,185 (-862) | 69 | 1 (1.5 %) | +132 | 2,219 (-164) |
| | 100 | 163 | 6 (3.8 %) | -1,678 | 8,248 (-799) | 70 | 2 (2.9 %) | +319 | 2,515 (+132) |
| | 250 | 164 | 7 (4.5 %) | -2,001 | 8,044 (-1,003) | 73 | 5 (7.3 %) | -770 | 1,528 (-855) |
| straddle_tight_1000_GC evC | 0 | 97 | 0 | 0 | 8,202 | 46 | 0 | 0 | 4,166 |
| | 25 | 97 | 0 | 0 | 8,202 (0) | 46 | 0 | 0 | 4,166 (0) |
| | 50 | 98 | 1 (1.0 %) | -78 | 7,968 (-234) | 46 | 0 | 0 | 4,166 (0) |
| | 100 | 98 | 1 (1.0 %) | -78 | 7,968 (-234) | 47 | 1 (2.2 %) | -348 | 3,992 (-174) |
| | 250 | 98 | 1 (1.0 %) | -78 | 7,968 (-234) | 49 | 3 (6.5 %) | -404 | 4,304 (+138) |

No member turns negative at any delay, on BUILD or on 2024. The biggest hit is NQ 08:30 (evB): -$1,003 of $9,047 on BUILD and -$855 of $2,383 on 2024 at 250 ms.
Why a total can go UP: the first leg loses the same with or without the delay. The change is only the late leg, a fresh trade in the new direction that wins about as often as it loses.
Distance between the two entry orders: orb median 12.0 pts ($240), p10 7.0 ($140), p90 23.25 ($465) over 819 brackets. Gold 08:30 and gold 10:00: always 1.2 pts ($120). NQ 08:30: always 10 pts ($200).
Worst single double fill (both legs): orb -$413 (2024-10-03), gold 08:30 -$498 (2024-09-11), NQ 08:30 -$918 (2023-01-12: the two fills 1 ms and 25 points apart), gold 10:00 -$348 (2024-10-01). Every pair is in `double_fills.csv`.

Limits (read before trusting it):
- Few events (0 to 7 per cell): the counts are solid, the dollar sums are noisy. Delays above 250 ms were not run. 2025+ was never read.
- The late leg fills on its trigger print + 1 tick: the same kind fill the earlier fill probe showed the three event members live on. That fill risk stays the big one.
- It assumes the broker keeps all four exit orders working. If the platform instead closes everything at the second fill (loss = distance between the two fills + 2 commissions), plain arithmetic on the same pairs at 250 ms changes the totals by: orb -$672 BUILD / -$1,540 2024, gold 08:30 +$48 / -$282, NQ 08:30 -$938 / -$1,505, gold 10:00 -$304 / +$88. Still none negative. (Arithmetic, not an engine run.)
Checks: 0 ms gives the stored member trades field by field (8 of 8 member-periods). An own recount on the raw tape gives the engine's double-fill count in all 32 delay cells. No session was dropped.
Files here: `oco_probe.py` (run / gaps / report), `oco_probe.json`, `gaps.json`, `double_fills.csv`, `runs/`, `pick_reads.csv` (24 reads of 2024), `run.log`. Ledger: 40 `member` run rows, 0 candidate cells.
