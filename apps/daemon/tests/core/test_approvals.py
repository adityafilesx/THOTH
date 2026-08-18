from datetime import UTC, datetime, timedelta

import pytest

from omnimac_daemon.core.approvals import (
    ApprovalEngine,
    ApprovalRequiredError,
    UnknownApprovalError,
)
from omnimac_daemon.schemas import ApprovalStatus, RiskLevel

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)


def make_engine(ttl: int = 120) -> ApprovalEngine:
    return ApprovalEngine(ttl_seconds=ttl, clock=lambda: NOW)


def request(engine: ApprovalEngine, invocation_id: str = "inv-1") -> str:
    req = engine.request(
        task_id="t1",
        invocation_id=invocation_id,
        step_id="s1",
        tool_name="mock_send_email",
        arguments={"recipient": "a@b.c", "body": "hi"},
        risk=RiskLevel.R2,
        reason="external side effect",
        target="a@b.c",
    )
    return req.id


class TestEnforcement:
    def test_execution_without_any_approval_is_blocked(self) -> None:
        engine = make_engine()
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-1")

    def test_pending_request_does_not_authorize(self) -> None:
        engine = make_engine()
        request(engine)
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-1")

    def test_denied_request_does_not_authorize(self) -> None:
        engine = make_engine()
        rid = request(engine)
        engine.decide(rid, approved=False)
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-1")

    def test_approval_bound_to_exact_invocation(self) -> None:
        engine = make_engine()
        rid = request(engine, invocation_id="inv-1")
        engine.decide(rid, approved=True)
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-OTHER")

    def test_approved_request_authorizes_exactly_once(self) -> None:
        engine = make_engine()
        rid = request(engine)
        engine.decide(rid, approved=True)
        grant = engine.authorize_execution("inv-1")
        assert grant.request_id == rid
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-1")  # single-use: consumed

    def test_expired_approval_does_not_authorize(self) -> None:
        moving_now = [NOW]
        engine = ApprovalEngine(ttl_seconds=60, clock=lambda: moving_now[0])
        req = engine.request(
            task_id="t1",
            invocation_id="inv-1",
            step_id="s1",
            tool_name="mock_send_email",
            arguments={},
            risk=RiskLevel.R2,
            reason="r",
            target="x",
        )
        engine.decide(req.id, approved=True)
        moving_now[0] = NOW + timedelta(seconds=61)
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("inv-1")


class TestDecisions:
    def test_decide_unknown_request_raises(self) -> None:
        engine = make_engine()
        with pytest.raises(UnknownApprovalError):
            engine.decide("nope", approved=True)

    def test_double_decision_rejected(self) -> None:
        engine = make_engine()
        rid = request(engine)
        engine.decide(rid, approved=True)
        with pytest.raises(UnknownApprovalError):
            engine.decide(rid, approved=True)

    def test_modified_arguments_flow_through_grant(self) -> None:
        engine = make_engine()
        rid = request(engine)
        engine.decide(rid, approved=True, modified_arguments={"recipient": "c@d.e", "body": "hi"})
        grant = engine.authorize_execution("inv-1")
        assert grant.arguments == {"recipient": "c@d.e", "body": "hi"}

    def test_pending_listing(self) -> None:
        engine = make_engine()
        rid = request(engine)
        assert [r.id for r in engine.pending()] == [rid]
        engine.decide(rid, approved=False)
        assert engine.pending() == []
        assert engine.get(rid).status is ApprovalStatus.DENIED

    def test_invalidate_for_task_revokes_pending_and_granted_approval(self) -> None:
        engine = make_engine()
        pending_id = request(engine, invocation_id="pending-inv")
        granted_id = request(engine, invocation_id="granted-inv")
        engine.decide(granted_id, approved=True)

        invalidated = engine.invalidate_for_task("t1")

        assert invalidated == {pending_id, granted_id}
        assert engine.get(pending_id).status is ApprovalStatus.INVALIDATED
        assert engine.get(granted_id).status is ApprovalStatus.INVALIDATED
        with pytest.raises(ApprovalRequiredError):
            engine.authorize_execution("granted-inv")

    def test_invalidate_all_does_not_change_consumed_or_denied_requests(self) -> None:
        engine = make_engine()
        consumed_id = request(engine, invocation_id="consumed")
        engine.decide(consumed_id, approved=True)
        engine.authorize_execution("consumed")
        denied_id = request(engine, invocation_id="denied")
        engine.decide(denied_id, approved=False)

        assert engine.invalidate_all() == set()
        assert engine.get(consumed_id).status is ApprovalStatus.APPROVED
        assert engine.get(denied_id).status is ApprovalStatus.DENIED
