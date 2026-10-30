# The middle-third skip: in-sample check (Amendment M; every NQ New York store, every box; nothing picked here)

75 stores, 10780 boxes. A middle day = the 09:30 open in the middle third of the 01:00-09:30 range. Averages = the average box of each store.

| Test (expected, written first) | Result |
|---|---|
| Holds (other > middle) in >= 70 % of stores, all months | 57 of 75 (76 %) |
| ... in the first half (2021-10..2023-12) | 55 of 75 (73 %) |
| ... in the second half (2024-01..2026-04) | 42 of 75 (56 %) |
| Holds in >= 4 of the 5 full years (stores where other - middle > 0, by year) | 2021: 19/73, 2022: 56/74, 2023: 55/73, 2024: 53/73, 2025: 39/74, 2026: 20/73 |
| Share of trades on middle days (mean over stores) | 31 % |
| Average trade, middle vs other days (mean over stores) | $-2.3 vs $23.7 |
| First half, middle vs other | $-11.6 vs $24.8 |
| Second half, middle vs other | $8.9 vs $21.8 |

## Verdict against Amendment M's EXPECTED line (written before the run)
**A weak lead, reported, not used.** It holds in 76 % of stores over all months and 73 % in the first half, but only 56 % in the second
half and 53 % of stores in 2025 (2022: 76 %, 2023: 75 %, 2024: 73 %). The gap shrank from $36 a trade (H1: -$11.6 vs +$24.8) to $13 (H2:
+$8.9 vs +$21.8). Of the 10 stack A / B rules, 3 hold in both halves (ORB confirm long, Donchian 15m, displacement 15m); 5 hold in the
first half only; the overnight-range ORB never trades middle days by construction. Nothing is re-picked. The skip stays what it was: a
free forward test (the day tag in STACK_REPORT.md), read once at the stacks' read dates under Amendment M's forward bar.

## Per store

| Store | Boxes | Middle share | Avg middle | Avg other | H1 mid / other | H2 mid / other | Holds all / H1 / H2 |
|---|---|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 180 | 33 % | 109 | 202 | 106 / 48 | 111 / 300 | Y / n / Y |
| vh_i27_onrorb_15_ny-NQ-tf15 | 180 | 0 % | nan | 127 | nan / 133 | nan / 123 | n / n / n |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 40 | 35 % | -46 | 122 | 67 / 161 | -185 / 86 | Y / Y / Y |
| vh_i7_orb_15_ny-NQ-tf15 | 180 | 30 % | 72 | 116 | 14 / 118 | 136 / 116 | Y / Y / n |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 180 | 32 % | 52 | 112 | 92 / 122 | 11 / 102 | Y / Y / Y |
| vh_i6_g_donch_15_ny-NQ-tf15 | 180 | 31 % | 34 | 106 | 35 / 115 | 33 / 97 | Y / Y / Y |
| vh_i7_orb_5_ny-NQ-tf5 | 180 | 30 % | 50 | 87 | -55 / 67 | 182 / 108 | Y / Y / n |
| vh_i12_orbpb_15_ny-NQ-tf15 | 180 | 32 % | -19 | 85 | -112 / 91 | 96 / 79 | Y / Y / n |
| vh_i12_orbpb_1_ny-NQ-tf1 | 180 | 31 % | 24 | 74 | -64 / 47 | 119 / 99 | Y / Y / n |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 180 | 30 % | -0 | 74 | 53 / 59 | -42 / 88 | Y / Y / Y |
| vh_i12_orbpb_5_ny-NQ-tf5 | 180 | 31 % | 16 | 67 | -69 / 62 | 114 / 71 | Y / Y / n |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 180 | 29 % | 15 | 66 | -61 / 77 | 107 / 55 | Y / Y / n |
| vh_i6_g_donch_5_ny-NQ-tf5 | 180 | 30 % | -12 | 64 | 10 / 59 | -37 / 69 | Y / Y / Y |
| vh_i6_g_disp_15_ny-NQ-tf15 | 180 | 31 % | 40 | 63 | 18 / 55 | 67 / 70 | Y / Y / Y |
| vh_i7_orb_1_ny-NQ-tf1 | 180 | 30 % | 28 | 59 | -38 / 55 | 105 / 64 | Y / Y / n |
| vh_i16_emax_15_ny-NQ-tf15 | 180 | 40 % | 2 | 58 | -36 / 47 | 52 / 70 | Y / Y / Y |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 180 | 32 % | 28 | 55 | 90 / 39 | -15 / 67 | Y / n / Y |
| vh_i5_touch_us_15_ny-NQ-tf15 | 120 | 31 % | -11 | 55 | -113 / 67 | 72 / 45 | Y / Y / n |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 180 | 30 % | 1 | 40 | 12 / 48 | -11 / 33 | Y / Y / Y |
| vh_i1_pb_15_ny-NQ-tf15 | 180 | 33 % | -51 | 38 | -73 / 23 | -26 / 53 | Y / Y / Y |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 120 | 32 % | 1 | 37 | -69 / 40 | 62 / 34 | Y / Y / n |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 120 | 28 % | 4 | 36 | 22 / 39 | -17 / 33 | Y / Y / Y |
| vh_i2_tp_15_ny-NQ-tf15 | 120 | 29 % | -4 | 34 | -30 / 60 | 30 / 5 | Y / Y / n |
| vh_i6_g_disp_5_ny-NQ-tf5 | 180 | 31 % | 14 | 34 | 25 / 27 | 1 / 40 | Y / Y / Y |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 120 | 32 % | -30 | 33 | -10 / 61 | -48 / 7 | Y / Y / Y |
| vh_i9_noise_long_5_ny-NQ-tf5 | 120 | 30 % | 48 | 31 | 80 / 47 | 13 / 14 | n / n / Y |
| vh_i2_tp_5_ny-NQ-tf5 | 120 | 30 % | -6 | 26 | 6 / 46 | -20 / 5 | Y / Y / Y |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 180 | 29 % | 27 | 24 | -14 / 19 | 83 / 28 | n / Y / n |
| vh_i10_adx_touch_5_ny-NQ-tf5 | 120 | 26 % | -37 | 21 | -88 / 14 | 11 / 28 | Y / Y / Y |
| vh_i11_flip_gx_15_ny-NQ-tf15 | 120 | 33 % | -43 | 21 | -15 / 52 | -71 / -11 | Y / Y / Y |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | 120 | 33 % | -38 | 20 | -9 / 48 | -65 / -7 | Y / Y / Y |
| vh_i5_touch_us_5_ny-NQ-tf5 | 120 | 30 % | -12 | 18 | -57 / 22 | 25 / 15 | Y / Y / n |
| vh_i1_pb_1_ny-NQ-tf1 | 180 | 30 % | -13 | 18 | -61 / 40 | 39 / -3 | Y / Y / n |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 180 | 30 % | 16 | 17 | -2 / -22 | 35 / 51 | Y / n / Y |
| vh_i23_fbar_5_all-NQ-tf5 | 180 | 30 % | -9 | 15 | 1 / 22 | -20 / 8 | Y / Y / Y |
| vh_i16_emavwma_5_ny-NQ-tf5 | 180 | 33 % | 1 | 12 | -23 / 9 | 27 / 14 | Y / Y / n |
| vh_i1_pb_5_ny-NQ-tf5 | 180 | 32 % | -2 | 12 | -19 / 37 | 16 / -9 | Y / Y / n |
| vh_i10_adx_flip_5_ny-NQ-tf5 | 120 | 26 % | -52 | 11 | -39 / -4 | -67 / 27 | Y / Y / Y |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 120 | 32 % | -12 | 11 | -29 / -42 | 5 / 55 | Y / n / Y |
| vh_i15_flip_wk_5_ny-NQ-tf5 | 120 | 32 % | -21 | 11 | -25 / 15 | -17 / 8 | Y / Y / Y |
| vh_i15_flip_long_5_ny-NQ-tf5 | 120 | 34 % | -10 | 10 | -4 / 10 | -13 / 9 | Y / Y / Y |
| vh_i2_tp_1_ny-NQ-tf1 | 120 | 30 % | -11 | 5 | -17 / 18 | -4 / -8 | Y / Y / n |
| vh_i11_flip_gx_1_ny-NQ-tf1 | 120 | 32 % | -35 | 4 | -49 / 5 | -20 / 3 | Y / Y / Y |
| vh_i5_touch_us_1_ny-NQ-tf1 | 120 | 30 % | -36 | 4 | -63 / 0 | -13 / 6 | Y / Y / Y |
| vh_i6_g_fvg_5_ny-NQ-tf5 | 180 | 31 % | -19 | 4 | 6 / 2 | -48 / 5 | Y / n / Y |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | 120 | 33 % | -15 | 3 | 2 / 5 | -32 / 2 | Y / Y / Y |
| vh_i16_emavwma_15_ny-NQ-tf15 | 180 | 31 % | -1 | 3 | 14 / 33 | -22 / -25 | Y / Y / n |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | 180 | 31 % | -12 | 3 | -21 / 4 | -3 / 1 | Y / Y / Y |
| vh_i11_flip_gx_5_ny-NQ-tf5 | 120 | 34 % | -11 | 2 | -2 / 4 | -21 / -1 | Y / Y / Y |
| vh_i9_bbrk_5_ny-NQ-tf5 | 120 | 30 % | -20 | -1 | -9 / -5 | -33 / 4 | Y / Y / Y |
| vh_i16_emax_5_ny-NQ-tf5 | 180 | 33 % | 3 | -1 | -5 / -4 | 11 / 2 | n / Y / n |
| vh_i16_emax_side_5_ny-NQ-tf5 | 180 | 33 % | 6 | -1 | -4 / -2 | 17 / -1 | n / Y / n |
| vh_i3_flip_15_ny-NQ-tf15 | 120 | 32 % | -44 | -2 | -7 / 26 | -81 / -29 | Y / Y / Y |
| vh_i15_flip_long_15_ny-NQ-tf15 | 120 | 33 % | -7 | -2 | -9 / 21 | -3 / -24 | Y / Y / n |
| vh_i9_noise_short_5_ny-NQ-tf5 | 120 | 27 % | -35 | -2 | 1 / 31 | -68 / -32 | Y / Y / Y |
| vh_i13_reclaim_15_ny-NQ-tf15 | 120 | 31 % | 54 | -3 | 78 / 51 | 37 / -65 | n / n / n |
| vh_i3_flip_5_ny-NQ-tf5 | 120 | 32 % | -28 | -5 | -10 / -7 | -47 / -2 | Y / Y / Y |
| vh_i3_flip_1_ny-NQ-tf1 | 120 | 31 % | -24 | -6 | -40 / -6 | -8 / -6 | Y / Y / Y |
| vh_i20_holy_grail_5_ny-NQ-tf5 | 180 | 24 % | -48 | -9 | -87 / 18 | 2 / -35 | Y / Y / n |
| vh_i13_reclaim_5_ny-NQ-tf5 | 120 | 34 % | -19 | -9 | -1 / 4 | -32 / -22 | Y / Y / Y |
| vh_i9_bbrk_15_ny-NQ-tf15 | 120 | 30 % | -27 | -11 | -28 / -5 | -26 / -17 | Y / Y / Y |
| vh_i4_emax_5_ny-NQ-tf5 | 120 | 31 % | 21 | -14 | 13 / 1 | 31 / -28 | n / n / n |
| vh_i15_touch_long_5_ny-NQ-tf5 | 120 | 32 % | -22 | -14 | -41 / -40 | -5 / 7 | Y / Y / Y |
| vh_i26_rv_look_5_ny-NQ-tf5 | 120 | 30 % | -15 | -16 | -22 / -34 | -8 / 1 | n / n / Y |
| vh_i8_z_15_ny-NQ-tf15 | 120 | 30 % | -28 | -18 | -15 / -32 | -42 / -3 | Y / n / Y |
| vh_i8_band_5_ny-NQ-tf5 | 120 | 30 % | 10 | -19 | -5 / -11 | 26 / -27 | n / n / n |
| vh_i8_z_5_ny-NQ-tf5 | 120 | 30 % | 18 | -19 | -7 / -7 | 45 / -31 | n / n / n |
| vh_i26_rv_15_ny-NQ-tf15 | 120 | 30 % | -7 | -20 | -20 / -27 | 1 / -13 | n / n / n |
| vh_i4_emax_15_ny-NQ-tf15 | 120 | 35 % | 12 | -21 | 20 / -15 | 3 / -25 | n / n / n |
| vh_i15_touch_long_15_ny-NQ-tf15 | 120 | 33 % | -17 | -21 | -32 / -60 | -3 / 12 | n / n / Y |
| vh_i26_rv_1_ny-NQ-tf1 | 120 | 30 % | -9 | -22 | -13 / -30 | -5 / -15 | n / n / n |
| vh_i26_rv_5_ny-NQ-tf5 | 120 | 30 % | -7 | -23 | -17 / -42 | 3 / -5 | n / n / n |
| vh_i13_reclaim_1_ny-NQ-tf1 | 120 | 32 % | -26 | -27 | -41 / -3 | -12 / -50 | n / Y / n |
| vh_i8_band_15_ny-NQ-tf15 | 120 | 30 % | 4 | -39 | 14 / -55 | -7 / -22 | n / n / n |
| vh_i10_adx_emax_5_ny-NQ-tf5 | 120 | 27 % | 70 | -42 | 41 / -15 | 124 / -71 | n / n / n |
