# gc_nfp pre-flight review (2026-10-01)

Strategy: desk `gc_nfp`, GC 08:30 NFP straddle, 4 contracts, OCO stops anchor +/- 2.0, SL 3.7, TP 7.7 from the fill,
cancel 08:45, flat 09:55, trades only 2026-10-02. Files: `homebase/config.py` (defaults), `homebase/timer.py`,
`homebase/strategies/gc_nfp.py` (tester twin), `tests/test_gc_nfp.py`. Research: `research/nfp-2026-10-02/verify`.
Review only: no backtest was run for this report.

## 1. Look-ahead bias: PASS
- Anchor = last print RECEIVED before 08:30:00.000 (`timer._fresh(..., before=fire_at)`; tester `ctx.last_price`
  at the fire event). Both legs are computed from that print alone. Entry prices are set after the anchor, never from
  the future move.
- Event day comes from a fixed list (`only_dates`, BLS schedule), known weeks ahead. No data from the day is used to
  decide whether to trade.
- Caveat (not a bias, a model gap): the tick files lag the live release by about 1 s, so the sim fills the first print
  through the stop. Live, the stops go out at about 08:30:00 + round trip. If the market has already jumped through
  the trigger, a buy stop rests above/below an already-moved price: it fills at market (worse than modeled) or is
  rejected. The desk places the legs AFTER 08:30:00.000, same as nq930. Not fixable without a pre-placed order.

## 2. Repainting: N/A
Tick-time clock strategy, no bars, no indicator, no signal that can change after the fact.

## 3. Overfitting: FAIL (known, user accepted the risk)
- Four tuned numbers (offset, SL, TP, event subset) on 57 events. The NFP subset was found post-hoc; the 2025-26
  window was already spent on this family on 09-25, so the "holdout" is a consistency check, not a clean test.
- Pass rate ~60% (CI 48-73%). Treat it as a coin flip with a good lean, not an edge proof.
- Offset 2.0 is the stable peak; SL/TP were chosen on the dollar rule (SL < $1,500, TP just over $3,000 net of fees).

## 4. Sizing and risk: PASS with two flags
- 4 GC: a stop-out is 3.7 x $100 x 4 = $1,480, plus $18.40 fees (Lucid GC $2.30 a side). That leaves about $500 of the
  $2,000 limit for slippage = about 11 ticks per contract on the stop. A normal stop-market in a NFP print can slip
  more than that: the sim's pessimistic model (2 ticks plus a cascade) busts 10.5% (6/57).
- SL/TP are attached at entry as a broker-managed OCO bracket (OSO) priced off the TRIGGER, then re-priced to the actual
  fill by `engine._move_brackets` (modify after the fill). Between the fill and the modify the trigger bracket is
  still working, so the position is never naked. If the modify fails the trigger bracket stays: protected, not
  re-priced (journaled `brackets_moved`).
- FLAG A: the two ENTRY legs are not an exchange OCO. The desk cancels the sibling entry when the first fill is
  heard (`engine.on_fill`, `_guard_sibling`). The study found the opposite leg touched within 1 s of entry in 8 of 57
  events. If both fill, the engine's `both_filled_emergency` flattens: a loss of roughly the straddle width plus
  slippage on each side, on every booked account at once. Not in the sim (OCO modeled as one leg).
- FLAG B: all booked evals fire the identical straddle at the same instant, so they win or lose together.

## 5. Live readiness (Lucid): FLAGS, user decision
- Flat time 09:55 ET, before Lucid's 16:10 flat: PASS. No overnight.
- Micro-scalping rule: 24 of 35 sim wins held 5 s or less (69% of profit) vs the 50% flag line. A manual review risk,
  warning at most on a first offense. User decision; the delayed-target variant passes only 54%.
- Cross-account hedging: PASS as built, all accounts get the same legs from one fire. Do NOT give two evals different
  offsets or sizes in the book for this strategy.
- News trading is allowed on Pro, per the verification.
- Desk token handling around 08:30 was built for 09:30: added a renewal quiet window 08:25-08:50
  (`broker/tradovate.renewal_due`) and the P2 view pause around the 08:30 fire (`trading._other_fire_near`). The feed
  quiet windows, the chart-trading lock (09:20-09:35) and the MCP write refusal (09:10-09:35) do NOT cover 08:30: do not
  add accounts, reconnect, or place chart orders 08:20-08:50.

## 6. Funnel sanity: PASS (by design)
One event, one trade day. About 12 NFP a year; the strategy is meant to be sparse.

## Verdict
Safe to run on real evals only if the user accepts: (1) the spent-holdout overfit risk, (2) the desk-side (not
exchange-side) entry OCO and the live-vs-tick-data timing gap, (3) the micro-scalping review risk. The code itself
is not the weak point: it is pinned by `tests/test_gc_nfp.py`. If any of (1)-(3) is not acceptable, run 1 eval first
or leave it shadow (`shadow: true`) and compare the journal to the study.
