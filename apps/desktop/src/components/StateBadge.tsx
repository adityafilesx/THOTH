import type { TaskState } from "@omnimac/shared-schemas";

import { cn } from "@/lib/utils";

const ACTIVE = "border-accent/40 bg-accent/10 text-accent";
const QUIET = "border-line bg-raised text-muted";

const STYLES: Record<TaskState, string> = {
  RECEIVED: QUIET,
  UNDERSTANDING: ACTIVE,
  PLANNING: ACTIVE,
  RISK_REVIEW: "border-amber/40 bg-amber/10 text-amber",
  WAITING_FOR_APPROVAL: "border-amber/40 bg-amber/10 text-amber",
  EXECUTING: ACTIVE,
  VERIFYING: ACTIVE,
  RECOVERING: "border-amber/40 bg-amber/10 text-amber",
  COMPLETED: "border-success/40 bg-success/10 text-success",
  FAILED: "border-danger/40 bg-danger/10 text-danger",
  FAILED_REQUIRES_USER: "border-danger/40 bg-danger/10 text-danger",
  CANCELLED: QUIET,
};

const PULSING: TaskState[] = [
  "EXECUTING",
  "VERIFYING",
  "PLANNING",
  "UNDERSTANDING",
  "RECOVERING",
];

export function StateBadge({ state }: { state: TaskState }) {
  return (
    <span
      data-testid={`state-${state}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        STYLES[state],
      )}
    >
      {PULSING.includes(state) && (
        <span
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
          aria-hidden
        />
      )}
      {state.replaceAll("_", " ")}
    </span>
  );
}
