"""Focus policy and restoration (Phase 5.3 slice 5).

Predictable focus management around focus-changing tool actions. Each
focus-changing tool declares an intended ``FocusPolicy``; the
``FocusManager`` records the prior focus, performs the action, restores
the previous application where the policy requires, and INDEPENDENTLY
verifies the final frontmost application via the OS. ASK_IF_AMBIGUOUS
never steals focus automatically — it defers to the user.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from omnimac_daemon.macos.app_control import AppControl
from omnimac_daemon.schemas.enums import FocusPolicy as FocusPolicy


class FocusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    bundle_id: str | None = None
    app_name: str | None = None


class FocusTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: FocusPolicy
    from_bundle_id: str | None
    target_app: str
    attempted: bool = False
    verified: bool = False
    to_bundle_id: str | None = None
    detail: str = ""


class FocusRestorationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restored: bool = False
    verified: bool = False
    requires_user: bool = False
    cancelled: bool = False
    final_bundle_id: str | None = None
    detail: str = ""


class FocusManager:
    def __init__(self, app_control: AppControl) -> None:
        self._app_control = app_control

    def snapshot(self, now: datetime) -> FocusSnapshot:
        front = self._app_control.frontmost()
        return FocusSnapshot(
            captured_at=now,
            bundle_id=front.bundle_id if front else None,
            app_name=front.name if front else None,
        )

    def prepare_transition(
        self,
        before: FocusSnapshot,
        target_app: str,
        policy: FocusPolicy,
    ) -> FocusTransition:
        """Temporarily focus a target only when the policy requires it."""
        transition = FocusTransition(
            policy=policy,
            from_bundle_id=before.bundle_id,
            target_app=target_app,
        )
        if policy is not FocusPolicy.RESTORE_PREVIOUS_FOCUS:
            return transition.model_copy(update={"verified": policy is not FocusPolicy.ASK_IF_AMBIGUOUS})

        activated = self._app_control.activate(target_app)
        final = self._app_control.frontmost()
        verified = activated and final is not None and (final.name == target_app or final.bundle_id == target_app)
        return transition.model_copy(
            update={
                "attempted": True,
                "verified": verified,
                "to_bundle_id": final.bundle_id if final else None,
                "detail": ("temporary target focus verified" if verified else "temporary target focus unavailable"),
            }
        )

    def change_focus(
        self,
        target_app: str,
        policy: FocusPolicy,
        action: Callable[[], None],
        now: datetime,
        cancelled: Callable[[], bool] | None = None,
    ) -> tuple[FocusTransition, FocusRestorationResult]:
        before = self.snapshot(now)
        transition = FocusTransition(policy=policy, from_bundle_id=before.bundle_id, target_app=target_app)

        # Ambiguous focus never auto-steals — defer to the user, run nothing.
        if policy is FocusPolicy.ASK_IF_AMBIGUOUS:
            return transition, FocusRestorationResult(
                requires_user=True,
                final_bundle_id=before.bundle_id,
                detail="focus change is ambiguous; awaiting user confirmation",
            )

        action()
        return transition, self.reconcile(
            before,
            target_app,
            policy,
            cancelled=cancelled is not None and cancelled(),
        )

    def reconcile(
        self,
        before: FocusSnapshot,
        target_app: str,
        policy: FocusPolicy,
        *,
        cancelled: bool = False,
    ) -> FocusRestorationResult:
        """Verify/restore focus after an action executed elsewhere.

        The orchestrator uses this form because tool execution is async. The
        final frontmost application is always read independently from macOS.
        """
        if policy is FocusPolicy.ASK_IF_AMBIGUOUS:
            return FocusRestorationResult(
                requires_user=True,
                final_bundle_id=before.bundle_id,
                detail="focus change is ambiguous; awaiting user confirmation",
            )

        if cancelled:
            # Cancelled mid-transition: do NOT perform restoration steps.
            final = self._app_control.frontmost()
            return FocusRestorationResult(
                cancelled=True,
                final_bundle_id=final.bundle_id if final else None,
                detail="cancelled during focus transition; no restoration performed",
            )

        if policy is FocusPolicy.RESTORE_PREVIOUS_FOCUS and before.app_name:
            self._app_control.activate(before.app_name)
            final = self._app_control.frontmost()
            verified = final is not None and final.bundle_id == before.bundle_id
            return FocusRestorationResult(
                restored=verified,
                verified=verified,
                final_bundle_id=final.bundle_id if final else None,
                detail="restored previous focus" if verified else "restoration unverified",
            )

        final = self._app_control.frontmost()
        final_bundle = final.bundle_id if final else None
        if policy is FocusPolicy.DO_NOT_STEAL_FOCUS:
            # Focus must NOT have moved off the prior app.
            verified = final_bundle == before.bundle_id
            return FocusRestorationResult(
                verified=verified,
                final_bundle_id=final_bundle,
                detail="focus preserved" if verified else "focus was stolen unexpectedly",
            )

        # KEEP_NEW_FOCUS: independently confirm the requested application,
        # rather than trusting the action's return value.
        verified = final is not None and (final.name == target_app or final.bundle_id == target_app)
        return FocusRestorationResult(
            verified=verified,
            final_bundle_id=final_bundle,
            detail="new focus kept" if verified else "target focus was not verified",
        )
