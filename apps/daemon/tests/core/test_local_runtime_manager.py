from __future__ import annotations

import asyncio

import pytest

from thoth_daemon.core.local_runtime import (
    LocalAIRuntimeManager,
    RuntimeComponent,
    RuntimeDriverHealth,
    RuntimeRegistration,
    RuntimeState,
    RuntimeUnavailable,
)


class Driver:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.loads = 0
        self.unloads = 0
        self.health_checks = 0

    async def load(self) -> None:
        self.loads += 1
        if not self.available:
            raise RuntimeUnavailable("local runtime unavailable")

    async def unload(self) -> None:
        self.unloads += 1

    async def health(self) -> RuntimeDriverHealth:
        self.health_checks += 1
        return RuntimeDriverHealth(
            available=self.available,
            detail="ready" if self.available else "missing",
        )


def registration(
    component: RuntimeComponent,
    driver: Driver,
    *,
    memory_bytes: int = 1_000,
    integrity_verified: bool = True,
) -> RuntimeRegistration:
    return RuntimeRegistration(
        component=component,
        display_name=component.value,
        driver=driver,
        memory_estimate_bytes=memory_bytes,
        integrity_verified=integrity_verified,
        heavy=component in {RuntimeComponent.PLANNER, RuntimeComponent.SPEECH_RECOGNITION},
    )


class TestLifecycle:
    async def test_load_use_and_idle_cache(self) -> None:
        now = [10.0]
        driver = Driver()
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000, clock=lambda: now[0])
        manager.register(registration(RuntimeComponent.PLANNER, driver))

        assert (
            manager.snapshot().components[RuntimeComponent.PLANNER].state is RuntimeState.UNLOADED
        )
        async with manager.use(RuntimeComponent.PLANNER):
            assert (
                manager.snapshot().components[RuntimeComponent.PLANNER].state is RuntimeState.BUSY
            )
        status = manager.snapshot().components[RuntimeComponent.PLANNER]
        assert status.state is RuntimeState.IDLE_CACHED
        assert driver.loads == 1

    async def test_integrity_failure_blocks_load(self) -> None:
        driver = Driver()
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000)
        manager.register(
            registration(
                RuntimeComponent.SPEECH_RECOGNITION,
                driver,
                integrity_verified=False,
            )
        )
        with pytest.raises(RuntimeUnavailable, match="integrity"):
            await manager.ensure_ready(RuntimeComponent.SPEECH_RECOGNITION)
        assert driver.loads == 0
        assert (
            manager.snapshot().components[RuntimeComponent.SPEECH_RECOGNITION].state
            is RuntimeState.FAILED
        )

    async def test_missing_local_runtime_degrades_without_fallback(self) -> None:
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000)
        manager.register(registration(RuntimeComponent.SPEECH_RECOGNITION, Driver(available=False)))
        with pytest.raises(RuntimeUnavailable):
            await manager.ensure_ready(RuntimeComponent.SPEECH_RECOGNITION)
        status = manager.snapshot().components[RuntimeComponent.SPEECH_RECOGNITION]
        assert status.state is RuntimeState.DEGRADED
        assert status.detail == "missing"

    async def test_restart_recovers_failed_runtime(self) -> None:
        driver = Driver(available=False)
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000)
        manager.register(registration(RuntimeComponent.TEXT_TO_SPEECH, driver))
        with pytest.raises(RuntimeUnavailable):
            await manager.ensure_ready(RuntimeComponent.TEXT_TO_SPEECH)
        driver.available = True
        await manager.restart(RuntimeComponent.TEXT_TO_SPEECH)
        assert (
            manager.snapshot().components[RuntimeComponent.TEXT_TO_SPEECH].state
            is RuntimeState.READY
        )
        assert driver.unloads == 1

    async def test_crash_recovery_attempt_is_bounded(self) -> None:
        driver = Driver()
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000)
        manager.register(registration(RuntimeComponent.PLANNER, driver))
        await manager.ensure_ready(RuntimeComponent.PLANNER)
        assert await manager.record_crash(RuntimeComponent.PLANNER) is True
        assert driver.loads == 2
        driver.available = False
        assert await manager.record_crash(RuntimeComponent.PLANNER) is False
        assert manager.snapshot().components[RuntimeComponent.PLANNER].state is RuntimeState.FAILED


class TestResources:
    async def test_heavy_qwen_and_whisper_work_is_serialized(self) -> None:
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000, max_heavy_concurrency=1)
        manager.register(registration(RuntimeComponent.PLANNER, Driver()))
        manager.register(registration(RuntimeComponent.SPEECH_RECOGNITION, Driver()))
        whisper_entered = asyncio.Event()

        async def use_whisper() -> None:
            async with manager.use(RuntimeComponent.SPEECH_RECOGNITION):
                whisper_entered.set()

        async with manager.use(RuntimeComponent.PLANNER):
            task = asyncio.create_task(use_whisper())
            await asyncio.sleep(0)
            assert not whisper_entered.is_set()
        await asyncio.wait_for(task, timeout=1)
        assert whisper_entered.is_set()

    async def test_memory_pressure_evicts_idle_cache_not_busy_runtime(self) -> None:
        planner = Driver()
        tts = Driver()
        manager = LocalAIRuntimeManager(memory_limit_bytes=1_500)
        manager.register(registration(RuntimeComponent.PLANNER, planner, memory_bytes=1_000))
        manager.register(registration(RuntimeComponent.TEXT_TO_SPEECH, tts, memory_bytes=700))
        async with manager.use(RuntimeComponent.PLANNER):
            evicted = await manager.handle_memory_pressure(required_bytes=700)
            assert RuntimeComponent.PLANNER not in evicted
        evicted = await manager.handle_memory_pressure(required_bytes=700)
        assert RuntimeComponent.PLANNER in evicted
        assert planner.unloads == 1

    async def test_battery_saver_evicts_idle_models(self) -> None:
        driver = Driver()
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000)
        manager.register(registration(RuntimeComponent.PLANNER, driver))
        async with manager.use(RuntimeComponent.PLANNER):
            pass
        await manager.set_battery_saver(True)
        assert manager.snapshot().battery_saver is True
        assert (
            manager.snapshot().components[RuntimeComponent.PLANNER].state is RuntimeState.UNLOADED
        )

    async def test_idle_timeout_evicts_warm_cache(self) -> None:
        now = [10.0]
        driver = Driver()
        manager = LocalAIRuntimeManager(
            memory_limit_bytes=16_000,
            idle_ttl_seconds=30,
            clock=lambda: now[0],
        )
        manager.register(registration(RuntimeComponent.PLANNER, driver))
        async with manager.use(RuntimeComponent.PLANNER):
            pass
        now[0] = 41.0
        assert await manager.evict_idle() == [RuntimeComponent.PLANNER]

    async def test_cancellation_releases_concurrency_slot(self) -> None:
        manager = LocalAIRuntimeManager(memory_limit_bytes=16_000, max_heavy_concurrency=1)
        manager.register(registration(RuntimeComponent.PLANNER, Driver()))

        async def cancelled_use() -> None:
            async with manager.use(RuntimeComponent.PLANNER):
                await asyncio.Event().wait()

        task = asyncio.create_task(cancelled_use())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with manager.use(RuntimeComponent.PLANNER):
            assert (
                manager.snapshot().components[RuntimeComponent.PLANNER].state is RuntimeState.BUSY
            )


def test_offline_status_is_explicit_and_does_not_disable_reflex_floor() -> None:
    manager = LocalAIRuntimeManager(memory_limit_bytes=16_000, offline=True)
    snapshot = manager.snapshot()
    assert snapshot.offline is True
    assert snapshot.reflex_available is True
