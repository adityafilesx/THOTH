"""LIVE local planner (Phase 5 slice 4).

Drives the REAL qwen3:4b model through OllamaPlanClient + LocalPlanner over
the actual tool catalog, proving the local model produces a plan that
passes the strict validator end-to-end. Skips when the model is not pulled.
"""

import json
import urllib.error
import urllib.request

import pytest

from thoth_daemon.core.local_plan_client import OllamaPlanClient
from thoth_daemon.core.local_planner import LocalPlanner
from thoth_daemon.schemas import ExecutionPlan
from thoth_daemon.tools.app_tools import register_app_tools
from thoth_daemon.tools.browser_tools import register_browser_tools
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.git_tools import register_git_tools
from thoth_daemon.tools.registry import ToolRegistry
from thoth_daemon.tools.shell_tool import register_shell_tool

ENDPOINT = "http://127.0.0.1:11434"
MODEL = "qwen3:4b"


def _model_available() -> bool:
    try:
        with urllib.request.urlopen(f"{ENDPOINT}/api/tags", timeout=3) as resp:
            tags = json.loads(resp.read().decode())
        return any(m.get("name", "").startswith(MODEL) for m in tags.get("models", []))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _model_available(), reason=f"{MODEL} not pulled")


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_fs_tools(reg)
    register_shell_tool(reg)
    register_git_tools(reg)
    register_app_tools(reg)
    register_browser_tools(reg)
    return reg


def test_live_local_planner_produces_valid_plan() -> None:
    planner = LocalPlanner(_registry(), OllamaPlanClient(model=MODEL, endpoint=ENDPOINT))
    plan = planner.plan("live-1", "Read the file at ~/notes.txt and show me its contents")
    assert isinstance(plan, ExecutionPlan)
    assert plan.steps
    # The validator already guaranteed every tool is real and no risk was
    # downgraded; just confirm it chose a filesystem read.
    assert any(s.tool_name.startswith("fs_") for s in plan.steps)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
