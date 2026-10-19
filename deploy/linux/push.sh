#!/bin/bash
# From the Mac: copy this checkout's tracked files to the server and (re)install the services there.
#   ./deploy/linux/push.sh [root@host]     default host: $HOMEBASE_SERVER
# Only git-tracked files go (so never config.json, .state, logins, venvs or tick data), and of research/
# only its .py code: the rest (~3 GB of heat-map cells, ledgers, specs) the live desk never reads.
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/home/homebase/ramos-quant-homebase
cd "$REPO"
ssh "$HOST" "install -d -o homebase -g homebase $DEST"
{ git ls-files | grep -v '^research/'; git ls-files 'research/*.py'; } |
  rsync -az --files-from=- ./ "$HOST:$DEST/"
ssh "$HOST" "chown -R homebase:homebase $DEST && $DEST/deploy/linux/install.sh"
