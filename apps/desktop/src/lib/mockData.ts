/**
 * MOCK fixtures — Phase 1 demo data for the Plan and Timeline views.
 * Shown only when the daemon has no real tasks, always behind a visible
 * "MOCK DATA" badge. Never mixed with live daemon state.
 */
import type { AuditEvent, ExecutionPlan, Task } from "@thoth/shared-schemas";

const MOCK_CORR = "mock-corr-0001";

export const MOCK_PLAN: ExecutionPlan = {
  id: "mock-plan-1",
  correlation_id: MOCK_CORR,
  task_id: "mock-task-1",
  summary:
    "Continue the THOTH project: restore workspace and start dev services",
  steps: [
    {
      id: "mock-step-1",
      correlation_id: MOCK_CORR,
      index: 0,
      title: "Inspect repository status",
      tool_name: "mock_read_file",
      arguments: { path: "~/projects/thoth/README.md" },
      declared_risk: "R0",
      status: "succeeded",
      verification_checks: [
        {
          kind: "file_exists",
          params: { path: "~/projects/thoth/README.md" },
          description: "",
          require: "all",
          children: [],
        },
      ],
      verification_passed: true,
      verification_detail: "Read 214 lines",
    },
    {
      id: "mock-step-2",
      correlation_id: MOCK_CORR,
      index: 1,
      title: "Open the editor workspace",
      tool_name: "mock_open_app",
      arguments: { app: "Visual Studio Code" },
      declared_risk: "R1",
      status: "running",
      verification_checks: [
        {
          kind: "application_running",
          params: { name: "Visual Studio Code" },
          description: "",
          require: "all",
          children: [],
        },
      ],
      verification_passed: null,
      verification_detail: null,
    },
    {
      id: "mock-step-3",
      correlation_id: MOCK_CORR,
      index: 2,
      title: "Push release branch",
      tool_name: "mock_git_push",
      arguments: { remote: "origin", branch: "release/0.1" },
      declared_risk: "R2",
      status: "pending",
      verification_checks: [
        {
          kind: "git_state",
          params: { repo: "~/projects/thoth", branch: "release/0.1" },
          description: "",
          require: "all",
          children: [],
        },
      ],
      verification_passed: null,
      verification_detail: null,
    },
  ],
};

export const MOCK_TASK: Task = {
  id: "mock-task-1",
  correlation_id: MOCK_CORR,
  goal: "Continue the THOTH project",
  source: "text",
  state: "EXECUTING",
  plan: MOCK_PLAN,
  result_summary: null,
  error: null,
  created_at: "2026-07-11T09:00:00Z",
  updated_at: "2026-07-11T09:00:12Z",
};

export const MOCK_AUDIT: AuditEvent[] = [
  {
    event_id: "mock-ev-1",
    correlation_id: MOCK_CORR,
    task_id: "mock-task-1",
    seq: 1,
    event_type: "task.created",
    payload: { goal: "Continue the THOTH project" },
    created_at: "2026-07-11T09:00:00Z",
  },
  {
    event_id: "mock-ev-2",
    correlation_id: MOCK_CORR,
    task_id: "mock-task-1",
    seq: 2,
    event_type: "state.transition",
    payload: { from: "RECEIVED", to: "UNDERSTANDING" },
    created_at: "2026-07-11T09:00:01Z",
  },
  {
    event_id: "mock-ev-3",
    correlation_id: MOCK_CORR,
    task_id: "mock-task-1",
    seq: 3,
    event_type: "state.transition",
    payload: { from: "UNDERSTANDING", to: "PLANNING" },
    created_at: "2026-07-11T09:00:02Z",
  },
  {
    event_id: "mock-ev-4",
    correlation_id: MOCK_CORR,
    task_id: "mock-task-1",
    seq: 4,
    event_type: "policy.decision",
    payload: { step: 0, effective_risk: "R0", requires_approval: false },
    created_at: "2026-07-11T09:00:04Z",
  },
  {
    event_id: "mock-ev-5",
    correlation_id: MOCK_CORR,
    task_id: "mock-task-1",
    seq: 5,
    event_type: "tool.result",
    payload: { tool: "mock_read_file", ok: true, duration_ms: 42 },
    created_at: "2026-07-11T09:00:08Z",
  },
];
