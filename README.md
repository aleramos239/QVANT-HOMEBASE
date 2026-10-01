# Ramos Quant Homebase

The live desk: runs the approved 9:30 straddle strategies against the broker.
Headless service on the Mac mini; controlled from any browser (laptop/phone)
over Tailscale.

## How it works

```
TradingView Pine (r5)          Mac mini                       Tradovate
  9:30 alert  ──webhook──▶  homebase server  ──OSO order──▶  entry stop ±off
  (TREND gate lives          · validates geometry             SL/TP attached
   in the Pine script)       · one trade/day                  broker-side
                             · clock guard 12:55/15:55
                             · journal + fill grading
```

- The alert only carries the two entry prices. Offset / SL / TP / qty are
  frozen server-side in `homebase/config.py` (overridable via `config.json`).
- SL/TP ride on the entry as a broker-side OSO bracket — a dead app can never
  leave a naked position. TV being down can only ever cost an entry.
- The app's own clock cancels unfilled entries at 12:55 ET and force-flattens
  at 15:55 ET. One trade per strategy per day.
- `armed: false` (the default) = dry run: alerts are validated and journaled,
  nothing is placed.

## Layout

- `homebase/engine.py` — alert → orders → clock-guarded flat (the core)
- `homebase/config.py` — strategies (nq930, gc_nfp, the nq_* levels algos), account, master arm switch
- `homebase/broker/` — Tradovate REST + websocket adapter (battle-tested,
  extracted from the TradeCopier lineage at snapshot `0a75af5`)
- `homebase/risk.py` — trailing-drawdown meter (prop-account style)
- `homebase/secrets_store.py` — broker credentials (never in git)
- `homebase/.state/` — tokens, day states, journal (gitignored)

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # engine tests
```

Server + dashboard: coming next (`homebase/server.py`, uvicorn).

## Deploy (Mac mini)

Planned: `git clone` → venv → launchd keepalive → Tailscale for the UI →
Cloudflare Tunnel for the TradingView webhook. Documented here once built.

The desk plist must include `--timeout-graceful-shutdown 5` (regenerate from
the template), otherwise the chart service's SSE link makes desk restarts
hang until SIGKILL.

## Tick archive

`python -m homebase.ticks` (launchd `com.ramosquant.homebase-ticks`: hourly, at load, 17:20 and 05:30 ET) keeps
`~/futures_ticks` complete. Each run reads what the archive file and the chart service's live recording of every
recent session hold -- by the broker's tick id, one gap-free counter per contract -- and fetches from the broker's
tick history only what is missing, then merges everything into the archive file (never replaces; the live file is
only read). The broker keeps ticks from 00:00 UTC of the previous day only, so a session's first hours are gone at
20:00 ET on the session day: the pieces that leave first are fetched first. By day a run spends at most 45 pages and
never runs 09:20–09:35 ET; the live login only. A run with nothing to do says nothing.

- `homebase/.state/tick_coverage.json`: every root's last 30 sessions hour by hour -- holes, missing tick ids, and
  what only Massive can still fill ("needs_massive"); one summary line in `ticks.log`. `--coverage` rewrites it.
- `--rescan`: writes each recent file's hour-by-hour coverage into its manifest (`complete` there checks every hour).
- `--fill-from-massive --holes [--dry-run]`: the manual, one-shot Massive fill (homebase/tickmassive.py).

## Charts

`python -m homebase.charts` (launchd `com.ramosquant.homebase-charts`, port 8852) is the chart half
of the terminal: multi-chart layouts on live ticks — time/tick/volume/range bars, VWAP/EMA/SMA/VWMA/ADX,
session levels, footprint, delta, cumulative delta, big prints, volume profile. Its OWN process: it
cannot place orders and cannot slow the trading app. It records every live tick to
`~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`; past sessions come from the archive.

- Records live ticks for the tick archive's 15 symbols (NQ ES YM RTY GC SI CL ZN NG HG 6E 6J 6B BTC MBT); `--roots`
  narrows it. The tick job (below) merges this recording into the archive and fills what it missed.
- BTC and MBT (CME crypto) trade 24/7: a session every day, 18:00 → 18:00 ET, weekends included -- in the chart
  service and the tick job alike. Never run `research/massive_ticks.py convert` over dates the desk recorded (from
  2026-09-23): it files Massive's CME trade dates (a Monday file holds the weekend's trades) and replaces an incomplete
  desk file whole. `python -m homebase.ticks --fill-from-massive` cuts each session to its own hours and merges.
- Replay any archived session (records nothing): `python -m homebase.charts --replay 2026-09-22 --roots NQ,ES,YM --speed 20 --port 8853`
- md login: the Apex eval by default; `HOMEBASE_CHARTS_MD=live` switches to the live login.
- Budget: one chart request per root per connection; gap refills ≤ 60/hour, never 09:20–09:35 ET.
- A symbol the md feed refuses (no realtimeId, an error answer, no answer in 15 s, no front contract) is isolated: the
  other symbols stay subscribed, the status bar shows it "unavailable" (the reason in the tooltip), and it is asked again
  every 10 min outside 09:20–09:35 ET and on every reconnect. A socket that refuses every symbol is replaced, at most
  once per 10 min.
- Drawings (trend line, horizontal line, rectangle) are saved per symbol: `GET /api/drawings/{root}` returns a symbol's
  list, `PUT /api/drawings/{root}` replaces it (validated, ≤ 500 per symbol; writes from another site's page are
  refused). They live in `homebase/.state/charts/drawings.json`, beside the saved layouts (`layouts.json`). A page saves
  a symbol's whole list, so across open pages the last save wins: a page sees another page's edits only after a reload,
  and its next save overwrites them.
- Over Tailscale, serve port 8852 alongside 8850.
- Spec/plan: `docs/superpowers/specs/2026-09-25-live-charts-design.md`, `docs/superpowers/plans/2026-09-25-live-charts.md`;
  the TradingView-style page and drawing tools: `docs/superpowers/specs/2026-09-26-charts-tv-redesign-design.md`,
  `docs/superpowers/plans/2026-09-26-charts-tv-redesign.md`; Bitcoin (24/7): `docs/superpowers/specs/2026-09-26-charts-btc-24x7-design.md`,
  `docs/superpowers/plans/2026-09-26-charts-btc-24x7.md`.
