/**
 * TypeScript mirror of the daemon's Pydantic contracts
 * (apps/daemon/src/thoth_daemon/schemas/). Keep in lockstep — the JSON
 * Schemas under ../schemas are generated from the same source via
 * `make schemas` and are the source of truth for shapes.
 */

export type TaskState =
  | "RECEIVED"
  | "UNDERSTANDING"
  | "PLANNING"
  | "RISK_REVIEW"
  | "WAITING_FOR_APPROVAL"
  | "EXECUTING"
  | "VERIFYING"
  | "RECOVERING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export const TASK_STATES: TaskState[] = [
  "RECEIVED",
  "UNDERSTANDING",
  "PLANNING",
  "RISK_REVIEW",
  "WAITING_FOR_APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "RECOVERING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

export type RiskLevel = "R0" | "R1" | "R2" | "R3";

export type TaskSource = "text" | "voice";

export type StepStatus =
  | "pending"
  | "running"
  | "verifying"
  | "succeeded"
  | "failed"
  | "skipped"
  | "cancelled";

export interface PlanStep {
  id: string;
  index: number;
  title: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  declared_risk: RiskLevel;
  status: StepStatus;
  verification_passed: boolean | null;
  verification_detail: string | null;
}

export interface ExecutionPlan {
  id: string;
  task_id: string;
  summary: string;
  steps: PlanStep[];
}

export interface Task {
  id: string;
  goal: string;
  source: TaskSource;
  state: TaskState;
  plan: ExecutionPlan | null;
  result_summary: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type ApprovalStatus = "pending" | "approved" | "denied" | "expired";

export interface ApprovalRequest {
  id: string;
  task_id: string;
  invocation_id: string;
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  risk: RiskLevel;
  reason: string;
  target: string;
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
}

export interface AuditEvent {
  event_id: string;
  task_id: string;
  seq: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export type WsEventType =
  | "connection.established"
  | "task.created"
  | "task.state_changed"
  | "task.step_started"
  | "task.step_finished"
  | "approval.requested"
  | "approval.decided"
  | "audit.appended";

export interface WsEnvelope {
  type: WsEventType;
  ts: string;
  payload: Record<string, unknown>;
}
