# Strategy review: setup B, one strategy per Apex 300K account (2026-10-30)

Setup B: ORB (nq_overnight_orb_micro) $1k · FVG side 0.75R (nq_fvg_oside_15_r075) $2k · Candle Break APEX300
(nq_candle_break_apex300) $2.5k · FVG15 VWAP .25/60/1R (nq_fvg15_ovw_g25_s60_r1) $500 · FVG15 VWAP .1/1.5R
(nq_fvg15_ovw_g10_s25_r15) $1k, each alone on one of the 5 PAAPEX accounts, all MNQ.

Code reviewed: the exact source the VPS Desk runs (`~/.homebase/desklab/<name>.json`, sha256 checked). The backtests
behind the cycle sim used the same source and settings (only an `own_stop = True` heat-map flag differs on two of them).

**Verdict: the five strategies are safe to run. Setup B is NOT ready to book. Fix 1-4 first.**

## Per strategy

| Strategy | Look-ahead | Repaint / fills | Sizing at B's risk | Exits | Fit |
|---|---|---|---|---|---|
| ORB | PASS | PASS | 4-8 micros; its own 10-micro cap is ignored on a risk row (never binds: stops 59+ pts) | PASS, flat 15:30 | 4 settings, from the source video |
| FVG side 0.75R | PASS | PASS (live touch fills may add trades) | median 30, max 133 micros: **the default Most 20 caps ~70%** | PASS, flat 15:55 | 2 settings |
| APEX300 | PASS | PASS | median 18, high 38, max 200 micros: **Most 20 caps 42%**; **$2,500 is over Apex's $2,250 per-trade loss limit** | PASS, flat 15:55 (backtest 15:58, 5.6% of trades) | **1R picked after seeing test months** |
| FVG15 VWAP .25/60/1R | PASS | PASS | 4 micros = $480 | PASS, flat 15:55 | 3 settings, 173/180 boxes green |
| FVG15 VWAP .1/1.5R | PASS | PASS | 20 micros = $1,000, exactly at Most 20 | PASS, flat 15:55 | same table |

Trades under 5 seconds are rare in every backtest (2-16 per strategy over 5 years): no microscalping problem.

## Setup issues (must fix before booking)

1. **No hedge block between accounts.** The Desk refuses an opposite-side NQ/MNQ entry across accounts only for accounts in an
   ON account cycle (`engine_groups.hedge_refusal`, called from `engine_lab.py`). One-strategy-per-account bookings get no
   check. B's five strategies held opposite sides at the same time **247 times on 113 of 1,257 days (9%)** in the backtests.
   Apex bans cross-account hedging. The cycle sim already skipped those trades, so B's numbers assume a block that does
   not exist yet. Fix: a Desk change that applies the hedge check to a chosen set of accounts (or all Apex accounts),
   tested, before B goes on.
2. **Most box per account.** A risk row is capped by the row's Most (default 20 micros). Set it on purpose: ORB 10,
   Side .75 140, APEX 170, V60 4, V.1 20. 170 is also Apex's half-size limit until the account is past $7,600 (one APEX
   backtest trade wanted 200).
3. **APEX at $2,500 breaks Apex's 30% rule** at the start ($2,250 per-trade limit). The Desk does not enforce this rule,
   and its sizing rounds up to 10% over the risk. Use **$2,000**. The sim with APEX $2k: 100% / 17 days / mode 8 / 3.06
   accounts at $10k / worse fills 97.9% / every start year 100% (vs $2.5k: 100% / 15 days / 97.5%).
4. **Leave the account cycle.** Side .75 and APEX are booked on all 5 accounts through the ON cycle, which overrides any
   per-account risk. Turn the cycle off and rebook each strategy on its one account. Never book another BREAK version
   (desk, fast, flex) on the APEX account.

## Concerns (no fix needed)

- APEX300's 1R target was chosen after its test months were seen, so they are no longer blind for that choice.
- The limit-entry strategies (FVG side, FVG15 x2) may get touch fills live that the backtest (one tick through) never took.
- The Desk does not enforce Apex's trailing drawdown, contract tiers or 30% rule; only the per-account day locks and the
  flat time. Every Apex rule is up to the settings.
- Pure-luck baseline for B is ~79%: most of the gain over the shared cycle comes from accounts failing independently, not
  from more edge.
