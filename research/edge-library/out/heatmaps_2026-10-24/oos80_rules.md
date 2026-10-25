# OOS batch of 2026-10-24 -- the rules, written BEFORE any test month of this batch was read

Owner's order (2026-10-24): "lets take these variants, run them OOS, take the ones that are not overfit and look real not luck, then take
the ones that survive and run those variants all years in and out sample together and run on monte carlo then let me know which survive
are real, robust, or fake".

80 boxes, NQ 5-minute wick break (candle_sweep mode break), hm40 exits, 3:1 block walk-forward. Each box is its own idea name holding
only its own setting value (one pick each). 6 delta-off boxes on 9:30-11 were already read on 2026-10-23/24 (nq_wcd5_b28, b44, b60, b64,
b63, b74 -- the same trades): their records are reused, not re-run.

## Step 1 -- the test months (15 months)
## Step 2 -- not overfit, not luck (a box must pass ALL)
1. Test months net > $0.
2. Keeps its pace: test-months $ a month >= 50 % of its in-sample $ a month.
3. Not luck: per-trade t on the test months >= 1.28 (one-sided p <= 0.10).
4. Not one stretch: test months net still > $0 without its 3 best trades.
5. Not alone: at least one of its direct neighbours in this batch (same window and setting, one step of stop or target) also passes 1-4.

## Step 3 -- the survivors, all months together (in-sample + test, ~5 years)
Monte Carlo: 1,000 reshuffles of whole days (blueprint/mc.py, fixed seed). Per year net.

## Verdict
- ROBUST: passes step 2; together: profit in >= 97.5 % of reshuffles AND every full year (2022-2025) positive AND >= 2 neighbours pass step 2.
- REAL: passes step 2; together: profit in >= 95 % of reshuffles.
- FAKE: fails step 2 (named by the line it fails), or passes it but < 95 % together.
Selection caveat stated with the verdict: 80 boxes were read; ~8 would pass line 3 by chance alone.

## Addendum, 2026-10-25, written BEFORE these test months were read -- idea D (pdelta: flow in the 5 minutes before the candle)
Owner: "run 5m Any (with the trade) Candle x1.5,2 1:1.5 1:2 / Top 20% Candle x2 1:2 OOS and show me their results are they real or luck
or overfit". 5 boxes, NQ 5m 9:30-11, one setting a copy (wk_dn_*). The same lines 1-5 and the same verdict as above, unchanged; a
neighbour = one of these 5 a step of stop or target away within the same setting (the top-20% box has no neighbour in the batch, so it
cannot pass line 5 -- said with its result). 5 boxes read: about 0.5 would pass line 3 by chance.
