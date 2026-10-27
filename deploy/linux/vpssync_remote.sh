#!/bin/bash
# The server's half of deploy/linux/vpssync.sh (sent over ssh on stdin by the Mac, from the commit being shipped, so the
# steps are always that commit's own). Run as root:
#   bash -s -- <rev> <tarball> <deleted-list> "<units>" "<services>"
# Puts the commit's changed files in place, removes the ones it deleted, installs changed unit files, restarts only the
# named services (charts, desk, runner, in that order) and checks each is up and answering. All good: the commit is
# written to $SYNC/rev. Any check fails: the commit is written to $SYNC/failed and the exit is non-zero -- the Mac never
# ships that commit again and says so. The gate (vpssync_gate.py) is asked again before the files go in place and before
# the desk and the runner restart: a position or order that appeared since the Mac asked exits 3, no marker written --
# the next pass ships the same commit again (a copy is safe to repeat). A "no" before the copy touches nothing; a "no"
# at a restart (a position opened during the copy) leaves the files on disk and the desk/runner not restarted yet,
# running their old code until the next pass restarts them (a lazy import in that window is the accepted small risk).
set -euo pipefail
REV="$1" TAR="$2" DEL="$3" UNITS="$4" SERVICES="$5"
DEST="${VPSSYNC_DEST:-/home/homebase/ramos-quant-homebase}"     # (the overrides are for its test only)
USR="${VPSSYNC_USER:-homebase}"
SYNC="${VPSSYNC_SYNC:-/home/homebase/.homebase-sync}"
mkdir -p "$SYNC"

GATE="${VPSSYNC_GATE:-python3}"                         # (the override is for its test only)
gate_ok() {                                            # exit 3 unless the desk is flat and answering
  local g="" v needs=0
  for g in "$STAGE/deploy/linux/vpssync_gate.py" "$DEST/deploy/linux/vpssync_gate.py"; do [ -f "$g" ] && break; g=""; done
  case " $SERVICES " in *" homebase-labrun "*) needs=1 ;; esac
  [ -n "$g" ] && v=$($GATE "$g" "$needs" 2>&1) || v="no: no gate script"
  [ "${v%%:*}" = ok ] || { find "$STAGE" -delete 2>/dev/null || true; echo "waits: $v"; exit 3; }
}

fail() { echo "$REV" > "$SYNC/failed"; echo "FAILED: $*"; exit 1; }

STAGE="$(mktemp -d "$(dirname "$DEST")/.vpssync-stage.XXXXXX")"
tar -x -C "$STAGE" -f "$TAR" || fail "the files did not unpack"
case " $SERVICES " in *" homebase "*|*" homebase-labrun "*) gate_ok ;; esac
chown -R "$USR:$(id -gn "$USR")" "$STAGE"              # only the shipped files, not a recursive chown of the whole checkout
nice -n 10 cp -a "$STAGE"/. "$DEST"/ || fail "the files could not be copied"
find "$STAGE" -delete
rm -f "$TAR"
while IFS= read -r p; do                               # only paths inside the checkout, never an absolute or ../ one
  case "$p" in ""|/*|*..*) continue ;; esac
  rm -f -- "$DEST/$p"
done < "$DEL"
rm -f "$DEL"

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
  case "$s" in homebase|homebase-labrun) gate_ok ;; esac
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
