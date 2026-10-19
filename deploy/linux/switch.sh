#!/bin/bash
# From the Mac: make the server THE Desk, or give the Desk back to the Mac.
# Spec: docs/superpowers/specs/2026-10-18-one-desk-on-the-server-design.md
#   ./deploy/linux/switch.sh on  [root@host]    1. you Disarm the Mac's Desk  2. run this  3. you Arm in the Desk tab
#   ./deploy/linux/switch.sh off [root@host]    1. you Disarm in the Desk tab 2. run this  3. you Arm the Mac's Desk
# It never arms or disarms anything: it refuses while the Desk it hands over is armed, holds a position or a
# working order, and on weekdays 08:00-16:15 ET.
set -euo pipefail
MODE="${1:?on or off}"
HOST="${2:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
DESK=com.ramosquant.homebase LABRUN=com.ramosquant.homebase-labrun TUNNEL=com.ramosquant.homebase-servertunnel
STATE="$REPO/homebase/.state"
DEST=/home/homebase/ramos-quant-homebase
cd "$REPO"

die() { echo "switch: $*" >&2; exit 1; }
# the desk answering on <url> as JSON: armed, connected accounts, open positions + working orders
desk() { curl -s --max-time 10 "$1/api/status" | python3 -c '
import json, sys
d = json.load(sys.stdin); a = d["accounts"].values()
print(d["armed"], sum(1 for x in a if x["connected"]), len(d["accounts"]),
      sum(x["open_position_count"] or 0 for x in a) + sum(len(x["working_orders"] or []) for x in a))'; }
handover_ok() {   # $1 = what the Desk is called for the owner, $2.. = its status line
  [ $# -eq 5 ] || die "$1 did not answer."
  local who="$1" armed="$2" open="$5"
  [ "$armed" = False ] || die "$who is ARMED. Click Disarm there first."
  [ "$open" = 0 ] || die "$who still holds $open position(s) / working order(s). Switch when flat."
}
[ "$(TZ=America/New_York date +%u)" -le 5 ] && [ "$(TZ=America/New_York date +%H%M)" -ge 0800 ] &&
  [ "$(TZ=America/New_York date +%H%M)" -le 1615 ] && die "not during desk hours (weekdays 08:00-16:15 ET)."
mac_desk() {   # the Mac's desk on port $1 (8850 = THE Desk, 8849 = the logins-only helper)
  sed -e "s|__REPO__|$REPO|g" -e "s|__PORT__|$1|g" deploy/$DESK.plist.template > "$AGENTS/$DESK.plist"
  launchctl bootout "gui/$(id -u)/$DESK" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$DESK.plist"
}
wait_desk() { for _ in $(seq 30); do curl -s -o /dev/null --max-time 3 "$1/api/status" && return 0; sleep 2; done; die "no desk on $1"; }

if [ "$MODE" = on ]; then
  [ -f "$STATE/onedesk.on" ] && die "already on: the server is the Desk."
  read -r -a MAC <<< "$(desk http://127.0.0.1:8850)"; handover_ok "The Mac's Desk" "${MAC[@]}"
  read -r -a SRV <<< "$(ssh "$HOST" "curl -s --max-time 10 http://127.0.0.1:8850/api/status" | python3 -c '
import json, sys
d = json.load(sys.stdin); a = d["accounts"].values()
print(d["armed"], sum(1 for x in a if x["connected"]), len(d["accounts"]))')"
  [ ${#SRV[@]} -eq 3 ] || die "the server's Desk did not answer."
  [ "${SRV[1]}" = "${SRV[2]}" ] || die "the server has only ${SRV[1]} of ${SRV[2]} accounts connected. Reconnect them in the server window."
  "$REPO/deploy/linux/sync.sh" "$HOST"                       # last practice sync: the server has every strategy
  # the chart pages' trade buttons send this Mac's desk key: the server's desk must hold the same one
  scp -q "$STATE/desk.key" "$HOST:$DEST/homebase/.state/desk.key"
  ssh "$HOST" "chown homebase:homebase $DEST/homebase/.state/desk.key && chmod 600 $DEST/homebase/.state/desk.key && systemctl restart homebase homebase-labrun"
  touch "$STATE/onedesk.on"
  rm -f "$STATE/lab_desk.on"                                  # the helper desk never touches the Lab strategies
  launchctl bootout "gui/$(id -u)/$LABRUN" 2>/dev/null || true; rm -f "$AGENTS/$LABRUN.plist"
  mac_desk 8849
  sed -e "s|__REPO__|$REPO|g" -e "s|__HOST__|$HOST|g" deploy/$TUNNEL.plist.template > "$AGENTS/$TUNNEL.plist"
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$TUNNEL.plist"
  wait_desk http://127.0.0.1:8850
  echo "switch: done. The Desk tab is now the SERVER's Desk (disarmed). Click Arm there when you are ready."
elif [ "$MODE" = off ]; then
  [ -f "$STATE/onedesk.on" ] || die "already off: the Mac is the Desk."
  read -r -a SRV <<< "$(desk http://127.0.0.1:8850)"; handover_ok "The server's Desk" "${SRV[@]}"
  launchctl bootout "gui/$(id -u)/$TUNNEL" 2>/dev/null || true; rm -f "$AGENTS/$TUNNEL.plist"
  rm -f "$STATE/onedesk.on"
  echo "the Mac is the Desk again (deploy/linux/switch.sh off)" > "$STATE/lab_desk.on"
  mac_desk 8850
  sed "s|__REPO__|$REPO|g" deploy/$LABRUN.plist.template > "$AGENTS/$LABRUN.plist"
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$LABRUN.plist"
  wait_desk http://127.0.0.1:8850
  "$REPO/deploy/linux/sync.sh" "$HOST"                       # back to practice: the server's config disarmed again
  echo "switch: done. The Desk tab is the Mac's Desk again (disarmed). Click Arm there when you are ready."
else
  die "on or off"
fi
