import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  captureStopDelay,
  flushAndStopRecorder,
  shouldRequestPartial,
  voiceRouteForIntent,
  VoiceOverlay,
  VoiceOverlayView,
} from "./VoiceOverlay";

describe("voice routing labels", () => {
  it("labels deterministic skill commands as Skill", () => {
    expect(
      voiceRouteForIntent({
        tier: "reflex",
        reflex_kind: "run_skill",
        target: "run-project-tests",
      }),
    ).toBe("skill");
  });

  it("does not mislabel a safety clarification as Reflex", () => {
    expect(voiceRouteForIntent({ tier: "clarify" })).toBe("clarify");
  });
});

describe("push-to-talk recorder release", () => {
  it("delays an early release until the minimum capture window", () => {
    expect(captureStopDelay(1_000, 1_100)).toBe(400);
    expect(captureStopDelay(1_000, 1_500)).toBe(0);
    expect(captureStopDelay(1_000, 2_000)).toBe(0);
  });

  it("requests pending audio before stopping the recorder", () => {
    const calls: string[] = [];
    const fakeRecorder = {
      state: "recording" as RecordingState,
      requestData: () => calls.push("requestData"),
      stop: () => calls.push("stop"),
    };

    expect(flushAndStopRecorder(fakeRecorder)).toBe(true);
    expect(calls).toEqual(["requestData", "stop"]);
  });

  it("does not stop an inactive recorder", () => {
    const requestData = vi.fn();
    const stop = vi.fn();

    expect(
      flushAndStopRecorder({ state: "inactive", requestData, stop }),
    ).toBe(false);
    expect(requestData).not.toHaveBeenCalled();
    expect(stop).not.toHaveBeenCalled();
  });
});

describe("partial transcription cadence", () => {
  it("waits before the initial partial and then throttles local whisper work", () => {
    expect(shouldRequestPartial(null, 749, 0)).toBe(false);
    expect(shouldRequestPartial(null, 750, 0)).toBe(true);
    expect(shouldRequestPartial(750, 1_499, 0)).toBe(false);
    expect(shouldRequestPartial(750, 1_500, 0)).toBe(true);
  });
});

describe("VoiceOverlayView", () => {
  it("can stay mounted for browser PTT without showing an idle panel", () => {
    const { container } = render(
      <VoiceOverlay listenForNativeEvents={false} hideWhenIdle />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("shows visible local listening and partial transcript state", () => {
    render(
      <VoiceOverlayView
        state="listening"
        partial="continue the omnimac"
        finalText=""
        route="reflex"
        error={null}
        onEdit={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText("Listening")).toBeInTheDocument();
    expect(screen.getByText("continue the omnimac")).toBeInTheDocument();
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
