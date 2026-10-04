# Event calendar -> engine/cache/events.csv (built 2026-10-04, calendar builder)
903 rows, 2021-09-01..2026-09-30, columns date,time_et,type,subtype,source. All 12 requested types kept (none dropped). No date was checked against prices/volume.
Rows per type (2021 = Sep-Dec only; 2026 = to Sep; 2025+ is optional and not used for BUILD/PICK):
```
type     2021  2022 2023 2024 | 2025 2026   time  subtype used
NFP/CPI     4    12   12   12 |   11    9   08:30
PPI         4    12   12   12 |   10   10   08:30
RETAIL      4    12   12   12 |   11   10   08:30
GDP         4    12   12   12 |   10    9   08:30  advance/second/third (Initial=advance, Updated=third)
PCE         4    12   12   12 |   11    9   08:30  (10:00 on 5 days, see below; data_update on 2025-12-23)
CLAIMS     18    52   52   52 |   46   38   08:30  moved = holiday week (11 rows)
ISM_MFG/SVC 4    12   12   12 |   12    9   10:00
JOLTS       4    12   12   12 |   11   10   10:00
UMICH       4    12   12   12 |   12    9   10:00  (preliminary release)
FOMC        3     8    8    8 |    8    6   14:00  decision day = last meeting day; 2025-08-22 notation vote excluded
```
Sources (official; the per-row `source` column holds the URL/path):
- BLS (NFP, CPI, PPI, JOLTS): yearly schedule pages bls.gov/schedule/<year>/home.htm AND release archives bls.gov/bls/news-release/<series>.htm. bls.gov blocks scripts, so both were read as web.archive.org copies and parsed by code (not by a model). The two sources agree on every date in the archive copy (239 of 241; the other 2 are Sep 2026 releases, see doubt 3).
- BEA (GDP, PCE = Personal Income and Outlays): bea.gov news archive (actual release date + time stamp per release). 2024 schedule PDF spot-checked (Jan-Apr: same dates).
- Census RETAIL: census.gov/retail/marts/www/MARTSreleasedates.xls (to Sep 2025) and census.gov/retail/release_schedule.html (Nov 2025 on).
- DOL CLAIMS: every date has its own DOL release PDF oui.doleta.gov/press/<yyyy>/<mmddyy>.pdf (file found = release held that day). Embargo line "8:30 A.M. (Eastern)" read in 14 PDFs, incl. every holiday move.
- ISM: ISM's own release stamps (prnewswire.com ISM newsroom, 10:00 ET) for every month. ismworld.org calendar is login-only, so it was NOT used (nothing entered). Consistent with the ISM rule (1st / 3rd business day) except 11 explained cases: January releases are one business day later (10 rows) and Good Friday 2026-04-03 is skipped (ISM_SVC 2026-04-06).
- UMich: data.sca.isr.umich.edu/fetchdoc.php?docid=75443 "Historical Prelim/Final Release Dates" (official).
- FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm.
Cross-check vs ../prop-portfolio/2026-09-29/news_days.csv (NFP, CPI, FOMC), 2021-09..2024-12: 40 NFP, 40 CPI, 27 FOMC dates in both, ZERO mismatches (also zero for 2025-2026).
Rescheduled / unusual time, 2021-09..2024-12 (no shutdown or BLS/Fed move in this span):
- CLAIMS moved Thursday -> Wednesday (holiday, each read in the DOL PDF): 2021-11-10 (Veterans Day), 2021-11-24, 2022-11-23, 2023-11-22, 2024-07-03, 2024-11-27 (Thanksgiving / July 4). Also 2025-01-08 (Carter mourning day), 2025-06-18, 2025-11-26, 2025-12-24, 2025-12-31.
- UMICH Apr 2022 prelim on Thursday 2022-04-14 (Good Friday week); the only non-Friday in 61.
- PCE released at 10:00, not 08:30: 2021-11-24, 2024-11-27 (also 2025-04-30, 2025-12-05, 2026-01-22). Their GDP the same day stayed at 08:30.
- 2025-10..2026-02 shutdown catch-up dates are kept as published (NFP 2025-11-20 and 12-16; CPI 2025-10-24; PPI 2025-11-25; Retail 2025-11-25; GDP 2025-12-23). Oct 2025 NFP/CPI and Sep 2025 JOLTS were never published (no row).
Known doubts:
1. UMICH time 10:00 comes from UMich's page ("at 10am ET"); the historical file has dates only.
2. BEA/Census/DOL/ISM/UMich dates are actual release dates from archives, so a postponement would not show as a "move"; none found.
3. CLAIMS 2025-10-02..2025-11-13 (7 weeks, shutdown): no DOL PDF found, rows left out. BEA 2026-07-30 GDP carried a 08:31 stamp, set to 08:30. PPI 2026-09-10 and JOLTS 2026-09-29 are on the BLS 2026 schedule but not yet in the archive copy.
4. Same-day stacking is kept as separate rows (max 3 per day). Inputs and the builder script are in out/events/inputs/ (build_events.py).
