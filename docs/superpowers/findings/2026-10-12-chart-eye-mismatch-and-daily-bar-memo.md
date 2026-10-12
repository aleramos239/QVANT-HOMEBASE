# Chart: the eye and the drawing disagreed; 1D / 1W switches re-read every session

**Date**: 2026-10-12
**Context**: main, charts page (cell.js, the overlay layers) and the chart service's bar history (history.py, store.py, hub.py).

## What we set out to do

Owner: "indicator is hidden but still shows on chart, or is not hidden but shows hidden" and "anything else that
could remove dead weight or speed up the app, especially the chart".

## What we found

**Eye mismatch, two causes (commit 9dd44a82, test `tests/js/cell-visibility.test.mjs`):**
- `buildSeries` spread a line's own Style-tab `visible` OVER the instance's eye (`visible: inst.visible !== false, ...opts`).
  Any rebuild (a setting, a timezone, a resubscribe) drew a hidden indicator again while its legend row stayed greyed.
  And `setVisible(uid, true)` set every line visible, including lines the Style tab had hidden.
  Now a line carries `own` (its Style flag) and shows only when `own && eye`.
- The flow / Level 2 / book-event layers read the eye as they draw but repainted only on a new bar or a pan, so an eye
  click left them as they were. `setVisible` now calls each layer's `onIndicators()`.

**Speed (history.py, store.py, hub.py):**
| what | before | after |
|---|---|---|
| NQ 1D switch, memo evicted | 0.9-1.5 s | 0.16-0.29 s |
| bar memo | 256 sessions (a 258-session daily chart never fitted) | 4M cells (~1 GB): a bar + each footprint level / big print / sweep / bubble it holds |
| 1W / 1M per-session bar | built from ~1,400 minutes (~55 ms a session) | resampled from the cached daily bar |
| cold 1D build, in process | 750 ms (45 % was directory listing: 3 whole-year folder reads a session) | listing scope: one read per year folder |

Not a problem (measured): static assets 1.5 MB in 52 ms cold / 29 ms revalidated; page load 90 ms; 1m/5m/15m/1h
switches 15-220 ms; adding an indicator 0.1-0.75 s with no main-thread task over 110 ms; the eye 1-4 ms; no event-loop
stall over 3 s since 23:29 on 10-11.

**A mistake on the way (fixed, 31256f71):** the first version weighed a daily bar as 1 and the service went to 3.2 GB in
90 s of 1D / 1W probes. A daily bar holds a whole day's footprint (~1,000 levels, ~0.5 MB in Python), so bars are the
wrong unit; the budget is in cells. After the fix five roots of 1D + 1W added ~250 MB.

## Why it happened

The eye was added after the per-line Style flags, and `add()` put the instance default FIRST so anything in `opts` won.
The memo was sized when a chart was 60 minute sessions; daily and weekly charts (1 bar a session, 250-1,300 sessions)
came later and shared the count cap with everything else.

## What changes because of this

- A line's Style flag and the eye are ANDed, in one place (`add()`); a new overlay layer that reads `inst.visible`
  must implement `onIndicators()` or it will go stale on an eye click.
- The memo's unit is cells, not bars or sessions: anything that keeps per-session bars in memory must count their footprint.
- `TickStore.listing()` is a per-call scope: use it around one build, never around a wait for a file.
- The lag report no longer lists parked pool workers (Python 3.14 parks them inside `thread._worker`).

## References

- `homebase/static/charts/cell.js` `buildSeries.add`, `setVisible`
- `homebase/charts/history.py` `MEMO_BARS`, `_coarse`; `homebase/charts/store.py` `listing`
- Related: 2026-10-11-chart-timeframe-switch-cold-bar-cache.md, 2026-10-11-charts-black-page-300mb-plots-bundle-on-the-loop.md
