import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TaskPresentation } from "@/lib/api";

import { OperationalSummary } from "./OperationalSummary";

function presentation(
  updates: Partial<TaskPresentation> = {},
): TaskPresentation {
  return {
    task_id: "t1",
    authoritative: true,
    response: {
      intent: "verified_completion",
      used_model: false,
      display: { text: "The task is verified." },
      spoken: { text: "Task verified.", max_chars: 240 },
    },
    display_response: "The task is verified.",
    spoken_response_preview: "Task verified.",
    foreground: null,
    matched_workspace_id: null,
    planned_focus_policy: "do_not_steal_focus",
    focus_result: null,
    runtime_status: "ready",
    dialogue_expires_at: "2999-01-01T00:00:00Z",
    stages: {
      proposed: true,
      approval: "not_required",
      executed: true,
      verified: true,
    },
    ...updates,
  };
}

describe("OperationalSummary", () => {
  it("renders verified completion and all reached stages", () => {
    render(<OperationalSummary presentation={presentation()} />);
    expect(screen.getByText("The task is verified.")).toBeInTheDocument();
    for (const stage of ["proposed", "approved", "executed", "verified"]) {
      expect(screen.getByTestId(`stage-${stage}`)).toHaveClass("text-accent");
    }
  });

  it("does not hide partial completion", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          response: {
            ...presentation().response,
            intent: "partial_completion",
          },
          display_response: "Daemon passed. Frontend failed.",
          stages: { ...presentation().stages, verified: false },
        })}
      />,
    );
    expect(screen.getByText(/Frontend failed/)).toHaveClass("text-warning");
    expect(screen.getByTestId("stage-verified")).toHaveClass("text-faint");
  });

  it("shows degraded runtime", () => {
    render(
      <OperationalSummary
        presentation={presentation({ runtime_status: "degraded" })}
      />,
    );
    expect(screen.getByTestId("runtime-status")).toHaveTextContent("degraded");
  });

  it("shows foreground app and bundle", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          foreground: {
            captured_at: "2026-07-13T12:00:00Z",
            reason: "status",
            active_bundle_id: "com.microsoft.VSCode",
            active_app_name: "Visual Studio Code",
            active_window_title: null,
            focused_ax_role: null,
            focused_ax_identifier: null,
            browser_domain: null,
            selected_file_paths: [],
            workspace_id: "thoth",
            previous_bundle_id: null,
            task_id: "t1",
          },
        })}
      />,
    );
    expect(screen.getByTestId("foreground-app")).toHaveTextContent(
      "Visual Studio Code · com.microsoft.VSCode",
    );
  });

  it("shows authoritative workspace match", () => {
    render(
      <OperationalSummary
        presentation={presentation({ matched_workspace_id: "thoth" })}
      />,
    );
    expect(screen.getByTestId("matched-workspace")).toHaveTextContent("thoth");
  });

  it("shows focus restoration failure", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          focus_result: {
            restored: false,
            verified: false,
            requires_user: false,
            cancelled: false,
            final_bundle_id: "com.apple.TextEdit",
            detail: "restoration unverified",
          },
        })}
      />,
    );
    expect(screen.getByTestId("focus-outcome")).toHaveTextContent(
      "failed · restoration unverified",
    );
  });

  it("shows expired dialogue context", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          dialogue_expires_at: "2000-01-01T00:00:00Z",
        })}
      />,
    );
    expect(screen.getByTestId("dialogue-expiry")).toHaveTextContent("Expired");
  });

  it("renders an ambiguous-reference clarification", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          response: {
            ...presentation().response,
            intent: "needs_clarification",
          },
          display_response: "Which artifact did you mean?",
        })}
      />,
    );
    expect(
      screen.getByText("Which artifact did you mean?"),
    ).toBeInTheDocument();
  });

  it("shows pending approval without marking approved", () => {
    render(
      <OperationalSummary
        presentation={presentation({
          response: {
            ...presentation().response,
            intent: "approval_required",
          },
          stages: {
            proposed: true,
            approval: "pending",
            executed: false,
            verified: false,
          },
        })}
      />,
    );
    expect(screen.getByText("approval pending")).toBeInTheDocument();
    expect(screen.getByTestId("stage-approved")).toHaveClass("text-faint");
    expect(screen.getByTestId("stage-executed")).toHaveClass("text-faint");
    expect(screen.getByTestId("stage-verified")).toHaveClass("text-faint");
  });
});
