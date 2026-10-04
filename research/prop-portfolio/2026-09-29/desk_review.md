# Desk review of the 3 approved NQ strategies (strategy-review, read-only) - Thu 2026-10-01
Reviewed: pp_straddle.py, pp_orb.py, template.py, families/{straddle,orb}.py, evalcore.py/funded.py (day-rule code), holdout_manifest.json,
holdout trades (runs 224006 / 224226 / 224650), and the desk (engine.py, timer.py, rules.py, risk.py, config.py, strategies/straddle.py).
Nothing was run, changed or deployed. Dollars are for 40 micros = 4 NQ minis ($80 per point) unless stated.

## Checks 1-2, 5-6: look-ahead, repaint, flat time, trade count: PASS
- ATR and levels use closed bars only. The tester delivers the bar that ends at 09:30:00 BEFORE the 09:30 event, so the 09:00-09:30 bar is in the ATR (not a leak).
- Anchor = last print before the event. ORB range = 1-min bars 11:00-11:04, all closed at 11:05:00. Stops/targets are set once, from closed data. No repaint.
- ROLLS only blanks prior-day levels; none of the 3 configs reads them. Daily bars are not used. The 2025+ ROLLS list was extended and re-checked.
- Exactly 1 trade per day per session in the holdout (433 / 433 / 338 days, max 1). Holds are 15 min to 2.5 h (never under 5 s). All flat by 15:58.

## Findings by severity
CRITICAL 1. Every Lucid number assumes Lucid only counts CLOSED balance against the $2,000 max-loss line.
  - The strategies' 3 x ATR stop is never a real stop. Median stop: nyam straddle $10.5k, ORB $9.8k, pm straddle $16.0k, i.e. 5-8x the $2,000 limit.
    Full-trade open loss went past $2,000 in 80% / 76% / 70% of trades (order vs the take unknown).
  - If Lucid liquidates on open loss (rules text says "account balance", silent on open P&L): Flex eval 78% -> 2%, Pro no-DLL eval 81% -> 20% (7% for the 3,000 variant),
    funded cheque value (E$40) Flex pm $2,488 -> $0, Pro ORB $4,824 -> $17 (holdout, out/holdout_summary.md).
  - Shape: win the small take on 87-89% of days; the other 11-20% lose $5.4k-$8.5k on average (3-4x the limit) and end the account. Per-day average is
    +$353 (nyam, Flex take) but -$103 (ORB) and -$213 (pm). Money comes only from "payout before the loss day". Get Lucid's answer in writing before real size.
CRITICAL 2. The desk has no daily-rule engine. day_take / day_lock / target_take do not exist in engine.py; risk.py (AccountRisk) is not wired to anything;
  the equity poll runs every 60 s (server.py EQUITY_INTERVAL_S). A polled watcher would miss a +$1,500 touch by minutes.
HIGH 3. The desk cannot express these geometries today:
  - StrategyCfg holds FIXED offset/SL/TP points; handle_alert refuses unless spread == 2 x offset_pts. These need a new ATR-based value every day.
  - timer.py fires only at 09:30:00 (FIRE_T constant). ORB (11:05) and pm straddle (13:30) have no fire path.
  - The "bars" path (rules.Signal) places ONE leg: no OCO, so no opening-range breakout or straddle from it.
  - One signal fans out to every booked account with ONE geometry, but the take level differs per account (Flex $1,500 vs Pro target). Use one strategy per rule set.
HIGH 4. Entry edge is thin or absent for 2 of 3. Holdout lift over day-matched random entries with the same rules: nyam straddle +0.125 [0.06, 0.21]
  (Flex eval) and +0.138 (Pro); pm straddle funded +$441 (Flex); ORB eval -0.044 [-0.09, 0.00], ORB funded -$753. Without the take rules, the all-session runs of ORB#10 lost $28.9k and #32 lost $33.3k per
  1 NQ over 2025-26 (PF 0.98 / 0.97); #10 made +$277.6k (PF 1.19). So (b) and (c) are carried by the take rule, not the entry.
MEDIUM 5. ATR parity. ATR(14, Wilder) restarts at 00:00 ET each day: first TR = high-low, seed = mean of first 14 bars (19 bars at 09:30, 27 at 13:30, 132 5-min bars at 11:05).
  A chart-history ATR will differ. The desk's 1-min bar closes on the next push or 3 s late; the 09:30 fire needs the 09:30:00.000 close, so build bars from ticks.
MEDIUM 6. Costs. Sim round trip = $16 for 40 micros only because it assumes 4 NQ minis ($4 each). 40 MNQ would be $40. Trade NQ minis. Sim slip: 1 tick on exit, and MFE is
  measured from the entry print, not the slipped fill (stop-entry slip median 0.25 pt, p90 0.5 pt): about $20-40 per trade of optimism. 4-lot market-outs may slip more.
MEDIUM 7. Selection. The 3 were picked after the holdout was seen (among 36 eval / 10 funded finalists). The holdout itself was frozen first and not re-tuned. Treat HO as lightly used.
LOW 8. day_lock (750 / 1000 / 300) is inert with 1 trade per day; build it anyway for multi-trade books. 9. pm session on early-close days (2026-11-27, 12-24) would arm in a
  closed market: skip. FOMC days: pm entry slip reached 40 pts once. 10. Desk flat_et default 15:55 vs 15:58 here. 11. Lucid's rule on resting buy+sell stops is unchecked
  (Apex bans it; the research flags only Apex). 12. Next roll 2026-12-14: take ATR, anchor and orders from the contract actually traded.

## Daily-rule semantics a live engine must copy (evalcore._walk_day)
- day_take X (net of the $16 round-trip fee): the moment closed day P&L + open P&L - fee >= X, market-flatten the whole account, cancel entries, no more trades today.
  Sim books X minus 1 tick per micro ($20 at 40). The trigger is the best price touched (intraday MFE), so it fires on a touch, not a close.
- With one trade per day it equals a broker-side TP at fill +/- (X + fee) / (2 x micros) points, rounded to a tick. Place it at the fill, in place of the 2R target
  (the 2R target is 6 ATR, far beyond). Add an engine tick watcher that market-outs if price touches the level but the limit is not filled (tester TP needs 1-tick penetration,
  day_take does not). Do not poll equity.
- target_take (eval only): X = the smallest day P&L that passes today, per account, each morning: L = target - profit; Flex also L >= largest_day/0.5 - profit, needs >= 2 trading
  days; skip if no valid L. Sim lands exactly on L: TP at L + 1 tick. The lower of day_take and L wins. Needs each account's EOD profit, largest day, day count.
- day_lock Y: after a CLOSED trade leaves day realised P&L >= Y, no new entries that day (open P&L ignored).
- Breach in the sim = closed balance or end-of-day profit at/below the trailing floor (floor trails EOD peak by $2,000, locks +$100 at +$2,100).

## Exact desk spec (all ET; NQ minis; one entry per day; OCO stop entries; SL/TP shifted to the actual fill)
(a) EVAL: nyam straddle (hm2-straddle-tf30#10), 4 NQ. Fire 09:30:00.000 on the last NQ print before it (accept 09:29-09:31, else skip). ATR30 = Wilder-14 on 30-min bars from 00:00,
    including the 09:00-09:30 bar. Buy stop anchor + 0.25 ATR, sell stop anchor - 0.25 ATR, SL 3.0 ATR from trigger, tick-rounded. Cancel unfilled 10:55:00, flat 11:00:00.
    Median ATR 44 pts (p10 25, p90 74): entry 11 pts off, SL 131 pts ($10.5k).
    - Flex account: TP = day_take 1500 -> 18.95 pts (19.00); also target_take (3 days minimum, 50% consistency). Sim P(pass <= 5 d) 0.78 (first possible day 3).
    - Pro no-DLL account: no day_take; TP = target_take, day 1 = $3,000 -> 37.7 pts (+1 tick). P1 0.79, P5 0.81, bust 0.19 (HO). Separate strategy name from the Flex one.
(b) FUNDED Pro no-DLL: ORB mid (hm-orb-tf5#10), 4 NQ always (no scaling). Arm 11:05:00 from 1-min bars 11:00-11:04: buy stop high + 1 tick, sell stop low - 1 tick (OCO).
    ATR5 = Wilder-14 on 5-min bars from 00:00, including the 11:00-11:05 bar (median 41 pts); SL 3.0 ATR from trigger. TP = day_take 1000 -> 12.7 pts. Cancel 13:25, flat 13:30.
    Request payout when cheque >= $1,000 (balance >= $53,100; also 40% consistency, cycle profit >= $500). Account must be bought with the daily-loss limit OFF. HO E$40 $4,824, 4-day median.
(c) FUNDED Flex: pm straddle (hm2-straddle-tf30#32). Fire 13:30:00.000 on the last print: buy stop anchor + 1.0 ATR30, sell stop anchor - 1.0 ATR30 (27 bars; median ATR 67 pts -> 67 pts off,
    SL 3.0 ATR). TP = day_take 600 net: 7.7 pts at 4 NQ, 10.2 at 3, 15.2 at 2. Size by EOD profit: < $1,000 2 NQ, < $2,000 3 NQ, >= $2,000 4 NQ (set each morning;
    steps down after a payout). Cancel 15:53, flat 15:58 (set flat_et 15:58). Skip early-close days. Request payout when cheque >= $1,500 (profit >= $3,000, 5 days >= $150).
    First payout request locks the floor at +$100 (sim does this). HO E$40 $2,488, median 8 days; fills on 77% of days.

## Verdict
Strategy logic is clean (no look-ahead, no repaint). NOT ready for real accounts: the desk lacks 4 pieces (per-day ATR geometry, a 2nd/3rd fire time with OCO, per-account
take/size state, tick-level take backstop), and the headline odds depend on an unconfirmed Lucid rule. Next safe step: build on paper accounts, confirm Lucid's breach rule.
Side note for tomorrow's NFP evals: a $2,000 stop on a fresh Lucid 50K equals the whole $2,000 limit, so a stop-out plus slippage/fees breaches it. Size so max loss is under about $1,800.
