# L2 features — one-page reference for family authors (NQ, pilot 2026-10-01-l2)

One row per Globex minute (18:00 → 16:59 ET, contiguous inside a session). A row stamped minute M holds the book
taken 59.0–59.98 s into M and our own tape's flow for [M, M+60 s); it is **usable from M + 60 s**. Evidence, sanity
tables, risks: `DATA.md`. Built by `l2data.py` — a family never imports it, it reads through `ctx` only.

## Reading a feature (`l2sim`)
```python
cols = ["imb10", "bid10_rel15", "bid_px", "bid_wall_dist", "bid_wall_sz", "bid_med_sz", "f_delta"]   # name every column you read
res  = S.run(MyFam, params, features=S.L2Features(cols))                       # in-sample; masked where book_ok is False
null = S.run(MyFam, params, features=score.C2Features(cols, shuffle_cols, seed=k))   # C2: the same call, shuffled features
```
| call (inside `fam_signal` / `on_bar` / `on_time`) | returns |
|---|---|
| `ctx.feat(name)` | the newest usable row: at a decision at T the row stamped T − 60 s (the minute that just ended), never the minute still forming |
| `ctx.feat(name, back=k)` | k rows = k minutes earlier (`k` int ≥ 0; negative raises `LookAheadError`) |
| `ctx.feat_window(name, n)` | numpy copy of the last n usable values, oldest first, NaNs included (`n=None`: every usable row of the slice) |
| `ctx.feat_n()` | number of usable rows so far |

* **Missing is NaN, not None.** `None` (or `default`) only when no row is usable yet. Test `v is None or v != v`; use
  `np.isfinite` + a minimum valid count on windows (`np.nanmean` alone will happily average 3 points).
* The session's slice starts at 18:01 ET the evening before (`lookback_min=360`), so 360 rows already exist at the
  00:00 ET asia open and a trailing window never reaches into the previous session.
* `tf` > 1: `ctx.feat` is still the last ONE-minute row. Aggregate yourself: `ctx.feat_window("f_delta", tf).sum()`.
* Only numeric / bool columns reach `ctx` (`t_utc`, `et_min`, flags do; `date`, `session`, `contract` do not).
  Freshness assert, if you want one: `ctx.feat("t_utc") + 60 == ctx.now_ns // 10**9`.
* Values are float32 (prices float64): never put a threshold on an attainable ratio tie; sizes / ticks are exact.

## Deployable columns (selection allowed)
Units: sz = contracts resting · ticks = 0.25 pt · pts = index points · ct = contracts traded. "RTH" = p5 / p50 / p95
over nyam+mid+pm in-sample; overnight books are roughly half as deep (DATA.md §5).

| column | meaning | unit | RTH p5 / p50 / p95 |
|---|---|---|---|
| `bid_top1` `ask_top1` | size at the best level | sz | 1 / 3 / 7 |
| `bid_top3` `ask_top3` | size summed over the best 3 near-book levels | sz | 7 / 15 / 27 |
| `bid_top10` `ask_top10` | size summed over the best 10 near-book levels | sz | 36 / 76 / 128 |
| `imb3` `imb10` | (ΣB − ΣA)/(ΣB + ΣA) on top-3 / top-10; + = bid heavier (B1, B2, O1, G1) | −1…1 | −0.24 / −0.02 / 0.21 (imb10) |
| `spread_ticks` | best ask − best bid | ticks | 1 / 2 / 3 |
| `bid_wall_sz` `ask_wall_sz` | the LARGEST level within the 10 (tie → nearest the touch) | sz | 6 / 12 / 25 |
| `bid_wall_dist` `ask_wall_dist` | that level's distance from its own best price (0 = the wall is the best) | ticks | 2 / 7 / 9 |
| `bid_med_sz` `ask_med_sz` | median level size over the 10 (B4: wall ⇔ `wall_sz ≥ m × med_sz`) | sz | 3.5 / 7.5 / 12.5 |
| `bid_n` `ask_n` | near levels found (10 on all but 1 usable row) | count | 10 |
| `depth10` | `bid_top10 + ask_top10` | sz | 77 / 157 / 251 |
| `bid10_chg` `ask10_chg` | top-10 depth minus the snapshot one minute earlier (pulled / added) | sz | −30 / 0 / 31 |
| `bid10_rel15` `ask10_rel15` | top-10 depth ÷ median of the previous 15 snapshots − 1 (B3: ≤ −x = that side thinned) | ratio | −0.25 / 0 / 0.42 |
| `depth10_rel20d` | `depth10` ÷ median at the same ET minute over the previous 20 sessions − 1 (B6, G2: < 0 = thin book). The SPEC's B6 thresholds are on the RATIO = 1 + this column: thin ≤ 0.8 (column ≤ −0.2), thick ≥ 1.2 (column ≥ +0.2). Always through `l2sim.depth_regime(v)` → `"thin" | "mid" | "thick" | None` (the Template filter `f_depth` and gate G2 share it) | ratio | −0.39 / 0 / 0.50 |
| `bid_px` `ask_px` | **price anchors**: best bid / ask of the snapshot in tape coordinates. Not features (see Walls) | pts | — |
| `f_o` `f_h` `f_l` `f_c` | our tape's minute OHLC (prices, not features) | pts | — |
| `f_volume` `f_buy_vol` `f_sell_vol` | contracts traded; by inferred aggressor side | ct | 374 / 966 / 2865 |
| `f_delta` | `f_buy_vol − f_sell_vol` (tick-rule estimate) (F1, F2) | ct | −283 / 0 / 276 |
| `f_cum_delta` | running delta since the **18:00 ET Globex open** — not since your session start (F3: rebuild from `f_delta`) | ct | — |
| `f_sweep_buy_vol` `f_sweep_sell_vol` · `f_sweeps_buy` `f_sweeps_sell` | volume · count of aggressor orders that walked ≥ 2 price levels | ct · count | — |
| `f_big_order` `f_big_order_levels` `f_big_order_side` | largest aggressor order of the minute, levels it walked, side +1 buy / −1 sell / 0 unknown (F4: `≥ X` and `levels ≥ 3`) | ct, count, sign | — |
| `f_big_print` `f_big_print_side` | largest single print and its side | ct, sign | — |
| `t_utc` `et_min` | stamp minute start (UTC s) · ET minute-of-day of the decision time (`usable_at`); 570 = 09:30:00 | s · min | — |
| `book_ok` | book columns of this row are valid (they are already NaN where it is False) | bool | 91.6% of R-session rows |

**Research tier — never in a promotable family:** `rt_size_imb`, `rt_qdepl_bid/ask`, `rt_pulled_bid/ask`,
`rt_ice_bid/ask`, `rt_cum_delta` (vendor slots, not reproducible live). Report as "would help if we had it" only.

## NaN rules
* **Book columns and anchors are NaN on the whole row when `book_ok` is False**: roll day −1 / 0 / +1 (39 sessions,
  4.6%), the first 1–2 evening hours of roll day +2, holiday / early-close minutes with no tape, a crossed or
  one-sided book (6 traded minutes). Inside R sessions that is 8.4% of rows, almost all of it whole sessions: a book
  family does not trade those days. NaN means "no signal" — never substitute 0, never forward-fill.
* `*_chg` is NaN on the first row after a missing snapshot; `*_rel15` needs ≥ 8 valid of the previous 15 snapshots
  (the first 8 minutes after the 18:00 open and after any gap); `depth10_rel20d` needs ≥ 10 valid of the previous 20
  sessions at that minute (9.5% NaN in R sessions; all of the first ~10 sessions, 2021-09-22 → early October).
* **Flow columns are independent of `book_ok`** (own tape: valid on roll days too). They are NaN on a minute with no
  print — not 0 — and on sessions without a tape (3.8% of R-session rows).
* A tape minute without prints fires no `on_bar`; the feature row still exists, so `back=k` always means k minutes.

## Walls: B4 `wall_bounce` / B5 `wall_break`
```python
bid, d, sz, med = (ctx.feat(c) for c in ("bid_px", "bid_wall_dist", "bid_wall_sz", "bid_med_sz"))
if bid == bid and sz >= m * med:                       # NaN-safe: every comparison with NaN is False
    wall = bid - d * ctx.tick                          # ask side: ask_px + ask_wall_dist * ctx.tick
    if 0 < ctx.last_price - wall <= 2 * ctx.tick:      # price within 2 ticks, wall not yet traded through
        self._lim(ctx, "long", wall, struct=wall - k * ctx.tick)        # limit AT the wall; stop_mode="struct" puts the stop beyond
```
* Compute the wall price from anchor + distance; no wall-price column exists on purpose: under C2 the distance and
  size come from the donor session and are re-anchored on the receiving session's own `bid_px` / `ask_px`.
  **`shuffle_cols` = the relative book / flow columns you read; never `bid_px`, `ask_px`, `f_o/h/l/c`, `t_utc`,
  `et_min`, flags.**
* Only the largest level per side is stored. B5 "standing ≥ 2 snapshots" = same wall price and `wall_sz ≥ m × med_sz`
  at `back=1` and `back=2`; "gone" = the current row no longer shows it there; "traded through" = `ctx.last_price`
  beyond that price. Then `_arm` / `_mkt`.
* The anchor is the book up to 1 s before the decision. Always compare with `ctx.last_price`; in 0.06% of minutes
  the tape is already more than 5 pts away (fast markets).

## Recipes and rules
* B1 / B2 z-score: `w = ctx.feat_window("imb10", 61); h = w[:-1][np.isfinite(w[:-1])]`; trade only if `w[-1] == w[-1]`
  and `len(h) >= 30` and `h.std() > 0`: `z = (w[-1] - h.mean()) / h.std()`.
* F1 / F2 decile: rank `abs(f_delta)` against `np.abs(ctx.feat_window("f_delta", 240))` (finite values only).
* F3: session cum-delta = `np.nansum(ctx.feat_window("f_delta", minutes_since_session_start))`.
* O1 at 03:00 / 09:30 / 11:05 / 13:30: `ctx.feat("imb10")` in `fam_time` is the book of the minute before the open.
* Thresholds as ratios / z-scores, never in contracts: the desk DOM runs ~30% thinner than this vendor book.
* Timestamp margin is 0.02–0.98 s depending on the month: report every candidate also with
  `S.run(..., latency_ms=1085)` (1 s execution guard). An edge that needs the first second is not deployable.
  The guard delays orders, not `ctx.flatten`: do not flatten on a feature. (A month that FAILS the snapshot-phase
  check gets that guard automatically when the run reads book columns — `res["meta"]["exec_guard"]`; in-sample no
  month failed, RTH or overnight.)
* Filter B6 for a Template family: input `f_depth` = `off` (default) | `thin` | `thick`, checked at every entry on the
  newest usable `depth10_rel20d` row; a missing value blocks the entry. It needs `"depth10_rel20d"` in the columns
  you load, and stays `off` in the Stage A screen.
* Writing a family for the screen: `families/README.md` (registry contract, `FEATURES`, `SCREEN_TFS`, smoke test).
* Holdout rows (≥ 2025-01-01) raise `HoldoutSealed`; leave `allow_holdout` and `mask_bad_book` at their defaults.
