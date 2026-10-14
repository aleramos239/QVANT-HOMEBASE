#!/bin/bash
# Keep THIS machine's app the same as GitHub main (for the mac mini).
#   ./deploy/autopull.sh install    run every 5 min via launchd (this machine only)
#   ./deploy/autopull.sh remove     stop it
#   ./deploy/autopull.sh            one pass now (what launchd runs)
# One pass: fast-forward main. Restart the desk + charts only when the code under homebase/
# changed AND it is safe: every account flat with no working orders, not 09:10-09:35 ET, no
# tester job running. If not safe it waits and tries again next pass. Never merges, never
# resets: local edits that block a fast-forward are logged and left alone.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=com.ramosquant.homebase-autopull
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$REPO/homebase/.state/autopull.log"
REV="$REPO/homebase/.state/autopull.rev"     # the commit the running services were started on

if [ "${1:-}" = "install" ]; then
  mkdir -p "$HOME/Library/LaunchAgents" "$REPO/homebase/.state"
  sed "s|__REPO__|$REPO|g" "$REPO/deploy/$LABEL.plist.template" > "$PLIST"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  git -C "$REPO" rev-parse HEAD > "$REV"
  echo "autopull installed (every 5 min). log: $LOG"
  exit 0
fi
if [ "${1:-}" = "remove" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "autopull removed"; exit 0
fi

say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
cd "$REPO" || exit 1
mkdir -p "$(dirname "$LOG")"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { say "not on main, skip"; exit 0; }

git fetch -q origin main 2>>"$LOG" || { say "fetch failed"; exit 0; }
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  if git merge-base --is-ancestor HEAD origin/main; then
    git merge -q --ff-only origin/main >>"$LOG" 2>&1 \
      && say "pulled to $(git rev-parse --short HEAD)" \
      || { say "pull blocked by local edits, left alone"; exit 0; }
  else
    say "local main has commits GitHub does not (or diverged): not touching"; exit 0
  fi
fi

HEAD_REV="$(git rev-parse HEAD)"
RUN_REV="$(cat "$REV" 2>/dev/null || echo "$HEAD_REV")"
[ "$HEAD_REV" = "$RUN_REV" ] && exit 0
# restart only if app code changed since the running revision
if ! git diff --name-only "$RUN_REV" "$HEAD_REV" 2>/dev/null | grep -q '^homebase/'; then
  echo "$HEAD_REV" > "$REV"; say "no app code change, no restart"; exit 0
fi

# gate: flat accounts, outside the open, no tester job
SAFE=$(python3 - <<'PY'
import json, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/New_York"))
m = now.hour * 60 + now.minute
if 9 * 60 + 10 <= m <= 9 * 60 + 35:
    print("no: 09:10-09:35 ET"); raise SystemExit
try:
    d = json.load(urllib.request.urlopen("http://127.0.0.1:8850/api/status", timeout=8))
except Exception as e:
    print("ok: desk not answering (%s)" % e); raise SystemExit
for k, a in (d.get("accounts") or {}).items():
    if a.get("open_position_count") or a.get("working_orders"):
        print("no: %s has a position or working orders" % a.get("label", k)); raise SystemExit
print("ok")
PY
)
if [ "${SAFE%%:*}" != "ok" ]; then say "restart waits: $SAFE"; exit 0; fi
if pgrep -f "bp.py _job" >/dev/null; then say "restart waits: a tester/pipeline job is running"; exit 0; fi

say "restarting desk + charts on $(git rev-parse --short HEAD)"
launchctl kickstart -k "gui/$(id -u)/com.ramosquant.homebase" >>"$LOG" 2>&1
launchctl kickstart -k "gui/$(id -u)/com.ramosquant.homebase-charts" >>"$LOG" 2>&1
echo "$HEAD_REV" > "$REV"
say "done"
