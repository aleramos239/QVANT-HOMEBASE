#!/bin/bash
# The server's half of deploy/linux/vpssync.sh (sent over ssh on stdin by the Mac, from the commit being shipped, so the
# steps are always that commit's own). Run as root:
#   bash -s -- <rev> <tarball> <deleted-list> "<units>" "<services>"
# Puts the commit's changed files in place, removes the ones it deleted, installs changed unit files, restarts only the
# named services (charts, desk, runner, in that order) and checks each is up and answering. All good: the commit is
# written to $SYNC/rev. Any check fails: the commit is written to $SYNC/failed and the exit is non-zero -- the Mac never
# ships that commit again and says so.
set -euo pipefail
REV="$1" TAR="$2" DEL="$3" UNITS="$4" SERVICES="$5"
DEST="${VPSSYNC_DEST:-/home/homebase/ramos-quant-homebase}"     # (the overrides are for its test only)
USR="${VPSSYNC_USER:-homebase}"
SYNC="${VPSSYNC_SYNC:-/home/homebase/.homebase-sync}"
mkdir -p "$SYNC"

fail() { echo "$REV" > "$SYNC/failed"; echo "FAILED: $*"; exit 1; }

STAGE="$(mktemp -d "$(dirname "$DEST")/.vpssync-stage.XXXXXX")"
tar -x -C "$STAGE" -f "$TAR" || fail "the files did not unpack"
cp -a "$STAGE"/. "$DEST"/ || fail "the files could not be copied"
find "$STAGE" -delete
rm -f "$TAR"
while IFS= read -r p; do                               # only paths inside the checkout, never an absolute or ../ one
  case "$p" in ""|/*|*..*) continue ;; esac
  rm -f -- "$DEST/$p"
done < "$DEL"
rm -f "$DEL"
chown -R "$USR:$(id -gn "$USR")" "$DEST"

for u in $UNITS; do                                    # as install.sh renders them
  sed -e "s|__REPO__|$DEST|g" -e "s|__USER__|$USR|g" "$DEST/deploy/linux/$u" > "/etc/systemd/system/$u"
done
if [ -n "$UNITS" ]; then systemctl daemon-reload; fi

up() {                                                 # <what> <seconds> <command...>: true once the command succeeds
  local what="$1" n="$2"; shift 2
  for _ in $(seq 1 "$n"); do "$@" >/dev/null 2>&1 && return 0; sleep 1; done
  fail "$what did not come back"
}
for s in homebase-charts homebase homebase-labrun; do
  case " $SERVICES " in *" $s "*) ;; *) continue ;; esac
  before=$(stat -c %Y /home/homebase/.homebase/desklab/runner.json 2>/dev/null || echo 0)
  systemctl restart "$s"
  case "$s" in
    homebase-charts) up "the chart service" 120 curl -fsS -m 3 -H "Origin: http://localhost:8850" http://127.0.0.1:8852/api/tester/desklab ;;
    homebase)        up "the desk" 90 curl -fsS -m 3 http://127.0.0.1:8850/api/status ;;
    homebase-labrun) up "the Lab runner" 60 bash -c "systemctl is-active -q homebase-labrun && [ \$(stat -c %Y /home/homebase/.homebase/desklab/runner.json) -gt $before ]" ;;
  esac
done
echo "$REV" > "$SYNC/rev"
rm -f "$SYNC/failed"
echo "OK $REV units=[$UNITS] restarted=[$SERVICES]"
