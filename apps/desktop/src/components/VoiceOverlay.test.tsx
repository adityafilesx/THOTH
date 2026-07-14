import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VoiceOverlayView } from "./VoiceOverlay";

describe("VoiceOverlayView", () => {
  it("shows visible local listening and partial transcript state", () => {
    render(
      <VoiceOverlayView
        state="listening"
        partial="continue the thoth"
        finalText=""
        route="reflex"
        error={null}
        onEdit={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText("Listening")).toBeInTheDocument();
    expect(screen.getByText("continue the thoth")).toBeInTheDocument();
    expect(screen.getByText("Processed locally")).toBeInTheDocument();
    expect(screen.getByTestId("microphone-indicator")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("allows final transcript correction before explicit submit", () => {
    const edit = vi.fn();
    const submit = vi.fn();
    render(
      <VoiceOverlayView
        state="ready"
        partial=""
        finalText="run the tests"
        route="skill"
        error={null}
        onEdit={edit}
        onCancel={vi.fn()}
        onSubmit={submit}
      />,
    );
    fireEvent.change(screen.getByLabelText("Final transcript"), {
      target: { value: "run all tests" },
    });
    expect(edit).toHaveBeenCalledWith("run all tests");
    fireEvent.click(screen.getByRole("button", { name: "Submit voice command" }));
    expect(submit).toHaveBeenCalledOnce();
    expect(screen.getByText("Skill")).toBeInTheDocument();
  });

  it("keeps failure visible and offers cancel", () => {
    const cancel = vi.fn();
    render(
      <VoiceOverlayView
        state="failed"
        partial=""
        finalText=""
        route={null}
        error="Local speech recognition is unavailable."
        onEdit={vi.fn()}
        onCancel={cancel}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Cancel voice command" }));
    expect(cancel).toHaveBeenCalledOnce();
  });
});
