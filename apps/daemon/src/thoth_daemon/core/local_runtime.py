"""Unified lifecycle and resource policy for local AI runtimes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.inference.base import InferenceProvider
from thoth_daemon.voice.contracts import (
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)


class RuntimeComponent(StrEnum):
    PLANNER = "planner"
    SPEECH_RECOGNITION = "speech_recognition"
    TEXT_TO_SPEECH = "text_to_speech"


class RuntimeState(StrEnum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    BUSY = "busy"
    IDLE_CACHED = "idle_cached"
    EVICTING = "evicting"
    DEGRADED = "degraded"
    FAILED = "failed"


class RuntimeUnavailable(RuntimeError):
    """A local component cannot become ready; no fallback is allowed."""


class RuntimeDriverHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    detail: str = ""


class RuntimeDriver(Protocol):
    async def load(self) -> None: ...

    async def unload(self) -> None: ...

    async def health(self) -> RuntimeDriverHealth: ...


@dataclass(frozen=True)
class RuntimeRegistration:
    component: RuntimeComponent
    display_name: str
    driver: RuntimeDriver
    memory_estimate_bytes: int
    integrity_verified: bool | None
    heavy: bool

    def __post_init__(self) -> None:
        if self.memory_estimate_bytes < 0:
            raise ValueError("memory estimate cannot be negative")


class RuntimeComponentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str
    state: RuntimeState
    memory_estimate_bytes: int = Field(ge=0)
    integrity_verified: bool | None
    heavy: bool
    detail: str


class LocalRuntimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    components: dict[RuntimeComponent, RuntimeComponentStatus]
    memory_limit_bytes: int = Field(gt=0)
    estimated_loaded_bytes: int = Field(ge=0)
    battery_saver: bool
    offline: bool
    reflex_available: bool = True


@dataclass
class _Entry:
    registration: RuntimeRegistration
    state: RuntimeState = RuntimeState.UNLOADED
    detail: str = "not loaded"
    last_used: float = 0


class LocalAIRuntimeManager:
    """Own local component state without owning planning or execution truth."""

    def __init__(
        self,
        *,
        memory_limit_bytes: int,
        max_heavy_concurrency: int = 1,
        idle_ttl_seconds: float = 300,
        battery_saver: bool = False,
        offline: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if memory_limit_bytes <= 0:
            raise ValueError("memory_limit_bytes must be positive")
        if max_heavy_concurrency <= 0:
            raise ValueError("max_heavy_concurrency must be positive")
        self._memory_limit = memory_limit_bytes
        self._idle_ttl = idle_ttl_seconds
        self._battery_saver = battery_saver
        self._offline = offline
        self._clock = clock
        self._entries: dict[RuntimeComponent, _Entry] = {}
        self._locks: dict[RuntimeComponent, asyncio.Lock] = {}
        self._heavy = asyncio.Semaphore(max_heavy_concurrency)

    def register(self, registration: RuntimeRegistration) -> None:
        if registration.component in self._entries:
            raise ValueError(f"runtime {registration.component.value!r} is already registered")
        self._entries[registration.component] = _Entry(registration=registration)
        self._locks[registration.component] = asyncio.Lock()

    async def ensure_ready(self, component: RuntimeComponent) -> None:
        entry = self._entry(component)
        async with self._locks[component]:
            if entry.state in {
                RuntimeState.READY,
                RuntimeState.BUSY,
                RuntimeState.IDLE_CACHED,
            }:
                return
            if entry.registration.integrity_verified is False:
                entry.state = RuntimeState.FAILED
                entry.detail = "model integrity verification failed"
                raise RuntimeUnavailable(entry.detail)
            entry.state = RuntimeState.LOADING
            entry.detail = "loading local runtime"
            try:
                await entry.registration.driver.load()
                health = await entry.registration.driver.health()
            except RuntimeUnavailable as exc:
                entry.state = RuntimeState.DEGRADED
                try:
                    failed_health = await entry.registration.driver.health()
                    entry.detail = failed_health.detail or str(exc)
                except Exception:
                    entry.detail = str(exc)
                raise
            except Exception as exc:
                entry.state = RuntimeState.FAILED
                entry.detail = f"local runtime load failed: {type(exc).__name__}"
                raise RuntimeUnavailable(entry.detail) from exc
            if not health.available:
                entry.state = RuntimeState.DEGRADED
                entry.detail = health.detail
                raise RuntimeUnavailable(health.detail)
            entry.state = RuntimeState.READY
            entry.detail = health.detail or "ready"
            entry.last_used = self._clock()

    @asynccontextmanager
    async def use(self, component: RuntimeComponent) -> AsyncIterator[None]:
        entry = self._entry(component)
        acquired = False
        try:
            if entry.registration.heavy:
                await self._heavy.acquire()
                acquired = True
            await self.ensure_ready(component)
            entry.state = RuntimeState.BUSY
            entry.detail = "busy"
            yield
        finally:
            if entry.state is RuntimeState.BUSY:
                entry.last_used = self._clock()
                if self._battery_saver:
                    entry.state = RuntimeState.EVICTING
                    await entry.registration.driver.unload()
                    entry.state = RuntimeState.UNLOADED
                    entry.detail = "evicted for battery saver"
                else:
                    entry.state = RuntimeState.IDLE_CACHED
                    entry.detail = "warm idle cache"
            if acquired:
                self._heavy.release()

    async def evict_idle(self) -> list[RuntimeComponent]:
        now = self._clock()
        candidates = [
            component
            for component, entry in self._entries.items()
            if entry.state is RuntimeState.IDLE_CACHED and now - entry.last_used >= self._idle_ttl
        ]
        return await self._evict(candidates, detail="idle cache expired")

    async def handle_memory_pressure(self, *, required_bytes: int) -> list[RuntimeComponent]:
        if required_bytes < 0:
            raise ValueError("required_bytes cannot be negative")
        loaded = self._estimated_loaded_bytes()
        if loaded + required_bytes <= self._memory_limit:
            return []
        candidates = sorted(
            (
                (component, entry)
                for component, entry in self._entries.items()
                if entry.state is RuntimeState.IDLE_CACHED
            ),
            key=lambda item: item[1].last_used,
        )
        selected: list[RuntimeComponent] = []
        for component, entry in candidates:
            selected.append(component)
            loaded -= entry.registration.memory_estimate_bytes
            if loaded + required_bytes <= self._memory_limit:
                break
        return await self._evict(selected, detail="evicted for memory pressure")

    async def set_battery_saver(self, enabled: bool) -> None:
        self._battery_saver = enabled
        if enabled:
            candidates = [
                component
                for component, entry in self._entries.items()
                if entry.state is RuntimeState.IDLE_CACHED
            ]
            await self._evict(candidates, detail="evicted for battery saver")

    async def restart(self, component: RuntimeComponent) -> None:
        entry = self._entry(component)
        async with self._locks[component]:
            entry.state = RuntimeState.EVICTING
            await entry.registration.driver.unload()
            entry.state = RuntimeState.UNLOADED
            entry.detail = "restarting"
        await self.ensure_ready(component)

    async def record_crash(self, component: RuntimeComponent) -> bool:
        """Make one bounded restart attempt for one observed crash."""
        entry = self._entry(component)
        entry.state = RuntimeState.FAILED
        entry.detail = "local runtime crashed"
        try:
            await entry.registration.driver.unload()
            entry.state = RuntimeState.UNLOADED
            await self.ensure_ready(component)
            return True
        except RuntimeUnavailable:
            entry.state = RuntimeState.FAILED
            entry.detail = "local runtime crash recovery failed"
            return False

    def snapshot(self) -> LocalRuntimeSnapshot:
        return LocalRuntimeSnapshot(
            components={
                component: RuntimeComponentStatus(
                    display_name=entry.registration.display_name,
                    state=entry.state,
                    memory_estimate_bytes=entry.registration.memory_estimate_bytes,
                    integrity_verified=entry.registration.integrity_verified,
                    heavy=entry.registration.heavy,
                    detail=entry.detail,
                )
                for component, entry in self._entries.items()
            },
            memory_limit_bytes=self._memory_limit,
            estimated_loaded_bytes=self._estimated_loaded_bytes(),
            battery_saver=self._battery_saver,
            offline=self._offline,
        )

    async def _evict(
        self,
        components: list[RuntimeComponent],
        *,
        detail: str,
    ) -> list[RuntimeComponent]:
        evicted: list[RuntimeComponent] = []
        for component in components:
            entry = self._entry(component)
            if entry.state is not RuntimeState.IDLE_CACHED:
                continue
            entry.state = RuntimeState.EVICTING
            await entry.registration.driver.unload()
            entry.state = RuntimeState.UNLOADED
            entry.detail = detail
            evicted.append(component)
        return evicted

    def _estimated_loaded_bytes(self) -> int:
        unloaded = {
            RuntimeState.UNLOADED,
            RuntimeState.DEGRADED,
            RuntimeState.FAILED,
        }
        return sum(
            entry.registration.memory_estimate_bytes
            for entry in self._entries.values()
            if entry.state not in unloaded
        )

    def _entry(self, component: RuntimeComponent) -> _Entry:
        try:
            return self._entries[component]
        except KeyError as exc:
            raise KeyError(f"runtime {component.value!r} is not registered") from exc


class InferenceRuntimeDriver:
    def __init__(self, provider: InferenceProvider) -> None:
        self._provider = provider

    async def load(self) -> None:
        await self._provider.warm_up()

    async def unload(self) -> None:
        await self._provider.unload()

    async def health(self) -> RuntimeDriverHealth:
        health = await self._provider.health()
        return RuntimeDriverHealth(available=health.available, detail=health.detail)


class SpeechRecognitionRuntimeDriver:
    def __init__(self, provider: SpeechRecognitionProvider) -> None:
        self._provider = provider

    async def load(self) -> None:
        health = await self._provider.health()
        if not health.available:
            raise RuntimeUnavailable(health.detail)

    async def unload(self) -> None:
        await self._provider.unload()

    async def health(self) -> RuntimeDriverHealth:
        health = await self._provider.health()
        return RuntimeDriverHealth(available=health.available, detail=health.detail)


class SpeechSynthesisRuntimeDriver:
    def __init__(self, provider: SpeechSynthesisProvider) -> None:
        self._provider = provider

    async def load(self) -> None:
        health = await self._provider.health()
        if not health.available:
            raise RuntimeUnavailable(health.detail)

    async def unload(self) -> None:
        await self._provider.interrupt()

    async def health(self) -> RuntimeDriverHealth:
        health = await self._provider.health()
        return RuntimeDriverHealth(available=health.available, detail=health.detail)
