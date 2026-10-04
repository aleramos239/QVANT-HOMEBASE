# bimb930 — NQ 09:30 book-imbalance direction, 1:2 bracket (pre-registered 2026-10-02, BEFORE any run)

User idea (2026-10-02): "Bid-side imbalance go long with the top 10 outweigh the [asks]; vice versa for shorts."
Account target: Apex Legacy 300K PA, 2 NQ, risk $1,000 (25 pt stop) / reward $2,000 (50 pt target).

## Plain-words reason (written before testing)
If more size is resting on the bid than on the ask in the top 10 levels just before the cash open, buyers are lined up
and the open should lift; if asks outweigh bids, sellers are lined up and it should fall. So follow the heavier side.

## Rule (one trigger, zero tunable parameters)
- Decision at 09:30:00 ET, once per day, from ONE row: the snapshot stamped 09:29 (usable at 09:30:00).
- `imb10` = (bid_top10 - ask_top10) / (bid_top10 + ask_top10). `imb10 > 0` -> market LONG; `< 0` -> market SHORT;
  `== 0` or no valid book -> no trade.
- Market entry at 09:30:00, stop 25 pts, target 50 pts (re-priced from the fill), 1 trade per day, held to the stop /
  target or FLAT AT 15:58 ET (user, 2026-10-02: "flat by 4pm"; the first run, which flattened at 11:00, was stopped and
  never read, its files are in out_flat1100_superseded/).
- Sizing: 1 NQ in the simulator, scored at 2 NQ (20 micros). Costs = tester law (1 tick slippage, $4/RT/contract).
- Window: 2021-09-22 .. 2024-12-31 (research window ONLY). 2025+ is sealed and not touched.

## Controls (same simulator, same days, same bracket)
- `long`  = always long on the days the book signal exists. `short` = always short on those days.
- C2 null = the same rule with `imb10` replaced by a random other day's value at the same time (score.C2Features),
  20 seeds. This is "does the book carry information beyond a random direction".

## Verdict rule (fixed now)
Informative ONLY IF all of:
1. real win rate >= the 95th percentile of the 20 null win rates (at most 1 of 20 nulls at or above it);
2. real net > 0 at 2 NQ after costs;
3. real win rate above the null mean in at least 3 of the 4 calendar years.
Anything else = no evidence. One run: no threshold, no retune. A changed rule is a NEW test and gets a new entry.
Break-even win rate at 1:2 with costs is ~34%.
