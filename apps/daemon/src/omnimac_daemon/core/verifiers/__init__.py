"""Independent verification framework (Phase 4 slice 7).

Twelve verifiers, each an independent probe of real world state after a
tool runs. See registry.py for the verifiers and context.py for the
injected probes.
"""

from omnimac_daemon.core.verifiers.context import (
    BrowserStateProbe,
    GitStateProbe,
    VerifierContext,
    VerifierOutcome,
)
from omnimac_daemon.core.verifiers.registry import evaluate_check

__all__ = [
    "BrowserStateProbe",
    "GitStateProbe",
    "VerifierContext",
    "VerifierOutcome",
    "evaluate_check",
]
