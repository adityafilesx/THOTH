import type { AuditEvent } from "@omnimac/shared-schemas";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MOCK_AUDIT } from "@/lib/mockData";
import { formatTime } from "@/lib/utils";
import { useTasksStore } from "@/stores/tasks";

function eventTone(type: string): "default" | "accent" | "amber" | "danger" | "success" {
  if (type.includes("blocked") || type.includes("rejected") || type.includes("failed"))
    return "danger";
  if (type.includes("approval")) return "amber";
  if (type.includes("verified") || type.includes("completed")) return "success";
  if (type.includes("tool") || type.includes("transition")) return "accent";
  return "default";
}

export function Timeline() {
  const auditByTask = useTasksStore((s) => s.auditByTask);
  const activeTaskId = useTasksStore((s) => s.activeTaskId);

  const liveEvents: AuditEvent[] = activeTaskId ? (auditByTask[activeTaskId] ?? []) : [];
  const events = liveEvents.length > 0 ? liveEvents : MOCK_AUDIT;
  const isMock = liveEvents.length === 0;

  return (
    <Card className="mx-auto max-w-3xl">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Activity timeline</CardTitle>
        {isMock && <Badge variant="amber">mock data</Badge>}
      </CardHeader>
      <CardContent className="p-0">
        {events.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted">
            No activity yet. Events appear here as tasks run.
          </p>
        ) : (
          <ol data-testid="timeline-list">
            {events.map((event) => (
              <li
                key={event.event_id}
                className="flex items-baseline gap-3 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <span className="w-16 shrink-0 font-mono text-[10px] text-faint">
                  {formatTime(event.created_at)}
                </span>
                <span className="w-8 shrink-0 text-right font-mono text-[10px] text-faint">
                  #{event.seq}
                </span>
                <Badge variant={eventTone(event.event_type)}>{event.event_type}</Badge>
                <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted">
                  {JSON.stringify(event.payload)}
                </code>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
