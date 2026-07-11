"""In-process async pub/sub, fanned out to WebSocket clients.

Single daemon process — no external broker (ADR-006). Every published
payload passes redaction before it can reach any subscriber.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from thoth_daemon.security.redaction import redact

_QUEUE_SIZE = 256


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        envelope = {
            "type": event_type,
            "ts": datetime.now(UTC).isoformat(),
            "payload": redact(payload),
        }
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                # Slow consumer: drop it rather than stall the daemon.
                self._subscribers.discard(queue)
