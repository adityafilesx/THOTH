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
    FAILED_REQUIRES_USER = "FAILED_REQUIRES_USER"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.FAILED_REQUIRES_USER, TaskState.CANCELLED})


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


class FocusPolicy(StrEnum):
    """Authoritative final-focus behaviour declared by registered tools."""

    KEEP_NEW_FOCUS = "keep_new_focus"
    RESTORE_PREVIOUS_FOCUS = "restore_previous_focus"
    DO_NOT_STEAL_FOCUS = "do_not_steal_focus"
    ASK_IF_AMBIGUOUS = "ask_if_ambiguous"


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
    INVALIDATED = "invalidated"


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


class VerifierKind(StrEnum):
    """Independent state probes (Phase 4 slice 7). Each confirms a real
    postcondition after a tool runs — never trusting the tool's own
    success flag. COMPOSITE combines children with all/any semantics."""

    FILE_EXISTS = "file_exists"
    FILE_CONTENT = "file_content"
    PROCESS_RUNNING = "process_running"
    PORT_LISTENING = "port_listening"
    HTTP_HEALTH = "http_health"
    GIT_STATE = "git_state"
    APPLICATION_RUNNING = "application_running"
    ACCESSIBILITY_VALUE = "accessibility_value"
    BROWSER_URL = "browser_url"
    BROWSER_ELEMENT = "browser_element"
    EXIT_CODE = "exit_code"
    COMPOSITE = "composite"
