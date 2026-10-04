**l2data fix report (2026-10-01 22:08 ET)** — all six verifier issues are fixed, the cache is rebuilt, and `FEATURES.md` is written. The whole suite passes: 342 tests in 6:47, of which 41 are in `tests/test_l2data.py`.

One earlier full run had a single failure in `tests/test_score_verify.py`, at the moment another agent was rewriting `apex300.py` and `score.py`; it passed on the rerun and does not touch l2data.

**1. Per-minute OFB-vs-tape mismatch flag**
- `ofb_mismatch` is now per minute: the old session rule, or the centred 61-minute median distance of the tape close to [best bid, best ask] beyond ±1.0 pt, padded ±2 minutes.
- It flags the 11 roll day +2 evenings: 1,159 rows, all with session tag `""`, none in an R session. `book_ok` is now False there.
- Clean minutes peak at 0.75 pts and flagged minutes start at 1.25, so no fast-market minute is masked.
- Trailing columns (`*_chg`, `*_rel15`) now skip flagged snapshots, so they never span a contract switch.
- Cache rebuilt (11 s, atomic writes): 1,179,675 rows, 62 columns, equal to a fresh build with the final code. R-session rows are value-identical to the old cache.

**2. Seal moved to 2024-12-31 17:00 ET**
- `SEAL_KEY = 20241231170000`. An in-sample build caps both the OFB key range and the flow cut there, so the New Year's Eve evening rows are never read.
- `iter_bin` raises for any `key_hi` past the seal.
- `BinFile` rows come only from `row(i)` / `rows(i, j)`, which raise `HoldoutSealed` on sealed rows unless opened with `allow_holdout=True`. `.mm` is refused the same way, and negative indices raise.

**3. `phase_check(months)`**
- It measures the snapshot instant per month on a 0.02 s grid and raises `PhaseCheckFailed` if the pooled instant or any session is ≥ 59.99 s, or if a month has OFB rows but nothing measurable.
- In-sample result: all 40 months pass (784 sessions, 10 s). Monthly range is 59.02–59.94 s, single sessions 59.00–59.98 s. The thinnest margins are 2023-11 (0.04 s) and 2024-12 (0.02 s).
- Synthetic tapes with the snapshot at 60.0 s, 60.4 s, or late in one session only all fail, as intended.
- `DATA.md` now has the per-month table and the recommended 1 s execution guard: `l2sim.run(..., latency_ms=1085)`.
- CLI: `python l2data.py phase` writes `out/phase_check.json`.

**4. Wall prices in tape coordinates**
- New columns `bid_px` / `ask_px` hold the snapshot's best bid / ask, NaN wherever `book_ok` is False. They are read from depth.bin rather than the tick files; a test confirms they equal ofb_tick `prev_best_bid/ask`.
- Wall price is `bid_px − bid_wall_dist × 0.25` or `ask_px + ask_wall_dist × 0.25`.
- I deliberately did not store a ready-made wall-price column: under C2 the distance comes from the donor session and must be re-anchored on the receiving session's own price. `bid_px` / `ask_px` must never be shuffled.

**5. `desk_minute_books`**
- It yields completed minutes only. The trailing minute is yielded only once the clock is more than 5 s past its snapshot instant.
- The default sampling instant is now M+59.0 s (`LIVE_SNAPSHOT_S`), per the SPEC override.

**6. `DATA.md` corrections**
- Desk recordings: only 2 of 4 days are complete. Outages were 03:27–09:02 ET on 09-29 and 00:39–09:05 ET on 09-30, plus shorter ones; per-session coverage is tabulated.
- Rows per session: 1,380 except 2024-11-29 (1,155).
- Fewer than 10 levels: 2,763 `book_valid` rows (0.24%), but only 3 inside the tape and 1 `book_ok`.
- Added the float32 note, the roll paragraph rewrite, the hindsight-mask caveats and the risk list.

**`FEATURES.md`** (102 lines) covers every deployable column with meaning, units, RTH p5/p50/p95 and NaN rules; `ctx.feat` / `ctx.feat_window` / `ctx.feat_n` semantics; B4/B5 wall recipe; C2 shuffle rules; z-score and flow recipes. A test checks its claims against `l2sim.L2Features`.

**What other components need to know**
- **Holdout build gate (my addition):** `build_cache(allow_holdout=True)` now refuses to read anything until the caller passes `phase_checked=True`. Stage E must run `phase_check(holdout months, allow_holdout=True)` first.
- **`BinFile.mm`:** any script indexing it directly must switch to `row()` / `rows()`. I updated `ts_law.py`; its output JSON is byte-identical.
- **`data_report.py`:** extended with outage, anchor and partial-mismatch tables, and rerun.

**Open risks**
- 672 `book_ok` minutes (0.06%) have the anchor more than 5 pts from the tape close, 50 more than 10 pts. These are isolated fast-market minutes and are intentionally not masked; B4/B5 must check `ctx.last_price` against the wall.
- A calendar spread under about 1.5 pts would escape the per-minute flag. None has occurred since 2022-03.
- The early sample (2017-06 → 2021-09) cannot be phase-checked or mismatch-checked because there is no tick tape.
- The holdout build path has still only run on synthetic files.
- The `l2sim.py` docstring example reads `imb10_z`, which is not a cache column; families compute the z-score themselves. That file belongs to the sim owner, so I left it.

Nothing was committed, and I did not touch `homebase/`, `~/.homebase` or the previous pilot. No sealed row was read. `git status` shows `homebase/static/index.html` as modified; that is not from this task.

The `plugin:nimble:nimble` MCP server needs authorising via `/mcp` before its tools can be used; it was not needed here.

Files are in `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2`:
- `l2data.py`
- `DATA.md`
- `FEATURES.md`
- `ts_law.py`
- `data_report.py`
- `tests/test_l2data.py`
- `cache/l2feat_NQ_{2021..2024}.parquet`
- `out/phase_check.json`
- `out/data_sanity.json`
- `out/data_sanity.md`