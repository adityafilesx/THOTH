import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

/**
 * MOCK view — the skill engine ships in Phase 3. These fixtures preview the
 * layout: installed skills, their workflow, inputs, and an enable toggle.
 */
const MOCK_SKILLS = [
  {
    name: "continue-project",
    description: "Restore a project workspace, inspect git state, start dev services.",
    workflow: ["mock_read_file", "mock_open_app", "mock_list_dir"],
    inputs: ["project directory"],
    enabled: true,
  },
  {
    name: "research-report",
    description: "Research a topic on approved domains and save a cited Markdown report.",
    workflow: ["mock_read_file", "mock_edit_file"],
    inputs: ["topic", "output path"],
    enabled: true,
  },
  {
    name: "daily-plan",
    description: "Draft a daily plan from configured calendars and notes.",
    workflow: ["mock_read_file", "mock_edit_file"],
    inputs: ["sources"],
    enabled: false,
  },
];

export function Skills() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          Skills are declarative workflows. Every run still passes risk review and approvals.
        </p>
        <Badge variant="amber">mock data</Badge>
      </div>
      {MOCK_SKILLS.map((skill) => (
        <Card key={skill.name}>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="font-mono">{skill.name}</CardTitle>
            <Switch defaultChecked={skill.enabled} aria-label={`Enable ${skill.name}`} />
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
            <div>
              <div className="eyebrow mb-1.5">inputs</div>
              <p className="font-mono text-xs text-ink">{skill.inputs.join(", ")}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
