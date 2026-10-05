# orb_NQ_tf15_pre — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** opening range break · **market** NQ · **session** pre · **bar size** 15 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**DEMOTED: luck not excluded (BUILD test (2) fails with every control seed on disk; it passes with the first 2). Kept on file, NOT counted as edge.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default $24,446, 22 of the 50 saved variants profitable.

**Reason (written before testing):** Opening range = the first balance of the session: the first or_min minutes set the range the rest of the session resolves, so a break of either side traps the other side and carries.

**Rules (default variant `or_min15_pct0p1-r0`):** Range = the first 15 minutes of the session. A buy stop one tick above it and a sell stop one tick below (one cancels the other). Stop 0.1 % of price; no target (out at the stop or at the flat time). Session: pre-market (08:25-09:30 ET); flat by 15:58 ET.

**Flags:** DEMOTED: luck not excluded (a real-edge test fails with every control seed on disk; kept on file, not counted as edge); 2025-26 was already seen once for this family's old favourite (an EXAM would be a second look); 2024 was already read for this idea at another bar size (an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went)

**The same idea at other bar sizes (same market and session):** 1-min: fails BUILD test 2; 30-min: fails BUILD test 2; 5-min: fails BUILD test 2.

## Average variant and default variant, per year then combined
Average = the 96 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 50 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 64 | -$468 | 32 % | 0.98 | $7,630 | -$7 |
| average variant | 2022 | 221 | $17,005 | 33 % | 1.18 | $13,365 | $77 |
| average variant | 2023 | 218 | $6,170 | 33 % | 1.08 | $12,820 | $28 |
| average variant | 2024 | 221 | $10,886 | 32 % | 1.11 | $15,370 | $49 |
| average variant | 2025 | 221 | -$9,371 | 29 % | 0.92 | $26,335 | -$42 |
| average variant | combined | 946 | $24,222 | 32 % | 1.06 | $32,489 | $26 |
| default `or_min15_pct0p1-r0` | 2021* | 68 | -$872 | 7 % | 0.96 | $7,714 | -$13 |
| default `or_min15_pct0p1-r0` | 2022 | 228 | $15,793 | 7 % | 1.28 | $16,912 | $69 |
| default `or_min15_pct0p1-r0` | 2023 | 226 | $23,571 | 12 % | 1.40 | $14,806 | $104 |
| default `or_min15_pct0p1-r0` | 2024 | 229 | $35,934 | 13 % | 1.46 | $13,981 | $157 |
| default `or_min15_pct0p1-r0` | 2025 | 221 | $24,446 | 8 % | 1.26 | $28,627 | $111 |
| default `or_min15_pct0p1-r0` | combined | 972 | $98,872 | 10 % | 1.32 | $28,627 | $102 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 96 | 75 | 78 % | pass | pass | fail | $22,707 | $17,217 |
| 2024 | 96 | 65 | 68 % | pass | fail | fail | $10,886 | $5,616 |
| 2024 under stress | 96 | 57 | 59 % | | | | $8,258 | $2,274 |
| 2025 | 96 | 25 | 26 % | fail | fail | fail | -$9,371 | -$10,122 |
| 2025 under stress | 96 | 24 | 25 % | | | | -$11,006 | -$12,090 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $11,530 | 79.4 % | $20,202, 96.8 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $8,091 | 78.6 % | $4,028, 67.5 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | -$12,180 | 15.0 % | -$23,832, 0.1 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $10,886 -> $8,258 under stress.
* Average variant, 2025: -$9,371 -> -$11,006 under stress.
* Default variant: BUILD $38,492 -> $35,642; 2024 $35,934 -> $28,219; 2025 $24,446 -> $23,316.
* Surviving set: 50 of 96 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 2 %, 2024 2 %, 2025 2 %, combined 2 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 2 %, 2024 -11 %, 2025 n/a, combined 0 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, 0 % of the net profit; those 1 trades net -$384.

## Size
* Worst open loss on one trade (default, 1 contract): $525 = $54 per micro -> at most 37 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `orb-NQ-tf15|pre|`.
