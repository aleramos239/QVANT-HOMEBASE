# PORT3_VALIDATION — families/port3.py (vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev) vs the Homebase Strategy Tester

Generated 2026-10-04 10:07 ET by `port3_validate.py` (sha256/16: families/port3.py 9b5667ebeaf01926, l2sim.py bc7394332573ff85, l2ref.py 51f18fb1b8c84bc1, port3_validate.py c03706d80bf29378).
Raw: `out/port3_validation.json`. In-sample bundles of the old pilots only (2021-09-22 → 2024-12-31; stages `screen` and `sizing`), trade IDENTITY only; nothing dated ≥ 2025-01-01 and no `holdout` bundle was read; no bundle P&L is shown.

## Verdict: ALL GATES PASS
Gate per bundle / cell: ≥ 99 % identical trades (date, side, entry time ± 1 s, entry price, exit price, exit reason), net within 0.5 %, the same skipped days, no session dropped by an error.

## NQ — screen runs (default inputs, sess all): PASS
| bundle | tester trades | sim trades | all-20-fields identical | match rate | net diff $ | skipped days equal | pass |
|---|---|---|---|---|---|---|---|
| screen-vwap_band-tf1 | 11426 | 11426 | 11426 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf5 | 5850 | 5850 | 5850 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf15 | 2155 | 2155 | 2155 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf30 | 596 | 596 | 596 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf1 | 11670 | 11670 | 11670 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf5 | 6345 | 6345 | 6345 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf15 | 2512 | 2512 | 2512 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf30 | 876 | 876 | 876 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf1 | 11231 | 11231 | 11231 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf5 | 7193 | 7193 | 7193 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf15 | 3630 | 3630 | 3630 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf30 | 1266 | 1266 | 1266 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf1 | 5879 | 5879 | 5879 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf5 | 2111 | 2111 | 2111 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf15 | 892 | 892 | 892 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf30 | 446 | 446 | 446 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf1 | 4020 | 4020 | 4020 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf5 | 3430 | 3430 | 3430 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf15 | 2811 | 2811 | 2811 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf30 | 2217 | 2217 | 2217 | 100.00% | +0.00 | True | True |

## NQ — every cell of the sizing heat-maps: PASS
| heat-map | tf | axes | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max abs net diff $ | pass |
|---|---|---|---|---|---|---|---|---|---|---|
| hm-vwap_band-tf5 | 5 | band [1.5, 2.0, 2.5, 3.0] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 48 | 48 | 188689 | 188689 | 188689 | 100.00% | 0.00 | True |
| hm-vwap_z-tf5 | 5 | zth [1.5, 2.0, 2.5, 3.0] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 48 | 48 | 207687 | 207687 | 207687 | 100.00% | 0.00 | True |
| fp-vwap_flip-tf1 | 1 | stop_val [10.0, 20.0, 30.0, 45.0] × tgt_r [0.25, 0.4, 0.6, 1.0] (pts stops) | 16 | 16 | 157558 | 157558 | 157558 | 100.00% | 0.00 | True |
| fp-vwap_flip-tf5 | 5 | stop_val [10.0, 20.0, 30.0, 45.0] × tgt_r [0.25, 0.4, 0.6, 1.0] (pts stops) | 16 | 16 | 119999 | 119999 | 119999 | 100.00% | 0.00 | True |
| hm-vwap_flip-tf15 | 15 | hold [1, 2, 3] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 126530 | 126530 | 126530 | 100.00% | 0.00 | True |
| hm2-vwap_flip-tf1 | 1 | hold [1, 2, 3] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 380857 | 380857 | 380857 | 100.00% | 0.00 | True |
| hm2-vwap_flip-tf5 | 5 | hold [1, 2, 3] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 243639 | 243639 | 243639 | 100.00% | 0.00 | True |
| hm2-pinbar-tf5 | 5 | wick [0.6, 0.667, 0.75] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 79946 | 79946 | 79946 | 100.00% | 0.00 | True |
| hm2-sweep_rev-tf5 | 5 | levels ['both', 'pd', 'on'] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 86010 | 86010 | 86010 | 100.00% | 0.00 | True |

## ES — screen runs (default inputs, sess all): PASS
| bundle | tester trades | sim trades | all-20-fields identical | match rate | net diff $ | skipped days equal | pass |
|---|---|---|---|---|---|---|---|
| screen-vwap_band-tf1 | 11637 | 11637 | 11637 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf5 | 6187 | 6187 | 6187 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf15 | 2279 | 2279 | 2279 | 100.00% | +0.00 | True | True |
| screen-vwap_band-tf30 | 654 | 654 | 654 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf1 | 11894 | 11894 | 11894 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf5 | 6729 | 6729 | 6729 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf15 | 2655 | 2655 | 2655 | 100.00% | +0.00 | True | True |
| screen-vwap_z-tf30 | 951 | 951 | 951 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf1 | 11420 | 11420 | 11420 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf5 | 7545 | 7545 | 7545 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf15 | 3716 | 3716 | 3716 | 100.00% | +0.00 | True | True |
| screen-vwap_flip-tf30 | 1263 | 1263 | 1263 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf1 | 6149 | 6149 | 6149 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf5 | 2123 | 2123 | 2123 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf15 | 895 | 895 | 895 | 100.00% | +0.00 | True | True |
| screen-pinbar-tf30 | 410 | 410 | 410 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf1 | 4022 | 4022 | 4022 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf5 | 3436 | 3436 | 3436 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf15 | 2816 | 2816 | 2816 | 100.00% | +0.00 | True | True |
| screen-sweep_rev-tf30 | 2256 | 2256 | 2256 | 100.00% | +0.00 | True | True |

## ES — every cell of the sizing heat-maps: PASS
| heat-map | tf | axes | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max abs net diff $ | pass |
|---|---|---|---|---|---|---|---|---|---|---|
| fp-vwap_z-tf5 | 5 | stop_val [3.0, 6.0, 10.0, 15.0] × tgt_r [0.25, 0.4, 0.6, 1.0] (pts stops) | 16 | 16 | 103007 | 103007 | 103007 | 100.00% | 0.00 | True |
| hm-vwap_z-tf5 | 5 | zth [1.5, 2.0, 2.5, 3.0] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 48 | 48 | 218499 | 218499 | 218499 | 100.00% | 0.00 | True |
| fp-vwap_flip-tf15 | 15 | stop_val [3.0, 6.0, 10.0, 15.0] × tgt_r [0.25, 0.4, 0.6, 1.0] (pts stops) | 16 | 16 | 58057 | 58057 | 58057 | 100.00% | 0.00 | True |
| fp-vwap_flip-tf5 | 5 | stop_val [3.0, 6.0, 10.0, 15.0] × tgt_r [0.25, 0.4, 0.6, 1.0] (pts stops) | 16 | 16 | 110136 | 110136 | 110136 | 100.00% | 0.00 | True |
| hm-vwap_flip-tf15 | 15 | hold [1, 2, 3] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 127462 | 127462 | 127462 | 100.00% | 0.00 | True |
| hm-vwap_flip-tf5 | 5 | hold [1, 2, 3] × stop_val [1.0, 2.0, 3.0] × tgt_r [0.5, 1.0, 2.0, 3.0] | 36 | 36 | 250857 | 250857 | 250857 | 100.00% | 0.00 | True |

## Registered family-parameter variants are tester-matched (NQ heat-maps)
| family | registered variants | matched first-axis values | missing | pass |
|---|---|---|---|---|
| vwap_band | [{'band': 1.5}, {'band': 2.0}, {'band': 2.5}, {'band': 3.0}] | {'band': [1.5, 2.0, 2.5, 3.0]} | — | True |
| vwap_z | [{'zth': 1.5}, {'zth': 2.0}, {'zth': 2.5}, {'zth': 3.0}] | {'zth': [1.5, 2.0, 2.5, 3.0]} | — | True |
| vwap_flip | [{'hold': 1}, {'hold': 2}, {'hold': 3}] | {'hold': [1, 2, 3]} | — | True |
| pinbar | [{'wick': 0.6}, {'wick': 0.667}, {'wick': 0.75}] | {'wick': [0.6, 0.667, 0.75]} | — | True |
| sweep_rev | [{'levels': 'both'}, {'levels': 'pd'}, {'levels': 'on'}] | {'levels': ['both', 'on', 'pd']} | — | True |

## Not covered by a tester bundle (flag)
* **GC**: no GC tester run exists (EDGE_VALIDATION.md "GC"); the five families run on GC with the same code, validated by construction only.
* **`pre` / `eve` sessions, `stop_mode="pct"`**: the tester cannot run them; their proof is internal (`tests/test_port3.py`: session windows, no look-ahead, worker parity; `tests/test_edge_template.py`).
* `vwap_flip` `anchor="rth"` and `f_trend` / `f_vwap` / `trail_atr` were never run in the tester for these families and are not menu variants.

## Reproduce
`"~/ONYX TRADING/.venv/bin/python" port3_validate.py --workers 2` in `engine/` (re-run after ANY change to `families/port3.py`, `l2sim.py` or `l2ref.py`; `tests/test_port3.py` fails when `families/port3.py` no longer has the sha above).
