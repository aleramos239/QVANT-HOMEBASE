#!/bin/bash
# Build the Homebase viewer (deploy/macapp/main_apple.swift): an Apple-style window, the new design as a skin.
#
#   build_app_apple.sh --mac [--out <path.app>]              "~/Applications/Homebase.app": this Mac's Homebase. Quit it
#                                                            first: the script refuses while it runs.
#   build_app_apple.sh --vps [root@host] [--out <path.app>]  "~/Applications/HOMEBASE VPS.app": the same viewer seeing the
#                                                            SERVER's Homebase through its own SSH SOCKS proxy (-D VPS; host
#                                                            default $HOMEBASE_SERVER, else root@144.202.51.163). Quit it
#                                                            first: the script refuses while it runs.
#   --out <path.app>   a test build there, with its own bundle id: it shares no saved settings with the installed app.
#
# The skin itself (homebase/static/apple/) is served by the desk and chart services, so rebuilding the app is only
# needed when main_apple.swift changes. Nothing is ever deleted: the new app is built in a temp folder and, only once
# it has compiled, the app it replaces is moved aside into another temp folder.
# Idempotent. Requires Xcode CLT (swiftc).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/Applications"
VPS_HOST=""; SWIFT_FLAGS=(); MIN_OS=13.0; ICON=Homebase
case "${1:-}" in
  --mac) shift; APP="$APPS/Homebase.app"; NAME="Homebase"; EXE="Homebase"; BUNDLE_ID="com.ramosquant.homebase.viewer" ;;
  --vps) shift; APP="$APPS/HOMEBASE VPS.app"; NAME="HOMEBASE VPS"; EXE="HomebaseVPS"
         BUNDLE_ID="com.ramosquant.homebase.viewer.vps"; SWIFT_FLAGS=(-D VPS -framework Network); MIN_OS=14.0; ICON=HomebaseVPS
         VPS_HOST="${HOMEBASE_SERVER:-root@144.202.51.163}"
         case "${1:-}" in -*|"") ;; *) VPS_HOST="$1"; shift ;; esac ;;     # a host never starts with "-"
  *)     echo "usage: build_app_apple.sh --mac | --vps [root@host]  [--out <path.app>]" >&2; exit 2 ;;
esac
# a path's real full form, so the same folder written another way (./, //, relative, a link) is the same app
real() { local d; d="$(cd "$(dirname "$1")" 2>/dev/null && pwd -P)" && echo "$d/$(basename "$1")" || echo "$1"; }
# the same app: the same folder on disk (-ef also catches other case, as this Mac's disk ignores case), else the same real path
same() { [ "$1" -ef "$2" ] || [ "$(real "$1")" = "$(real "$2")" ]; }
if [ "${1:-}" = --out ]; then
  [ $# -eq 2 ] || { echo "--out takes one .app path" >&2; exit 2; }
  case "$2" in *.app) ;; *) echo "the output must be a .app path" >&2; exit 2 ;; esac
  if ! same "$2" "$APP"; then APP="$(real "$2")"; BUNDLE_ID="$BUNDLE_ID.test"; fi
elif [ $# -gt 0 ]; then
  echo "unknown argument: $1" >&2; exit 2
fi
# an installed app is never replaced while it runs (a test build elsewhere with --out may go ahead)
if same "$APP" "$APPS/Homebase.app"; then RUN=Homebase; APP="$APPS/Homebase.app"     # its own name, in its own case
elif same "$APP" "$APPS/HOMEBASE VPS.app"; then RUN=HomebaseVPS; APP="$APPS/HOMEBASE VPS.app"
else RUN=""; fi
guard() {
  if [ -n "$RUN" ] && pgrep -x "$RUN" >/dev/null; then
    echo "$(basename "$APP" .app) is running: quit it first (nothing was changed)." >&2; exit 1
  fi
}
guard

BUILD="$(mktemp -d)/$(basename "$APP")"
mkdir -p "$BUILD/Contents/MacOS" "$BUILD/Contents/Resources"
cat > "$BUILD/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleExecutable</key><string>$EXE</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>LSMinimumSystemVersion</key><string>$MIN_OS</string>
  <key>HomebaseVPSHost</key><string>$VPS_HOST</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>CFBundleIconFile</key><string>$ICON</string>
</dict>
</plist>
PLIST
cp "$HERE/$ICON.icns" "$BUILD/Contents/Resources/$ICON.icns"     # HomebaseVPS.icns = the same, colours inverted
swiftc -O ${SWIFT_FLAGS[@]+"${SWIFT_FLAGS[@]}"} "$HERE/main_apple.swift" -o "$BUILD/Contents/MacOS/$EXE" -framework Cocoa -framework WebKit
codesign --force --sign - "$BUILD" 2>/dev/null || true

guard     # again: it may have been started during the build
mkdir -p "$(dirname "$APP")"
OLD=""
if [ -e "$APP" ]; then OLD="$(mktemp -d)/previous.app"; mv "$APP" "$OLD"; fi
if ! mv "$BUILD" "$APP"; then
  if [ -n "$OLD" ]; then mv "$OLD" "$APP"; fi
  echo "could not install the new app; the previous one was put back" >&2; exit 1
fi
if [ "$ICON" = HomebaseVPS ]; then   # a Finder custom icon is not darkened by the macOS 26 dark icon style
  swift - "$APP" <<'SWIFT' || true
import Cocoa
let a = CommandLine.arguments[1]
_ = NSWorkspace.shared.setIcon(NSImage(contentsOfFile: a + "/Contents/Resources/HomebaseVPS.icns"), forFile: a, options: [])
SWIFT
fi
echo "built: $APP"
