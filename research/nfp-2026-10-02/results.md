# NFP Fri 2026-10-02 08:30 ET: LucidPro 50K full-port, one trade (study run 2026-10-01 evening)
Scripts here (nfp_lib, build_cache, grid, analyze, select_is, freeze, score_holdout, report, vol_scaling_test). Python: ONYX TRADING/.venv. Tables in out/.

## 1. Is tomorrow NFP?  YES.
BLS schedule page: September 2026 Employment Situation = Oct. 02, 2026, 08:30 AM ET; a news-search summary says the same. CAUTION: our own calendar file
(homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv) ENDS 2026-09-30, so it has NO row for 2026-10-02 (nor the next CPI). gc_nfpcpi would not trade it.
gc_nfpcpi is tester-only: the live desk config has no GC straddle at all (only nq930/ym930/nq10am/nq_open_*). Tomorrow's trade needs a desk strategy plus that calendar row.

## 2. Method (plain)
Tick replay, same engine as the 09-25 research script (replicates its numbers exactly: 38 NFPs, WR 68.4%, +$11,478 per contract). Straddle: stops at last 08:30:00 print +/- offset, live +85 ms,
first fill cancels the other, cancel 08:45, flat 09:55. Target = $ needed to NET $3,000 after commission (4 GC $16 round-turn; micros $1.50 each, assumed). Pass = net >= $3,000 on the day. Bust = balance
reaches -$2,000 (EOD trail only matters after a win; one trade a day). Slip models: M1 = house (1 tick each way, first-print fills); P1/P2/P4 = 1/2/4 ticks on entry and stop PLUS the 08:30:01 cascade
(a stop hit in the first 2 s fills at the worst print of the next 1 s: an upper bound, not a typical fill). 59 NFP + 59 CPI; first 4 dropped (volatility warm-up): IS 73 (36 NFP + 37 CPI; GC has no
tape for Good Friday 2023), holdout 39 (19 NFP). Pooled NFP+CPI is used for selection because 36 NFPs alone cannot rank 500 cells (SE ~8 pts).

## 3. Anti-overfit  (READ FIRST: the 2025+ window was NOT untouched)
The ledger shows 2025-01 -> 2026-09 was already SPENT for this family on 09-25 (one-shot plus a 2nd pass, "window closed", the $2k/$3k 4-ct NFP bracket included). So the holdout below is a
consistency check on a window already seen, not a clean exam. Procedure anyway: pick on 2021-24 only (498 cells; rule in select_is.py: mean P(pass) over M1/P2/P4, smoothed over neighbouring
offsets), freeze 5 finalists + sha256 (6054cc4c...b029, 16:34 ET) BEFORE scoring, score 2025-26 once, decision rule fixed in advance. Burn recorded in the ledger (vault, 2026-10-01 entry).

## 4. What 2021-24 says
* More contracts is better, always: P(pass) falls monotonically as the target distance grows (4 GC / 40 MGC = 7.6 pts: 62%; 30 MGC 52%; 20 MGC 37%; 15 MGC 23%; 10 MGC 8%). Max size wins. Same in
  every volatility tercile, so there is no sign the target should scale up with volatility.
* Offset: 2 pts is the peak and stable (1: 58%, 2: 62%, 3: 55%, 5: 47%, 8: 33% on 4 GC). Volatility-scaled offsets (0.1-0.2 x trailing 8-event first-minute range) tie it in 2021-24 (60-61%).
* Stop: P(pass) barely moves (1,200: 61.6%, 1,500: 61.6%, 1,800: 64.4%, 2,000: 64.4%). What moves is bust: a $2,000 stop nets below -$2,000 after commission+slip, so EVERY stop-out busts (34%);
  $1,200/$1,500 stops bust 0% on first-print fills, 12% under the pessimistic cascade. Two-event alternative ($1,500 target) needs two wins, so it cannot pass tomorrow and no better over 4 events.
* Comparison, same $3k/$1.5k bracket at max size, IS pooled, M1 | P2 (pass / bust under P2): GC 62% | 62% (12%); NQ 57% | 57% (22%); ES 49% | 47% (16%); SI (40 SIL) 67% | 67% (26%, mean net only $88 under P2,
  micro-silver depth for 40 lots at 08:30 is doubtful). GC is the most robust to slippage; SI is not clearly better (CI 56-77%). NQ/ES/SI are IS-only, not scored on 2025+.

## 5. Frozen finalists, holdout 2025-01 -> 2026-09 (39 events), pass this event M1 | P2, bust M1 | P2
| id | variant (4 GC unless noted) | IS pass | HO pass | HO bust | 2026 only (17) pass |
| A | off 2 / SL 3.7 pts ($1,500) / TP 7.6 pts  (IS pick) | 62% | 64% | 5% | 13% | 53% |
| B | off 2 / SL 5.0 ($2,000) / TP 7.6  (plain user bracket) | 64% | 67% | 33% | 33% | 59% |
| C | off 2 / SL 3.0 ($1,200) / TP 7.6 | 62% | 56% | 3% | 13% | 47% |
| D | off 0.1 x V (scaled) / SL $1,500 | 60% | 64% | 8% | 21% | 59% |
| E | contracts scaled to V (b 0.3) / off 0.1 V / SL $1,500 | 60% | 62% | 3% | 23% | 53% |
Pre-declared rule: recommend A unless a rival is >= 15 pts better under P2. None is (B +5). Scaling (D, E) does not help; points-based brackets still work at 2x-4x the 2021-24 volatility.

## 6. RECOMMENDATION for tomorrow (variant A)
GC, 4 contracts (40 MGC is the same $/pt but 4x the commission), OCO stop entries anchor +2.0 / -2.0, stop 3.7 pts ($1,480 + $16 comm, about -$1,500 to -$1,550 with a tick of slip), target 7.6 pts
(+$3,040 gross, +$3,024 net), cancel unfilled 08:45, flat 09:55. Anchor = last print before 08:30:00.000.
Plain $2,000/$3,000 comparison (B): same but stop 5.0 pts, target 7.6.
| per eval | A: IS | HO | B: IS | HO |
| P(pass tomorrow), first-print fills | 62% [50-72] | 64% [48-77] | 64% | 67% |
| ... pessimistic 2-tick + cascade | 62% | 62% | 64% | 67% |
| ... 4-tick + cascade | 60% | 59% | 63% | 64% |
| P(bust tomorrow) first-print | 0% | 5% | 34% | 33% |
| P(bust) pessimistic 2-tick + cascade | 12% | 13% | 34% | 33% |
| P(pass within the next 4 NFP/CPI events) | 71% | 77% | 64% | 67% |
Cost per PASSED eval at $140: A $226 (IS) / $219 (HO) / $264 if 2026 repeats (53%); with the 4-event survival path $182-$197. B $219 / $209 (but a bust is final).
Honest range for tomorrow: ~55-65% pass, 0-13% bust, the rest survive with about -$1,500. 2026 alone is weaker (53%, 9 of 17), and since June the realised NFP/CPI candle is 35-93 pts.
Evals bought together are NOT independent: all copies of one variant win or lose together (that is the 62%). Mixing offsets 1/2/3 across evals lifts "at least one passes" only to 67%.

## 7. Caveats
Tick data is the first-print model, not your broker's queue: a 4-GC stop at 08:30:00 can fill several points worse (cascade rows show -$6k to -$17k extreme tails; not a typical fill). IS SL $1,800 (4.5 pts) looked
better than $1,500 on IS only (64% pass, 3% bust first-print) but was not a finalist: untested on the holdout, mention only. Lucid real-time vs EOD breach on open P&L is unconfirmed (rules_research.md). Tests untouched (no homebase code changed).
Prop firms may bar news trading. Nothing was deployed; the desk was only read.
