"""Export JSON Schemas for all contracts to packages/shared-schemas.

Usage: python -m thoth_daemon.schemas.export <output-dir>   (see `make schemas`)
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from thoth_daemon import schemas

CONTRACTS: list[type[BaseModel]] = [
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
