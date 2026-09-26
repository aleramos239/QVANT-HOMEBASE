# Charts — Bitcoin futures (a 24/7 market) on the live charts

Date: 2026-09-26 · Status: requested by the user ("the bitcoin futures wasnt there"); plan stated in chat, no objection; built after/alongside the TradingView-style redesign on `feat/charts-ui`

## Why

The chart service charts and records ten CME roots (NQ ES YM RTY GC SI CL ZN NG HG). The user expected Bitcoin futures too. CME crypto futures have traded 24/7 since 2026-05-30. Everything in the chart engine assumes the classic Globex day: 18:00 ET → 17:00 ET, weekdays, with a weekend print filed into Monday. Adding `BTC` to the root list without changing that would:
- file every Saturday/Sunday Bitcoin trade into Monday's session;
- clip bars at 17:00;
- drop live prints in the 17:00 hour;
- (worst) turn a single refused subscription into a whole-feed reconnect loop. `TickFeed.run()` subscribes the roots one after another inside one `try`, so an exception on one root tears the socket down for all ten.

## Decisions

1. **Per-root trading day.** A 24/7 root (`ALWAYS_OPEN = {BTC, MBT, ETH, MET}`) has a session every calendar day:
   - session D = 18:00 ET on D-1 → 18:00 ET on D, weekends included;
   - `session_date(ts, root)` and `session_range_ms(d, root)` take the root, and every chart-engine call site passes it: bars, history, hub, recorder, server;
   - classic roots are unchanged, including their weekend-print → Monday rule;
   - the session open stays 18:00 for both, so time-bar anchoring, the 18:00 VWAP reset, levels, the refill floor and 1m→Nm resampling behave the same.
2. **One refused symbol never takes the others down.** A root the md feed refuses is recorded as that root's error and the other roots carry on.
   - "Refused" covers two cases: `md/getChart` answers without a `realtimeId`, or the contract cannot be resolved.
   - The page shows "BTC unavailable" in amber with the reason in a tooltip.
   - A refused root is retried every 10 minutes and on every reconnect.
   - Socket-level failures still reconnect everything, as today.
3. **Bitcoin = the standard CME contract `BTC`** (5 BTC, tick 5.0 = $25), the one TradingView shows as BTC1!.
   - Monthly contracts expire on the contract month's last Friday. Front = the contract whose last Friday minus 2 days is still ahead. This was measured on 59 BTC rolls 2021-26: the volume moved 1–3 days before expiry, median 1.
   - `MBT` (micro) gets the same session and roll rules but is not charted by default.
4. **Charted, not in the nightly job.** `DEFAULT_ROOTS` = the nightly archive's roots + `BTC`.
   - The nightly job's weekday 18:00→17:00 fetch would lose the 17:00 hour and weekends. The chart service records Bitcoin live, 24/7, into `~/futures_ticks/BTC/`.
   - Past Bitcoin sessions come from the existing Massive backfill in `~/futures_ticks/BTC`. Those are weekday files to 2026-09-22 with no bid/ask, so they get the "approx. flow" badge.
5. **Closed markets are not "stale".** The bottom bar only flags a symbol whose market is open (Globex: Sun 18:00 → Fri 17:00 ET, daily break 17:00–18:00; 24/7 roots always). On a weekend it no longer shows every closed future in amber while Bitcoin trades. Ages read as s / m / h / d.

## Out of scope

- Contract re-resolution at the session roll while the service stays up. This is the Build-1 parked follow-up. Bitcoin's next roll is 2026-10-28; a service restart re-resolves.
- Exchange holidays in the market-open rule.
- Charting MBT/ETH by default.
- Backfilling Bitcoin's 17:00 hour and weekends before today.

## Testing

pytest:
- session maths for 24/7 vs classic roots;
- 24/7 time bars through 17:00 and into Saturday, and `on_clock` closing at 18:00;
- the hub rolling to a Saturday session;
- the recorder filing a Saturday trade under Saturday;
- live mode keeping a Saturday Bitcoin print while still dropping a classic root's weekend straggler;
- the feed isolating a refused root, retrying it, and still reconnecting on socket failures;
- the `front_month` BTC/MBT roll dates;
- the contract spec;
- the root list.

Node: root names and the market-open rule.

After merge + a chart-service restart: Bitcoin's live ticks flow on the weekend, get recorded to `2026-09-26_BTCV6.live.csv.gz`, and move the chart. The status shows BTC fresh and the closed markets as closed.
