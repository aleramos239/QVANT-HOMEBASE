# NQ prop-portfolio pilot: build spec (shared by every agent)

Root: `R = ~/ramos-quant-homebase/research/prop-portfolio/2026-09-29/`. Repo: `~/ramos-quant-homebase`
(python: `~/ramos-quant-homebase/.venv/bin/python`, stdlib and whatever the venv has; check before
importing numpy). **Never touch the live desk** (port 8850) or anything under `homebase/` except for
reading. **Never commit.** The desk is ARMED on real accounts. This research only uses the Strategy
Tester (chart service, `http://127.0.0.1:8852/api/tester/...`) and local files.

## Goal (context only)
Find NQ strategies, sizing and daily rules, and combine them into a portfolio that maximises
P(pass the eval within 5 trading days) under two rule sets:
`lucid-flex-50k@2026-09-27` and `apex-legacy-50k@2026-09-27b` (Apex is UNCONFIRMED; flag it
everywhere). Rule files: `homebase/backtest/propsim/rules/*.json`. The sim engine is
`homebase/backtest/propsim/propsim.py` (`run_eval`, `run_funded`, `_floor`) plus
`homebase/backtest/propsim/__init__.py` (the `limit_trades` helper and the `evaluate` wrapper).
Research window 2021-01-01 → 2024-12-31. Holdout 2025-01-01 → latest: DO NOT run or read it
unless the orchestrator explicitly says "holdout".

## Tester facts (read `homebase/backtest/engine.py`, `runner.py`, `strategies/base.py`)
* Drafts live in `~/.homebase/strategies/<name>.py`, tester id `draft_<name>`. Stdlib only, one
  Strategy subclass, class attributes literal, `inputs()` is exactly `return [Input(...), ...]`
  with literal args. `Input(key,label,type,default,min,max,step,choices)`; types float|int|bool|choice.
  The draft template is shown by the MCP `read_strategy` tool (engine rules: events run BEFORE the
  first print at/after their time; bar closes deliver `bar.o/h/l/c/v/start_ns/end_ns`; orders:
  `ctx.market/stop_entry/limit_entry(side, ..., sl=, tp=, tp_rr=, ref=)`, `ctx.oco`, `ctx.cancel`,
  `ctx.flatten`, `ctx.move_brackets_to_fill=True`, `ctx.flat`, `ctx.last_price`, `ctx.daily`
  (prior daily bars when `needs_daily()` returns True), `ctx.date`, `ctx.now_ns`).
* Session windows are CALENDAR-DAY ET windows (`et_ns(date, "HH:MM")`); a window cannot start
  the previous evening, so "Asia" is only reachable as 00:00–03:00 ET. State that limitation.
* Run bundles: `homebase/.state/tester/runs/<run_id>/{run.json,trades.json,equity.json,propsim.json}`;
  heat-maps: `homebase/.state/tester/grids/<grid_id>/{grid.json,cells/...}`; walk-forwards:
  `homebase/.state/tester/walkforward/`. Trades carry `date, side, qty, entry_price, exit_price,
  exit_reason, gross, commission, net, mae_usd, mfe_usd, mae_pts, entry_ms, exit_ms` (per 1 NQ).
* API: the MCP bridge's HTTP client is `homebase/claude_mcp/client.py`; the request bodies it
  sends are in `homebase/claude_mcp/tools.py` (`t_backtest`, `t_heatmap`, `t_walkforward`,
  `t_get_run`, `t_cancel`, ...). Reuse that client and copy those bodies exactly.
* Machine cap: 2 backtests at once (a heat-map's cells share it). Nothing may START 09:20–09:35 ET
  on weekdays (refusal). Never retry a refusal in a tight loop (≥ 60 s back-off; inside the window,
  sleep until 09:36 ET).

## Sessions (ET)  — `sess` input
| key | window | flatten at |
|---|---|---|
| asia | 00:00–03:00 | 03:00 |
| london | 03:00–08:25 | 08:25 |
| nyam | 09:30–11:00 | 11:00 |
| mid | 11:00–13:30 | 13:30 |
| pm | 13:30–15:58 | 15:58 |
`all` = trade every session independently (state resets at each session start, flat at each
session end; the offline layer splits trades by session using `entry_ms`). No new entries in the
last 5 minutes of a session. Class `session_window = ("00:00", "16:10")`, `bar_minutes = 1`,
`session_independent = True`, `needs_daily()` True.

## The shared template (`R/template.py` + `R/families/<fam>.py` → `R/gen_drafts.py`)
`gen_drafts.py` splices each family's trigger code into the one template and writes
`~/.homebase/strategies/pp_<fam>.py` (tester id `draft_pp_<fam>`). It then confirms through
`GET /api/tester/strategies` that each draft loads with no error.

Common inputs (every family):
* `tf` choice "1","5","15","30": the signal timeframe. 1-minute bars come from the engine; the
  template aggregates them into tf bars aligned to ET clock multiples of tf. Signals are evaluated
  ONLY at tf-bar close, using completed bars only.
* `sess` choice all|asia|london|nyam|mid|pm (default all).
* `dir` choice both|long|short (default both).
* `stop_mode` choice atr|pts|struct (default atr). `stop_val` float (ATR multiple, or points).
  ATR = Wilder ATR(14) on tf bars. `struct` = the family's structural level (defined per family;
  fallback to atr when the family has none), floored at 0.25 × ATR.
* `tgt_r` float (target = tgt_r × stop distance; 0 = no target), default 2.0.
* `trail_atr` float (0 = off): close-based trailing exit at market when a tf-bar close retraces
  more than trail_atr × ATR from the best close since entry.
* `exit_bars` int (0 = off): exit at market after N tf bars in the trade.
* `max_tr` int: max entries per session (default 3). One position at a time.
* up to 2 family params and at most 2 filters (1 trigger + ≤2 filters total).
Rolling indicators (EMA, ATR, RSI, BB, KC, ...) run over every tf bar since 00:00 of the day (they
reset each day, so warm-up is short for 30m; state this). Session objects (VWAP, opening range,
counters) reset at each session start. Orders: market entries use `ref=` the signal close and
`move_brackets_to_fill=True`; breakout families may use `stop_entry` at the level. Qty is always
the run's qty (never pass qty). Plot nothing (keeps bundles small).
Daily money rules (contracts, daily profit lock, daily loss stop, scale after win/loss, stop at
eval target) are NOT in the draft: they are applied exactly by the offline layer on the trade
sequence (one tester run → many rule sets). Only `max_tr` and the signal logic live in the draft.

## Families (clean base; the default params ARE the screen)
Filters are optional inputs default OFF unless noted.
1. `orb`: opening range of the first `or_min` (5/15/30, default 15) minutes of the session;
   OCO stop entries at OR high+1 tick / low−1 tick placed at OR end; struct stop = other side.
2. `straddle`: at session start + `delay_min` (default 0) bracket last price ± `off_atr`×ATR
   (default 0.5) with OCO stop entries. Param `news_only` bool (default False): on news days
   (CPI/NFP/FOMC list) in london the bracket is set at 08:29:30 around the last price (pre-news).
3. `donchian`: close > highest high of prior `n` tf bars (default 20) → long; mirror short.
   struct stop = opposite channel side.
4. `squeeze`: `sq_type` choice bbkc|nr7|inside (default bbkc). bbkc: BB(20,2) inside KC(20,1.5)
   for ≥ 3 bars then release; direction = close vs BB mid. nr7/inside: stop entries at the
   narrow/inside bar's high/low (OCO); struct stop = other side.
5. `ema_ribbon`: EMA 8/21/55 become fully aligned (8>21>55 long, reverse short) on this bar.
6. `tema_slope`: TEMA(`n`, default 20) slope changes sign (turn up → long, down → short).
7. `ema_pullback`: EMA(50) slope > 0 and a bar's low touches EMA(20) then closes back above
   it → long (mirror short). struct stop = pullback bar extreme.
8. `supertrend`: Supertrend(10, 3) flip → enter in the new direction. struct stop = ST line.
9. `rsi2`: RSI(2) < 10 → long, > 90 → short (mean reversion); filter `trend_f` bool (default
   False) = only with EMA(200-on-tf... use EMA(50)) slope.
10. `vwap_band`: session VWAP ± `band` σ (default 2.0; σ = volume-weighted stdev of typical
    price since session start): bar closes back inside after closing outside → fade.
11. `vwap_z`: z = (close − VWAP)/σ; |z| ≥ `zth` (default 2.0) → immediate fade at close.
12. `vwap_flip`: close crosses session VWAP and the next `hold` bars (default 2) close on the new
    side → enter that way. `anchor` choice session|rth (rth = VWAP anchored at 09:30 for NY
    sessions, 03:00 for London) — this is the anchored-VWAP reclaim variant.
13. `pinbar`: wick ≥ 2/3 of bar range, bar within 0.25×ATR of a key level (prior-day H/L/C,
    overnight 00:00–09:30 H/L for NY sessions, session VWAP) → reversal. struct stop = wick end.
14. `sweep_rev`: price trades beyond prior-day high/low or the overnight (00:00→session start)
    high/low and a tf bar closes back inside → reversal. struct stop = sweep extreme.
15. `ib`: initial balance 09:30–10:30 (NY only; other sessions: no trades). `mode` choice
    break|fade (default break). break = stop entries at IB high/low after 10:30; fade = first
    close back inside after an IB break → fade to IB mid.
16. `gap`: RTH gap = 09:30 open vs prior-day close (ctx.daily), |gap| ≥ `min_gap_atr`×daily
    ATR(14) (default 0.1). `mode` choice fill|go. NY AM only (entry at first tf close ≥ 09:30).
17. `tod_drift`: enter `dir` (default long) at session start + `off_min` minutes (default 0),
    exit after `exit_bars` (default 6) tf bars; max 1 per session. Tests pure time-of-day drift.
18. `random`: CONTROL. At each tf-bar close while flat and entries < max_tr, enter with
    probability `p_entry` (default 0.05), side random; RNG = `random.Random(f"{seed}|{ctx.date}|{sess}")`
    (deterministic). Same stops/targets/exits as the others. Param `seed` int.
Invented (hypothesis stated in the family's docstring):
19. `lon_break`: NY AM break of the London (03:00–08:25) high/low by stop entry, OCO — the London
    range is the overnight inventory; the NY open resolves it.
20. `first_bar_mom`: first tf bar of the session with range ≥ `k`×ATR (default 1.5) → follow its
    direction at its close (momentum ignition).
21. `mid_fade`: in `mid`, fade the NY AM move (09:30–11:00 net change) when |move| ≥ 1×daily ATR
    ×0.3 — lunch mean reversion.

News days: build `R/news_days.csv` (date, tags among CPI, NFP, FOMC) from
`~/ONYX TRADING/research/data/ff_usd_red_raw.txt` (FF red USD events: "CPI m/m"/"Core CPI",
"Non-Farm Employment Change", "FOMC Statement"/"Federal Funds Rate"). Embed the dates as a
literal set in each draft that needs them (drafts cannot read files).

## Costs & sizing conventions (offline layer)
Tester runs at qty 1 NQ, commission $4.00 RT/NQ, slippage 1 tick/side (market & stop fills).
Resizing to n micros (MNQ = NQ/10): pnl = n × gross/10 − cost(n), where cost(n) =
floor(n/10)×$4.00 + (n mod 10)×$1.00 (MNQ $0.50/side, Lucid sheet; the mini leg of NQ at
$4.00 RT). MAE scales the same way. Cost rule: RT cost (commission + 2 ticks slippage) < 3% of
the stop's $ risk — evaluated per config at its instrument mix. Contract caps: Lucid 40 micros
(funded scaling 20 → 30 at +$1,000 → 40 at +$2,000); Apex 100 micros (10 NQ).
Fees (ASSUMPTIONS, in `R/fees.json`, change freely): Lucid Flex 50K eval $100, no activation;
Apex Legacy 50K eval $35 (promo; list $167), PA activation $85. Flag both as assumptions.

## Driver / job queue (`R/hb.py`) — the ONLY thing that submits tester jobs
* `hb.py submit <jobs.jsonl>` appends to `R/queue.jsonl`; `hb.py run` (a long-lived loop, run with
  nohup, logs to `R/hb.log`) drains the queue: ≤ 2 of OUR jobs running at once, submit with
  wait 0 through the bridge's HTTP client, poll by id every 15–30 s, respect the 09:20–09:35 ET
  weekday window (don't submit from 09:18; resume 09:36) and refusals (back off ≥ 60 s).
* Job line: `{"key": unique, "kind": "run"|"grid"|"walkforward", "stage": "calib|screen|sizing|
  wf|ctrl|holdout", "strategy": ..., "inputs": {...}, "range": {...}, "costs": {...},
  "axes": [...], "max_cells": n, "prop_rules": "lucid-flex-50k@2026-09-27", ...}`.
* Idempotent: `R/jobs.jsonl` records key → id, status, submitted/finished times, elapsed_s. A key
  already done is never resubmitted (safe to restart after a crash; on restart it re-attaches to
  jobs still running by id).
* Caps (hard, refuse to submit past them, log it): screening runs (stage screen|ctrl) ≤ 400,
  heat-map cells ≤ 3000 (sum of max_cells actually expanded), walk-forwards ≤ 15.
* On each finished job append to `R/ledger.csv` (one row per run or per heat-map cell):
  `stage,key,kind,strategy,params_json,run_id,grid_id,cell,trades,net,sharpe,wr,pf,maxdd,
  pe_lucid_pass,pe_lucid_bust,pe_lucid_days,elapsed_s,finished_utc` (metrics from the bundle's
  run.json report / propsim.json; exact field names discovered from real bundles).
* Keep `R/progress.md`'s "## Queue status" block current (auto-written: counts per stage,
  caps used, running ids, last error). Other sections of progress.md are the orchestrator's.
* `hb.py status` prints a ≤ 15-line summary. `hb.py wait <stage>` blocks until that stage's
  queued jobs are all finished.

## Offline evaluator (`R/evalcore.py`, CLI `R/evaluate.py`) — exact P(pass ≤ 5d)
Input: one or more "members" = (trade source: run_id or grid_id+cell, session filter, micros,
daily rules). Loads trades.json from disk (never through the chat).
1. Per-trade resize with the cost model above; sort by entry time; tag session and news day.
2. Daily rules, walked trade by trade within a day (portfolio: all members' trades merged in
   entry-time order): `max_day_tr`; `day_stop` Y (if day P&L + this trade's worst point
   (−MAE scaled − costs) ≤ −Y → trade closes at −Y − day P&L − 1 tick×contracts, stop for the
   day); `day_lock` X (after a trade CLOSES with day P&L ≥ X, stop for the day); `after_loss`
   / `after_win` size multipliers for the next trade (reset daily; micros rounded down, ≥ 1);
   `target_stop` (in eval simulation only: stop for the day once the account has reached the
   pass condition, i.e. profit ≥ target and, for Lucid, the consistency check would pass).
   Overlapping trades (portfolio): the intraday worst point is realised P&L + the sum of the
   concurrent trades' worst points (conservative); count opposite-side overlaps as conflicts
   and the max concurrent micros vs the firm cap.
3. Eval race per firm (rules from the rule file, identical semantics to `propsim.run_eval`:
   EOD floor = `_floor(peak)`, locks at lock_at, consistency and min days for Lucid, none for
   Apex). Two breach models: `eod` = EXACTLY Homebase (bust iff EOD profit ≤ floor) — PRIMARY,
   matches the rule files (Lucid help-centre: intraday recovery OK); `intraday` = also bust if
   the day's worst intraday point ≤ the floor in force that day — SENSITIVITY column.
   Unit test: for any daily series, `eod` outcomes must equal `propsim.run_eval` exactly.
4. Rolling starts: an attempt starts on EVERY trading session in the window; it runs ≤ 5 trading
   sessions (weekdays with a tape; no-trade weekdays count as a day with 0 P&L). Outcome: pass
   (day), bust (day), neither. Report P(pass≤5d), P(bust≤5d), P(neither), median days to pass,
   P(pass by day k) k=1..5, P(bust by day k).
5. CI: moving-block bootstrap over start days (block = 20 sessions, 2,000 resamples) → 95% CI
   for P(pass≤5d). Also an i.i.d. day-bootstrap Monte Carlo (≤ 10,000 paths of 5 days, trade
   days sampled as whole days with their intraday worst) as a second estimate.
6. Eventual pass (Homebase-style, horizon 250 weekdays, i.i.d.) by calling
   `homebase.backtest.propsim.propsim.run` on the resized daily series — the "prop_eval" number.
7. Funded mode per firm: rolling starts with horizon 60 sessions from a flat funded account:
   P(bust before first payout), P(first payout), median days to first payout, E[first cheque]
   (propsim `run_funded` semantics; Lucid scaling caps sizing at 20/30/40 micros by profit;
   Apex payout terms are Lucid placeholders — flag).
8. Economics: expected evals per funded = 1 / P(pass≤5d) (5-day policy: abandon/reset after 5
   days) and eventual; cost per funded = fee × evals (+ activation).
9. Output: one JSON per evaluated config in `R/out/` + a compact one-line summary on stdout.
   Must evaluate one config over 2021–2024 in ≤ 2 s (vectorise the bootstrap; numpy if in venv).
Search helper `R/search_rules.py`: given member trades, grid over micros × day_lock × day_stop ×
max_day_tr × after_loss × target_stop per firm, write `R/out/search_<tag>.csv`, print the top 10
and a stability score (median P of each cell's neighbours).

## Desk-window rule for OFFLINE compute (added 2026-09-30)
The live desk trades from this Mac at 09:30 ET. Any offline multiprocessing job (searches, Monte
Carlo) must not run 09:18–09:36 ET on weekdays: check the ET clock before starting a batch and
between batches; if inside or about to enter the window, sleep until 09:36. Keep ≤ 8 workers.

## Firms (updated 2026-09-30, user request): FOUR rule sets, score every config under all
| id | rule file | notes |
|---|---|---|
| lucid (Flex) | lucid-flex-50k@2026-09-27 | 50% consistency, 2-day min, 40 micros |
| lucidpro | lucid-pro-50k@2026-09-27b | no consistency, 1-day pass, $1,200 SOFT daily limit (stops the day), 40 micros |
| lucidpro_nodll | lucid-pro-50k-no-dll@2026-09-27b | same without the daily limit (removable option), 40 micros |
| apex | apex-legacy-50k@2026-09-27b | UNCONFIRMED; no consistency, 1-day pass, 100 micros |
LucidPro rules grid: micros {10,20,30,40} × day_lock {none,1000,2000} × day_take {none,1500,2000,3000} ×
day_stop {none,1000,2000} (the rule-file DLL applies automatically) × max_day_tr {1,none} × target_take {off,on}.
Ranking (user priority): P(pass ≤ k days) for k = 1,2,3,5 first; bust %; edge lift = warning label.
LucidPro fees (user 2026-09-30): $115 with the daily limit, $140 without; activation assumed $0.

## Multi-pilot (added 2026-09-30): ES pilot in ../2026-09-30-es (see its SPEC.md)
`pilot.py` selects root / data dir (`PP_PILOT=es` or `--pilot es`; NQ default, nothing changes). Code stays here; per-pilot data (queue, jobs,
ledger, out/, bundles_cache/, progress.md) lives in the pilot dir. hb.py: ONE daemon, job field `"pilot"` ("nq" default | "es"), queues/ledgers/
blocks per pilot, caps PER pilot, NQ jobs taken before ES jobs, <= 2 of our jobs at once across both.
