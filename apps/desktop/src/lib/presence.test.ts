import { describe, expect, it } from "vitest";

import { buildPresenceState } from "./presence";

describe("buildPresenceState", () => {
  it("maps live task and runtime state without transcript or secret fields", () => {
    const state = buildPresenceState({
      taskState: "WAITING_FOR_APPROVAL",
      hasPendingApproval: true,
      microphoneEnabled: true,
      voiceState: "idle",
      plannerState: "ready",
      sttState: "degraded",
      ttsState: "ready",
      accessibilityState: "not_determined",
      privacyMode: "ephemeral",
    });
    expect(state.status).toBe("WAITING_FOR_APPROVAL");
    expect(state.pendingApproval).toBe(true);
    expect(state.sttStatus).toBe("degraded");
    expect(JSON.stringify(state).toLowerCase()).not.toContain("transcript");
    expect(JSON.stringify(state).toLowerCase()).not.toContain("token");
  });
});
