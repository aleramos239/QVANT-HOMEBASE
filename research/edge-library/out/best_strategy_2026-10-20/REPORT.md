# The best simple NQ strategies on file (2026-10-20)

Asked (owner, 2026-10-20 00:25): inspect every strategy tested, find what works and in what combination, build the best simple
strategy, 1-2+ trades a day, more than one if possible, 3:1 block walk-forward as the out-of-sample method, **do not touch the
out-of-sample until the owner says.**

**Nothing here has read a day after 2025-06-30.** Every number is the build days (2021-09-22 .. 2025-06-30, 948 sessions),
NQ, 1 contract, after costs ($4 a round turn + 1 tick on every market or stop fill), engine tick replay, taught lane
(`bp.py taught run`). The walk-forward is ready to run (section 6) and was not run.

## 1. The answer

Three simple rules, each one trigger, each with its own cause. Together on one account: 2.6 trades a day.

| | Strategy | When | Trades a day | Avg trade | PF | Sharpe | Months won | Worst DD | Unseen days |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Open-side FVG** | 10:15-15:00 | 1.34 | $108 | 1.30 | 2.07 | 78 % | $15.1k | family's months already read (7 walk-forwards + the Desk, 10-19/20) |
| 2 | **10:00 displacement** | 10:00-10:45 closes | 0.64 | $171 | 1.25 | 1.25 | 65 % | $17.6k | fully blind |
| 3 | **13:30 first bar** | 13:45 | 0.63 | $93 | 1.38 | 1.64 | 72 % | $7.1k | partly read (same entries, other exit) |
| | **All three, 1 NQ each** | | **2.61** | **$120** | **1.29** | **2.36** | **78 %** | **$25.3k** | |

All three together, net by year (1 NQ each): 2021 (Sep-Dec) +$29.0k · 2022 +$110.9k · 2023 +$24.5k · 2024 +$80.3k · 2025 (Jan-Jun) +$52.1k.
Every build year is positive. Net / worst drawdown 11.7. Daily correlation between the three: 0.31, 0.10, -0.08.

![equity](equity_build_days.png)

With harsher fills (audit: targets need 2 ticks through, +1 extra tick on market and stop fills, $5 a round turn, the two
tape-hole trades booked as plain stops): **#1 $96, #2 $162, #3 $82 a trade.** All three stay above the $70 floor.

If only ONE strategy: **#1, the open-side FVG** (most trades, highest Sharpe, stable to every setting). If the owner wants the
cleanest out-of-sample test: **#2** is the only one whose unseen days nobody has ever read.

## 2. The rules, in plain words

### Strategy 1 — Open-side FVG (sheet `cl_fvg_oside_15_mid_r1_t2_gap0p1`, family `fvg_oside`)
1. NQ, 15-minute candles from 09:30. Mark the 09:30 open.
2. At each 15-minute close: price above the 09:30 open = longs only; below = shorts only.
3. A fair value gap on that side: three candles, the third's low above the first's high (up gap; mirror for down), at least
   0.1 x ATR(14) tall, all three candles from 09:30 on.
4. Rest a LIMIT at the near edge of the newest such gap (a newer gap or a flip of side moves it). Cancel at 15:00.
5. Stop at the middle candle's far end (median 37 points). Target 1:1.
6. At most 2 trades a day, one at a time. Flat 15:58.

Why it works: above the open buyers are in control, and the newest up gap is their unfilled buying; price comes back to it and
they defend it. The traders fading the open's side pay. (Below the open: the mirror.)

### Strategy 2 — 10:00 displacement (sheet `cl_am_disp15_vwap_10to11`, family `displace`)
1. NQ, 15-minute candles. Only the candles that close at 10:00, 10:15, 10:30 or 10:45 (the 09:45-10:00 candle through the 10:30-10:45 candle).
2. The first of them whose body is at least 1.5 x ATR(14) of the candles before it (and is on the VWAP side, step 3).
3. Long if it is green and closes above the session VWAP; short if red and below. Market order at its close.
4. Stop at the candle's other end. Target 1:1. One trade a day. Flat 15:58.

Most of the money is the 10:00 close (the 09:45-10:00 candle): 285 of 608 trades. On days without a 10:00 data release it
averages $282 a trade; only 37 trades fall on a 10:00 release day, and dropping them changes nothing ($176 vs $171). The owner's
first sheet started at 09:30 (adding the 09:30-09:45 candle): $67 a trade. The 10:00 start was chosen on build days: say so in the luck count.

Why it works: a candle that big in the first hour is orders that had to fill at any price; the push carries on. The VWAP side keeps
it with the session's buyers or sellers. (The owner's original used EMA20 instead of VWAP: $177, same result. VWAP is a session
level, the kind of indicator the owner keeps.)

### Strategy 3 — 13:30 first bar (sheet `cl_pm_first_bar_cdl_ema_15`, family `first_bar_mom`)
1. NQ, the 13:30-13:45 15-minute candle.
2. At its close: green and above the EMA20 of 15-minute closes = buy; red and below = sell. Otherwise no trade.
3. Stop at the candle's other end. Target 1:1. One trade a day. Flat 15:58.

Why it works: the first afternoon candle after lunch shows which side came back; with the day's trend it carries into the close.

## 3. Every variant (build days, 1 NQ)

See `variants_table.md` (taken straight from the result files). The short version:

| Strategy 1, the knob | trades a day | avg | PF | Sharpe |
|---|---|---|---|---|
| any gap, 1 a day (owner's sheet) | 0.94 | $99 | 1.27 | 1.51 |
| any gap, 2 a day | 1.48 | $98 | 1.29 | 2.03 |
| **gap >= 0.1 ATR, 2 a day (pick)** | **1.34** | **$108** | **1.30** | **2.07** |
| gap >= 0.25 ATR, 2 a day | 1.07 | $121 | 1.30 | 1.80 |
| any gap, 3 a day | 1.64 | $87 | 1.25 | 1.88 |
| any gap, no cap | 1.66 | $86 | 1.25 | 1.88 |
| 0.5R target (70 % win), 2 a day | 1.52 | $54 | 1.23 | 1.56 |
| fixed 37-pt stop and target | 1.37 | $53 | 1.16 | 1.35 |

- The gap knob orders cleanly: bigger gap = bigger average, fewer trades. Not a lucky cell.
- Trade 2 of the day pays as much as trade 1 ($120 vs $102), every year. Trade 3 adds nothing: cap at 2.
- Every entry hour 10:00-14:00 makes money.

| Strategy 2, the knob | trades a day | avg | PF |
|---|---|---|---|
| body >= 1.0 ATR, 10-11 | 0.82 | $90 | 1.14 |
| **body >= 1.5 ATR, 10-11 (pick)** | **0.64** | **$171** | **1.25** |
| body >= 2.0 ATR, 10-11 | 0.36 | $219 | 1.31 |
| body >= 1.5 ATR, stretched to 10:00-15:00 | 0.91 | $117 | 1.17 |

- Its whole edge is the 10:00 hour. Stretching the window adds trades worth about $0 (12:00 and 14:00 entries lose).

## 4. What proves it (and what does not)

| Test | Result |
|---|---|
| Beats random entries, both sides, same exits (the house line) | 1: 100 % · 2: 100 % · 3: 100 % |
| Fair drift check: rule vs random SAME-SIDE entries on all build days, same exits, 10 seeds | 1 long +$106, short +$146 a trade over random; 2 long +$132, short +$244; 10 of 10 seeds each |
| Is the 09:30 side the edge? Same FVG, same fixed 37-pt bracket | with the open's side $53 · with EMA20 side $31 · no side $12 |
| Is the middle-candle stop the edge? | middle candle $108 · fixed 37 pt $53 (same entries) |
| Both sides make money | 1: long $67k / short $70k · 2: long $48k / short $56k · 3: long $29k / short $27k |
| Monte Carlo, 1,000 reshuffles | 1: 100 % · 2: 99.3 % · 3: 99.9 % profitable |
| Without the best 1 % of days | 1: +$102.2k · 2: +$61.3k · 3: +$32.9k |
| Worse fills (from the trades): +1 tick each fill / +2 ticks | see the audit note in section 7 |

Red flags, said plainly:
- **NQ only, 15-minute only.** Strategy 1 makes $4 on ES and -$19 on GC; 30-minute bars lose. Strategy 2 loses on ES, flat on GC,
  loses on 5-minute bars. Almost everything in Homebase works only on NQ; still, a market-specific edge is weaker evidence.
- **2023 is flat for strategy 1** (-$3 a trade). It lives on 2022 and 2025. Strategies 2 and 3 carry 2023 in the stack.
- **The lane's own same-side random line fails** for 1 and 2. That line draws random trades only on the days the rule fired, so it
  already knows the day went above (or below) the open; on all days the rules win by $106-244 a trade (row 2 above).
- **Selection:** about 45 sheets of the open-side FVG family and 40 of the displacement have been read on build days. The picks are
  the middle of monotone knobs, not best cells, but the luck risk is real.
- **Build days are a lead, not proof.** In this repo a build-day pass has held unseen about 1 time in 5 to 1 in 10.

## 5. How they fit together
- They trade different hours: #2 10:00-10:45 closes, #1 mostly 10:15-15:00 (median hold 23 minutes), #3 13:45 on.
- #2 is open at the same time as a #1 trade on 39 % of its trades, #3 on 26 %. All three on one account: at most 3 positions at once (1 NQ each).
- Size by a fixed number of contracts, not by dollar risk: strategy 1's small-stop setups (under 25 points) are about break-even,
  and dollar-risk sizing gives them the most contracts (that is what cut fvg_odir from $49 to $7 unseen).

## 6. The out-of-sample, ready to run on the owner's word (NOT run)
The house method, the 3:1 block walk-forward, per sheet (it writes its claim before opening any test day, and can never be re-run):
```
cd research/edge-library
.venv-research/bin/python bp.py taught wf cl_am_disp15_vwap_10to11
.venv-research/bin/python bp.py taught wf cl_pm_first_bar_cdl_ema_15
.venv-research/bin/python bp.py taught wf cl_fvg_oside_15_mid_r1_t2_gap0p1
```
- #2 is fully blind: its walk-forward is a clean test.
- #3's entries were walk-forwarded on 2026-10-19 with a 30/30 bracket (owner_pm_first_bar_15); its test months are partly seen.
- #1's family (fvg_oside): 7 walk-forward stores of its 3 x 1m-ATR parents were read 2026-10-19 20:34 to 2026-10-20 00:44 ET (another
  session's JJ-plan night run), plus the Desk's read; their results were in the notes before #1's gap and cap were chosen. A walk-forward
  of #1 is not blind. The only fully clean test left for #1 is new days: forward / shadow from 2026-10-17 on.
- At 0.6 trades a day, #2 and #3 alone reach about 180 walk-forward trades; the 200-trade line (P6.4) may fail on count, not on edge.

## 6b. RESULT, 2026-10-20 15:31 ET (owner: "just check the OOS for number 2"): #2's 3:1 block walk-forward FAILED
- Stitched test months: 130 trades, +$3,855, $30 a trade, PF 1.04. P6.1 pass; P6.2 random 75.5 % (need 95), P6.3 win rate 55.4 %
  vs 57.4 % needed, P6.4 130 trades (need 200): FAIL. NOT PROVEN under the house law. 5 of 15 test months stood aside.
- Each cell alone on the same months (`taught wf-each`): the sheet's own 1R cell 188 trades, $123, PF 1.17; its unseen part 47
  trades +$3,462. 0.75R $64; 1.25R $34 (unseen -$4.7k). The walk's monthly pick and stand-asides cut the 1R cell's $123 to $30.
- Full metrics and the lines each strategy passed: `METRICS.md`. Raw output: `walkforward_strategy2.txt`.

## 7. Audit (independent, read-only, 4 agents)
- **No look-ahead.** A rebuild from the raw NQ prints, using only data before each decision, reproduced 3,025 of 3,025 stored trades
  (entry time, side, stop, exit, net) on 934 build days. Rewriting the future on synthetic days never changed an earlier decision.
- **Trade replay (blueprint lines 1.1-1.5):** 53 of 53 hand-rebuilt trades match to the cent. Over all trades: 0 entries outside the
  window, 0 days over the cap, 0 overlapping positions, 0 trades not flat by 15:58.
- **Fills and costs:** limits fill only 1 tick through, at the limit; market entries pay 1 tick; stops pay the gap + 1 tick; ticks are
  replayed (no same-bar guessing). Average trade at +1 / +2 ticks on every fill: #1 $98 / $88 · #2 $161 / $151 · #3 $83 / $73.
- **Found, small:** two FVG trades were decided at the first print after a tape hole (-$3.8k of $137k); 41 of #3's trades use the
  engine's 0.25 x ATR stop floor instead of the candle (they net $0); on market entries the stop keeps its distance but moves with the
  fill (dollars per R unchanged).
- **Found, process (major):** #1 and #3 were designed after their parents' unseen months had been read (see section 6). Build-day
  numbers are unaffected; their walk-forward would not be blind.
- **Paperwork:** the FVG sheet's not_run text says the side is read on 5-minute closes (it is 15-minute) and lists two gap-size lines;
  the EMA displacement sheet's taught line says 09:30. The trades follow the run settings. The sheets were left unedited so their
  stores still match them.
- #2's EMA20 twin shares 541 of 568 trades with the VWAP version: one strategy, book one.

## 8. Files
- Sheets: `research/edge-library/taught/cl_*.json` (this session's 37), results in `~/.homebase/taught/<sheet>/`.
- `variants_table.md` every variant · `equity_build_days.png` · `fair_drift_control.txt` · `WHAT_WORKS.md` the inventory of every
  store in the repo (613 items, 10 readers, 3 syntheses, a critic) · `NEW_RUNS.md` this session's runs in order · scripts
  `combo.py` (stacks), `split.py` (trade number / hour / year), `vtable.py`, `chart.py`.

## 9. Not done
- No walk-forward, no unseen read (owner's order).
- Not on the Desk. Strategy 1 needs limit orders, which the Desk cannot book yet. Strategies 2 and 3 are market orders at a bar close.
- No blueprint card / lock: the blueprint's standard exit table has no candle stop, so these live on the taught route.
