import { TASK_STATES, type TaskState } from "@thoth/shared-schemas";

import { cn } from "@/lib/utils";

/**
 * The state ladder — THOTH's signature element. The full task lifecycle
 * rendered as a launch-sequence checklist; the current state is lit, past
 * states dimly confirmed, terminal states colored by outcome.
 */
const ORDER: TaskState[] = TASK_STATES.filter(
  (s) => !["COMPLETED", "FAILED", "CANCELLED"].includes(s),
);
const TERMINALS: TaskState[] = ["COMPLETED", "FAILED", "CANCELLED"];

function terminalStyle(state: TaskState): string {
  if (state === "COMPLETED") return "text-success";
  if (state === "FAILED") return "text-danger";
  return "text-muted";
}

export function StateLadder({ current }: { current: TaskState | null }) {
  const currentIndex = current ? ORDER.indexOf(current) : -1;
  const isTerminal = current !== null && TERMINALS.includes(current);

  return (
    <ol data-testid="state-ladder" className="flex flex-col gap-0.5 font-mono text-[11px]">
      {ORDER.map((state, i) => {
        const isCurrent = state === current;
        const isPast = !isTerminal && currentIndex > i;
        return (
          <li
            key={state}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-sm px-2 py-1 uppercase tracking-wider",
              isCurrent && "bg-accent/10 text-accent",
              isPast && "text-faint",
              !isCurrent && !isPast && "text-faint/60",
            )}
          >
            <span aria-hidden>{isCurrent ? "▶" : isPast ? "✓" : "·"}</span>
            {state.replaceAll("_", " ")}
          </li>
        );
      })}
      <li aria-hidden className="px-2 text-faint/60">
        ──────
      </li>
      {TERMINALS.map((state) => (
        <li
          key={state}
          aria-current={state === current ? "step" : undefined}
          className={cn(
            "flex items-center gap-2 rounded-sm px-2 py-1 uppercase tracking-wider",
            state === current ? cn("bg-raised", terminalStyle(state)) : "text-faint/60",
          )}
        >
          <span aria-hidden>{state === current ? "■" : "·"}</span>
          {state}
        </li>
      ))}
    </ol>
  );
}
