import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

/**
 * Live view over GET/PATCH /api/skills. Lists whatever SkillDefinitions the
 * daemon actually has (none until the skill engine ships) and toggles their
 * enabled flag. Every skill run still passes risk review and approvals.
 */
export function Skills() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["skills"],
    queryFn: api.skills,
  });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.setSkillEnabled(id, enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          Skills are declarative workflows. Every run still passes risk review
          and approvals.
        </p>
        <Badge variant="success">live</Badge>
      </div>

      {isLoading && <p className="text-xs text-muted">Loading skills…</p>}
      {isError && (
        <p className="text-xs text-danger">Could not reach the daemon.</p>
      )}

      {data && data.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-xs text-muted">
              No skills installed. The skill engine arrives later in Phase 3 —
              every skill run will still pass risk review and approvals.
            </p>
          </CardContent>
        </Card>
      )}

      {data?.map((skill) => (
        <Card key={skill.id}>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="font-mono">{skill.name}</CardTitle>
            <Switch
              checked={skill.enabled}
              disabled={toggle.isPending}
              onCheckedChange={(enabled) =>
                toggle.mutate({ id: skill.id, enabled })
              }
              aria-label={`Enable ${skill.name}`}
            />
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-xs text-muted">{skill.description}</p>
            <div>
              <div className="eyebrow mb-1.5">workflow</div>
              <div className="flex flex-wrap items-center gap-1.5">
                {skill.workflow.map((tool, i) => (
                  <span key={tool} className="flex items-center gap-1.5">
                    {i > 0 && <span className="text-faint">→</span>}
                    <code className="rounded-sm border border-line bg-raised px-1.5 py-0.5 font-mono text-[11px] text-muted">
                      {tool}
                    </code>
                  </span>
                ))}
              </div>
            </div>
            {skill.inputs.length > 0 && (
              <div>
                <div className="eyebrow mb-1.5">inputs</div>
                <p className="font-mono text-xs text-ink">
                  {skill.inputs.join(", ")}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
