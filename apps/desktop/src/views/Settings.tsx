import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

/**
 * MOCK view — settings persistence lands with the daemon settings API
 * (Phase 3). Values shown are the daemon defaults.
 */
export function Settings() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">Daemon defaults shown; editing is wired in Phase 3.</p>
        <Badge variant="amber">mock data</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <label className="flex items-center justify-between gap-4 text-xs text-muted">
            Planner
            <Input readOnly value="mock (deterministic)" className="w-64 font-mono text-xs" />
          </label>
          <p className="text-[11px] text-faint">
            The claude-agent-sdk planner activates in Phase 3. The mock planner never leaves this
            machine.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Voice</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <label className="flex items-center justify-between text-xs text-muted">
            Push-to-talk (Phase 3)
            <Switch disabled aria-label="Push-to-talk" />
          </label>
          <p className="text-[11px] text-faint">
            No always-on listening, ever. Audio is transcribed locally and discarded.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Privacy & retention</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <label className="flex items-center justify-between gap-4 text-xs text-muted">
            Keep task history (days)
            <Input readOnly value="90" className="w-24 text-right font-mono text-xs" />
          </label>
          <label className="flex items-center justify-between gap-4 text-xs text-muted">
            Keep diagnostic logs (days)
            <Input readOnly value="14" className="w-24 text-right font-mono text-xs" />
          </label>
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
          <code className="rounded-md border border-line bg-raised px-3 py-2 font-mono text-xs text-ink">
            ~/projects/thoth
          </code>
        </CardContent>
      </Card>
    </div>
  );
}
