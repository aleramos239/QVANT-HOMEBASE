# Tape, TradingView-match studies, order-flow app indicators, Pine runtime (2026-10-21)

Owner (2026-10-21): "lets do 4, also match all the indicators, also from the other apps like Order-flow apps: Bookmap, ATAS,
Jigsaw and similar; TradingView itself: running Pine scripts inside Homebase, plus exact indicator matching against
TradingView's own export".

Branch `feat/indicator-apps` (light worktree `.worktrees/indicator-apps`, no `research/`). Nothing lands on `main` until the
owner says so (main ships to the VPS by itself).

The six read-only reports this plan rests on (scratchpad, read them for file:line detail):
`/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/b578f2fb-54b7-4eed-850c-d32bd81bb2ac/scratchpad/reports/`
`studies.md` (how a study is declared, computed, streamed, drawn; what must not change), `orderflow.md` (tick/L2 path, DOM,
panels; the tape build guide), `inventory.md` (every Homebase study vs every TradingView built-in, with the Pine formula),
`ofapps.md` (clean-room specs of Bookmap/ATAS/Jigsaw/Sierra/Exocharts/Quantower/MotiveWave/Deepcharts, with worked
examples usable as tests), `pine.md` (PineTS verdict, hosting design), `oracle.md` (TradingView export recipe + parity harness).

## Laws that bind every piece

1. **No existing wire key changes its output.** The strategy engine mirrors chart definitions and parity tests hold both
   sides equal (studies.md §5). New behaviour = new key, new name, or a new optional token/param whose default reproduces
   today's key byte for byte (`clampParams` re-keys every saved layout at load).
2. **`Bar` fields, `BarBuilder`, `resample`, `BIG_MIN`, `SWEEP_TICKS`, `SW_CAP`, `BUB_*`, `Pressure.*` stay byte-stable.**
   A new Bar field gets a class default (`None`) so v2 pickles load; `CACHE_VERSION` is NOT bumped in this round.
3. **No TradingView data, no third-party Pine, no PineTS in the repo** (the GitHub repo is public; TV data is
   display-licensed; PineTS is AGPL; LuxAlgo scripts are CC BY-NC-SA). They live under `~/.homebase/`.
4. **Hot paths:** `preview()` runs for every study 4x/s; `add_study` on an existing stream runs on the event loop over
   every loaded bar. New studies are O(window) per step. New per-bar arrays are capped and ride a flag.
5. **Tests first.** Every new pure function has a test; doc worked examples become fixtures. Python:
   `.venv/bin/python -m pytest tests/<file>` from the worktree (venv at `../../.venv`). JS: `node --test tests/js/<file>`.
6. **Karpathy rules:** smallest change that fully works, no speculative options, match the surrounding style, touch only
   owned files, remove only your own orphans.
7. **No `?v=` bumps by agents** (one final pass). No git commits by agents (one commit per wave).
8. The `pre_tool_safety` hook blocks shell lines containing `rm -rf` and "live"+"tradovate" together.

## Naming decisions (fixed)

- TradingView-match studies live in the **`tv:` namespace**: key `tv:<name>[:args][@sec]`, e.g. `tv:rsi:14`, `tv:ema:20:close`,
  `tv:vwap:session`. Server module `homebase/charts/studies_tv.py` (core) + `studies_tv2.py` (long tail), dispatched from
  `studies.make()` the way `FLOW_NAMES` is; `"tv"` goes in `HTF_OK` (its studies read only OHLCV/buy/sell/n). Catalog ids
  `tv_<name>`, group "TradingView", TA_DEFS entries whose `key(p)` returns exactly the Python key.
- Reconstructed aggressor order ("tape order"): consecutive prints with the **same `ts_ms` and the same side** (the CME
  rule, identical to `bars.py:137-150`). Output `[ts_ms, vwap, lo_px, hi_px, size, side, n_prints]`.
- New Bar fields (all default `None`): `ag` (tape orders ≥ `AG_MIN=10`, capped `AG_CAP=60`, under the `flow` flag),
  `fpn` (`{tick_idx: [sell_prints, buy_prints]}`, under the `fp` flag as `fpn: [[price, s, b]]`), and four numbers always
  on the wire: `dmax`, `dmin` (running-delta extremes inside the bar), `dhi`, `dlo` (running delta when the bar last made
  its high / low).
- Time & Sales wire: op `{"op":"tape","root":R|null}`; message `{"type":"tape","root","s","i0","rows":[[ts_ms,price,size,side,id],...],"reset"?:true}`.
- Pine: PineTS 0.12.1 in a Web Worker per instance; runtime at `~/.homebase/pine/runtime/node_modules/pinets/dist/pinets.min.browser.js`
  served by `GET /api/pine/runtime.js` (sha256 pinned); scripts in `~/.homebase/pine/scripts/*.pine`; catalog id `pine`
  (page-only, no server key).
- TradingView parity data under `~/.homebase/tvparity/` (`HOMEBASE_TVPARITY_DIR` override), harness `tools/tvparity.py`.

## Wave 1 (parallel, strict file ownership)

| Agent | Owns (nobody else touches these in wave 1) | Builds |
|---|---|---|
| A1 tape-server | `homebase/charts/tapelive.py` (new), `homebase/charts/server.py`, `tests/test_charts_tapelive.py` | `TapeLive` (orderflow.md §7.1): per-root Fanout, `flush()` from the pump after `hub.drain()`, `tape` op, `drop_conn` in the ws finally; reset hello when `hub.today[root]` is a new list or >4000 rows pending |
| A2 tape-client | `homebase/static/charts/tape.js`, `tapeui.js`, `tape.css` (new), `app.js`, `panellayout.js`, `panelshell.js`, `charts.html`, `backtest.html`, `tests/js/tape.test.mjs`, `tests/js/panellayout.test.mjs`, `tests/js/panelshell.test.mjs` | pure `HBTape.apply/orders/filter`; `HBTapeUI` dockable panel (Raw/Orders switch, min size, side, newest first, ≤10 patches/s, ET ms time); `page.send`; ws route `tape`; panel id `tape` + toolbar button `#tbTape`; CSS in tape.css linked from charts.html |
| A3 dom-columns | `homebase/static/charts/dom.js`, `domui.js`, `charts.css`, `tests/js/dom.test.mjs` | orderflow.md §7.2: pure `fpSplit`, `knownRange`, `pullStack` (Sierra −10 then +5 → −5 fixture), Sierra "Recent Bid/Ask" timeout rule (2500 ms fixtures → 3 and → 1), columns P/S bid · Sold · Bid · Price · Ask · Bought · P/S ask · Vol, Reset button, column choice in localStorage (try/catch), grid follows visible columns |
| A4 bars-fields | `homebase/charts/bars.py`, `homebase/charts/history.py`, `tests/test_charts_bars_flow.py` (new) | the new Bar fields above; `_g` gains pv at index 6 (indices 0-5 untouched); `wire()`; `copy/merge/finish_merge`; `resample()` equality test; old-pickle load test; byte-stability test of `sw/bub/big/ords/fp` on a fixture; a `recount`-style backfill is NOT added (document it) |
| A5a tv-core | `homebase/charts/studies_tv.py` (new), `studies.py`, `hub.py`, `tests/test_charts_studies_tv.py` | namespace dispatch + warm/prime hooks + the P1 set in Pine's own math (inventory.md §3/§4): `ema` (SMA seed, na before len), `sma`, `rma`, `wma`, `rsi` (down=0→100, up=0→0), `macd`, `stoch:14:1:3`, `adx:14:14` (ta.tr na at bar 0, fixnan), `atr`, `bb`, `keltner:20:2:10` (+`range`/`tr` option), `donchian`, `supertrend:10:3` (TV start dir, flip vs current band, dir 1=down/−1=up as TV), `tema`, `mfi` (na on 0), `vwap:session|week|month|quarter|year` (hlc3·v, bands = vol-weighted sd of hlc3, 1/2/3), `cvd` (TV lower-tf rule on the chart's own bars: close>open up, <open down, equal → previous bar's rule, inherit; candles {o,h,l,c}), `vdelta`, `updown`, `rvol:14` (mean, cumulative-since-session-open, `regular` option), `adr:14`, `pivots:<type>` (Traditional/Fibonacci/Woodie/Classic/DM/Camarilla from the prior session's H/L/last-trade C; `settlement` noted as TODO), `pivothl:10:10`, `twap`. `make_tv` also merges `studies_tv2.PARAMS` (try/except import). Tests restate each Pine formula independently and compare at every bar; a bad-key test; warm/prime asserts |
| A5b tv-tail | `homebase/charts/studies_tv2.py` (new), `tests/test_charts_studies_tv2.py` | the "missing" TV built-ins (inventory.md §3 P2/P3 that are computable from OHLCV): `hma`, `dema`, `smma`, `alma`, `lsma`, `mcginley`, `kama`, `envelope`, `stochrsi`, `bbpct`, `bbw`, `bbtrend`, `sar`, `chandelier`, `vstop`, `chandekroll`, `ichimoku`, `alligator`, `fractals`, `cci`, `wpr`, `mom`, `roc`, `ao`, `bop`, `bbp`, `cmo`, `connors`, `fisher`, `ppo`, `pvo`, `trix`, `tsi`, `smi`, `smio`, `smindex`, `uo`, `rvgi`, `rvi`, `coppock`, `kst`, `dpo`, `massindex`, `ulcer`, `aroon`, `aroonosc`, `vortex`, `chop`, `rci`, `hv`, `obv`, `pvt`, `adl`, `cmf`, `chaikin`, `klinger`, `efi`, `eom`, `nvi`, `pvi`, `netvol`, `zigzag:5:10`, `median`, `cog`, `corr` (vs bar_index), `linreg` channel. Same test discipline (independent restatement of each Pine formula, defaults = TV defaults) |
| A6 tvparity | `tools/tvparity.py` (new), `tests/test_tvparity.py`, `tools/pine/hb_parity_p1.pine … p4.pine`, `.gitignore`, `docs/tvparity-export-recipe.md` | oracle.md §3-§6: loader (unix s/ms, ISO, BOM, NaN, duplicate titles), `tv_bars`, `hb_bars`, `run`, `verdict` (identical / warm-up only / differs / no-tv), OHLCV pass with holiday/roll/boundary tags, report writer, CLI `python -m tools.tvparity run`, refuse ROOT inside repo_root(); probes P1-P4 validated with `~/.claude/skills/pine-validate`; the owner's click-by-click recipe (3.0 calibration, 3.1 setup with the 17-indicator layout A, 3.2 exports) |
| A7 pine-runtime | `~/.homebase/pine/runtime` (npm, outside repo), `homebase/charts/pineapi.py` (new; `routes()` returning aiohttp routes, NOT registered yet), `homebase/static/charts/pineworker.js` (new), `tools/pine/parity.mjs` (new), `tests/test_charts_pineapi.py`, `tests/js/pineworker.test.mjs` | pine.md §4-§6: runtime install (`npm install --ignore-scripts --save-exact pinets@0.12.1`, sha256 pinned in pineapi), `/api/pine/runtime.js` (404 when missing), `/api/pine/scripts` (name, version, kind, title), `/api/pine/scripts/{name}` (name regex + resolve-inside check), the Worker (provider from Homebase bars/fp, syminfo per root with `America/Chicago` + `1700-1600`, same-symbol HTF `request.security` aggregated from chart bars, run + stream, results as `{plots:{title:[{time,value,color}]}, shapes, boxes, lines, labels, tables, warnings}`), `parity.mjs <script> <tv.csv>` with `--bars homebase` mode; Node test loads the UMD in a vm like the probe |

A1 and A7 both need `server.py`: A7 does NOT edit it (its `routes()` is registered in wave 2).

## Wave 2 (after wave 1 is green and committed)

| Agent | Owns | Builds |
|---|---|---|
| B1 client-wiring (sequential chain: B1a then B1b) | `catalog.js`, `cell.js`, `indicator-settings-dialog.js`, `indstatus.js`, `guide-ta.js`, `guide-flow.js`, `guide-tv.js` (new), `charts.html`, `backtest.html`, `tests/js/catalog.test.mjs`, `tests/js/guide.test.mjs` | B1a: TA_DEFS entries for every `tv:` study (ids `tv_*`, group "TradingView", TV defaults, `HTF_IDS`), guide entries. B1b: `bigtrades` CATALOG entry (params min 25, max, side, cluster none\|volume\|price\|priceside, thr 100), footprint params `imb` (homebase\|atas\|exocharts\|sierra), `zero`, `edge`, `minvol`, `mindiff`, `text` (bidask\|delta\|volume\|trades\|dom\|price), profile param `method` (homebase\|sierra\|tv), `tpo`, `npoc`, `cstat`, `dturn`, `dstr`, `mwabs` entries (page-only), `pine` entry + `case 'pine'` in `buildSeries`/`point` + `setExtraMarkers` + settings-dialog hook for per-instance inputs; `need()`: `flow ||= on('bigtrades')`, `fp ||= on('npoc')||on('cstat')||pine-with-footprint`; a test that feeds every TA_DEFS `key(p)` to Python `make()` (the gap studies.md §2.1 step 8 names) |
| B2 flow-indicators | `flowmath.js`, `flowdefs.js`, `flowlayer.js`, `primitives.js`, `tests/js/flowmath.test.mjs`, `tests/js/flowdefs.test.mjs` | ofapps.md P1/P4/P5 + thin layers: `imbalancesV2(fp, opts)` with the four presets (fixtures: ATAS 30×350%→>105; Sierra A-F bar), `valueAreaV2(rows, pct, method)` (Sierra tie→both, TV stop-before-overshoot, homebase today) + POC tie rules, `nakedPocs`, `tpo(bars, periodMin, rowTicks, mode)` + IB + single prints, `agOf(bar,min,max,side)` + Bookmap clustering (`volume` with carry: 100/[20,15,35,270]→300 carry 40; `price`; `priceside`), `clusterStats(bar)` (Δ, Vol, Trades, MaxΔ, MinΔ, Δ/Vol, duration), `deltaTurnaround` (ATAS 3-bar, documented + corrected option), `deltaStrength`, MotiveWave absorption (reversal N ticks from an imbalance), Sierra Numbers Bars text types + dominant % + diagonal diff in `primitives.js` Footprint; layers for bubbles-of-orders, naked POCs, TPO, cluster-stat strip, turnaround marks |
| B3 pine-client | `homebase/static/charts/pinelayer.js` (new), `homebase/charts/server.py` (register `pineapi.routes()` only), `tests/js/pinelayer.test.mjs` | `PineLayer extends HBLayers.Layer` drawing boxes/lines/labels/linefills/polylines (bar_index → logical index via `XI()`, `xloc.bar_time` via `logicalAt`), `bgcolor` stripes, table overlay; exposes `HBPineLayer` for cell.js |

## Wave 3 (me)

`?v=` bumps in both html files; full test run (`tests/`, `tests/js`, and the engine parity tests from the main checkout);
chart service in the app; screenshots of the tape panel, DOM columns, a TV study beside its house twin, a Pine script;
adversarial review workflow over the whole diff; vault note; then ask the owner about merging.

## Open items the owner decides later

- The TradingView exports (the recipe in `docs/tvparity-export-recipe.md`): nothing can be called "exact" until they exist.
- A settlement-price source for `tv:pivots` / PDC (CME settlement; round-1 idea #4).
- PineTS issue #401 (session day = UTC calendar): `ta.vwap`, `timeframe.change("D")`, `time_tradingday` will not match on
  CME charts until fixed upstream or patched; marked xfail in the parity wrapper.
- Bubbles on days cached before this change need a `recount`-style backfill or a `CACHE_VERSION` bump.
