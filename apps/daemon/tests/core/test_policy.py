import pytest

from omnimac_daemon.core.policy import PolicyEngine
from omnimac_daemon.schemas import RiskLevel

engine = PolicyEngine()


def evaluate(
    declared: RiskLevel,
    tool_default: RiskLevel | None,
    trusted: bool = False,
) -> object:
    return engine.evaluate(
        tool_name="mock_tool",
        declared_risk=declared,
        tool_default_risk=tool_default,
        workspace_trusted=trusted,
    )


class TestClassification:
    def test_r0_runs_automatically(self) -> None:
        d = evaluate(RiskLevel.R0, RiskLevel.R0)
        assert d.allowed and not d.requires_approval
        assert d.effective_risk is RiskLevel.R0

    def test_r1_requires_approval_outside_trusted_workspace(self) -> None:
        d = evaluate(RiskLevel.R1, RiskLevel.R1, trusted=False)
        assert d.allowed and d.requires_approval

    def test_r1_auto_in_trusted_workspace(self) -> None:
        d = evaluate(RiskLevel.R1, RiskLevel.R1, trusted=True)
        assert d.allowed and not d.requires_approval

    def test_r2_always_requires_approval_even_in_trusted_workspace(self) -> None:
        d = evaluate(RiskLevel.R2, RiskLevel.R2, trusted=True)
        assert d.allowed and d.requires_approval

    def test_r3_blocked_by_default(self) -> None:
        d = evaluate(RiskLevel.R3, RiskLevel.R3, trusted=True)
        assert not d.allowed
        assert any("R3" in r or "blocked" in r.lower() for r in d.reasons)


class TestNoDowngrade:
    def test_step_cannot_downgrade_tool_risk(self) -> None:
        d = evaluate(declared=RiskLevel.R0, tool_default=RiskLevel.R2)
        assert d.effective_risk is RiskLevel.R2
        assert d.requires_approval

    def test_step_can_upgrade_tool_risk(self) -> None:
        d = evaluate(declared=RiskLevel.R2, tool_default=RiskLevel.R0)
        assert d.effective_risk is RiskLevel.R2

    def test_r3_tool_cannot_be_smuggled_as_r0_step(self) -> None:
        d = evaluate(declared=RiskLevel.R0, tool_default=RiskLevel.R3)
        assert not d.allowed


class TestUnknownTool:
    def test_unknown_tool_denied(self) -> None:
        d = evaluate(RiskLevel.R0, tool_default=None)
        assert not d.allowed
        assert any("unknown" in r.lower() for r in d.reasons)


class TestTypedInputsOnly:
    def test_evaluate_accepts_no_free_text_beyond_tool_name(self) -> None:
        """The policy engine's signature is the enforcement surface: it takes
        typed enums/bools only, so model prose or untrusted content cannot
        influence a decision."""
        import inspect

        params = inspect.signature(engine.evaluate).parameters
        assert set(params) == {
            "tool_name",
            "declared_risk",
            "tool_default_risk",
            "workspace_trusted",
        }

    def test_reasons_are_always_present_for_denials(self) -> None:
        for declared, default in [
            (RiskLevel.R3, RiskLevel.R3),
            (RiskLevel.R0, None),
        ]:
            d = evaluate(declared, default)
            assert not d.allowed and d.reasons


@pytest.mark.parametrize(
    ("declared", "default", "expected"),
    [
        (RiskLevel.R0, RiskLevel.R0, RiskLevel.R0),
        (RiskLevel.R0, RiskLevel.R1, RiskLevel.R1),
        (RiskLevel.R1, RiskLevel.R0, RiskLevel.R1),
        (RiskLevel.R2, RiskLevel.R1, RiskLevel.R2),
        (RiskLevel.R1, RiskLevel.R2, RiskLevel.R2),
    ],
)
def test_effective_risk_is_max(declared: RiskLevel, default: RiskLevel, expected: RiskLevel) -> None:
    assert evaluate(declared, default).effective_risk is expected
