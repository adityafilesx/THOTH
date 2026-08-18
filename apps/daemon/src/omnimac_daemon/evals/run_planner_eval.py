"""CLI: evaluate a planner and write a redacted report.

    uv run --project apps/daemon python -m omnimac_daemon.evals.run_planner_eval \
        --planner mock --out docs/evaluations

``--planner claude`` runs LIVE_CASES against the live ClaudePlanner over the
real tool catalog. Pending live verification: requires ANTHROPIC_API_KEY in
the environment (never logged, never stored, never placed in the report).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from omnimac_daemon.core.planner import DeterministicMockPlanner
from omnimac_daemon.evals.planner_eval import (
    LIVE_CASES,
    MOCK_CASES,
    render_report_markdown,
    run_planner_evals,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planner", choices=["mock", "claude"], default="mock")
    parser.add_argument("--out", type=Path, default=Path("docs/evaluations"))
    args = parser.parse_args(argv)

    if args.planner == "mock":
        report = run_planner_evals(DeterministicMockPlanner(), MOCK_CASES, planner_name="mock")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set. The live planner evaluation is pending live verification; set the key (never commit it) and rerun.",
                file=sys.stderr,
            )
            return 2
        from omnimac_daemon.core.claude_planner import AnthropicPlannerClient, ClaudePlanner
        from omnimac_daemon.tools.app_tools import register_app_tools
        from omnimac_daemon.tools.browser_tools import register_browser_tools
        from omnimac_daemon.tools.fs_tools import register_fs_tools
        from omnimac_daemon.tools.git_tools import register_git_tools
        from omnimac_daemon.tools.registry import ToolRegistry
        from omnimac_daemon.tools.shell_tool import register_shell_tool

        # The real tool catalog the planner may plan over (same set app.py wires).
        registry = ToolRegistry()
        register_fs_tools(registry)
        register_shell_tool(registry)
        register_git_tools(registry)
        register_app_tools(registry)
        register_browser_tools(registry)
        planner = ClaudePlanner(registry, AnthropicPlannerClient())
        report = run_planner_evals(planner, LIVE_CASES, planner_name="claude")

    path = write_report(report, args.out)
    print(render_report_markdown(report))
    print(f"report written: {path}")
    return 0 if report.pass_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
