#!/bin/bash
# Install Homebase as always-on launchd services on THIS machine (laptop or
# mini — same script). Idempotent: re-running updates and restarts.
#   ./deploy/install.sh          install/refresh app + ticks + charts + sleep-blocker + the pipeline's runner
#                                + the Lab strategies' runner at login (reload it outside the sessions only)
#                                + the weekly prune of old tester output
#   ./deploy/install.sh remove   unload everything
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS=(com.ramosquant.homebase com.ramosquant.homebase-awake com.ramosquant.homebase-ticks com.ramosquant.homebase-charts com.ramosquant.homebase-pipeline com.ramosquant.homebase-labrun com.ramosquant.homebase-prune)
# no longer installed; still unloaded and deleted so an old install gets cleaned
RETIRED=(com.ramosquant.homebase-tunnel)
# One Desk on the server (docs/superpowers/specs/2026-10-18-one-desk-on-the-server-design.md, set by
# deploy/linux/switch.sh): the tunnel to the server's desk holds 8850, this Mac's desk is a logins-only helper on
# 8849, and the Lab strategies' runner runs on the server only.
PORT=8850
if [ -f "$REPO/homebase/.state/onedesk.on" ]; then
  PORT=8849
  LABELS=(com.ramosquant.homebase com.ramosquant.homebase-awake com.ramosquant.homebase-ticks com.ramosquant.homebase-charts com.ramosquant.homebase-pipeline com.ramosquant.homebase-prune)
  RETIRED+=(com.ramosquant.homebase-labrun)
fi

if [ "${1:-}" = "remove" ]; then
  for l in "${LABELS[@]}" "${RETIRED[@]}"; do
    launchctl bootout "gui/$(id -u)/$l" 2>/dev/null || true
    rm -f "$AGENTS/$l.plist"
  done
  echo "removed"
  exit 0
fi

[ -x "$REPO/.venv/bin/python" ] || {
  python3 -m venv "$REPO/.venv"
  "$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
}
mkdir -p "$AGENTS" "$REPO/homebase/.state"

for l in "${RETIRED[@]}"; do
  launchctl bootout "gui/$(id -u)/$l" 2>/dev/null || true
  rm -f "$AGENTS/$l.plist"
done

for l in "${LABELS[@]}"; do
  [ "$l" = com.ramosquant.homebase-awake ] && continue    # written below
  sed -e "s|__REPO__|$REPO|g" -e "s|__PORT__|$PORT|g" "$REPO/deploy/$l.plist.template" > "$AGENTS/$l.plist"
done

# sleep blocker: keeps the machine awake while on AC power (a closed laptop
# lid on battery still sleeps — that is what the mini is for)
cat > "$AGENTS/com.ramosquant.homebase-awake.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ramosquant.homebase-awake</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/caffeinate</string><string>-s</string><string>-i</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
EOF

for l in "${LABELS[@]}"; do
  launchctl bootout "gui/$(id -u)/$l" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$l.plist"
done
sleep 2
launchctl list | grep ramosquant || true
echo "installed — dashboard: http://localhost:8850 · charts: http://localhost:8852"
