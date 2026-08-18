import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTasksStore } from "@/stores/tasks";
import type { TaskPayload } from "@/lib/api";

import { CommandCenter } from "./CommandCenter";

const { beginPushToTalk, createTask, dispatchCommand, endPushToTalk, globalStop, routeIntent } =
  vi.hoisted(() => ({
    beginPushToTalk: vi.fn(),
    createTask: vi.fn(),
    dispatchCommand: vi.fn(),
    endPushToTalk: vi.fn(),
    globalStop: vi.fn(),
    routeIntent: vi.fn(),
  }));

vi.mock("@/lib/api", () => ({
  api: { createTask, dispatchCommand, globalStop, routeIntent },
}));

vi.mock("@/lib/native", () => ({
  native: { beginPushToTalk, endPushToTalk },
}));

describe("CommandCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useTasksStore.setState({
      tasks: {},
      activeTaskId: null,
      pendingApprovals: [],
      auditByTask: {},
    });
  });

  it("dispatches a typed Stop reflex without sending it to the planner", async () => {
    dispatchCommand.mockResolvedValue({
      route: { tier: "reflex", reflex_kind: "stop" },
      control: "stopped",
      response: {
        intent: "interrupted",
        display: { text: "Stopped. No external action was taken." },
        spoken: { text: "Stopped. No external action was taken.", max_chars: 240 },
        used_model: false,
      },
      task: null,
    });
    render(<CommandCenter />);

    fireEvent.change(screen.getByLabelText("Goal"), {
      target: { value: "omnimac stop" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send goal" }));

    await waitFor(() => expect(dispatchCommand).toHaveBeenCalledWith("omnimac stop", "text"));
    expect(createTask).not.toHaveBeenCalled();
    expect(routeIntent).not.toHaveBeenCalled();
    expect(globalStop).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Goal")).toHaveValue("");
    expect(screen.getByLabelText("OmniMac control response")).toHaveTextContent(
      "Stopped. No external action was taken.",
    );
  });

  it("dispatches click-to-talk when the button is clicked", () => {
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    render(<CommandCenter />);
    const microphone = screen.getByRole("button", { name: "Click to talk" });

    fireEvent.click(microphone);
    
    expect(dispatchSpy).toHaveBeenCalled();
    const callArg = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(callArg.type).toBe("omnimac:ptt");
    expect(callArg.detail).toEqual({ state: "Pressed" });
    
    dispatchSpy.mockRestore();
  });

  it("does not expose internal task errors when a safe presentation exists", () => {
    const failed = {
      id: "failed-task",
      goal: "Open TextEdit",
      state: "FAILED_REQUIRES_USER",
      error: "authoritative plan failed; model-generated recovery is disabled",
      result_summary: null,
      presentation: {
        task_id: "failed-task",
        authoritative: true,
        response: {
          intent: "resumable_task",
          used_model: false,
          display: {
            text: "TextEdit did not become frontmost. No completion was claimed.",
          },
          spoken: {
            text: "TextEdit did not become frontmost.",
            max_chars: 240,
          },
        },
        display_response: "TextEdit did not become frontmost. No completion was claimed.",
        spoken_response_preview: "TextEdit did not become frontmost.",
        foreground: null,
        matched_workspace_id: null,
        planned_focus_policy: "keep_new_focus",
        focus_result: null,
        runtime_status: "ready",
        dialogue_expires_at: null,
        stages: {
          proposed: true,
          approval: "not_required",
          executed: true,
          verified: false,
        },
      },
    } as unknown as TaskPayload;
    useTasksStore.setState({
      tasks: { [failed.id]: failed },
      activeTaskId: failed.id,
      pendingApprovals: [],
      auditByTask: {},
    });

    render(<CommandCenter />);

    expect(
      screen.getAllByText("TextEdit did not become frontmost. No completion was claimed."),
    ).not.toHaveLength(0);
    expect(screen.queryByText(/model-generated recovery/)).not.toBeInTheDocument();
  });
});
