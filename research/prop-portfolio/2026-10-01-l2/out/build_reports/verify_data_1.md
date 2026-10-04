{
 "ok": true,
 "summary": "The data layer passes the live-parity and correctness checks: I found no blocker or major issue, and seven minor ones (listed in issues). The one worth patching is a hole in `book_ok` after rolls, which touches no tradeable session.\n\nComponent verified: `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py`, its cache `cache/l2feat_NQ_{2021..2024}.parquet`, and `DATA.md`. I changed nothing in the pilot directory; my scripts are in the scratchpad under `v/` (`hand30.py`, `cov.py`, `desk.py`, `fuzz.py`, `live.py`, `contract*.py`, `tslaw.py`, `dyn.py`, `flowchk.py`). I read only in-sample OFB, tick and flow rows, plus desk DOM lines for parity. The builder's 24 tests pass (3.3 s).\n\n**What I checked**\n- **Hand recompute from raw bytes:** using my own struct reader and pure-python features, 30 of 30 random in-sample rows match the cache on all 18 static columns. Extended to 20,000 random rows: 0 mismatches, and 158 invalid books are all NaN with `book_valid=False`.\n- **Top-10 near-book only:** on 40,000 sampled `book_ok` sides the near prefix is at least 40 levels, with no zero slots inside it, so no far-cluster slot can reach the top 10. The top-10 span is 9 ticks at the median, the same as the desk DOM.\n- **Relative, not absolute:** the cache has 60 columns and none holds an OFB price; the only prices are our own tape's `f_o/h/l/c`.\n- **Identical book, identical numbers:**\n  - The same 20,000 rows passed desk-shaped through `features_from_book` equal the cache 20,000 of 20,000.\n  - A 4,000-row fuzz of the 64-slot block path (zero holes, far clusters, crossed and dead sides) against the desk path gave 0 mismatches.\n  - `LiveFeatureState` fed minute by minute over 11 normal whole sessions reproduces all static and trailing columns exactly; the three tape-gap or holiday sessions differ only as in issue 5.\n  - On about 10,000 real desk lines, `features_from_book` equals my hand calculation, and the desk lines are best-first with positive integer sizes.\n  - `desk_minute_books` matches an independent snapshot selection on two desk files.\n- **Trailing columns by hand:** `*_chg` and `*_rel15` match on 3,000 rows (11,494 finite values); `depth10_rel20d` matches on 1,100 values.\n- **NaN handling and coverage:** no infinities; a masked load has no non-NaN book or research-tier value where `book_ok` is False, and no NaN static value where it is True. Rows per year, sessions (855, of which 30 have no tape), `book_ok` 92.93 / 91.52 / 91.58 / 91.56% and the NaN shares all reproduce `DATA.md`. A fresh in-memory rebuild equals the cache on every column.\n- **Timestamp law:** independently confirmed on 2,016 minutes over 48 days. Mean distance of the last print to [bid, ask] is 4.45 pts at M+0, 0.114 at M+59.4 s and 0.226 at M+60 s; end-of-minute is closer in 1,805 minutes against 65. Flow minute M equals the prints in [M, M+60 s) on 450 of 450 rows.\n- **Holdout guards:** five probes all raise `HoldoutSealed`, and the cache holds 2021\u20132024 only.\n\n**Recommended patch:** add a per-minute contract check, or extend the roll block to 00:00 UTC of the session two after the roll, and correct the roll paragraph in `DATA.md`.",
 "issues": [
  {
   "severity": "minor",
   "desc": "`book_ok` is True on rows whose OFB book is still the old contract. On 11 of 13 rolls OFB switches at 00:00 UTC inside the session two after the tape roll, so that session's first 1-2 hours (18:01 ET to 19:00/20:00 ET) carry the old contract's book. The static block {-1, 0, +1} ends a session too early, and the session-median `ofb_mismatch` flag cannot see a partial session, so it is not the holdout safety net the builder describes. No tradeable-session row is affected: every leaked row is tagged session ''. Contamination is limited to evening rows and their `*_rel15` / `depth10_rel20d` values.",
   "evidence": "scratch `contract2.py` / `contract3.py` / `last.py`: 1,015 `book_ok` rows with |OFB mid - tape close| > 20 pts, contiguous from 18:01 ET, in 10 sessions (2022-06-15 120 rows median -33.0; 2022-09-14 120, -79.5; 2022-12-14 59, -120.1; 2023-03-15 119, -129.9; 2023-06-14 120, -185.5; 2023-09-13 120, -194.8; 2023-12-13 60, -212.8; 2024-03-13 120, -249.0; 2024-09-18 118, -236.1; 2024-12-19 59, -272.6). 2022-03-16 also leaks: its 18:00-20:00 ET bucket has median +3.25 pts with book_ok share 1.00. Upper bound of the window: 1,320 book_ok rows; R-session rows among them: 0. DATA.md's 'every other session |median| <= 0.12 pts' is true only because the median hides an 8-12% partial session.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py"
  },
  {
   "severity": "minor",
   "desc": "The desk DOM recordings are not '4 full days' as DATA.md section 3 and the builder report state. Two of the four days have multi-hour outages, so any asia or london book strategy would have had NaN features live. This is a deployability risk for the pilot rather than a research-data defect, and it is not among the listed open risks.",
   "evidence": "scratch `desk2.py` / `desk3.py`: gaps of 20,101 s (2026-09-29 03:27 -> 09:02 ET), 30,390 s (09-30 00:39 -> 09:05 ET), 1,455 s (09-30 14:33 -> 14:57 ET) and 1,556 s (09-30 19:30 -> 19:56 ET). Minute snapshots per R session: 09-29 london 29/325; 09-30 asia 41/180, london 0/325, pm 125/148. 09-28 and 10-01 are complete. `desk_minute_books` skips these minutes, whereas OFB carries a row for every grid minute.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/DATA.md"
  },
  {
   "severity": "minor",
   "desc": "B4 `wall_bounce` and B5 `wall_break` need the wall's price in tape coordinates, and the cache stores only relative features (wall distance from the OFB best, as the SPEC requires). Anchoring on the tape close instead is noisy at about the scale of B4's 2-tick trigger. The family authors should take the absolute best from ofb_tick `prev_best_bid/ask`, or a tape-relative best offset should be added; live, the desk knows the exact wall price.",
   "evidence": "scratch `contract.py`: on 1,080,914 book_ok rows, |OFB mid - tape close| is 0.25 pts at the median, 0.75 at p90 and 2.25 at p99 (1, 3 and 9 ticks). Cache columns contain no best price or tape-relative offset.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py"
  },
  {
   "severity": "minor",
   "desc": "`desk_minute_books` yields the in-progress minute when it reaches the end of a file that is still being written. A live caller would feed `LiveFeatureState` a snapshot taken before the 59.3 s instant, and the value for that minute changes on re-read.",
   "evidence": "scratch `desk3.py` on the growing 2026-10-02 file: last line t=1790900138315 ms, last yielded minute 1790900100, whose snapshot instant is 1790900159300 ms, so the yield is 21.0 s premature. The unconditional final `yield` is at l2data.py lines 351-352.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py"
  },
  {
   "severity": "minor",
   "desc": "The cached trailing columns depend on the hindsight `in_tape` mask, so live and cache differ on tape-gap and holiday sessions. The cache is NaN there (conservative, not a look-ahead). Normal sessions match exactly.",
   "evidence": "scratch `live.py`: 11 normal sessions (10 random plus the 2023-11-24 early close) have 0 static and 0 trailing mismatches. 2022-06-21 (tape starts 14:28) has 1,242 trailing mismatches, 15 of them on in_tape rows where the cache is NaN and live has a value. 2024-07-04 has 1,299 and 2023-07-03 has 225, all on rows outside the tape.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py"
  },
  {
   "severity": "minor",
   "desc": "Two small inaccuracies in DATA.md. The 'fewer than 10 near levels in 0.0002% of rows' figure holds only for traded rows; and '1,380 rows per session' has one exception.",
   "evidence": "scratch `cov.py` / `dyn.py`: bid_n or ask_n < 10 on 2,763 book_valid rows (0.236%), against 3 in_tape rows and 1 book_ok row. Session 2024-11-29 has 1,155 rows because the OFB grid ends at 13:15 ET; the other 854 sessions have 1,380.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/DATA.md"
  },
  {
   "severity": "minor",
   "desc": "The cache stores features as float32 while `features_from_book` and `LiveFeatureState` return float64. Ratios such as imb3, imb10 and `*_rel15` therefore agree to about 1e-7 relative rather than bit for bit; sizes and tick counts are exact. Research thresholds should not sit on exact ratio ties.",
   "evidence": "scratch `hand30.py` / `live.py`: equality holds at rel_tol 1e-6 on 20,000 rows and 11 normal sessions; `build_features` casts BOOK_COLS to np.float32 at l2data.py lines 479-481.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2data.py"
  }
 ]
}