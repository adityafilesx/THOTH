#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
configuration=${CONFIGURATION:-release}
identity=${THOTH_CODESIGN_IDENTITY:--}
destination="$root/dist/THOTH Accessibility Helper.app"

swift build --package-path "$root" -c "$configuration"
rm -rf "$destination"
mkdir -p "$destination/Contents/MacOS"
cp "$root/Info.plist" "$destination/Contents/Info.plist"
cp "$root/.build/$configuration/THOTHAXHelper" "$destination/Contents/MacOS/THOTHAXHelper"
codesign --force --options runtime --sign "$identity" "$destination"
codesign --verify --deep --strict "$destination"
printf '%s\n' "$destination"
