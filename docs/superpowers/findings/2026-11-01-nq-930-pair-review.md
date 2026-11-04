# NQ 9:30 pair (draft_nq_930_pair_long / _short) — pre-flight review, 2026-11-01

Files: `~/.homebase/strategies/nq_930_pair_long.py`, `nq_930_pair_short.py`. Market order at 09:30:00, stop/target in points
re-priced to the fill (default 25 / 37.5), flat 15:55. Parity: in-sample runs 2044 / 5d41 = earlier runs 5a03 / 918d, 943/943 days identical.

1. Look-ahead — PASS. Only input is `ctx.last_price` at 09:30:00 (the print before the order); no indicators.
2. Repainting — N/A. No bar signal; a clock-time market order.
3. Overfitting — PASS (as a rule). Two settings (stop, target); no filters. Test months read 2026-11-01 (owner said):
   ≥1 hits full TP 77.6% in-sample, 78.2% test months (4c 1:1.5). Net is negative on both legs (owner judges hit rate only).
4. Sizing & risk — WARN. 4 NQ x 25 pts = $2,000 + costs; worst trade -$2,196 (gap through the stop). That is above a
   LucidFlex 50K trailing max loss ($2,000) and near Apex's $2,250 per-trade limit — one stop can end a 50K account.
   Size is set per account on the Desk; the strategy itself sends the account's size. Brackets go with the entry (OSO).
5. Live-readiness — FAIL by design: multi-account hedging (one account long, one short, same moment) is banned at Apex,
   Lucid, Alpha Futures and most prop firms, and is detectable when both accounts sit at the same firm. Flat 15:55 PASS.
   Holds under 5 s: 59 / 53 trades, 3.5-3.9% of profit — PASS (well under 50%).
6. Funnel — PASS. One trade per leg every trading day.

**Verdict:** code is safe to run (matches the backtest exactly); the owner must decide the hedging rule risk and size each
account so one stop (~$2,200 worst at 4 NQ) fits its loss limit. Put on the Desk OFF / no account until he books accounts.
