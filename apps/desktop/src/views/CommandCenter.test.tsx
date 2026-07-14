import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTasksStore } from "@/stores/tasks";

import { CommandCenter } from "./CommandCenter";

const { createTask, dispatchCommand, globalStop, routeIntent } = vi.hoisted(() => ({
  createTask: vi.fn(),
  dispatchCommand: vi.fn(),
  globalStop: vi.fn(),
  routeIntent: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: { createTask, dispatchCommand, globalStop, routeIntent },
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
      target: { value: "thoth stop" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send goal" }));

    await waitFor(() => expect(dispatchCommand).toHaveBeenCalledWith("thoth stop", "text"));
    expect(createTask).not.toHaveBeenCalled();
    expect(routeIntent).not.toHaveBeenCalled();
    expect(globalStop).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Goal")).toHaveValue("");
    expect(screen.getByLabelText("THOTH control response")).toHaveTextContent(
      "Stopped. No external action was taken.",
    );
  });
});
