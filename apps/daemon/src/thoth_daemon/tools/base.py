"""Tool contract base.

Every tool exposes the full contract from docs/TOOL_CONTRACTS.md: unique
name, typed input/output models, default risk, timeout, cancellation and
dry-run behavior, verification strategy, resource scope, and redaction
fields. No tool accepts arbitrary shell text (that is reserved for the
dedicated restricted shell tool in Phase 3).
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from thoth_daemon.schemas import (
    ResourceScope,
    RiskLevel,
    ToolInvocation,
    VerificationStrategy,
)

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class UnknownToolError(Exception):
    pass


class DuplicateToolError(Exception):
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
    redaction_fields: list[str] = []

    def __init__(self) -> None:
        if not getattr(self, "resource_scope", None):
            self.resource_scope = ResourceScope()

    def parse_arguments(self, invocation: ToolInvocation) -> BaseModel:
        """Validate raw args against input_model (extra='forbid')."""
        return self.input_model.model_validate(invocation.arguments)

    @abstractmethod
    async def run(self, args: Any, dry_run: bool) -> BaseModel:
        """Execute the tool. Must cooperate with cancellation and honor
        dry_run by producing no side effect. Timeout is enforced by the
        registry."""
        raise NotImplementedError
