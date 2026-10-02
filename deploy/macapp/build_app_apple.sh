#!/bin/bash
# Build "Homebase Next.app" -- the viewer with an Apple-style window and the new design as a skin
# (deploy/macapp/main_apple.swift). The classic Homebase.app (build_app.sh) is a separate app and is never
# touched by this script. Idempotent; rebuild any time. Requires Xcode CLT (swiftc).
#
# Usage: build_app_apple.sh [output .app path]   -- defaults to "~/Applications/Homebase Next.app".
# A test build passes its own scratch path and gets its own bundle id, so it never shares preferences or web
# storage with the installed app.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_APP="$HOME/Applications/Homebase Next.app"
APP="${1:-$DEFAULT_APP}"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

if [ "$APP" = "$DEFAULT_APP" ]; then
  BUNDLE_ID="com.ramosquant.homebase.viewer.next"
else
  BUNDLE_ID="com.ramosquant.homebase.viewer.next.test"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Homebase Next</string>
  <key>CFBundleDisplayName</key><string>Homebase Next</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleExecutable</key><string>HomebaseNext</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>CFBundleIconFile</key><string>Homebase</string>
</dict>
</plist>
PLIST

cp "$HERE/Homebase.icns" "$APP/Contents/Resources/Homebase.icns"
swiftc -O "$HERE/main_apple.swift" -o "$APP/Contents/MacOS/HomebaseNext" \
  -framework Cocoa -framework WebKit
codesign --force --sign - "$APP" 2>/dev/null || true
echo "built: $APP"
