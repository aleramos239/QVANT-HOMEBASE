#!/bin/bash
# From the Mac: send this Mac's live Level 2 book to the server's charts, so the VPS DOM shows it, or stop.
# (homebase/charts/depthrelay.py: Level 2 needs the live login, which Tradovate serves to one connection: the Mac's.)
#   ./deploy/linux/depthrelay.sh on  [root@host]    the ssh tunnel + the pusher, as launchd jobs (kept alive)
#   ./deploy/linux/depthrelay.sh off                both gone
# The server's charts take the book only with HOMEBASE_DEPTH_RELAY_IN=1 (deploy/linux/homebase-charts.service).
set -euo pipefail
MODE="${1:?on or off}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
JOBS=(com.ramosquant.homebase-depthtunnel com.ramosquant.homebase-depthrelay)

for j in "${JOBS[@]}"; do launchctl bootout "gui/$(id -u)/$j" 2>/dev/null || true; done
if [ "$MODE" = off ]; then
  for j in "${JOBS[@]}"; do rm -f "$AGENTS/$j.plist"; done
  echo "depth relay off"
  exit 0
fi
HOST="${2:-${HOMEBASE_SERVER:-root@144.202.51.163}}"
for j in "${JOBS[@]}"; do
  sed -e "s|__REPO__|$REPO|g" -e "s|__HOST__|$HOST|g" "$REPO/deploy/$j.plist.template" > "$AGENTS/$j.plist"
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$j.plist"
done
echo "depth relay on -> $HOST (logs: homebase/.state/depthtunnel.log, depthrelay.log)"
