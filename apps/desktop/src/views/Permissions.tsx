import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppWindow, FolderOpen, Globe } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Grant } from "@/lib/api";

const KIND_META = {
  app: { icon: AppWindow, label: "Applications" },
  path: { icon: FolderOpen, label: "Workspace directories" },
  domain: { icon: Globe, label: "Browser domains" },
} as const;

const KIND_ORDER = ["app", "path", "domain"] as const;

/**
 * Live view over the daemon permissions API. THOTH may only touch what is
 * granted here; revoking hits DELETE /api/permissions/grants/{id} and the
 * scope enforcer honors it immediately.
 */
export function Permissions() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["permissions"],
    queryFn: api.permissions,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.revokeGrant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          THOTH may only touch what is granted here. Revoking takes effect
          immediately.
        </p>
        <Badge variant="success">live</Badge>
      </div>

      {isLoading && <p className="text-xs text-muted">Loading permissions…</p>}
      {isError && (
        <p className="text-xs text-danger">Could not reach the daemon.</p>
      )}

      {data && data.workspaces.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center gap-2">
            <FolderOpen size={14} className="text-muted" />
            <CardTitle>Trusted workspaces</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul>
              {data.workspaces.map((w) => (
                <li
                  key={w.id}
                  className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0"
                >
                  <span className="font-mono text-xs text-ink">
                    {w.root_path || "(none)"}
                  </span>
                  {w.trusted && <Badge variant="success">trusted</Badge>}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {KIND_ORDER.map((kind) => {
        const items = (data?.grants ?? []).filter((g) => g.kind === kind);
        if (items.length === 0) return null;
        const { icon: Icon, label } = KIND_META[kind];
        return (
          <Card key={kind}>
            <CardHeader className="flex-row items-center gap-2">
              <Icon size={14} className="text-muted" />
              <CardTitle>{label}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ul>
                {items.map((g: Grant) => (
                  <li
                    key={g.id}
                    className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0"
                  >
                    <span className="font-mono text-xs text-ink">
                      {g.value}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={revoke.isPending}
                      onClick={() => revoke.mutate(g.id)}
                    >
                      Revoke
                    </Button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        );
      })}

      {data && data.grants.length === 0 && (
        <p className="text-xs text-muted">
          No grants yet. THOTH can only act inside the trusted workspaces above.
        </p>
      )}
    </div>
  );
}
