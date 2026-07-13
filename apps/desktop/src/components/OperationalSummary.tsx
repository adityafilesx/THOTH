import { AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { TaskPresentation } from "@/lib/api";
import { cn } from "@/lib/utils";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function Stage({ name, reached }: { name: string; reached: boolean }) {
  return (
    <span
      data-testid={`stage-${name}`}
      className={cn(
        "font-mono text-[10px] uppercase tracking-wide",
        reached ? "text-accent" : "text-faint",
      )}
    >
      {name}
    </span>
  );
}

export function OperationalSummary({
  presentation,
}: {
  presentation: TaskPresentation;
}) {
  const expired =
    presentation.dialogue_expires_at !== null &&
    Date.parse(presentation.dialogue_expires_at) <= Date.now();
  const isPartial = presentation.response.intent === "partial_completion";

  return (
    <Card
      aria-label="THOTH operational status"
      data-testid="operational-summary"
    >
      <CardContent className="space-y-4">
        <div>
          <div className="eyebrow mb-1">THOTH</div>
          <p
            data-testid="display-response"
            className={cn("text-sm text-ink", isPartial && "text-warning")}
          >
            {presentation.display_response}
          </p>
          {presentation.spoken_response_preview && (
            <p className="mt-1 text-xs text-muted" data-testid="spoken-preview">
              Spoken preview: {presentation.spoken_response_preview}
            </p>
          )}
        </div>

        <div
          className="flex flex-wrap items-center gap-2"
          aria-label="Task stage status"
        >
          <Stage name="proposed" reached={presentation.stages.proposed} />
          <Stage
            name="approved"
            reached={
              presentation.stages.approval === "approved" ||
              presentation.stages.approval === "not_required"
            }
          />
          <Stage name="executed" reached={presentation.stages.executed} />
          <Stage name="verified" reached={presentation.stages.verified} />
          {presentation.stages.approval === "pending" && (
            <Badge variant="amber">approval pending</Badge>
          )}
        </div>

        <dl className="grid gap-2 text-xs sm:grid-cols-2">
          <div>
            <dt className="eyebrow">foreground</dt>
            <dd data-testid="foreground-app" className="text-ink">
              {presentation.foreground?.active_app_name ?? "Unavailable"}
              {presentation.foreground?.active_bundle_id
                ? ` · ${presentation.foreground.active_bundle_id}`
                : ""}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">workspace</dt>
            <dd data-testid="matched-workspace" className="text-ink">
              {presentation.matched_workspace_id ?? "No authoritative match"}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">planned focus</dt>
            <dd data-testid="planned-focus" className="text-ink">
              {presentation.planned_focus_policy
                ? label(presentation.planned_focus_policy)
                : "Not applicable"}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">local runtime</dt>
            <dd
              data-testid="runtime-status"
              className="flex items-center gap-1 text-ink"
            >
              {presentation.runtime_status === "ready" ? (
                <CheckCircle2 size={12} className="text-success" />
              ) : (
                <AlertTriangle size={12} className="text-warning" />
              )}
              {label(presentation.runtime_status)}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">focus outcome</dt>
            <dd
              data-testid="focus-outcome"
              className={cn(
                "text-ink",
                presentation.focus_result &&
                  !presentation.focus_result.verified &&
                  "text-danger",
              )}
            >
              {presentation.focus_result
                ? `${presentation.focus_result.verified ? "verified" : "failed"} · ${presentation.focus_result.detail}`
                : "Not recorded"}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">dialogue context</dt>
            <dd
              data-testid="dialogue-expiry"
              className="flex items-center gap-1 text-ink"
            >
              <Clock3 size={12} />
              {presentation.dialogue_expires_at
                ? expired
                  ? "Expired"
                  : `Expires ${presentation.dialogue_expires_at}`
                : "Unavailable"}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
