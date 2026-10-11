# Manual lane: the owner's by-hand tests, kept as toolkit pieces

The owner and Claude test an idea by hand, **not through the queue, a card or the Lab** (build days only, 2021-09-22 .. 2025-06-30). Two
families of the 08:30 ET data release were built for it on 2026-10-10 and live in `engine/families/orb830.py`; this folder holds the
settings files and the two report scripts, so the next test is "take it from the toolkit", not a new build.

## The pieces

| piece | what it is |
|---|---|
| family `orb_close` | the opening range (`or_min` 5 / 15 / 30 / 60 minutes) broken on a **close** of the tf bar. `start` 0830 (default) = ONE session 08:30-11:00 (`sessions: ["pre"]`), 0930 = NY sessions (the library's `orb_confirm` is the older 09:30 rule). `entry` market, or limit AT the broken edge for `wait` 0 / 5 / 15 / 30 minutes (0 = to the last 5 minutes of the session; the signal is used up filled or not). `dir` both / long / short (a limit key, in `limits`). `vwap` off / on / first, `vwap_tf` 0 (every print) / 15 (15-minute bars): long only above, short only below the VWAP anchored at 16:00 ET of the prior session, at the signal's close; **build days only, a later date raises** |
| family `open_candle` | the candle that opens at `start` (0830 default = sessions `["pre"]`; 0200 or 0300 ET = the London opens, sessions `["london"]`, window to 08:25), followed at its close, market, stop = its other extreme. Gates, all off at 0: `k` range >= k x ATR(14), `body_r` body >= r x range, `body_pts` body >= points, `vol_m` volume >= m x the median of the same bar over 14 dates |
| exits `"own"` | the family's own table (`orb_close`): stop = the far side of the range, x the six standard targets (none, 0.5R, 0.75R, 1R, 2R, 3R) = 6 cells. Manual lane only (the card / pipeline take `standard`) |
| `specs/*.json` | the eight settings files that produced the tables of 2026-10-10 (below); copy one, change the numbers |
| `heatmap.py` | stop x target heat map for every variant of one or more stores, one colour scale, metric picker (Net $, Average trade $, Win %) |
| `by_year.py` | the house metric set per year, then combined, for every cell of a store; `--risk 750` sizes every trade to about $750 of risk in micros |
| `by_year.py --prop` | the same page plus each cell's prop sim (the pipeline's account and days, plain row, stress row); `--cells` keeps your order |
| `sizing_sweep.py` | the prop sim of each cell at EVERY whole micro (1 .. the account's maximum): eval odds by day, bust, payout, stress; a grid by dollars of risk a trade |

Only `engine/families/orb830.py`, `run_idea.py` and `blueprint/runner.py` (the `own` allow-list) are new or changed: no hashed engine file moved,
so no earlier store or lock is marked "written by other code".

## Run one (from the toolkit checkout, with the research Python)

```
S=<a scratch folder>; PY=<repo>/.venv-research/bin/python; cd research/edge-library
mkdir -p $S/out $S/ideas $S/tester
cp -R <an earlier scratch>/c1-NQ-tf5 $S/out/      # the build's random-entry pool of that bar size (or copy runs_bp/c1-NQ-tf5); without it the build
                                                  # recomputes the pool on one worker for an hour. "REFUSED: control pool ..." at the end is harmless.
$PY bp.py build my_idea --spec-file=manual_lane/specs/orb830_range_stop.json --reason="why this run, in words" \
    --out=$S/out --root=$S/ideas --tester=$S/tester --ledger=$S/out/ledger.csv --workers=8
$PY manual_lane/heatmap.py $S/heat.html $S/out/my_idea-NQ-tf1 --title "NQ 08:30 range, stop at the range"
$PY manual_lane/by_year.py $S/out/my_idea-NQ-tf1 $S/by_year.html --risk 750
```

A settings file is `run_idea`'s format: `name`, `reason`, `family`, `markets`, `bar_sizes`, `sessions`, `params` (the settings that vary, each a list: the
variants), `fixed`, `filters`, `exits` (`standard` or `own`), `limits`. 12 cells = 2 entries x 6 targets; 48 cells x 3 variants = 144.

## What was tested (build days; 1 contract; costs on) and where the tables are

| settings file | question | stored table (2026-10-10 scratch) | rows |
|---|---|---|---|
| `orb830_range_stop` | 08:30 5-min range, first 1-minute close beyond it, market vs limit at the edge, stop at the other side | orb830_range_stop-NQ-tf1 | 10,980 |
| `orb830_range_stop_vwap_first_15m` | + the first break decides, 15-minute 16:00 VWAP | orb830_vwap16_15m_first-NQ-tf1 | 7,344 |
| `orb830_range_stop_vwap_on_tick` | + a break against the tick VWAP is skipped, the next may trade | orb830_vwap16-NQ-tf1 (corrected one) | 10,452 |
| `open_candle_none` | 08:30 5-min candle, its own direction, no filter | fb830_none_tf5-NQ-tf5 | 44,928 |
| `open_candle_a / b / d / e` | the four displacement filters: range vs ATR, body share, volume vs median, body points | fb830_{a,b,d,e}_tf5-NQ-tf5 | 82,128 / 35,904 / 36,096 / 31,200 |
| `open_candle_london_0200_tf5_tk` / `_tf1_tk` (+ `_tf5_ts0825_tk`, `_tf5_ts0925_tk`: time stop 76 / 88 five-minute bars) | the 02:00 ET candle followed at its close, body gate 0 / 0.5 / 0.7 / 0.85 (2026-10-11) | open_candle_london_0200_* | 78,864 each (tf5), 80,208 (tf1) |
| `open_candle_london_0300_tk` | the 03:00 ET candle (London cash open), 1- and 5-minute, body gate 0 / 0.5 / 0.7 / 0.85 | open_candle_london_0300_tk-NQ-tf1 / -tf5 | 80k / 77k |

London (2026-10-11): 02:00 ET does not follow (13 of 48 cells profitable with no gate, body 0.5 / 0.7 lose); 03:00 ET does (5-minute, body 0.7: 42 of 48
cells profitable, 30-pt stop 3R +$27.5k, 189 trades). A time stop (`exit_bars` is a limit key, one spec each) is not a variant.

All eight were rebuilt from the toolkit families and **match the stored tables element for element** (cells, entries, nets, exits).

Findings (vault: `30-Projects/Onyx-Trading/orb830-manual-lane-toolkit.md` and the finding `2026-10-10-nq-0830-orb-vwap-and-candle-filters`): the
16:00 VWAP side rule made the range break worse (limit 0.75R at $750 risk: +$15,178 without it, -$2,700 with the 15-minute VWAP first-break rule,
-$40,714 with the tick VWAP); in all three tables the longs make money and the shorts lose; the 08:30 candle works as a plain follow (34 of 48 cells
profitable, 5-minute); of the four filters only **body share (B) at 70 %** lifts it (48 of 48 cells, avg +$97 a trade, no-target +$230), volume
(D) and big body in points (E) hurt. Build days only: nothing here has seen the test days, and a heat map that is green on the build days is
a coin flip next year (finding 2026-10-05): it needs the blueprint's one out-of-sample read before it is more than a lead.

## Rules the families follow (so a result can be trusted)

* Signals read bars that have closed; the VWAP at a boundary holds only prints before it (15-minute: only completed bars); the volume gate
  uses the 14 dates before.
* A roll day (the prior and the trade date are different contracts) has no VWAP and does not trade under `vwap` on / first.
* The structure stop distance is read at the signal's close and applied to the fill (one tick of slippage on a sell), as every `struct` stop.
* `engine/tests/test_orb830.py` pins each rule on synthetic days with exact numbers, restates the rule on seeded random days at every bar
  size, and checks the invariants on real build days.
