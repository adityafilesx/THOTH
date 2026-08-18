#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_ROOT=${1:-"$APP_ROOT/dist"}
BUNDLE="$OUTPUT_ROOT/OmniMac AX Test App.app"

swift build --package-path "$APP_ROOT" -c release --product OmniMacAXTestApp
BIN_DIR=$(swift build --package-path "$APP_ROOT" -c release --show-bin-path)

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
cp "$APP_ROOT/Info.plist" "$BUNDLE/Contents/Info.plist"
cp "$BIN_DIR/OmniMacAXTestApp" "$BUNDLE/Contents/MacOS/OmniMacAXTestApp"
chmod 755 "$BUNDLE/Contents/MacOS/OmniMacAXTestApp"
codesign --force --sign - "$BUNDLE"

printf '%s\n' "$BUNDLE"
