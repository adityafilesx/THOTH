import { useEffect, useState } from "react";

import { RiskBadge } from "@/components/RiskBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useTasksStore } from "@/stores/tasks";
import { useUiStore } from "@/stores/ui";

/**
 * Approval drawer: shows the exact proposed action and its payload.
 * Decisions are single-use and bound to one tool invocation — "Approve once"
 * is the only grant the daemon accepts.
 */
export function ApprovalDrawer() {
  const pending = useTasksStore((s) => s.pendingApprovals);
  const open = useUiStore((s) => s.approvalDrawerOpen);
  const setOpen = useUiStore((s) => s.setApprovalDrawerOpen);
  const [modifying, setModifying] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const approval = pending[0] ?? null;

  useEffect(() => {
    if (pending.length > 0) setOpen(true);
  }, [pending.length, setOpen]);

  useEffect(() => {
    setModifying(false);
    setError(null);
    setDraft(approval ? JSON.stringify(approval.arguments, null, 2) : "");
  }, [approval?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!approval) return null;

  const decide = async (approved: boolean, modifiedArguments?: Record<string, unknown>) => {
    setError(null);
    try {
      await api.decideApproval(approval.id, approved, modifiedArguments);
      if (pending.length <= 1) setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    }
  };

  const submitModified = () => {
    try {
      const parsed = JSON.parse(draft) as Record<string, unknown>;
      void decide(true, parsed);
    } catch {
      setError("Arguments must be valid JSON");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent aria-describedby={undefined}>
        <div className="flex flex-col gap-4 overflow-y-auto p-5">
          <div>
            <div className="eyebrow mb-1 text-amber">approval required</div>
            <DialogTitle className="text-base font-medium text-ink">
              {approval.tool_name}
            </DialogTitle>
            <DialogDescription className="mt-1 text-xs text-muted">
              {approval.reason}
            </DialogDescription>
          </div>

          <div className="flex items-center gap-2">
            <RiskBadge risk={approval.risk} />
            <span className="font-mono text-[10px] text-faint">
              expires {new Date(approval.expires_at).toLocaleTimeString()}
            </span>
          </div>

          <div>
            <div className="eyebrow mb-1">target</div>
            <p className="font-mono text-xs text-ink">{approval.target}</p>
          </div>

          <div>
            <div className="eyebrow mb-1">data to be sent</div>
            {modifying ? (
              <Textarea
                rows={8}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="font-mono text-xs"
                aria-label="Modified arguments (JSON)"
              />
            ) : (
              <pre className="overflow-x-auto rounded-md border border-line bg-raised p-3 font-mono text-xs text-ink">
                {JSON.stringify(approval.arguments, null, 2)}
              </pre>
            )}
          </div>

          {error && (
            <p role="alert" className="font-mono text-xs text-danger">
              {error}
            </p>
          )}

          <div className="mt-auto flex gap-2 border-t border-line pt-4">
            {modifying ? (
              <>
                <Button variant="success" onClick={submitModified}>
                  Approve modified
                </Button>
                <Button variant="ghost" onClick={() => setModifying(false)}>
                  Back
                </Button>
              </>
            ) : (
              <>
                <Button variant="success" onClick={() => void decide(true)}>
                  Approve once
                </Button>
                <Button variant="danger" onClick={() => void decide(false)}>
                  Deny
                </Button>
                <Button variant="outline" onClick={() => setModifying(true)}>
                  Modify
                </Button>
              </>
            )}
          </div>
          {pending.length > 1 && (
            <p className="font-mono text-[10px] text-faint">
              {pending.length - 1} more approval{pending.length > 2 ? "s" : ""} queued
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
