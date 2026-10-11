# Strategy review: NQ 08:30 Candle Body (Lab draft `nq_0830_candle_body`)

Reviewed 2026-10-11 on the draft's source (`~/.homebase/strategies/nq_0830_candle_body.py`) and its build-day run
`20261011-000143-draft_nq_0830_candle_body-7b6e` (qty 1, $4 + 1 tick, 2021-09-22 to 2025-06-30). Scope: promote to the Desk OFF / shadow, no account.

**The rule:** at the close of the 5-minute candle that opens 08:30 ET (08:35:00), go with its direction if its body is at least `body_r`
of its high-low range; market entry, stop `stop_pts` and target `rr` x stop, both re-priced to the fill; one trade a day; flat 15:55.
Defaults: body 0.7, stop 30 pts, 3R. Settings the Desk's Setup panel may change: `body_r`, `stop_pts`, `rr`.

## 1. Look-ahead bias: PASS
The signal is read in `on_bar` on the bar whose `end_ns` is exactly the session start + 5 minutes. It uses that bar's `o/h/l/c`, all closed
at the moment it runs. The order is a market order sent after the close, so it fills on prints after the bar. No daily bars, no indicator, no
value from a later bar. Walked the one chain: `share = |c - o| / (h - l)` -> side by `c > o` -> `ctx.market(...)`.

## 2. Repainting: PASS (N/A for Pine)
A closed 5-minute bar does not change. The strategy plots one value (`body_share`) and nothing it plots feeds a later decision.

## 3. Overfitting smell tests: WARN
- Three settings (body, stop, target) and one filter: within the "fewer rules" bar.
- The default box is the best-looking of 96 boxes on the build days (body 0.5/0.7 x 8 stops x 6 targets) and of 27 more cells swept for this
  page. A heat map that is green on the build days is a coin flip next year (finding 2026-10-05). The test days (2025-07-01 on) are NOT read for
  this rule: its one out-of-sample read is still owed under the blueprint before any claim beyond "worth watching".
- 2022 is 45 % of the build-day net ($18.3k of $40.4k); 2025 (part year) is the weakest year ($2.1k, Sharpe 0.46).
- Nearly all profit is the short side ($35.4k vs $5.1k long): partly a falling market in the build days.

## 4. Position sizing and risk: WARN
- One mini (qty 1): stop 30 pts = $600 + costs; worst trade on the build days -$619. One trade a day, so the daily loss is the trade's loss.
- A bigger size puts one losing trade near the account's $2,000 trailing limit: 3 minis lose $1,800 + costs on one stop. The prop sim's best
  eval sizes are "two wins and you are through" and one loss nearly busts it. Keep the Desk size at 1-2 minis until the owner decides.
- The bracket is re-priced from the fill (`move_brackets_to_fill`): the stop is sent or moved after the fill, not in the entry's body. This is the
  Desk's open item for EVERY Lab strategy (the demo step must prove the stop-only bracket bodies before funded / live). Paper and shadow are fine.
- Entry is a market order seconds after the 08:30 release candle closes: a fast market can fill worse than the tester's 1 tick.

## 5. Live-readiness (Lucid): PASS
- Flat 15:55 ET, before Lucid's 16:10.
- Holds: shortest 51 s (2022-02-04), most are 10 minutes to 2 hours. No holds under 5 s, so the micro-scalp rule is not touched.
- One trade a day, one market, no hedging.

## 6. Funnel sanity: PASS
228 trades in 44 months, about 5 a month at the default (447 at body 0.5, 77 at body 0.85). Over the 2-a-month line.

## Parity with the research box (body_r 0.7, pts 30, 3R)
227 of 228 trades match the research run to the dollar. One extra Lab trade (2022-08-05 short, -$609, a day the research run did not
take) and one half day (2022-11-25: Lab exits at its 13:00 clamp, +$806 vs research +$821). Net: Lab $40,448 vs research $41,072.

## Verdict
**Safe to run on sim / shadow (promote OFF, no account).** Before an account: the owner's decision on size (1-2 minis). Before funded or live:
the demo step on stop-only bracket bodies (open for all Lab strategies), the one out-of-sample read of the test days, and live prices that are
real-time (the chart feed was 10 minutes late on 2026-10-06; the Desk's door refuses late prices).
