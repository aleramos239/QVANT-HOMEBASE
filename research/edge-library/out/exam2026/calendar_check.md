# Release calendar 2025-26 — check of engine/cache/events.csv (2026-10-05, before any 2025 scoring; no market data used)

**Result: every 2025-26 row that was checked is right. No row changed, none removed. 5 rows ADDED (30 Sep - 2 Oct 2026).**
The 2025 shutdown dates in the file are the dates the releases actually came out. No release type had to be left out of a filter.

| check | rows 2025-26 | source read today | result |
|---|---|---|---|
| NFP / CPI / FOMC vs `../prop-portfolio/2026-09-29/news_days.csv` | 20 / 20 / 14 | the reference file | 0 mismatches either way |
| FOMC | 14 | federalreserve.gov/monetarypolicy/fomccalendars.htm (last meeting day) | 14 of 14 |
| CPI | 20 | bls.gov/bls/news-release/cpi.htm (web.archive.org copy of 2026-10-02), release file names | 20 of 20, none extra |
| NFP | 20 | bls.gov schedule pages 2025 + 2026 and bls.gov/bls/news-release/empsit.htm (archive copies) | 20 of 20 |
| weekly jobless claims | 84 | oui.doleta.gov/press/<yyyy>/<mmddyy>.pdf asked for EVERY weekday 2025-01-01..2026-09-30 (456 requests) | the 84 days with a release file = the 84 rows; the 7 shutdown weeks (2 Oct - 13 Nov 2025) have no file; embargo line "8:30 A.M. (Eastern)" read in 6 files incl. the moved days |
| GDP | 19 | bea.gov/news/schedule/full-2025, /full (2026), bea.gov/news/archive (publication dates) | 19 of 19; the 30 Oct 2025 advance estimate was scheduled, never released (no row: right); it came out 23 Dec 2025 |
| PCE (personal income and outlays) | 20 | same BEA pages | 19 of 19 release rows incl. the three 10:00 releases (30 Apr 2025, 5 Dec 2025, 22 Jan 2026); the 20th row (2025-12-23, "data_update") is not a BEA income-and-outlays release — it sits on a GDP day at the same time, so it changes no filter day; left in |
| retail sales | 12 of 21 | census.gov/retail/release_schedule.html (Sep 2025 data on) | 12 of 12 (25 Nov 2025 ... 16 Sep 2026); the 9 rows Jan-Sep 2025 were not re-read today |
| PPI | 20 | BLS schedule pages 2025 + 2026; bls.gov/bls/news-release/ppi.htm (archive copy 2026-08-21) | 20 of 20 on the schedule; 19 of 19 release files |
| JOLTS | 21 | BLS schedule pages; jolts.htm (archive copy 2026-09-15) | 21 of 21 on the schedule; 20 of 20 release files (Sep + Oct 2025 data came out together on 9 Dec 2025) |
| ISM manufacturing / services | 21 / 21 | prnewswire.com ISM newsroom release stamps, 3 pages | 42 of 42 stamped 10:00 ET on the row's date |
| Michigan sentiment (prelim) | 21 | data.sca.isr.umich.edu/fetchdoc.php?docid=75443 (updated 2026-08-06) | 21 of 21 |

Spot check asked for: at least 25 rows other than NFP / CPI / FOMC. Done: 238 of the 248 other rows (all but 9 retail rows and the PCE "data_update" row).

## Changes to events.csv (5 rows added, nothing else touched; the old file is `out/exam2026/events_before_fix.csv`)
| date | time ET | type | source |
|---|---|---|---|
| 2026-09-30 | 08:30 | GDP (third estimate, Q2 2026) | bea.gov/news/current-releases, published 30 Sep 2026 — MISSING before (the file said it covered to 30 Sep) |
| 2026-09-30 | 08:30 | PCE (August 2026) | same |
| 2026-10-01 | 08:30 | CLAIMS | oui.doleta.gov/press/2026/100126.pdf (embargo 8:30 A.M. Thursday, October 1, 2026) |
| 2026-10-01 | 10:00 | ISM_MFG | ISM release stamp Oct 01, 2026, 10:00 ET |
| 2026-10-02 | 08:30 | NFP | bls.gov/news.release/empsit.nr0.htm (archive copy of 2026-10-05: embargoed until 8:30 a.m. Friday, October 2, 2026) |

These five days are AFTER the 2026 period that was scored (it ends 2026-09-22), so they change no result; they are in so the calendar
is right for the next user. Not checked: the time of day inside the BLS / Census pages beyond what the pages print (08:30 / 10:00).
