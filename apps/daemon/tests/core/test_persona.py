"""Persona response composition (Phase 5.2 slice 1).

The composer turns immutable, verified structured facts into THOTH's voice.
It NEVER invents facts and never claims completion without verification.
Routine responses are deterministic templates — no LLM. The response
policy engine forbids filler, approval pressure, and success language when
verification did not pass.
"""

import pytest

from thoth_daemon.core.persona import (
    PersonaResponseComposer,
    ResponseFact,
    ResponseIntent,
    ResponseMode,
    ResponsePolicyEngine,
    ResponsePolicyViolation,
)

COMPOSER = PersonaResponseComposer()


def _fact(**kw) -> ResponseFact:
    base = dict(
        intent=ResponseIntent.ACKNOWLEDGEMENT,
        summary="",
        succeeded_items=[],
        failed_items=[],
        verified=None,
        risk=None,
        approval_target=None,
        failure_reason=None,
    )
    base.update(kw)
    return ResponseFact(**base)


class TestDeterministicTemplates:
    def test_acknowledgement(self) -> None:
        r = COMPOSER.compose(_fact(intent=ResponseIntent.ACKNOWLEDGEMENT))
        assert r.display.text == "Understood."
        assert r.used_model is False

    def test_verified_completion_states_facts(self) -> None:
        r = COMPOSER.compose(
            _fact(
                intent=ResponseIntent.VERIFIED_COMPLETION,
                verified=True,
                succeeded_items=[
                    "The daemon and desktop are running",
                    "Both health checks passed",
                    "Four files are modified",
                ],
            )
        )
        assert "health checks passed" in r.display.text
        assert r.used_model is False

    def test_partial_completion_names_what_failed_and_why(self) -> None:
        r = COMPOSER.compose(
            _fact(
                intent=ResponseIntent.PARTIAL_COMPLETION,
                succeeded_items=["The repository is open", "the daemon is healthy"],
                failed_items=["The desktop failed because port 5173 is occupied"],
            )
        )
        assert "repository is open" in r.display.text
        assert "5173" in r.display.text

    def test_approval_states_effect_and_that_nothing_was_sent(self) -> None:
        r = COMPOSER.compose(
            _fact(
                intent=ResponseIntent.APPROVAL_REQUIRED,
                risk="R2",
                approval_target="submit your name and email to example.com",
            )
        )
        assert "Nothing has been sent" in r.display.text
        assert "Approve" in r.display.text

    def test_policy_refusal_gives_the_reason(self) -> None:
        r = COMPOSER.compose(
            _fact(
                intent=ResponseIntent.POLICY_REFUSAL,
                failure_reason="It requests access outside the approved workspace.",
            )
        )
        assert r.display.text.lower().startswith("i won't")
        assert "approved workspace" in r.display.text

    def test_interrupted_states_no_external_action(self) -> None:
        r = COMPOSER.compose(_fact(intent=ResponseIntent.INTERRUPTED))
        assert "Stopped" in r.display.text
        assert "No external action" in r.display.text

    def test_degraded_mode_is_honest(self) -> None:
        r = COMPOSER.compose(_fact(intent=ResponseIntent.DEGRADED_MODE))
        assert "local model" in r.display.text.lower()


class TestFactsAreNotAltered:
    def test_composer_does_not_mutate_input_facts(self) -> None:
        fact = _fact(
            intent=ResponseIntent.VERIFIED_COMPLETION,
            verified=True,
            succeeded_items=["a", "b"],
        )
        before = fact.model_dump()
        COMPOSER.compose(fact)
        assert fact.model_dump() == before  # no mutation

    def test_response_carries_the_exact_policy_facts_unchanged(self) -> None:
        r = COMPOSER.compose(
            _fact(intent=ResponseIntent.APPROVAL_REQUIRED, risk="R2", approval_target="x")
        )
        # The structured facts travel alongside the phrasing, verbatim.
        assert r.facts.risk == "R2"
        assert r.facts.approval_target == "x"


class TestResponsePolicy:
    def _policy(self) -> ResponsePolicyEngine:
        return ResponsePolicyEngine()

    def test_rejects_banned_filler(self) -> None:
        for bad in ("Certainly, done.", "As an AI, I completed it.", "I'd be happy to help!"):
            with pytest.raises(ResponsePolicyViolation):
                self._policy().check(bad, _fact(intent=ResponseIntent.ACKNOWLEDGEMENT))

    def test_rejects_success_language_when_not_verified(self) -> None:
        with pytest.raises(ResponsePolicyViolation):
            self._policy().check(
                "Done — everything completed successfully.",
                _fact(intent=ResponseIntent.FAILED, verified=False),
            )

    def test_rejects_completion_language_for_proposed_action(self) -> None:
        with pytest.raises(ResponsePolicyViolation):
            self._policy().check(
                "I have submitted the form.",
                _fact(intent=ResponseIntent.APPROVAL_REQUIRED, risk="R2"),
            )

    def test_rejects_approval_pressure(self) -> None:
        for bad in ("You should really approve this now.", "Just approve it, it's fine."):
            with pytest.raises(ResponsePolicyViolation):
                self._policy().check(bad, _fact(intent=ResponseIntent.APPROVAL_REQUIRED))

    def test_rejects_unsupported_emotional_claim(self) -> None:
        with pytest.raises(ResponsePolicyViolation):
            self._policy().check(
                "I'm so excited and I feel proud of this!",
                _fact(intent=ResponseIntent.VERIFIED_COMPLETION, verified=True),
            )

    def test_accepts_clean_verified_completion(self) -> None:
        self._policy().check(
            "The build passed. Four files are modified.",
            _fact(intent=ResponseIntent.VERIFIED_COMPLETION, verified=True),
        )


class TestSpokenDisplaySeparation:
    def test_spoken_is_within_the_length_cap_and_omits_technical_detail(self) -> None:
        r = COMPOSER.compose(
            _fact(
                intent=ResponseIntent.VERIFIED_COMPLETION,
                verified=True,
                succeeded_items=[
                    "The daemon is running at /Users/x/thoth on port 7710",
                    "Both health checks passed",
                    "Four files are modified in ~/projects/thoth/apps/daemon/src",
                ],
            ),
            mode=ResponseMode.CONCISE,
        )
        assert len(r.spoken.text) <= r.spoken.max_chars
        # Spoken form suppresses paths/ports; the display form may keep them.
        assert "7710" not in r.spoken.text
        assert len(r.display.text) >= len(r.spoken.text)

    def test_ambient_mode_is_minimal(self) -> None:
        r = COMPOSER.compose(
            _fact(intent=ResponseIntent.EXECUTION_PROGRESS, summary="executing step 2 of 4"),
            mode=ResponseMode.AMBIENT,
        )
        assert r.spoken.text == ""  # ambient does not speak routine progress
        assert r.display.text


class TestAllIntentsHaveATemplate:
    @pytest.mark.parametrize("intent", list(ResponseIntent))
    def test_every_intent_composes_without_a_model(self, intent: ResponseIntent) -> None:
        r = COMPOSER.compose(
            _fact(intent=intent, verified=(intent == ResponseIntent.VERIFIED_COMPLETION))
        )
        assert r.display.text
        assert r.used_model is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
