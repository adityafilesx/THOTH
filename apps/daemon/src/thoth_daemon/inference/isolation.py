"""Network isolation guard (Phase 5 slice 1).

In isolation mode any inference endpoint that is not loopback (or
in-process) is refused, at construction AND per request. The cloud
provider is refused outright in isolation regardless of other flags.
"""

from __future__ import annotations

from urllib.parse import urlparse

from thoth_daemon.inference.base import InferenceError

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", ""})


class IsolationViolation(InferenceError):
    """A non-loopback endpoint was used while network isolation is on."""


class NetworkIsolationGuard:
    def __init__(self, isolation: bool = False) -> None:
        self.isolation = isolation

    def check(self, endpoint: str) -> None:
        if not self.isolation:
            return
        host = self._host(endpoint)
        if host not in _LOOPBACK_HOSTS:
            raise IsolationViolation(
                f"network isolation is on: endpoint host {host!r} is not loopback"
            )

    @staticmethod
    def _host(endpoint: str) -> str:
        parsed = urlparse(endpoint if "//" in endpoint else f"//{endpoint}")
        host = parsed.hostname
        return host if host is not None else ""
