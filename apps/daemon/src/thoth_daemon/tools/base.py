"""Tool contract base.

Every tool exposes the full contract from docs/TOOL_CONTRACTS.md: unique
name, typed input/output models, default risk, timeout, cancellation and
dry-run behavior, verification strategy, resource scope, and redaction
fields. No tool accepts arbitrary shell text (that is reserved for the
dedicated restricted shell tool in Phase 3).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.schemas import (
    ResourceScope,
    RiskLevel,
    ToolInvocation,
    VerificationStrategy,
)

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


@dataclass(frozen=True)
class IndependentToolVerification:
    passed: bool
    detail: str
    available: bool = True


class UnknownToolError(Exception):
    pass


class DuplicateToolError(Exception):
    pass


class InvalidToolDefinitionError(Exception):
    pass


class ToolDefinition(ABC, Generic[TInput, TOutput]):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    default_risk: RiskLevel
    timeout_s: float = 10.0
    supports_dry_run: bool = False
    supports_cancellation: bool = True
    verification: VerificationStrategy = VerificationStrategy.OUTPUT_ASSERTION
    resource_scope: ResourceScope
    redaction_fields: ClassVar[list[str]] = []
    # Intended focus behaviour (Phase 5.3). Default: never steal focus; a
    # focus-changing tool (app launch/focus) overrides to KEEP_NEW_FOCUS.
    focus_policy: FocusPolicy = FocusPolicy.DO_NOT_STEAL_FOCUS

    def __init__(self) -> None:
        if not getattr(self, "resource_scope", None):
            self.resource_scope = ResourceScope()

    def parse_arguments(self, invocation: ToolInvocation) -> BaseModel:
        """Validate raw args against input_model (extra='forbid')."""
        return self.input_model.model_validate(invocation.arguments)

    def requested_scope(self, args: Any) -> ResourceScope:
        """The concrete paths/domains/apps this invocation will touch. The
        orchestrator and executor check these against the effective allowed
        scope. Default: touches nothing (mocks and pure-compute tools)."""
        return ResourceScope()

    def validate_authority(self, args: Any) -> None:
        """Apply trusted, tool-specific authorization before policy review.

        Typed input validation is necessary but not sufficient for tools whose
        targets are constrained by a separate trusted profile. Most tools have
        no additional authority source and therefore use this no-op default.
        """
        del args

    def focus_target(self, args: Any) -> str | None:
        """Return the OS application name whose focus must be verified.

        Most tools do not target an application. Focus-changing tools must
        override this rather than relying on model-provided target text.
        """
        return None

    def verify_independently(self, args: Any) -> IndependentToolVerification | None:
        """Re-probe state after execution when the tool has a registered verifier.

        Returning ``None`` preserves the existing strategy baseline. Effectful
        semantic tools override this and must not derive the result from their
        own action response.
        """
        return None

    @abstractmethod
    async def run(self, args: Any, dry_run: bool) -> BaseModel:
        """Execute the tool. Must cooperate with cancellation and honor
        dry_run by producing no side effect. Timeout is enforced by the
        registry."""
        raise NotImplementedError
