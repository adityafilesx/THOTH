"""Bounded, redacted AX snapshot collection."""

from datetime import UTC, datetime

from thoth_daemon.macos.ax_snapshot import (
    AXObservedNode,
    AXSnapshotLimits,
    bounded_text,
    build_window_snapshot,
)

NOW = datetime(2026, 7, 14, 13, tzinfo=UTC)
BUNDLE = "me.adityalabs.thoth.axtest"


def test_text_is_bounded_by_utf8_bytes() -> None:
    result, truncated = bounded_text("🙂" * 20, max_bytes=17)
    assert truncated
    assert len(result.encode()) <= 17


def test_secure_and_authentication_values_are_never_captured() -> None:
    roots = [
        AXObservedNode(
            role="AXSecureTextField",
            identifier="password",
            label="Password",
            value="correct horse battery staple",
        ),
        AXObservedNode(
            role="AXTextField",
            identifier="one-time-code",
            label="Verification code",
            value="123456",
        ),
    ]
    window = build_window_snapshot(
        application_bundle_id=BUNDLE,
        window_identifier="main",
        window_title="Fixture",
        focused=True,
        roots=roots,
        captured_at=NOW,
    )

    assert all(element.value_metadata is not None for element in window.elements)
    assert all(
        element.value_metadata.redacted for element in window.elements if element.value_metadata
    )
    assert all(
        element.value_metadata.value is None
        for element in window.elements
        if element.value_metadata
    )


def test_window_title_and_element_strings_are_redacted_and_bounded() -> None:
    window = build_window_snapshot(
        application_bundle_id=BUNDLE,
        window_identifier="main",
        window_title="token ghp_abcdefghijklmnopqrstuvwxyz123456",
        focused=True,
        roots=[AXObservedNode(role="AXStaticText", label="x" * 100)],
        captured_at=NOW,
        limits=AXSnapshotLimits(max_string_bytes=24),
    )

    assert "ghp_" not in (window.title or "")
    assert len((window.elements[0].label or "").encode()) <= 24
    assert window.elements[0].truncated


def test_element_count_is_strictly_bounded() -> None:
    roots = [AXObservedNode(role="AXButton", identifier=f"item-{index}") for index in range(600)]
    window = build_window_snapshot(
        application_bundle_id=BUNDLE,
        window_identifier="main",
        window_title="Fixture",
        focused=True,
        roots=roots,
        captured_at=NOW,
    )
    assert len(window.elements) == 500
    assert window.truncated


def test_depth_and_cycles_fail_bounded_without_repeating_nodes() -> None:
    root = AXObservedNode(role="AXGroup", identifier="root")
    current = root
    for index in range(20):
        child = AXObservedNode(role="AXGroup", identifier=f"depth-{index}")
        current.children.append(child)
        current = child
    current.children.append(root)

    window = build_window_snapshot(
        application_bundle_id=BUNDLE,
        window_identifier="main",
        window_title="Fixture",
        focused=True,
        roots=[root],
        captured_at=NOW,
    )

    assert len(window.elements) <= 13
    assert len({element.reference_id for element in window.elements}) == len(window.elements)
    assert window.truncated
