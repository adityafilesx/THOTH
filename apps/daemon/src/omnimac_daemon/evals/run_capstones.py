"""CLI: run the five capstone workflows and write docs/CAPSTONE_REPORT.md.

    uv run --project apps/daemon python -m omnimac_daemon.evals.run_capstones \
        --planner scripted --out docs/CAPSTONE_REPORT.md

``--planner scripted`` proves the full pipeline downstream of planning
against the REAL OS. ``--planner claude`` additionally exercises live
natural-language planning — pending live verification (ANTHROPIC_API_KEY).
``--skip`` names capstones to leave out (e.g. launch-app on a headless
machine, research-and-save without network).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import tempfile
from pathlib import Path

from omnimac_daemon.evals.capstones import (
    CAPSTONES,
    CapstoneResult,
    render_capstone_report,
    run_capstone,
)


def _setup_workspace(root: Path) -> Path:
    """A real git repo with a committed README — the world the capstones act on."""
    ws = root / "capstone-ws"
    ws.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "capstone@omnimac.local")
    git("config", "user.name", "omnimac-capstone")
    (ws / "README.md").write_text("# Capstone workspace\n")
    git("add", "-A")
    git("commit", "-m", "capstone fixture")
    return ws


async def _run_all(planner: str, skip: set[str]) -> list[CapstoneResult]:
    results: list[CapstoneResult] = []
    with tempfile.TemporaryDirectory(prefix="omnimac-capstones-") as tmp:
        root = Path(tmp)
        for capstone in CAPSTONES:
            if capstone.name in skip:
                results.append(
                    CapstoneResult(
                        capstone=capstone.name,
                        planner=planner,
                        task_state="SKIPPED",
                        approvals_granted=0,
                        check_results=[],
                        final_state_verified=False,
                        detail=f"skipped by operator ({capstone.needs or 'no reason given'})",
                    )
                )
                continue
            ws = _setup_workspace(root / capstone.name)
            result = await run_capstone(capstone, workspace=ws, planner=planner)  # type: ignore[arg-type]
            results.append(result)
            print(
                f"{capstone.name}: {result.task_state} (approvals={result.approvals_granted}, verified={result.final_state_verified}) {result.detail}"
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planner", choices=["scripted", "claude"], default="scripted")
    parser.add_argument("--out", type=Path, default=Path("docs/CAPSTONE_REPORT.md"))
    parser.add_argument("--skip", nargs="*", default=[])
    args = parser.parse_args(argv)

    results = asyncio.run(_run_all(args.planner, set(args.skip)))
    report = render_capstone_report(results, planner=args.planner)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"\nreport written: {args.out}")
    ran = [r for r in results if r.task_state != "SKIPPED"]
    return 0 if ran and all(r.final_state_verified for r in ran) else 1


if __name__ == "__main__":
    raise SystemExit(main())
