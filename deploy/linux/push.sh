#!/bin/bash
# From the Mac: copy this checkout's tracked files to the server and (re)install the services there.
#   ./deploy/linux/push.sh [root@host]     default host: $HOMEBASE_SERVER
# Only git-tracked files go (so never config.json, .state, logins, venvs or tick data).
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/home/homebase/ramos-quant-homebase
cd "$REPO"
ssh "$HOST" "install -d -o homebase -g homebase $DEST"
git ls-files -z | rsync -az --from0 --files-from=- --chown=homebase:homebase ./ "$HOST:$DEST/"
ssh "$HOST" "$DEST/deploy/linux/install.sh"
