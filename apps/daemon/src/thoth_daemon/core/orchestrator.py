"""Agent orchestrator.

Drives a task through the deterministic state machine:

    RECEIVED -> UNDERSTANDING -> PLANNING -> RISK_REVIEW
      -> (WAITING_FOR_APPROVAL) -> EXECUTING -> VERIFYING
      -> COMPLETED | FAILED | CANCELLED  (with bounded RECOVERING)

Enforcement wired here, not by convention:
  - The planner only produces a plan; ``guarded_execute`` refuses to run a
    tool unless the machine is in EXECUTING.
  - The policy engine classifies every step from typed inputs; R3 fails the
    task at RISK_REVIEW, R2 halts at WAITING_FOR_APPROVAL.
  - R2 execution requires a single-use approval bound to the invocation.
  - Every transition and decision is audited; task.* / approval.* / audit.*
    events are published to the event bus.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine, ApprovalRequiredError
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.scope import ScopeEnforcer, ScopeViolation
from thoth_daemon.core.state_machine import InvalidTransitionError, TaskStateMachine
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    TERMINAL_STATES,
    ExecutionPlan,
    PlanStep,
    ResourceScope,
    StepStatus,
    Task,
    TaskSource,
    TaskState,
    ToolInvocation,
    ToolResult,
    WorkspaceProfile,
)
from thoth_daemon.tools.registry import ToolRegistry

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
ScopeProvider = Callable[[], Awaitable[ResourceScope]]


class ExecutionStateError(Exception):
    """Raised when tool execution is attempted outside the EXECUTING state."""


async def _empty_scope() -> ResourceScope:
    return ResourceScope()


async def guarded_execute(
    machine: TaskStateMachine,
    registry: ToolRegistry,
    invocation: ToolInvocation,
    allowed_scope: ResourceScope | None = None,
) -> ToolResult:
    """The ONLY path to a tool. Refuses unless the task is EXECUTING."""
    if machine.state is not TaskState.EXECUTING:
        raise ExecutionStateError(
            f"tool execution requires EXECUTING state, not {machine.state.value}"
        )
    return await registry.execute(invocation, allowed_scope)


class _TaskRunner:
    def __init__(
        self,
        task: Task,
        plan: ExecutionPlan,
        *,
        registry: ToolRegistry,
        policy: PolicyEngine,
        approvals: ApprovalEngine,
        verifier: VerificationEngine,
        recovery: RecoveryController,
        audit: AuditStore,
        publish: Publish,
        workspace: WorkspaceProfile,
        enforcer: ScopeEnforcer,
        scope_provider: ScopeProvider,
    ) -> None:
        self.task = task
        self.plan = plan
        self._corr = task.correlation_id
        self._registry = registry
        self._policy = policy
        self._approvals = approvals
        self._verifier = verifier
        self._recovery = recovery
        self._audit = audit
        self._publish = publish
        self._workspace = workspace
        self._enforcer = enforcer
        self._scope_provider = scope_provider

        self._pending: list[tuple[str, dict[str, Any]]] = []
        self.machine = TaskStateMachine(task.id, task.state, emit=self._collect)
        self._cancel = asyncio.Event()
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_ok: dict[str, bool] = {}
        self.paused = asyncio.Event()
        self.done: asyncio.Future[Task] = asyncio.get_event_loop().create_future()

    # -- audit / event plumbing ------------------------------------------
    def _collect(self, event_type: str, payload: dict[str, Any]) -> None:
        self._pending.append((event_type, payload))

    async def _drain(self) -> None:
        while self._pending:
            event_type, payload = self._pending.pop(0)
            event = await self._audit.append(
                self.task.id, event_type, payload, correlation_id=self._corr
            )
            await self._publish("audit.appended", {"event": event.model_dump(mode="json")})
            if event_type == "state.transition":
                await self._publish(
                    "task.state_changed", {"task": self.task.model_dump(mode="json")}
                )

    async def _goto(self, state: TaskState, reason: str) -> None:
        self.task.state = state
        try:
            self.machine.transition(state, reason)
        finally:
            await self._drain()

    async def _audit_only(self, event_type: str, payload: dict[str, Any]) -> None:
        event = await self._audit.append(
            self.task.id, event_type, payload, correlation_id=self._corr
        )
        await self._publish("audit.appended", {"event": event.model_dump(mode="json")})

    # -- cancellation ----------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()
        for ev in self._approval_events.values():
            ev.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # -- approvals -------------------------------------------------------
    def resolve_approval(self, invocation_id: str, approved: bool) -> None:
        self._approval_ok[invocation_id] = approved
        ev = self._approval_events.get(invocation_id)
        if ev is not None:
            ev.set()

    async def _await_approval(self, invocation_id: str) -> bool:
        ev = asyncio.Event()
        self._approval_events[invocation_id] = ev
        self.paused.set()
        await ev.wait()
        self.paused.clear()
        if self.cancelled:
            return False
        return self._approval_ok.get(invocation_id, False)

    # -- main loop -------------------------------------------------------
    async def run(self) -> None:
        try:
            await self._run()
        except Exception as exc:  # fail safe: any error drives the task terminal
            await self._audit_only("orchestrator.error", {"error": str(exc)})
            await self._fail(str(exc))
        finally:
            self.paused.set()  # unblock any settle() waiters
            if not self.done.done():
                self.done.set_result(self.task)

    async def _run(self) -> None:
        await self._goto(TaskState.UNDERSTANDING, "normalizing intent")
        if await self._check_cancel():
            return

        await self._goto(TaskState.PLANNING, "building execution plan")
        self.plan.correlation_id = self._corr
        for step in self.plan.steps:
            step.correlation_id = self._corr
        self.task.plan = self.plan
        # Validate the plan against the tool registry BEFORE risk review.
        for step in self.plan.steps:
            if not self._registry.has(step.tool_name):
                await self._audit_only(
                    "plan.rejected", {"reason": f"unknown tool '{step.tool_name}'"}
                )
                await self._goto(TaskState.RISK_REVIEW, "risk review")
                await self._fail(f"unknown tool '{step.tool_name}' in plan")
                return
        if await self._check_cancel():
            return

        await self._goto(TaskState.RISK_REVIEW, "risk review")
        decisions = []
        for step in self.plan.steps:
            decision = self._policy.evaluate(
                tool_name=step.tool_name,
                declared_risk=step.declared_risk,
                tool_default_risk=self._registry.default_risk(step.tool_name),
                workspace_trusted=self._workspace.trusted,
            )
            await self._audit_only(
                "policy.decision",
                {
                    "step_id": step.id,
                    "tool": step.tool_name,
                    "effective_risk": decision.effective_risk.value,
                    "allowed": decision.allowed,
                    "requires_approval": decision.requires_approval,
                    "reasons": decision.reasons,
                },
            )
            if not decision.allowed:
                await self._fail(
                    f"step '{step.title}' blocked by policy: {'; '.join(decision.reasons)}"
                )
                return
            decisions.append(decision)
        if await self._check_cancel():
            return

        for step, decision in zip(self.plan.steps, decisions, strict=True):
            ok = await self._execute_step(step, decision.requires_approval, decision.effective_risk)
            if not ok:
                return  # terminal state already set

        await self._goto(TaskState.COMPLETED, "all steps verified")
        self.task.result_summary = f"Completed {len(self.plan.steps)} step(s)."
        await self._audit_only("task.completed", {"steps": len(self.plan.steps)})

    async def _execute_step(
        self, step: PlanStep, requires_approval: bool, effective_risk: Any
    ) -> bool:
        invocation = ToolInvocation(
            correlation_id=self._corr,
            task_id=self.task.id,
            step_id=step.id,
            tool_name=step.tool_name,
            arguments=step.arguments,
            effective_risk=effective_risk,
        )

        # Scope gate — deny out-of-scope targets before any move toward
        # EXECUTING. Resolved fresh so a revocation mid-task takes effect now.
        allowed_scope = await self._scope_provider()
        if not await self._scope_gate(step, invocation, allowed_scope):
            return False

        # Reach EXECUTING, passing through approval if the step needs it.
        if self.machine.state is TaskState.VERIFYING:
            await self._goto(TaskState.EXECUTING, "advance to next step")

        if requires_approval:
            request = self._approvals.request(
                task_id=self.task.id,
                invocation_id=invocation.id,
                step_id=step.id,
                tool_name=step.tool_name,
                arguments=step.arguments,
                risk=effective_risk,
                reason=f"{effective_risk.value} action requires explicit approval before execution",
                target=self._target_of(step),
            )
            request.correlation_id = self._corr
            await self._goto(TaskState.WAITING_FOR_APPROVAL, "awaiting approval")
            await self._publish("approval.requested", {"approval": request.model_dump(mode="json")})
            approved = await self._await_approval(invocation.id)
            decided = self._approvals.get(request.id)
            await self._publish("approval.decided", {"approval": decided.model_dump(mode="json")})
            if self.cancelled:
                await self._goto(TaskState.CANCELLED, "cancelled while awaiting approval")
                return False
            if not approved:
                rec = self._recovery.on_denied(self.task.id, step.id, "approval denied")
                await self._audit_only("recovery.decision", rec.model_dump(mode="json"))
                await self._fail(f"approval denied for step '{step.title}'")
                return False
            # Refresh invocation arguments if the user modified them.
            invocation.arguments = decided.arguments
            await self._goto(TaskState.EXECUTING, "approved; executing")
        elif self.machine.state is TaskState.RISK_REVIEW:
            await self._goto(TaskState.EXECUTING, "executing")

        # Execute with bounded retries.
        step.status = StepStatus.RUNNING
        await self._publish(
            "task.step_started",
            {"task": self.task.model_dump(mode="json"), "step_id": step.id},
        )
        while True:
            if await self._check_cancel():
                return False

            if requires_approval:
                try:
                    self._approvals.authorize_execution(invocation.id)
                except ApprovalRequiredError as exc:
                    await self._audit_only("execution_blocked", {"reason": str(exc)})
                    await self._fail(str(exc))
                    return False

            result = await self._run_tool(invocation, allowed_scope)
            result.correlation_id = self._corr
            if self.cancelled or result.cancelled:
                await self._goto(TaskState.CANCELLED, "cancelled mid-execution")
                return False

            await self._audit_only(
                "tool.result",
                {
                    "step_id": step.id,
                    "tool": step.tool_name,
                    "ok": result.ok,
                    "duration_ms": result.duration_ms,
                    "timed_out": result.timed_out,
                    **({"output": result.output} if result.output else {}),
                    **({"error": result.error} if result.error else {}),
                },
            )

            await self._goto(TaskState.VERIFYING, "verifying step result")
            tool = self._registry.get(step.tool_name)
            # Independent verification: the tool's declared strategy is the
            # system-enforced minimum; structured checks only ADD strictness.
            # "Exited 0" is never sufficient on its own.
            verification = self._verifier.verify_step(step, result, tool.verification)
            verification.correlation_id = self._corr
            step.verification_passed = verification.passed
            step.verification_detail = verification.detail
            await self._audit_only("verification.result", verification.model_dump(mode="json"))
            await self._publish(
                "task.step_finished",
                {
                    "task": self.task.model_dump(mode="json"),
                    "step_id": step.id,
                    "verification": verification.model_dump(mode="json"),
                },
            )

            if verification.passed:
                step.status = StepStatus.SUCCEEDED
                return True

            rec = self._recovery.on_step_failure(
                self.task.id,
                step.id,
                result,
                verification_failed=result.ok and not verification.passed,
            )
            await self._audit_only("recovery.decision", rec.model_dump(mode="json"))
            if rec.action == "fail":
                step.status = StepStatus.FAILED
                await self._fail(f"step '{step.title}' failed: {verification.detail}")
                return False
            await self._goto(TaskState.RECOVERING, f"retry {rec.attempt}")
            await self._goto(TaskState.EXECUTING, "retrying step")

    async def _scope_gate(
        self, step: PlanStep, invocation: ToolInvocation, allowed_scope: ResourceScope
    ) -> bool:
        """Primary scope enforcement: refuse out-of-scope or malformed steps
        before EXECUTING. Fails like a denial — no retry, budget untouched."""
        tool = self._registry.get(step.tool_name)
        try:
            parsed = tool.parse_arguments(invocation)
            self._enforcer.check(tool.requested_scope(parsed), allowed_scope)
        except ScopeViolation as exc:
            await self._audit_only(
                "scope.denied",
                {
                    "step_id": step.id,
                    "tool": step.tool_name,
                    "kind": exc.kind,
                    "value": exc.value,
                    "reason": exc.reason,
                },
            )
            await self._fail(f"step '{step.title}' blocked by scope: {exc.reason}")
            return False
        except ValidationError as exc:
            await self._audit_only(
                "scope.denied",
                {"step_id": step.id, "tool": step.tool_name, "reason": f"invalid arguments: {exc}"},
            )
            await self._fail(f"step '{step.title}' has invalid arguments")
            return False
        return True

    async def _run_tool(
        self, invocation: ToolInvocation, allowed_scope: ResourceScope
    ) -> ToolResult:
        exec_task = asyncio.ensure_future(
            guarded_execute(self.machine, self._registry, invocation, allowed_scope)
        )
        cancel_task = asyncio.ensure_future(self._cancel.wait())
        done, _ = await asyncio.wait({exec_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
        if exec_task in done:
            cancel_task.cancel()
            return exec_task.result()
        # Cancellation won the race.
        exec_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await exec_task
        return ToolResult(invocation_id=invocation.id, ok=False, cancelled=True, error="cancelled")

    async def _check_cancel(self) -> bool:
        if self.cancelled and self.machine.state not in TERMINAL_STATES:
            await self._goto(TaskState.CANCELLED, "cancelled by user")
            return True
        return self.cancelled

    async def _fail(self, error: str) -> None:
        self.task.error = error
        if self.machine.state not in TERMINAL_STATES:
            with contextlib.suppress(InvalidTransitionError):
                await self._goto(TaskState.FAILED, error)
        await self._audit_only("task.failed", {"error": error})

    @staticmethod
    def _target_of(step: PlanStep) -> str:
        args = step.arguments
        for key in ("recipient", "remote", "path", "app", "domain"):
            if key in args:
                return f"{key}={args[key]}"
        return step.tool_name


class Orchestrator:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        policy: PolicyEngine,
        approvals: ApprovalEngine,
        verifier: VerificationEngine,
        recovery: RecoveryController,
        audit: AuditStore,
        planner: PlannerAdapter,
        publish: Publish,
        workspace: WorkspaceProfile,
        enforcer: ScopeEnforcer | None = None,
        scope_provider: ScopeProvider | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._approvals = approvals
        self._verifier = verifier
        self._recovery = recovery
        self._audit = audit
        self._planner = planner
        self._publish = publish
        self._workspace = workspace
        self._enforcer = enforcer or ScopeEnforcer()
        self._scope_provider = scope_provider or _empty_scope
        self._runners: dict[str, _TaskRunner] = {}
        self._tasks: dict[str, Task] = {}
        self._background: set[asyncio.Task[None]] = set()

    async def submit(self, goal: str, source: TaskSource = TaskSource.TEXT) -> Task:
        task = Task(goal=goal, source=source, state=TaskState.RECEIVED)
        self._tasks[task.id] = task
        corr = task.correlation_id
        await self._audit.append(
            task.id, "task.created", {"goal": goal, "source": source.value}, correlation_id=corr
        )
        await self._publish("task.created", {"task": task.model_dump(mode="json")})

        # The planner is untrusted and (for the real planner) can raise on a
        # network/parse/validation error — fail the task cleanly, never crash.
        try:
            plan = self._planner.plan(task.id, goal)
        except Exception as exc:
            task.state = TaskState.FAILED
            task.error = f"planning failed: {exc}"
            await self._audit.append(
                task.id, "planner.error", {"error": str(exc)}, correlation_id=corr
            )
            await self._audit.append(
                task.id, "task.failed", {"error": task.error}, correlation_id=corr
            )
            await self._publish("task.state_changed", {"task": task.model_dump(mode="json")})
            return task
        runner = _TaskRunner(
            task,
            plan,
            registry=self._registry,
            policy=self._policy,
            approvals=self._approvals,
            verifier=self._verifier,
            recovery=self._recovery,
            audit=self._audit,
            publish=self._publish,
            workspace=self._workspace,
            enforcer=self._enforcer,
            scope_provider=self._scope_provider,
        )
        self._runners[task.id] = runner
        background = asyncio.ensure_future(runner.run())
        self._background.add(background)
        background.add_done_callback(self._background.discard)
        return task

    async def settle(self, task_id: str, timeout: float = 3.0) -> Task:  # noqa: ASYNC109
        """Await until the task reaches a terminal state or pauses for
        approval. Returns the current task snapshot."""
        runner = self._runners[task_id]
        waiters: list[asyncio.Future[Any]] = [
            asyncio.ensure_future(runner.paused.wait()),
            asyncio.ensure_future(asyncio.shield(runner.done)),
        ]
        try:
            await asyncio.wait_for(
                asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED),
                timeout=timeout,
            )
        finally:
            for waiter in waiters:
                waiter.cancel()
        return runner.task

    async def decide_approval(
        self, request_id: str, approved: bool, modified_arguments: dict[str, Any] | None = None
    ) -> Task:
        request = self._approvals.get(request_id)
        runner = self._runners[request.task_id]
        self._approvals.decide(request_id, approved, modified_arguments)
        runner.resolve_approval(request.invocation_id, approved)
        return await self.settle(request.task_id)

    async def cancel(self, task_id: str) -> Task:
        runner = self._runners.get(task_id)
        if runner is None:
            raise KeyError(task_id)
        runner.cancel()
        return await self.settle(task_id)

    def get_task(self, task_id: str) -> Task | None:
        runner = self._runners.get(task_id)
        return runner.task if runner else self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return [r.task for r in self._runners.values()]

    def pending_approvals(self) -> list[Any]:
        return self._approvals.pending()

    async def task_audit(self, task_id: str) -> list[Any]:
        return await self._audit.for_task(task_id)
