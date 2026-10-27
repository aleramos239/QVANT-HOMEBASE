#!/bin/bash
# Keep the server (the VPS Desk) on the Mac's main by itself (the owner, 2026-10-20: "every time you or any agent change
# something on the Mac homebase, it changes the VPS homebase too").
#   ./deploy/linux/vpssync.sh install     run every 2 minutes via launchd (this Mac only)
#   ./deploy/linux/vpssync.sh remove      stop it
#   ./deploy/linux/vpssync.sh status      main, what the server runs, and the last lines of the log
#   ./deploy/linux/vpssync.sh --dry-run   one pass that says what it would ship and restart, and sends nothing
#   ./deploy/linux/vpssync.sh --first     the FIRST sync of a server that has no commit recorded: every file, by hand,
#                                         with someone watching (the timer never makes that jump by itself)
#   ./deploy/linux/vpssync.sh             one pass (what launchd runs)
#
# What ships is the COMMITTED main (refs/heads/main), never the working tree: another session's unfinished edits never
# reach the server, whatever branch this checkout is on. One pass:
#   1. main's commit, against the one the server runs (/home/homebase/.homebase-sync/rev). Same: nothing to do.
#   2. A clean copy of the commit. The server's three programs must import from it (desk, charts, Lab runner), or the
#      commit is never shipped and a notification says so.
#   3. The files it changed since the server's commit (every file the first time, or when history was rewritten); of
#      research/ only its .py code, as push.sh. What they need: deploy/linux/vpssync_plan.py (services by the code's own
#      imports; a page file restarts nothing; a new requirements.txt blocks it until installed by hand).
#   4. The gate, on the server, as deploy/autopull.sh: every account flat with no working orders, and not 09:10-09:35 ET.
#      And when the Lab runner must restart, on a weekday 08:00-16:15 ET no Lab strategy may be booked on an account
#      (a runner restart ends a desk day that has begun). No: nothing is copied; the next pass asks again.
#   5. vpssync_remote.sh on the server: copy, delete, units, restart only those services, each one up and answering.
#      A failure is never retried for that commit (the next commit is shipped as usual).
set -uo pipefail
HOST="${HOMEBASE_SERVER:-root@144.202.51.163}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/home/homebase/ramos-quant-homebase
SYNC=/home/homebase/.homebase-sync
LABEL=com.ramosquant.homebase-vpssync
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STATE="$REPO/homebase/.state"
LOG="$STATE/vpssync.log"
PY="$REPO/.venv/bin/python"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST")

case "${1:-}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$STATE"
    sed "s|__REPO__|$REPO|g" "$REPO/deploy/$LABEL.plist.template" > "$PLIST"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "vpssync installed (every 2 min). log: $LOG"; exit 0 ;;
  remove)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"; echo "vpssync removed"; exit 0 ;;
  status)
    echo "main:   $(git -C "$REPO" log -1 --format='%h %s' refs/heads/main | cut -c1-110)"
    srv=$("${SSH[@]}" "cat $SYNC/rev 2>/dev/null; echo; cat $SYNC/failed 2>/dev/null; true")
    echo "server: $(echo "$srv" | sed -n 1p | cut -c1-12) (failed: $(echo "$srv" | sed -n 2p | cut -c1-12))"
    tail -n 8 "$LOG" 2>/dev/null; exit 0 ;;
esac
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
FIRST=0; [ "${1:-}" = "--first" ] && FIRST=1

mkdir -p "$STATE"
say() { echo "$(date '+%F %T') $*" >> "$LOG"; [ $DRY = 1 ] && echo "$*"; return 0; }
tell() { osascript -e "display notification \"$1\" with title \"Homebase VPS sync\"" >/dev/null 2>&1 || true; }

LOCK="$STATE/vpssync.lock"                             # one pass at a time (a pass can outlast the 2 minutes)
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK"; else exit 0; fi
fi
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vpssync.XXXXXX")"
cleanup() { find "$WORK" -delete 2>/dev/null; rmdir "$LOCK" 2>/dev/null; }
trap cleanup EXIT

cd "$REPO" || exit 1
REF="${HOMEBASE_SYNC_REF:-refs/heads/main}"           # (another commit only for a --dry-run test)
[ "$REF" != refs/heads/main ] && [ $DRY = 0 ] && { echo "HOMEBASE_SYNC_REF is for --dry-run only"; exit 1; }
REV="$(git rev-parse --verify -q "$REF^{commit}")" || { say "no main branch"; exit 0; }
SRV="$("${SSH[@]}" "cat $SYNC/rev 2>/dev/null; echo; cat $SYNC/failed 2>/dev/null; true")" || { say "server not reachable"; exit 0; }
RUN="$(echo "$SRV" | sed -n 1p)"; FAILED="$(echo "$SRV" | sed -n 2p)"
[ "$REV" = "$RUN" ] && { [ $DRY = 1 ] && echo "the server already runs main ${REV:0:8}"; exit 0; }
NOIMP="$STATE/vpssync.noimport"                        # the commit that would not import: told once, not retried
if [ "$REV" = "$FAILED" ] || [ "$REV" = "$(cat "$NOIMP" 2>/dev/null)" ]; then
  [ $DRY = 1 ] && echo "main ${REV:0:8} failed before: it is not shipped again"; exit 0
fi

# 2. a clean copy, and the server's programs must import from it
git archive "$REV" | tar -x -C "$WORK" || { say "${REV:0:8}: could not make a clean copy"; exit 0; }
if ! ERR=$(cd "$WORK" && "$PY" -c \
    "import homebase.server, homebase.charts.server, homebase.labrun.host, homebase.labrun.__main__, homebase.charts.__main__, homebase.tickjob" 2>&1); then
  say "${REV:0:8}: NOT SHIPPED -- it does not import: $(echo "$ERR" | tail -1)"
  [ $DRY = 1 ] || { echo "$REV" > "$NOIMP"; tell "main ${REV:0:8} does not import: not sent to the server"; }
  exit 0
fi

# 3. what changed, and what it needs
if [ -n "$RUN" ] && git cat-file -e "$RUN^{commit}" 2>/dev/null && git merge-base --is-ancestor "$RUN" "$REV"; then
  git diff --name-status --no-renames "$RUN" "$REV" > "$WORK/.changes"
elif [ $FIRST = 0 ] && [ $DRY = 0 ]; then
  say "${REV:0:8}: waits -- the server has no commit recorded (or history was rewritten): run vpssync.sh --first by hand"
  exit 0
else
  git ls-tree -r --name-only "$REV" | sed 's/^/M\t/' > "$WORK/.changes"     # first time, or history rewritten: all
fi
awk -F'\t' '$1 != "D" {print $2}' "$WORK/.changes" | grep -v -E '^research/' > "$WORK/.ship"
awk -F'\t' '$1 != "D" {print $2}' "$WORK/.changes" | grep -E '^research/.*\.py$' >> "$WORK/.ship"
awk -F'\t' '$1 == "D" {print $2}' "$WORK/.changes" > "$WORK/.deleted"
if [ ! -f "$WORK/deploy/linux/vpssync_plan.py" ] || [ ! -f "$WORK/deploy/linux/vpssync_remote.sh" ]; then
  say "${REV:0:8}: waits -- this commit has no deploy/linux/vpssync_plan.py or vpssync_remote.sh"; exit 0
fi
ASK=$(cat "$WORK/.ship" "$WORK/.deleted")
if grep -qx requirements.txt "$WORK/.ship" && [ "$("${SSH[@]}" "md5sum < $DEST/requirements.txt" | cut -c1-32)" = "$(md5 -q "$WORK/requirements.txt")" ]; then
  ASK=$(echo "$ASK" | grep -vx requirements.txt)    # the same packages the server already has: nothing to install
fi
PLAN="$("$PY" "$WORK/deploy/linux/vpssync_plan.py" "$WORK" $ASK)" \
  || { say "${REV:0:8}: waits -- the plan could not be read"; exit 0; }
if echo "$PLAN" | grep -q '^block '; then
  say "${REV:0:8}: waits -- $(echo "$PLAN" | sed -n 's/^block //p' | head -1)"; exit 0
fi
UNITS="$(echo "$PLAN" | sed -n 's/^unit //p' | tr '\n' ' ' | sed 's/ $//')"
SERVICES="$(echo "$PLAN" | sed -n 's/^service //p' | tr '\n' ' ' | sed 's/ $//')"
NFILES=$(wc -l < "$WORK/.ship" | tr -d ' '); NDEL=$(wc -l < "$WORK/.deleted" | tr -d ' ')

# 4. the gate, on the server
NEEDS_RUNNER=0; case " $SERVICES " in *" homebase-labrun "*) NEEDS_RUNNER=1 ;; esac
GATE=$("${SSH[@]}" "python3 - $NEEDS_RUNNER" <<'PY'
import json, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/New_York"))
m = now.hour * 60 + now.minute
if 9 * 60 + 10 <= m <= 9 * 60 + 35:
    print("no: 09:10-09:35 ET"); raise SystemExit
try:
    d = json.load(urllib.request.urlopen("http://127.0.0.1:8850/api/status", timeout=8))
except Exception as e:
    print("ok: the desk is not answering (%s)" % type(e).__name__); raise SystemExit
for k, a in (d.get("accounts") or {}).items():
    if a.get("open_position_count") or a.get("working_orders"):
        print("no: %s has a position or working orders" % (a.get("label") or k)); raise SystemExit
if sys.argv[1] == "1" and now.weekday() < 5 and 8 * 60 <= m <= 16 * 60 + 15:
    booked = [k for k, v in (d.get("book") or {}).items() if k.startswith("lab_") and v]
    if booked:
        print("no: %s is booked on an account (a runner restart would end its day)" % booked[0]); raise SystemExit
print("ok")
PY
) || { say "${REV:0:8}: server not reachable for the gate"; exit 0; }

WHAT="${REV:0:8}: $NFILES files, $NDEL deleted, units [${UNITS}], restart [${SERVICES:-nothing}]"
if [ $DRY = 1 ]; then
  echo "$WHAT"; echo "gate: $GATE"; head -n 15 "$WORK/.ship" | sed 's/^/  /'; [ "$NFILES" -gt 15 ] && echo "  ..."
  exit 0
fi
if [ "${GATE%%:*}" != "ok" ]; then say "$WHAT -- waits: $GATE"; exit 0; fi

# 5. ship
(cd "$WORK" && tar -cf "$WORK/.ship.tar" -T .ship) || { say "${REV:0:8}: could not pack"; exit 0; }
NAME="vpssync-${REV:0:12}"
scp -q -o BatchMode=yes "$WORK/.ship.tar" "$HOST:/tmp/$NAME.tar" && scp -q -o BatchMode=yes "$WORK/.deleted" "$HOST:/tmp/$NAME.del" \
  || { say "${REV:0:8}: upload failed"; exit 0; }
OUT=$("${SSH[@]}" "bash -s -- '$REV' '/tmp/$NAME.tar' '/tmp/$NAME.del' '$UNITS' '$SERVICES'" < "$WORK/deploy/linux/vpssync_remote.sh" 2>&1)
if [ $? -eq 0 ]; then
  say "$WHAT -- shipped. $(echo "$OUT" | tail -1)"
else
  say "$WHAT -- FAILED: $(echo "$OUT" | tail -2 | tr '\n' ' ')"
  tell "main ${REV:0:8} failed on the server: $(echo "$OUT" | tail -1)"
fi
