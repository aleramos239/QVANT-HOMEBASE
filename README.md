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
- `homebase/config.py` — strategies (nq930, ym930), account, master arm switch
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

## Charts

`python -m homebase.charts` (launchd `com.ramosquant.homebase-charts`, port 8852) is the chart half
of the terminal: multi-chart layouts on live ticks — time/tick/volume/range bars, VWAP/EMA/SMA/VWMA/ADX,
session levels, footprint, delta, cumulative delta, big prints, volume profile. Its OWN process: it
cannot place orders and cannot slow the trading app. It records every live tick to
`~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`; past sessions come from the archive.

- Records live ticks for the nightly archive's 10 symbols (NQ ES YM RTY GC SI CL ZN NG HG) plus Bitcoin (BTC); `--roots` narrows it.
- BTC (CME crypto) trades 24/7: a session every day, 18:00 → 18:00 ET, weekends included. Only the chart service records
  it (the nightly job's weekday 18:00 → 17:00 fetch cannot). Never Massive-backfill BTC over dates the chart service
  recorded: the store prefers a complete archive file to the live one, and Massive files follow CME trade dates (a
  Monday file can hold the weekend's trades), so the weekend would be charted twice.
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
