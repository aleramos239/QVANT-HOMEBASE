#!/bin/bash
# From the Mac: make the server's app data the same as this Mac's (the owner, 2026-10-18: "the exact same").
#   ./deploy/linux/mirror.sh [root@host]     default host: $HOMEBASE_SERVER
# Copies ~/.homebase, homebase/.state and all git-tracked research files, then the config. The Mac wins:
# what the server wrote itself (journal, days) is overwritten. The server's services are stopped meanwhile.
# Never copied: logins (credentials.json, *.tokens.json, *.device.json), the desk's own keys (*.key), locks,
# logs, and the chart bar cache (rebuilt from the ticks). The server's config always lands with
# armed=false and chart trading off: only the owner arms it, from its own page.
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
H=/home/homebase
DEST=$H/ramos-quant-homebase
SERVICES="homebase-labrun homebase-charts homebase"
cd "$REPO"

ssh "$HOST" "systemctl stop $SERVICES"
trap 'ssh "$HOST" "chown -R homebase:homebase $H && systemctl start $SERVICES"' EXIT

rsync -az --delete --exclude '*.lock' "$HOME/.homebase/" "$HOST:$H/.homebase/"
rsync -az --delete \
  --exclude credentials.json --exclude '*.tokens.json' --exclude '*.device.json' --exclude '*.key' \
  --exclude '*.lock' --exclude '*.log' --exclude '*.out' --exclude 'charts/cache/' \
  homebase/.state/ "$HOST:$DEST/homebase/.state/"
git ls-files research | rsync -az --files-from=- ./ "$HOST:$DEST/"

python3 -c "
import json, sys
c = json.load(open('homebase/config.json'))
c['armed'] = False
c['chart_trading']['enabled'] = False
json.dump(c, sys.stdout, indent=2)" | ssh "$HOST" "cat > $DEST/homebase/config.json"
echo "mirrored to $HOST (armed=false, chart trading off, no logins)"
