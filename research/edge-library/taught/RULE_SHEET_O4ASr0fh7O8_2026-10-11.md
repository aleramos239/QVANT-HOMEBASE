# Rule sheet: "Trader Math" trend-dip breakout (video `O4ASr0fh7O8`, IQCapital, 25:29)

Written 2026-10-11 for the owner to CHECK BEFORE ANYTHING RUNS. Nothing here has been run. Notes: `videos/O4ASr0fh7O8.md`.
Parts: **Taught** (the video's rule, with time marks), **Pick** (what the video does not say, my choice, yours to change),
**Would run** (what the engine does), **Not the video**, **Can it run now**.

## 1. Taught

| # | Part | The video says | Time |
|---|---|---|---|
| T1 | Market | NQ family (MNQ shown). ES, MES and a little BTC "mostly similar" | 1:38, 22:54 |
| T2 | Bars | 15-minute, "exclusively". 30 minute or higher "no reason it fails" | 1:49 |
| T3 | Side | Long shown. Short side never shown | 10:42 |
| T4 | Filter 1 | "Hurst proxy" above 50 (scale 0-100, not 0-1). "Compares the price range to volatility"; higher = price moves persistently | 4:35, 5:02 |
| T5 | Filter 2 | Autocorrelation of price direction: now vs 5 bars ago, over the last 20 bars. Must be -0.1 or lower (slight anti-persistence = a short pullback inside the trend) | 6:41, 8:39 |
| T6 | Trigger | The bar CLOSES above the highest high of the previous 5 bars (current bar not counted). Only while T4 and T5 are true on that bar | 9:50, 10:35 |
| T7 | Entry | Market order at the close of the trigger bar ("at the close or the open of the very next bar") | 11:05, 19:25 |
| T8 | Target | 5 x ATR(20), fixed, set from the ATR at entry | 11:43, 14:18 |
| T9 | Stop | 4 x ATR(20) below entry, set from the ATR at entry; it TRAILS: moves up with the highest high reached in the trade, never down | 14:30, 15:12 |
| T10 | Size | Contracts scaled so a stop-out costs under the firm's per-trade cap (1 % eval, 0.5 % funded). Example: 5 MNQ = $10 a point | 15:57, 16:17 |
| T11 | Not objective | His real exits and his scale-ins on pullbacks are by feel. The host has NO rule for them | 11:21, 24:00 |

Host's own numbers for this coded version (TradingView, MNQ 15 m, 2025-04-09 to 2026-09-07, 100K account): +$19,706,
PF 1.381, 486 trades, win 44.65 %, max drawdown $4,172. The trader's own claim (22 days: +$33.95k, PF 4.03, 126 trades) is
the discretionary version, not this one. Both are claims until we repeat them.

## 2. Pick (the video does not give it; each is open to you)

| # | Gap | My pick | Why |
|---|---|---|---|
| P1 | Hurst proxy formula | Variance ratio: H = ln( Var(5-bar change) / Var(1-bar change) ) / (2 x ln 5), over the last 20 bars, x 100, clamped 0-100 | Centred at 50 for a random walk, like the video's line (the chart line swings 30-70 around 50). A classic rescaled-range Hurst over 20 bars sits near 65 for a random walk, so "above 50" would be almost always true |
| P2 | Autocorrelation series | Correlation of the 1-bar close change with the 1-bar close change 5 bars earlier, over the last 20 bars | The video's chart line swings between -0.4 and +0.4. A correlation of price LEVELS would sit near +1 |
| P3 | Entry price | Open of the bar after the trigger bar | The engine fills a bar-close signal at the next open. T7 allows both |
| P4 | ATR | ATR(20), simple true-range average, frozen at the entry bar | T8, T9 say "set when the entry is taken" |
| P5 | Trailing | Stop = highest HIGH since entry minus 4 x ATR(entry). Checked on every bar; the stop only rises | T9 |
| P6 | Hours | All sessions the engine has (Asia, London, pre, NY morning, midday, afternoon, evening), flat 15:58 ET | His chart shows 24-hour bars. The house rule is in and out the same day |
| P7 | One position | One trade at a time; no scale-in; no pyramiding | The video's objective version closes everything at the target (24:56) |
| P8 | Trades a day | No cap (the video gives none) | T6 only |
| P9 | Short side | Not run (not taught) | T3. A mirror would be a separate sheet |
| P10 | Markets | NQ (main). ES as the only other, shown not judged | BTC is not in the engine |

## 3. Would run (the taught lane, `bp.py taught`)

- One cell as taught, plus 8 neighbours: stop x {0.75, 1, 1.25} crossed with target x {0.75, 1, 1.25}
  = stop 3 / 4 / 5 ATR, target 3.75 / 5 / 6.25 ATR. Neighbours show fragility; none is picked from.
- Control: the pipeline's random entries at the same exits, and random LONG-only entries (a long rule must beat random longs).
- Bars: 15 (the video) and 30 (the video allows it). Build days only, 2021-09-22 to 2025-06-30. The unseen days are read once, only on your word.
- Reads: metrics per year then combined, prop odds on the PLAIN row (stress beside it), lines P3.2-P3.10, the lock's 3.3-3.8, reshuffled runs, random line.
- Settings the new rule needs: `hurst_min` 50, `ac_max` -0.1, `ac_lag` 5, `ac_win` 20, `h_win` 20, `break_n` 5, `atr_n` 20.

## 4. Not the video

- The size rule (T10) is not run: the engine trades 1 contract per cell; sizing steps are read afterwards (phase 5).
- His discretionary exit and scale-ins (T11) are not run.
- Flat at 15:58 cuts any trade still open; the video's chart holds across sessions. A trail of 4 ATR on 15 minutes often needs more than one session.
- The host's TradingView result uses 15-minute bars on a 100K account, one contract count unknown; ours is per-contract.
- BTC and ES micro are not run (see P10).

## 5. Can it run now?

NO. Three pieces are missing, each is code to build and lock before a run:

| Missing | Why | Nearest that exists |
|---|---|---|
| Entry rule `hurst_ac_break` (T4 + T5 + T6 as one rule) | No Hurst or autocorrelation block; "a card names no indicator" | `donchian` n=5 on 15 m is T6 alone; filter `er trend` is the closest cousin of T4 |
| Trailing stop exit (T9) | `limits.trail_atr` is "NOT IN VERSION 1"; the taught lane takes a fixed stop or a structure stop only | none |
| ATR(20) and 5 / 4 x ATR sizes (T8, T9) | Standard table: stops 1.5 / 3 x ATR(14), targets 0.5-3 x the stop | The taught lane takes fixed points; ATR(20) x 4 would have to be a points value per trade |

A faked version (donchian 5 + standard stops) would NOT be this strategy; I would not report it as a test of the video.
