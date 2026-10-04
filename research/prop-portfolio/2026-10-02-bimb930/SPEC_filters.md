# ADX and RSI filters on the 8 signals, longs and shorts (pre-registered 2026-10-02, BEFORE any run)

User: "run ... same exact ideas, for longs and shorts [8 signals] ... but now for each i want you to add an adx filter only entering with trend
forming and above and a separate test of adding RSI and only when we have good momentum." (the ADX idea was first asked just before; this is the version to run).

## The 8 signals (unchanged definitions, SPEC.md / SPEC_flow.md / SPEC_wide.md / SPEC_heatmap2.md)
volume `flow` / `flow_inv`; wide ladder `wimb` / `wimb_inv`; top-10 book `imb` / `imb_inv`; combined `agree` / `agree_inv`.
Each is run THREE ways: (off) no filter [regression: must reproduce heat map v2 exactly], (adx), (rsi). ADX and RSI are SEPARATE tests, never combined.
"Longs and shorts": every table is reported for ALL trades, the LONG trades alone and the SHORT trades alone (same trades, split by side).

## Filters (zero tunable parameters beyond the two standard constants below; the filter only removes entries, it never changes the side)
- `adx` ("trend forming and above"): the house gate, `homebase/gate.py adx_series`: Wilder ADX(14) on COMPLETED DAILY bars (last completed day), RMA smoothing.
  Enter only if ADX > 20 (the house THRESHOLD) AND ADX is rising (ADX of the last completed day > ADX of the day before). Same for longs and shorts.
  Days with too few daily bars to compute ADX are skipped.
- `rsi` ("good momentum"): Wilder RSI(14) (RMA, the same helper) on the closes of the completed 5-minute candles since 00:00 ET, read at 09:30.
  LONG only if RSI > 50; SHORT only if RSI < 50 (momentum agrees with the trade side). RSI == 50 or < 30 candles = no trade.
  50 is the standard bull/bear line; a stronger line (55/45, 60/40) is a different test, not run here.

## Everything else as in heat map v2 (SPEC_heatmap2.md)
Entry 09:30:00 market, one trade a day, flat 15:58 ET, 2021-09-22..2024-12-31 only (2025+ sealed). Grid: fixed stops 10/15/20/25/30 pts and 1/1.5/2/2.5/3 x ATR14(5m),
each at 1:1, 1:2, 1:3 (30 variants per table). Every trade sized in MNQ micros to ~$1,000 stop risk (round(1000/(stop pts x $2)), cap 170), $1.04 per micro round turn.
Controls on the same days AND the same filter: always-long / always-short (book, wide, flow day sets) and long/short on all / agree days (combined).

## Reported (the user's yardstick): per table the share of the 30 variants with net > 0, overall and for longs-only / shorts-only, with trades per variant
(filters shrink the sample: a variant under ~150 trades has a Sharpe uncertainty of +-1.3 or more), any table above 60%, top cells by Sharpe with per-year.
Multiple-testing note: 8 signals x 3 filters x 30 cells = 720 more cells on overlapping days (1,320 with heat map v2). A filter that only helps is a LEAD;
the control row with the same filter must be beaten before it means anything. One run, no retune of the grid, thresholds or filter rules.
