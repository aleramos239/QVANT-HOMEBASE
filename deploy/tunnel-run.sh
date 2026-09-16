#!/bin/bash
# Quick-tunnel runner: starts cloudflared against the hook-only port, waits
# for the public URL, and registers it with the app so the TV setup card
# always shows the CURRENT URL (quick tunnels rotate on every restart).
# The named-tunnel upgrade at mini-deploy time replaces only this file.
set -u
LOG="${TMPDIR:-/tmp}/homebase-tunnel.log"
: > "$LOG"
/opt/homebrew/bin/cloudflared tunnel --url http://127.0.0.1:8851 --no-autoupdate >> "$LOG" 2>&1 &
CF_PID=$!
trap 'kill $CF_PID 2>/dev/null' EXIT
for _ in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "${URL:-}" ] && break
  sleep 1
done
if [ -n "${URL:-}" ]; then
  for _ in $(seq 1 30); do
    if curl -s -X POST http://127.0.0.1:8850/api/hook-url \
        -H 'Content-Type: application/json' -d "{\"url\":\"$URL\"}" | grep -q '"ok":true'; then
      echo "registered $URL"
      break
    fi
    sleep 2
  done
fi
wait $CF_PID
