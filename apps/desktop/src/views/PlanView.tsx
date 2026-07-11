import type { ExecutionPlan, PlanStep } from "@thoth/shared-schemas";
import { CheckCircle2, Circle, CircleDashed, Loader2, XCircle } from "lucide-react";

import { RiskBadge } from "@/components/RiskBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MOCK_PLAN } from "@/lib/mockData";
import { cn } from "@/lib/utils";
import { useTasksStore } from "@/stores/tasks";

function StepIcon({ step }: { step: PlanStep }) {
  switch (step.status) {
    case "succeeded":
      return <CheckCircle2 size={15} className="text-success" />;
    case "failed":
      return <XCircle size={15} className="text-danger" />;
    case "running":
    case "verifying":
      return <Loader2 size={15} className="animate-spin text-accent" />;
    case "cancelled":
    case "skipped":
      return <Circle size={15} className="text-faint" />;
    default:
      return <CircleDashed size={15} className="text-faint" />;
  }
}

function verificationLabel(step: PlanStep): string {
  if (step.verification_passed === true) return "verified";
  if (step.verification_passed === false) return "verification failed";
  if (step.status === "verifying") return "verifying…";
  return "not verified";
}

export function PlanView() {
  const tasks = useTasksStore((s) => s.tasks);
  const activeTaskId = useTasksStore((s) => s.activeTaskId);
  const activePlan = activeTaskId ? tasks[activeTaskId]?.plan : null;

  const plan: ExecutionPlan | null = activePlan ?? MOCK_PLAN;
  const isMock = !activePlan;

  if (!plan) {
    return <p className="py-16 text-center text-sm text-muted">No plan yet.</p>;
  }

  return (
    <Card className="mx-auto max-w-3xl">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <div className="eyebrow mb-1">execution plan</div>
          <CardTitle>{plan.summary}</CardTitle>
        </div>
        {isMock && <Badge variant="amber">mock data</Badge>}
      </CardHeader>
      <CardContent className="p-0">
        <ol>
          {plan.steps.map((step) => (
            <li
              key={step.id}
              className={cn(
                "flex items-start gap-3 border-b border-line px-4 py-3 last:border-b-0",
                (step.status === "running" || step.status === "verifying") && "bg-accent/5",
              )}
            >
              <span className="mt-0.5 shrink-0">
                <StepIcon step={step} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-faint">
                    {String(step.index + 1).padStart(2, "0")}
                  </span>
                  <span className="truncate text-sm text-ink">{step.title}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <code className="font-mono text-[11px] text-muted">{step.tool_name}</code>
                  <span className="font-mono text-[10px] text-faint">
                    {verificationLabel(step)}
                    {step.verification_detail ? ` — ${step.verification_detail}` : ""}
                  </span>
                </div>
              </div>
              <RiskBadge risk={step.declared_risk} compact />
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
