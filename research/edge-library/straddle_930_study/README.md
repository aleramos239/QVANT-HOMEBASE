# NQ 9:30 straddle study (2026-10-30 → 2026-11-01)

3:1 in-sample months only, 1 NQ, $4 round turn, 8 ticks slippage, cancel rule. No box picked, no test months run.
Vault note: `50-Permanent/Findings/2026-10-30-nq-930-straddle-entry-distance-fixed-pts-vs-atr-in-sample.md`.

## drafts/  (copy into `~/.homebase/strategies/` to use in the tester; the originals live there)
| file | id | what |
|---|---|---|
| nq_930_straddle.py | draft_nq_930_straddle | reference: k pts each side of the 9:30 print, other side cancelled at the first fill |
| nq_930_straddle_reopen.py | | `second` = cancel / live / hold / none (engine `oco(mode=)`) |
| nq_930_straddle_trend.py, _long.py, es_930_straddle_long.py, nq_930_random.py | | trend-side, long-only, ES long-only, random-side control |
| nq_930_straddle_dist.py | draft_nq_930_straddle_dist | distance rule `dist`: pts / pct / preopen / rv / rvd, times `k`; `gap` both / with / against |
| nq_930_straddle_vol.py | draft_nq_930_straddle_vol | volume rules: `off_mode` pts / rvol_wide / rvol_tight / vwapdev / vband; `stop_kind` ctl / atr / vwatr / rvol_up / rvol_dn; `dryup` exit |

Stops and targets come from the run controls (`stop_mode atr`, `target_mode rr`, axes `ctl.stop_atr`, `ctl.target_rr`).
The ATR stop is read when the orders are placed (09:30), not at the fill. `vol_kind` = atr (mean) | median | std.
Existing controls with no code: `exit_line` vwap | vwap_rth | ema20 | ema50, `be_after_pts`, `be_at`, `trail_from`.

## pages/  (heat-map page generators; they read walk-forward runs from `homebase/.state/tester/walkforward/<id>/`)
`read_wf.py` summarises a run by id. `gen18.py` = 7 groups x 3 distances x 15 boxes with the full-target %;
`gen19.py` = the same with 5 stops (3-5 x ATR) and the extra runs merged. Run ids are hard-coded in each file;
paths to the scratch folder at the top need changing to run them again.
