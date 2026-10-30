# Shadow bar for the 3 shadow rules (written 2026-10-21 ~09:20 ET, BEFORE any shadow day exists)

The owner put three Amendment-J passes on the Desk in SHADOW (paper, no money): NQ VWAP touch on ADX days (vh_i10 box g_lvl30_pts60-r2),
EMA x VWAP + RVOL (vh_i16 box fast_n13_own1-r1p5), RVOL break 5m (vh_i17 box m2_atr2-r2), each as 3 session drafts (nyam / mid / pm).
Shadow months (from the first shadow day, expected 2026-10-22) are the only months nobody has read. This bar is fixed now and is not
changed after a shadow day is seen.

## What the test months say to expect (per rule, all 3 sessions together)
| Rule | Trades / week | Avg trade | Per-trade spread (sd) | Win | Break-even |
|---|---|---|---|---|---|
| VWAP touch, ADX days | 2.5 | +$80 | $1,576 | 41.3 % | 38.6 % |
| EMA x VWAP + RVOL | 2.3 | +$74 | $1,645 | 48.9 % | 46.1 % |
| RVOL break 5m | 5.2 | +$43 | $1,676 | 38.6 % | 37.1 % |

## The bar
1. **Fidelity first (the copy is the rule).** The Desk's daily "Matched the backtest" line: on >= 90 % of shadow days every shadow trade
   matches the Lab backtest of the frozen code. Below 90 % after 4 weeks: that rule's shadow record does not count until the copy is fixed.
2. **Stop (checked weekly once a rule has 30+ shadow trades):** its shadow average trade is below the test-month average minus 2 standard
   errors -> switch it off, failed. Lines: at 30 trades -$496 / -$527 / -$569; at 60 trades -$327 / -$351 / -$390; at 130 trades -$197 /
   -$215 / -$251 (VWAP touch / EMA x VWAP / RVOL break).
3. **Pass, read once at 26 weeks of shadow** (about 65 / 60 / 135 trades): not stopped; net > 0 after costs AND still > 0 with one more
   tick a side; win rate >= the break-even of its own realized reward-to-risk (Amendment J); fidelity (1) met.

## What a pass would and would not mean (said now)
With a $1,600 spread a trade, 26 weeks cannot prove a +$40-80 edge: proving it at 2 standard errors needs ~1,500 trades (~10 years). If a
rule's true edge is what the test months showed, it passes this bar about 62-66 % of the time; a rule with NO edge passes about 50 % of
the time. So shadow is mainly a check that the Desk copy trades like the engine, and a stop for a rule that has clearly broken. A pass
means "not contradicted", not "proven". Their Monte Carlo already says they are not robust (MC_PASSES_J.txt: money in 69-73 % of runs,
negative with winners -15 %).
