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
