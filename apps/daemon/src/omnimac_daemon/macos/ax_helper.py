"""Client for the stable, local-only macOS Accessibility helper host."""

from __future__ import annotations

import json
import os
import socket
import stat
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from omnimac_daemon.schemas.ax import (
    AXApplicationSnapshot,
    AXElementSnapshot,
    AXPrimitive,
    AXWindowSnapshot,
)

AX_HELPER_PROTOCOL_VERSION = 1
MAX_AX_HELPER_MESSAGE_BYTES = 4 * 1024 * 1024


class AXHelperError(RuntimeError):
    """The local helper is absent, unsafe, or rejected an operation."""


class AXHelperProtocolError(AXHelperError):
    """The helper violated its strict versioned response contract."""


class _HelperResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    request_id: str = Field(min_length=1, max_length=64)
    ok: bool
    trusted: bool
    result: dict[str, Any]
    error: str | None = Field(default=None, max_length=4096)


Transport = Callable[[dict[str, Any]], dict[str, Any]]


class AXHelperClient:
    """Synchronous NDJSON IPC over a restrictive per-user Unix socket."""

    def __init__(
        self,
        socket_path: Path | None = None,
        *,
        home: Path | None = None,
        transport: Transport | None = None,
        timeout_s: float = 2.0,
    ) -> None:
        if timeout_s <= 0 or timeout_s > 30:
            raise ValueError("AX helper timeout must be within 0-30 seconds")
        root = home or Path.home()
        self.socket_path = socket_path or (root / "Library" / "Application Support" / "OmniMac" / "ax-helper.sock")
        self._transport = transport or self._socket_transport
        self._timeout_s = timeout_s

    def is_trusted(self) -> bool:
        return self._call("health", {})[0]

    def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot:
        _, result = self._call("inspect_application", {"bundle_id": bundle_id})
        try:
            return AXApplicationSnapshot.model_validate(result["snapshot"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AXHelperProtocolError("helper returned an invalid application snapshot") from exc

    def set_value(self, element: AXElementSnapshot, value: AXPrimitive) -> bool:
        return self._performed("set_value", element, value=value)

    def perform_action(self, element: AXElementSnapshot, action_name: str) -> bool:
        return self._performed("perform_action", element, action_name=action_name)

    def select_option(self, element: AXElementSnapshot, option: str) -> bool:
        return self._performed("select_option", element, option=option)

    def _performed(
        self,
        operation: str,
        element: AXElementSnapshot,
        **specific: AXPrimitive,
    ) -> bool:
        payload: dict[str, Any] = {"target": self._semantic_target(element), **specific}
        _, result = self._call(operation, payload)
        performed = result.get("performed")
        if not isinstance(performed, bool):
            raise AXHelperProtocolError("helper mutation response omitted performed boolean")
        return performed

    @staticmethod
    def _semantic_target(element: AXElementSnapshot) -> dict[str, Any]:
        # Intentionally omit coordinates, frame, raw object identity, observed
        # value, and window title. The helper re-resolves current semantics.
        return {
            "application_bundle_id": element.application_bundle_id,
            "window_identifier": element.window_identifier,
            "role": element.role,
            "identifier": element.identifier,
            "label": element.label,
            "description": element.description,
            "parent_path": list(element.parent_path),
        }

    def _call(self, operation: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        request_id = str(uuid.uuid4())
        request = {
            "version": AX_HELPER_PROTOCOL_VERSION,
            "request_id": request_id,
            "operation": operation,
            "payload": payload,
        }
        try:
            raw = self._transport(request)
            response = _HelperResponse.model_validate(raw)
        except AXHelperError:
            raise
        except Exception as exc:
            raise AXHelperProtocolError("helper response was malformed") from exc
        if response.version != AX_HELPER_PROTOCOL_VERSION:
            raise AXHelperProtocolError("helper protocol version mismatch")
        if response.request_id != request_id:
            raise AXHelperProtocolError("helper response request id mismatch")
        if not response.ok:
            raise AXHelperError(response.error or "Accessibility helper rejected the request")
        return response.trusted, response.result

    def _socket_transport(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate_socket()
        encoded = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_AX_HELPER_MESSAGE_BYTES:
            raise AXHelperProtocolError("AX helper request exceeds the message ceiling")
        chunks = bytearray()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._timeout_s)
            connection.connect(str(self.socket_path))
            connection.sendall(encoded)
            while b"\n" not in chunks:
                chunk = connection.recv(65_536)
                if not chunk:
                    break
                chunks.extend(chunk)
                if len(chunks) > MAX_AX_HELPER_MESSAGE_BYTES:
                    raise AXHelperProtocolError("AX helper response exceeds the message ceiling")
        line, separator, _ = bytes(chunks).partition(b"\n")
        if not separator:
            raise AXHelperProtocolError("AX helper returned an incomplete response")
        try:
            decoded = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AXHelperProtocolError("AX helper returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise AXHelperProtocolError("AX helper response must be an object")
        return decoded

    def _validate_socket(self) -> None:
        try:
            metadata = self.socket_path.stat()
        except OSError as exc:
            raise AXHelperError("Accessibility helper socket is unavailable") from exc
        if not stat.S_ISSOCK(metadata.st_mode):
            raise AXHelperError("Accessibility helper path is not a Unix socket")
        if metadata.st_uid != os.getuid():
            raise AXHelperError("Accessibility helper socket is not owned by the current user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise AXHelperError("Accessibility helper socket permissions are not restrictive")


class AXHelperSemanticAXAdapter:
    """Semantic adapter whose OS calls execute only in the signed helper."""

    def __init__(self, client: AXHelperClient) -> None:
        self._client = client

    def inspect_application(self, bundle_id: str) -> AXApplicationSnapshot:
        return self._client.inspect_application(bundle_id)

    def inspect_window(self, bundle_id: str, window_identifier: str) -> AXWindowSnapshot | None:
        application = self.inspect_application(bundle_id)
        return next(
            (window for window in application.windows if window.identifier == window_identifier),
            None,
        )

    def set_value(self, element: AXElementSnapshot, value: AXPrimitive) -> bool:
        return self._client.set_value(element, value)

    def perform_action(self, element: AXElementSnapshot, action_name: str) -> bool:
        return self._client.perform_action(element, action_name)

    def select_option(self, element: AXElementSnapshot, option: str) -> bool:
        return self._client.select_option(element, option)
