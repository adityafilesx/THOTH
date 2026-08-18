"""Tamper-evident hash chain over the audit log (Phase 4 slice 9).

Each event's hash commits to the previous event's hash plus every
integrity-relevant field, so any after-the-fact mutation, deletion, or
reordering of stored rows breaks recomputation. The chain is per task
(``seq`` is already per-task and gap-free). The store itself exposes no
update/delete surface; the chain catches tampering done AROUND the store
(direct database edits).
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


def canonical_payload(payload: dict[str, Any]) -> str:
    """Stable serialization: sorted keys, no whitespace, no NaN."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_timestamp(created_at: datetime) -> str:
    """SQLite round-trips aware datetimes as naive UTC; canonicalize so the
    hash is identical before and after storage."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC).isoformat()


def compute_event_hash(
    *,
    prev_hash: str,
    task_id: str,
    correlation_id: str,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
    created_at: datetime,
) -> str:
    material = "\x1f".join(
        [
            prev_hash,
            task_id,
            correlation_id,
            str(seq),
            event_type,
            canonical_payload(payload),
            canonical_timestamp(created_at),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ChainManifest(BaseModel):
    """Result of verifying a task's audit chain."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    valid: bool
    events: int
    head_hash: str
    first_invalid_seq: int | None = None
    reason: str = ""
