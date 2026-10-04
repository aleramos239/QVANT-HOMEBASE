The L2 data layer is built, cached for the in-sample window and tested (24 tests pass). Two findings change assumptions in the SPEC: the book snapshot is end-of-minute, and OFB rolls after our tape, not before.

## What was built (all under `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/`)
- **`l2data.py`** — readers, feature functions, cache builder and loader.
  - `load_features(start, end, allow_holdout=False)` returns a DataFrame indexed by `usable_at` (UTC ns) with `date`, `et_min`, `session` (R sessions, tagged by decision time), `globex_date` and `contract`. By default it sets book and research-tier columns to NaN wherever `book_ok` is False.
  - `features_from_book(bids, asks)` is the single implementation; the cache builder calls the same vectorised core.
  - `LiveFeatureState.update()` adds the trailing columns minute by minute for live use; `desk_minute_books()` picks the desk DOM line at the historical snapshot instant.
  - Holdout guards raise `HoldoutSealed` in `load_features`, `build_features`, `build_cache` and `iter_bin`.
- **`cache/l2feat_NQ_{2021,2022,2023,2024}.parquet`** — 1,179,675 rows, about 100 MB; single-process build takes 12 s.
- **`DATA.md`** — timestamp law with numbers, column definitions, roll finding, live parity, sanity report, open risks.
- **`ts_law.py`** → `out/ts_law.json`, and **`data_report.py`** → `out/data_sanity.{json,md}`.
- **`tests/test_l2data.py`** — 24 passed (about 5 s).

## Timestamp law
A depth.bin or hist.bin row stamped minute M is the book at the **end** of M, about 59.3 s into it. So `usable_at(M) = M + 60 s`, and own flow for minute M is usable at the same instant.

- **Sample:** 14,341 random in-sample minutes across 2021–2024, compared against ofb_tick prints.
- **Distance of the last print to [bid, ask]:** 4.23 pts at M+0, 0.23 pts at M+60 s, 1.37 pts at M+65 s.
- **Head to head:** end-of-minute closer in 12,779 minutes, start closer in 498, tie in 1,064.
- **Snapshot instant:** the minimum sits at 59.25–59.45 s in every year, so reading at M+60 s is not a look-ahead.
- **hist vs depth:** hist best bid/ask equals depth best on 14,373 of 14,373 sampled rows.
- **ofb_tick lag convention:** its `prev_best_*` equals the row stamped `flow_t` on 14,337 of 14,337.
- **Vendor vs own delta:** correlation 0.951 at the same minute, about 0.1 at ±1 minute.

## Feature table
- **Deployable book** (top 10 near levels, relative only): top1/3/10 sums per side, `imb3`, `imb10`, `spread_ticks`, wall size and tick distance, median level size, `bid_n`/`ask_n`, `depth10`, change vs previous snapshot, ratio to trailing-15-min median.
- **Added beyond the brief:** `depth10_rel20d` (depth vs same-minute median over the prior 20 sessions), as the input for the B6 filter.
- **Deployable flow** (`f_*`, from `flow_1m/NQ.parquet`): tape OHLC, volume, buy/sell volume, delta, cum delta, sweep volume and counts, big print and big order.
- **Research tier** (`rt_*`): size_imb, pulled, ice, qdepl, cum_delta.
- **Flags:** `book_valid`, `in_tape`, `roll_block`, `ofb_mismatch`, `book_ok`.
- **Coverage:** `book_ok` is 91.5–92.9% per year; the rest is roll block (4.6%) plus 30 holiday sessions with no tape and early closes.
- **Sanity correlation:** I3 and I10 against the next 1- and 5-minute return give |r| ≤ 0.017 everywhere. I10 against the past minute's return is −0.19, which also confirms the stamps are not shifted.

## Roll finding
In 2021–2024 OFB rolls **after** our tape. The session before the tape roll shows zero mismatch on all 13 rolls; the roll day is on the other contract on 13 of 13, and the day after on 12 of 13. I set `book_ok=False` on roll day −1 (per SPEC), roll day, and roll day +1 (measured), 39 sessions in total. A per-session mismatch flag (25 sessions, all inside that block) is the safety net for the holdout.

## Open risks
1. **Roll assumption elsewhere:** any other component still assuming "OFB rolls first" will mishandle roll week.
2. **Desk vs OFB sizes unverified:** there is no overlapping day (OFB ends 2026-07-08, desk DOM starts 2026-09-25). Desk RTH top-10 depth is about 30% below OFB 2024-Q4; prefer ratios and z-scores over thresholds in contracts.
3. **Snapshot staleness:** research books are about 0.7 s old at the boundary. Live should sample at or before M+59.3 s to match.
4. **Holdout book coverage:** by file size alone (not read), the 2026-06-01→07-08 depth file is about 10 days of 40-level rows, against 37 days of hist. Most of June 2026 will lack book features in stage E. The holdout build path has only run on synthetic files.
5. **Early sample not built:** there is no tape before 2021-09-22, so `book_ok` would be False throughout 2017-06 → 2021-09-21. Stage E needs a bars-based session mask first.
6. **Hindsight masks:** `in_tape` and `ofb_mismatch` use whole-session information. They are data-quality masks, not signals.
7. **`depth10_rel20d` live:** it needs 20 sessions of stored desk DOM; the desk has 4 full days.
8. **Tick-archive gap:** the 2022-06-21 tape only starts at 14:28 ET.
9. **Vault learnings not written:** house rules restrict writes to the pilot directory, so the roll and timestamp findings are only in `DATA.md` for now.

Nothing was committed, and nothing in `homebase/`, `~/.homebase` or the previous pilot was touched. No OFB, tick or flow row dated 2025 or later was read; the only later data touched were desk DOM lines, for live parity.