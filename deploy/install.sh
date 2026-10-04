#!/bin/bash
# Install Homebase as always-on launchd services on THIS machine (laptop or
# mini — same script). Idempotent: re-running updates and restarts.
#   ./deploy/install.sh          install/refresh app + ticks + charts + sleep-blocker
#   ./deploy/install.sh remove   unload everything
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS=(com.ramosquant.homebase com.ramosquant.homebase-awake com.ramosquant.homebase-ticks com.ramosquant.homebase-charts)
# no longer installed; still unloaded and deleted so an old install gets cleaned
RETIRED=(com.ramosquant.homebase-tunnel)

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

for l in com.ramosquant.homebase com.ramosquant.homebase-ticks com.ramosquant.homebase-charts; do
  sed "s|__REPO__|$REPO|g" "$REPO/deploy/$l.plist.template" > "$AGENTS/$l.plist"
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
