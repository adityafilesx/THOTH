import { AppWindow, FolderOpen, Globe } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * MOCK view — grants are static fixtures until the daemon exposes a
 * permissions API (Phase 3). Revoke buttons are disabled placeholders.
 */
const MOCK_GRANTS = [
  {
    icon: AppWindow,
    kind: "Applications",
    items: ["Visual Studio Code", "Terminal", "Safari"],
  },
  {
    icon: FolderOpen,
    kind: "Workspace directories",
    items: ["~/projects/thoth"],
  },
  {
    icon: Globe,
    kind: "Browser domains",
    items: ["docs.python.org", "developer.apple.com"],
  },
];

export function Permissions() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          THOTH may only touch what is granted here. Revoking takes effect immediately.
        </p>
        <Badge variant="amber">mock data</Badge>
      </div>
      {MOCK_GRANTS.map(({ icon: Icon, kind, items }) => (
        <Card key={kind}>
          <CardHeader className="flex-row items-center gap-2">
            <Icon size={14} className="text-muted" />
            <CardTitle>{kind}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul>
              {items.map((item) => (
                <li
                  key={item}
                  className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0"
                >
                  <span className="font-mono text-xs text-ink">{item}</span>
                  <Button variant="ghost" size="sm" disabled title="Wired in Phase 3">
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
