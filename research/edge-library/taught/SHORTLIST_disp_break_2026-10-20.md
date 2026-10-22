# Shortlist: candle break + body multiple (owner, 2026-10-20)

The owner's rule: a candle closes beyond the previous candle's wick (above its high = long, below its low = short) AND its body is at least
N x the previous candle's body. Enter at the close, stop at the breaking candle's far extreme (floored at 0.25 x ATR14), no daily cap
(20 a session), one position at a time, flat 15:58 ET, 1 contract, $4 a round turn + 1 tick of slippage. Family `candle_sweep`, mode `break`, `body_x` N.

The owner keeps these three to test later out-of-sample, together, to see which are real and which are overfit.
All numbers below are IN-SAMPLE: the 3-month pick windows of the 3:1 block walk-forward (2021-10 .. 2026-08, about 945 session days).

## 1. NQ 15-minute, NY morning (09:30-11:00), 2x body

Sheets: `owner_disp_break_body2x_15_nyam` (targets 0.75 / 1 / 1.25) and `_r0p5` (0.375 / 0.5 / 0.625). Not run yet as their own sheets.
The numbers are the NY-morning slice of `owner_disp_break_body2x_15_allday` (+ `_r0p5`): the passes run independently, so the trades are the same.

| Target | Win | Realized RR | PF | Sharpe | Avg trade | Net | Trades | Per week |
|---|---|---|---|---|---|---|---|---|
| 1:0.5 | 68.9% | 0.49 | 1.09 | 0.66 | $48 | $58,366 | 1,206 | 6.4 |
| 1:0.75 | 59.8% | 0.73 | 1.08 | 0.61 | $56 | $64,834 | 1,154 | 6.1 |
| 1:1 | 54.5% | 0.98 | 1.18 | 1.21 | $133 | $147,114 | 1,104 | 5.8 |
| 1:1.25 | 49.9% | 1.19 | 1.19 | 1.23 | $149 | $159,472 | 1,067 | 5.6 |

Caveat: NY morning was picked after seeing the all-day session table.

## 2. GC 15-minute, NY morning, 3x body

Sheets: `owner_disp_break_body3x_15_4s_gc` (+ `_r0p5`), the NY-morning pass (the sheets also hold eve, asia, london).

| Target | Win | Realized RR | PF | Sharpe | Avg trade | Net | Trades | Per week |
|---|---|---|---|---|---|---|---|---|
| 1:0.5 | 64.5% | 0.61 | 1.10 | 0.51 | $30 | $24,160 | 800 | 4.2 |
| 1:0.75 | 55.4% | 0.88 | 1.09 | 0.44 | $33 | $25,298 | 778 | 4.1 |
| 1:1 | 49.6% | 1.19 | 1.17 | 0.78 | $67 | $51,444 | 764 | 4.0 |
| 1:1.25 | 46.4% | 1.29 | 1.12 | 0.58 | $52 | $38,962 | 752 | 4.0 |

Below GC's $140 floor at every target.

## 3. NQ 5-minute, NY morning, 1.5x body, 1:1.5

Sheet: `owner_disp_break_body1p5x_5_nyam_r1p5` (targets 1.125 / 1.5 / 1.875).

| Target | Win | Realized RR | PF | Sharpe | Avg trade | Net | Trades | Per week |
|---|---|---|---|---|---|---|---|---|
| 1:1.125 | 48.2% | 1.08 | 1.01 | 0.12 | $5 | $14,794 | 2,724 | 14.4 |
| 1:1.5 | 42.5% | 1.44 | 1.06 | 0.67 | $39 | $92,970 | 2,395 | 12.6 |
| 1:1.875 | 37.4% | 1.76 | 1.05 | 0.50 | $34 | $74,462 | 2,172 | 11.5 |

Below NQ's $70 floor.

## Out-of-sample: already on file, read once

`bp.py taught wf` ran on every sheet above (and claimed it: `~/.homebase/taught/<name>/wf/claim.json`), so their test months are no longer
blind for these rules. The out-of-sample result of each is stored in `~/.homebase/taught/<name>/wf/result.json` and was NOT shown to the owner.
"Run them OOS" = show those stored results; never re-run, never re-tune after seeing them.
The NQ 15-minute NY-only sheets (#1) have no walk-forward of their own; theirs is the NY-morning part of the all-day sheet's.

## 4. NQ 1-minute ORB + ATR displacement (owner, 2026-10-21) -- app draft `draft_nq_disp_orb_lab`

Range 09:30-09:45; after 09:45 a 1-minute candle closing beyond the range AND beyond the previous 1-minute candle, body >= k x ATR(14)
(optional: volume >= v x the 20-candle mean); stop at its other end, target rr x the stop; entries to 15:00. In-sample = the 3:1 block
in-sample days (883, 2021-10 .. 2026-04). App walk-forwards 20261021-143905-...-d206 (ATR), -4e5d (ATR x volume); test months stored, not shown.

| Version | Edge | Avg | Net | Trades | /week | Sharpe | Years |
|---|---|---|---|---|---|---|---|
| ATR 2x, 1:2 | +4.5 | $91 | $64,192 | 702 | 4.0 | 0.98 | 2022-26 all + except 2024 (-$1k) |
| ATR 2x + volume 3x, 1:2 | +8.8 | $192 | $66,219 | 344 | 1.9 | 1.18 | 2022-26 all + |
| ATR 1.5x + volume 3x, 1:2 | +6.8 | $124 | $65,928 | 533 | 3.0 | 1.13 | 2022-26 all + |

Also in the app: `draft_nq_disp_1m_lab` (15-minute direction + ATR): ATR 2x 1:1-1:2 +4.3..+5.5, ~1.5/week, loses Feb-Apr 2026.
