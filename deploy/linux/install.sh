#!/bin/bash
# Install Homebase as systemd services on a Linux server (run as root, on the server).
# Idempotent: re-running updates and restarts. The Linux twin of deploy/install.sh.
#   sudo ./deploy/linux/install.sh          desk + charts + Lab runner + the tick recorder's timer
#   sudo ./deploy/linux/install.sh remove   stop and delete them
# Not installed here (Mac / research only): the pipeline, the tester prune, the sleep blocker.
# homebase/config.json and homebase/.state are never written by this script.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
USR="$(stat -c %U "$REPO")"
UNITS=(homebase.service homebase-charts.service homebase-labrun.service homebase-ticks.service homebase-ticks.timer)
STARTED=(homebase.service homebase-charts.service homebase-labrun.service homebase-ticks.timer)

if [ "${1:-}" = "remove" ]; then
  systemctl disable --now "${STARTED[@]}" 2>/dev/null || true
  for u in "${UNITS[@]}"; do rm -f "/etc/systemd/system/$u"; done
  systemctl daemon-reload
  echo "removed"
  exit 0
fi

[ -x "$REPO/.venv/bin/python" ] || sudo -u "$USR" python3 -m venv "$REPO/.venv"
sudo -u "$USR" "$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
sudo -u "$USR" mkdir -p "$REPO/homebase/.state"

for u in "${UNITS[@]}"; do
  sed -e "s|__REPO__|$REPO|g" -e "s|__USER__|$USR|g" "$REPO/deploy/linux/$u" > "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable "${STARTED[@]}" >/dev/null 2>&1
systemctl restart "${STARTED[@]}"
sleep 2
systemctl --no-pager --lines=0 status "${STARTED[@]}" | grep -E "^●|Active:" || true
echo "installed — on the server: http://127.0.0.1:8850 · charts: http://127.0.0.1:8852"
