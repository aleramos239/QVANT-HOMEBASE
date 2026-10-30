# The day-type study: in-sample check (Note N; every NQ New York store, every box; nothing picked here)

75 stores, 10780 boxes (>= 50 NY in-sample trades each), 876 in-sample days. Each feature is known by 09:30 ET of the trade date and cut in thirds over the in-sample days (tertiles; the open's place in the range keeps the middle-third definition). Averages = the average box of each store, $ a trade. Halves: H1 = 2021-10..2023-12, H2 = 2024-01..2026-04. 'Holds' = the store's best third (chosen on all months, over all stores) beats its worst; the strict column chooses the thirds on H1 alone and reads H2. Day tags from ~/futures_1m/NQ_1m.csv (front month; may differ from the engine's contract on roll days).

## The answer

**Leads** (hold in >= 70 % of stores in BOTH halves): gap (up beats flat).  
**Noise**: onr, gap_abs, drift, drift_abs, pos.  
A lead found in-sample proves nothing in-sample (Note N): it is not applied to any stack; it may become a day tag in STACK_REPORT.md with its own written forward bar, read once at the stacks' read dates.

## Reading (written after the run, by hand)

**One lead, and it is "a flat open is bad", not "an up gap is good".** The signed gap's flat third (open within -0.105..+0.163 of the
20-day daily range from the prior 16:00 close; 34 % of trades) averages $-8.4 a trade; both gap sides are positive (up $35.0, down $22.8).
Flat is the worst third in 50 of 75 stores. Up beats flat in 80 % (H1) / 79 % (H2) of stores and passes the bar; up beats down in only
64 % / 60 % (a coin flip between the two gap sides); down beats flat in 67 % / 67 % (short of the bar).

**It leans on the cut.** The same days read as |gap| small (<= 0.135; 359 of 390 flat days are also "small") against |gap| big hold in only
65 % / 67 % of stores. One pair of thirds clears 70 % in both halves, the two neighbouring pairs do not. The half-split check that chooses the
thirds on H1 alone gives the same pair (up vs flat, 79 % in H2), so it is not a pick made on H2, but it is one comparison out of several
near-identical ones. Read it as a weak lead, like the middle-third skip: the middle-third skip itself (pos) is 68 % / 63 % here, below the bar,
as MID3_CHECK.md already found.

**Nothing is picked.** Per Note N, the lead is not applied to any stack in-sample; if the owner wants it, it becomes a day tag in STACK_REPORT.md
(a "no-gap day" = |09:30 open - prior 16:00 close| inside the flat band above) with its own written forward bar (Amendment M style), read once
at the stacks' read dates. The other five features (overnight range size, |gap|, overnight drift sign and size, the open's place in the range)
each hold in one half or neither: noise.

## Verdicts against Note N's EXPECTED line (written before the run)

| Feature | Best third | Worst third | Holds, all months | H1 | H2 | H2, thirds chosen on H1 | Verdict |
|---|---|---|---|---|---|---|---|
| onr | mid ($25.5) | small ($9.1) | 48 of 75 (64 %) | 38 of 75 (51 %) | 47 of 75 (63 %) | mid vs big: 34 of 75 (45 %) | noise |
| gap | up ($35.0) | flat ($-8.4) | 63 of 75 (84 %) | 60 of 75 (80 %) | 59 of 75 (79 %) | up vs flat: 59 of 75 (79 %) | LEAD |
| gap_abs | big ($31.4) | small ($-1.0) | 58 of 75 (77 %) | 49 of 75 (65 %) | 50 of 75 (67 %) | big vs small: 50 of 75 (67 %) | noise |
| drift | up ($25.2) | down ($9.8) | 49 of 75 (65 %) | 53 of 75 (71 %) | 45 of 75 (60 %) | up vs down: 45 of 75 (60 %) | noise |
| drift_abs | mid ($28.0) | small ($5.3) | 56 of 75 (75 %) | 51 of 75 (68 %) | 48 of 75 (64 %) | mid vs small: 48 of 75 (64 %) | noise |
| pos | top ($30.0) | middle ($-2.3) | 59 of 75 (79 %) | 51 of 75 (68 %) | 47 of 75 (63 %) | bottom vs middle: 35 of 75 (47 %) | noise |

## Per feature

### 1. onr: overnight range (01:00-09:30) / 20-day daily range

Cuts (units of the 20-day daily range): small <= 0.342, mid to 0.501, big above. Tagged trades: 100 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| small | 32 % | $9.1 | $14.3 | $1.5 | 12 |
| mid | 33 % | $25.5 | $15.2 | $33.0 | 36 |
| big | 35 % | $13.2 | $2.1 | $20.4 | 27 |

mid beats small in 48 of 75 (64 %) of stores (all months), 38 of 75 (51 %) in H1, 47 of 75 (63 %) in H2. Thirds chosen on H1 alone (mid vs big): hold in H2 in 34 of 75 (45 %). **Verdict: noise** (the bar: >= 70 % in both halves).

### 2. gap: 09:30 open - prior session's 16:00 close, / 20-day daily range (signed)

Cuts (units of the 20-day daily range): down <= -0.105, flat to 0.163, up above. Tagged trades: 98 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| down | 34 % | $22.8 | $15.1 | $30.1 | 24 |
| flat | 34 % | $-8.4 | $0.6 | $-19.8 | 7 |
| up | 33 % | $35.0 | $28.7 | $39.3 | 44 |

up beats flat in 63 of 75 (84 %) of stores (all months), 60 of 75 (80 %) in H1, 59 of 75 (79 %) in H2. Thirds chosen on H1 alone (up vs flat): hold in H2 in 59 of 75 (79 %). **Verdict: LEAD** (the bar: >= 70 % in both halves).

### 3. gap_abs: |gap| / 20-day daily range

Cuts (units of the 20-day daily range): small <= 0.135, mid to 0.342, big above. Tagged trades: 98 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| small | 34 % | $-1.0 | $1.6 | $-4.7 | 10 |
| mid | 33 % | $16.8 | $16.2 | $17.6 | 32 |
| big | 33 % | $31.4 | $23.6 | $37.7 | 33 |

big beats small in 58 of 75 (77 %) of stores (all months), 49 of 75 (65 %) in H1, 50 of 75 (67 %) in H2. Thirds chosen on H1 alone (big vs small): hold in H2 in 50 of 75 (67 %). **Verdict: noise** (the bar: >= 70 % in both halves).

### 4. drift: 09:30 open - 18:00 open the evening before, / 20-day daily range (signed)

Cuts (units of the 20-day daily range): down <= -0.105, flat to 0.150, up above. Tagged trades: 100 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| down | 33 % | $9.8 | $3.1 | $16.0 | 17 |
| flat | 34 % | $13.7 | $10.0 | $16.6 | 15 |
| up | 33 % | $25.2 | $27.2 | $22.2 | 43 |

up beats down in 49 of 75 (65 %) of stores (all months), 53 of 75 (71 %) in H1, 45 of 75 (60 %) in H2. Thirds chosen on H1 alone (up vs down): hold in H2 in 45 of 75 (60 %). **Verdict: noise** (the bar: >= 70 % in both halves).

### 5. drift_abs: |drift| / 20-day daily range

Cuts (units of the 20-day daily range): small <= 0.126, mid to 0.311, big above. Tagged trades: 100 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| small | 34 % | $5.3 | $2.1 | $7.8 | 12 |
| mid | 33 % | $28.0 | $25.4 | $30.5 | 40 |
| big | 33 % | $14.3 | $14.3 | $15.3 | 23 |

mid beats small in 56 of 75 (75 %) of stores (all months), 51 of 75 (68 %) in H1, 48 of 75 (64 %) in H2. Thirds chosen on H1 alone (mid vs small): hold in H2 in 48 of 75 (64 %). **Verdict: noise** (the bar: >= 70 % in both halves).

### 6. pos: the 09:30 open's place in the 01:00-09:30 range (the middle-third definition)

Cuts: the open below the bottom third / inside the middle third / above the top third of the range. Tagged trades: 100 %.

| Third | Share of trades | Avg all | Avg H1 | Avg H2 | Stores where it is the best third |
|---|---|---|---|---|---|
| bottom | 33 % | $16.1 | $26.5 | $4.4 | 21 |
| middle | 31 % | $-2.3 | $-11.6 | $8.9 | 9 |
| top | 36 % | $30.0 | $22.0 | $34.5 | 45 |

top beats middle in 59 of 75 (79 %) of stores (all months), 51 of 75 (68 %) in H1, 47 of 75 (63 %) in H2. Thirds chosen on H1 alone (bottom vs middle): hold in H2 in 35 of 75 (47 %). **Verdict: noise** (the bar: >= 70 % in both halves).

## Per store

Y / n = holds (best third beats worst, the thirds above) on all months / H1 / H2.

| Store | Boxes | onr | gap | gap_abs | drift | drift_abs | pos |
|---|---|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 180 | Y / n / Y | n / n / Y | n / n / n | Y / n / Y | n / n / n | Y / n / Y |
| vh_i27_onrorb_15_ny-NQ-tf15 | 180 | Y / Y / Y | n / n / n | Y / Y / Y | n / Y / n | Y / Y / n | n / n / n |
| vh_i7_orb_15_ny-NQ-tf15 | 180 | Y / Y / n | Y / n / Y | Y / n / Y | Y / Y / n | Y / n / Y | Y / Y / Y |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 180 | n / n / n | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / n | Y / Y / Y |
| vh_i6_g_donch_15_ny-NQ-tf15 | 180 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i7_orb_5_ny-NQ-tf5 | 180 | Y / Y / n | Y / Y / Y | Y / n / Y | Y / Y / n | Y / Y / Y | Y / Y / n |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 40 | Y / n / Y | n / n / Y | n / n / n | n / n / n | n / Y / n | Y / n / Y |
| vh_i12_orbpb_1_ny-NQ-tf1 | 180 | n / n / Y | Y / Y / Y | Y / n / Y | n / Y / n | Y / Y / Y | Y / Y / n |
| vh_i6_g_disp_15_ny-NQ-tf15 | 180 | Y / Y / Y | Y / Y / Y | Y / Y / Y | n / n / Y | Y / n / Y | n / n / Y |
| vh_i12_orbpb_15_ny-NQ-tf15 | 180 | Y / n / Y | Y / Y / Y | Y / n / Y | n / Y / n | Y / Y / Y | Y / Y / n |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / n |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / n / Y | Y / Y / Y | n / Y / n | n / n / n | Y / n / Y |
| vh_i12_orbpb_5_ny-NQ-tf5 | 180 | Y / n / Y | Y / Y / Y | Y / n / Y | n / Y / n | Y / Y / Y | Y / Y / n |
| vh_i7_orb_1_ny-NQ-tf1 | 180 | Y / Y / Y | Y / Y / Y | Y / n / Y | n / Y / n | Y / Y / Y | Y / Y / n |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / n / Y | Y / Y / Y | n / n / n | n / n / Y | Y / n / Y |
| vh_i6_g_donch_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / n | Y / Y / Y |
| vh_i9_noise_long_5_ny-NQ-tf5 | 120 | n / n / n | Y / Y / Y | Y / n / Y | Y / Y / Y | n / Y / n | Y / n / Y |
| vh_i16_emax_15_ny-NQ-tf15 | 180 | n / Y / n | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i5_touch_us_15_ny-NQ-tf15 | 120 | Y / Y / n | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / n |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 180 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i6_g_disp_5_ny-NQ-tf5 | 180 | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / n | Y / n / Y |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 120 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / n / Y | Y / Y / Y |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 120 | Y / Y / Y | Y / Y / Y | Y / Y / Y | n / Y / n | n / n / n | Y / Y / n |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 180 | Y / n / Y | Y / Y / Y | Y / Y / Y | n / Y / n | Y / Y / Y | n / Y / n |
| vh_i2_tp_15_ny-NQ-tf15 | 120 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / n / Y | Y / Y / Y |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / Y / n | n / Y / n | n / Y / n | Y / Y / Y | Y / n / Y |
| vh_i2_tp_5_ny-NQ-tf5 | 120 | Y / Y / Y | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 120 | n / n / n | Y / Y / Y | Y / Y / n | n / n / Y | Y / Y / n | Y / Y / Y |
| vh_i13_reclaim_15_ny-NQ-tf15 | 120 | n / n / n | Y / Y / Y | Y / Y / n | Y / Y / n | n / Y / n | n / n / n |
| vh_i1_pb_15_ny-NQ-tf15 | 180 | n / n / Y | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / n / Y | Y / Y / Y |
| vh_i5_touch_us_5_ny-NQ-tf5 | 120 | n / n / Y | Y / n / Y | Y / Y / Y | n / n / n | Y / Y / Y | Y / Y / n |
| vh_i16_emavwma_5_ny-NQ-tf5 | 180 | n / n / n | Y / Y / Y | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / n |
| vh_i1_pb_1_ny-NQ-tf1 | 180 | Y / n / Y | n / Y / n | Y / Y / Y | Y / Y / n | Y / Y / n | Y / Y / n |
| vh_i23_fbar_5_all-NQ-tf5 | 180 | n / n / n | Y / n / Y | Y / n / Y | Y / Y / Y | Y / Y / n | Y / Y / Y |
| vh_i1_pb_5_ny-NQ-tf5 | 180 | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | n / Y / n | Y / Y / Y |
| vh_i10_adx_touch_5_ny-NQ-tf5 | 120 | Y / n / Y | Y / Y / Y | Y / Y / Y | n / n / n | n / Y / n | Y / Y / n |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 120 | n / n / n | Y / n / Y | n / n / Y | n / Y / n | n / n / n | Y / Y / Y |
| vh_i15_flip_long_5_ny-NQ-tf5 | 120 | Y / n / Y | Y / Y / Y | Y / Y / Y | n / n / Y | Y / Y / Y | Y / n / Y |
| vh_i16_emavwma_15_ny-NQ-tf15 | 180 | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / n / Y | Y / n / Y | Y / n / Y |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | 120 | n / n / Y | Y / Y / Y | Y / Y / n | Y / n / Y | Y / Y / Y | Y / Y / Y |
| vh_i16_emax_side_5_ny-NQ-tf5 | 180 | n / n / n | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i15_flip_wk_5_ny-NQ-tf5 | 120 | n / Y / n | Y / Y / Y | Y / n / Y | Y / Y / n | Y / n / Y | Y / Y / Y |
| vh_i16_emax_5_ny-NQ-tf5 | 180 | n / n / n | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i2_tp_1_ny-NQ-tf1 | 120 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / n | Y / Y / Y | Y / Y / n |
| vh_i11_flip_gx_15_ny-NQ-tf15 | 120 | n / n / Y | Y / Y / Y | Y / Y / n | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | 180 | Y / Y / n | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | 120 | n / n / n | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i11_flip_gx_5_ny-NQ-tf5 | 120 | Y / Y / n | Y / Y / Y | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i6_g_fvg_5_ny-NQ-tf5 | 180 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / n / Y |
| vh_i4_emax_5_ny-NQ-tf5 | 120 | Y / Y / Y | n / Y / n | n / Y / n | Y / Y / Y | Y / n / Y | n / Y / n |
| vh_i15_flip_long_15_ny-NQ-tf15 | 120 | Y / Y / n | Y / Y / Y | Y / Y / Y | n / n / n | n / n / Y | Y / Y / n |
| vh_i10_adx_flip_5_ny-NQ-tf5 | 120 | n / n / n | Y / Y / n | Y / Y / Y | Y / Y / n | Y / Y / n | Y / Y / Y |
| vh_i9_bbrk_5_ny-NQ-tf5 | 120 | n / Y / n | Y / Y / n | n / n / n | Y / Y / Y | Y / Y / Y | Y / n / Y |
| vh_i4_emax_15_ny-NQ-tf15 | 120 | Y / Y / Y | n / Y / n | n / Y / n | Y / Y / Y | Y / Y / n | n / n / n |
| vh_i8_z_5_ny-NQ-tf5 | 120 | Y / Y / Y | n / n / n | n / Y / n | n / n / n | Y / n / Y | n / n / n |
| vh_i5_touch_us_1_ny-NQ-tf1 | 120 | n / n / n | Y / Y / Y | Y / Y / n | n / n / n | Y / Y / n | Y / Y / Y |
| vh_i11_flip_gx_1_ny-NQ-tf1 | 120 | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | Y / Y / n | Y / Y / Y |
| vh_i8_band_5_ny-NQ-tf5 | 120 | Y / Y / n | n / n / n | n / n / Y | n / n / n | Y / n / Y | n / n / n |
| vh_i9_noise_short_5_ny-NQ-tf5 | 120 | Y / Y / Y | Y / Y / Y | n / Y / n | Y / Y / Y | Y / n / Y | Y / Y / Y |
| vh_i10_adx_emax_5_ny-NQ-tf5 | 120 | Y / n / Y | Y / Y / Y | Y / Y / Y | Y / Y / Y | n / Y / n | n / n / n |
| vh_i3_flip_1_ny-NQ-tf1 | 120 | Y / n / Y | Y / Y / n | Y / Y / n | Y / Y / Y | Y / Y / n | Y / Y / Y |
| vh_i3_flip_5_ny-NQ-tf5 | 120 | n / n / n | Y / Y / Y | Y / Y / n | Y / Y / Y | Y / Y / Y | Y / Y / Y |
| vh_i13_reclaim_5_ny-NQ-tf5 | 120 | Y / Y / Y | Y / Y / n | Y / Y / n | Y / n / Y | Y / Y / Y | Y / Y / Y |
| vh_i3_flip_15_ny-NQ-tf15 | 120 | n / n / Y | Y / Y / Y | Y / Y / n | Y / n / Y | Y / Y / n | Y / Y / Y |
| vh_i26_rv_look_5_ny-NQ-tf5 | 120 | n / Y / n | Y / Y / Y | n / Y / n | Y / Y / Y | n / n / Y | Y / Y / Y |
| vh_i9_bbrk_15_ny-NQ-tf15 | 120 | Y / Y / Y | n / n / Y | n / n / n | Y / n / Y | n / n / n | Y / Y / Y |
| vh_i15_touch_long_5_ny-NQ-tf5 | 120 | Y / Y / Y | n / n / Y | n / n / n | n / Y / n | Y / n / Y | n / n / Y |
| vh_i26_rv_15_ny-NQ-tf15 | 120 | n / n / n | Y / Y / Y | Y / n / Y | Y / Y / Y | n / n / Y | Y / Y / n |
| vh_i20_holy_grail_5_ny-NQ-tf5 | 180 | n / n / n | Y / Y / Y | Y / n / Y | Y / Y / Y | n / Y / n | Y / Y / Y |
| vh_i26_rv_1_ny-NQ-tf1 | 120 | n / n / n | Y / Y / n | n / Y / n | n / Y / n | n / n / n | n / n / n |
| vh_i26_rv_5_ny-NQ-tf5 | 120 | n / n / n | Y / Y / n | Y / Y / n | Y / Y / n | n / n / Y | n / n / n |
| vh_i15_touch_long_15_ny-NQ-tf15 | 120 | Y / Y / Y | Y / n / Y | n / n / Y | n / n / n | n / n / Y | n / n / n |
| vh_i8_z_15_ny-NQ-tf15 | 120 | Y / n / Y | n / Y / n | n / Y / n | n / n / Y | Y / Y / Y | n / n / Y |
| vh_i8_band_15_ny-NQ-tf15 | 120 | Y / n / Y | n / Y / n | n / n / n | n / n / n | Y / Y / Y | n / n / n |
| vh_i13_reclaim_1_ny-NQ-tf1 | 120 | Y / Y / Y | Y / Y / n | Y / Y / n | Y / n / Y | Y / Y / n | n / Y / n |

## Per store, the average box on each third ($ a trade; all months, then H1 / H2)

### onr

| Store | small | mid | big | H1 small / mid / big | H2 small / mid / big |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 107 | 297 | 74 | 287 / 6 / -367 | -128 / 436 / 221 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 83 | 276 | 7 | 9 / 285 / 5 | 143 / 262 / 9 |
| vh_i7_orb_15_ny-NQ-tf15 | 84 | 106 | 110 | 14 / 93 / 144 | 143 / 140 / 80 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 132 | 64 | 81 | 154 / 121 / 58 | 110 / -3 / 99 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 80 | 134 | 34 | 88 / 148 / 12 | 72 / 115 / 54 |
| vh_i7_orb_5_ny-NQ-tf5 | 69 | 74 | 81 | -5 / 69 / 13 | 139 / 84 / 154 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 22 | 166 | -16 | 277 / 186 / -334 | -349 / 152 / 252 |
| vh_i12_orbpb_1_ny-NQ-tf1 | 42 | 40 | 94 | 39 / -35 / 28 | 44 / 117 / 156 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 30 | 57 | 86 | 8 / 30 / 103 | 53 / 88 / 69 |
| vh_i12_orbpb_15_ny-NQ-tf15 | 63 | 75 | 14 | 81 / 36 / -60 | 44 / 117 / 95 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 7 | 89 | 55 | 2 / 85 / 11 | 11 / 93 / 107 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | -7 | 99 | 55 | 54 / 77 / 41 | -58 / 118 / 67 |
| vh_i12_orbpb_5_ny-NQ-tf5 | 52 | 54 | 48 | 59 / -36 / 33 | 46 / 150 / 66 |
| vh_i7_orb_1_ny-NQ-tf1 | 30 | 51 | 68 | -1 / 37 / 41 | 62 / 70 / 96 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | -16 | 91 | 63 | 42 / 110 / 28 | -75 / 81 / 84 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 32 | 64 | 26 | 40 / 80 / 5 | 24 / 46 / 46 |
| vh_i9_noise_long_5_ny-NQ-tf5 | 70 | 21 | 23 | 94 / 52 / 29 | 40 / -17 / 19 |
| vh_i16_emax_15_ny-NQ-tf15 | 30 | 21 | 57 | 8 / 23 / 6 | 55 / 20 / 122 |
| vh_i5_touch_us_15_ny-NQ-tf15 | 64 | 69 | -17 | 23 / 43 / -28 | 98 / 93 / -11 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 23 | 35 | 26 | 27 / 42 / 40 | 20 / 28 / 13 |
| vh_i6_g_disp_5_ny-NQ-tf5 | 7 | 9 | 71 | 2 / -2 / 90 | 12 / 21 / 54 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 15 | 43 | 23 | 23 / 49 / 29 | 8 / 36 / 17 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 18 | 39 | 19 | 6 / 12 / -7 | 27 / 65 / 38 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 27 | 39 | 8 | 61 / 24 / -65 | -9 / 61 / 73 |
| vh_i2_tp_15_ny-NQ-tf15 | 1 | 61 | 7 | 11 / 64 / 19 | -9 / 57 / -5 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | -27 | 90 | -5 | -103 / -103 / 124 | 70 / 235 / -104 |
| vh_i2_tp_5_ny-NQ-tf5 | 2 | 35 | 11 | 24 / 48 / 27 | -20 / 19 / -4 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 26 | 7 | 4 | 42 / 38 / 32 | 11 / -28 / -20 |
| vh_i13_reclaim_15_ny-NQ-tf15 | 51 | -27 | 12 | 37 / -3 / 111 | 72 / -67 / -62 |
| vh_i1_pb_15_ny-NQ-tf15 | -4 | -11 | 45 | -7 / -24 / 6 | -0 / 6 / 81 |
| vh_i5_touch_us_5_ny-NQ-tf5 | 20 | 16 | -4 | -5 / -9 / 7 | 40 / 40 / -12 |
| vh_i16_emavwma_5_ny-NQ-tf5 | 4 | -6 | 28 | -12 / -28 / 37 | 20 / 17 / 18 |
| vh_i1_pb_1_ny-NQ-tf1 | 10 | 20 | -4 | 14 / 9 / 1 | 6 / 32 / -8 |
| vh_i23_fbar_5_all-NQ-tf5 | 11 | -12 | 25 | 12 / -4 / 41 | 9 / -20 / 9 |
| vh_i1_pb_5_ny-NQ-tf5 | -1 | 11 | 14 | 5 / 1 / 53 | -7 / 21 / -18 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | -9 | -5 | 27 | -45 / -47 / 38 | 18 / 38 / 19 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 24 | 3 | -11 | -9 / -13 / -83 | 51 / 19 / 49 |
| vh_i15_flip_long_5_ny-NQ-tf5 | -10 | -1 | 21 | 2 / -6 / 22 | -17 / 5 / 19 |
| vh_i16_emavwma_15_ny-NQ-tf15 | -17 | 16 | 11 | 25 / 32 / 23 | -59 / -5 / -1 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | 3 | -7 | 9 | 45 / 7 / 37 | -35 / -24 / -17 |
| vh_i16_emax_side_5_ny-NQ-tf5 | 5 | -28 | 27 | -5 / -17 / 15 | 14 / -39 / 37 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | 10 | -3 | -6 | 13 / 14 / -27 | 8 / -21 / 12 |
| vh_i16_emax_5_ny-NQ-tf5 | 6 | -33 | 27 | -5 / -25 / 18 | 16 / -41 / 37 |
| vh_i2_tp_1_ny-NQ-tf1 | -5 | 5 | 0 | 8 / 17 / -3 | -16 / -9 / 3 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | -2 | -9 | 10 | 44 / 14 / 33 | -44 / -35 / -11 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | -4 | -1 | -1 | -12 / 3 / -3 | 4 / -5 / 1 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -2 | -5 | -0 | 5 / 3 / 3 | -8 / -14 / -4 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -2 | -1 | -5 | 2 / 12 / -7 | -6 / -16 / -2 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -12 | 4 | -1 | -1 / 1 / 9 | -23 / 8 / -12 |
| vh_i4_emax_5_ny-NQ-tf5 | -22 | 13 | -1 | -5 / 1 / 18 | -39 / 28 / -19 |
| vh_i15_flip_long_15_ny-NQ-tf15 | -16 | 2 | 4 | 26 / 51 / -44 | -47 / -54 / 53 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | 1 | -47 | 32 | -19 / -31 / 13 | 24 / -66 / 51 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -2 | -11 | -7 | -3 / 10 / -28 | -2 / -35 / 13 |
| vh_i4_emax_15_ny-NQ-tf15 | -52 | 19 | 12 | -17 / 24 / -6 | -82 / 13 / 23 |
| vh_i8_z_5_ny-NQ-tf5 | -25 | 5 | -4 | -26 / -18 / 22 | -24 / 32 / -29 |
| vh_i5_touch_us_1_ny-NQ-tf1 | 1 | -8 | -15 | -19 / -27 / -13 | 16 / 9 / -17 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -8 | 8 | -26 | -5 / 6 / -43 | -11 / 11 / -10 |
| vh_i8_band_5_ny-NQ-tf5 | -22 | -17 | 7 | -33 / -8 / 12 | -12 / -27 / 2 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -42 | 21 | -18 | -40 / 34 / 58 | -41 / 8 / -87 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | -16 | -14 | -4 | -24 / -31 / 64 | -6 / 8 / -82 |
| vh_i3_flip_1_ny-NQ-tf1 | -14 | -9 | -12 | -13 / -19 / -19 | -16 / 2 / -6 |
| vh_i3_flip_5_ny-NQ-tf5 | -10 | -22 | -4 | -11 / -22 / 10 | -8 / -23 / -17 |
| vh_i13_reclaim_5_ny-NQ-tf5 | -52 | 9 | -2 | -59 / -47 / 93 | -45 / 54 / -77 |
| vh_i3_flip_15_ny-NQ-tf15 | -9 | -27 | -9 | 32 / -13 / 29 | -48 / -43 / -45 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -14 | -29 | -4 | -39 / -35 / -17 | 7 / -22 / 7 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -20 | -7 | -20 | 0 / 14 / -51 | -38 / -33 / 7 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -3 | 32 | -68 | -31 / -9 / -74 | 16 / 71 / -63 |
| vh_i26_rv_15_ny-NQ-tf15 | -2 | -43 | -5 | 3 / -31 / -43 | -5 / -54 / 28 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | 2 | -31 | -17 | 37 / -31 / -13 | -24 / -27 / -20 |
| vh_i26_rv_1_ny-NQ-tf1 | -15 | -30 | -9 | -23 / -38 / -12 | -8 / -23 / -7 |
| vh_i26_rv_5_ny-NQ-tf5 | -12 | -38 | -5 | -38 / -42 / -23 | 11 / -33 / 10 |
| vh_i15_touch_long_15_ny-NQ-tf15 | -2 | 60 | -104 | -40 / -11 / -97 | 26 / 129 / -113 |
| vh_i8_z_15_ny-NQ-tf15 | -24 | -21 | -18 | -10 / -51 / -18 | -40 / 19 / -19 |
| vh_i8_band_15_ny-NQ-tf15 | -40 | -18 | -20 | -16 / -34 / -51 | -66 / 3 / 8 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -38 | -18 | -26 | -30 / -22 / 2 | -46 / -14 / -50 |
### gap

| Store | down | flat | up | H1 down / flat / up | H2 down / flat / up |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 126 | 213 | 177 | 33 / 236 / -121 | 142 / 190 / 384 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 223 | 155 | 40 | 91 / 234 / 109 | 351 / 75 / -16 |
| vh_i7_orb_15_ny-NQ-tf15 | 141 | 19 | 142 | 81 / 87 / 85 | 205 / -75 / 192 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 50 | 51 | 189 | 48 / 125 / 181 | 52 / -25 / 195 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 89 | 32 | 146 | 103 / 61 / 116 | 73 / -3 / 173 |
| vh_i7_orb_5_ny-NQ-tf5 | 114 | -29 | 148 | 38 / -4 / 74 | 209 / -67 / 215 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 108 | 56 | 34 | 185 / 189 / -26 | 63 / -173 / 85 |
| vh_i12_orbpb_1_ny-NQ-tf1 | 95 | 6 | 69 | -12 / -3 / 44 | 204 / 16 / 88 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 79 | 3 | 97 | 100 / -20 / 70 | 56 / 32 / 120 |
| vh_i12_orbpb_15_ny-NQ-tf15 | 119 | -75 | 102 | 3 / -11 / 75 | 242 / -141 / 130 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 54 | -22 | 123 | 15 / 17 / 63 | 104 / -74 / 177 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 84 | 28 | 55 | 83 / 50 / 47 | 85 / 9 / 63 |
| vh_i12_orbpb_5_ny-NQ-tf5 | 105 | -46 | 79 | -4 / -7 / 61 | 217 / -85 / 94 |
| vh_i7_orb_1_ny-NQ-tf1 | 81 | -4 | 79 | 45 / 4 / 38 | 133 / -18 / 114 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 99 | 18 | 45 | 120 / 54 / 2 | 80 / -11 / 72 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 35 | 5 | 91 | 47 / 22 / 67 | 23 / -14 / 111 |
| vh_i9_noise_long_5_ny-NQ-tf5 | 26 | 3 | 82 | 61 / 29 / 100 | -13 / -28 / 67 |
| vh_i16_emax_15_ny-NQ-tf15 | 28 | -26 | 135 | -4 / -32 / 90 | 77 / -18 / 175 |
| vh_i5_touch_us_15_ny-NQ-tf15 | 53 | -28 | 76 | -1 / 15 / 35 | 96 / -67 / 104 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 26 | 8 | 55 | 54 / 9 / 49 | -5 / 6 / 61 |
| vh_i6_g_disp_5_ny-NQ-tf5 | 33 | -8 | 63 | 41 / -14 / 69 | 25 / -2 / 58 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 24 | 1 | 63 | 8 / 25 / 77 | 45 / -25 / 50 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 74 | -25 | 20 | 4 / -6 / 32 | 131 / -44 / 13 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 65 | -35 | 39 | 21 / -46 / 44 | 116 / -23 / 32 |
| vh_i2_tp_15_ny-NQ-tf15 | 30 | -27 | 64 | 24 / -2 / 69 | 39 / -60 / 58 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 11 | 10 | 41 | -21 / -64 / 61 | 40 / 86 / 25 |
| vh_i2_tp_5_ny-NQ-tf5 | 1 | 5 | 46 | 12 / 34 / 52 | -11 / -29 / 40 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 37 | -7 | 12 | 84 / 13 / 41 | -13 / -27 / -11 |
| vh_i13_reclaim_15_ny-NQ-tf15 | 11 | -62 | 75 | 60 / -81 / 194 | -15 / -48 / -27 |
| vh_i1_pb_15_ny-NQ-tf15 | -5 | -10 | 33 | -36 / -16 / 13 | 29 / -2 / 49 |
| vh_i5_touch_us_5_ny-NQ-tf5 | 41 | -21 | -1 | 6 / -2 / -8 | 68 / -39 / 3 |
| vh_i16_emavwma_5_ny-NQ-tf5 | 5 | -2 | 23 | 24 / -27 / -4 | -15 / 26 / 46 |
| vh_i1_pb_1_ny-NQ-tf1 | -6 | 11 | 8 | -26 / 19 / 23 | 13 / 4 / -3 |
| vh_i23_fbar_5_all-NQ-tf5 | -14 | 22 | 30 | 12 / 39 / 11 | -43 / 3 / 46 |
| vh_i1_pb_5_ny-NQ-tf5 | -23 | -19 | 56 | -14 / -21 / 86 | -31 / -17 / 31 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | 59 | -47 | 10 | 4 / -42 / 6 | 105 / -52 / 13 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | -0 | 3 | 4 | -79 / -7 / -27 | 73 / 12 / 26 |
| vh_i15_flip_long_5_ny-NQ-tf5 | 22 | -33 | 23 | 42 / -35 / 12 | 3 / -32 / 32 |
| vh_i16_emavwma_15_ny-NQ-tf15 | 3 | -35 | 35 | 21 / 39 / 21 | -15 / -110 / 46 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | 4 | -37 | 36 | 65 / -22 / 58 | -59 / -49 / 17 |
| vh_i16_emax_side_5_ny-NQ-tf5 | -15 | -10 | 27 | 22 / -32 / -4 | -51 / 14 / 54 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | -0 | -4 | 4 | -34 / 18 / 24 | 34 / -28 / -9 |
| vh_i16_emax_5_ny-NQ-tf5 | -16 | -16 | 32 | 16 / -38 / 3 | -48 / 8 / 58 |
| vh_i2_tp_1_ny-NQ-tf1 | 5 | -17 | 12 | 1 / -10 / 32 | 9 / -25 / -4 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | 9 | -39 | 31 | 67 / -11 / 51 | -53 / -65 / 13 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | -5 | -19 | 17 | -5 / -24 / 18 | -6 / -13 / 16 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -26 | -9 | 25 | -20 / 4 / 32 | -32 / -22 / 20 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -20 | -12 | 23 | -20 / 3 / 29 | -20 / -29 / 18 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -6 | -22 | 19 | 0 / -12 / 24 | -13 / -33 / 15 |
| vh_i4_emax_5_ny-NQ-tf5 | -25 | 9 | 6 | -4 / 4 / 15 | -47 / 17 / -2 |
| vh_i15_flip_long_15_ny-NQ-tf15 | 20 | -64 | 39 | 32 / -41 / 48 | 7 / -89 / 23 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | 11 | -24 | 1 | -32 / -38 / 43 | 64 / -9 / -32 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -12 | -7 | -5 | 2 / -16 / -13 | -26 / 3 / 1 |
| vh_i4_emax_15_ny-NQ-tf15 | -33 | 20 | -11 | -9 / -2 / 17 | -69 / 42 / -33 |
| vh_i8_z_5_ny-NQ-tf5 | -0 | 0 | -23 | 1 / -6 / -17 | -3 / 7 / -28 |
| vh_i5_touch_us_1_ny-NQ-tf1 | 7 | -24 | -14 | -7 / -32 / -16 | 16 / -16 / -13 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -18 | -20 | 12 | -16 / -38 / 20 | -20 / -1 / 6 |
| vh_i8_band_5_ny-NQ-tf5 | 2 | -11 | -23 | -1 / -12 / -12 | 4 / -11 / -33 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -38 | -20 | 24 | 5 / -10 / 71 | -75 / -30 / -12 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | -28 | -15 | 3 | 1 / 1 / 13 | -73 / -38 / -7 |
| vh_i3_flip_1_ny-NQ-tf1 | -15 | -20 | -3 | -15 / -45 / 10 | -16 / 7 / -14 |
| vh_i3_flip_5_ny-NQ-tf5 | -26 | -13 | 1 | -11 / -14 / 4 | -39 / -13 / -2 |
| vh_i13_reclaim_5_ny-NQ-tf5 | 1 | -45 | -11 | 54 / -78 / 14 | -47 / -18 / -32 |
| vh_i3_flip_15_ny-NQ-tf15 | -20 | -37 | 9 | 57 / -29 / 29 | -102 / -44 / -8 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -10 | -24 | -8 | -30 / -36 / -23 | 10 / -11 / 2 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -19 | -13 | -17 | -4 / -11 / -33 | -36 / -15 / -3 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -7 | -17 | -25 | -68 / -9 / -42 | 51 / -25 / -17 |
| vh_i26_rv_15_ny-NQ-tf15 | -1 | -31 | -12 | -39 / -20 / -16 | 35 / -42 / -9 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | -44 | -48 | 34 | -19 / -26 / 25 | -72 / -73 / 42 |
| vh_i26_rv_1_ny-NQ-tf1 | -16 | -21 | -17 | -30 / -30 / -12 | -1 / -12 / -21 |
| vh_i26_rv_5_ny-NQ-tf5 | -11 | -26 | -15 | -40 / -43 / -17 | 18 / -8 / -12 |
| vh_i15_touch_long_15_ny-NQ-tf15 | -7 | -25 | -18 | -79 / 7 / -89 | 61 / -58 / 21 |
| vh_i8_z_15_ny-NQ-tf15 | -22 | -2 | -35 | -6 / -38 / -27 | -44 / 32 / -43 |
| vh_i8_band_15_ny-NQ-tf15 | 9 | -16 | -72 | 9 / -56 / -48 | 8 / 21 / -95 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -16 | -42 | -27 | 15 / -71 / 12 | -48 / -10 / -57 |
### gap_abs

| Store | small | mid | big | H1 small / mid / big | H2 small / mid / big |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 341 | -140 | 224 | 266 / -309 / 124 | 397 / -34 / 287 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 103 | 194 | 109 | 143 / 126 / 156 | 65 / 270 / 73 |
| vh_i7_orb_15_ny-NQ-tf15 | 50 | 78 | 179 | 137 / 46 / 81 | -56 / 117 / 268 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 60 | 86 | 139 | 135 / 127 / 74 | -15 / 44 / 197 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 65 | 66 | 140 | 71 / 92 / 118 | 56 / 36 / 159 |
| vh_i7_orb_5_ny-NQ-tf5 | -3 | 85 | 151 | 28 / 64 / 10 | -43 / 116 / 286 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 165 | -126 | 96 | 171 / 57 / 99 | 161 / -235 / 90 |
| vh_i12_orbpb_1_ny-NQ-tf1 | 11 | 84 | 76 | 2 / 71 / -52 | 20 / 96 / 188 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 29 | 53 | 98 | -6 / 61 / 95 | 71 / 45 / 100 |
| vh_i12_orbpb_15_ny-NQ-tf15 | -63 | 94 | 113 | -11 / 108 / -34 | -115 / 80 / 265 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 18 | 30 | 104 | 54 / 4 / 31 | -32 / 61 / 174 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 65 | 11 | 85 | 64 / 7 / 99 | 66 / 15 / 73 |
| vh_i12_orbpb_5_ny-NQ-tf5 | -33 | 65 | 106 | 18 / 53 / -25 | -87 / 76 / 229 |
| vh_i7_orb_1_ny-NQ-tf1 | 14 | 25 | 120 | 30 / 30 / 29 | -7 / 27 / 204 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 53 | -13 | 98 | 66 / -12 / 103 | 45 / -16 / 94 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 15 | 37 | 78 | 20 / 66 / 49 | 10 / 7 / 104 |
| vh_i9_noise_long_5_ny-NQ-tf5 | 14 | 66 | 29 | 42 / 127 / 8 | -21 / 2 / 49 |
| vh_i16_emax_15_ny-NQ-tf15 | -18 | 48 | 105 | -31 / 18 / 63 | -2 / 84 / 148 |
| vh_i5_touch_us_15_ny-NQ-tf15 | -22 | 37 | 83 | 7 / -0 / 38 | -48 / 68 / 113 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 9 | 44 | 35 | 12 / 49 / 51 | 7 / 38 / 22 |
| vh_i6_g_disp_5_ny-NQ-tf5 | -15 | 57 | 45 | -21 / 66 / 47 | -8 / 49 / 43 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 22 | 17 | 50 | 34 / 13 / 60 | 8 / 22 / 42 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | -19 | 38 | 58 | 0 / -1 / 26 | -38 / 71 / 78 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | -39 | 43 | 69 | -44 / 8 / 59 | -35 / 83 / 78 |
| vh_i2_tp_15_ny-NQ-tf15 | -21 | 12 | 74 | 4 / 19 / 66 | -53 / 5 / 81 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 43 | 14 | 4 | -60 / 3 / 28 | 145 / 25 / -8 |
| vh_i2_tp_5_ny-NQ-tf5 | 12 | 16 | 23 | 35 / 31 / 30 | -15 / 0 / 16 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | -7 | 48 | -3 | -6 / 70 / 78 | -7 / 31 / -77 |
| vh_i13_reclaim_15_ny-NQ-tf15 | -29 | -49 | 99 | -88 / -10 / 250 | 40 / -79 / -40 |
| vh_i1_pb_15_ny-NQ-tf15 | -26 | 46 | -1 | -10 / -2 / -34 | -45 / 93 / 27 |
| vh_i5_touch_us_5_ny-NQ-tf5 | -17 | 15 | 27 | 1 / -14 / 13 | -33 / 39 / 34 |
| vh_i16_emavwma_5_ny-NQ-tf5 | -12 | 21 | 17 | -30 / 24 / 0 | 8 / 17 / 32 |
| vh_i1_pb_1_ny-NQ-tf1 | -8 | 3 | 19 | -6 / -2 / 22 | -10 / 7 / 17 |
| vh_i23_fbar_5_all-NQ-tf5 | -2 | 19 | 22 | 23 / 28 / 11 | -30 / 9 / 32 |
| vh_i1_pb_5_ny-NQ-tf5 | -23 | 22 | 14 | -26 / 48 / 25 | -20 / -3 / 5 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | -43 | 18 | 44 | -31 / 5 / -6 | -56 / 29 / 74 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 2 | 7 | -1 | -8 / -38 / -77 | 11 / 46 / 54 |
| vh_i15_flip_long_5_ny-NQ-tf5 | -32 | 7 | 44 | -14 / 11 / 28 | -49 / 3 / 58 |
| vh_i16_emavwma_15_ny-NQ-tf15 | -7 | -1 | 8 | 40 / -17 / 60 | -52 / 16 / -43 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | -34 | 20 | 18 | -27 / 24 / 109 | -41 / 17 / -68 |
| vh_i16_emax_side_5_ny-NQ-tf5 | -16 | 14 | 4 | -27 / 29 / -18 | -3 / -1 / 21 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | -10 | 21 | -10 | 9 / 11 / -17 | -33 / 30 / -3 |
| vh_i16_emax_5_ny-NQ-tf5 | -19 | 10 | 8 | -34 / 32 / -18 | -3 / -10 / 31 |
| vh_i2_tp_1_ny-NQ-tf1 | -15 | 7 | 8 | -12 / 11 / 21 | -20 / 3 / -3 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | -36 | 15 | 22 | -18 / 28 / 102 | -53 / 3 / -55 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | -21 | 20 | -6 | -25 / 20 / -9 | -16 / 19 / -4 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -15 | 17 | -13 | -5 / 27 / -10 | -26 / 8 / -15 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -18 | 17 | -9 | -7 / 32 / -18 | -31 / 3 / -1 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -20 | 8 | 2 | -11 / 3 / 19 | -31 / 14 / -14 |
| vh_i4_emax_5_ny-NQ-tf5 | 9 | -9 | -8 | -6 / 2 / 21 | 26 / -20 / -33 |
| vh_i15_flip_long_15_ny-NQ-tf15 | -35 | -38 | 74 | -10 / -39 / 107 | -63 / -35 / 36 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | -41 | 56 | -18 | -49 / 55 / -35 | -31 / 58 / -4 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -14 | 18 | -28 | -18 / 22 / -30 | -9 / 14 / -26 |
| vh_i4_emax_15_ny-NQ-tf15 | 23 | 14 | -59 | -18 / 30 / -9 | 63 / -0 / -95 |
| vh_i8_z_5_ny-NQ-tf5 | 3 | -27 | 1 | 1 / -33 / 14 | 5 / -19 / -12 |
| vh_i5_touch_us_1_ny-NQ-tf1 | -23 | 4 | -8 | -34 / -17 / -1 | -13 / 21 / -13 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -31 | 12 | -9 | -47 / 23 / -16 | -14 / 2 / -3 |
| vh_i8_band_5_ny-NQ-tf5 | -12 | -4 | -16 | -4 / -0 / -20 | -22 / -10 / -11 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -8 | -9 | -14 | -6 / 9 / 61 | -8 / -24 / -69 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | -36 | -8 | 7 | -21 / 22 / 16 | -62 / -46 / -3 |
| vh_i3_flip_1_ny-NQ-tf1 | -26 | -3 | -10 | -47 / 6 / -11 | -4 / -11 / -8 |
| vh_i3_flip_5_ny-NQ-tf5 | -19 | -5 | -16 | -21 / 7 / -8 | -16 / -16 / -22 |
| vh_i13_reclaim_5_ny-NQ-tf5 | -54 | 11 | -13 | -84 / 34 / 39 | -28 / -12 / -53 |
| vh_i3_flip_15_ny-NQ-tf15 | -37 | -5 | -5 | -35 / 11 / 88 | -38 / -21 / -91 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -11 | -14 | -18 | -28 / -36 / -25 | 8 / 8 / -13 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -12 | -3 | -35 | -10 / -8 / -29 | -14 / 4 / -40 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -25 | 4 | -30 | -38 / -30 / -50 | -13 / 34 / -21 |
| vh_i26_rv_15_ny-NQ-tf15 | -6 | -33 | -5 | -12 / -34 / -30 | 1 / -31 / 15 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | -44 | 4 | -16 | -11 / 16 / -30 | -81 / -8 / -4 |
| vh_i26_rv_1_ny-NQ-tf1 | -14 | -22 | -18 | -26 / -34 / -13 | -1 / -10 / -22 |
| vh_i26_rv_5_ny-NQ-tf5 | -13 | -29 | -11 | -36 / -45 / -21 | 13 / -13 / -3 |
| vh_i15_touch_long_15_ny-NQ-tf15 | -29 | 13 | -43 | -20 / -41 / -95 | -40 / 59 / -11 |
| vh_i8_z_15_ny-NQ-tf15 | 2 | -26 | -35 | -27 / -22 / -22 | 31 / -32 / -49 |
| vh_i8_band_15_ny-NQ-tf15 | -20 | 36 | -89 | -51 / 51 / -105 | 7 / 18 / -77 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -51 | -7 | -28 | -74 / 25 / 4 | -25 / -39 / -52 |
### drift

| Store | down | flat | up | H1 down / flat / up | H2 down / flat / up |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 83 | 323 | 87 | 6 / 294 / -155 | 113 / 342 / 245 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 151 | 190 | 63 | 50 / 102 / 224 | 254 / 260 / -95 |
| vh_i7_orb_15_ny-NQ-tf15 | 115 | 60 | 130 | 28 / 115 / 107 | 210 / -3 / 154 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 2 | 117 | 163 | 42 / 147 / 154 | -38 / 90 / 172 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 44 | 100 | 104 | 75 / 89 / 102 | 10 / 112 / 106 |
| vh_i7_orb_5_ny-NQ-tf5 | 74 | 43 | 109 | -9 / 28 / 71 | 168 / 61 / 148 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 87 | 167 | -55 | 185 / 189 / 9 | -1 / 135 / -112 |
| vh_i12_orbpb_1_ny-NQ-tf1 | 106 | 8 | 60 | 12 / -25 / 43 | 204 / 39 / 71 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 59 | 71 | 39 | 73 / 37 / 26 | 45 / 108 / 52 |
| vh_i12_orbpb_15_ny-NQ-tf15 | 87 | -7 | 73 | -2 / -20 / 82 | 180 / 2 / 62 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 38 | 19 | 97 | -36 / 70 / 65 | 118 / -46 / 128 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 46 | 67 | 41 | 42 / 85 / 44 | 49 / 52 / 39 |
| vh_i12_orbpb_5_ny-NQ-tf5 | 100 | 1 | 51 | 17 / -13 / 47 | 187 / 12 / 50 |
| vh_i7_orb_1_ny-NQ-tf1 | 74 | 35 | 39 | 21 / 18 / 40 | 137 / 56 / 37 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 68 | 55 | 28 | 75 / 100 / 2 | 62 / 25 / 47 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 10 | 54 | 57 | 27 / 42 / 62 | -7 / 68 / 52 |
| vh_i9_noise_long_5_ny-NQ-tf5 | -23 | 69 | 69 | 34 / 83 / 62 | -87 / 56 / 78 |
| vh_i16_emax_15_ny-NQ-tf15 | 31 | 3 | 82 | 13 / -5 / 31 | 55 / 12 / 129 |
| vh_i5_touch_us_15_ny-NQ-tf15 | 39 | -4 | 71 | 9 / -4 / 32 | 62 / -4 / 103 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 10 | 29 | 46 | 26 / 41 / 43 | -6 / 16 / 49 |
| vh_i6_g_disp_5_ny-NQ-tf5 | 12 | 29 | 42 | 33 / -10 / 63 | -12 / 70 / 24 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 5 | 30 | 45 | -10 / 53 / 59 | 23 / 3 / 33 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 42 | 12 | 20 | -7 / -12 / 38 | 83 / 32 / 6 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 62 | -24 | 35 | 7 / -8 / 26 | 119 / -41 / 46 |
| vh_i2_tp_15_ny-NQ-tf15 | 16 | -2 | 56 | 9 / 51 / 40 | 23 / -69 / 73 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 9 | 41 | 3 | -47 / -48 / 50 | 53 / 135 / -35 |
| vh_i2_tp_5_ny-NQ-tf5 | -3 | 13 | 40 | 2 / 50 / 51 | -9 / -31 / 29 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 18 | 21 | -1 | 73 / -11 / 53 | -47 / 55 / -45 |
| vh_i13_reclaim_15_ny-NQ-tf15 | 10 | -20 | 43 | 29 / -76 / 152 | 12 / 51 / -64 |
| vh_i1_pb_15_ny-NQ-tf15 | -29 | -0 | 55 | -88 / 35 / 26 | 37 / -41 / 80 |
| vh_i5_touch_us_5_ny-NQ-tf5 | 27 | -9 | 7 | 13 / -28 / 8 | 38 / 7 / 5 |
| vh_i16_emavwma_5_ny-NQ-tf5 | 14 | -7 | 19 | 13 / -24 / 7 | 15 / 10 / 30 |
| vh_i1_pb_1_ny-NQ-tf1 | 8 | -8 | 28 | -12 / -20 / 62 | 26 / 3 / -3 |
| vh_i23_fbar_5_all-NQ-tf5 | -25 | 21 | 26 | 1 / 12 / 36 | -53 / 31 / 17 |
| vh_i1_pb_5_ny-NQ-tf5 | -27 | -0 | 51 | -28 / 8 / 77 | -26 / -8 / 29 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | 40 | -20 | 3 | 54 / -76 / -21 | 25 / 29 / 20 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 1 | 9 | 1 | -59 / -31 / -20 | 53 / 48 / 17 |
| vh_i15_flip_long_5_ny-NQ-tf5 | 23 | -25 | 17 | 32 / -20 / 6 | 15 / -30 / 26 |
| vh_i16_emavwma_15_ny-NQ-tf15 | -5 | 3 | 6 | 30 / 62 / -16 | -37 / -62 / 27 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | -2 | -15 | 23 | 59 / -23 / 54 | -68 / -6 / -8 |
| vh_i16_emax_side_5_ny-NQ-tf5 | -26 | 4 | 27 | -9 / -10 / 13 | -44 / 18 / 41 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | -6 | 2 | 5 | -33 / 10 / 29 | 22 / -6 / -13 |
| vh_i16_emax_5_ny-NQ-tf5 | -27 | -2 | 31 | -11 / -16 / 15 | -43 / 13 / 45 |
| vh_i2_tp_1_ny-NQ-tf1 | -6 | -5 | 11 | -9 / 7 / 26 | -2 / -18 / -2 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | -3 | -17 | 21 | 57 / -22 / 60 | -73 / -10 / -15 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | -11 | -7 | 12 | -17 / -9 / 16 | -4 / -5 / 9 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -30 | -6 | 30 | -28 / -2 / 47 | -31 / -11 / 16 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -28 | -7 | 28 | -31 / -5 / 49 | -26 / -8 / 10 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -14 | -9 | 14 | -11 / 1 / 22 | -16 / -19 / 6 |
| vh_i4_emax_5_ny-NQ-tf5 | -33 | 4 | 17 | -27 / 16 / 27 | -41 / -6 / 8 |
| vh_i15_flip_long_15_ny-NQ-tf15 | 6 | -3 | -10 | 6 / 34 / -8 | 7 / -39 / -13 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | -27 | 5 | 8 | -70 / 3 / 33 | 24 / 6 / -14 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -17 | 6 | -8 | -14 / 5 / -11 | -20 / 8 / -7 |
| vh_i4_emax_15_ny-NQ-tf15 | -61 | -0 | 27 | -50 / 2 / 38 | -73 / -10 / 18 |
| vh_i8_z_5_ny-NQ-tf5 | 23 | -33 | -15 | 30 / -38 / -14 | 15 / -27 / -15 |
| vh_i5_touch_us_1_ny-NQ-tf1 | -4 | -17 | -5 | 1 / -55 / -3 | -7 / 14 / -7 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -30 | -12 | 17 | -32 / -30 / 27 | -27 / 7 / 9 |
| vh_i8_band_5_ny-NQ-tf5 | 17 | -38 | -10 | 22 / -42 / -7 | 10 / -34 / -12 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -44 | -4 | 15 | -31 / 22 / 79 | -54 / -33 / -37 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | -61 | 23 | -1 | -38 / 27 / 18 | -95 / 18 / -20 |
| vh_i3_flip_1_ny-NQ-tf1 | -16 | -15 | -3 | -21 / -28 / 0 | -11 / -3 / -6 |
| vh_i3_flip_5_ny-NQ-tf5 | -26 | -16 | 8 | -23 / -11 / 13 | -29 / -22 / 3 |
| vh_i13_reclaim_5_ny-NQ-tf5 | -15 | -40 | 11 | 21 / -37 / 18 | -43 / -42 / 5 |
| vh_i3_flip_15_ny-NQ-tf15 | -23 | -26 | 4 | 49 / -27 / 24 | -104 / -22 / -15 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -23 | -17 | -7 | -38 / -30 / -21 | -7 / -4 / 5 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -37 | 15 | -25 | -28 / 28 / -38 | -47 / 0 / -12 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -4 | -15 | -29 | -59 / -25 / -35 | 48 / -4 / -26 |
| vh_i26_rv_15_ny-NQ-tf15 | -25 | -20 | -4 | -61 / 8 / -19 | 8 / -47 / 9 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | -77 | -12 | 35 | -39 / -18 / 31 | -121 / -4 / 40 |
| vh_i26_rv_1_ny-NQ-tf1 | -18 | -16 | -20 | -33 / -20 / -21 | -4 / -12 / -20 |
| vh_i26_rv_5_ny-NQ-tf5 | -23 | -16 | -16 | -48 / -30 / -25 | 2 / -1 / -8 |
| vh_i15_touch_long_15_ny-NQ-tf15 | -12 | -6 | -37 | -48 / -42 / -65 | 22 / 30 / -20 |
| vh_i8_z_15_ny-NQ-tf15 | 4 | -46 | -22 | 30 / -67 / -45 | -25 / -23 / 2 |
| vh_i8_band_15_ny-NQ-tf15 | 40 | -48 | -72 | 27 / -66 / -65 | 56 / -28 / -78 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -27 | -29 | -25 | 4 / -43 / -8 | -56 / -15 / -40 |
### drift_abs

| Store | small | mid | big | H1 small / mid / big | H2 small / mid / big |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 315 | 120 | 30 | 300 / -19 / -129 | 318 / 170 / 206 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 195 | 232 | 1 | 97 / 231 / 79 | 276 / 233 / -68 |
| vh_i7_orb_15_ny-NQ-tf15 | 12 | 159 | 135 | 79 / 35 / 138 | -66 / 290 / 131 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | 92 | 98 | 86 | 114 / 136 / 86 | 72 / 63 / 87 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 62 | 114 | 75 | 55 / 137 / 78 | 69 / 93 / 72 |
| vh_i7_orb_5_ny-NQ-tf5 | -22 | 153 | 92 | -24 / 74 / 33 | -19 / 236 / 151 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 181 | 61 | -86 | 169 / 425 / -148 | 195 / -210 / -2 |
| vh_i12_orbpb_1_ny-NQ-tf1 | -1 | 88 | 88 | -20 / 13 / 37 | 17 / 161 / 135 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 35 | 43 | 93 | 7 / 7 / 131 | 67 / 80 / 60 |
| vh_i12_orbpb_15_ny-NQ-tf15 | -21 | 62 | 113 | -31 / 42 / 48 | -15 / 85 / 184 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | -25 | 167 | 18 | 28 / 117 / -26 | -97 / 215 / 66 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 52 | 46 | 55 | 75 / 74 / 29 | 33 / 27 / 80 |
| vh_i12_orbpb_5_ny-NQ-tf5 | -9 | 68 | 95 | -9 / 12 / 48 | -11 / 120 / 145 |
| vh_i7_orb_1_ny-NQ-tf1 | -10 | 68 | 88 | -8 / 13 / 73 | -10 / 126 / 103 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 38 | 32 | 70 | 86 / 31 / 41 | 3 / 26 / 99 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 27 | 54 | 42 | 15 / 90 / 29 | 41 / 19 / 55 |
| vh_i9_noise_long_5_ny-NQ-tf5 | 57 | 36 | 19 | 62 / 69 / 45 | 52 / 0 / -3 |
| vh_i16_emax_15_ny-NQ-tf15 | -26 | 68 | 78 | -37 / 27 / 63 | -12 / 111 / 95 |
| vh_i5_touch_us_15_ny-NQ-tf15 | -7 | 45 | 66 | -18 / 13 / 41 | 4 / 70 / 84 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 8 | 41 | 36 | 12 / 47 / 52 | 3 / 35 / 21 |
| vh_i6_g_disp_5_ny-NQ-tf5 | 5 | 40 | 41 | -31 / 71 / 50 | 43 / 12 / 31 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 10 | 41 | 30 | 39 / 32 / 31 | -26 / 49 / 29 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 10 | 3 | 62 | -11 / -18 / 43 | 30 / 20 / 76 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | -24 | 50 | 47 | -10 / 38 / -1 | -41 / 62 / 105 |
| vh_i2_tp_15_ny-NQ-tf15 | -11 | 40 | 40 | 43 / 28 / 27 | -83 / 52 / 54 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 12 | 55 | -8 | -56 / -21 / 41 | 91 / 118 / -43 |
| vh_i2_tp_5_ny-NQ-tf5 | -8 | 35 | 20 | 31 / 43 / 28 | -55 / 27 / 13 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 32 | 43 | -35 | -3 / 92 / 37 | 73 / -0 / -103 |
| vh_i13_reclaim_15_ny-NQ-tf15 | 7 | -78 | 71 | -60 / 20 / 140 | 81 / -163 / -0 |
| vh_i1_pb_15_ny-NQ-tf15 | -4 | 5 | 27 | 17 / -87 / 36 | -28 / 91 / 18 |
| vh_i5_touch_us_5_ny-NQ-tf5 | -8 | 5 | 29 | -28 / -8 / 30 | 10 / 15 / 28 |
| vh_i16_emavwma_5_ny-NQ-tf5 | -28 | 35 | 22 | -32 / 13 / 19 | -24 / 55 / 25 |
| vh_i1_pb_1_ny-NQ-tf1 | -9 | 5 | 32 | -29 / 7 / 50 | 10 / 3 / 15 |
| vh_i23_fbar_5_all-NQ-tf5 | 6 | 13 | 5 | 4 / 39 / 4 | 7 / -13 / 6 |
| vh_i1_pb_5_ny-NQ-tf5 | 3 | -6 | 25 | 2 / 7 / 48 | 5 / -16 / 6 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | -14 | -19 | 45 | -75 / 17 / 23 | 45 / -48 / 60 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 18 | -10 | 2 | -12 / -48 / -60 | 48 / 20 / 51 |
| vh_i15_flip_long_5_ny-NQ-tf5 | -39 | 28 | 26 | -28 / 37 / 12 | -49 / 20 / 41 |
| vh_i16_emavwma_15_ny-NQ-tf15 | -11 | 22 | -4 | 39 / 28 / 8 | -69 / 17 / -16 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | -10 | 24 | -8 | -18 / 46 / 67 | 1 / 3 / -84 |
| vh_i16_emax_side_5_ny-NQ-tf5 | -15 | 6 | 13 | -18 / 7 / 5 | -11 / 5 / 20 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | 3 | 12 | -14 | 11 / 3 / -12 | -4 / 20 / -15 |
| vh_i16_emax_5_ny-NQ-tf5 | -20 | 6 | 16 | -25 / 9 / 5 | -15 / 3 / 26 |
| vh_i2_tp_1_ny-NQ-tf1 | -13 | 6 | 6 | -3 / 13 / 12 | -23 / -0 / 0 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | -12 | 26 | -13 | -16 / 54 / 61 | -6 / -1 / -88 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | -17 | 13 | -3 | -23 / 22 / -10 | -10 / 5 / 4 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -9 | 8 | -5 | -9 / 16 / 8 | -10 / 1 / -16 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -10 | 9 | -5 | -10 / 17 / 4 | -11 / 2 / -14 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -27 | 12 | 6 | -15 / 20 / 7 | -40 / 4 / 6 |
| vh_i4_emax_5_ny-NQ-tf5 | 2 | 7 | -20 | 9 / -1 / 7 | -2 / 15 / -46 |
| vh_i15_flip_long_15_ny-NQ-tf15 | 11 | 4 | -35 | 39 / 20 / -33 | -17 / -11 / -36 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | -5 | 19 | -24 | -31 / 21 / -24 | 24 / 19 / -24 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -5 | 10 | -24 | -10 / 18 / -26 | 1 / 2 / -23 |
| vh_i4_emax_15_ny-NQ-tf15 | 18 | 19 | -71 | 12 / 40 / -62 | 21 / 1 / -80 |
| vh_i8_z_5_ny-NQ-tf5 | -20 | -9 | 5 | -9 / -32 / 18 | -34 / 13 / -8 |
| vh_i5_touch_us_1_ny-NQ-tf1 | -15 | -5 | -5 | -52 / -6 / 3 | 17 / -4 / -11 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -11 | -7 | -8 | -26 / -3 / -10 | 6 / -11 / -6 |
| vh_i8_band_5_ny-NQ-tf5 | -25 | -1 | -5 | -12 / -20 / 4 | -42 / 17 / -14 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -11 | 16 | -35 | 20 / 9 / 39 | -45 / 22 / -96 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | 25 | -13 | -40 | 9 / 40 / -30 | 43 / -71 / -53 |
| vh_i3_flip_1_ny-NQ-tf1 | -15 | -11 | -9 | -26 / -12 / -12 | -4 / -10 / -6 |
| vh_i3_flip_5_ny-NQ-tf5 | -21 | -9 | -5 | -21 / 0 / -0 | -20 / -17 / -10 |
| vh_i13_reclaim_5_ny-NQ-tf5 | -62 | 25 | -5 | -67 / 55 / 14 | -57 / -2 / -22 |
| vh_i3_flip_15_ny-NQ-tf15 | -20 | 1 | -26 | -25 / 34 / 42 | -13 / -30 / -95 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -14 | -18 | -15 | -20 / -45 / -26 | -7 / 6 / -5 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -2 | -8 | -37 | 5 / -4 / -38 | -11 / -12 / -36 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -13 | -3 | -32 | -19 / -60 / -43 | -6 / 44 / -24 |
| vh_i26_rv_15_ny-NQ-tf15 | -7 | -12 | -29 | 22 / -51 / -47 | -37 / 22 / -15 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | -27 | -44 | 16 | -39 / -4 / 13 | -16 / -83 / 20 |
| vh_i26_rv_1_ny-NQ-tf1 | -12 | -26 | -17 | -19 / -41 / -15 | -5 / -12 / -19 |
| vh_i26_rv_5_ny-NQ-tf5 | -13 | -28 | -14 | -23 / -58 / -24 | -2 / -1 / -5 |
| vh_i15_touch_long_15_ny-NQ-tf15 | -9 | -9 | -38 | -35 / -65 / -57 | 18 / 34 / -23 |
| vh_i8_z_15_ny-NQ-tf15 | -41 | -2 | -21 | -47 / -19 / -14 | -32 / 16 / -28 |
| vh_i8_band_15_ny-NQ-tf15 | -51 | 47 | -74 | -49 / 27 / -78 | -52 / 72 / -70 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -28 | -27 | -25 | -45 / -5 / 7 | -10 / -49 / -51 |
### pos

| Store | bottom | middle | top | H1 bottom / middle / top | H2 bottom / middle / top |
|---|---|---|---|---|---|
| vh_i17_rvbrk_15_ny-NQ-tf15 | 133 | 109 | 271 | 97 / 106 / -20 | 194 / 111 / 382 |
| vh_i27_onrorb_15_ny-NQ-tf15 | 115 | nan | 139 | 140 / nan / 125 | 88 / nan / 149 |
| vh_i7_orb_15_ny-NQ-tf15 | 80 | 72 | 152 | 90 / 14 / 153 | 73 / 136 / 151 |
| vh_i7_orbc_long_5_ny-NQ-tf5 | -13 | 52 | 221 | 57 / 92 / 184 | -87 / 11 / 253 |
| vh_i6_g_donch_15_ny-NQ-tf15 | 61 | 34 | 146 | 143 / 35 / 86 | -39 / 33 / 199 |
| vh_i7_orb_5_ny-NQ-tf5 | 51 | 50 | 121 | 15 / -55 / 123 | 93 / 182 / 120 |
| vh_i20_volspike_pm_15_ny-NQ-tf15 | 213 | -46 | 31 | 329 / 67 / -57 | 74 / -185 / 97 |
| vh_i12_orbpb_1_ny-NQ-tf1 | 93 | 24 | 57 | 17 / -64 / 76 | 169 / 119 / 37 |
| vh_i6_g_disp_15_ny-NQ-tf15 | 95 | 40 | 37 | 117 / 18 / -6 | 71 / 67 / 71 |
| vh_i12_orbpb_15_ny-NQ-tf15 | 132 | -19 | 35 | 85 / -112 / 98 | 177 / 96 / -21 |
| vh_i7_orbc_short_5_ny-NQ-tf5 | 70 | 15 | 63 | 65 / -61 / 90 | 77 / 107 / 37 |
| vh_i17_rvbrk_n_5_ny-NQ-tf5 | 59 | -0 | 87 | 75 / 53 / 43 | 43 / -42 / 123 |
| vh_i12_orbpb_5_ny-NQ-tf5 | 112 | 16 | 24 | 61 / -69 / 64 | 163 / 114 / -12 |
| vh_i7_orb_1_ny-NQ-tf1 | 48 | 28 | 70 | 27 / -38 / 89 | 75 / 105 / 55 |
| vh_i17_rvbrk_5_ny-NQ-tf5 | 42 | 28 | 68 | 111 / 90 / -36 | -18 / -15 / 139 |
| vh_i6_g_donch_5_ny-NQ-tf5 | 32 | -12 | 92 | 69 / 10 / 49 | -8 / -37 / 130 |
| vh_i9_noise_long_5_ny-NQ-tf5 | -36 | 48 | 86 | 45 / 80 / 50 | -145 / 13 / 117 |
| vh_i16_emax_15_ny-NQ-tf15 | 65 | 2 | 52 | 101 / -36 / -9 | 22 / 52 / 106 |
| vh_i5_touch_us_15_ny-NQ-tf15 | 78 | -11 | 27 | 73 / -113 / 60 | 81 / 72 / 3 |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | 40 | 1 | 41 | 68 / 12 / 28 | 10 / -11 / 52 |
| vh_i6_g_disp_5_ny-NQ-tf5 | 13 | 14 | 53 | 33 / 25 / 21 | -9 / 1 / 78 |
| vh_i10_adx_tp_5_ny-NQ-tf5 | 22 | 4 | 48 | 39 / 22 / 40 | 3 / -17 / 56 |
| vh_i11_touch_gx_5_ny-NQ-tf5 | 54 | 1 | 18 | 38 / -69 / 41 | 67 / 62 / 0 |
| vh_i6_g_fvg_15_ny-NQ-tf15 | 36 | 27 | 13 | 15 / -14 / 22 | 59 / 83 / 3 |
| vh_i2_tp_15_ny-NQ-tf15 | 10 | -4 | 56 | 40 / -30 / 81 | -27 / 30 / 32 |
| vh_i16_emavwap_rv_5_ny-NQ-tf5 | 10 | 16 | 22 | -39 / -2 / -12 | 50 / 35 / 51 |
| vh_i2_tp_5_ny-NQ-tf5 | 11 | -6 | 39 | 41 / 6 / 52 | -23 / -20 / 28 |
| vh_i15_flip_wk_15_ny-NQ-tf15 | 30 | -30 | 36 | 57 / -10 / 66 | 0 / -48 / 12 |
| vh_i13_reclaim_15_ny-NQ-tf15 | 9 | 54 | -10 | 68 / 78 / 32 | -42 / 37 / -52 |
| vh_i1_pb_15_ny-NQ-tf15 | -12 | -51 | 83 | -22 / -73 / 67 | -1 / -26 / 96 |
| vh_i5_touch_us_5_ny-NQ-tf5 | 41 | -12 | -6 | 36 / -57 / 6 | 44 / 25 / -15 |
| vh_i16_emavwma_5_ny-NQ-tf5 | 6 | 1 | 17 | 5 / -23 / 13 | 7 / 27 / 20 |
| vh_i1_pb_1_ny-NQ-tf1 | 15 | -13 | 19 | 18 / -61 / 62 | 13 / 39 / -16 |
| vh_i23_fbar_5_all-NQ-tf5 | 19 | -9 | 11 | 30 / 1 / 15 | 7 / -20 / 8 |
| vh_i1_pb_5_ny-NQ-tf5 | -19 | -2 | 39 | 7 / -19 / 68 | -42 / 16 / 18 |
| vh_i10_adx_touch_5_ny-NQ-tf5 | 63 | -37 | -20 | 68 / -88 / -48 | 58 / 11 / -0 |
| vh_i15_touch_ext_5_ny-NQ-tf5 | 11 | -12 | 11 | -70 / -29 / -13 | 84 / 5 / 30 |
| vh_i15_flip_long_5_ny-NQ-tf5 | 14 | -10 | 8 | 41 / -4 / -20 | -14 / -13 / 33 |
| vh_i16_emavwma_15_ny-NQ-tf15 | -5 | -1 | 10 | 76 / 14 / -6 | -74 / -22 / 26 |
| vh_i14_flip_ldn_15_ny-NQ-tf15 | -13 | -38 | 48 | 30 / -9 / 66 | -62 / -65 / 32 |
| vh_i16_emax_side_5_ny-NQ-tf5 | -25 | 6 | 21 | -8 / -4 / 5 | -43 / 17 / 35 |
| vh_i15_flip_wk_5_ny-NQ-tf5 | 1 | -21 | 19 | 3 / -25 / 26 | 0 / -17 / 14 |
| vh_i16_emax_5_ny-NQ-tf5 | -25 | 3 | 21 | -13 / -5 / 5 | -37 / 11 / 34 |
| vh_i2_tp_1_ny-NQ-tf1 | 0 | -11 | 9 | 12 / -17 / 25 | -12 / -4 / -5 |
| vh_i11_flip_gx_15_ny-NQ-tf15 | -10 | -43 | 46 | 32 / -15 / 73 | -60 / -71 / 23 |
| vh_i6_g_cbrk_5_ny-NQ-tf5 | 3 | -12 | 3 | 12 / -21 / -4 | -7 / -3 / 8 |
| vh_i14_flip_ldn_5_ny-NQ-tf5 | -27 | -15 | 30 | -12 / 2 / 21 | -41 / -32 / 39 |
| vh_i11_flip_gx_5_ny-NQ-tf5 | -26 | -11 | 26 | -15 / -2 / 22 | -37 / -21 / 29 |
| vh_i6_g_fvg_5_ny-NQ-tf5 | -0 | -19 | 7 | 10 / 6 / -7 | -12 / -48 / 20 |
| vh_i4_emax_5_ny-NQ-tf5 | -40 | 21 | 8 | -15 / 13 / 19 | -69 / 31 / 2 |
| vh_i15_flip_long_15_ny-NQ-tf15 | 3 | -7 | -5 | 46 / -9 / -1 | -39 / -3 / -9 |
| vh_i10_adx_flip_5_ny-NQ-tf5 | 10 | -52 | 13 | -18 / -39 / 10 | 40 / -67 / 15 |
| vh_i9_bbrk_5_ny-NQ-tf5 | -3 | -20 | 2 | 6 / -9 / -17 | -13 / -33 / 18 |
| vh_i4_emax_15_ny-NQ-tf15 | -49 | 12 | -3 | -28 / 20 / -8 | -69 / 3 / 0 |
| vh_i8_z_5_ny-NQ-tf5 | -5 | 18 | -32 | -6 / -7 / -8 | -3 / 45 / -55 |
| vh_i5_touch_us_1_ny-NQ-tf1 | 17 | -36 | -11 | 13 / -63 / -14 | 19 / -13 / -8 |
| vh_i11_flip_gx_1_ny-NQ-tf1 | -7 | -35 | 14 | -10 / -49 / 19 | -4 / -20 / 9 |
| vh_i8_band_5_ny-NQ-tf5 | -9 | 10 | -28 | -16 / -5 / -5 | -0 / 26 / -49 |
| vh_i9_noise_short_5_ny-NQ-tf5 | -9 | -35 | 4 | -5 / 1 / 70 | -13 / -68 / -50 |
| vh_i10_adx_emax_5_ny-NQ-tf5 | -95 | 70 | 2 | -45 / 41 / 16 | -159 / 124 / -10 |
| vh_i3_flip_1_ny-NQ-tf1 | -7 | -24 | -5 | -9 / -40 / -3 | -5 / -8 / -7 |
| vh_i3_flip_5_ny-NQ-tf5 | -22 | -28 | 11 | -12 / -10 / -2 | -31 / -47 / 23 |
| vh_i13_reclaim_5_ny-NQ-tf5 | -30 | -19 | 10 | -5 / -1 / 12 | -52 / -32 / 9 |
| vh_i3_flip_15_ny-NQ-tf15 | -36 | -44 | 27 | 12 / -7 / 39 | -91 / -81 / 18 |
| vh_i26_rv_look_5_ny-NQ-tf5 | -27 | -15 | -6 | -58 / -22 / -8 | 6 / -8 / -4 |
| vh_i9_bbrk_15_ny-NQ-tf15 | -16 | -27 | -7 | 5 / -28 / -14 | -37 / -26 / -0 |
| vh_i15_touch_long_5_ny-NQ-tf5 | -4 | -22 | -24 | -27 / -41 / -52 | 16 / -5 / -5 |
| vh_i26_rv_15_ny-NQ-tf15 | -48 | -7 | 5 | -77 / -20 / 21 | -18 / 1 / -8 |
| vh_i20_holy_grail_5_ny-NQ-tf5 | -21 | -48 | 2 | 51 / -87 / -16 | -94 / 2 / 18 |
| vh_i26_rv_1_ny-NQ-tf1 | -28 | -9 | -16 | -43 / -13 / -16 | -13 / -5 / -17 |
| vh_i26_rv_5_ny-NQ-tf5 | -37 | -7 | -11 | -67 / -17 / -18 | -6 / 3 / -5 |
| vh_i15_touch_long_15_ny-NQ-tf15 | 10 | -17 | -51 | -12 / -32 / -108 | 30 / -3 / -6 |
| vh_i8_z_15_ny-NQ-tf15 | 17 | -28 | -51 | 17 / -15 / -84 | 16 / -42 / -20 |
| vh_i8_band_15_ny-NQ-tf15 | -10 | 4 | -66 | -29 / 14 / -84 | 10 / -7 / -49 |
| vh_i13_reclaim_1_ny-NQ-tf1 | -26 | -26 | -28 | 1 / -41 / -7 | -52 / -12 / -48 |

## Verdict against Note N (written before the run), after the skeptic's check
One of six features clears the bar: the signed gap, as "a FLAT open is bad" (flat third -$8.4 a trade vs +$35.0 up / +$22.8 down; up-vs-
flat holds in 80 % / 79 % of stores by half, 75 % with H1-only cut points). The skeptic's caveats stand: six features were tried, so one
clearing is about a 1-in-5 chance event; 75 stores are not independent (a random tag already gets ~67 % agreement); by year it holds in
2022 and 2024 only. **A weak lead, like the middle-third skip: not applied to any stack; a forward day tag ("flat open", STACK_BAR.md) read
once at the stacks' read dates.** The other five cuts (overnight range size, |gap|, drift, |drift|, the open's place) are noise.
