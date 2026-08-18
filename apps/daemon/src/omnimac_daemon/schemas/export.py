"""Export JSON Schemas for all contracts to packages/shared-schemas.

Usage: python -m omnimac_daemon.schemas.export <output-dir>   (see `make schemas`)
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from omnimac_daemon import schemas

CONTRACTS: list[type[BaseModel]] = [
    schemas.AXApplicationSnapshot,
    schemas.AXWindowSnapshot,
    schemas.AXElementSnapshot,
    schemas.AXElementQuery,
    schemas.AXElementReference,
    schemas.AXActionRequest,
    schemas.AXActionResult,
    schemas.AXVerificationRequest,
    schemas.AXVerificationResult,
    schemas.AXPermissionState,
    schemas.Task,
    schemas.ExecutionPlan,
    schemas.PlanStep,
    schemas.ToolInvocation,
    schemas.ToolResult,
    schemas.VerificationResult,
    schemas.ApprovalRequest,
    schemas.ApprovalDecision,
    schemas.AuditEvent,
    schemas.PolicyDecision,
    schemas.RecoveryDecision,
    schemas.SkillDefinition,
    schemas.WorkspaceProfile,
    schemas.PermissionGrant,
    schemas.TaggedContent,
    schemas.ResourceScope,
]


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in CONTRACTS:
        path = out_dir / f"{model.__name__}.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../packages/shared-schemas/schemas")
    files = export(target)
    print(f"wrote {len(files)} schemas to {target}")
