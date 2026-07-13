"""Independent verification framework (Phase 4 slice 7).

Each verifier probes REAL world state through the tool result's claimed
postcondition, never trusting ``result.ok`` alone. A tool that reports
success but left the world in the wrong state must fail verification. A
probe whose capability is not wired (Accessibility without TCC, browser
without Playwright) reports ``available=False`` — never a silent pass.
"""

import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from thoth_daemon.core.verifiers import (
    BrowserStateProbe,
    VerifierContext,
    evaluate_check,
)
from thoth_daemon.schemas import ToolResult, VerificationCheck, VerifierKind


def _ok(output: dict | None = None) -> ToolResult:
    return ToolResult(invocation_id="inv-1", ok=True, output=output)


def check(kind: VerifierKind, **params) -> VerificationCheck:
    return VerificationCheck(kind=kind, params=params)


# ---------------------------------------------------------------- filesystem


def test_file_exists_passes_when_present(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hi")
    ctx = VerifierContext(path_exists=lambda p: Path(p).exists())
    out = evaluate_check(check(VerifierKind.FILE_EXISTS, path=str(f)), ctx, _ok())
    assert out.passed and out.available


def test_file_exists_fails_when_absent(tmp_path: Path) -> None:
    ctx = VerifierContext(path_exists=lambda p: Path(p).exists())
    out = evaluate_check(check(VerifierKind.FILE_EXISTS, path=str(tmp_path / "nope")), ctx, _ok())
    assert not out.passed


def test_file_exists_should_not_exist(tmp_path: Path) -> None:
    ctx = VerifierContext(path_exists=lambda p: Path(p).exists())
    out = evaluate_check(
        check(VerifierKind.FILE_EXISTS, path=str(tmp_path / "gone"), should_exist=False),
        ctx,
        _ok(),
    )
    assert out.passed


def test_file_content_contains(tmp_path: Path) -> None:
    f = tmp_path / "log.txt"
    f.write_text("build succeeded\n")
    ctx = VerifierContext(read_text=lambda p: Path(p).read_text())
    ok = evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(f), contains="succeeded"), ctx, _ok()
    )
    bad = evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(f), contains="FAILED"), ctx, _ok()
    )
    assert ok.passed and not bad.passed


def test_file_content_regex_and_equals(tmp_path: Path) -> None:
    f = tmp_path / "v.txt"
    f.write_text("v1.2.3")
    ctx = VerifierContext(read_text=lambda p: Path(p).read_text())
    assert evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(f), regex=r"v\d+\.\d+\.\d+"), ctx, _ok()
    ).passed
    assert evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(f), equals="v1.2.3"), ctx, _ok()
    ).passed
    assert not evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(f), equals="other"), ctx, _ok()
    ).passed


def test_file_content_missing_file_fails(tmp_path: Path) -> None:
    def _read(p: str) -> str:
        return Path(p).read_text()

    ctx = VerifierContext(read_text=_read)
    out = evaluate_check(
        check(VerifierKind.FILE_CONTENT, path=str(tmp_path / "x"), contains="a"), ctx, _ok()
    )
    assert not out.passed


# ------------------------------------------------------------------- process


def test_process_running(monkeypatch) -> None:
    ctx = VerifierContext(process_running=lambda pat: pat == "vite")
    assert evaluate_check(check(VerifierKind.PROCESS_RUNNING, pattern="vite"), ctx, _ok()).passed
    assert not evaluate_check(
        check(VerifierKind.PROCESS_RUNNING, pattern="ghost"), ctx, _ok()
    ).passed


def test_process_should_not_run() -> None:
    ctx = VerifierContext(process_running=lambda pat: False)
    out = evaluate_check(
        check(VerifierKind.PROCESS_RUNNING, pattern="daemon", should_run=False), ctx, _ok()
    )
    assert out.passed


# ---------------------------------------------------------------------- port


def test_port_listening_real_socket() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        ctx = VerifierContext.with_real_probes()
        assert evaluate_check(check(VerifierKind.PORT_LISTENING, port=port), ctx, _ok()).passed
    finally:
        srv.close()
    # After close, nothing listens.
    ctx2 = VerifierContext.with_real_probes()
    assert not evaluate_check(check(VerifierKind.PORT_LISTENING, port=port), ctx2, _ok()).passed


# ---------------------------------------------------------------------- http


def test_http_health_real_server() -> None:
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"THOTH-OK")

        def log_message(self, *a):  # silence
            pass

    httpd = HTTPServer(("127.0.0.1", 0), H)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        ctx = VerifierContext.with_real_probes()
        url = f"http://127.0.0.1:{port}/health"
        assert evaluate_check(check(VerifierKind.HTTP_HEALTH, url=url), ctx, _ok()).passed
        assert evaluate_check(
            check(VerifierKind.HTTP_HEALTH, url=url, contains="THOTH-OK"), ctx, _ok()
        ).passed
        assert not evaluate_check(
            check(VerifierKind.HTTP_HEALTH, url=url, expect_status=500), ctx, _ok()
        ).passed
    finally:
        httpd.shutdown()


# ----------------------------------------------------------------------- git


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_git_state_real_repo(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    ctx = VerifierContext.with_real_probes()
    assert evaluate_check(
        check(VerifierKind.GIT_STATE, repo=str(repo), branch="main", clean=True), ctx, _ok()
    ).passed
    # Dirty the tree.
    (repo / "a.txt").write_text("y")
    assert not evaluate_check(
        check(VerifierKind.GIT_STATE, repo=str(repo), clean=True), ctx, _ok()
    ).passed
    assert evaluate_check(
        check(VerifierKind.GIT_STATE, repo=str(repo), clean=False), ctx, _ok()
    ).passed


# ------------------------------------------------------------- application/ax


def test_application_running_probe() -> None:
    ctx = VerifierContext(application_running=lambda n: n == "Safari")
    assert evaluate_check(check(VerifierKind.APPLICATION_RUNNING, name="Safari"), ctx, _ok()).passed
    assert not evaluate_check(
        check(VerifierKind.APPLICATION_RUNNING, name="Xcode"), ctx, _ok()
    ).passed


def test_accessibility_value_probe() -> None:
    ctx = VerifierContext(ax_value=lambda app, sel: "Submitted" if sel == "#status" else None)
    assert evaluate_check(
        check(VerifierKind.ACCESSIBILITY_VALUE, app="App", selector="#status", equals="Submitted"),
        ctx,
        _ok(),
    ).passed
    assert evaluate_check(
        check(VerifierKind.ACCESSIBILITY_VALUE, app="App", selector="#status", contains="ubmit"),
        ctx,
        _ok(),
    ).passed


def test_accessibility_unavailable_is_not_a_pass() -> None:
    ctx = VerifierContext()  # no ax_value wired (no TCC)
    out = evaluate_check(
        check(VerifierKind.ACCESSIBILITY_VALUE, app="App", selector="#s", equals="x"), ctx, _ok()
    )
    assert not out.passed
    assert not out.available


# -------------------------------------------------------------------- browser


def test_browser_url_and_element() -> None:
    probe = BrowserStateProbe(
        url="https://example.com/thanks", present_selectors=frozenset({"#confirmation"})
    )
    ctx = VerifierContext(browser_probe=lambda: probe)
    assert evaluate_check(check(VerifierKind.BROWSER_URL, contains="/thanks"), ctx, _ok()).passed
    assert evaluate_check(
        check(VerifierKind.BROWSER_URL, prefix="https://example.com"), ctx, _ok()
    ).passed
    assert evaluate_check(
        check(VerifierKind.BROWSER_ELEMENT, selector="#confirmation"), ctx, _ok()
    ).passed
    assert not evaluate_check(
        check(VerifierKind.BROWSER_ELEMENT, selector="#error"), ctx, _ok()
    ).passed


def test_browser_unavailable_is_not_a_pass() -> None:
    ctx = VerifierContext()
    out = evaluate_check(check(VerifierKind.BROWSER_URL, contains="x"), ctx, _ok())
    assert not out.passed and not out.available


# ------------------------------------------------------------------ exit code


def test_exit_code_reads_tool_output() -> None:
    ctx = VerifierContext()
    assert evaluate_check(
        check(VerifierKind.EXIT_CODE, expected=0), ctx, _ok(output={"exit_code": 0})
    ).passed
    assert not evaluate_check(
        check(VerifierKind.EXIT_CODE, expected=0), ctx, _ok(output={"exit_code": 1})
    ).passed


# ------------------------------------------------------------------- composite


def test_composite_all_and_any(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("done")
    ctx = VerifierContext(
        path_exists=lambda p: Path(p).exists(), read_text=lambda p: Path(p).read_text()
    )
    exists = check(VerifierKind.FILE_EXISTS, path=str(f))
    wrong = check(VerifierKind.FILE_CONTENT, path=str(f), contains="nope")
    all_check = VerificationCheck(
        kind=VerifierKind.COMPOSITE, require="all", children=[exists, wrong]
    )
    any_check = VerificationCheck(
        kind=VerifierKind.COMPOSITE, require="any", children=[exists, wrong]
    )
    assert not evaluate_check(all_check, ctx, _ok()).passed
    assert evaluate_check(any_check, ctx, _ok()).passed


# ----------------------------------------------- fail-closed hardening (review)


def test_run_checks_composite_any_with_unwired_child_fails(tmp_path: Path) -> None:
    """A COMPOSITE(any) containing an un-wired probe must NOT verify, even
    if a sibling child passes: available=False can never be part of a
    verified success (fail-closed)."""
    from thoth_daemon.core.verification import VerificationEngine
    from thoth_daemon.schemas import PlanStep, RiskLevel

    f = tmp_path / "present.txt"
    f.write_text("here")
    composite = VerificationCheck(
        kind=VerifierKind.COMPOSITE,
        require="any",
        children=[
            check(VerifierKind.BROWSER_URL, contains="/thanks"),  # un-wired
            check(VerifierKind.FILE_EXISTS, path=str(f)),  # passes
        ],
    )
    step = PlanStep(
        index=0,
        title="s",
        tool_name="t",
        declared_risk=RiskLevel.R1,
        verification_checks=[composite],
    )
    ctx = VerifierContext(path_exists=lambda p: Path(p).exists())  # no browser probe
    engine = VerificationEngine(context=ctx)
    res = engine.run_checks(step, _ok(), step.verification_checks)
    assert not res.passed
    assert "not wired" in res.detail


def test_exit_code_without_explicit_code_is_unavailable() -> None:
    """EXIT_CODE may never fall back to the tool's own ok flag — that would
    let a tool self-certify. No explicit exit_code => unavailable."""
    ctx = VerifierContext()
    for output in (None, {}, {"stdout": "done"}):
        out = evaluate_check(check(VerifierKind.EXIT_CODE, expected=0), ctx, _ok(output=output))
        assert not out.passed
        assert not out.available


def test_malformed_params_fail_closed() -> None:
    """Bad param values (non-numeric port, invalid regex) must fail closed
    with a detail, never raise into the orchestrator loop."""
    ctx = VerifierContext.with_real_probes()
    bad_port = evaluate_check(check(VerifierKind.PORT_LISTENING, port="not-a-port"), ctx, _ok())
    assert not bad_port.passed
    assert "malformed" in bad_port.detail

    bad_regex = evaluate_check(
        check(VerifierKind.FILE_CONTENT, path="/etc/hosts", regex="["), ctx, _ok()
    )
    assert not bad_regex.passed
    assert "malformed" in bad_regex.detail


def test_engine_verify_step_enforces_baseline_minimum(tmp_path: Path) -> None:
    """Declared checks AUGMENT the tool's own verification strategy — they
    never replace it. The baseline is the system-enforced minimum."""
    from thoth_daemon.core.verification import VerificationEngine
    from thoth_daemon.schemas import PlanStep, RiskLevel, VerificationStrategy

    f = tmp_path / "present.txt"
    f.write_text("here")
    step = PlanStep(
        index=0,
        title="s",
        tool_name="t",
        declared_risk=RiskLevel.R1,
        verification_checks=[check(VerifierKind.FILE_EXISTS, path=str(f))],
    )
    engine = VerificationEngine(context=VerifierContext.with_real_probes())

    # Check passes, but the tool's OUTPUT_ASSERTION baseline fails (no output)
    # => overall verification must fail.
    no_output = ToolResult(invocation_id="i", ok=True, output=None)
    res = engine.verify_step(step, no_output, VerificationStrategy.OUTPUT_ASSERTION)
    assert not res.passed

    # Baseline passes AND the check passes => verified.
    with_output = ToolResult(invocation_id="i", ok=True, output={"content": "x"})
    res2 = engine.verify_step(step, with_output, VerificationStrategy.OUTPUT_ASSERTION)
    assert res2.passed


# ----------------------------------------------------------- engine integration


def test_engine_run_checks_gates_on_tool_failure() -> None:
    from thoth_daemon.core.verification import VerificationEngine
    from thoth_daemon.schemas import PlanStep, RiskLevel

    step = PlanStep(
        index=0,
        title="s",
        tool_name="t",
        declared_risk=RiskLevel.R0,
        verification_checks=[check(VerifierKind.EXIT_CODE, expected=0)],
    )
    failed = ToolResult(invocation_id="i", ok=False, error="boom")
    engine = VerificationEngine()
    res = engine.run_checks(step, failed, step.verification_checks)
    assert not res.passed
    assert "boom" in res.detail


def test_engine_run_checks_independent_pass(tmp_path: Path) -> None:
    from thoth_daemon.core.verification import VerificationEngine
    from thoth_daemon.schemas import PlanStep, RiskLevel

    f = tmp_path / "out.txt"
    f.write_text("ok")
    step = PlanStep(
        index=0,
        title="write file",
        tool_name="fs.write_file",
        declared_risk=RiskLevel.R1,
        verification_checks=[check(VerifierKind.FILE_EXISTS, path=str(f))],
    )
    engine = VerificationEngine(context=VerifierContext.with_real_probes())
    res = engine.run_checks(step, _ok(), step.verification_checks)
    assert res.passed


def test_engine_run_checks_fails_when_probe_false(tmp_path: Path) -> None:
    """Tool reports ok, but the independent probe says the file is absent —
    verification must fail. 'Exited 0' is never sufficient."""
    from thoth_daemon.core.verification import VerificationEngine
    from thoth_daemon.schemas import PlanStep, RiskLevel

    step = PlanStep(
        index=0,
        title="write file",
        tool_name="fs.write_file",
        declared_risk=RiskLevel.R1,
        verification_checks=[check(VerifierKind.FILE_EXISTS, path=str(tmp_path / "missing"))],
    )
    engine = VerificationEngine(context=VerifierContext.with_real_probes())
    res = engine.run_checks(step, _ok(), step.verification_checks)
    assert not res.passed


def test_unknown_git_probe_absent_reports_unavailable() -> None:
    ctx = VerifierContext()  # git_probe None
    out = evaluate_check(check(VerifierKind.GIT_STATE, repo="/x", clean=True), ctx, _ok())
    assert not out.passed and not out.available


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
