# O4ASr0fh7O8 — "This Guy QUIT His Job for PROP TRADING. So I STOLE His Strategy" (IQCapital, 25:29)

Watched 2026-10-10 (captions + frames, downloaded with Chrome cookies on the owner's yes). Source is a prop-firm promo
(IQ Capital sells the indicators and the $9 challenge). Owner's trader is called "Trader Math" (TM).

## Claims (not checked)
- TM, last 22 days: +$33.95k, profit factor 4.03, 126 trades, discretionary exits and scale-ins.
- Host's "objective version" (TradingView, MNQ 15m, 2025-04-09 → 2026-09-07, 100K account):
  +$19,706 (19.7 %), PF 1.381, 486 trades, win 44.65 %, max drawdown $4,172 (3.56 %).
  This window crosses the test days (2025-07-01 →): it says nothing under the blueprint.

## Rules as taught (long only is shown; no short side given)
- Market / bar: NQ family (MNQ shown; ES and BTC "similar"), 15-minute. He says 30 m or higher should also work.
- Filter 1: "Hurst proxy" > 50 (scale 0-100). Described only as "price range compared to volatility".
  EXACT FORMULA NOT GIVEN (it is in the seller's indicator). Host: an AI rebuild "won't be correct".
- Filter 2: autocorrelation of price direction now vs 5 bars ago, over the last 20 bars, <= -0.1
  (slightly anti-persistent). Lag / return definition "glossed over".
- Trigger: bar CLOSES above the previous 5 bars' high (current bar excluded). Market order at that close (or next open).
- Exit (objective version): target = entry + 5 x ATR(20), fixed. Stop = 4 x ATR(20) below entry, TRAILING with the highest high.
  Both set from the ATR at entry.
- Size: contracts so the stop risk stays under the firm's per-trade loss cap (0.5 % funded, 1 % eval).
- Not testable: discretionary exit, scaling in on pullbacks (host has no objective rule).

## Open questions for the rule sheet (owner checks before any run)
1. Hurst proxy: pick a published one (e.g. rescaled-range / variance ratio over N bars) — the video gives none.
2. Autocorrelation: lag 5 on 1-bar returns over a 20-bar window? ("5 bars ago" could also mean 5-bar returns).
3. Entry price: close of the trigger bar, or open of the next bar.
4. Stop: trails the highest HIGH or highest CLOSE; does it only ratchet up.
5. Short side: mirror, or long only (as shown).
6. Session: all hours (chart shows ETH) or RTH only; flat by 15:55 would break the 5 ATR / trailing idea on 15 m.

## Frames / transcript
Working copy (temp): $TMPDIR/o4asr (mp4, vtt, transcript.txt, frames every 30 s).

## VERDICT 2026-10-11: DROPPED (owner)
Run AS TAUGHT in the taught lane on the build days (sheet `taught/tm_hurst_ac_break.json`, rule sheet
`taught/RULE_SHEET_O4ASr0fh7O8_2026-10-11.md`): 411 trades, -$81 a trade, -$33,114, PF 0.89, eval odds 21.7 %, beats 0 % of random
longs, 1 of 11 lines. The same 5-bar break with both filters off: 1,807 trades, +$22, PF 1.03, still fails. The filters make it worse.
Unseen days never read. Vault finding: `50-Permanent/Findings/2026-10-11-hurst-autocorr-break-loses-as-taught.md`.
Family `hurst_ac_break` (engine/families/hurstac.py) and its tests stay as a tested block.
