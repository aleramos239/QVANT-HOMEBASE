# L2 data layer (NQ) — `l2data.py`

Built 2026-10-01, revised the same evening after the two verifier reviews (`out/build_reports/verify_data_*.md`).
In-sample only: no OFB / tick / flow row of a session dated ≥ 2025-01-01 was read. The only later data touched are
desk DOM lines (2026-09-28 →, outside every research window) for live parity of the feature function (§3).
Code `l2data.py` · evidence `ts_law.py` → `out/ts_law.json`, `l2data.py phase` → `out/phase_check.json` · sanity
`data_report.py` → `out/data_sanity.{json,md}` · tests `tests/test_l2data.py` (41 pass) · cache
`cache/l2feat_NQ_{2021..2024}.parquet` (1,179,675 rows, ~100 MB). Column reference for family authors: `FEATURES.md`.

```python
import l2data as D
df = D.load_features("2022-01-03", "2022-12-30")          # indexed by usable_at (UTC ns); HoldoutSealed if end >= 2025
row = df.loc[pd.Timestamp("2022-03-01 09:30", tz="America/New_York").tz_convert("UTC")]   # decision AT 09:30:00 ET
f = D.features_from_book(bids, asks)                      # same function on a desk DOM line {"b": [[px,sz],..], "a": ..}
D.phase_check(["2024-11", "2024-12"])                     # per-month timestamp-law check; raises PhaseCheckFailed
```
Rebuild: `"~/ONYX TRADING/.venv/bin/python" l2data.py build` (single process, 11 s; files are replaced atomically).
Tests: `... -m pytest tests/test_l2data.py`. Families never import this module: they read columns through
`ctx.feat` / `ctx.feat_window` (FEATURES.md).

**Changes in this revision** (all in-sample R-session rows are unchanged; `book_ok` changed on 1,159 evening rows):
per-minute `ofb_mismatch` (roll day +2 evenings) · reads capped at 2024-12-31 17:00 ET and a guarded `BinFile` ·
`phase_check(months)` · price anchors `bid_px` / `ask_px` · `desk_minute_books` yields completed minutes only.

## 1. Timestamp law (measured)

**A depth.bin / hist.bin row keyed minute M (ET wall clock `yyyymmddHHMM00`) is the book at the END of minute M —
between 59.02 and 59.98 s into it depending on the calendar month (pooled median 59.3 s) — never the start.
`usable_at(M) = M + 60 s`.** Own flow minute M (`t_utc == M`) aggregates prints in [M, M+60 s) and is usable at the
same instant. A decision at a minute boundary T reads the row whose `usable_at == T` (stamp T−60 s) and executes on
the first print after T. The law holds in every in-sample month, but in two of them (2023-11, 2024-12) by only
0.02–0.08 s: see "Per-month phase" below before trusting it on new data.

Method (`ts_law.py`, seed 20261001): 40 sessions per year 2021–2024 (roll-block sessions excluded) × (60 random
RTH minutes + 30 random 02:00–08:00 ET minutes) = 14,341 minutes with a two-sided book. For each, the distance in
points from the ofb_tick print just before / just after `M + τ` to the row's [best bid, best ask] (0 if inside).

| τ (last print before M+τ) | −60 s | −30 s | 0 s (start) | +30 s | +55 s | **+60 s (end)** | +65 s | +90 s | +120 s |
|---|---|---|---|---|---|---|---|---|---|
| mean distance, pts (all) | 6.14 | 5.12 | 4.23 | 2.70 | 0.85 | **0.23** | 1.37 | 3.16 | 4.34 |
| RTH only | 7.48 | 6.24 | 5.17 | 3.32 | 1.07 | **0.30** | 1.75 | 3.91 | 5.34 |
| overnight only | 3.47 | 2.88 | 2.37 | 1.49 | 0.40 | **0.09** | 0.61 | 1.66 | 2.37 |

* Head to head on the same 14,341 minutes: end-of-minute closer in **12,779**, start closer in 498, tie 1,064.
  Last print inside [bid, ask]: 8.1% at M+0 vs 64.2% at M+60 s (76.9% at M+59.3 s).
* Fine grid (0.05 s): the distance is minimal at **τ = 59.3 s** (last print before) / 59.15 s (first print after):
  0.115 / 0.110 pts, against 0.226 / 0.281 at 60.0 s and 0.353 / 0.409 at 60.1 s. By year (RTH): 2021 59.25 s,
  2022 59.30 s, 2023 59.45 s, 2024 59.35 s. These are yearly POOLED figures (0.5–0.9 s before the boundary on
  average); the phase is not the same every month — the per-month table below is the binding statement.
* hist.bin best_bid/ask == depth.bin best on 14,373 / 14,373 sampled rows (same snapshot instant); ofb_tick's
  `prev_best_bid/ask` on ticks with `flow_t == M` == the row stamped M on 14,337 / 14,337 (its lag convention —
  ticks of minute M+1 carry row M — is this same law).
* Vendor Δcum_delta of row M vs own `f_delta`: r = 0.951 with our minute M, 0.09 / 0.12 with M−1 / M+1 (RTH, n = 303k):
  hist stamp M covers the same minute as our flow minute M.
* Timezone: keys are ET wall clock including DST (winter and summer samples both sit inside the spread at +60 s).
* Leak check from the finished table: imb10 vs the PAST 1-min mid change r = −0.19 (Spearman −0.24); vs the NEXT
  1-min change |r| < 0.005 (§5). A one-minute mis-stamp would have put the −0.19 on the forward side.

### Per-month phase (`phase_check`, `out/phase_check.json`)

The vendor's snapshot instant is **constant within a calendar month and changes between months**. `phase_check`
measures it mechanically: for every tape session of a month outside the roll block, every RTH row (stamps
09:30–15:59 ET) with a two-sided book, the distance from the last ofb_tick print before M+τ to [best bid, best ask]
on a 0.02 s grid of τ ∈ [58, 61] s; the τ minimising the mean distance is the instant the book was taken (ties
resolve towards the boundary). Per month it reports the pooled instant `phase_s` and the per-session range.
All 40 in-sample months, 784 sessions, 304,495 minutes (10 s, single process):

| year | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021 |  |  |  |  |  |  |  |  | 59.10 | 59.14 | 59.24 | 59.72 |
| 2022 | 59.04 | 59.62 | 59.26 | 59.14 | 59.78 | 59.02 | 59.52 | 59.06 | 59.26 | 59.30 | 59.32 | 59.30 |
| 2023 | 59.64 | 59.22 | 59.76 | 59.30 | 59.62 | 59.66 | 59.44 | 59.40 | 59.72 | 59.36 | **59.92** | 59.06 |
| 2024 | 59.38 | 59.24 | 59.64 | 59.62 | 59.28 | 59.46 | 59.38 | 59.54 | 59.18 | 59.14 | 59.16 | **59.94** |

* Monthly range **59.02–59.94 s** (pooled), single sessions 59.00–59.98 s (the verifier's independent figure on the
  raw tick archive: 59.02–59.98 s); within a month the sessions agree to ≤ 0.08 s. No session reaches 60.00 s, so
  `usable_at = M + 60 s` is not a look-ahead anywhere in-sample.
* The margin is thin: 2023-11 (sessions ≤ 59.96 s) and 2024-12 (≤ 59.98 s) take the book 0.02–0.08 s before the
  boundary; seven months have less than 0.3 s. Nothing in the vendor data promises the next month stays below 60 s.
* **Overnight bucket (added 2026-10-02).** The RTH rows say nothing about a phase that is late only overnight, where
  asia, london and the 03:00 / 09:30 opens decide. `phase_check` now also measures every other in-hours stamp of the
  same sessions (the evening before, 00:00–09:29, 16:00–16:59 ET), POOLED per month (per-session overnight
  estimates are too noisy; minutes whose book is on another contract are dropped): `on_phase_s`, `on_minutes`,
  `on_margin_s`, and `failed_parts` (`rth` / `overnight`). In-sample: 775,321 overnight minutes, pooled instant
  59.00–59.96 s, within 0.02 s of the RTH instant in every month; the two thin months are
  2023-11 (59.92 s) and 2024-12 (59.96 s). All 40 months pass both buckets; the RTH
  numbers above are unchanged.
* **Rule for new data (holdout stage E, early sample):** `l2data.phase_check(months, allow_holdout=True)` must run on
  every month before any feature of that month is used. It raises `PhaseCheckFailed` (table in `.result`) if a
  month's pooled RTH instant, any session's RTH instant or the pooled overnight instant is ≥ 59.99 s, if a month has
  OFB rows but no measurable session, or if its overnight rows cannot be measured; a month with no OFB depth rows at
  all passes vacuously (it has no book features). Tested on synthetic tapes with the snapshot at 60.0 s, 60.4 s, in
  one session of a month only, and late overnight only: all fail.
* **Enforced, not an honour flag (2026-10-02).** The verdicts are persisted in `cache/phase_guard.json`
  (`persist_phase`; `python l2data.py phase` writes the in-sample months, the holdout build writes its own months:
  `build_cache(allow_holdout=True)` runs `phase_check` itself before any feature is computed). `l2sim` reads that file:
  a run whose `features=` loader reads BOOK columns executes every session of a failed month with `EXEC_GUARD_MS`
  (1 s) of extra placement latency (`meta["exec_guard"]`), and a HOLDOUT run on book features raises
  `PhaseGuardMissing` for any month that is not in the file. Flow-only loaders (`f_*`: our own tape) and runs without
  features are not touched. In-sample no month failed, so no in-sample session is guarded.
* **Recommended option — 1 s execution guard.** Run with `l2sim.run(..., latency_ms=1085)` (order placement
  85 ms + `EXEC_GUARD_MS` 1,000): the decision still reads the row at M+60 s, but no order can fill before
  M+61.085 s, so the trade is causal for any snapshot instant up to 61 s. Use it (a) as a standing robustness line
  next to every promoted pick — an edge that does not survive a 1 s delay lives inside the 0.02–1 s margin and is
  not deployable anyway — and (b) as the mandatory fallback for any month `phase_check` fails. It is not the
  default because it would break the validated tester parity (85 ms).

Constants: `USABLE_LAG_S = 60`, `SNAPSHOT_OFFSET_S = 59.3` (pooled median, descriptive), `LIVE_SNAPSHOT_S = 59.0`,
`PHASE_MAX_S = 59.99`, `EXEC_GUARD_MS = 1000`. Live parity: sample the DOM at the last line ≤ **M+59.0 s**
(`desk_minute_books` default), i.e. never fresher than the earliest research month; a live book taken at M+60.0 s
would be up to 0.98 s fresher than research saw in the early-phase months (a train/live mismatch, not a look-ahead).

## 2. The table (one row per Globex minute, 2021-09-21 18:00 ET → 2024-12-31 16:59 ET)

Index `usable_at` (datetime64[ns, UTC]) = stamp + 60 s. Rows: every OFB grid minute inside Globex hours (Sun–Thu
18:00 → 16:59 ET next day; the 17:00–18:00 break, Saturdays and Sunday pre-open are dropped — the vendor grid holds
crossed pre-open / stale books there). 1,380 rows per session on 854 of the 855 sessions; 2024-11-29 (day after
Thanksgiving) has 1,155 because the vendor grid itself ends at 13:15 ET that day.

| group | columns | definition |
|---|---|---|
| tags | `t_utc` | stamp minute start, UTC seconds (`usable_at − 60`) |
| | `date`, `et_min` | ET calendar date and minute-of-day of `usable_at` (the decision time) |
| | `session` | R/SPEC session containing the decision time: asia 00:00–03:00, london 03:00–08:25, nyam 09:30–11:00, mid 11:00–13:30, pm 13:30–15:58, else `""`. The 09:30:00 row (minute 09:29) is `nyam`. |
| | `globex_date`, `contract` | trading-session date (17:00 ET boundary, = flow `session`); tape front contract |
| flags | `book_valid` | both sides ≥ 1 near level and ask > bid |
| | `in_tape` | stamp between the first and last traded minute of that session on our tape (False on holidays without a tape, after early closes) |
| | `roll_block` | session ∈ {roll day −1, roll day, roll day +1}, rolls = `R/gen_drafts.build_rolls` logic |
| | `ofb_mismatch` | PER MINUTE: the OFB book is on another contract than our tape. True when the session median \|OFB mid − tape close\| > 2 pts (whole session), or when the centred 61-minute median distance of the tape close to [best bid, best ask] is beyond ±1 pt, ±2 minutes of padding (`mismatch_minutes`). Hindsight data-quality flag. |
| | **`book_ok`** | `book_valid & in_tape & ~roll_block & ~ofb_mismatch`. `load_features` NaNs every book, anchor and rt_ column where it is False. |
| book (deployable) | `bid_top1/3/10`, `ask_top1/3/10` | resting size summed over the best 1 / 3 / 10 near-book levels |
| | `imb3`, `imb10` | (B − A)/(B + A) on top-3 / top-10 sums (I3, I10) |
| | `spread_ticks` | (best ask − best bid)/0.25 |
| | `bid_wall_sz`, `bid_wall_dist` (+ask) | largest level size within the 10 levels and its tick distance from the best (tie → nearest) |
| | `bid_med_sz`, `ask_med_sz` | median level size over the 10 levels |
| | `bid_n`, `ask_n`, `depth10` | near levels used (≤ 10); `bid_top10 + ask_top10`. Fewer than 10 levels on either side: 2,763 `book_valid` rows (0.24%), almost all outside the traded session (stale vendor books on holidays) — 3 rows inside the tape, 1 `book_ok` row. |
| | `bid10_chg`, `ask10_chg` | top-10 depth minus the snapshot exactly one minute earlier (pulled/added proxy) |
| | `bid10_rel15`, `ask10_rel15` | top-10 depth / median of the previous 15 minutes' snapshots (≥ 8 valid) − 1 (B3 input) |
| | `depth10_rel20d` | depth10 / median of depth10 at the same ET minute over the previous 20 sessions (≥ 10 valid, book_ok only) − 1 (B6 input) |
| price anchors (deployable, NOT features) | `bid_px`, `ask_px` | best bid / best ask of the snapshot, in TAPE coordinates (float64). Equal to ofb_tick `prev_best_bid` / `prev_best_ask` of the same stamp. NaN wherever `book_ok` is False. Wall price = `bid_px − bid_wall_dist × 0.25` / `ask_px + ask_wall_dist × 0.25`. |
| flow (deployable) | `f_o f_h f_l f_c` | OUR tape's minute OHLC (not OFB prices) |
| | `f_volume f_buy_vol f_sell_vol f_delta f_cum_delta` | tick-rule aggressor volume, delta, session cum delta (resets 18:00 ET) |
| | `f_sweep_buy_vol f_sweep_sell_vol f_sweeps_buy f_sweeps_sell` | orders that walked ≥ 2 levels (volume / count) |
| | `f_big_print(_side) f_big_order(_side, _levels)` | largest print / aggressor order of the minute |
| research (never promotable) | `rt_size_imb rt_qdepl_bid/ask rt_pulled_bid/ask rt_ice_bid/ask rt_cum_delta` | OFB hist slots 5, 7–12, 14 of the same row |

Near book = `ladder_split` rule, vectorised: zero-size slots dropped, then the best-first prefix that keeps stepping
away from the best by ≤ 10 pts; only the first 10 such levels are used (identical to
`onyx.lab.ofb.ladder_split(side)[0][:10]` on 600 sampled sides). Flow rows exist only for traded minutes (NaN
otherwise, never filled). Every feature is backward looking: a 2-session build reproduces the full build row for
row (test). The trailing columns (`*_chg`, `*_rel15`) are computed on snapshots that are valid, inside the traded
session and not `ofb_mismatch`, so they never span a contract switch.

**Precision.** The cache stores book, flow-size and rt_ columns as float32 (prices `bid_px`, `ask_px`, `f_o/h/l/c`
and the cum-deltas as float64); `features_from_book` / `LiveFeatureState` return float64. Sizes, counts and tick
distances are exact in both; ratios (`imb3`, `imb10`, `*_rel15`, `depth10_rel20d`) agree to ~1e-7 relative, not bit
for bit. Do not put a research threshold on an exact ratio tie (e.g. `imb10 >= 0.2` where 0.2 is attainable):
compare with a margin or use `>` on a value no book can hit.

### Price anchors (`bid_px`, `ask_px`) — for B4 `wall_bounce` / B5 `wall_break`
The features stay relative (the SPEC's rule), but B4/B5 must place an order AT the wall, and the tape close is too
noisy an anchor for that: on `book_ok` rows |OFB mid − tape close| is 0.25 pts at the median, 0.75 at p90, 2.1 at
p99 (1 / 3 / 8 ticks) against B4's 2-tick trigger. So the cache carries the snapshot's own best bid / ask — the
same numbers as ofb_tick `prev_best_bid/ask` (test: equal on every joined minute of two sessions; `ts_law.py`:
14,337 / 14,337), read from depth.bin instead of the tick files. They are tape coordinates exactly where the OFB
book is on the tape's contract, which is what `book_ok` certifies; `load_features` NaNs them elsewhere, so an
other-contract price can never reach a family. Rules: (1) anchors are not features — never z-score, threshold or
C2-shuffle them (the C2 null transplants `*_wall_dist` / `*_wall_sz` from the donor and re-anchors on the receiving
session's own `bid_px` / `ask_px`, which is why no ready-made wall-price column is stored); (2) the anchor is the
book ~0.02–1 s before the decision: check it against `ctx.last_price` (a wall the tape has already traded through is
gone); (3) 672 `book_ok` minutes (0.06%) have the anchor mid more than 5 pts from the tape close, 50 more than 10
pts (max 28 pts): isolated fast-market minutes, not contract errors — B4/B5 must tolerate or skip them.

### Roll finding (differs from the SPEC's premise)
In 2021-09 → 2024 the OFB continuous does **not** roll before our tape — it rolls **after** it. Session median of
(OFB mid − tape close): day before the tape roll 0.00 on all 13 rolls; roll day ≠ 0 on 13/13 (−300 … +4 pts = the
calendar spread, OFB still on the OLD contract); roll day +1 ≠ 0 on 12/13. The static block is therefore
{−1 (SPEC), 0, +1 (measured)} = 39 sessions.

That block ends too early: on 11 of the 13 rolls OFB switches at 00:00 UTC inside the session two after the tape
roll, so the first 60–120 minutes of the roll day +2 evening (usable 18:01 → 19:00 / 20:00 ET) still carry the OLD
contract's book. A session median cannot see that (the "every other session |median| ≤ 0.12 pts" of the first
version of this file was true only because the median hides an 8–12% partial session). `ofb_mismatch` is now a
per-minute flag (`mismatch_minutes`): the signed distance of our tape's close to the snapshot's [best bid, best
ask], centred 61-minute median beyond ±1.0 pt, padded ±2 minutes. Measured in-sample:

* it flags the 11 evenings — 2022-03-16 (123 rows; the smallest offset, +3 pts), 2022-06-15 (122), 2022-09-14
  (122), 2022-12-14 (61), 2023-03-15 (121), 2023-06-14 (122), 2023-09-13 (122), 2023-12-13 (62), 2024-03-13 (122),
  2024-09-18 (121), 2024-12-19 (61) — **1,159 rows, all with session tag `""`, none in an R session**, and nothing
  else outside the static block (the 2021-12 and 2024-06 rolls had already switched);
* inside the block it flags every minute of the 25 other-contract sessions;
* on the remaining clean sessions the 61-minute median never exceeds 0.75 pts (tolerance 1.0), so no fast-market
  minute is masked: the flag removes other-contract books only (flagged minutes start at a median of 1.25 pts).
  After it, no `book_ok` row of a roll week sits more than 20 pts from the tape and the 61-minute median over all
  `book_ok` rows stays within the tolerance (test). 39 traded minutes have too few neighbours with a print to be
  checked (fewer than 5 in 61) and are left unflagged.

The flag is data-driven and per minute, so it also covers a holdout roll whose timing differs from the static
block, or any other partial-session mismatch — as long as the offset exceeds ~1.5 pts (NQ calendar spreads have been
25–300 pts since 2022-06; the two 2021-12 / 2022-03 spreads of 2.5–4 pts were caught). It looks up to 32 minutes
ahead: a hindsight data-quality mask, never a signal. Live there is nothing to reproduce (book and tape are one feed).

## 3. Live parity (`features_from_book`, `LiveFeatureState`, `desk_minute_books`)

`features_from_book(bids, asks)` takes `[[px, sz], ...]` best first and returns the 18 static columns + `book_valid`
(`with_px=True` adds the anchors `bid_px` / `ask_px`); the cache builder calls the same vectorised core
(`book_features_arrays`). `LiveFeatureState.update(minute_utc, bids, asks)` adds the four trailing columns, the
anchors and `usable_at`. Verified by the builder and both verifiers: cache == `features_from_book` on 20,000 random
OFB rows (all 64 slots and truncated to 10 levels); a 4,000-row fuzz of zero holes, far clusters, crossed and dead
sides; live state == cached static and trailing columns over 11 whole normal sessions (anchors: 09:00–12:00 ET on
2023-05-10, test); batch == live on a synthetic series with gaps and crossed books; ~10,000 real desk lines by hand.

`desk_minute_books(path)` picks, for each minute M, the last DOM line stamped ≤ M + 59.0 s (`LIVE_SNAPSHOT_S`).
It yields COMPLETED minutes only: a minute is complete once a later line exists; the trailing minute of a file is
yielded only when the clock is more than 5 s past its snapshot instant (a finished recording), never while the
minute is still in progress — so a value can no longer change on a re-read of a growing file (test).

Where live and cache differ by construction (not look-aheads; the cache is the conservative side):
* `in_tape`, `roll_block` and `ofb_mismatch` are hindsight masks. Live code must reproduce them from a calendar
  (holiday / early-close sessions, roll day −1 … +1) — and needs no mismatch flag, the desk book and tape being one
  feed. On tape-gap and holiday sessions the cached trailing columns are NaN where a live state fed the same books
  would have a value (2022-06-21: 15 traded rows; 2024-07-04, 2023-07-03: rows outside the tape only).
* `depth10_rel20d` needs 20 sessions of stored minute features; the desk has 4 days.
* float32 cache vs float64 live: §2 "Precision".

**Desk DOM recordings are not continuous.** Of the four recorded days 2026-09-28 → 10-01 only two are complete:

| ET day | asia | london | nyam | mid | pm | outages > 5 min (ET) |
|---|---|---|---|---|---|---|
| 2026-09-28 | 180/180 | 325/325 | 90/90 | 150/150 | 148/148 | 19:12–19:19 |
| 2026-09-29 | 180/180 | **29/325** | 90/90 | 150/150 | 148/148 | **03:27–09:02** (335 min), 19:45–19:54 |
| 2026-09-30 | **41/180** | **0/325** | 90/90 | 150/150 | **125/148** | **00:39–09:05** (506 min), 14:33–14:57, 19:30–19:56 |
| 2026-10-01 | 180/180 | 325/325 | 90/90 | 150/150 | 148/148 | — |

(minute snapshots present / decision minutes per R session.) `desk_minute_books` skips those minutes, whereas OFB
carries a row for every grid minute: an asia or london book strategy would have had NaN features — no signal — for
most of two of four nights. This is a deployability risk of the desk recorder, not a defect of the research data;
any book pick needs the recorder's uptime fixed (or a rule for what the strategy does without a book) before it runs.

Desk DOM vs OFB, RTH medians (design check only; different years, no overlap exists — OFB ends 2026-07-08, desk DOM
starts 2026-09-25): desk 2026-09-28→10-01 depth10 97, top1 2, spread 2, wall 8 @ 5 ticks, median level 4.5, 10
levels spanning 9 ticks, |imb10| 0.075 · OFB 2024-Q4 depth10 134, top1 2, spread 2, wall 10 @ 7 ticks, median level
6, |imb10| 0.078. Same order of magnitude and shape; desk depth runs ~30% thinner, and level/scale differences
cannot be separated from regime: prefer ratios / z-scores, never thresholds in contracts.

## 4. Holdout guard

The seal is the Globex session dated 2025-01-01, which opens on New Year's Eve: every OFB key ≥
`SEAL_KEY = 20241231170000` (2024-12-31 17:00 ET) and every flow row with `t_utc` ≥ that instant is sealed.

* `load_features`, `build_features`, `build_cache`, `phase_check` raise `HoldoutSealed` (a `PermissionError`) when
  the requested end is ≥ 2025-01-01 without `allow_holdout=True`; `iter_bin` raises for any `key_hi > SEAL_KEY`.
* An in-sample build caps its own reads at the seal: `build_features(end=2024-12-31)` asks `iter_bin` for keys
  `< SEAL_KEY` and the flow parquet for `t_utc <` 2024-12-31 17:00 ET, so the New Year's Eve evening rows (which the
  first version read and then dropped) are never touched (test with spies on both readers).
* `BinFile` no longer exposes its memmap: rows come from `row(i)` / `rows(i, j)`, which raise `HoldoutSealed` for
  any row keyed ≥ `SEAL_KEY` unless the file was opened with `allow_holdout=True` (the literal `True`); `.mm` is
  refused the same way; negative indices raise. `key(i)` / `bounds` read 8-byte stamps only — locating the seal
  needs them — never a payload. In the main file the first 3,923,718 rows are open (last key 2024-12-31 16:59 ET)
  and the other 729,344 (through 2026-05-31) sealed.
* The 2026-06-01→07-08 OFB file is not listed by default; the roll scan skips manifests named ≥ 2025.
* The cache holds 2021–2024 only; last row usable 2024-12-31 17:00 ET. A later holdout build
  (`build_cache(end=..., allow_holdout=True)`) writes only the 2025+ year files and leaves the in-sample files
  byte-identical. **It runs `phase_check` (RTH + overnight) on its own holdout months first and persists the
  verdicts in `cache/phase_guard.json` (§1)**: no flag can skip it (`phase_checked=` is accepted and ignored), and
  `l2sim` refuses a holdout run on book features for a month that file does not hold.

## 5. Sanity report (in-sample; full tables in `out/data_sanity.md`)

| year | rows | sessions | in_tape % | book_valid % | roll_block % | book_ok % | flow % |
|---|---|---|---|---|---|---|---|
| 2021 | 100,740 | 73 | 97.04 | 98.23 | 4.11 | 92.93 | 96.82 |
| 2022 | 358,800 | 260 | 96.13 | 99.10 | 4.62 | 91.40 | 96.07 |
| 2023 | 359,159 | 261 | 96.19 | 99.36 | 4.61 | 91.46 | 96.18 |
| 2024 | 360,976 | 262 | 96.15 | 99.24 | 4.59 | 91.48 | 96.14 |

book_ok by session (unchanged by the per-minute flag): asia 91.8, london 91.8, nyam 91.7, mid 91.6, pm 91.1 %; in
the untagged evening / gap minutes 91.4 %. The ~8.5% not-ok = roll block 4.6% + sessions with no tape / early
closes 3.9% + the roll day +2 evenings 0.1% (the grid has 855 in-sample sessions, the tape 825: the 30 missing are
US holidays; early closes end at 13:00; the 2022-06-21 tape only starts 14:28 ET — an archive gap). Inside the
traded session only 6 minutes have an invalid book. No frozen snapshots: 0 of 303,026 traded RTH minutes repeat the
previous minute's book. Index unique and increasing.

NaN share (as loaded): static book, anchors + rt_ 8.43%; `*_chg` 8.50%; `*_rel15` 8.96%; `depth10_rel20d` 9.60%;
flow 3.81% (RTH 4.05%, all of it no-tape days). Inside R sessions: 8.36% / 8.36% / 8.36% / 9.53% (unchanged).

Quantiles 1 / 5 / 25 / 50 / 75 / 95 / 99 %:

| column | RTH (nyam+mid+pm) | everything else |
|---|---|---|
| bid_top1 | 1 / 1 / 2 / 3 / 4 / 7 / 10 | 1 / 1 / 1 / 2 / 3 / 5 / 8 |
| bid_top3 | 5 / 7 / 11 / 15 / 19 / 27 / 36 | 3 / 4 / 7 / 9 / 12 / 18 / 26 |
| bid_top10 | 25 / 36 / 59 / 76 / 95 / 128 / 156 | 16 / 21 / 32 / 44 / 56 / 79 / 108 |
| ask_top10 | 26 / 37 / 60 / 79 / 99 / 134 / 166 | 16 / 21 / 32 / 44 / 57 / 81 / 109 |
| imb3 | −0.43 / −0.29 / −0.12 / 0 / 0.10 / 0.27 / 0.41 | −0.50 / −0.33 / −0.14 / 0 / 0.14 / 0.33 / 0.50 |
| imb10 | −0.35 / −0.24 / −0.11 / −0.02 / 0.07 / 0.21 / 0.32 | −0.39 / −0.26 / −0.11 / 0 / 0.09 / 0.25 / 0.38 |
| spread_ticks | 1 / 1 / 2 / 2 / 2 / 3 / 4 | 1 / 1 / 2 / 3 / 3 / 5 / 7 |
| bid_wall_sz | 4 / 6 / 9 / 12 / 16 / 25 / 46 | 3 / 4 / 6 / 8 / 10 / 19 / 38 |
| bid_wall_dist | 1 / 2 / 5 / 7 / 8 / 9 / 9 | 0 / 1 / 4 / 6 / 8 / 9 / 10 |
| bid_med_sz | 2 / 3.5 / 5.5 / 7.5 / 9.5 / 12.5 / 15.5 | 1 / 2 / 3 / 4 / 5.5 / 7.5 / 9.5 |
| depth10 | 55 / 77 / 122 / 157 / 192 / 251 / 301 | 34 / 44 / 66 / 90 / 112 / 153 / 199 |
| bid10_chg | −54 / −30 / −10 / 0 / 10 / 31 / 53 | −37 / −19 / −6 / 0 / 6 / 18 / 36 |
| bid10_rel15 | −0.38 / −0.25 / −0.10 / 0 / 0.14 / 0.42 / 0.78 | −0.40 / −0.28 / −0.12 / 0 / 0.15 / 0.47 / 0.97 |
| depth10_rel20d | −0.57 / −0.39 / −0.16 / 0 / 0.18 / 0.50 / 0.82 | −0.50 / −0.34 / −0.13 / 0.01 / 0.16 / 0.46 / 0.81 |
| f_volume | 257 / 374 / 644 / 966 / 1502 / 2865 / 4348 | 7 / 15 / 41 / 80 / 159 / 450 / 1155 |
| f_delta | −521 / −283 / −84 / 0 / 83 / 276 / 503 | −142 / −60 / −14 / 0 / 14 / 59 / 137 |

RTH median depth10 by year: 171 / 135 / 176 / 149 (2021–2024); spread 2 ticks every year. The NQ book is thin: the
best level holds 1–4 contracts, the whole top 10 per side ~76.

I3 / I10 vs next return (Pearson / Spearman; data check only, nothing selected from it):

| pair | all | RTH | overnight |
|---|---|---|---|
| imb3 → next 1 min, OFB mid-to-mid | +0.004 / +0.010 (n = 1.08M) | +0.001 / +0.001 (303k) | +0.007 / +0.016 (777k) |
| imb3 → next 5 min, mid | +0.002 / +0.004 | −0.003 / −0.003 | +0.005 / +0.009 |
| imb10 → next 1 min, mid | +0.000 / +0.011 | −0.001 / +0.005 | +0.001 / +0.015 |
| imb10 → next 5 min, mid | −0.000 / +0.005 | −0.003 / −0.002 | +0.001 / +0.009 |
| imb10 → next 1 min, tape close-to-close | −0.003 / +0.004 | −0.001 / +0.003 | −0.004 / +0.005 |
| imb10 → next 5 min, tape | −0.002 / +0.002 | −0.003 / −0.002 | −0.001 / +0.005 |

RTH by year, imb10 → next 1 min (Spearman): +0.017 / −0.003 / +0.016 / +0.002. In short: a once-a-minute top-10
imbalance carries essentially no linear information about the next 1–5 minutes (|r| ≤ 0.017), while it is clearly
tied to the minute just finished (r = −0.19). Expect B1/B2 to live or die on conditioning, not on raw imbalance.

## 6. Open risks

1. **Timestamp margin**: the law holds by 0.02–0.98 s depending on the month (§1), RTH and overnight. `phase_check`
   is the gate for every new month and `l2sim` enforces the 1 s execution guard on the months it fails; the same
   guard on every month (`latency_ms=1085`) stays the recommended robustness line for a pick.
2. **Roll direction**: the "day before" in the SPEC is not where the mismatch is (it is roll day, roll day +1 and
   the first evening hours of roll day +2). Handled here by the static block plus the per-minute flag; any other
   component that still assumes "OFB rolls first" will mis-handle roll week. A calendar spread under ~1.5 pts
   would escape the per-minute flag (none since 2022-03; the static block covers the roll days themselves).
3. **Vendor vs desk book**: no overlapping day exists between OFB (→ 2026-07-08) and the desk DOM (2026-09-25 →), so
   OFB-vs-Tradovate equivalence of sizes is unverified; desk depth10 runs ~30% lower than OFB 2024-Q4 (regime or
   vendor, unknown). Thresholds in absolute contracts would not transfer; ratios / z-scores are safer. Live parity
   cannot be proven until an overlapping OFB pull exists.
4. **Desk recorder uptime**: multi-hour outages on 2 of 4 recorded days (§3) — asia / london book strategies would
   have been blind. Needs fixing, or an explicit no-book rule, before any book pick is deployed.
5. **Snapshot instant live**: sample at ≤ M+59.0 s. Research books are 0.02–0.98 s old at the boundary depending on
   the month; a strategy whose edge needs the freshest 59.9 s book is not reproducible.
6. **Holdout book coverage**: by file size alone (not read) the 2026-06-01→07-08 depth file is 14,430 rows of 40
   levels ≈ 10 days, while its hist file is 53,040 rows ≈ 37 days — book features will be missing for most of June
   2026 in stage E; `build_cache(end=..., allow_holdout=True)` handles 40-level rows but that
   path has only been exercised on synthetic files.
7. **Early sample 2017-06 → 2021-09-21**: not built. There is no tape before 2021-09-22, so `in_tape` (and hence
   `book_ok`), the per-minute mismatch flag and `phase_check` (which needs a tick tape) have nothing to work with;
   the stage-E early check needs a bars-based session mask first, and its timestamp law is unverifiable there.
8. `ofb_mismatch`, `in_tape` and `roll_block` use hindsight (data-quality masks, not signals; §3). `depth10_rel20d`
   is not available live until 20 sessions of desk DOM are stored.
9. **Anchors in fast markets**: 50 `book_ok` minutes have the anchor mid > 10 pts from the tape close (§2). They
   are real books of the right contract; B4/B5 must check `ctx.last_price` against the wall before placing.
10. Flow delta is a tick-rule ESTIMATE on the backfill (vault: minute sign agreement 88.6% vs vendor in RTH); desk
    live flow uses quote-side — small-|delta| minutes are noise on both.
11. No tape on 30 holiday sessions, and 2022-06-21 has ticks only from 14:28 ET (tick-archive gap): those rows are
    `book_ok = False` (`in_tape`). The execution sim cannot trade them either.
