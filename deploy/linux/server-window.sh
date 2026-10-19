#!/bin/bash
# From the Mac: open a separate Chrome window that sees the SERVER's Homebase exactly as the server does --
# localhost:8850 / :8852 in that window are the server's, so every page, tab and link works unchanged
# (a plain port tunnel cannot: the pages build their links as <same host>:8850 / :8852).
#   ./deploy/linux/server-window.sh [root@host]     default host: $HOMEBASE_SERVER
# How: an SSH SOCKS proxy on 127.0.0.1:1080 and a Chrome profile of its own that sends even localhost through it.
set -euo pipefail
HOST="${1:-${HOMEBASE_SERVER:?give root@host or set HOMEBASE_SERVER}}"
PORT=1080
nc -z 127.0.0.1 "$PORT" 2>/dev/null ||
  ssh -f -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -D "127.0.0.1:$PORT" "$HOST"
open -na "Google Chrome" --args \
  --user-data-dir="$HOME/Library/Application Support/Homebase Server Window" \
  --proxy-server="socks5://127.0.0.1:$PORT" --proxy-bypass-list="<-loopback>" \
  --no-first-run --new-window http://localhost:8850/
