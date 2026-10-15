# strategy-review: NQ AM 15-min FVG gap (alone) and NQ AM VWAP pullback (plain) -- 2026-10-14

Drafts (frozen copies, `~/.homebase/strategies/`):
- `nq_am_fvg15_gap.py` sha256 `002710391eb0923fc6067301dec55bdf94dae8758fcc168b776320e6e2ef47b1` (tf 15, stop 2.0 ATR, rr 0.75, max 4, valid 12 bars)
- `nq_am_vwpb_plain.py` sha256 `286f33526ec3e79f880ca537bfc6654078ee3b1cf3402f0415894073efb276ab` (tf 5, trend 30, stop 2.0 ATR, rr 1.0, max 4)

Asked by the owner (2026-10-14): "add AM 15-min FVG gap, alone and AM VWAP pullback, alone to desk".
Both already FAILED their pre-registered unseen read (round-2 note `2026-10-14-round2-seven-families-four-sessions`, lock notes
`2026-10-14-round2-lock-nq_am_fvg15_gap` / `-nq_am_vwpb_plain`). This review judges the code and the Desk fit; it runs no backtest.

## 1. Look-ahead bias -- PASS (both)
- FVG: a gap is read only when the third 15-minute bar has CLOSED (`on_bar` appends to `self.bf` on `bar.end_ns % bfn == 0` or when the next
  bucket opens; `_new_gap` is called with that close time). The limit sits at bar 3's near edge, i.e. already traded. ATR = last 14 closed
  5-minute buckets (`_atr`, `self.b5[-15:]`), re-read only when a bucket closes. One chain walked: 10:00 close -> bars 09:30/09:45/10:00 closed
  -> `l3 > h1` -> `ctx.limit_entry("long", l3, sl=l3-2*ATR, tp=l3+1.5*ATR)`. Nothing after 10:00 is used.
- VWAP pullback: the signal bar is evaluated at its own close (`(bar.end_ns - open_ns) % (tf*MIN) == 0`); `prior = self.sides[-need:]` is read
  BEFORE the current side is appended; VWAP is the running 09:30-anchored value up to and including that bar. Market order at the close, `ref=c`.
- Independent check already done: the screener's own 1-minute implementation matched the tester on build days (trades within 15 %, win within
  3 pts, PF within 0.15) before any unseen read.

## 2. Repainting -- N/A for Pine, PASS for Python
Both act on closed bars only; a signal never disappears after the bar closes. (FVG: a newer gap replaces an older RESTING order by design.)

## 3. Overfitting smell -- FAIL (it did not hold out of sample)
- Tunable inputs: FVG 5 (tf, stop_atr, rr, max_trades, valid_bars), VWAP pullback 5 (tf, trend_min, stop_atr, rr, max_trades). No walk-forward.
- Out-of-sample split exists and was read ONCE (2025-07-01 -> 2026-10-13, 3 micros, 1 tick):

| | FVG gap alone | VWAP pullback plain |
|---|---|---|
| trades (per day) | 401 (1.23) | 183 (0.56) |
| win % / realized RR | 58.9 / 0.81 | 54.6 / 0.88 |
| PF | 1.16 | 1.06 |
| net | +$10,768 | +$2,354 |
| halves | +$12,298 / -$1,530 | -- |
| long / short | +$6,912 / +$3,856 | +$3,279 / -$926 |
| 2 ticks / without 3 best days | +$10,431 / +$6,753 | -- / -$1,186 |
| months at 55 %+ | 75 % | 44 % |
| Monte Carlo | 90.0 % | 63.3 % |
| LucidPro 50K no-DLL eval | pass 36.4 %, bust 63.6 % | pass 30.2 %, bust 69.8 % |

- Pre-registered floor (win >= 58 %, PF >= 1.2, C lines): FVG missed PF (1.16) and the second half; VWAP pullback missed PF, the short side,
  the best-3-days line, months and Monte Carlo. FVG's edge ran Jul 2025 - Jun 2026 (56-73 % a month), then Jul-Oct 2026 42/42/48/38 %.
- Filters stacked: none (both are the "alone" rule on purpose).

## 4. Position sizing and risk -- WARN
- Desk size is the tested size: 1 micro. Stop = 2 x ATR(5-min) is wide: unseen median 82 pts (FVG) / 85 pts (VWAP), build-day max 558 / 249 pts
  (= $1,116 / $498 on ONE micro; worst build trade -$480 / -$392; worst build day -$806 / -$490). A LucidPro 50K max loss is $2,000 trailing:
  put `max_risk_usd` on any account (about $400) before assigning one; the door then refuses an entry whose stop is too far.
- VWAP pullback: market entry with SL and TP sent with it (the Desk's door insists on a stop held at the broker); `move_brackets_to_fill`
  re-prices both after the fill (the "a modify's 200 is not done" demo-checklist item still applies before a funded or live account).
- FVG: a RESTING LIMIT entry with a bracket that is cancelled and re-sent every time the 5-minute ATR moves (`new5` branch).
  **The Desk door refuses limit entries ("Limit entries are not built yet.", `labrun/door.py` NO_LIMIT).** It can be hosted in SHADOW
  (the tester's own `_Sim`, `labrun/livectx.py`, `shadowfills.py`) but can NEVER be booked on an account until limit entries are built.

## 5. Live-readiness (Lucid) -- PASS
- Flat: both flatten at 12:55 ET (window 08:00-13:00); the 16:10 flat is never in play.
- Microscalping (<5 s and > 50 % of profit): 0 trades under 5 s in 1,289 + 585 build trades and 401 + 183 unseen; median hold 28-47 minutes.
- Hedging / multi-account: none; one position at a time, one market.
- Exits: build-day mix FVG sl 339 / tp 585 / time 365; VWAP sl 155 / tp 188 / time 242 (a third of trades ride to the 12:55 clock).

## 6. Funnel sanity -- PASS
1.23 and 0.56 trades a day on unseen (>= 2 a month by a wide margin). The VWAP pullback is below the 1-a-day line the owner set in round 1.

## Verdict
**Safe to run in shadow only (OFF, no account, no order sent).** Neither strategy is safe to book on any account: both failed the
pre-registered unseen bar, and the FVG gap additionally cannot be booked at all (limit entries are not built on the Desk). If the owner ever
wants an account on the VWAP pullback: paper first, `max_risk_usd` about $400, long side only is the only part that held (short lost
-$926 unseen and -$1,092 on build days) -- that would be a NEW rule and needs its own build, lock and one read.
No code was rewritten by this review.
