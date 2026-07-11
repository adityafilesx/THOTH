import {
  Activity,
  ListChecks,
  Settings2,
  Shield,
  Terminal,
  Wand2,
} from "lucide-react";
import type { ReactNode } from "react";

import { StopButton } from "@/components/StopButton";
import { cn } from "@/lib/utils";
import { useConnectionStore } from "@/stores/connection";
import { useUiStore, type View } from "@/stores/ui";

const NAV: { view: View; label: string; icon: typeof Terminal }[] = [
  { view: "command", label: "Command", icon: Terminal },
  { view: "plan", label: "Plan", icon: ListChecks },
  { view: "timeline", label: "Timeline", icon: Activity },
  { view: "permissions", label: "Permissions", icon: Shield },
  { view: "skills", label: "Skills", icon: Wand2 },
  { view: "settings", label: "Settings", icon: Settings2 },
];

const STATUS_STYLE: Record<string, string> = {
  connected: "text-success",
  connecting: "text-amber",
  disconnected: "text-danger",
};

export function Layout({ children }: { children: ReactNode }) {
  const { view, setView } = useUiStore();
  const status = useConnectionStore((s) => s.status);
  const version = useConnectionStore((s) => s.daemonVersion);

  return (
    <div className="flex h-full">
      <nav className="flex w-44 shrink-0 flex-col border-r border-line bg-surface">
        <div className="border-b border-line px-4 py-4">
          <div className="font-mono text-sm font-semibold tracking-[0.3em] text-ink">THOTH</div>
          <div className="eyebrow mt-1">computer operator</div>
        </div>
        <ul className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV.map(({ view: v, label, icon: Icon }) => (
            <li key={v}>
              <button
                type="button"
                onClick={() => setView(v)}
                aria-current={view === v ? "page" : undefined}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-xs transition-colors",
                  view === v
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:bg-raised hover:text-ink",
                )}
              >
                <Icon size={14} />
                {label}
              </button>
            </li>
          ))}
        </ul>
        <div className="border-t border-line p-3">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
            <span
              className={cn("h-1.5 w-1.5 rounded-full bg-current", STATUS_STYLE[status])}
              aria-hidden
            />
            <span className={STATUS_STYLE[status]} data-testid="connection-status">
              {status}
            </span>
          </div>
          {version && <div className="mt-1 font-mono text-[10px] text-faint">daemon v{version}</div>}
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-line bg-surface px-4">
          <span className="eyebrow">{NAV.find((n) => n.view === view)?.label}</span>
          <StopButton />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-4">{children}</main>
      </div>
    </div>
  );
}
