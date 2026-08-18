import type { TaskState } from "@omnimac/shared-schemas";

export type PresenceStatus =
  | "IDLE"
  | "LISTENING"
  | "TRANSCRIBING"
  | "ROUTING"
  | "PLANNING"
  | "WAITING_FOR_APPROVAL"
  | "EXECUTING"
  | "VERIFYING"
  | "RECOVERING"
  | "SPEAKING"
  | "DEGRADED"
  | "FAILED";

export interface PresenceInput {
  taskState: TaskState | null;
  hasPendingApproval: boolean;
  microphoneEnabled: boolean;
  voiceState: "idle" | "listening" | "transcribing" | "speaking" | "failed";
  plannerState: string;
  sttState: string;
  ttsState: string;
  accessibilityState: string;
  privacyMode: "ephemeral" | "retain_transcripts";
}

export interface PresenceState {
  status: PresenceStatus;
  currentTask: boolean;
  pendingApproval: boolean;
  microphoneEnabled: boolean;
  plannerStatus: string;
  sttStatus: string;
  ttsStatus: string;
  accessibilityStatus: string;
  privacyMode: string;
}

const TERMINAL = new Set<TaskState>([
  "COMPLETED",
  "FAILED",
  "FAILED_REQUIRES_USER",
  "CANCELLED",
]);

export function buildPresenceState(input: PresenceInput): PresenceState {
  let status: PresenceStatus = "IDLE";
  if (input.voiceState === "listening") status = "LISTENING";
  else if (input.voiceState === "transcribing") status = "TRANSCRIBING";
  else if (input.voiceState === "speaking") status = "SPEAKING";
  else if (input.voiceState === "failed") status = "FAILED";
  else if (input.taskState === "UNDERSTANDING") status = "ROUTING";
  else if (input.taskState === "PLANNING") status = "PLANNING";
  else if (input.taskState === "WAITING_FOR_APPROVAL") status = "WAITING_FOR_APPROVAL";
  else if (input.taskState === "EXECUTING") status = "EXECUTING";
  else if (input.taskState === "VERIFYING") status = "VERIFYING";
  else if (input.taskState === "RECOVERING") status = "RECOVERING";
  else if (input.taskState === "FAILED" || input.taskState === "FAILED_REQUIRES_USER") {
    status = "FAILED";
  } else if (input.sttState === "degraded" || input.plannerState === "degraded") {
    status = "DEGRADED";
  }

  return {
    status,
    currentTask: input.taskState !== null && !TERMINAL.has(input.taskState),
    pendingApproval: input.hasPendingApproval,
    microphoneEnabled: input.microphoneEnabled,
    plannerStatus: input.plannerState,
    sttStatus: input.sttState,
    ttsStatus: input.ttsState,
    accessibilityStatus: input.accessibilityState,
    privacyMode: input.privacyMode,
  };
}
