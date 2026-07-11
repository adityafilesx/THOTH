"""Risk & policy engine.

Runs independently of model recommendations: the only inputs are typed
values (enums, bools, a tool name for reporting). Free text — model prose,
web content, tool output — has no path into a decision.

Rules, in order:
  1. Unknown tool -> deny.
  2. effective_risk = max(tool default, declared step risk). Risk NEVER
     downgrades; there is deliberately no code path that lowers it.
  3. R3 -> deny (blocked by default in this product).
  4. R2 -> allowed, requires explicit approval immediately before execution.
  5. R1 -> allowed; requires approval unless the workspace is trusted.
  6. R0 -> allowed automatically inside approved boundaries.
"""

from thoth_daemon.schemas import PolicyDecision, RiskLevel


class PolicyEngine:
    def evaluate(
        self,
        tool_name: str,
        declared_risk: RiskLevel,
        tool_default_risk: RiskLevel | None,
        workspace_trusted: bool,
    ) -> PolicyDecision:
        if tool_default_risk is None:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                effective_risk=declared_risk,
                reasons=[f"unknown tool '{tool_name}' is not registered"],
            )

        effective = max(declared_risk, tool_default_risk)
        reasons: list[str] = []
        if effective is not declared_risk:
            reasons.append(
                f"declared risk {declared_risk.value} raised to tool default "
                f"{tool_default_risk.value} (no downgrade)"
            )

        if effective is RiskLevel.R3:
            reasons.append("R3 (destructive/highly sensitive) is blocked by default")
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                effective_risk=effective,
                reasons=reasons,
            )

        if effective is RiskLevel.R2:
            reasons.append("R2 external side effect requires explicit approval")
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                effective_risk=effective,
                reasons=reasons,
            )

        if effective is RiskLevel.R1:
            if workspace_trusted:
                reasons.append("R1 reversible local action in trusted workspace")
                return PolicyDecision(
                    allowed=True,
                    requires_approval=False,
                    effective_risk=effective,
                    reasons=reasons,
                )
            reasons.append("R1 outside a trusted workspace requires approval")
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                effective_risk=effective,
                reasons=reasons,
            )

        reasons.append("R0 read-only action inside approved boundaries")
        return PolicyDecision(
            allowed=True,
            requires_approval=False,
            effective_risk=effective,
            reasons=reasons,
        )
