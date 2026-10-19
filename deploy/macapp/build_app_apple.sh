#!/bin/bash
# Build the viewer with the Apple-style window and the new design as a skin (deploy/macapp/main_apple.swift).
#
#   build_app_apple.sh                 "~/Applications/Homebase Next.app": a second app beside the classic Homebase.app
#   build_app_apple.sh --as-homebase   "~/Applications/Homebase.app": the new viewer takes the classic app's name and
#                                      bundle id (same Dock icon, same saved web settings). The classic viewer is first
#                                      kept as "Homebase Classic.app" (its own bundle id). Quit Homebase first: the
#                                      script refuses while it runs.
#   build_app_apple.sh --vps [root@host]  "~/Applications/HOMEBASE VPS.app": the same viewer seeing the SERVER's Homebase
#                                      through its own SSH SOCKS proxy (main_apple.swift, -D VPS; host default
#                                      $HOMEBASE_SERVER, else root@144.202.51.163). Homebase.app is not touched.
#   build_app_apple.sh <path.app>      a test build with its own bundle id, sharing nothing with an installed app
#
# The classic build (build_app.sh) also writes ~/Applications/Homebase.app: run it and the classic viewer is back.
# The skin itself (homebase/static/apple/) is served by the desk and chart services, so rebuilding the app is only
# needed when main_apple.swift changes. Nothing is ever deleted: the new app is built in a temp folder and, only once
# it has compiled, the app it replaces is moved aside into another temp folder.
# Idempotent. Requires Xcode CLT (swiftc).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/Applications"
VPS_HOST=""; SWIFT_FLAGS=(); MIN_OS=13.0; ICON=Homebase
case "${1:-}" in
  --vps)         MODE=vps; APP="${VPS_APP:-$APPS/HOMEBASE VPS.app}"; NAME="HOMEBASE VPS"; EXE="HomebaseVPS"
                 BUNDLE_ID="com.ramosquant.homebase.viewer.vps"; SWIFT_FLAGS=(-D VPS -framework Network); MIN_OS=14.0; ICON=HomebaseVPS
                 VPS_HOST="${2:-${HOMEBASE_SERVER:-root@144.202.51.163}}" ;;
  --as-homebase) MODE=homebase; APP="$APPS/Homebase.app"; NAME="Homebase"; EXE="Homebase"
                 BUNDLE_ID="com.ramosquant.homebase.viewer" ;;
  "")            MODE=next; APP="$APPS/Homebase Next.app"; NAME="Homebase Next"; EXE="HomebaseNext"
                 BUNDLE_ID="com.ramosquant.homebase.viewer.next" ;;
  *)             MODE=test; APP="$1"; NAME="Homebase Next"; EXE="HomebaseNext"
                 BUNDLE_ID="com.ramosquant.homebase.viewer.next.test"
                 if [ "$APP" = "$APPS/Homebase Next.app" ]; then MODE=next; BUNDLE_ID="com.ramosquant.homebase.viewer.next"; fi ;;
esac
case "$APP" in *.app) ;; *) echo "the output must be a .app path" >&2; exit 2 ;; esac

if [ "$MODE" = homebase ]; then
  if pgrep -x "$EXE" >/dev/null; then echo "Homebase is running: quit it first (nothing was changed)." >&2; exit 1; fi
  CLASSIC="$APPS/Homebase Classic.app"
  if [ -d "$APP" ] && [ ! -e "$CLASSIC" ]; then
    cur="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist" 2>/dev/null || true)"
    case "$cur" in
      1.*) ditto "$APP" "$CLASSIC"
           PB=/usr/libexec/PlistBuddy; P="$CLASSIC/Contents/Info.plist"
           $PB -c "Set :CFBundleIdentifier com.ramosquant.homebase.viewer.classic" "$P"
           $PB -c "Set :CFBundleName Homebase Classic" "$P"
           $PB -c "Set :CFBundleDisplayName Homebase Classic" "$P"
           codesign --force --sign - "$CLASSIC"
           echo "kept the classic viewer as: $CLASSIC" ;;
    esac
  fi
fi

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

mkdir -p "$(dirname "$APP")"
OLD=""
if [ -e "$APP" ]; then OLD="$(mktemp -d)/previous.app"; mv "$APP" "$OLD"; fi
if ! mv "$BUILD" "$APP"; then
  if [ -n "$OLD" ]; then mv "$OLD" "$APP"; fi
  echo "could not install the new app; the previous one was put back" >&2; exit 1
fi
echo "built: $APP"
