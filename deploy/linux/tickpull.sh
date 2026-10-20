#!/bin/bash
# From the Mac: bring the VPS's finished tick-archive days into ~/futures_ticks (the VPS runs the hourly
# tick job since 2026-10-20: it holds the live md login, and a second machine on it kicks the VPS feed off).
# Only a better day replaces the Mac's (deploy/linux/tickmerge.py); live recordings stay each machine's own.
#   ./deploy/linux/tickpull.sh [root@host]        (launchd com.ramosquant.homebase-tickpull runs it hourly)
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:-root@144.202.51.163}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$HOME/.homebase/vps_ticks"
mkdir -p "$STAGE"
echo "[tickpull] $(date '+%F %T') from $HOST"
rsync -a --timeout=120 --exclude='*.live*' --include='*/' --include='*.csv.gz' --include='*.json' --exclude='*' \
  "$HOST:/home/homebase/futures_ticks/" "$STAGE/"
/usr/bin/python3 "$REPO/deploy/linux/tickmerge.py" "$STAGE" "$HOME/futures_ticks" --lock "$REPO/homebase/.state/ticks.lock"
