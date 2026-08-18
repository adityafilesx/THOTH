"""Stable-host Accessibility helper IPC boundary."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from omnimac_daemon.macos.ax_helper import (
    AXHelperClient,
    AXHelperProtocolError,
    AXHelperSemanticAXAdapter,
)
from omnimac_daemon.schemas.ax import AXElementSnapshot

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        result: dict[str, Any]
        if request["operation"] == "inspect_application":
            result = {
                "snapshot": {
                    "bundle_id": request["payload"]["bundle_id"],
                    "display_name": "Fixture",
                    "process_identifier": 42,
                    "windows": [],
                    "captured_at": NOW.isoformat(),
                    "truncated": False,
                    "provenance": "TOOL_RESULT_UNTRUSTED",
                }
            }
        else:
            result = {"performed": True}
        return {
            "version": 1,
            "request_id": request["request_id"],
            "ok": True,
            "trusted": True,
            "result": result,
            "error": None,
        }


def _element() -> AXElementSnapshot:
    return AXElementSnapshot(
        reference_id="ref",
        application_bundle_id="me.adityalabs.omnimac.axtest",
        window_identifier="main",
        role="AXTextField",
        identifier="profile-name",
        label="Profile name",
        child_count=0,
        captured_at=NOW,
    )


def test_helper_health_is_the_authoritative_tcc_probe() -> None:
    transport = _RecordingTransport()
    client = AXHelperClient(transport=transport)

    assert client.is_trusted() is True
    assert transport.requests[0]["operation"] == "health"
    assert transport.requests[0]["payload"] == {}


def test_helper_adapter_uses_only_semantic_target_fields() -> None:
    transport = _RecordingTransport()
    adapter = AXHelperSemanticAXAdapter(AXHelperClient(transport=transport))

    assert adapter.set_value(_element(), "Aditya") is True
    payload = transport.requests[0]["payload"]
    assert payload["value"] == "Aditya"
    assert payload["target"] == {
        "application_bundle_id": "me.adityalabs.omnimac.axtest",
        "window_identifier": "main",
        "role": "AXTextField",
        "identifier": "profile-name",
        "label": "Profile name",
        "description": None,
        "parent_path": [],
    }
    assert "coordinates" not in str(payload).lower()
    assert "window_title" not in str(payload)


def test_helper_snapshot_is_strictly_parsed_as_untrusted_data() -> None:
    transport = _RecordingTransport()
    adapter = AXHelperSemanticAXAdapter(AXHelperClient(transport=transport))

    snapshot = adapter.inspect_application("me.adityalabs.omnimac.axtest")

    assert snapshot.bundle_id == "me.adityalabs.omnimac.axtest"
    assert snapshot.provenance.value == "TOOL_RESULT_UNTRUSTED"


def test_helper_rejects_mismatched_or_malformed_response() -> None:
    def mismatched(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "request_id": "different",
            "ok": True,
            "trusted": True,
            "result": {},
            "error": None,
        }

    with pytest.raises(AXHelperProtocolError, match="request id"):
        AXHelperClient(transport=mismatched).is_trusted()


def test_default_socket_path_is_local_user_application_support() -> None:
    client = AXHelperClient(home=Path("/Users/test"))

    assert client.socket_path == Path("/Users/test/Library/Application Support/OmniMac/ax-helper.sock")
