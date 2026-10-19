#!/bin/bash
# From the Mac, every few minutes (launchd, deploy/com.ramosquant.homebase-serversync.plist.template): keep the server's
# Desk in step with the Mac (the owner, 2026-10-18: "if i add a strategy it also shows on the server").
# Spec: docs/superpowers/specs/2026-10-18-one-desk-on-the-server-design.md
#   ./deploy/linux/sync.sh [root@host]     default host: $HOMEBASE_SERVER
# Every 5 min:  sed -e "s|__REPO__|$PWD|g" -e "s|__HOST__|root@<host>|g" deploy/com.ramosquant.homebase-serversync.plist.template \
#                 > ~/Library/LaunchAgents/com.ramosquant.homebase-serversync.plist
#               launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ramosquant.homebase-serversync.plist
# Stop it:      launchctl bootout gui/$(id -u)/com.ramosquant.homebase-serversync
#
# PRACTICE (no homebase/.state/onedesk.on): the Mac is the real Desk, the server practises beside it. Mac -> server,
#   the Mac wins: the Lab strategies on the Desk (records, archive, groups), drafts, ideas, the Lab side switch, chart
#   layouts, and the config -- always with armed=false and chart trading off. Only a changed config restarts the
#   server's desk (it re-reads the strategy store by itself every 2 s).
# ONE DESK (onedesk.on, set by switch.sh): the server is the Desk and owns its config. Mac -> server: what the Lab
#   writes (records, archive, groups, drafts, ideas). Server -> Mac: what the Desk and its runner write (days, journal,
#   heartbeat, the desk's sidecars), for the Mac Lab's Desk panels. Never the config either way.
# Either way the server keeps its own logins and keys.
# shortcut: a file deleted on the Mac outside desklab/strategies/ideas stays on the server; mirror.sh clears that.
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
H=/home/homebase
DEST=$H/ramos-quant-homebase
LAB="$HOME/.homebase/desklab"
RS=(rsync -az --bwlimit=100 --timeout=60)
cd "$REPO"
ONEDESK=0; [ -f homebase/.state/onedesk.on ] && ONEDESK=1

# the Lab's side of the store (a sidecar is the desk's: the Mac's own only while the Mac is the Desk)
SIDECARS=(); [ $ONEDESK = 1 ] && SIDECARS=(--exclude '/*.desk.json')
"${RS[@]}" --delete --include '/.archive/' --include '/.archive/**' --exclude '/*/' --exclude '/runner.json' \
  --exclude '/desk.lock' ${SIDECARS[@]+"${SIDECARS[@]}"} "$LAB/" "$HOST:$H/.homebase/desklab/"
"${RS[@]}" --delete "$HOME/.homebase/strategies" "$HOME/.homebase/ideas" "$HOST:$H/.homebase/"
( cd "$HOME/.homebase" && "${RS[@]}" deskgroups.json arsenal.json tester_keep.json tester_slots.json "$HOST:$H/.homebase/" )
OWN="$H/.homebase/desklab $H/.homebase/strategies $H/.homebase/ideas $H/.homebase/*.json"

if [ $ONEDESK = 1 ]; then
  "${RS[@]}" --exclude '/.archive/' --include '/*/' --include '/*/**' --include '/runner.json' --include '/*.desk.json' \
    --exclude '*' "$HOST:$H/.homebase/desklab/" "$LAB/"
  ssh "$HOST" "chown -R homebase:homebase $OWN"
  echo "$(date '+%F %T') synced (one Desk)"
  exit 0
fi

( cd homebase/.state && "${RS[@]}" lab_desk.on data_watch.json "$HOST:$DEST/homebase/.state/" &&
  cd charts && "${RS[@]}" layouts.json drawings.json templates.json "$HOST:$DEST/homebase/.state/charts/" )
python3 -c "
import json, sys
c = json.load(open('homebase/config.json'))
c['armed'] = False
c['chart_trading']['enabled'] = False
json.dump(c, sys.stdout, indent=2)" | ssh "$HOST" "
cat > /tmp/hb-config.json
chown -R homebase:homebase $OWN $DEST/homebase/.state/lab_desk.on $DEST/homebase/.state/data_watch.json \
  $DEST/homebase/.state/charts/*.json
python3 -c 'import json, sys; sys.exit(json.load(open(\"/tmp/hb-config.json\")) != json.load(open(\"$DEST/homebase/config.json\")))' ||
  { install -o homebase -g homebase -m 644 /tmp/hb-config.json $DEST/homebase/config.json &&
    systemctl restart homebase homebase-labrun && echo \"\$(date '+%F %T') config changed: server desk restarted\"; }"
echo "$(date '+%F %T') synced"
