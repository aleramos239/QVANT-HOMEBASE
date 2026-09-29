#!/bin/bash
# Build Homebase.app -- a native WKWebView window onto the dashboard (Desk / Charts / Backtest
# tabs). Idempotent; rebuild any time. Requires Xcode CLT (swiftc).
#
# Usage: build_app.sh [output .app path]   -- defaults to ~/Applications/Homebase.app.
# A test build passes its own scratch path so it never touches the installed app.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="${1:-$HOME/Applications/Homebase.app}"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Homebase</string>
  <key>CFBundleDisplayName</key><string>Homebase</string>
  <key>CFBundleIdentifier</key><string>com.ramosquant.homebase.viewer</string>
  <key>CFBundleExecutable</key><string>Homebase</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>CFBundleIconFile</key><string>Homebase</string>
</dict>
</plist>
EOF

cp "$HERE/Homebase.icns" "$APP/Contents/Resources/Homebase.icns"
swiftc -O "$HERE/main.swift" -o "$APP/Contents/MacOS/Homebase" \
  -framework Cocoa -framework WebKit
codesign --force --sign - "$APP" 2>/dev/null || true
echo "built: $APP"
