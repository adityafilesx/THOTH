"""Capstone harness (Phase 4 slice 10).

The harness runs a natural-language goal through the FULL pipeline
(plan → policy review → approval → real tool execution → in-loop
verification → bounded recovery) and then re-verifies the FINAL world
state with independent probes (core/verifiers, real context). The five
capstone definitions each carry a scripted reference plan for offline
harness proof; the live-planner runs (--planner claude) are pending an
API key. Approvals in harness runs are granted programmatically through
the real single-use ApprovalEngine — the machinery is exercised, the
human step is simulated and recorded as such.
"""

from pathlib import Path

import pytest

from omnimac_daemon.evals.capstones import (
    CAPSTONES,
    CapstoneResult,
    CapstoneWorkflow,
    render_capstone_report,
    run_capstone,
)
from omnimac_daemon.schemas import (
    PlanStep,
    RiskLevel,
    TaskState,
    VerificationCheck,
    VerifierKind,
)


def _write_note_capstone(ws: Path) -> CapstoneWorkflow:
    return CapstoneWorkflow(
        name="write-note",
        goal=f"Create a note file at {ws}/note.txt containing 'phase four'",
        reference_steps=[
            PlanStep(
                index=0,
                title="write the note",
                tool_name="fs_write_file",
                arguments={"path": str(ws / "note.txt"), "content": "phase four"},
                declared_risk=RiskLevel.R1,
            )
        ],
        final_checks=[
            VerificationCheck(kind=VerifierKind.FILE_EXISTS, params={"path": str(ws / "note.txt")}),
            VerificationCheck(
                kind=VerifierKind.FILE_CONTENT,
                params={"path": str(ws / "note.txt"), "contains": "phase four"},
            ),
        ],
    )


class TestHarness:
    async def test_capstone_completes_and_final_state_verified(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        result = await run_capstone(_write_note_capstone(ws), workspace=ws, planner="scripted")
        assert result.task_state == TaskState.COMPLETED.value
        assert result.final_state_verified
        assert all(c.passed for c in result.check_results)
        assert (ws / "note.txt").read_text() == "phase four"

    async def test_final_check_failure_is_reported_not_hidden(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        capstone = _write_note_capstone(ws)
        capstone = capstone.model_copy(
            update={"final_checks": [VerificationCheck(kind=VerifierKind.FILE_EXISTS, params={"path": str(ws / "other.txt")})]}
        )
        result = await run_capstone(capstone, workspace=ws, planner="scripted")
        assert result.task_state == TaskState.COMPLETED.value  # task itself succeeded
        assert not result.final_state_verified  # but the capstone is NOT verified

    async def test_r2_step_requires_and_records_approval(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        capstone = CapstoneWorkflow(
            name="r2-flow",
            goal="write with explicit approval",
            reference_steps=[
                PlanStep(
                    index=0,
                    title="write the note",
                    tool_name="fs_write_file",
                    arguments={"path": str(ws / "a.txt"), "content": "x"},
                    declared_risk=RiskLevel.R2,  # force approval
                )
            ],
            final_checks=[VerificationCheck(kind=VerifierKind.FILE_EXISTS, params={"path": str(ws / "a.txt")})],
        )
        result = await run_capstone(capstone, workspace=ws, planner="scripted")
        assert result.task_state == TaskState.COMPLETED.value
        assert result.approvals_granted == 1
        assert result.final_state_verified


class TestDefinitions:
    def test_five_capstones_defined(self) -> None:
        assert len(CAPSTONES) == 5
        names = {c.name for c in CAPSTONES}
        assert names == {
            "create-project-note",
            "continue-project",
            "research-and-save",
            "prepare-commit",
            "launch-app",
        }
        for capstone in CAPSTONES:
            assert capstone.goal  # natural-language goal
            assert capstone.final_checks  # independent final-state verification
            assert capstone.reference_steps  # scripted harness-proof plan

    def test_report_renders_without_arguments(self, tmp_path: Path) -> None:
        result = CapstoneResult(
            capstone="write-note",
            planner="scripted",
            task_state="COMPLETED",
            approvals_granted=0,
            check_results=[],
            final_state_verified=True,
            detail="ok",
        )
        md = render_capstone_report([result], planner="scripted")
        assert "write-note" in md
        assert "scripted" in md
        assert "pending live verification" in md.lower()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
