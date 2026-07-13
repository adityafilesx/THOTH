"""Optional local-model persona summary (Phase 5.2 slice 2).

The local model is used ONLY to compress complex VERIFIED facts into a
natural summary. It receives the structured facts, the prohibited-claim
rules, a maximum length, the response mode, and the persona. Its output
must pass the ``FactualConsistencyValidator`` — otherwise the composer
falls back to the deterministic templates. Safety-sensitive intents
(approval, refusal, failure, clarification, degraded) are NEVER
model-phrased so their wording cannot drift. No cloud model is ever used.
"""

from __future__ import annotations

import re
from typing import Protocol

from thoth_daemon.core.persona import (
    PersonaResponse,
    PersonaResponseComposer,
    ResponseFact,
    ResponseIntent,
    ResponseMode,
    ResponsePolicyEngine,
    ResponsePolicyViolation,
    SpokenResponse,
)
from thoth_daemon.inference.base import InferenceRequest, InferenceResult

# Only these intents may be model-summarized; everything else is
# deterministic (safety-sensitive wording must not drift).
_MODEL_SUMMARIZABLE = frozenset(
    {ResponseIntent.VERIFIED_COMPLETION, ResponseIntent.PARTIAL_COMPLETION}
)

_EXECUTION_OR_POLICY_DIRECTIVE = re.compile(
    r"(?:\btool_name\b|\barguments\b|\bshell_run\b|\bapprove\b|\bapproval\b|"
    r"\blower\b.{0,24}\brisk\b|\brisk\b.{0,12}\bR[0-3]\b|\brm\s+-rf\b)",
    re.IGNORECASE,
)
_CAPITALIZED_TARGET = re.compile(r"\b[A-Z][A-Za-z0-9_.-]{2,}\b")
_PROTECTED_TARGET = re.compile(
    r"(?:https?://[^\s,;]+|[\w.+-]+@[\w-]+\.[\w.-]+|"
    r"(?:~|/)[^\s,;]+|\b(?:[a-z0-9-]+\.){2,}[a-z0-9-]+\b)",
    re.IGNORECASE,
)
_GENERIC_CAPITALIZED = frozenset(
    {
        "all",
        "both",
        "everything",
        "facts",
        "four",
        "one",
        "summary",
        "task",
        "the",
        "three",
        "thoth",
        "two",
    }
)

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}


def _number_tokens(text: str) -> set[str]:
    """Digit tokens present in ``text``, with number-words normalized to
    digits so 'Four' and '4' compare equal."""
    tokens = set(re.findall(r"\d+", text))
    for word, digit in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            tokens.add(digit)
    return tokens


class FactualConsistencyError(Exception):
    """A candidate summary is not grounded in the verified facts."""


class FactualConsistencyValidator:
    def __init__(self, policy: ResponsePolicyEngine | None = None) -> None:
        self._policy = policy or ResponsePolicyEngine()

    def validate(self, candidate: str, fact: ResponseFact, max_chars: int = 240) -> None:
        if len(candidate) > max_chars:
            raise FactualConsistencyError(
                f"summary is {len(candidate)} chars, over the {max_chars} limit"
            )
        try:
            self._policy.check(candidate, fact)
        except ResponsePolicyViolation as exc:
            raise FactualConsistencyError(f"policy: {exc}") from exc

        if _EXECUTION_OR_POLICY_DIRECTIVE.search(candidate):
            raise FactualConsistencyError(
                "model summary contains an execution, approval, or policy directive"
            )

        # No invented numbers: every digit token in the candidate must appear
        # in the source facts (counts, ports, versions cannot be hallucinated).
        corpus = " ".join(
            [fact.summary, *fact.succeeded_items, *fact.failed_items, fact.failure_reason or ""]
        )
        corpus_folded = corpus.casefold()
        for token in _PROTECTED_TARGET.findall(candidate):
            if token.casefold().rstrip(".\")'}]") not in corpus_folded:
                raise FactualConsistencyError(f"unsupported named target {token!r}")
        for token in _CAPITALIZED_TARGET.findall(candidate):
            folded = token.casefold()
            if folded not in _GENERIC_CAPITALIZED and folded not in corpus_folded:
                raise FactualConsistencyError(f"unsupported named target {token!r}")

        allowed = _number_tokens(corpus)
        for token in _number_tokens(candidate):
            if token not in allowed:
                raise FactualConsistencyError(f"invented number {token!r} not present in the facts")


def _build_prompt(fact: ResponseFact, mode: ResponseMode, max_chars: int) -> InferenceRequest:
    facts_block = "\n".join(
        [
            *(f"- succeeded: {item}" for item in fact.succeeded_items),
            *(f"- failed: {item}" for item in fact.failed_items),
        ]
    )
    system = (
        "You are THOTH, a calm, precise, restrained operations partner. Rephrase "
        "the VERIFIED facts below into one plain sentence or two. Rules: state only "
        "what is in the facts; invent no numbers, names, paths, or claims; no filler "
        "('Certainly', 'As an AI'); no emotion; do not claim anything not listed. "
        f"Maximum {max_chars} characters. Mode: {mode.value}."
    )
    return InferenceRequest(
        system=system,
        prompt=f"Facts:\n{facts_block}\n\nSummary:",
        max_tokens=160,
        timeout_s=60,
        temperature=0.0,
    )


class _Provider(Protocol):
    async def generate(self, request: InferenceRequest) -> InferenceResult: ...


class PersonaSummaryComposer:
    def __init__(
        self,
        composer: PersonaResponseComposer | None = None,
        validator: FactualConsistencyValidator | None = None,
    ) -> None:
        self._composer = composer or PersonaResponseComposer()
        self._validator = validator or FactualConsistencyValidator()

    async def compose(
        self,
        fact: ResponseFact,
        provider: _Provider,
        mode: ResponseMode = ResponseMode.STANDARD,
    ) -> PersonaResponse:
        template = self._composer.compose(fact, mode)
        if fact.intent not in _MODEL_SUMMARIZABLE:
            return template  # deterministic, never model-phrased

        max_chars = SpokenResponse.model_fields["max_chars"].default * 2
        try:
            result = await provider.generate(_build_prompt(fact, mode, max_chars))
            candidate = result.text.strip()
            self._validator.validate(candidate, fact, max_chars=max_chars)
        except Exception:
            return template  # fall back to the deterministic template

        # Re-phrase the display with the validated model summary; spoken form is
        # still derived deterministically from the validated text.
        spoken = self._composer.compose(fact.model_copy(update={"summary": candidate}), mode).spoken
        return template.model_copy(
            update={
                "display": template.display.model_copy(update={"text": candidate}),
                "spoken": spoken,
                "used_model": True,
            }
        )
