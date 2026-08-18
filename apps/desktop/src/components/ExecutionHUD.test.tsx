import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TaskPayload } from "@/lib/api";

import { ExecutionHUD } from "./ExecutionHUD";

function task(overrides: Partial<TaskPayload> = {}): TaskPayload {
  return {
    id: "task-1",
    correlation_id: "corr-1",
    goal: "Continue OmniMac",
    source: "text",
    state: "EXECUTING",
    plan: {
      id: "plan-1",
      correlation_id: "corr-1",
      task_id: "task-1",
      summary: "Continue safely",
      steps: [
        {
          id: "step-1",
          correlation_id: "corr-1",
          index: 0,
          title: "Verify daemon health",
          tool_name: "mock_health",
          arguments: {},
          declared_risk: "R0",
          focus_policy: "do_not_steal_focus",
          status: "verifying",
          verification_checks: [],
          verification_passed: null,
          verification_detail: null,
        },
      ],
    },
    result_summary: null,
    error: null,
    created_at: "2026-07-14T09:00:00Z",
    updated_at: "2026-07-14T09:00:01Z",
    ...overrides,
  };
}

describe("ExecutionHUD", () => {
  it("shows real progress, verification and focus policy", () => {
    render(<ExecutionHUD task={task()} />);
    expect(screen.getByText("Continue OmniMac")).toBeInTheDocument();
    expect(screen.getByText(/1 of 1 · Verify daemon health/)).toBeInTheDocument();
    expect(screen.getByText("Verifying")).toBeInTheDocument();
    expect(screen.getByText("Do not steal focus")).toBeInTheDocument();
  });

  it("does not label execution as verified completion", () => {
    render(<ExecutionHUD task={task()} />);
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  it("keeps partial failure visible", () => {
    render(
      <ExecutionHUD
        task={task({
          state: "FAILED",
          error: "frontend failed",
          result_summary: "Daemon started; frontend failed.",
        })}
      />,
    );
    expect(screen.getByText("Partial or failed")).toBeInTheDocument();
    expect(screen.getByText("Daemon started; frontend failed.")).toBeInTheDocument();
  });

  it("renders the safe presentation instead of internal task errors", () => {
    render(
      <ExecutionHUD
        task={task({
          state: "FAILED_REQUIRES_USER",
          error: "authoritative plan failed; model-generated recovery is disabled",
          presentation: {
            display_response: "TextEdit did not become frontmost. No completion was claimed.",
          } as TaskPayload["presentation"],
        })}
      />,
    );

    expect(
      screen.getByText("TextEdit did not become frontmost. No completion was claimed."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/model-generated recovery/)).not.toBeInTheDocument();
  });
});
