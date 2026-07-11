import type { RiskLevel } from "@thoth/shared-schemas";

import { cn } from "@/lib/utils";

/**
 * Risk chips use a fixed color ramp — green/cyan/amber/red — so risk reads
 * at a glance everywhere in the product. Never restyle per-view.
 */
const STYLES: Record<RiskLevel, string> = {
  R0: "border-r0/40 bg-r0/10 text-r0",
  R1: "border-r1/40 bg-r1/10 text-r1",
  R2: "border-r2/40 bg-r2/10 text-r2",
  R3: "border-r3/40 bg-r3/10 text-r3",
};

const LABELS: Record<RiskLevel, string> = {
  R0: "R0 read",
  R1: "R1 local",
  R2: "R2 external",
  R3: "R3 blocked",
};

export function RiskBadge({ risk, compact = false }: { risk: RiskLevel; compact?: boolean }) {
  return (
    <span
      data-testid={`risk-${risk}`}
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        STYLES[risk],
      )}
    >
      {compact ? risk : LABELS[risk]}
    </span>
  );
}
