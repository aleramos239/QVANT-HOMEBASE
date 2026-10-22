# TradingView export recipe (indicator parity)

What this is for: Homebase's indicators are checked against TradingView's own numbers. Claude cannot open TradingView, so
the numbers come from your "Export chart data" CSVs. Each CSV holds TradingView's bars plus every indicator on the chart.
The files stay on this Mac in `~/.homebase/tvparity/` and never go into the repo (the repo is public).

Then: `.venv/bin/python -m tools.tvparity run` reads `~/.homebase/tvparity/inbox/`, files each CSV under
`exports/<date>/`, and writes `reports/<stamp>.md` with one verdict per indicator: identical, warm-up only, differs,
no-tv (no TradingView source) or no-data (no Homebase bars for those days).

## 3.0 Calibration export (once, about 5 minutes)

This settles how TradingView writes the file. Do it once, before the real exports.

1. Finish 3.1 first (layout A on the 1-minute chart).
2. Add a second "Moving Average Exponential" (any settings). That shows how a duplicate name comes out.
3. Turn the eye OFF on one built-in (say ATR). That shows a hidden indicator is left out.
4. Export once with **Time format: UNIX timestamp** (steps 4-5 of 3.2).
5. Export again with **Time format: ISO time**.
6. Remove the second EMA and turn the eye back ON.
7. Put both files in `~/.homebase/tvparity/inbox/` and tell Claude "calibration exports are in". The harness reads
   either time format; the two files answer the open questions (seconds or milliseconds, the time zone, how `na` and
   duplicates are written, whether the developing bar is in the file).

## 3.1 One-time setup (about 20 minutes)

### The four probe scripts

1. In TradingView open the Pine Editor (bottom panel, "Pine Editor").
2. Click "Open" → "New indicator". Select all the template text and delete it.
3. Paste the whole of `tools/pine/hb_parity_p1.pine` from the repo. Click "Save" and name it exactly **HB parity P1**.
4. Repeat for `hb_parity_p2.pine` → **HB parity P2**, `hb_parity_p3.pine` → **HB parity P3**,
   `hb_parity_p4.pine` → **HB parity P4**.
   P4 uses `request.footprint`, which needs Premium (you have it). If it refuses to add, say so: P4 is then skipped.

### The symbol and its settings (both layouts)

5. Symbol: **CME_MINI:NQ1!**.
6. Right-click the chart → Settings → **Symbol** tab:
   - Session: **ETH (electronic trading hours)**.
   - **Uncheck** "Use settlement as close on daily interval" (the SET button in the bottom toolbar must not be lit).
   - **Uncheck** "Adjust for contracts changes" (the B-ADJ button must not be lit).
7. Time zone (bottom right of the chart): any. The export uses UNIX time, which has no zone.

### Layout "HB parity A" (17 indicators)

8. Open a new layout (top right, the layout name → "New layout"), call it **HB parity A**.
9. Indicators → "My scripts" → add **HB parity P1**.
10. Add these 16 built-ins (Indicators → search the name), with these settings in each one's Inputs tab:

| # | Built-in | Inputs |
|---|---|---|
| 1 | Volume | default |
| 2 | Moving Average Simple | length 50, source close |
| 3 | Moving Average Exponential | length 20, source close |
| 4 | VWMA | length 20 |
| 5 | Triple EMA | length 20 |
| 6 | Relative Strength Index | length 14; "RSI-based MA" type **None** if the option exists |
| 7 | MACD | 12 / 26 / 9, both MA types EMA |
| 8 | Bollinger Bands | 20, StdDev 2, basis SMA, source close |
| 9 | Average True Range | 14, smoothing RMA |
| 10 | Stochastic | %K length 14, **%K smoothing 3**, %D smoothing 3 (TradingView's default smoothing is 1) |
| 11 | Supertrend | ATR length 10, factor 3 |
| 12 | Donchian Channels | 20 |
| 13 | Keltner Channels | length 20, multiplier 1.5, "Use Exponential MA" on, bands style "Average True Range", ATR length 20 |
| 14 | Money Flow Index | 14 |
| 15 | Directional Movement Index | DI length 14, ADX smoothing 14 |
| 16 | VWAP | anchor Session, source hlc3, Bands: band 1 multiplier 1 and ON, bands 2 and 3 OFF; **uncheck "Hide VWAP on 1D or above"** |

11. Every indicator's eye must be ON (visible). In each indicator's **Style** tab set **Precision** to the highest value
    offered (so the file carries all the decimals).
12. Save this set as an indicator template: Indicators → Templates → "Save indicator template" → **HB parity A**.

### Layout "HB parity B"

13. New layout, call it **HB parity B**. Same symbol and symbol settings as step 6.
14. Add **HB parity P2**, **HB parity P3**, **HB parity P4** (Indicators → My scripts).
15. Add the built-ins **Cumulative Volume Delta** (anchor Session) and **Volume Delta** (defaults). These are reference
    only: TradingView defines delta from lower-timeframe bars, Homebase from each trade's side.
16. Add your own Pine scripts you want checked against Homebase's Pine runtime, up to 20 indicators on this chart in
    total (the chart limit is 25).
17. Precision to the highest value in every Style tab (step 11). Save as indicator template **HB parity B**.

## 3.2 The ten exports (2 layouts x 1m, 5m, 15m, 1h, 1D; about 2 minutes each)

Do this at the weekend (Saturday, or Sunday before 18:00 ET) so no bar is still forming.

1. Open layout **HB parity A**, timeframe **1m**.
2. Press **Alt+G** (Go to date), type **2000-01-01**, Enter. Wait until the chart stops loading. Premium stops at about
   20,000 bars; the 1D chart reaches the start of the series.
3. Top right, the layout dropdown (the layout's name) → **Export chart data…**
4. In the dialog: Chart = this chart; **Time format: UNIX timestamp**. Click **Export**.
5. Save the file into `~/.homebase/tvparity/inbox/`. Keep the name TradingView gives it. The harness works out the
   timeframe from the bar spacing and the group (P1 … P4) from the probe column, and renames the file itself.
6. Switch the timeframe to **5m** and repeat steps 2-5. Then **15m**, **1h**, **1D**.
7. Open layout **HB parity B** and repeat steps 1-6.
8. Tell Claude "the exports are in". Claude runs `.venv/bin/python -m tools.tvparity run` and reads
   `~/.homebase/tvparity/reports/`.

Optional extras, same steps:
- 1D with the SET button ON (to measure the settlement gap).
- CME_MINI:ES1! 1m on layout B (the SMT partner market).
- RTH session 1m / 5m, once Homebase has an RTH bar mode.

Known differences the report sets apart (they are not bugs): a holiday session folded into the next day, the September
2026 roll one session apart (TradingView NQ1! switched to NQZ6 on 09-15, Homebase on 09-14), a print landing on the other
side of a bar boundary, settlement closes if SET was left on, roll-week volume (TradingView counts spread legs), days with
Homebase data gaps, and the first bars of each study (seeding).
