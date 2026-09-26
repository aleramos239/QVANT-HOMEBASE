# Charts page — TradingView-style redesign + basic drawing tools

Date: 2026-09-26 · Status: design approved in chat ("do it"); the user reviews the finished result

## Why

The Build-1 chart page works but reads as generic/AI-made: form controls in
every chart (selects, a typed "tick:750" box, a big "Studies" button), a
checkbox-and-"0 = off" studies form, a monospace debug-style legend, big
rounded outline buttons. The user trades on TradingView and wants ours to
look and behave like it. Nothing about the data, maths, websocket protocol or
footprint/profile layers changes.

Decisions (user, 2026-09-26): ONE top toolbar acting on the selected chart;
basic drawing tools INCLUDED; light theme by default.

## Measured reference (tradingview.com/chart, 2026-09-26)

- Font: `-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`; toolbar 14px/400; legend title 16px/400; legend values 13px.
- Top toolbar 38px tall; buttons full-height, no border, no radius, padding `0 10px`.
- Symbol search: pill 28px tall, radius 14px, background `#EBEBEB`, padding `0 34px 0 12px`.
- Left drawing rail 52px wide. Page frame `#EBEBEB`; panels white, 4px apart.
- Legend: title at (8px, 7px) of the pane; OHLC row labels in text colour `#0F0F0F`, values coloured by bar direction; up `#089981`.
- Indicators dialog: large modal, title + close, 34px search box (16px text), category column, plain name rows ~31px; clicking a row adds it.
- Indicator legend rows show eye / settings / remove on hover.

We follow these conventions; we do NOT copy TradingView's icons, logo or
branding. Icons: Lucide (MIT), `lucide-static@1.48.0`, inlined as SVG.

## Design tokens

| token | light | dark |
|---|---|---|
| `--frame` (page behind panels) | `#EBEBEB` | `#0A0A0A` |
| `--panel` | `#FFFFFF` | `#0F0F0F` |
| `--text` | `#0F0F0F` | `#DBDBDB` |
| `--text-2` (secondary) | `#787B86` | `#8C8C8C` |
| `--border` | `#E0E3EB` | `#2E2E2E` |
| `--grid` (chart grid) | `#F0F3FA` | `#1C1C1C` |
| `--hover` | `#F0F3FA` | `#2A2A2A` |
| `--pill` (symbol pill) | `#EBEBEB` | `#2A2A2A` |
| `--accent` | `#2962FF` | `#2962FF` |
| `--accent-soft` | `rgba(41,98,255,.10)` | `rgba(41,98,255,.20)` |
| `--up` / `--down` | `#089981` / `#F23645` | same |
| volume up/down | `rgba(8,153,129,.5)` / `rgba(242,54,69,.5)` | same |
| crosshair | `#9598A1` dashed, label bg `#131722` | same |
| watermark | `rgba(15,15,15,.06)` | `rgba(219,219,219,.06)` |

Type: the TradingView font stack above; toolbar/menus 14px; legend title 16px
in 1–2-chart layouts, 14px in 4–6-chart layouts; legend values 13px; axes
12px; bottom bar 12px; all numbers `font-variant-numeric: tabular-nums`.
Radii: panels 6px, menus/dialog 8px, pill 14px, rail buttons 4px. Shadows:
menus `0 2px 8px rgba(0,0,0,.16)`, dialog `0 8px 32px rgba(0,0,0,.24)`.
Focus: 2px `--accent` outline on `:focus-visible` for every control.

## Page structure

```
┌ top toolbar 38px ──────────────────────────────────────────────────────┐
│ ⌂Desk │ (NQ ▾) │ 1m 5m 15m 1h 4h D ▾ │ ƒx Indicators │ ⊞▾ ···· Layout ▾ Save │ ☾ │
├─rail─┬─ grid of panels (4px gaps on --frame, 6px radius) ─────────────┤
│ ⌖    │ ┌ panel (selected: 1px --accent inset outline) ┐ ┌ panel ┐     │
│ ╱    │ │ NQ · E-mini Nasdaq-100 · 1m  [approx. flow]  │ │       │     │
│ ─    │ │ O… H… L… C… +2.75 (+0.01%)  Vol 1.2K  Δ +62  │ │       │     │
│ ▭    │ │ VWAP 30,902.10              (hover: 👁 ⚙ ✕)   │ │       │     │
│ 📏   │ │            "NQ, 1m" watermark                 │ │       │     │
│ 🗑   │ └───────────────────────────────────────────────┘ └───────┘     │
├──────┴────────────────────────────────────────────────────────────────┤
│ ● Live · md demo · feeds ok          09:49:14 ET · md 10/180 · credit │ 30px
└────────────────────────────────────────────────────────────────────────┘
```

### Top toolbar (acts on the selected chart)
1. **Desk** — home icon + "Desk", links to `http://<host>:8850/`.
2. **Symbol pill** — shows the root (e.g. `NQ`, 14px/600) + chevron; opens a
   menu of the service's roots with full names (NQ E-mini Nasdaq-100, ES E-mini
   S&P 500, YM E-mini Dow, RTY E-mini Russell 2000, GC Gold, SI Silver, CL Crude
   Oil, ZN 10-Year T-Note, NG Natural Gas, HG Copper); type-ahead filter input at
   the top of the menu; Enter picks the first match.
3. **Interval buttons** — favourites `1m 5m 15m 1h 4h D`; the selected chart's
   interval is shown in `--accent`. If the selected chart uses a non-favourite
   interval, a button with its label appears after the favourites, active.
   **▾** opens a menu grouped SECONDS (5s 15s 30s) · MINUTES (1m 2m 3m 5m 10m 15m
   30m) · HOURS (1h 4h) · DAYS (1D) · TICKS (500T 1000T) · VOLUME (2000V) · RANGE
   (10R 20R) · CUSTOM (input "tick:750" + Apply; the server's error message is
   shown inline in the menu if it refuses the spec).
4. **ƒx Indicators** — opens the Indicators dialog for the selected chart.
5. **Layout grid** — grid icon + chevron; menu with four thumbnails: 1, 2 side
   by side, 2×2, 3×2. Current one highlighted.
6. right side: **layout name ▾** (current saved-layout name, or "Unsaved") →
   menu: saved layouts (click loads; × deletes after inline "Delete?" confirm),
   "Save as…" (inline name input + Enter); **Save** button saves to the current
   name (asks for a name if none); a failure shows inline in the menu / next to
   Save (`textContent`, no native dialogs).
7. **Theme** — sun/moon icon toggle (light ↔ dark), persisted in `hb_theme`.

Toolbar buttons: 38px tall, `0 10px` padding, no border, hover `--hover`,
active text `--accent`; 1px×20px `--border` separators between groups. On a
narrow window the toolbar scrolls horizontally instead of wrapping.

### Left rail (52px): cursor · trend line · horizontal line · rectangle · measure · — · remove all drawings
Tool buttons 36×36 centred, radius 4, icon 20px `--text`; hover `--hover`;
active tool: icon `--accent` on `--accent-soft`. Tooltips name each tool.

### Panels (one per chart)
- Background `--panel`, radius 6px, 4px gaps on `--frame`; the grid fills the
  space between toolbar/rail/bottom bar. Clicking a panel selects it; with more
  than one panel the selected one has a 1px inset `--accent` outline.
- No controls inside panels except the legend.
- **Legend** (DOM overlay, top-left at 8px/7px, no background):
  - Row 1: `NQ · E-mini Nasdaq-100 · 1m` (title size per layout) + small
    `approx. flow` badge (11px, `--text-2` on `--hover`, radius 4) when any
    loaded session lacks bid/ask (tooltip explains). A "loading…" / error text
    shows on this row while loading or on a server error (errors in `--down`).
  - Row 2 (13px): `O 30,919.25 H 30,922.25 L 30,918.00 C 30,921.75 +2.75 (+0.01%) Vol 1.23K Δ +62` — letters in `--text`,
    values coloured `--up`/`--down` by the bar's direction (close ≥ open), change
    vs the previous bar's close; Vol compact (K/M); Δ coloured by sign. Follows
    the crosshair; shows the last bar when the crosshair leaves.
  - One row per indicator (13px): name + params in `--text` (e.g. `EMA 20`,
    `VWAP RTH`, `ADX 14`), then its values in the line colour(s). On row hover:
    light `--hover` background (radius 4) and three 18px icon buttons: eye
    (hide/show; hidden rows at 50% opacity with eye-off), gear (settings), ×
    (remove). Rows are clickable; the rest of the legend lets mouse events
    through to the chart.
- **Watermark**: `NQ, 1m` centred in the price pane (LWC v5
  `createTextWatermark`), 48px, watermark colour.
- **Chart styling** (Lightweight Charts options): background `--panel`, text
  `--text-2`, axes font 12px, grid `--grid`, borders `--border`, candles up
  `--up`/down `--down` with matching wicks, borderVisible false, crosshair per
  tokens, `attributionLogo: false` (credit lives in the bottom bar).
- **Volume** is an overlay at the bottom 20% of the price pane (own price scale,
  scaleMargins top .8), bars coloured by delta sign (volume up/down tokens).
- Other panes (delta, cumulative delta, ADX) as today, separator `--border`.
- Price-pane indicator lines show their last value as a coloured tag on the
  price axis (`lastValueVisible: true`, `title` = short name).
- Existing layers keep working: footprint (with the render-time body hiding),
  volume profile, gap bands, session-level price lines, big-print markers —
  restyled with the new palette (footprint text `--text`, POC box `#F7A600`,
  value area `--accent-soft`, gap band `rgba(120,123,134,.14)`).

### Bottom bar (30px, 12px, `--text-2`)
Left: status dot (`--up` ok · `#F7A600` warn · `--down` bad) + `Live · md demo`
or `Replay 2026-09-22 ×20 · 09:31:13 ET`, then a one-phrase feed summary
(`feeds ok` / `NQ stale 26s` / the error); the per-root ages go in its tooltip.
Right: ET clock `HH:MM:SS ET` (1 s tick, from the browser clock via
`Intl.DateTimeFormat(..., {timeZone: 'America/New_York'})`), `md 10/180`, `rec
buffered N` (live only, amber ≥ 5000), and the credit link "Charts: TradingView
Lightweight Charts™". The stale-status greying (6 s) and red-on-disconnect
behaviour stays.

## Indicators

### Model
A chart's config becomes `{root, spec, indicators: [{uid, id, params, visible}]}`.
The catalog (below) turns instances into the server's study keys (deduplicated)
and into series/legend rows. Old saved configs (`{root, spec, st: {...}}` from
Build 1 — in localStorage `hb_charts_last` and in server `layouts.json`) are
migrated on load:

| old `st` | new instance |
|---|---|
| `vwap` true | `vwap {anchor: st.vwapAnchor, bands: st.vwapBands}` |
| `ema1`/`ema2` > 0 | `ema {length}` each |
| `sma` > 0 · `vwma` > 0 | `sma {length}` · `vwma {length}` |
| `levels` · `volume` · `delta` · `cumdelta` true | `levels` · `volume` · `delta` · `cumdelta` |
| `adx` > 0 | `adx {length}` |
| `footprint` true | `footprint {imbalance: st.imbalance}` |
| `profile` true | `profile` |
| `bigMin` > 0 | `bigprints {min: st.bigMin}` |

Default indicators for a new chart: `volume`, `vwap {eth}`, `levels`,
`footprint {imbalance 3}`.

### Catalog
| id | group | name in dialog | params (default) | server key | draws |
|---|---|---|---|---|---|
| volume | Volume | Volume | — | — | price-pane overlay histogram |
| vwap | VWAP | VWAP | anchor eth\|rth (eth), bands (off) | `vwap` / `vwap:rth` | 2px line + dashed 1σ/2σ bands |
| ema | Moving averages | EMA | length 1–1000 (20) | `ema:N` | 1.5px line |
| sma | Moving averages | SMA | length (50) | `sma:N` | 1.5px line |
| vwma | Moving averages | VWMA | length (20) | `vwma:N` | 1.5px line |
| adx | Trend | ADX / DMI | length (14) | `adx:N` | own pane: ADX, +DI, −DI |
| levels | Levels | Session levels | — | `levels` | dashed price lines PDH/PDL/PDC/ONH/ONL/Open |
| footprint | Order flow | Footprint | imbalance ratio 0–20 (3) | (fp always sent) | footprint layer |
| profile | Order flow | Volume profile | — | `profile` | profile layer |
| delta | Order flow | Delta | — | — | own pane histogram |
| cumdelta | Order flow | Cumulative delta | — | `cumdelta` | own pane line |
| bigprints | Order flow | Big prints | min size 1–100000 (25) | — | markers |

Line colours cycle `#2962FF, #FF6D00, #9C27B0, #00897B, #E91E63` per chart;
VWAP `#9C27B0` with bands `rgba(156,39,176,.45)`; ADX `--text`, +DI `--up`,
−DI `--down`; cum. delta `#FF6D00`; session levels `--text-2`.

### Indicators dialog
Modal (width `min(720px, 92vw)`, max-height 80vh, radius 8, dialog shadow,
backdrop `rgba(0,0,0,.25)`): header "Indicators" 20px/600 + close ×; search box
(34px, radius 8, 16px text, search icon, autofocus); left column of groups
(All, VWAP, Moving averages, Trend, Levels, Volume, Order flow) 180px; right: name
rows 32px/14px, hover `--hover`, click adds the indicator with defaults to the
selected chart (the dialog stays open; a row already on the chart shows a small
check — adding again creates a second instance, e.g. two EMAs). Esc / × /
backdrop click closes. Filtering matches name and group.

### Settings dialog (gear on a legend row)
Small modal titled with the indicator's name: one labelled field per param
(number inputs with min/max; anchor as a two-button segmented control; bands
as a checkbox), "Cancel" / "OK" (OK applies + resubscribes). Values outside
the range are clamped on OK.

## Drawing tools

- **Types saved**: trend line (2 points), horizontal line (1 price), rectangle
  (2 corners). **Measure** is transient (never saved).
- **Model**: `{id, type: 'trend'|'hline'|'rect', points: [{t, p}], color}` — `t`
  real epoch ms (a bar start), `p` price rounded to the tick size; `hline` has
  one point with `p` only. Colour `#2962FF` (style editing out of scope).
- **Anchoring**: a point's `t` maps to x through the chart's bars: the bar with
  `ms ≤ t` (binary search) plus the fraction toward the next bar, interpolated
  between the two INTEGER logical coordinates (Lightweight Charts v5 returns 0
  for a fractional logical). Before the first / after the last loaded bar: time
  bars extrapolate with the bar duration and spacing; tick/volume/range bars
  clamp to the first/last bar. So drawings stay put across timeframes, like
  TradingView. Placing snaps x to the nearest bar's `ms`.
- **Interaction**:
  - Pick a tool on the rail (active style). Trend/rectangle: click, move,
    click (or press-drag-release) — a live preview follows the pointer.
    Horizontal line: one click. Measure: press-drag-release (or click-move-click)
    shows a box with `+12.50 (+0.04%) · 50 ticks` and `8 bars · 8m`, blue when up,
    red when down; the next click or Esc removes it.
  - After placing, the tool returns to cursor.
  - Cursor mode: hovering a drawing shows a move cursor; press on it selects it
    (handles: 4px-radius white dots with accent stroke) and dragging moves it;
    dragging a handle moves that point; release saves. Click on empty chart
    deselects. `Delete`/`Backspace` removes the selected drawing (not while
    typing in an input). `Esc` cancels a drawing in progress / deselects.
  - While a tool is active or a drawing is dragged, chart panning/zooming is
    disabled (`handleScroll`/`handleScale` false) and restored afterwards.
  - Drawings live in the price pane only.
  - **Remove all** (trash on the rail): first click turns it red with the
    tooltip "Click again to remove N drawings on <ROOT>" for 3 s; the second
    click removes them.
- **Rendering**: a `Drawings` series primitive on the candle series (top):
  trend 2px accent line; rectangle 1px accent stroke + `--accent-soft` fill;
  handles when selected; measure box + label; horizontal lines via
  `createPriceLine` (1px accent, axis label on) so the price tag is native.
- **Persistence**: per symbol on the server — every chart showing that root
  shows its drawings. The page keeps one in-memory store per root, loads it
  with `GET /api/drawings/{root}` when a root is first shown, and saves the
  root's full list with `PUT /api/drawings/{root}` (debounced 300 ms) after
  each create / move / delete; all charts of that root re-render.

## Server changes (the only backend change)
- `GET /api/drawings/{root}` → the root's list (`[]` if none);
  `PUT /api/drawings/{root}` with a JSON list → validates and saves. Unknown
  root → 404. Validation: list ≤ 500 items; `id` string 1–40 chars; `type` in
  {trend, hline, rect}; points: trend/rect exactly 2 with integer `t` and
  finite `p`, hline exactly 1 with finite `p`; optional `color` `#RRGGBB`;
  anything else → 400 with a message. Stored in `.state/charts/drawings.json`
  (`{root: [...]}`) via temp file + `os.replace`.
- Browser writes are Origin-checked like `/ws`: `PUT/DELETE /api/layouts/...`
  and `PUT /api/drawings/...` refuse a foreign `Origin` with 403 (reuse
  `origin_ok`). (Closes the parked "no Origin check on layout routes" item.)

## Files
| file | responsibility |
|---|---|
| `homebase/static/charts.html` | page shell markup only (toolbar, rail, grid, bottom bar, dialog/menu roots) |
| `homebase/static/charts/charts.css` | tokens (light/dark) + every style |
| `homebase/static/charts/icons.js` | `window.HBIcons`: Lucide SVG strings used by the page |
| `homebase/static/charts/catalog.js` | `window.HBCatalog`: indicator catalog, instance helpers, server keys, migration, legend/number formatting — pure, Node-testable |
| `homebase/static/charts/drawings.js` | `window.HBDrawings`: pure geometry (time↔x, hit tests, tick rounding, measure text), the Drawings primitive, the per-chart controller, the per-root store client |
| `homebase/static/charts/primitives.js` | existing layers (palette keys only) |
| `homebase/static/charts/cell.js` | `window.HBCell`: one chart — Lightweight Charts setup, series from the catalog, legend DOM, watermark, history/update handling, layers, drawings hookup |
| `homebase/static/charts/app.js` | the page: state + selection, toolbar, menus, dialogs, layouts, websocket, bottom bar + clock |
| `homebase/charts/server.py` | drawings endpoints + Origin check on HTTP writes |
| `tests/test_charts_server.py` | endpoint tests |
| `tests/js/*.test.mjs` + `tests/test_charts_js.py` | Node tests of the pure JS (catalog, geometry), run by pytest through `node --test` (skipped if node is missing) |

Plain scripts (no bundler); each file exposes one `window.HB*` namespace and, when
`module` exists, `module.exports` for Node tests.

## Testing & verification
- pytest: drawings GET/PUT (valid, each validation error, unknown root, size
  cap, atomic file), Origin 403 on the three write routes, existing tests green.
- Node (`node --test`): catalog (defaults, server keys + dedupe, migration of
  every old `st` field, legend formatting incl. compact volume, change %),
  drawings geometry (time→x incl. between bars, before first/after last for
  time and non-time bars, x→time snapping, hit tests for segment/rectangle/
  handle, tick rounding, measure text).
- Controller browser verification on the replay (worktree, 2026-09-22 ×20):
  toolbar (symbol, favourites, ▾ menu incl. custom + a refused spec, grid
  picker, layout menu save/load/delete, theme), selection outline, legend
  (OHLC colours, crosshair follow, indicator rows, hover icons, hide/settings/
  remove), indicators dialog (search, groups, add twice), watermark, volume
  overlay, each drawing tool (create, select, move, handle drag, delete, Esc,
  remove all, persistence across reload and across a timeframe change, shared
  across two charts of one root, measure), footprint/profile still working,
  dark theme, 1/2/2×2/3×2 layouts, narrow window, zero console errors.

## Out of scope
Drawing styles/colours editing, more drawing types (fib, text, arrows),
drawing undo, alerts, click-trading/DOM (Build 2), per-indicator colour
editing, a right-hand watchlist/details panel, compare symbols.
