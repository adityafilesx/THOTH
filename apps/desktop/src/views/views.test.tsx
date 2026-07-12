import { render, screen, within } from "@testing-library/react";
import type { ApprovalRequest } from "@thoth/shared-schemas";
import { beforeEach, describe, expect, it } from "vitest";

import { MOCK_TASK } from "@/lib/mockData";
import { useTasksStore } from "@/stores/tasks";
import { useUiStore } from "@/stores/ui";

import { ApprovalDrawer } from "./ApprovalDrawer";
import { PlanView } from "./PlanView";
import { Timeline } from "./Timeline";

const APPROVAL: ApprovalRequest = {
  id: "ap-1",
  correlation_id: "t-1",
  task_id: "t-1",
  invocation_id: "inv-1",
  step_id: "s-1",
  tool_name: "mock_send_email",
  arguments: { recipient: "a@b.c", subject: "Hello" },
  risk: "R2",
  reason: "External side effect: sending email requires explicit approval.",
  target: "a@b.c",
  status: "pending",
  created_at: "2026-07-11T09:00:00Z",
  expires_at: "2026-07-11T09:02:00Z",
};

beforeEach(() => {
  useTasksStore.setState({
    tasks: {},
    activeTaskId: null,
    pendingApprovals: [],
    auditByTask: {},
  });
  useUiStore.setState({ view: "command", approvalDrawerOpen: false });
});

describe("PlanView", () => {
  it("shows the mock-data badge when no live plan exists", () => {
    render(<PlanView />);
    expect(screen.getByText(/mock data/i)).toBeInTheDocument();
    expect(screen.getByText("Inspect repository status")).toBeInTheDocument();
  });

  it("renders a live plan without the mock badge", () => {
    useTasksStore.setState({
      tasks: {
        [MOCK_TASK.id]: {
          ...MOCK_TASK,
          plan: { ...MOCK_TASK.plan!, summary: "Live plan" },
        },
      },
      activeTaskId: MOCK_TASK.id,
    });
    render(<PlanView />);
    expect(screen.getByText("Live plan")).toBeInTheDocument();
    expect(screen.queryByText(/mock data/i)).not.toBeInTheDocument();
  });

  it("shows risk chips for every step", () => {
    render(<PlanView />);
    expect(screen.getByTestId("risk-R0")).toBeInTheDocument();
    expect(screen.getByTestId("risk-R1")).toBeInTheDocument();
    expect(screen.getByTestId("risk-R2")).toBeInTheDocument();
  });

  it("distinguishes proposed, approved, executed and verified per step", () => {
    render(<PlanView />);
    const lifecycles = screen.getAllByTestId("lifecycle");
    expect(lifecycles).toHaveLength(3);
    // Each step renders all four lifecycle labels; reached stages are
    // accent-toned, unreached are faint (both present as text).
    for (const stage of ["proposed", "approved", "executed", "verified"]) {
      expect(within(lifecycles[0]).getByText(stage)).toBeInTheDocument();
    }
    // Step 1 is succeeded+verified → all four reached.
    const verifiedStep = lifecycles[0];
    expect(within(verifiedStep).getByText("verified")).toHaveClass(
      "text-accent",
    );
    // Step 3 is pending → only "proposed" reached.
    const pendingStep = lifecycles[2];
    expect(within(pendingStep).getByText("proposed")).toHaveClass(
      "text-accent",
    );
    expect(within(pendingStep).getByText("approved")).toHaveClass("text-faint");
  });

  it("surfaces the correlation id for the active plan", () => {
    render(<PlanView />);
    expect(screen.getByText(/corr mock-cor/i)).toBeInTheDocument();
  });

  it("lists the independent verifier probes declared for each step", () => {
    render(<PlanView />);
    const probeRows = screen.getAllByTestId("verifier-checks");
    expect(probeRows).toHaveLength(3);
    expect(within(probeRows[0]).getByText("file_exists")).toBeInTheDocument();
    expect(
      within(probeRows[1]).getByText("application_running"),
    ).toBeInTheDocument();
    expect(within(probeRows[2]).getByText("git_state")).toBeInTheDocument();
  });
});

describe("Timeline", () => {
  it("falls back to mock audit events with a badge", () => {
    render(<Timeline />);
    expect(screen.getByText(/mock data/i)).toBeInTheDocument();
    expect(screen.getByTestId("timeline-list")).toBeInTheDocument();
  });
});

describe("ApprovalDrawer", () => {
  it("shows the exact action, target, payload and reason", () => {
    useTasksStore.setState({ pendingApprovals: [APPROVAL] });
    useUiStore.setState({ approvalDrawerOpen: true });
    render(<ApprovalDrawer />);
    expect(screen.getByText("mock_send_email")).toBeInTheDocument();
    expect(screen.getByText("a@b.c")).toBeInTheDocument();
    expect(screen.getByText(/requires explicit approval/i)).toBeInTheDocument();
    expect(screen.getByText(/"subject": "Hello"/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /approve once/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deny/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /modify/i })).toBeInTheDocument();
  });

  it("renders nothing when no approval is pending", () => {
    useUiStore.setState({ approvalDrawerOpen: true });
    const { container } = render(<ApprovalDrawer />);
    expect(container).toBeEmptyDOMElement();
  });
});
