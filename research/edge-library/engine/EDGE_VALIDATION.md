# EDGE_VALIDATION — the edge-library engine vs the Homebase Strategy Tester

Generated 2026-10-06 00:54 ET by `edge_validate.py` (code sha256/16: l2sim.py 653e964f1fd3adb0, l2ref.py 51f18fb1b8c84bc1, edge_validate.py 8c5e39a19def9a7f). Raw: `out/edge_validation.json`.
In-sample bundles of the old pilots only (2021-09-22 → 2024-12-31), trade IDENTITY only; nothing dated ≥ 2025-01-01 was read.

## Verdict: ALL GATES PASS

## NQ — the SIM VALIDATION GATE again, every new option off: PASS (100 %)
| config | scope | tester trades | sim trades | all-20-fields identical | net diff $ |
|---|---|---|---|---|---|
| hm2-straddle-tf30#10 | all sessions | 3273 | 3273 | 100.00% | +0.00 |
| hm2-straddle-tf30#10 | nyam | 820 | 820 | 100.00% | +0.00 |
| hm-orb-tf5#10 | all sessions | 3272 | 3272 | 100.00% | +0.00 |
| hm-orb-tf5#10 | mid | 820 | 820 | 100.00% | +0.00 |
| fp-donchian-tf15#10 | all sessions | 3571 | 3571 | 100.00% | +0.00 |
| fp-donchian-tf15#10 | pm | 760 | 760 | 100.00% | +0.00 |
| hm2-straddle-tf30#9 | all sessions | 3273 | 3273 | 100.00% | +0.00 |
| hm2-straddle-tf30#9 | nyam | 820 | 820 | 100.00% | +0.00 |
| hm2-straddle-tf30#32 | all sessions | 3137 | 3137 | 100.00% | +0.00 |
| hm2-straddle-tf30#32 | pm | 706 | 706 | 100.00% | +0.00 |
| fp-donchian-tf15#1 | all sessions | 3852 | 3852 | 100.00% | +0.00 |
| fp-donchian-tf15#1 | nyam | 1141 | 1141 | 100.00% | +0.00 |
| fp-donchian-tf15#15 | all sessions | 2874 | 2874 | 100.00% | +0.00 |
| fp-donchian-tf15#15 | pm | 586 | 586 | 100.00% | +0.00 |

| heat-map | cells | cells 100% identical | tester trades | sim trades | max abs net diff $ |
|---|---|---|---|---|---|
| straddle 20260930-001526-draft_pp_straddle-67c2 | 36 | 36 | 116172 | 116172 | 0.00 |
| orb 20260929-231930-draft_pp_orb-5276 | 36 | 36 | 136392 | 136392 | 0.00 |
| donchian 20260930-111627-draft_pp_donchian-cd3c | 16 | 16 | 58142 | 58142 | 0.00 |

## ES — the ES pilot's tester bundles (tester tape cache, $50 / pt, tick 0.25, $4 RT, 1 tick slip): PASS
Gate: ≥ 99 % identical trades and net within 0.5 % per bundle / cell.
| bundle | root | tester trades | sim trades | all-20-fields identical | match rate | net diff % | skipped days equal | pass |
|---|---|---|---|---|---|---|---|---|
| es-screen-straddle-tf30 | ES | 3285 | 3285 | 3285 | 100.00% | 0.000 | True | True |
| es-screen-orb-tf5 | ES | 4095 | 4095 | 4095 | 100.00% | 0.000 | True | True |
| es-screen-donchian-tf15 | ES | 2397 | 2397 | 2397 | 100.00% | 0.000 | True | True |

| heat-map | root | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max net diff % | pass |
|---|---|---|---|---|---|---|---|---|---|
| es-fp-straddle-tf30 | ES | 16 | 16 | 52560 | 52560 | 52560 | 100.00% | 0.000 | True |
| es-fp-orb-tf5 | ES | 16 | 16 | 65520 | 65520 | 65520 | 100.00% | 0.000 | True |
| es-hm-donchian-tf15 | ES | 36 | 36 | 98645 | 98645 | 98645 | 100.00% | 0.000 | True |
| es-hm-straddle-tf15 | ES | 36 | 36 | 117816 | 117816 | 117816 | 100.00% | 0.000 | True |

## RANDOM — the C1 control port (l2ref.Random) vs the pilots' control bundles: PASS
Gate: ≥ 99 % identical trades and net within 0.5 % per bundle / cell.
| bundle | root | tester trades | sim trades | all-20-fields identical | match rate | net diff % | skipped days equal | pass |
|---|---|---|---|---|---|---|---|---|
| nq-ctrl-random-tf5-s1 | NQ | 7208 | 7208 | 7208 | 100.00% | 0.000 | True | True |
| es-ctrl-random-tf15-s1 | ES | 3221 | 3221 | 3221 | 100.00% | 0.000 | True | True |

| heat-map | root | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | max net diff % | pass |
|---|---|---|---|---|---|---|---|---|---|
| nq-fpctrl-random-tf30-s21 | NQ | 16 | 16 | 111701 | 111701 | 111701 | 100.00% | 0.000 | True |

## CLOCK — StraddleT (the Globex-clock path) vs the existing Straddle: PASS (identical)
| root | fire time | = session | exit cell | Straddle trades | StraddleT trades | identical lists | skipped days equal |
|---|---|---|---|---|---|---|---|
| NQ | 03:00 | london | atr1p5-r2 | 820 | 820 | True | True |
| NQ | 03:00 | london | atr3-r0 | 820 | 820 | True | True |
| NQ | 03:00 | london | pts20-r1 | 820 | 820 | True | True |
| NQ | 03:00 | london | pct0p1-r3 | 820 | 820 | True | True |
| NQ | 09:30 | nyam | atr1p5-r2 | 820 | 820 | True | True |
| NQ | 09:30 | nyam | atr3-r0 | 820 | 820 | True | True |
| NQ | 09:30 | nyam | pts20-r1 | 820 | 820 | True | True |
| NQ | 09:30 | nyam | pct0p1-r3 | 820 | 820 | True | True |
| NQ | 13:30 | pm | atr1p5-r2 | 811 | 811 | True | True |
| NQ | 13:30 | pm | atr3-r0 | 811 | 811 | True | True |
| NQ | 13:30 | pm | pts20-r1 | 811 | 811 | True | True |
| NQ | 13:30 | pm | pct0p1-r3 | 811 | 811 | True | True |
| ES | 03:00 | london | atr1p5-r2 | 823 | 823 | True | True |
| ES | 03:00 | london | atr3-r0 | 823 | 823 | True | True |
| ES | 03:00 | london | pts5-r1 | 823 | 823 | True | True |
| ES | 03:00 | london | pct0p1-r3 | 823 | 823 | True | True |
| ES | 09:30 | nyam | atr1p5-r2 | 823 | 823 | True | True |
| ES | 09:30 | nyam | atr3-r0 | 823 | 823 | True | True |
| ES | 09:30 | nyam | pts5-r1 | 823 | 823 | True | True |
| ES | 09:30 | nyam | pct0p1-r3 | 823 | 823 | True | True |
| ES | 13:30 | pm | atr1p5-r2 | 816 | 816 | True | True |
| ES | 13:30 | pm | atr3-r0 | 816 | 816 | True | True |
| ES | 13:30 | pm | pts5-r1 | 816 | 816 | True | True |
| ES | 13:30 | pm | pct0p1-r3 | 816 | 816 | True | True |

## GC
No GC run exists in `homebase/.state/tester` (runs / grids / walk-forwards hold NQ and ES only), so GC cannot be matched against the tester. It rests on: the tape (a session built with the tester's own `TapeStore` code is byte-identical to the tester's cached file), the same engine code that matches NQ and ES 100 %, tick / point arithmetic unit tests ($100 / pt, tick 0.10) and an independent replay (`research/nfp-2026-10-02/nfp_lib.py`, 5 BUILD NFP days: same entries, TP / SL exits to the cent except where nfp_lib's exact float comparison misses a print AT the stop by float noise). `tests/test_edge_roots.py`. **FLAG: GC is validated by construction, not by a tester bundle.**

## Reproduce
`"~/ONYX TRADING/.venv/bin/python" edge_validate.py --workers 4` and `-m pytest` in this directory.
