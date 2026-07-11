"""Secret redaction, applied at every serialization boundary:

- audit store writes (audit/store.py)
- JSONL log writes (logging_setup.py)
- WebSocket event emission (events/bus.py)

Secrets must never reach SQLite, logs, prompts, or frontend state.
"""

from typing import Any

REDACTED = "[REDACTED]"

SECRET_KEY_PATTERNS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "cookie",
    "private_key",
    "passphrase",
)


def _is_secret_key(key: str, extra: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return lowered in extra or any(pattern in lowered for pattern in SECRET_KEY_PATTERNS)


def redact(value: Any, extra_fields: list[str] | None = None) -> Any:
    """Return a deep copy of *value* with secret values masked.

    Keys are matched case-insensitively by substring against
    SECRET_KEY_PATTERNS, plus exact (case-insensitive) matches of
    *extra_fields* (per-tool ``redaction_fields``). The input is not mutated.
    """
    extra = tuple(f.lower() for f in (extra_fields or []))

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: (REDACTED if _is_secret_key(str(k), extra) else walk(v))
                for k, v in node.items()
            }
        if isinstance(node, (list, tuple)):
            walked = [walk(item) for item in node]
            return walked if isinstance(node, list) else tuple(walked)
        return node

    return walk(value)
