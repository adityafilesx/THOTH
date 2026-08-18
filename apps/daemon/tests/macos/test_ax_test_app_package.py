"""Contract tests for the packaged native Accessibility fixture."""

import plistlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
APP = REPO / "apps" / "ax-test-app"
SOURCE = APP / "Sources" / "OmniMacAXTestApp" / "OmniMacAXTestApp.swift"

REQUIRED_IDENTIFIERS = {
    "ax-single-line-input",
    "ax-multiline-input",
    "ax-checkbox",
    "ax-toggle",
    "ax-picker",
    "ax-stepper",
    "ax-item-list",
    "ax-search-field",
    "ax-disabled-button",
    "ax-save-button",
    "ax-modal-button",
    "ax-confirm-alert-button",
    "ax-status-label",
    "ax-progress",
    "ax-segmented-control",
    "ax-moving-control",
    "ax-delayed-control",
    "ax-disappearing-control",
    "ax-validation-error",
    "ax-reset-button",
}


def test_native_fixture_has_unique_authoritative_bundle_identifier() -> None:
    with (APP / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)

    assert info["CFBundleIdentifier"] == "me.adityalabs.omnimac.axtest"
    assert info["CFBundleExecutable"] == "OmniMacAXTestApp"
    assert info["CFBundlePackageType"] == "APPL"


def test_native_fixture_exposes_complete_unique_identifier_inventory() -> None:
    source = SOURCE.read_text()
    identifiers = re.findall(r'\.accessibilityIdentifier\("([^"]+)"\)', source)

    assert set(identifiers) >= REQUIRED_IDENTIFIERS
    assert len(identifiers) == len(set(identifiers))


def test_native_fixture_supports_deterministic_reset_and_packaging() -> None:
    source = SOURCE.read_text()
    package_script = (APP / "scripts" / "package_app.sh").read_text()

    assert "--reset" in source
    assert "resetState()" in source
    assert "swift build" in package_script
    assert "codesign" in package_script
    assert "sudo" not in package_script
