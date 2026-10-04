# Out-of-sample run (2025+ holdout) of two combinations (pre-registered 2026-10-03, BEFORE any 2025+ data is read)

User (2026-10-03): "run the heat map again for 3 · COMBINATION: AGREE + RSI x AGREE INVERSE + RSI and run it OOS and show me; and run it for
5 · COMBINATION: AGREE INVERSE + RSI x Wide INVERSE + ADX, 30pt 1:2,3 and just show me those two OOS". This is the first time any 2025+ data is used for these rules
(the user lifted the seal on 2026-10-03; until then everything ran on 2021-09..2024-12, and 2022-2024 in the later tables).

## Frozen: nothing below changes after the OOS numbers are seen
- Rules exactly as in SPEC.md / SPEC_wide.md / SPEC_heatmap2.md / SPEC_filters.md: entry 09:30:00 market, one trade a day, flat 15:58 ET; volume sign = 15-minute pre-open f_delta (>= 8 finite
  minutes), orders sign = wide-ladder imbalance wimb at the 09:29 snapshot; agree = same sign, AGREE follows the volume side, AGREE INVERSE takes the opposite side;
  RSI filter = 5-minute Wilder RSI(14) at 09:30 (long only if > 50, short only if < 50); ADX filter = house daily ADX(14) > 20 and rising (homebase/gate.py).
- Every trade sized in MNQ micros to ~$1,000 stop risk (round(1000 / (stop pts x $2)), cap 170), $1.04 per micro round-turn; tester fill law (1 tick slippage), 1 s execution guard on any month the
  timestamp phase check fails (enforced by l2sim).
- OOS window: 2025-01-02 .. 2026-05-29. The depth archive is complete through 2026-05-31; the extra file after that covers only ~10 days of June-July 2026 with 40-level books and is NOT used.
- Combination 3 (AGREE + RSI x AGREE INVERSE + RSI): the full grid, 30 variants (fixed 10/15/20/25/30 pts and 1/1.5/2/2.5/3 x ATR14(5m), each at 1:1, 1:2, 1:3). The two never trade the same day.
- Combination 5 (AGREE INVERSE + RSI x Wide INVERSE + ADX): ONLY the 30-pt stop at 1:2 and 1:3 (2 variants). Where both fire on a day they are on the same side and are traded once.

## Verdict rules (fixed now)
- Combination 3 passes if >= 60% of its 30 OOS variants are profitable (the user's yardstick), reported with Sharpe, win rate, realized RR, trades per week and per-year (2025, 2026) numbers.
  With ~150 OOS trades per variant a single variant is noisy (Sharpe uncertainty about +-1.3): the share across variants is the read, not the best cell.
- Combination 5: each of its two variants is shown with the same metrics; "holds" = net > 0 in both. In-sample 2022-24 comparison numbers are quoted from the earlier tables.
One run. If it fails, it fails: no retune, no new filter, no new window. The tester is not used; l2sim runs on the same tape and book archive as before.

## Addendum (2026-10-03, before running): the three single signals out of sample, full grids
User: "run AGREE + RSI, AGREE INVERSE + RSI, and Wide INVERSE + ADX on OOS and show me heatmaps." Same frozen rules, same window (2025-01-02 .. 2026-05-29), same sizing and costs.
AGREE + RSI and AGREE INVERSE + RSI: the full 30-variant OOS grids already exist from the first OOS run (no new data pass). Wide INVERSE + ADX: the full 30-variant grid is run now
(only its two 30-pt cells had been run). Same yardstick (share of the 30 variants profitable, green above 60%) and same reporting. One run, no retune.
