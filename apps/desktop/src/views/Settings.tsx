import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

/**
 * Live, read-only view of daemon settings (GET /api/settings). Editing lands
 * later; values here are the daemon's real running config.
 */
export function Settings() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          Live daemon config (read-only; editing lands later).
        </p>
        <Badge variant="success">live</Badge>
      </div>

      {isLoading && <p className="text-xs text-muted">Loading settings…</p>}
      {isError && (
        <p className="text-xs text-danger">Could not reach the daemon.</p>
      )}

      {data && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Planner &amp; execution</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <label className="flex items-center justify-between gap-4 text-xs text-muted">
                Planner
                <Input
                  readOnly
                  value={data.planner}
                  className="w-64 font-mono text-xs"
                />
              </label>
              <label className="flex items-center justify-between gap-4 text-xs text-muted">
                Approval TTL (seconds)
                <Input
                  readOnly
                  value={String(data.approval_ttl_seconds)}
                  className="w-24 text-right font-mono text-xs"
                />
              </label>
              <label className="flex items-center justify-between gap-4 text-xs text-muted">
                Retry budget (step / task)
                <Input
                  readOnly
                  value={`${data.max_retries_per_step} / ${data.max_retries_per_task}`}
                  className="w-24 text-right font-mono text-xs"
                />
              </label>
              <p className="text-[11px] text-faint">Daemon v{data.version}.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Voice</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <label className="flex items-center justify-between text-xs text-muted">
                Push-to-talk (later in Phase 3)
                <Switch disabled aria-label="Push-to-talk" />
              </label>
              <p className="text-[11px] text-faint">
                No always-on listening, ever. Audio is transcribed locally and
                discarded.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Trusted workspaces</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <p className="text-[11px] text-faint">
                R1 actions run without prompting only inside these directories.
              </p>
              {data.trusted_workspaces.length === 0 ? (
                <p className="text-xs text-muted">None configured.</p>
              ) : (
                data.trusted_workspaces.map((ws) => (
                  <code
                    key={ws}
                    className="rounded-md border border-line bg-raised px-3 py-2 font-mono text-xs text-ink"
                  >
                    {ws}
                  </code>
                ))
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
