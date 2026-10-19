#!/bin/bash
# Install Homebase as systemd services on a Linux server (run as root, on the server).
# Idempotent: re-running updates and restarts. The Linux twin of deploy/install.sh.
#   sudo ./deploy/linux/install.sh          desk + charts (demo login only) + Lab runner + the doorman
#                                           for HOMEBASE VPS (nginx-homebase-vps.conf)
#   sudo ./deploy/linux/install.sh remove   stop and delete them
# Not installed here (Mac / research only): the pipeline, the tester prune, the sleep blocker.
# homebase/config.json and homebase/.state are never written by this script.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
USR="$(stat -c %U "$REPO")"
UNITS=(homebase.service homebase-charts.service homebase-labrun.service homebase-ticks.service homebase-ticks.timer)
# not the tick recorder's timer: it pages on the live login, which kicks the Mac's charts off it (the Mac's job keeps the archive)
STARTED=(homebase.service homebase-charts.service homebase-labrun.service)

if [ "${1:-}" = "remove" ]; then
  systemctl disable --now "${STARTED[@]}" homebase-ticks.timer 2>/dev/null || true
  for u in "${UNITS[@]}"; do rm -f "/etc/systemd/system/$u"; done
  systemctl daemon-reload
  echo "removed"
  exit 0
fi

[ -x "$REPO/.venv/bin/python" ] || sudo -u "$USR" python3 -m venv "$REPO/.venv"
sudo -u "$USR" "$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
sudo -u "$USR" mkdir -p "$REPO/homebase/.state"

# the doorman HOMEBASE VPS (the Mac app) comes in through: nginx on 127.0.0.2 only, the firewall untouched
command -v nginx >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx >/dev/null
rm -f /etc/nginx/sites-enabled/default
grep -q " homebase-vps$" /etc/hosts || echo "127.0.0.2 homebase-vps" >> /etc/hosts
install -m 644 "$REPO/deploy/linux/nginx-homebase-vps.conf" /etc/nginx/conf.d/homebase-vps.conf
nginx -t -q && systemctl enable --now nginx >/dev/null 2>&1 && systemctl reload nginx

for u in "${UNITS[@]}"; do
  sed -e "s|__REPO__|$REPO|g" -e "s|__USER__|$USR|g" "$REPO/deploy/linux/$u" > "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl disable --now homebase-ticks.timer >/dev/null 2>&1 || true
systemctl enable "${STARTED[@]}" >/dev/null 2>&1
systemctl restart "${STARTED[@]}"
sleep 2
systemctl --no-pager --lines=0 status "${STARTED[@]}" | grep -E "^●|Active:" || true
echo "installed — on the server: http://127.0.0.1:8850 · charts: http://127.0.0.1:8852"
