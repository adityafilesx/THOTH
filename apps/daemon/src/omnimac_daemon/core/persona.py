"""Persona response composition (Phase 5.2).

OmniMac's voice: calm, precise, restrained, slightly formal, quiet during
routine execution, honest about uncertainty, confident only when
verification supports it.

The composer is a POST-verification composition layer. It receives
immutable, verified structured facts and phrases them; it never invents a
fact, never claims completion without verification, and cannot alter any
execution/policy/verification/audit datum — those travel alongside the
phrasing verbatim (``PersonaResponse.facts``). Routine responses are
deterministic templates: NO language model is required. A separate,
optional local-model summary path (slice 2) is gated by a factual-
consistency validator and falls back to these templates.

The ``ResponsePolicyEngine`` is the guard rail on ANY candidate text
(template or model): it forbids filler ("Certainly", "As an AI"), approval
pressure, unsupported emotional claims, success language when verification
did not pass, and completion language for a merely-proposed action.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ResponseMode(StrEnum):
    AMBIENT = "ambient"
    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


class ResponseIntent(StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    PLAN_READY = "plan_ready"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTION_PROGRESS = "execution_progress"
    VERIFIED_COMPLETION = "verified_completion"
    PARTIAL_COMPLETION = "partial_completion"
    FAILED = "failed"
    POLICY_REFUSAL = "policy_refusal"
    NEEDS_CLARIFICATION = "needs_clarification"
    INTERRUPTED = "interrupted"
    DEGRADED_MODE = "degraded_mode"
    RESUMABLE_TASK = "resumable_task"


class AccessibilityOutcome(StrEnum):
    PERMISSION_MISSING = "permission_missing"
    PERMISSION_REVOKED = "permission_revoked"
    ELEMENT_NOT_FOUND = "element_not_found"
    MULTIPLE_ELEMENTS = "multiple_elements"
    ELEMENT_DISABLED = "element_disabled"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    ACTION_VERIFIED = "action_verified"
    PARTIAL_COMPLETION = "partial_completion"
    FOCUS_RESTORATION_FAILED = "focus_restoration_failed"
    APPLICATION_CLOSED = "application_closed"
    STALE_REFERENCE = "stale_reference"
    ACTION_CANCELLED = "action_cancelled"


class ResponseFact(BaseModel):
    """Immutable, verified facts the composer may phrase but never change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: ResponseIntent
    summary: str = ""
    succeeded_items: list[str] = Field(default_factory=list)
    failed_items: list[str] = Field(default_factory=list)
    verified: bool | None = None
    risk: str | None = None
    approval_target: str | None = None
    failure_reason: str | None = None
    clarification_question: str | None = None
    resumable_step: str | None = None
    step_progress: str | None = None
    accessibility_outcome: AccessibilityOutcome | None = None
    application_name: str | None = None


class SpokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    max_chars: int = 240


class DisplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class PersonaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ResponseIntent
    mode: ResponseMode
    spoken: SpokenResponse
    display: DisplayResponse
    facts: ResponseFact  # the verbatim structured facts, unaltered
    used_model: bool = False


class ResponsePolicyViolation(Exception):
    """Candidate text violated the persona response policy."""


_BANNED_PHRASES = (
    "certainly",
    "as an ai",
    "as a language model",
    "i'd be happy to",
    "i am happy to",
    "happy to help",
    "no problem",
    "of course!",
)

_APPROVAL_PRESSURE = (
    "you should really",
    "just approve",
    "go ahead and approve",
    "why not approve",
    "trust me",
    "it's fine",
    "it is fine",
)

_EMOTION_CLAIMS = (
    "i'm so excited",
    "i am so excited",
    "i feel proud",
    "i'm proud",
    "i am proud",
    "i love",
    "i'm thrilled",
    "i am thrilled",
    "i feel",
)

_SUCCESS_WORDS = re.compile(r"\b(done|completed?|succeeded|success(fully)?|finished|all set)\b", re.IGNORECASE)
_COMPLETION_CLAIM = re.compile(
    r"\bi (have |'ve )?(submitted|sent|deleted|committed|pushed|created|opened|ran|executed)\b",
    re.IGNORECASE,
)

# Intents for which overall success language is never truthful.
_NO_SUCCESS_INTENTS = frozenset(
    {
        ResponseIntent.FAILED,
        ResponseIntent.POLICY_REFUSAL,
        ResponseIntent.APPROVAL_REQUIRED,
        ResponseIntent.PLAN_READY,
        ResponseIntent.NEEDS_CLARIFICATION,
        ResponseIntent.EXECUTION_PROGRESS,
        ResponseIntent.DEGRADED_MODE,
        ResponseIntent.INTERRUPTED,
        ResponseIntent.RESUMABLE_TASK,
    }
)


class ResponsePolicyEngine:
    def check(self, text: str, fact: ResponseFact) -> None:
        low = text.lower()

        for phrase in _BANNED_PHRASES:
            if phrase in low:
                raise ResponsePolicyViolation(f"banned filler: {phrase!r}")

        if fact.intent is ResponseIntent.APPROVAL_REQUIRED:
            for phrase in _APPROVAL_PRESSURE:
                if phrase in low:
                    raise ResponsePolicyViolation(f"approval pressure: {phrase!r}")
            if _COMPLETION_CLAIM.search(text):
                raise ResponsePolicyViolation("completion language for a merely-proposed (approval-pending) action")

        for phrase in _EMOTION_CLAIMS:
            if phrase in low:
                raise ResponsePolicyViolation(f"unsupported emotional claim: {phrase!r}")

        # Success language is only allowed when verification passed. It is
        # forbidden outright for intents where overall success would be a lie
        # (a failure, a refusal, a merely-proposed or in-flight action).
        # PARTIAL_COMPLETION is exempt: it legitimately reports mixed results.
        if fact.intent is ResponseIntent.VERIFIED_COMPLETION:
            if fact.verified is not True and _SUCCESS_WORDS.search(text):
                raise ResponsePolicyViolation("success language without a passing verification result")
        elif fact.intent in _NO_SUCCESS_INTENTS and _SUCCESS_WORDS.search(text):
            raise ResponsePolicyViolation(f"success language is not permitted for a {fact.intent.value} response")


def _join(items: list[str]) -> str:
    parts = [p.strip().rstrip(".") for p in items if p.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0] + "."
    return ". ".join(parts) + "."


# Technical detail suppressed in spoken form (paths, ports, long hex).
_TECHNICAL = re.compile(r"(/[\w./~-]+|\b\d{2,5}\b|\b[0-9a-f]{7,}\b|port \d+)", re.IGNORECASE)


class PersonaResponseComposer:
    def __init__(self, policy: ResponsePolicyEngine | None = None) -> None:
        self._policy = policy or ResponsePolicyEngine()

    def compose(self, fact: ResponseFact, mode: ResponseMode = ResponseMode.STANDARD) -> PersonaResponse:
        display_text = self._template(fact)
        # The response policy validates our own templates too — a template
        # that ever drifts into forbidden language fails loudly in tests.
        self._policy.check(display_text, fact)

        spoken_text = self._spoken(fact, display_text, mode)
        spoken = SpokenResponse(text=spoken_text)
        if spoken_text:
            self._policy.check(spoken_text, fact)

        return PersonaResponse(
            intent=fact.intent,
            mode=mode,
            spoken=spoken,
            display=DisplayResponse(text=display_text),
            facts=fact,
            used_model=False,
        )

    # -- deterministic templates -----------------------------------------
    def _template(self, fact: ResponseFact) -> str:
        if fact.accessibility_outcome is not None:
            return self._accessibility_template(fact)
        intent = fact.intent
        if intent is ResponseIntent.ACKNOWLEDGEMENT:
            return fact.summary or "Right away, sir."
        if intent is ResponseIntent.PLAN_READY:
            return fact.summary or "I have prepared a plan for your review, sir."
        if intent is ResponseIntent.APPROVAL_REQUIRED:
            target = fact.approval_target or "this action"
            return f"This will {target}. Shall I proceed, sir?"
        if intent is ResponseIntent.EXECUTION_PROGRESS:
            return fact.step_progress or fact.summary or "On it, sir."
        if intent is ResponseIntent.VERIFIED_COMPLETION:
            body = _join(fact.succeeded_items) or (fact.summary or "The task is complete.")
            return body
        if intent is ResponseIntent.PARTIAL_COMPLETION:
            ok = _join(fact.succeeded_items)
            bad = _join(fact.failed_items)
            return " ".join(p for p in (ok, bad) if p) or "The task was only partially completed, sir."
        if intent is ResponseIntent.FAILED:
            reason = fact.failure_reason or "an error occurred"
            return f"I'm afraid the task failed, sir: {reason}"
        if intent is ResponseIntent.POLICY_REFUSAL:
            reason = fact.failure_reason or "it is outside my approved scope."
            return f"I cannot execute that, sir. {reason}"
        if intent is ResponseIntent.NEEDS_CLARIFICATION:
            return fact.clarification_question or "I require some clarification before proceeding, sir."
        if intent is ResponseIntent.INTERRUPTED:
            return "Stopped as requested, sir. No action was taken."
        if intent is ResponseIntent.DEGRADED_MODE:
            return "The local model is unavailable, so I'm limited to deterministic commands and installed skills."
        if intent is ResponseIntent.RESUMABLE_TASK:
            step = fact.resumable_step or "where it left off"
            return f"I can resume the task from {step}. Shall I proceed, sir?"
        return fact.summary or "Right away, sir."  # pragma: no cover - exhaustive above

    @staticmethod
    def _accessibility_template(fact: ResponseFact) -> str:
        outcome = fact.accessibility_outcome
        if outcome is None:  # guarded by _template; keeps this helper total
            raise ValueError("an Accessibility outcome is required")
        app = fact.application_name or "the application"
        templates = {
            AccessibilityOutcome.PERMISSION_MISSING: (f"Accessibility permission is not granted. I did not interact with {app}."),
            AccessibilityOutcome.PERMISSION_REVOKED: (f"Accessibility permission was revoked. I did not interact with {app}."),
            AccessibilityOutcome.ELEMENT_NOT_FOUND: (f"I could not find the requested element in {app}. No action was taken."),
            AccessibilityOutcome.MULTIPLE_ELEMENTS: (f"I found multiple matching elements in {app}. No action was taken."),
            AccessibilityOutcome.ELEMENT_DISABLED: (f"The requested element in {app} is disabled. No action was taken."),
            AccessibilityOutcome.UNSUPPORTED_CAPABILITY: (f"That Accessibility capability is not supported for {app}. No action was taken."),
            AccessibilityOutcome.ACTION_VERIFIED: (f"The Accessibility action in {app} was independently verified."),
            AccessibilityOutcome.PARTIAL_COMPLETION: (
                "The verified substep was completed, but the remaining Accessibility action could not be verified."
            ),
            AccessibilityOutcome.FOCUS_RESTORATION_FAILED: ("The Accessibility action was verified, but focus restoration failed."),
            AccessibilityOutcome.APPLICATION_CLOSED: (
                f"The application closed during the Accessibility action. No further action was taken in {app}."
            ),
            AccessibilityOutcome.STALE_REFERENCE: (f"The Accessibility element reference was stale in {app}. No action was taken."),
            AccessibilityOutcome.ACTION_CANCELLED: ("The Accessibility action was cancelled. No further action was taken."),
        }
        return templates[outcome]

    # -- spoken form ------------------------------------------------------
    def _spoken(self, fact: ResponseFact, display_text: str, mode: ResponseMode) -> str:
        if mode is ResponseMode.AMBIENT and fact.intent is ResponseIntent.EXECUTION_PROGRESS:
            return ""  # ambient does not speak routine progress
        if fact.accessibility_outcome is not None:
            spoken_templates = {
                AccessibilityOutcome.PERMISSION_MISSING: "Accessibility permission is missing, sir.",
                AccessibilityOutcome.PERMISSION_REVOKED: "Accessibility permission was revoked, sir.",
                AccessibilityOutcome.ELEMENT_NOT_FOUND: "I could not find the element, sir.",
                AccessibilityOutcome.MULTIPLE_ELEMENTS: "Multiple elements matched, sir.",
                AccessibilityOutcome.ELEMENT_DISABLED: "The element is disabled, sir.",
                AccessibilityOutcome.UNSUPPORTED_CAPABILITY: "That capability is not supported, sir.",
                AccessibilityOutcome.ACTION_VERIFIED: "The UI result was verified, sir.",
                AccessibilityOutcome.PARTIAL_COMPLETION: ("The UI action was only partially verified, sir."),
                AccessibilityOutcome.FOCUS_RESTORATION_FAILED: ("The action was verified, but focus was not restored, sir."),
                AccessibilityOutcome.APPLICATION_CLOSED: ("The application closed during the action, sir."),
                AccessibilityOutcome.STALE_REFERENCE: "The element reference was stale, sir.",
                AccessibilityOutcome.ACTION_CANCELLED: "The action was cancelled, sir.",
            }
            return spoken_templates[fact.accessibility_outcome]
        # Suppress technical detail (paths/ports/hashes) in the spoken form.
        spoken = _TECHNICAL.sub("", display_text)
        spoken = re.sub(r"\s{2,}", " ", spoken).replace(" .", ".").replace(" ,", ",").strip()
        cap = SpokenResponse.model_fields["max_chars"].default
        if len(spoken) > cap:
            spoken = spoken[: cap - 1].rstrip() + "…"
        return spoken
