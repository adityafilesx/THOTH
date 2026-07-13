import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { api, type ApplicationProfile } from "@/lib/api";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function CapabilityGroup({
  title,
  values,
  variant,
}: {
  title: string;
  values: string[];
  variant: "success" | "amber" | "danger";
}) {
  return (
    <div>
      <p className="eyebrow mb-1.5">{title}</p>
      <div className="flex flex-wrap gap-1">
        {values.length === 0 ? (
          <span className="text-[11px] text-faint">None</span>
        ) : (
          values.map((value) => (
            <Badge key={value} variant={variant}>
              {label(value)}
            </Badge>
          ))
        )}
      </div>
    </div>
  );
}

function ApplicationCapabilities({ profile }: { profile: ApplicationProfile }) {
  return (
    <Card data-testid={`ax-app-${profile.bundle_id}`}>
      <CardHeader>
        <CardTitle>{profile.display_name}</CardTitle>
        <code className="font-mono text-[10px] text-faint">{profile.bundle_id}</code>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <CapabilityGroup
          title="Verified"
          values={profile.verified_capabilities}
          variant="success"
        />
        <CapabilityGroup
          title="Experimental"
          values={profile.experimental_capabilities}
          variant="amber"
        />
        <CapabilityGroup
          title="Forbidden"
          values={profile.forbidden_operations}
          variant="danger"
        />
      </CardContent>
    </Card>
  );
}

export function Accessibility() {
  const [developerDiagnostics, setDeveloperDiagnostics] = useState(false);
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["accessibility"],
    queryFn: api.accessibility,
    refetchInterval: 5000,
  });
  const openSettings = useMutation({
    mutationFn: api.openAccessibilitySettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["accessibility"] }),
  });

  if (status.isLoading) return <p className="text-xs text-muted">Loading Accessibility…</p>;
  if (status.isError || !status.data) {
    return <p className="text-xs text-danger">Accessibility status is unavailable.</p>;
  }

  const { permission, applications, diagnostics } = status.data;
  const permissionVariant = permission.status === "granted" ? "success" : "amber";
  const target =
    diagnostics.semantic_target?.identifier ??
    diagnostics.semantic_target?.semantic_alias ??
    diagnostics.semantic_target?.role ??
    "None";

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>Accessibility permission</CardTitle>
            <Badge variant={permissionVariant} data-testid="ax-permission-state">
              {label(permission.status)}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="flex items-start justify-between gap-4">
          <p className="max-w-2xl text-xs text-muted">{permission.detail}</p>
          {permission.status !== "granted" && (
            <Button
              variant="outline"
              onClick={() => openSettings.mutate()}
              disabled={openSettings.isPending}
            >
              Open Accessibility Settings
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current semantic operation</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="eyebrow">AX task</p>
            <p data-testid="ax-current-task" className="mt-1 font-mono text-ink">
              {diagnostics.current_task_id ?? "None"}
            </p>
          </div>
          <div>
            <p className="eyebrow">Tool</p>
            <p className="mt-1 font-mono text-ink">{diagnostics.current_tool ?? "None"}</p>
          </div>
          <div>
            <p className="eyebrow">Semantic target</p>
            <p data-testid="ax-semantic-target" className="mt-1 font-mono text-ink">
              {target}
            </p>
          </div>
          <div>
            <p className="eyebrow">Focus policy</p>
            <p data-testid="ax-focus-policy" className="mt-1 text-ink">
              {diagnostics.focus_policy ? label(diagnostics.focus_policy) : "None"}
            </p>
          </div>
          {diagnostics.permission_error && (
            <p className="text-danger sm:col-span-2" role="alert">
              {diagnostics.permission_error}
            </p>
          )}
          {diagnostics.clarification_required && (
            <p className="text-amber sm:col-span-2" data-testid="ax-clarification">
              Multiple semantic candidates require clarification. No action was taken.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>Developer diagnostics</CardTitle>
              <p className="mt-1 text-[11px] text-faint">
                Bounded semantic metadata only; raw AX trees and secure values are excluded.
              </p>
            </div>
            <Switch
              aria-label="Enable developer diagnostics"
              checked={developerDiagnostics}
              onCheckedChange={setDeveloperDiagnostics}
            />
          </div>
        </CardHeader>
        {developerDiagnostics && (
          <CardContent className="grid gap-3 text-xs sm:grid-cols-3">
            <div>
              <p className="eyebrow">Resolution</p>
              <p data-testid="ax-resolution" className="mt-1 text-ink">
                {diagnostics.resolution_method
                  ? `${label(diagnostics.resolution_method)} · ${Math.round(
                      (diagnostics.resolution_confidence ?? 0) * 100,
                    )}%`
                  : "No resolution evidence"}
              </p>
            </div>
            <div>
              <p className="eyebrow">Candidates</p>
              <p className="mt-1 text-ink">{diagnostics.candidate_count ?? "Unknown"}</p>
            </div>
            <div>
              <p className="eyebrow">Verification evidence</p>
              <p data-testid="ax-verification-evidence" className="mt-1 text-ink">
                {diagnostics.verification_evidence ?? "No verification evidence"}
              </p>
            </div>
          </CardContent>
        )}
      </Card>

      <section>
        <h2 className="mb-3 text-sm font-medium text-ink">Supported applications</h2>
        <div className="grid gap-3 lg:grid-cols-2">
          {applications.map((profile) => (
            <ApplicationCapabilities key={profile.bundle_id} profile={profile} />
          ))}
        </div>
      </section>
    </div>
  );
}
