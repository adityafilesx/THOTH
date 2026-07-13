"""Local runtime status boundary (Phase 5.2 slice 3).

A minimal status/health surface for persona + UI — NOT the full
LocalAIRuntimeManager. Persona reports degraded operation honestly.
"""

import pytest

from thoth_daemon.core.runtime_status import (
    LocalRuntimeMonitor,
    LocalRuntimeStatus,
)
from thoth_daemon.core.persona import ResponseIntent
from thoth_daemon.inference.base import ProviderHealth


class _Provider:
    def __init__(self, available: bool) -> None:
        self._available = available

    async def health(self) -> ProviderHealth:
        return ProviderHealth(available=self._available, model_id="m")


class TestMonitor:
    async def test_healthy_provider_is_ready(self) -> None:
        monitor = LocalRuntimeMonitor(_Provider(available=True))
        assert await monitor.status() is LocalRuntimeStatus.READY

    async def test_unavailable_provider_is_unavailable(self) -> None:
        monitor = LocalRuntimeMonitor(_Provider(available=False))
        assert await monitor.status() is LocalRuntimeStatus.UNAVAILABLE

    async def test_provider_error_is_failed(self) -> None:
        class _Broken:
            async def health(self):  # noqa: ANN202
                raise RuntimeError("crashed")

        monitor = LocalRuntimeMonitor(_Broken())
        assert await monitor.status() is LocalRuntimeStatus.FAILED

    def test_degraded_maps_to_persona_intent(self) -> None:
        # A non-ready runtime yields the honest DEGRADED_MODE persona intent.
        for status in (
            LocalRuntimeStatus.UNAVAILABLE,
            LocalRuntimeStatus.DEGRADED,
            LocalRuntimeStatus.FAILED,
        ):
            assert status.persona_intent() is ResponseIntent.DEGRADED_MODE

    def test_ready_has_no_degraded_intent(self) -> None:
        assert LocalRuntimeStatus.READY.persona_intent() is None

    def test_all_named_states_exist(self) -> None:
        names = {s.value for s in LocalRuntimeStatus}
        assert names == {
            "unavailable",
            "starting",
            "ready",
            "generating",
            "degraded",
            "failed",
        }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
