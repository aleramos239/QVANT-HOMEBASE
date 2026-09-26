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

- Records live ticks for the same 10 symbols as the nightly archive (NQ ES YM RTY GC SI CL ZN NG HG); `--roots` narrows it.
- Replay any archived session (records nothing): `python -m homebase.charts --replay 2026-09-22 --roots NQ,ES,YM --speed 20 --port 8853`
- md login: the Apex eval by default; `HOMEBASE_CHARTS_MD=live` switches to the live login.
- Budget: one chart request per root per connection; gap refills ≤ 60/hour, never 09:20–09:35 ET.
- Over Tailscale, serve port 8852 alongside 8850.
- Spec/plan: `docs/superpowers/specs/2026-09-25-live-charts-design.md`, `docs/superpowers/plans/2026-09-25-live-charts.md`.
