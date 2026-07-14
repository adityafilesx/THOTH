import { ShieldCheck, Square } from "lucide-react";

import { api, type TaskPayload } from "@/lib/api";

const ACTIVE_STEP_STATES = new Set(["running", "verifying", "pending"]);

function label(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/^./, (first) => first.toUpperCase());
}

export function ExecutionHUD({ task }: { task: TaskPayload | null }) {
  if (!task || ["COMPLETED", "CANCELLED"].includes(task.state)) return null;
  const steps = task.plan?.steps ?? [];
  const current = steps.find((step) => ACTIVE_STEP_STATES.has(step.status));
  const index = current ? steps.indexOf(current) + 1 : 0;
  const status =
    task.state === "FAILED" || task.state === "FAILED_REQUIRES_USER"
      ? "Partial or failed"
      : current?.status === "verifying"
        ? "Verifying"
      : task.state === "WAITING_FOR_APPROVAL"
        ? "Approval required"
        : label(task.state);

  return (
    <aside
      aria-label="Execution status"
      className="fixed bottom-5 right-5 z-40 w-80 rounded-xl border border-line bg-panel/95 p-4 shadow-2xl backdrop-blur"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="eyebrow">{status}</div>
          <p className="truncate text-sm font-medium text-ink">{task.goal}</p>
        </div>
        <button
          type="button"
          aria-label="Stop active task"
          className="rounded border border-danger/50 p-1.5 text-danger"
          onClick={() => void api.globalStop("global_button")}
        >
          <Square size={12} fill="currentColor" />
        </button>
      </div>

      {current && (
        <p className="mt-3 text-xs text-muted">
          {index} of {steps.length} · {current.title}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-faint">
        {current?.focus_policy && (
          <span className="rounded bg-surface px-2 py-1">
            {label(current.focus_policy)}
          </span>
        )}
        {current?.verification_passed === true && (
          <span className="inline-flex items-center gap-1 rounded bg-success/10 px-2 py-1 text-success">
            <ShieldCheck size={11} /> Verified
          </span>
        )}
      </div>
      {(task.result_summary || task.error) && (
        <p className="mt-3 text-xs text-muted">
          {task.result_summary ?? task.error}
        </p>
      )}
    </aside>
  );
}
