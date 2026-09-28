# Standing gotchas — staple this to every implementation brief

These are the findings that independent reviews of this repo keep re-discovering. Preventing one
costs a sentence; finding one costs a review round and a fix round. If your task touches the area,
treat the line as a requirement, not a suggestion.

## The chart page

- **Never rebuild a container while an input inside it has focus.** `<input type="date">` fires
  `change` on the first digit of the year, so a rebuild there destroys the field mid-typing and
  leaves a mangled value. Patch in place; defer any rebuild to `blur`.
- **`HBPanel.refresh()` re-renders the active tab on every desk event, quotes included.** A tab that
  rebuilds its own form will fight the user. Patch in place, and give the tab a `TAB_EVENTS` entry.
- **Keyboard auto-repeat fires an action repeatedly.** Any Enter/Space that confirms or sends must
  ignore `e.repeat`. A held key has sent duplicate orders here before.
- **A cell reference goes stale** on a grid rebuild, a layout load or a symbol change. Re-resolve the
  cell at click time and re-check it at send time; never cache one when you render.
- **Lightweight Charts 5.2.1 delivers mouse events only.** Any owned pointer gesture needs
  `pointercancel`, `blur` and buttons-lost cancellation, or the gesture sticks.
- **`logicalToCoordinate` is only valid for integer logicals.**
- **Markers are shared.** Merge through the cell's extra-markers hook under your own key; never
  replace the map, or you wipe the bot, fill, tester and paper markers.
- **Bar Replay:** a replaying chart must never send a real order, and must never be drawn with live
  data or with anything past its cursor. Re-check the replay guard at send time, not only at render.

## The live chart service (`:8852`)

- **Nothing heavy on the event loop.** Decoding, parsing, gzip and directory scans go to a thread —
  or a process when they hold the GIL for seconds. A full-day depth decode stalled the loop 14× until
  it moved to its own process.
- **No new market-data requests.** The broker allows 180 chart requests per hour per login and a
  burst penalises every request for an hour. Reuse what is already streaming.
- **The 09:20–09:35 ET window is sacred** — the desk's 9:30 bot shares this machine. Nothing new
  starts in it: no backtest, no heavy decode, no market-data re-login.

## Money paths

- **Fail closed.** An account the desk does not list, a quote you cannot read, an order state you
  cannot resolve: refuse and say so. Never assume the benign case.
- **Freeze the preview.** What the confirm dialog showed is what gets sent — prices, bracket,
  quantity, accounts. Never recompute at send.
- **A kill or flatten acts on its own position only**, capped at its own filled quantity, and never
  removes protection from a position it cannot fully attribute.
- **No planned broker socket drop 09:20–09:35 ET on weekdays.** A token renewal drops the
  socket, so it renews early (09:10–09:20) instead. Inside the window only a token that would
  expire there anyway is renewed, and a socket that lives through 09:28–09:31 is never dropped
  (`broker/tradovate.py` `renewal_due`). Anything new that closes or rebuilds a broker socket
  keeps out of that window too.

## Numbers

- **Bar-path ambiguity resolves pessimistically.** When one bar spans both the stop and the target,
  the stop fills. Optimistic ordering is the exact bias that made TradingView's 15s backtests wrong
  here.
- **Tick-grid comparisons need an epsilon.** `64.01 + 0.01` is not `64.02`.
- **Sign and scale:** drawdowns negative, MAE a loss, percent versus fraction, `$` versus ticks.
- **Days a strategy chose to skip are flat days, not data holes.** Dropping them inflated Sharpe ~50%.
- **A prop-rule number must be traceable** to the account holder or the firm's rulebook. Never copy
  one ruleset's numbers into another's file.

## Process

- Tests never open broker connections, and never write to `~/futures_ticks` or `~/futures_depth`.
- No native dialogs — the viewer blocks them.
- Lucide icons only, copied from `lucide-static@1.48.0`; never TradingView's.
- Asset changes need the `?v=` bump, or WKWebView serves the cached page.
