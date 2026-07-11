from enum import StrEnum


class TaskState(StrEnum):
    RECEIVED = "RECEIVED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    RISK_REVIEW = "RISK_REVIEW"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED})


class RiskLevel(StrEnum):
    """R0 read-only · R1 reversible local · R2 external side effect ·
    R3 destructive/highly sensitive (blocked by default).

    Totally ordered so that ``max()`` expresses the no-downgrade rule.
    """

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"

    @property
    def rank(self) -> int:
        return int(self.value[1])

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank >= other.rank


class TaskSource(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class Provenance(StrEnum):
    USER_TRUSTED = "USER_TRUSTED"
    SYSTEM_TRUSTED = "SYSTEM_TRUSTED"
    TOOL_RESULT_UNTRUSTED = "TOOL_RESULT_UNTRUSTED"
    WEB_UNTRUSTED = "WEB_UNTRUSTED"
    FILE_UNTRUSTED = "FILE_UNTRUSTED"


TRUSTED_PROVENANCE = frozenset({Provenance.USER_TRUSTED, Provenance.SYSTEM_TRUSTED})


class VerificationStrategy(StrEnum):
    OUTPUT_ASSERTION = "output_assertion"
    STATE_PROBE = "state_probe"
    NONE_READONLY = "none_readonly"
