# Charts — Long/Short position tools, Weak/Strong magnet, chart Settings dialog

Date: 2026-09-26 · Status: approved in chat. The user asked: "i want to add a short and long position,
i want to add a magnet that adjusts from strong and weak"; the design was shown in chat and the user
said "yes". The user then asked: "i want to have a settings in the chart like trading view where i can
edit settings in of the chart", with a screenshot of TradingView's Settings → Symbol tab. The tab list
below was stated in chat and nobody objected. The page is the TradingView-style chart page from
`2026-09-26-charts-tv-redesign-design.md`. Its tokens, fonts, radii and conventions bind here.

## Why

These are the chart tools the user relies on in TradingView and that the homebase page still lacks:
- a risk/reward planner (TradingView's "Long Position" / "Short Position");
- a magnet that snaps drawing points to candle prices;
- a per-chart Settings dialog for candle colours, status line, scales and canvas.

## Global constraints (carried from the redesign; bind every task)

- **Plain scripts:** each file is an IIFE exposing one `window.HB*` namespace. Pure halves must load in
  Node (`module.exports`) with no browser globals at load time.
- **Icons:** Lucide only (`lucide-static@1.48.0`, inlined SVG). Never TradingView's icons, logo or branding.
- **Styling:** design tokens as in the redesign spec (`--frame --panel --text --text-2 --border --grid
  --hover --pill --accent --accent-soft --up --down`), light theme default, dark supported. Font stack:
  `-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`. Menus and dialogs
  have radius 8 and use the shadows from the spec. Every control gets a 2px `--accent` `:focus-visible`
  outline. Numbers use `tabular-nums`.
- **No native dialogs:** no `alert`, `confirm` or `prompt`; the desktop viewer blocks them. All text
  input is inline.
- **RR notation:** risk:reward is written **1:X** (e.g. `RR 1:2`, `RR 1:1.5`), never "2" or "2:1".
- **Dollars:** every P&L figure shows dollars as well as points.
- **Tests:**
  - Tests never open broker connections, never use tokens, and never write under `~/futures_ticks`.
  - Pure logic is tested in Node (`node --test tests/js/`).
  - Server changes are tested in pytest.
  - Both suites stay green.
- **Git and deploy:**
  - Work happens on branch `feat/charts-build2` in `.worktrees/build2`.
  - Never touch the live checkout; never run `deploy/install.sh`; never restart services.
  - Changed page assets bump their cache-bust query from `?v=2` to `?v=3` in `charts.html`.

## 1 · Long / Short position tools

**Rail:** two new tools after the rectangle, in this order: "Long position" and "Short position".
Lucide `trending-up` and `trending-down` icons; rail tooltip names as given. Each behaves like the other
drawing tools: pick it, place it, then the rail returns to the cursor with the new drawing selected.

**Model** (saved per symbol with the other drawings):
```
{id, type: 'long'|'short', points: [entry, target, stop], qty, color?}
  entry  = {t: t0, p: entry price}       t0 = the box's left edge (a bar start, epoch ms)
  target = {t: t1, p: target price}      t1 = the box's right edge (same t for target and stop)
  stop   = {t: t1, p: stop price}
  qty    = integer 1..10000 (default 1)
long:  stop < entry < target      short: target < entry < stop     (every gap ≥ 1 tick)
```

**Placing:**
- One click at (t0, entry).
- Risk R = the price distance of 8% of the price pane's height, rounded to the tick, at least 4 ticks.
  This way the new box has the same on-screen size at any zoom.
- Long: stop = entry − R, target = entry + 2R, so a new box reads **RR 1:2**. Short: mirrored.
- Right edge: t1 = the bar 20 bars after t0. Time bars extrapolate beyond the last loaded bar with the
  existing `snapTime` rule.
- A press-drag-release also places it at the press point; the drag distance is ignored.

**Handles** (4, white dot with a coloured stroke, as for the other tools):

| # | at | dragging it |
|---|---|---|
| 0 | (x0, entry) | Sets t0 and the entry price. Target and stop keep their prices. Entry is clamped to stay ≥ 1 tick inside (stop, target). |
| 1 | (x0, target) | Sets the target price only. Clamped ≥ 1 tick beyond the entry. |
| 2 | (x0, stop) | Sets the stop price only. Clamped ≥ 1 tick beyond the entry on the risk side. |
| 3 | (x1, entry) | Sets t1. Clamped to at least 1 bar after t0. |

- Pressing inside the box selects it. Dragging the body moves the whole box; the existing `moveDrawing`
  applies, since every point moves.
- Double-clicking a position opens its small settings dialog (§1.1).

**Rendering** (canvas primitive, price pane only; TradingView's look):
- **Zones:** profit zone fill `rgba(8,153,129,.20)`, loss zone fill `rgba(242,54,69,.20)`, no zone
  borders. The entry line is 1px `--text-2` across the box. Selected: the handles, plus a 1px outline
  of the whole box in `--text-2`.
- **Labels:** 12px, white text on a rounded (radius 4) rect in `--up` / `--down` / `--text-2`, centred
  horizontally on the box.
  - **Target label**, outside the profit zone (above for long, below for short):
    `Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000`
  - **Stop label**, outside the loss zone: `Stop 30,875.00 · −25.00 (0.08%) · 100 ticks · −$500`
  - **Centre label** on the entry line, grey box: `RR 1:2 · Qty 1`, with a second line giving the
    outcome (below).
  - A label that would leave the pane is clamped inside it.
- **Dollars:** $ = price move × `point_value` × qty. `point_value` comes from the server snapshot. When
  it is unknown, the `· $…` parts are omitted.
- **RR:** reward ÷ risk with at most 2 decimals and trailing zeros trimmed, written `1:X`.

**Outcome** (TradingView shows how the planned trade played out). It is evaluated on the chart's bars at
each redraw, using binary search into the bars within [t0, t1]. It is honest about bar ambiguity:
- **Entered** on the first bar with `ms ≥ bar-of(t0)` whose low ≤ entry ≤ high. No such bar up to t1 →
  second line `Not entered`, no path drawn.
- **Exit:** the first later bar whose range reaches the target or the stop (long: high ≥ target /
  low ≤ stop; short mirrored).
  - A bar that reaches both → `Stop and target in one bar`. No P&L is claimed and no path is drawn.
  - The entry bar itself reaching the target or stop → also ambiguous: `Entry bar touched stop/target`.
- **Closed:** the second line reads `Closed +$1,000` (or `Closed −$500`; in points when $ is unknown). A
  dashed 1px path in `--text-2` runs from (entry bar x, entry) to (exit bar x, exit price).
- **Still open** (t1 is at or after the last loaded bar, entered, no exit): `Open −$120` at the last
  close.
- **Expired** (t1 before the last loaded bar, entered, no exit by t1): `Open at end −$120`, at the
  close of the last bar ≤ t1.

### 1.1 Position settings (double-click)

A small modal in the style of the existing indicator Settings dialog.
- **Fields:** Entry, Target, Stop (price inputs, tick-rounded) and Qty (integer 1–10000).
- **Buttons:** Cancel / OK. OK validates the ordering for the type. An invalid combination shows an
  inline error under the fields and does not save.

## 2 · Magnet (Weak / Strong)

- **Rail button:** Lucide `magnet`, placed below the drawing tools and above "Remove all".
  - A click toggles it on/off. The button stays pressed while on.
  - A 6px corner triangle at its bottom-right opens a flyout (menu styling, right of the rail) with two
    rows, "Weak magnet" and "Strong magnet", with a check on the current one. Picking a row sets the mode
    and turns the magnet on.
  - Tooltip: `Magnet (weak)`, `Magnet (strong)` or `Magnet off`.
  - State `{on, mode}` persists per viewer in `localStorage` key `hb_charts_magnet`. Every access is
    wrapped in try/catch; the default is `{on: false, mode: 'weak'}`.
- **Snap (pure):** candidates are the O, H, L and C of the bar nearest the pointer (the bar the time
  already snaps to).
  - **Weak:** use the candidate nearest the pointer in pixels if it is within **12 px**; otherwise keep
    the pointer's tick-rounded price.
  - **Strong:** always use the nearest candidate.
  - Time always snaps to the bar, as today.
- **Applies to:** placing points (trend, rectangle, horizontal line, measure, position entry), dragging
  handles (including the position's target/stop/entry handles), and a position box's entry at placement.
  It does **not** apply to moving a whole drawing by its body.
- **⌘ (Meta) held** during a pointer event inverts the magnet for that event: an active magnet is off,
  an inactive one uses the current mode (TradingView's Ctrl/Cmd behaviour).
- **Crosshair:** while the magnet is on, a drawing tool is active and the vendored Lightweight Charts
  exposes `CrosshairMode.MagnetOHLC`, the selected chart's crosshair uses it. Otherwise the crosshair is
  unchanged. This is restored when the tool returns to the cursor.

## 3 · Chart Settings dialog (TradingView parity for what applies to us)

**Opening:** a gear button in the top toolbar (Lucide `settings`, tooltip "Chart settings", just left
of the theme button) opens Settings for the **selected** chart.

**Dialog layout:**
- Modal `min(820px, 94vw)` × `min(600px, 88vh)`, title "Settings" 20px/600, × close.
- **Left column (220px):** tab rows 40px high (icon + 15px label), selected row on `--hover`, radius 6.
- **Right pane:** scrolls. Section captions are uppercase 12px `--text-2` with letter-spacing .04em.
  Rows are 40px: label on the left, controls right-aligned at a fixed column (as in the screenshot).
- **Footer (top border):**
  - `Template ▾` on the left;
  - on the right: `Apply to all` (outlined), `Cancel` (outlined), `Ok` (solid `--text` background,
    `--panel` text, as TradingView's dark primary).

**Behaviour:**
- Every change previews live on the selected chart.
- Cancel, ×, Esc or a backdrop click revert to the state at open.
- Ok keeps the changes and marks the layout Unsaved.
- `Apply to all` copies the dialog's current settings to every chart in the layout (live) and keeps the
  dialog open.
- Settings are **per chart** and live in the layout: `cells[i].settings`. Only values that differ from
  the defaults are stored. Old layouts without `settings` load with the defaults.

**Tabs and fields** (Trading, Alerts and Events tabs are out of scope here; Trading arrives with chart
trading):

1. **Symbol** (Lucide `chart-candlestick`)
   - **CANDLES**
     - Colour bars based on previous close (checkbox, default off). When on, a candle is up/down by its
       close against the previous bar's close, not its own open.
     - Body / Borders / Wick: each is a checkbox plus an up swatch and a down swatch. Defaults: all on;
       colours follow the theme (`--up` / `--down`).
   - **DATA**
     - Precision: `Default` (from the tick size), or 0 to 6 decimals.
     - Timezone: `Exchange (New York)` (default), `UTC`, `Chicago`, `London`, `Local`. It drives the time
       axis, crosshair and legend times.
     - Electronic trading hours background: checkbox (default off) plus a swatch (default
       `rgba(120,123,134,.08)`). It shades bars outside 09:30–16:00 ET on intraday time charts only.
2. **Status line** (Lucide `list`)
   - Checkboxes for what the chart's legend shows:
     - Symbol title, with a select: `Ticker` / `Description` / `Ticker and description`, default the
       latter;
     - OHLC values;
     - Bar change values;
     - Volume;
     - Indicator titles, Indicator arguments and Indicator values.
   - All default on, except as the legend does today.
3. **Scales and lines** (Lucide `ruler`)
   - **PRICE SCALE**
     - Scale price chart only (checkbox, default off). When on, overlays on the price pane (MAs, VWAP,
       levels…) do not take part in autoscale. This closes a Build-1 follow-up.
     - Symbol last price label (checkbox, on).
     - Symbol last price line (checkbox, on), with style Solid / Dotted / Dashed.
     - Countdown to bar close (checkbox, default on for time bars): `mm:ss` (`h:mm:ss` ≥ 1h) in a label
       just below the last-price label, via a primitive price-axis view, ticking once a second.
     - Top margin / Bottom margin (%, 0–40; defaults as today).
   - **TIME SCALE**
     - Right margin (bars, 0–100; default as today).
4. **Canvas** (Lucide `paintbrush`)
   - **CHART BASIC STYLES**
     - Background: swatch (default follows the theme).
     - Vert grid lines / Horz grid lines: checkbox + swatch each.
     - Crosshair: swatch + style (Solid / Dotted / Dashed) + width (1–4).
     - Watermark: checkbox + swatch.
   - **SCALES**
     - Text colour: swatch.
     - Text size: 10–16, default 12.
     - Lines colour: swatch.

**Swatch popover** (menu styling):
- a 10-column palette (10 hues × 6 tints/shades, TradingView-like);
- an opacity slider 0–100%;
- a hex input (`#RRGGBB`), with an inline error for anything else;
- a `Default` link that returns the field to "follow the theme / default".

**Theme:** a colour field that was never changed follows the theme, and switching light/dark updates it.
A changed colour stays when the theme switches. `Template ▾ → Apply defaults` clears every override.

**Templates** (named, shared by every chart; saved on the server like layouts):
- **Menu:**
  - `Save as…`: an inline name field inside the menu, Enter to save.
  - `Apply defaults`.
  - A divider, then saved template names (a click applies it to the dialog, live). A row's × deletes it
    after an inline "Delete?" confirm.
- **Server:**
  - `GET /api/templates` → `{name: settings}`.
  - `PUT /api/templates/{name}`: a JSON object ≤ 16 KB; name 1–40 characters, no `/ \ .. ` or control
    characters.
  - `DELETE /api/templates/{name}`.
  - Stored in `.state/charts/templates.json` with the existing atomic `read_json` / `write_json`.
  - Writes use the same Origin check as the other browser writes (`browser_write_ok`).

**Model** (pure, `homebase/static/charts/settings.js` → `window.HBSettings`, Node-tested):
- `DEFAULTS`: every field; colours that follow the theme are `null`.
- `normalize(obj)`: drops unknown keys, clamps numbers, validates colours (`#RRGGBB` or
  `rgba(r,g,b,a)`) and enums.
- `overrides(full)`: returns only the non-default values (what the layout and templates store).
- `resolve(overrides, palette)`: returns concrete values for a theme palette.
- Mappings to Lightweight Charts options: `chartOptions(resolved)` (layout background/text/fontSize,
  grid, crosshair, rightOffset); `candleOptions(resolved, tick)` (up/down/border/wick colours and
  visibility, priceFormat precision, lastValueVisible, priceLineVisible/Style); `scaleMargins(resolved)`;
  `legendFlags(resolved)`.
- `barColorsByPrevClose(bars, resolved)`: the per-bar colour overrides used when "Colour bars based on
  previous close" is on.

## 4 · Server changes

- **`check_drawings`:**
  - Accepts `long` / `short` with exactly 3 points, each with finite `t` and `p`.
  - `points[1].t == points[2].t`.
  - The price ordering above for the type.
  - Optional `qty`, an integer 1–10000, kept.
  - Everything else is unchanged; `color` stays optional.
- **Hub snapshot** (the message carrying `tick_size`) adds `point_value` from
  `homebase.contracts.point_value(root)`, `null` when unknown.
- **`/api/templates` routes** as above.

## Files

| File | Change |
|---|---|
| `homebase/static/charts/position.js` (new, `HBPosition`) | Pure position geometry: defaults, handles, hit test, setHandle with clamps, labels, outcome. Also `drawPosition(ctx, d, geo, P, pctx)`. |
| `homebase/static/charts/drawings.js` | Magnet snap (pure) plus controller integration; long/short dispatch to `HBPosition` for handles, hit, set, draw and placement; double-click → position settings. |
| `homebase/static/charts/settings.js` (new, `HBSettings`) | The pure settings model and option mappings. |
| `homebase/static/charts/settings-dialog.js` (new, `HBSettingsDialog`) | The dialog, tabs, swatch popover and templates menu (browser only). |
| `homebase/static/charts/cell.js` | Applies settings: chart/candle options, legend flags, margins, the "Scale price chart only" autoscale, the ETH-background and countdown primitives, previous-close colouring. Stores `point_value`. |
| `homebase/static/charts/app.js` | Toolbar gear; rail long/short/magnet with its flyout and persistence; templates API client; layouts carry `cells[i].settings`. |
| `homebase/static/charts.html`, `charts/charts.css`, `charts/icons.js` | Shell, styles, icons. |
| `homebase/charts/server.py`, `homebase/charts/hub.py` | As in §4. |
| Tests | `tests/js/drawings.test.mjs`, new `tests/js/position.test.mjs`, new `tests/js/settings.test.mjs`, `tests/test_charts_server.py`, `tests/test_charts_hub.py`. |

## Testing & verification

**Node:**
- magnet weak/strong/⌘ and the 12 px rule;
- position defaults (RR 1:2, 8% of pane height, min 4 ticks);
- handle clamps for long and short;
- labels (`RR 1:1.5`, $ with and without `point_value`);
- the outcome cases: not entered, target, stop, both-in-one-bar, entry-bar touch, open, expired;
- settings normalize/overrides/resolve round-trip, theme-following colours, and every mapping.

**pytest:**
- long/short validation (accepted, wrong count, wrong ordering, bad qty);
- `point_value` in the snapshot;
- the templates routes (round-trip, size and name limits, the Origin check on PUT/DELETE).

**Browser** (controller, on the replay at :8854):
- place long and short; drag every handle; read the labels and the outcome;
- magnet weak/strong and ⌘;
- every Settings tab: live preview, Cancel revert, Ok, Apply to all, templates, the theme switch;
- a saved layout reloads with its settings;
- screenshots.

## Out of scope

- The Trading, Alerts and Events tabs.
- RTH-only session bars, and "adjust for contract changes".
- Style editing for other drawings.
- Position-tool account-size/risk-% sizing (qty only).
- Sending a position drawing as an order (chart trading decides that).

## 5 · Deep history: scroll back through the whole tick archive (added 2026-09-26, user: "yes")

Why: past sessions already come from our archive (`~/futures_ticks`, from 2021-09-22), not Tradovate, but the
hub loads only `sessions_back(spec)` sessions (1 / 3 / 10 / 60) and the page cannot ask for more — the user
asked to "fill in the charts with the tick data that we have".

- **Deeper default load**: sub-minute and tick/volume/range bars 1 session (unchanged); time bars ≤ 5m
  **5 sessions**; ≤ 1h **20 sessions**; > 1h (4h, D) **250 sessions** (≈ 1 year). `HISTORY_MAX` (20,000 bars
  per message) still caps a message.
- **Scroll-back (TradingView behaviour)**: when the visible logical range's left edge comes within **50 bars**
  of the first loaded bar, the page sends `{"t": "older", "id": <stream id>, "before": <first bar ms>}` once
  (no second request while one is pending). The server answers `{"t": "older", "id", "bars": [...],
  "sessions": [...], "done": bool}` with the next chunk of OLDER completed sessions from the archive
  (chunk = the stream's default session count, at most `HISTORY_MAX` bars), built exactly like today's
  history (1-minute pickle cache → resample; tick bars from ticks). The page prepends them keeping the
  view still (shift the visible logical range by the number of bars added), re-runs studies/indicators for
  the new range as today's full reload does, and draws a `Start of data` label at the archive's first bar
  when `done` is true. Session gap marks and the `approx. flow` badge apply to the older sessions as they do today.
- **Work happens off the event loop** (the hub already builds history in worker threads) and shares the
  refill budget with nothing — it never touches the broker.
- **Warm-up (optional command)**: `python -m homebase.charts.warm --roots NQ,ES --since 2021-09-22` builds
  the per-session 1-minute pickles ahead of time (skips existing, prints progress; read-only on
  `~/futures_ticks`). Not scheduled automatically.
- **Rolls**: sessions stitch front month to front month unadjusted (as today); back-adjusting is out of scope.
- **Tests**: pytest — `older` returns the next chunk strictly before `before`, respects `HISTORY_MAX`, sets
  `done` at the first archive session, never returns today's session, works for tick bars (1 session per
  chunk); the warm-up command skips built sessions. Node/browser — the pending-request guard, the view does
  not jump after a prepend, `Start of data` appears.

## 6 · Economic calendar (ForexFactory) on the charts (added 2026-09-26, user asked; design stated in chat)

Why: the user wants to see USD red / orange / grey "folder" news on the charts.

- **Source**: ForexFactory's public weekly feed `https://nfs.faireconomy.media/ff_calendar_thisweek.json`
  (verified 2026-09-26: 200, 82 events; fields `title, country, date (ISO with ET offset), impact
  (High|Medium|Low|Holiday|Non-Economic), forecast, previous`). Only the current week is published
  (`…nextweek.json` 404s until FF rolls over).
- **Chart service** `homebase/charts/calendar.py`: fetch at startup and then every **60 min** (never more
  than one request per 30 min — FF blocks aggressive polling), with a browser User-Agent and a 10 s
  timeout; failures keep the last good data and are reported in `/api/status` (`calendar: {ok, fetched_at,
  error}`). Each fetch is stored per week at `.state/charts/calendar/<week-start-date>.json` (atomic
  write) so past weeks accumulate from now on. `GET /api/calendar?from=<ms>&to=<ms>&countries=USD,EUR`
  returns the merged events in range as `[{t_ms, title, country, impact, forecast, previous}]`.
- **Colours** (ForexFactory's folders): High `#F23645` (red), Medium `#FF9800` (orange), Low `#F7C600`
  (yellow), Holiday / Non-Economic `#9598A1` (grey).
- **On each chart** (intraday and daily): a 10 px coloured circle flag on the time axis strip at the event
  time (primitive, drawn at the bottom of the price pane); High events also get a 1 px dotted vertical line
  in the event colour through the price pane. Hovering a flag shows a small tooltip
  `08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%` (several events at one time list together).
- **Status bar**: `Next USD: CPI m/m 08:30 (in 2h 14m)` for the next shown-impact event, coloured by impact;
  hidden when none this week.
- **Settings → Events tab** (Lucide `calendar`): checkboxes High / Medium / Low / Holiday (defaults High +
  Medium on), currencies (multi-select of the feed's countries, default USD), `Vertical lines for high
  impact` (on). Stored per chart with the other settings (HBSettings).
- **Tests**: pytest — parsing (ISO offsets → ms, all impact values), the 30-min floor, keeping last good
  data on failure, per-week storage + range merge, `countries` filter; Node — flag layout/grouping, the
  countdown text; browser — flags, tooltip, line, Events tab toggles.

## 7 · Chart context menu + moving indicators between panes (added 2026-09-26, user request with TradingView screenshots)

User: "i also want to be able to double click the chart and see some options, and to be able to either remove or
add these to the big chart" — screenshots: TradingView's chart right-click menu, and our Delta / Cumulative delta
panes below the price chart.

- **Chart menu** (menu styling from the redesign spec; opens at the pointer, clamped inside the window; Esc /
  outside click closes; arrow keys + Enter): opened by **right-click** anywhere in a chart's price pane, and by a
  **double-click on empty chart space** (a double-click on a drawing keeps its own behaviour, e.g. position
  settings). Items, in order, with dividers like TradingView:
  1. `Reset chart view` (⌥R) — fit content + reset the price scale to auto;
  2. `Copy price 30,878.00` — the price under the pointer, tick-rounded, to the clipboard (try/catch;
     silent failure);
  3. *(trading items, inserted later by the chart-trading page build: Buy/Sell limit/stop at the price)* — leave
     an extension point `HBChartMenu.register(section, itemsFn)` so that build adds them without editing this code;
  4. `Remove N drawings` (only when N > 0; same double-confirm rule as the rail's Remove all) and
     `Remove N indicators` (only when N > 0; removes all indicators of this chart, one undo-free click);
  5. `Settings…` — opens the chart Settings dialog (§3) for this chart.
  Items that do not exist yet (alerts, object tree, table view, chart templates submenu) are **not** shown.
- **Move indicators between panes**: every indicator that can live in its own pane (Delta, Cumulative delta,
  and any other pane-type indicator in the catalog) gets a `pane` placement in the indicator model
  (`{uid, id, params, visible, pane: 'own'|'main'}`, default = today's placement; migrated layouts keep today's
  placement). On `main`, the series overlays the price pane on its own hidden overlay price scale pinned to the
  bottom (scaleMargins like Volume: top ≈ .75, bottom 0), never affecting the price autoscale. On `own`, it gets
  its own pane below (today's behaviour, stretch factors as today). Price-pane-only indicators (VWAP, MAs,
  levels) do not offer the move.
- **Where the move lives**: the indicator's legend row gets a `⋯` (Lucide `ellipsis`) menu next to eye / gear /
  × with `Move to main chart` or `Move to new pane below`, and `Remove`; right-clicking inside an indicator's own
  pane opens the same three items (not the chart menu).
- Placement is saved with the layout (the indicator object) and survives reload / symbol change.
- **Tests**: Node — the migrate default for `pane`, the menu item list for N drawings / N indicators = 0 or > 0,
  the extension-point ordering; browser — right-click and empty-space double-click open the menu, Reset / Copy /
  Remove / Settings work, Delta moves to the main chart and back, the price autoscale ignores it on main, a saved
  layout restores the placement.

## 8 · Chart templates per chart (added 2026-09-26, user: "i want each chart to have its own settings, and be able to save layouts so i can just set a saved layout per chart")

Settings are already per chart (§3). This extends the named templates into TradingView-style **chart templates**:
- A template stores `{settings, indicators, spec?}` — the chart's settings overrides, its indicator list
  (ids + params + visibility + pane placement, fresh uids on apply) and, only when "Include interval" was ticked at
  save time, its bar spec. Never the symbol. Existing settings-only templates stay valid (missing keys = unchanged).
- **Save**: chart menu (§7) `Chart template ›` → `Save this chart as template…` (inline name field, same name
  rules and 16 KB limit as §3's templates API; an existing name asks inline "Replace?"), and the Settings dialog's
  `Template ▾ → Save as…` now also stores indicators (checkbox "Include indicators", on by default; "Include
  interval", off).
- **Apply**: chart menu `Chart template ›` lists saved templates; clicking one applies it to **that chart only**
  (settings + indicators replaced, interval changed only if stored), marks the layout Unsaved. The Settings
  dialog's `Template ▾` list applies to the dialog's chart as today (live preview; Cancel reverts indicators too).
- **Server**: unchanged routes (`/api/templates`); validation accepts the three keys (indicators validated with
  the catalog's migrate on the page; server just enforces JSON object + size).
- **Tests**: Node — template build/apply (fresh uids, spec only when stored, old settings-only templates);
  browser — save from one chart, apply to another, cancel-revert in the dialog, reload keeps it.
