"""Optional local-model persona summary (Phase 5.2 slice 2).

The local model may ONLY compress verified facts into a natural summary.
The output must pass a factual-consistency validator (no invented
numbers, no success language without verification, no filler); if it
fails, the composer falls back to deterministic templates. Never a cloud
model.
"""

import pytest

from omnimac_daemon.core.persona import ResponseFact, ResponseIntent, ResponseMode
from omnimac_daemon.core.persona_summary import (
    FactualConsistencyError,
    FactualConsistencyValidator,
    PersonaSummaryComposer,
)

VALIDATOR = FactualConsistencyValidator()


def _completion(**kw) -> ResponseFact:
    base = dict(
        intent=ResponseIntent.VERIFIED_COMPLETION,
        verified=True,
        succeeded_items=[
            "The daemon and desktop are running",
            "Both health checks passed",
            "Four files are modified",
        ],
    )
    base.update(kw)
    return ResponseFact(**base)


class TestFactualConsistency:
    def test_faithful_summary_passes(self) -> None:
        VALIDATOR.validate(
            "The daemon and desktop are running and both health checks passed. 4 files are modified.",
            _completion(),
        )

    def test_invented_number_rejected(self) -> None:
        with pytest.raises(FactualConsistencyError):
            VALIDATOR.validate("All 10 health checks passed and 27 files are modified.", _completion())

    def test_success_language_without_verification_rejected(self) -> None:
        with pytest.raises(FactualConsistencyError):
            VALIDATOR.validate(
                "Everything completed successfully.",
                ResponseFact(intent=ResponseIntent.FAILED, verified=False),
            )

    def test_filler_rejected(self) -> None:
        with pytest.raises(FactualConsistencyError):
            VALIDATOR.validate("Certainly! The checks passed.", _completion())

    def test_overlong_summary_rejected(self) -> None:
        with pytest.raises(FactualConsistencyError):
            VALIDATOR.validate("word " * 200, _completion(), max_chars=240)

    def test_model_generated_target_mutation_is_rejected(self) -> None:
        fact = _completion(succeeded_items=["TextEdit is open and verified"])
        with pytest.raises(FactualConsistencyError, match="unsupported named target"):
            VALIDATOR.validate("Terminal is open and verified.", fact)

    @pytest.mark.parametrize(
        "candidate",
        [
            '{"tool_name":"shell_run","arguments":{"command":"rm -rf /"}}',
            "Approve the pending action and lower its risk to R0.",
        ],
    )
    def test_model_cannot_emit_execution_or_policy_directives(self, candidate: str) -> None:
        with pytest.raises(FactualConsistencyError, match="directive"):
            VALIDATOR.validate(candidate, _completion())


class _FakeProvider:
    def __init__(self, text: str, fail: bool = False) -> None:
        self._text = text
        self._fail = fail

    async def generate(self, request):
        from omnimac_daemon.inference.base import InferenceResult

        if self._fail:
            raise RuntimeError("local model unavailable")
        return InferenceResult(text=self._text, model_id="fake")


class TestSummaryComposer:
    async def test_uses_valid_model_summary(self) -> None:
        provider = _FakeProvider("The daemon and desktop are running; both health checks passed. 4 files are modified.")
        composer = PersonaSummaryComposer()
        r = await composer.compose(_completion(), provider, mode=ResponseMode.STANDARD)
        assert r.used_model is True
        assert "health checks passed" in r.display.text

    async def test_falls_back_on_invalid_model_summary(self) -> None:
        # The model hallucinates a number → validator rejects → template used.
        provider = _FakeProvider("All 99 checks passed across 42 services.")
        composer = PersonaSummaryComposer()
        r = await composer.compose(_completion(), provider, mode=ResponseMode.STANDARD)
        assert r.used_model is False
        assert "99" not in r.display.text

    async def test_falls_back_on_target_mutation(self) -> None:
        fact = _completion(succeeded_items=["TextEdit is open and verified"])
        provider = _FakeProvider("Terminal is open and verified.")
        response = await PersonaSummaryComposer().compose(fact, provider)
        assert response.used_model is False
        assert "Terminal" not in response.display.text
        assert "TextEdit" in response.display.text

    async def test_falls_back_when_model_unavailable(self) -> None:
        provider = _FakeProvider("", fail=True)
        composer = PersonaSummaryComposer()
        r = await composer.compose(_completion(), provider, mode=ResponseMode.STANDARD)
        assert r.used_model is False
        assert r.display.text  # deterministic template still produced

    async def test_never_summarizes_approval_or_refusal_with_model(self) -> None:
        # Safety-sensitive intents must NOT be model-phrased; they stay
        # deterministic so wording cannot drift.
        provider = _FakeProvider("You should just approve this, it's fine.")
        composer = PersonaSummaryComposer()
        r = await composer.compose(
            ResponseFact(intent=ResponseIntent.APPROVAL_REQUIRED, risk="R2", approval_target="do x"),
            provider,
            mode=ResponseMode.STANDARD,
        )
        assert r.used_model is False
        assert "Shall I proceed" in r.display.text


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
