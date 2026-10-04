# SIM_VALIDATION — l2sim vs the Homebase Strategy Tester (in-sample 2021-09-22 → 2024-12-31)

Generated 2026-10-01 23:47 ET by `sim_validate.py` (code sha256/16: l2sim.py 147dd16bfca56b36, l2ref.py 3616529ba81acf99, sim_validate.py f19dd72c99835e24). Raw numbers: `out/sim_validation.json`.

## Verdict: GATE PASS
Gate (SPEC.md): for each of the three approved tester strategies, >= 95% of trades identical on
(date, side, entry time ±1 s, entry price, exit price, exit_reason) AND total net within 2% of the tester bundle.
Match rate = matched / max(tester trades, sim trades); "all-20-fields identical" additionally requires qty,
order_price, sl, tp, gross, commission, net, mae/mfe (pts and usd), bars, seconds, entry_ms and exit_ms to be equal.
Each config is checked on every session of the run (sess = all) and on the approved pick's own session.

| config | role | scope | tester trades | sim trades | matched | match rate | all-20-fields identical | tester net $ | sim net $ | net diff |
|---|---|---|---|---|---|---|---|---|---|---|
| hm2-straddle-tf30#10 | Flex eval pick | all sessions | 3273 | 3273 | 3273 | 100.00% | 100.00% | +141,158 | +141,158 | +0.00 (0.000%) |
| hm2-straddle-tf30#10 | Flex eval pick | nyam | 820 | 820 | 820 | 100.00% | 100.00% | +95,315 | +95,315 | +0.00 (0.000%) |
| hm-orb-tf5#10 | Pro noDLL funded pick | all sessions | 3272 | 3272 | 3272 | 100.00% | 100.00% | +16,152 | +16,152 | +0.00 (0.000%) |
| hm-orb-tf5#10 | Pro noDLL funded pick | mid | 820 | 820 | 820 | 100.00% | 100.00% | +62,610 | +62,610 | +0.00 (0.000%) |
| fp-donchian-tf15#10 | Pro DLL funded pick | all sessions | 3571 | 3571 | 3571 | 100.00% | 100.00% | -8,064 | -8,064 | +0.00 (0.000%) |
| fp-donchian-tf15#10 | Pro DLL funded pick | pm | 760 | 760 | 760 | 100.00% | 100.00% | +26,940 | +26,940 | +0.00 (0.000%) |

Sessions: 825 in-sample sessions with a tape, 820 used; the 5 coverage-hole days are skipped by the sim for the
same reason strings as the tester (2021-12-01, 2022-06-21, 2022-08-05, 2022-09-06, 2023-04-07). No row dated >= 2025-01-01 was read (bundles end 2024-12-31; the tape
loader raises on 2025+).

## Other baseline picks (not part of the gate, same check)
| config | role | scope | tester trades | sim trades | matched | match rate | all-20-fields identical | tester net $ | sim net $ | net diff |
|---|---|---|---|---|---|---|---|---|---|---|
| hm2-straddle-tf30#9 | Pro noDLL eval pick | all sessions | 3273 | 3273 | 3273 | 100.00% | 100.00% | +132,603 | +132,603 | +0.00 (0.000%) |
| hm2-straddle-tf30#9 | Pro noDLL eval pick | nyam | 820 | 820 | 820 | 100.00% | 100.00% | +65,610 | +65,610 | +0.00 (0.000%) |
| hm2-straddle-tf30#32 | Flex funded pick | all sessions | 3137 | 3137 | 3137 | 100.00% | 100.00% | +14,202 | +14,202 | +0.00 (0.000%) |
| hm2-straddle-tf30#32 | Flex funded pick | pm | 706 | 706 | 706 | 100.00% | 100.00% | +14,621 | +14,621 | +0.00 (0.000%) |
| fp-donchian-tf15#1 | Apex PA pick | all sessions | 3852 | 3852 | 3852 | 100.00% | 100.00% | -14,013 | -14,013 | +0.00 (0.000%) |
| fp-donchian-tf15#1 | Apex PA pick | nyam | 1141 | 1141 | 1141 | 100.00% | 100.00% | +11,911 | +11,911 | +0.00 (0.000%) |
| fp-donchian-tf15#15 | Lucid Pro DLL eval single | all sessions | 2874 | 2874 | 2874 | 100.00% | 100.00% | -4,086 | -4,086 | +0.00 (0.000%) |
| fp-donchian-tf15#15 | Lucid Pro DLL eval single | pm | 586 | 586 | 586 | 100.00% | 100.00% | +43,596 | +43,596 | +0.00 (0.000%) |

## Which tape
The tester replays `~/futures_ticks/NQ/<YYYY>/<date>_<contract>.csv.gz` (front contract = the manifest with the most
ticks, stable-sorted by ts_ns), cached as `~/futures_derived/homebase_tape/NQ/<date>.tape`. The SPEC's execution tape
`~/futures_derived/ofb_tick/NQ/YYYY/MM/<date>.parquet` is built from the same archive files with the same front-month
rule. Checked on every in-sample session: **825 of 825 sessions are print-identical** (ts_ns, price, size,
row order, contract). l2sim therefore reads the ofb_tick parquet (columns ts_ns, price, size only): it IS the
tester's tape, and the lagged OFB columns stay available to the data layer from the same file.

## Conventions reproduced (homebase/backtest/engine.py "tick-2", runner.py, strategies/base.py, tape.py)
* Stop orders (stop entries, stop-losses): market-on-touch, fill = max/min(trigger, print) ± 1 tick (a gap costs the gap).
* Limit orders (limit entries, targets): fill only on a 1-tick trade-through, at the limit price, no slip.
* Market orders: first print at/after the order goes live, ± 1 tick. Flatten: first print at/after the event, ∓ 1 tick.
* Orders go live 85 ms (`placement_ms`) after the event that sent them; cancel / flatten act at once.
* A strategy callback that raises costs that session only: orders cancelled, the session's trades dropped, the day
  listed under no_trade as "strategy error: ..." and counted in `skipped_by_error` (gate runs: 0 such sessions).
* Inputs are validated and coerced like the tester's `resolve_inputs` (unknown key, wrong type, bad choice, out of
  range -> error); `session_independent` is opt-in as in the tester (the Template and the three families set it).
* SL/TP ride the entry and can trigger from the print after the entry print; one print hitting both -> SL
  (orders triggering on one print fill oldest first; the SL is created before the TP).
* `move_brackets_to_fill`: SL (and TP) keep their distance to `ref`; `tp_rr` re-derives the TP from the fill.
* Prices snapped to the tick grid; touch comparisons epsilon-tolerant (tick × 1e-6).
* Commission $4.00 per round turn per NQ, qty 1; gross = side × (exit − entry) × $20.
* MAE/MFE: extremes of the prints from the entry print's index to the exit print, against the slipped fill price.
* Events: session start, 1-minute bar closes (bars only for minutes with prints; a bar closing at 10:00:00 runs before
  the first print stamped >= 10:00:00 and sees only earlier prints), `times()`; same-time order session < bar < time;
  events at/after the session end never fire; end of session flattens everything ("eod").
* Calendar: weekday sessions with a tape; a session with an empty clock hour inside the window is skipped
  ("missing HH:MM–HH:MM ET"); CME half days clamp the window to 13:15 ET. Daily bars (prior-day H/L/C, daily ATR) =
  whole archive day, contract-roll days drop the prior-day levels (same 13 in-sample roll dates as the drafts).
* Trades: the tester's trades.json schema (date, side, qty, entry_price, exit_price, exit_reason, order_price, sl, tp,
  gross, commission, net, mae_pts, mfe_pts, mae_usd, mfe_usd, bars, seconds, entry_ms, exit_ms), sorted by (exit, entry).
The three strategies are re-implemented on `l2sim.Template` (the port of R/template.py: tf aggregation, Wilder ATR(14)
since 00:00 ET, sessions asia/london/nyam/mid/pm, atr|pts|struct stops, tgt_r, trail_atr, exit_bars, max_tr, no
entries in the last 5 minutes, flat at session end) in `l2ref.py`; inputs are read from each bundle's run.json.

## Every cell of the three source heat-maps (parameter coverage)
Each family's whole tester grid replayed in one tape pass (`l2sim.run_many`) and compared cell by cell:

| family | tester grid | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max abs net diff $ | sim time |
|---|---|---|---|---|---|---|---|---|---|
| straddle | 20260930-001526-draft_pp_straddle-67c2 | 36 | 36 | 116,172 | 116,172 | 116,172 | 100.00% | 0.00 | 22 s |
| orb | 20260929-231930-draft_pp_orb-5276 | 36 | 36 | 136,392 | 136,392 | 136,392 | 100.00% | 0.00 | 23 s |
| donchian | 20260930-111627-draft_pp_donchian-cd3c | 16 | 16 | 58,142 | 58,142 | 58,142 | 100.00% | 0.00 | 9 s |

## Negative controls (the comparison can fail)
Same strategies, ONE convention changed, full in-sample window:

| config | change | tester trades | sim trades | match rate | all-fields identical | net diff $ |
|---|---|---|---|---|---|---|
| hm2-straddle-tf30#10 | slippage 0 ticks (instead of 1) | 3273 | 3273 | 0.00% | 0.00% | +33,295 |
| fp-donchian-tf15#10 | slippage 0 ticks (instead of 1) | 3571 | 3575 | 0.00% | 0.00% | +28,469 |
| fp-donchian-tf15#10 | placement latency 0 ms (instead of 85) | 3571 | 3573 | 32.24% | 20.99% | +19,262 |
| hm2-straddle-tf30#10 | placement latency 0 ms (instead of 85) | 3273 | 3273 | 99.63% | 99.60% | -2,880 |

## Engine-level differential tests (tests/test_l2sim_engine_diff.py)
The tester's own `run_session` (imported read-only, no bytecode written) and l2sim's are fed the same tape and the
same strategy object: a random order-flow fuzz over the whole ctx API (market / stop / limit entries, sl / tp / tp_rr
/ ref, OCO, cancel, flatten, off-grid prices, overlapping positions, same-timestamp bursts, empty minutes) on 12
synthetic tapes and 6 real in-sample days (2 half days, 2 roll days), plus the reference families incl. struct stops,
trail / exit_bars and both filters. Trades and final order states are identical in every case. This covers what the
three approved strategies do not exercise: limit entries, tp_rr, trailing / bar exits, overlapping positions.

## Speed
Full in-sample run (825 sessions, sess = all) on 8 worker processes: hm2-straddle-tf30#10 1.4 s, hm-orb-tf5#10 1.4 s, fp-donchian-tf15#10 1.3 s. SPEC target <= 60 s.
A grid shares one tape pass (`run_many`): 36 straddle cells 22 s, 36 orb cells 23 s, 16 donchian cells 9 s. Per session-day: ~16 ms to read the tape, ~8 ms per cell.

## Execution sensitivity of the gate configs (not part of the gate)
`l2sim.run(..., slip_ticks=, latency_ms=, strict_limit=)`; defaults = the tester law above. Stress = `l2sim.STRESS`
(2 ticks of slip per market / stop / flatten fill, 250 ms placement latency). Full in-sample window:

| config | execution | trades | net $ (all sessions) | pick session | trades | net $ |
|---|---|---|---|---|---|---|
| hm2-straddle-tf30#10 | tester law (1 tick, 85 ms) | 3273 | +141,158 | nyam | 820 | +95,315 |
| hm2-straddle-tf30#10 | slip 2 ticks | 3273 | +111,638 | nyam | 820 | +87,750 |
| hm2-straddle-tf30#10 | latency 250 ms | 3273 | +145,228 | nyam | 820 | +95,045 |
| hm2-straddle-tf30#10 | 2 ticks + 250 ms | 3273 | +115,698 | nyam | 820 | +87,475 |
| hm-orb-tf5#10 | tester law (1 tick, 85 ms) | 3272 | +16,152 | mid | 820 | +62,610 |
| hm-orb-tf5#10 | slip 2 ticks | 3272 | -13,953 | mid | 820 | +52,590 |
| hm-orb-tf5#10 | latency 250 ms | 3272 | +13,087 | mid | 820 | +62,235 |
| hm-orb-tf5#10 | 2 ticks + 250 ms | 3272 | -17,043 | mid | 820 | +52,215 |
| fp-donchian-tf15#10 | tester law (1 tick, 85 ms) | 3571 | -8,064 | pm | 760 | +26,940 |
| fp-donchian-tf15#10 | slip 2 ticks | 3563 | -37,017 | pm | 759 | +20,609 |
| fp-donchian-tf15#10 | latency 250 ms | 3560 | -37,195 | pm | 757 | +20,872 |
| fp-donchian-tf15#10 | 2 ticks + 250 ms | 3555 | -62,920 | pm | 757 | +14,792 |

## Open risks (read before screening)
**Where the fill law is NOT pessimistic.** These are the tester's conventions, reproduced on purpose (the gate needs
them); they are not port defects, and a new family must survive the stress run before it is believed.
1. **Market and flatten fills pay 1 tick from the last print, not the spread.** In-sample `l2data.spread_ticks` at
   minute ends (1.08 million book_ok rows): median 2 ticks in nyam / mid / pm (means 2.14 / 1.96 / 1.98), median 3 ticks
   in asia / london (means 2.87 / 2.85); the spread is wider than 2 ticks in 56.5% of asia and 59.9% of london minutes
   against 14–23% in RTH. One tick is about half the RTH spread and less than half overnight: asia / london market
   entries are optimistic by roughly half a tick to a tick per side. Check with `slip_ticks=2`.
2. **Cancels, flattens and OCO cancels have zero latency** while new orders wait 85 ms: a cancel at a bar close always
   beats a print 1 ms later, and an OCO sibling is cancelled the instant the other leg fills (no double fill in a fast
   market). The 'eod' flatten on a CME half day fills on the last print BEFORE 13:15 ET (∓ 1 tick), not on a print
   at/after the close (6 trades per gate config).
3. **Results move with the 85 ms figure, and live latency above it is not modelled.** fp-donchian-tf15#10 nets −8,064
   at 85 ms and +11,198 at 0 ms (about one tick per trade over 3,571 trades; see the negative controls). 85 ms is the
   desk's measured placement latency, not a bound. Check with `latency_ms=250`.
4. **A limit entry's stop is armed one print after the fill print.** A print that trades through the limit and is
   already at/through the stop does not stop the trade; some of these end as booked target wins that are losers live.
   Independent verifier's probe (out/build_reports/verify_sim_1.md; 59 in-sample days, a limit 1 tick passive every
   minute, target 1R): with a 2-tick stop 28.0% of 20,430 fills were through the stop on the fill print and 392 of
   them exited 'tp'; 4 ticks 7.2% (60 'tp'); 8 ticks 1.2%; 16 ticks 0.2%; net bias about zero (−$0.08 per trade at
   2 ticks). For every limit-entry family (B4 wall_bounce): `result["unrealistic_winners"]` /
   `l2sim.unrealistic_winners(trades)` lists the limit-entry trades with exit_reason 'tp' and mae_pts >= the stop
   distance; more than a handful -> judge the family on `strict_limit=True` (the stop is live ON the fill print),
   which removes them by construction.
5. **A limit fills on a 1-tick trade-through with no queue model** (this one IS pessimistic for passive fills, but a
   trade-through of several ticks still fills at the limit price in full size).

**Coverage of the validation.**
* 100% is by construction, not luck: same tape, a line-by-line port of the engine, same strategy logic. The gate
  proves the execution layer adds no drift; it says nothing about how close the tester's law is to live fills.
* No tester bundle exercises struct stops, trail_atr, exit_bars, f_trend / f_vwap, dir long / short, news_only or the
  new `_lim` limit-entry helper: their fidelity rests on code identity with R/template.py and on the engine
  differential tests, not on a trade-for-trade bundle match.
* `ctx.daily` / `datr()` are not covered by the gate (no gate strategy reads them). The daily cache starts 2021-09-22
  (first tape session) while the tester loads 400 days before the range start, so `datr()` is None for the first 15
  sessions and its Wilder seed differs from the tester's early in the sample and on sub-range runs.
* `on_bar` fires only for minutes that have prints (tester convention). A strategy that must act on a minute with no
  print should use `times()`.
* Feature rows are visible to a strategy only through `ctx.feat` / `ctx.feat_window` (usable_ns <= decision time; a
  negative `back` / `n` raises `LookAheadError`, which aborts the run); a strategy that reads the data layer directly
  bypasses that guard. The adapter's absolute clock is tested against the tape's (tests/test_l2sim_lookahead.py).
* A session dropped by a strategy error is NOT a flat day: check `result["skipped_by_error"] == 0` before scoring.
* A raw `Strategy` subclass runs on ONE process unless it sets `session_independent = True` (tester default: False).
* Holdout tapes (2025+) raise `HoldoutSealed` unless `allow_holdout=True`; the half-day table covers 2017–2026.
* The differential tests import the tester's engine as it is on disk today; if `homebase/backtest/engine.py` changes
  (ENGINE_VERSION != tick-2) the port must be re-diffed.

## Reproduce
`"~/ONYX TRADING/.venv/bin/python" sim_validate.py` (about 96 s) and
`"~/ONYX TRADING/.venv/bin/python" -m pytest` in this directory.
