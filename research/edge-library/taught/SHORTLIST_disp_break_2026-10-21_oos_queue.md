# Out-of-sample queue: 1-minute displacement (owner, 2026-10-21)

The owner keeps these four to run out-of-sample later, together (his words: "add ... to the list which we will run OOS later").
Their test months are stored by the app walk-forwards and NOT shown yet; the owner says when.

| # | Version | App strategy + inputs | Walk-forward (cell) | In-sample edge | Avg | /week |
|---|---|---|---|---|---|---|
| 1 | ORB + ATR 2x + volume 3x, 1:2 | draft_nq_disp_orb_lab: trig atr, atr_k 2, vol_x 3, rr 2, orb_min 15, w_end 15:00 | 20261021-143905-draft_nq_disp_orb_lab-4e5d | +8.8 | $192 | 1.9 |
| 2 | ORB + ATR 1.5x + volume 3x, 1:2 | draft_nq_disp_orb_lab: atr_k 1.5, vol_x 3, rr 2 | 20261021-143905-draft_nq_disp_orb_lab-4e5d | +6.8 | $124 | 3.0 |
| 3 | ORB + ATR 2x, 1:2 (no volume) | draft_nq_disp_orb_lab: atr_k 2, vol_x 0, rr 2 | 20261021-143905-draft_nq_disp_orb_lab-d206 | +4.5 | $91 | 4.0 |
| 4 | 15-min direction + ATR 2x, 1:2 | draft_nq_disp_1m_lab: trig atr, htf 15, atr_k 2, vol_x 0, rr 2, w 09:30-15:00 | 20261021-143518-draft_nq_disp_1m_lab-1886 | +4.4 | $88 | 1.5 |

In-sample = the 3:1 block in-sample days (883, 2021-10 .. 2026-04), NQ, 1 contract, $4 + 1 tick. Tables: SHORTLIST_disp_break_2026-10-20.md section 4.
Earlier shortlist (15-minute rules): SHORTLIST_disp_break_2026-10-20.md sections 1-3.

## Range-by-range search (owner, 2026-10-21: "find a variant that works in each range ... until a couple work for each range")

App strategy `draft_nq_disp_range_lab` (any range: r_start, orb_min, w_len = entry minutes after the range; trig atr). Walk-forward ids in the
session scratch (S1 all ranges 20261021-181444-...-452b; S2 per range 20261021-1823xx; S3 per range 20261021-192933/4). Fade version:
`draft_nq_disp_range_fade` (F1 20261021-182449-...-3988). Same 883 in-sample days. All test months stored, NOT shown.

| Range | Range length | Entries for | Version | Edge | nbrs | Avg | /week | Years + 2022-25 | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 09:30 | 15 min | 4 h | ATR 2x + vol 3x, 1:2 | +13.2 | +10.3 | $301 | 1.3 | 4/4 | strong (all 24 boxes +, mean +8.0) |
| 09:30 | 15 min | 4 h | ATR 1.5x + vol 3x, 1:2 | +10.7 | +8.5 | $207 | 2.0 | 4/4 | strong |
| 10:30 | 60 min | 4 h | ATR 2x + vol 3x, 1:2 | +7.5 | +6.0 | $159 | 1.6 | 4/4 | strong (all 24 +, mean +5.2) |
| 10:30 | 60 min | 4 h | ATR 2x + vol 3x, 1:1.5 | +5.9 | +5.5 | $102 | 1.6 | 4/4 | good |
| 12:00 | 60 min | 4 h | ATR 2.5x, 1:2 | +9.5 | +8.8 | $198 | 1.2 | 4/4 | strong (all 24 +, mean +6.7) |
| 12:00 | 60 min | 4 h | ATR 2.5x, 1:1.5 | +8.7 | +8.3 | $156 | 1.2 | 4/4 | strong |
| 08:30 | 60 min | 4 h | ATR 3x, 1:2 | +4.6 | +2.4 | $121 | 1.9 | 4/4 (mostly 2025) | borderline |
| 13:30 | 30 min | 2 h | ATR 2x + vol 3x, 1:2 | +3.5 | +2.2 | $55 | 1.3 | 3/4 | borderline |
| 03:00 | 15 min | 2 h | FADE ATR 2.5x, 1:2 | +2.9 | -0.2 | $39 | 1.4 | 4/4 | weak |
| 08:00 | 15 min | 2 h | FADE ATR 2.5x, 1:1 | +2.5 | +1.5 | $49 | 4.3 | 4/4 (mostly 2025) | weak |
| 00:00 | 60 min | 1 h | ATR 2.5x + vol 3x, 1:2 | +3.6 | +2.1 | $28 | 1.0 | 2/4 | no |

## Overnight windows + ES / GC (owner, 2026-10-21: "find something that works for the other windows 6pm thru 9am also ... ES or GC")

App strategies: `draft_nq_disp_range_ovn` (NQ, session 18:00 .. 09:30, flat 09:25), `draft_es_disp_range_lab`, `draft_gc_disp_range_lab`
(the NQ range lab on another root). Searches: O1 (NQ overnight, 11 range starts x 30/60 min x vol 0/3, ATR 2 and 2.5), M1 (ES/GC day
ranges), R2 (refine: ATR 2/2.5/3 x vol 0/3 x target 1.5/2/3). Ids in the session scratch rng_ids.json. Same 3:1 in-sample months
(2021-10 .. 2026-04); all test months stored, NOT shown.

| Market | Range | Length | Entries for | Version | Edge | nbrs | Avg | /week | Years + 22-25 | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 04:00 | 60 min | 4 h | ATR 2.5x + vol 3x, 1:3 | +5.7 | +5.1 | $83 | 2.6 | 3/4 (2023 -) | all 18 boxes + |
| NQ | 04:00 | 60 min | 4 h | ATR 3x, 1:3 | +7.0 | +6.3 | $112 | 1.8 | 3/4 (2023 -) | |
| NQ | 06:00 | 60 min | 4 h | ATR 3x, 1:1.5 | +7.2 | +5.8 | $114 | 1.5 | 3/4 (2023 -) | 2025 weak; all 18 + |
| NQ | 18:00-22:00, 00:00, 02:00 | | | any | <= +3.3 | <= +0.7 | | | | NO: evening/Asia/Frankfurt do not work |
| ES | 09:30 | 60 min | 4 h | ATR 2.5x, 1:2 | +11.5 | +9.3 | $167 | 1.1 | 3/4 (2024 -$588) | all 18 + |
| ES | 10:30 | 60 min | 4 h | ATR 2.5x + vol 3x, 1:2 | +8.4 | +7.3 | $130 | 1.1 | 3/4 (2023 -) | all 18 + |
| ES | 12:00 | 60 min | 4 h | ATR 3x + vol 3x, 1:3 | +13.8 | +12.0 | $259 | 0.7 | 4/4 | all 18 +; rarest |
| ES | 12:00 | 60 min | 4 h | ATR 3x, 1:2 | +12.2 | +11.4 | $194 | 0.7 | 4/4 | |
| GC | 12:00 | 60 min | 4 h | ATR 3x + vol 3x, 1:3 | +13.6 | +10.9 | $181 | 0.8 | 4/4 | 2022 ~0; HALF the net is Jan-Apr 2026 |
| GC | 13:30 | 15 min | 4 h | ATR 3x + vol 3x, 1:2 | +14.9 | +12.5 | $180 | 0.8 | 3/4 (2022 -) | 2026 is half the net |
| GC | 08:30, 09:30, 10:30 | | | any | <= +1.0 | | | | | NO |
| ES | 08:30, 13:30 | | | any | <= +5.2 | <= +2.9 | | | | weak |

Floors: ES $75 (all rows clear), GC $140 (only the 3x rows clear, and those lean on 2026).
Every refine's best lands at ATR 3x = the top of the grid: 3.5x / 4x untested (trades thin out: NQ day 4x was 0.3/week).

## Frequency round (owner, 2026-10-21: "higher trade frequency ... separate by sessions ... extend the sessions ... afternoon or overnight")

Searches X1-X4 (17 walk-forwards, ids in the session scratch rng_ids.json; every table in `RANGE_SEARCH_TABLES_2026-10-21.md`).
App strategies: `draft_nq_disp_range_full`, `draft_es_disp_range_full`, `draft_gc_disp_range_full` (session 18:00 .. 16:00, range start any of 23 times,
entries to 15:55, flat 15:58). All in-sample (3:1 blocks, 2021-10 .. 2026-04); test months stored, NOT shown. Floors NQ $70 / ES $75 / GC $140.

What the longer windows did: a longer entry window adds trades but each added hour dilutes the edge. The 09:30 NQ range is the clearest case:
4 h +13.2 at 1.3/week, 5.5 h +8.2 at 2.0/week.

| Market | Range | Length | Entries for | Version | Edge | nbrs | Avg | /week | Years + 22-25 | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 09:30 | 15 min | 4 h | ATR 2x + vol 3x, 1:2 | +13.2 | +9.8 | $301 | 1.3 | 4/4 | best single leg |
| NQ | 09:30 | 15 min | 5.5 h | ATR 2x + vol 3x, 1:2 | +8.2 | +8.4 | $178 | 2.0 | 4/4 | the frequency version |
| NQ | 10:30 | 60 min | 5.5 h | ATR 2.5x + vol 3x, 1:2 | +8.9 | +8.1 | $205 | 1.1 | 3/4 (2023 -) | |
| NQ | 12:00 | 60 min | 3 h | ATR 2.5x, 1:2 | +9.5 | +9.1 | $198 | 1.2 | 4/4 | |
| NQ | 12:00 | 60 min | 3 h | ATR 3x + vol 3x, 1:2 | +12.5 | +11.5 | $353 | 0.6 | 4/4 | rarer, stronger |
| NQ | 13:00 | 15 min | 3 h | ATR 2.5x, 1:2 | +9.2 | +9.4 | $189 | 1.4 | 4/4 | NEW window; all 18 boxes + |
| NQ | 13:00 | 15 min | 1 h | ATR 2.5x, 1:2 | +13.1 | +12.7 | $351 | 0.7 | 4/4 | |
| NQ | 04:00 | 60 min | 4 h | ATR 3x, 1:3 | +7.0 | +6.3 | $112 | 1.8 | 3/4 (2023 -) | longer than 4 h loses it (+1.6 at 11 h) |
| NQ | 06:00 | 60 min | 4 h | ATR 3x, 1:1.5 | +7.2 | +5.8 | $114 | 1.5 | 3/4 (2023 -) | longer than 4 h loses it |
| NQ | 20:00 (Asia) | 30 min | 4 h | ATR 3x, 1:2 | +5.0 | +2.8 | $47 | 1.8 | 3/4 | below the $70 floor: NO |
| NQ | 21:00, 02:00, 03:00, 14:00 | | | any | <= +2.4 | | | | | NO (London 02:00 / 03:00 lose outright) |
| ES | 09:30 | 60 min | 4 h | ATR 2.5x, 1:2 | +11.5 | +11.1 | $167 | 1.1 | 3/4 (2024 -$588) | |
| ES | 12:00 | 60 min | 2-3 h | ATR 3x, 1:2 | +12.2-13.3 | +12 | $194-236 | 0.6-0.7 | 4/4 | |
| ES | 10:30 | 60 min | 5.5 h | ATR 3x, 1:2 | +11.0 | +9.5 | $179 | 0.9 | 3/4 (2023 -) | |
| ES | 06:00 | 60 min | 8 h | ATR 3x, 1:2 | +4.8 | +1.9 | $76 | 3.3 | 3/4 | weak, not carried |
| GC | 13:30 | 15 min | 2 h | ATR 3x + vol 3x, 1:2 | +16.1 | +12.5 | $197 | 0.8 | 3/4 (2022 -) | clears the $140 floor; 2026 is half the net |
| GC | 12:00 | 60 min | 3 h | ATR 3x + vol 3x, 1:2 | +12.2 | +8.9 | $157 | 0.8 | 3/4 (2022 -) | clears the $140 floor |

### Stacked NQ legs (same candle taken by two legs counts once; one position at a time)

Legs A 09:30 (15 m, 4 h, ATR 2x + vol 3x) / B 10:30 (60 m, 5.5 h, ATR 2.5x + vol 3x) / C 12:00 (60 m, 3 h, ATR 2.5x) / D 13:00 (15 m, 3 h, ATR 2.5x) / E 04:00 (60 m, ATR 3x, 1:3).
The legs overlap in time and often fire on the same candle, so the stack is about half of the sum of the legs.

| Mix | Edge | Avg | Net | Trades | /week | Sharpe | Years + |
|---|---|---|---|---|---|---|---|
| A + B + C + D | +8.8 | $184 | $90,769 | 494 | 2.8 | 1.53 | 4/4 |
| A + B + C + D + E | +8.2 | $155 | $127,019 | 819 | 4.6 | 1.91 | 4/4 |
| A + D + E (least overlap) | +8.3 | $156 | $121,364 | 779 | 4.4 | 1.91 | 4/4 |

All three clear +3 by a wide margin. The stack keeps every year positive; 2023 is the weak year (+$4k of +$127k).
Run as separate Desk strategies, a candle that fires two legs would take two positions: size or de-dupe before the Desk.

Review of the drafts (2026-10-21, 31-agent adversarial pass): the drafts did not declare `own_stop`, which only changes the default hm40 table;
every run here passed its own axes, so no shown number moved. `own_stop = True` is now set on all ten displacement drafts. Two tiny biases remain, noted not fixed:
ATR(14)'s first true range uses the plain candle range, and `trig=prev` lets a doji previous candle through (a handful of trades in 5 years, not used by any version above).
