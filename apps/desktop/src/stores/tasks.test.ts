import type {
  ApprovalRequest,
  AuditEvent,
  Task,
  WsEnvelope,
} from "@thoth/shared-schemas";
import { beforeEach, describe, expect, it } from "vitest";

import { useTasksStore } from "./tasks";

function reset() {
  useTasksStore.setState({
    tasks: {},
    activeTaskId: null,
    pendingApprovals: [],
    auditByTask: {},
  });
}

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: "t-1",
    correlation_id: "t-1",
    goal: "read notes",
    source: "text",
    state: "PLANNING",
    plan: null,
    result_summary: null,
    error: null,
    created_at: "2026-07-11T09:00:00Z",
    updated_at: "2026-07-11T09:00:00Z",
    ...overrides,
  };
}

function envelope(
  type: WsEnvelope["type"],
  payload: Record<string, unknown>,
): WsEnvelope {
  return { type, ts: "2026-07-11T09:00:00Z", payload };
}

const APPROVAL: ApprovalRequest = {
  id: "ap-1",
  correlation_id: "t-1",
  task_id: "t-1",
  invocation_id: "inv-1",
  step_id: "s-1",
  tool_name: "mock_send_email",
  arguments: {},
  risk: "R2",
  reason: "external side effect",
  target: "a@b.c",
  status: "pending",
  created_at: "2026-07-11T09:00:00Z",
  expires_at: "2026-07-11T09:02:00Z",
};

beforeEach(reset);

describe("applyEvent", () => {
  it("connection.established is a no-op", () => {
    useTasksStore.getState().applyEvent(envelope("connection.established", {}));
    expect(useTasksStore.getState().tasks).toEqual({});
  });

  it("task.created stores the task and sets it active", () => {
    useTasksStore
      .getState()
      .applyEvent(envelope("task.created", { task: task() }));
    const s = useTasksStore.getState();
    expect(s.tasks["t-1"].goal).toBe("read notes");
    expect(s.activeTaskId).toBe("t-1");
  });

  it.each([
    "task.state_changed",
    "task.step_started",
    "task.step_finished",
  ] as const)("%s upserts the task", (type) => {
    useTasksStore
      .getState()
      .applyEvent(envelope("task.created", { task: task() }));
    useTasksStore
      .getState()
      .applyEvent(envelope(type, { task: task({ state: "EXECUTING" }) }));
    expect(useTasksStore.getState().tasks["t-1"].state).toBe("EXECUTING");
  });

  it("approval.requested adds a pending approval", () => {
    useTasksStore
      .getState()
      .applyEvent(envelope("approval.requested", { approval: APPROVAL }));
    expect(useTasksStore.getState().pendingApprovals).toHaveLength(1);
  });

  it("approval.requested is idempotent by id", () => {
    const apply = useTasksStore.getState().applyEvent;
    apply(envelope("approval.requested", { approval: APPROVAL }));
    apply(envelope("approval.requested", { approval: APPROVAL }));
    expect(useTasksStore.getState().pendingApprovals).toHaveLength(1);
  });

  it("approval.decided removes the pending approval", () => {
    const apply = useTasksStore.getState().applyEvent;
    apply(envelope("approval.requested", { approval: APPROVAL }));
    apply(envelope("approval.decided", { approval: APPROVAL }));
    expect(useTasksStore.getState().pendingApprovals).toHaveLength(0);
  });

  it("audit.appended accumulates ordered, de-duplicated events", () => {
    const apply = useTasksStore.getState().applyEvent;
    const ev = (seq: number, id: string): AuditEvent => ({
      event_id: id,
      correlation_id: "t-1",
      prev_hash: "",
      hash: `h-${seq}`,
      task_id: "t-1",
      seq,
      event_type: "state.transition",
      payload: {},
      created_at: "2026-07-11T09:00:00Z",
    });
    apply(envelope("audit.appended", { event: ev(2, "e2") }));
    apply(envelope("audit.appended", { event: ev(0, "e0") }));
    apply(envelope("audit.appended", { event: ev(1, "e1") }));
    apply(envelope("audit.appended", { event: ev(0, "e0") })); // duplicate
    const events = useTasksStore.getState().auditByTask["t-1"];
    expect(events.map((e) => e.seq)).toEqual([0, 1, 2]);
  });
});
