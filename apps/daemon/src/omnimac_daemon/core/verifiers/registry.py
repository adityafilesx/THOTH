"""The twelve independent verifiers and the dispatcher.

Each verifier takes a declared ``VerificationCheck``, the injected
``VerifierContext``, and the ``ToolResult`` (for probes like EXIT_CODE that
read the tool's own output), and returns a ``VerifierOutcome``. A verifier
NEVER trusts ``result.ok``; it confirms the declared postcondition against
real state. Missing probes yield ``available=False`` (a failure, not a
pass). Unknown params are ignored defensively — a malformed check fails
closed rather than raising into the orchestrator loop.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from omnimac_daemon.core.verifiers.context import VerifierContext, VerifierOutcome
from omnimac_daemon.schemas import ToolResult, VerificationCheck, VerifierKind

Verifier = Callable[[VerificationCheck, VerifierContext, ToolResult], VerifierOutcome]

_UNAVAILABLE = "probe not wired in this environment (pending live verification)"


def _unavailable(cap: str) -> VerifierOutcome:
    return VerifierOutcome(passed=False, detail=f"{cap}: {_UNAVAILABLE}", available=False)


def _match_text(value: str, params: dict[str, Any]) -> tuple[bool, str]:
    """Apply the equals/contains/regex/prefix matchers present in params.
    All present matchers must hold. No matchers => existence-only pass."""
    checks: list[tuple[bool, str]] = []
    if "equals" in params:
        checks.append((value == params["equals"], f"equals {params['equals']!r}"))
    if "contains" in params:
        checks.append((params["contains"] in value, f"contains {params['contains']!r}"))
    if "prefix" in params:
        checks.append((value.startswith(params["prefix"]), f"prefix {params['prefix']!r}"))
    if "regex" in params:
        checks.append((re.search(params["regex"], value) is not None, f"regex {params['regex']!r}"))
    if not checks:
        return True, "value present"
    ok = all(c[0] for c in checks)
    failed = [desc for passed, desc in checks if not passed]
    detail = "all matchers satisfied" if ok else "unmet: " + ", ".join(failed)
    return ok, detail


# --------------------------------------------------------------------- probes


def _file_exists(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.path_exists is None:
        return _unavailable("file_exists")
    path = check.params["path"]
    should = check.params.get("should_exist", True)
    exists = ctx.path_exists(path)
    passed = exists is should
    return VerifierOutcome(passed=passed, detail=f"{path} exists={exists} (want {should})")


def _file_content(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.read_text is None:
        return _unavailable("file_content")
    path = check.params["path"]
    try:
        text = ctx.read_text(path)
    except (FileNotFoundError, OSError) as exc:
        return VerifierOutcome(passed=False, detail=f"{path}: unreadable ({exc.__class__.__name__})")
    ok, detail = _match_text(text, check.params)
    return VerifierOutcome(passed=ok, detail=f"{path}: {detail}")


def _process_running(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.process_running is None:
        return _unavailable("process_running")
    pattern = check.params["pattern"]
    should = check.params.get("should_run", True)
    running = ctx.process_running(pattern)
    return VerifierOutcome(passed=running is should, detail=f"process {pattern!r} running={running}")


def _port_listening(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.tcp_listening is None:
        return _unavailable("port_listening")
    host = check.params.get("host", "127.0.0.1")
    port = int(check.params["port"])
    should = check.params.get("should_listen", True)
    timeout = float(check.params.get("timeout_s", 2.0))
    listening = ctx.tcp_listening(host, port, timeout)
    return VerifierOutcome(passed=listening is should, detail=f"{host}:{port} listening={listening}")


def _http_health(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.http_get is None:
        return _unavailable("http_health")
    url = check.params["url"]
    expect = int(check.params.get("expect_status", 200))
    timeout = float(check.params.get("timeout_s", 5.0))
    try:
        status, body = ctx.http_get(url, timeout)
    except OSError as exc:
        return VerifierOutcome(passed=False, detail=f"{url}: request failed ({exc})")
    if status != expect:
        return VerifierOutcome(passed=False, detail=f"{url}: status {status} (want {expect})")
    if "contains" in check.params and check.params["contains"] not in body:
        return VerifierOutcome(passed=False, detail=f"{url}: body missing {check.params['contains']!r}")
    return VerifierOutcome(passed=True, detail=f"{url}: {status} ok")


def _git_state(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.git_probe is None:
        return _unavailable("git_state")
    repo = check.params["repo"]
    try:
        state = ctx.git_probe(repo)
    except Exception as exc:  # a non-repo path is a verification failure, not a crash
        return VerifierOutcome(passed=False, detail=f"{repo}: git probe failed ({exc})")
    failures: list[str] = []
    if "branch" in check.params and state.branch != check.params["branch"]:
        failures.append(f"branch {state.branch} (want {check.params['branch']})")
    if "clean" in check.params and state.clean is not bool(check.params["clean"]):
        failures.append(f"clean={state.clean} (want {check.params['clean']})")
    if "head" in check.params and not state.head.startswith(check.params["head"]):
        failures.append(f"head {state.head[:8]} (want {check.params['head']})")
    if failures:
        return VerifierOutcome(passed=False, detail=f"{repo}: " + "; ".join(failures))
    return VerifierOutcome(passed=True, detail=f"{repo}: {state.branch} clean={state.clean}")


def _application_running(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.application_running is None:
        return _unavailable("application_running")
    name = check.params["name"]
    should = check.params.get("should_run", True)
    running = ctx.application_running(name)
    return VerifierOutcome(passed=running is should, detail=f"app {name!r} running={running}")


def _accessibility_value(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.ax_value is None:
        return _unavailable("accessibility_value")
    app = check.params["app"]
    selector = check.params["selector"]
    value = ctx.ax_value(app, selector)
    if value is None:
        return VerifierOutcome(passed=False, detail=f"{app} {selector}: element/value not found")
    ok, detail = _match_text(value, check.params)
    return VerifierOutcome(passed=ok, detail=f"{app} {selector}={value!r}: {detail}")


def _browser_url(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.browser_probe is None:
        return _unavailable("browser_url")
    state = ctx.browser_probe()
    ok, detail = _match_text(state.url, check.params)
    return VerifierOutcome(passed=ok, detail=f"url {state.url}: {detail}")


def _browser_element(check: VerificationCheck, ctx: VerifierContext, _r: ToolResult) -> VerifierOutcome:
    if ctx.browser_probe is None:
        return _unavailable("browser_element")
    selector = check.params["selector"]
    present_want = check.params.get("present", True)
    state = ctx.browser_probe()
    present = selector in state.present_selectors
    return VerifierOutcome(passed=present is present_want, detail=f"element {selector} present={present}")


def _exit_code(check: VerificationCheck, _ctx: VerifierContext, result: ToolResult) -> VerifierOutcome:
    expected = int(check.params.get("expected", 0))
    output = result.output or {}
    actual = output.get("exit_code")
    if actual is None:
        # NEVER fall back to result.ok — that would let a tool self-certify.
        # A result carrying no explicit exit_code cannot be independently
        # verified by this probe.
        return VerifierOutcome(
            passed=False,
            detail="tool emitted no exit_code; cannot verify independently",
            available=False,
        )
    passed = int(actual) == expected
    return VerifierOutcome(passed=passed, detail=f"exit_code={actual} (want {expected})")


def _composite(check: VerificationCheck, ctx: VerifierContext, result: ToolResult) -> VerifierOutcome:
    if not check.children:
        return VerifierOutcome(passed=False, detail="composite has no children")
    outcomes = [evaluate_check(child, ctx, result) for child in check.children]
    passed = any(o.passed for o in outcomes) if check.require == "any" else all(o.passed for o in outcomes)
    available = all(o.available for o in outcomes)
    detail = f"composite({check.require}): " + " | ".join(o.detail for o in outcomes)
    return VerifierOutcome(passed=passed, detail=detail, available=available)


_REGISTRY: dict[VerifierKind, Verifier] = {
    VerifierKind.FILE_EXISTS: _file_exists,
    VerifierKind.FILE_CONTENT: _file_content,
    VerifierKind.PROCESS_RUNNING: _process_running,
    VerifierKind.PORT_LISTENING: _port_listening,
    VerifierKind.HTTP_HEALTH: _http_health,
    VerifierKind.GIT_STATE: _git_state,
    VerifierKind.APPLICATION_RUNNING: _application_running,
    VerifierKind.ACCESSIBILITY_VALUE: _accessibility_value,
    VerifierKind.BROWSER_URL: _browser_url,
    VerifierKind.BROWSER_ELEMENT: _browser_element,
    VerifierKind.EXIT_CODE: _exit_code,
    VerifierKind.COMPOSITE: _composite,
}


def evaluate_check(check: VerificationCheck, ctx: VerifierContext, result: ToolResult) -> VerifierOutcome:
    """Dispatch a check to its verifier. A missing or malformed param fails
    closed with a clear detail rather than raising into the caller."""
    verifier = _REGISTRY.get(check.kind)
    if verifier is None:  # pragma: no cover - registry is exhaustive
        return VerifierOutcome(passed=False, detail=f"no verifier for {check.kind}")
    try:
        return verifier(check, ctx, result)
    except KeyError as exc:
        return VerifierOutcome(passed=False, detail=f"{check.kind.value}: missing param {exc}")
    except (ValueError, TypeError, re.error) as exc:
        return VerifierOutcome(passed=False, detail=f"{check.kind.value}: malformed check ({exc})")
