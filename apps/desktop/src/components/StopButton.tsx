import { Square } from "lucide-react";

import { api } from "@/lib/api";
import { useTasksStore } from "@/stores/tasks";

const ACTIVE_STATES = [
  "RECEIVED",
  "UNDERSTANDING",
  "PLANNING",
  "RISK_REVIEW",
  "WAITING_FOR_APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "RECOVERING",
];

/** Global stop: cancels every non-terminal task immediately. */
export function StopButton() {
  const tasks = useTasksStore((s) => s.tasks);
  const active = Object.values(tasks).filter((t) => ACTIVE_STATES.includes(t.state));

  const stopAll = () => void api.globalStop("global_button").catch(() => {});

  return (
    <button
      type="button"
      onClick={stopAll}
      disabled={active.length === 0}
      data-testid="global-stop"
      className="inline-flex h-8 items-center gap-2 rounded-md border border-danger/50 bg-danger/10 px-3 font-mono text-xs uppercase tracking-wider text-danger transition-colors hover:bg-danger hover:text-bg disabled:pointer-events-none disabled:opacity-30"
    >
      <Square size={12} fill="currentColor" />
      Stop{active.length > 0 ? ` (${active.length})` : ""}
    </button>
  );
}
