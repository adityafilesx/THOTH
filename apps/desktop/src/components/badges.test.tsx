import { render, screen } from "@testing-library/react";
import { TASK_STATES, type RiskLevel, type TaskState } from "@omnimac/shared-schemas";
import { describe, expect, it } from "vitest";

import { RiskBadge } from "./RiskBadge";
import { StateBadge } from "./StateBadge";
import { StateLadder } from "./StateLadder";

describe("RiskBadge", () => {
  it.each(["R0", "R1", "R2", "R3"] as RiskLevel[])("renders %s", (risk) => {
    render(<RiskBadge risk={risk} />);
    expect(screen.getByTestId(`risk-${risk}`)).toBeInTheDocument();
    expect(screen.getByTestId(`risk-${risk}`).textContent).toContain(risk);
  });
});

describe("StateBadge", () => {
  it.each(TASK_STATES)("renders task state %s", (state: TaskState) => {
    render(<StateBadge state={state} />);
    const el = screen.getByTestId(`state-${state}`);
    expect(el).toBeInTheDocument();
    expect(el.textContent).toContain(state.replaceAll("_", " "));
  });
});

describe("StateLadder", () => {
  it.each(TASK_STATES)("marks %s as the current step", (state: TaskState) => {
    render(<StateLadder current={state} />);
    const current = screen
      .getAllByRole("listitem")
      .filter((li) => li.getAttribute("aria-current") === "step");
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain(state.replaceAll("_", " "));
  });

  it("renders nothing lit when no task is active", () => {
    render(<StateLadder current={null} />);
    const current = screen
      .getAllByRole("listitem")
      .filter((li) => li.getAttribute("aria-current") === "step");
    expect(current).toHaveLength(0);
  });
});
