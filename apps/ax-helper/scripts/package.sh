#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
configuration=${CONFIGURATION:-release}
identity=${OmniMac_CODESIGN_IDENTITY:--}
destination="$root/dist/OmniMac Accessibility Helper.app"

swift build --package-path "$root" -c "$configuration"
rm -rf "$destination"
mkdir -p "$destination/Contents/MacOS"
cp "$root/Info.plist" "$destination/Contents/Info.plist"
cp "$root/.build/$configuration/OmniMacAXHelper" "$destination/Contents/MacOS/OmniMacAXHelper"
codesign --force --options runtime --sign "$identity" "$destination"
codesign --verify --deep --strict "$destination"
printf '%s\n' "$destination"
