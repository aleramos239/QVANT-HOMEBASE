# 5-layer Monte Carlo on the AGREE + RSI heat map (defined 2026-10-05, before running)

User: "run a 5 layer monte carlo on the heatmap and show me the median". "5-layer" = the user's own retired Onyx simulator (onyx/report/propsim5.py, frozen copy
research/_propsim5_frozen.py): L1 iid day bootstrap, L2 block bootstrap (5-day blocks), L3 block bootstrap (20-day blocks), L4 replay (real order from every start day, wrapping),
L5 cost2x (5-day blocks on a cost-stressed series). Same layer logic, seeded per layer with crc32.

- Series: for each of the 30 AGREE + RSI variants, the daily P&L of the sized trades ($1,000 micro sizing, $1.04/micro) on the full weekday grid (Mon-Fri, zero on days with no trade, as in the
  Onyx sim). Two heat maps: OVERALL (2022-01-03 .. 2026-05-29, in-sample + OOS pooled) and OOS (2025-01-02 .. 2026-05-29).
- Path: 60 weekdays (about 3 months); 10,000 paths per layer for L1, L2, L3, L5; L4 = one path per start day.
- L5 cost2x series: each trade pays an extra (commission + one extra tick of slippage) = n micros x ($1.04 + $0.50) on top of the existing costs (costs roughly doubled).
- Per path (closed-day equity, so drawdowns are optimistic vs the intraday-trailing Apex rule): final net, max drawdown, ruin = drawdown from the running peak >= $7,500 (Apex Legacy 300K
  trailing threshold), "pass-like" = profit reaches +$7,500 before ruin, P(final net > 0).
- "The median": per variant, the median across the five layers of each layer's median. All five layers are shown in the tooltip.
No tuning; one run; seed 20261005.
